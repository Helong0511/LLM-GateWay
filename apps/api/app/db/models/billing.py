"""价格版本、余额、只追加账本和预扣。余额不放在 users 上。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    event,
    func,
    text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PricingVersion(Base):
    __tablename__ = "pricing_versions"
    __table_args__ = (
        UniqueConstraint("model_id", "version", name="uq_pricing_versions_model_version"),
        CheckConstraint("version >= 1", name="ck_pricing_versions_version"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    model_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("model_catalog.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    schedule_rules: Mapped[dict | None] = mapped_column(
        JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=True
    )


class ModelPrice(Base):
    __tablename__ = "model_prices"
    __table_args__ = (
        UniqueConstraint(
            "pricing_version_id", "meter", "tier_min_tokens",
            name="uq_model_prices_version_meter_tier",
        ),
        CheckConstraint(
            "meter IN ('input_token', 'output_token', 'cached_input_token', 'image')",
            name="ck_model_prices_meter",
        ),
        CheckConstraint("unit_price >= 0 AND cost_price >= 0", name="ck_model_prices_nonnegative"),
        CheckConstraint("min_billable_units >= 0", name="ck_model_prices_min_units"),
        CheckConstraint("tier_min_tokens >= 0", name="ck_model_prices_tier_min"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    pricing_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("pricing_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    meter: Mapped[str] = mapped_column(String(32), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    cost_price: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    min_billable_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tier_min_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ExchangeRate(Base):
    __tablename__ = "exchange_rates"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    base_currency: Mapped[str] = mapped_column(String(8), nullable=False)
    quote_currency: Mapped[str] = mapped_column(String(8), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AccountBalance(Base):
    __tablename__ = "account_balances"
    __table_args__ = (
        CheckConstraint("balance >= 0", name="ck_account_balances_balance"),
        CheckConstraint("held >= 0", name="ck_account_balances_held"),
        CheckConstraint("frozen >= 0", name="ck_account_balances_frozen"),
        CheckConstraint("balance >= held + frozen", name="ck_account_balances_available"),
    )

    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True
    )
    currency: Mapped[str] = mapped_column(String(8), primary_key=True)
    balance: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False, default=Decimal("0"))
    held: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False, default=Decimal("0"))
    frozen: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False, default=Decimal("0"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AccountLedger(Base):
    """只追加。应用层拦截 ORM 更新，PostgreSQL 触发器拦截 SQL 更新。"""

    __tablename__ = "account_ledger"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_account_ledger_idempotency"),
        CheckConstraint("amount > 0", name="ck_account_ledger_amount"),
        CheckConstraint("direction IN ('C', 'D', 'N')", name="ck_account_ledger_direction"),
        CheckConstraint("balance_before >= 0 AND balance_after >= 0", name="ck_account_ledger_balance"),
        # 高并发查询索引：用户按时间倒序翻页账单流水
        Index("ix_account_ledger_user_created", "user_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    entry_type: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str] = mapped_column(String(1), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    balance_before: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(32))
    reference_id: Mapped[str | None] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))


class BalanceHold(Base):
    __tablename__ = "balance_holds"
    __table_args__ = (
        UniqueConstraint("request_id", name="uq_balance_holds_request"),
        UniqueConstraint("idempotency_key", name="uq_balance_holds_idempotency"),
        CheckConstraint("status IN ('held', 'committed', 'released')", name="ck_balance_holds_status"),
        CheckConstraint("amount > 0", name="ck_balance_holds_amount"),
        CheckConstraint(
            "committed_amount >= 0 AND committed_amount <= amount",
            name="ck_balance_holds_committed",
        ),
        # 过期预扣定时释放扫描（部分索引，只覆盖 held 状态）
        Index(
            "ix_balance_holds_held_expiry",
            "expires_at",
            postgresql_where=text("status = 'held'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    api_key_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("api_keys.id", ondelete="SET NULL"))
    amount: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    committed_amount: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False, default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="held")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    pricing_version_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UsageSettlement(Base):
    __tablename__ = "usage_settlements"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'settled', 'released', 'disputed')",
            name="ck_usage_settlements_status",
        ),
        # 结算记录按预扣反查
        Index("ix_usage_settlements_hold_id", "hold_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    usage_record_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("usage_records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    hold_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("balance_holds.id", ondelete="SET NULL"))
    ledger_entry_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("account_ledger.id", ondelete="RESTRICT")
    )
    settled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def _reject_ledger_write(_mapper: object, _connection: object, _target: object) -> None:
    raise RuntimeError("account_ledger is append-only")


event.listen(AccountLedger, "before_update", _reject_ledger_write)
event.listen(AccountLedger, "before_delete", _reject_ledger_write)
