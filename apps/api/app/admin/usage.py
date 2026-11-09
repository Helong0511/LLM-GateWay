"""管理端调用记录。只读，不含密钥。"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.tokens import as_utc
from app.billing.money import format_money
from app.core.paging import clamp_page, page_meta, page_offset
from app.db.models.auth import User
from app.db.models.keys import UsageRecord


async def admin_usage(session: AsyncSession, *, page: int, page_size: int) -> dict[str, object]:
    page, page_size = clamp_page(page, page_size)
    total = int(await session.scalar(select(func.count()).select_from(UsageRecord)) or 0)
    result = await session.execute(
        select(UsageRecord, User.email)
        .join(User, User.id == UsageRecord.user_id)
        .order_by(UsageRecord.started_at.desc(), UsageRecord.id.desc())
        .offset(page_offset(page, page_size))
        .limit(page_size)
    )
    records = []
    for row, email in result.all():
        records.append(
            {
                "id": str(row.id),
                "email": email,
                "request_id": row.request_id,
                "model_id": row.model_id,
                "started_at": as_utc(row.started_at).isoformat(),
                "input_tokens": row.input_tokens,
                "output_tokens": row.output_tokens,
                "http_status": row.http_status,
                "latency_ms": row.latency_ms,
                "user_charge": format_money(row.user_charge)
                if row.user_charge is not None
                else None,
                "currency": row.currency,
                "settlement_status": row.settlement_status,
            }
        )
    return {**page_meta(page, page_size, total), "records": records}
