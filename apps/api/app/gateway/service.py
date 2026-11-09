"""用户 API Key 进入 /v1 后的鉴权、预扣、限额和转发。"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.billing.service import BillingService
from app.core.clock import Clock
from app.core.config import Settings
from app.core.errors import AppError
from app.db.models.auth import User
from app.db.models.providers import ModelCatalog, ModelDeployment
from app.gateway.limit import MemoryRateLimiter, MemorySlots
from app.keys.cache import KeyCache
from app.keys.entitlements import effective_allowed_models
from app.keys.service import KeyService
from app.ops.content import record_call

_CLOSED = {
    "/v1/audio/transcriptions",
    "/v1/audio/speech",
    "/v1/files",
    "/v1/batches",
    "/v1/images/generations",
}


@dataclass
class PreparedCall:
    request_id: str
    user_id: UUID
    api_key_id: UUID
    public_model: str
    upstream_model: str
    stream: bool
    slot_key: str
    concurrency_limit: int | None
    payload: dict[str, Any]


class GatewayService:
    def __init__(
        self,
        session: AsyncSession,
        clock: Clock,
        settings: Settings,
        cache: KeyCache,
        limiter: MemoryRateLimiter,
        slots: MemorySlots,
        transport: httpx.AsyncBaseTransport | None,
        *,
        upstream_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.session = session
        self.clock = clock
        self.settings = settings
        self.keys = KeyService(session, clock, cache, settings)
        self.limiter = limiter
        self.slots = slots
        self.transport = transport
        self.client = upstream_client

    async def prepare(
        self,
        *,
        raw_key: str,
        body: dict[str, Any],
        request_id: str,
        ip: str | None,
        require_embeddings: bool,
    ) -> PreparedCall:
        model_name = body.get("model")
        if not isinstance(model_name, str) or not model_name:
            raise AppError(400, "GATEWAY_MODEL_REQUIRED")
        row = await self.keys.authenticate(raw_key, model=model_name, ip=ip)
        user = await self.session.get(User, row.user_id)
        if user is None:
            raise AppError(403, "GATEWAY_KEY_USER_MISSING")
        if user.status != "active":
            raise AppError(403, "GATEWAY_ACCOUNT_UNAVAILABLE")
        catalog = await self._published(model_name)
        if require_embeddings and catalog.supports_embeddings is not True:
            raise AppError(404, "GATEWAY_EMBEDDINGS_UNSUPPORTED")
        estimate = _estimate(body)
        if not self.limiter.allow(self.clock, f"rpm:{row.id}", row.rpm_limit):
            await self._record_failure(user.id, row.id, request_id, model_name, 429, "rate_limited")
            raise AppError(429, "GATEWAY_RPM_LIMIT")
        if not self.limiter.allow(self.clock, f"tpm:{row.id}", row.tpm_limit, cost=estimate):
            await self._record_failure(user.id, row.id, request_id, model_name, 429, "rate_limited")
            raise AppError(429, "GATEWAY_TPM_LIMIT")
        slot_key = str(row.id)
        if not self.slots.acquire(slot_key, row.max_concurrency):
            await self._record_failure(
                user.id, row.id, request_id, model_name, 429, "concurrency_limited"
            )
            raise AppError(429, "GATEWAY_CONCURRENCY_LIMIT")
        try:
            usage = await self.keys.start_usage(user.id, row.id, request_id, model_name)
            usage.is_stream = body.get("stream") is True
            await record_call(
                self.session,
                user_id=user.id,
                model_name=model_name,
                request_id=request_id,
                now=self.clock.now(),
            )
        except Exception:
            self.slots.release(slot_key, row.max_concurrency)
            raise
        try:
            await self._billing().reserve(
                user_id=user.id,
                api_key_id=row.id,
                request_id=request_id,
                catalog_id=catalog.id,
                input_tokens=_estimate(body),
                output_tokens=0 if require_embeddings else _reserve_output(body),
            )
        except AppError as exc:
            self.slots.release(slot_key, row.max_concurrency)
            if exc.status_code == 402:
                await self.keys.finalize_usage(
                    request_id,
                    input_tokens=0,
                    output_tokens=0,
                    http_status=402,
                    finish_reason="insufficient_balance",
                    usage_source="reported",
                    settlement_status="released",
                    user_charge=Decimal("0"),
                )
            raise
        except Exception:
            self.slots.release(slot_key, row.max_concurrency)
            raise
        payload = dict(body)
        payload["model"] = catalog.upstream_name
        if payload.get("stream") is True:
            options = payload.get("stream_options")
            merged = dict(options) if isinstance(options, dict) else {}
            merged["include_usage"] = True
            payload["stream_options"] = merged
        return PreparedCall(
            request_id=request_id,
            user_id=user.id,
            api_key_id=row.id,
            public_model=model_name,
            upstream_model=catalog.upstream_name,
            stream=payload.get("stream") is True,
            slot_key=slot_key,
            concurrency_limit=row.max_concurrency,
            payload=payload,
        )

    async def complete(self, prepared: PreparedCall) -> dict[str, Any]:
        started = self.clock.now()
        try:
            response = await self._post("/v1/chat/completions", prepared.payload)
            latency = _millis(self.clock.now() - started)
            if response.status_code >= 400:
                await self._billing().finish(
                    request_id=prepared.request_id,
                    input_tokens=0,
                    output_tokens=0,
                    http_status=response.status_code,
                    finish_reason="error",
                    latency_ms=latency,
                    usage_source="reported",
                    chargeable=False,
                )
                raise AppError(502, "GATEWAY_UPSTREAM_STATUS")
            try:
                payload = response.json()
            except ValueError:
                await self._billing().finish(
                    request_id=prepared.request_id,
                    input_tokens=0,
                    output_tokens=0,
                    http_status=502,
                    finish_reason="error",
                    latency_ms=latency,
                    usage_source="reported",
                    chargeable=False,
                )
                raise AppError(502, "GATEWAY_UPSTREAM_UNREADABLE") from None
            if isinstance(payload, dict):
                raw_usage = payload.get("usage")
                usage = raw_usage if isinstance(raw_usage, dict) else {}
                await self._billing().finish(
                    request_id=prepared.request_id,
                    input_tokens=_int(usage.get("prompt_tokens")),
                    output_tokens=_int(usage.get("completion_tokens")),
                    http_status=200,
                    finish_reason="stop",
                    latency_ms=latency,
                    usage_source="reported" if usage else "estimated",
                    chargeable=True,
                    cached_tokens=_cached_tokens(usage),
                )
                return payload
            await self._billing().finish(
                request_id=prepared.request_id,
                input_tokens=0,
                output_tokens=0,
                http_status=502,
                finish_reason="error",
                latency_ms=latency,
                usage_source="reported",
                chargeable=False,
            )
            raise AppError(502, "GATEWAY_UPSTREAM_UNREADABLE")
        finally:
            self.slots.release(prepared.slot_key, prepared.concurrency_limit)

    async def stream(
        self,
        prepared: PreparedCall,
        disconnected: Callable[[], Awaitable[bool]],
        sessionmaker: async_sessionmaker[AsyncSession],
    ) -> AsyncIterator[str]:
        started = self.clock.now()
        first_token_ms: int | None = None
        raw_usage: dict[str, Any] | None = None
        finish = "stop"
        status = 200
        try:
            client = self.client or httpx.AsyncClient(transport=self.transport, timeout=60)
            own = self.client is None
            try:
                async with client.stream(
                    "POST",
                    self._url("/v1/chat/completions"),
                    headers=self._headers(),
                    json=prepared.payload,
                ) as response:
                    status = response.status_code
                    async for line in response.aiter_lines():
                        if await disconnected():
                            finish = "cancelled"
                            await response.aclose()
                            break
                        if line.startswith("data:") and first_token_ms is None:
                            first_token_ms = _millis(self.clock.now() - started)
                        parsed = _usage_from_sse(line)
                        if parsed is not None:
                            raw_usage = parsed
                        yield line + "\n"
            finally:
                if own:
                    await client.aclose()
        except httpx.HTTPError:
            status = 502
            finish = "error"
            yield (
                'data: {"error":{"message":"上游暂时繁忙，请稍后再试",'
                '"type":"upstream_error","code":"UPSTREAM_ERROR"}}\n\n'
            )
        finally:
            self.slots.release(prepared.slot_key, prepared.concurrency_limit)
            source = "reported"
            prompt = completion = 0
            cached = 0
            if raw_usage is None:
                source = "estimated"
                prompt = _estimate(prepared.payload)
            else:
                prompt = _int(raw_usage.get("prompt_tokens"))
                completion = _int(raw_usage.get("completion_tokens"))
                cached = _cached_tokens(raw_usage)
            async with sessionmaker() as session:
                billing = BillingService(session, self.clock, self.settings, self.keys.cache)
                await billing.finish(
                    request_id=prepared.request_id,
                    input_tokens=prompt,
                    output_tokens=completion,
                    http_status=status,
                    finish_reason=finish,
                    latency_ms=_millis(self.clock.now() - started),
                    first_token_ms=first_token_ms,
                    usage_source=source,
                    chargeable=status == 200,
                    cached_tokens=cached,
                )
                await session.commit()

    async def list_models(self, raw_key: str) -> dict[str, Any]:
        key = await self.keys.lookup(raw_key)
        # 模型范围由账号决定（用户级 > 套餐级 > 不限），API Key 不再单独配置。
        allowed = await effective_allowed_models(self.session, key.user_id)
        result = await self.session.execute(
            select(ModelCatalog).where(ModelCatalog.status == "published")
        )
        visible = []
        for row in result.scalars().all():
            if allowed is not None and row.public_name not in allowed:
                continue
            visible.append(
                {
                    "id": row.public_name,
                    "object": "model",
                    "owned_by": "forge",
                }
            )
        return {"object": "list", "data": visible}

    async def embeddings(self, prepared: PreparedCall) -> dict[str, Any]:
        started = self.clock.now()
        try:
            response = await self._post("/v1/embeddings", prepared.payload)
            latency = _millis(self.clock.now() - started)
            if response.status_code >= 400:
                await self._billing().finish(
                    request_id=prepared.request_id,
                    input_tokens=0,
                    output_tokens=0,
                    http_status=response.status_code,
                    finish_reason="error",
                    latency_ms=latency,
                    chargeable=False,
                )
                raise AppError(502, "GATEWAY_UPSTREAM_STATUS")
            try:
                payload = response.json()
            except ValueError:
                payload = None
            raw_usage = payload.get("usage") if isinstance(payload, dict) else None
            usage = raw_usage if isinstance(raw_usage, dict) else {}
            await self._billing().finish(
                request_id=prepared.request_id,
                input_tokens=_int(usage.get("prompt_tokens")),
                output_tokens=0,
                http_status=200 if isinstance(payload, dict) else 502,
                finish_reason="stop" if isinstance(payload, dict) else "error",
                latency_ms=latency,
                usage_source="reported" if usage else "estimated",
                chargeable=isinstance(payload, dict),
                cached_tokens=_cached_tokens(usage),
            )
            if not isinstance(payload, dict):
                raise AppError(502, "GATEWAY_UPSTREAM_UNREADABLE")
            return payload
        finally:
            self.slots.release(prepared.slot_key, prepared.concurrency_limit)

    async def _published(self, public_name: str) -> ModelCatalog:
        row = await self.session.scalar(select(ModelCatalog).where(ModelCatalog.public_name == public_name))
        if row is None:
            raise AppError(404, "GATEWAY_MODEL_NOT_FOUND")
        if row.status != "published":
            raise AppError(404, "GATEWAY_MODEL_UNPUBLISHED")
        deployment = await self.session.scalar(
            select(ModelDeployment).where(ModelDeployment.model_id == row.id)
        )
        if deployment is not None and deployment.status != "active":
            raise AppError(404, "GATEWAY_DEPLOYMENT_DISABLED")
        return row

    async def _record_failure(
        self,
        user_id: UUID,
        api_key_id: UUID,
        request_id: str,
        model_name: str,
        http_status: int,
        finish_reason: str,
    ) -> None:
        await self.keys.start_usage(user_id, api_key_id, request_id, model_name)
        await self.keys.finalize_usage(
            request_id,
            input_tokens=0,
            output_tokens=0,
            http_status=http_status,
            finish_reason=finish_reason,
            usage_source="reported",
        )

    async def _post(self, path: str, payload: dict[str, Any]) -> httpx.Response:
        if self.client is not None:
            try:
                return await self.client.post(self._url(path), headers=self._headers(), json=payload)
            except httpx.HTTPError as exc:
                raise AppError(503, "GATEWAY_UPSTREAM_UNREACHABLE") from exc
        async with httpx.AsyncClient(transport=self.transport, timeout=60) as client:
            try:
                return await client.post(self._url(path), headers=self._headers(), json=payload)
            except httpx.HTTPError as exc:
                raise AppError(503, "GATEWAY_UPSTREAM_UNREACHABLE") from exc

    def _url(self, path: str) -> str:
        return self.settings.litellm_base_url.rstrip("/") + path

    def _headers(self) -> dict[str, str]:
        return {"authorization": f"Bearer {self.settings.litellm_master_key}"}

    def _billing(self) -> BillingService:
        return BillingService(self.session, self.clock, self.settings, self.keys.cache)


def closed_path(path: str) -> bool:
    return path in _CLOSED


def _estimate(body: dict[str, Any]) -> int:
    return max(1, len(json.dumps(body, ensure_ascii=False)) // 4)


def _reserve_output(body: dict[str, Any]) -> int:
    raw = body.get("max_tokens")
    if isinstance(raw, int) and 0 < raw <= 8192:
        return raw
    return 256


def _int(value: object) -> int:
    if isinstance(value, int):
        return value
    return 0


def _millis(delta: object) -> int:
    seconds = getattr(delta, "total_seconds", None)
    if seconds is None:
        return 0
    return int(seconds() * 1000)


def _usage_from_sse(line: str) -> dict[str, Any] | None:
    if not line.startswith("data:"):
        return None
    raw = line.removeprefix("data:").strip()
    if raw == "[DONE]":
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    usage = payload.get("usage") if isinstance(payload, dict) else None
    if isinstance(usage, dict):
        return usage
    return None


def _cached_tokens(usage: dict[str, Any]) -> int:
    """从上游 usage 中提取缓存命中 token 数，兼容多家字段名。

    DeepSeek: cache_hit_tokens / prompt_cache_hit_tokens
    OpenRouter: cache_read_input_tokens / cached_tokens
    Anthropic: cache_read_input_tokens
    阿里云 / 火山方舟无独立 cached 字段，直接返回 0
    """
    candidates = (
        "cache_hit_tokens",
        "prompt_cache_hit_tokens",
        "cached_tokens",
        "cache_read_input_tokens",
    )
    for key in candidates:
        val = usage.get(key)
        if isinstance(val, int) and val >= 0:
            return val
    return 0
