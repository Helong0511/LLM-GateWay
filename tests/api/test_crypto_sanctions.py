"""制裁地址：后台增删改、规范化匹配。"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth.emailer import CaptureEmailSender
from app.auth.rbac import ROLE_IDS
from app.core.clock import ManualClock
from app.core.config import Settings
from app.core.readiness import StaticProbes
from app.db.base import Base
from app.db.models.auth import UserRole
from app.main import create_app

PASSWORD = "Correct-horse-1"
TRC_ADDR = "TBadPayer0000000000000000000001"
ERC_ADDR = "0xAbCdEf0123456789AbCdEf0123456789aBcDeF01"


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


async def _login(client: AsyncClient, app: object, email: str) -> UUID:
    registered = await client.post(
        "/api/auth/register",
        json={"email": email, "password": PASSWORD, "accept_terms": True, "accept_privacy": True},
    )
    assert registered.status_code == 200, registered.text
    user_id = UUID(registered.json()["data"]["user_id"])
    sender: CaptureEmailSender = app.state.email_sender  # type: ignore[attr-defined]
    verified = await client.post("/api/auth/verify-email", json={"email": email, "token": _token(sender)})
    assert verified.status_code == 200, verified.text
    logged = await client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert logged.status_code == 200, logged.text
    return user_id


async def _grant_admin(app: object, user_id: UUID) -> None:
    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        session.add(UserRole(user_id=user_id, role_id=UUID(ROLE_IDS["admin"])))
        await session.commit()


@pytest.mark.asyncio
async def test_admin_can_manage_sanction_addresses(api: tuple[AsyncClient, object]) -> None:
    client, app = api
    plain_id = await _login(client, app, "plain-sanction@example.com")
    forbidden = await client.post(
        "/api/admin/crypto/sanctions",
        json={"address": TRC_ADDR, "network": "TRC20", "source": "人工", "reason": "测试"},
    )
    assert forbidden.status_code == 403

    await _grant_admin(app, plain_id)

    created = await client.post(
        "/api/admin/crypto/sanctions",
        json={"address": TRC_ADDR, "network": "trc20", "source": "人工录入", "reason": "测试名单"},
    )
    assert created.status_code == 200, created.text
    data = created.json()["data"]
    assert data["network"] == "TRC20"
    assert data["address"] == TRC_ADDR
    assert data["source"] == "人工录入"
    sanction_id = data["id"]

    dup = await client.post(
        "/api/admin/crypto/sanctions",
        json={"address": TRC_ADDR, "network": "TRC20", "source": "重复", "reason": ""},
    )
    assert dup.status_code == 409
    assert "已在" in dup.json()["error"]["message"]

    listed = await client.get("/api/admin/crypto?q=人工")
    assert listed.status_code == 200
    assert listed.json()["data"]["sanctioned_total"] >= 1
    assert "networks" in listed.json()["data"]
    row = next(item for item in listed.json()["data"]["sanctioned"] if item["id"] == sanction_id)
    assert row["address"] == TRC_ADDR
    assert "address_masked" in row

    patched = await client.patch(
        f"/api/admin/crypto/sanctions/{sanction_id}",
        json={"source": "OFAC SDN", "reason": "已核对"},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["data"]["source"] == "OFAC SDN"
    assert patched.json()["data"]["reason"] == "已核对"

    erc = await client.post(
        "/api/admin/crypto/sanctions",
        json={"address": ERC_ADDR, "network": "ERC20", "source": "人工", "reason": "eth"},
    )
    assert erc.status_code == 200, erc.text
    assert erc.json()["data"]["address"] == ERC_ADDR.lower()

    bad = await client.post(
        "/api/admin/crypto/sanctions",
        json={"address": "not-an-address", "network": "ERC20", "source": "x", "reason": ""},
    )
    assert bad.status_code == 400

    deleted = await client.delete(f"/api/admin/crypto/sanctions/{sanction_id}")
    assert deleted.status_code == 200
    assert deleted.json()["data"]["deleted"] is True
    gone = await client.delete(f"/api/admin/crypto/sanctions/{sanction_id}")
    assert gone.status_code == 404


@pytest.mark.asyncio
async def test_sanction_match_normalizes_erc20_case(api: tuple[AsyncClient, object]) -> None:
    client, app = api
    user_id = await _login(client, app, "erc-sanction@example.com")
    await _grant_admin(app, user_id)

    created = await client.post(
        "/api/admin/crypto/sanctions",
        json={"address": ERC_ADDR, "network": "ERC20", "source": "测试", "reason": "大小写"},
    )
    assert created.status_code == 200, created.text
    assert created.json()["data"]["address"] == ERC_ADDR.lower()

    from app.admin.crypto import is_sanctioned

    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        assert await is_sanctioned(session, ERC_ADDR.upper(), "erc20") is True
        assert await is_sanctioned(session, "0x0000000000000000000000000000000000000001", "ERC20") is False
