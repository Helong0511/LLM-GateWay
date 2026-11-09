"""管理概览、审计哈希链和越权拒绝。"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID

import pytest
from app.auth.emailer import CaptureEmailSender
from app.auth.rbac import ROLE_IDS
from app.core.clock import ManualClock
from app.core.config import Settings
from app.core.readiness import StaticProbes
from app.db.base import Base
from app.db.models.auth import User, UserRole
from app.db.models.providers import AuditEvent
from app.main import create_app
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, select, update
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


async def _register(client: AsyncClient, email: str) -> None:
    response = await client.post(
        "/api/auth/register",
        json={"email": email, "password": PASSWORD, "accept_terms": True, "accept_privacy": True},
    )
    assert response.status_code == 200, response.text


async def _verify_and_login(client: AsyncClient, app: object, email: str) -> None:
    sender: CaptureEmailSender = app.state.email_sender  # type: ignore[attr-defined]
    verified = await client.post("/api/auth/verify-email", json={"email": email, "token": _token(sender)})
    assert verified.status_code == 200, verified.text
    logged = await client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert logged.status_code == 200, logged.text


async def _grant(app: object, email: str, role: str) -> None:
    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        user = (await session.execute(select(User).where(User.email_normalized == email))).scalar_one()
        session.add(
            UserRole(
                user_id=user.id,
                role_id=UUID(ROLE_IDS[role]),
                granted_at=app.state.clock.now(),  # type: ignore[attr-defined]
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_admin_overview_requires_permission(api: tuple[AsyncClient, object]) -> None:
    client, app = api
    anonymous = await client.get("/api/admin/overview")
    assert anonymous.status_code == 401
    await _register(client, "plain@example.com")
    await _verify_and_login(client, app, "plain@example.com")
    for path in ("/api/admin/overview", "/api/admin/audit", "/api/admin/audit/verify"):
        denied = await client.get(path)
        assert denied.status_code == 403, path
    await _grant(app, "plain@example.com", "finance")
    finance = await client.get("/api/admin/overview")
    assert finance.status_code == 403


@pytest.mark.asyncio
async def test_admin_overview_and_audit_chain(api: tuple[AsyncClient, object]) -> None:
    client, app = api
    await _register(client, "target@example.com")
    await _register(client, "ops@example.com")
    await _verify_and_login(client, app, "ops@example.com")
    await _grant(app, "ops@example.com", "admin")
    overview = await client.get("/api/admin/overview")
    assert overview.status_code == 200, overview.text
    data = overview.json()["data"]
    assert data["users"] == 2
    assert data["active_users"] == 1
    assert data["published_models"] == 0
    assert data["audit_events"] == 0
    empty = await client.get("/api/admin/audit/verify")
    assert empty.json()["data"] == {"ok": True, "checked": 0, "broken_seq": None}
    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        target = (await session.execute(select(User).where(User.email_normalized == "target@example.com"))).scalar_one()
        target_id = target.id
    assigned = await client.post(f"/api/admin/users/{target_id}/roles", json={"role_code": "support"})
    assert assigned.status_code == 200, assigned.text
    verified = await client.get("/api/admin/audit/verify")
    assert verified.json()["data"]["ok"] is True
    assert verified.json()["data"]["checked"] == 1
    listed = await client.get("/api/admin/audit")
    event = listed.json()["data"]["events"][0]
    assert event["action"] == "rbac.assign"
    assert event["target_id"] == str(target_id)
    assert "support" in event["detail"]
    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        await session.execute(update(AuditEvent).where(AuditEvent.seq == 1).values(detail="tampered"))
        await session.commit()
    broken = await client.get("/api/admin/audit/verify")
    assert broken.json()["data"]["ok"] is False
    assert broken.json()["data"]["broken_seq"] == 1


@pytest.mark.asyncio
async def test_admin_can_list_and_freeze_users(api: tuple[AsyncClient, object]) -> None:
    client, app = api
    await _register(client, "member@example.com")
    await _verify_and_login(client, app, "member@example.com")
    denied = await client.get("/api/admin/users")
    assert denied.status_code == 403
    await _register(client, "ops2@example.com")
    await _verify_and_login(client, app, "ops2@example.com")
    await _grant(app, "ops2@example.com", "admin")
    listed = await client.get("/api/admin/users")
    assert listed.status_code == 200, listed.text
    emails = {item["email"] for item in listed.json()["data"]["users"]}
    assert "member@example.com" in emails
    member_id = next(item["id"] for item in listed.json()["data"]["users"] if item["email"] == "member@example.com")
    me = await client.get("/api/auth/me")
    self_id = me.json()["data"]["user"]["id"]
    cannot = await client.post(f"/api/admin/users/{self_id}/status", json={"status": "frozen"})
    assert cannot.status_code == 400
    frozen = await client.post(f"/api/admin/users/{member_id}/status", json={"status": "frozen"})
    assert frozen.status_code == 200, frozen.text
    assert frozen.json()["data"]["status"] == "frozen"
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as other:
        blocked = await other.post("/api/auth/login", json={"email": "member@example.com", "password": PASSWORD})
    assert blocked.status_code == 403
    restored = await client.post(f"/api/admin/users/{member_id}/status", json={"status": "active"})
    assert restored.status_code == 200
    chain = await client.get("/api/admin/audit/verify")
    assert chain.json()["data"]["ok"] is True
    assert chain.json()["data"]["checked"] == 2


@pytest.mark.asyncio
async def test_catalog_seed_and_admin_orders(api: tuple[AsyncClient, object]) -> None:
    client, app = api
    await _register(client, "buyer@example.com")
    await _verify_and_login(client, app, "buyer@example.com")
    products = await client.get("/api/payments/products")
    assert products.status_code == 200, products.text
    names = [item["name"] for item in products.json()["data"]["products"]]
    assert names == ["Starter", "Standard", "More usage"]
    again = await client.get("/api/payments/products")
    assert [item["name"] for item in again.json()["data"]["products"]] == names
    denied = await client.get("/api/admin/orders")
    assert denied.status_code == 403
    for path in ("/api/admin/refunds", "/api/admin/ledger", "/api/admin/usage"):
        denied = await client.get(path)
        assert denied.status_code == 403, path
    await _grant(app, "buyer@example.com", "admin")
    listed = await client.get("/api/admin/orders")
    assert listed.status_code == 200, listed.text
    assert listed.json()["data"]["total"] == 0
    assert listed.json()["data"]["orders"] == []
    refunds = await client.get("/api/admin/refunds")
    assert refunds.status_code == 200, refunds.text
    assert refunds.json()["data"]["can_execute"] is True
    assert refunds.json()["data"]["can_request"] is False
    assert refunds.json()["data"]["refunds"] == []
    ledger = await client.get("/api/admin/ledger")
    assert ledger.status_code == 200, ledger.text
    assert ledger.json()["data"]["balances"] == []
    usage = await client.get("/api/admin/usage")
    assert usage.status_code == 200, usage.text
    assert usage.json()["data"]["total"] == 0


@pytest.mark.asyncio
async def test_admin_keys_deployments_crypto_and_health(api: tuple[AsyncClient, object]) -> None:
    client, app = api
    await _register(client, "key-admin@example.com")
    await _verify_and_login(client, app, "key-admin@example.com")
    created = await client.post("/api/keys", json={"name": "后台"})
    assert created.status_code == 200, created.text
    secret = created.json()["data"]["secret"]
    key_id = created.json()["data"]["id"]
    saved = await client.patch(
        "/api/notifications/preferences",
        json={"balance_alerts_enabled": False, "warn_high": "8", "warn_low": "1"},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["data"]["balance_alerts_enabled"] is False
    for path in ("/api/admin/keys", "/api/admin/deployments", "/api/admin/crypto", "/api/admin/health"):
        denied = await client.get(path)
        assert denied.status_code == 403, path
    await _grant(app, "key-admin@example.com", "admin")
    listed = await client.get("/api/admin/keys")
    assert listed.status_code == 200, listed.text
    body = listed.text
    assert secret not in body
    assert "key_hash" not in body
    row = listed.json()["data"]["keys"][0]
    assert row["key_prefix"]
    assert row["email"] == "key-admin@example.com"
    limits = await client.post(
        f"/api/admin/keys/{key_id}/limits",
        json={"rpm_limit": 3, "tpm_limit": 100, "max_concurrency": 1, "budget_limit": "1.50000000"},
    )
    assert limits.status_code == 200, limits.text
    assert limits.json()["data"]["rpm_limit"] == 3
    revoked = await client.post(f"/api/admin/keys/{key_id}/revoke")
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["data"]["status"] == "revoked"
    deployments = await client.get("/api/admin/deployments")
    assert deployments.status_code == 200
    assert deployments.json()["data"]["deployments"] == []
    crypto = await client.get("/api/admin/crypto")
    assert crypto.status_code == 200, crypto.text
    assert crypto.json()["data"]["intents"] == []
    health = await client.get("/api/admin/health")
    assert health.status_code == 200, health.text
    assert health.json()["data"]["status"] == "ready"
    assert health.json()["data"]["checks"] == {"postgres": "ok", "redis": "ok"}
