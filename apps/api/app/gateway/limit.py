"""请求限流与并发闸。

进程内实现只在单 worker 下准确：多副本时实际阈值 = 配置值 × 进程数，
且 `_hits` 字典永不回收。生产环境用 Redis 实现（固定窗口计数 + 带 TTL 的
并发计数），Redis 不可用时自动退回进程内实现，保证降级可用。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol

from app.core.clock import Clock


class RateLimiter(Protocol):
    async def allow(
        self, clock: Clock, key: str, limit: int | None, *, cost: int = 1, window_seconds: int = 60
    ) -> bool: ...


class Slots(Protocol):
    async def acquire(self, key: str, limit: int | None) -> bool: ...

    async def release(self, key: str, limit: int | None) -> None: ...


class MemoryRateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, list[tuple[datetime, int]]] = {}

    async def allow(
        self, clock: Clock, key: str, limit: int | None, *, cost: int = 1, window_seconds: int = 60
    ) -> bool:
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
        # 顺手回收长期空闲的键，避免长跑进程内存单调增长。
        if len(self._hits) > 10_000:
            for stale in [k for k, v in self._hits.items() if not v or v[-1][0] < cutoff]:
                self._hits.pop(stale, None)
        return True


class MemorySlots:
    def __init__(self) -> None:
        self._held: dict[str, int] = {}

    async def acquire(self, key: str, limit: int | None) -> bool:
        if limit is None:
            return True
        current = self._held.get(key, 0)
        if current >= limit:
            return False
        self._held[key] = current + 1
        return True

    async def release(self, key: str, limit: int | None) -> None:
        if limit is None:
            return
        self._held[key] = max(0, self._held.get(key, 0) - 1)

    def held(self, key: str) -> int:
        return self._held.get(key, 0)


class RedisRateLimiter:
    """固定窗口计数器。窗口边界会有最多一个窗口的突发，换取 O(1) 的开销。"""

    def __init__(self, redis: object, fallback: MemoryRateLimiter | None = None) -> None:
        self.redis = redis
        self.fallback = fallback or MemoryRateLimiter()

    async def allow(
        self, clock: Clock, key: str, limit: int | None, *, cost: int = 1, window_seconds: int = 60
    ) -> bool:
        if limit is None:
            return True
        bucket = int(clock.now().timestamp()) // window_seconds
        redis_key = f"forge:rl:{key}:{bucket}"
        try:
            pipe = self.redis.pipeline()  # type: ignore[attr-defined]
            pipe.incrby(redis_key, cost)
            pipe.expire(redis_key, window_seconds + 5)
            used, _ = await pipe.execute()
            return int(used) <= limit
        except Exception:  # noqa: BLE001 - Redis 故障时必须降级而不是全站 500
            return await self.fallback.allow(
                clock, key, limit, cost=cost, window_seconds=window_seconds
            )


class RedisSlots:
    """带 TTL 的并发计数。进程崩溃不会永久占坑（120 秒后自动过期）。"""

    def __init__(self, redis: object, fallback: MemorySlots | None = None) -> None:
        self.redis = redis
        self.fallback = fallback or MemorySlots()

    async def acquire(self, key: str, limit: int | None) -> bool:
        if limit is None:
            return True
        redis_key = f"forge:slot:{key}"
        try:
            current = int(await self.redis.incr(redis_key))  # type: ignore[attr-defined]
            await self.redis.expire(redis_key, 120)  # type: ignore[attr-defined]
            if current > limit:
                await self.redis.decr(redis_key)  # type: ignore[attr-defined]
                return False
            return True
        except Exception:  # noqa: BLE001
            return await self.fallback.acquire(key, limit)

    async def release(self, key: str, limit: int | None) -> None:
        if limit is None:
            return
        redis_key = f"forge:slot:{key}"
        try:
            remaining = int(await self.redis.decr(redis_key))  # type: ignore[attr-defined]
            if remaining < 0:
                await self.redis.set(redis_key, 0)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            await self.fallback.release(key, limit)

    def held(self, key: str) -> int:
        return 0
