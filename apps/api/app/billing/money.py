"""金额只走 Decimal。禁止把 float 引进账本。"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app.core.errors import AppError

QUANTUM = Decimal("0.00000001")

ENTRY_TYPES = frozenset(
    {
        "recharge",
        "consume",
        "refund",
        "adjust",
        "bonus",
        "hold",
        "hold_commit",
        "hold_release",
        "freeze",
        "unfreeze",
        "reconcile_adjust",
        "package_purchase",
        "package_expire",
        "referral_reward",
        "crypto_recharge",
        "crypto_refund",
    }
)

# 余额只被 C 增加、被 D 减少。N 不改余额，只改预扣或冻结。
DEFAULT_DIRECTION: dict[str, str] = {
    "recharge": "C",
    "consume": "D",
    "refund": "D",
    "bonus": "C",
    "hold": "N",
    "hold_commit": "D",
    "hold_release": "N",
    "freeze": "N",
    "unfreeze": "N",
    "package_purchase": "D",
    "package_expire": "C",
    "referral_reward": "C",
    "crypto_recharge": "C",
    "crypto_refund": "D",
}

METERS = frozenset({"input_token", "output_token", "cached_input_token", "image"})


def q(value: Decimal) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise AppError(400, "AMOUNT_BAD_FORMAT")
    return value.quantize(QUANTUM, rounding=ROUND_HALF_UP)


def parse_money(raw: str) -> Decimal:
    try:
        value = Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise AppError(400, "AMOUNT_BAD_FORMAT") from exc
    if not value.is_finite():
        raise AppError(400, "AMOUNT_BAD_FORMAT")
    if value < 0:
        raise AppError(400, "AMOUNT_NEGATIVE")
    exponent = value.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -8:
        raise AppError(400, "AMOUNT_SCALE")
    return q(value)


def format_money(value: Decimal) -> str:
    return format(q(value), "f")


def settlement_currency(operating_mode: str) -> str:
    if operating_mode == "mainland":
        return "CNY"
    return "USD"


def currency_code(value: str) -> str:
    code = value.strip().upper()
    if len(code) < 3 or len(code) > 8 or not code.isalpha():
        raise AppError(400, "CURRENCY_INVALID")
    return code
