from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.worker import WorkerSettings, purge_litellm_logs, worker_ping


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 10, 28, 3, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_worker_ping_uses_injected_clock() -> None:
    stamped = await worker_ping({"clock": FixedClock()})
    assert stamped == "2026-10-28T03:00:00+00:00"


def test_background_jobs_are_actually_scheduled() -> None:
    """cron_jobs 为空时 arq 只消费队列，资金闭环任务永远不会跑。"""
    scheduled = {job.coroutine.__name__ for job in WorkerSettings.cron_jobs}
    assert {
        "release_expired_holds",
        "close_expired_payments",
        "close_stale_usage",
        "reconcile_litellm_registry",
        "purge_litellm_logs",
        "verify_audit_chain",
    } <= scheduled
    functions = {getattr(fn, "__name__", "") for fn in WorkerSettings.functions}
    assert scheduled <= functions


@pytest.mark.asyncio
async def test_purge_litellm_logs_is_noop_without_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LITELLM_DATABASE_URL", "")
    assert await purge_litellm_logs({}) == 0
