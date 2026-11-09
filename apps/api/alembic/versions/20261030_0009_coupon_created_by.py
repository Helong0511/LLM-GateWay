"""优惠券记录创建人，便于后台展示。"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261030_0009"
down_revision: str | None = "20261029_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("coupons")}
    if "created_by" not in columns:
        op.add_column(
            "coupons",
            sa.Column(
                "created_by",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
    # 从审计链回填创建人（coupon.create / target_id = 券 id）
    op.execute(
        sa.text(
            """
            UPDATE coupons AS c
            SET created_by = a.actor_id
            FROM (
                SELECT DISTINCT ON (target_id) target_id, actor_id
                FROM audit_events
                WHERE action = 'coupon.create' AND target_type = 'coupon' AND actor_id IS NOT NULL
                ORDER BY target_id, seq ASC
            ) AS a
            WHERE c.id::text = a.target_id AND c.created_by IS NULL
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("coupons")}
    if "created_by" in columns:
        op.drop_column("coupons", "created_by")
