from __future__ import annotations

import app.db.models as _models
import pytest
from app.core.config import Settings
from app.core.readiness import StaticProbes
from app.main import create_app
from httpx import ASGITransport, AsyncClient

_ = _models


@pytest.fixture
async def client() -> AsyncClient:
    app = create_app(Settings(), probes=StaticProbes(postgres_ok=True, redis_ok=True))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
