"""模型权限上提到账号级：

- users.allowed_models：账号级可用模型（空数组 = 未显式配置，回退套餐）
- recharge_products.allowed_models：套餐默认可用模型（空数组 = 不限）
- 存量数据：把 api_keys 上的白名单合并到所属用户，并清空 Key 级配置

脚本可重复执行：列已存在则跳过，存量迁移只影响仍为空账号级配置的用户。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261102_0016"
down_revision: str | None = "20261102_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _column_exists(bind: sa.Connection, table: str, column: str) -> bool:
    row = bind.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = current_schema() "
            "AND table_name = :table AND column_name = :column"
        ),
        {"table": table, "column": column},
    ).first()
    return row is not None


def upgrade() -> None:
    bind = op.get_bind()
    if not _column_exists(bind, "users", "allowed_models"):
        op.add_column(
            "users",
            sa.Column("allowed_models", sa.Text(), nullable=False, server_default="[]"),
        )
    if not _column_exists(bind, "recharge_products", "allowed_models"):
        op.add_column(
            "recharge_products",
            sa.Column("allowed_models", sa.Text(), nullable=False, server_default="[]"),
        )

    # 把存量 Key 级白名单合并进所属用户（仅当账号级仍为空）。
    bind.execute(
        sa.text(
            """
            UPDATE users AS u
            SET allowed_models = sub.merged
            FROM (
                SELECT k.user_id,
                       to_jsonb(array_agg(DISTINCT elem))::text AS merged
                FROM api_keys AS k
                CROSS JOIN LATERAL jsonb_array_elements_text(k.allowed_models::jsonb) AS elem
                WHERE k.allowed_models::jsonb <> '[]'::jsonb
                GROUP BY k.user_id
            ) AS sub
            WHERE u.id = sub.user_id
              AND u.allowed_models::jsonb = '[]'::jsonb
            """
        )
    )
    # Key 级配置不再生效，统一清空，全部改为继承账号级。
    bind.execute(
        sa.text("UPDATE api_keys SET allowed_models = '[]' WHERE allowed_models::jsonb <> '[]'::jsonb")
    )


def downgrade() -> None:
    bind = op.get_bind()
    if _column_exists(bind, "users", "allowed_models"):
        op.drop_column("users", "allowed_models")
    if _column_exists(bind, "recharge_products", "allowed_models"):
        op.drop_column("recharge_products", "allowed_models")
