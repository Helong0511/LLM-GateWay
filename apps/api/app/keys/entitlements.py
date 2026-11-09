from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.auth import User
from app.db.models.payments import PaymentOrder, RechargeProduct


def parse_models(raw: str | None) -> list[str]:
    """解析存储的 JSON 数组；非法内容一律视为未配置。"""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, str)]


async def effective_allowed_models(session: AsyncSession, user_id: UUID) -> set[str] | None:
    """账号实际可调用的模型。

    优先级：用户级显式配置 > 最近一次已完成订单所属套餐的范围 > 不限（None）。
    """
    user = await session.get(User, user_id)
    if user is not None:
        models = parse_models(user.allowed_models)
        if models:
            return set(models)

    stmt = (
        select(RechargeProduct.allowed_models)
        .join(PaymentOrder, PaymentOrder.product_id == RechargeProduct.id)
        .where(PaymentOrder.user_id == user_id, PaymentOrder.status == "completed")
        .order_by(PaymentOrder.created_at.desc())
        .limit(1)
    )
    raw = (await session.execute(stmt)).scalar_one_or_none()
    models = parse_models(raw)
    return set(models) if models else None
