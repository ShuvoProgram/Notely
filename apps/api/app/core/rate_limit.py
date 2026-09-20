"""Fixed-window rate limiting (PRD 64) keyed by route scope + an identity.

Identities: `user` (session user id, falls back to IP when anonymous), `tenant`, `ip`, or
`provider` (the `{provider_id}` path parameter + IP, for webhooks). Counters live in Redis
(memory fallback) and expire with the window. Limits are configurable through Settings.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Literal

from fastapi import Request

from app.core.config import Settings, get_settings
from app.core.exceptions import RateLimited
from app.core.kv import kv

Identity = Literal["user", "tenant", "ip", "provider"]
LimitSpec = int | Callable[[Settings], int] | None
WINDOW_SECONDS = 60


def client_ip(request: Request) -> str:
    """The caller's IP. Forwarded headers are honoured only when the deployment says the app
    sits behind a trusted proxy — otherwise anyone could spoof their way past IP limits."""
    if get_settings().trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def identity_for(request: Request, key: Identity) -> str:
    if key == "ip":
        return client_ip(request)
    if key == "tenant":
        tenant = getattr(request.state, "tenant_id", None)
        return f"t:{tenant}" if tenant else client_ip(request)
    if key == "provider":
        provider = request.path_params.get("provider_id", "-")
        return f"{provider}:{client_ip(request)}"
    user = getattr(request.state, "user_id", None)
    return f"u:{user}" if user else client_ip(request)


def rate_limit(
    scope: str, per_minute: LimitSpec = None, *, key: Identity = "user"
) -> Callable[[Request], Awaitable[None]]:
    """FastAPI dependency factory.

    `per_minute` may be a number, a function of Settings (so limits stay configurable), or None
    for the default limit. Stack several `Depends(rate_limit(...))` to combine user + tenant +
    IP limits on one route.
    """

    async def _dependency(request: Request) -> None:
        settings = get_settings()
        if not settings.rate_limit_enabled:
            return
        if callable(per_minute):
            limit = per_minute(settings)
        else:
            limit = per_minute or settings.rate_limit_default_per_minute
        now = time.time()
        bucket = int(now // WINDOW_SECONDS)
        identity = identity_for(request, key)
        count = await kv.incr(f"rl:{scope}:{key}:{identity}:{bucket}", WINDOW_SECONDS)
        if count > limit:
            retry_after = WINDOW_SECONDS - int(now % WINDOW_SECONDS)
            raise RateLimited(headers={"Retry-After": str(retry_after)})

    return _dependency
