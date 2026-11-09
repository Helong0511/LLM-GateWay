"""充值幂等、USDT 三重校验和退款职责分离。"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from app.auth.emailer import CaptureEmailSender
from app.auth.rbac import ROLE_IDS
from app.billing.ledger import LedgerService
from app.core.clock import ManualClock
from app.core.config import Settings
from app.core.readiness import StaticProbes
from app.db.base import Base
from app.db.models.auth import UserRole
from app.db.models.billing import ExchangeRate
from app.db.models.payments import PaymentEvent, PaymentOrder, RechargeProduct, SanctionedAddress
from app.main import create_app
from app.payments.signatures import stripe_signature_ok, usdt_signature
from sqlalchemy import event, select
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
        Settings(admin_init_token_path=str(tmp_path / "admin.sha256"), usdt_callback_ips="127.0.0.1"),
        probes=StaticProbes(postgres_ok=True, redis_ok=True),
    )
    app.state.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    app.state.email_sender = CaptureEmailSender()
    app.state.clock = ManualClock()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, app
    await engine.dispose()


async def _login(client: httpx.AsyncClient, app: object, email: str) -> UUID:
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


async def _grant(app: object, user_id: UUID, role: str) -> None:
    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        session.add(
            UserRole(user_id=user_id, role_id=UUID(ROLE_IDS[role]), granted_at=app.state.clock.now())  # type: ignore[attr-defined]
        )
        await session.commit()


async def _product(app: object, amount: str, name: str) -> str:
    clock: ManualClock = app.state.clock  # type: ignore[attr-defined]
    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        row = RechargeProduct(
            name=name,
            amount=Decimal(amount),
            currency="USD",
            bonus_amount=Decimal("0"),
            enabled=True,
            sort_order=1,
            created_at=clock.now(),
        )
        session.add(row)
        await session.commit()
        return str(row.id)


def _usdt_body(order: dict[str, object], *, amount: str, confirmations: int, payer: str = "TPayerAddressForTest0001") -> dict[str, object]:
    return {
        "order_no": order["order_no"],
        "tx_hash": "tx-" + str(order["order_no"]),
        "amount": amount,
        "address": order["pay_address"],
        "network": "TRC20",
        "confirmations": confirmations,
        "payer": payer,
    }


@pytest.mark.asyncio
async def test_tc_pay_001_mock_confirm_is_idempotent(api: tuple[httpx.AsyncClient, object]) -> None:
    client, app = api
    user_id = await _login(client, app, "pay@example.com")
    product_id = await _product(app, "10", "10 美元")
    created = await client.post(
        "/api/payments/orders",
        headers={"Idempotency-Key": "order-1"},
        json={"product_id": product_id, "channel": "mock"},
    )
    assert created.status_code == 200, created.text
    order_no = created.json()["data"]["order_no"]
    replay = await client.post(
        "/api/payments/orders",
        headers={"Idempotency-Key": "order-1"},
        json={"product_id": product_id, "channel": "mock"},
    )
    assert replay.json()["data"]["order_no"] == order_no
    conflict = await client.post(
        "/api/payments/orders",
        headers={"Idempotency-Key": "order-1"},
        json={"product_id": product_id, "channel": "stripe"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_PAYLOAD_MISMATCH"
    denied = await client.post(
        "/api/payments/orders",
        headers={"Idempotency-Key": "order-wechat"},
        json={"product_id": product_id, "channel": "wechat"},
    )
    assert denied.status_code == 400
    confirmed = await client.post("/api/payments/mock/confirm", json={"order_no": order_no})
    assert confirmed.status_code == 200, confirmed.text
    again = await client.post("/api/payments/mock/confirm", json={"order_no": order_no})
    assert again.status_code == 200
    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        snap = await LedgerService(session, app.state.clock).snapshot(user_id, "USD")  # type: ignore[attr-defined]
    assert snap.available == Decimal("10.00000000")
    hidden = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=hidden, base_url="http://test") as other:
        await _login(other, app, "other-pay@example.com")
        foreign = await other.get(f"/api/payments/orders/{order_no}")
    assert foreign.status_code == 404


@pytest.mark.asyncio
async def test_tc_pay_101_usdt_triple_check_and_amount_bands(api: tuple[httpx.AsyncClient, object]) -> None:
    client, app = api
    user_id = await _login(client, app, "usdt@example.com")
    settings: Settings = app.state.settings  # type: ignore[attr-defined]
    small_id = await _product(app, "10", "小额")
    created = await client.post(
        "/api/payments/orders",
        headers={"Idempotency-Key": "usdt-1"},
        json={"product_id": small_id, "channel": "usdt"},
    )
    assert created.status_code == 200, created.text
    order = created.json()["data"]
    assert order["warning"]
    assert order["network"] == "TRC20"
    raw_bad = json.dumps({"order_no": order["order_no"]}).encode()
    bad = await client.post("/api/payments/usdt/notify", content=raw_bad, headers={"x-forge-signature": "00"})
    assert bad.status_code == 400
    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        event = (await session.execute(select(PaymentEvent))).scalar_one()
        assert event.signature_ok is False

    body = _usdt_body(order, amount=str(order["crypto_amount"]), confirmations=0)
    app.state.usdt_gateway.orders[order["order_no"]] = body  # type: ignore[attr-defined]
    raw = json.dumps(body).encode()
    signature = usdt_signature(settings.usdt_webhook_secret, raw)
    waiting = await client.post(
        "/api/payments/usdt/notify",
        content=raw,
        headers={"x-forge-signature": signature},
    )
    assert waiting.status_code == 200, waiting.text
    assert waiting.json()["data"]["accepted"] is False
    body["confirmations"] = 1
    app.state.usdt_gateway.orders[order["order_no"]] = body  # type: ignore[attr-defined]
    raw = json.dumps(body).encode()
    signature = usdt_signature(settings.usdt_webhook_secret, raw)
    paid = await client.post("/api/payments/usdt/notify", content=raw, headers={"x-forge-signature": signature})
    assert paid.status_code == 200, paid.text
    assert paid.json()["data"]["accepted"] is True
    paid_again = await client.post("/api/payments/usdt/notify", content=raw, headers={"x-forge-signature": signature})
    assert paid_again.json()["data"]["accepted"] is True
    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        snap = await LedgerService(session, app.state.clock).snapshot(user_id, "USD")  # type: ignore[attr-defined]
    assert snap.available == Decimal("10.00000000")

    under_id = await _product(app, "12", "少付")
    under = await client.post(
        "/api/payments/orders",
        headers={"Idempotency-Key": "usdt-under"},
        json={"product_id": under_id, "channel": "usdt"},
    )
    under_order = under.json()["data"]
    under_body = _usdt_body(under_order, amount="1.00000000", confirmations=1)
    app.state.usdt_gateway.orders[under_order["order_no"]] = under_body  # type: ignore[attr-defined]
    under_raw = json.dumps(under_body).encode()
    under_paid = await client.post(
        "/api/payments/usdt/notify",
        content=under_raw,
        headers={"x-forge-signature": usdt_signature(settings.usdt_webhook_secret, under_raw)},
    )
    assert under_paid.json()["data"]["accepted"] is False
    assert under_paid.json()["data"]["order"]["status"] == "underpaid"

    blocked_id = await _product(app, "8", "黑名单")
    blocked = await client.post(
        "/api/payments/orders",
        headers={"Idempotency-Key": "usdt-block"},
        json={"product_id": blocked_id, "channel": "usdt"},
    )
    blocked_order = blocked.json()["data"]
    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        session.add(
            SanctionedAddress(
                address="TBadPayer0000000000000000000001",
                network="TRC20",
                source="test",
                reason="名单",
                created_at=app.state.clock.now(),  # type: ignore[attr-defined]
            )
        )
        await session.commit()
    blocked_body = _usdt_body(
        blocked_order,
        amount=str(blocked_order["crypto_amount"]),
        confirmations=1,
        payer="TBadPayer0000000000000000000001",
    )
    app.state.usdt_gateway.orders[blocked_order["order_no"]] = blocked_body  # type: ignore[attr-defined]
    blocked_raw = json.dumps(blocked_body).encode()
    blocked_paid = await client.post(
        "/api/payments/usdt/notify",
        content=blocked_raw,
        headers={"x-forge-signature": usdt_signature(settings.usdt_webhook_secret, blocked_raw)},
    )
    assert blocked_paid.json()["data"]["accepted"] is False
    assert blocked_paid.json()["data"]["order"]["risk_status"] == "sanctioned"
    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        snap = await LedgerService(session, app.state.clock).snapshot(user_id, "USD")  # type: ignore[attr-defined]
    assert snap.available == Decimal("10.00000000")


@pytest.mark.asyncio
async def test_tc_pay_102_stripe_requires_signature_and_query(api: tuple[httpx.AsyncClient, object]) -> None:
    client, app = api
    user_id = await _login(client, app, "stripe@example.com")
    settings: Settings = app.state.settings  # type: ignore[attr-defined]
    clock: ManualClock = app.state.clock  # type: ignore[attr-defined]
    product_id = await _product(app, "10", "卡")
    created = await client.post(
        "/api/payments/orders",
        headers={"Idempotency-Key": "stripe-1"},
        json={"product_id": product_id, "channel": "stripe"},
    )
    assert created.status_code == 200, created.text
    order_no = created.json()["data"]["order_no"]
    ref = "cs_" + order_no
    app.state.stripe_gateway.sessions[ref]["payment_status"] = "paid"  # type: ignore[attr-defined]
    payload = {
        "id": "evt_1",
        "data": {
            "object": {
                "id": ref,
                "client_reference_id": order_no,
                "amount_total": 1000,
                "currency": "usd",
                "payment_status": "paid",
            }
        },
    }
    raw = json.dumps(payload).encode()
    forged = await client.post("/api/payments/stripe/webhook", content=raw, headers={"stripe-signature": "t=1,v1=00"})
    assert forged.status_code == 400
    timestamp = str(int(clock.now().timestamp()))
    import hashlib
    import hmac

    signature = hmac.new(
        settings.stripe_webhook_secret.encode(),
        timestamp.encode() + b"." + raw,
        hashlib.sha256,
    ).hexdigest()
    header = f"t={timestamp},v1={signature}"
    assert stripe_signature_ok(settings.stripe_webhook_secret, raw, header, clock.now())
    paid = await client.post("/api/payments/stripe/webhook", content=raw, headers={"stripe-signature": header})
    assert paid.status_code == 200, paid.text
    paid_again = await client.post("/api/payments/stripe/webhook", content=raw, headers={"stripe-signature": header})
    assert paid_again.status_code == 200
    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        snap = await LedgerService(session, clock).snapshot(user_id, "USD")
        count = (await session.execute(select(PaymentOrder).where(PaymentOrder.status == "completed"))).scalars().all()
    assert snap.available == Decimal("10.00000000")
    assert len(count) == 1


@pytest.mark.asyncio
async def test_tc_pay_103_refund_needs_two_people(api: tuple[httpx.AsyncClient, object]) -> None:
    client, app = api
    requester = await _login(client, app, "finance1@example.com")
    await _grant(app, requester, "finance")
    product_id = await _product(app, "10", "退款")
    created = await client.post(
        "/api/payments/orders",
        headers={"Idempotency-Key": "refund-1"},
        json={"product_id": product_id, "channel": "mock"},
    )
    order_no = created.json()["data"]["order_no"]
    assert (await client.post("/api/payments/mock/confirm", json={"order_no": order_no})).status_code == 200
    requested = await client.post("/api/admin/refunds", json={"order_no": order_no, "reason": "客户要求"})
    assert requested.status_code == 200, requested.text
    refund_id = requested.json()["data"]["id"]
    listed = await client.get("/api/admin/refunds")
    assert listed.status_code == 200, listed.text
    assert listed.json()["data"]["can_request"] is True
    assert listed.json()["data"]["refunds"][0]["order_no"] == order_no
    assert listed.json()["data"]["refunds"][0]["reason"] == "客户要求"
    self_review = await client.post(f"/api/admin/refunds/{refund_id}/review")
    assert self_review.status_code == 403
    reviewer_transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    executor_transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=reviewer_transport, base_url="http://test") as reviewer:
        reviewer_id = await _login(reviewer, app, "finance2@example.com")
        await _grant(app, reviewer_id, "finance")
        reviewed = await reviewer.post(f"/api/admin/refunds/{refund_id}/review")
        assert reviewed.status_code == 200, reviewed.text
        cannot_execute = await reviewer.post(f"/api/admin/refunds/{refund_id}/execute", json={})
        assert cannot_execute.status_code == 403
    async with httpx.AsyncClient(transport=executor_transport, base_url="http://test") as executor:
        executor_id = await _login(executor, app, "admin-pay@example.com")
        await _grant(app, executor_id, "admin")
        executed = await executor.post(f"/api/admin/refunds/{refund_id}/execute", json={"tx_hash": None})
        assert executed.status_code == 200, executed.text
        assert executed.json()["data"]["status"] == "executed"
    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        snap = await LedgerService(session, app.state.clock).snapshot(requester, "USD")  # type: ignore[attr-defined]
    assert snap.available == Decimal("0.00000000")


@pytest.mark.asyncio
async def test_tc_pay_104_reconcile_marks_mismatch_disputed(api: tuple[httpx.AsyncClient, object]) -> None:
    client, app = api
    user_id = await _login(client, app, "recon@example.com")
    await _grant(app, user_id, "finance")
    product_id = await _product(app, "10", "对账")
    created = await client.post(
        "/api/payments/orders",
        headers={"Idempotency-Key": "recon-1"},
        json={"product_id": product_id, "channel": "mock"},
    )
    order_no = created.json()["data"]["order_no"]
    assert (await client.post("/api/payments/mock/confirm", json={"order_no": order_no})).status_code == 200
    clock: ManualClock = app.state.clock  # type: ignore[attr-defined]
    report = await client.post(
        "/api/admin/payments/reconcile",
        json={"channel": "mock", "bill_date": clock.now().date().isoformat(), "rows": []},
    )
    assert report.status_code == 200, report.text
    assert report.json()["data"]["disputed"] == 1
    matched = await client.post(
        "/api/admin/payments/reconcile",
        json={
            "channel": "mock",
            "bill_date": clock.now().date().isoformat(),
            "rows": [{"order_no": order_no, "amount": "10.00000000"}],
        },
    )
    assert matched.json()["data"]["matched"] == 1
    assert matched.json()["data"]["disputed"] == 0


@pytest.mark.asyncio
async def test_tc_pay_105_rate_deviation_and_expiry(api: tuple[httpx.AsyncClient, object]) -> None:
    client, app = api
    await _login(client, app, "rate@example.com")
    clock: ManualClock = app.state.clock  # type: ignore[attr-defined]
    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        session.add(
            ExchangeRate(
                base_currency="USDT",
                quote_currency="USD",
                rate=Decimal("1.20000000"),
                source="bad-feed",
                captured_at=clock.now(),
            )
        )
        await session.commit()
    product_id = await _product(app, "10", "偏离")
    rejected = await client.post(
        "/api/payments/orders",
        headers={"Idempotency-Key": "rate-1"},
        json={"product_id": product_id, "channel": "usdt"},
    )
    assert rejected.status_code == 400
    tiny = await _product(app, "1", "过低")
    low = await client.post(
        "/api/payments/orders",
        headers={"Idempotency-Key": "rate-2"},
        json={"product_id": tiny, "channel": "usdt"},
    )
    assert low.status_code == 400
    app.state.settings = Settings(  # type: ignore[attr-defined]
        admin_init_token_path="unused",
        usdt_callback_ips="testclient",
        operating_mode="mainland",
    )
    mainland = await client.post(
        "/api/payments/orders",
        headers={"Idempotency-Key": "rate-3"},
        json={"product_id": product_id, "channel": "usdt"},
    )
    assert mainland.status_code == 400
