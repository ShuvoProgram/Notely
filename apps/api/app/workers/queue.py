"""Job queue facade over ARQ (Redis). Requests only *enqueue*; workers do the work.

When Redis is unreachable (tests, local dev without Redis) jobs are recorded in memory so callers
and tests can still observe what would have been queued.
"""

from __future__ import annotations

from typing import Any

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

_pool: ArqRedis | None = None
_degraded = False
# Jobs captured while degraded: (function name, args)
captured_jobs: list[tuple[str, tuple[Any, ...]]] = []


def force_memory() -> None:
    global _degraded
    _degraded = True


def reset() -> None:
    global _degraded
    _degraded = False
    captured_jobs.clear()


async def _get_pool() -> ArqRedis:
    global _pool
    if _pool is None:
        _pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    return _pool


async def enqueue(function: str, *args: Any) -> str | None:
    global _degraded
    if not _degraded:
        try:
            job = await (await _get_pool()).enqueue_job(function, *args)
            return job.job_id if job else None
        except Exception as exc:  # noqa: BLE001 — connection problems
            _degraded = True
            log.warning("queue_redis_unavailable", extra={"reason": type(exc).__name__})
    captured_jobs.append((function, args))
    return None


async def close_queue() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None
