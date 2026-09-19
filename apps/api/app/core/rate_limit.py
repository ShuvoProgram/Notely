"""Fixed-window rate limiting keyed by route scope + client identity (user id or IP)."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from fastapi import Request

from app.core.config import Settings, get_settings
from app.core.exceptions import RateLimited
from app.core.kv import kv


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


LimitSpec = int | Callable[[Settings], int] | None


def rate_limit(scope: str, per_minute: LimitSpec = None) -> Callable[[Request], Awaitable[None]]:
    """FastAPI dependency factory.

    `per_minute` may be a number, a function of Settings (so limits stay configurable), or None
    for the default limit.
    Usage: `Depends(rate_limit("auth", lambda s: s.rate_limit_auth_per_minute))`.
    """

    async def _dependency(request: Request) -> None:
        settings = get_settings()
        if not settings.rate_limit_enabled:
            return
        if callable(per_minute):
            limit = per_minute(settings)
        else:
            limit = per_minute or settings.rate_limit_default_per_minute
        window = 60
        now = time.time()
        bucket = int(now // window)
        identity = getattr(request.state, "user_id", None) or client_ip(request)
        key = f"rl:{scope}:{identity}:{bucket}"
        count = await kv.incr(key, window)
        if count > limit:
            retry_after = window - int(now % window)
            raise RateLimited(headers={"Retry-After": str(retry_after)})

    return _dependency
