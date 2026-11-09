"""FastAPI 应用工厂。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import structlog
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.admin.router import router as admin_router
from app.api.routes import router
from app.auth.emailer import build_email_sender
from app.auth.router import router as auth_router
from app.billing.router import router as billing_router
from app.core.clock import SystemClock
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.core.readiness import DefaultProbes, ReadinessProbes
from app.crud_ext.router import router as crud_ext_router
from app.gateway.limit import MemoryRateLimiter, MemorySlots, RedisRateLimiter, RedisSlots
from app.gateway.router import router as gateway_router
from app.keys.cache import MemoryKeyCache
from app.keys.router import router as keys_router
from app.notify.router import router as notify_router
from app.ops.router import router as ops_router
from app.payments.gateways import StripeGateway, UsdtGateway
from app.payments.router import router as payments_router
from app.payments.router import webhook_router
from app.providers.router import catalog_router
from app.providers.router import router as providers_router
from app.security.ssrf import default_resolver


def create_app(
    settings: Settings | None = None,
    probes: ReadinessProbes | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)
    if settings.app_env == "production" and not settings.backup_encryption_key:
        # 不阻断启动：已有部署可能先跑起来再补密钥；但这属于必须修的安全缺口。
        structlog.get_logger("forgeapi").warning(
            "backup_encryption_disabled",
            hint="设置 BACKUP_ENCRYPTION_KEY（Fernet key），否则备份文件是明文",
        )

    docs_url = None if settings.app_env == "production" else "/docs"
    redoc_url = None if settings.app_env == "production" else "/redoc"
    openapi_url = None if settings.app_env == "production" else "/openapi.json"

    engine: AsyncEngine | None = None
    redis: Redis | None = None
    limit_redis: Redis | None = None
    sessionmaker: async_sessionmaker[AsyncSession] | None = None
    if probes is None:
        engine = create_async_engine(
            settings.database_url,
            pool_pre_ping=True,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
        )
        redis = Redis.from_url(settings.redis_url)
        # 限流/并发闸独立连接：与 arq 队列分库，避免缓存淘汰误伤待执行任务。
        limit_redis = Redis.from_url(settings.redis_rate_limit_url)
        probes = DefaultProbes(engine, redis)
        sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    # 全局持久化 httpx.AsyncClient：连接池复用，避免每次新建 SSL/TLS 握手
    # pool_size=20 / max_overflow=30 / keepalive=30s → 足够支撑 gateway 并发 + probe
    upstream_client = httpx.AsyncClient(
        timeout=httpx.Timeout(60.0, connect=15.0),
        limits=httpx.Limits(max_connections=50, max_keepalive_connections=20, keepalive_expiry=30.0),
        follow_redirects=False,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        await upstream_client.aclose()
        if engine is not None:
            await engine.dispose()
        if redis is not None:
            await redis.aclose()
        if limit_redis is not None:
            await limit_redis.aclose()

    app = FastAPI(
        title="ForgeAPI",
        version="0.1.0",
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.redis = redis
    app.state.probes = probes
    app.state.sessionmaker = sessionmaker
    app.state.clock = SystemClock()
    app.state.email_sender = build_email_sender(settings)
    app.state.key_cache = MemoryKeyCache(app.state.clock)
    # 限流与并发闸优先走 Redis：多副本时才能得到全局限额。
    if limit_redis is not None:
        app.state.rate_limit_redis = limit_redis
        app.state.rate_limiter = RedisRateLimiter(limit_redis)
        app.state.slots = RedisSlots(limit_redis)
    else:
        app.state.rate_limiter = MemoryRateLimiter()
        app.state.slots = MemorySlots()
    app.state.ssrf_resolver = default_resolver
    app.state.upstream_client = upstream_client
    app.state.stripe_gateway = StripeGateway(settings)
    app.state.usdt_gateway = UsdtGateway(settings)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-Id", "Idempotency-Key"],
    )
    app.add_middleware(RequestContextMiddleware, max_body_bytes=settings.max_body_bytes)
    register_exception_handlers(app)

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> Response:
        return Response(status_code=204)

    app.include_router(router)
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(keys_router)
    app.include_router(notify_router)
    app.include_router(providers_router)
    app.include_router(catalog_router)
    app.include_router(gateway_router)
    app.include_router(billing_router)
    app.include_router(payments_router)
    app.include_router(ops_router)
    app.include_router(crud_ext_router)
    app.include_router(webhook_router)
    return app


app = create_app()
