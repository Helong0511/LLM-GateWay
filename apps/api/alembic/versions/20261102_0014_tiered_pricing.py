"""ModelPrice 加阶梯计费 tier_min_tokens 列 + 唯一约束升级（幂等）。"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261102_0014"
down_revision: str | None = "20261102_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_CONSTRAINT = "uq_model_prices_version_meter"
_NEW_CONSTRAINT = "uq_model_prices_version_meter_tier"


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    cols = {c["name"] for c in insp.get_columns("model_prices")}
    constraints = {c["name"] for c in insp.get_unique_constraints("model_prices")}

    if "tier_min_tokens" not in cols:
        op.add_column(
            "model_prices",
            sa.Column("tier_min_tokens", sa.Integer(), nullable=False, server_default="0"),
        )

    if _NEW_CONSTRAINT not in constraints:
        if _OLD_CONSTRAINT in constraints:
            op.drop_constraint(_OLD_CONSTRAINT, "model_prices", type_="unique")
        op.create_unique_constraint(
            _NEW_CONSTRAINT,
            "model_prices",
            ["pricing_version_id", "meter", "tier_min_tokens"],
        )


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    cols = {c["name"] for c in insp.get_columns("model_prices")}
    constraints = {c["name"] for c in insp.get_unique_constraints("model_prices")}

    if _NEW_CONSTRAINT in constraints:
        op.drop_constraint(_NEW_CONSTRAINT, "model_prices", type_="unique")

    if _OLD_CONSTRAINT not in constraints:
        op.create_unique_constraint(
            _OLD_CONSTRAINT,
            "model_prices",
            ["pricing_version_id", "meter"],
        )

    if "tier_min_tokens" in cols:
        op.drop_column("model_prices", "tier_min_tokens")
