"""Prometheus scrape endpoint. Bearer-protected when METRICS_TOKEN is set (mandatory in
production). Gauges that describe stored state are sampled right before rendering."""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Request, Response

from app.core import metrics
from app.core.config import get_settings
from app.core.exceptions import Unauthorized

router = APIRouter(tags=["observability"])


async def _sample_queue_depth() -> None:
    from app.core.kv import get_redis

    depth = await get_redis().zcard("arq:queue")
    metrics.queue_depth.set(int(depth))


async def _sample_connections() -> None:
    from sqlalchemy import func, select

    from app.db.session import get_session_factory
    from app.models.integration import UserConnection

    async with get_session_factory()() as db:
        rows = await db.execute(
            select(UserConnection.provider, UserConnection.status, func.count()).group_by(
                UserConnection.provider, UserConnection.status
            )
        )
        seen: set[tuple[str, str]] = set()
        for provider, status, count in rows.all():
            metrics.connections_by_status.labels(provider, status.value).set(int(count))
            seen.add((provider, status.value))
        # Zero out combinations that disappeared so stale values don't linger between scrapes.
        for labels in list(metrics.connections_by_status._metrics):  # noqa: SLF001
            if tuple(labels) not in seen:
                metrics.connections_by_status.labels(*labels).set(0)


metrics.register_sampler(_sample_queue_depth)
metrics.register_sampler(_sample_connections)


@router.get("/metrics", include_in_schema=False)
async def scrape(request: Request) -> Response:
    token = get_settings().metrics_token
    if token:
        presented = request.headers.get("authorization", "")
        if not (
            presented.startswith("Bearer ")
            and hmac.compare_digest(presented.removeprefix("Bearer ").strip(), token)
        ):
            raise Unauthorized()
    await metrics.sample()
    body, content_type = metrics.render()
    return Response(body, media_type=content_type, headers={"Cache-Control": "no-store"})
