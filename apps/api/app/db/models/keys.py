"""用户 API Key 与调用记录。完整密钥不入库。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ApiKey(Base):
    __tablename__ = "api_keys"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'disabled', 'revoked', 'expired')", name="ck_api_keys_status"),
        CheckConstraint("char_length(key_hash) = 64", name="ck_api_keys_key_hash_len"),
        UniqueConstraint("key_hash", name="uq_api_keys_key_hash"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(24), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # 仅用于“复制”场景的 AES-256-GCM 密文；为空表示历史密钥（仅存 digest，无法再复制）。
    key_ciphertext: Mapped[str | None] = mapped_column(Text)
    key_enc_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rpm_limit: Mapped[int | None] = mapped_column(Integer)
    tpm_limit: Mapped[int | None] = mapped_column(Integer)
    max_concurrency: Mapped[int | None] = mapped_column(Integer)
    budget_limit: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    budget_spent: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False, default=Decimal("0"))
    allowed_models: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    ip_allowlist: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UsageRecord(Base):
    __tablename__ = "usage_records"
    __table_args__ = (
        CheckConstraint(
            "settlement_status IN ('pending', 'settled', 'released', 'disputed')",
            name="ck_usage_records_settlement",
        ),
        UniqueConstraint("request_id", name="uq_usage_records_request_id"),
        # 高并发查询索引：用户按时间倒序翻页自己的用量历史
        Index("ix_usage_records_user_created", "user_id", "created_at"),
        # 运营按模型维度统计用量
        Index("ix_usage_records_model_created", "model_id", "created_at"),
        # 异常结算定时扫描（部分索引，只覆盖未完结状态，保持索引小）
        Index(
            "ix_usage_records_unsettled",
            "created_at",
            postgresql_where=text("settlement_status IN ('pending', 'disputed')"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    api_key_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("api_keys.id", ondelete="SET NULL")
    )
    model_id: Mapped[str | None] = mapped_column(String(128))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cached_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    user_charge: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    http_status: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    first_token_ms: Mapped[int | None] = mapped_column(Integer)
    is_stream: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    settlement_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    pricing_version_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    unit_price_snapshot: Mapped[str | None] = mapped_column(Text)
    provider_cost: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    usage_source: Mapped[str | None] = mapped_column(String(16))
    finish_reason: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
