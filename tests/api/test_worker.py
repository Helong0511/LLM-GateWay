from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.worker import worker_ping


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 10, 28, 3, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_worker_ping_uses_injected_clock() -> None:
    stamped = await worker_ping({"clock": FixedClock()})
    assert stamped == "2026-10-28T03:00:00+00:00"
