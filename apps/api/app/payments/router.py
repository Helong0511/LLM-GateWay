"""充值、回调和退款。回调验签，不走浏览器来源检查。"""

from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import (
    assert_browser_origin,
    client_ip,
    get_current_user,
    require_any_permission,
    require_permission,
)
from app.auth.repository import AuthRepository
from app.core.errors import AppError, failure, success
from app.db.models.auth import User
from app.db.session import get_db
from app.payments.service import IngestResult, PaymentService

router = APIRouter(tags=["payments"], dependencies=[Depends(assert_browser_origin)])
webhook_router = APIRouter(tags=["payments"])


class CreateOrderBody(BaseModel):
    product_id: UUID
    channel: str = Field(min_length=3, max_length=16)


class MockConfirmBody(BaseModel):
    order_no: str = Field(min_length=4, max_length=40)


class BillRowBody(BaseModel):
    order_no: str
    amount: str


class ReconcileBody(BaseModel):
    channel: str
    bill_date: date
    rows: list[BillRowBody]


class ReconcileStatusBody(BaseModel):
    status: Literal["unchecked", "matched", "disputed"]


class RefundBody(BaseModel):
    order_no: str
    destination: str = ""
    reason: str = ""


class ExecuteRefundBody(BaseModel):
    tx_hash: str | None = None


class RejectRefundBody(BaseModel):
    reason: str = ""


def _service(request: Request, db: AsyncSession) -> PaymentService:
    return PaymentService(
        db,
        request.app.state.clock,
        request.app.state.settings,
        request.app.state.stripe_gateway,
        request.app.state.usdt_gateway,
    )


def _ingest_response(request: Request, result: IngestResult) -> JSONResponse | dict[str, object]:
    if result.status_code == 200 and result.data is not None:
        return success(request, result.data)
    return failure(
        request,
        result.status_code,
        result.error_code or "VALIDATION_ERROR",
        result.error_message or "回调没有受理",
    )


@router.get("/api/payments/products")
async def products(
    request: Request,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(request, await _service(request, db).list_products())


@router.post("/api/payments/orders")
async def create_order(
    body: CreateOrderBody,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, object]:
    if not idempotency_key:
        raise AppError(400, "IDEMPOTENCY_KEY_REQUIRED")
    data = await _service(request, db).create_order(
        user.id,
        product_id=body.product_id,
        channel=body.channel,
        idempotency_key=idempotency_key,
    )
    return success(request, data)


@router.get("/api/payments/orders")
async def list_orders(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(request, await _service(request, db).list_orders(user.id, page=page, page_size=page_size))


@router.get("/api/payments/orders/{order_no}")
async def get_order(
    order_no: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(request, await _service(request, db).get_order(user.id, order_no))


@router.post("/api/payments/mock/confirm")
async def confirm_mock(
    body: MockConfirmBody,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(request, await _service(request, db).confirm_mock(user.id, body.order_no))


@router.get("/api/admin/orders")
async def admin_orders(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
    reconcile_status: str | None = Query(default=None),
    q: str | None = Query(default=None, max_length=128),
    _actor: User = Depends(require_permission("admin:access")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(
        request,
        await _service(request, db).list_admin_orders(
            page=page,
            page_size=page_size,
            status=status,
            reconcile_status=reconcile_status,
            q=q,
        ),
    )


@router.post("/api/admin/orders/{order_no}/reconcile")
async def set_order_reconcile(
    order_no: str,
    body: ReconcileStatusBody,
    request: Request,
    _actor: User = Depends(require_permission("refund:request")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(request, await _service(request, db).set_reconcile_status(order_no, body.status))


@router.post("/api/admin/payments/reconcile")
async def reconcile(
    body: ReconcileBody,
    request: Request,
    _actor: User = Depends(require_permission("refund:request")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    from app.billing.money import parse_money

    rows = [(item.order_no, parse_money(item.amount)) for item in body.rows]
    data = await _service(request, db).reconcile(body.channel, body.bill_date, rows)
    return success(request, data)


@router.get("/api/admin/refunds")
async def admin_refunds(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    actor: User = Depends(require_any_permission("admin:access", "refund:request", "refund:execute")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    granted = await AuthRepository(db).permission_codes(actor.id)
    data = await _service(request, db).list_admin_refunds(page=page, page_size=page_size)
    data["actor_id"] = str(actor.id)
    data["can_request"] = "refund:request" in granted
    data["can_execute"] = "refund:execute" in granted
    return success(request, data)


@router.post("/api/admin/refunds")
async def request_refund(
    body: RefundBody,
    request: Request,
    actor: User = Depends(require_permission("refund:request")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    data = await _service(request, db).request_refund(
        actor.id,
        body.order_no,
        destination=body.destination,
        reason=body.reason,
    )
    return success(request, data)


@router.post("/api/admin/refunds/{refund_id}/review")
async def review_refund(
    refund_id: UUID,
    request: Request,
    actor: User = Depends(require_permission("refund:request")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(request, await _service(request, db).review_refund(actor.id, refund_id))


@router.post("/api/admin/refunds/{refund_id}/reject")
async def reject_refund(
    refund_id: UUID,
    body: RejectRefundBody,
    request: Request,
    actor: User = Depends(require_permission("refund:request")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return success(request, await _service(request, db).reject_refund(actor.id, refund_id, reason=body.reason))


@router.post("/api/admin/refunds/{refund_id}/execute")
async def execute_refund(
    refund_id: UUID,
    body: ExecuteRefundBody,
    request: Request,
    actor: User = Depends(require_permission("refund:execute")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    data = await _service(request, db).execute_refund(actor.id, refund_id, body.tx_hash)
    return success(request, data)


@webhook_router.post("/api/payments/stripe/webhook", response_model=None)
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)) -> JSONResponse | dict[str, object]:
    raw = await request.body()
    signature = request.headers.get("stripe-signature", "")
    result = await _service(request, db).ingest_stripe(raw, signature)
    return _ingest_response(request, result)


@webhook_router.post("/api/payments/usdt/notify", response_model=None)
async def usdt_notify(request: Request, db: AsyncSession = Depends(get_db)) -> JSONResponse | dict[str, object]:
    raw = await request.body()
    signature = request.headers.get("x-forge-signature", "")
    result = await _service(request, db).ingest_usdt(raw, signature, client_ip(request))
    return _ingest_response(request, result)
