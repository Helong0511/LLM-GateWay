"""Argon2id 密码哈希与口令规则。"""

from __future__ import annotations

import re

from pwdlib import PasswordHash

from app.core.errors import AppError

_HASHER = PasswordHash.recommended()
_DUMMY: str | None = None
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}$")
_COMMON = {
    "password123",
    "password1234",
    "1234567890",
    "qwerty1234",
    "admin12345",
    "letmein123",
    "welcome123",
    "changeme123",
    "abc1234567",
    "passw0rd12",
}


def hash_password(password: str) -> str:
    return str(_HASHER.hash(password))


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bool(_HASHER.verify(password, hashed))
    except Exception:
        return False


def dummy_password_hash() -> str:
    global _DUMMY
    if _DUMMY is None:
        _DUMMY = hash_password("dummy-password-not-used")
    return _DUMMY


def normalize_email(email: str) -> str:
    return email.strip().lower()


def validate_email(email: str) -> str:
    normalized = normalize_email(email)
    if _EMAIL.fullmatch(normalized) is None or "." not in normalized.split("@", 1)[1]:
        raise AppError(400, "EMAIL_INVALID")
    return normalized


def validate_password(password: str, email: str) -> None:
    if len(password) < 10 or len(password) > 128:
        raise AppError(400, "PASSWORD_LENGTH")
    if re.search(r"[A-Za-z]", password) is None or re.search(r"\d", password) is None:
        raise AppError(400, "PASSWORD_COMPLEXITY")
    if password.lower() in _COMMON or password.lower() == email.lower():
        raise AppError(400, "PASSWORD_COMMON")
