"""Phase 6 — cross-app AI: planning, cross-source search, verification, cancellation.

Pipeline under test: discover → plan → read → propose → approve → execute → verify."""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from langchain_core.messages import AIMessage

from app.ai import agent as agent_module
from app.ai.cancel import cancel_key
from app.ai.llm import captured_prompts, set_fake_script
from app.ai.runner import _mark_plan
from app.core.kv import kv
from app.models.ai import AIRun
from app.tests.conftest import ORIGIN, read_sse, signup
from app.tests.test_ai import chat, tool_call, types
from app.tests.test_notes import create_note
from app.tests.test_providers import CASES, connect_via_oauth
from app.tests.test_providers import vendor as vendor  # noqa: F401 — fixture re-export
from app.tests.vendor_mocks import VendorMock

PLAN: dict[str, Any] = {
    "goal": "Prepare the launch follow-up",
    "steps": [
        {"title": "Find launch material", "kind": "read", "tools": ["search_everything"]},
        {"title": "Propose follow-up tasks", "kind": "propose", "tools": ["create_task"]},
        {"title": "Confirm the tasks exist", "kind": "verify", "tools": []},
        {"title": "Summarise for you", "kind": "answer", "tools": []},
    ],
}


async def run_of(client: AsyncClient, run_id: str) -> dict[str, Any]:
    return (await client.get(f"/api/v1/ai/runs/{run_id}")).json()["data"]


