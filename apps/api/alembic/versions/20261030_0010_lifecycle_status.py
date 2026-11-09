"""区分启用/停用/删除：供应商 deleted；套餐与优惠券 deleted_at；密钥 disabled。"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261030_0010"
down_revision: str | None = "20261030_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    product_cols = {col["name"] for col in inspector.get_columns("recharge_products")}
    if "deleted_at" not in product_cols:
        op.add_column("recharge_products", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))

    coupon_cols = {col["name"] for col in inspector.get_columns("coupons")}
    if "deleted_at" not in coupon_cols:
        op.add_column("coupons", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))

    # 放宽状态约束（PostgreSQL 需先 drop 再 add；SQLite create_all 测试不走这里）
    dialect = bind.dialect.name
    if dialect == "postgresql":
        op.execute("ALTER TABLE providers DROP CONSTRAINT IF EXISTS ck_providers_status")
        op.execute(
            "ALTER TABLE providers ADD CONSTRAINT ck_providers_status "
            "CHECK (status IN ('active', 'disabled', 'deleted'))"
        )
        op.execute("ALTER TABLE api_keys DROP CONSTRAINT IF EXISTS ck_api_keys_status")
        op.execute(
            "ALTER TABLE api_keys ADD CONSTRAINT ck_api_keys_status "
            "CHECK (status IN ('active', 'disabled', 'revoked', 'expired'))"
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    dialect = bind.dialect.name

    if dialect == "postgresql":
        op.execute("UPDATE providers SET status = 'disabled' WHERE status = 'deleted'")
        op.execute("ALTER TABLE providers DROP CONSTRAINT IF EXISTS ck_providers_status")
        op.execute(
            "ALTER TABLE providers ADD CONSTRAINT ck_providers_status "
            "CHECK (status IN ('active', 'disabled'))"
        )
        op.execute("UPDATE api_keys SET status = 'revoked' WHERE status = 'disabled'")
        op.execute("ALTER TABLE api_keys DROP CONSTRAINT IF EXISTS ck_api_keys_status")
        op.execute(
            "ALTER TABLE api_keys ADD CONSTRAINT ck_api_keys_status "
            "CHECK (status IN ('active', 'revoked', 'expired'))"
        )

    coupon_cols = {col["name"] for col in inspector.get_columns("coupons")}
    if "deleted_at" in coupon_cols:
        op.drop_column("coupons", "deleted_at")

    product_cols = {col["name"] for col in inspector.get_columns("recharge_products")}
    if "deleted_at" in product_cols:
        op.drop_column("recharge_products", "deleted_at")
