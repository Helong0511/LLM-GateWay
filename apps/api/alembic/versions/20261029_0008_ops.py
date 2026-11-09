"""工单、发票、公告、优惠券、内容审计和任务记录。"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261029_0008"
down_revision: str | None = "20261029_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tickets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category", sa.String(16), nullable=False),
        sa.Column("subject", sa.String(160), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("priority", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "category IN ('billing', 'technical', 'refund', 'chain', 'other')",
            name="ck_tickets_category",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'pending', 'resolved', 'closed')", name="ck_tickets_status"
        ),
        sa.CheckConstraint("priority IN ('low', 'normal', 'high')", name="ck_tickets_priority"),
    )
    op.create_table(
        "ticket_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "ticket_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tickets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "author_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ticket_messages_ticket_id", "ticket_messages", ["ticket_id"])
    op.create_table(
        "invoice_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("order_no", sa.String(40), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("tax_no", sa.String(64), nullable=False),
        sa.Column("amount", sa.Numeric(24, 8), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("order_no", name="uq_invoice_requests_order"),
        sa.CheckConstraint(
            "status IN ('requested', 'issued', 'rejected')", name="ck_invoice_requests_status"
        ),
        sa.CheckConstraint("amount > 0", name="ck_invoice_requests_amount"),
    )
    op.create_table(
        "announcements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("published", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("slug", name="uq_announcements_slug"),
    )
    op.create_table(
        "coupons",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("bonus_amount", sa.Numeric(24, 8), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=False),
        sa.Column("used_count", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("code", name="uq_coupons_code"),
        sa.CheckConstraint("bonus_amount > 0", name="ck_coupons_bonus"),
        sa.CheckConstraint(
            "max_uses >= 1 AND used_count >= 0 AND used_count <= max_uses", name="ck_coupons_uses"
        ),
    )
    op.create_table(
        "coupon_redemptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "coupon_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("coupons.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("coupon_id", "user_id", name="uq_coupon_redemptions_user"),
    )
    op.create_table(
        "content_safety_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
    )
    op.execute(sa.text("INSERT INTO content_safety_settings (id, enabled) VALUES (1, false)"))
    op.create_table(
        "content_audit_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")
        ),
        sa.Column("model_name", sa.String(128), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("summary_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "job_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("detail", sa.String(256), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('succeeded', 'failed')", name="ck_job_runs_status"),
    )


def downgrade() -> None:
    op.drop_table("job_runs")
    op.drop_table("content_audit_records")
    op.drop_table("content_safety_settings")
    op.drop_table("coupon_redemptions")
    op.drop_table("coupons")
    op.drop_table("announcements")
    op.drop_table("invoice_requests")
    op.drop_index("ix_ticket_messages_ticket_id", table_name="ticket_messages")
    op.drop_table("ticket_messages")
    op.drop_table("tickets")
