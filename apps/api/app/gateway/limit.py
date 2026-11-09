"""单进程请求与并发闸。多进程部署时这只覆盖当前进程。"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.core.clock import Clock


class MemoryRateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, list[tuple[datetime, int]]] = {}

    def allow(self, clock: Clock, key: str, limit: int | None, *, cost: int = 1, window_seconds: int = 60) -> bool:
        if limit is None:
            return True
        now = clock.now()
        cutoff = now - timedelta(seconds=window_seconds)
        recent = [item for item in self._hits.get(key, []) if item[0] >= cutoff]
        used = sum(item[1] for item in recent)
        if used + cost > limit:
            self._hits[key] = recent
            return False
        recent.append((now, cost))
        self._hits[key] = recent
        return True


class MemorySlots:
    def __init__(self) -> None:
        self._held: dict[str, int] = {}

    def acquire(self, key: str, limit: int | None) -> bool:
        if limit is None:
            return True
        current = self._held.get(key, 0)
        if current >= limit:
            return False
        self._held[key] = current + 1
        return True

    def release(self, key: str, limit: int | None) -> None:
        if limit is None:
            return
        self._held[key] = max(0, self._held.get(key, 0) - 1)

    def held(self, key: str) -> int:
        return self._held.get(key, 0)
