"""充值订单。入账必须验签并且主动查单，同一订单只入账一次。"""

from __future__ import annotations

import hashlib
import json
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.tokens import as_utc
from app.billing.ledger import LedgerService
from app.billing.money import format_money, parse_money, q, settlement_currency
from app.core.clock import Clock
from app.core.config import Settings
from app.core.errors import AppError
from app.db.models.auth import User
from app.db.models.payments import (
    ORDER_STATUSES,
    CryptoDepositIntent,
    IdempotencyRecord,
    PaymentEvent,
    PaymentOrder,
    RechargeProduct,
    RefundOrder,
)
from app.payments.gateways import StripeGateway, UsdtGateway
from app.payments.rules import (
    needs_large_review,
    payment_band,
    rate_within_peg,
    required_confirmations,
)
from app.payments.signatures import (
    ip_allowed,
    redact_payload,
    stripe_signature_ok,
    usdt_signature_ok,
)

_OPEN = {"pending", "confirming"}
_CREDITED = {"completed", "overpaid"}


@dataclass(frozen=True)
class IngestResult:
    status_code: int
    data: dict[str, object] | None = None
    error_code: str | None = None
    error_message: str | None = None


def canonical_hash(payload: Mapping[str, object]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


class PaymentService:
    def __init__(
        self,
        session: AsyncSession,
        clock: Clock,
        settings: Settings,
        stripe: StripeGateway,
        usdt: UsdtGateway,
    ) -> None:
        self.session = session
        self.clock = clock
        self.settings = settings
        self.stripe = stripe
        self.usdt = usdt
        self.ledger = LedgerService(session, clock)

    async def list_products(self) -> dict[str, object]:
        await self.ensure_catalog()
        currency = settlement_currency(self.settings.operating_mode)
        result = await self.session.execute(
            select(RechargeProduct)
            .where(
                RechargeProduct.enabled.is_(True),
                RechargeProduct.deleted_at.is_(None),
                RechargeProduct.currency == currency,
            )
            .order_by(RechargeProduct.sort_order, RechargeProduct.amount)
        )
        return {
            "currency": currency,
            "mock_payments_enabled": self.settings.mock_payments_enabled,
            "products": [self._product(row) for row in result.scalars().all()],
        }

    async def create_order(
        self,
        user_id: UUID,
        *,
        product_id: UUID,
        channel: str,
        idempotency_key: str,
    ) -> dict[str, object]:
        self._require_key(idempotency_key)
        body = {"product_id": str(product_id), "channel": channel}
        digest = canonical_hash(body)
        replay = await self._replay(user_id, idempotency_key, digest)
        if replay is not None:
            return replay
        self._assert_channel(channel)
        product = await self.session.get(RechargeProduct, product_id)
        currency = settlement_currency(self.settings.operating_mode)
        if product is None:
            raise AppError(404, "PRODUCT_NOT_FOUND")
        if product.deleted_at is not None:
            raise AppError(404, "PRODUCT_DELETED")
        if not product.enabled:
            raise AppError(404, "PRODUCT_DISABLED")
        if product.currency != currency:
            raise AppError(400, "PRODUCT_CURRENCY_MISMATCH")
        now = self.clock.now()
        order = PaymentOrder(
            id=uuid4(),
            order_no="FG" + secrets.token_hex(8).upper(),
            user_id=user_id,
            product_id=product.id,
            channel=channel,
            amount=product.amount,
            currency=currency,
            bonus_amount=product.bonus_amount,
            status="pending",
            risk_status="clear",
            reconcile_status="unchecked",
            idempotency_key=idempotency_key,
            request_hash=digest,
            confirmations=0,
            expires_at=now + timedelta(seconds=self.settings.payment_ttl_seconds),
            created_at=now,
            updated_at=now,
        )
        self.session.add(order)
        if channel == "usdt":
            await self._fill_usdt(order)
        elif channel == "stripe":
            self._fill_stripe(order)
        try:
            async with self.session.begin_nested():
                await self.session.flush()
        except IntegrityError as exc:
            raise AppError(409, "IDEMPOTENCY_KEY_REUSED") from exc
        data = self._public(order)
        await self._remember(user_id, idempotency_key, digest, data)
        return data

    async def ensure_catalog(self) -> None:
        currency = settlement_currency(self.settings.operating_mode)
        existing = await self.session.scalars(select(RechargeProduct.amount).where(RechargeProduct.currency == currency))
        have = {q(amount if isinstance(amount, Decimal) else Decimal(str(amount))) for amount in existing.all()}
        now = self.clock.now()
        for amount, name, sort_order in (
            (Decimal("10"), "Starter", 1),
            (Decimal("50"), "Standard", 2),
            (Decimal("100"), "More usage", 3),
        ):
            if q(amount) in have:
                continue
            self.session.add(
                RechargeProduct(
                    name=name,
                    amount=amount,
                    currency=currency,
                    bonus_amount=Decimal("0"),
                    enabled=True,
                    sort_order=sort_order,
                    created_at=now,
                )
            )
        await self.session.flush()

    async def list_admin_orders(
        self,
        *,
        page: int,
        page_size: int,
        status: str | None = None,
        reconcile_status: str | None = None,
        q: str | None = None,
    ) -> dict[str, object]:
        from app.core.paging import clamp_page, page_meta, page_offset

        page, page_size = clamp_page(page, page_size)
        filters = []
        if status:
            if status not in ORDER_STATUSES:
                raise AppError(400, "ORDER_STATUS_FILTER_INVALID", details={"status": status})
            filters.append(PaymentOrder.status == status)
        if reconcile_status:
            if reconcile_status not in {"unchecked", "matched", "disputed"}:
                raise AppError(400, "RECONCILE_STATUS_INVALID")
            filters.append(PaymentOrder.reconcile_status == reconcile_status)
        needle = (q or "").strip().lower()
        if needle:
            filters.append(or_(PaymentOrder.order_no.contains(needle), User.email_normalized.contains(needle)))
        total = int(
            await self.session.scalar(
                select(func.count())
                .select_from(PaymentOrder)
                .join(User, User.id == PaymentOrder.user_id)
                .where(*filters)
            )
            or 0
        )
        result = await self.session.execute(
            select(PaymentOrder, User.email)
            .join(User, User.id == PaymentOrder.user_id)
            .where(*filters)
            .order_by(PaymentOrder.created_at.desc(), PaymentOrder.id.desc())
            .offset(page_offset(page, page_size))
            .limit(page_size)
        )
        orders = []
        for order, email in result.all():
            item = self._public(order)
            item["email"] = email
            orders.append(item)
        return {**page_meta(page, page_size, total), "orders": orders}

    async def set_reconcile_status(self, order_no: str, status: str) -> dict[str, object]:
        if status not in {"unchecked", "matched", "disputed"}:
            raise AppError(400, "RECONCILE_STATUS_INVALID")
        order = await self._by_no(order_no)
        if order is None:
            raise AppError(404, "ORDER_NOT_FOUND")
        if status != "unchecked" and order.status not in _CREDITED:
            raise AppError(400, "RECONCILE_ORDER_NOT_CREDITED")
        order.reconcile_status = status
        order.updated_at = self.clock.now()
        user = await self.session.get(User, order.user_id)
        data = self._public(order)
        data["email"] = user.email if user else ""
        return data

    async def list_admin_refunds(self, *, page: int, page_size: int) -> dict[str, object]:
        from app.core.paging import clamp_page, page_meta, page_offset

        page, page_size = clamp_page(page, page_size)
        total = int(await self.session.scalar(select(func.count()).select_from(RefundOrder)) or 0)
        result = await self.session.execute(
            select(RefundOrder, PaymentOrder.order_no, User.email)
            .join(PaymentOrder, PaymentOrder.id == RefundOrder.order_id)
            .join(User, User.id == PaymentOrder.user_id)
            .order_by(RefundOrder.created_at.desc(), RefundOrder.id.desc())
            .offset(page_offset(page, page_size))
            .limit(page_size)
        )
        refunds = []
        for refund, order_no, email in result.all():
            refunds.append(
                {
                    "id": str(refund.id),
                    "order_no": order_no,
                    "email": email,
                    "amount": format_money(refund.amount),
                    "currency": refund.currency,
                    "status": refund.status,
                    "destination_address": refund.destination_address,
                    "reason": refund.reason,
                    "tx_hash": refund.tx_hash,
                    "requested_by": str(refund.requested_by),
                    "reviewed_by": str(refund.reviewed_by) if refund.reviewed_by else None,
                    "executed_by": str(refund.executed_by) if refund.executed_by else None,
                }
            )
        return {**page_meta(page, page_size, total), "refunds": refunds}

    async def list_orders(self, user_id: UUID, *, page: int = 1, page_size: int = 20) -> dict[str, object]:
        from app.core.paging import clamp_page, page_meta, page_offset

        page, page_size = clamp_page(page, page_size)
        total = int(
            await self.session.scalar(
                select(func.count()).select_from(PaymentOrder).where(PaymentOrder.user_id == user_id)
            )
            or 0
        )
        result = await self.session.execute(
            select(PaymentOrder)
            .where(PaymentOrder.user_id == user_id)
            .order_by(PaymentOrder.created_at.desc(), PaymentOrder.id.desc())
            .offset(page_offset(page, page_size))
            .limit(page_size)
        )
        return {**page_meta(page, page_size, total), "orders": [self._public(row) for row in result.scalars().all()]}

    async def get_order(self, user_id: UUID, order_no: str) -> dict[str, object]:
        order = await self._owned(user_id, order_no)
        return self._public(order)

    async def confirm_mock(self, user_id: UUID, order_no: str) -> dict[str, object]:
        if not self.settings.mock_payments_enabled:
            raise AppError(403, "MOCK_PAYMENTS_DISABLED")
        order = await self._owned(user_id, order_no)
        if order.channel != "mock":
            raise AppError(400, "MOCK_CHANNEL_REQUIRED")
        if order.status in _CREDITED:
            return self._public(order)
        if order.status != "pending":
            raise AppError(400, "ORDER_CONFIRM_STATUS_INVALID", details={"status": order.status})
        if self.clock.now() > as_utc(order.expires_at):
            order.status = "expired"
            order.updated_at = self.clock.now()
            raise AppError(400, "ORDER_EXPIRED")
        await self._credit(order, order.amount, "recharge")
        order.status = "completed"
        order.paid_at = self.clock.now()
        order.updated_at = self.clock.now()
        self._event(order.id, "mock", {"order_no": order.order_no, "result": "completed"}, True)
        return self._public(order)

    async def ingest_stripe(self, raw: bytes, signature: str) -> IngestResult:
        payload, parsed = _loads(raw)
        ok = stripe_signature_ok(self.settings.stripe_webhook_secret, raw, signature, self.clock.now())
        order = await self._order_from_stripe(parsed) if isinstance(parsed, dict) else None
        self._event(order.id if order else None, "stripe", payload, ok)
        if not ok:
            return IngestResult(400, None, "VALIDATION_ERROR", "Stripe 回调签名校验未通过")
        if order is None:
            return IngestResult(404, None, "NOT_FOUND", "回调对应的订单不存在")
        if order.status in _CREDITED:
            return IngestResult(200, self._public(order))
        session = self.stripe.sessions.get(order.provider_ref or "")
        if not isinstance(session, dict) or not _stripe_matches(order, parsed, session):
            return IngestResult(400, None, "VALIDATION_ERROR", "Stripe 回调内容与主动查单结果不一致")
        await self._credit(order, order.amount, "recharge")
        order.status = "completed"
        order.paid_at = self.clock.now()
        order.updated_at = self.clock.now()
        return IngestResult(200, self._public(order))

    async def ingest_usdt(self, raw: bytes, signature: str, ip: str) -> IngestResult:
        payload, parsed = _loads(raw)
        ok = usdt_signature_ok(self.settings.usdt_webhook_secret, raw, signature)
        order = None
        order_no = parsed.get("order_no") if isinstance(parsed, dict) else None
        if isinstance(order_no, str):
            order = await self._by_no(order_no)
        self._event(order.id if order else None, "usdt", payload, ok)
        if not ok:
            return IngestResult(400, None, "VALIDATION_ERROR", "USDT 回调签名校验未通过")
        if not ip_allowed(self.settings.usdt_callback_ips, ip):
            return IngestResult(403, None, "FORBIDDEN", "回调来源 IP 不在白名单")
        if order is None:
            return IngestResult(404, None, "NOT_FOUND", "回调对应的订单不存在")
        if order.channel != "usdt":
            return IngestResult(404, None, "NOT_FOUND", "该订单不是 USDT 渠道")
        if order.status in _CREDITED:
            return IngestResult(200, {"accepted": True, "order": self._public(order)})
        if order.status not in _OPEN:
            return IngestResult(200, {"accepted": False, "order": self._public(order)})
        query = self.usdt.orders.get(order.order_no)
        if not isinstance(query, dict):
            return IngestResult(503, None, "DEPENDENCY_UNAVAILABLE", "主动查单没有返回这笔订单，请稍后再试")
        if not isinstance(parsed, dict) or not _usdt_same(parsed, query):
            return IngestResult(400, None, "VALIDATION_ERROR", "USDT 回调内容与主动查单结果不一致")
        return await self._apply_usdt(order, query)

    async def close_expired(self) -> int:
        now = self.clock.now()
        result = await self.session.execute(
            select(PaymentOrder).where(PaymentOrder.status == "pending", PaymentOrder.expires_at <= now)
        )
        count = 0
        for order in result.scalars().all():
            order.status = "expired"
            order.updated_at = now
            await self._release_tail(order.id, "released")
            count += 1
        return count

    async def reconcile(self, channel: str, bill_date: date, rows: list[tuple[str, Decimal]]) -> dict[str, object]:
        if channel not in {"mock", "stripe", "usdt", "wechat", "alipay"}:
            raise AppError(400, "RECONCILE_CHANNEL_INVALID", details={"channel": channel})
        remote = {order_no: amount for order_no, amount in rows}
        result = await self.session.execute(
            select(PaymentOrder).where(
                PaymentOrder.channel == channel,
                PaymentOrder.paid_at.is_not(None),
                PaymentOrder.status.in_(tuple(_CREDITED)),
            )
        )
        matched = 0
        disputed = 0
        seen: set[str] = set()
        for order in result.scalars().all():
            if order.paid_at is None or as_utc(order.paid_at).date() != bill_date:
                continue
            seen.add(order.order_no)
            expected = order.credited_amount if order.credited_amount is not None else order.amount
            reported = remote.get(order.order_no)
            if reported is not None and reported == expected:
                order.reconcile_status = "matched"
                matched += 1
            else:
                order.reconcile_status = "disputed"
                disputed += 1
        for order_no in remote:
            if order_no not in seen:
                disputed += 1
        return {"channel": channel, "bill_date": bill_date.isoformat(), "matched": matched, "disputed": disputed}

    async def request_refund(
        self,
        actor_id: UUID,
        order_no: str,
        *,
        destination: str,
        reason: str,
    ) -> dict[str, object]:
        order = await self._by_no(order_no)
        if order is None:
            raise AppError(404, "ORDER_NOT_FOUND")
        if order.status not in _CREDITED:
            raise AppError(400, "REFUND_ORDER_NOT_CREDITED", details={"status": order.status})
        if order.channel == "usdt":
            if not order.payer_address or destination != order.payer_address:
                raise AppError(400, "REFUND_USDT_DESTINATION")
        existing = await self.session.execute(select(RefundOrder).where(RefundOrder.order_id == order.id))
        if existing.scalar_one_or_none() is not None:
            raise AppError(409, "REFUND_ALREADY_EXISTS")
        refund = RefundOrder(
            order_id=order.id,
            amount=order.amount,
            currency=order.currency,
            status="requested",
            requested_by=actor_id,
            destination_address=destination,
            reason=reason[:256],
            created_at=self.clock.now(),
        )
        self.session.add(refund)
        await self.session.flush()
        return self._refund_public(refund, order)

    async def review_refund(self, actor_id: UUID, refund_id: UUID) -> dict[str, object]:
        refund, order = await self._refund(refund_id)
        if refund.status != "requested":
            raise AppError(400, "REFUND_NOT_PENDING_REVIEW", details={"status": refund.status})
        if refund.requested_by == actor_id:
            raise AppError(403, "REFUND_SELF_REVIEW_FORBIDDEN")
        refund.status = "reviewed"
        refund.reviewed_by = actor_id
        refund.reviewed_at = self.clock.now()
        return self._refund_public(refund, order)

    async def reject_refund(self, actor_id: UUID, refund_id: UUID, *, reason: str = "") -> dict[str, object]:
        refund, order = await self._refund(refund_id)
        if refund.status not in {"requested", "reviewed"}:
            raise AppError(400, "REFUND_REJECT_STATUS_INVALID", details={"status": refund.status})
        if refund.requested_by == actor_id:
            raise AppError(403, "REFUND_SELF_REJECT_FORBIDDEN")
        refund.status = "rejected"
        refund.reviewed_by = actor_id
        refund.reviewed_at = self.clock.now()
        if reason.strip():
            refund.reason = f"{refund.reason}；拒绝：{reason.strip()[:120]}"
        return self._refund_public(refund, order)

    async def execute_refund(self, actor_id: UUID, refund_id: UUID, tx_hash: str | None) -> dict[str, object]:
        refund, order = await self._refund(refund_id)
        if refund.status != "reviewed":
            raise AppError(400, "REFUND_NOT_REVIEWED", details={"status": refund.status})
        if actor_id in {refund.requested_by, refund.reviewed_by}:
            raise AppError(403, "REFUND_EXECUTOR_MUST_BE_THIRD")
        entry_type = "crypto_refund" if order.channel == "usdt" else "refund"
        await self.ledger.post(
            user_id=order.user_id,
            entry_type=entry_type,
            amount=refund.amount,
            currency=refund.currency,
            idempotency_key=f"{entry_type}:{refund.id}",
            reference_type="refund_order",
            reference_id=str(refund.id),
            reason="refund",
            created_by=actor_id,
        )
        refund.status = "executed"
        refund.executed_by = actor_id
        refund.executed_at = self.clock.now()
        refund.tx_hash = tx_hash
        order.status = "refunded"
        order.updated_at = self.clock.now()
        return self._refund_public(refund, order)

    async def _apply_usdt(self, order: PaymentOrder, query: dict[str, object]) -> IngestResult:
        if query.get("address") != order.pay_address or query.get("network") != order.network:
            return IngestResult(200, {"accepted": False, "reason": "address_or_network_mismatch", "order": self._public(order)})
        payer = query.get("payer")
        if isinstance(payer, str):
            order.payer_address = payer
            if await self._sanctioned(payer, order.network or ""):
                order.risk_status = "sanctioned"
                order.status = "confirming"
                order.updated_at = self.clock.now()
                return IngestResult(
                    200,
                    {
                        "accepted": False,
                        "reason": "sanctioned_address",
                        "order": self._public(order),
                    },
                )
        actual = parse_money(str(query.get("amount")))
        confirmations = query.get("confirmations")
        if not isinstance(confirmations, int):
            return IngestResult(400, None, "VALIDATION_ERROR", "确认数无效")
        order.actual_amount = actual
        order.confirmations = confirmations
        order.tx_hash = str(query.get("tx_hash") or "")
        needed = required_confirmations(order.amount)
        if confirmations < needed:
            order.status = "confirming"
            order.updated_at = self.clock.now()
            return IngestResult(200, {"accepted": False, "reason": "insufficient_confirmations", "order": self._public(order)})
        expected = order.crypto_amount if order.crypto_amount is not None else order.amount
        band = payment_band(expected, actual)
        if band == "underpaid":
            order.status = "underpaid"
            order.updated_at = self.clock.now()
            return IngestResult(200, {"accepted": False, "order": self._public(order)})
        rate = order.locked_rate if order.locked_rate is not None else Decimal("1")
        if band == "overpaid":
            extra = q((actual - expected) / rate)
            cash = q(order.amount + extra)
            order.status = "overpaid"
        else:
            cash = order.amount
            order.status = "completed"
        if needs_large_review(order.amount):
            order.risk_status = "large_review"
        await self._credit(order, cash, "crypto_recharge")
        await self._release_tail(order.id, "used")
        order.paid_at = self.clock.now()
        order.updated_at = self.clock.now()
        return IngestResult(200, {"accepted": True, "order": self._public(order)})

    async def _credit(self, order: PaymentOrder, cash: Decimal, entry_type: str) -> None:
        key = "crypto_confirm" if entry_type == "crypto_recharge" else "recharge"
        await self.ledger.post(
            user_id=order.user_id,
            entry_type=entry_type,
            amount=cash,
            currency=order.currency,
            idempotency_key=f"{key}:{order.order_no}",
            reference_type="payment_order",
            reference_id=order.order_no,
            reason="topup",
        )
        if order.bonus_amount > 0:
            await self.ledger.post(
                user_id=order.user_id,
                entry_type="bonus",
                amount=order.bonus_amount,
                currency=order.currency,
                idempotency_key=f"bonus:{order.order_no}",
                reference_type="payment_order",
                reference_id=order.order_no,
                reason="topup_bonus",
            )
        order.credited_amount = cash

    async def _fill_usdt(self, order: PaymentOrder) -> None:
        if order.amount < self.settings.usdt_min_amount:
            raise AppError(
                400,
                "USDT_AMOUNT_TOO_LOW",
                details={"min_amount": str(self.settings.usdt_min_amount)},
            )
        rate, source = await self._rate()
        if not rate_within_peg(rate, self.settings.rate_deviation_limit):
            raise AppError(400, "FX_DEVIATION_TOO_HIGH")
        now = self.clock.now()
        order.locked_rate = rate
        order.rate_source = source
        order.locked_at = now
        order.crypto_currency = "USDT"
        order.network = "TRC20"
        await self.session.flush()
        if self.settings.usdt_address_mode == "tail":
            if not self.settings.usdt_shared_address:
                raise AppError(503, "USDT_ADDRESS_UNCONFIGURED")
            order.pay_address = self.settings.usdt_shared_address
            tail = await self._allocate_tail(order)
            order.crypto_amount = q(order.amount * rate + tail)
            return
        digest = hashlib.sha256(order.order_no.encode()).hexdigest()
        order.pay_address = "T" + digest[:33]
        order.crypto_amount = q(order.amount * rate)
        self.session.add(
            CryptoDepositIntent(
                order_id=order.id,
                address=order.pay_address,
                network="TRC20",
                tail_amount=Decimal("0"),
                tail_status="reserved",
                expires_at=order.expires_at,
            )
        )

    async def _allocate_tail(self, order: PaymentOrder) -> Decimal:
        await self._release_expired_tails()
        address = order.pay_address or ""
        for index in range(1, 100):
            tail = q(Decimal(index) / Decimal("10000"))
            intent = CryptoDepositIntent(
                order_id=order.id,
                address=address,
                network=order.network or "TRC20",
                tail_amount=tail,
                tail_status="reserved",
                expires_at=order.expires_at,
            )
            self.session.add(intent)
            try:
                async with self.session.begin_nested():
                    await self.session.flush()
                    return tail
            except IntegrityError:
                continue
        raise AppError(503, "USDT_TAIL_POOL_FULL")

    def _fill_stripe(self, order: PaymentOrder) -> None:
        ref = "cs_" + order.order_no
        cents = int(q(order.amount) * 100)
        self.stripe.sessions[ref] = {
            "id": ref,
            "order_no": order.order_no,
            "amount_total": cents,
            "currency": order.currency.lower(),
            "payment_status": "unpaid",
        }
        order.provider_ref = ref

    async def _rate(self) -> tuple[Decimal, str]:
        from app.db.models.billing import ExchangeRate

        result = await self.session.execute(
            select(ExchangeRate)
            .where(ExchangeRate.base_currency == "USDT", ExchangeRate.quote_currency == "USD")
            .order_by(ExchangeRate.captured_at.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return Decimal("1"), "usdt-usd-peg"
        return row.rate, row.source

    async def _sanctioned(self, address: str, network: str) -> bool:
        from app.admin.crypto import is_sanctioned

        return await is_sanctioned(self.session, address, network)

    async def _release_tail(self, order_id: UUID, status: str) -> None:
        result = await self.session.execute(
            select(CryptoDepositIntent).where(CryptoDepositIntent.order_id == order_id)
        )
        intent = result.scalar_one_or_none()
        if intent is not None and intent.tail_status == "reserved":
            intent.tail_status = status

    async def _release_expired_tails(self) -> None:
        now = self.clock.now()
        result = await self.session.execute(
            select(CryptoDepositIntent).where(
                CryptoDepositIntent.tail_status == "reserved",
                CryptoDepositIntent.expires_at <= now,
            )
        )
        for intent in result.scalars().all():
            intent.tail_status = "released"

    def _require_key(self, key: str) -> None:
        if not key or len(key) > 80:
            raise AppError(400, "IDEMPOTENCY_KEY_INVALID")

    def _assert_channel(self, channel: str) -> None:
        if channel == "mock":
            if not self.settings.mock_payments_enabled:
                raise AppError(403, "MOCK_PAYMENTS_DISABLED")
            return
        mode = self.settings.operating_mode
        if mode == "overseas" and channel in {"wechat", "alipay"}:
            raise AppError(400, "CHANNEL_NOT_ALLOWED_OVERSEAS")
        if mode == "mainland" and channel in {"stripe", "usdt"}:
            raise AppError(400, "CHANNEL_NOT_ALLOWED_CN")
        if channel in {"wechat", "alipay"}:
            raise AppError(503, "CHANNEL_NOT_CONFIGURED", details={"channel": channel})
        if channel not in {"stripe", "usdt"}:
            raise AppError(400, "CHANNEL_UNSUPPORTED", details={"channel": channel})

    async def _replay(self, user_id: UUID, key: str, digest: str) -> dict[str, object] | None:
        result = await self.session.execute(
            select(IdempotencyRecord).where(
                IdempotencyRecord.user_id == user_id,
                IdempotencyRecord.idempotency_key == key,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        if row.request_hash != digest:
            raise AppError(409, "IDEMPOTENCY_PAYLOAD_MISMATCH")
        if as_utc(row.expires_at) <= self.clock.now():
            return None
        parsed = json.loads(row.response_body)
        if not isinstance(parsed, dict):
            raise AppError(500, "INTERNAL")
        return parsed

    async def _remember(self, user_id: UUID, key: str, digest: str, data: dict[str, object]) -> None:
        now = self.clock.now()
        self.session.add(
            IdempotencyRecord(
                user_id=user_id,
                idempotency_key=key,
                request_hash=digest,
                status_code=200,
                response_body=json.dumps(data, ensure_ascii=False, sort_keys=True),
                created_at=now,
                expires_at=now + timedelta(hours=24),
            )
        )
        await self.session.flush()

    async def _owned(self, user_id: UUID, order_no: str) -> PaymentOrder:
        order = await self._by_no(order_no)
        if order is None or order.user_id != user_id:
            raise AppError(404, "ORDER_NOT_FOUND")
        return order

    async def _by_no(self, order_no: str) -> PaymentOrder | None:
        result = await self.session.execute(select(PaymentOrder).where(PaymentOrder.order_no == order_no))
        return result.scalar_one_or_none()

    async def _order_from_stripe(self, payload: dict[str, object] | None) -> PaymentOrder | None:
        if not isinstance(payload, dict):
            return None
        data = payload.get("data")
        obj = data.get("object") if isinstance(data, dict) else None
        if not isinstance(obj, dict):
            return None
        order_no = obj.get("client_reference_id")
        if not isinstance(order_no, str):
            return None
        return await self._by_no(order_no)

    async def _refund(self, refund_id: UUID) -> tuple[RefundOrder, PaymentOrder]:
        refund = await self.session.get(RefundOrder, refund_id)
        if refund is None:
            raise AppError(404, "REFUND_NOT_FOUND")
        order = await self.session.get(PaymentOrder, refund.order_id)
        if order is None:
            raise AppError(404, "ORDER_NOT_FOUND")
        return refund, order

    def _event(self, order_id: UUID | None, source: str, payload: dict[str, object], signature_ok: bool) -> None:
        self.session.add(
            PaymentEvent(
                order_id=order_id,
                source=source,
                payload_redacted=redact_payload(payload),
                signature_ok=signature_ok,
                created_at=self.clock.now(),
            )
        )

    def _public(self, order: PaymentOrder) -> dict[str, object]:
        address = order.pay_address or ""
        check = address
        if len(address) >= 16:
            check = address[:8] + "…" + address[-8:]
        return {
            "order_no": order.order_no,
            "channel": order.channel,
            "status": order.status,
            "amount": format_money(order.amount),
            "currency": order.currency,
            "bonus_amount": format_money(order.bonus_amount),
            "credited_amount": format_money(order.credited_amount) if order.credited_amount is not None else None,
            "crypto_amount": format_money(order.crypto_amount) if order.crypto_amount is not None else None,
            "crypto_currency": order.crypto_currency,
            "network": order.network,
            "pay_address": order.pay_address,
            "address_check": check if address else None,
            "payer_address": order.payer_address,
            "locked_rate": format_money(order.locked_rate) if order.locked_rate is not None else None,
            "rate_source": order.rate_source,
            "expires_at": order.expires_at.isoformat(),
            "confirmations": order.confirmations,
            "tx_hash": order.tx_hash,
            "risk_status": order.risk_status,
            "reconcile_status": order.reconcile_status,
            "warning": "usdt_wrong_chain" if order.channel == "usdt" else None,
            "mock": order.channel == "mock",
        }

    @staticmethod
    def _product(row: RechargeProduct) -> dict[str, object]:
        return {
            "id": str(row.id),
            "name": row.name,
            "amount": format_money(row.amount),
            "currency": row.currency,
            "bonus_amount": format_money(row.bonus_amount),
        }

    @staticmethod
    def _refund_public(refund: RefundOrder, order: PaymentOrder) -> dict[str, object]:
        return {
            "id": str(refund.id),
            "order_no": order.order_no,
            "amount": format_money(refund.amount),
            "currency": refund.currency,
            "status": refund.status,
            "destination_address": refund.destination_address,
            "requested_by": str(refund.requested_by),
            "reviewed_by": str(refund.reviewed_by) if refund.reviewed_by else None,
            "executed_by": str(refund.executed_by) if refund.executed_by else None,
        }


def _loads(raw: bytes) -> tuple[dict[str, object], dict[str, object] | None]:
    try:
        parsed = json.loads(raw.decode())
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}, None
    if not isinstance(parsed, dict):
        return {}, None
    clean: dict[str, object] = {}
    for key, value in parsed.items():
        if isinstance(key, str):
            clean[key] = value
    return clean, clean


def _stripe_matches(order: PaymentOrder, payload: dict[str, object] | None, query: dict[str, object]) -> bool:
    if not isinstance(payload, dict):
        return False
    data = payload.get("data")
    obj = data.get("object") if isinstance(data, dict) else None
    if not isinstance(obj, dict):
        return False
    if obj.get("client_reference_id") != order.order_no:
        return False
    if obj.get("payment_status") != "paid" or query.get("payment_status") != "paid":
        return False
    if query.get("order_no") != order.order_no:
        return False
    amount = obj.get("amount_total")
    queried = query.get("amount_total")
    if not isinstance(amount, int) or amount != queried:
        return False
    if obj.get("currency") != order.currency.lower() or query.get("currency") != order.currency.lower():
        return False
    return q(Decimal(amount) / Decimal(100)) == order.amount


def _usdt_same(body: dict[str, object], query: dict[str, object]) -> bool:
    for key in ("amount", "address", "network", "tx_hash", "confirmations", "payer"):
        if body.get(key) != query.get(key):
            return False
    return True
