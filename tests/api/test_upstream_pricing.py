"""上游 /models 价格解析。"""

from __future__ import annotations

from decimal import Decimal

from app.providers.upstream_pricing import (
    UpstreamModelQuote,
    apply_output_markup,
    classify_price_change,
    extract_token_prices,
    parse_upstream_models,
    suggest_prices,
)


def test_openrouter_style_per_token() -> None:
    rows = parse_upstream_models(
        {
            "data": [
                {
                    "id": "openai/gpt-test",
                    "pricing": {"prompt": "0.00000005", "completion": "0.0000005"},
                }
            ]
        }
    )
    assert len(rows) == 1
    assert rows[0].upstream_name == "openai/gpt-test"
    assert rows[0].input_price == Decimal("0.00000005")
    assert rows[0].output_price == Decimal("0.00000050")


def test_per_million_explicit_fields() -> None:
    input_price, output_price = extract_token_prices(
        {
            "id": "demo",
            "input_cost_per_million_tokens": "3",
            "output_cost_per_million_tokens": "15",
        }
    )
    assert input_price == Decimal("0.00000300")
    assert output_price == Decimal("0.00001500")


def test_large_bare_number_treated_as_per_million() -> None:
    input_price, output_price = extract_token_prices(
        {"id": "demo", "pricing": {"prompt": "2.5", "completion": "10"}}
    )
    assert input_price == Decimal("0.00000250")
    assert output_price == Decimal("0.00001000")


def test_missing_pricing_still_lists_model() -> None:
    rows = parse_upstream_models({"data": [{"id": "only-id"}]})
    assert rows == [UpstreamModelQuote(upstream_name="only-id")]


def test_apply_output_markup_keeps_input() -> None:
    base = UpstreamModelQuote(
        upstream_name="m",
        input_price=Decimal("0.00000100"),
        output_price=Decimal("0.00000200"),
    )
    marked = apply_output_markup(base, Decimal("20"))
    assert marked.input_price == Decimal("0.00000100")
    assert marked.output_price == Decimal("0.00000240")
    assert apply_output_markup(base, Decimal("0")).output_price == Decimal("0.00000200")
    # 上游有输出价时，优先按上游输出价加价
    assert (
        apply_output_markup(base, Decimal("20"), derive_from_input=True).output_price
        == Decimal("0.00000240")
    )


def test_apply_output_markup_derives_output_from_input_when_missing() -> None:
    base = UpstreamModelQuote(upstream_name="m", input_price=Decimal("0.00000100"))
    marked = apply_output_markup(base, Decimal("20"), derive_from_input=True)
    assert marked.input_price == Decimal("0.00000100")
    assert marked.output_price == Decimal("0.00000120")


def test_missing_prices_derive_output_from_default_input() -> None:
    """上游完全没给价时，先用默认输入价补齐，再按输入价加价推导输出价。"""
    adjusted, used_default = suggest_prices(
        UpstreamModelQuote(upstream_name="m"),
        default_input=Decimal("0.00000100"),
        markup_percent=Decimal("20"),
    )
    assert used_default is True
    assert adjusted.input_price == Decimal("0.00000100")
    assert adjusted.output_price == Decimal("0.00000120")


def test_suggest_prices_markup_upstream_output() -> None:
    adjusted, used_default = suggest_prices(
        UpstreamModelQuote(
            upstream_name="m",
            input_price=Decimal("0.00000100"),
            output_price=Decimal("0.00000200"),
        ),
        default_input=Decimal("0.00000100"),
        markup_percent=Decimal("20"),
    )
    assert used_default is False
    assert adjusted.input_price == Decimal("0.00000100")
    assert adjusted.output_price == Decimal("0.00000240")


def test_classify_price_change_increase_and_unchanged() -> None:
    assert (
        classify_price_change(
            old_input=Decimal("0.00000100"),
            old_output=Decimal("0.00000200"),
            new_input=Decimal("0.00000100"),
            new_output=Decimal("0.00000300"),
        )
        == "increased"
    )
    assert (
        classify_price_change(
            old_input=Decimal("0.00000100"),
            old_output=Decimal("0.00000200"),
            new_input=Decimal("0.00000100"),
            new_output=Decimal("0.00000200"),
        )
        == "unchanged"
    )
    assert (
        classify_price_change(
            old_input=None,
            old_output=None,
            new_input=Decimal("0.00000100"),
            new_output=Decimal("0.00000200"),
        )
        == "new"
    )
