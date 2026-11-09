"""充值套餐、支付订单、退款和 USDT 尾数。"""

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

ORDER_STATUSES = (
    "pending",
    "confirming",
    "completed",
    "expired",
    "underpaid",
    "overpaid",
    "closed",
    "refunded",
)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key", name="uq_idempotency_user_key"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(80), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RechargeProduct(Base):
    __tablename__ = "recharge_products"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_recharge_products_amount"),
        CheckConstraint("bonus_amount >= 0", name="ck_recharge_products_bonus"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    bonus_amount: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False, default=Decimal("0"))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 套餐默认可用模型（JSON 数组，空数组表示该套餐不限模型）
    allowed_models: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class PaymentOrder(Base):
    __tablename__ = "payment_orders"
    __table_args__ = (
        UniqueConstraint("order_no", name="uq_payment_orders_order_no"),
        UniqueConstraint("user_id", "idempotency_key", name="uq_payment_orders_user_idempotency"),
        CheckConstraint(
            "status IN ('pending', 'confirming', 'completed', 'expired', 'underpaid', 'overpaid', 'closed', 'refunded')",
            name="ck_payment_orders_status",
        ),
        CheckConstraint(
            "channel IN ('mock', 'stripe', 'usdt', 'wechat', 'alipay')",
            name="ck_payment_orders_channel",
        ),
        CheckConstraint("amount > 0", name="ck_payment_orders_amount"),
        CheckConstraint(
            "risk_status IN ('clear', 'sanctioned', 'large_review')",
            name="ck_payment_orders_risk",
        ),
        CheckConstraint(
            "reconcile_status IN ('unchecked', 'matched', 'disputed')",
            name="ck_payment_orders_reconcile",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    order_no: Mapped[str] = mapped_column(String(40), nullable=False)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    product_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("recharge_products.id", ondelete="SET NULL")
    )
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    bonus_amount: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False, default=Decimal("0"))
    credited_amount: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    crypto_amount: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    crypto_currency: Mapped[str | None] = mapped_column(String(8))
    network: Mapped[str | None] = mapped_column(String(16))
    pay_address: Mapped[str | None] = mapped_column(String(128))
    payer_address: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    locked_rate: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    rate_source: Mapped[str | None] = mapped_column(String(64))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    provider_ref: Mapped[str | None] = mapped_column(String(128))
    tx_hash: Mapped[str | None] = mapped_column(String(128))
    confirmations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    actual_amount: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    risk_status: Mapped[str] = mapped_column(String(16), nullable=False, default="clear")
    reconcile_status: Mapped[str] = mapped_column(String(16), nullable=False, default="unchecked")
    idempotency_key: Mapped[str] = mapped_column(String(80), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PaymentEvent(Base):
    __tablename__ = "payment_events"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    order_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("payment_orders.id", ondelete="SET NULL"), index=True
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    payload_redacted: Mapped[str] = mapped_column(Text, nullable=False)
    signature_ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RefundOrder(Base):
    __tablename__ = "refund_orders"
    __table_args__ = (
        UniqueConstraint("order_id", name="uq_refund_orders_order"),
        CheckConstraint(
            "status IN ('requested', 'reviewed', 'executed', 'rejected')",
            name="ck_refund_orders_status",
        ),
        CheckConstraint("amount > 0", name="ck_refund_orders_amount"),
        CheckConstraint(
            "executed_by IS NULL OR executed_by <> requested_by",
            name="ck_refund_orders_executor",
        ),
        CheckConstraint(
            "reviewed_by IS NULL OR reviewed_by <> requested_by",
            name="ck_refund_orders_reviewer",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    order_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("payment_orders.id", ondelete="RESTRICT"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="requested")
    requested_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    reviewed_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    executed_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    destination_address: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    tx_hash: Mapped[str | None] = mapped_column(String(128))
    reason: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CryptoDepositIntent(Base):
    __tablename__ = "crypto_deposit_intents"
    __table_args__ = (
        UniqueConstraint("order_id", name="uq_crypto_deposit_intents_order"),
        CheckConstraint("tail_status IN ('reserved', 'used', 'released')", name="ck_crypto_tail_status"),
        Index(
            "uq_crypto_tail_open",
            "address",
            "network",
            "tail_amount",
            unique=True,
            sqlite_where=text("tail_status = 'reserved'"),
            postgresql_where=text("tail_status = 'reserved'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    order_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("payment_orders.id", ondelete="CASCADE"), nullable=False
    )
    address: Mapped[str] = mapped_column(String(128), nullable=False)
    network: Mapped[str] = mapped_column(String(16), nullable=False)
    tail_amount: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False, default=Decimal("0"))
    tail_status: Mapped[str] = mapped_column(String(16), nullable=False, default="reserved")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SanctionedAddress(Base):
    __tablename__ = "sanctioned_address_blocks"
    __table_args__ = (UniqueConstraint("address", "network", name="uq_sanctioned_address_network"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    address: Mapped[str] = mapped_column(String(128), nullable=False)
    network: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
