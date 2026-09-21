"""Typed application errors and the {error: {code, message, details}} envelope."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger

log = get_logger(__name__)


class APIError(Exception):
    """Base class for errors that are safe to surface to clients."""

    status_code: int = 400
    code: str = "BAD_REQUEST"
    message: str = "The request could not be completed."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.status_code = status_code or self.status_code
        self.details = details or {}
        self.headers = headers
        super().__init__(self.message)


class ValidationFailed(APIError):
    status_code = 422
    code = "VALIDATION_ERROR"
    message = "Some fields are invalid."


class Unauthorized(APIError):
    status_code = 401
    code = "UNAUTHORIZED"
    message = "You need to sign in to continue."


class Forbidden(APIError):
    status_code = 403
    code = "FORBIDDEN"
    message = "You don't have access to this resource."


class NotFound(APIError):
    status_code = 404
    code = "NOT_FOUND"
    message = "The requested resource was not found."


class Conflict(APIError):
    status_code = 409
    code = "CONFLICT"
    message = "This action conflicts with the current state."


class RateLimited(APIError):
    status_code = 429
    code = "RATE_LIMITED"
    message = "Too many requests. Please try again shortly."


class ProviderNotConfigured(APIError):
    status_code = 404
    code = "PROVIDER_NOT_CONFIGURED"
    message = "This sign-in provider is not available."


class InvalidOAuthState(APIError):
    status_code = 400
    code = "OAUTH_STATE_INVALID"
    message = "The sign-in request expired or was tampered with. Please try again."


class OAuthExchangeFailed(APIError):
    status_code = 502
    code = "OAUTH_EXCHANGE_FAILED"
    message = "Authorization failed. Your access wasn't granted."

    def __init__(
        self,
        message: str | None = None,
        *,
        oauth_error: str | None = None,
        transient: bool = False,
    ) -> None:
        super().__init__(message)
        # The vendor's `error` code ("invalid_grant", "invalid_client", …) when it sent one, and
        # whether the failure was the network/vendor being down rather than a verdict on the
        # grant. Refresh logic needs the difference: only a rejected grant means "reconnect".
        self.oauth_error = oauth_error
        self.transient = transient

    @property
    def grant_rejected(self) -> bool:
        return self.oauth_error in ("invalid_grant", "invalid_token", "unauthorized_client")


# HTTP status per provider error kind (see integrations/base/errors.py).
PROVIDER_STATUS: dict[str, int] = {
    "auth_failed": 401,
    "expired": 409,
    "admin_approval_required": 403,
    "permission_denied": 403,
    "rate_limited": 429,
    "unavailable": 503,
    "invalid_request": 400,
    "not_found": 404,
    "misconfigured": 503,
    "unknown": 502,
}


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": details or {}}},
        headers=headers,
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(APIError)
    async def _api_error(_: Request, exc: APIError) -> JSONResponse:
        return error_response(exc.status_code, exc.code, exc.message, exc.details, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields: dict[str, list[str]] = {}
        for err in exc.errors():
            loc = ".".join(str(p) for p in err.get("loc", []) if p not in ("body", "query"))
            fields.setdefault(loc or "_", []).append(str(err.get("msg", "Invalid value")))
        return error_response(
            422, "VALIDATION_ERROR", "Some fields are invalid.", {"fields": fields}
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
            429: "RATE_LIMITED",
        }.get(exc.status_code, "HTTP_ERROR")
        message = (
            exc.detail if isinstance(exc.detail, str) else "The request could not be completed."
        )
        return error_response(
            exc.status_code, code, message, headers=dict(exc.headers) if exc.headers else None
        )

    from app.integrations.base.errors import ProviderError

    @app.exception_handler(ProviderError)
    async def _provider_error(_: Request, exc: ProviderError) -> JSONResponse:
        # One mapping for every route that touches a provider: categorised, never a traceback.
        title, body = exc.user_message()
        status = PROVIDER_STATUS.get(exc.kind.value, 502)
        headers = {"Retry-After": str(int(exc.retry_after))} if exc.retry_after else None
        return error_response(
            status,
            f"PROVIDER_{exc.kind.value.upper()}",
            body,
            {"title": title, "provider": exc.provider, "retryable": exc.retryable},
            headers,
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Never leak Python exception messages to clients.
        log.exception(
            "unhandled_error",
            extra={
                "path": request.url.path,
                "request_id": getattr(request.state, "request_id", None),
            },
        )
        return error_response(500, "INTERNAL_ERROR", "Something went wrong on our side.")
