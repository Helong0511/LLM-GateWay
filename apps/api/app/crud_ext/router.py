"""补齐各实体缺失的改、删、列表接口。路径不带版本段。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import assert_browser_origin, get_current_user, require_permission
from app.core.errors import AppError, success
from app.crud_ext.service import CrudExtService
from app.db.models.auth import User
from app.db.session import get_db
from app.keys.cache import MemoryKeyCache

router = APIRouter(tags=["crud-ext"], dependencies=[Depends(assert_browser_origin)])


class UpdateKeyBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    budget_limit: str | None = None
    clear_budget_limit: bool = False
    rpm_limit: int | None = Field(default=None, ge=1)
    clear_rpm_limit: bool = False
    tpm_limit: int | None = Field(default=None, ge=1)
    clear_tpm_limit: bool = False
    max_concurrency: int | None = Field(default=None, ge=1)
    clear_max_concurrency: bool = False
    ip_allowlist: list[str] | None = None
    expires_at: str | None = None
    clear_expires_at: bool = False
    status: str | None = None


class ProviderUpdateBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    base_url: str | None = Field(default=None, min_length=8, max_length=2048)
    status: str | None = None
    priority: int | None = None
    weight: int | None = Field(default=None, ge=1)


class CouponUpdateBody(BaseModel):
    enabled: bool | None = None
    max_uses: int | None = Field(default=None, ge=1)
    expires_at: str | None = None
    clear_expires_at: bool = False


class AnnouncementUpdateBody(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    body: str | None = Field(default=None, min_length=1)


class ProductCreateBody(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    amount: str
    bonus_amount: str = "0"
    currency: str | None = None
    sort_order: int = 0
    allowed_models: list[str] = Field(default_factory=list)


class ProductUpdateBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    enabled: bool | None = None
    bonus_amount: str | None = None
    sort_order: int | None = None
    allowed_models: list[str] | None = None


class AdjustBody(BaseModel):
    user_id: UUID
    amount: str
    direction: str = Field(pattern="^[CD]$")
    reason: str = Field(min_length=2, max_length=256)


class RemoveRoleBody(BaseModel):
    role_code: str = Field(min_length=1, max_length=32)


def _service(request: Request, db: AsyncSession) -> CrudExtService:
    cache = getattr(request.app.state, "key_cache", None)
    if cache is None:
        cache = MemoryKeyCache(request.app.state.clock)
        request.app.state.key_cache = cache
    return CrudExtService(db, request.app.state.clock, request.app.state.settings, cache)


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


@router.patch("/api/keys/{key_id}")
async def update_key(
    key_id: UUID,
    body: UpdateKeyBody,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    kwargs: dict[str, object] = {}
    if body.name is not None:
        kwargs["name"] = body.name
    if body.clear_budget_limit:
        kwargs["budget_limit"] = None
    elif body.budget_limit is not None:
        kwargs["budget_limit"] = _budget(body.budget_limit)
    if body.clear_rpm_limit:
        kwargs["rpm_limit"] = None
    elif body.rpm_limit is not None:
        kwargs["rpm_limit"] = body.rpm_limit
    if body.clear_tpm_limit:
        kwargs["tpm_limit"] = None
    elif body.tpm_limit is not None:
        kwargs["tpm_limit"] = body.tpm_limit
    if body.clear_max_concurrency:
        kwargs["max_concurrency"] = None
    elif body.max_concurrency is not None:
        kwargs["max_concurrency"] = body.max_concurrency
    if body.ip_allowlist is not None:
        kwargs["ip_allowlist"] = body.ip_allowlist
    if body.clear_expires_at:
        kwargs["expires_at"] = None
    elif body.expires_at is not None:
        kwargs["expires_at"] = _expires(body.expires_at)
    if body.status is not None:
        kwargs["status"] = body.status
    data = await _service(request, db).update_key(user.id, key_id, **kwargs)  # type: ignore[arg-type]
    return success(request, data)


@router.get("/api/admin/allowlist")
async def list_allowlist(
    request: Request,
    _user: User = Depends(require_permission("provider:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(request, await _service(request, db).list_allowlist())


@router.post("/api/admin/allowlist/{item_id}/revoke")
async def revoke_allowlist(
    item_id: UUID,
    request: Request,
    user: User = Depends(require_permission("provider:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(request, await _service(request, db).revoke_allowlist(user.id, item_id))


@router.patch("/api/admin/providers/{provider_id}")
async def update_provider(
    provider_id: UUID,
    body: ProviderUpdateBody,
    request: Request,
    user: User = Depends(require_permission("provider:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    data = await _service(request, db).update_provider(
        user.id,
        provider_id,
        name=body.name,
        base_url=body.base_url,
        status=body.status,
        priority=body.priority,
        weight=body.weight,
    )
    return success(request, data)


@router.post("/api/admin/credentials/{credential_id}/revoke")
async def revoke_credential(
    credential_id: UUID,
    request: Request,
    user: User = Depends(require_permission("provider:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(request, await _service(request, db).revoke_credential(user.id, credential_id))


@router.post("/api/admin/models/{model_id}/unpublish")
async def unpublish_model(
    model_id: UUID,
    request: Request,
    user: User = Depends(require_permission("model:publish")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(request, await _service(request, db).unpublish_model(user.id, model_id))


@router.get("/api/admin/prices")
async def list_prices(
    request: Request,
    model_id: UUID | None = Query(default=None),
    _user: User = Depends(require_permission("model:publish")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(request, await _service(request, db).list_prices(model_id=model_id))


@router.delete("/api/admin/users/{user_id}/roles/{role_code}")
async def remove_role(
    user_id: UUID,
    role_code: str,
    request: Request,
    actor: User = Depends(require_permission("rbac:assign")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(request, await _service(request, db).remove_role(actor.id, user_id, role_code))


@router.post("/api/admin/users/{user_id}/roles/remove")
async def remove_role_post(
    user_id: UUID,
    body: RemoveRoleBody,
    request: Request,
    actor: User = Depends(require_permission("rbac:assign")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(request, await _service(request, db).remove_role(actor.id, user_id, body.role_code))


@router.patch("/api/admin/coupons/{coupon_id}")
async def update_coupon(
    coupon_id: UUID,
    body: CouponUpdateBody,
    request: Request,
    user: User = Depends(require_permission("admin:access")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    expires: datetime | None | object = ...
    if body.clear_expires_at:
        expires = None
    elif body.expires_at is not None:
        expires = _expires(body.expires_at)
    data = await _service(request, db).update_coupon(
        user.id,
        coupon_id,
        enabled=body.enabled,
        max_uses=body.max_uses,
        expires_at=expires,
    )
    return success(request, data)


@router.get("/api/coupons/redemptions")
async def my_redemptions(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(request, await _service(request, db).my_redemptions(user.id))


@router.patch("/api/admin/announcements/{announcement_id}")
async def update_announcement(
    announcement_id: UUID,
    body: AnnouncementUpdateBody,
    request: Request,
    user: User = Depends(require_permission("admin:access")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    data = await _service(request, db).update_announcement(
        user.id, announcement_id, title=body.title, body=body.body
    )
    return success(request, data)


@router.delete("/api/admin/announcements/{announcement_id}")
async def delete_announcement(
    announcement_id: UUID,
    request: Request,
    user: User = Depends(require_permission("admin:access")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(request, await _service(request, db).delete_announcement(user.id, announcement_id))


@router.post("/api/tickets/{ticket_id}/close")
async def close_ticket(
    ticket_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(request, await _service(request, db).close_ticket(ticket_id, user_id=user.id))


@router.post("/api/invoices/{invoice_id}/cancel")
async def cancel_invoice(
    invoice_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(request, await _service(request, db).cancel_invoice(invoice_id, user_id=user.id))


@router.get("/api/admin/products")
async def list_admin_products(
    request: Request,
    _user: User = Depends(require_permission("admin:access")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(request, await _service(request, db).list_admin_products())


@router.post("/api/admin/products")
async def create_product(
    body: ProductCreateBody,
    request: Request,
    user: User = Depends(require_permission("admin:access")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    data = await _service(request, db).create_product(
        user.id,
        name=body.name,
        amount=body.amount,
        bonus_amount=body.bonus_amount,
        currency=body.currency,
        sort_order=body.sort_order,
        allowed_models=body.allowed_models,
    )
    return success(request, data)


@router.patch("/api/admin/products/{product_id}")
async def update_product(
    product_id: UUID,
    body: ProductUpdateBody,
    request: Request,
    user: User = Depends(require_permission("admin:access")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    data = await _service(request, db).update_product(
        user.id,
        product_id,
        name=body.name,
        enabled=body.enabled,
        bonus_amount=body.bonus_amount,
        sort_order=body.sort_order,
        allowed_models=body.allowed_models,
    )
    return success(request, data)


@router.post("/api/admin/ledger/adjust")
async def adjust_ledger(
    body: AdjustBody,
    request: Request,
    user: User = Depends(require_permission("ledger:adjust")),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, object]:
    if not idempotency_key:
        raise AppError(400, "IDEMPOTENCY_KEY_REQUIRED_GENERIC")
    data = await _service(request, db).adjust_ledger(
        user.id,
        user_id=body.user_id,
        amount=body.amount,
        direction=body.direction,
        reason=body.reason,
        idempotency_key=idempotency_key,
    )
    return success(request, data)


@router.post("/api/payments/orders/{order_no}/cancel")
async def cancel_order(
    order_no: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(request, await _service(request, db).cancel_order(user.id, order_no))


@router.post("/api/admin/orders/{order_no}/cancel")
async def admin_cancel_order(
    order_no: str,
    request: Request,
    user: User = Depends(require_permission("admin:access")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(request, await _service(request, db).admin_cancel_order(user.id, order_no))


@router.delete("/api/admin/products/{product_id}")
async def delete_product(
    product_id: UUID,
    request: Request,
    user: User = Depends(require_permission("admin:access")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(request, await _service(request, db).delete_product(user.id, product_id))


@router.post("/api/admin/products/{product_id}/restore")
async def restore_product(
    product_id: UUID,
    request: Request,
    user: User = Depends(require_permission("admin:access")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(request, await _service(request, db).restore_product(user.id, product_id))


@router.delete("/api/admin/coupons/{coupon_id}")
async def delete_coupon(
    coupon_id: UUID,
    request: Request,
    user: User = Depends(require_permission("admin:access")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(request, await _service(request, db).delete_coupon(user.id, coupon_id))


@router.post("/api/admin/coupons/{coupon_id}/restore")
async def restore_coupon(
    coupon_id: UUID,
    request: Request,
    user: User = Depends(require_permission("admin:access")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(request, await _service(request, db).restore_coupon(user.id, coupon_id))


@router.delete("/api/admin/providers/{provider_id}")
async def delete_provider(
    provider_id: UUID,
    request: Request,
    user: User = Depends(require_permission("provider:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(request, await _service(request, db).delete_provider(user.id, provider_id))


@router.post("/api/admin/providers/{provider_id}/restore")
async def restore_provider(
    provider_id: UUID,
    request: Request,
    user: User = Depends(require_permission("provider:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(request, await _service(request, db).restore_provider(user.id, provider_id))


@router.post("/api/admin/tickets/{ticket_id}/close")
async def admin_close_ticket(
    ticket_id: UUID,
    request: Request,
    user: User = Depends(require_permission("admin:access")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(request, await _service(request, db).admin_close_ticket(user.id, ticket_id))


@router.post("/api/admin/users/{user_id}/delete")
async def soft_delete_user(
    user_id: UUID,
    request: Request,
    user: User = Depends(require_permission("admin:access")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(request, await _service(request, db).soft_delete_user(user.id, user_id))
