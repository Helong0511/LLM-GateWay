"""API Key 加密存储：新增密文列（幂等）。

目的：
- 把明文 API Key 用 AES-256-GCM 加密后持久化，支持“复制前二次验证后临时解密”
- 旧列 key_hash 保持不变（仍用于网关 lookup 的 SHA-256 匹配）
- 历史存量密钥 key_ciphertext 为 NULL / key_enc_version=0，表示无法再复制明文
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261102_0017_api_key_crypto"
down_revision: str | None = "20261102_0016"
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
    if not _column_exists("api_keys", "key_ciphertext"):
        op.add_column("api_keys", sa.Column("key_ciphertext", sa.Text(), nullable=True, comment="AES-256-GCM 密文，格式 v1|iv|tag|body；空=历史无加密"))
    if not _column_exists("api_keys", "key_enc_version"):
        op.add_column(
            "api_keys",
            sa.Column(
                "key_enc_version",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
                comment="加密算法版本，0=无加密（存量），1=AES-256-GCM",
            ),
        )


def downgrade() -> None:
    if _column_exists("api_keys", "key_enc_version"):
        op.drop_column("api_keys", "key_enc_version")
    if _column_exists("api_keys", "key_ciphertext"):
        op.drop_column("api_keys", "key_ciphertext")
