"""业务指标采集。

只做只读聚合，且带 15 秒进程内缓存：Prometheus 抓取频率通常 15~30 秒，
没必要每次抓取都扫一遍表。多 worker 由 Prometheus 侧聚合。
"""

from __future__ import annotations

import time
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock
from app.core.metrics import (
    HOLDS_PENDING,
    HOLDS_PENDING_AMOUNT,
    REGISTRY,
    REGISTRY_ERRORS,
    USAGE_PENDING,
)
from app.db.models.billing import BalanceHold
from app.db.models.keys import UsageRecord
from app.db.models.providers import ModelDeployment

CACHE_TTL_SECONDS = 15.0
_cache: tuple[float, dict[str, float]] | None = None


async def business_gauges(session: AsyncSession, clock: Clock) -> dict[str, float]:
    global _cache
    now = time.monotonic()
    if _cache is not None and now - _cache[0] < CACHE_TTL_SECONDS:
        return _cache[1]

    holds = await session.execute(
        select(func.count(), func.coalesce(func.sum(BalanceHold.amount), 0)).where(
            BalanceHold.status == "held"
        )
    )
    hold_count, hold_amount = holds.one()
    pending = await session.scalar(
        select(func.count()).select_from(UsageRecord).where(UsageRecord.settlement_status == "pending")
    )
    registry_errors = await session.scalar(
        select(func.count())
        .select_from(ModelDeployment)
        .where(ModelDeployment.registry_error.is_not(None))
    )

    values = {
        HOLDS_PENDING: float(hold_count or 0),
        HOLDS_PENDING_AMOUNT: float(Decimal(hold_amount or 0)),
        USAGE_PENDING: float(pending or 0),
        REGISTRY_ERRORS: float(registry_errors or 0),
    }
    for name, value in values.items():
        REGISTRY.gauge(name, value)
    _cache = (now, values)
    # clock 参数保留：调用方需要与其它服务一致的时钟语义，缓存过期仍按单调时钟计算。
    _ = clock
    return values


def reset_cache() -> None:
    global _cache
    _cache = None
