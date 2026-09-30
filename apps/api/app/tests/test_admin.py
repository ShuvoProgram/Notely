"""Admin dashboard: authorization, account actions, monitoring reports, settings, privacy."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.base import utcnow
from app.db.session import get_session_factory
from app.main import create_app
from app.models.admin import AdminAuditEvent, PlatformEvent
from app.models.ai import AIRun, AIThread, RunStatus
from app.models.automation import (
    Automation,
    AutomationAction,
    AutomationExecution,
    AutomationExecutionStep,
)
from app.models.user import User, UserSession
from app.tests.conftest import ORIGIN, signup

PASSWORD = "correct horse battery"


@pytest.fixture
async def other() -> AsyncIterator[AsyncClient]:
    """A second browser: its own cookie jar against the same app."""
    transport = ASGITransport(app=create_app(get_settings()))
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


async def set_role(email: str, role: str) -> None:
    async with get_session_factory()() as db:
        user = await db.scalar(select(User).where(User.email == email))
        assert user is not None
        user.role = role
        await db.commit()


async def user_id(email: str) -> str:
    async with get_session_factory()() as db:
        user = await db.scalar(select(User).where(User.email == email))
        assert user is not None
        return str(user.id)


async def audit_actions() -> list[tuple[str, str]]:
    async with get_session_factory()() as db:
        rows = await db.scalars(select(AdminAuditEvent).order_by(AdminAuditEvent.created_at))
        return [(r.action, r.result) for r in rows]


async def as_staff(client: AsyncClient, email: str, role: str) -> dict[str, Any]:
    user = await signup(client, email=email)
    await set_role(email, role)
    return user


# --- authorization ------------------------------------------------------------------------------


async def test_anonymous_and_regular_users_are_refused(
    client: AsyncClient, other: AsyncClient
) -> None:
    assert (await other.get("/api/v1/admin/overview")).status_code == 401

    await signup(client, email="regular@example.com")
    for path in (
        "/api/v1/admin/me",
        "/api/v1/admin/overview",
        "/api/v1/admin/users",
        "/api/v1/admin/automations/executions",
        "/api/v1/admin/connectors",
        "/api/v1/admin/ai",
        "/api/v1/admin/audit",
        "/api/v1/admin/settings",
    ):
        resp = await client.get(path)
        assert resp.status_code == 403, path
        assert resp.json()["error"]["code"] == "ADMIN_ONLY"
    target = await user_id("regular@example.com")
    resp = await client.post(
        f"/api/v1/admin/users/{target}/suspend", json={"reason": "nope"}, headers=ORIGIN
    )
    assert resp.status_code == 403
    resp = await client.patch(
        "/api/v1/admin/settings", json={"changes": {"maintenance_mode": True}}, headers=ORIGIN
    )
    assert resp.status_code == 403
    # Denied attempts are on the record — once per person per window, not once per request.
    assert (await audit_actions()).count(("admin.access_denied", "denied")) == 1


async def test_role_claimed_by_client_is_ignored(client: AsyncClient) -> None:
    await signup(client, email="sneaky@example.com")
    # A role in the profile update is not a field the API accepts, and headers mean nothing.
    await client.patch("/api/v1/users/me", json={"role": "admin"}, headers=ORIGIN)
    resp = await client.get("/api/v1/admin/me", headers={"X-Role": "admin"})
    assert resp.status_code == 403
    me = (await client.get("/api/v1/users/me")).json()["data"]
    assert me["role"] == "user"


async def test_staff_roles_and_permissions(client: AsyncClient) -> None:
    await as_staff(client, "viewer@example.com", "viewer")
    me = (await client.get("/api/v1/admin/me")).json()["data"]
    assert me["role"] == "viewer"
    assert me["permissions"] == ["admin:read"]
    assert (await client.get("/api/v1/admin/overview")).status_code == 200
    assert (await client.get("/api/v1/admin/settings")).status_code == 200
    resp = await client.patch(
        "/api/v1/admin/settings", json={"changes": {"signups_enabled": False}}, headers=ORIGIN
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "ADMIN_PERMISSION"
    assert ("admin.permission_denied", "denied") in await audit_actions()


async def test_admin_login_is_audited(client: AsyncClient, other: AsyncClient) -> None:
    await as_staff(client, "boss@example.com", "admin")
    resp = await other.post(
        "/api/v1/auth/login",
        json={"email": "boss@example.com", "password": PASSWORD},
        headers=ORIGIN,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["role"] == "admin"
    assert ("admin.login", "success") in await audit_actions()


async def test_old_sessions_must_reauthenticate_for_admin(client: AsyncClient) -> None:
    await as_staff(client, "old@example.com", "admin")
    async with get_session_factory()() as db:
        for session in await db.scalars(select(UserSession)):
            session.created_at = utcnow() - timedelta(hours=13)
        await db.commit()
    resp = await client.get("/api/v1/admin/overview")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "ADMIN_REAUTH_REQUIRED"
    # The ordinary app keeps working with the same (week-long) session.
    assert (await client.get("/api/v1/users/me")).status_code == 200


async def test_admin_responses_are_not_cached(client: AsyncClient) -> None:
    await as_staff(client, "cache@example.com", "admin")
    resp = await client.get("/api/v1/admin/overview")
    assert "no-store" in resp.headers["cache-control"]


# --- overview & users ---------------------------------------------------------------------------


async def test_overview_reflects_real_data(client: AsyncClient, other: AsyncClient) -> None:
    await signup(other, email="member@example.com")
    for title in ("One", "Two"):
        resp = await other.post("/api/v1/notes", json={"title": title}, headers=ORIGIN)
        assert resp.status_code == 201
    await as_staff(client, "admin@example.com", "admin")

    data = (await client.get("/api/v1/admin/overview?days=7")).json()["data"]
    assert data["users"]["total"] == 2
    assert data["users"]["new"] == 2
    assert data["users"]["active"]["day"] == 2
    assert data["users"]["staff"] == 1
    assert data["usage"]["notes_created"] == 2
    assert len(data["users"]["growth"]) == 7
    assert data["users"]["growth"][-1]["total"] == 2
    assert sum(p["notes"] for p in data["usage_series"]) == 2
    assert {u["email"] for u in data["users"]["recent"]} == {
        "member@example.com",
        "admin@example.com",
    }


async def test_user_search_filters_and_paging(client: AsyncClient, other: AsyncClient) -> None:
    await signup(other, email="zoe@example.com")
    await signup(other, email="yan@sample.org")
    await as_staff(client, "admin@example.com", "admin")

    found = (await client.get("/api/v1/admin/users?q=SAMPLE")).json()
    assert [u["email"] for u in found["data"]] == ["yan@sample.org"]
    assert found["meta"]["total"] == 1
    # LIKE wildcards in the search are literal.
    assert (await client.get("/api/v1/admin/users?q=%25")).json()["meta"]["total"] == 0
    staff = (await client.get("/api/v1/admin/users?role=staff")).json()["data"]
    assert [u["email"] for u in staff] == ["admin@example.com"]
    page = (await client.get("/api/v1/admin/users?page_size=2&sort=email")).json()
    assert page["meta"]["total"] == 3 and len(page["data"]) == 2
    assert page["data"][0]["email"] == "admin@example.com"
    assert (await client.get("/api/v1/admin/users?page_size=500")).status_code == 422
    assert (await client.get("/api/v1/admin/users?status=bogus")).status_code == 422


async def test_user_detail_never_exposes_secrets(client: AsyncClient, other: AsyncClient) -> None:
    await signup(other, email="private@example.com")
    await other.post("/api/v1/notes", json={"title": "Secret plans"}, headers=ORIGIN)
    async with get_session_factory()() as db:
        user = await db.scalar(select(User).where(User.email == "private@example.com"))
        assert user is not None
        user.totp_secret_encrypted = "gAAAAA-totp-ciphertext"
        password_hash = user.password_hash
        await db.commit()
        target = str(user.id)
    await as_staff(client, "admin@example.com", "admin")

    resp = await client.get(f"/api/v1/admin/users/{target}")
    assert resp.status_code == 200
    body = resp.text
    assert password_hash and password_hash not in body
    assert "gAAAAA" not in body
    assert "Secret plans" not in body  # usage is counted, content is not shown
    assert "token_hash" not in body
    data = resp.json()["data"]
    assert data["profile"]["two_factor_enabled"] is True
    assert data["usage"]["notes"] == 1
    assert data["sessions"] and data["sessions"][0]["ip"] in ("127.0.0.x", None, "…")
    assert (await client.get(f"/api/v1/admin/users/{uuid.uuid4()}")).status_code == 404


# --- account actions ----------------------------------------------------------------------------


async def test_suspend_and_reactivate(client: AsyncClient, other: AsyncClient) -> None:
    await signup(other, email="member@example.com")
    target = await user_id("member@example.com")
    await as_staff(client, "support@example.com", "support")

    resp = await client.post(
        f"/api/v1/admin/users/{target}/suspend",
        json={"reason": "Spam reports"},
        headers=ORIGIN,
    )
    assert resp.status_code == 200, resp.text
    # Their open session is gone and they can't sign back in.
    assert (await other.get("/api/v1/users/me")).status_code == 401
    login = await other.post(
        "/api/v1/auth/login",
        json={"email": "member@example.com", "password": PASSWORD},
        headers=ORIGIN,
    )
    assert login.json()["error"]["code"] == "ACCOUNT_DISABLED"
    again = await client.post(
        f"/api/v1/admin/users/{target}/suspend", json={"reason": "twice"}, headers=ORIGIN
    )
    assert again.status_code == 409

    detail = (await client.get(f"/api/v1/admin/users/{target}")).json()["data"]
    assert detail["profile"]["is_active"] is False
    assert detail["profile"]["suspension_reason"] == "Spam reports"
    assert detail["admin_actions"][0]["action"] == "user.suspend"
    kinds = {e["kind"] for e in detail["security_events"]}
    assert {"account.suspended", "auth.sign_in_blocked"} <= kinds

    resp = await client.post(f"/api/v1/admin/users/{target}/reactivate", headers=ORIGIN)
    assert resp.status_code == 200
    login = await other.post(
        "/api/v1/auth/login",
        json={"email": "member@example.com", "password": PASSWORD},
        headers=ORIGIN,
    )
    assert login.status_code == 200
    assert [a for a in await audit_actions() if a[0].startswith("user.")] == [
        ("user.suspend", "success"),
        ("user.reactivate", "success"),
    ]


async def test_suspend_requires_a_reason(client: AsyncClient, other: AsyncClient) -> None:
    await signup(other, email="member@example.com")
    target = await user_id("member@example.com")
    await as_staff(client, "admin@example.com", "admin")
    resp = await client.post(
        f"/api/v1/admin/users/{target}/suspend", json={"reason": ""}, headers=ORIGIN
    )
    assert resp.status_code == 422


async def test_account_action_guard_rails(client: AsyncClient, other: AsyncClient) -> None:
    await as_staff(other, "chief@example.com", "admin")
    chief = await user_id("chief@example.com")
    await as_staff(client, "helper@example.com", "support")
    helper = await user_id("helper@example.com")

    # Support can't act on an admin, nor on themselves, nor change roles.
    resp = await client.post(
        f"/api/v1/admin/users/{chief}/suspend", json={"reason": "coup"}, headers=ORIGIN
    )
    assert resp.status_code == 403
    resp = await client.post(f"/api/v1/admin/users/{helper}/sessions/revoke", headers=ORIGIN)
    assert resp.json()["error"]["code"] == "SELF_ACTION"
    resp = await client.patch(
        f"/api/v1/admin/users/{helper}/role", json={"role": "admin"}, headers=ORIGIN
    )
    assert resp.status_code == 403

    # The only admin can't be suspended or demoted, even by an admin... who can't target
    # themselves anyway.
    resp = await other.patch(
        f"/api/v1/admin/users/{chief}/role", json={"role": "user"}, headers=ORIGIN
    )
    assert resp.json()["error"]["code"] == "SELF_ACTION"


async def test_role_changes(client: AsyncClient, other: AsyncClient) -> None:
    await as_staff(client, "admin@example.com", "admin")
    await signup(other, email="member@example.com")
    target = await user_id("member@example.com")

    resp = await client.patch(
        f"/api/v1/admin/users/{target}/role", json={"role": "support"}, headers=ORIGIN
    )
    assert resp.json()["data"]["role"] == "support"
    assert (await other.get("/api/v1/admin/me")).json()["data"]["role"] == "support"
    assert (
        await client.patch(
            f"/api/v1/admin/users/{target}/role", json={"role": "owner"}, headers=ORIGIN
        )
    ).status_code == 422

    # A demotion ends their sessions immediately.
    resp = await client.patch(
        f"/api/v1/admin/users/{target}/role", json={"role": "user"}, headers=ORIGIN
    )
    assert resp.status_code == 200
    assert (await other.get("/api/v1/admin/me")).status_code == 401

    async with get_session_factory()() as db:
        row = await db.scalar(
            select(AdminAuditEvent)
            .where(AdminAuditEvent.action == "user.role_change")
            .order_by(AdminAuditEvent.created_at.desc())
        )
        assert (
            row is not None and row.metadata_["from"] == "support" and row.metadata_["to"] == "user"
        )


async def test_last_admin_cannot_be_removed(client: AsyncClient) -> None:
    """Only reachable in a race (an admin acting on another admin means two exist), so the
    guard is exercised at the service: the actor's rights are checked, then the count."""
    from fastapi import Request

    from app.core.exceptions import Conflict
    from app.services.admin_users import AdminUserService

    await as_staff(client, "only@example.com", "admin")
    request = Request({"type": "http", "headers": [], "client": ("127.0.0.1", 1)})
    async with get_session_factory()() as db:
        target = await db.scalar(select(User).where(User.email == "only@example.com"))
        assert target is not None
        ghost = User(id=uuid.uuid4(), email="ghost@example.com", role="admin", display_name="g")
        service = AdminUserService(db)
        with pytest.raises(Conflict):
            await service.change_role(ghost, target, role="user", request=request)
        with pytest.raises(Conflict):
            await service.suspend(
                ghost, target, reason="gone", revoke_sessions=True, request=request
            )


