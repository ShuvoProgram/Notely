"""Unified search: Notely notes plus every usable connection, queried concurrently.

Provider failures never fail the search; they are reported per source so the UI can say
"Slack didn't respond" instead of silently dropping results."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.logging import get_logger
from app.integrations.base.errors import ProviderError
from app.integrations.registry import get_provider
from app.models.user import User
from app.services.connection_service import ConnectionService
from app.services.note_service import NoteService
from app.services.rich_text import excerpt

log = get_logger(__name__)

PROVIDER_TIMEOUT = 6.0


@dataclass
class UnifiedHit:
    source: str
    kind: str
    id: str
    title: str
    snippet: str
    url: str | None
    score: float
    updated_at: str | None


@dataclass
class SourceStatus:
    source: str
    ok: bool
    count: int = 0
    error: str | None = None


@dataclass
class UnifiedSearchResult:
    query: str
    hits: list[UnifiedHit] = field(default_factory=list)
    sources: list[SourceStatus] = field(default_factory=list)


class UnifiedSearchService:
    def __init__(self, db: AsyncSession, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    async def search(self, user: User, q: str, limit: int = 20) -> UnifiedSearchResult:
        result = UnifiedSearchResult(query=q)
        rows = await NoteService(self.db).search(user, q, limit)
        for row in rows:
            result.hits.append(
                UnifiedHit(
                    source="notely",
                    kind="note",
                    id=str(row.note.id),
                    title=row.note.title or "Untitled",
                    snippet=excerpt(row.note.plain_text, 200),
                    url=f"/app/notes/{row.note.id}",
                    score=row.score,
                    updated_at=row.note.updated_at.isoformat(),
                )
            )
        result.sources.append(SourceStatus("notely", True, len(rows)))

        connections = ConnectionService(self.db, self.settings)
        usable = await connections.list_usable(user)
        # Provider calls only need the connection + credentials; run them concurrently but keep
        # the shared DB session out of them (status updates happen afterwards, sequentially).
        contexts = [(conn, connections.context(user, conn)) for conn in usable]

        async def one(conn: Any, ctx: Any) -> tuple[Any, list[dict[str, Any]] | ProviderError]:
            provider = get_provider(conn.provider)
            if provider is None:
                return conn, []
            try:
                return conn, await asyncio.wait_for(
                    provider.search(ctx, q, limit), PROVIDER_TIMEOUT
                )
            except ProviderError as exc:
                return conn, exc
            except TimeoutError:
                from app.integrations.base.errors import ProviderErrorKind

                return conn, ProviderError(
                    ProviderErrorKind.unavailable, "timeout", provider=conn.provider
                )
            except Exception as exc:  # noqa: BLE001
                from app.integrations.base.errors import ProviderErrorKind

                log.exception("provider_search_failed", extra={"provider": conn.provider})
                return conn, ProviderError(
                    ProviderErrorKind.unknown, type(exc).__name__, provider=conn.provider
                )

        outcomes = await asyncio.gather(*(one(c, ctx) for c, ctx in contexts))
        for conn, outcome in outcomes:
            if isinstance(outcome, ProviderError):
                await connections.record_tool_failure(conn, outcome)
                result.sources.append(
                    SourceStatus(conn.provider, False, 0, outcome.user_message()[1])
                )
                continue
            for i, hit in enumerate(outcome):
                result.hits.append(
                    UnifiedHit(
                        source=conn.provider,
                        kind=str(hit.get("kind") or "item"),
                        id=str(hit.get("id") or ""),
                        title=str(hit.get("title") or "Untitled"),
                        snippet=str(hit.get("snippet") or "")[:240],
                        url=hit.get("url"),
                        score=max(0.05, 0.5 - i * 0.02),  # providers rank; we only preserve order
                        updated_at=hit.get("updated_at"),
                    )
                )
            result.sources.append(SourceStatus(conn.provider, True, len(outcome)))
        return result
