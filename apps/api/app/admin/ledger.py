"""管理端只读账本。不提供改历史流水的入口。"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.money import format_money, q
from app.core.paging import clamp_page, page_meta, page_offset
from app.db.models.auth import User
from app.db.models.billing import AccountBalance, AccountLedger


async def admin_ledger(session: AsyncSession, *, page: int, page_size: int) -> dict[str, object]:
    page, page_size = clamp_page(page, page_size)
    balances = await session.execute(
        select(AccountBalance, User.email)
        .join(User, User.id == AccountBalance.user_id)
        .order_by(User.email, AccountBalance.currency, AccountBalance.user_id)
    )
    total = int(await session.scalar(select(func.count()).select_from(AccountLedger)) or 0)
    entries = await session.execute(
        select(AccountLedger, User.email)
        .join(User, User.id == AccountLedger.user_id)
        .order_by(AccountLedger.created_at.desc(), AccountLedger.id.desc())
        .offset(page_offset(page, page_size))
        .limit(page_size)
    )
    meta = page_meta(page, page_size, total)
    return {
        "balances": [_balance(row, email) for row, email in balances.all()],
        "page": meta["page"],
        "page_size": meta["page_size"],
        "total": meta["total"],
        "pages": meta["pages"],
        "entry_total": total,
        "entries": [_entry(row, email) for row, email in entries.all()],
    }


def _balance(row: AccountBalance, email: str) -> dict[str, object]:
    available = q(row.balance - row.held - row.frozen)
    return {
        "user_id": str(row.user_id),
        "email": email,
        "currency": row.currency,
        "balance": format_money(row.balance),
        "held": format_money(row.held),
        "frozen": format_money(row.frozen),
        "available": format_money(available),
    }


def _entry(row: AccountLedger, email: str) -> dict[str, object]:
    return {
        "id": str(row.id),
        "email": email,
        "entry_type": row.entry_type,
        "direction": row.direction,
        "amount": format_money(row.amount),
        "currency": row.currency,
        "balance_after": format_money(row.balance_after),
        "reason": row.reason,
        "reference_type": row.reference_type,
        "reference_id": row.reference_id,
        "created_at": row.created_at.isoformat(),
    }
