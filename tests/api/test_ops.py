"""工单、发票、公告、优惠券入账、配置和任务探活。"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from app.auth.emailer import CaptureEmailSender
from app.auth.rbac import ROLE_IDS
from app.billing.ledger import LedgerService
from app.core.clock import ManualClock
from app.core.config import Settings
from app.core.readiness import StaticProbes
from app.db.base import Base
from app.db.models.auth import User, UserRole
from app.main import create_app
from app.ops.content import record_call
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
        Settings(
            admin_init_token_path=str(tmp_path / "admin.sha256"),
            register_ip_hourly_limit=20,
            database_url="sqlite+aiosqlite:///:memory:",
        ),
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
    registered = await client.post(
        "/api/auth/register",
        json={"email": email, "password": PASSWORD, "accept_terms": True, "accept_privacy": True},
    )
    assert registered.status_code == 200, registered.text
    sender: CaptureEmailSender = app.state.email_sender  # type: ignore[attr-defined]
    verified = await client.post("/api/auth/verify-email", json={"email": email, "token": _token(sender)})
    assert verified.status_code == 200, verified.text
    logged = await client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert logged.status_code == 200, logged.text


async def _enter(client: AsyncClient, email: str) -> None:
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
async def test_tickets_invoices_coupons_and_ops_views(api: tuple[AsyncClient, object]) -> None:
    client, app = api
    await _login(client, app, "buyer@example.com")
    denied = await client.get("/api/admin/settings")
    assert denied.status_code == 403
    products = await client.get("/api/payments/products")
    product_id = products.json()["data"]["products"][0]["id"]
    created = await client.post(
        "/api/payments/orders",
        headers={"Idempotency-Key": "ops-order"},
        json={"product_id": product_id, "channel": "mock"},
    )
    assert created.status_code == 200, created.text
    order_no = created.json()["data"]["order_no"]
    pending = await client.post("/api/invoices", json={"order_no": order_no, "title": "未支付公司", "tax_no": "A"})
    assert pending.status_code == 404
    confirmed = await client.post("/api/payments/mock/confirm", json={"order_no": order_no})
    assert confirmed.status_code == 200, confirmed.text
    invoice = await client.post("/api/invoices", json={"order_no": order_no, "title": "测试公司", "tax_no": "91310000"})
    assert invoice.status_code == 200, invoice.text
    assert invoice.json()["data"]["amount"] == "10.00000000"
    again = await client.post("/api/invoices", json={"order_no": order_no, "title": "测试公司", "tax_no": "91310000"})
    assert again.status_code == 409
    ticket = await client.post(
        "/api/tickets",
        json={"category": "billing", "subject": "账单问题", "body": "这一笔金额需要核对"},
    )
    assert ticket.status_code == 200, ticket.text
    ticket_id = ticket.json()["data"]["id"]
    await _login(client, app, "other@example.com")
    hidden = await client.get(f"/api/tickets/{ticket_id}")
    assert hidden.status_code == 404
    await _login(client, app, "ops@example.com")
    await _grant(app, "ops@example.com", "admin")
    settings = await client.get("/api/admin/settings")
    assert settings.status_code == 200, settings.text
    payload = settings.json()["data"]
    assert payload["operating_mode"] == "overseas"
    assert "database_url" not in payload
    assert "session_secret" not in payload
    assert "redis_url" not in payload
    routes = await client.get("/api/admin/routes")
    routes_data = routes.json()["data"]
    assert routes_data["routes"] == []
    assert routes_data["total"] == 0
    assert "page" in routes_data
    filtered = await client.get("/api/admin/routes", params={"status": "active", "q": "demo"})
    assert filtered.status_code == 200
    assert filtered.json()["data"]["routes"] == []
    bad_status = await client.get("/api/admin/routes", params={"status": "deleted"})
    assert bad_status.status_code == 400
    margin = await client.get("/api/admin/margin")
    assert margin.status_code == 200, margin.text
    invoices = await client.get("/api/admin/invoices")
    assert invoices.json()["data"]["can_review"] is False
    blocked = await client.post(f"/api/admin/invoices/{invoice.json()['data']['id']}/status", json={"status": "issued"})
    assert blocked.status_code == 403
    reply = await client.post(
        f"/api/admin/tickets/{ticket_id}/messages",
        json={"body": "已核对", "status": "resolved"},
    )
    assert reply.status_code == 200, reply.text
    assert reply.json()["data"]["status"] == "resolved"
    announcement = await client.post(
        "/api/admin/announcements",
        json={"slug": "maintenance", "title": "维护", "body": "今晚维护"},
    )
    assert announcement.status_code == 200, announcement.text
    unpublished = await client.get("/api/announcements/maintenance")
    assert unpublished.status_code == 404
    published = await client.post(
        f"/api/admin/announcements/{announcement.json()['data']['id']}/publish",
        json={"published": True},
    )
    assert published.status_code == 200
    public = await client.get("/api/announcements/maintenance")
    assert public.json()["data"]["body"] == "今晚维护"
    generated = await client.post("/api/admin/coupons/generate")
    assert generated.status_code == 200, generated.text
    code = generated.json()["data"]["code"]
    formatted = generated.json()["data"]["formatted"]
    coupon = await client.post(
        "/api/admin/coupons",
        json={"code": code, "bonus_amount": "3.5", "max_uses": 1},
    )
    assert coupon.status_code == 200, coupon.text
    dup = await client.post(
        "/api/admin/coupons",
        json={"code": formatted, "bonus_amount": "1", "max_uses": 1},
    )
    assert dup.status_code == 409
    await _enter(client, "buyer@example.com")
    bad = await client.post("/api/coupons/redeem", json={"code": "GIFT10"})
    assert bad.status_code == 400
    redeemed = await client.post("/api/coupons/redeem", json={"code": formatted.lower()})
    assert redeemed.status_code == 200, redeemed.text
    repeat = await client.post("/api/coupons/redeem", json={"code": code})
    assert repeat.status_code == 409
    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        user = (await session.execute(select(User).where(User.email_normalized == "buyer@example.com"))).scalar_one()
        snap = await LedgerService(session, app.state.clock).snapshot(user.id, "USD")  # type: ignore[attr-defined]
    assert snap.available == Decimal("13.50000000")
    await _enter(client, "ops@example.com")
    listed = await client.get("/api/admin/backups")
    assert listed.status_code == 200
    listed_data = listed.json()["data"]
    assert listed_data["backups"] == []
    assert "can_backup" in listed_data
    assert "docker_available" in listed_data
    assert "hint_code" in listed_data
    backup = await client.post("/api/admin/backups")
    # 测试库是 sqlite，解析/导出都会失败，应明确返回不可用
    assert backup.status_code == 503
    assert backup.json()["error"]["code"] == "BACKUP_NOT_POSTGRES"
    ping = await client.post("/api/admin/tasks/ping")
    assert ping.status_code == 200, ping.text
    assert ping.json()["data"]["runs"][0]["name"] == "worker_ping"
    assert ping.json()["data"]["failed"] == []
    toggled = await client.post("/api/admin/content-safety", json={"enabled": True})
    assert toggled.json()["data"]["enabled"] is True
    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        user = (await session.execute(select(User).where(User.email_normalized == "buyer@example.com"))).scalar_one()
        await record_call(
            session,
            user_id=user.id,
            model_name="demo",
            request_id="req-1",
            now=app.state.clock.now(),  # type: ignore[attr-defined]
        )
        await session.commit()
    records = await client.get("/api/admin/content-safety")
    row = records.json()["data"]["records"][0]
    assert row["category"] == "call"
    assert row["model_name"] == "demo"
    assert "prompt" not in row
    assert len(row["summary_hash"]) == 64
