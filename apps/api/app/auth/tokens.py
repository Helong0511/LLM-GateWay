"""令牌只以 SHA-256 摘要入库。明文只出现在当次邮件或响应里。"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime


def new_secret() -> str:
    return secrets.token_urlsafe(32)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def same_digest(stored: str, raw: str) -> bool:
    return hmac.compare_digest(stored, digest(raw))


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
