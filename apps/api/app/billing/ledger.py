"""三段式预扣和只追加流水。同一幂等键重放返回第一次的流水。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.money import DEFAULT_DIRECTION, ENTRY_TYPES, currency_code, format_money, q
from app.core.clock import Clock
from app.core.errors import BALANCE_INSUFFICIENT, AppError
from app.db.models.billing import AccountBalance, AccountLedger, BalanceHold


@dataclass(frozen=True)
class Settlement:
    amount: Decimal
    status: str
    hold_id: UUID | None
    ledger_entry_id: UUID | None


@dataclass(frozen=True)
class Snapshot:
    currency: str
    balance: Decimal
    held: Decimal
    frozen: Decimal
    available: Decimal


class LedgerService:
    def __init__(self, session: AsyncSession, clock: Clock) -> None:
        self.session = session
        self.clock = clock

    async def post(
        self,
        *,
        user_id: UUID,
        entry_type: str,
        amount: Decimal,
        currency: str,
        idempotency_key: str,
        direction: str | None = None,
        hold_delta: Decimal = Decimal("0"),
        frozen_delta: Decimal = Decimal("0"),
        reference_type: str | None = None,
        reference_id: str | None = None,
        reason: str = "",
        created_by: UUID | None = None,
    ) -> AccountLedger:
        if entry_type not in ENTRY_TYPES:
            raise AppError(400, "LEDGER_ENTRY_TYPE_INVALID", details={"entry_type": entry_type})
        chosen = direction or DEFAULT_DIRECTION.get(entry_type)
        if chosen not in {"C", "D", "N"}:
            raise AppError(400, "LEDGER_DIRECTION_INVALID")
        posted = q(amount)
        if posted <= 0:
            raise AppError(400, "AMOUNT_POSITIVE")
        code = currency_code(currency)
        existing = await self._by_key(idempotency_key)
        if existing is not None:
            return existing
        try:
            async with self.session.begin_nested():
                balance = await self._lock_or_create(user_id, code)
                existing = await self._by_key(idempotency_key)
                if existing is not None:
                    return existing
                credit = posted if chosen == "C" else Decimal("0")
                debit = posted if chosen == "D" else Decimal("0")
                new_balance = q(balance.balance + credit - debit)
                new_held = q(balance.held + hold_delta)
                new_frozen = q(balance.frozen + frozen_delta)
                if min(new_balance, new_held, new_frozen) < 0 or new_balance < q(new_held + new_frozen):
                    raise AppError(402, BALANCE_INSUFFICIENT)
                entry = AccountLedger(
                    user_id=user_id,
                    entry_type=entry_type,
                    direction=chosen,
                    amount=posted,
                    currency=code,
                    idempotency_key=idempotency_key,
                    balance_before=balance.balance,
                    balance_after=new_balance,
                    reference_type=reference_type,
                    reference_id=reference_id,
                    reason=reason[:256],
                    created_at=self.clock.now(),
                    created_by=created_by,
                )
                balance.balance = new_balance
                balance.held = new_held
                balance.frozen = new_frozen
                balance.updated_at = self.clock.now()
                self.session.add(entry)
                await self.session.flush()
                return entry
        except IntegrityError:
            found = await self._by_key(idempotency_key)
            if found is None:
                raise
            return found

    async def place_hold(
        self,
        *,
        user_id: UUID,
        request_id: str,
        amount: Decimal,
        currency: str,
        ttl_seconds: int,
        api_key_id: UUID | None,
        pricing_version_id: UUID | None,
    ) -> BalanceHold:
        key = f"hold:{request_id}"
        existing = await self._hold_by_key(key)
        if existing is not None:
            return existing
        posted = q(amount)
        if posted <= 0:
            raise AppError(400, "HOLD_AMOUNT_POSITIVE")
        if ttl_seconds <= 0:
            raise AppError(400, "HOLD_TTL_POSITIVE")
        now = self.clock.now()
        await self.post(
            user_id=user_id,
            entry_type="hold",
            amount=posted,
            currency=currency,
            idempotency_key=key,
            hold_delta=posted,
            reference_type="request",
            reference_id=request_id,
            reason="hold",
        )
        existing = await self._hold_by_key(key)
        if existing is not None:
            return existing
        hold = BalanceHold(
            user_id=user_id,
            api_key_id=api_key_id,
            amount=posted,
            committed_amount=Decimal("0"),
            currency=currency_code(currency),
            idempotency_key=key,
            status="held",
            expires_at=now + timedelta(seconds=ttl_seconds),
            request_id=request_id,
            pricing_version_id=pricing_version_id,
            created_at=now,
        )
        self.session.add(hold)
        try:
            async with self.session.begin_nested():
                await self.session.flush()
        except IntegrityError:
            found = await self._hold_by_key(key)
            if found is None:
                raise
            return found
        return hold

    async def release_hold(self, request_id: str) -> Settlement:
        hold = await self._hold_by_request(request_id)
        if hold is None:
            return Settlement(Decimal("0"), "released", None, None)
        if hold.status != "held":
            return Settlement(Decimal("0"), hold.status, hold.id, None)
        entry = await self.post(
            user_id=hold.user_id,
            entry_type="hold_release",
            amount=hold.amount,
            currency=hold.currency,
            idempotency_key=f"hold_release:{request_id}",
            hold_delta=-hold.amount,
            reference_type="request",
            reference_id=request_id,
            reason="release_hold",
        )
        hold.status = "released"
        hold.closed_at = self.clock.now()
        await self.session.flush()
        return Settlement(Decimal("0"), "released", hold.id, entry.id)

    async def settle_hold(
        self,
        request_id: str,
        actual: Decimal,
        *,
        user_id: UUID,
        currency: str,
    ) -> Settlement:
        hold = await self._hold_by_request(request_id)
        charged = q(actual)
        if charged < 0:
            raise AppError(400, "SETTLE_AMOUNT_NEGATIVE")
        if hold is None:
            if charged == 0:
                return Settlement(Decimal("0"), "settled", None, None)
            entry = await self.post(
                user_id=user_id,
                entry_type="consume",
                amount=charged,
                currency=currency,
                idempotency_key=f"consume:{request_id}",
                reference_type="request",
                reference_id=request_id,
                reason="catchUpNoHold",
            )
            return Settlement(charged, "settled", None, entry.id)
        if hold.status == "committed":
            return Settlement(hold.committed_amount, "settled", hold.id, None)
        if hold.status == "released":
            return Settlement(Decimal("0"), "released", hold.id, None)
        taken = hold.amount if charged > hold.amount else charged
        remainder = q(hold.amount - taken)
        entry_id: UUID | None = None
        if taken > 0:
            entry = await self.post(
                user_id=hold.user_id,
                entry_type="hold_commit",
                amount=taken,
                currency=hold.currency,
                idempotency_key=f"hold_commit:{request_id}",
                hold_delta=-taken,
                reference_type="request",
                reference_id=request_id,
                reason="settleHold",
            )
            entry_id = entry.id
        if remainder > 0:
            await self.post(
                user_id=hold.user_id,
                entry_type="hold_release",
                amount=remainder,
                currency=hold.currency,
                idempotency_key=f"hold_release:{request_id}",
                hold_delta=-remainder,
                reference_type="request",
                reference_id=request_id,
                reason="refundUnusedHold",
            )
        status = "settled"
        total = taken
        extra = q(charged - taken)
        if extra > 0:
            try:
                extra_entry = await self.post(
                    user_id=hold.user_id,
                    entry_type="consume",
                    amount=extra,
                    currency=hold.currency,
                    idempotency_key=f"consume:{request_id}",
                    reference_type="request",
                    reference_id=request_id,
                    reason="catchUpOverHold",
                )
                entry_id = extra_entry.id
                total = charged
            except AppError as exc:
                if exc.code != BALANCE_INSUFFICIENT:
                    raise
                status = "disputed"
                total = taken
        hold.committed_amount = taken
        hold.status = "committed" if taken > 0 else "released"
        hold.closed_at = self.clock.now()
        await self.session.flush()
        return Settlement(total, status, hold.id, entry_id)

    async def release_expired(self, limit: int = 200) -> int:
        """释放到期预扣。

        `limit` 用于分批：积压时不至于一次性把全表读进内存、也不会撞 worker 的
        job_timeout。返回本批处理条数，调用方可据此继续下一批。
        """
        now = self.clock.now()
        result = await self.session.execute(
            select(BalanceHold)
            .where(BalanceHold.status == "held", BalanceHold.expires_at <= now)
            .order_by(BalanceHold.expires_at.asc())
            .limit(limit)
        )
        count = 0
        for hold in result.scalars().all():
            await self.release_hold(hold.request_id)
            count += 1
        return count

    async def snapshot(self, user_id: UUID, currency: str) -> Snapshot:
        code = currency_code(currency)
        row = await self._select_balance(user_id, code, lock=False)
        if row is None:
            zero = Decimal("0")
            return Snapshot(code, zero, zero, zero, zero)
        available = q(row.balance - row.held - row.frozen)
        return Snapshot(code, row.balance, row.held, row.frozen, available)

    async def list_entries(self, user_id: UUID, currency: str, *, page: int, page_size: int) -> dict[str, object]:
        from app.core.paging import clamp_page, page_meta, page_offset

        page, page_size = clamp_page(page, page_size)
        code = currency_code(currency)
        snap = await self.snapshot(user_id, code)
        total = int(
            await self.session.scalar(
                select(func.count())
                .select_from(AccountLedger)
                .where(AccountLedger.user_id == user_id, AccountLedger.currency == code)
            )
            or 0
        )
        result = await self.session.execute(
            select(AccountLedger)
            .where(AccountLedger.user_id == user_id, AccountLedger.currency == code)
            .order_by(AccountLedger.created_at.desc(), AccountLedger.id.desc())
            .offset(page_offset(page, page_size))
            .limit(page_size)
        )
        rows = result.scalars().all()
        return {
            "ledger_enabled": True,
            "currency": code,
            "balance": format_money(snap.balance),
            "held": format_money(snap.held),
            "frozen": format_money(snap.frozen),
            "available": format_money(snap.available),
            **page_meta(page, page_size, total),
            "entries": [self._public(row) for row in rows],
            "note": "available_formula",
        }

    async def audit(self, user_id: UUID, currency: str) -> dict[str, bool]:
        code = currency_code(currency)
        snap = await self.snapshot(user_id, code)
        entries = await self.session.execute(
            select(AccountLedger).where(AccountLedger.user_id == user_id, AccountLedger.currency == code)
        )
        net = Decimal("0")
        frozen = Decimal("0")
        keys: set[str] = set()
        duplicate = False
        for row in entries.scalars().all():
            if row.idempotency_key in keys:
                duplicate = True
            keys.add(row.idempotency_key)
            if row.direction == "C":
                net += row.amount
            elif row.direction == "D":
                net -= row.amount
            if row.entry_type == "freeze":
                frozen += row.amount
            elif row.entry_type == "unfreeze":
                frozen -= row.amount
        holds = await self.session.execute(
            select(BalanceHold).where(BalanceHold.user_id == user_id, BalanceHold.currency == code)
        )
        held = Decimal("0")
        terminal = True
        for hold in holds.scalars().all():
            if hold.status not in {"held", "committed", "released"}:
                terminal = False
            if hold.status == "held":
                held += hold.amount
            elif hold.closed_at is None:
                terminal = False
        return {
            "balance_matches": snap.balance == q(net),
            "held_matches": snap.held == q(held),
            "frozen_matches": snap.frozen == q(frozen),
            "available_nonnegative": snap.available >= 0,
            "holds_terminal": terminal,
            "idempotency_unique": not duplicate,
        }

    async def _by_key(self, key: str) -> AccountLedger | None:
        result = await self.session.execute(select(AccountLedger).where(AccountLedger.idempotency_key == key))
        return result.scalar_one_or_none()

    async def _hold_by_key(self, key: str) -> BalanceHold | None:
        result = await self.session.execute(select(BalanceHold).where(BalanceHold.idempotency_key == key))
        return result.scalar_one_or_none()

    async def _hold_by_request(self, request_id: str) -> BalanceHold | None:
        # 加行锁串行化"结算/释放"与 worker 的"到期释放"并发，避免 held 双重扣减。
        stmt = select(BalanceHold).where(BalanceHold.request_id == request_id)
        connection = await self.session.connection()
        if connection.dialect.name == "postgresql":
            stmt = stmt.with_for_update()
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _lock_or_create(self, user_id: UUID, currency: str) -> AccountBalance:
        row = await self._select_balance(user_id, currency, lock=True)
        if row is not None:
            return row
        try:
            async with self.session.begin_nested():
                created = AccountBalance(
                    user_id=user_id,
                    currency=currency,
                    balance=Decimal("0"),
                    held=Decimal("0"),
                    frozen=Decimal("0"),
                    updated_at=self.clock.now(),
                )
                self.session.add(created)
                await self.session.flush()
                return created
        except IntegrityError:
            found = await self._select_balance(user_id, currency, lock=True)
            if found is None:
                raise
            return found

    async def _select_balance(self, user_id: UUID, currency: str, *, lock: bool) -> AccountBalance | None:
        stmt = select(AccountBalance).where(AccountBalance.user_id == user_id, AccountBalance.currency == currency)
        if lock:
            connection = await self.session.connection()
            if connection.dialect.name == "postgresql":
                stmt = stmt.with_for_update()
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    def _public(row: AccountLedger) -> dict[str, object]:
        return {
            "id": str(row.id),
            "entry_type": row.entry_type,
            "direction": row.direction,
            "amount": format_money(row.amount),
            "currency": row.currency,
            "balance_before": format_money(row.balance_before),
            "balance_after": format_money(row.balance_after),
            "reference_type": row.reference_type,
            "reference_id": row.reference_id,
            "reason": row.reason,
            "created_at": row.created_at.isoformat(),
        }
