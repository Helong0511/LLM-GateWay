"""可注入时钟。超时、过期与锁价测试不得依赖真实墙钟。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:
        """返回带时区的当前时刻（UTC）。"""


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class ManualClock:
    """测试用时钟。推进时间不会等待真实秒数。"""

    def __init__(self, current: datetime | None = None) -> None:
        self.current = current or datetime(2026, 10, 28, tzinfo=UTC)

    def now(self) -> datetime:
        return self.current

    def advance(self, *, seconds: int = 0, hours: int = 0, days: int = 0) -> None:
        self.current += timedelta(seconds=seconds, hours=hours, days=days)
