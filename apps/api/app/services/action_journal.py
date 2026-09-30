"""Capture side of the change journal (see app.models.journal).

A batch context is opened around every AI tool execution and every automation step:

    with action_journal.batch("ai_run", run.id, user, source_ref=call_id):
        await tool(...)

While it is open, the services that change data call `record(...)` with before/after state.
Outside a batch (someone editing in the UI) nothing is journaled — those edits have their own
undo and version history. Connector writes are recorded by `record_tool_call`, using the revert
hooks each connector tool declares.
"""

from __future__ import annotations

import contextlib
import itertools
import uuid
from collections.abc import Iterator
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.models.journal import ActionRecord

if TYPE_CHECKING:
    from app.ai.tools.base import ToolSpec
    from app.models.note import Note
    from app.models.task import Task
    from app.models.user import User


@dataclass(frozen=True)
class BatchContext:
    kind: str
    batch_id: uuid.UUID
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    source_ref: str | None


_current: ContextVar[BatchContext | None] = ContextVar("action_batch", default=None)
_sequence = itertools.count(1)

DEFAULT_IRREVERSIBLE = "This app offers no reliable way to undo this action automatically."


@contextlib.contextmanager
def batch(
    kind: str, batch_id: uuid.UUID, user: User, *, source_ref: str | None = None
) -> Iterator[BatchContext]:
    ctx = BatchContext(
        kind=kind,
        batch_id=batch_id,
        user_id=user.id,
        tenant_id=user.tenant_id,
        source_ref=source_ref,
    )
    token = _current.set(ctx)
    try:
        yield ctx
    finally:
        _current.reset(token)


def current() -> BatchContext | None:
    return _current.get()


def record(
    db: AsyncSession,
    *,
    kind: str,
    resource_type: str,
    resource_id: uuid.UUID | str | None,
    label: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    reversible: bool = True,
    irreversible_reason: str | None = None,
    revert_ref: dict[str, Any] | None = None,
    provider: str = "notely",
) -> ActionRecord | None:
    """Journal one change if a batch is open; a no-op otherwise."""
    ctx = _current.get()
    if ctx is None:
        return None
    row = ActionRecord(
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        batch_kind=ctx.kind,
        batch_id=ctx.batch_id,
        sequence=next(_sequence),
        source_ref=ctx.source_ref,
        provider=provider,
        kind=kind,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        label=label[:300],
        before=before,
        after=after,
        revert_ref=revert_ref,
        reversible=reversible,
        irreversible_reason=None if reversible else (irreversible_reason or DEFAULT_IRREVERSIBLE),
        status="applied",
        revert_attempts=0,
        created_at=utcnow(),
    )
    db.add(row)
    return row


def record_tool_call(db: AsyncSession, spec: ToolSpec, args: Any, result: dict[str, Any]) -> None:
    """Journal a successful write by a connected-app tool. Notely's own tools are journaled
    by the services they call, so they're skipped here (no double entries)."""
    from app.models.ai import RiskLevel

    if spec.provider == "notely" or spec.risk == RiskLevel.read or _current.get() is None:
        return
    ref: dict[str, Any] | None = None
    if spec.revert is not None and spec.revert_ref is not None:
        try:
            ref = spec.revert_ref(args, result)
        except Exception:  # noqa: BLE001 — an unexpected result shape means "can't undo"
            ref = None
    try:
        label = spec.summarize(args)
    except Exception:  # noqa: BLE001
        label = spec.name
    tool = spec.name.split("__", 1)[-1]
    record(
        db,
        provider=spec.provider,
        kind=f"{spec.provider}.{tool}",
        resource_type=tool,
        resource_id=next(iter(ref.values()), None) if ref else None,
        label=label,
        revert_ref={"tool": spec.name, **ref} if ref else None,
        reversible=ref is not None,
        irreversible_reason=spec.irreversible or DEFAULT_IRREVERSIBLE,
    )


# --- snapshots -----------------------------------------------------------------------------------


def _iso(value: date | time | datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def task_snapshot(task: Task) -> dict[str, Any]:
    return {
        "title": task.title,
        "description": task.description,
        "due_date": _iso(task.due_date),
        "due_time": _iso(task.due_time),
        "priority": task.priority.value,
        "status": task.status.value,
        "note_id": str(task.note_id) if task.note_id else None,
    }


def note_snapshot(note: Note) -> dict[str, Any]:
    return {
        "title": note.title,
        "content_json": note.content_json,
        "folder_id": str(note.folder_id) if note.folder_id else None,
        "color": note.color,
        "is_favorite": note.is_favorite,
        "archived_at": _iso(note.archived_at),
        "reminder_at": _iso(note.reminder_at),
        "version": note.version,
    }


def diff(before: dict[str, Any], after: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Only the fields that changed (version is kept as the concurrency marker)."""
    keys = [k for k in after if k != "version" and before.get(k) != after.get(k)]
    b = {k: before.get(k) for k in keys}
    a = {k: after.get(k) for k in keys}
    if "version" in after:
        b["version"], a["version"] = before.get("version"), after["version"]
    return b, a
