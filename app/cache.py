"""Hot-path cache for code → link lookups, plus a fixed-window rate limiter.

Both have a Redis implementation for production and an in-memory one for
tests and single-process runs; the app only sees the `Cache` protocol.
"""

import json
import time
from typing import Any, Protocol

from redis.asyncio import Redis


class Cache(Protocol):
    async def get(self, code: str) -> dict[str, Any] | None: ...
    async def set(self, code: str, value: dict[str, Any], ttl: int) -> None: ...
    async def delete(self, code: str) -> None: ...
    async def allow(self, key: str, limit: int, window: int) -> bool: ...
    async def close(self) -> None: ...


class MemoryCache:
    def __init__(self) -> None:
        self._values: dict[str, tuple[float, dict[str, Any]]] = {}
        self._windows: dict[str, tuple[int, int]] = {}

    async def get(self, code: str) -> dict[str, Any] | None:
        hit = self._values.get(code)
        if hit is None or hit[0] < time.monotonic():
            self._values.pop(code, None)
            return None
        return hit[1]

    async def set(self, code: str, value: dict[str, Any], ttl: int) -> None:
        self._values[code] = (time.monotonic() + ttl, value)

    async def delete(self, code: str) -> None:
        self._values.pop(code, None)

    async def allow(self, key: str, limit: int, window: int) -> bool:
        slot = int(time.time() // window)
        current_slot, count = self._windows.get(key, (slot, 0))
        if current_slot != slot:
            count = 0
        self._windows[key] = (slot, count + 1)
        return count + 1 <= limit

    async def close(self) -> None:
        pass


class RedisCache:
    def __init__(self, url: str) -> None:
        self._redis = Redis.from_url(url, decode_responses=True)

    async def get(self, code: str) -> dict[str, Any] | None:
        raw = await self._redis.get(f"link:{code}")
        return json.loads(raw) if raw else None

    async def set(self, code: str, value: dict[str, Any], ttl: int) -> None:
        await self._redis.set(f"link:{code}", json.dumps(value), ex=ttl)

    async def delete(self, code: str) -> None:
        await self._redis.delete(f"link:{code}")

    async def allow(self, key: str, limit: int, window: int) -> bool:
        bucket = f"rate:{key}:{int(time.time() // window)}"
        async with self._redis.pipeline(transaction=True) as pipe:
            count, _ = await pipe.incr(bucket).expire(bucket, window).execute()
        return int(count) <= limit

    async def close(self) -> None:
        await self._redis.aclose()


def make_cache(redis_url: str) -> Cache:
    return RedisCache(redis_url) if redis_url else MemoryCache()
