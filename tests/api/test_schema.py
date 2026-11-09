from __future__ import annotations

from app.db.base import Base
from app.db.models import auth as _auth
from app.db.models import billing as _billing
from app.db.models import keys as _keys
from app.db.models import notify as _notify
from app.db.models import payments as _payments
from app.db.models import providers as _providers

_ = (_auth, _billing, _keys, _notify, _payments, _providers)


def test_stage2_auth_tables_are_mapped() -> None:
    names = set(Base.metadata.tables)
    expected = {
        "users",
        "roles",
        "permissions",
        "role_permissions",
        "user_roles",
        "sessions",
        "email_verification_tokens",
        "password_reset_tokens",
        "email_change_tokens",
        "totp_recovery_codes",
        "mfa_challenges",
        "user_profiles",
        "login_devices",
        "api_keys",
        "usage_records",
        "notifications",
        "notification_preferences",
        "providers",
        "provider_credentials",
        "endpoint_allowlist",
        "model_catalog",
        "model_deployments",
        "model_sync_jobs",
        "model_test_runs",
        "audit_events",
        "pricing_versions",
        "model_prices",
        "exchange_rates",
        "account_balances",
        "account_ledger",
        "balance_holds",
        "usage_settlements",
        "idempotency_records",
        "recharge_products",
        "payment_orders",
        "payment_events",
        "refund_orders",
        "crypto_deposit_intents",
        "sanctioned_address_blocks",
    }
    assert expected <= names
    assert "balance" not in Base.metadata.tables["users"].columns
    assert "pricing_version_id" in Base.metadata.tables["usage_records"].columns