async def test_plan_read_propose_approve_verify(client: AsyncClient) -> None:
    await signup(client)
    note = await create_note(client, "Launch plan", "Finalize the pricing page by Friday.")

    # Turn 1: the model declares a plan and reads across sources in the same step.
    set_fake_script(
        [
            AIMessage(
                content="",
                tool_calls=[
                    tool_call("plan_steps", PLAN, "p1"),
                    tool_call("search_everything", {"query": "pricing"}, "c1"),
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[tool_call("create_task", {"title": "Finalize pricing"}, "c2")],
            ),
        ]
    )
    events = await chat(client, "Prepare the follow-up from the launch plan")
    kinds = types(events)
    assert kinds.index("plan") < kinds.index("approval_required")
    plan_event = next(e for e in events if e["type"] == "plan")
    assert plan_event["goal"] == PLAN["goal"]
    assert [s["title"] for s in plan_event["steps"]] == [s["title"] for s in PLAN["steps"]]

    # The cross-app search read the note and cited it (with retrieved_at).
    search_step = next(
        e for e in events if e["type"] == "step" and e["tool"] == "search_everything"
    )
    assert search_step["status"] == "running"
    tool_msgs = [m for call in captured_prompts for m in call if m.type == "tool"]
    search_result = next(m for m in tool_msgs if m.name == "search_everything")
    assert note["id"] in str(search_result.content)
    assert "untrusted_content" in str(search_result.content)
    assert '"sources_searched"' in str(search_result.content)

    approval = next(e for e in events if e["type"] == "approval_required")
    run = await run_of(client, approval["run_id"])
    assert run["status"] == "waiting_for_approval"
    # Progress is derived from execution: the read step is done, the proposal is waiting.
    assert [s["status"] for s in run["plan"]["steps"]] == ["done", "waiting", "pending", "pending"]

    # Turn 2: approve → execute → verify → answer.
    set_fake_script([AIMessage(content="Created the task and verified it exists.")])
    resumed = await read_sse(
        await client.post(
            "/api/v1/ai/approve",
            json={
                "run_id": approval["run_id"],
                "approval_id": approval["approval_id"],
                "approved_call_ids": ["c2"],
            },
            headers=ORIGIN,
        )
    )
    verification = next(e for e in resumed if e["type"] == "verification")
    assert verification["call_id"] == "c2" and verification["status"] == "verified"
    assert "Finalize pricing" in verification["detail"]
    # The model is told the outcome so it can report it honestly.
    tool_msgs = [m for call in captured_prompts for m in call if m.type == "tool"]
    assert '"verification": {"status": "verified"' in str(
        next(m for m in tool_msgs if m.name == "create_task").content
    )

    run = await run_of(client, approval["run_id"])
    assert run["status"] == "completed"
    assert [s["status"] for s in run["plan"]["steps"]] == ["done", "done", "done", "done"]
    step = next(s for s in run["steps"] if s.get("call_id") == "c2")
    assert step["verification"]["status"] == "verified"
    tc = next(t for t in run["tool_calls"] if t["call_id"] == "c2")
    assert tc["status"] == "executed" and tc["verification"]["status"] == "verified"

    message = next(e for e in resumed if e["type"] == "message")
    assert message["sources"][0]["provider"] == "notely"
    assert message["sources"][0]["retrieved_at"]


async def test_simple_question_needs_no_plan(client: AsyncClient) -> None:
    await signup(client)
    set_fake_script([AIMessage(content="Nothing to do.")])
    events = await chat(client, "hi")
    assert "plan" not in types(events)
    run = await run_of(client, events[0]["run_id"])
    assert run["plan"] is None


@pytest.mark.parametrize("vendor", ["todoist"], indirect=True)
async def test_search_everything_spans_connected_apps(
    client: AsyncClient, vendor: VendorMock
) -> None:
    await signup(client)
    await connect_via_oauth(client, "todoist", CASES["todoist"])
    await create_note(client, "Pricing notes", "Pricing page draft.")
    set_fake_script(
        [
            AIMessage(
                content="", tool_calls=[tool_call("search_everything", {"query": "pricing"}, "c1")]
            ),
            AIMessage(content="ok"),
        ]
    )
    events = await chat(client, "what do I have about pricing?")
    message = next(e for e in events if e["type"] == "message")
    providers = {s["provider"] for s in message["sources"]}
    assert providers == {"notely", "todoist"}
    todoist_source = next(s for s in message["sources"] if s["provider"] == "todoist")
    assert todoist_source["title"] == "Finalize pricing"
    assert todoist_source["url"]


@pytest.mark.parametrize("vendor", ["todoist"], indirect=True)
async def test_failed_read_back_is_reported_not_hidden(
    client: AsyncClient, vendor: VendorMock
) -> None:
    """If the provider accepted the write but the read-back contradicts it, the user hears so."""
    await signup(client)
    await connect_via_oauth(client, "todoist", CASES["todoist"])
    vendor.state["todoist_readback_content"] = "Something else entirely"
    set_fake_script(
        [
            AIMessage(
                content="",
                tool_calls=[tool_call("todoist__create_task", {"content": "Email the team"}, "c1")],
            ),
            AIMessage(content="done"),
        ]
    )
    events = await chat(client, "add a todoist task")
    approval = next(e for e in events if e["type"] == "approval_required")
    set_fake_script([AIMessage(content="done")])
    resumed = await read_sse(
        await client.post(
            "/api/v1/ai/approve",
            json={
                "run_id": approval["run_id"],
                "approval_id": approval["approval_id"],
                "approved_call_ids": ["c1"],
            },
            headers=ORIGIN,
        )
    )
    verification = next(e for e in resumed if e["type"] == "verification")
    assert verification["status"] == "failed"
    run = await run_of(client, approval["run_id"])
    tc = run["tool_calls"][0]
    assert tc["status"] == "executed"  # the write did happen ...
    assert tc["verification"]["status"] == "failed"  # ... but the check says it doesn't match
    audit = (await client.get("/api/v1/audit")).json()["data"]
    assert ("verify", "failed") in {(a["action"], a["status"]) for a in audit}


@pytest.mark.parametrize("vendor", ["todoist"], indirect=True)
async def test_unreachable_provider_means_unverified(
    client: AsyncClient, vendor: VendorMock
) -> None:
    await signup(client)
    await connect_via_oauth(client, "todoist", CASES["todoist"])
    vendor.state["todoist_readback_status"] = 503
    set_fake_script(
        [
            AIMessage(
                content="",
                tool_calls=[tool_call("todoist__create_task", {"content": "Email the team"}, "c1")],
            ),
            AIMessage(content="done"),
        ]
    )
    events = await chat(client, "add a todoist task")
    approval = next(e for e in events if e["type"] == "approval_required")
    set_fake_script([AIMessage(content="done")])
    resumed = await read_sse(
        await client.post(
            "/api/v1/ai/approve",
            json={
                "run_id": approval["run_id"],
                "approval_id": approval["approval_id"],
                "approved_call_ids": ["c1"],
            },
            headers=ORIGIN,
        )
    )
    verification = next(e for e in resumed if e["type"] == "verification")
    assert verification["status"] == "unverified"
    assert "Could not confirm" in verification["detail"]
    assert [e for e in resumed if e["type"] == "done"][-1]["status"] == "completed"


async def test_stop_between_approved_writes_prevents_the_rest(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await signup(client)
    set_fake_script(
        [
            AIMessage(
                content="",
                tool_calls=[
                    tool_call("create_task", {"title": "First"}, "c1"),
                    tool_call("create_task", {"title": "Second"}, "c2"),
                ],
            ),
            AIMessage(content="done"),
        ]
    )
    events = await chat(client, "make two tasks")
    approval = next(e for e in events if e["type"] == "approval_required")

    # The user presses Stop while the first approved write is executing.
    original = agent_module._execute

    async def execute_then_cancel(ctx: Any, call: Any, writer: Any) -> dict[str, Any]:
        result = await original(ctx, call, writer)
        await kv.set(cancel_key(ctx.run_id), "1", 60)
        return result

    monkeypatch.setattr(agent_module, "_execute", execute_then_cancel)
    resumed = await read_sse(
        await client.post(
            "/api/v1/ai/approve",
            json={
                "run_id": approval["run_id"],
                "approval_id": approval["approval_id"],
                "approved_call_ids": ["c1", "c2"],
            },
            headers=ORIGIN,
        )
    )
    assert resumed[-1]["status"] == "cancelled"
    titles = [t["title"] for t in (await client.get("/api/v1/tasks")).json()["data"]]
    assert titles == ["First"]
    run = await run_of(client, approval["run_id"])
    assert run["status"] == "cancelled"
    assert {tc["call_id"]: tc["status"] for tc in run["tool_calls"]} == {
        "c1": "executed",
        "c2": "approved",  # approved but never executed; the audit log has no entry for it
    }
    assert next(tc for tc in run["tool_calls"] if tc["call_id"] == "c2")["error"] == (
        "Stopped before execution"
    )
    audit = (await client.get("/api/v1/audit")).json()["data"]
    assert all(a["request_metadata"].get("summary") != "Create task “Second”" for a in audit)


def test_plan_progress_is_derived_from_execution() -> None:
    run = AIRun(plan={"goal": "g", "steps": [dict(s, status="pending") for s in PLAN["steps"]]})

    def statuses() -> list[str]:
        assert run.plan is not None
        return [s["status"] for s in run.plan["steps"]]

    _mark_plan(run, tool="search_everything", status="active")
    assert statuses() == ["active", "pending", "pending", "pending"]
    _mark_plan(run, tool="search_everything", status="done")
    # A later step completing marks the earlier ones done, even if their tools never ran.
    _mark_plan(run, kind="verify", status="done")
    assert statuses() == ["done", "done", "done", "pending"]
    _mark_plan(run, tool="unknown_tool", status="done")  # no match → no change
    assert statuses() == ["done", "done", "done", "pending"]
