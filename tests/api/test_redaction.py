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
