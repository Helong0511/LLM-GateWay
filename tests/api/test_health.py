from __future__ import annotations

import pytest
from app.core.config import Settings
from app.core.readiness import StaticProbes
from app.main import create_app
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_healthz_ok(client: AsyncClient) -> None:
    response = await client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["status"] == "ok"
    assert body["error"] is None
    assert body["request_id"]
    assert response.headers["x-request-id"] == body["request_id"]


@pytest.mark.asyncio
async def test_readyz_reports_dependency_checks() -> None:
    app = create_app(Settings(), probes=StaticProbes(postgres_ok=True, redis_ok=False))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/readyz")
    assert response.status_code == 503
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
    assert body["data"]["checks"] == {"postgres": "ok", "redis": "unavailable"}


@pytest.mark.asyncio
async def test_readyz_ready(client: AsyncClient) -> None:
    response = await client.get("/readyz")
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["status"] == "ready"
    assert body["data"]["checks"] == {"postgres": "ok", "redis": "ok"}


@pytest.mark.asyncio
async def test_request_id_is_preserved_when_safe(client: AsyncClient) -> None:
    response = await client.get("/healthz", headers={"X-Request-Id": "req-1234abcd"})
    assert response.headers["x-request-id"] == "req-1234abcd"
    assert response.json()["request_id"] == "req-1234abcd"


@pytest.mark.asyncio
async def test_request_id_rejects_unsafe_header(client: AsyncClient) -> None:
    response = await client.get("/healthz", headers={"X-Request-Id": "bad id"})
    request_id = response.json()["request_id"]
    assert request_id != "bad id"
    assert len(request_id) >= 8


@pytest.mark.asyncio
async def test_meta_declares_operating_mode(client: AsyncClient) -> None:
    response = await client.get("/api/meta")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["product"] == "ForgeAPI"
    assert data["operating_mode"] in {"overseas", "mainland"}
    assert "session_secret" not in response.text
    assert "encryption_master_key" not in response.text


@pytest.mark.asyncio
async def test_versioned_meta_path_is_gone(client: AsyncClient) -> None:
    response = await client.get("/api/v1/meta")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
