"""后台各模块操作矩阵验收：角色 code 与增删改查是否真正打通。"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from datetime import date
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
from app.db.models.auth import UserRole
from app.db.models.payments import RechargeProduct
from app.db.models.providers import ModelCatalog, ModelDeployment
from app.main import create_app
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
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


async def _login(client: AsyncClient, app: object, email: str, *, register: bool = True) -> UUID:
    if register:
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
            UserRole(
                user_id=user_id,
                role_id=UUID(ROLE_IDS[role]),
                granted_at=app.state.clock.now(),  # type: ignore[attr-defined]
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_user_roles_return_codes_and_remove_works(api: tuple[AsyncClient, object]) -> None:
    """修复点：列表必须返回 code；普通用户不可撤；客服可撤。"""
    client, app = api
    target_id = await _login(client, app, "matrix-user@example.com")
    admin_id = await _login(client, app, "matrix-admin@example.com")
    await _grant(app, admin_id, "admin")
    await _grant(app, admin_id, "superadmin")

    assigned = await client.post(f"/api/admin/users/{target_id}/roles", json={"role_code": "support"})
    assert assigned.status_code == 200, assigned.text

    listed = await client.get("/api/admin/users")
    assert listed.status_code == 200, listed.text
    row = next(item for item in listed.json()["data"]["users"] if item["id"] == str(target_id))
    assert "user" in row["roles"]
    assert "support" in row["roles"]
    assert "普通用户" not in row["roles"]
    assert "客服" not in row["roles"]
    assert "User" in row["role_labels"]
    assert "Support" in row["role_labels"]

    # 中文名路径必须失败（旧前端 bug）
    bad = await client.delete(f"/api/admin/users/{target_id}/roles/普通用户")
    assert bad.status_code == 400

    # 基础角色不可撤
    blocked = await client.delete(f"/api/admin/users/{target_id}/roles/user")
    assert blocked.status_code == 400
    assert blocked.json()["error"]["code"] == "ROLE_USER_REVOKE_FORBIDDEN"

    # 附加角色可撤
    removed = await client.delete(f"/api/admin/users/{target_id}/roles/support")
    assert removed.status_code == 200, removed.text
    assert removed.json()["data"]["removed"] is True

    listed2 = await client.get("/api/admin/users")
    row2 = next(item for item in listed2.json()["data"]["users"] if item["id"] == str(target_id))
    assert "support" not in row2["roles"]
    assert "user" in row2["roles"]

    searched = await client.get("/api/admin/users?q=matrix-user")
    assert searched.status_code == 200
    assert any(item["id"] == str(target_id) for item in searched.json()["data"]["users"])
    empty = await client.get("/api/admin/users?q=no-such-user-xyz")
    assert empty.status_code == 200
    assert empty.json()["data"]["users"] == []
    frozen_filter = await client.get("/api/admin/users?status=active")
    assert frozen_filter.status_code == 200
    assert all(item["status"] == "active" for item in frozen_filter.json()["data"]["users"])


@pytest.mark.asyncio
async def test_admin_feature_matrix_crud(api: tuple[AsyncClient, object]) -> None:
    """逐模块打通：供应商/模型/套餐/优惠券/公告/工单/订单/账本/退款/发票/备份等。"""
    client, app = api
    customer_id = await _login(client, app, "matrix-customer@example.com")
    admin_id = await _login(client, app, "matrix-ops@example.com")
    await _grant(app, admin_id, "admin")
    await _grant(app, admin_id, "superadmin")
    await _grant(app, admin_id, "model_ops")
    await _grant(app, admin_id, "finance")

    # --- 只读入口 ---
    for path in (
        "/api/admin/overview",
        "/api/admin/users",
        "/api/admin/providers",
        "/api/admin/providers/presets",
        "/api/admin/models",
        "/api/admin/deployments",
        "/api/admin/keys",
        "/api/admin/orders",
        "/api/admin/products",
        "/api/admin/refunds",
        "/api/admin/ledger",
        "/api/admin/usage",
        "/api/admin/crypto",
        "/api/admin/health",
        "/api/admin/audit",
        "/api/admin/audit/verify",
        "/api/admin/routes",
        "/api/admin/settings",
        "/api/admin/backups",
        "/api/admin/announcements",
        "/api/admin/tickets",
        "/api/admin/invoices",
        "/api/admin/coupons",
        "/api/admin/margin",
        "/api/admin/content-safety",
        "/api/admin/tasks",
        "/api/admin/allowlist",
        "/api/admin/prices",
    ):
        resp = await client.get(path)
        assert resp.status_code == 200, f"{path} -> {resp.status_code} {resp.text}"

    # --- 供应商 C/U/D ---
    provider = await client.post(
        "/api/admin/providers",
        json={"name": "测试上游", "kind": "openai", "base_url": "https://api.openai.com/v1"},
    )
    assert provider.status_code == 200, provider.text
    provider_id = provider.json()["data"]["id"]
    patched = await client.patch(
        f"/api/admin/providers/{provider_id}",
        json={"name": "测试上游2", "priority": 50, "weight": 2},
    )
    assert patched.status_code == 200
    assert patched.json()["data"]["name"] == "测试上游2"

    allow = await client.post("/api/admin/allowlist", json={"host": "127.0.0.1", "note": "本机"})
    assert allow.status_code == 200, allow.text
    allow_list = await client.get("/api/admin/allowlist")
    allow_id = allow_list.json()["data"]["items"][0]["id"]
    assert (await client.post(f"/api/admin/allowlist/{allow_id}/revoke")).status_code == 200

    # --- 模型/部署 ---
    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        model = ModelCatalog(
            provider_id=UUID(provider_id),
            upstream_name="gpt-matrix",
            public_name="gpt-matrix",
            display_name="GPT Matrix",
            status="pending",
            supports_stream=True,
            supports_embeddings=False,
        )
        session.add(model)
        await session.flush()
        model_id = str(model.id)
        session.add(
            ModelDeployment(
                model_id=model.id,
                provider_id=UUID(provider_id),
                status="disabled",
            )
        )
        await session.commit()

    published = await client.post(
        f"/api/admin/models/{model_id}/publish",
        json={"display_name": "矩阵模型", "supports_stream": True, "supports_embeddings": False},
    )
    assert published.status_code == 200, published.text
    priced = await client.post(
        "/api/admin/prices",
        json={
            "model_id": model_id,
            "meters": [
                {"meter": "input_token", "unit_price": "0.000001", "cost_price": "0.0000005", "min_billable_units": 0},
                {"meter": "output_token", "unit_price": "0.000002", "cost_price": "0.000001", "min_billable_units": 0},
            ],
        },
    )
    assert priced.status_code == 200, priced.text
    deps = await client.get("/api/admin/deployments")
    assert deps.status_code == 200
    dep_id = deps.json()["data"]["deployments"][0]["id"]
    assert (await client.post(f"/api/admin/deployments/{dep_id}/status", json={"status": "disabled"})).status_code == 200
    assert (await client.post(f"/api/admin/models/{model_id}/unpublish")).status_code == 200
    assert (await client.delete(f"/api/admin/providers/{provider_id}")).status_code == 200

    # --- 套餐 ---
    product = await client.post(
        "/api/admin/products",
        json={"name": "矩阵套餐", "amount": "15", "bonus_amount": "1", "sort_order": 1},
    )
    assert product.status_code == 200, product.text
    product_id = product.json()["data"]["id"]
    assert (await client.patch(f"/api/admin/products/{product_id}", json={"name": "矩阵套餐改", "bonus_amount": "2"})).status_code == 200
    assert (await client.delete(f"/api/admin/products/{product_id}")).status_code == 200

    # --- 优惠券 ---
    coupon = await client.post("/api/admin/coupons", json={"auto_generate": True, "bonus_amount": "3", "max_uses": 5})
    assert coupon.status_code == 200, coupon.text
    coupon_id = coupon.json()["data"]["id"]
    assert (await client.patch(f"/api/admin/coupons/{coupon_id}", json={"max_uses": 8, "enabled": True})).status_code == 200
    assert (await client.delete(f"/api/admin/coupons/{coupon_id}")).status_code == 200

    # --- 公告 ---
    ann = await client.post("/api/admin/announcements", json={"slug": "matrix", "title": "矩阵公告", "body": "正文"})
    assert ann.status_code == 200, ann.text
    ann_id = ann.json()["data"]["id"]
    assert (await client.patch(f"/api/admin/announcements/{ann_id}", json={"title": "改标题", "body": "改正文"})).status_code == 200
    assert (await client.post(f"/api/admin/announcements/{ann_id}/publish", json={"published": True})).status_code == 200
    assert (await client.delete(f"/api/admin/announcements/{ann_id}")).status_code == 200

    # --- 工单（客户建，管理关）---
    await client.post("/api/auth/logout")
    await _login(client, app, "matrix-customer@example.com", register=False)
    ticket = await client.post(
        "/api/tickets",
        json={"category": "billing", "subject": "矩阵工单", "body": "请处理"},
    )
    assert ticket.status_code == 200, ticket.text
    ticket_id = ticket.json()["data"]["id"]
    await client.post("/api/auth/logout")
    await _login(client, app, "matrix-ops@example.com", register=False)
    reply = await client.post(
        f"/api/admin/tickets/{ticket_id}/messages",
        json={"body": "已收到", "status": "pending"},
    )
    assert reply.status_code == 200, reply.text
    assert (await client.post(f"/api/admin/tickets/{ticket_id}/close")).status_code == 200

    # --- 订单关闭 ---
    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        product_row = RechargeProduct(
            name="订单套餐",
            amount=Decimal("9"),
            bonus_amount=Decimal("0"),
            currency="USD",
            enabled=True,
            sort_order=1,
            created_at=app.state.clock.now(),  # type: ignore[attr-defined]
        )
        session.add(product_row)
        await session.commit()
        live_product_id = str(product_row.id)

    await client.post("/api/auth/logout")
    await _login(client, app, "matrix-customer@example.com", register=False)
    order = await client.post(
        "/api/payments/orders",
        json={"product_id": live_product_id, "channel": "mock"},
        headers={"Idempotency-Key": "matrix-order-1"},
    )
    assert order.status_code == 200, order.text
    order_no = order.json()["data"]["order_no"]
    await client.post("/api/auth/logout")
    await _login(client, app, "matrix-ops@example.com", register=False)
    assert (await client.post(f"/api/admin/orders/{order_no}/cancel")).status_code == 200

    # --- 账本调账 ---
    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        await LedgerService(session, app.state.clock).post(  # type: ignore[attr-defined]
            user_id=customer_id,
            entry_type="recharge",
            amount=Decimal("50"),
            currency="USD",
            idempotency_key="matrix-seed",
            direction="C",
            reason="seed",
        )
        await session.commit()
    adjust = await client.post(
        "/api/admin/ledger/adjust",
        json={"user_id": str(customer_id), "amount": "1", "direction": "D", "reason": "矩阵纠错"},
        headers={"Idempotency-Key": "matrix-adjust-1"},
    )
    assert adjust.status_code == 200, adjust.text

    # --- 内容安全 / 任务 / 对账空跑 ---
    assert (await client.post("/api/admin/content-safety", json={"enabled": True})).status_code == 200
    assert (await client.post("/api/admin/tasks/ping")).status_code == 200
    reconcile = await client.post(
        "/api/admin/payments/reconcile",
        json={"channel": "mock", "bill_date": date.today().isoformat(), "rows": []},
    )
    assert reconcile.status_code == 200, reconcile.text

    # --- 用户冻结/注销 ---
    assert (await client.post(f"/api/admin/users/{customer_id}/status", json={"status": "frozen"})).status_code == 200
    assert (await client.post(f"/api/admin/users/{customer_id}/status", json={"status": "active"})).status_code == 200
    assert (await client.post(f"/api/admin/users/{customer_id}/delete")).status_code == 200
