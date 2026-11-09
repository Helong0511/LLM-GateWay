from __future__ import annotations

from collections.abc import AsyncIterator
from decimal import Decimal
from pathlib import Path

import pytest
from app.auth.emailer import CaptureEmailSender
from app.core.clock import ManualClock
from app.core.config import Settings
from app.core.errors import AppError
from app.core.readiness import StaticProbes
from app.core.redaction import REDACTED, redact
from app.db.base import Base
from app.main import create_app
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

PASSWORD = "Correct-horse-1"


@pytest.fixture
async def api(tmp_path: Path) -> AsyncIterator[tuple[AsyncClient, object]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite(dbapi_conn, _record) -> None:  # type: ignore[no-untyped-def]
        dbapi_conn.create_function("char_length", 1, lambda value: len(value) if isinstance(value, str) else None)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    app = create_app(
        Settings(admin_init_token_path=str(tmp_path / "admin.sha256")),
        probes=StaticProbes(postgres_ok=True, redis_ok=True),
    )
    app.state.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    app.state.email_sender = CaptureEmailSender()
    app.state.clock = ManualClock()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, app
    await engine.dispose()


async def _login(client: AsyncClient, app: object, email: str) -> None:
    import re

    registered = await client.post(
        "/api/auth/register",
        json={"email": email, "password": PASSWORD, "accept_terms": True, "accept_privacy": True},
    )
    assert registered.status_code == 200, registered.text
    sender: CaptureEmailSender = app.state.email_sender  # type: ignore[attr-defined]
    token = re.search(r"(?:令牌：|[Tt]oken:\s*)(\S+)", sender.messages[-1].text)
    assert token is not None
    verified = await client.post("/api/auth/verify-email", json={"email": email, "token": token.group(1)})
    assert verified.status_code == 200, verified.text
    logged = await client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert logged.status_code == 200, logged.text


@pytest.mark.asyncio
async def test_tc_key_create_lists_prefix_and_revoke_blocks_use(api: tuple[AsyncClient, object]) -> None:
    client, app = api
    await _login(client, app, "key@example.com")
    created = await client.post(
        "/api/keys",
        json={"name": "本地调试", "budget_limit": "10.50"},
    )
    assert created.status_code == 200, created.text
    secret = created.json()["data"]["secret"]
    assert secret.startswith("sk-")
    assert Decimal(created.json()["data"]["budget_limit"]) == Decimal("10.50")
    listed = await client.get("/api/keys")
    body = listed.text
    assert secret not in body
    assert listed.json()["data"]["keys"][0]["key_prefix"] == secret[:12]
    key_id = created.json()["data"]["id"]
    service_cache = app.state.key_cache  # type: ignore[attr-defined]
    from app.keys.service import KeyService

    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        service = KeyService(session, app.state.clock, service_cache)  # type: ignore[attr-defined]
        row = await service.authenticate(secret, model="demo-model", ip="127.0.0.1")
        await service.start_usage(row.user_id, row.id, "req-1", "demo-model")
        await service.finalize_usage(
            "req-1", input_tokens=3, output_tokens=4, http_status=200, finish_reason="stop", latency_ms=120
        )
        await session.commit()
    revoked = await client.post(f"/api/keys/{key_id}/revoke")
    assert revoked.status_code == 200
    assert revoked.json()["data"]["status"] == "revoked"
    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        service = KeyService(session, app.state.clock, service_cache)  # type: ignore[attr-defined]
        with pytest.raises(Exception) as caught:
            await service.authenticate(secret, model="demo-model")
        assert getattr(caught.value, "code", "") == "API_KEY_REVOKED"
    summary = await client.get("/api/console/summary")
    assert summary.status_code == 200
    assert summary.json()["data"]["today_requests"] == 1
    assert summary.json()["data"]["today_tokens"] == 7
    assert summary.json()["data"]["avg_latency_ms"] == 120
    assert summary.json()["data"]["trend"][0]["requests"] == 1
    assert summary.json()["data"]["success_rate"] == "1.0000"
    assert summary.json()["data"]["balance"] == "0.00000000"
    assert redact({"api_key": secret})["api_key"] == REDACTED
    assert secret not in str(redact(secret))


@pytest.mark.asyncio
async def test_customer_can_edit_and_delete_key(api: tuple[AsyncClient, object]) -> None:
    client, app = api
    await _login(client, app, "key-edit@example.com")
    created = await client.post(
        "/api/keys",
        json={"name": "可改", "budget_limit": "5"},
    )
    assert created.status_code == 200, created.text
    key_id = created.json()["data"]["id"]
    patched = await client.patch(
        f"/api/keys/{key_id}",
        json={
            "name": "已改名",
            "budget_limit": "8",
            "rpm_limit": 60,
        },
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["data"]["name"] == "已改名"
    # 模型范围由账号决定，密钥级始终为空数组。
    assert patched.json()["data"]["allowed_models"] == []
    assert patched.json()["data"]["rpm_limit"] == 60
    disabled = await client.patch(f"/api/keys/{key_id}", json={"status": "disabled"})
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["data"]["status"] == "disabled"
    blocked_edit = await client.patch(f"/api/keys/{key_id}", json={"name": "停用中改名"})
    assert blocked_edit.status_code == 409
    enabled = await client.patch(f"/api/keys/{key_id}", json={"status": "active"})
    assert enabled.status_code == 200, enabled.text
    assert enabled.json()["data"]["status"] == "active"
    deleted = await client.delete(f"/api/keys/{key_id}")
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["data"]["status"] == "revoked"
    listed = await client.get("/api/keys")
    assert listed.status_code == 200
    row = next(item for item in listed.json()["data"]["keys"] if item["id"] == key_id)
    assert row["status"] == "revoked"
    blocked = await client.patch(f"/api/keys/{key_id}", json={"name": "再改"})
    assert blocked.status_code == 409


@pytest.mark.asyncio
async def test_tc_key_other_user_cannot_revoke(api: tuple[AsyncClient, object]) -> None:
    owner, app = api
    await _login(owner, app, "owner@example.com")
    created = await owner.post("/api/keys", json={"name": "我的"})
    key_id = created.json()["data"]["id"]
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as other:
        await _login(other, app, "other@example.com")
        response = await other.post(f"/api/keys/{key_id}/revoke")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_tc_key_budget_and_empty_models_fail_closed(api: tuple[AsyncClient, object]) -> None:
    client, app = api
    await _login(client, app, "budget@example.com")
    created = await client.post(
        "/api/keys",
        json={"name": "预算", "budget_limit": "1.00"},
    )
    secret = created.json()["data"]["secret"]
    limited = await client.post("/api/keys", json={"name": "受限账号"})
    limited_secret = limited.json()["data"]["secret"]
    from app.db.models.auth import User
    from app.keys.service import KeyService

    cache = app.state.key_cache  # type: ignore[attr-defined]
    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        service = KeyService(session, app.state.clock, cache)  # type: ignore[attr-defined]
        row = await service.authenticate(secret, model="demo-model")
        row.budget_spent = Decimal("1.00")
        await session.commit()
    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        service = KeyService(session, app.state.clock, cache)  # type: ignore[attr-defined]
        with pytest.raises(AppError) as caught:
            await service.authenticate(secret, model="demo-model")
        assert caught.value.status_code == 402
        # 账号级模型范围决定可用模型：只允许别的模型时，demo-model 被拒绝。
        user = await session.get(User, (await service.lookup(limited_secret)).user_id)
        assert user is not None
        user.allowed_models = '["other-model"]'
        await session.commit()
        with pytest.raises(AppError) as denied:
            await service.authenticate(limited_secret, model="demo-model")
        assert denied.value.status_code == 403


@pytest.mark.asyncio
async def test_usage_is_isolated_and_notifications_follow_keys(api: tuple[AsyncClient, object]) -> None:
    owner, app = api
    await _login(owner, app, "usage-owner@example.com")
    created = await owner.post(
        "/api/keys",
        json={
            "name": "将到期",
            "expires_at": "2026-10-30T00:00:00+00:00",
        },
    )
    assert created.status_code == 200, created.text
    secret = created.json()["data"]["secret"]
    key_id = created.json()["data"]["id"]
    from app.keys.service import KeyService

    cache = app.state.key_cache  # type: ignore[attr-defined]
    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        service = KeyService(session, app.state.clock, cache)  # type: ignore[attr-defined]
        row = await service.authenticate(secret, model="demo-model")
        await service.start_usage(row.user_id, row.id, "req-owner", "demo-model")
        await service.finalize_usage("req-owner", input_tokens=1, output_tokens=1, http_status=200, finish_reason="stop")
        await session.commit()
    listed = await owner.get("/api/usage")
    assert listed.status_code == 200
    assert listed.json()["data"]["total"] == 1
    assert listed.json()["data"]["records"][0]["request_id"] == "req-owner"
    refreshed = await owner.post("/api/notifications/refresh")
    assert refreshed.status_code == 200
    assert refreshed.json()["data"]["balance_alerts"] == 1
    assert refreshed.json()["data"]["ledger_enabled"] is True
    assert refreshed.json()["data"]["expiry_notifications"] == 1
    notes = await owner.get("/api/notifications")
    assert notes.json()["data"]["unread"] == 2
    note_id = notes.json()["data"]["notifications"][0]["id"]
    read = await owner.post(f"/api/notifications/{note_id}/read")
    assert read.status_code == 200
    assert read.json()["data"]["read_at"] is not None
    revoked = await owner.post(f"/api/keys/{key_id}/revoke")
    assert revoked.status_code == 200
    after = await owner.get("/api/notifications")
    assert after.json()["data"]["total"] == 3
    billing = await owner.get("/api/billing")
    assert billing.json()["data"]["ledger_enabled"] is True
    assert billing.json()["data"]["available"] == "0.00000000"
    profile = await owner.patch("/api/auth/profile", json={"display_name": "甲", "timezone": "UTC", "locale": "zh-CN"})
    assert profile.status_code == 200, profile.text
    assert profile.json()["data"]["display_name"] == "甲"
    devices = await owner.get("/api/auth/devices")
    assert devices.status_code == 200
    assert len(devices.json()["data"]["devices"]) >= 1
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as other:
        await _login(other, app, "usage-other@example.com")
        foreign = await other.get("/api/usage")
        hidden = await other.post(f"/api/notifications/{note_id}/read")
    assert foreign.json()["data"]["total"] == 0
    assert hidden.status_code == 404
