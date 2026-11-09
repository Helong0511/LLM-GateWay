"""日志脱敏。密码、令牌、sk- 密钥、Cookie、邮箱、私钥与助记词不得落明文。"""

from __future__ import annotations

import re
from collections.abc import Mapping, MutableMapping
from typing import Any

REDACTED = "***"

_SENSITIVE_KEYS = {
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "cookie",
    "set_cookie",
    "api_key",
    "apikey",
    "private_key",
    "mnemonic",
    "seed",
    "master_key",
    "refresh_token",
    "access_token",
    "totp",
    "recovery_code",
    "session_secret",
    "encryption_master_key",
    "backup_encryption_key",
    "litellm_master_key",
    "database_url",
    "litellm_database_url",
    "redis_url",
    "redis_rate_limit_url",
}

_SECRET_VALUE = re.compile(
    r"(?i)(bearer\s+[a-z0-9\-._~+/]+=*)"
    r"|(sk-[a-z0-9_\-]{8,})"
    r"|(-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----)"
)
_EMAIL = re.compile(
    r"([A-Za-z0-9._%+\-])[A-Za-z0-9._%+\-]*@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})"
)
_MNEMONIC_LINE = re.compile(
    r"(?i)\b(?:mnemonic|seed phrase|助记词)\b\s*[:=]\s*\S+(?:\s+\S+){0,23}"
)


def _key_sensitive(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    if normalized in _SENSITIVE_KEYS:
        return True
    return (
        normalized.endswith("_token")
        or normalized.endswith("_secret")
        or normalized.endswith("_password")
        or "private_key" in normalized
        or "mnemonic" in normalized
    )


def redact_string(text: str) -> str:
    text = _SECRET_VALUE.sub(REDACTED, text)
    text = _MNEMONIC_LINE.sub(REDACTED, text)
    return _EMAIL.sub(lambda match: f"{match.group(1)}***@{match.group(2)}", text)


def redact(value: Any, key: str | None = None) -> Any:
    if key is not None and _key_sensitive(key):
        return REDACTED
    if isinstance(value, Mapping):
        return {str(item_key): redact(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list | tuple):
        redacted = [redact(item, key) for item in value]
        return type(value)(redacted) if isinstance(value, tuple) else redacted
    if isinstance(value, str):
        return redact_string(value)
    return value


def redact_event(
    _logger: Any,
    _method: str,
    event_dict: MutableMapping[str, Any],
) -> Mapping[str, Any]:
    redacted = redact(dict(event_dict))
    if isinstance(redacted, dict):
        return redacted
    return {"event": REDACTED}
