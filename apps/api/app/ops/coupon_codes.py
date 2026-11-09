"""优惠券码生成与校验。

格式：10 位载荷 + 1 位校验（共 11 位），字符集避开 0/O、1/I/L。
展示时可按 4-4-3 插入连字符，入库与比对一律去连字符并大写。
"""

from __future__ import annotations

import secrets

# 32 字符，排除易混：0/O、1/I/L
ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
ALPHABET_INDEX = {ch: i for i, ch in enumerate(ALPHABET)}
PAYLOAD_LEN = 10
CODE_LEN = PAYLOAD_LEN + 1  # 含校验位
MAX_GENERATE_ATTEMPTS = 32


class CouponCodeError(ValueError):
    """券码格式或校验失败。"""


def normalize_code(raw: str) -> str:
    cleaned = "".join(ch for ch in raw.strip().upper() if ch not in {"-", " ", "_"})
    return cleaned


def format_code(code: str) -> str:
    normalized = normalize_code(code)
    if len(normalized) != CODE_LEN:
        return normalized
    return f"{normalized[:4]}-{normalized[4:8]}-{normalized[8:]}"


def _check_char(payload: str) -> str:
    if len(payload) != PAYLOAD_LEN:
        raise CouponCodeError(f"主体应为 {PAYLOAD_LEN} 位字符")
    total = 0
    # 类 Luhn：从右加权，模字母表长度
    for i, ch in enumerate(reversed(payload)):
        if ch not in ALPHABET_INDEX:
            raise CouponCodeError("含不支持的字符（已避开易混的 0/O、1/I/L）")
        value = ALPHABET_INDEX[ch]
        if i % 2 == 0:
            value *= 2
            if value >= len(ALPHABET):
                value = value // len(ALPHABET) + (value % len(ALPHABET))
        total += value
    return ALPHABET[(-total) % len(ALPHABET)]


def generate_code(*, rng: secrets.SystemRandom | None = None) -> str:
    picker = rng or secrets.SystemRandom()
    payload = "".join(picker.choice(ALPHABET) for _ in range(PAYLOAD_LEN))
    return payload + _check_char(payload)


def validate_code(raw: str) -> str:
    """校验通过返回规范化券码，否则抛 CouponCodeError。"""
    normalized = normalize_code(raw)
    if len(normalized) != CODE_LEN:
        raise CouponCodeError(
            f"去空格与连字符后应为 {CODE_LEN} 位，当前是 {len(normalized)} 位"
        )
    if any(ch not in ALPHABET_INDEX for ch in normalized):
        raise CouponCodeError("含不支持的字符（已避开易混的 0/O、1/I/L）")
    payload, check = normalized[:-1], normalized[-1]
    if _check_char(payload) != check:
        raise CouponCodeError("校验未通过，请核对是否抄错或漏字")
    return normalized


def looks_like_system_code(raw: str) -> bool:
    normalized = normalize_code(raw)
    return len(normalized) == CODE_LEN and all(ch in ALPHABET_INDEX for ch in normalized)
