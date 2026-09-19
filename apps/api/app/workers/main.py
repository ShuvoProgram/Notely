"""ARQ worker entrypoint. Run with: `arq app.workers.main.WorkerSettings`."""

from __future__ import annotations

from typing import Any

from arq.connections import RedisSettings
from arq.cron import cron

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import dispose_engine
from app.workers.jobs.cleanup import cleanup_expired_sessions, purge_trashed_notes


async def startup(_: dict[str, Any]) -> None:
    configure_logging(get_settings().log_level)


async def shutdown(_: dict[str, Any]) -> None:
    await dispose_engine()


class WorkerSettings:
    functions: list[Any] = []
    cron_jobs = [
        cron(cleanup_expired_sessions, hour=None, minute=17, run_at_startup=True),  # type: ignore[arg-type]
        cron(purge_trashed_notes, hour=3, minute=30),  # type: ignore[arg-type]
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 10
    job_timeout = 300
