"""就绪探针。财务状态不以 Redis 为准；此处只判断进程能否连上依赖。"""

from __future__ import annotations

from typing import Protocol

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


class ReadinessProbes(Protocol):
    async def postgres(self) -> tuple[bool, str]:
        """返回 (是否可用, 对外状态词)。状态词不得包含连接串。"""

    async def redis(self) -> tuple[bool, str]:
        """返回 (是否可用, 对外状态词)。"""


class DefaultProbes:
    def __init__(self, engine: AsyncEngine, redis: Redis) -> None:
        self._engine = engine
        self._redis = redis

    async def postgres(self) -> tuple[bool, str]:
        try:
            async with self._engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except Exception:
            return False, "unavailable"
        return True, "ok"

    async def redis(self) -> tuple[bool, str]:
        try:
            pong = await self._redis.ping()
        except Exception:
            return False, "unavailable"
        return (True, "ok") if pong else (False, "unavailable")


class StaticProbes:
    """测试用探针，不访问网络。"""

    def __init__(self, postgres_ok: bool, redis_ok: bool) -> None:
        self._postgres_ok = postgres_ok
        self._redis_ok = redis_ok

    async def postgres(self) -> tuple[bool, str]:
        return self._postgres_ok, "ok" if self._postgres_ok else "unavailable"

    async def redis(self) -> tuple[bool, str]:
        return self._redis_ok, "ok" if self._redis_ok else "unavailable"
