"""上游供应商官方接入预设（按公开文档整理）。

base_url 约定与 OpenAI SDK 一致：指向「已含版本段」的根，例如 .../v1。
请求路径再拼 models / chat/completions，避免出现 /v1/v1。

label / note 使用英文作为 API 默认值；管理端展示文案由前端按 code 做 i18n。
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class ProviderPreset:
    code: str
    label: str
    kind: str
    protocol: str
    base_url: str
    auth: str  # bearer | x-api-key | azure-key
    models_path: str
    chat_path: str
    note: str
    needs_allowlist: bool = False
    extra_headers: dict[str, str] | None = None


PRESETS: tuple[ProviderPreset, ...] = (
    ProviderPreset(
        code="openai",
        label="OpenAI",
        kind="openai",
        protocol="openai",
        base_url="https://api.openai.com/v1",
        auth="bearer",
        models_path="/models",
        chat_path="/chat/completions",
        note="Authorization: Bearer sk-...; optional OpenAI-Organization / OpenAI-Project.",
    ),
    ProviderPreset(
        code="anthropic",
        label="Anthropic Claude",
        kind="anthropic",
        protocol="anthropic",
        base_url="https://api.anthropic.com",
        auth="x-api-key",
        models_path="/v1/models",
        chat_path="/v1/messages",
        note="x-api-key or Bearer; anthropic-version required (e.g. 2023-06-01).",
        extra_headers={"anthropic-version": "2023-06-01"},
    ),
    ProviderPreset(
        code="gemini_openai",
        label="Google Gemini (OpenAI-compatible)",
        kind="compatible",
        protocol="openai",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        auth="bearer",
        models_path="/models",
        chat_path="/chat/completions",
        note="Use a Gemini API key as Bearer; path must include /openai.",
    ),
    ProviderPreset(
        code="azure_openai",
        label="Azure OpenAI (v1)",
        kind="cloud",
        protocol="openai",
        base_url="https://YOUR-RESOURCE.openai.azure.com/openai/v1",
        auth="bearer",
        models_path="/models",
        chat_path="/chat/completions",
        note="Replace YOUR-RESOURCE with your resource name; model is the deployment name. New v1 may omit api-version.",
    ),
    ProviderPreset(
        code="deepseek",
        label="DeepSeek",
        kind="compatible",
        protocol="openai",
        base_url="https://api.deepseek.com/v1",
        auth="bearer",
        models_path="/models",
        chat_path="/chat/completions",
        note="OpenAI-compatible; https://api.deepseek.com (without /v1) also works.",
    ),
    ProviderPreset(
        code="openrouter",
        label="OpenRouter",
        kind="compatible",
        protocol="openai",
        base_url="https://openrouter.ai/api/v1",
        auth="bearer",
        models_path="/models",
        chat_path="/chat/completions",
        note="Bearer = OpenRouter key; model looks like openai/gpt-4o.",
    ),
    ProviderPreset(
        code="apispace",
        label="ApiSpace",
        kind="compatible",
        protocol="openai",
        base_url="https://apispace.ai/v1",
        auth="bearer",
        models_path="/models",
        chat_path="/chat/completions",
        note="OpenAI-compatible public gateway; base_url is https://apispace.ai/v1 (not .../chat/completions).",
    ),
    ProviderPreset(
        code="ollama",
        label="Ollama (local)",
        kind="ollama",
        protocol="openai",
        base_url="http://127.0.0.1:11434/v1",
        auth="bearer",
        models_path="/models",
        chat_path="/chat/completions",
        note="Local installs ignore the secret (use ollama); host must be allowlisted.",
        needs_allowlist=True,
    ),
    ProviderPreset(
        code="compatible",
        label="Generic OpenAI-compatible",
        kind="compatible",
        protocol="openai",
        base_url="https://example.com/v1",
        auth="bearer",
        models_path="/models",
        chat_path="/chat/completions",
        note="Any OpenAI-compatible gateway; base_url should include /v1.",
    ),
    ProviderPreset(
        code="self_hosted",
        label="Self-hosted endpoint",
        kind="self_hosted",
        protocol="openai",
        base_url="https://llm.internal.example/v1",
        auth="bearer",
        models_path="/models",
        chat_path="/chat/completions",
        note="Private/internal hosts must be allowlisted first.",
        needs_allowlist=True,
    ),
)

PRESET_BY_CODE = {item.code: item for item in PRESETS}
PRESET_BY_KIND = {item.kind: item for item in PRESETS}


def list_presets() -> list[dict[str, object]]:
    return [
        {
            "code": item.code,
            "label": item.label,
            "kind": item.kind,
            "protocol": item.protocol,
            "base_url": item.base_url,
            "auth": item.auth,
            "models_path": item.models_path,
            "chat_path": item.chat_path,
            "note": item.note,
            "needs_allowlist": item.needs_allowlist,
            "extra_headers": item.extra_headers or {},
        }
        for item in PRESETS
    ]


def resolve_preset(kind: str, base_url: str) -> ProviderPreset:
    host = (urlparse(base_url).hostname or "").lower()
    if "anthropic.com" in host or kind == "anthropic":
        return PRESET_BY_CODE["anthropic"]
    if "generativelanguage.googleapis.com" in host:
        return PRESET_BY_CODE["gemini_openai"]
    if "openai.azure.com" in host:
        return PRESET_BY_CODE["azure_openai"]
    if "deepseek.com" in host:
        return PRESET_BY_CODE["deepseek"]
    if "openrouter.ai" in host:
        return PRESET_BY_CODE["openrouter"]
    if "apispace.ai" in host:
        return PRESET_BY_CODE["apispace"]
    if kind == "ollama" or host in {"127.0.0.1", "localhost"} and ":11434" in base_url:
        return PRESET_BY_CODE["ollama"]
    if kind == "openai":
        return PRESET_BY_CODE["openai"]
    if kind == "self_hosted":
        return PRESET_BY_CODE["self_hosted"]
    return PRESET_BY_CODE["compatible"]


def join_api_url(base_url: str, path: str) -> str:
    """把官方 base_url 与相对路径拼成完整 URL，避免 /v1/v1。"""
    root = base_url.strip().rstrip("/")
    rel = path if path.startswith("/") else f"/{path}"
    # 已带版本根时，path 应是 /models；未带时 path 常是 /v1/models
    if root.lower().endswith("/v1") and rel.startswith("/v1/"):
        rel = rel[3:]
    return f"{root}{rel}"


def auth_headers(kind: str, base_url: str, secret: str) -> dict[str, str]:
    preset = resolve_preset(kind, base_url)
    headers: dict[str, str] = {"content-type": "application/json"}
    if preset.extra_headers:
        headers.update(preset.extra_headers)
    if preset.auth == "x-api-key":
        headers["x-api-key"] = secret
        headers.setdefault("authorization", f"Bearer {secret}")
    else:
        headers["authorization"] = f"Bearer {secret}"
    return headers


def endpoint_paths(kind: str, base_url: str) -> tuple[str, str]:
    preset = resolve_preset(kind, base_url)
    return preset.models_path, preset.chat_path


def default_protocol(kind: str) -> str:
    preset = PRESET_BY_KIND.get(kind) or PRESET_BY_CODE["compatible"]
    return preset.protocol
