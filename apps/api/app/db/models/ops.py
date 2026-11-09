"""工单、发票、公告、优惠券、内容审计和任务记录。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        CheckConstraint(
            "category IN ('billing', 'technical', 'refund', 'chain', 'other')",
            name="ck_tickets_category",
        ),
        CheckConstraint("status IN ('open', 'pending', 'resolved', 'closed')", name="ck_tickets_status"),
        CheckConstraint("priority IN ('low', 'normal', 'high')", name="ck_tickets_priority"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    category: Mapped[str] = mapped_column(String(16), nullable=False)
    subject: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="normal")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TicketMessage(Base):
    __tablename__ = "ticket_messages"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    ticket_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class InvoiceRequest(Base):
    __tablename__ = "invoice_requests"
    __table_args__ = (
        UniqueConstraint("order_no", name="uq_invoice_requests_order"),
        CheckConstraint("status IN ('requested', 'issued', 'rejected')", name="ck_invoice_requests_status"),
        CheckConstraint("amount > 0", name="ck_invoice_requests_amount"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    order_no: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    tax_no: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    amount: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="requested")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Announcement(Base):
    __tablename__ = "announcements"
    __table_args__ = (UniqueConstraint("slug", name="uq_announcements_slug"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Coupon(Base):
    __tablename__ = "coupons"
    __table_args__ = (
        UniqueConstraint("code", name="uq_coupons_code"),
        CheckConstraint("bonus_amount > 0", name="ck_coupons_bonus"),
        CheckConstraint("max_uses >= 1 AND used_count >= 0 AND used_count <= max_uses", name="ck_coupons_uses"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    bonus_amount: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    max_uses: Mapped[int] = mapped_column(Integer, nullable=False)
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CouponRedemption(Base):
    __tablename__ = "coupon_redemptions"
    __table_args__ = (UniqueConstraint("coupon_id", "user_id", name="uq_coupon_redemptions_user"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    coupon_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("coupons.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ContentSafetySetting(Base):
    __tablename__ = "content_safety_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class ContentAuditRecord(Base):
    __tablename__ = "content_audit_records"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    summary_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class JobRun(Base):
    __tablename__ = "job_runs"
    __table_args__ = (CheckConstraint("status IN ('succeeded', 'failed')", name="ck_job_runs_status"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    detail: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
