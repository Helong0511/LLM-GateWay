"""供应商、模型目录和审计。密钥只存密文。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Provider(Base):
    __tablename__ = "providers"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('openai', 'anthropic', 'cloud', 'self_hosted', 'ollama', 'compatible')",
            name="ck_providers_kind",
        ),
        CheckConstraint("status IN ('active', 'disabled', 'deleted')", name="ck_providers_status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    protocol: Mapped[str] = mapped_column(String(32), nullable=False, default="openai")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    weight: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    max_concurrency: Mapped[int | None] = mapped_column(Integer)
    rpm_limit: Mapped[int | None] = mapped_column(Integer)
    tpm_limit: Mapped[int | None] = mapped_column(Integer)
    last_error: Mapped[str | None] = mapped_column(String(256))
    last_latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ProviderCredential(Base):
    __tablename__ = "provider_credentials"
    __table_args__ = (CheckConstraint("status IN ('active', 'revoked')", name="ck_provider_credentials_status"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    provider_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("providers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    secret_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    secret_hint: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class EndpointAllowlist(Base):
    __tablename__ = "endpoint_allowlist"
    __table_args__ = (UniqueConstraint("host", name="uq_endpoint_allowlist_host"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    note: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ModelCatalog(Base):
    __tablename__ = "model_catalog"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'published', 'disabled')", name="ck_model_catalog_status"),
        UniqueConstraint("provider_id", "upstream_name", name="uq_model_catalog_provider_upstream"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    provider_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("providers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    public_name: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    upstream_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    supports_stream: Mapped[bool | None] = mapped_column(Boolean)
    supports_tools: Mapped[bool | None] = mapped_column(Boolean)
    supports_vision: Mapped[bool | None] = mapped_column(Boolean)
    supports_embeddings: Mapped[bool | None] = mapped_column(Boolean)
    supports_images: Mapped[bool | None] = mapped_column(Boolean)
    context_window: Mapped[int | None] = mapped_column(Integer)
    max_output: Mapped[int | None] = mapped_column(Integer)
    upstream_input_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    upstream_output_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    upstream_schedule_rules: Mapped[dict | None] = mapped_column(
        JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ModelDeployment(Base):
    __tablename__ = "model_deployments"
    __table_args__ = (CheckConstraint("status IN ('active', 'disabled')", name="ck_model_deployments_status"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    model_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("model_catalog.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("providers.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    # 与 LiteLLM 执行面的同步状态：成功记录时间，失败记录原因供对账任务重试。
    registry_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    registry_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ModelSyncJob(Base):
    __tablename__ = "model_sync_jobs"
    __table_args__ = (
        CheckConstraint("status IN ('running', 'succeeded', 'failed')", name="ck_model_sync_jobs_status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    provider_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("providers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    discovered_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(String(256))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ModelTestRun(Base):
    __tablename__ = "model_test_runs"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    provider_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("providers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    usage_present: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AuditChainLock(Base):
    __tablename__ = "audit_chain_lock"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        UniqueConstraint("seq", name="uq_audit_events_seq"),
        UniqueConstraint("content_hash", name="uq_audit_events_content_hash"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    detail: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    recorded_at: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
