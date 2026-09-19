"""Small key/value abstraction over Redis with an in-process fallback.

Used for rate-limit counters and short-lived OAuth state. Falls back to memory when Redis is
unavailable (tests, local dev without Redis) and logs so it is never silent in production.
Redis is never a source of truth for permanent application data.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from redis.asyncio import Redis, from_url

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

_redis: Redis | None = None


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = from_url(get_settings().redis_url, decode_responses=True)  # type: ignore[no-untyped-call]
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


async def redis_healthy() -> bool:
    try:
        return bool(await get_redis().ping())
    except Exception:
        return False


class MemoryKV:
    def __init__(self) -> None:
        self._data: dict[str, tuple[str, float]] = {}
        self._lock = asyncio.Lock()

    def _purge(self) -> None:
        now = time.monotonic()
        for k in [k for k, (_, exp) in self._data.items() if exp <= now]:
            del self._data[k]

    async def set(self, key: str, value: str, ttl: int) -> None:
        async with self._lock:
            self._purge()
            self._data[key] = (value, time.monotonic() + ttl)

    async def get(self, key: str) -> str | None:
        async with self._lock:
            self._purge()
            item = self._data.get(key)
            return item[0] if item else None

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._data.pop(key, None)

    async def incr(self, key: str, ttl: int) -> int:
        async with self._lock:
            self._purge()
            value, exp = self._data.get(key, ("0", time.monotonic() + ttl))
            n = int(value) + 1
            self._data[key] = (str(n), exp)
            return n


class RedisKV:
    async def set(self, key: str, value: str, ttl: int) -> None:
        await get_redis().set(key, value, ex=ttl)

    async def get(self, key: str) -> str | None:
        return await get_redis().get(key)

    async def delete(self, key: str) -> None:
        await get_redis().delete(key)

    async def incr(self, key: str, ttl: int) -> int:
        r = get_redis()
        async with r.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, ttl, nx=True)
            n, _ = await pipe.execute()
        return int(n)


class KV:
    """Prefers Redis; degrades to memory on connection failure."""

    def __init__(self) -> None:
        self._redis = RedisKV()
        self._memory = MemoryKV()
        self._degraded = False

    @property
    def degraded(self) -> bool:
        return self._degraded

    def force_memory(self) -> None:
        self._degraded = True

    def reset(self) -> None:
        self._degraded = False
        self._memory = MemoryKV()

    async def _run(self, op: str, *args: Any) -> Any:
        if not self._degraded:
            try:
                return await getattr(self._redis, op)(*args)
            except Exception as exc:  # connection errors, timeouts
                self._degraded = True
                log.warning(
                    "kv_redis_unavailable_falling_back_to_memory",
                    extra={"reason": type(exc).__name__},
                )
        return await getattr(self._memory, op)(*args)

    async def set(self, key: str, value: str, ttl: int) -> None:
        await self._run("set", key, value, ttl)

    async def get(self, key: str) -> str | None:
        result: str | None = await self._run("get", key)
        return result

    async def delete(self, key: str) -> None:
        await self._run("delete", key)

    async def incr(self, key: str, ttl: int) -> int:
        result: int = await self._run("incr", key, ttl)
        return result


kv = KV()
