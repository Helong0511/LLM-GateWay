"""价格、账本、预扣和充值订单。"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261028_0006"
down_revision: str | None = "20261028_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATUSES = "pending', 'confirming', 'completed', 'expired', 'underpaid', 'overpaid', 'closed', 'refunded"


def upgrade() -> None:
    op.drop_constraint("ck_notifications_kind", "notifications", type_="check")
    op.create_check_constraint(
        "ck_notifications_kind",
        "notifications",
        "kind IN ('security', 'key_expiry', 'balance')",
    )
    op.create_table(
        "pricing_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("model_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("model_catalog.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True)),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_pricing_versions_version"),
        sa.UniqueConstraint("model_id", "version", name="uq_pricing_versions_model_version"),
    )
    op.create_index("ix_pricing_versions_model_id", "pricing_versions", ["model_id"])
    op.create_table(
        "model_prices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "pricing_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("pricing_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("meter", sa.String(32), nullable=False),
        sa.Column("unit_price", sa.Numeric(24, 8), nullable=False),
        sa.Column("cost_price", sa.Numeric(24, 8), nullable=False),
        sa.Column("min_billable_units", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint(
            "meter IN ('input_token', 'output_token', 'cached_input_token', 'image')",
            name="ck_model_prices_meter",
        ),
        sa.CheckConstraint("unit_price >= 0 AND cost_price >= 0", name="ck_model_prices_nonnegative"),
        sa.CheckConstraint("min_billable_units >= 0", name="ck_model_prices_min_units"),
        sa.UniqueConstraint("pricing_version_id", "meter", name="uq_model_prices_version_meter"),
    )
    op.create_index("ix_model_prices_pricing_version_id", "model_prices", ["pricing_version_id"])
    op.create_table(
        "exchange_rates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("base_currency", sa.String(8), nullable=False),
        sa.Column("quote_currency", sa.String(8), nullable=False),
        sa.Column("rate", sa.Numeric(24, 8), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.add_column("usage_records", sa.Column("pricing_version_id", postgresql.UUID(as_uuid=True)))
    op.add_column("usage_records", sa.Column("unit_price_snapshot", sa.Text()))
    op.add_column("usage_records", sa.Column("provider_cost", sa.Numeric(24, 8)))
    op.create_table(
        "account_balances",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("currency", sa.String(8), primary_key=True),
        sa.Column("balance", sa.Numeric(24, 8), nullable=False),
        sa.Column("held", sa.Numeric(24, 8), nullable=False),
        sa.Column("frozen", sa.Numeric(24, 8), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("balance >= 0", name="ck_account_balances_balance"),
        sa.CheckConstraint("held >= 0", name="ck_account_balances_held"),
        sa.CheckConstraint("frozen >= 0", name="ck_account_balances_frozen"),
        sa.CheckConstraint("balance >= held + frozen", name="ck_account_balances_available"),
    )
    op.create_table(
        "account_ledger",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("entry_type", sa.String(32), nullable=False),
        sa.Column("direction", sa.String(1), nullable=False),
        sa.Column("amount", sa.Numeric(24, 8), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("balance_before", sa.Numeric(24, 8), nullable=False),
        sa.Column("balance_after", sa.Numeric(24, 8), nullable=False),
        sa.Column("reference_type", sa.String(32)),
        sa.Column("reference_id", sa.String(64)),
        sa.Column("reason", sa.String(256), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.UniqueConstraint("idempotency_key", name="uq_account_ledger_idempotency"),
        sa.CheckConstraint("amount > 0", name="ck_account_ledger_amount"),
        sa.CheckConstraint("direction IN ('C', 'D', 'N')", name="ck_account_ledger_direction"),
        sa.CheckConstraint("balance_before >= 0 AND balance_after >= 0", name="ck_account_ledger_balance"),
    )
    op.create_index("ix_account_ledger_user_id", "account_ledger", ["user_id"])
    op.execute(
        """
        CREATE FUNCTION forbid_account_ledger_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'account_ledger is append-only';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_account_ledger_append_only
        BEFORE UPDATE OR DELETE ON account_ledger
        FOR EACH ROW
        EXECUTE FUNCTION forbid_account_ledger_mutation()
        """
    )
    op.create_table(
        "balance_holds",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("api_key_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("api_keys.id", ondelete="SET NULL")),
        sa.Column("amount", sa.Numeric(24, 8), nullable=False),
        sa.Column("committed_amount", sa.Numeric(24, 8), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="held"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("pricing_version_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("request_id", name="uq_balance_holds_request"),
        sa.UniqueConstraint("idempotency_key", name="uq_balance_holds_idempotency"),
        sa.CheckConstraint("status IN ('held', 'committed', 'released')", name="ck_balance_holds_status"),
        sa.CheckConstraint("amount > 0", name="ck_balance_holds_amount"),
        sa.CheckConstraint(
            "committed_amount >= 0 AND committed_amount <= amount",
            name="ck_balance_holds_committed",
        ),
    )
    op.create_index("ix_balance_holds_user_id", "balance_holds", ["user_id"])
    op.create_table(
        "usage_settlements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "usage_record_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("usage_records.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("hold_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("balance_holds.id", ondelete="SET NULL")),
        sa.Column("ledger_entry_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("account_ledger.id", ondelete="RESTRICT")),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'settled', 'released', 'disputed')",
            name="ck_usage_settlements_status",
        ),
    )
    op.create_index("ix_usage_settlements_usage_record_id", "usage_settlements", ["usage_record_id"])
    op.create_table(
        "idempotency_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("idempotency_key", sa.String(80), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("response_body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_idempotency_user_key"),
    )
    op.create_table(
        "recharge_products",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("amount", sa.Numeric(24, 8), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("bonus_amount", sa.Numeric(24, 8), nullable=False, server_default="0"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_recharge_products_amount"),
        sa.CheckConstraint("bonus_amount >= 0", name="ck_recharge_products_bonus"),
    )
    products = sa.table(
        "recharge_products",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String()),
        sa.column("amount", sa.Numeric()),
        sa.column("currency", sa.String()),
        sa.column("bonus_amount", sa.Numeric()),
        sa.column("enabled", sa.Boolean()),
        sa.column("sort_order", sa.Integer()),
    )
    op.bulk_insert(
        products,
        [
            {
                "id": UUID("00000000-0000-4000-8000-000000000201"),
                "name": "10 美元",
                "amount": "10",
                "currency": "USD",
                "bonus_amount": "0",
                "enabled": True,
                "sort_order": 1,
            },
            {
                "id": UUID("00000000-0000-4000-8000-000000000202"),
                "name": "50 美元",
                "amount": "50",
                "currency": "USD",
                "bonus_amount": "0",
                "enabled": True,
                "sort_order": 2,
            },
            {
                "id": UUID("00000000-0000-4000-8000-000000000203"),
                "name": "100 美元",
                "amount": "100",
                "currency": "USD",
                "bonus_amount": "0",
                "enabled": True,
                "sort_order": 3,
            },
        ],
    )
    op.create_table(
        "payment_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("order_no", sa.String(40), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("recharge_products.id", ondelete="SET NULL")),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("amount", sa.Numeric(24, 8), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("bonus_amount", sa.Numeric(24, 8), nullable=False, server_default="0"),
        sa.Column("credited_amount", sa.Numeric(24, 8)),
        sa.Column("crypto_amount", sa.Numeric(24, 8)),
        sa.Column("crypto_currency", sa.String(8)),
        sa.Column("network", sa.String(16)),
        sa.Column("pay_address", sa.String(128)),
        sa.Column("payer_address", sa.String(128)),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("locked_rate", sa.Numeric(24, 8)),
        sa.Column("rate_source", sa.String(64)),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider_ref", sa.String(128)),
        sa.Column("tx_hash", sa.String(128)),
        sa.Column("confirmations", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("actual_amount", sa.Numeric(24, 8)),
        sa.Column("risk_status", sa.String(16), nullable=False, server_default="clear"),
        sa.Column("reconcile_status", sa.String(16), nullable=False, server_default="unchecked"),
        sa.Column("idempotency_key", sa.String(80), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("order_no", name="uq_payment_orders_order_no"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_payment_orders_user_idempotency"),
        sa.CheckConstraint(f"status IN ('{_STATUSES}')", name="ck_payment_orders_status"),
        sa.CheckConstraint("channel IN ('mock', 'stripe', 'usdt', 'wechat', 'alipay')", name="ck_payment_orders_channel"),
        sa.CheckConstraint("amount > 0", name="ck_payment_orders_amount"),
        sa.CheckConstraint("risk_status IN ('clear', 'sanctioned', 'large_review')", name="ck_payment_orders_risk"),
        sa.CheckConstraint(
            "reconcile_status IN ('unchecked', 'matched', 'disputed')",
            name="ck_payment_orders_reconcile",
        ),
    )
    op.create_index("ix_payment_orders_user_id", "payment_orders", ["user_id"])
    op.create_table(
        "payment_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("payment_orders.id", ondelete="SET NULL")),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("payload_redacted", sa.Text(), nullable=False),
        sa.Column("signature_ok", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_payment_events_order_id", "payment_events", ["order_id"])
    op.create_table(
        "refund_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("payment_orders.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("amount", sa.Numeric(24, 8), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="requested"),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("executed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("destination_address", sa.String(128), nullable=False, server_default=""),
        sa.Column("tx_hash", sa.String(128)),
        sa.Column("reason", sa.String(256), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("executed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("order_id", name="uq_refund_orders_order"),
        sa.CheckConstraint(
            "status IN ('requested', 'reviewed', 'executed', 'rejected')",
            name="ck_refund_orders_status",
        ),
        sa.CheckConstraint("amount > 0", name="ck_refund_orders_amount"),
        sa.CheckConstraint("executed_by IS NULL OR executed_by <> requested_by", name="ck_refund_orders_executor"),
        sa.CheckConstraint("reviewed_by IS NULL OR reviewed_by <> requested_by", name="ck_refund_orders_reviewer"),
    )
    op.create_table(
        "crypto_deposit_intents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("payment_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("address", sa.String(128), nullable=False),
        sa.Column("network", sa.String(16), nullable=False),
        sa.Column("tail_amount", sa.Numeric(24, 8), nullable=False, server_default="0"),
        sa.Column("tail_status", sa.String(16), nullable=False, server_default="reserved"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("order_id", name="uq_crypto_deposit_intents_order"),
        sa.CheckConstraint("tail_status IN ('reserved', 'used', 'released')", name="ck_crypto_tail_status"),
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_crypto_tail_open
        ON crypto_deposit_intents (address, network, tail_amount)
        WHERE tail_status = 'reserved'
        """
    )
    op.create_table(
        "sanctioned_address_blocks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("address", sa.String(128), nullable=False),
        sa.Column("network", sa.String(16), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(256), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("address", "network", name="uq_sanctioned_address_network"),
    )


def downgrade() -> None:
    op.drop_table("sanctioned_address_blocks")
    op.execute("DROP INDEX IF EXISTS uq_crypto_tail_open")
    op.drop_table("crypto_deposit_intents")
    op.drop_table("refund_orders")
    op.drop_index("ix_payment_events_order_id", table_name="payment_events")
    op.drop_table("payment_events")
    op.drop_index("ix_payment_orders_user_id", table_name="payment_orders")
    op.drop_table("payment_orders")
    op.drop_table("recharge_products")
    op.drop_table("idempotency_records")
    op.drop_index("ix_usage_settlements_usage_record_id", table_name="usage_settlements")
    op.drop_table("usage_settlements")
    op.drop_index("ix_balance_holds_user_id", table_name="balance_holds")
    op.drop_table("balance_holds")
    op.execute("DROP TRIGGER IF EXISTS trg_account_ledger_append_only ON account_ledger")
    op.execute("DROP FUNCTION IF EXISTS forbid_account_ledger_mutation()")
    op.drop_index("ix_account_ledger_user_id", table_name="account_ledger")
    op.drop_table("account_ledger")
    op.drop_table("account_balances")
    op.drop_column("usage_records", "provider_cost")
    op.drop_column("usage_records", "unit_price_snapshot")
    op.drop_column("usage_records", "pricing_version_id")
    op.drop_table("exchange_rates")
    op.drop_index("ix_model_prices_pricing_version_id", table_name="model_prices")
    op.drop_table("model_prices")
    op.drop_index("ix_pricing_versions_model_id", table_name="pricing_versions")
    op.drop_table("pricing_versions")
    op.drop_constraint("ck_notifications_kind", "notifications", type_="check")
    op.create_check_constraint(
        "ck_notifications_kind",
        "notifications",
        "kind IN ('security', 'key_expiry')",
    )
