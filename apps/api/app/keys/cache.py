"""密钥校验缓存。吊销会立刻删除；删不掉时最多保留 30 秒。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol

from app.core.clock import Clock

CACHE_TTL_SECONDS = 30


class KeyCache(Protocol):
    async def get(self, key: str) -> str | None:
        """读取缓存值。过期或不存在时返回 None。"""

    async def set(self, key: str, value: str) -> None:
        """写入缓存，有效期不超过 30 秒。"""

    async def delete(self, key: str) -> None:
        """立刻删除缓存。"""


class MemoryKeyCache:
    def __init__(self, clock: Clock, ttl_seconds: int = CACHE_TTL_SECONDS) -> None:
        self.clock = clock
        self.ttl_seconds = ttl_seconds
        self._items: dict[str, tuple[datetime, str]] = {}

    async def get(self, key: str) -> str | None:
        item = self._items.get(key)
        if item is None:
            return None
        expires_at, value = item
        if self.clock.now() >= expires_at:
            self._items.pop(key, None)
            return None
        return value

    async def set(self, key: str, value: str) -> None:
        self._items[key] = (self.clock.now() + timedelta(seconds=self.ttl_seconds), value)

    async def delete(self, key: str) -> None:
        self._items.pop(key, None)
