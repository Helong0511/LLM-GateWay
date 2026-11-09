"""model_catalog 加上游建议的时段规则 upstream_schedule_rules（JSONB，幂等）。"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20261102_0013"
down_revision: str | None = "20261102_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    cols = {c["name"] for c in insp.get_columns("model_catalog")}
    if "upstream_schedule_rules" not in cols:
        op.add_column(
            "model_catalog",
            sa.Column(
                "upstream_schedule_rules",
                sa.JSON().with_variant(JSONB(), "postgresql"),
            ),
        )


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    cols = {c["name"] for c in insp.get_columns("model_catalog")}
    if "upstream_schedule_rules" in cols:
        op.drop_column("model_catalog", "upstream_schedule_rules")
