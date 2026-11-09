"""分页不得因同时间戳漏数或重复，并返回准确 total。"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from app.auth.emailer import CaptureEmailSender
from app.auth.rbac import ROLE_IDS
from app.core.clock import ManualClock
from app.core.config import Settings
from app.core.paging import clamp_page, page_meta
from app.core.readiness import StaticProbes
from app.db.base import Base
from app.db.models.auth import User, UserRole
from app.db.models.keys import UsageRecord
from app.main import create_app
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

PASSWORD = "Correct-horse-1"


def _token(sender: CaptureEmailSender) -> str:
    match = re.search(r"(?:令牌：|[Tt]oken:\s*)(\S+)", sender.messages[-1].text)
    assert match is not None
    return match.group(1)


@pytest.fixture
async def api(tmp_path: Path) -> AsyncIterator[tuple[AsyncClient, object]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite(dbapi_conn, _record) -> None:  # type: ignore[no-untyped-def]
        dbapi_conn.create_function("char_length", 1, lambda value: len(value) if isinstance(value, str) else None)
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    app = create_app(
        Settings(admin_init_token_path=str(tmp_path / "admin.sha256"), register_ip_hourly_limit=20),
        probes=StaticProbes(postgres_ok=True, redis_ok=True),
    )
    app.state.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    app.state.email_sender = CaptureEmailSender()
    app.state.clock = ManualClock()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, app
    await engine.dispose()


def test_clamp_and_pages() -> None:
    assert clamp_page(0, 0) == (1, 20)
    assert clamp_page(2, 500) == (2, 100)
    assert page_meta(1, 20, 0)["pages"] == 1
    assert page_meta(1, 20, 21)["pages"] == 2
    assert page_meta(1, 20, 40)["pages"] == 2


@pytest.mark.asyncio
async def test_usage_pages_do_not_drop_or_duplicate_same_timestamp(api: tuple[AsyncClient, object]) -> None:
    client, app = api
    registered = await client.post(
        "/api/auth/register",
        json={"email": "page@example.com", "password": PASSWORD, "accept_terms": True, "accept_privacy": True},
    )
    assert registered.status_code == 200, registered.text
    sender: CaptureEmailSender = app.state.email_sender  # type: ignore[attr-defined]
    assert (await client.post("/api/auth/verify-email", json={"email": "page@example.com", "token": _token(sender)})).status_code == 200
    assert (await client.post("/api/auth/login", json={"email": "page@example.com", "password": PASSWORD})).status_code == 200
    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        user = (await session.execute(select(User).where(User.email_normalized == "page@example.com"))).scalar_one()
        session.add(
            UserRole(user_id=user.id, role_id=UUID(ROLE_IDS["admin"]), granted_at=app.state.clock.now())  # type: ignore[attr-defined]
        )
        stamped = datetime(2026, 10, 29, 12, 0, 0, tzinfo=UTC)
        for index in range(25):
            session.add(
                UsageRecord(
                    id=uuid4(),
                    user_id=user.id,
                    api_key_id=None,
                    request_id=f"req-{index}",
                    model_id="demo",
                    started_at=stamped,
                    input_tokens=1,
                    output_tokens=1,
                    http_status=200,
                    latency_ms=1,
                    settlement_status="settled",
                    currency="USD",
                )
            )
        await session.commit()
    first = await client.get("/api/admin/usage?page=1&page_size=20")
    second = await client.get("/api/admin/usage?page=2&page_size=20")
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["data"]["total"] == 25
    assert first.json()["data"]["pages"] == 2
    ids_one = [row["id"] for row in first.json()["data"]["records"]]
    ids_two = [row["id"] for row in second.json()["data"]["records"]]
    assert len(ids_one) == 20
    assert len(ids_two) == 5
    assert len(set(ids_one) & set(ids_two)) == 0
    assert len(set(ids_one) | set(ids_two)) == 25
