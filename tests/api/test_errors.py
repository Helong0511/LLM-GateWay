from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from app.core.config import Settings
from app.core.readiness import StaticProbes
from app.main import create_app
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_unknown_route_uses_error_envelope(client: AsyncClient) -> None:
    response = await client.get("/missing")
    assert response.status_code == 404
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "NOT_FOUND"
    assert "traceback" not in response.text.lower()


@pytest.mark.asyncio
async def test_validation_error_does_not_echo_secret_input() -> None:
    app = create_app(Settings(), probes=StaticProbes(True, True))

    @app.post("/echo-check")
    async def echo_check(payload: dict[str, str]) -> dict[str, str]:
        return payload

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/echo-check", json=["not-an-object"])
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "not-an-object" not in response.text


@pytest.mark.asyncio
async def test_unhandled_error_hides_internals() -> None:
    app = create_app(Settings(), probes=StaticProbes(True, True))

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("sk-supersecretkeyvalue password=hunter2")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/boom")
    assert response.status_code == 500
    text = response.text
    assert response.json()["error"]["code"] == "INTERNAL"
    assert "sk-supersecretkeyvalue" not in text
    assert "hunter2" not in text
    assert "Traceback" not in text


@pytest.mark.asyncio
async def test_body_over_limit_is_rejected() -> None:
    app = create_app(Settings(max_body_bytes=32), probes=StaticProbes(True, True))
    transport = ASGITransport(app=app)
    async def _chunks() -> AsyncIterator[bytes]:
        for _ in range(3):
            yield b"y" * 20

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/healthz", content=b"x" * 64)
        # chunked（无 Content-Length）也必须被累计字节数拦住；
        # /healthz 只接受 GET，405 不会读 body，所以这里打到真正解析 body 的路由。
        streamed = await client.post("/api/auth/login", content=_chunks())
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"
    assert streamed.status_code == 413
    assert streamed.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"
