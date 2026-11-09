"""支付订单：新增收银台地址与查单快照（幂等）。

背景：`sessions` / `orders` 只是进程内字典，真实渠道回调必然失败。改造后
Stripe 会返回真实的 Checkout Session URL，主动查单结果也需要落库留痕。

- checkout_url：下单后直接返回给前端跳转收银台
- provider_snapshot：最近一次主动查单的原始 JSON，回调只与它比对
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261109_0018_payment_checkout"
down_revision: str | None = "20261102_0017_api_key_crypto"
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
    if not _column_exists("payment_orders", "checkout_url"):
        op.add_column(
            "payment_orders",
            sa.Column("checkout_url", sa.String(length=512), nullable=True, comment="收银台跳转地址"),
        )
    if not _column_exists("payment_orders", "provider_snapshot"):
        op.add_column(
            "payment_orders",
            sa.Column("provider_snapshot", sa.Text(), nullable=True, comment="最近一次主动查单快照 JSON"),
        )


def downgrade() -> None:
    if _column_exists("payment_orders", "provider_snapshot"):
        op.drop_column("payment_orders", "provider_snapshot")
    if _column_exists("payment_orders", "checkout_url"):
        op.drop_column("payment_orders", "checkout_url")
