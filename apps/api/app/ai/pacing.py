"""Pacing model calls so concurrent conversations share a provider key instead of tripping it.

Every conversation runs independently, but they all spend the same key's quota. A burst (three
conversations generating at once, each making several calls for tool use) easily exceeds a
free-tier key's per-minute limit, and before this each 429 failed its run outright.

  - `model_slot(key)`: at most N model calls in flight per provider key (per process). Extra
    calls wait their turn; nothing fails for being concurrent.
  - `retry_delay(exc, attempt)`: for rate-limit / overload errors, how long to wait before trying
    again (the provider's own "retry in Ns" when it says so, else exponential backoff).
"""

from __future__ import annotations

import asyncio
import hashlib
import re

from app.ai.byo import BYOModel

# A user's own key is usually a small quota; the workspace gateway balances across keys itself.
BYO_CONCURRENCY = 2
GATEWAY_CONCURRENCY = 16
RATE_LIMIT_RETRIES = 4
MAX_WAIT_SECONDS = 30.0

_slots: dict[str, asyncio.Semaphore] = {}


def slot_key(byo: BYOModel | None) -> tuple[str, int]:
    """Which shared budget a run's model calls draw on, and how wide it is."""
    if byo is None:
        return "gateway", GATEWAY_CONCURRENCY
    digest = hashlib.sha256(f"{byo.provider.value}:{byo.api_key}".encode()).hexdigest()[:16]
    return f"byo:{digest}", BYO_CONCURRENCY


def model_slot(key: str, limit: int) -> asyncio.Semaphore:
    slot = _slots.get(key)
    if slot is None:
        slot = _slots[key] = asyncio.Semaphore(limit)
    return slot


def is_transient(exc: BaseException) -> bool:
    """Rate limited, out of short-term quota, or overloaded: worth waiting and trying again."""
    status = getattr(exc, "status_code", None) or getattr(
        getattr(exc, "response", None), "status_code", None
    )
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    if status in (429, 500, 502, 503, 504):
        return True
    return (
        "ratelimit" in name
        or "resource_exhausted" in text
        or "rate limit" in text
        or "overloaded" in text
        or "unavailable" in text
        or "try again later" in text
    )


_RETRY_HINT = re.compile(
    r"retry(?:[ _-]?delay|[ _-]?after| in)?\W{0,6}(\d+(?:\.\d+)?)\s*s", re.IGNORECASE
)


def retry_delay(exc: BaseException, attempt: int) -> float:
    """Seconds to wait before attempt `attempt + 1`."""
    hinted: float | None = None
    headers = getattr(getattr(exc, "response", None), "headers", None)
    if headers is not None:
        try:
            hinted = float(headers.get("retry-after"))
        except (TypeError, ValueError):
            hinted = None
    if hinted is None and (match := _RETRY_HINT.search(str(exc))):
        hinted = float(match.group(1))
    delay = hinted if hinted is not None else 2.0 * (2**attempt)
    return max(1.0, min(delay + 0.5, MAX_WAIT_SECONDS))
