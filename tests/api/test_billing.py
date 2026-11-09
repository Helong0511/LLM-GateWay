"""账本不变量、预扣结算和按价转发。"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from app.auth.emailer import CaptureEmailSender
from app.billing.ledger import LedgerService
from app.billing.money import format_money, q
from app.billing.pricing import MeterInput, PricingService, calculate
from app.core.clock import ManualClock
from app.core.config import Settings
from app.core.readiness import StaticProbes
from app.db.base import Base
from app.db.models.billing import AccountLedger
from app.db.models.keys import ApiKey, UsageRecord
from app.db.models.providers import ModelCatalog, Provider
from app.keys.cache import MemoryKeyCache
from app.keys.service import KeyService
from app.main import create_app
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

PASSWORD = "Correct-horse-1"


def _token(sender: CaptureEmailSender) -> str:
    match = re.search(r"(?:令牌：|[Tt]oken:\s*)(\S+)", sender.messages[-1].text)
    assert match is not None
    return match.group(1)


@pytest.fixture
async def api(tmp_path: Path) -> AsyncIterator[tuple[httpx.AsyncClient, object]]:
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
            usdt_callback_ips="127.0.0.1",
        ),
        probes=StaticProbes(postgres_ok=True, redis_ok=True),
    )
    app.state.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    app.state.email_sender = CaptureEmailSender()
    app.state.clock = ManualClock()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, app
    await engine.dispose()


async def _user(client: httpx.AsyncClient, app: object, email: str) -> UUID:
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
    me = await client.get("/api/auth/me")
    return UUID(me.json()["data"]["user"]["id"])


@pytest.mark.asyncio
async def test_tc_bill_001_hold_settles_once_and_keeps_invariants(api: tuple[httpx.AsyncClient, object]) -> None:
    client, app = api
    user_id = await _user(client, app, "bill@example.com")
    clock: ManualClock = app.state.clock  # type: ignore[attr-defined]
    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        ledger = LedgerService(session, clock)
        await ledger.post(
            user_id=user_id,
            entry_type="recharge",
            amount=Decimal("10"),
            currency="USD",
            idempotency_key="recharge:bill-1",
            reason="测试入账",
        )
        again = await ledger.post(
            user_id=user_id,
            entry_type="recharge",
            amount=Decimal("10"),
            currency="USD",
            idempotency_key="recharge:bill-1",
        )
        assert again.balance_after == Decimal("10.00000000")
        await ledger.place_hold(
            user_id=user_id,
            request_id="req-bill-1",
            amount=Decimal("4"),
            currency="USD",
            ttl_seconds=600,
            api_key_id=None,
            pricing_version_id=None,
        )
        held = await ledger.snapshot(user_id, "USD")
        assert held.available == Decimal("6.00000000")
        settled = await ledger.settle_hold("req-bill-1", Decimal("1.5"), user_id=user_id, currency="USD")
        assert settled.status == "settled"
        assert settled.amount == Decimal("1.50000000")
        repeated = await ledger.settle_hold("req-bill-1", Decimal("1.5"), user_id=user_id, currency="USD")
        assert repeated.amount == settled.amount
        after = await ledger.snapshot(user_id, "USD")
        assert after.balance == Decimal("8.50000000")
        assert after.held == Decimal("0.00000000")
        audit = await ledger.audit(user_id, "USD")
        assert audit == {key: True for key in audit}
        row = (await session.execute(select(AccountLedger).limit(1))).scalar_one()
        row.reason = "篡改"
        with pytest.raises(RuntimeError, match="append-only"):
            await session.flush()


@pytest.mark.asyncio
async def test_tc_bill_002_expired_hold_is_released_once(api: tuple[httpx.AsyncClient, object]) -> None:
    client, app = api
    user_id = await _user(client, app, "expire@example.com")
    clock: ManualClock = app.state.clock  # type: ignore[attr-defined]
    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        ledger = LedgerService(session, clock)
        await ledger.post(
            user_id=user_id,
            entry_type="recharge",
            amount=Decimal("3"),
            currency="USD",
            idempotency_key="recharge:expire",
        )
        await ledger.place_hold(
            user_id=user_id,
            request_id="req-expire",
            amount=Decimal("1"),
            currency="USD",
            ttl_seconds=30,
            api_key_id=None,
            pricing_version_id=None,
        )
        clock.advance(seconds=31)
        assert await ledger.release_expired() == 1
        assert await ledger.release_expired() == 0
        snap = await ledger.snapshot(user_id, "USD")
        assert snap.available == Decimal("3.00000000")
        assert (await ledger.audit(user_id, "USD"))["held_matches"] is True
        await session.commit()


@pytest.mark.asyncio
async def test_tc_bill_003_gateway_charges_reported_usage_and_rejects_empty_balance(
    api: tuple[httpx.AsyncClient, object],
) -> None:
    client, app = api
    user_id = await _user(client, app, "gw-bill@example.com")
    clock: ManualClock = app.state.clock  # type: ignore[attr-defined]
    captured: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.headers.get("authorization", ""))
        body = json.loads(request.content or b"{}")
        if body.get("model") == "boom":
            return httpx.Response(500, json={"error": {"message": "boom"}})
        return httpx.Response(
            200,
            json={"id": "cmpl", "choices": [], "usage": {"prompt_tokens": 3, "completion_tokens": 4}},
        )

    app.state.upstream_transport = httpx.MockTransport(handler)  # type: ignore[attr-defined]
    meters = [
        MeterInput("input_token", Decimal("0.001"), Decimal("0.0004"), 0),
        MeterInput("output_token", Decimal("0.002"), Decimal("0.0008"), 0),
    ]
    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        provider = Provider(
            name="计费上游",
            kind="openai",
            base_url="http://upstream.test",
            created_at=clock.now(),
            updated_at=clock.now(),
        )
        session.add(provider)
        await session.flush()
        catalog = ModelCatalog(
            provider_id=provider.id,
            public_name="priced-model",
            display_name="计价模型",
            upstream_name="upstream-priced",
            status="published",
            supports_stream=True,
            created_at=clock.now(),
        )
        session.add(catalog)
        await session.flush()
        await PricingService(session, clock, Settings()).publish(catalog.id, "USD", meters, user_id)
        keys = KeyService(session, clock, MemoryKeyCache(clock))
        created = await keys.create(user_id, "计费", max_concurrency=1)
        secret = str(created["secret"])
        ledger = LedgerService(session, clock)
        await ledger.post(
            user_id=user_id,
            entry_type="recharge",
            amount=Decimal("20"),
            currency="USD",
            idempotency_key="recharge:gw",
        )
        await session.commit()

    broke = await client.post(
        "/v1/chat/completions",
        headers={"authorization": "Bearer " + secret},
        json={"model": "priced-model", "messages": [{"role": "user", "content": "x"}]},
    )
    assert broke.status_code == 200, broke.text
    expected = calculate(meters, 3, 4, 0).user_charge
    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        usage = (await session.execute(select(UsageRecord).where(UsageRecord.http_status == 200))).scalar_one()
        assert usage.user_charge == expected
        assert usage.settlement_status == "settled"
        snap = await LedgerService(session, clock).snapshot(user_id, "USD")
        assert snap.available == q(Decimal("20") - expected)
        assert snap.held == Decimal("0")
    assert captured
    assert captured[0].startswith("Bearer sk-")

    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        catalog = (
            await session.execute(select(ModelCatalog).where(ModelCatalog.public_name == "priced-model"))
        ).scalar_one()
        catalog.upstream_name = "boom"
        await session.commit()
    before = len(captured)
    upstream_fail = await client.post(
        "/v1/chat/completions",
        headers={"authorization": "Bearer " + secret},
        json={"model": "priced-model", "messages": [{"role": "user", "content": "x"}]},
    )
    assert upstream_fail.status_code == 502
    assert len(captured) == before + 1
    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        snap = await LedgerService(session, clock).snapshot(user_id, "USD")
        assert snap.held == Decimal("0")
        assert snap.available == q(Decimal("20") - expected)

    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        await LedgerService(session, clock).post(
            user_id=user_id,
            entry_type="adjust",
            direction="D",
            amount=q(Decimal("20") - expected),
            currency="USD",
            idempotency_key="adjust:drain",
            reason="清空余额",
        )
        await session.commit()
    empty = await client.post(
        "/v1/chat/completions",
        headers={"authorization": "Bearer " + secret},
        json={"model": "priced-model", "messages": [{"role": "user", "content": "x"}]},
    )
    assert empty.status_code == 402
    assert empty.json()["error"]["code"] == "BALANCE_INSUFFICIENT"
    again = await client.post(
        "/v1/chat/completions",
        headers={"authorization": "Bearer " + secret},
        json={"model": "priced-model", "messages": [{"role": "user", "content": "x"}]},
    )
    assert again.status_code == 402
    assert format_money(expected) == "0.01100000"


@pytest.mark.asyncio
async def test_tc_conc_001_parallel_recharge_credits_once() -> None:
    engine = create_async_engine("postgresql+asyncpg://forge:forge-dev-only@127.0.0.1:5432/forge")
    try:
        async with engine.connect() as conn:
            ready = await conn.scalar(text("SELECT to_regclass('public.account_ledger')"))
    except (OSError, DBAPIError):
        await engine.dispose()
        pytest.skip("PostgreSQL 不可用")
    if ready is None:
        await engine.dispose()
        pytest.skip("账本迁移还没有执行")
    user_id = uuid4()
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO users (id, email, email_normalized, password_hash, status) "
                    "VALUES (:id, :email, :email, 'x', 'active')"
                ),
                {"id": user_id, "email": f"conc-{user_id}@example.com"},
            )

        async def once() -> None:
            async with maker() as session:
                await LedgerService(session, ManualClock()).post(
                    user_id=user_id,
                    entry_type="recharge",
                    amount=Decimal("5"),
                    currency="USD",
                    idempotency_key=f"recharge:conc-{user_id}",
                )
                await session.commit()

        import asyncio

        await asyncio.gather(once(), once())
        async with maker() as session:
            count = await session.scalar(
                select(func.count()).select_from(AccountLedger).where(AccountLedger.user_id == user_id)
            )
            snap = await LedgerService(session, ManualClock()).snapshot(user_id, "USD")
        assert count == 1
        assert snap.balance == Decimal("5.00000000")
    finally:
        async with engine.begin() as conn:
            await conn.execute(text("ALTER TABLE account_ledger DISABLE TRIGGER USER"))
            await conn.execute(text("DELETE FROM account_ledger WHERE user_id = :id"), {"id": user_id})
            await conn.execute(text("ALTER TABLE account_ledger ENABLE TRIGGER USER"))
            await conn.execute(text("DELETE FROM account_balances WHERE user_id = :id"), {"id": user_id})
            await conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
        await engine.dispose()


@pytest.mark.asyncio
async def test_tc_bill_004_cached_tokens_use_cached_meter(api: tuple[httpx.AsyncClient, object]) -> None:
    """有 cached_input_token meter 的模型，缓存命中部分必须按 cached 价（不是 full input 价）计费。"""
    client, app = api
    user_id = await _user(client, app, "cache@example.com")
    clock: ManualClock = app.state.clock  # type: ignore[attr-defined]

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content or b"{}")
        _ = body
        # 上游返回 cache_hit_tokens 字段（模拟 DeepSeek）
        return httpx.Response(
            200,
            json={
                "id": "cmpl-cache",
                "choices": [],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "cache_hit_tokens": 70,  # 70 是缓存命中，30 是新输入
                },
            },
        )

    app.state.upstream_transport = httpx.MockTransport(handler)  # type: ignore[attr-defined]
    meters = [
        MeterInput("input_token", Decimal("0.000002"), Decimal("0.000001"), 0),
        MeterInput("cached_input_token", Decimal("0.0000005"), Decimal("0.0000002"), 0),
        MeterInput("output_token", Decimal("0.000004"), Decimal("0.000002"), 0),
    ]
    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        provider = Provider(
            name="cache-provider", kind="openai", base_url="http://upstream.test",
            created_at=clock.now(), updated_at=clock.now(),
        )
        session.add(provider)
        await session.flush()
        catalog = ModelCatalog(
            provider_id=provider.id,
            public_name="cache-model", display_name="缓存模型",
            upstream_name="cache-upstream", status="published",
            supports_stream=True, created_at=clock.now(),
        )
        session.add(catalog)
        await session.flush()
        await PricingService(session, clock, Settings()).publish(catalog.id, "USD", meters, user_id)
        keys = KeyService(session, clock, MemoryKeyCache(clock))
        created = await keys.create(user_id, "缓存", max_concurrency=1)
        secret = str(created["secret"])
        ledger = LedgerService(session, clock)
        await ledger.post(
            user_id=user_id, entry_type="recharge", amount=Decimal("100"),
            currency="USD", idempotency_key="recharge:cache",
        )
        await session.commit()

    resp = await client.post(
        "/v1/chat/completions",
        headers={"authorization": "Bearer " + secret},
        json={"model": "cache-model", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 200, resp.text

    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        usage = (await session.execute(select(UsageRecord).where(UsageRecord.model_id == "cache-model"))).scalar_one()
        # 期望：input_token 按 30 uncached + 70 cached 计费
        uncached_part = meters[0].unit_price * 30  # 0.00006000
        cached_part = meters[1].unit_price * 70   # 0.00003500
        output_part = meters[2].unit_price * 50    # 0.00020000
        expected = q(uncached_part + cached_part + output_part)
        assert usage.user_charge == expected, f"期望 {expected}，实际 {usage.user_charge}"
        assert usage.cached_tokens == 70


@pytest.mark.asyncio
async def test_tc_bill_005_cross_timezone_reserve_finish_uses_finish_time(
    api: tuple[httpx.AsyncClient, object],
) -> None:
    """reserve 在 peak 时段发起，finish 跨时段在 off-peak 完成 → 必须按 finish 时刻的价结算。

    DeepSeek 规则：Peak = UTC 01:00-04:00 + 06:00-10:00 工作日。
    测试用 UTC 周一 09:50 reserve（仍在 peak），advance 到 10:10 finish（已过 peak，off-peak）。
    预期：按 finish 时刻的 off-peak 价结算。
    """
    from datetime import UTC, datetime

    client, app = api
    user_id = await _user(client, app, "peak@example.com")
    clock: ManualClock = app.state.clock  # type: ignore[attr-defined]
    # 设置在 peak 时段：周一 UTC 09:50
    clock.current = datetime(2026, 11, 2, 9, 50, tzinfo=UTC)

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content or b"{}")
        _ = body
        # 模拟请求耗时：从 peak 09:50 推进到 off-peak 10:10
        clock.advance(seconds=20 * 60)
        return httpx.Response(
            200,
            json={
                "id": "cmpl-peak",
                "choices": [],
                "usage": {"prompt_tokens": 1000, "completion_tokens": 100},
            },
        )

    app.state.upstream_transport = httpx.MockTransport(handler)  # type: ignore[attr-defined]

    peak_input = Decimal("0.00000030")    # $0.30 / 1M → per token
    peak_output = Decimal("0.00000120")   # $1.20 / 1M
    off_peak_input = Decimal("0.00000015")  # Peak ÷ 2
    off_peak_output = Decimal("0.00000060")  # Peak ÷ 2

    meters = [
        MeterInput("input_token", peak_input, peak_input, 0),
        MeterInput("output_token", peak_output, peak_output, 0),
    ]
    schedule = {
        "timezone": "UTC",
        "rules": [
            {
                "label": "off_peak",
                "windows": [
                    {"hours_utc": "00:00-01:00", "weekdays": [1, 2, 3, 4, 5]},
                    {"hours_utc": "04:00-06:00", "weekdays": [1, 2, 3, 4, 5]},
                    {"hours_utc": "10:00-00:00", "weekdays": [1, 2, 3, 4, 5]},
                    {"hours_utc": "00:00-00:00", "weekdays": [6, 7]},
                ],
                "overrides": {
                    "input_token": {"unit_price": "0.00000015", "cost_price": "0.00000015"},
                    "output_token": {"unit_price": "0.00000060", "cost_price": "0.00000060"},
                },
            }
        ],
    }

    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        provider = Provider(
            name="peak-provider", kind="cloud", base_url="http://upstream.test",
            created_at=clock.now(), updated_at=clock.now(),
        )
        session.add(provider)
        await session.flush()
        catalog = ModelCatalog(
            provider_id=provider.id,
            public_name="peak-model", display_name="时段模型",
            upstream_name="peak-upstream", status="published",
            supports_stream=True, created_at=clock.now(),
        )
        session.add(catalog)
        await session.flush()
        await PricingService(session, clock, Settings()).publish(
            catalog.id, "USD", meters, user_id, schedule_rules=schedule,
        )
        keys = KeyService(session, clock, MemoryKeyCache(clock))
        created = await keys.create(user_id, "时段", max_concurrency=1)
        secret = str(created["secret"])
        ledger = LedgerService(session, clock)
        await ledger.post(
            user_id=user_id, entry_type="recharge", amount=Decimal("100"),
            currency="USD", idempotency_key="recharge:peak",
        )
        await session.commit()

    # reserve 在 peak（09:50 UTC 周一），handler 内部推进到 10:10（off-peak）后 finish
    resp = await client.post(
        "/v1/chat/completions",
        headers={"authorization": "Bearer " + secret},
        json={"model": "peak-model", "messages": [{"role": "user", "content": "x"}]},
    )
    assert resp.status_code == 200, resp.text

    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        usage = (await session.execute(select(UsageRecord).where(UsageRecord.model_id == "peak-model"))).scalar_one()
        # finish 时刻 10:10 已在 off-peak 窗口 → 必须按 off-peak 价结算
        expected_input = off_peak_input * 1000  # 0.00015
        expected_output = off_peak_output * 100  # 0.00006
        expected_total = q(expected_input + expected_output)
        assert usage.user_charge == expected_total, (
            f"期望 off-peak 价 {expected_total}，实际 {usage.user_charge}；"
            f"snapshot={usage.unit_price_snapshot}"
        )
        # 确认用的不是 peak 价（反证）
        peak_total = q(peak_input * 1000 + peak_output * 100)  # 0.0003 + 0.00012 = 0.00042
        assert usage.user_charge < peak_total, "跨时段后仍按 peak 价扣费！"
