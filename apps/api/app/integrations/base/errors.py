"""Provider error taxonomy. Adapters raise these; the framework maps them to connection status,
retry behaviour and the user-facing messages from the PRD (section 34)."""

from __future__ import annotations

import enum

from app.core.exceptions import APIError


class ProviderErrorKind(enum.StrEnum):
    auth_failed = "auth_failed"  # OAuth denied / invalid credentials
    expired = "expired"  # token expired and could not be refreshed
    admin_approval_required = "admin_approval_required"
    permission_denied = "permission_denied"  # missing scope / forbidden
    rate_limited = "rate_limited"
    unavailable = "unavailable"  # 5xx, network, timeout
    invalid_request = "invalid_request"  # 4xx we caused
    not_found = "not_found"
    misconfigured = "misconfigured"  # provider not configured on this deployment
    unknown = "unknown"


RETRYABLE = {ProviderErrorKind.rate_limited, ProviderErrorKind.unavailable}

USER_MESSAGES: dict[ProviderErrorKind, tuple[str, str]] = {
    ProviderErrorKind.auth_failed: ("Authorization failed", "Your access wasn't granted."),
    ProviderErrorKind.expired: ("Your connection expired", "Reconnect to continue."),
    ProviderErrorKind.admin_approval_required: (
        "Administrator approval required",
        "Your organization requires an administrator to approve this app.",
    ),
    ProviderErrorKind.permission_denied: (
        "Permission denied",
        "Notely doesn't have permission to perform this action.",
    ),
    ProviderErrorKind.rate_limited: (
        "Temporarily rate-limited",
        "This service is temporarily rate-limited. We'll retry automatically.",
    ),
    ProviderErrorKind.unavailable: (
        "Service unavailable",
        "{provider} is temporarily unavailable.",
    ),
    ProviderErrorKind.invalid_request: (
        "This action couldn't be completed",
        "Review the details and try again.",
    ),
    ProviderErrorKind.not_found: ("Not found", "That item no longer exists in {provider}."),
    ProviderErrorKind.misconfigured: (
        "Not available",
        "{provider} isn't configured on this Notely deployment yet.",
    ),
    ProviderErrorKind.unknown: (
        "This action couldn't be completed",
        "Review the details and try again.",
    ),
}


class ProviderError(Exception):
    def __init__(
        self,
        kind: ProviderErrorKind,
        detail: str | None = None,
        *,
        provider: str = "provider",
        retry_after: float | None = None,
    ) -> None:
        self.kind = kind
        self.detail = detail
        self.provider = provider
        self.retry_after = retry_after
        super().__init__(detail or kind.value)

    @property
    def retryable(self) -> bool:
        return self.kind in RETRYABLE

    def user_message(self) -> tuple[str, str]:
        title, body = USER_MESSAGES[self.kind]
        return title, body.format(provider=self.provider.title())

    def as_api_error(self) -> APIError:
        """The same categorised envelope the global handler produces (one mapping, see
        `app.core.exceptions.PROVIDER_STATUS`)."""
        from app.core.exceptions import PROVIDER_STATUS

        title, body = self.user_message()
        status = PROVIDER_STATUS.get(self.kind.value, 502)
        return APIError(
            body,
            code=f"PROVIDER_{self.kind.value.upper()}",
            status_code=status,
            details={"title": title, "provider": self.provider},
        )


def classify_http_status(
    status: int, *, provider: str, body_hint: str | None = None
) -> ProviderError:
    text = (body_hint or "").lower()
    if status == 401:
        kind = ProviderErrorKind.expired if "expired" in text else ProviderErrorKind.auth_failed
    elif status == 403:
        kind = (
            ProviderErrorKind.admin_approval_required
            if "admin" in text and "consent" in text
            else ProviderErrorKind.permission_denied
        )
    elif status == 404:
        kind = ProviderErrorKind.not_found
    elif status == 429:
        kind = ProviderErrorKind.rate_limited
    elif status in (502, 503, 504):
        kind = ProviderErrorKind.unavailable
    elif 400 <= status < 500:
        kind = ProviderErrorKind.invalid_request
    else:
        kind = ProviderErrorKind.unavailable
    return ProviderError(kind, f"HTTP {status}", provider=provider)
