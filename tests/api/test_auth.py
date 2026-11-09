from __future__ import annotations

import hashlib
import re
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID

import pyotp
import pytest
from app.auth.emailer import CaptureEmailSender, UnconfiguredEmailSender
from app.auth.rbac import ROLE_IDS, refund_duties_are_split
from app.core.clock import ManualClock
from app.core.config import Settings
from app.core.readiness import StaticProbes
from app.db.base import Base
from app.db.models.auth import UserRole
from app.main import create_app
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

PASSWORD = "Correct-horse-1"
NEW_PASSWORD = "Correct-horse-2"


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
        json={
            "email": email,
            "password": PASSWORD,
            "accept_terms": True,
            "accept_privacy": True,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["email_delivery"] == "sent"
    assert "令牌" not in response.text


async def _verify_and_login(client: AsyncClient, app: object, email: str) -> None:
    sender: CaptureEmailSender = app.state.email_sender  # type: ignore[attr-defined]
    verified = await client.post("/api/auth/verify-email", json={"email": email, "token": _token(sender)})
    assert verified.status_code == 200, verified.text
    logged = await client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert logged.status_code == 200, logged.text
    assert "session=" in logged.headers.get("set-cookie", "")


@pytest.mark.asyncio
async def test_tc_auth_001_register_verify_and_login(api: tuple[AsyncClient, object]) -> None:
    client, app = api
    await _register(client, "user@example.com")
    await _verify_and_login(client, app, "user@example.com")
    me = await client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["data"]["user"]["email"] == "user@example.com"
    assert me.json()["data"]["roles"] == ["user"]


@pytest.mark.asyncio
async def test_tc_auth_004_locks_after_five_failures(api: tuple[AsyncClient, object]) -> None:
    client, app = api
    await _register(client, "lock@example.com")
    await _verify_and_login(client, app, "lock@example.com")
    await client.post("/api/auth/logout")
    for _ in range(5):
        failed = await client.post("/api/auth/login", json={"email": "lock@example.com", "password": "Wrong-horse-9"})
        assert failed.status_code == 401
    locked = await client.post("/api/auth/login", json={"email": "lock@example.com", "password": PASSWORD})
    assert locked.status_code == 403
    assert locked.json()["error"]["code"] == "ACCOUNT_LOCKED"


@pytest.mark.asyncio
async def test_tc_auth_005_logout_ends_session(api: tuple[AsyncClient, object]) -> None:
    client, app = api
    await _register(client, "out@example.com")
    await _verify_and_login(client, app, "out@example.com")
    logged_out = await client.post("/api/auth/logout")
    assert logged_out.status_code == 200
    me = await client.get("/api/auth/me")
    assert me.status_code == 401


@pytest.mark.asyncio
async def test_tc_auth_006_reset_password(api: tuple[AsyncClient, object]) -> None:
    client, app = api
    await _register(client, "reset@example.com")
    await _verify_and_login(client, app, "reset@example.com")
    sender: CaptureEmailSender = app.state.email_sender  # type: ignore[attr-defined]
    forgot = await client.post("/api/auth/forgot-password", json={"email": "reset@example.com"})
    assert forgot.json()["data"]["email_delivery"] == "sent"
    assert "令牌" not in forgot.text
    reset = await client.post(
        "/api/auth/reset-password",
        json={"email": "reset@example.com", "token": _token(sender), "password": NEW_PASSWORD},
    )
    assert reset.status_code == 200, reset.text
    old = await client.post("/api/auth/login", json={"email": "reset@example.com", "password": PASSWORD})
    assert old.status_code == 401
    new = await client.post("/api/auth/login", json={"email": "reset@example.com", "password": NEW_PASSWORD})
    assert new.status_code == 200


@pytest.mark.asyncio
async def test_tc_auth_007_change_password_revokes_other_sessions(api: tuple[AsyncClient, object]) -> None:
    client, app = api
    await _register(client, "shift@example.com")
    await _verify_and_login(client, app, "shift@example.com")
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as other:
        other_login = await other.post("/api/auth/login", json={"email": "shift@example.com", "password": PASSWORD})
        assert other_login.status_code == 200
        changed = await client.post(
            "/api/auth/change-password",
            json={"current_password": PASSWORD, "password": NEW_PASSWORD},
        )
        assert changed.status_code == 200, changed.text
        assert (await other.get("/api/auth/me")).status_code == 401
        assert (await client.get("/api/auth/me")).status_code == 200


@pytest.mark.asyncio
async def test_tc_auth_008_change_email(api: tuple[AsyncClient, object]) -> None:
    client, app = api
    await _register(client, "old@example.com")
    await _verify_and_login(client, app, "old@example.com")
    sender: CaptureEmailSender = app.state.email_sender  # type: ignore[attr-defined]
    requested = await client.post(
        "/api/auth/email-change",
        json={"password": PASSWORD, "new_email": "new@example.com"},
    )
    assert requested.json()["data"]["email_delivery"] == "sent"
    confirmed = await client.post("/api/auth/email-change/confirm", json={"token": _token(sender)})
    assert confirmed.status_code == 200, confirmed.text
    me = await client.get("/api/auth/me")
    assert me.json()["data"]["user"]["email"] == "new@example.com"


@pytest.mark.asyncio
async def test_tc_auth_009_idle_session_expires(api: tuple[AsyncClient, object]) -> None:
    client, app = api
    await _register(client, "idle@example.com")
    await _verify_and_login(client, app, "idle@example.com")
    app.state.clock.advance(days=8)  # type: ignore[attr-defined]
    me = await client.get("/api/auth/me")
    assert me.status_code == 401


@pytest.mark.asyncio
async def test_tc_auth_010_totp_required_after_enable(api: tuple[AsyncClient, object]) -> None:
    client, app = api
    await _register(client, "totp@example.com")
    await _verify_and_login(client, app, "totp@example.com")
    setup = await client.post("/api/auth/totp/setup")
    secret = setup.json()["data"]["secret"]
    enabled = await client.post("/api/auth/totp/enable", json={"code": pyotp.TOTP(secret).now()})
    assert enabled.status_code == 200, enabled.text
    assert len(enabled.json()["data"]["recovery_codes"]) == 8
    await client.post("/api/auth/logout")
    challenged = await client.post("/api/auth/login", json={"email": "totp@example.com", "password": PASSWORD})
    assert challenged.json()["data"]["totp_required"] is True
    assert "session=" not in challenged.headers.get("set-cookie", "")
    verified = await client.post(
        "/api/auth/totp/verify",
        json={"challenge": challenged.json()["data"]["challenge"], "code": pyotp.TOTP(secret).now()},
    )
    assert verified.status_code == 200, verified.text
    assert (await client.get("/api/auth/me")).status_code == 200


@pytest.mark.asyncio
async def test_tc_auth_011_me_requires_session(api: tuple[AsyncClient, object]) -> None:
    client, _app = api
    response = await client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


@pytest.mark.asyncio
async def test_mail_unconfigured_does_not_pretend_success(api: tuple[AsyncClient, object]) -> None:
    client, app = api
    app.state.email_sender = UnconfiguredEmailSender()  # type: ignore[attr-defined]
    response = await client.post(
        "/api/auth/register",
        json={
            "email": "nomail@example.com",
            "password": PASSWORD,
            "accept_terms": True,
            "accept_privacy": True,
        },
    )
    assert response.status_code == 200
    assert response.json()["data"]["email_delivery"] == "unconfigured"
    assert "令牌" not in response.text
    forgot = await client.post("/api/auth/forgot-password", json={"email": "nomail@example.com"})
    assert forgot.json()["data"]["email_delivery"] == "unconfigured"
    assert "已发送" not in forgot.text


@pytest.mark.asyncio
async def test_tc_rbac_001_user_cannot_open_admin(api: tuple[AsyncClient, object]) -> None:
    client, app = api
    await _register(client, "plain@example.com")
    await _verify_and_login(client, app, "plain@example.com")
    response = await client.get("/api/admin/whoami")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_tc_rbac_002_refund_duties_stay_split() -> None:
    assert refund_duties_are_split() is True


@pytest.mark.asyncio
async def test_admin_with_permission_can_open_admin(api: tuple[AsyncClient, object]) -> None:
    client, app = api
    await _register(client, "admin@example.com")
    await _verify_and_login(client, app, "admin@example.com")
    me = await client.get("/api/auth/me")
    user_id = UUID(me.json()["data"]["user"]["id"])
    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        session.add(
            UserRole(
                user_id=user_id,
                role_id=UUID(ROLE_IDS["admin"]),
                granted_at=app.state.clock.now(),  # type: ignore[attr-defined]
            )
        )
        await session.commit()
    response = await client.get("/api/admin/whoami")
    assert response.status_code == 200
    assert "admin:access" in response.json()["data"]["permissions"]


@pytest.mark.asyncio
async def test_bootstrap_consumes_init_token(api: tuple[AsyncClient, object], tmp_path: Path) -> None:
    client, _app = api
    token = "init_test-token-value"
    path = tmp_path / "admin.sha256"
    path.write_text(hashlib.sha256(token.encode()).hexdigest(), encoding="utf-8")
    created = await client.post(
        "/api/auth/bootstrap",
        json={"token": token, "email": "root@example.com", "password": PASSWORD},
    )
    assert created.status_code == 200, created.text
    assert created.json()["data"]["role"] == "superadmin"
    assert not path.exists()
    assert path.with_suffix(path.suffix + ".consumed").exists()
    again = await client.post(
        "/api/auth/bootstrap",
        json={"token": token, "email": "other@example.com", "password": PASSWORD},
    )
    assert again.status_code == 403


@pytest.mark.asyncio
async def test_cross_origin_post_is_rejected(api: tuple[AsyncClient, object]) -> None:
    client, _app = api
    response = await client.post(
        "/api/auth/login",
        headers={"origin": "https://evil.example"},
        json={"email": "user@example.com", "password": PASSWORD},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_database_outage_reports_unavailable(api: tuple[AsyncClient, object]) -> None:
    _client, app = api

    class BrokenSession:
        async def get(self, *_args: object, **_kwargs: object) -> None:
            from sqlalchemy.exc import OperationalError

            raise OperationalError("connect", {}, OSError("down"))

        def add(self, _row: object) -> None:
            return None

        async def commit(self) -> None:
            return None

        async def rollback(self) -> None:
            return None

    class BrokenMaker:
        async def __aenter__(self) -> BrokenSession:
            return BrokenSession()

        async def __aexit__(self, *_args: object) -> bool:
            return False

        def __call__(self) -> BrokenMaker:
            return self

    app.state.sessionmaker = BrokenMaker()  # type: ignore[attr-defined]
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/auth/register",
            json={
                "email": "down@example.com",
                "password": PASSWORD,
                "accept_terms": True,
                "accept_privacy": True,
            },
        )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DB_NOT_READY"
    assert response.json()["error"]["message"] == "数据库未就绪"
    assert "down" not in response.text


@pytest.mark.asyncio
async def test_weak_password_is_rejected(api: tuple[AsyncClient, object]) -> None:
    client, _app = api
    response = await client.post(
        "/api/auth/register",
        json={"email": "weak@example.com", "password": "short1", "accept_terms": True, "accept_privacy": True},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "PASSWORD_LENGTH"


@pytest.mark.asyncio
async def test_session_expires_by_idle_and_absolute(tmp_path: Path) -> None:
    """空闲超时与绝对上限都必须强制重新登录，不能一次登录长期有效。"""
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
            session_idle_hours=2,
            session_absolute_hours=5,
        ),
        probes=StaticProbes(postgres_ok=True, redis_ok=True),
    )
    app.state.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    app.state.email_sender = CaptureEmailSender()
    clock = ManualClock()
    app.state.clock = clock
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await _register(client, "ttl@example.com")
        await _verify_and_login(client, app, "ttl@example.com")
        me = await client.get("/api/auth/me")
        assert me.status_code == 200
        policy = me.json()["data"]["session_policy"]
        assert policy["idle_hours"] == 2
        assert policy["absolute_hours"] == 5
        assert "idle_expires_at" in me.json()["data"]["session"]

        # 空闲超时：2 小时无请求后应失效并清 Cookie
        clock.advance(hours=3)
        expired = await client.get("/api/auth/me")
        assert expired.status_code == 401
        set_cookie = expired.headers.get("set-cookie", "")
        assert "session=" in set_cookie
        assert "Max-Age=0" in set_cookie or "max-age=0" in set_cookie.lower()

        # 重新登录后，即使持续活跃，超过绝对上限也必须重登
        logged = await client.post("/api/auth/login", json={"email": "ttl@example.com", "password": PASSWORD})
        assert logged.status_code == 200
        for _ in range(3):
            clock.advance(hours=1)
            alive = await client.get("/api/auth/me")
            assert alive.status_code == 200
        clock.advance(hours=3)  # 累计超过绝对 5 小时
        forced = await client.get("/api/auth/me")
        assert forced.status_code == 401
    await engine.dispose()
