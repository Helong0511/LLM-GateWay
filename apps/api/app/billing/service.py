"""把价格、预扣和调用记录接在同一次结算里。"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.ledger import LedgerService, Settlement
from app.billing.money import format_money, q, settlement_currency
from app.billing.pricing import PricingService
from app.core.clock import Clock
from app.core.config import Settings
from app.core.errors import AppError
from app.db.models.billing import BalanceHold, UsageSettlement
from app.db.models.keys import ApiKey, UsageRecord
from app.keys.cache import KeyCache
from app.keys.service import KeyService


class BillingService:
    def __init__(self, session: AsyncSession, clock: Clock, settings: Settings, cache: KeyCache) -> None:
        self.session = session
        self.clock = clock
        self.settings = settings
        self.ledger = LedgerService(session, clock)
        self.pricing = PricingService(session, clock, settings)
        self.keys = KeyService(session, clock, cache, settings)

    async def reserve(
        self,
        *,
        user_id: UUID,
        api_key_id: UUID | None,
        request_id: str,
        catalog_id: UUID,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        currency = settlement_currency(self.settings.operating_mode)
        version = await self.pricing.active(catalog_id, currency)
        if version is None:
            await self._stamp(request_id, None, None)
            return
        quote = await self.pricing.quote(version.id, input_tokens, output_tokens, 0, at=self.clock.now())
        await self._stamp(request_id, version.id, quote.snapshot_json)
        if quote.user_charge <= 0:
            return
        await self._check_budget(api_key_id, quote.user_charge)
        await self.ledger.place_hold(
            user_id=user_id,
            request_id=request_id,
            amount=quote.user_charge,
            currency=currency,
            ttl_seconds=self.settings.hold_ttl_seconds,
            api_key_id=api_key_id,
            pricing_version_id=version.id,
        )

    async def finish(
        self,
        *,
        request_id: str,
        input_tokens: int,
        output_tokens: int,
        http_status: int,
        finish_reason: str,
        latency_ms: int | None = None,
        first_token_ms: int | None = None,
        usage_source: str = "reported",
        cached_tokens: int = 0,
        chargeable: bool,
    ) -> None:
        usage = await self._usage(request_id)
        if not chargeable:
            result = await self.ledger.release_hold(request_id)
            await self._close(usage, result, Decimal("0"), "released", input_tokens, output_tokens, cached_tokens)
            await self.keys.finalize_usage(
                request_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                http_status=http_status,
                finish_reason=finish_reason,
                latency_ms=latency_ms,
                first_token_ms=first_token_ms,
                usage_source=usage_source,
                settlement_status="released",
                user_charge=Decimal("0"),
                cached_tokens=cached_tokens,
            )
            return
        actual = Decimal("0")
        provider_cost = Decimal("0")
        snapshot = usage.unit_price_snapshot
        if usage.pricing_version_id is not None:
            quote = await self.pricing.quote(
                usage.pricing_version_id,
                input_tokens,
                output_tokens,
                cached_tokens,
                at=self.clock.now(),
            )
            actual = quote.user_charge
            provider_cost = quote.provider_cost
            snapshot = quote.snapshot_json
        currency = usage.currency or settlement_currency(self.settings.operating_mode)
        try:
            result = await self.ledger.settle_hold(
                request_id,
                actual,
                user_id=usage.user_id,
                currency=currency,
            )
        except AppError as exc:
            if exc.code != "INSUFFICIENT_BALANCE":
                raise
            result = Settlement(Decimal("0"), "disputed", None, None)
        if usage.api_key_id is not None and result.amount > 0:
            key = await self.session.get(ApiKey, usage.api_key_id)
            if key is not None:
                key.budget_spent = q(Decimal(str(key.budget_spent)) + result.amount)
        await self._close(usage, result, provider_cost, result.status, input_tokens, output_tokens, cached_tokens)
        await self.keys.finalize_usage(
            request_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            http_status=http_status,
            finish_reason=finish_reason,
            latency_ms=latency_ms,
            first_token_ms=first_token_ms,
            usage_source=usage_source,
            settlement_status=result.status,
            user_charge=result.amount,
            pricing_version_id=usage.pricing_version_id,
            unit_price_snapshot=snapshot,
            provider_cost=provider_cost,
            cached_tokens=cached_tokens,
        )

    async def _check_budget(self, api_key_id: UUID | None, amount: Decimal) -> None:
        if api_key_id is None:
            return
        key = await self.session.get(ApiKey, api_key_id)
        if key is None or key.budget_limit is None:
            return
        inflight = await self.session.execute(
            select(func.coalesce(func.sum(BalanceHold.amount), 0)).where(
                BalanceHold.api_key_id == api_key_id,
                BalanceHold.status == "held",
            )
        )
        already = Decimal(str(inflight.scalar_one()))
        if q(Decimal(str(key.budget_spent)) + already + amount) > key.budget_limit:
            raise AppError(402, "KEY_BUDGET_EXHAUSTED")

    async def _stamp(self, request_id: str, version_id: UUID | None, snapshot: str | None) -> None:
        usage = await self._usage(request_id)
        usage.currency = settlement_currency(self.settings.operating_mode)
        if version_id is not None:
            usage.pricing_version_id = version_id
        if snapshot is not None:
            usage.unit_price_snapshot = snapshot

    async def _usage(self, request_id: str) -> UsageRecord:
        result = await self.session.execute(select(UsageRecord).where(UsageRecord.request_id == request_id))
        row = result.scalar_one_or_none()
        if row is None:
            raise AppError(404, "BILLING_USAGE_NOT_FOUND")
        return row

    async def _close(
        self,
        usage: UsageRecord,
        result: Settlement,
        provider_cost: Decimal,
        status: str,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int,
    ) -> None:
        _ = (input_tokens, output_tokens, cached_tokens, provider_cost)
        self.session.add(
            UsageSettlement(
                usage_record_id=usage.id,
                status=status,
                hold_id=result.hold_id,
                ledger_entry_id=result.ledger_entry_id,
                settled_at=self.clock.now(),
            )
        )

    def format_snapshot_balance(self, snap_balance: Decimal, snap_held: Decimal, snap_frozen: Decimal) -> dict[str, str]:
        available = q(snap_balance - snap_held - snap_frozen)
        return {
            "balance": format_money(snap_balance),
            "held": format_money(snap_held),
            "frozen": format_money(snap_frozen),
            "available": format_money(available),
        }
