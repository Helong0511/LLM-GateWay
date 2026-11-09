"""HTTP 路由。"""

from __future__ import annotations

import hmac

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.core.errors import failure, success
from app.core.metrics import REGISTRY
from app.core.readiness import ReadinessProbes
from app.core.schemas import HealthResponse, MetaResponse, ReadyResponse
from app.ops.metrics import business_gauges

router = APIRouter()
logger = structlog.get_logger(__name__)


@router.get("/healthz", response_model=HealthResponse)
async def healthz(request: Request) -> dict[str, object]:
    return success(request, {"status": "ok"})


@router.get(
    "/readyz",
    response_model=ReadyResponse,
    responses={503: {"model": ReadyResponse}},
)
async def readyz(request: Request) -> dict[str, object] | JSONResponse:
    probes: ReadinessProbes = request.app.state.probes
    postgres_ok, postgres_state = await probes.postgres()
    redis_ok, redis_state = await probes.redis()
    checks = {"postgres": postgres_state, "redis": redis_state}
    if postgres_ok and redis_ok:
        return success(request, {"status": "ready", "checks": checks})
    return failure(
        request,
        503,
        "DEPENDENCY_UNAVAILABLE",
        data={"status": "not_ready", "checks": checks},
    )


@router.get("/api/meta", response_model=MetaResponse)
async def meta(request: Request) -> dict[str, object]:
    settings: Settings = request.app.state.settings
    return success(
        request,
        {
            "product": "ForgeAPI",
            "operating_mode": settings.operating_mode,
            "app_env": settings.app_env,
            "mock_payments_enabled": settings.mock_payments_enabled,
            "demo_models_enabled": settings.demo_models_enabled,
        },
    )


@router.get("/metrics", include_in_schema=False)
async def metrics(request: Request) -> Response:
    """Prometheus 抓取端点。

    不依赖 `get_db`：数据库挂了更要知道进程还在不在，此时仍应返回进程内指标，
    业务 gauge 采集失败只记日志、不拖垮整个抓取。
    """
    settings: Settings = request.app.state.settings
    if not settings.metrics_enabled:
        return Response(content="not found\n", status_code=404, media_type="text/plain")
    if settings.metrics_token:
        presented = request.headers.get("authorization", "")
        expected = f"Bearer {settings.metrics_token}"
        if not hmac.compare_digest(presented, expected):
            return Response(content="unauthorized\n", status_code=401, media_type="text/plain")

    maker = getattr(request.app.state, "sessionmaker", None)
    if maker is not None:
        try:
            async with maker() as session:
                await business_gauges(session, request.app.state.clock)
        except (SQLAlchemyError, OSError) as exc:
            logger.warning("metrics_business_gauges_failed", error_type=type(exc).__name__)

    return Response(
        content=REGISTRY.render(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
