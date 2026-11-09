"""上游供应商 URL 拼接与预设。"""

from __future__ import annotations

from app.providers.presets import auth_headers, join_api_url, list_presets, resolve_preset


def test_join_avoids_double_v1() -> None:
    assert join_api_url("https://api.openai.com/v1", "/models") == "https://api.openai.com/v1/models"
    assert join_api_url("https://api.openai.com/v1", "/v1/models") == "https://api.openai.com/v1/models"
    assert join_api_url("https://api.anthropic.com", "/v1/models") == "https://api.anthropic.com/v1/models"
    assert (
        join_api_url("https://generativelanguage.googleapis.com/v1beta/openai", "/models")
        == "https://generativelanguage.googleapis.com/v1beta/openai/models"
    )


def test_presets_cover_major_upstreams() -> None:
    codes = {item["code"] for item in list_presets()}
    assert {"openai", "anthropic", "gemini_openai", "azure_openai", "deepseek", "openrouter", "ollama"} <= codes


def test_anthropic_auth_headers() -> None:
    headers = auth_headers("anthropic", "https://api.anthropic.com", "sk-ant-test")
    assert headers["x-api-key"] == "sk-ant-test"
    assert headers["anthropic-version"]
    assert resolve_preset("compatible", "https://openrouter.ai/api/v1").code == "openrouter"
