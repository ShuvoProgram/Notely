"""HTTP middleware: request ids, access logging, CSRF origin enforcement, security headers."""

from __future__ import annotations

import re
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core import metrics
from app.core.config import Settings
from app.core.exceptions import error_response
from app.core.logging import get_logger, request_id_var, user_id_var

log = get_logger("access")

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def route_template(request: Request) -> str:
    """The matched route as a template (`/api/v1/notes/{note_id}`) so metric labels stay
    bounded: every path parameter value is replaced by its name."""
    if request.scope.get("route") is None:
        return "unmatched"
    segments = request.url.path.split("/")
    by_value = {str(v): k for k, v in request.path_params.items()}
    return "/".join(f"{{{by_value[seg]}}}" if seg in by_value else seg for seg in segments)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = request_id
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
            user_id_var.set(None)
        duration = time.perf_counter() - started
        response.headers["X-Request-ID"] = request_id
        route = route_template(request)
        if route != "unmatched" and not route.startswith("/metrics"):
            metrics.http_requests.labels(
                request.method, route, metrics.status_class(response.status_code)
            ).inc()
            metrics.http_latency.labels(request.method, route).observe(duration)
            if response.status_code >= 500:
                metrics.http_errors.labels(route).inc()
        log.info(
            "request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "route": route,
                "status": response.status_code,
                "duration_ms": round(duration * 1000, 2),
                "user_id": getattr(request.state, "user_id", None),
            },
        )
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Defensive headers for a JSON API. HSTS is only meaningful (and safe) over TLS, so it is
    sent when the deployment runs with secure cookies (always true in production)."""

    def __init__(self, app: object, settings: Settings) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.hsts = settings.cookie_secure

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        # The API never serves HTML; a restrictive CSP still blocks any accidental rendering.
        response.headers.setdefault(
            "Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'"
        )
        if self.hsts:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=63072000; includeSubDomains"
            )
        return response


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject oversized bodies up front (413) instead of parsing them. Streams are unaffected:
    only requests that declare a Content-Length are checked here; chunked uploads are capped
    by the route that reads them."""

    def __init__(self, app: object, settings: Settings) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.max_bytes = settings.max_request_bytes
        self.max_webhook_bytes = settings.max_webhook_bytes
        self.webhook_prefix = f"{settings.api_prefix}/webhooks/"
        # Profile pictures are the one multipart upload; the service caps and re-encodes them.
        self.avatar_path = f"{settings.api_prefix}/users/me/avatar"
        self.max_avatar_bytes = 5 * 1024 * 1024 + 64 * 1024  # 5 MB image + multipart framing

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        length = request.headers.get("content-length")
        if length and length.isdigit():
            path = request.url.path
            limit = (
                self.max_webhook_bytes
                if path.startswith(self.webhook_prefix)
                else self.max_avatar_bytes
                if path == self.avatar_path
                else self.max_bytes
            )
            if int(length) > limit:
                return error_response(
                    413,
                    "PAYLOAD_TOO_LARGE",
                    "The request body is too large.",
                    {"max_bytes": limit},
                )
        return await call_next(request)


_LOCAL_ORIGIN = re.compile(r"https?://(?:localhost|127\.0\.0\.1)(?::\d{1,5})?")


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
        # Local development only: the web app may start on another port when 3000 is taken
        # (Next.js moves to 3001), so trust this machine on any port. Never in production.
        self.any_local_port = settings.environment == "development"

    def _allowed(self, origin: str) -> bool:
        return origin in self.allowed or (
            self.any_local_port and _LOCAL_ORIGIN.fullmatch(origin) is not None
        )

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.method in UNSAFE_METHODS:
            origin = request.headers.get("origin")
            if origin is not None and origin != "null" and not self._allowed(origin):
                return error_response(403, "CSRF_ORIGIN_REJECTED", "Request origin not allowed.")
            if origin == "null" or request.headers.get("sec-fetch-site") == "cross-site":
                return error_response(403, "CSRF_ORIGIN_REJECTED", "Request origin not allowed.")
        return await call_next(request)
