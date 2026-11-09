from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from app.core.clock import SystemClock
from app.db.base import Base
from app.db.models.auth import User
from app.db.models.billing import AccountBalance, AccountLedger
from app.db.models.providers import AuditEvent
from app.ops.ledger_audit import reconcile
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def _entry(user_id, *, direction: str, amount: str, before: str, after: str, key: str) -> AccountLedger:
    now = datetime.now(UTC)
    return AccountLedger(
        user_id=user_id,
        entry_type="recharge" if direction == "C" else "consume",
        direction=direction,
        amount=Decimal(amount),
        currency="USD",
        idempotency_key=key,
        balance_before=Decimal(before),
        balance_after=Decimal(after),
        reason="test",
        created_at=now,
    )


@pytest.mark.asyncio
async def test_reconcile_detects_and_repairs_snapshot_drift() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite(dbapi_conn, _record) -> None:  # type: ignore[no-untyped-def]
        dbapi_conn.create_function(
            "char_length", 1, lambda value: len(value) if isinstance(value, str) else None
        )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)

    async with maker() as session:
        user = User(
            id=uuid4(),
            email="drift@example.com",
            email_normalized="drift@example.com",
            password_hash="x",
            status="active",
        )
        session.add(user)
        await session.flush()
        # 快照被改坏了：流水净额应为 100 - 30 = 70
        session.add(
            AccountBalance(
                user_id=user.id,
                currency="USD",
                balance=Decimal("999"),
                held=Decimal("0"),
                frozen=Decimal("0"),
                updated_at=now,
            )
        )
        session.add_all(
            [
                _entry(user.id, direction="C", amount="100", before="0", after="100", key="k1"),
                _entry(user.id, direction="D", amount="30", before="100", after="70", key="k2"),
            ]
        )
        await session.commit()

        dry_run = await reconcile(session, SystemClock(), apply=False)
        await session.commit()
        assert dry_run["checked_accounts"] == 1
        assert dry_run["mismatch_count"] == 1
        assert dry_run["repaired"] == 0
        mismatch = dry_run["mismatches"][0]
        assert mismatch["snapshot"]["balance"] == "999.00000000"
        assert mismatch["expected"]["balance"] == "70.00000000"
        assert mismatch["delta"]["balance"] == "-929.00000000"

        repaired = await reconcile(session, SystemClock(), apply=True)
        await session.commit()
        assert repaired["repaired"] == 1

        snapshot = await session.get(AccountBalance, (user.id, "USD"))
        assert snapshot is not None
        assert snapshot.balance == Decimal("70.00000000")

        audits = await session.scalar(select(func.count()).select_from(AuditEvent))
        assert audits == 1

        # 修完之后再跑一次应当是干净的
        clean = await reconcile(session, SystemClock(), apply=False)
        await session.commit()
        assert clean["mismatch_count"] == 0

    await engine.dispose()
