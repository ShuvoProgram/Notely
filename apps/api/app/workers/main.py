"""ARQ worker entrypoint. Run with: `arq app.workers.main.WorkerSettings`."""

from __future__ import annotations

from typing import Any

from arq.connections import RedisSettings
from arq.cron import cron

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import dispose_engine
from app.workers.instrument import instrumented
from app.workers.jobs import automations, cleanup, integrations

cleanup_expired_sessions = instrumented(cleanup.cleanup_expired_sessions)
purge_trashed_notes = instrumented(cleanup.purge_trashed_notes)
check_connections = instrumented(integrations.check_connections)
process_webhook = instrumented(integrations.process_webhook)
refresh_oauth_tokens = instrumented(integrations.refresh_oauth_tokens)
sync_integration = instrumented(integrations.sync_integration)
run_due_automations = instrumented(automations.run_due_automations)
run_automation_execution = instrumented(automations.run_automation_execution)


async def startup(_: dict[str, Any]) -> None:
    configure_logging(get_settings().log_level)


async def shutdown(_: dict[str, Any]) -> None:
    await dispose_engine()


class WorkerSettings:
    functions: list[Any] = [process_webhook, sync_integration, run_automation_execution]
    cron_jobs = [
        cron(cleanup_expired_sessions, hour=None, minute=17, run_at_startup=True),  # type: ignore[arg-type]
        cron(purge_trashed_notes, hour=3, minute=30),  # type: ignore[arg-type]
        cron(check_connections, hour=None, minute={5, 35}),  # type: ignore[arg-type]
        cron(refresh_oauth_tokens, hour=None, minute=set(range(0, 60, 5))),  # type: ignore[arg-type]
        cron(run_due_automations, hour=None, minute=set(range(0, 60))),  # type: ignore[arg-type]
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 10
    job_timeout = 300
