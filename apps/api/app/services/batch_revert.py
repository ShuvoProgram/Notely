"""Reverting a batch (one AI run or automation run) from the change journal.

Rules:
- The journal is the only source of truth: each row says what changed and how to undo it.
- Changes are undone newest-first, one at a time, each committed on its own, so a crash or a
  vendor error leaves an accurate record of what was and wasn't reverted.
- A change is only undone if the thing still looks the way the run left it. Anything edited
  since is left alone and reported ("changed since") — a revert never clobbers later work.
- Rows are never deleted: they are marked reverted / revert_skipped / revert_failed.
- `batch_reverts` has one row per batch (unique), so a second click can't run a revert twice;
  a partially failed revert can be retried, and only the failed changes are attempted again.
"""

from __future__ import annotations

import uuid
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, time, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import Conflict, NotFound
from app.core.logging import get_logger
from app.db.base import utcnow
from app.models.ai import AIRun, AIThread
from app.models.automation import Automation, AutomationExecution
from app.models.journal import BATCH_KINDS, ActionRecord, BatchRevert
from app.models.note import Note
from app.models.task import Task, TaskPriority, TaskStatus
from app.models.user import User
from app.services import action_journal as journal

log = get_logger(__name__)

# A revert that crashed mid-way ("running" for this long) may be retried.
STALE_RUNNING = timedelta(minutes=10)

APP_NAMES = {
    "notely": "Notely",
    "google_calendar": "Google Calendar",
    "gmail": "Gmail",
    "todoist": "Todoist",
    "notion": "Notion",
    "slack": "Slack",
}


def app_name(provider: str) -> str:
    if provider in APP_NAMES:
        return APP_NAMES[provider]
    from app.integrations.registry import get_provider

    p = get_provider(provider)
    return p.manifest.name if p else provider.replace("_", " ").title()


# --- preview wording -----------------------------------------------------------------------------


def _group(row: ActionRecord) -> tuple[str, str, str]:
    """(key, singular, plural) for "3 tasks created"-style lines."""
    if row.kind == "task.create":
        return ("task.create", "task created", "tasks created")
    if row.kind == "task.update":
        fields = set(row.after or {})
        if fields <= {"due_date", "due_time"}:
            return ("task.date", "task date changed", "task dates changed")
        if fields == {"status"}:
            return ("task.status", "task completed", "tasks completed")
        return ("task.update", "task updated", "tasks updated")
    if row.kind == "task.delete":
        return ("task.delete", "task deleted", "tasks deleted")
    if row.kind == "note.create":
        return ("note.create", "Notely note created", "Notely notes created")
    if row.kind == "note.update":
        return ("note.update", "Notely note updated", "Notely notes updated")
    if row.kind in ("google_calendar.task_event", "google_calendar.create_event"):
        return ("gcal.event", "Google Calendar event created", "Google Calendar events created")
    if row.kind == "gmail.draft_mail":
        return ("gmail.draft", "Gmail draft created", "Gmail drafts created")
    if row.kind == "gmail.send_mail":
        return ("gmail.send", "email sent", "emails sent")
    name = app_name(row.provider)
    return (row.kind, f"{name}: {row.label}", f"{name}: {row.label}")


def summarize(rows: list[ActionRecord]) -> list[dict[str, Any]]:
    groups: OrderedDict[tuple[str, bool], dict[str, Any]] = OrderedDict()
    for row in rows:
        key, one, many = _group(row)
        g = groups.setdefault(
            (key, row.reversible),
            {"key": key, "count": 0, "one": one, "many": many, "reversible": row.reversible},
        )
        g["count"] += 1
    out = []
    for g in groups.values():
        n = g["count"]
        text = f"{n} {g['one'] if n == 1 else g['many']}" if ":" not in g["one"] else g["one"]
        out.append({"key": g["key"], "count": n, "text": text, "reversible": g["reversible"]})
    return out


