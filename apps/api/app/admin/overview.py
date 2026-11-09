"""运营概览。数字只来自当前库里的行数。"""

from __future__ import annotations

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.auth import User
from app.db.models.billing import AccountLedger
from app.db.models.keys import ApiKey
from app.db.models.payments import PaymentOrder
from app.db.models.providers import AuditEvent, ModelCatalog, Provider


async def _count(session: AsyncSession, statement: Select[int]) -> int:
    value = await session.scalar(statement)
    if isinstance(value, tuple):
        return int(value[0])
    return int(value or 0)


async def admin_overview(session: AsyncSession) -> dict[str, int]:
    return {
        "users": await _count(session, select(func.count()).select_from(User)),
        "active_users": await _count(session, select(func.count()).select_from(User).where(User.status == "active")),
        "providers": await _count(session, select(func.count()).select_from(Provider)),
        "published_models": await _count(
            session,
            select(func.count()).select_from(ModelCatalog).where(ModelCatalog.status == "published"),
        ),
        "active_api_keys": await _count(
            session,
            select(func.count()).select_from(ApiKey).where(ApiKey.status == "active"),
        ),
        "payment_orders": await _count(session, select(func.count()).select_from(PaymentOrder)),
        "ledger_entries": await _count(session, select(func.count()).select_from(AccountLedger)),
        "audit_events": await _count(session, select(func.count()).select_from(AuditEvent)),
    }
