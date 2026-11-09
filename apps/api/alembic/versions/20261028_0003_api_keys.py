"""API Key 与调用记录。"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261028_0003"
down_revision: str | None = "20261028_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("key_prefix", sa.String(24), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("rpm_limit", sa.Integer()),
        sa.Column("tpm_limit", sa.Integer()),
        sa.Column("max_concurrency", sa.Integer()),
        sa.Column("budget_limit", sa.Numeric(24, 8)),
        sa.Column("budget_spent", sa.Numeric(24, 8), nullable=False, server_default="0"),
        sa.Column("allowed_models", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("ip_allowlist", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('active', 'revoked', 'expired')", name="ck_api_keys_status"),
        sa.CheckConstraint("char_length(key_hash) = 64", name="ck_api_keys_key_hash_len"),
        sa.UniqueConstraint("key_hash", name="uq_api_keys_key_hash"),
    )
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])
    op.create_table(
        "usage_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("api_key_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("api_keys.id", ondelete="SET NULL")),
        sa.Column("model_id", sa.String(128)),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cached_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("user_charge", sa.Numeric(24, 8)),
        sa.Column("currency", sa.String(8), nullable=False, server_default="USD"),
        sa.Column("http_status", sa.Integer()),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("is_stream", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("settlement_status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("usage_source", sa.String(16)),
        sa.Column("finish_reason", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "settlement_status IN ('pending', 'settled', 'released', 'disputed')",
            name="ck_usage_records_settlement",
        ),
        sa.UniqueConstraint("request_id", name="uq_usage_records_request_id"),
    )
    op.create_index("ix_usage_records_user_id", "usage_records", ["user_id"])


def downgrade() -> None:
    op.drop_table("usage_records")
    op.drop_table("api_keys")
