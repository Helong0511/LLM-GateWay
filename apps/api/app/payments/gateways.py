"""支付网关：真实渠道查单 + 沙箱替身。

历史实现里 `sessions` / `orders` 只是进程内字典，而且从来没有把
`payment_status` 改成 `paid` 的路径，于是真实 Stripe 回调必然 400、
USDT 回调必然 503 —— 除 mock 外充值 100% 失败，多副本下订单与回调
跨进程也必然失配。

现在的行为：
- 配置了 `STRIPE_SECRET_KEY`：走 Stripe Checkout Sessions API（创建 + 查单）；
- 配置了 `USDT_QUERY_URL`：走服务商查单接口；
- 都未配置：退化为内存沙箱（仅测试 / mock 模式可用），生产环境下单入口会被
  `_assert_channel` 直接拒绝，不再保留「看似可用、实则必失败」的入口。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx
import structlog

from app.core.config import Settings
from app.core.errors import AppError

logger = structlog.get_logger("forgeapi.payments.gateway")


@dataclass(frozen=True)
class CheckoutSession:
    ref: str
    url: str | None


def _cents(amount: Decimal) -> int:
    return int((amount * 100).to_integral_value())


class StripeGateway:
    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self.client = client
        # 沙箱状态：仅在未配置密钥时使用，测试也直接读写它。
        self.sessions: dict[str, dict[str, object]] = {}

    @property
    def configured(self) -> bool:
        return bool(self.settings and self.settings.stripe_secret_key)

    def _base(self) -> str:
        return (self.settings.stripe_api_base if self.settings else "https://api.stripe.com").rstrip("/")

    def _headers(self) -> dict[str, str]:
        key = self.settings.stripe_secret_key if self.settings else ""
        return {"authorization": f"Bearer {key}"}

    async def create(
        self,
        *,
        order_no: str,
        amount: Decimal,
        currency: str,
        product_name: str = "Recharge",
    ) -> CheckoutSession:
        if not self.configured:
            ref = "cs_" + order_no
            self.sessions[ref] = {
                "id": ref,
                "order_no": order_no,
                "amount_total": _cents(amount),
                "currency": currency.lower(),
                "payment_status": "unpaid",
            }
            return CheckoutSession(ref=ref, url=None)

        app_url = (self.settings.public_app_url if self.settings else "").rstrip("/")
        form: dict[str, Any] = {
            "mode": "payment",
            "client_reference_id": order_no,
            "line_items[0][quantity]": "1",
            "line_items[0][price_data][currency]": currency.lower(),
            "line_items[0][price_data][unit_amount]": str(_cents(amount)),
            "line_items[0][price_data][product_data][name]": product_name,
            "metadata[order_no]": order_no,
        }
        if app_url:
            form["success_url"] = f"{app_url}/console/billing?order={order_no}&result=success"
            form["cancel_url"] = f"{app_url}/console/billing?order={order_no}&result=cancel"
        payload = await self._post("/v1/checkout/sessions", form)
        ref = str(payload.get("id") or "")
        if not ref:
            raise AppError(502, "CHANNEL_UPSTREAM_FAILED", details={"channel": "stripe"})
        url = payload.get("url")
        self.sessions[ref] = {
            "id": ref,
            "order_no": order_no,
            "amount_total": payload.get("amount_total"),
            "currency": str(payload.get("currency") or currency.lower()),
            "payment_status": str(payload.get("payment_status") or "unpaid"),
        }
        return CheckoutSession(ref=ref, url=str(url) if isinstance(url, str) else None)

    async def query(self, ref: str | None) -> dict[str, object] | None:
        if not ref:
            return None
        if not self.configured:
            return self.sessions.get(ref)
        payload = await self._get(f"/v1/checkout/sessions/{ref}")
        metadata = payload.get("metadata")
        order_no = None
        if isinstance(metadata, dict):
            order_no = metadata.get("order_no")
        return {
            "id": payload.get("id"),
            "order_no": order_no or payload.get("client_reference_id"),
            "amount_total": payload.get("amount_total"),
            "currency": str(payload.get("currency") or ""),
            "payment_status": str(payload.get("payment_status") or ""),
        }

    async def _post(self, path: str, form: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", path, data=form)

    async def _get(self, path: str) -> dict[str, Any]:
        return await self._request("GET", path)

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        url = self._base() + path
        try:
            if self.client is not None:
                response = await self.client.request(method, url, headers=self._headers(), **kwargs)
            else:
                async with httpx.AsyncClient(timeout=20) as client:
                    response = await client.request(method, url, headers=self._headers(), **kwargs)
        except httpx.HTTPError as exc:
            logger.warning("stripe_unreachable", path=path, error_type=type(exc).__name__)
            raise AppError(503, "DEPENDENCY_UNAVAILABLE") from exc
        if response.status_code >= 400:
            logger.warning("stripe_error", path=path, status=response.status_code)
            raise AppError(502, "CHANNEL_UPSTREAM_FAILED", details={"channel": "stripe"})
        body = response.json()
        if not isinstance(body, dict):
            raise AppError(502, "CHANNEL_UPSTREAM_FAILED", details={"channel": "stripe"})
        return body


class UsdtGateway:
    """USDT 查单。

    真实链上查询与具体服务商强相关，这里只约定一个最小 HTTP 契约：
    `GET {USDT_QUERY_URL}?order_no=&address=&network=` 返回
    `{amount, address, network, tx_hash, confirmations, payer}`。
    """

    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self.client = client
        # 沙箱状态：未配置查单地址时使用，测试直接写入。
        self.orders: dict[str, dict[str, object]] = {}

    @property
    def configured(self) -> bool:
        return bool(self.settings and self.settings.usdt_query_url)

    async def query(self, order_no: str, *, address: str | None, network: str | None) -> dict[str, object] | None:
        if not self.configured:
            return self.orders.get(order_no)
        assert self.settings is not None
        params = {"order_no": order_no}
        if address:
            params["address"] = address
        if network:
            params["network"] = network
        headers: dict[str, str] = {}
        if self.settings.usdt_query_token:
            headers["authorization"] = f"Bearer {self.settings.usdt_query_token}"
        try:
            if self.client is not None:
                response = await self.client.get(
                    self.settings.usdt_query_url, params=params, headers=headers
                )
            else:
                async with httpx.AsyncClient(timeout=20) as client:
                    response = await client.get(
                        self.settings.usdt_query_url, params=params, headers=headers
                    )
        except httpx.HTTPError as exc:
            logger.warning("usdt_unreachable", error_type=type(exc).__name__)
            raise AppError(503, "DEPENDENCY_UNAVAILABLE") from exc
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            logger.warning("usdt_query_error", status=response.status_code)
            raise AppError(502, "CHANNEL_UPSTREAM_FAILED", details={"channel": "usdt"})
        body = response.json()
        if not isinstance(body, dict):
            raise AppError(502, "CHANNEL_UPSTREAM_FAILED", details={"channel": "usdt"})
        return body
