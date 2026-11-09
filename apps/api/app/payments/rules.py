"""USDT 确认数、金额分档和锁价偏差。纯函数，不访问数据库。"""

from __future__ import annotations

from decimal import Decimal


def required_confirmations(amount_usd: Decimal) -> int:
    if amount_usd < Decimal("100"):
        return 1
    if amount_usd <= Decimal("1000"):
        return 2
    return 3


def needs_large_review(amount_usd: Decimal) -> bool:
    return amount_usd > Decimal("1000")


def payment_band(expected: Decimal, actual: Decimal) -> str:
    if actual < expected:
        return "underpaid"
    if actual > expected:
        return "overpaid"
    return "exact"


def rate_within_peg(rate: Decimal, limit: Decimal) -> bool:
    if rate <= 0:
        return False
    return abs(rate - Decimal("1")) <= limit
