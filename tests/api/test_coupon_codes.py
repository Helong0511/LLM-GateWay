"""券码生成与校验算法。"""

from __future__ import annotations

import pytest
from app.ops.coupon_codes import (
    ALPHABET,
    CODE_LEN,
    CouponCodeError,
    format_code,
    generate_code,
    normalize_code,
    validate_code,
)


def test_generate_passes_validate_and_format() -> None:
    code = generate_code()
    assert len(code) == CODE_LEN
    assert all(ch in ALPHABET for ch in code)
    assert validate_code(code) == code
    assert validate_code(format_code(code).lower()) == code
    assert normalize_code(format_code(code)) == code


def test_tampered_check_digit_rejected() -> None:
    code = generate_code()
    bad = code[:-1] + ("2" if code[-1] != "2" else "3")
    with pytest.raises(CouponCodeError):
        validate_code(bad)


def test_illegal_length_and_charset() -> None:
    with pytest.raises(CouponCodeError):
        validate_code("SHORT")
    with pytest.raises(CouponCodeError):
        validate_code("0" * CODE_LEN)  # 0 不在字母表