# --- per-change undo -----------------------------------------------------------------------------


@dataclass
class Outcome:
    status: str  # reverted | revert_skipped | revert_failed
    note: str | None = None


class Unsafe(Exception):
    """The target changed since the run (or is gone): leave it, report it."""


def _task_matches(task: Task, expected: dict[str, Any]) -> bool:
    current = journal.task_snapshot(task)
    return all(current.get(k) == v for k, v in expected.items())


def _apply_task_fields(task: Task, values: dict[str, Any]) -> None:
    for key, value in values.items():
        if key == "due_date":
            task.due_date = date.fromisoformat(value) if value else None
        elif key == "due_time":
            task.due_time = time.fromisoformat(value) if value else None
        elif key == "priority":
            task.priority = TaskPriority(value)
        elif key == "status":
            task.status = TaskStatus(value)
            task.completed_at = utcnow() if task.status == TaskStatus.done else None
        elif key == "note_id":
            task.note_id = uuid.UUID(value) if value else None
        elif key in ("title", "description"):
            setattr(task, key, value)


class BatchRevertService:
    def __init__(self, db: AsyncSession, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    # --- reading ----------------------------------------------------------------------------

    async def records(self, user: User, kind: str, batch_id: uuid.UUID) -> list[ActionRecord]:
        if kind not in BATCH_KINDS:
            raise NotFound("Unknown history entry.")
        rows = list(
            await self.db.scalars(
                select(ActionRecord)
                .where(
                    ActionRecord.batch_kind == kind,
                    ActionRecord.batch_id == batch_id,
                    ActionRecord.user_id == user.id,
                )
                .order_by(ActionRecord.sequence)
            )
        )
        if not rows:
            raise NotFound("Nothing was changed by this run, or it isn't yours.")
        return rows

    async def revert_row(self, kind: str, batch_id: uuid.UUID) -> BatchRevert | None:
        row: BatchRevert | None = await self.db.scalar(
            select(BatchRevert).where(
                BatchRevert.batch_kind == kind, BatchRevert.batch_id == batch_id
            )
        )
        return row

    async def batch_titles(
        self, keys: list[tuple[str, uuid.UUID]]
    ) -> dict[tuple[str, uuid.UUID], dict[str, Any]]:
        """Human title + link for each batch (conversation title / automation name)."""
        out: dict[tuple[str, uuid.UUID], dict[str, Any]] = {}
        run_ids = [b for k, b in keys if k == "ai_run"]
        if run_ids:
            for run_id, thread_id, title in (
                await self.db.execute(
                    select(AIRun.id, AIThread.id, AIThread.title)
                    .join(AIThread, AIThread.id == AIRun.thread_id)
                    .where(AIRun.id.in_(run_ids))
                )
            ).all():
                out[("ai_run", run_id)] = {
                    "source": "AI Assistant",
                    "title": title or "Conversation",
                    "href": f"/app/ai?thread={thread_id}",
                }
        exec_ids = [b for k, b in keys if k == "automation_run"]
        if exec_ids:
            for exec_id, automation_id, name in (
                await self.db.execute(
                    select(AutomationExecution.id, Automation.id, Automation.name)
                    .join(Automation, Automation.id == AutomationExecution.automation_id)
                    .where(AutomationExecution.id.in_(exec_ids))
                )
            ).all():
                out[("automation_run", exec_id)] = {
                    "source": "Automation",
                    "title": name,
                    "href": f"/app/automations/{automation_id}?run={exec_id}",
                }
        return out

    async def list_batches(
        self, user: User, *, limit: int = 30, before: Any = None
    ) -> list[dict[str, Any]]:
        stmt = (
            select(
                ActionRecord.batch_kind,
                ActionRecord.batch_id,
                func.min(ActionRecord.created_at).label("at"),
                func.count().label("n"),
            )
            .where(ActionRecord.user_id == user.id)
            .group_by(ActionRecord.batch_kind, ActionRecord.batch_id)
            .order_by(func.min(ActionRecord.created_at).desc())
            .limit(limit)
        )
        if before is not None:
            stmt = stmt.having(func.min(ActionRecord.created_at) < before)
        batches = (await self.db.execute(stmt)).all()
        keys = [(k, b) for k, b, _, _ in batches]
        titles = await self.batch_titles(keys)
        out = []
        for kind, batch_id, at, _ in batches:
            rows = await self.records(user, kind, batch_id)
            out.append(await self.describe(kind, batch_id, rows, titles.get((kind, batch_id)), at))
        return out

    async def describe(
        self,
        kind: str,
        batch_id: uuid.UUID,
        rows: list[ActionRecord],
        title: dict[str, Any] | None = None,
        at: Any = None,
    ) -> dict[str, Any]:
        revert = await self.revert_row(kind, batch_id)
        if title is None:
            title = (await self.batch_titles([(kind, batch_id)])).get((kind, batch_id))
        requester = (
            await self.db.get(User, revert.requested_by) if revert and revert.requested_by else None
        )
        return {
            "kind": kind,
            "batch_id": str(batch_id),
            "source": (title or {}).get(
                "source", "AI Assistant" if kind == "ai_run" else "Automation"
            ),
            "title": (title or {}).get("title", "Deleted"),
            "href": (title or {}).get("href"),
            "created_at": at or rows[0].created_at,
            "summary": summarize(rows),
            "reversible_count": sum(1 for r in rows if r.reversible and r.status != "reverted"),
            "revert": (
                {
                    "status": revert.status,
                    "requested_at": revert.requested_at,
                    "finished_at": revert.finished_at,
                    "requested_by": requester.display_name if requester else None,
                    "attempts": revert.attempts,
                    "summary": revert.summary,
                }
                if revert
                else None
            ),
            "changes": [
                {
                    "id": str(r.id),
                    "kind": r.kind,
                    "provider": r.provider,
                    "app": app_name(r.provider),
                    "label": r.label,
                    "resource_type": r.resource_type,
                    "resource_id": r.resource_id,
                    "reversible": r.reversible,
                    "irreversible_reason": r.irreversible_reason,
                    "status": r.status,
                    "revert_note": r.revert_note,
                    "revert_attempts": r.revert_attempts,
                    "reverted_at": r.reverted_at,
                    "created_at": r.created_at,
                }
                for r in rows
            ],
        }

    async def preview(self, user: User, kind: str, batch_id: uuid.UUID) -> dict[str, Any]:
        """What a revert would do right now, checked against the current data (dry run)."""
        rows = await self.records(user, kind, batch_id)
        will, left, cannot = [], [], []
        for row in rows:
            if row.status == "reverted":
                continue
            if not row.reversible:
                cannot.append(row)
                continue
            try:
                await self._check(user, row)
                will.append(row)
            except Unsafe as exc:
                left.append((row, str(exc)))
        described = await self.describe(kind, batch_id, rows)
        return {
            **described,
            "preview": {
                "will_revert": summarize(will),
                "will_leave": [
                    {"label": r.label, "app": app_name(r.provider), "reason": why}
                    for r, why in left
                ],
                "cannot_revert": [
                    {"label": r.label, "app": app_name(r.provider), "reason": r.irreversible_reason}
                    for r in cannot
                ],
            },
        }

    # --- reverting --------------------------------------------------------------------------

    async def revert(
        self, user: User, kind: str, batch_id: uuid.UUID, *, retry: bool = False
    ) -> dict[str, Any]:
        rows = await self.records(user, kind, batch_id)  # ownership check first
        claim_id = (await self._claim(user, kind, batch_id, retry=retry)).id
        counts = {"reverted": 0, "skipped": 0, "failed": 0, "not_reversible": 0}
        order = [
            (r.id, r.status, r.reversible)
            for r in sorted(rows, key=lambda r: r.sequence, reverse=True)
        ]
        for row_id, status, reversible in order:
            if status in ("reverted", "revert_skipped"):
                continue
            if not reversible:
                counts["not_reversible"] += 1
                continue
            outcome = await self._revert_one(user, row_id)
            # A failed undo rolled back its session work: reload the row before marking it.
            row = await self.db.get(ActionRecord, row_id)
            assert row is not None
            row.status = outcome.status
            row.revert_note = outcome.note
            row.revert_attempts = (row.revert_attempts or 0) + 1
            if outcome.status == "reverted":
                row.reverted_at = utcnow()
            await self.db.commit()
            counts[
                {"reverted": "reverted", "revert_skipped": "skipped"}.get(outcome.status, "failed")
            ] += 1
        # Totals across attempts (a retry only touches what failed before).
        fresh = await self.records(user, kind, batch_id)
        totals = {
            "reverted": sum(1 for r in fresh if r.status == "reverted"),
            "skipped": sum(1 for r in fresh if r.status == "revert_skipped"),
            "failed": sum(1 for r in fresh if r.status == "revert_failed"),
            "not_reversible": sum(1 for r in fresh if not r.reversible),
        }
        claim = await self.db.get(BatchRevert, claim_id)
        assert claim is not None
        claim.summary = {**totals, "last_attempt": counts}
        claim.status = (
            "partial"
            if totals["failed"] and totals["reverted"]
            else "failed"
            if totals["failed"]
            else "reverted"
        )
        claim.finished_at = utcnow()
        await self.db.commit()
        return await self.describe(kind, batch_id, fresh)

    async def _claim(
        self, user: User, kind: str, batch_id: uuid.UUID, *, retry: bool
    ) -> BatchRevert:
        """Take the batch's single revert slot, or refuse. Idempotent under double clicks."""
        existing = await self.revert_row(kind, batch_id)
        if existing is None:
            claim = BatchRevert(
                tenant_id=user.tenant_id,
                user_id=user.id,
                batch_kind=kind,
                batch_id=batch_id,
                status="running",
                requested_by=user.id,
                attempts=1,
                summary={},
                requested_at=utcnow(),
            )
            self.db.add(claim)
            try:
                await self.db.commit()
                return claim
            except IntegrityError:
                await self.db.rollback()
                existing = await self.revert_row(kind, batch_id)
                assert existing is not None
        if existing.status == "reverted":
            raise Conflict("This run was already reverted.", code="ALREADY_REVERTED")
        stale = existing.status == "running" and utcnow() - existing.requested_at > STALE_RUNNING
        if existing.status == "running" and not stale:
            raise Conflict(
                "A revert of this run is already in progress.", code="REVERT_IN_PROGRESS"
            )
        if not retry and not stale:
            raise Conflict(
                "Part of this revert failed. Retry to attempt only what failed.",
                code="REVERT_NEEDS_RETRY",
            )
        # Conditional update: of two concurrent retries only one wins the slot.
        result = await self.db.execute(
            update(BatchRevert)
            .where(BatchRevert.id == existing.id, BatchRevert.status == existing.status)
            .values(
                status="running",
                attempts=BatchRevert.attempts + 1,
                requested_at=utcnow(),
                requested_by=user.id,
                finished_at=None,
            )
        )
        if not getattr(result, "rowcount", 0):
            await self.db.rollback()
            raise Conflict(
                "A revert of this run is already in progress.", code="REVERT_IN_PROGRESS"
            )
        await self.db.commit()
        await self.db.refresh(existing)
        return existing

    async def _revert_one(self, user: User, row_id: uuid.UUID) -> Outcome:
        row = await self.db.get(ActionRecord, row_id)
        assert row is not None
        kind, provider = row.kind, row.provider
        try:
            await self._check(user, row)
        except Unsafe as exc:
            return Outcome("revert_skipped", str(exc))
        try:
            await self._undo(user, row)
            return Outcome("reverted")
        except Unsafe as exc:
            await self.db.rollback()
            await self.db.refresh(user)  # the rollback expired everything, the user included
            return Outcome("revert_skipped", str(exc))
        except Exception as exc:  # noqa: BLE001 — recorded, retryable, never raised to the user
            await self.db.rollback()
            await self.db.refresh(user)
            log.info("revert_change_failed", extra={"kind": kind, "error": type(exc).__name__})
            return Outcome("revert_failed", _failure_message(provider, exc))

    # Checks are pure reads (used by the preview too); _undo repeats what it needs.
    async def _check(self, user: User, row: ActionRecord) -> None:
        if row.kind.startswith("task."):
            task = await self._task(user, row.resource_id)
            if row.kind == "task.delete":
                if task is not None:
                    raise Unsafe("A task with this id exists again.")
                return
            if task is None:
                raise Unsafe("The task was already deleted.")
            expected = row.after or {}
            if not _task_matches(task, expected):
                raise Unsafe("The task was changed after this run, so it was left as it is.")
        elif row.kind.startswith("note."):
            note = await self._note(user, row.resource_id)
            if note is None or (row.kind == "note.create" and note.deleted_at is not None):
                raise Unsafe("The note was already deleted.")
            version = (row.after or {}).get("version")
            if version is not None and note.version != version:
                raise Unsafe("The note was edited after this run, so it was left as it is.")
        elif row.kind == "google_calendar.task_event":
            ref = row.revert_ref or {}
            task = await self._task(user, ref.get("task_id"))
            if task is None or task.calendar_event_id != ref.get("event_id"):
                raise Unsafe("The event is no longer linked to its task.")

    async def _undo(self, user: User, row: ActionRecord) -> None:
        if row.kind == "task.create":
            task = await self._task(user, row.resource_id)
            assert task is not None
            if task.calendar_event_id:
                await self._delete_task_event(user, task)
            await self.db.delete(task)
            await self.db.commit()
        elif row.kind == "task.update":
            task = await self._task(user, row.resource_id)
            assert task is not None
            _apply_task_fields(task, row.before or {})
            await self.db.commit()
            from app.services.calendar_sync_service import CalendarSyncService

            await CalendarSyncService(self.db, self.settings).resync_if_linked(user, task)
        elif row.kind == "task.delete":
            before = row.before or {}
            task = Task(
                id=uuid.UUID(str(row.resource_id)),
                tenant_id=user.tenant_id,
                user_id=user.id,
                title=before.get("title") or "Untitled",
            )
            _apply_task_fields(task, before)
            self.db.add(task)
            await self.db.commit()
        elif row.kind == "note.create":
            note = await self._note(user, row.resource_id)
            assert note is not None
            note.deleted_at = utcnow()  # to the trash, restorable for 30 days
            await self.db.commit()
        elif row.kind == "note.update":
            await self._restore_note(user, row)
        elif row.kind == "google_calendar.task_event":
            task = await self._task(user, (row.revert_ref or {}).get("task_id"))
            assert task is not None
            await self._delete_task_event(user, task)
            await self.db.commit()
        else:
            await self._undo_provider(user, row)

    async def _restore_note(self, user: User, row: ActionRecord) -> None:
        from app.services.note_service import NoteService

        note = await self._note(user, row.resource_id)
        assert note is not None
        before = row.before or {}
        service = NoteService(self.db)
        # The current state goes into version history first, so the revert is itself undoable.
        await service._snapshot_if_due(
            user, note, note.title, note.content_json, reason="before_revert"
        )
        from datetime import datetime

        from app.services.rich_text import to_plain_text

        content_changed = False
        for key, value in before.items():
            if key == "title":
                note.title, content_changed = value, True
            elif key == "content_json":
                note.content_json = value
                note.plain_text = to_plain_text(value)
                content_changed = True
            elif key == "folder_id":
                note.folder_id = uuid.UUID(value) if value else None
            elif key in ("archived_at", "reminder_at"):
                setattr(note, key, datetime.fromisoformat(value) if value else None)
            elif key in ("color", "is_favorite"):
                setattr(note, key, value)
        if content_changed:
            await service.notes.mark_updated(note)
        await self.db.commit()

    async def _delete_task_event(self, user: User, task: Task) -> None:
        """Delete the task's Google Calendar event and unlink it. Unlike the UI's best-effort
        unlink, a failure here is raised so the change is reported as not reverted."""
        from app.integrations.base.errors import ProviderError, ProviderErrorKind
        from app.integrations.base.rest import RestOAuthProvider
        from app.services.calendar_sync_service import PROVIDER
        from app.services.connection_service import ConnectionService

        connections = ConnectionService(self.db, self.settings)
        conn = await connections.get_by_provider(user, PROVIDER)
        if conn is None or not conn.is_usable:
            raise RuntimeError("Google Calendar isn't connected")
        provider = connections.adapter(conn)
        assert isinstance(provider, RestOAuthProvider)
        await connections.refresh_if_needed(user, conn)
        try:
            async with provider.http(connections.context(user, conn)) as http:
                await http.delete(
                    f"/calendars/{task.calendar_id or 'primary'}/events/{task.calendar_event_id}"
                )
        except ProviderError as exc:
            if exc.kind != ProviderErrorKind.not_found:  # already gone counts as done
                raise
        task.calendar_id = task.calendar_event_id = task.calendar_event_url = None
        task.calendar_synced_at = None
        if task.external_provider == PROVIDER:
            task.external_provider = task.external_task_id = None

    async def _undo_provider(self, user: User, row: ActionRecord) -> None:
        from app.ai.tools.base import ToolContext
        from app.integrations.base.errors import ProviderError, ProviderErrorKind
        from app.services.connection_service import ConnectionService

        ref = dict(row.revert_ref or {})
        tool = ref.pop("tool", None)
        connections = ConnectionService(self.db, self.settings)
        conn = await connections.get_by_provider(user, row.provider)
        if conn is None or not conn.is_usable:
            raise RuntimeError(f"{app_name(row.provider)} isn't connected")
        await connections.refresh_if_needed(user, conn)
        specs = await connections.adapter(conn).tools(connections.context(user, conn))
        spec = next((s for s in specs if s.name == tool), None)
        if spec is None or spec.revert is None:
            raise RuntimeError(f"{app_name(row.provider)} no longer allows undoing this")
        credential = connections.vault.load(conn).access_token
        try:
            await spec.revert(ToolContext(user=user, db=self.db, credential=credential), ref)
        except ProviderError as exc:
            if exc.kind == ProviderErrorKind.not_found:
                raise Unsafe("It was already removed in the app.") from exc
            await connections.record_tool_failure(conn, exc, user=user)
            raise

    async def _task(self, user: User, task_id: Any) -> Task | None:
        if not task_id:
            return None
        task: Task | None = await self.db.scalar(
            select(Task).where(Task.id == uuid.UUID(str(task_id)), Task.user_id == user.id)
        )
        return task

    async def _note(self, user: User, note_id: Any) -> Note | None:
        if not note_id:
            return None
        note: Note | None = await self.db.scalar(
            select(Note).where(Note.id == uuid.UUID(str(note_id)), Note.user_id == user.id)
        )
        return note


def _failure_message(provider: str, exc: Exception) -> str:
    from app.integrations.base.errors import ProviderError

    if isinstance(exc, ProviderError):
        return f"{app_name(provider)}: {exc.user_message()[1]}"
    text = str(exc) if isinstance(exc, RuntimeError) else "Something went wrong"
    return f"{text}. You can retry."
