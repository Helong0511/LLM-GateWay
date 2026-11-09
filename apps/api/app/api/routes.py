"""HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core.config import Settings
from app.core.errors import failure, success
from app.core.readiness import ReadinessProbes
from app.core.schemas import HealthResponse, MetaResponse, ReadyResponse

router = APIRouter()


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
