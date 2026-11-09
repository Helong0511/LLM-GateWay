"""ARQ worker。任务只传 ID。探活、过期预扣和超时关单都可以重入。

调度说明（曾经缺失，导致 HOLD_TTL_SECONDS 承诺的「到期自动释放」从未执行）：
- release_expired_holds：每 15 秒一批，每批 200 条，最多连续 10 批
- close_expired_payments：每 5 分钟关闭超时未支付订单
- close_stale_usage：每 10 分钟兜底，把长期 pending 的用量结清并释放预扣
- verify_audit_chain：每天 03:10 校验审计哈希链
"""

from __future__ import annotations

from datetime import datetime

import structlog
from arq import cron
from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.admin.audit import verify_chain
from app.billing.ledger import LedgerService
from app.billing.service import BillingService
from app.core.clock import Clock, SystemClock
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.payments.gateways import StripeGateway, UsdtGateway
from app.payments.service import PaymentService

logger = structlog.get_logger("forgeapi.worker")

# 单个批次条目数与轮次上限：避免积压时任务超时，也避免长时间占用同一事务。
RELEASE_BATCH = 200
RELEASE_ROUNDS = 10


def _now_iso(ctx: dict[str, object]) -> str:
    candidate = ctx.get("clock")
    now = getattr(candidate, "now", None)
    if callable(now):
        value = now()
        if isinstance(value, datetime):
            return value.isoformat()
    return SystemClock().now().isoformat()


async def worker_ping(ctx: dict[str, object]) -> str:
    """探活任务。幂等：重复执行只返回当前时刻，不写财务状态。"""

    stamped = _now_iso(ctx)
    logger.info("worker_ping", at=stamped)
    return stamped


def _clock(ctx: dict[str, object]) -> Clock:
    candidate = ctx.get("clock")
    now = getattr(candidate, "now", None)
    if callable(now):
        return candidate  # type: ignore[return-value]
    return SystemClock()


async def _sessionmaker(
    ctx: dict[str, object],
) -> tuple[async_sessionmaker, AsyncEngine | None]:
    """复用 startup 里建好的连接池；独立调用任务时退化为临时连接池。"""

    maker = ctx.get("sessionmaker")
    if isinstance(maker, async_sessionmaker):
        return maker, None
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True, pool_size=2, max_overflow=2)
    return async_sessionmaker(engine, expire_on_commit=False), engine


async def release_expired_holds(ctx: dict[str, object]) -> int:
    """释放到期预扣。重复执行不会再次改余额。"""

    maker, owned = await _sessionmaker(ctx)
    total = 0
    try:
        async with maker() as session:
            ledger = LedgerService(session, _clock(ctx))
            for _ in range(RELEASE_ROUNDS):
                count = await ledger.release_expired(limit=RELEASE_BATCH)
                await session.commit()
                total += count
                if count < RELEASE_BATCH:
                    break
        if total:
            logger.info("holds_released", count=total)
        return total
    finally:
        if owned is not None:
            await owned.dispose()


async def close_expired_payments(ctx: dict[str, object]) -> int:
    """关闭超时未支付订单，并回收 USDT 尾数。"""

    settings = get_settings()
    maker, owned = await _sessionmaker(ctx)
    try:
        async with maker() as session:
            service = PaymentService(
                session,
                _clock(ctx),
                settings,
                StripeGateway(settings),
                UsdtGateway(settings),
            )
            count = await service.close_expired()
            await session.commit()
            if count:
                logger.info("payments_closed", count=count)
            return count
    finally:
        if owned is not None:
            await owned.dispose()


async def close_stale_usage(ctx: dict[str, object]) -> int:
    """兜底结清：长期停在 pending 的用量记录释放预扣并落 released。

    进程崩溃、上游挂死等场景会让 usage 永远停在 pending。预扣本身会按 TTL
    过期释放，但 usage 状态会一直留在「未结算」，对账与用户账单都会失真。
    """

    settings = get_settings()
    maker, owned = await _sessionmaker(ctx)
    try:
        async with maker() as session:
            service = BillingService(session, _clock(ctx), settings, _NullCache())
            count = await service.close_stale(
                older_than_seconds=settings.hold_ttl_seconds + 120,
                limit=RELEASE_BATCH,
            )
            await session.commit()
            if count:
                logger.info("stale_usage_closed", count=count)
            return count
    finally:
        if owned is not None:
            await owned.dispose()


class _NullCache:
    """worker 侧不使用 KeyCache，给 BillingService 一个空实现即可。"""

    async def get(self, key: str) -> str | None:  # noqa: ARG002
        return None

    async def set(self, key: str, value: str) -> None:  # noqa: ARG002
        return None

    async def delete(self, key: str) -> None:  # noqa: ARG002
        return None


async def verify_audit_chain(ctx: dict[str, object]) -> dict[str, object]:
    """校验审计哈希链。只读，链断裂时记错误日志。"""

    maker, owned = await _sessionmaker(ctx)
    try:
        async with maker() as session:
            status = await verify_chain(session)
        if status["ok"] is not True:
            logger.error("audit_chain_broken", broken_seq=status["broken_seq"], checked=status["checked"])
        else:
            logger.info("audit_chain_ok", checked=status["checked"])
        return status
    finally:
        if owned is not None:
            await owned.dispose()
        _ = ctx


async def startup(ctx: dict[str, object]) -> None:
    settings = get_settings()
    configure_logging(settings)
    engine = create_async_engine(settings.database_url, pool_pre_ping=True, pool_size=2, max_overflow=2)
    ctx["clock"] = SystemClock()
    ctx["engine"] = engine
    ctx["sessionmaker"] = async_sessionmaker(engine, expire_on_commit=False)
    logger.info("worker_started", app_env=settings.app_env, operating_mode=settings.operating_mode)


async def shutdown(ctx: dict[str, object]) -> None:
    engine = ctx.get("engine")
    if isinstance(engine, AsyncEngine):
        await engine.dispose()
    logger.info("worker_stopped")


class WorkerSettings:
    functions = [
        worker_ping,
        release_expired_holds,
        close_expired_payments,
        close_stale_usage,
        verify_audit_chain,
    ]
    # 关键：没有 cron_jobs 时 arq 只做「消费队列」，上面这些任务永远不会被触发。
    cron_jobs = [
        cron(release_expired_holds, second={0, 15, 30, 45}, run_at_startup=True),
        cron(close_expired_payments, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}),
        cron(close_stale_usage, minute={2, 12, 22, 32, 42, 52}),
        cron(verify_audit_chain, hour={3}, minute={10}),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    job_timeout = 120
    max_tries = 3
    health_check_interval = 30
