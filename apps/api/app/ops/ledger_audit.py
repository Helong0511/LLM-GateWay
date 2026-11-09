"""余额快照对账。

`account_balances` 是 `account_ledger` 的聚合结果。只要某次事务「写了流水但没更新快照」
（历史 bug、人工改库、迁移中断），账面余额就会与流水永久偏离，而扣费逻辑只看快照。
这里提供两件事：

- 只读比对：按流水重算 balance / frozen，按预扣表重算 held，列出差异；
- 修复模式：把快照改成重算值，并写审计链。

修复只改快照，绝不改流水——流水是事实，快照是缓存。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.audit import append_audit
from app.billing.money import q
from app.core.clock import Clock
from app.db.models.billing import AccountBalance, AccountLedger, BalanceHold

_MAX_REPORTED = 200


def _net_expression() -> Any:
    return func.sum(
        case(
            (AccountLedger.direction == "C", AccountLedger.amount),
            (AccountLedger.direction == "D", -AccountLedger.amount),
            else_=Decimal("0"),
        )
    )


def _frozen_expression() -> Any:
    return func.sum(
        case(
            (AccountLedger.entry_type == "freeze", AccountLedger.amount),
            (AccountLedger.entry_type == "unfreeze", -AccountLedger.amount),
            else_=Decimal("0"),
        )
    )


async def reconcile(
    session: AsyncSession,
    clock: Clock,
    *,
    apply: bool,
) -> dict[str, object]:
    ledger = (
        select(
            AccountLedger.user_id.label("user_id"),
            AccountLedger.currency.label("currency"),
            _net_expression().label("net"),
            _frozen_expression().label("frozen"),
        )
        .group_by(AccountLedger.user_id, AccountLedger.currency)
        .subquery()
    )
    holds = (
        select(
            BalanceHold.user_id.label("user_id"),
            BalanceHold.currency.label("currency"),
            func.sum(BalanceHold.amount).label("held"),
        )
        .where(BalanceHold.status == "held")
        .group_by(BalanceHold.user_id, BalanceHold.currency)
        .subquery()
    )

    # 以「流水/预扣」为左表做外连接：既能发现「快照漂移」，也能发现「有流水但没快照」。
    stmt = (
        select(
            func.coalesce(ledger.c.user_id, holds.c.user_id).label("user_id"),
            func.coalesce(ledger.c.currency, holds.c.currency).label("currency"),
            ledger.c.net,
            ledger.c.frozen,
            holds.c.held,
            AccountBalance.balance,
            AccountBalance.held.label("snapshot_held"),
            AccountBalance.frozen.label("snapshot_frozen"),
        )
        .select_from(ledger)
        .outerjoin(
            holds,
            (holds.c.user_id == ledger.c.user_id) & (holds.c.currency == ledger.c.currency),
        )
        .outerjoin(
            AccountBalance,
            (AccountBalance.user_id == func.coalesce(ledger.c.user_id, holds.c.user_id))
            & (AccountBalance.currency == func.coalesce(ledger.c.currency, holds.c.currency)),
        )
    )

    rows = (await session.execute(stmt)).all()
    mismatches: list[dict[str, object]] = []
    mismatch_total = 0
    repaired = 0
    failed = 0
    now = clock.now()

    for row in rows:
        expected_balance = q(row.net or Decimal("0"))
        expected_frozen = q(row.frozen or Decimal("0"))
        expected_held = q(row.held or Decimal("0"))
        snapshot_balance = None if row.balance is None else q(row.balance)
        snapshot_held = None if row.snapshot_held is None else q(row.snapshot_held)
        snapshot_frozen = None if row.snapshot_frozen is None else q(row.snapshot_frozen)
        if (
            snapshot_balance == expected_balance
            and snapshot_held == expected_held
            and snapshot_frozen == expected_frozen
        ):
            continue

        item = {
            "user_id": str(row.user_id),
            "currency": row.currency,
            "snapshot": {
                "balance": _money(snapshot_balance),
                "held": _money(snapshot_held),
                "frozen": _money(snapshot_frozen),
            },
            "expected": {
                "balance": _money(expected_balance),
                "held": _money(expected_held),
                "frozen": _money(expected_frozen),
            },
            "delta": {
                "balance": _money(expected_balance - (snapshot_balance or Decimal("0"))),
                "held": _money(expected_held - (snapshot_held or Decimal("0"))),
                "frozen": _money(expected_frozen - (snapshot_frozen or Decimal("0"))),
            },
        }
        if len(mismatches) < _MAX_REPORTED:
            mismatches.append(item)
        mismatch_total += 1

        if not apply:
            continue
        try:
            await _repair(
                session,
                user_id=row.user_id,
                currency=row.currency,
                balance=expected_balance,
                held=expected_held,
                frozen=expected_frozen,
                now=now,
            )
            await append_audit(
                session,
                actor_id=None,
                action="ledger.reconcile",
                target_type="account",
                target_id=f"{row.user_id}:{row.currency}",
                detail=(
                    f"balance {_money(snapshot_balance)}->{_money(expected_balance)} "
                    f"held {_money(snapshot_held)}->{_money(expected_held)}"
                ),
                now=now,
            )
            repaired += 1
        except IntegrityError:
            failed += 1

    return {
        "checked_accounts": len(rows),
        "mismatch_count": mismatch_total,
        "mismatches": mismatches,
        "apply": apply,
        "repaired": repaired,
        "failed": failed,
        "generated_at": now.isoformat(),
        "truncated": mismatch_total > len(mismatches),
    }


async def _repair(
    session: AsyncSession,
    *,
    user_id: UUID,
    currency: str,
    balance: Decimal,
    held: Decimal,
    frozen: Decimal,
    now: datetime,
) -> None:
    row = await session.get(AccountBalance, (user_id, currency), with_for_update=True)
    async with session.begin_nested():
        if row is None:
            session.add(
                AccountBalance(
                    user_id=user_id,
                    currency=currency,
                    balance=balance,
                    held=held,
                    frozen=frozen,
                    updated_at=now,
                )
            )
        else:
            row.balance = balance
            row.held = held
            row.frozen = frozen
            row.updated_at = now
        await session.flush()


def _money(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return f"{q(value):.8f}"
