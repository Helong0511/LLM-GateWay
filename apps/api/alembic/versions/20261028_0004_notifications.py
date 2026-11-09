"""站内通知与通知偏好。"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261028_0004"
down_revision: str | None = "20261028_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("related_id", postgresql.UUID(as_uuid=True)),
        sa.Column("dedupe_key", sa.String(160), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("kind IN ('security', 'key_expiry')", name="ck_notifications_kind"),
        sa.UniqueConstraint("user_id", "dedupe_key", name="uq_notifications_user_dedupe"),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_table(
        "notification_preferences",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("balance_alerts_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("warn_high", sa.Numeric(24, 8), nullable=False, server_default="10"),
        sa.Column("warn_low", sa.Numeric(24, 8), nullable=False, server_default="2"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("notification_preferences")
    op.drop_table("notifications")
