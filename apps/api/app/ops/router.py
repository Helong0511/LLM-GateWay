"""工单、发票、公告、优惠券和运营只读接口。路径不带版本段。"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import (
    assert_browser_origin,
    get_current_user,
    require_any_permission,
    require_permission,
)
from app.auth.repository import AuthRepository
from app.core.errors import success
from app.db.models.auth import User
from app.db.session import get_db
from app.ops.platform import (
    content_view,
    create_backup,
    delete_backup,
    list_backups,
    list_jobs,
    list_routes,
    public_settings,
    record_ping,
    set_content_enabled,
)
from app.ops.service import OpsService, margin_report
from app.worker import worker_ping

router = APIRouter(tags=["ops"], dependencies=[Depends(assert_browser_origin)])


class TicketBody(BaseModel):
    category: str
    subject: str
    body: str


class ReplyBody(BaseModel):
    body: str
    status: str | None = None


class InvoiceBody(BaseModel):
    order_no: str
    title: str
    tax_no: str = ""


class InvoiceStatusBody(BaseModel):
    status: str


class AnnouncementBody(BaseModel):
    slug: str
    title: str
    body: str


class PublishBody(BaseModel):
    published: bool


class CouponBody(BaseModel):
    code: str | None = None
    bonus_amount: str
    max_uses: int
    auto_generate: bool = False


class RedeemBody(BaseModel):
    code: str


class ContentBody(BaseModel):
    enabled: bool


def _ops(request: Request, db: AsyncSession) -> OpsService:
    return OpsService(db, request.app.state.clock, request.app.state.settings)


@router.post("/api/tickets")
async def create_ticket(
    body: TicketBody,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    data = await _ops(request, db).create_ticket(
        user.id, category=body.category, subject=body.subject, body=body.body
    )
    return success(request, data)


@router.get("/api/tickets")
async def my_tickets(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(
        request,
        await _ops(request, db).list_tickets(user_id=user.id, page=page, page_size=page_size),
    )


@router.get("/api/tickets/{ticket_id}")
async def my_ticket(
    ticket_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(
        request, await _ops(request, db).ticket_detail(ticket_id, viewer_id=user.id, staff=False)
    )


@router.post("/api/tickets/{ticket_id}/messages")
async def reply_ticket(
    ticket_id: UUID,
    body: ReplyBody,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    data = await _ops(request, db).add_message(
        ticket_id, author_id=user.id, body=body.body, staff=False
    )
    return success(request, data)


@router.get("/api/admin/tickets")
async def admin_tickets(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: User = Depends(require_permission("admin:access")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(
        request, await _ops(request, db).list_tickets(user_id=None, page=page, page_size=page_size)
    )


@router.get("/api/admin/tickets/{ticket_id}")
async def admin_ticket(
    ticket_id: UUID,
    request: Request,
    user: User = Depends(require_permission("admin:access")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(
        request, await _ops(request, db).ticket_detail(ticket_id, viewer_id=user.id, staff=True)
    )


@router.post("/api/admin/tickets/{ticket_id}/messages")
async def admin_reply(
    ticket_id: UUID,
    body: ReplyBody,
    request: Request,
    user: User = Depends(require_permission("admin:access")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    data = await _ops(request, db).add_message(
        ticket_id, author_id=user.id, body=body.body, staff=True, status=body.status
    )
    return success(request, data)


@router.post("/api/invoices")
async def request_invoice(
    body: InvoiceBody,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    data = await _ops(request, db).request_invoice(
        user.id, order_no=body.order_no, title=body.title, tax_no=body.tax_no
    )
    return success(request, data)


@router.get("/api/invoices")
async def my_invoices(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(
        request,
        await _ops(request, db).list_invoices(user_id=user.id, page=page, page_size=page_size),
    )


@router.get("/api/admin/invoices")
async def admin_invoices(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(require_any_permission("admin:access", "refund:request")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    data = await _ops(request, db).list_invoices(user_id=None, page=page, page_size=page_size)
    granted = await AuthRepository(db).permission_codes(user.id)
    data["can_review"] = "refund:request" in granted
    return success(request, data)


@router.post("/api/admin/invoices/{invoice_id}/status")
async def invoice_status(
    invoice_id: UUID,
    body: InvoiceStatusBody,
    request: Request,
    user: User = Depends(require_permission("refund:request")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(
        request, await _ops(request, db).set_invoice_status(user.id, invoice_id, body.status)
    )


@router.get("/api/announcements")
async def published_announcements(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(
        request,
        await _ops(request, db).list_announcements(
            published_only=True, page=page, page_size=page_size
        ),
    )


@router.get("/api/announcements/{slug}")
async def published_announcement(
    slug: str, request: Request, db: AsyncSession = Depends(get_db)
) -> dict[str, object]:
    return success(request, await _ops(request, db).announcement(slug))


@router.get("/api/admin/announcements")
async def admin_announcements(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: User = Depends(require_permission("admin:access")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(
        request,
        await _ops(request, db).list_announcements(
            published_only=False, page=page, page_size=page_size
        ),
    )


@router.post("/api/admin/announcements")
async def create_announcement(
    body: AnnouncementBody,
    request: Request,
    user: User = Depends(require_permission("admin:access")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    data = await _ops(request, db).create_announcement(
        user.id, slug=body.slug, title=body.title, body=body.body
    )
    return success(request, data)


@router.post("/api/admin/announcements/{announcement_id}/publish")
async def publish_announcement(
    announcement_id: UUID,
    body: PublishBody,
    request: Request,
    user: User = Depends(require_permission("admin:access")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(
        request,
        await _ops(request, db).publish_announcement(user.id, announcement_id, body.published),
    )


@router.get("/api/admin/coupons")
async def admin_coupons(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: User = Depends(require_permission("admin:access")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(request, await _ops(request, db).list_coupons(page=page, page_size=page_size))


@router.get("/api/admin/coupons/{coupon_id}")
async def admin_coupon_detail(
    coupon_id: UUID,
    request: Request,
    _: User = Depends(require_permission("admin:access")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(request, await _ops(request, db).get_coupon(coupon_id))


@router.post("/api/admin/coupons/generate")
async def generate_coupon_code(
    request: Request,
    _: User = Depends(require_permission("admin:access")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(request, await _ops(request, db).generate_coupon_code())


@router.post("/api/admin/coupons")
async def create_coupon(
    body: CouponBody,
    request: Request,
    user: User = Depends(require_permission("admin:access")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    data = await _ops(request, db).create_coupon(
        user.id,
        code=body.code,
        bonus_amount=body.bonus_amount,
        max_uses=body.max_uses,
        auto_generate=body.auto_generate,
    )
    return success(request, data)


@router.post("/api/coupons/redeem")
async def redeem_coupon(
    body: RedeemBody,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(request, await _ops(request, db).redeem_coupon(user.id, body.code))


@router.get("/api/admin/margin")
async def admin_margin(
    request: Request,
    _: User = Depends(require_any_permission("admin:access", "refund:request")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(request, await margin_report(db))


@router.get("/api/admin/routes")
async def admin_routes(
    request: Request,
    status: str | None = Query(default="all"),
    q: str | None = Query(default=None, max_length=128),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: User = Depends(require_permission("admin:access")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(
        request,
        await list_routes(db, status=status, q=q, page=page, page_size=page_size),
    )


@router.get("/api/admin/settings")
async def admin_settings(
    request: Request,
    _: User = Depends(require_permission("admin:access")),
) -> dict[str, object]:
    return success(request, public_settings(request.app.state.settings))


@router.get("/api/admin/content-safety")
async def admin_content(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: User = Depends(require_permission("admin:access")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(request, await content_view(db, page=page, page_size=page_size))


@router.post("/api/admin/content-safety")
async def update_content(
    body: ContentBody,
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(require_permission("admin:access")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    data = await set_content_enabled(
        db, user.id, body.enabled, request.app.state.clock.now(), page=page, page_size=page_size
    )
    return success(request, data)


@router.get("/api/admin/tasks")
async def admin_tasks(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: User = Depends(require_permission("admin:access")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(request, await list_jobs(db, page=page, page_size=page_size))


@router.post("/api/admin/tasks/ping")
async def ping_task(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: User = Depends(require_permission("admin:access")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    stamped = await worker_ping({"clock": request.app.state.clock})
    return success(
        request,
        await record_ping(
            db, stamped, request.app.state.clock.now(), page=page, page_size=page_size
        ),
    )


@router.get("/api/admin/backups")
async def admin_backups(
    request: Request,
    _: User = Depends(require_permission("admin:access")),
) -> dict[str, object]:
    return success(request, list_backups(request.app.state.settings))


@router.post("/api/admin/backups")
async def run_backup(
    request: Request,
    _: User = Depends(require_permission("admin:access")),
) -> dict[str, object]:
    settings = request.app.state.settings
    return success(request, await create_backup(settings.database_url, settings))


@router.delete("/api/admin/backups/{name}")
async def remove_backup(
    name: str,
    request: Request,
    _: User = Depends(require_permission("admin:access")),
) -> dict[str, object]:
    return success(request, delete_backup(name))
