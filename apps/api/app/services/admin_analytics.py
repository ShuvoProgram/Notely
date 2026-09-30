"""Read models for the admin dashboard. Every number comes from the database; nothing is
estimated or invented. Queries are aggregate-first (COUNT/SUM/GROUP BY) and bounded, and stay
portable between PostgreSQL and SQLite (the test database).

Privacy: these reports carry metadata only — counts, statuses, timings, error codes. Note
content, AI messages, automation step inputs/outputs, OAuth tokens, API keys and TOTP material
never leave this module.
"""

from __future__ import annotations

import statistics
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import Select, and_, case, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.core.config import Settings
from app.db.base import utcnow
from app.integrations.registry import get_providers
from app.models.admin import AdminAuditEvent, PlatformEvent
from app.models.ai import (
    AIApproval,
    AIRun,
    AIThread,
    AIToolCall,
    AuditEvent,
    RunStatus,
    ToolCallStatus,
    UserAISetting,
)
from app.models.automation import Automation, AutomationExecution, AutomationExecutionStep
from app.models.integration import ConnectionStatus, Integration, UserConnection
from app.models.note import Note
from app.models.task import Task, TaskStatus
from app.models.tenant import Tenant
from app.models.user import STAFF_ROLES, AuthIdentity, PlatformRole, User, UserSession
from app.services.platform_events import scrub

# Rows fetched for percentile/duration maths. Aggregates above this are sampled (newest first)
# and the response says so.
SAMPLE_LIMIT = 5000
AUTH_ERROR_CODES = ("auth_failed", "expired")
LIVE_CONNECTION = (ConnectionStatus.connected, ConnectionStatus.syncing)
FAILED_EXECUTION = "failed"
SUCCESS_EXECUTION = ("completed", "stopped")


# --- helpers ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Window:
    days: int
    since: datetime
    previous_since: datetime
    until: datetime

    @classmethod
    def of(cls, days: int) -> Window:
        now = utcnow()
        start = datetime.combine(now.date() - timedelta(days=days - 1), datetime.min.time(), UTC)
        return cls(days=days, since=start, previous_since=start - timedelta(days=days), until=now)

    def dates(self) -> list[date]:
        first = self.since.date()
        return [first + timedelta(days=i) for i in range(self.days)]


async def _count(db: AsyncSession, stmt: Select[Any]) -> int:
    return int(await db.scalar(stmt) or 0)


def _pairs(rows: Any) -> dict[Any, int]:
    """`{key: count}` from `(key, count)` result rows."""
    return {k: int(v or 0) for k, v in rows}


def _count_of(model: Any, *where: Any) -> Select[Any]:
    return select(func.count()).select_from(model).where(*where)


async def _daily(
    db: AsyncSession, column: Any, window: Window, *where: ColumnElement[bool]
) -> dict[str, int]:
    day = func.date(column)
    rows = await db.execute(
        select(day, func.count()).where(column >= window.since, *where).group_by(day)
    )
    return {str(d)[:10]: int(c) for d, c in rows}


def _series(window: Window, **counts: dict[str, int]) -> list[dict[str, Any]]:
    out = []
    for d in window.dates():
        key = d.isoformat()
        out.append({"date": key, **{name: data.get(key, 0) for name, data in counts.items()}})
    return out


def _seconds(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None:
        return None
    return max((end - start).total_seconds(), 0.0)


def _duration_stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "avg_ms": None, "p50_ms": None, "p95_ms": None}
    ordered = sorted(values)
    p95 = ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]
    return {
        "count": len(values),
        "avg_ms": round(statistics.fmean(values) * 1000),
        "p50_ms": round(statistics.median(values) * 1000),
        "p95_ms": round(p95 * 1000),
    }


def _pct(part: int, whole: int) -> float | None:
    return round(100 * part / whole, 1) if whole else None


def mask_ip(ip: str | None) -> str | None:
    """Enough to tell sessions apart, not enough to locate someone."""
    if not ip:
        return None
    if ":" in ip:
        return ":".join(ip.split(":")[:3]) + ":…"
    parts = ip.split(".")
    return ".".join(parts[:3] + ["x"]) if len(parts) == 4 else "…"


def device_label(user_agent: str | None) -> str:
    ua = (user_agent or "").lower()
    if not ua:
        return "Unknown device"
    browser = next(
        (
            name
            for key, name in (
                ("edg/", "Edge"),
                ("chrome/", "Chrome"),
                ("firefox/", "Firefox"),
                ("safari/", "Safari"),
                ("python", "API client"),
                ("curl", "API client"),
            )
            if key in ua
        ),
        "Browser",
    )
    system = next(
        (
            name
            for key, name in (
                ("iphone", "iPhone"),
                ("ipad", "iPad"),
                ("android", "Android"),
                ("mac os", "macOS"),
                ("windows", "Windows"),
                ("linux", "Linux"),
            )
            if key in ua
        ),
        "",
    )
    return f"{browser} on {system}" if system else browser


def _provider_name(provider_id: str) -> str:
    provider = get_providers().get(provider_id)
    if provider is not None:
        return provider.manifest.name
    if provider_id == "notely":
        return "Notely"
    return provider_id.replace("_", " ").title()


def _step_connector(kind: str) -> str | None:
    """Action steps are stored with kind "<app>.<capability>"; filters/branches have none."""
    if "." not in kind:
        return None
    from app.automation.catalog import BUILTIN_APPS

    app = kind.split(".", 1)[0]
    return None if app in BUILTIN_APPS else app


def _user_brief(user: User | None) -> dict[str, Any] | None:
    if user is None:
        return None
    return {"id": str(user.id), "email": user.email, "display_name": user.display_name}


async def _users_by_id(db: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, User]:
    ids = {i for i in ids if i is not None}
    if not ids:
        return {}
    return {u.id: u for u in await db.scalars(select(User).where(User.id.in_(ids)))}


def _tokens(column: Any, key: str) -> Any:
    return func.coalesce(func.sum(column[key].as_integer()), 0)


# --- overview -----------------------------------------------------------------------------------


