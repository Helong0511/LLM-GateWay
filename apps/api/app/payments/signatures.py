"""支付回调验签。Stripe 使用官方 t、v1 方案，USDT 使用正文 HMAC-SHA256。"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime


def stripe_signature_ok(secret: str, payload: bytes, header: str, now: datetime, *, tolerance: int = 300) -> bool:
    if not header or not secret:
        return False
    # 同一头里可能同时出现多个 v1（官方密钥轮换期），必须逐个比对而不是只取最后一个。
    parts: dict[str, list[str]] = {}
    for item in header.split(","):
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        parts.setdefault(key.strip(), []).append(value.strip())
    timestamps = parts.get("t") or []
    signatures = parts.get("v1") or []
    if not timestamps or not signatures or not timestamps[0].isdigit():
        return False
    timestamp = timestamps[0]
    if abs(int(now.timestamp()) - int(timestamp)) > tolerance:
        return False
    signed = timestamp.encode() + b"." + payload
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    matched = False
    for signature in signatures:
        matched |= hmac.compare_digest(expected, signature)
    return matched


def usdt_signature(secret: str, payload: bytes) -> str:
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def usdt_signature_ok(secret: str, payload: bytes, header: str) -> bool:
    if not header or not secret:
        return False
    return hmac.compare_digest(usdt_signature(secret, payload), header.strip())


def ip_allowed(allowlist: str, ip: str) -> bool:
    allowed = {item.strip() for item in allowlist.split(",") if item.strip()}
    return bool(ip) and ip in allowed


def redact_payload(payload: dict[str, object]) -> str:
    blocked = {"secret", "signature", "api_key", "authorization", "password"}
    clean = {key: value for key, value in payload.items() if key.lower() not in blocked}
    return json.dumps(clean, ensure_ascii=False, sort_keys=True, default=str)[:8000]