# --- settings & enforcement ---------------------------------------------------------------------


async def test_settings_update_is_validated_audited_and_enforced(
    client: AsyncClient, other: AsyncClient
) -> None:
    await as_staff(client, "admin@example.com", "admin")
    await signup(other, email="member@example.com")

    bad = await client.patch(
        "/api/v1/admin/settings", json={"changes": {"nope": 1}}, headers=ORIGIN
    )
    assert bad.status_code == 422
    bad = await client.patch(
        "/api/v1/admin/settings",
        json={"changes": {"automations_max_per_user": -3}},
        headers=ORIGIN,
    )
    assert bad.status_code == 422

    resp = await client.patch(
        "/api/v1/admin/settings",
        json={"changes": {"maintenance_mode": True, "maintenance_message": "Back at 5pm"}},
        headers=ORIGIN,
    )
    assert resp.status_code == 200
    values = {s["key"]: s["value"] for s in resp.json()["data"]["settings"]}
    assert values["maintenance_mode"] is True

    status = (await other.get("/api/v1/system/status")).json()["data"]
    assert status["maintenance"] == {"enabled": True, "message": "Back at 5pm"}
    blocked = await other.post("/api/v1/notes", json={"title": "x"}, headers=ORIGIN)
    assert blocked.status_code == 503
    assert blocked.json()["error"]["message"] == "Back at 5pm"
    assert (await other.get("/api/v1/notes")).status_code == 200  # reads still work
    # The admin can always switch it back off.
    resp = await client.patch(
        "/api/v1/admin/settings", json={"changes": {"maintenance_mode": False}}, headers=ORIGIN
    )
    assert resp.status_code == 200
    assert (
        await other.post("/api/v1/notes", json={"title": "x"}, headers=ORIGIN)
    ).status_code == 201

    await client.patch(
        "/api/v1/admin/settings", json={"changes": {"signups_enabled": False}}, headers=ORIGIN
    )
    async with AsyncClient(
        transport=ASGITransport(app=create_app(get_settings())), base_url="http://testserver"
    ) as third:
        resp = await third.post(
            "/api/v1/auth/signup",
            json={"email": "late@example.com", "password": PASSWORD, "display_name": "Late"},
            headers=ORIGIN,
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "SIGNUPS_DISABLED"

    changed = [a for a in await audit_actions() if a[0] == "settings.update"]
    assert len(changed) == 4  # maintenance on, message, maintenance off, sign-ups off

    # Environment facts are shown without any secret.
    env = (await client.get("/api/v1/admin/settings")).json()["data"]["environment"]
    text = str(env)
    assert get_settings().session_secret not in text
    assert get_settings().encryption_key not in text


async def test_ai_feature_flag_and_daily_limit(client: AsyncClient, other: AsyncClient) -> None:
    await as_staff(client, "admin@example.com", "admin")
    member = await signup(other, email="member@example.com")

    await client.patch(
        "/api/v1/admin/settings", json={"changes": {"ai_enabled": False}}, headers=ORIGIN
    )
    resp = await other.post("/api/v1/ai/chat", json={"message": "hi"}, headers=ORIGIN)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FEATURE_DISABLED"

    await client.patch(
        "/api/v1/admin/settings",
        json={"changes": {"ai_enabled": True, "ai_daily_requests_per_user": 1}},
        headers=ORIGIN,
    )
    async with get_session_factory()() as db:
        thread = AIThread(tenant_id=uuid.UUID(member["tenant_id"]), user_id=uuid.UUID(member["id"]))
        db.add(thread)
        await db.flush()
        db.add(
            AIRun(
                tenant_id=thread.tenant_id,
                user_id=thread.user_id,
                thread_id=thread.id,
                status=RunStatus.completed,
                created_at=utcnow(),
            )
        )
        await db.commit()
    resp = await other.post("/api/v1/ai/chat", json={"message": "hi"}, headers=ORIGIN)
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "AI_DAILY_LIMIT"


# --- monitoring ---------------------------------------------------------------------------------


async def _seed_executions(owner: dict[str, Any]) -> tuple[str, str]:
    now = utcnow()
    async with get_session_factory()() as db:
        automation = Automation(
            tenant_id=uuid.UUID(owner["tenant_id"]),
            user_id=uuid.UUID(owner["id"]),
            name="Daily digest",
            action=AutomationAction.workflow,
            schedule_kind="daily",
        )
        db.add(automation)
        await db.flush()
        ok_run = AutomationExecution(
            automation_id=automation.id,
            occurrence_at=now - timedelta(hours=2),
            status="completed",
            attempts=1,
            started_at=now - timedelta(hours=2),
            finished_at=now - timedelta(hours=2) + timedelta(seconds=3),
        )
        bad_run = AutomationExecution(
            automation_id=automation.id,
            occurrence_at=now - timedelta(hours=1),
            status="failed",
            attempts=2,
            error="Search Gmail: Gmail needs you to reconnect",
            started_at=now - timedelta(hours=1),
            finished_at=now - timedelta(hours=1) + timedelta(seconds=1),
        )
        db.add_all([ok_run, bad_run])
        await db.flush()
        db.add(
            AutomationExecutionStep(
                execution_id=bad_run.id,
                step_id="find",
                position=0,
                kind="gmail.search_emails",
                status="failed",
                input={"query": "from:ceo@example.com"},
                output={"emails": ["confidential"]},
                result={"kind": "auth_failed"},
                error="Gmail needs you to reconnect",
                attempts=2,
            )
        )
        db.add(
            AutomationExecutionStep(
                execution_id=ok_run.id,
                step_id="note",
                position=0,
                kind="notely.create_note",
                status="completed",
                attempts=1,
            )
        )
        await db.commit()
        return str(automation.id), str(bad_run.id)


async def test_automation_monitoring(client: AsyncClient, other: AsyncClient) -> None:
    owner = await signup(other, email="owner@example.com")
    automation_id, bad_run = await _seed_executions(owner)
    await as_staff(client, "viewer@example.com", "viewer")

    summary = (await client.get("/api/v1/admin/automations/summary?days=7")).json()["data"]
    assert summary["executions"]["total"] == 2
    assert summary["executions"]["failed"] == 1
    assert summary["executions"]["success_rate"] == 50.0
    assert summary["executions"]["retried"] == 1
    assert summary["executions"]["duration"]["count"] == 2
    assert summary["top_failing"][0]["name"] == "Daily digest"
    assert summary["failures_by_error"] == [{"error_type": "auth_failed", "count": 1}]
    assert summary["failures_by_connector"][0]["connector"] == "gmail"

    def ids(resp: Any) -> list[str]:
        return [e["id"] for e in resp.json()["data"]]

    base = "/api/v1/admin/automations/executions"
    assert len(ids(await client.get(base))) == 2
    assert ids(await client.get(f"{base}?status=failed")) == [bad_run]
    assert len(ids(await client.get(f"{base}?status=succeeded"))) == 1
    assert ids(await client.get(f"{base}?connector=gmail")) == [bad_run]
    assert ids(await client.get(f"{base}?connector=slack")) == []
    assert ids(await client.get(f"{base}?error_type=auth_failed")) == [bad_run]
    assert ids(await client.get(f"{base}?error_type=rate_limited")) == []
    assert len(ids(await client.get(f"{base}?user_id={owner['id']}"))) == 2
    assert len(ids(await client.get(f"{base}?automation_id={automation_id}"))) == 2
    today = utcnow().date().isoformat()
    assert len(ids(await client.get(f"{base}?from={today}&to={today}"))) == 2
    assert ids(await client.get(f"{base}?from=2000-01-01&to=2000-01-02")) == []
    assert (await client.get(f"{base}?connector=gm%25")).status_code == 422

    row = (await client.get(f"{base}?status=failed")).json()["data"][0]
    assert row["error_type"] == "auth_failed"
    assert row["connectors"] == ["gmail"]
    assert row["attempts"] == 2
    assert row["duration_ms"] == 1000

    detail = await client.get(f"{base}/{bad_run}")
    assert detail.status_code == 200
    step = detail.json()["data"]["steps"][0]
    assert step["input_fields"] == ["query"]
    assert step["error_type"] == "auth_failed"
    # Technical detail without the people's data the step handled.
    assert "ceo@example.com" not in detail.text
    assert "confidential" not in detail.text


async def test_connector_and_ai_reports(client: AsyncClient, other: AsyncClient) -> None:
    member = await signup(other, email="member@example.com")
    async with get_session_factory()() as db:
        thread = AIThread(tenant_id=uuid.UUID(member["tenant_id"]), user_id=uuid.UUID(member["id"]))
        db.add(thread)
        await db.flush()
        now = utcnow()
        db.add_all(
            [
                AIRun(
                    tenant_id=thread.tenant_id,
                    user_id=thread.user_id,
                    thread_id=thread.id,
                    status=RunStatus.completed,
                    model="notely-default",
                    provider="anthropic",
                    token_usage={"input_tokens": 100, "output_tokens": 40},
                    created_at=now - timedelta(minutes=5),
                    started_at=now - timedelta(minutes=5),
                    completed_at=now - timedelta(minutes=5) + timedelta(seconds=2),
                ),
                AIRun(
                    tenant_id=thread.tenant_id,
                    user_id=thread.user_id,
                    thread_id=thread.id,
                    status=RunStatus.failed,
                    model="notely-default",
                    provider="anthropic",
                    error="The model provider rejected the key.",
                    created_at=now - timedelta(minutes=1),
                ),
                PlatformEvent(
                    category="error",
                    kind="oauth_failed",
                    source="slack",
                    message="Authorization denied",
                    metadata_={},
                    occurred_at=now,
                ),
            ]
        )
        await db.commit()
    await as_staff(client, "admin@example.com", "admin")

    ai = (await client.get("/api/v1/admin/ai?days=7")).json()["data"]
    assert ai["requests"]["total"] == 2
    assert ai["requests"]["failed"] == 1
    assert ai["tokens"] == {"input": 100, "output": 40, "runs_without_usage": 1}
    assert ai["latency"]["count"] == 1 and ai["latency"]["avg_ms"] == 2000
    assert ai["by_model"][0] == {
        "provider": "anthropic",
        "model": "notely-default",
        "requests": 2,
        "failed": 1,
        "input_tokens": 100,
        "output_tokens": 40,
    }
    assert ai["cost"]["tracked"] is False
    assert ai["top_users"][0]["user"]["email"] == "member@example.com"

    connectors = (await client.get("/api/v1/admin/connectors?days=7")).json()["data"]
    slack = next(c for c in connectors if c["provider"] == "slack")
    assert slack["oauth_failures"] == 1
    # Observed failures outrank "no OAuth app configured on this deployment".
    assert slack["health"] == "degraded"
    assert "access_token" not in str(connectors)
    detail = (await client.get("/api/v1/admin/connectors/slack")).json()["data"]
    assert detail["auth_events"][0]["kind"] == "oauth_failed"

    resp = await client.patch(
        "/api/v1/admin/connectors/slack", json={"enabled": False}, headers=ORIGIN
    )
    assert resp.json()["data"]["enabled"] is False
    assert ("connector.disable", "success") in await audit_actions()
    assert (
        await client.patch("/api/v1/admin/connectors/nope", json={"enabled": False}, headers=ORIGIN)
    ).status_code == 404

    audit = (await client.get("/api/v1/admin/audit?action=connector.")).json()
    assert audit["meta"]["total"] == 1
    assert audit["data"][0]["resource_id"] == "slack"


async def test_failed_jobs_and_sign_ins_are_recorded(client: AsyncClient) -> None:
    from app.workers.instrument import instrumented

    async def exploding_job(_: dict[str, Any]) -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await instrumented(exploding_job)({"job_try": 1, "job_id": "abc"})

    await signup(client, email="member@example.com")
    await client.post("/api/v1/auth/logout", headers=ORIGIN)
    await client.post(
        "/api/v1/auth/login",
        json={"email": "member@example.com", "password": "wrong password!!"},
        headers=ORIGIN,
    )
    async with get_session_factory()() as db:
        kinds = [(e.kind, e.source) for e in await db.scalars(select(PlatformEvent))]
    assert ("job_failed", "exploding_job") in kinds
    assert ("auth.sign_in", None) in kinds
    assert ("auth.sign_in_failed", "password") in kinds
