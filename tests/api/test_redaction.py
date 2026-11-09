from __future__ import annotations

from app.core.redaction import REDACTED, redact


def test_redacts_sensitive_keys_and_nested_values() -> None:
    payload = {
        "password": "hunter2",
        "Authorization": "Bearer abc.def.ghi",
        "cookie": "session=1",
        "nested": {"api_key": "sk-should-not-appear-here", "ok": True},
        "note": "contact ada@example.com about sk-realsecretkey",
        "mnemonic": "abandon ability able about above absent absorb abstract absurd abuse access accident",
    }
    cleaned = redact(payload)
    assert cleaned["password"] == REDACTED
    assert cleaned["Authorization"] == REDACTED
    assert cleaned["cookie"] == REDACTED
    assert cleaned["nested"]["api_key"] == REDACTED
    assert cleaned["nested"]["ok"] is True
    assert cleaned["mnemonic"] == REDACTED
    assert "hunter2" not in str(cleaned)
    assert "sk-should-not-appear-here" not in str(cleaned)
    assert "sk-realsecretkey" not in str(cleaned)
    assert "a***@example.com" in cleaned["note"]


def test_redacts_private_key_block() -> None:
    text = "-----BEGIN PRIVATE KEY-----\nABCDEF\n-----END PRIVATE KEY-----"
    cleaned = redact(text)
    assert "ABCDEF" not in str(cleaned)
    assert cleaned == REDACTED


def test_redacts_new_secret_settings() -> None:
    """新增密钥字段不能因为名字不匹配而落进日志。"""
    payload = {
        "backup_encryption_key": "Zm9yZ2UtYmFja3VwLWtleS1ub3QtcmVhbA==",
        "litellm_database_url": "postgresql://forge:pw@postgres/litellm",
        "redis_rate_limit_url": "redis://:pw@redis:6379/1",
        "metrics_token": "scrape-token",
    }
    cleaned = redact(payload)
    for key in payload:
        assert cleaned[key] == REDACTED, key
