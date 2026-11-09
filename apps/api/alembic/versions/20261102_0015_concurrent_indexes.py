"""高并发查询索引：用量/账本/预扣/结算/通知（幂等）。

多用户高并发场景补齐：
- 用户按时间倒序翻页自己的用量与账单
- 运营按模型统计用量
- 过期预扣定时释放扫描（部分索引）
- 未完结结算扫描（部分索引）
- 未读通知拉取（部分索引）
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261102_0015"
down_revision: str | None = "20261102_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEXES: list[tuple[str, str, str]] = [
    # (表名, 索引名, 列/SQL 尾句)
    ("usage_records", "ix_usage_records_user_created", "(user_id, created_at)"),
    ("usage_records", "ix_usage_records_model_created", "(model_id, created_at)"),
    (
        "usage_records",
        "ix_usage_records_unsettled",
        "(created_at) WHERE settlement_status IN ('pending', 'disputed')",
    ),
    ("account_ledger", "ix_account_ledger_user_created", "(user_id, created_at)"),
    ("balance_holds", "ix_balance_holds_held_expiry", "(expires_at) WHERE status = 'held'"),
    ("usage_settlements", "ix_usage_settlements_hold_id", "(hold_id)"),
    (
        "notifications",
        "ix_notifications_user_unread",
        "(user_id, created_at) WHERE read_at IS NULL",
    ),
]


def upgrade() -> None:
    for table, name, tail in INDEXES:
        op.execute(
            sa.text(
                f"CREATE INDEX IF NOT EXISTS {name} ON {table} {tail}"
            )
        )


def downgrade() -> None:
    for _table, name, _tail in reversed(INDEXES):
        op.execute(sa.text(f"DROP INDEX IF EXISTS {name}"))
