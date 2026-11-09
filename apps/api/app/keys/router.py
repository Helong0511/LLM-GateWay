"""API Key 与控制台汇总。路径不带版本段。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import assert_browser_origin, get_current_user
from app.billing.money import settlement_currency
from app.core.errors import AppError, success
from app.db.models.auth import User
from app.db.session import get_db
from app.keys.cache import MemoryKeyCache
from app.keys.service import KeyService
from app.notify.service import NotifyService

router = APIRouter(tags=["keys"], dependencies=[Depends(assert_browser_origin)])


class CreateKeyBody(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    rpm_limit: int | None = Field(default=None, ge=1)
    tpm_limit: int | None = Field(default=None, ge=1)
    max_concurrency: int | None = Field(default=None, ge=1)
    budget_limit: str | None = None
    ip_allowlist: list[str] = Field(default_factory=list)
    expires_at: str | None = None


class RevealKeyBody(BaseModel):
    password: str = Field(min_length=1, max_length=256)


def _service(request: Request, db: AsyncSession) -> KeyService:
    cache = getattr(request.app.state, "key_cache", None)
    if cache is None:
        cache = MemoryKeyCache(request.app.state.clock)
        request.app.state.key_cache = cache
    return KeyService(db, request.app.state.clock, cache, request.app.state.settings)


def _expires(raw: str | None) -> datetime | None:
    if raw is None or raw == "":
        return None
    try:
        value = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise AppError(400, "KEY_EXPIRES_BAD_FORMAT") from exc
    if value.tzinfo is None:
        raise AppError(400, "KEY_EXPIRES_TZ_REQUIRED")
    return value


def _budget(raw: str | None) -> Decimal | None:
    if raw is None or raw == "":
        return None
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise AppError(400, "KEY_BUDGET_BAD_FORMAT") from exc
    if value <= 0:
        raise AppError(400, "KEY_BUDGET_POSITIVE")
    return value


@router.post("/api/keys")
async def create_key(
    body: CreateKeyBody,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    data = await _service(request, db).create(
        user.id,
        body.name,
        rpm_limit=body.rpm_limit,
        tpm_limit=body.tpm_limit,
        max_concurrency=body.max_concurrency,
        budget_limit=_budget(body.budget_limit),
        ip_allowlist=body.ip_allowlist,
        expires_at=_expires(body.expires_at),
    )
    return success(request, data)


@router.get("/api/keys")
async def list_keys(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(request, await _service(request, db).list_for_user(user.id, page=page, page_size=page_size))


@router.post("/api/keys/{key_id}/revoke")
async def revoke_key(
    key_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    data = await _service(request, db).revoke(user.id, key_id)
    await NotifyService(db, request.app.state.clock).key_revoked(user.id, key_id, str(data["name"]))
    return success(request, data)


@router.post("/api/keys/{key_id}/reveal")
async def reveal_key(
    key_id: UUID,
    body: RevealKeyBody,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """二次密码验证后解密明文 API Key；前端不得把该值注入 DOM 持久化。"""
    ip = request.client.host if request.client is not None else None
    data = await _service(request, db).reveal(user, key_id, password=body.password, ip=ip)
    return success(request, data)


@router.delete("/api/keys/{key_id}")
async def delete_key(
    key_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """客户删除密钥：不可恢复（吊销），与「停用」不同。"""
    data = await _service(request, db).revoke(user.id, key_id)
    await NotifyService(db, request.app.state.clock).key_revoked(user.id, key_id, str(data["name"]))
    return success(request, data)


@router.get("/api/usage")
async def list_usage(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    model_id: str | None = None,
    settlement_status: str | None = None,
    sort: str = Query(default="-started_at"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    if sort not in {"started_at", "-started_at"}:
        raise AppError(400, "SORT_FIELD_INVALID")
    if settlement_status not in {None, "pending", "settled", "released", "disputed"}:
        raise AppError(400, "SETTLEMENT_STATUS_INVALID")
    data = await _service(request, db).list_usage(
        user.id,
        page=page,
        page_size=page_size,
        model_id=model_id,
        settlement_status=settlement_status,
        sort=sort,
    )
    return success(request, data)


@router.get("/api/console/summary")
async def console_summary(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    currency = settlement_currency(request.app.state.settings.operating_mode)
    data = await _service(request, db).summary(user.id, currency=currency)
    return success(request, data)
