"""供应商、模型目录、审计，以及首 Token 延迟。"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.auth.rbac import PERMISSIONS, ROLE_GRANTS, ROLE_IDS
from sqlalchemy.dialects import postgresql

revision: str = "20261028_0005"
down_revision: str | None = "20261028_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_CODES = {"provider:manage", "model:publish"}


def upgrade() -> None:
    op.add_column("usage_records", sa.Column("first_token_ms", sa.Integer()))
    op.create_table(
        "providers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("protocol", sa.String(32), nullable=False, server_default="openai"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("weight", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("max_concurrency", sa.Integer()),
        sa.Column("rpm_limit", sa.Integer()),
        sa.Column("tpm_limit", sa.Integer()),
        sa.Column("last_error", sa.String(256)),
        sa.Column("last_latency_ms", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "kind IN ('openai', 'anthropic', 'cloud', 'self_hosted', 'ollama', 'compatible')",
            name="ck_providers_kind",
        ),
        sa.CheckConstraint("status IN ('active', 'disabled')", name="ck_providers_status"),
    )
    op.create_table(
        "provider_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "provider_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("providers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String(128), nullable=False),
        sa.Column("secret_ciphertext", sa.Text(), nullable=False),
        sa.Column("secret_hint", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('active', 'revoked')", name="ck_provider_credentials_status"),
    )
    op.create_index("ix_provider_credentials_provider_id", "provider_credentials", ["provider_id"])
    op.create_table(
        "endpoint_allowlist",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("note", sa.String(256), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("host", name="uq_endpoint_allowlist_host"),
    )
    op.create_table(
        "model_catalog",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "provider_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("providers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("public_name", sa.String(128), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("upstream_name", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("supports_stream", sa.Boolean()),
        sa.Column("supports_tools", sa.Boolean()),
        sa.Column("supports_vision", sa.Boolean()),
        sa.Column("supports_embeddings", sa.Boolean()),
        sa.Column("supports_images", sa.Boolean()),
        sa.Column("context_window", sa.Integer()),
        sa.Column("max_output", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('pending', 'published', 'disabled')", name="ck_model_catalog_status"),
        sa.UniqueConstraint("provider_id", "upstream_name", name="uq_model_catalog_provider_upstream"),
    )
    op.create_index("ix_model_catalog_provider_id", "model_catalog", ["provider_id"])
    op.create_table(
        "model_deployments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "model_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("model_catalog.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "provider_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("providers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('active', 'disabled')", name="ck_model_deployments_status"),
    )
    op.create_index("ix_model_deployments_model_id", "model_deployments", ["model_id"])
    op.create_table(
        "model_sync_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "provider_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("providers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("discovered_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.String(256)),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('running', 'succeeded', 'failed')", name="ck_model_sync_jobs_status"),
    )
    op.create_index("ix_model_sync_jobs_provider_id", "model_sync_jobs", ["provider_id"])
    op.create_table(
        "model_test_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "provider_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("providers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("mode", sa.String(32), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("http_status", sa.Integer()),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("usage_present", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error", sa.String(256)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_model_test_runs_provider_id", "model_test_runs", ["provider_id"])
    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(64), nullable=False),
        sa.Column("target_id", sa.String(64), nullable=False),
        sa.Column("detail", sa.String(256), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    bind = op.get_bind()
    for item_id, code, description in PERMISSIONS:
        if code not in _NEW_CODES:
            continue
        bind.execute(
            sa.text(
                "INSERT INTO permissions (id, code, description) "
                "VALUES (:id, :code, :description) ON CONFLICT (id) DO NOTHING"
            ),
            {"id": item_id, "code": code, "description": description},
        )
    permission_ids = {code: item_id for item_id, code, _description in PERMISSIONS}
    for role_code, grants in ROLE_GRANTS.items():
        for permission_code in grants:
            if permission_code not in _NEW_CODES:
                continue
            bind.execute(
                sa.text(
                    "INSERT INTO role_permissions (role_id, permission_id) "
                    "VALUES (:role_id, :permission_id) ON CONFLICT DO NOTHING"
                ),
                {"role_id": ROLE_IDS[role_code], "permission_id": permission_ids[permission_code]},
            )


def downgrade() -> None:
    op.execute(
        "DELETE FROM role_permissions WHERE permission_id IN "
        "(SELECT id FROM permissions WHERE code IN ('provider:manage', 'model:publish'))"
    )
    op.execute("DELETE FROM permissions WHERE code IN ('provider:manage', 'model:publish')")
    op.drop_table("audit_events")
    op.drop_table("model_test_runs")
    op.drop_table("model_sync_jobs")
    op.drop_table("model_deployments")
    op.drop_table("model_catalog")
    op.drop_table("endpoint_allowlist")
    op.drop_table("provider_credentials")
    op.drop_table("providers")
    op.drop_column("usage_records", "first_token_ms")
