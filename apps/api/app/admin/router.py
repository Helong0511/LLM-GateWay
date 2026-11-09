"""管理接口。普通用户没有 admin:access 时返回 403。"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.audit import list_events, verify_chain
from app.admin.crypto import admin_crypto, create_sanction, delete_sanction, update_sanction
from app.admin.ledger import admin_ledger
from app.admin.overview import admin_overview
from app.admin.usage import admin_usage
from app.admin.users import list_users, set_user_models, set_user_status
from app.auth.deps import assert_browser_origin, get_service, require_permission
from app.auth.schemas import AssignRoleBody
from app.auth.service import AuthService
from app.billing.money import parse_money
from app.core.errors import AppError, success
from app.db.models.auth import User
from app.db.session import get_db
from app.keys.cache import MemoryKeyCache
from app.keys.service import KeyService
from app.notify.service import NotifyService

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(assert_browser_origin)])


class UserStatusBody(BaseModel):
    status: Literal["active", "frozen"]


class KeyLimitsBody(BaseModel):
    rpm_limit: int | None = Field(default=None, ge=1)
    tpm_limit: int | None = Field(default=None, ge=1)
    max_concurrency: int | None = Field(default=None, ge=1)
    budget_limit: str | None = None


class UserModelsBody(BaseModel):
    allowed_models: list[str] = Field(default_factory=list)


class SanctionCreateBody(BaseModel):
    address: str = Field(min_length=1, max_length=128)
    network: str = Field(min_length=1, max_length=16)
    source: str = Field(min_length=1, max_length=64)
    reason: str = Field(default="", max_length=256)


class SanctionUpdateBody(BaseModel):
    source: str | None = Field(default=None, min_length=1, max_length=64)
    reason: str | None = Field(default=None, max_length=256)


def _key_service(request: Request, db: AsyncSession) -> KeyService:
    cache = getattr(request.app.state, "key_cache", None)
    if cache is None:
        cache = MemoryKeyCache(request.app.state.clock)
        request.app.state.key_cache = cache
    return KeyService(db, request.app.state.clock, cache, request.app.state.settings)


def _budget(raw: str | None) -> Decimal | None:
    if raw is None or raw.strip() == "":
        return None
    value = parse_money(raw)
    if value <= 0:
        raise AppError(400, "ADMIN_BUDGET_POSITIVE")
    return value


@router.get("/whoami")
async def whoami(
    request: Request,
    user: User = Depends(require_permission("admin:access")),
    service: AuthService = Depends(get_service),
) -> dict[str, object]:
    result = await service.me(user)
    data = dict(result.data)
    data["permissions"] = sorted(await service.repo.permission_codes(user.id))
    return success(request, data)


@router.get("/overview")
async def overview(
    request: Request,
    _user: User = Depends(require_permission("admin:access")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(request, await admin_overview(db))


@router.get("/audit")
async def audit_events(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _user: User = Depends(require_permission("admin:access")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(request, await list_events(db, page=page, page_size=page_size))


@router.get("/audit/verify")
async def audit_verify(
    request: Request,
    _user: User = Depends(require_permission("admin:access")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(request, await verify_chain(db))


@router.get("/ledger")
async def ledger(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _user: User = Depends(require_permission("admin:access")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(request, await admin_ledger(db, page=page, page_size=page_size))


@router.get("/usage")
async def usage(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _user: User = Depends(require_permission("admin:access")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(request, await admin_usage(db, page=page, page_size=page_size))


@router.get("/keys")
async def admin_keys(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None, max_length=128),
    status: str | None = Query(default=None),
    _user: User = Depends(require_permission("admin:access")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(
        request,
        await _key_service(request, db).list_admin(page=page, page_size=page_size, q=q, status=status),
    )


@router.post("/keys/{key_id}/revoke")
async def admin_revoke_key(
    key_id: UUID,
    request: Request,
    actor: User = Depends(require_permission("user:ban")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    data = await _key_service(request, db).admin_revoke(actor.id, key_id)
    owner_id = data.get("user_id")
    if isinstance(owner_id, str):
        await NotifyService(db, request.app.state.clock).key_revoked(UUID(owner_id), key_id, str(data["name"]))
    return success(request, data)


@router.post("/keys/{key_id}/limits")
async def admin_key_limits(
    key_id: UUID,
    body: KeyLimitsBody,
    request: Request,
    actor: User = Depends(require_permission("admin:access")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    data = await _key_service(request, db).admin_limits(
        actor.id,
        key_id,
        rpm_limit=body.rpm_limit,
        tpm_limit=body.tpm_limit,
        max_concurrency=body.max_concurrency,
        budget_limit=_budget(body.budget_limit),
    )
    return success(request, data)


@router.get("/crypto")
async def crypto(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sanctioned_page: int = Query(default=1, ge=1),
    sanctioned_page_size: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None, max_length=128),
    _user: User = Depends(require_permission("admin:access")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(
        request,
        await admin_crypto(
            db,
            page=page,
            page_size=page_size,
            sanctioned_page=sanctioned_page,
            sanctioned_page_size=sanctioned_page_size,
            q=q,
        ),
    )


@router.post("/crypto/sanctions")
async def create_crypto_sanction(
    body: SanctionCreateBody,
    request: Request,
    user: User = Depends(require_permission("admin:access")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    data = await create_sanction(
        db,
        request.app.state.clock,
        user.id,
        address=body.address,
        network=body.network,
        source=body.source,
        reason=body.reason,
    )
    return success(request, data)


@router.patch("/crypto/sanctions/{sanction_id}")
async def update_crypto_sanction(
    sanction_id: UUID,
    body: SanctionUpdateBody,
    request: Request,
    user: User = Depends(require_permission("admin:access")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    if body.source is None and body.reason is None:
        raise AppError(400, "SANCTION_PATCH_EMPTY")
    data = await update_sanction(
        db,
        request.app.state.clock,
        user.id,
        sanction_id,
        source=body.source,
        reason=body.reason,
    )
    return success(request, data)


@router.delete("/crypto/sanctions/{sanction_id}")
async def delete_crypto_sanction(
    sanction_id: UUID,
    request: Request,
    user: User = Depends(require_permission("admin:access")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    data = await delete_sanction(db, request.app.state.clock, user.id, sanction_id)
    return success(request, data)


@router.get("/health")
async def admin_health(
    request: Request,
    _user: User = Depends(require_permission("admin:access")),
) -> dict[str, object]:
    probes = request.app.state.probes
    postgres_ok, postgres_state = await probes.postgres()
    redis_ok, redis_state = await probes.redis()
    settings = request.app.state.settings
    ready = postgres_ok and redis_ok
    return success(
        request,
        {
            "status": "ready" if ready else "not_ready",
            "checks": {"postgres": postgres_state, "redis": redis_state},
            "app_env": settings.app_env,
            "operating_mode": settings.operating_mode,
            "mock_payments_enabled": settings.mock_payments_enabled,
        },
    )


@router.get("/users")
async def users(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
    q: str | None = Query(default=None, max_length=128),
    _user: User = Depends(require_permission("admin:access")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(request, await list_users(db, page=page, page_size=page_size, status=status, q=q))


@router.post("/users/{user_id}/status")
async def user_status(
    user_id: UUID,
    body: UserStatusBody,
    request: Request,
    actor: User = Depends(require_permission("user:ban")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    data = await set_user_status(db, actor=actor, user_id=user_id, status=body.status, now=request.app.state.clock.now())
    return success(request, data)


@router.post("/users/{user_id}/models")
async def user_models(
    user_id: UUID,
    body: UserModelsBody,
    request: Request,
    actor: User = Depends(require_permission("admin:access")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """配置账号级可用模型；所有 API Key 只读继承。"""
    data = await set_user_models(
        db, actor=actor, user_id=user_id, models=body.allowed_models, now=request.app.state.clock.now()
    )
    return success(request, data)


@router.post("/users/{user_id}/roles")
async def assign_role(
    user_id: UUID,
    body: AssignRoleBody,
    request: Request,
    actor: User = Depends(require_permission("rbac:assign")),
    service: AuthService = Depends(get_service),
) -> dict[str, object]:
    result = await service.assign_role(actor, user_id, body.role_code)
    return success(request, result.data)
