"""API Key 加密工具：AES-256-GCM，带版本头，密钥从环境变量派生。

设计要点：
- 密钥用 HMAC-SHA256(encryption_master_key, 固定盐) 派生得到 32-byte AES 密钥，
  避免直接把 master key 用作对称密钥，也便于以后轮换（改盐 = 换算法版本）。
- 密文字符串统一格式：``v1|<base64url iv>|<base64url tag>|<base64url ciphertext>``。
- 拒绝使用开发默认密钥（``dev-only`` 标记），防止线上误留默认值导致密钥可预测。
- 解密失败抛出 :class:`KeyDecryptionError`，调用方必须显式处理，禁止静默吞错。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# 拒绝使用包含以下任一标记的 master key。
_DEV_MARKERS = ("dev-only", "change-me", "forge-dev-only", "encryption-master-key-32bytes")
# 密钥派生用途（固定盐），一旦发布不可改动；更换时需升级版本号并迁移历史数据。
_DERIVE_SALT = b"forge:api-key-enc:v1"
_VERSION = "v1"


class KeyDecryptionError(RuntimeError):
    """密文不合法、算法版本不支持或完整性校验失败时抛出。"""


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _derive_key(master: str) -> bytes:
    """从配置项派生出 32-byte AES-256 密钥。"""
    if any(marker in master.lower() for marker in _DEV_MARKERS):
        raise KeyDecryptionError(
            "refusing to use development ENCRYPTION_MASTER_KEY; set a strong value via environment"
        )
    if len(master) < 32:
        raise KeyDecryptionError("ENCRYPTION_MASTER_KEY must be at least 32 bytes")
    return hmac.new(master.encode("utf-8"), _DERIVE_SALT, hashlib.sha256).digest()


def encrypt(plaintext: str, master_key: str | None = None) -> str:
    """使用 AES-256-GCM 加密 ``plaintext``，返回带版本头的密文字符串。

    ``master_key`` 为 ``None`` 时读取环境变量 ``ENCRYPTION_MASTER_KEY``。
    """
    key = _derive_key(master_key or os.environ.get("ENCRYPTION_MASTER_KEY", ""))
    iv = secrets.token_bytes(12)  # GCM 推荐 12-byte nonce
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(iv, plaintext.encode("utf-8"), None)
    # AESGCM.encrypt 输出 = ciphertext || 16-byte tag
    tag = ciphertext[-16:]
    body = ciphertext[:-16]
    return f"{_VERSION}|{_b64url(iv)}|{_b64url(tag)}|{_b64url(body)}"


def decrypt(payload: str, master_key: str | None = None) -> str:
    """解密 ``encrypt()`` 输出的密文字符串。

    密文被篡改、算法版本不匹配或配置密钥不可用时抛出 :class:`KeyDecryptionError`。
    """
    if not payload:
        raise KeyDecryptionError("empty ciphertext")
    parts = payload.split("|")
    if len(parts) != 4 or parts[0] != _VERSION:
        raise KeyDecryptionError("unsupported or malformed ciphertext")
    key = _derive_key(master_key or os.environ.get("ENCRYPTION_MASTER_KEY", ""))
    try:
        iv = _b64url_decode(parts[1])
        tag = _b64url_decode(parts[2])
        body = _b64url_decode(parts[3])
    except Exception as exc:  # noqa: BLE001  -- 解码错误统一转业务异常
        raise KeyDecryptionError("invalid ciphertext encoding") from exc
    aesgcm = AESGCM(key)
    try:
        plain = aesgcm.decrypt(iv, body + tag, None)
    except Exception as exc:  # noqa: BLE001  -- GCM 完整性失败统一转业务异常
        raise KeyDecryptionError("decryption failed or ciphertext tampered") from exc
    return plain.decode("utf-8")


def is_configured(master_key: str | None = None) -> bool:
    """判断加密主密钥是否已正确配置（非开发默认）。"""
    master = master_key or os.environ.get("ENCRYPTION_MASTER_KEY", "")
    if not master or len(master) < 32:
        return False
    return not any(marker in master.lower() for marker in _DEV_MARKERS)
