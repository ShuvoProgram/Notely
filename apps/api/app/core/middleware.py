"""HTTP middleware: request ids, access logging, CSRF origin enforcement, security headers."""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import Settings
from app.core.exceptions import error_response
from app.core.logging import get_logger

log = get_logger("access")

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = request_id
        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        log.info(
            "request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
                "user_id": getattr(request.state, "user_id", None),
            },
        )
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cache-Control", "no-store")
        return response


class CSRFOriginMiddleware(BaseHTTPMiddleware):
    """Reject state-changing requests that a browser attributes to a foreign site.

    Browsers attach `Origin` to every cross-site unsafe request and `Sec-Fetch-Site` to all
    fetches. Combined with `SameSite=Lax` session cookies this defeats CSRF without per-form
    tokens. The OAuth callback is a top-level GET navigation and is unaffected.
    """

    def __init__(self, app: object, settings: Settings) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.allowed = set(settings.allowed_origins) | {
            settings.frontend_origin,
            settings.api_public_url,
        }

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.method in UNSAFE_METHODS:
            origin = request.headers.get("origin")
            if origin is not None and origin != "null" and origin not in self.allowed:
                return error_response(403, "CSRF_ORIGIN_REJECTED", "Request origin not allowed.")
            if origin == "null" or request.headers.get("sec-fetch-site") == "cross-site":
                return error_response(403, "CSRF_ORIGIN_REJECTED", "Request origin not allowed.")
        return await call_next(request)
