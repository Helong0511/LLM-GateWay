"""各实体缺失的改、删、列表补齐逻辑。"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.audit import append_audit
from app.auth.rbac import ROLE_IDS
from app.auth.tokens import as_utc
from app.billing.ledger import LedgerService
from app.billing.money import format_money, parse_money, settlement_currency
from app.core.clock import Clock
from app.core.config import Settings
from app.core.errors import AppError
from app.db.models.auth import User, UserRole
from app.db.models.billing import ModelPrice, PricingVersion
from app.db.models.keys import ApiKey
from app.db.models.ops import Announcement, Coupon, CouponRedemption, InvoiceRequest, Ticket
from app.db.models.payments import PaymentOrder, RechargeProduct
from app.db.models.providers import (
    EndpointAllowlist,
    ModelCatalog,
    ModelDeployment,
    Provider,
    ProviderCredential,
)
from app.keys.cache import KeyCache


def _loads(raw: str) -> list[str]:
    try:
        value = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


class CrudExtService:
    def __init__(self, session: AsyncSession, clock: Clock, settings: Settings, key_cache: KeyCache | None = None) -> None:
        self.session = session
        self.clock = clock
        self.settings = settings
        self.key_cache = key_cache

    # --- API Key ---
    async def update_key(
        self,
        user_id: UUID,
        key_id: UUID,
        *,
        name: str | None = None,
        budget_limit: Decimal | None | object = ...,
        rpm_limit: int | None | object = ...,
        tpm_limit: int | None | object = ...,
        max_concurrency: int | None | object = ...,
        ip_allowlist: list[str] | None = None,
        expires_at: datetime | None | object = ...,
        status: str | None = None,
    ) -> dict[str, object]:
        row = await self.session.get(ApiKey, key_id)
        if row is None or row.user_id != user_id:
            raise AppError(404, "KEY_NOT_FOUND")
        if row.status in {"revoked", "expired"} or row.revoked_at is not None:
            raise AppError(409, "KEY_IMMUTABLE_DELETED")
        if status is not None:
            if status not in {"active", "disabled"}:
                raise AppError(
                    400,
                    "VALIDATION_ERROR",
                    "状态只能是 active（启用）或 disabled（停用）；删除请用删除接口",
                )
            if row.status not in {"active", "disabled"}:
                raise AppError(409, "KEY_STATUS_TOGGLE_FORBIDDEN")
            row.status = status
        elif row.status != "active":
            # 停用中的密钥只允许改状态（上面已处理），其它字段需先启用
            raise AppError(409, "KEY_DISABLED_EDIT_FORBIDDEN")
        if name is not None:
            cleaned = name.strip()
            if not cleaned or len(cleaned) > 128:
                raise AppError(400, "KEY_NAME_INVALID")
            row.name = cleaned
        if budget_limit is not ...:
            row.budget_limit = budget_limit  # type: ignore[assignment]
        if rpm_limit is not ...:
            row.rpm_limit = rpm_limit  # type: ignore[assignment]
        if tpm_limit is not ...:
            row.tpm_limit = tpm_limit  # type: ignore[assignment]
        if max_concurrency is not ...:
            row.max_concurrency = max_concurrency  # type: ignore[assignment]
        if ip_allowlist is not None:
            row.ip_allowlist = json.dumps(ip_allowlist)
        if expires_at is not ...:
            row.expires_at = expires_at  # type: ignore[assignment]
        await self.session.flush()
        if self.key_cache is not None:
            await self.key_cache.delete(row.key_hash)
        return {
            "id": str(row.id),
            "name": row.name,
            "status": row.status,
            "allowed_models": _loads(row.allowed_models),
            "budget_limit": format_money(row.budget_limit) if row.budget_limit is not None else None,
            "rpm_limit": row.rpm_limit,
            "tpm_limit": row.tpm_limit,
            "max_concurrency": row.max_concurrency,
            "ip_allowlist": _loads(row.ip_allowlist),
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        }

    # --- Allowlist ---
    async def list_allowlist(self) -> dict[str, object]:
        result = await self.session.execute(select(EndpointAllowlist).order_by(EndpointAllowlist.created_at.desc()))
        rows = [
            {
                "id": str(row.id),
                "host": row.host,
                "approved": row.approved,
                "note": row.note,
                "created_at": as_utc(row.created_at).isoformat(),
            }
            for row in result.scalars().all()
        ]
        return {"items": rows, "total": len(rows)}

    async def revoke_allowlist(self, actor_id: UUID, item_id: UUID) -> dict[str, object]:
        row = await self.session.get(EndpointAllowlist, item_id)
        if row is None:
            raise AppError(404, "ALLOWLIST_NOT_FOUND")
        row.approved = False
        await self.session.flush()
        await append_audit(
            self.session,
            actor_id=actor_id,
            action="allowlist.revoke",
            target_type="endpoint",
            target_id=row.host,
            detail="自建端点已撤销",
            now=self.clock.now(),
        )
        return {"id": str(row.id), "host": row.host, "approved": False}

    # --- Provider ---
    async def update_provider(
        self,
        actor_id: UUID,
        provider_id: UUID,
        *,
        name: str | None = None,
        base_url: str | None = None,
        status: str | None = None,
        priority: int | None = None,
        weight: int | None = None,
    ) -> dict[str, object]:
        row = await self.session.get(Provider, provider_id)
        if row is None:
            raise AppError(404, "PROVIDER_NOT_FOUND")
        if name is not None:
            cleaned = name.strip()
            if not cleaned:
                raise AppError(400, "PROVIDER_NAME_REQUIRED")
            row.name = cleaned[:128]
        if base_url is not None:
            cleaned = base_url.strip()
            if len(cleaned) < 8 or not cleaned.startswith(("http://", "https://")):
                raise AppError(400, "PROVIDER_BASE_URL_INVALID")
            row.base_url = cleaned
        if status is not None:
            if status not in {"active", "disabled"}:
                raise AppError(
                    400,
                    "VALIDATION_ERROR",
                    "状态只能是 active（启用）或 disabled（停用）；删除请用删除接口",
                )
            if row.status == "deleted":
                raise AppError(
                    409,
                    "CONFLICT",
                    "供应商已删除，不能直接启用/停用；请先恢复后再操作",
                )
            row.status = status
        if priority is not None:
            row.priority = priority
        if weight is not None:
            row.weight = weight
        if row.status == "deleted" and (name is not None or base_url is not None or priority is not None or weight is not None):
            raise AppError(409, "PROVIDER_DELETED_IMMUTABLE")
        row.updated_at = self.clock.now()
        await self.session.flush()
        await append_audit(
            self.session,
            actor_id=actor_id,
            action="provider.update",
            target_type="provider",
            target_id=str(row.id),
            detail=row.name,
            now=self.clock.now(),
        )
        return {
            "id": str(row.id),
            "name": row.name,
            "kind": row.kind,
            "base_url": row.base_url,
            "status": row.status,
            "priority": row.priority,
            "weight": row.weight,
        }

    async def revoke_credential(self, actor_id: UUID, credential_id: UUID) -> dict[str, object]:
        row = await self.session.get(ProviderCredential, credential_id)
        if row is None:
            raise AppError(404, "CREDENTIAL_NOT_FOUND")
        row.status = "revoked"
        await self.session.flush()
        await append_audit(
            self.session,
            actor_id=actor_id,
            action="credential.revoke",
            target_type="provider",
            target_id=str(row.provider_id),
            detail=row.label,
            now=self.clock.now(),
        )
        return {"id": str(row.id), "status": row.status}

    # --- Model ---
    async def unpublish_model(self, actor_id: UUID, model_id: UUID) -> dict[str, object]:
        row = await self.session.get(ModelCatalog, model_id)
        if row is None:
            raise AppError(404, "PROVIDER_MODEL_NOT_FOUND")
        row.status = "disabled"
        result = await self.session.execute(select(ModelDeployment).where(ModelDeployment.model_id == row.id))
        for deployment in result.scalars().all():
            deployment.status = "disabled"
        await self.session.flush()
        await append_audit(
            self.session,
            actor_id=actor_id,
            action="model.unpublish",
            target_type="model",
            target_id=str(row.id),
            detail=row.public_name,
            now=self.clock.now(),
        )
        return {"id": str(row.id), "public_name": row.public_name, "status": row.status}

    # --- Pricing ---
    async def list_prices(self, *, model_id: UUID | None = None) -> dict[str, object]:
        statement = (
            select(PricingVersion, ModelCatalog.public_name)
            .join(ModelCatalog, ModelCatalog.id == PricingVersion.model_id)
            .order_by(PricingVersion.created_at.desc(), PricingVersion.id.desc())
            .limit(100)
        )
        if model_id is not None:
            statement = statement.where(PricingVersion.model_id == model_id)
        result = await self.session.execute(statement)
        items = []
        for version, public_name in result.all():
            meters = await self.session.execute(select(ModelPrice).where(ModelPrice.pricing_version_id == version.id))
            items.append(
                {
                    "id": str(version.id),
                    "model_id": str(version.model_id),
                    "public_name": public_name,
                    "version": version.version,
                    "currency": version.currency,
                    "effective_from": as_utc(version.effective_from).isoformat(),
                    "effective_to": as_utc(version.effective_to).isoformat() if version.effective_to else None,
                    "active": version.effective_to is None,
                    "meters": [
                        {
                            "meter": m.meter,
                            "unit_price": format_money(m.unit_price),
                            "cost_price": format_money(m.cost_price),
                            "min_billable_units": m.min_billable_units,
                        }
                        for m in meters.scalars().all()
                    ],
                }
            )
        return {"prices": items, "total": len(items)}

    # --- Roles ---
    async def remove_role(self, actor_id: UUID, user_id: UUID, role_code: str) -> dict[str, object]:
        if role_code == "superadmin":
            raise AppError(403, "ROLE_SUPERADMIN_FORBIDDEN")
        if role_code == "user":
            raise AppError(400, "ROLE_USER_REVOKE_FORBIDDEN")
        if role_code not in ROLE_IDS:
            raise AppError(400, "ROLE_NOT_FOUND")
        target = await self.session.get(User, user_id)
        if target is None:
            raise AppError(404, "USER_NOT_FOUND")
        role_id = UUID(ROLE_IDS[role_code])
        existing = (
            await self.session.execute(
                select(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == role_id)
            )
        ).scalar_one_or_none()
        removed = existing is not None
        if existing is not None:
            await self.session.delete(existing)
        await append_audit(
            self.session,
            actor_id=actor_id,
            action="rbac.remove",
            target_type="user",
            target_id=str(user_id),
            detail=f"role={role_code};removed={'true' if removed else 'false'}",
            now=self.clock.now(),
        )
        return {"user_id": str(user_id), "role": role_code, "removed": removed}

    # --- Coupons ---
    async def update_coupon(
        self,
        actor_id: UUID,
        coupon_id: UUID,
        *,
        enabled: bool | None = None,
        max_uses: int | None = None,
        expires_at: datetime | None | object = ...,
    ) -> dict[str, object]:
        row = await self.session.get(Coupon, coupon_id)
        if row is None:
            raise AppError(404, "COUPON_ADMIN_NOT_FOUND")
        if row.deleted_at is not None:
            raise AppError(409, "COUPON_DELETED_IMMUTABLE")
        if enabled is not None:
            row.enabled = enabled
        if max_uses is not None:
            if max_uses < row.used_count or max_uses < 1:
                raise AppError(400, "COUPON_MAX_USES_INVALID")
            row.max_uses = max_uses
        if expires_at is not ...:
            row.expires_at = expires_at  # type: ignore[assignment]
        await self.session.flush()
        await append_audit(
            self.session,
            actor_id=actor_id,
            action="coupon.update",
            target_type="coupon",
            target_id=str(row.id),
            detail=row.code,
            now=self.clock.now(),
        )
        from app.ops.service import OpsService

        return await OpsService(self.session, self.clock, self.settings).get_coupon(coupon_id)

    async def my_redemptions(self, user_id: UUID) -> dict[str, object]:
        result = await self.session.execute(
            select(CouponRedemption, Coupon)
            .join(Coupon, Coupon.id == CouponRedemption.coupon_id)
            .where(CouponRedemption.user_id == user_id)
            .order_by(CouponRedemption.created_at.desc())
        )
        items = [
            {
                "id": str(redemption.id),
                "code": coupon.code,
                "bonus_amount": format_money(coupon.bonus_amount),
                "currency": coupon.currency,
                "created_at": as_utc(redemption.created_at).isoformat(),
            }
            for redemption, coupon in result.all()
        ]
        return {"redemptions": items, "total": len(items)}

    # --- Announcements ---
    async def update_announcement(
        self, actor_id: UUID, announcement_id: UUID, *, title: str | None = None, body: str | None = None
    ) -> dict[str, object]:
        row = await self.session.get(Announcement, announcement_id)
        if row is None:
            raise AppError(404, "ANNOUNCEMENT_NOT_FOUND")
        if title is not None:
            cleaned = title.strip()
            if not cleaned:
                raise AppError(400, "ANNOUNCEMENT_TITLE_EMPTY")
            row.title = cleaned[:160]
        if body is not None:
            cleaned = body.strip()
            if not cleaned:
                raise AppError(400, "ANNOUNCEMENT_BODY_EMPTY")
            row.body = cleaned
        await self.session.flush()
        await append_audit(
            self.session,
            actor_id=actor_id,
            action="announcement.update",
            target_type="announcement",
            target_id=str(row.id),
            detail=row.slug,
            now=self.clock.now(),
        )
        return {"id": str(row.id), "slug": row.slug, "title": row.title, "published": row.published}

    async def delete_announcement(self, actor_id: UUID, announcement_id: UUID) -> dict[str, object]:
        row = await self.session.get(Announcement, announcement_id)
        if row is None:
            raise AppError(404, "ANNOUNCEMENT_NOT_FOUND")
        slug = row.slug
        await self.session.delete(row)
        await self.session.flush()
        await append_audit(
            self.session,
            actor_id=actor_id,
            action="announcement.delete",
            target_type="announcement",
            target_id=str(announcement_id),
            detail=slug,
            now=self.clock.now(),
        )
        return {"id": str(announcement_id), "deleted": True}

    # --- Tickets / Invoices ---
    async def close_ticket(self, ticket_id: UUID, *, user_id: UUID) -> dict[str, object]:
        row = await self.session.get(Ticket, ticket_id)
        if row is None or row.user_id != user_id:
            raise AppError(404, "TICKET_NOT_FOUND")
        if row.status == "closed":
            return {"id": str(row.id), "status": row.status}
        row.status = "closed"
        row.updated_at = self.clock.now()
        await self.session.flush()
        return {"id": str(row.id), "status": row.status}

    async def cancel_invoice(self, invoice_id: UUID, *, user_id: UUID) -> dict[str, object]:
        row = await self.session.get(InvoiceRequest, invoice_id)
        if row is None or row.user_id != user_id:
            raise AppError(404, "INVOICE_NOT_FOUND")
        if row.status != "requested":
            raise AppError(409, "INVOICE_CANCEL_PENDING_ONLY")
        row.status = "rejected"
        await self.session.flush()
        return {"id": str(row.id), "status": row.status}

    # --- Products ---
    async def list_admin_products(self) -> dict[str, object]:
        result = await self.session.execute(select(RechargeProduct).order_by(RechargeProduct.sort_order, RechargeProduct.amount))
        return {
            "products": [
                {
                    "id": str(row.id),
                    "name": row.name,
                    "amount": format_money(row.amount),
                    "bonus_amount": format_money(row.bonus_amount),
                    "currency": row.currency,
                    "enabled": row.enabled,
                    "deleted": row.deleted_at is not None,
                    "deleted_at": as_utc(row.deleted_at).isoformat() if row.deleted_at else None,
                    "sort_order": row.sort_order,
                    "allowed_models": _loads(row.allowed_models),
                }
                for row in result.scalars().all()
            ]
        }

    async def create_product(
        self,
        actor_id: UUID,
        *,
        name: str,
        amount: str,
        bonus_amount: str = "0",
        currency: str | None = None,
        sort_order: int = 0,
        allowed_models: list[str] | None = None,
    ) -> dict[str, object]:
        code = currency or settlement_currency(self.settings.operating_mode)
        row = RechargeProduct(
            id=uuid4(),
            name=name.strip()[:128],
            amount=parse_money(amount),
            bonus_amount=parse_money(bonus_amount),
            currency=code,
            enabled=True,
            sort_order=sort_order,
            allowed_models=json.dumps(allowed_models or [], ensure_ascii=False),
            created_at=self.clock.now(),
        )
        if row.amount <= 0:
            raise AppError(400, "AMOUNT_POSITIVE")
        self.session.add(row)
        await self.session.flush()
        await append_audit(
            self.session,
            actor_id=actor_id,
            action="product.create",
            target_type="product",
            target_id=str(row.id),
            detail=row.name,
            now=self.clock.now(),
        )
        return {"id": str(row.id), "name": row.name, "amount": format_money(row.amount), "enabled": True}

    async def update_product(
        self,
        actor_id: UUID,
        product_id: UUID,
        *,
        name: str | None = None,
        enabled: bool | None = None,
        bonus_amount: str | None = None,
        sort_order: int | None = None,
        allowed_models: list[str] | None = None,
    ) -> dict[str, object]:
        row = await self.session.get(RechargeProduct, product_id)
        if row is None:
            raise AppError(404, "PRODUCT_NOT_FOUND")
        if row.deleted_at is not None:
            raise AppError(409, "PRODUCT_DELETED_IMMUTABLE")
        if name is not None:
            row.name = name.strip()[:128]
        if enabled is not None:
            row.enabled = enabled
        if bonus_amount is not None:
            row.bonus_amount = parse_money(bonus_amount)
        if sort_order is not None:
            row.sort_order = sort_order
        if allowed_models is not None:
            row.allowed_models = json.dumps(allowed_models, ensure_ascii=False)
        await self.session.flush()
        await append_audit(
            self.session,
            actor_id=actor_id,
            action="product.update",
            target_type="product",
            target_id=str(row.id),
            detail=row.name,
            now=self.clock.now(),
        )
        return {
            "id": str(row.id),
            "name": row.name,
            "enabled": row.enabled,
            "deleted": False,
            "bonus_amount": format_money(row.bonus_amount),
            "sort_order": row.sort_order,
            "allowed_models": _loads(row.allowed_models),
        }

    # --- Ledger adjust ---
    async def adjust_ledger(
        self,
        actor_id: UUID,
        *,
        user_id: UUID,
        amount: str,
        direction: str,
        reason: str,
        idempotency_key: str,
    ) -> dict[str, object]:
        if direction not in {"C", "D"}:
            raise AppError(400, "LEDGER_ADJUST_DIRECTION")
        cleaned = reason.strip()
        if len(cleaned) < 2:
            raise AppError(400, "LEDGER_ADJUST_REASON_REQUIRED")
        user = await self.session.get(User, user_id)
        if user is None:
            raise AppError(404, "USER_NOT_FOUND")
        currency = settlement_currency(self.settings.operating_mode)
        entry = await LedgerService(self.session, self.clock).post(
            user_id=user_id,
            entry_type="adjust",
            amount=parse_money(amount),
            currency=currency,
            idempotency_key=idempotency_key.strip() or f"adjust:{uuid4()}",
            direction=direction,
            reason=cleaned[:256],
            created_by=actor_id,
            reference_type="admin_adjust",
            reference_id=str(actor_id),
        )
        await append_audit(
            self.session,
            actor_id=actor_id,
            action="ledger.adjust",
            target_type="user",
            target_id=str(user_id),
            detail=f"{direction} {format_money(entry.amount)} {currency}",
            now=self.clock.now(),
        )
        return {
            "entry_id": str(entry.id),
            "user_id": str(user_id),
            "direction": direction,
            "amount": format_money(entry.amount),
            "currency": currency,
        }

    # --- Orders cancel ---
    async def cancel_order(self, user_id: UUID, order_no: str) -> dict[str, object]:
        result = await self.session.execute(
            select(PaymentOrder).where(PaymentOrder.order_no == order_no, PaymentOrder.user_id == user_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise AppError(404, "ORDER_NOT_FOUND")
        if row.status != "pending":
            raise AppError(409, "ORDER_CANCEL_PENDING_ONLY")
        row.status = "closed"
        await self.session.flush()
        return {"order_no": row.order_no, "status": row.status}

    async def admin_cancel_order(self, actor_id: UUID, order_no: str) -> dict[str, object]:
        result = await self.session.execute(select(PaymentOrder).where(PaymentOrder.order_no == order_no))
        row = result.scalar_one_or_none()
        if row is None:
            raise AppError(404, "ORDER_NOT_FOUND")
        if row.status != "pending":
            raise AppError(409, "ORDER_CLOSE_PENDING_ONLY")
        row.status = "closed"
        await self.session.flush()
        await append_audit(
            self.session,
            actor_id=actor_id,
            action="order.cancel",
            target_type="payment_order",
            target_id=row.order_no,
            detail="pending→closed",
            now=self.clock.now(),
        )
        return {"order_no": row.order_no, "status": row.status}

    async def delete_product(self, actor_id: UUID, product_id: UUID) -> dict[str, object]:
        row = await self.session.get(RechargeProduct, product_id)
        if row is None:
            raise AppError(404, "PRODUCT_NOT_FOUND")
        if row.deleted_at is not None:
            return {"id": str(row.id), "enabled": row.enabled, "deleted": True}
        now = self.clock.now()
        row.deleted_at = now
        row.enabled = False
        await self.session.flush()
        await append_audit(
            self.session,
            actor_id=actor_id,
            action="product.delete",
            target_type="product",
            target_id=str(row.id),
            detail=row.name,
            now=now,
        )
        return {
            "id": str(row.id),
            "enabled": False,
            "deleted": True,
            "deleted_at": as_utc(now).isoformat(),
        }

    async def restore_product(self, actor_id: UUID, product_id: UUID) -> dict[str, object]:
        row = await self.session.get(RechargeProduct, product_id)
        if row is None:
            raise AppError(404, "PRODUCT_NOT_FOUND")
        if row.deleted_at is None:
            raise AppError(409, "PRODUCT_RESTORE_NOT_DELETED")
        row.deleted_at = None
        # 恢复后保持停用，避免突然对客户可见
        row.enabled = False
        await self.session.flush()
        await append_audit(
            self.session,
            actor_id=actor_id,
            action="product.restore",
            target_type="product",
            target_id=str(row.id),
            detail=row.name,
            now=self.clock.now(),
        )
        return {"id": str(row.id), "enabled": False, "deleted": False, "restored": True}

    async def delete_coupon(self, actor_id: UUID, coupon_id: UUID) -> dict[str, object]:
        row = await self.session.get(Coupon, coupon_id)
        if row is None:
            raise AppError(404, "COUPON_ADMIN_NOT_FOUND")
        if row.deleted_at is not None:
            return {"id": str(row.id), "enabled": row.enabled, "deleted": True}
        now = self.clock.now()
        row.deleted_at = now
        row.enabled = False
        await self.session.flush()
        await append_audit(
            self.session,
            actor_id=actor_id,
            action="coupon.delete",
            target_type="coupon",
            target_id=str(row.id),
            detail=row.code,
            now=now,
        )
        return {
            "id": str(row.id),
            "enabled": False,
            "deleted": True,
            "deleted_at": as_utc(now).isoformat(),
        }

    async def restore_coupon(self, actor_id: UUID, coupon_id: UUID) -> dict[str, object]:
        row = await self.session.get(Coupon, coupon_id)
        if row is None:
            raise AppError(404, "COUPON_ADMIN_NOT_FOUND")
        if row.deleted_at is None:
            raise AppError(409, "COUPON_RESTORE_NOT_DELETED")
        row.deleted_at = None
        row.enabled = False
        await self.session.flush()
        await append_audit(
            self.session,
            actor_id=actor_id,
            action="coupon.restore",
            target_type="coupon",
            target_id=str(row.id),
            detail=row.code,
            now=self.clock.now(),
        )
        return {"id": str(row.id), "enabled": False, "deleted": False, "restored": True}

    async def delete_provider(self, actor_id: UUID, provider_id: UUID) -> dict[str, object]:
        row = await self.session.get(Provider, provider_id)
        if row is None:
            raise AppError(404, "PROVIDER_NOT_FOUND")
        if row.status == "deleted":
            return {"id": str(row.id), "status": "deleted", "deleted": True}
        row.status = "deleted"
        row.updated_at = self.clock.now()
        await self.session.flush()
        await append_audit(
            self.session,
            actor_id=actor_id,
            action="provider.delete",
            target_type="provider",
            target_id=str(row.id),
            detail=row.name,
            now=self.clock.now(),
        )
        return {"id": str(row.id), "status": "deleted", "deleted": True}

    async def restore_provider(self, actor_id: UUID, provider_id: UUID) -> dict[str, object]:
        row = await self.session.get(Provider, provider_id)
        if row is None:
            raise AppError(404, "PROVIDER_NOT_FOUND")
        if row.status != "deleted":
            raise AppError(409, "PROVIDER_RESTORE_NOT_DELETED")
        # 恢复到停用，需管理员再点「启用」，避免误开路由
        row.status = "disabled"
        row.updated_at = self.clock.now()
        await self.session.flush()
        await append_audit(
            self.session,
            actor_id=actor_id,
            action="provider.restore",
            target_type="provider",
            target_id=str(row.id),
            detail=row.name,
            now=self.clock.now(),
        )
        return {"id": str(row.id), "status": row.status, "restored": True}

    async def admin_close_ticket(self, actor_id: UUID, ticket_id: UUID) -> dict[str, object]:
        row = await self.session.get(Ticket, ticket_id)
        if row is None:
            raise AppError(404, "TICKET_NOT_FOUND")
        if row.status == "closed":
            return {"id": str(row.id), "status": row.status}
        row.status = "closed"
        row.updated_at = self.clock.now()
        await self.session.flush()
        await append_audit(
            self.session,
            actor_id=actor_id,
            action="ticket.close",
            target_type="ticket",
            target_id=str(row.id),
            detail="closed",
            now=self.clock.now(),
        )
        return {"id": str(row.id), "status": row.status}

    async def soft_delete_user(self, actor_id: UUID, user_id: UUID) -> dict[str, object]:
        if actor_id == user_id:
            raise AppError(400, "USER_CANNOT_DELETE_SELF")
        target = await self.session.get(User, user_id)
        if target is None or target.status == "deleted":
            raise AppError(404, "USER_NOT_FOUND")
        if target.status not in {"active", "frozen"}:
            raise AppError(400, "USER_DELETE_TYPE_FORBIDDEN")
        target.status = "deleted"
        target.updated_at = self.clock.now()
        await self.session.flush()
        await append_audit(
            self.session,
            actor_id=actor_id,
            action="user.delete",
            target_type="user",
            target_id=str(target.id),
            detail="status=deleted",
            now=self.clock.now(),
        )
        return {"id": str(target.id), "status": "deleted"}
