"""HTTP client for provider adapters: bearer auth, timeouts, categorised errors and retries
with exponential backoff + jitter for retryable failures only (PRD section 35)."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Callable
from typing import Any

import httpx

from app.core import metrics
from app.core.logging import get_logger
from app.integrations.base.errors import ProviderError, ProviderErrorKind, classify_http_status

log = get_logger(__name__)

DEFAULT_TIMEOUT = 20.0
MAX_ATTEMPTS = 3
BASE_DELAY = 0.5

# Tests install a factory returning an httpx MockTransport per provider id.
TransportFactory = Callable[[str], httpx.AsyncBaseTransport | None]
_transport_override: TransportFactory | None = None


def set_transport_override(factory: TransportFactory | None) -> None:
    global _transport_override
    _transport_override = factory


def transport_for(provider: str) -> httpx.AsyncBaseTransport | None:
    return _transport_override(provider) if _transport_override else None


class ProviderHttpClient:
    def __init__(
        self,
        *,
        provider: str,
        base_url: str = "",
        bearer_token: str | None = None,
        headers: dict[str, str] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_attempts: int = MAX_ATTEMPTS,
    ) -> None:
        self.provider = provider
        self.max_attempts = max_attempts
        merged = {"Accept": "application/json", **(headers or {})}
        if bearer_token:
            merged["Authorization"] = f"Bearer {bearer_token}"
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers=merged,
            timeout=timeout,
            transport=transport or transport_for(provider),
        )

    async def __aenter__(self) -> ProviderHttpClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._client.aclose()

    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        attempt = 0
        while True:
            attempt += 1
            try:
                with metrics.Timer() as timer:
                    response = await self._client.request(method, url, **kwargs)
                metrics.provider_latency.labels(self.provider, method.upper()).observe(
                    timer.seconds
                )
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                metrics.provider_errors.labels(self.provider, "unavailable").inc()
                error = ProviderError(
                    ProviderErrorKind.unavailable, type(exc).__name__, provider=self.provider
                )
                if attempt >= self.max_attempts:
                    raise error from exc
                await self._backoff(attempt, None)
                continue
            if response.status_code < 400:
                return response
            error = classify_http_status(
                response.status_code, provider=self.provider, body_hint=response.text[:500]
            )
            metrics.provider_errors.labels(self.provider, error.kind.value).inc()
            retry_after = _retry_after_seconds(response)
            error.retry_after = retry_after
            if error.retryable and attempt < self.max_attempts:
                await self._backoff(attempt, retry_after)
                continue
            raise error

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", url, **kwargs)

    async def _backoff(self, attempt: int, retry_after: float | None) -> None:
        delay = retry_after if retry_after is not None else BASE_DELAY * (2 ** (attempt - 1))
        delay = min(delay, 10.0) + random.uniform(0, 0.25)  # noqa: S311 — jitter, not security
        log.info(
            "provider_retry",
            extra={"provider": self.provider, "attempt": attempt, "delay": round(delay, 2)},
        )
        await asyncio.sleep(delay)


def _retry_after_seconds(response: httpx.Response) -> float | None:
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None
