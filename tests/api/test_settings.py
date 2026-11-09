from __future__ import annotations

import pytest
from app.core.config import Settings
from pydantic import ValidationError


def _production(**overrides: object) -> Settings:
    payload: dict[str, object] = {
        "app_env": "production",
        "mock_payments_enabled": False,
        "demo_models_enabled": False,
        "session_secret": "p" * 48,
        "encryption_master_key": "e" * 48,
        "database_url": "postgresql+asyncpg://forge:strong-secret@db.internal:5432/forge",
        "litellm_master_key": "sk-" + ("a" * 40),
        "redis_url": "redis://redis.internal:6379/0",
        "stripe_webhook_secret": "s" * 40,
        "usdt_webhook_secret": "u" * 40,
    }
    payload.update(overrides)
    return Settings(**payload)  # type: ignore[arg-type]


def test_tc_pay_120_production_rejects_mock_payments() -> None:
    with pytest.raises(ValidationError, match="mock 支付"):
        _production(mock_payments_enabled=True)


def test_tc_dep_020_production_rejects_demo_models() -> None:
    with pytest.raises(ValidationError, match="演示模型"):
        _production(demo_models_enabled=True)


def test_production_rejects_dev_secrets() -> None:
    with pytest.raises(ValidationError, match="SESSION_SECRET"):
        _production(session_secret="dev-only-session-secret-change-me-32bytes")


def test_production_accepts_explicit_secrets() -> None:
    settings = _production()
    assert settings.app_env == "production"
    assert settings.mock_payments_enabled is False
    assert settings.demo_models_enabled is False


def test_development_allows_mock() -> None:
    settings = Settings(app_env="development", mock_payments_enabled=True, demo_models_enabled=True)
    assert settings.mock_payments_enabled is True
