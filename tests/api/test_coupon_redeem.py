"""优惠券兑换各分支提示与业务关系。"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth.emailer import CaptureEmailSender
from app.auth.rbac import ROLE_IDS
from app.billing.ledger import LedgerService
from app.core.clock import ManualClock
from app.core.config import Settings
from app.core.readiness import StaticProbes
from app.db.base import Base
from app.db.models.auth import User, UserRole
from app.main import create_app
from app.ops.coupon_codes import format_code, generate_code

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
async def test_coupon_redeem_message_matrix(api: tuple[AsyncClient, object]) -> None:
    client, app = api
    await _login(client, app, "coupon-admin@example.com")
    await _grant(app, "coupon-admin@example.com", "admin")
    await _grant(app, "coupon-admin@example.com", "superadmin")

    empty = await client.post("/api/coupons/redeem", json={"code": "   "})
    assert empty.status_code == 400
    assert empty.json()["error"]["code"] == "COUPON_EMPTY"

    bad_fmt = await client.post("/api/coupons/redeem", json={"code": "GIFT10"})
    assert bad_fmt.status_code == 400
    assert bad_fmt.json()["error"]["code"] == "COUPON_BAD_FORMAT"

    missing = await client.post("/api/coupons/redeem", json={"code": format_code(generate_code())})
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "COUPON_NOT_FOUND"

    created = await client.post(
        "/api/admin/coupons",
        json={"auto_generate": True, "bonus_amount": "2.5", "max_uses": 2},
    )
    assert created.status_code == 200, created.text
    payload = created.json()["data"]
    code = payload["code"]
    coupon_id = payload["id"]
    formatted = payload["formatted"]
    assert payload["usable"] is True
    assert payload["created_by_email"] == "coupon-admin@example.com"
    assert payload["redemptions"] == []
    assert payload["usable_reason"] == "ok"

    listed = await client.get("/api/admin/coupons")
    assert listed.status_code == 200
    row = next(item for item in listed.json()["data"]["coupons"] if item["id"] == coupon_id)
    assert row["created_by_email"] == "coupon-admin@example.com"
    assert row["usable"] is True
    assert row["usable_reason"] == "ok"

    await client.patch(f"/api/admin/coupons/{coupon_id}", json={"enabled": False})
    disabled = await client.post("/api/coupons/redeem", json={"code": formatted})
    assert disabled.status_code == 403
    assert disabled.json()["error"]["code"] == "COUPON_DISABLED"
    await client.patch(f"/api/admin/coupons/{coupon_id}", json={"enabled": True})

    past = (app.state.clock.now() - timedelta(hours=1)).isoformat()  # type: ignore[attr-defined]
    await client.patch(f"/api/admin/coupons/{coupon_id}", json={"expires_at": past})
    expired = await client.post("/api/coupons/redeem", json={"code": code})
    assert expired.status_code == 400
    assert expired.json()["error"]["code"] == "COUPON_EXPIRED"
    await client.patch(f"/api/admin/coupons/{coupon_id}", json={"clear_expires_at": True})

    await _login(client, app, "coupon-buyer@example.com")
    ok = await client.post("/api/coupons/redeem", json={"code": formatted.lower()})
    assert ok.status_code == 200, ok.text
    assert ok.json()["data"]["bonus_amount"].startswith("2.5")

    again = await client.post("/api/coupons/redeem", json={"code": code})
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "COUPON_ALREADY_REDEEMED"

    await _login(client, app, "coupon-buyer-2@example.com")
    second = await client.post("/api/coupons/redeem", json={"code": code})
    assert second.status_code == 200, second.text

    await _enter(client, "coupon-admin@example.com")
    detail = await client.get(f"/api/admin/coupons/{coupon_id}")
    assert detail.status_code == 200, detail.text
    body = detail.json()["data"]
    assert body["used_count"] == 2
    assert body["usable"] is False
    assert body["usable_reason"] == "exhausted"
    assert len(body["redemptions"]) == 2
    emails = {item["email"] for item in body["redemptions"]}
    assert emails == {"coupon-buyer@example.com", "coupon-buyer-2@example.com"}

    await _login(client, app, "coupon-buyer-3@example.com")
    exhausted = await client.post("/api/coupons/redeem", json={"code": code})
    assert exhausted.status_code == 409
    assert exhausted.json()["error"]["code"] == "COUPON_EXHAUSTED"

    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        user = (await session.execute(select(User).where(User.email_normalized == "coupon-buyer@example.com"))).scalar_one()
        snap = await LedgerService(session, app.state.clock).snapshot(user.id, "USD")  # type: ignore[attr-defined]
    assert snap.available == Decimal("2.50000000")
