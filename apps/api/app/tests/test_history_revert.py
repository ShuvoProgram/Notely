"""Change journal + batch revert for AI runs and automation runs."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from langchain_core.messages import AIMessage
from sqlalchemy import select

from app.ai.llm import set_fake_script
from app.core.config import get_settings
from app.db.base import utcnow
from app.db.session import get_session_factory
from app.main import create_app
from app.models.journal import ActionRecord
from app.models.user import User
from app.tests.conftest import ORIGIN, read_sse, signup
from app.tests.test_ai import chat, tool_call
from app.tests.test_automations import action, create, run


@pytest.fixture
async def other() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=create_app(get_settings()))
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        await signup(c, email="eve@example.com")
        yield c


async def tasks(client: AsyncClient) -> dict[str, dict[str, Any]]:
    return {t["title"]: t for t in (await client.get("/api/v1/tasks")).json()["data"]}


async def history(client: AsyncClient) -> list[dict[str, Any]]:
    resp = await client.get("/api/v1/history")
    assert resp.status_code == 200, resp.text
    data: list[dict[str, Any]] = resp.json()["data"]
    return data


async def revert(client: AsyncClient, batch: dict[str, Any], **extra: Any) -> Any:
    return await client.post(
        f"/api/v1/history/{batch['kind']}/{batch['batch_id']}/revert",
        json={"confirm": True, **extra},
        headers=ORIGIN,
    )


async def approved_ai_run(client: AsyncClient, calls: list[dict[str, Any]]) -> None:
    set_fake_script([AIMessage(content="", tool_calls=calls), AIMessage(content="Done.")])
    events = await chat(client, "Plan my launch")
    approval = next(e for e in events if e["type"] == "approval_required")
    set_fake_script([AIMessage(content="Done.")])
    resp = await client.post(
        "/api/v1/ai/approve",
        json={
            "run_id": approval["run_id"],
            "approval_id": approval["approval_id"],
            "approved_call_ids": [c["id"] for c in calls],
        },
        headers=ORIGIN,
    )
    assert resp.status_code == 200
    await read_sse(resp)


async def test_ai_batch_preview_revert_and_history(client: AsyncClient, other: AsyncClient) -> None:
    await signup(client)
    existing = (
        await client.post("/api/v1/tasks", json={"title": "Existing"}, headers=ORIGIN)
    ).json()["data"]
    # Edits made in the UI are not part of any batch.
    assert await history(client) == []

    await approved_ai_run(
        client,
        [
            tool_call("create_task", {"title": "Draft pricing page"}, "c1"),
            tool_call("create_task", {"title": "Email the team"}, "c2"),
            tool_call("complete_task", {"task_id": existing["id"]}, "c3"),
        ],
    )
    assert (await tasks(client))["Existing"]["status"] == "done"

    [batch] = await history(client)
    assert batch["kind"] == "ai_run" and batch["source"] == "AI Assistant"
    assert [s["text"] for s in batch["summary"]] == ["2 tasks created", "1 task completed"]
    assert batch["revert"] is None and batch["reversible_count"] == 3

    preview = (await client.get(f"/api/v1/history/{batch['kind']}/{batch['batch_id']}")).json()[
        "data"
    ]["preview"]
    assert [s["text"] for s in preview["will_revert"]] == ["2 tasks created", "1 task completed"]
    assert preview["will_leave"] == [] and preview["cannot_revert"] == []

    # Other people can neither see nor revert it.
    assert (
        await other.get(f"/api/v1/history/{batch['kind']}/{batch['batch_id']}")
    ).status_code == 404
    assert (await revert(other, batch)).status_code == 404
    # Reverting needs an explicit confirmation.
    unconfirmed = await client.post(
        f"/api/v1/history/{batch['kind']}/{batch['batch_id']}/revert",
        json={"confirm": False},
        headers=ORIGIN,
    )
    assert unconfirmed.status_code == 422

    done = await revert(client, batch)
    assert done.status_code == 200, done.text
    result = done.json()["data"]
    assert result["revert"]["status"] == "reverted"
    assert result["revert"]["summary"]["reverted"] == 3
    assert {c["status"] for c in result["changes"]} == {"reverted"}
    after = await tasks(client)
    assert set(after) == {"Existing"} and after["Existing"]["status"] == "open"

    # History keeps the entry, marked reverted; a second revert does nothing.
    [kept] = await history(client)
    assert kept["revert"]["status"] == "reverted" and kept["revert"]["requested_by"] == "Ada"
    again = await revert(client, batch)
    assert again.status_code == 409 and again.json()["error"]["code"] == "ALREADY_REVERTED"
    assert set(await tasks(client)) == {"Existing"}


async def test_changes_made_after_the_run_are_left_alone(client: AsyncClient) -> None:
    await signup(client)
    await approved_ai_run(client, [tool_call("create_task", {"title": "Call Sam"}, "c1")])
    task = (await tasks(client))["Call Sam"]
    await client.patch(
        f"/api/v1/tasks/{task['id']}", json={"title": "Call Sam today"}, headers=ORIGIN
    )

    [batch] = await history(client)
    preview = (await client.get(f"/api/v1/history/{batch['kind']}/{batch['batch_id']}")).json()[
        "data"
    ]["preview"]
    assert preview["will_revert"] == []
    assert "changed after this run" in preview["will_leave"][0]["reason"]

    result = (await revert(client, batch)).json()["data"]
    assert result["revert"]["summary"]["skipped"] == 1
    assert result["changes"][0]["status"] == "revert_skipped"
    assert "Call Sam today" in await tasks(client)


async def test_automation_run_revert(client: AsyncClient) -> None:
    await signup(client)
    automation = await create(
        client,
        [
            action("task", "notely.create_task", {"title": "Weekly review"}),
            action(
                "note", "notely.create_note", {"title": "Weekly summary", "content": "All good"}
            ),
        ],
    )
    detail = await run(client, automation["id"])
    assert detail["status"] == "completed", detail
    assert "Weekly review" in await tasks(client)

    [batch] = await history(client)
    assert batch["kind"] == "automation_run" and batch["title"] == "Test automation"
    assert sorted(s["text"] for s in batch["summary"]) == [
        "1 Notely note created",
        "1 task created",
    ]
    result = (await revert(client, batch)).json()["data"]
    assert result["revert"]["status"] == "reverted"
    assert "Weekly review" not in await tasks(client)
    # A created note goes to the trash (restorable), never straight to permanent deletion.
    trash = (await client.get("/api/v1/notes", params={"view": "trash"})).json()["data"]
    assert [n["title"] for n in trash] == ["Weekly summary"]


async def test_date_and_note_edits_restore_previous_values(client: AsyncClient) -> None:
    """Service-level: a batch that changes a task date and rewrites a note."""
    from app.schemas.notes import NoteUpdate
    from app.schemas.tasks import TaskUpdate
    from app.services import action_journal as journal
    from app.services.note_service import NoteService
    from app.services.task_service import TaskService

    await signup(client)
    task = (
        await client.post(
            "/api/v1/tasks", json={"title": "Ship", "due_date": "2026-10-01"}, headers=ORIGIN
        )
    ).json()["data"]
    note = (await client.post("/api/v1/notes", json={"title": "Plan"}, headers=ORIGIN)).json()[
        "data"
    ]
    body = {
        "type": "doc",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": "AI text"}]}],
    }
    batch_id = uuid.uuid4()
    async with get_session_factory()() as db:
        user = await db.scalar(select(User))
        assert user is not None
        with journal.batch("ai_run", batch_id, user):
            await TaskService(db).update(
                user, uuid.UUID(task["id"]), TaskUpdate.model_validate({"due_date": "2026-10-09"})
            )
            await NoteService(db).update_note(
                user, uuid.UUID(note["id"]), NoteUpdate(title="Plan v2", content_json=body)
            )

    [batch] = await history(client)
    assert [s["text"] for s in batch["summary"]] == ["1 task date changed", "1 Notely note updated"]
    result = (await revert(client, batch)).json()["data"]
    assert result["revert"]["summary"]["reverted"] == 2
    assert (await tasks(client))["Ship"]["due_date"] == "2026-10-01"
    restored = (await client.get(f"/api/v1/notes/{note['id']}")).json()["data"]
    assert restored["title"] == "Plan" and "AI text" not in restored["plain_text"]
    # The overwritten state is kept in version history, so the revert can itself be undone.
    versions = (await client.get(f"/api/v1/notes/{note['id']}/versions")).json()["data"]
    assert any(v["reason"] == "before_revert" and v["title"] == "Plan v2" for v in versions)


async def test_irreversible_and_failed_changes_are_reported(client: AsyncClient) -> None:
    await signup(client)
    batch_id = uuid.uuid4()
    async with get_session_factory()() as db:
        user = await db.scalar(select(User))
        assert user is not None
        common = {
            "tenant_id": user.tenant_id,
            "user_id": user.id,
            "batch_kind": "ai_run",
            "batch_id": batch_id,
            "status": "applied",
            "revert_attempts": 0,
            "created_at": utcnow(),
        }
        db.add_all(
            [
                ActionRecord(
                    **common,
                    sequence=1,
                    provider="gmail",
                    kind="gmail.send_mail",
                    resource_type="send_mail",
                    label="Send email “Hi” to a@b.c",
                    reversible=False,
                    irreversible_reason="An email that was sent can't be recalled.",
                ),
                ActionRecord(
                    **common,
                    sequence=2,
                    provider="gmail",
                    kind="gmail.draft_mail",
                    resource_type="draft_mail",
                    resource_id="d1",
                    label="Draft email “Follow-up”",
                    reversible=True,
                    revert_ref={"tool": "gmail__draft_mail", "draft_id": "d1"},
                ),
            ]
        )
        await db.commit()

    [batch] = await history(client)
    preview = (await client.get(f"/api/v1/history/{batch['kind']}/{batch['batch_id']}")).json()[
        "data"
    ]["preview"]
    assert preview["cannot_revert"][0]["reason"] == "An email that was sent can't be recalled."
    assert [s["text"] for s in preview["will_revert"]] == ["1 Gmail draft created"]

    # Gmail isn't connected, so the draft can't be deleted: reported, not faked.
    result = (await revert(client, batch)).json()["data"]
    assert result["revert"]["status"] == "failed"
    assert result["revert"]["summary"] == {
        "reverted": 0,
        "skipped": 0,
        "failed": 1,
        "not_reversible": 1,
        "last_attempt": {"reverted": 0, "skipped": 0, "failed": 1, "not_reversible": 1},
    }
    draft = next(c for c in result["changes"] if c["kind"] == "gmail.draft_mail")
    assert draft["status"] == "revert_failed" and "isn't connected" in draft["revert_note"]
    # A failed revert is retried explicitly; a plain second click is refused.
    plain = await revert(client, batch)
    assert plain.status_code == 409 and plain.json()["error"]["code"] == "REVERT_NEEDS_RETRY"
    retried = (await revert(client, batch, retry=True)).json()["data"]
    assert retried["revert"]["attempts"] == 2
    assert (
        next(c for c in retried["changes"] if c["kind"] == "gmail.draft_mail")["revert_attempts"]
        == 2
    )


async def test_concurrent_revert_is_refused_and_stale_one_resumes(client: AsyncClient) -> None:
    from datetime import timedelta

    from app.models.journal import BatchRevert

    await signup(client)
    await approved_ai_run(client, [tool_call("create_task", {"title": "Once"}, "c1")])
    [batch] = await history(client)
    async with get_session_factory()() as db:
        user = await db.scalar(select(User))
        assert user is not None
        claim = BatchRevert(
            tenant_id=user.tenant_id,
            user_id=user.id,
            batch_kind=batch["kind"],
            batch_id=uuid.UUID(batch["batch_id"]),
            status="running",
            requested_by=user.id,
            attempts=1,
            summary={},
            requested_at=utcnow(),
        )
        db.add(claim)
        await db.commit()
        # Another tab's revert is mid-flight: this click must not run it a second time.
        busy = await revert(client, batch)
        assert busy.status_code == 409 and busy.json()["error"]["code"] == "REVERT_IN_PROGRESS"
        assert "Once" in await tasks(client)
        # That revert crashed long ago: the next click picks it up.
        claim.requested_at = utcnow() - timedelta(hours=1)
        await db.commit()
    resumed = await revert(client, batch)
    assert resumed.status_code == 200
    assert resumed.json()["data"]["revert"]["status"] == "reverted"
    assert "Once" not in await tasks(client)
