"""model_catalog 保存上游同步到的建议单价（幂等：列已存在则跳过）。"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261102_0011"
down_revision: str | None = "20261030_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    cols = {c["name"] for c in insp.get_columns("model_catalog")}
    if "upstream_input_price" not in cols:
        op.add_column("model_catalog", sa.Column("upstream_input_price", sa.Numeric(24, 8)))
    if "upstream_output_price" not in cols:
        op.add_column("model_catalog", sa.Column("upstream_output_price", sa.Numeric(24, 8)))


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    cols = {c["name"] for c in insp.get_columns("model_catalog")}
    if "upstream_output_price" in cols:
        op.drop_column("model_catalog", "upstream_output_price")
    if "upstream_input_price" in cols:
        op.drop_column("model_catalog", "upstream_input_price")
