"""账单和调价。路径不带版本段。"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import assert_browser_origin, get_current_user, require_permission
from app.billing.ledger import LedgerService
from app.billing.money import settlement_currency
from app.billing.pricing import PricingService
from app.core.errors import success
from app.db.models.auth import User
from app.db.session import get_db

router = APIRouter(tags=["billing"], dependencies=[Depends(assert_browser_origin)])


class MeterBody(BaseModel):
    meter: str
    unit_price: str
    cost_price: str
    min_billable_units: int = Field(default=0, ge=0)
    tier_min_tokens: int = Field(default=0, ge=0)


class PublishPriceBody(BaseModel):
    model_id: UUID
    meters: list[MeterBody] = Field(min_length=1)
    schedule_rules: dict | None = None


@router.get("/api/billing")
async def billing(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    currency = settlement_currency(request.app.state.settings.operating_mode)
    data = await LedgerService(db, request.app.state.clock).list_entries(
        user.id,
        currency,
        page=page,
        page_size=page_size,
    )
    return success(request, data)


@router.post("/api/admin/prices")
async def publish_price(
    body: PublishPriceBody,
    request: Request,
    actor: User = Depends(require_permission("model:publish")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    currency = settlement_currency(request.app.state.settings.operating_mode)
    meters = PricingService.meters_from_payload([item.model_dump() for item in body.meters])
    version = await PricingService(db, request.app.state.clock, request.app.state.settings).publish(
        body.model_id,
        currency,
        meters,
        actor.id,
        schedule_rules=body.schedule_rules,
    )
    return success(
        request,
        {"id": str(version.id), "version": version.version, "currency": version.currency},
    )
