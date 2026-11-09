"""身份表：用户、角色、权限、会话与令牌摘要。"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261028_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLE_ROWS = [
    {
        "id": "00000000-0000-4000-8000-000000000001",
        "code": "user",
        "name": "普通用户",
        "description": "默认注册角色",
    },
    {
        "id": "00000000-0000-4000-8000-000000000002",
        "code": "support",
        "name": "客服",
        "description": "工单与用户协助，不含退款与账本修改",
    },
    {
        "id": "00000000-0000-4000-8000-000000000003",
        "code": "finance",
        "name": "财务",
        "description": "订单、退款复核与账本查询，不含供应商密钥",
    },
    {
        "id": "00000000-0000-4000-8000-000000000004",
        "code": "operator",
        "name": "运营人员",
        "description": "公告、用户运营与活动配置",
    },
    {
        "id": "00000000-0000-4000-8000-000000000005",
        "code": "model_ops",
        "name": "模型运维人员",
        "description": "供应商、模型与路由",
    },
    {
        "id": "00000000-0000-4000-8000-000000000006",
        "code": "admin",
        "name": "系统管理员",
        "description": "除超管专属操作外的管理权限",
    },
    {
        "id": "00000000-0000-4000-8000-000000000007",
        "code": "superadmin",
        "name": "超级管理员",
        "description": "初始化时仅创建一个，使用行为单独告警",
    },
]


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("email_normalized", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
        sa.Column("totp_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("totp_secret_encrypted", sa.Text()),
        sa.Column("terms_version", sa.String(64)),
        sa.Column("terms_accepted_at", sa.DateTime(timezone=True)),
        sa.Column("privacy_version", sa.String(64)),
        sa.Column("privacy_accepted_at", sa.DateTime(timezone=True)),
        sa.Column("register_ip", sa.String(64)),
        sa.Column("register_user_agent", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('pending_verification', 'active', 'frozen', 'deleted')",
            name="ck_users_status",
        ),
        sa.UniqueConstraint("email_normalized", name="uq_users_email_normalized"),
    )
    op.create_index("ix_users_status", "users", ["status"])

    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("code", name="uq_roles_code"),
    )

    op.create_table(
        "permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("code", name="uq_permissions_code"),
    )

    op.create_table(
        "role_permissions",
        sa.Column("role_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column(
            "permission_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("permissions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    op.create_table(
        "user_roles",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("granted_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("granted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idle_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_ip", sa.String(64)),
        sa.Column("last_seen_ip", sa.String(64)),
        sa.Column("user_agent", sa.Text()),
        sa.CheckConstraint("char_length(token_hash) = 64", name="ck_sessions_token_hash_len"),
        sa.UniqueConstraint("token_hash", name="uq_sessions_token_hash"),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])

    for table_name, constraint, unique_name in (
        ("email_verification_tokens", "ck_email_verification_token_hash_len", "uq_email_verification_token_hash"),
        ("password_reset_tokens", "ck_password_reset_token_hash_len", "uq_password_reset_token_hash"),
    ):
        op.create_table(
            table_name,
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("token_hash", sa.String(64), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("consumed_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.CheckConstraint("char_length(token_hash) = 64", name=constraint),
            sa.UniqueConstraint("token_hash", name=unique_name),
        )
        op.create_index(f"ix_{table_name}_user_id", table_name, ["user_id"])

    roles = sa.table(
        "roles",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.String),
        sa.column("is_system", sa.Boolean),
    )
    op.bulk_insert(
        roles,
        [{**row, "is_system": True} for row in ROLE_ROWS],
    )


def downgrade() -> None:
    op.drop_table("password_reset_tokens")
    op.drop_table("email_verification_tokens")
    op.drop_table("sessions")
    op.drop_table("user_roles")
    op.drop_table("role_permissions")
    op.drop_table("permissions")
    op.drop_table("roles")
    op.drop_table("users")
