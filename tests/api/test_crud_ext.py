"""补齐的增删改查接口验收。"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
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
from decimal import Decimal

from app.db.models.ops import Coupon
from app.db.models.payments import RechargeProduct
from app.db.models.providers import EndpointAllowlist, ModelCatalog, ModelDeployment, Provider
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
async def test_key_update_and_order_cancel(api: tuple[AsyncClient, object]) -> None:
    client, app = api
    user_id = await _login(client, app, "crud-key@example.com")
    created = await client.post("/api/keys", json={"name": "调试"})
    assert created.status_code == 200, created.text
    key_id = created.json()["data"]["id"]
    updated = await client.patch(
        f"/api/keys/{key_id}",
        json={"name": "生产", "budget_limit": "12.5"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["name"] == "生产"
    assert updated.json()["data"]["allowed_models"] == []

    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        product = RechargeProduct(
            name="10 元",
            amount=Decimal("10"),
            bonus_amount=Decimal("0"),
            currency="USD",
            enabled=True,
            sort_order=1,
            created_at=app.state.clock.now(),  # type: ignore[attr-defined]
        )
        session.add(product)
        await session.commit()
        product_id = str(product.id)

    order = await client.post(
        "/api/payments/orders",
        json={"product_id": product_id, "channel": "mock"},
        headers={"Idempotency-Key": "cancel-order-1"},
    )
    assert order.status_code == 200, order.text
    order_no = order.json()["data"]["order_no"]
    canceled = await client.post(f"/api/payments/orders/{order_no}/cancel")
    assert canceled.status_code == 200, canceled.text
    assert canceled.json()["data"]["status"] == "closed"
    _ = user_id


@pytest.mark.asyncio
async def test_admin_products_allowlist_announcement_adjust(api: tuple[AsyncClient, object]) -> None:
    client, app = api
    admin_id = await _login(client, app, "crud-admin@example.com")
    await _grant(app, admin_id, "superadmin")
    await _grant(app, admin_id, "admin")
    await _grant(app, admin_id, "model_ops")

    product = await client.post(
        "/api/admin/products",
        json={"name": "试玩", "amount": "5", "bonus_amount": "1", "sort_order": 1},
    )
    assert product.status_code == 200, product.text
    product_id = product.json()["data"]["id"]
    disabled = await client.patch(f"/api/admin/products/{product_id}", json={"enabled": False})
    assert disabled.status_code == 200
    assert disabled.json()["data"]["enabled"] is False

    allow = await client.post("/api/admin/allowlist", json={"host": "lab.local", "note": "本地"})
    assert allow.status_code == 200, allow.text
    listed = await client.get("/api/admin/allowlist")
    assert listed.status_code == 200
    item_id = listed.json()["data"]["items"][0]["id"]
    revoked = await client.post(f"/api/admin/allowlist/{item_id}/revoke")
    assert revoked.status_code == 200
    assert revoked.json()["data"]["approved"] is False

    created = await client.post(
        "/api/admin/announcements",
        json={"slug": "n1", "title": "标题", "body": "正文内容"},
    )
    assert created.status_code == 200, created.text
    announcement_id = created.json()["data"]["id"]
    patched = await client.patch(
        f"/api/admin/announcements/{announcement_id}",
        json={"title": "新标题", "body": "新正文"},
    )
    assert patched.status_code == 200
    deleted = await client.delete(f"/api/admin/announcements/{announcement_id}")
    assert deleted.status_code == 200

    customer_id = await _login(client, app, "crud-user@example.com")
    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        await LedgerService(session, app.state.clock).post(  # type: ignore[attr-defined]
            user_id=customer_id,
            entry_type="recharge",
            amount=Decimal("20"),
            currency="USD",
            idempotency_key="seed-balance",
            direction="C",
            reason="seed",
        )
        await session.commit()

    await client.post("/api/auth/logout")
    await _login(client, app, "crud-admin@example.com", register=False)
    adjusted = await client.post(
        "/api/admin/ledger/adjust",
        json={"user_id": str(customer_id), "amount": "3", "direction": "D", "reason": "纠错"},
        headers={"Idempotency-Key": "adjust-1"},
    )
    assert adjusted.status_code == 200, adjusted.text
    assert adjusted.json()["data"]["direction"] == "D"


@pytest.mark.asyncio
async def test_ticket_close_coupon_disable_role_remove(api: tuple[AsyncClient, object]) -> None:
    client, app = api
    user_id = await _login(client, app, "crud-ops@example.com")
    ticket = await client.post(
        "/api/tickets",
        json={"category": "billing", "subject": "余额疑问", "body": "请帮忙看一下"},
    )
    assert ticket.status_code == 200, ticket.text
    ticket_id = ticket.json()["data"]["id"]
    closed = await client.post(f"/api/tickets/{ticket_id}/close")
    assert closed.status_code == 200
    assert closed.json()["data"]["status"] == "closed"

    admin_id = await _login(client, app, "crud-ops-admin@example.com")
    await _grant(app, admin_id, "admin")
    await _grant(app, admin_id, "superadmin")

    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        coupon = Coupon(
            code="BONUS1",
            bonus_amount=Decimal("2"),
            currency="USD",
            max_uses=10,
            used_count=0,
            enabled=True,
            created_at=app.state.clock.now(),  # type: ignore[attr-defined]
        )
        session.add(coupon)
        await session.commit()
        coupon_id = str(coupon.id)

    disabled = await client.patch(f"/api/admin/coupons/{coupon_id}", json={"enabled": False})
    assert disabled.status_code == 200
    assert disabled.json()["data"]["enabled"] is False

    await _grant(app, user_id, "support")
    removed = await client.delete(f"/api/admin/users/{user_id}/roles/support")
    assert removed.status_code == 200, removed.text
    assert removed.json()["data"]["removed"] is True


@pytest.mark.asyncio
async def test_provider_update_model_unpublish_prices(api: tuple[AsyncClient, object]) -> None:
    client, app = api
    admin_id = await _login(client, app, "crud-model@example.com")
    await _grant(app, admin_id, "model_ops")
    await _grant(app, admin_id, "admin")

    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        provider = Provider(
            name="demo",
            kind="openai",
            base_url="https://example.com/v1",
            status="active",
            created_at=app.state.clock.now(),  # type: ignore[attr-defined]
            updated_at=app.state.clock.now(),  # type: ignore[attr-defined]
        )
        session.add(provider)
        await session.flush()
        model = ModelCatalog(
            provider_id=provider.id,
            upstream_name="gpt-test",
            public_name="gpt-test",
            display_name="GPT Test",
            status="published",
            supports_stream=True,
            supports_embeddings=False,
        )
        session.add(model)
        session.add(EndpointAllowlist(host="ok.local", approved=True, note=""))
        await session.commit()
        provider_id = str(provider.id)
        model_id = str(model.id)

    patched = await client.patch(f"/api/admin/providers/{provider_id}", json={"status": "disabled", "name": "demo2"})
    assert patched.status_code == 200, patched.text
    assert patched.json()["data"]["status"] == "disabled"
    unpublished = await client.post(f"/api/admin/models/{model_id}/unpublish")
    assert unpublished.status_code == 200, unpublished.text
    assert unpublished.json()["data"]["status"] == "disabled"
    prices = await client.get("/api/admin/prices")
    assert prices.status_code == 200
    deleted = await client.delete(f"/api/admin/providers/{provider_id}")
    assert deleted.status_code == 200
    assert deleted.json()["data"]["status"] == "deleted"
    restored = await client.post(f"/api/admin/providers/{provider_id}/restore")
    assert restored.status_code == 200
    assert restored.json()["data"]["status"] == "disabled"


@pytest.mark.asyncio
async def test_admin_order_cancel_ticket_close_user_delete(api: tuple[AsyncClient, object]) -> None:
    client, app = api
    customer_id = await _login(client, app, "crud-order-user@example.com")
    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        product = RechargeProduct(
            name="20 元",
            amount=Decimal("20"),
            bonus_amount=Decimal("0"),
            currency="USD",
            enabled=True,
            sort_order=1,
            created_at=app.state.clock.now(),  # type: ignore[attr-defined]
        )
        session.add(product)
        await session.commit()
        product_id = str(product.id)

    order = await client.post(
        "/api/payments/orders",
        json={"product_id": product_id, "channel": "mock"},
        headers={"Idempotency-Key": "admin-cancel-1"},
    )
    assert order.status_code == 200, order.text
    order_no = order.json()["data"]["order_no"]

    ticket = await client.post(
        "/api/tickets",
        json={"category": "other", "subject": "后台关闭", "body": "请后台处理"},
    )
    assert ticket.status_code == 200, ticket.text
    ticket_id = ticket.json()["data"]["id"]

    admin_id = await _login(client, app, "crud-order-admin@example.com")
    await _grant(app, admin_id, "admin")
    await _grant(app, admin_id, "superadmin")

    canceled = await client.post(f"/api/admin/orders/{order_no}/cancel")
    assert canceled.status_code == 200, canceled.text
    assert canceled.json()["data"]["status"] == "closed"

    closed = await client.post(f"/api/admin/tickets/{ticket_id}/close")
    assert closed.status_code == 200, closed.text
    assert closed.json()["data"]["status"] == "closed"

    deleted_user = await client.post(f"/api/admin/users/{customer_id}/delete")
    assert deleted_user.status_code == 200, deleted_user.text
    assert deleted_user.json()["data"]["status"] == "deleted"

    product_create = await client.post(
        "/api/admin/products",
        json={"name": "待删", "amount": "8", "bonus_amount": "0"},
    )
    assert product_create.status_code == 200
    product_id_del = product_create.json()["data"]["id"]
    product_del = await client.delete(f"/api/admin/products/{product_id_del}")
    assert product_del.status_code == 200
    assert product_del.json()["data"]["deleted"] is True
    assert product_del.json()["data"]["enabled"] is False
    product_restore = await client.post(f"/api/admin/products/{product_id_del}/restore")
    assert product_restore.status_code == 200
    assert product_restore.json()["data"]["deleted"] is False
    assert product_restore.json()["data"]["enabled"] is False

@pytest.mark.asyncio
async def test_publish_models_batch(api: tuple[AsyncClient, object]) -> None:
    client, app = api
    admin_id = await _login(client, app, 'batch-pub@example.com')
    await _grant(app, admin_id, 'admin')
    await _grant(app, admin_id, 'model_ops')
    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        provider = Provider(
            name='batch-upstream',
            kind='compatible',
            base_url='https://example.com/v1',
            protocol='openai',
            status='active',
            timeout_seconds=60,
            priority=100,
            weight=1,
        )
        session.add(provider)
        await session.flush()
        ids = []
        for name in ('m-a', 'm-b', 'm-c'):
            row = ModelCatalog(
                provider_id=provider.id,
                upstream_name=name,
                public_name=name,
                display_name=name,
                status='pending',
            )
            session.add(row)
            await session.flush()
            ids.append(str(row.id))
        await session.commit()
    result = await client.post(
        '/api/admin/models/publish-batch',
        json={'model_ids': ids, 'supports_stream': True, 'supports_embeddings': False},
    )
    assert result.status_code == 200, result.text
    body = result.json()['data']
    assert body['published'] == 3
    assert body['skipped'] == 0
    deps = await client.get('/api/admin/deployments')
    assert deps.status_code == 200
    assert len(deps.json()['data']['deployments']) == 3


@pytest.mark.asyncio
async def test_unpublish_models_batch(api: tuple[AsyncClient, object]) -> None:
    client, app = api
    admin_id = await _login(client, app, 'batch-unpub@example.com')
    await _grant(app, admin_id, 'admin')
    await _grant(app, admin_id, 'model_ops')
    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        provider = Provider(
            name='unpub-upstream',
            kind='compatible',
            base_url='https://example.com/v1',
            protocol='openai',
            status='active',
            timeout_seconds=60,
            priority=100,
            weight=1,
        )
        session.add(provider)
        await session.flush()
        ids = []
        for name in ('u-a', 'u-b', 'u-c'):
            row = ModelCatalog(
                provider_id=provider.id,
                upstream_name=name,
                public_name=name,
                display_name=name,
                status='disabled' if name == 'u-c' else 'published',
            )
            session.add(row)
            await session.flush()
            session.add(
                ModelDeployment(
                    model_id=row.id,
                    provider_id=provider.id,
                    status='active',
                )
            )
            ids.append(str(row.id))
        await session.commit()
    result = await client.post('/api/admin/models/unpublish-batch', json={'model_ids': ids})
    assert result.status_code == 200, result.text
    body = result.json()['data']
    assert body['unpublished'] == 2
    assert body['skipped'] == 1
    assert body['missing'] == 0
    deps = await client.get('/api/admin/deployments')
    assert deps.status_code == 200
    by_model = {row['model_id']: row for row in deps.json()['data']['deployments']}
    assert by_model[ids[0]]['status'] == 'disabled'
    assert by_model[ids[1]]['status'] == 'disabled'
    assert by_model[ids[2]]['status'] == 'active'
    again = await client.post('/api/admin/models/unpublish-batch', json={'model_ids': ids})
    assert again.status_code == 200, again.text
    assert again.json()['data']['unpublished'] == 0
    assert again.json()['data']['skipped'] == 3


@pytest.mark.asyncio
async def test_republish_restores_deployment_without_touching_published_edits(
    api: tuple[AsyncClient, object],
) -> None:
    """已下架模型重新上架要恢复部署；已上架模型只编辑设置时不能改动部署状态。"""
    client, app = api
    admin_id = await _login(client, app, 'republish@example.com')
    await _grant(app, admin_id, 'admin')
    await _grant(app, admin_id, 'model_ops')
    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        provider = Provider(
            name='repub-upstream',
            kind='compatible',
            base_url='https://example.com/v1',
            protocol='openai',
            status='active',
            timeout_seconds=60,
            priority=100,
            weight=1,
        )
        session.add(provider)
        await session.flush()
        disabled_row = ModelCatalog(
            provider_id=provider.id,
            upstream_name='repub-a',
            public_name='repub-a',
            display_name='repub-a',
            status='disabled',
            supports_stream=False,
            supports_embeddings=True,
        )
        published_row = ModelCatalog(
            provider_id=provider.id,
            upstream_name='repub-b',
            public_name='repub-b',
            display_name='repub-b',
            status='published',
            supports_stream=True,
            supports_embeddings=False,
        )
        session.add_all([disabled_row, published_row])
        await session.flush()
        session.add_all(
            [
                ModelDeployment(model_id=disabled_row.id, provider_id=provider.id, status='disabled'),
                ModelDeployment(model_id=published_row.id, provider_id=provider.id, status='disabled'),
            ]
        )
        await session.commit()
        disabled_id = str(disabled_row.id)
        published_id = str(published_row.id)

    republished = await client.post(
        f'/api/admin/models/{disabled_id}/publish',
        json={'display_name': 'repub-a', 'supports_stream': False, 'supports_embeddings': True},
    )
    assert republished.status_code == 200, republished.text
    deps = await client.get('/api/admin/deployments')
    assert deps.status_code == 200
    by_model = {row['model_id']: row for row in deps.json()['data']['deployments']}
    assert by_model[disabled_id]['status'] == 'active'
    assert by_model[disabled_id]['model_status'] == 'published'

    edited = await client.post(
        f'/api/admin/models/{published_id}/publish',
        json={'display_name': 'repub-b-new', 'supports_stream': True, 'supports_embeddings': False},
    )
    assert edited.status_code == 200, edited.text
    deps = await client.get('/api/admin/deployments')
    by_model = {row['model_id']: row for row in deps.json()['data']['deployments']}
    assert by_model[published_id]['status'] == 'disabled'
    assert by_model[published_id]['model_status'] == 'published'


@pytest.mark.asyncio
async def test_publish_batch_keeps_disabled_capabilities_and_restores_deployments(
    api: tuple[AsyncClient, object],
) -> None:
    """批量上架：待上架模型用批量默认能力；已下架模型保留原能力并恢复部署。"""
    client, app = api
    admin_id = await _login(client, app, 'batch-cap@example.com')
    await _grant(app, admin_id, 'admin')
    await _grant(app, admin_id, 'model_ops')
    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        provider = Provider(
            name='cap-upstream',
            kind='compatible',
            base_url='https://example.com/v1',
            protocol='openai',
            status='active',
            timeout_seconds=60,
            priority=100,
            weight=1,
        )
        session.add(provider)
        await session.flush()
        disabled_row = ModelCatalog(
            provider_id=provider.id,
            upstream_name='cap-a',
            public_name='cap-a',
            display_name='cap-a',
            status='disabled',
            supports_stream=False,
            supports_embeddings=True,
        )
        pending_row = ModelCatalog(
            provider_id=provider.id,
            upstream_name='cap-b',
            public_name='cap-b',
            display_name='cap-b',
            status='pending',
            supports_stream=None,
            supports_embeddings=None,
        )
        session.add_all([disabled_row, pending_row])
        await session.flush()
        session.add(
            ModelDeployment(model_id=disabled_row.id, provider_id=provider.id, status='disabled')
        )
        await session.commit()
        ids = [str(disabled_row.id), str(pending_row.id)]

    result = await client.post(
        '/api/admin/models/publish-batch',
        json={'model_ids': ids, 'supports_stream': True, 'supports_embeddings': False},
    )
    assert result.status_code == 200, result.text
    assert result.json()['data']['published'] == 2

    models = await client.get('/api/admin/models')
    assert models.status_code == 200
    by_id = {row['id']: row for row in models.json()['data']['models']}
    assert by_id[ids[0]]['supports_stream'] is False
    assert by_id[ids[0]]['supports_embeddings'] is True
    assert by_id[ids[1]]['supports_stream'] is True
    assert by_id[ids[1]]['supports_embeddings'] is False

    deps = await client.get('/api/admin/deployments')
    by_model = {row['model_id']: row for row in deps.json()['data']['deployments']}
    assert by_model[ids[0]]['status'] == 'active'


@pytest.mark.asyncio
async def test_deployment_enable_requires_published_model(api: tuple[AsyncClient, object]) -> None:
    """模型未上架时不能启用部署；批量启用计入 blocked，停用不受限制。"""
    client, app = api
    admin_id = await _login(client, app, 'dep-gate@example.com')
    await _grant(app, admin_id, 'admin')
    await _grant(app, admin_id, 'model_ops')
    async with app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        provider = Provider(
            name='dep-upstream',
            kind='compatible',
            base_url='https://example.com/v1',
            protocol='openai',
            status='active',
            timeout_seconds=60,
            priority=100,
            weight=1,
        )
        session.add(provider)
        await session.flush()
        row = ModelCatalog(
            provider_id=provider.id,
            upstream_name='dep-a',
            public_name='dep-a',
            display_name='dep-a',
            status='pending',
            supports_stream=True,
            supports_embeddings=False,
        )
        session.add(row)
        await session.flush()
        deployment = ModelDeployment(model_id=row.id, provider_id=provider.id, status='disabled')
        session.add(deployment)
        await session.commit()
        deployment_id = str(deployment.id)
        model_id = str(row.id)

    single = await client.post(
        f'/api/admin/deployments/{deployment_id}/status',
        json={'status': 'active'},
    )
    assert single.status_code == 409
    assert single.json()['error']['code'] == 'DEPLOYMENT_MODEL_UNPUBLISHED'

    batch = await client.post(
        '/api/admin/deployments/status-batch',
        json={'deployment_ids': [deployment_id], 'status': 'active'},
    )
    assert batch.status_code == 200, batch.text
    assert batch.json()['data']['updated'] == 0
    assert batch.json()['data']['blocked'] == 1

    published = await client.post(
        f'/api/admin/models/{model_id}/publish',
        json={'display_name': 'dep-a', 'supports_stream': True, 'supports_embeddings': False},
    )
    assert published.status_code == 200, published.text
    deps = await client.get('/api/admin/deployments')
    by_model = {row['model_id']: row for row in deps.json()['data']['deployments']}
    assert by_model[model_id]['status'] == 'active'

    disabled = await client.post(
        f'/api/admin/deployments/{deployment_id}/status',
        json={'status': 'disabled'},
    )
    assert disabled.status_code == 200, disabled.text
    batch_again = await client.post(
        '/api/admin/deployments/status-batch',
        json={'deployment_ids': [deployment_id], 'status': 'active'},
    )
    assert batch_again.status_code == 200, batch_again.text
    assert batch_again.json()['data']['updated'] == 1
    assert batch_again.json()['data']['blocked'] == 0
