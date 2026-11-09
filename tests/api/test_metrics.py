from __future__ import annotations

import pytest
from app.core.config import Settings
from app.core.metrics import REGISTRY, route_label
from app.core.readiness import StaticProbes
from app.main import create_app
from httpx import ASGITransport, AsyncClient


def test_route_label_folds_ids_to_control_cardinality() -> None:
    folded = route_label("/api/admin/providers/123e4567-e89b-12d3-a456-426614174000/credentials")
    assert folded == "/api/admin/providers/{id}"
    assert route_label("/v1/chat/completions") == "/v1/chat/completions"
    assert route_label("/pricing/42") == "/pricing/{id}"
    assert route_label("/") == "/"
    # 超长路径截断到四段，扫描器无法制造无限多时间序列
    assert route_label("/a/b/c/d/e/f").count("/") == 4


@pytest.mark.asyncio
async def test_metrics_endpoint_requires_token_and_records_requests() -> None:
    REGISTRY.reset()
    app = create_app(
        Settings(metrics_enabled=True, metrics_token="scrape-token"),
        probes=StaticProbes(True, True),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.get("/healthz")
        unauthorized = await client.get("/metrics")
        authorized = await client.get(
            "/metrics", headers={"authorization": "Bearer scrape-token"}
        )

    assert unauthorized.status_code == 401
    assert authorized.status_code == 200
    assert authorized.headers["content-type"].startswith("text/plain; version=0.0.4")
    body = authorized.text
    assert (
        'forge_http_requests_total{method="GET",route="/healthz",status="200"} 1' in body
    )
    assert 'forge_http_request_duration_seconds_bucket{method="GET",route="/healthz",le="+Inf"} 1' in body
    assert "# TYPE forge_http_inflight_requests gauge" in body
    assert "forge_api_errors_total" in body


@pytest.mark.asyncio
async def test_metrics_can_be_disabled() -> None:
    REGISTRY.reset()
    app = create_app(Settings(metrics_enabled=False), probes=StaticProbes(True, True))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/metrics")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_app_errors_are_counted_by_code() -> None:
    REGISTRY.reset()
    app = create_app(Settings(metrics_enabled=True), probes=StaticProbes(True, True))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.get("/missing")
        metrics = await client.get("/metrics")
    assert 'forge_api_errors_total{code="NOT_FOUND"} 1' in metrics.text
