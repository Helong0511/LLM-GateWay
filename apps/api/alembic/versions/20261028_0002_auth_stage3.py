"""邮箱变更、二次验证、登录设备和权限种子。"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.auth.rbac import PERMISSIONS, ROLE_GRANTS, ROLE_IDS
from sqlalchemy.dialects import postgresql

revision: str = "20261028_0002"
down_revision: str | None = "20261028_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _token_table(name: str, constraint: str, unique_name: str, extra: list[sa.Column] | None = None) -> None:
    columns: list[sa.Column] = [
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    ]
    if extra:
        columns.extend(extra)
    columns.extend(
        [
            sa.Column("token_hash", sa.String(64), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("consumed_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.CheckConstraint("char_length(token_hash) = 64", name=constraint),
            sa.UniqueConstraint("token_hash", name=unique_name),
        ]
    )
    op.create_table(name, *columns)
    op.create_index(f"ix_{name}_user_id", name, ["user_id"])


def upgrade() -> None:
    _token_table(
        "email_change_tokens",
        "ck_email_change_token_hash_len",
        "uq_email_change_token_hash",
        [sa.Column("new_email", sa.String(320), nullable=False)],
    )
    _token_table("mfa_challenges", "ck_mfa_challenge_token_hash_len", "uq_mfa_challenge_token_hash")
    op.create_table(
        "totp_recovery_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("char_length(code_hash) = 64", name="ck_totp_recovery_code_hash_len"),
        sa.UniqueConstraint("code_hash", name="uq_totp_recovery_code_hash"),
    )
    op.create_index("ix_totp_recovery_codes_user_id", "totp_recovery_codes", ["user_id"])
    op.create_table(
        "user_profiles",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("display_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
        sa.Column("locale", sa.String(16), nullable=False, server_default="zh-CN"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_table(
        "login_devices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_agent", sa.Text(), nullable=False, server_default=""),
        sa.Column("ip", sa.String(64), nullable=False, server_default=""),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_login_devices_user_id", "login_devices", ["user_id"])

    permissions = sa.table(
        "permissions",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("code", sa.String),
        sa.column("description", sa.String),
    )
    op.bulk_insert(
        permissions,
        [{"id": item_id, "code": code, "description": description} for item_id, code, description in PERMISSIONS],
    )
    role_permissions = sa.table(
        "role_permissions",
        sa.column("role_id", postgresql.UUID(as_uuid=True)),
        sa.column("permission_id", postgresql.UUID(as_uuid=True)),
    )
    permission_ids = {code: item_id for item_id, code, _description in PERMISSIONS}
    op.bulk_insert(
        role_permissions,
        [
            {"role_id": ROLE_IDS[role_code], "permission_id": permission_ids[permission_code]}
            for role_code, grants in ROLE_GRANTS.items()
            for permission_code in grants
        ],
    )


def downgrade() -> None:
    op.execute("DELETE FROM role_permissions")
    op.execute("DELETE FROM permissions")
    op.drop_table("login_devices")
    op.drop_table("user_profiles")
    op.drop_table("totp_recovery_codes")
    op.drop_table("mfa_challenges")
    op.drop_table("email_change_tokens")
