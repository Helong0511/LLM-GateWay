"""站内通知接口。路径不带版本段。"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import assert_browser_origin, get_current_user
from app.billing.money import parse_money, settlement_currency
from app.core.errors import success
from app.db.models.auth import User
from app.db.session import get_db
from app.notify.service import NotifyService

router = APIRouter(tags=["notifications"], dependencies=[Depends(assert_browser_origin)])


class PreferenceBody(BaseModel):
    balance_alerts_enabled: bool
    warn_high: str
    warn_low: str


def _service(request: Request, db: AsyncSession) -> NotifyService:
    return NotifyService(db, request.app.state.clock)


@router.get("/api/notifications")
async def list_notifications(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    data = await _service(request, db).list_for_user(user.id, page=page, page_size=page_size)
    return success(request, data)


@router.get("/api/notifications/preferences")
async def notification_preferences(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(request, await _service(request, db).preference(user.id))


@router.patch("/api/notifications/preferences")
async def update_notification_preferences(
    body: PreferenceBody,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    data = await _service(request, db).update_preference(
        user.id,
        enabled=body.balance_alerts_enabled,
        warn_high=parse_money(body.warn_high),
        warn_low=parse_money(body.warn_low),
    )
    return success(request, data)


@router.post("/api/notifications/refresh")
async def refresh_notifications(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    currency = settlement_currency(request.app.state.settings.operating_mode)
    data = await _service(request, db).refresh(user.id, currency=currency)
    return success(request, data)


@router.post("/api/notifications/{notification_id}/read")
async def read_notification(
    notification_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    data = await _service(request, db).mark_read(user.id, notification_id)
    return success(request, data)
