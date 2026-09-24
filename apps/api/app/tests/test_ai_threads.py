"""Concurrent, independent AI conversations: isolation, cancellation, recovery and retries.

The scripted model streams word by word (`ai_fake_stream_delay_ms`) so runs genuinely overlap.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from langchain_core.messages import AIMessage
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.ai.llm import ScriptedChatModel, captured_prompts, set_fake_script
from app.ai.streams import hub
from app.core.config import get_settings
from app.core.kv import kv
from app.db.base import utcnow
from app.db.session import configure_database, dispose_engine, get_session_factory
from app.models import Base
from app.models.ai import AIRun, RunStatus
from app.tests.conftest import ORIGIN, read_sse, signup
from app.workers import queue

REPLY = "one two three four five six seven eight nine ten eleven twelve"


@pytest.fixture(autouse=True)
async def _database(tmp_path: Path) -> AsyncIterator[None]:
    """Overrides the shared fixture. Runs here overlap, each with its own DB session, and the
    default single shared in-memory connection cannot keep those sessions apart (one session's
    pool reset rolls back another's work). A file database gives each session a real
    connection, as Postgres does in production."""
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'ai.db'}",
        poolclass=NullPool,
        connect_args={"timeout": 30},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _pragmas(dbapi_conn, _record):  # type: ignore[no-untyped-def]
        dbapi_conn.execute("PRAGMA foreign_keys=ON")
        dbapi_conn.execute("PRAGMA journal_mode=WAL")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    configure_database(engine)
    kv.reset()
    kv.force_memory()
    queue.reset()
    queue.force_memory()
    yield
    await dispose_engine()


@pytest.fixture(autouse=True)
def _slow_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "ai_fake_stream_delay_ms", 20)


@pytest.fixture(autouse=True)
async def _no_leftover_runs() -> AsyncIterator[None]:
    yield
    await hub.shutdown()


async def new_thread(client: AsyncClient, title: str | None = None) -> str:
    resp = await client.post("/api/v1/ai/threads", json={"title": title}, headers=ORIGIN)
    assert resp.status_code == 201, resp.text
    return str(resp.json()["data"]["id"])


async def send(client: AsyncClient, thread_id: str, message: str, **extra: Any) -> Any:
    return await client.post(
        "/api/v1/ai/chat",
        json={"message": message, "thread_id": thread_id, **extra},
        headers=ORIGIN,
    )


async def events_of(resp: Any) -> list[dict[str, Any]]:
    assert resp.status_code == 200, resp.text
    return await read_sse(resp)


async def wait_until_running(client: AsyncClient, thread_id: str) -> str:
    for _ in range(200):
        detail = (await client.get(f"/api/v1/ai/threads/{thread_id}")).json()["data"]
        if detail["active_run"] and detail["active_run"]["status"] == "running":
            return str(detail["active_run"]["id"])
        await asyncio.sleep(0.01)
    raise AssertionError("run never started")


def tokens(events: list[dict[str, Any]]) -> str:
    return "".join(e["text"] for e in events if e["type"] == "token")


async def test_two_conversations_stream_at_once_without_mixing(client: AsyncClient) -> None:
    await signup(client)
    set_fake_script([AIMessage(content=REPLY)])
    a, b = await new_thread(client), await new_thread(client)

    ra, rb = await asyncio.gather(
        send(client, a, "Question for A about apples"),
        send(client, b, "Question for B about bananas"),
    )
    ea, eb = await events_of(ra), await events_of(rb)

    # Every event is labelled with its own conversation, in order, with no gaps.
    assert {e["thread_id"] for e in ea} == {a} and {e["thread_id"] for e in eb} == {b}
    assert [e["seq"] for e in ea] == list(range(len(ea)))
    assert len({e["run_id"] for e in ea}) == 1 and ea[0]["run_id"] != eb[0]["run_id"]
    # Both really streamed (many token events each) and both completed.
    assert tokens(ea).strip() == REPLY and tokens(eb).strip() == REPLY
    assert sum(e["type"] == "token" for e in ea) == len(REPLY.split())
    # ...and overlapped in time: B started before A finished.
    runs = {r["thread_id"]: r for r in (await client.get("/api/v1/ai/runs")).json()["data"]}
    assert runs[b]["started_at"] < runs[a]["completed_at"]
    assert runs[a]["started_at"] < runs[b]["completed_at"]
    assert ea[-1]["status"] == "completed" and eb[-1]["status"] == "completed"

    # Context isolation: every prompt the model saw holds only one conversation's messages.
    for prompt in captured_prompts:
        humans = " ".join(str(m.content) for m in prompt if m.type == "human")
        assert ("apples" in humans) != ("bananas" in humans)

    for tid, word in ((a, "apples"), (b, "bananas")):
        detail = (await client.get(f"/api/v1/ai/threads/{tid}")).json()["data"]
        assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
        assert word in detail["messages"][0]["content"]
        assert detail["active_run"] is None and detail["last_run"]["status"] == "completed"


async def test_cancelling_one_conversation_leaves_the_other_running(client: AsyncClient) -> None:
    await signup(client)
    set_fake_script([AIMessage(content=" ".join([REPLY] * 4))])
    a, b = await new_thread(client), await new_thread(client)

    task_a = asyncio.create_task(send(client, a, "long answer please"))
    run_a = await wait_until_running(client, a)
    task_b = asyncio.create_task(send(client, b, "and another"))
    await wait_until_running(client, b)

    cancelled = await client.post(f"/api/v1/ai/runs/{run_a}/cancel", headers=ORIGIN)
    assert cancelled.status_code == 200
    ea, eb = await events_of(await task_a), await events_of(await task_b)

    assert ea[-1]["type"] == "done" and ea[-1]["status"] == "cancelled"
    assert "message" not in [e["type"] for e in ea]
    assert eb[-1]["status"] == "completed" and tokens(eb).strip() == " ".join([REPLY] * 4)

    detail_a = (await client.get(f"/api/v1/ai/threads/{a}")).json()["data"]
    assert [m["role"] for m in detail_a["messages"]] == ["user"]
    assert detail_a["last_run"]["status"] == "cancelled"
    # The stopped conversation accepts the next message right away.
    again = await events_of(await send(client, a, "short one then"))
    assert again[-1]["status"] == "completed"


async def test_one_open_run_per_conversation(client: AsyncClient) -> None:
    await signup(client)
    set_fake_script([AIMessage(content=REPLY)])
    a = await new_thread(client)
    first = asyncio.create_task(send(client, a, "first"))
    await wait_until_running(client, a)

    second = await send(client, a, "second, too soon")
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "RUN_IN_PROGRESS"
    assert (await events_of(await first))[-1]["status"] == "completed"
    detail = (await client.get(f"/api/v1/ai/threads/{a}")).json()["data"]
    assert [m["content"] for m in detail["messages"] if m["role"] == "user"] == ["first"]


async def test_a_failure_stays_in_its_conversation(client: AsyncClient) -> None:
    await signup(client)
    set_fake_script([AIMessage(content=REPLY)])
    a, b = await new_thread(client), await new_thread(client)
    ra, rb = await asyncio.gather(send(client, a, "!fail on purpose"), send(client, b, "fine"))
    ea, eb = await events_of(ra), await events_of(rb)

    assert [e["type"] for e in ea][-2:] == ["error", "done"] and ea[-1]["status"] == "failed"
    assert all(e["thread_id"] == a for e in ea)
    assert eb[-1]["status"] == "completed" and "error" not in [e["type"] for e in eb]
    detail = (await client.get(f"/api/v1/ai/threads/{a}")).json()["data"]
    assert detail["last_run"]["status"] == "failed" and detail["active_run"] is None


async def test_retry_answers_the_last_message_without_repeating_it(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await signup(client)
    set_fake_script([AIMessage(content="Recovered answer")])
    a = await new_thread(client)
    original = ScriptedChatModel._generate
    calls = {"n": 0}

    def flaky(self: ScriptedChatModel, messages: Any, *args: Any, **kwargs: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("provider hiccup")
        return original(self, messages, *args, **kwargs)

    monkeypatch.setattr(ScriptedChatModel, "_generate", flaky)
    failed = await events_of(await send(client, a, "What is on my plate?"))
    assert failed[-1]["status"] == "failed"

    retried = await client.post(
        "/api/v1/ai/chat", json={"thread_id": a, "retry": True}, headers=ORIGIN
    )
    events = await events_of(retried)
    assert events[-1]["status"] == "completed"
    detail = (await client.get(f"/api/v1/ai/threads/{a}")).json()["data"]
    assert [(m["role"], m["content"]) for m in detail["messages"]] == [
        ("user", "What is on my plate?"),
        ("assistant", "Recovered answer"),
    ]
    # The model saw the question exactly once.
    last_prompt = captured_prompts[-1]
    assert [m.content for m in last_prompt if m.type == "human"] == ["What is on my plate?"]
    # Nothing left to retry once answered.
    again = await client.post(
        "/api/v1/ai/chat", json={"thread_id": a, "retry": True}, headers=ORIGIN
    )
    assert again.status_code == 409 and again.json()["error"]["code"] == "NOTHING_TO_RETRY"


async def test_reattach_replays_missed_events_then_ends(client: AsyncClient) -> None:
    await signup(client)
    set_fake_script([AIMessage(content=REPLY)])
    a = await new_thread(client)
    events = await events_of(await send(client, a, "hello"))
    run_id = events[0]["run_id"]

    tail = await events_of(await client.get(f"/api/v1/ai/runs/{run_id}/stream?after=3"))
    assert [e["seq"] for e in tail] == [e["seq"] for e in events[4:]]
    assert tail[-1]["type"] == "done"

    # Once the live channel is gone, the persisted outcome is served instead.
    hub._channels.clear()
    persisted = await events_of(await client.get(f"/api/v1/ai/runs/{run_id}/stream"))
    assert [e["type"] for e in persisted] == ["message", "done"]
    assert persisted[0]["content"] == REPLY and persisted[0]["thread_id"] == a


async def test_orphaned_run_does_not_block_its_conversation(client: AsyncClient) -> None:
    """A run left `running` by a crashed process is closed instead of locking the thread."""
    await signup(client)
    set_fake_script([AIMessage(content=REPLY)])
    a = await new_thread(client)
    await events_of(await send(client, a, "first"))
    async with get_session_factory()() as db:
        done = await db.get(AIRun, uuid.UUID((await _last_run(client, a))["id"]))
        assert done is not None
        orphan = AIRun(
            tenant_id=done.tenant_id,
            user_id=done.user_id,
            thread_id=done.thread_id,
            status=RunStatus.running,
            created_at=utcnow(),
        )
        db.add(orphan)
        await db.commit()

    listed = (await client.get("/api/v1/ai/threads")).json()["data"]
    assert listed[0]["active_run_status"] is None  # settled on read
    events = await events_of(await send(client, a, "still there?"))
    assert events[-1]["status"] == "completed"
    stream = await events_of(await client.get(f"/api/v1/ai/runs/{orphan.id}/stream"))
    assert [e["type"] for e in stream] == ["error", "done"]
    assert "interrupted" in stream[0]["message"]


async def test_new_message_supersedes_a_pending_approval(client: AsyncClient) -> None:
    await signup(client)
    set_fake_script(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "create_task", "args": {"title": "X"}, "id": "c1", "type": "tool_call"}
                ],
            )
        ]
    )
    a = await new_thread(client)
    first = await events_of(await send(client, a, "make a task"))
    assert first[-1]["status"] == "waiting_for_approval"
    run_id = first[-1]["run_id"]

    set_fake_script([AIMessage(content="Sure, never mind the task.")])
    second = await events_of(await send(client, a, "actually, forget it"))
    assert second[-1]["status"] == "completed"

    run = (await client.get(f"/api/v1/ai/runs/{run_id}")).json()["data"]
    assert run["status"] == "cancelled" and run["approvals"][0]["status"] == "expired"
    assert (await client.get("/api/v1/tasks")).json()["data"] == []
    # The unanswered proposal is closed in the prompt, so real model APIs accept the history.
    tool_msgs = [m for m in captured_prompts[-1] if m.type == "tool"]
    assert [m.tool_call_id for m in tool_msgs] == ["c1"]
    assert "cancelled" in str(tool_msgs[0].content)


async def test_thread_list_rename_archive_and_order(client: AsyncClient) -> None:
    await signup(client)
    set_fake_script([AIMessage(content="Answer")])
    older, newer = await new_thread(client), await new_thread(client)
    await events_of(await send(client, older, "about the older one"))
    await events_of(await send(client, newer, "about the newer one"))

    listed = (await client.get("/api/v1/ai/threads")).json()["data"]
    assert [t["id"] for t in listed] == [newer, older]
    assert listed[0]["title"] == "about the newer one"  # the first message names it
    assert listed[0]["last_message"] == "Answer" and listed[0]["last_message_role"] == "assistant"

    # Renaming does not bump a conversation to the top; activity does.
    renamed = await client.patch(
        f"/api/v1/ai/threads/{older}", json={"title": "Renamed"}, headers=ORIGIN
    )
    assert renamed.json()["data"]["title"] == "Renamed"
    listed = (await client.get("/api/v1/ai/threads")).json()["data"]
    assert [t["id"] for t in listed] == [newer, older]

    await client.patch(f"/api/v1/ai/threads/{newer}", json={"archived": True}, headers=ORIGIN)
    assert [t["id"] for t in (await client.get("/api/v1/ai/threads")).json()["data"]] == [older]
    archived = (await client.get("/api/v1/ai/threads?archived=true")).json()["data"]
    assert [t["id"] for t in archived] == [newer]


async def test_deleting_a_working_conversation_stops_it(client: AsyncClient) -> None:
    await signup(client)
    set_fake_script([AIMessage(content=" ".join([REPLY] * 4))])
    a, b = await new_thread(client), await new_thread(client)
    task_a = asyncio.create_task(send(client, a, "long"))
    await wait_until_running(client, a)
    task_b = asyncio.create_task(send(client, b, "keep going"))

    deleted = await client.delete(f"/api/v1/ai/threads/{a}", headers=ORIGIN)
    assert deleted.status_code == 200
    assert (await events_of(await task_a))[-1]["status"] == "cancelled"
    assert (await events_of(await task_b))[-1]["status"] == "completed"
    assert (await client.get(f"/api/v1/ai/threads/{a}")).status_code == 404
    assert [t["id"] for t in (await client.get("/api/v1/ai/threads")).json()["data"]] == [b]


async def _last_run(client: AsyncClient, thread_id: str) -> dict[str, Any]:
    detail = (await client.get(f"/api/v1/ai/threads/{thread_id}")).json()["data"]
    return dict(detail["last_run"])


# --- sharing one provider key across concurrent conversations ------------------------------------


class ProviderRateLimit(Exception):
    """Shaped like a vendor 429 (e.g. Gemini's GoogleRateLimitError)."""

    status_code = 429


def flaky_model(monkeypatch: pytest.MonkeyPatch, failures: int) -> dict[str, int]:
    original = ScriptedChatModel._generate
    calls = {"n": 0}

    def generate(self: ScriptedChatModel, messages: Any, *args: Any, **kwargs: Any) -> Any:
        calls["n"] += 1
        if calls["n"] <= failures:
            raise ProviderRateLimit("Resource exhausted. Please retry in 7s.")
        return original(self, messages, *args, **kwargs)

    monkeypatch.setattr(ScriptedChatModel, "_generate", generate)
    monkeypatch.setattr("app.ai.agent.retry_delay", lambda exc, attempt: 0.05)
    return calls


async def test_a_rate_limited_call_is_retried_instead_of_failing_the_run(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await signup(client)
    set_fake_script([AIMessage(content=REPLY)])
    calls = flaky_model(monkeypatch, failures=2)
    a = await new_thread(client)
    events = await events_of(await send(client, a, "hello"))

    assert events[-1]["status"] == "completed" and calls["n"] == 3
    notices = [e for e in events if e["type"] == "notice"]
    assert len(notices) == 2 and "busy" in notices[0]["message"]


async def test_after_retries_the_failure_says_why_even_after_a_reload(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await signup(client)
    set_fake_script([AIMessage(content=REPLY)])
    flaky_model(monkeypatch, failures=99)
    a = await new_thread(client)
    events = await events_of(await send(client, a, "hello"))

    error = next(e for e in events if e["type"] == "error")
    assert "busy" in error["message"]
    detail = (await client.get(f"/api/v1/ai/threads/{a}")).json()["data"]
    assert detail["last_run"]["error_message"] == error["message"]


async def test_stop_during_a_retry_wait_cancels_promptly(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await signup(client)
    set_fake_script([AIMessage(content=REPLY)])
    flaky_model(monkeypatch, failures=99)
    monkeypatch.setattr("app.ai.agent.retry_delay", lambda exc, attempt: 30.0)
    a = await new_thread(client)
    task = asyncio.create_task(send(client, a, "hello"))
    run_id = await wait_until_running(client, a)
    await asyncio.sleep(0.2)
    await client.post(f"/api/v1/ai/runs/{run_id}/cancel", headers=ORIGIN)
    events = await events_of(await asyncio.wait_for(task, 5))
    assert events[-1]["status"] == "cancelled"


async def test_conversations_sharing_a_key_take_turns_and_all_finish(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Three conversations at once on a key that allows one call at a time: none fails, and
    the provider never sees two calls in flight."""
    await signup(client)
    set_fake_script([AIMessage(content=REPLY)])
    monkeypatch.setattr("app.ai.runner.slot_key", lambda byo: ("narrow-test-key", 1))
    in_flight = {"now": 0, "max": 0}
    original = ScriptedChatModel._astream

    async def tracked(self: ScriptedChatModel, *args: Any, **kwargs: Any) -> Any:
        in_flight["now"] += 1
        in_flight["max"] = max(in_flight["max"], in_flight["now"])
        try:
            async for chunk in original(self, *args, **kwargs):
                yield chunk
        finally:
            in_flight["now"] -= 1

    monkeypatch.setattr(ScriptedChatModel, "_astream", tracked)
    ids = [await new_thread(client) for _ in range(3)]
    results = await asyncio.gather(*(send(client, t, f"question {i}") for i, t in enumerate(ids)))
    for tid, resp in zip(ids, results, strict=True):
        events = await events_of(resp)
        assert events[-1]["status"] == "completed" and {e["thread_id"] for e in events} == {tid}
    assert in_flight["max"] == 1
