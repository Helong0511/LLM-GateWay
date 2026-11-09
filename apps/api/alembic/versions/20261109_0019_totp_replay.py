"""users 表新增 TOTP 时间步水位线（幂等）。

用于拒绝同一个 6 位动态码在 ±30 秒窗口内重复使用（重放）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261109_0019_totp_replay"
down_revision: str | None = "20261109_0018_payment_checkout"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    row = conn.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c)"
        ),
        {"t": table, "c": column},
    ).scalar_one()
    return bool(row)


def upgrade() -> None:
    if not _column_exists("users", "totp_last_step"):
        op.add_column(
            "users",
            sa.Column("totp_last_step", sa.Integer(), nullable=True, comment="最近一次成功的 TOTP 时间步"),
        )


def downgrade() -> None:
    if _column_exists("users", "totp_last_step"):
        op.drop_column("users", "totp_last_step")
