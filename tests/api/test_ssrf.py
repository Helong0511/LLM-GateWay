from __future__ import annotations

import ipaddress

import httpx
import pytest
from app.core.errors import AppError
from app.security.ssrf import fetch_checked, inspect_url


async def _resolver(host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    mapping = {
        "upstream.test": "8.8.8.8",
        "inside.test": "10.1.2.3",
    }
    if host not in mapping:
        raise AppError(400, "VALIDATION_ERROR", "域名无法解析")
    return [ipaddress.ip_address(mapping[host])]


@pytest.mark.asyncio
async def test_ssrf_rejects_private_metadata_and_unlisted_self_hosted() -> None:
    with pytest.raises(AppError, match="私有或保留"):
        await inspect_url("http://127.0.0.1/x", resolver=_resolver, allowlist=set(), endpoint_kind="openai")
    with pytest.raises(AppError, match="云元数据"):
        await inspect_url(
            "http://metadata.google.internal/",
            resolver=_resolver,
            allowlist={"metadata.google.internal"},
            endpoint_kind="self_hosted",
        )
    with pytest.raises(AppError, match="云元数据"):
        await inspect_url("http://169.254.169.254/latest", resolver=_resolver, allowlist=set(), endpoint_kind="openai")
    with pytest.raises(AppError, match="白名单"):
        await inspect_url("http://10.1.2.3:11434", resolver=_resolver, allowlist=set(), endpoint_kind="ollama")
    decision = await inspect_url(
        "http://10.1.2.3:11434",
        resolver=_resolver,
        allowlist={"10.1.2.3"},
        endpoint_kind="self_hosted",
    )
    assert str(decision.ip) == "10.1.2.3"
    public = await inspect_url("https://upstream.test/v1", resolver=_resolver, allowlist=set(), endpoint_kind="openai")
    assert str(public.ip) == "8.8.8.8"


@pytest.mark.asyncio
async def test_ssrf_does_not_follow_redirect_to_metadata() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.host)
        if request.url.host == "8.8.8.8":
            return httpx.Response(302, headers={"location": "http://169.254.169.254/latest"})
        return httpx.Response(200, text="should-not-reach")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AppError, match="云元数据"):
            await fetch_checked(
                client,
                "GET",
                "http://upstream.test/v1/models",
                resolver=_resolver,
                allowlist=set(),
                endpoint_kind="openai",
            )
    assert seen == ["8.8.8.8"]
