"""从上游 /models 条目中尽力解析每 token 单价。

支持常见形态：
- OpenRouter：pricing.prompt / pricing.completion（每 token）
- LiteLLM 风格：input_cost_per_token / output_cost_per_token
- 每百万 token：*_per_million* 或数值明显偏大时按 1e6 折算
解析失败返回 None，不阻断同步。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from app.billing.money import QUANTUM, q


@dataclass(frozen=True)
class UpstreamModelQuote:
    upstream_name: str
    input_price: Decimal | None = None
    output_price: Decimal | None = None


def suggest_prices(
    quote: UpstreamModelQuote,
    *,
    default_input: Decimal,
    markup_percent: Decimal,
) -> tuple[UpstreamModelQuote, bool]:
    """生成同步建议价，返回 (建议价, 是否用过兜底规则)。

    - 上游缺输入价：用平台默认输入价补齐；
    - 上游有输出价：输出建议价 = 上游输出价 × (1+加价%)；
    - 上游缺输出价：输出建议价 = 输入建议价 × (1+加价%)，不再使用默认输出价。
    """
    used_default = quote.input_price is None or quote.output_price is None
    input_price = q(default_input) if quote.input_price is None else quote.input_price
    filled = UpstreamModelQuote(
        upstream_name=quote.upstream_name,
        input_price=input_price,
        output_price=quote.output_price,
    )
    adjusted = apply_output_markup(
        filled,
        markup_percent,
        derive_from_input=quote.output_price is None,
    )
    return adjusted, used_default


def apply_output_markup(
    quote: UpstreamModelQuote,
    markup_percent: Decimal,
    *,
    derive_from_input: bool = False,
) -> UpstreamModelQuote:
    """对输出单价按百分比加价；输入价保持上游原值。

    derive_from_input=True 且上游没有输出价时，用输入价作为加价基数推导输出价，
    即输出建议价 = 输入价 × (1+加价%)，避免把平台默认输出价再乘一次导致翻倍。
    """
    if quote.output_price is not None:
        if markup_percent == 0:
            return quote
        factor = Decimal("1") + (markup_percent / Decimal("100"))
        output_price = q(quote.output_price * factor)
    elif derive_from_input and quote.input_price is not None:
        factor = Decimal("1") + (markup_percent / Decimal("100"))
        output_price = q(quote.input_price * factor)
    else:
        return quote
    return UpstreamModelQuote(
        upstream_name=quote.upstream_name,
        input_price=quote.input_price,
        output_price=output_price,
    )


def meter_direction(old: Decimal | None, new: Decimal | None) -> str | None:
    """比较单侧单价：new / up / down / same；无新价返回 None。"""
    if new is None:
        return None
    if old is None:
        return "new"
    if new > old:
        return "up"
    if new < old:
        return "down"
    return "same"


def classify_price_change(
    *,
    old_input: Decimal | None,
    old_output: Decimal | None,
    new_input: Decimal | None,
    new_output: Decimal | None,
) -> str | None:
    """
    相对已有建议价的整体变动：
    - None：本次没有可写入的新价
    - new：首次写入
    - unchanged：与已有一致
    - increased：任一方向上涨且无下跌
    - decreased：任一方向下跌且无上涨
    - mixed：有涨有跌
    """
    directions = [
        item
        for item in (
            meter_direction(old_input, new_input),
            meter_direction(old_output, new_output),
        )
        if item is not None
    ]
    if not directions:
        return None
    if all(item == "new" for item in directions):
        return "new"
    meaningful = [item for item in directions if item != "same"]
    if not meaningful:
        return "unchanged"
    # 首次补全某一侧也算 new；若另一侧已存在且上涨，优先按涨跌归类
    ups = meaningful.count("up")
    downs = meaningful.count("down")
    news = meaningful.count("new")
    if ups and downs:
        return "mixed"
    if ups:
        return "increased"
    if downs:
        return "decreased"
    if news:
        return "new"
    return "unchanged"


def parse_upstream_models(payload: object) -> list[UpstreamModelQuote]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if not isinstance(data, list):
        return []
    rows: list[UpstreamModelQuote] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = item.get("id")
        if not isinstance(name, str) or not name.strip():
            continue
        input_price, output_price = extract_token_prices(item)
        rows.append(
            UpstreamModelQuote(
                upstream_name=name.strip(),
                input_price=input_price,
                output_price=output_price,
            )
        )
    return rows


def extract_token_prices(item: dict[str, Any]) -> tuple[Decimal | None, Decimal | None]:
    raw_p = item.get("pricing")
    pricing: dict[str, Any] = raw_p if isinstance(raw_p, dict) else {}
    raw_price = item.get("price")
    price: dict[str, Any] = raw_price if isinstance(raw_price, dict) else {}

    input_raw = _first_present(
        item,
        pricing,
        price,
        keys=(
            "input_cost_per_token",
            "prompt_cost_per_token",
            "input_price",
            "prompt_price",
            "prompt",
            "input",
        ),
        million_keys=(
            "input_cost_per_million_tokens",
            "prompt_cost_per_million_tokens",
            "input_cost_per_million",
            "prompt_cost_per_million",
        ),
    )
    output_raw = _first_present(
        item,
        pricing,
        price,
        keys=(
            "output_cost_per_token",
            "completion_cost_per_token",
            "output_price",
            "completion_price",
            "completion",
            "output",
        ),
        million_keys=(
            "output_cost_per_million_tokens",
            "completion_cost_per_million_tokens",
            "output_cost_per_million",
            "completion_cost_per_million",
        ),
    )
    return _normalize_token_price(input_raw), _normalize_token_price(output_raw)


def _first_present(
    item: dict[str, Any],
    pricing: dict[str, Any],
    price: dict[str, Any],
    *,
    keys: tuple[str, ...],
    million_keys: tuple[str, ...],
) -> tuple[object, bool] | None:
    for key in million_keys:
        for source in (item, pricing, price):
            if key in source and source[key] is not None:
                return source[key], True
    for key in keys:
        for source in (item, pricing, price):
            if key in source and source[key] is not None:
                return source[key], False
    return None


def _normalize_token_price(raw: tuple[object, bool] | None) -> Decimal | None:
    if raw is None:
        return None
    value, is_per_million = raw
    parsed = _to_decimal(value)
    if parsed is None:
        return None
    if is_per_million or parsed >= Decimal("0.01"):
        # 显式百万价，或绝对值大到不像每 token（例如 3 表示 $3/1M）
        parsed = parsed / Decimal("1000000")
    try:
        return q(parsed)
    except Exception:
        return None


def _to_decimal(value: object) -> Decimal | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        number = value
    elif isinstance(value, int):
        number = Decimal(value)
    elif isinstance(value, float):
        # 上游偶发 float；转 str 再 Decimal，避免二进制误差直接入库
        number = Decimal(str(value))
    elif isinstance(value, str):
        text = value.strip().replace("$", "").replace(",", "")
        if not text:
            return None
        try:
            number = Decimal(text)
        except (InvalidOperation, ValueError):
            return None
    else:
        return None
    if not number.is_finite() or number < 0:
        return None
    # 过小且非 0 也可能有效（OpenRouter）；仅拒绝低于 quantum 的非零噪声可在 q 时处理
    try:
        quantized = number.quantize(QUANTUM)
    except InvalidOperation:
        return None
    return quantized
