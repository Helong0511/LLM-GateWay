"""工单、发票、公告和优惠券。优惠券兑换记一笔赠送流水，同一用户同一码只入账一次。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.audit import append_audit
from app.auth.tokens import as_utc
from app.billing.ledger import LedgerService
from app.billing.money import format_money, parse_money, settlement_currency
from app.core.clock import Clock
from app.core.config import Settings
from app.core.errors import AppError
from app.db.models.auth import User
from app.db.models.ops import (
    Announcement,
    Coupon,
    CouponRedemption,
    InvoiceRequest,
    Ticket,
    TicketMessage,
)
from app.db.models.payments import PaymentOrder
from app.ops.coupon_codes import (
    MAX_GENERATE_ATTEMPTS,
    CouponCodeError,
    format_code,
    generate_code,
    validate_code,
)

_CATEGORIES = {"billing", "technical", "refund", "chain", "other"}
_TICKET_STATUS = {"open", "pending", "resolved", "closed"}
_INVOICE_STATUS = {"issued", "rejected"}


class OpsService:
    def __init__(self, session: AsyncSession, clock: Clock, settings: Settings) -> None:
        self.session = session
        self.clock = clock
        self.settings = settings

    async def create_ticket(
        self, user_id: UUID, *, category: str, subject: str, body: str
    ) -> dict[str, object]:
        if category not in _CATEGORIES:
            raise AppError(400, "TICKET_CATEGORY_INVALID")
        subject = subject.strip()
        body = body.strip()
        if not subject or not body:
            raise AppError(400, "TICKET_EMPTY")
        now = self.clock.now()
        ticket = Ticket(
            user_id=user_id,
            category=category,
            subject=subject[:160],
            status="open",
            priority="normal",
            created_at=now,
            updated_at=now,
        )
        self.session.add(ticket)
        await self.session.flush()
        self.session.add(
            TicketMessage(ticket_id=ticket.id, author_id=user_id, body=body[:4000], created_at=now)
        )
        await self.session.flush()
        return await self._ticket(ticket.id, viewer_id=user_id, staff=False)

    async def list_tickets(self, *, user_id: UUID | None, page: int = 1, page_size: int = 20) -> dict[str, object]:
        from app.core.paging import clamp_page, page_meta, page_offset

        page, page_size = clamp_page(page, page_size)
        filters = []
        if user_id is not None:
            filters.append(Ticket.user_id == user_id)
        total = int(await self.session.scalar(select(func.count()).select_from(Ticket).where(*filters)) or 0)
        statement = (
            select(Ticket, User.email)
            .join(User, User.id == Ticket.user_id)
            .where(*filters)
            .order_by(Ticket.updated_at.desc(), Ticket.id.desc())
            .offset(page_offset(page, page_size))
            .limit(page_size)
        )
        result = await self.session.execute(statement)
        return {
            **page_meta(page, page_size, total),
            "tickets": [_ticket_row(ticket, email) for ticket, email in result.all()],
        }

    async def ticket_detail(
        self, ticket_id: UUID, *, viewer_id: UUID, staff: bool
    ) -> dict[str, object]:
        return await self._ticket(ticket_id, viewer_id=viewer_id, staff=staff)

    async def add_message(
        self,
        ticket_id: UUID,
        *,
        author_id: UUID,
        body: str,
        staff: bool,
        status: str | None = None,
    ) -> dict[str, object]:
        ticket = await self._owned(ticket_id, viewer_id=author_id, staff=staff)
        text = body.strip()
        if not text:
            raise AppError(400, "TICKET_REPLY_EMPTY")
        now = self.clock.now()
        if staff and status is not None:
            if status not in _TICKET_STATUS:
                raise AppError(400, "TICKET_STATUS_INVALID")
            ticket.status = status
        elif not staff and ticket.status == "closed":
            raise AppError(400, "TICKET_CLOSED")
        elif not staff:
            ticket.status = "pending"
        ticket.updated_at = now
        self.session.add(
            TicketMessage(
                ticket_id=ticket.id, author_id=author_id, body=text[:4000], created_at=now
            )
        )
        if staff:
            await append_audit(
                self.session,
                actor_id=author_id,
                action="ticket.reply",
                target_type="ticket",
                target_id=str(ticket.id),
                detail=ticket.status,
                now=now,
            )
        await self.session.flush()
        return await self._ticket(ticket.id, viewer_id=author_id, staff=staff)

    async def request_invoice(
        self, user_id: UUID, *, order_no: str, title: str, tax_no: str
    ) -> dict[str, object]:
        order = await self.session.scalar(
            select(PaymentOrder).where(
                PaymentOrder.order_no == order_no, PaymentOrder.user_id == user_id
            )
        )
        if order is None or order.status not in {"completed", "overpaid", "refunded"}:
            raise AppError(404, "INVOICE_ORDER_NOT_FOUND")
        title = title.strip()
        if not title:
            raise AppError(400, "INVOICE_TITLE_EMPTY")
        row = InvoiceRequest(
            user_id=user_id,
            order_no=order.order_no,
            title=title[:160],
            tax_no=tax_no.strip()[:64],
            amount=order.amount,
            currency=order.currency,
            status="requested",
            created_at=self.clock.now(),
        )
        self.session.add(row)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            raise AppError(409, "INVOICE_ALREADY_REQUESTED") from exc
        return _invoice(row)

    async def list_invoices(self, *, user_id: UUID | None, page: int = 1, page_size: int = 20) -> dict[str, object]:
        from app.core.paging import clamp_page, page_meta, page_offset

        page, page_size = clamp_page(page, page_size)
        filters = []
        if user_id is not None:
            filters.append(InvoiceRequest.user_id == user_id)
        total = int(
            await self.session.scalar(select(func.count()).select_from(InvoiceRequest).where(*filters)) or 0
        )
        statement = (
            select(InvoiceRequest, User.email)
            .join(User, User.id == InvoiceRequest.user_id)
            .where(*filters)
            .order_by(InvoiceRequest.created_at.desc(), InvoiceRequest.id.desc())
            .offset(page_offset(page, page_size))
            .limit(page_size)
        )
        result = await self.session.execute(statement)
        return {
            **page_meta(page, page_size, total),
            "invoices": [{**_invoice(row), "email": email} for row, email in result.all()],
        }

    async def set_invoice_status(
        self, actor_id: UUID, invoice_id: UUID, status: str
    ) -> dict[str, object]:
        if status not in _INVOICE_STATUS:
            raise AppError(400, "INVOICE_STATUS_INVALID")
        row = await self.session.get(InvoiceRequest, invoice_id)
        if row is None:
            raise AppError(404, "INVOICE_NOT_FOUND")
        if row.status != "requested":
            raise AppError(400, "INVOICE_ALREADY_REVIEWED")
        row.status = status
        await append_audit(
            self.session,
            actor_id=actor_id,
            action="invoice.status",
            target_type="invoice",
            target_id=str(row.id),
            detail=status,
            now=self.clock.now(),
        )
        return _invoice(row)

    async def create_announcement(
        self, actor_id: UUID, *, slug: str, title: str, body: str
    ) -> dict[str, object]:
        slug = _slug(slug)
        title = title.strip()
        body = body.strip()
        if not title or not body:
            raise AppError(400, "ANNOUNCEMENT_EMPTY")
        row = Announcement(
            slug=slug, title=title[:160], body=body, published=False, created_at=self.clock.now()
        )
        self.session.add(row)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            raise AppError(409, "ANNOUNCEMENT_SLUG_TAKEN") from exc
        await append_audit(
            self.session,
            actor_id=actor_id,
            action="announcement.create",
            target_type="announcement",
            target_id=str(row.id),
            detail=slug,
            now=self.clock.now(),
        )
        return _announcement(row)

    async def list_announcements(
        self, *, published_only: bool, page: int = 1, page_size: int = 20
    ) -> dict[str, object]:
        from app.core.paging import clamp_page, page_meta, page_offset

        page, page_size = clamp_page(page, page_size)
        filters = [Announcement.published.is_(True)] if published_only else []
        total = int(
            await self.session.scalar(select(func.count()).select_from(Announcement).where(*filters)) or 0
        )
        rows = await self.session.scalars(
            select(Announcement)
            .where(*filters)
            .order_by(Announcement.created_at.desc(), Announcement.id.desc())
            .offset(page_offset(page, page_size))
            .limit(page_size)
        )
        return {
            **page_meta(page, page_size, total),
            "announcements": [_announcement(row) for row in rows.all()],
        }

    async def announcement(self, slug: str) -> dict[str, object]:
        row = await self.session.scalar(
            select(Announcement).where(Announcement.slug == slug, Announcement.published.is_(True))
        )
        if row is None:
            raise AppError(404, "ANNOUNCEMENT_NOT_FOUND")
        return _announcement(row)

    async def publish_announcement(
        self, actor_id: UUID, announcement_id: UUID, published: bool
    ) -> dict[str, object]:
        row = await self.session.get(Announcement, announcement_id)
        if row is None:
            raise AppError(404, "ANNOUNCEMENT_NOT_FOUND")
        row.published = published
        await append_audit(
            self.session,
            actor_id=actor_id,
            action="announcement.publish",
            target_type="announcement",
            target_id=str(row.id),
            detail="published" if published else "hidden",
            now=self.clock.now(),
        )
        return _announcement(row)

    async def generate_coupon_code(self) -> dict[str, object]:
        code = await self._unique_coupon_code()
        return {"code": code, "formatted": format_code(code)}

    async def create_coupon(
        self,
        actor_id: UUID,
        *,
        code: str | None,
        bonus_amount: str,
        max_uses: int,
        auto_generate: bool = False,
    ) -> dict[str, object]:
        amount = parse_money(bonus_amount)
        if amount <= 0:
            raise AppError(400, "COUPON_BONUS_POSITIVE")
        if max_uses < 1:
            raise AppError(400, "COUPON_MAX_USES_MIN")
        raw = (code or "").strip()
        if auto_generate or raw == "":
            normalized = await self._unique_coupon_code()
        else:
            try:
                normalized = validate_code(raw)
            except CouponCodeError as exc:
                raise AppError(400, "COUPON_BAD_FORMAT", details={"reason": str(exc)}) from exc
            exists = await self.session.scalar(select(Coupon.id).where(Coupon.code == normalized))
            if exists is not None:
                raise AppError(409, "COUPON_CODE_EXISTS")
        row = Coupon(
            code=normalized,
            bonus_amount=amount,
            currency=settlement_currency(self.settings.operating_mode),
            max_uses=max_uses,
            used_count=0,
            enabled=True,
            expires_at=None,
            created_by=actor_id,
            created_at=self.clock.now(),
        )
        self.session.add(row)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            raise AppError(409, "COUPON_CODE_EXISTS") from exc
        await append_audit(
            self.session,
            actor_id=actor_id,
            action="coupon.create",
            target_type="coupon",
            target_id=str(row.id),
            detail=normalized,
            now=self.clock.now(),
        )
        return await self._coupon_detail(row, now=self.clock.now())

    async def list_coupons(self, *, page: int = 1, page_size: int = 20) -> dict[str, object]:
        from app.core.paging import clamp_page, page_meta, page_offset

        page, page_size = clamp_page(page, page_size)
        total = int(await self.session.scalar(select(func.count()).select_from(Coupon)) or 0)
        rows = (
            await self.session.scalars(
                select(Coupon)
                .order_by(Coupon.created_at.desc(), Coupon.id.desc())
                .offset(page_offset(page, page_size))
                .limit(page_size)
            )
        ).all()
        now = self.clock.now()
        coupons = [await self._coupon_detail(row, now=now) for row in rows]
        return {**page_meta(page, page_size, total), "coupons": coupons}

    async def get_coupon(self, coupon_id: UUID) -> dict[str, object]:
        row = await self.session.get(Coupon, coupon_id)
        if row is None:
            raise AppError(404, "COUPON_ADMIN_NOT_FOUND")
        return await self._coupon_detail(row, now=self.clock.now())

    async def _coupon_detail(self, row: Coupon, *, now: datetime) -> dict[str, object]:
        creator_email: str | None = None
        if row.created_by is not None:
            creator_email = await self.session.scalar(select(User.email).where(User.id == row.created_by))
        redemptions = await self.session.execute(
            select(CouponRedemption, User.email)
            .join(User, User.id == CouponRedemption.user_id)
            .where(CouponRedemption.coupon_id == row.id)
            .order_by(CouponRedemption.created_at.desc(), CouponRedemption.id.desc())
        )
        redeem_items = [
            {
                "id": str(redemption.id),
                "user_id": str(redemption.user_id),
                "email": email,
                "created_at": _iso(redemption.created_at),
            }
            for redemption, email in redemptions.all()
        ]
        remaining = max(row.max_uses - row.used_count, 0)
        usable, usable_reason = _coupon_usability(row, now=now)
        return {
            "id": str(row.id),
            "code": row.code,
            "formatted": format_code(row.code),
            "bonus_amount": format_money(_money(row.bonus_amount)),
            "currency": row.currency,
            "max_uses": row.max_uses,
            "used_count": row.used_count,
            "remaining_uses": remaining,
            "enabled": row.enabled,
            "deleted": row.deleted_at is not None,
            "deleted_at": _iso(row.deleted_at) if row.deleted_at else None,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            "created_at": _iso(row.created_at),
            "created_by": str(row.created_by) if row.created_by else None,
            "created_by_email": creator_email,
            "usable": usable,
            "usable_reason": usable_reason,
            "redemptions": redeem_items,
            "redemption_count": len(redeem_items),
        }

    async def redeem_coupon(self, user_id: UUID, code: str) -> dict[str, object]:
        raw = (code or "").strip()
        if not raw:
            raise AppError(400, "COUPON_EMPTY")
        try:
            normalized = validate_code(raw)
        except CouponCodeError as exc:
            raise AppError(400, "COUPON_BAD_FORMAT", details={"reason": str(exc)}) from exc
        coupon = await self.session.scalar(select(Coupon).where(Coupon.code == normalized))
        now = self.clock.now()
        if coupon is None:
            raise AppError(404, "COUPON_NOT_FOUND")
        if coupon.deleted_at is not None:
            raise AppError(404, "COUPON_DELETED")
        if not coupon.enabled:
            raise AppError(403, "COUPON_DISABLED")
        if coupon.currency != settlement_currency(self.settings.operating_mode):
            raise AppError(
                400,
                "COUPON_CURRENCY",
                details={"currency": coupon.currency},
            )
        if coupon.expires_at is not None and as_utc(coupon.expires_at) <= now:
            raise AppError(400, "COUPON_EXPIRED")
        # 先查本人是否兑过，避免 max_uses=1 时误报「已用完」
        already = await self.session.scalar(
            select(CouponRedemption.id).where(
                CouponRedemption.coupon_id == coupon.id,
                CouponRedemption.user_id == user_id,
            )
        )
        if already is not None:
            raise AppError(409, "COUPON_ALREADY_REDEEMED")
        if coupon.used_count >= coupon.max_uses:
            raise AppError(409, "COUPON_EXHAUSTED")
        # 原子抢名额：条件更新 + 受影响行数判定。
        # 原先「读 used_count → +1 → 写回」在并发下会丢更新，两个用户可同时
        # 拿到最后一个名额（ck_coupons_uses 也不会报错，因为两次写入都合法）。
        claimed = await self.session.execute(
            update(Coupon)
            .where(Coupon.id == coupon.id, Coupon.used_count < Coupon.max_uses)
            .values(used_count=Coupon.used_count + 1)
            .execution_options(synchronize_session=False)
        )
        if claimed.rowcount != 1:
            raise AppError(409, "COUPON_EXHAUSTED")
        self.session.add(CouponRedemption(coupon_id=coupon.id, user_id=user_id, created_at=now))
        try:
            async with self.session.begin_nested():
                await self.session.flush()
        except IntegrityError as exc:
            # 并发：同人重复兑，或最后名额被抢光触发 used_count 约束
            raced = await self.session.scalar(
                select(CouponRedemption.id).where(
                    CouponRedemption.coupon_id == coupon.id,
                    CouponRedemption.user_id == user_id,
                )
            )
            if raced is not None:
                raise AppError(409, "COUPON_ALREADY_REDEEMED") from exc
            raise AppError(409, "COUPON_EXHAUSTED") from exc
        await LedgerService(self.session, self.clock).post(
            user_id=user_id,
            entry_type="bonus",
            amount=_money(coupon.bonus_amount),
            currency=coupon.currency,
            idempotency_key=f"coupon:{coupon.id}:{user_id}",
            reference_type="coupon",
            reference_id=str(coupon.id),
            reason="coupon_bonus",
        )
        return {
            "code": coupon.code,
            "formatted": format_code(coupon.code),
            "bonus_amount": format_money(_money(coupon.bonus_amount)),
            "currency": coupon.currency,
        }

    async def _unique_coupon_code(self) -> str:
        for _ in range(MAX_GENERATE_ATTEMPTS):
            candidate = generate_code()
            exists = await self.session.scalar(select(Coupon.id).where(Coupon.code == candidate))
            if exists is None:
                return candidate
        raise AppError(503, "COUPON_GENERATE_CONFLICT")

    async def _owned(self, ticket_id: UUID, *, viewer_id: UUID, staff: bool) -> Ticket:
        ticket = await self.session.get(Ticket, ticket_id)
        if ticket is None or (not staff and ticket.user_id != viewer_id):
            raise AppError(404, "TICKET_NOT_FOUND")
        return ticket

    async def _ticket(self, ticket_id: UUID, *, viewer_id: UUID, staff: bool) -> dict[str, object]:
        ticket = await self._owned(ticket_id, viewer_id=viewer_id, staff=staff)
        email = await self.session.scalar(select(User.email).where(User.id == ticket.user_id))
        messages = await self.session.scalars(
            select(TicketMessage)
            .where(TicketMessage.ticket_id == ticket.id)
            .order_by(TicketMessage.created_at.asc(), TicketMessage.id.asc())
        )
        data = _ticket_row(ticket, email or "")
        data["messages"] = [
            {
                "id": str(item.id),
                "author_id": str(item.author_id),
                "body": item.body,
                "created_at": _iso(item.created_at),
            }
            for item in messages.all()
        ]
        return data


def _money(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _slug(raw: str) -> str:
    slug = raw.strip().lower()
    if len(slug) < 2 or len(slug) > 80 or not all(part.isalnum() or part == "-" for part in slug):
        raise AppError(400, "ANNOUNCEMENT_SLUG_INVALID")
    return slug


def _iso(value: datetime) -> str:
    return as_utc(value).isoformat()


def _ticket_row(ticket: Ticket, email: str) -> dict[str, object]:
    return {
        "id": str(ticket.id),
        "email": email,
        "category": ticket.category,
        "subject": ticket.subject,
        "status": ticket.status,
        "priority": ticket.priority,
        "created_at": _iso(ticket.created_at),
        "updated_at": _iso(ticket.updated_at),
    }


def _invoice(row: InvoiceRequest) -> dict[str, object]:
    return {
        "id": str(row.id),
        "order_no": row.order_no,
        "title": row.title,
        "tax_no": row.tax_no,
        "amount": format_money(_money(row.amount)),
        "currency": row.currency,
        "status": row.status,
        "created_at": _iso(row.created_at),
    }


def _announcement(row: Announcement) -> dict[str, object]:
    return {
        "id": str(row.id),
        "slug": row.slug,
        "title": row.title,
        "body": row.body,
        "published": row.published,
        "created_at": _iso(row.created_at),
    }


def _coupon_usability(row: Coupon, *, now: datetime) -> tuple[bool, str]:
    """返回 (是否可用, 稳定 reason 码；文案由前端按语言渲染)。"""
    if row.deleted_at is not None:
        return False, "deleted"
    if not row.enabled:
        return False, "disabled"
    if row.expires_at is not None and as_utc(row.expires_at) <= now:
        return False, "expired"
    if row.used_count >= row.max_uses:
        return False, "exhausted"
    return True, "ok"


async def margin_report(session: AsyncSession) -> dict[str, object]:
    from app.db.models.keys import UsageRecord

    charges = await session.execute(
        select(
            func.coalesce(func.sum(UsageRecord.user_charge), 0),
            func.coalesce(func.sum(UsageRecord.provider_cost), 0),
        )
    )
    user_charge, provider_cost = charges.one()
    grouped = await session.execute(
        select(PaymentOrder.reconcile_status, func.count()).group_by(PaymentOrder.reconcile_status)
    )
    revenue = parse_money(str(user_charge or 0))
    cost = parse_money(str(provider_cost or 0))
    return {
        "user_charge": format_money(revenue),
        "provider_cost": format_money(cost),
        "margin": format_money(revenue - cost),
        "reconcile": {status: int(count) for status, count in grouped.all()},
    }
