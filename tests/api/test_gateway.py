from __future__ import annotations

import ipaddress
import json
import re
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from app.auth.emailer import CaptureEmailSender
from app.auth.rbac import ROLE_IDS
from app.core.clock import ManualClock
from app.core.config import Settings
from app.core.errors import AppError
from app.core.readiness import StaticProbes
from app.db.base import Base
from app.db.models.auth import User, UserRole
from app.db.models.keys import UsageRecord
from app.gateway.service import GatewayService
from app.main import create_app
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

PASSWORD = "Correct-horse-1"
UPSTREAM_SECRET = "upstream-secret-value"
MOCK_MODEL_PRICING = {"prompt": "0.000001", "completion": "0.000002"}


async def _resolver(host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    if host == "upstream.test":
        return [ipaddress.ip_address("8.8.8.8")]
    raise AppError(400, "VALIDATION_ERROR", "域名无法解析")


def _upstream(captured: list[str]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.headers.get("authorization", ""))
        # 官方 openai 预设拼 /models；旧写法是 /v1/models。SSRF 会把 host 钉成解析 IP。
        path = request.url.path.rstrip("/")
        if path.endswith("/models"):
            if request.headers.get("authorization") != f"Bearer {UPSTREAM_SECRET}":
                return httpx.Response(401, json={"error": {"message": "unauthorized"}})
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "mock-model",
                            "pricing": dict(MOCK_MODEL_PRICING),
                        }
                    ]
                },
            )
        body = json.loads(request.content or b"{}")
        if body.get("model") == "__missing__":
            return httpx.Response(404, json={"error": {"message": "missing"}})
        if body.get("stream") is True:
            text = (
                'data: {"choices":[{"delta":{"content":"hi"}}]}\n'
                "\n"
                'data: {"usage":{"prompt_tokens":2,"completion_tokens":3}}\n'
                "\n"
                "data: [DONE]\n"
                "\n"
            )
            return httpx.Response(200, text=text, headers={"content-type": "text/event-stream"})
        return httpx.Response(
            200,
            json={
                "id": "cmpl",
                "choices": [{"message": {"role": "assistant", "content": "hi"}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 4},
            },
        )

    return httpx.MockTransport(handler)


def _registry(calls: list[tuple[str, dict[str, object]]]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content or b"{}")
        calls.append((request.url.path, body))
        if request.url.path.endswith("/model/info"):
            return httpx.Response(200, json={"data": []})
        return httpx.Response(200, json={})

    return httpx.MockTransport(handler)


@pytest.fixture
async def api(tmp_path: Path) -> AsyncIterator[tuple[AsyncClient, object, list[str]]]:
    from httpx import ASGITransport, AsyncClient

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite(dbapi_conn, _record) -> None:  # type: ignore[no-untyped-def]
        dbapi_conn.create_function("char_length", 1, lambda value: len(value) if isinstance(value, str) else None)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    captured: list[str] = []
    app = create_app(
        Settings(admin_init_token_path=str(tmp_path / "admin.sha256")),
        probes=StaticProbes(postgres_ok=True, redis_ok=True),
    )
    app.state.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    app.state.email_sender = CaptureEmailSender()
    app.state.clock = ManualClock()
    app.state.ssrf_resolver = _resolver
    app.state.upstream_transport = _upstream(captured)
    # LiteLLM 执行面替身：记录 /model/new、/model/delete，避免测试真连 4000 端口。
    app.state.registry_calls = []
    app.state.litellm_transport = _registry(app.state.registry_calls)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, app, captured
    await engine.dispose()


async def _login(client: object, app: object, email: str) -> None:
    registered = await client.post(  # type: ignore[attr-defined]
        "/api/auth/register",
        json={"email": email, "password": PASSWORD, "accept_terms": True, "accept_privacy": True},
    )
    assert registered.status_code == 200, registered.text
    sender: CaptureEmailSender = app.state.email_sender  # type: ignore[attr-defined]
    token = re.search(r"(?:令牌：|[Tt]oken:\s*)(\S+)", sender.messages[-1].text)
    assert token is not None
    verified = await client.post(  # type: ignore[attr-defined]
        "/api/auth/verify-email",
        json={"email": email, "token": token.group(1)},
    )
    assert verified.status_code == 200, verified.text
    logged = await client.post("/api/auth/login", json={"email": email, "password": PASSWORD})  # type: ignore[attr-defined]
    assert logged.status_code == 200, logged.text


async def _grant_model_ops(app: object, email: str) -> None:
    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        user = (
            await session.execute(select(User).where(User.email_normalized == email))
        ).scalar_one()
        session.add(
            UserRole(
                user_id=user.id,
                role_id=UUID(ROLE_IDS["model_ops"]),
                granted_at=app.state.clock.now(),  # type: ignore[attr-defined]
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_tc_gw_publish_and_chat_hide_upstream_secret(api: tuple[object, object, list[str]]) -> None:
    client, app, captured = api
    await _login(client, app, "ops@example.com")
    await _grant_model_ops(app, "ops@example.com")
    denied = await client.post(  # type: ignore[attr-defined]
        "/api/admin/providers",
        json={"name": "内网", "kind": "openai", "base_url": "http://127.0.0.1:11434"},
    )
    assert denied.status_code == 400
    created = await client.post(  # type: ignore[attr-defined]
        "/api/admin/providers",
        json={"name": "模拟上游", "kind": "openai", "base_url": "http://upstream.test"},
    )
    assert created.status_code == 200, created.text
    provider_id = created.json()["data"]["id"]
    secret_response = await client.post(  # type: ignore[attr-defined]
        f"/api/admin/providers/{provider_id}/credentials",
        json={"label": "主凭证", "secret": UPSTREAM_SECRET},
    )
    assert secret_response.status_code == 200, secret_response.text
    assert UPSTREAM_SECRET not in secret_response.text
    assert secret_response.json()["data"]["hint"].startswith(UPSTREAM_SECRET[:4])
    listed = await client.get("/api/admin/providers")  # type: ignore[attr-defined]
    assert UPSTREAM_SECRET not in listed.text
    MOCK_MODEL_PRICING.update({"prompt": "0.000001", "completion": "0.000002"})
    synced = await client.post(  # type: ignore[attr-defined]
        f"/api/admin/providers/{provider_id}/sync",
        json={"output_markup_percent": 20},
    )
    assert synced.status_code == 200, synced.text
    assert synced.json()["data"]["priced_count"] == 1
    assert synced.json()["data"]["price_new"] == 1
    assert synced.json()["data"]["output_markup_percent"] == 20
    models = await client.get("/api/admin/models")  # type: ignore[attr-defined]
    model_row = models.json()["data"]["models"][0]
    model_id = model_row["id"]
    assert isinstance(model_row["provider_name"], str)
    assert model_row["supports_stream"] is None
    assert model_row["upstream_input_price"] == "0.00000100"
    assert model_row["upstream_output_price"] == "0.00000240"
    # 上游输出涨价 → 建议价上涨，并单独计数
    MOCK_MODEL_PRICING["completion"] = "0.000004"
    bumped = await client.post(  # type: ignore[attr-defined]
        f"/api/admin/providers/{provider_id}/sync",
        json={"output_markup_percent": 20},
    )
    assert bumped.status_code == 200, bumped.text
    assert bumped.json()["data"]["price_increased"] == 1
    assert "mock-model" in bumped.json()["data"]["price_increased_models"]
    models = await client.get("/api/admin/models")  # type: ignore[attr-defined]
    assert models.json()["data"]["models"][0]["upstream_output_price"] == "0.00000480"
    published = await client.post(  # type: ignore[attr-defined]
        f"/api/admin/models/{model_id}/publish",
        json={"display_name": "模拟模型", "supports_stream": True, "supports_embeddings": False},
    )
    assert published.status_code == 200, published.text
    key = await client.post(  # type: ignore[attr-defined]
        "/api/keys",
        json={"name": "调用", "rpm_limit": 10},
    )
    user_secret = key.json()["data"]["secret"]
    chat = await client.post(  # type: ignore[attr-defined]
        "/v1/chat/completions",
        headers={"authorization": f"Bearer {user_secret}"},
        json={"model": "mock-model", "messages": [{"role": "user", "content": "ping"}]},
    )
    assert chat.status_code == 200, chat.text
    assert chat.json()["usage"]["completion_tokens"] == 4
    assert UPSTREAM_SECRET not in chat.text
    assert user_secret not in "".join(captured)
    assert any(item == "Bearer sk-dev-only-litellm-master-key" for item in captured)
    embeddings = await client.post(  # type: ignore[attr-defined]
        "/v1/embeddings",
        headers={"authorization": f"Bearer {user_secret}"},
        json={"model": "mock-model", "input": "ping"},
    )
    assert embeddings.status_code == 404
    assert embeddings.json()["error"]["code"] == "GATEWAY_EMBEDDINGS_UNSUPPORTED"
    closed = await client.post("/v1/images/generations", json={})  # type: ignore[attr-defined]
    assert closed.status_code == 501
    stranger = await client.post(  # type: ignore[attr-defined]
        "/api/admin/providers",
        json={"name": "别人", "kind": "openai", "base_url": "http://upstream.test"},
    )
    await client.post("/api/auth/logout")  # type: ignore[attr-defined]
    fresh = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=fresh, base_url="http://test") as other:
        await _login(other, app, "user@example.com")
        forbidden = await other.post(
            "/api/admin/providers",
            json={"name": "越权", "kind": "openai", "base_url": "http://upstream.test"},
        )
    assert forbidden.status_code == 403
    assert stranger.status_code == 200


@pytest.mark.asyncio
async def test_tc_gw_stream_cancel_releases_slot_and_rate_limit(api: tuple[object, object, list[str]]) -> None:
    client, app, _captured = api
    await _login(client, app, "stream@example.com")
    await _grant_model_ops(app, "stream@example.com")
    created = await client.post(  # type: ignore[attr-defined]
        "/api/admin/providers",
        json={"name": "模拟上游", "kind": "openai", "base_url": "http://upstream.test"},
    )
    provider_id = created.json()["data"]["id"]
    await client.post(  # type: ignore[attr-defined]
        f"/api/admin/providers/{provider_id}/credentials",
        json={"secret": UPSTREAM_SECRET},
    )
    await client.post(f"/api/admin/providers/{provider_id}/sync")  # type: ignore[attr-defined]
    model_id = (await client.get("/api/admin/models")).json()["data"]["models"][0]["id"]  # type: ignore[attr-defined]
    await client.post(  # type: ignore[attr-defined]
        f"/api/admin/models/{model_id}/publish",
        json={"display_name": "模拟模型", "supports_stream": True, "supports_embeddings": True},
    )
    key = await client.post(  # type: ignore[attr-defined]
        "/api/keys",
        json={"name": "限流", "rpm_limit": 1, "max_concurrency": 1},
    )
    user_secret = key.json()["data"]["secret"]
    first = await client.post(  # type: ignore[attr-defined]
        "/v1/chat/completions",
        headers={"authorization": f"Bearer {user_secret}"},
        json={"model": "mock-model", "messages": [{"role": "user", "content": "ping"}], "stream": True},
    )
    assert first.status_code == 200, first.text
    assert "text/event-stream" in first.headers["content-type"]
    assert '"usage"' in first.text
    second = await client.post(  # type: ignore[attr-defined]
        "/v1/chat/completions",
        headers={"authorization": f"Bearer {user_secret}"},
        json={"model": "mock-model", "messages": [{"role": "user", "content": "ping"}]},
    )
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "GATEWAY_RPM_LIMIT"
    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        service = GatewayService(
            session,
            app.state.clock,  # type: ignore[attr-defined]
            app.state.settings,  # type: ignore[attr-defined]
            app.state.key_cache,  # type: ignore[attr-defined]
            app.state.rate_limiter,  # type: ignore[attr-defined]
            app.state.slots,  # type: ignore[attr-defined]
            app.state.upstream_transport,  # type: ignore[attr-defined]
        )
        app.state.clock.advance(seconds=61)  # type: ignore[attr-defined]
        prepared = await service.prepare(
            raw_key=user_secret,
            body={"model": "mock-model", "messages": [{"role": "user", "content": "ping"}], "stream": True},
            request_id="cancel-1",
            ip=None,
            require_embeddings=False,
        )
        await session.commit()
        chunks = [
            chunk
            async for chunk in service.stream(prepared, _always_disconnected, app.state.sessionmaker)  # type: ignore[attr-defined]
        ]
    assert chunks == []
    assert app.state.slots.held(prepared.slot_key) == 0  # type: ignore[attr-defined]
    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        row = (
            await session.execute(select(UsageRecord).where(UsageRecord.request_id == "cancel-1"))
        ).scalar_one()
    assert row.finish_reason == "cancelled"


async def _always_disconnected() -> bool:
    return True


@pytest.mark.asyncio
async def test_publish_and_unpublish_sync_to_litellm(api: tuple[object, object, list[str]]) -> None:
    """上架必须把 deployment 注册进 LiteLLM，下架必须撤销。

    否则管理后台显示「已上架」，真实 /v1 调用却是 model not found。
    """
    client, app, _captured = api
    await _login(client, app, "registry@example.com")
    await _grant_model_ops(app, "registry@example.com")
    created = await client.post(  # type: ignore[attr-defined]
        "/api/admin/providers",
        json={"name": "同步上游", "kind": "openai", "base_url": "http://upstream.test"},
    )
    provider_id = created.json()["data"]["id"]
    await client.post(  # type: ignore[attr-defined]
        f"/api/admin/providers/{provider_id}/credentials",
        json={"secret": UPSTREAM_SECRET},
    )
    await client.post(f"/api/admin/providers/{provider_id}/sync")  # type: ignore[attr-defined]
    model_id = (await client.get("/api/admin/models")).json()["data"]["models"][0]["id"]  # type: ignore[attr-defined]

    published = await client.post(  # type: ignore[attr-defined]
        f"/api/admin/models/{model_id}/publish",
        json={"display_name": "同步模型", "supports_stream": True, "supports_embeddings": False},
    )
    assert published.status_code == 200, published.text

    calls: list[tuple[str, dict[str, object]]] = app.state.registry_calls  # type: ignore[attr-defined]
    registered = [body for path, body in calls if path.endswith("/model/new")]
    assert registered, "上架没有调用 LiteLLM /model/new"
    payload = registered[-1]
    assert payload["model_name"] == "mock-model"
    params = payload["litellm_params"]
    assert isinstance(params, dict)
    assert params["model"] == "openai/mock-model"
    assert params["api_base"] == "http://upstream.test"
    assert params["api_key"] == UPSTREAM_SECRET
    info = payload["model_info"]
    assert isinstance(info, dict) and info["id"]

    unpublished = await client.post(  # type: ignore[attr-defined]
        "/api/admin/models/unpublish-batch", json={"model_ids": [model_id]}
    )
    assert unpublished.status_code == 200, unpublished.text
    removed = [body for path, body in calls if path.endswith("/model/delete")]
    assert removed and removed[-1]["id"] == info["id"]
