"""Wrap job coroutines so every outcome and duration is measured (PRD 51: job failures).
ARQ's hooks don't receive the function name or exception, hence a decorator."""

from __future__ import annotations

import functools
import time
from collections.abc import Awaitable, Callable
from typing import Any

from app.core import metrics


def instrumented[R](job: Callable[..., Awaitable[R]]) -> Callable[..., Awaitable[R]]:
    name = job.__name__

    @functools.wraps(job)
    async def run(ctx: dict[str, Any], *args: Any, **kwargs: Any) -> R:
        started = time.perf_counter()
        try:
            result = await job(ctx, *args, **kwargs)
        except BaseException:
            metrics.jobs.labels(name, "failed").inc()
            metrics.job_latency.labels(name).observe(time.perf_counter() - started)
            raise
        metrics.jobs.labels(name, "completed").inc()
        metrics.job_latency.labels(name).observe(time.perf_counter() - started)
        return result

    return run
