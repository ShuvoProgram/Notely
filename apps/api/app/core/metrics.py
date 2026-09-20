"""Prometheus metrics (PRD 51). Labels are low-cardinality only: never user ids, never content.

Application: request latency/errors, DB query latency, queue depth, job outcomes.
AI: runs, latency, tokens, tool calls/failures, approval decisions.
Integrations: provider API latency, provider errors, OAuth failures, webhooks, connection status.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

registry = CollectorRegistry(auto_describe=True)

LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60)

# --- application --------------------------------------------------------------------------------

http_requests = Counter(
    "notely_http_requests_total",
    "HTTP requests by method, route template and status class",
    ["method", "route", "status"],
    registry=registry,
)
http_latency = Histogram(
    "notely_http_request_seconds",
    "HTTP request latency by route template",
    ["method", "route"],
    buckets=LATENCY_BUCKETS,
    registry=registry,
)
http_errors = Counter(
    "notely_http_errors_total",
    "Responses with status >= 500 (unhandled or upstream failures)",
    ["route"],
    registry=registry,
)
db_query_latency = Histogram(
    "notely_db_query_seconds",
    "Database statement latency by statement verb",
    ["verb"],
    buckets=LATENCY_BUCKETS,
    registry=registry,
)
queue_depth = Gauge(
    "notely_queue_depth", "Jobs waiting in the ARQ queue (sampled on scrape)", registry=registry
)
jobs = Counter("notely_jobs_total", "Background job outcomes", ["job", "status"], registry=registry)
job_latency = Histogram(
    "notely_job_seconds",
    "Background job duration",
    ["job"],
    buckets=LATENCY_BUCKETS,
    registry=registry,
)

# --- AI -----------------------------------------------------------------------------------------

ai_runs = Counter(
    "notely_ai_runs_total",
    "Agent runs by model and final status",
    ["model", "status"],
    registry=registry,
)
ai_run_latency = Histogram(
    "notely_ai_run_seconds",
    "Wall-clock time of one agent drive (start or resume until pause/finish)",
    ["model"],
    buckets=LATENCY_BUCKETS,
    registry=registry,
)
ai_tokens = Counter(
    "notely_ai_tokens_total",
    "Tokens by model and direction",
    ["model", "direction"],
    registry=registry,
)
ai_tool_calls = Counter(
    "notely_ai_tool_calls_total",
    "Tool executions by provider, tool and outcome",
    ["provider", "tool", "status"],
    registry=registry,
)
ai_approvals = Counter(
    "notely_ai_approvals_total",
    "Approval decisions (per proposed call)",
    ["decision"],
    registry=registry,
)
ai_verifications = Counter(
    "notely_ai_verifications_total",
    "Post-write read-back outcomes",
    ["provider", "status"],
    registry=registry,
)

# --- integrations ---------------------------------------------------------------------------------

provider_latency = Histogram(
    "notely_provider_request_seconds",
    "Outbound provider API latency",
    ["provider", "method"],
    buckets=LATENCY_BUCKETS,
    registry=registry,
)
provider_errors = Counter(
    "notely_provider_errors_total",
    "Provider errors by kind (rate_limited, unavailable, expired, ...)",
    ["provider", "kind"],
    registry=registry,
)
oauth_failures = Counter(
    "notely_oauth_failures_total", "OAuth flow failures", ["provider", "stage"], registry=registry
)
webhooks = Counter(
    "notely_webhooks_total", "Webhook deliveries", ["provider", "outcome"], registry=registry
)
connections_by_status = Gauge(
    "notely_connections",
    "User connections by provider and status (sampled on scrape)",
    ["provider", "status"],
    registry=registry,
)


class Timer:
    """`with Timer() as t: ...; t.seconds`"""

    def __enter__(self) -> Timer:
        self._start = time.perf_counter()
        return self

    def __exit__(self, *exc: object) -> None:
        self.seconds = time.perf_counter() - self._start


def status_class(status_code: int) -> str:
    return f"{status_code // 100}xx"


def render() -> tuple[bytes, str]:
    return generate_latest(registry), CONTENT_TYPE_LATEST


# Optional samplers run right before a scrape (queue depth, connection gauges). Registered by
# the modules that own the data so this module stays dependency-free.
_samplers: list[Callable[[], Any]] = []


def register_sampler(fn: Callable[[], Any]) -> None:
    _samplers.append(fn)


async def sample() -> None:
    import inspect

    for fn in _samplers:
        try:
            result = fn()
            if inspect.isawaitable(result):
                await result
        except Exception:  # noqa: BLE001 — a failing sampler must not break scraping
            pass
