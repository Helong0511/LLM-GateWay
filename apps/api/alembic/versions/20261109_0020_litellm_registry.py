"""model_deployments 记录 LiteLLM 执行面同步状态（幂等）。

`/v1` 转发打给 LiteLLM，而模型目录只在自家库；不同步就会出现
「后台显示已上架、真实调用 400 model not found」。这里补两列，
让上架失败可观测，并作为对账任务的重试依据。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261109_0020_litellm_registry"
down_revision: str | None = "20261109_0019_totp_replay"
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
    if not _column_exists("model_deployments", "registry_synced_at"):
        op.add_column(
            "model_deployments",
            sa.Column(
                "registry_synced_at",
                sa.DateTime(timezone=True),
                nullable=True,
                comment="最近一次成功同步到 LiteLLM 的时间",
            ),
        )
    if not _column_exists("model_deployments", "registry_error"):
        op.add_column(
            "model_deployments",
            sa.Column(
                "registry_error",
                sa.Text(),
                nullable=True,
                comment="最近一次同步失败原因；对账任务会重试",
            ),
        )


def downgrade() -> None:
    if _column_exists("model_deployments", "registry_error"):
        op.drop_column("model_deployments", "registry_error")
    if _column_exists("model_deployments", "registry_synced_at"):
        op.drop_column("model_deployments", "registry_synced_at")