class AdminAnalytics:
    def __init__(self, db: AsyncSession, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    async def overview(self, days: int) -> dict[str, Any]:
        db, w = self.db, Window.of(days)

        def in_window(col: Any) -> ColumnElement[bool]:
            return col >= w.since

        def in_previous(col: Any) -> ColumnElement[bool]:
            return and_(col >= w.previous_since, col < w.since)

        total_users = await _count(db, _count_of(User))
        new_users = await _count(db, _count_of(User, in_window(User.created_at)))
        new_users_prev = await _count(db, _count_of(User, in_previous(User.created_at)))
        now = utcnow()
        active = {
            "day": await _count(
                db, _count_of(User, User.last_active_at >= now - timedelta(days=1))
            ),
            "week": await _count(
                db, _count_of(User, User.last_active_at >= now - timedelta(days=7))
            ),
            "month": await _count(
                db, _count_of(User, User.last_active_at >= now - timedelta(days=30))
            ),
            "window": await _count(db, _count_of(User, in_window(User.last_active_at))),
        }
        suspended = await _count(db, _count_of(User, User.is_active.is_(False)))
        staff = await _count(db, _count_of(User, User.role.in_([r.value for r in STAFF_ROLES])))
        before_window = await _count(db, _count_of(User, User.created_at < w.since))
        signups = await _daily(db, User.created_at, w)
        growth, running = [], before_window
        for point in _series(w, signups=signups):
            running += point["signups"]
            growth.append({**point, "total": running})
        recent_users = [
            {
                **(_user_brief(u) or {}),
                "created_at": u.created_at,
                "is_active": u.is_active,
                "role": u.role,
            }
            for u in await db.scalars(select(User).order_by(User.created_at.desc()).limit(8))
        ]

        exec_counts = _pairs(
            (
                await db.execute(
                    select(AutomationExecution.status, func.count())
                    .where(in_window(AutomationExecution.started_at))
                    .group_by(AutomationExecution.status)
                )
            ).all()
        )
        executions_total = sum(int(v) for v in exec_counts.values())
        executions_failed = int(exec_counts.get(FAILED_EXECUTION, 0))
        executions_succeeded = sum(int(exec_counts.get(s, 0)) for s in SUCCESS_EXECUTION)
        ai_requests = await _count(db, _count_of(AIRun, in_window(AIRun.created_at)))
        ai_failed = await _count(
            db, _count_of(AIRun, in_window(AIRun.created_at), AIRun.status == RunStatus.failed)
        )
        connector_calls = await _count(
            db,
            _count_of(
                AuditEvent,
                in_window(AuditEvent.created_at),
                AuditEvent.provider != "notely",
                AuditEvent.action != "verify",
            ),
        )
        usage = {
            "notes_created": await _count(db, _count_of(Note, in_window(Note.created_at))),
            "notes_total": await _count(db, _count_of(Note, Note.deleted_at.is_(None))),
            "tasks_created": await _count(db, _count_of(Task, in_window(Task.created_at))),
            "tasks_completed": await _count(
                db,
                _count_of(Task, Task.status == TaskStatus.done, in_window(Task.completed_at)),
            ),
            "ai_conversations": await _count(
                db, _count_of(AIThread, in_window(AIThread.created_at))
            ),
            "ai_requests": ai_requests,
            "automations_created": await _count(
                db, _count_of(Automation, in_window(Automation.created_at))
            ),
            "automations_total": await _count(db, _count_of(Automation)),
            "automations_enabled": await _count(db, _count_of(Automation, Automation.enabled)),
            "automation_runs": executions_total,
            "automation_runs_succeeded": executions_succeeded,
            "automation_runs_failed": executions_failed,
            "active_connections": await _count(
                db, _count_of(UserConnection, UserConnection.status.in_(LIVE_CONNECTION))
            ),
            "connector_calls": connector_calls,
        }
        usage_series = _series(
            w,
            notes=await _daily(db, Note.created_at, w),
            ai_requests=await _daily(db, AIRun.created_at, w),
            automation_runs=await _daily(db, AutomationExecution.started_at, w),
            tasks=await _daily(db, Task.created_at, w),
        )

        health = await self._health(w)
        health["automation_runs_failed"] = executions_failed
        health["ai_requests_failed"] = ai_failed
        return {
            "window": {"days": days, "since": w.since, "until": w.until},
            "users": {
                "total": total_users,
                "new": new_users,
                "new_previous": new_users_prev,
                "active": active,
                "suspended": suspended,
                "staff": staff,
                "growth": growth,
                "recent": recent_users,
            },
            "usage": usage,
            "usage_series": usage_series,
            "health": health,
        }

    async def _health(self, w: Window) -> dict[str, Any]:
        db = self.db
        kinds = _pairs(
            (
                await db.execute(
                    select(PlatformEvent.kind, func.count())
                    .where(PlatformEvent.category == "error", PlatformEvent.occurred_at >= w.since)
                    .group_by(PlatformEvent.kind)
                )
            ).all()
        )
        connections_auth_failing = await _count(
            db,
            _count_of(
                UserConnection,
                or_(
                    UserConnection.status == ConnectionStatus.expired,
                    and_(
                        UserConnection.status.in_(
                            (ConnectionStatus.error, ConnectionStatus.needs_attention)
                        ),
                        UserConnection.last_error_code.in_(AUTH_ERROR_CODES),
                    ),
                ),
            ),
        )
        incidents = await self.events(category="error", page=1, page_size=8)
        from app.core.kv import redis_healthy

        return {
            "api_errors": int(kinds.get("api_error", 0)),
            "job_failures": int(kinds.get("job_failed", 0)),
            "oauth_failures": int(kinds.get("oauth_failed", 0)),
            "connector_auth_failures": int(kinds.get("connector_auth_failed", 0)),
            "connections_needing_reauth": connections_auth_failing,
            "recent_incidents": incidents["items"],
            "services": {"database": True, "redis": await redis_healthy()},
        }

    # --- platform events --------------------------------------------------------------------

    async def events(
        self,
        *,
        category: str | None = None,
        kind: str | None = None,
        kinds: tuple[str, ...] | None = None,
        source: str | None = None,
        user_id: uuid.UUID | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        where: list[ColumnElement[bool]] = []
        if category:
            where.append(PlatformEvent.category == category)
        if kind:
            where.append(PlatformEvent.kind == kind)
        if kinds:
            where.append(PlatformEvent.kind.in_(kinds))
        if source:
            where.append(PlatformEvent.source == source)
        if user_id:
            where.append(PlatformEvent.user_id == user_id)
        if since:
            where.append(PlatformEvent.occurred_at >= since)
        if until:
            where.append(PlatformEvent.occurred_at < until)
        total = await _count(self.db, _count_of(PlatformEvent, *where))
        rows = list(
            await self.db.scalars(
                select(PlatformEvent)
                .where(*where)
                .order_by(PlatformEvent.occurred_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        users = await _users_by_id(self.db, {r.user_id for r in rows if r.user_id})
        items = [
            {
                "id": str(r.id),
                "category": r.category,
                "kind": r.kind,
                "source": r.source,
                "message": r.message,
                "user": _user_brief(users.get(r.user_id)) if r.user_id else None,
                "metadata": r.metadata_,
                "occurred_at": r.occurred_at,
            }
            for r in rows
        ]
        return {"items": items, "total": total}

    # --- users ------------------------------------------------------------------------------

    async def list_users(
        self,
        *,
        q: str | None,
        status: str | None,
        role: str | None,
        activity: str | None,
        sort: str,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        where: list[ColumnElement[bool]] = []
        if q:
            term = (
                "%"
                + q.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                + "%"
            )
            where.append(
                or_(
                    func.lower(User.email).like(term, escape="\\"),
                    func.lower(User.display_name).like(term, escape="\\"),
                )
            )
        if status == "active":
            where.append(User.is_active.is_(True))
        elif status == "suspended":
            where.append(User.is_active.is_(False))
        if role == "staff":
            where.append(User.role.in_([r.value for r in STAFF_ROLES]))
        elif role:
            where.append(User.role == role)
        now = utcnow()
        if activity == "active_7d":
            where.append(User.last_active_at >= now - timedelta(days=7))
        elif activity == "active_30d":
            where.append(User.last_active_at >= now - timedelta(days=30))
        elif activity == "dormant":
            where.append(
                or_(User.last_active_at.is_(None), User.last_active_at < now - timedelta(days=30))
            )
        elif activity == "new_7d":
            where.append(User.created_at >= now - timedelta(days=7))

        orderings: dict[str, list[Any]] = {
            "created_desc": [User.created_at.desc()],
            "created_asc": [User.created_at.asc()],
            "active_desc": [User.last_active_at.desc().nulls_last(), User.created_at.desc()],
            "email": [User.email.asc()],
        }
        order = orderings.get(sort, orderings["created_desc"])

        notes = (
            select(func.count(Note.id))
            .where(Note.user_id == User.id, Note.deleted_at.is_(None))
            .scalar_subquery()
        )
        automations = select(func.count(Automation.id)).where(Automation.user_id == User.id)
        connections = select(func.count(UserConnection.id)).where(
            UserConnection.user_id == User.id, UserConnection.status.in_(LIVE_CONNECTION)
        )
        ai_runs = select(func.count(AIRun.id)).where(
            AIRun.user_id == User.id, AIRun.created_at >= now - timedelta(days=30)
        )
        total = await _count(self.db, _count_of(User, *where))
        rows = await self.db.execute(
            select(
                User,
                notes.label("notes"),
                automations.scalar_subquery().label("automations"),
                connections.scalar_subquery().label("connections"),
                ai_runs.scalar_subquery().label("ai_requests_30d"),
            )
            .where(*where)
            .order_by(*order)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = [
            {
                "id": str(u.id),
                "email": u.email,
                "display_name": u.display_name,
                "role": u.role,
                "is_active": u.is_active,
                "suspended_at": u.suspended_at,
                "email_verified": u.email_verified,
                "two_factor_enabled": u.totp_secret_encrypted is not None,
                "created_at": u.created_at,
                "last_active_at": u.last_active_at,
                "counts": {
                    "notes": int(n or 0),
                    "automations": int(a or 0),
                    "connections": int(c or 0),
                    "ai_requests_30d": int(r or 0),
                },
            }
            for u, n, a, c, r in rows.all()
        ]
        return {"items": items, "total": total}

    async def user_detail(self, user: User) -> dict[str, Any]:
        db, uid, now = self.db, user.id, utcnow()
        month = now - timedelta(days=30)
        tenant = await db.get(Tenant, user.tenant_id)
        identities = list(await db.scalars(select(AuthIdentity).where(AuthIdentity.user_id == uid)))
        sessions = list(
            await db.scalars(
                select(UserSession)
                .where(
                    UserSession.user_id == uid,
                    UserSession.revoked_at.is_(None),
                    UserSession.expires_at > now,
                )
                .order_by(UserSession.last_seen_at.desc())
                .limit(20)
            )
        )

        run_rows = (
            await db.execute(
                select(
                    func.count(AIRun.id),
                    func.sum(case((AIRun.created_at >= month, 1), else_=0)),
                    func.sum(case((AIRun.status == RunStatus.failed, 1), else_=0)),
                    _tokens(AIRun.token_usage, "input_tokens"),
                    _tokens(AIRun.token_usage, "output_tokens"),
                    func.max(AIRun.created_at),
                ).where(AIRun.user_id == uid)
            )
        ).one()
        byo = await db.scalar(select(UserAISetting).where(UserAISetting.user_id == uid))

        automations = list(
            await db.scalars(
                select(Automation)
                .where(Automation.user_id == uid)
                .order_by(Automation.updated_at.desc())
                .limit(25)
            )
        )
        exec_where = and_(
            AutomationExecution.automation_id.in_(
                select(Automation.id).where(Automation.user_id == uid)
            ),
            AutomationExecution.started_at >= month,
        )
        exec_counts = _pairs(
            (
                await db.execute(
                    select(AutomationExecution.status, func.count())
                    .where(exec_where)
                    .group_by(AutomationExecution.status)
                )
            ).all()
        )
        last_runs: dict[uuid.UUID, datetime] = {}
        if automations:
            last_rows = await db.execute(
                select(AutomationExecution.automation_id, func.max(AutomationExecution.started_at))
                .where(AutomationExecution.automation_id.in_([a.id for a in automations]))
                .group_by(AutomationExecution.automation_id)
            )
            last_runs = {k: v for k, v in last_rows.all()}

        connections = list(
            await db.scalars(
                select(UserConnection)
                .where(UserConnection.user_id == uid)
                .order_by(UserConnection.updated_at.desc())
            )
        )
        activity = list(
            await db.scalars(
                select(AuditEvent)
                .where(AuditEvent.user_id == uid)
                .order_by(AuditEvent.created_at.desc())
                .limit(20)
            )
        )
        failed_runs = list(
            await db.scalars(
                select(AIRun)
                .where(AIRun.user_id == uid, AIRun.status == RunStatus.failed)
                .order_by(AIRun.created_at.desc())
                .limit(10)
            )
        )
        failed_execs = (
            await db.execute(
                select(AutomationExecution, Automation.name)
                .join(Automation, Automation.id == AutomationExecution.automation_id)
                .where(Automation.user_id == uid, AutomationExecution.status == FAILED_EXECUTION)
                .order_by(AutomationExecution.started_at.desc())
                .limit(10)
            )
        ).all()
        error_events = await self.events(category="error", user_id=uid, page=1, page_size=10)
        security_events = await self.events(category="security", user_id=uid, page=1, page_size=20)
        admin_actions = list(
            await db.scalars(
                select(AdminAuditEvent)
                .where(
                    AdminAuditEvent.resource_type == "user",
                    AdminAuditEvent.resource_id == str(uid),
                )
                .order_by(AdminAuditEvent.created_at.desc())
                .limit(20)
            )
        )

        errors: list[dict[str, Any]] = [
            {
                "source": "ai",
                "message": scrub(r.error, 300) or "The AI request failed.",
                "occurred_at": r.completed_at or r.created_at,
                "ref": str(r.id),
            }
            for r in failed_runs
        ]
        errors += [
            {
                "source": "automation",
                "message": scrub(e.error, 300) or "The run failed.",
                "label": name,
                "occurred_at": e.finished_at or e.started_at,
                "ref": str(e.id),
            }
            for e, name in failed_execs
        ]
        errors += [
            {
                "source": "connector",
                "label": _provider_name(c.provider),
                "message": scrub(c.last_error, 300),
                "code": c.last_error_code,
                "occurred_at": c.last_checked_at or c.updated_at,
                "ref": str(c.id),
            }
            for c in connections
            if c.last_error_code and c.status != ConnectionStatus.disconnected
        ]
        errors += [
            {
                "source": "platform",
                "label": e["kind"],
                "message": e["message"],
                "occurred_at": e["occurred_at"],
                "ref": e["id"],
            }
            for e in error_events["items"]
        ]
        errors.sort(key=lambda e: e["occurred_at"], reverse=True)

        return {
            "profile": {
                "id": str(user.id),
                "email": user.email,
                "display_name": user.display_name,
                "role": user.role,
                "is_active": user.is_active,
                "suspended_at": user.suspended_at,
                "suspension_reason": user.suspension_reason,
                "email_verified": user.email_verified,
                "created_at": user.created_at,
                "last_login_at": user.last_login_at,
                "last_active_at": user.last_active_at,
                "has_password": user.password_hash is not None,
                "two_factor_enabled": user.totp_secret_encrypted is not None,
                "sign_in_methods": (["password"] if user.password_hash else [])
                + [i.provider.value for i in identities],
                "workspace": {"name": tenant.name, "kind": tenant.kind.value} if tenant else None,
            },
            "usage": {
                "notes": await _count(
                    db, _count_of(Note, Note.user_id == uid, Note.deleted_at.is_(None))
                ),
                "notes_trashed": await _count(
                    db, _count_of(Note, Note.user_id == uid, Note.deleted_at.is_not(None))
                ),
                "notes_created_30d": await _count(
                    db, _count_of(Note, Note.user_id == uid, Note.created_at >= month)
                ),
                "tasks_open": await _count(
                    db, _count_of(Task, Task.user_id == uid, Task.status == TaskStatus.open)
                ),
                "tasks_done": await _count(
                    db, _count_of(Task, Task.user_id == uid, Task.status == TaskStatus.done)
                ),
            },
            "ai": {
                "conversations": await _count(db, _count_of(AIThread, AIThread.user_id == uid)),
                "requests": int(run_rows[0] or 0),
                "requests_30d": int(run_rows[1] or 0),
                "failed": int(run_rows[2] or 0),
                "input_tokens": int(run_rows[3] or 0),
                "output_tokens": int(run_rows[4] or 0),
                "last_request_at": run_rows[5],
                "own_model": (
                    {"provider": byo.provider, "model": byo.model, "enabled": byo.enabled}
                    if byo
                    else None
                ),
            },
            "automations": {
                "total": await _count(db, _count_of(Automation, Automation.user_id == uid)),
                "enabled": await _count(
                    db, _count_of(Automation, Automation.user_id == uid, Automation.enabled)
                ),
                "runs_30d": sum(int(v) for v in exec_counts.values()),
                "failed_30d": int(exec_counts.get(FAILED_EXECUTION, 0)),
                "items": [
                    {
                        "id": str(a.id),
                        "name": a.name,
                        "enabled": a.enabled,
                        "schedule_kind": a.schedule_kind,
                        "consecutive_failures": a.consecutive_failures,
                        "next_run_at": a.next_run_at,
                        "last_run_at": last_runs.get(a.id),
                        "created_at": a.created_at,
                    }
                    for a in automations
                ],
            },
            "connections": [
                {
                    "id": str(c.id),
                    "provider": c.provider,
                    "name": _provider_name(c.provider),
                    "status": c.status.value,
                    "auth_type": c.auth_type,
                    "scopes_count": len(c.scopes or []),
                    "last_error_code": c.last_error_code,
                    "last_checked_at": c.last_checked_at,
                    "last_sync_at": c.last_sync_at,
                    "connected_at": c.created_at,
                }
                for c in connections
            ],
            "sessions": [
                {
                    "id": str(s.id),
                    "device": device_label(s.user_agent),
                    "ip": mask_ip(s.ip_address),
                    "created_at": s.created_at,
                    "last_seen_at": s.last_seen_at,
                    "expires_at": s.expires_at,
                    "two_factor_verified": s.two_factor_verified_at is not None,
                }
                for s in sessions
            ],
            "activity": [
                {
                    "id": str(e.id),
                    "provider": e.provider,
                    "provider_name": _provider_name(e.provider),
                    "action": e.action,
                    "tool": e.tool_name,
                    "risk": e.risk_level.value,
                    "status": e.status,
                    "created_at": e.created_at,
                }
                for e in activity
            ],
            "errors": errors[:20],
            "security_events": security_events["items"],
            "admin_actions": [audit_row(e) for e in admin_actions],
        }

    # --- automations ------------------------------------------------------------------------

    async def automation_summary(self, days: int) -> dict[str, Any]:
        db, w = self.db, Window.of(days)
        recent = AutomationExecution.started_at >= w.since
        status_counts = _pairs(
            (
                await db.execute(
                    select(AutomationExecution.status, func.count())
                    .where(recent)
                    .group_by(AutomationExecution.status)
                )
            ).all()
        )
        mode_counts = _pairs(
            (
                await db.execute(
                    select(AutomationExecution.run_mode, func.count())
                    .where(recent)
                    .group_by(AutomationExecution.run_mode)
                )
            ).all()
        )
        timings = (
            await db.execute(
                select(AutomationExecution.started_at, AutomationExecution.finished_at)
                .where(recent, AutomationExecution.finished_at.is_not(None))
                .order_by(AutomationExecution.started_at.desc())
                .limit(SAMPLE_LIMIT)
            )
        ).all()
        durations = [d for d in (_seconds(s, f) for s, f in timings) if d is not None]
        retried = await _count(
            db, _count_of(AutomationExecution, recent, AutomationExecution.attempts > 1)
        )
        failing = (
            await db.execute(
                select(
                    Automation.id,
                    Automation.name,
                    Automation.user_id,
                    Automation.enabled,
                    Automation.consecutive_failures,
                    func.count(AutomationExecution.id).label("runs"),
                    func.sum(
                        case((AutomationExecution.status == FAILED_EXECUTION, 1), else_=0)
                    ).label("failed"),
                    func.max(AutomationExecution.started_at).label("last_run"),
                )
                .join(AutomationExecution, AutomationExecution.automation_id == Automation.id)
                .where(recent)
                .group_by(
                    Automation.id,
                    Automation.name,
                    Automation.user_id,
                    Automation.enabled,
                    Automation.consecutive_failures,
                )
                .having(
                    func.sum(case((AutomationExecution.status == FAILED_EXECUTION, 1), else_=0)) > 0
                )
                .order_by(
                    func.sum(
                        case((AutomationExecution.status == FAILED_EXECUTION, 1), else_=0)
                    ).desc()
                )
                .limit(10)
            )
        ).all()
        owners = await _users_by_id(db, {row.user_id for row in failing})

        failed_steps = (
            await db.execute(
                select(AutomationExecutionStep.kind, AutomationExecutionStep.result)
                .join(
                    AutomationExecution,
                    AutomationExecution.id == AutomationExecutionStep.execution_id,
                )
                .where(recent, AutomationExecutionStep.status == "failed")
                .order_by(AutomationExecution.started_at.desc())
                .limit(SAMPLE_LIMIT)
            )
        ).all()
        by_error: dict[str, int] = {}
        by_connector: dict[str, int] = {}
        for kind, result in failed_steps:
            error_type = error_type_of(result)
            by_error[error_type] = by_error.get(error_type, 0) + 1
            connector = _step_connector(kind) or "notely"
            by_connector[connector] = by_connector.get(connector, 0) + 1

        total = sum(int(v) for v in status_counts.values())
        failed = int(status_counts.get(FAILED_EXECUTION, 0))
        succeeded = sum(int(status_counts.get(s, 0)) for s in SUCCESS_EXECUTION)
        return {
            "window": {"days": days, "since": w.since, "until": w.until},
            "automations": {
                "total": await _count(db, _count_of(Automation)),
                "enabled": await _count(db, _count_of(Automation, Automation.enabled)),
                "paused_after_failures": await _count(
                    db,
                    _count_of(
                        Automation,
                        Automation.enabled.is_(False),
                        Automation.consecutive_failures > 0,
                    ),
                ),
                "event_triggered": await _count(
                    db, _count_of(Automation, Automation.schedule_kind == "event")
                ),
                "created_in_window": await _count(
                    db, _count_of(Automation, Automation.created_at >= w.since)
                ),
            },
            "executions": {
                "total": total,
                "succeeded": succeeded,
                "failed": failed,
                "waiting_for_approval": int(status_counts.get("waiting_for_approval", 0)),
                "in_progress": int(status_counts.get("running", 0))
                + int(status_counts.get("queued", 0)),
                "success_rate": _pct(succeeded, succeeded + failed),
                "retried": retried,
                "by_status": {str(k): int(v) for k, v in status_counts.items()},
                "by_mode": {str(k): int(v) for k, v in mode_counts.items()},
                "duration": {**_duration_stats(durations), "sampled": len(timings) >= SAMPLE_LIMIT},
            },
            "series": _series(
                w,
                succeeded=await _daily(
                    db,
                    AutomationExecution.started_at,
                    w,
                    AutomationExecution.status.in_(SUCCESS_EXECUTION),
                ),
                failed=await _daily(
                    db,
                    AutomationExecution.started_at,
                    w,
                    AutomationExecution.status == FAILED_EXECUTION,
                ),
            ),
            "top_failing": [
                {
                    "id": str(row.id),
                    "name": row.name,
                    "owner": _user_brief(owners.get(row.user_id)),
                    "enabled": row.enabled,
                    "consecutive_failures": row.consecutive_failures,
                    "runs": int(row.runs),
                    "failed": int(row.failed or 0),
                    "failure_rate": _pct(int(row.failed or 0), int(row.runs)),
                    "last_run_at": row.last_run,
                }
                for row in failing
            ],
            "failures_by_error": sorted(
                ({"error_type": k, "count": v} for k, v in by_error.items()),
                key=lambda r: -r["count"],
            ),
            "failures_by_connector": sorted(
                (
                    {"connector": k, "name": _provider_name(k), "count": v}
                    for k, v in by_connector.items()
                ),
                key=lambda r: -r["count"],
            ),
        }

    async def list_executions(
        self,
        *,
        status: str | None,
        user_id: uuid.UUID | None,
        automation_id: uuid.UUID | None,
        connector: str | None,
        error_type: str | None,
        run_mode: str | None,
        since: datetime | None,
        until: datetime | None,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        where: list[ColumnElement[bool]] = []
        if status == "succeeded":
            where.append(AutomationExecution.status.in_(SUCCESS_EXECUTION))
        elif status:
            where.append(AutomationExecution.status == status)
        if user_id:
            where.append(Automation.user_id == user_id)
        if automation_id:
            where.append(AutomationExecution.automation_id == automation_id)
        if run_mode:
            where.append(AutomationExecution.run_mode == run_mode)
        if since:
            where.append(AutomationExecution.started_at >= since)
        if until:
            where.append(AutomationExecution.started_at < until)
        step = AutomationExecutionStep
        if connector:
            where.append(
                exists().where(
                    step.execution_id == AutomationExecution.id,
                    step.kind.like(
                        connector.replace("%", "").replace("_", "\\_") + ".%", escape="\\"
                    ),
                )
            )
        if error_type:
            failed_step = and_(step.execution_id == AutomationExecution.id, step.status == "failed")
            if error_type in ("step_error", "declined"):
                marker = (
                    step.result["declined"].as_boolean().is_(True)
                    if error_type == "declined"
                    else and_(
                        step.result["kind"].as_string().is_(None),
                        or_(
                            step.result["declined"].as_boolean().is_(None),
                            step.result["declined"].as_boolean().is_(False),
                        ),
                    )
                )
                where.append(exists().where(failed_step, marker))
            elif error_type == "run_error":
                where.append(AutomationExecution.status == FAILED_EXECUTION)
                where.append(~exists().where(failed_step))
            else:
                where.append(
                    exists().where(failed_step, step.result["kind"].as_string() == error_type)
                )

        base = select(AutomationExecution, Automation).join(
            Automation, Automation.id == AutomationExecution.automation_id
        )
        total = await _count(
            self.db,
            select(func.count())
            .select_from(AutomationExecution)
            .join(Automation, Automation.id == AutomationExecution.automation_id)
            .where(*where),
        )
        rows = (
            await self.db.execute(
                base.where(*where)
                .order_by(AutomationExecution.started_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        ids = [e.id for e, _ in rows]
        step_rows = (
            (
                await self.db.execute(
                    select(step.execution_id, step.kind, step.status, step.result).where(
                        step.execution_id.in_(ids)
                    )
                )
            ).all()
            if ids
            else []
        )
        connectors: dict[uuid.UUID, set[str]] = {}
        errors: dict[uuid.UUID, str] = {}
        counts: dict[uuid.UUID, int] = {}
        for exec_id, kind, st, result in step_rows:
            counts[exec_id] = counts.get(exec_id, 0) + 1
            app = _step_connector(kind)
            if app:
                connectors.setdefault(exec_id, set()).add(app)
            if st == "failed" and exec_id not in errors:
                errors[exec_id] = error_type_of(result)
        owners = await _users_by_id(self.db, {a.user_id for _, a in rows})
        items = []
        for e, a in rows:
            duration = _seconds(e.started_at, e.finished_at)
            items.append(
                {
                    "id": str(e.id),
                    "automation": {"id": str(a.id), "name": a.name},
                    "owner": _user_brief(owners.get(a.user_id)),
                    "status": e.status,
                    "run_mode": e.run_mode,
                    "attempts": e.attempts,
                    "started_at": e.started_at,
                    "finished_at": e.finished_at,
                    "duration_ms": round(duration * 1000) if duration is not None else None,
                    "error": scrub(e.error, 300),
                    "error_type": errors.get(e.id)
                    or ("run_error" if e.status == FAILED_EXECUTION else None),
                    "connectors": sorted(connectors.get(e.id, set())),
                    "steps": counts.get(e.id, 0),
                }
            )
        return {"items": items, "total": total}

    async def execution_detail(self, execution_id: uuid.UUID) -> dict[str, Any] | None:
        row = (
            await self.db.execute(
                select(AutomationExecution, Automation)
                .join(Automation, Automation.id == AutomationExecution.automation_id)
                .where(AutomationExecution.id == execution_id)
            )
        ).first()
        if row is None:
            return None
        e, a = row
        owner = await self.db.get(User, a.user_id)
        steps = list(
            await self.db.scalars(
                select(AutomationExecutionStep)
                .where(AutomationExecutionStep.execution_id == e.id)
                .order_by(AutomationExecutionStep.position)
            )
        )
        from app.models.automation import AutomationApproval

        approvals = list(
            await self.db.scalars(
                select(AutomationApproval).where(AutomationApproval.execution_id == e.id)
            )
        )
        duration = _seconds(e.started_at, e.finished_at)
        return {
            "id": str(e.id),
            "status": e.status,
            "run_mode": e.run_mode,
            "attempts": e.attempts,
            "occurrence_at": e.occurrence_at,
            "started_at": e.started_at,
            "finished_at": e.finished_at,
            "duration_ms": round(duration * 1000) if duration is not None else None,
            "error": scrub(e.error, 1000),
            "outcome": (e.result or {}).get("outcome"),
            # Trigger/context: field names only — values can be people's emails, titles, etc.
            "context_keys": sorted((e.context or {}).keys())[:30],
            "automation": {
                "id": str(a.id),
                "name": a.name,
                "enabled": a.enabled,
                "schedule_kind": a.schedule_kind,
                "timezone": a.timezone,
                "consecutive_failures": a.consecutive_failures,
                "next_run_at": a.next_run_at,
                "created_at": a.created_at,
            },
            "owner": _user_brief(owner),
            "steps": [
                {
                    "step_id": s.step_id,
                    "position": s.position,
                    "kind": s.kind,
                    "connector": _step_connector(s.kind),
                    "name": s.name,
                    "status": s.status,
                    "attempts": s.attempts,
                    "error": scrub(s.error, 1000),
                    "error_type": error_type_of(s.result) if s.status == "failed" else None,
                    "input_fields": sorted((s.input or {}).keys())[:30]
                    if isinstance(s.input, dict)
                    else [],
                    "has_output": s.output is not None,
                    "started_at": s.started_at,
                    "finished_at": s.finished_at,
                    "duration_ms": (
                        round(d * 1000)
                        if (d := _seconds(s.started_at, s.finished_at)) is not None
                        else None
                    ),
                }
                for s in steps
            ],
            "approvals": [
                {"step_id": ap.step_id, "status": ap.status, "decided_at": ap.decided_at}
                for ap in approvals
            ],
        }

    # --- connectors -------------------------------------------------------------------------

    async def connectors(self, days: int) -> dict[str, Any]:
        db, w = self.db, Window.of(days)
        status_rows = (
            await db.execute(
                select(UserConnection.provider, UserConnection.status, func.count()).group_by(
                    UserConnection.provider, UserConnection.status
                )
            )
        ).all()
        auth_failing = _pairs(
            (
                await db.execute(
                    select(UserConnection.provider, func.count())
                    .where(
                        UserConnection.status != ConnectionStatus.disconnected,
                        or_(
                            UserConnection.status == ConnectionStatus.expired,
                            UserConnection.last_error_code.in_(AUTH_ERROR_CODES),
                        ),
                    )
                    .group_by(UserConnection.provider)
                )
            ).all()
        )
        calls = (
            await db.execute(
                select(
                    AuditEvent.provider,
                    func.count(),
                    func.sum(case((AuditEvent.status == "failed", 1), else_=0)),
                    func.max(case((AuditEvent.status == "failed", AuditEvent.created_at))),
                )
                .where(AuditEvent.created_at >= w.since, AuditEvent.action != "verify")
                .group_by(AuditEvent.provider)
            )
        ).all()
        event_counts = (
            await db.execute(
                select(PlatformEvent.source, PlatformEvent.kind, func.count())
                .where(
                    PlatformEvent.occurred_at >= w.since,
                    PlatformEvent.kind.in_(("oauth_failed", "connector_auth_failed")),
                )
                .group_by(PlatformEvent.source, PlatformEvent.kind)
            )
        ).all()
        enabled = {row.provider: row.enabled for row in await db.scalars(select(Integration))}

        stats: dict[str, dict[str, Any]] = {}

        def entry(pid: str) -> dict[str, Any]:
            return stats.setdefault(
                pid,
                {
                    "by_status": {},
                    "auth_failing": 0,
                    "calls": 0,
                    "failed_calls": 0,
                    "last_failure_at": None,
                    "oauth_failures": 0,
                    "auth_failures": 0,
                },
            )

        for pid, st, n in status_rows:
            entry(pid)["by_status"][st.value if hasattr(st, "value") else str(st)] = int(n)
        for pid, n in auth_failing.items():
            entry(pid)["auth_failing"] = int(n)
        for pid, n, failed, last_failed in calls:
            e = entry(pid)
            e["calls"], e["failed_calls"], e["last_failure_at"] = (
                int(n),
                int(failed or 0),
                last_failed,
            )
        for source, kind, n in event_counts:
            if source:
                key = "oauth_failures" if kind == "oauth_failed" else "auth_failures"
                entry(source)[key] += int(n)

        items = []
        providers = get_providers()
        for pid in [*providers.keys(), *[p for p in stats if p not in providers and p != "notely"]]:
            provider = providers.get(pid)
            s = entry(pid)
            by = s["by_status"]
            connected = sum(by.get(x.value, 0) for x in LIVE_CONNECTION)
            accounts = sum(v for k, v in by.items() if k != ConnectionStatus.disconnected.value)
            failed, calls_n = s["failed_calls"], s["calls"]
            is_enabled = enabled.get(pid, True)
            configured = bool(provider and provider.is_configured(self.settings))
            # Observed problems outrank configuration state: a vendor people failed to sign in
            # to is "degraded" even if its OAuth app has since been removed.
            troubled = bool(
                (calls_n and failed / calls_n >= 0.1)
                or s["auth_failing"]
                or s["oauth_failures"]
                or s["auth_failures"]
            )
            if not is_enabled:
                health = "disabled"
            elif calls_n >= 5 and failed / calls_n >= 0.5:
                health = "failing"
            elif troubled:
                health = "degraded"
            elif provider is not None and not configured and accounts == 0:
                health = "not_configured"
            elif accounts == 0 and calls_n == 0:
                health = "unused"
            else:
                health = "healthy"
            items.append(
                {
                    "provider": pid,
                    "name": _provider_name(pid),
                    "category": provider.manifest.category if provider else "custom",
                    "enabled": is_enabled,
                    "configured": configured,
                    "health": health,
                    "accounts": accounts,
                    "connected": connected,
                    "expired": by.get(ConnectionStatus.expired.value, 0),
                    "needs_attention": by.get(ConnectionStatus.needs_attention.value, 0),
                    "errored": by.get(ConnectionStatus.error.value, 0),
                    "disconnected": by.get(ConnectionStatus.disconnected.value, 0),
                    "auth_failing": s["auth_failing"],
                    "oauth_failures": s["oauth_failures"],
                    "auth_failures": s["auth_failures"],
                    "calls": calls_n,
                    "failed_calls": failed,
                    "failure_rate": _pct(failed, calls_n),
                    "last_failure_at": s["last_failure_at"],
                }
            )
        order = {
            "failing": 0,
            "degraded": 1,
            "healthy": 2,
            "unused": 3,
            "not_configured": 4,
            "disabled": 5,
        }
        items.sort(key=lambda i: (order.get(i["health"], 9), -i["accounts"], i["name"]))
        return {"window": {"days": days, "since": w.since, "until": w.until}, "items": items}

    async def connector_detail(self, provider_id: str, days: int) -> dict[str, Any]:
        db, w = self.db, Window.of(days)
        problems = (
            await db.execute(
                select(UserConnection, User)
                .join(User, User.id == UserConnection.user_id)
                .where(
                    UserConnection.provider == provider_id,
                    UserConnection.status.in_(
                        (
                            ConnectionStatus.expired,
                            ConnectionStatus.error,
                            ConnectionStatus.needs_attention,
                        )
                    ),
                )
                .order_by(UserConnection.last_checked_at.desc().nulls_last())
                .limit(50)
            )
        ).all()
        failures = (
            await db.execute(
                select(AuditEvent, User)
                .join(User, User.id == AuditEvent.user_id)
                .where(
                    AuditEvent.provider == provider_id,
                    AuditEvent.status == "failed",
                    AuditEvent.created_at >= w.since,
                )
                .order_by(AuditEvent.created_at.desc())
                .limit(50)
            )
        ).all()
        events = await self.events(
            kinds=("oauth_failed", "connector_auth_failed"),
            source=provider_id,
            since=w.since,
            page=1,
            page_size=50,
        )
        return {
            "provider": provider_id,
            "name": _provider_name(provider_id),
            "connections_with_problems": [
                {
                    "id": str(c.id),
                    "user": _user_brief(u),
                    "status": c.status.value,
                    "error_code": c.last_error_code,
                    "error": scrub(c.last_error, 300),
                    "last_checked_at": c.last_checked_at,
                }
                for c, u in problems
            ],
            "recent_failures": [
                {
                    "id": str(e.id),
                    "user": _user_brief(u),
                    "action": e.action,
                    "tool": e.tool_name,
                    "created_at": e.created_at,
                }
                for e, u in failures
            ],
            "auth_events": events["items"],
        }

    # --- AI ---------------------------------------------------------------------------------

    async def ai(self, days: int) -> dict[str, Any]:
        db, w = self.db, Window.of(days)
        recent = AIRun.created_at >= w.since
        status_counts = _pairs(
            (
                await db.execute(
                    select(AIRun.status, func.count()).where(recent).group_by(AIRun.status)
                )
            ).all()
        )
        by_model = (
            await db.execute(
                select(
                    AIRun.provider,
                    AIRun.model,
                    func.count(),
                    func.sum(case((AIRun.status == RunStatus.failed, 1), else_=0)),
                    _tokens(AIRun.token_usage, "input_tokens"),
                    _tokens(AIRun.token_usage, "output_tokens"),
                )
                .where(recent)
                .group_by(AIRun.provider, AIRun.model)
                .order_by(func.count().desc())
            )
        ).all()
        totals = (
            await db.execute(
                select(
                    _tokens(AIRun.token_usage, "input_tokens"),
                    _tokens(AIRun.token_usage, "output_tokens"),
                    func.count(AIRun.cost_usd),
                    func.sum(AIRun.cost_usd),
                ).where(recent)
            )
        ).one()
        # Latency: completed runs that never paused for a person's approval, so human
        # think-time doesn't pollute model latency.
        timings = (
            await db.execute(
                select(AIRun.started_at, AIRun.completed_at)
                .where(
                    recent,
                    AIRun.status == RunStatus.completed,
                    AIRun.started_at.is_not(None),
                    ~exists().where(AIApproval.run_id == AIRun.id),
                )
                .order_by(AIRun.created_at.desc())
                .limit(SAMPLE_LIMIT)
            )
        ).all()
        durations = [d for d in (_seconds(s, f) for s, f in timings) if d is not None]

        tool_recent = AIToolCall.created_at >= w.since
        tool_status = _pairs(
            (
                await db.execute(
                    select(AIToolCall.status, func.count())
                    .where(tool_recent)
                    .group_by(AIToolCall.status)
                )
            ).all()
        )
        top_tools = (
            await db.execute(
                select(
                    AIToolCall.tool_name,
                    AIToolCall.provider,
                    func.count(),
                    func.sum(case((AIToolCall.status == ToolCallStatus.failed, 1), else_=0)),
                )
                .where(tool_recent)
                .group_by(AIToolCall.tool_name, AIToolCall.provider)
                .order_by(func.count().desc())
                .limit(12)
            )
        ).all()
        drafts = _pairs(
            (
                await db.execute(
                    select(PlatformEvent.kind, func.count())
                    .where(
                        PlatformEvent.occurred_at >= w.since,
                        PlatformEvent.kind.in_(
                            ("ai_automation_draft", "ai_automation_draft_failed")
                        ),
                    )
                    .group_by(PlatformEvent.kind)
                )
            ).all()
        )
        top_users_rows = (
            await db.execute(
                select(
                    AIRun.user_id,
                    func.count(),
                    _tokens(AIRun.token_usage, "input_tokens"),
                    _tokens(AIRun.token_usage, "output_tokens"),
                )
                .where(recent)
                .group_by(AIRun.user_id)
                .order_by(func.count().desc())
                .limit(10)
            )
        ).all()
        users = await _users_by_id(db, {r[0] for r in top_users_rows})
        tokens_daily_rows = (
            await db.execute(
                select(
                    func.date(AIRun.created_at),
                    _tokens(AIRun.token_usage, "input_tokens"),
                    _tokens(AIRun.token_usage, "output_tokens"),
                )
                .where(recent)
                .group_by(func.date(AIRun.created_at))
            )
        ).all()
        tokens_in = {str(d)[:10]: int(i or 0) for d, i, _ in tokens_daily_rows}
        tokens_out = {str(d)[:10]: int(o or 0) for d, _, o in tokens_daily_rows}

        requests = sum(int(v) for v in status_counts.values())
        failed = int(status_counts.get(RunStatus.failed, 0))
        cost_rows, cost_sum = int(totals[2] or 0), totals[3]
        return {
            "window": {"days": days, "since": w.since, "until": w.until},
            "requests": {
                "total": requests,
                "failed": failed,
                "failure_rate": _pct(failed, requests),
                "by_status": {
                    (k.value if hasattr(k, "value") else str(k)): int(v)
                    for k, v in status_counts.items()
                },
                "conversations": await _count(
                    db, _count_of(AIThread, AIThread.created_at >= w.since)
                ),
                "active_users": await _count(
                    db, select(func.count(func.distinct(AIRun.user_id))).where(recent)
                ),
            },
            "tokens": {
                "input": int(totals[0] or 0),
                "output": int(totals[1] or 0),
                "runs_without_usage": await _count(
                    db,
                    _count_of(
                        AIRun,
                        recent,
                        AIRun.token_usage["input_tokens"].as_integer().is_(None),
                    ),
                ),
            },
            # Only present when runs actually recorded a cost. Always an estimate from the
            # gateway's price table — never the provider's invoice.
            "cost": {
                "tracked": cost_rows > 0,
                "estimated_usd": float(cost_sum) if cost_sum is not None else None,
                "runs_with_cost": cost_rows,
            },
            "latency": {**_duration_stats(durations), "sampled": len(timings) >= SAMPLE_LIMIT},
            "by_model": [
                {
                    "provider": p or "unknown",
                    "model": m or "unknown",
                    "requests": int(n),
                    "failed": int(f or 0),
                    "input_tokens": int(i or 0),
                    "output_tokens": int(o or 0),
                }
                for p, m, n, f, i, o in by_model
            ],
            "tools": {
                "total": sum(int(v) for v in tool_status.values()),
                "by_status": {
                    (k.value if hasattr(k, "value") else str(k)): int(v)
                    for k, v in tool_status.items()
                },
                "top": [
                    {
                        "tool": t,
                        "provider": p,
                        "provider_name": _provider_name(p),
                        "calls": int(n),
                        "failed": int(f or 0),
                    }
                    for t, p, n, f in top_tools
                ],
            },
            "automation_drafts": {
                "succeeded": int(drafts.get("ai_automation_draft", 0)),
                "failed": int(drafts.get("ai_automation_draft_failed", 0)),
            },
            "own_model_users": await _count(
                db, _count_of(UserAISetting, UserAISetting.enabled.is_(True))
            ),
            "top_users": [
                {
                    "user": _user_brief(users.get(uid)),
                    "requests": int(n),
                    "input_tokens": int(i or 0),
                    "output_tokens": int(o or 0),
                }
                for uid, n, i, o in top_users_rows
            ],
            "series": _series(
                w,
                requests=await _daily(db, AIRun.created_at, w),
                failed=await _daily(db, AIRun.created_at, w, AIRun.status == RunStatus.failed),
                input_tokens=tokens_in,
                output_tokens=tokens_out,
            ),
        }

    # --- audit ------------------------------------------------------------------------------

    async def audit(
        self,
        *,
        action: str | None,
        actor_id: uuid.UUID | None,
        resource_id: str | None,
        result: str | None,
        q: str | None,
        since: datetime | None,
        until: datetime | None,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        where: list[ColumnElement[bool]] = []
        if action:
            where.append(
                AdminAuditEvent.action.like(action.replace("%", "") + "%")
                if action.endswith(".")
                else AdminAuditEvent.action == action
            )
        if actor_id:
            where.append(AdminAuditEvent.actor_id == actor_id)
        if resource_id:
            where.append(AdminAuditEvent.resource_id == resource_id)
        if result:
            where.append(AdminAuditEvent.result == result)
        if q:
            term = "%" + q.strip().lower().replace("%", "").replace("_", "\\_") + "%"
            where.append(
                or_(
                    func.lower(AdminAuditEvent.actor_email).like(term, escape="\\"),
                    func.lower(AdminAuditEvent.resource_label).like(term, escape="\\"),
                )
            )
        if since:
            where.append(AdminAuditEvent.created_at >= since)
        if until:
            where.append(AdminAuditEvent.created_at < until)
        total = await _count(self.db, _count_of(AdminAuditEvent, *where))
        rows = await self.db.scalars(
            select(AdminAuditEvent)
            .where(*where)
            .order_by(AdminAuditEvent.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        actions = [
            a
            for (a,) in (
                await self.db.execute(
                    select(AdminAuditEvent.action).distinct().order_by(AdminAuditEvent.action)
                )
            ).all()
        ]
        return {"items": [audit_row(e) for e in rows], "total": total, "actions": actions}


def audit_row(e: AdminAuditEvent) -> dict[str, Any]:
    return {
        "id": str(e.id),
        "created_at": e.created_at,
        "actor": {
            "id": str(e.actor_id) if e.actor_id else None,
            "email": e.actor_email,
            "role": e.actor_role,
        },
        "action": e.action,
        "resource_type": e.resource_type,
        "resource_id": e.resource_id,
        "resource_label": e.resource_label,
        "result": e.result,
        "ip": mask_ip(e.ip_address),
        "request_id": e.request_id,
        "metadata": e.metadata_,
    }


def error_type_of(result: Any) -> str:
    """A failed step's category: the provider error kind when a vendor failed, "declined" when
    a person rejected the approval, otherwise a generic step error."""
    if isinstance(result, dict):
        if result.get("declined"):
            return "declined"
        kind = result.get("kind")
        if isinstance(kind, str) and kind:
            return kind
    return "step_error"


__all__ = ["AdminAnalytics", "PlatformRole", "audit_row", "device_label", "mask_ip"]
