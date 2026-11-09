"""用主密钥派生 Fernet 密钥，加密 TOTP 种子。"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.errors import AppError


def _fernet(secret: str) -> Fernet:
    digest = hashlib.sha256(secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_text(secret: str, value: str) -> str:
    return _fernet(secret).encrypt(value.encode()).decode("ascii")


def decrypt_text(secret: str, value: str, *, code: str = "INTERNAL") -> str:
    try:
        return _fernet(secret).decrypt(value.encode()).decode()
    except (InvalidToken, ValueError) as exc:
        raise AppError(500, code) from exc
