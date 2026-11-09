"""ARQ worker。任务只传 ID。探活、过期预扣和超时关单都可以重入。"""

from __future__ import annotations

from datetime import datetime

import structlog
from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.admin.audit import verify_chain
from app.billing.ledger import LedgerService
from app.core.clock import Clock, SystemClock
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.payments.gateways import StripeGateway, UsdtGateway
from app.payments.service import PaymentService

logger = structlog.get_logger("forgeapi.worker")


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


async def release_expired_holds(ctx: dict[str, object]) -> int:
    """释放到期预扣。重复执行不会再次改余额。"""

    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as session:
            count = await LedgerService(session, _clock(ctx)).release_expired()
            await session.commit()
            return count
    finally:
        await engine.dispose()


async def close_expired_payments(ctx: dict[str, object]) -> int:
    """关闭超时未支付订单，并回收 USDT 尾数。"""

    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as session:
            service = PaymentService(session, _clock(ctx), settings, StripeGateway(), UsdtGateway())
            count = await service.close_expired()
            await session.commit()
            return count
    finally:
        await engine.dispose()


async def verify_audit_chain(ctx: dict[str, object]) -> dict[str, object]:
    """校验审计哈希链。只读，链断裂时记错误日志。"""

    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as session:
            status = await verify_chain(session)
        if status["ok"] is not True:
            logger.error("audit_chain_broken", broken_seq=status["broken_seq"], checked=status["checked"])
        else:
            logger.info("audit_chain_ok", checked=status["checked"])
        return status
    finally:
        await engine.dispose()
        _ = ctx


async def startup(ctx: dict[str, object]) -> None:
    settings = get_settings()
    configure_logging(settings)
    ctx["clock"] = SystemClock()
    logger.info("worker_started", app_env=settings.app_env, operating_mode=settings.operating_mode)


async def shutdown(ctx: dict[str, object]) -> None:
    logger.info("worker_stopped")
    _ = ctx


class WorkerSettings:
    functions = [worker_ping, release_expired_holds, close_expired_payments, verify_audit_chain]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    job_timeout = 30
    max_tries = 3
    health_check_interval = 30
