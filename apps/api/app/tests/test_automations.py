"""Automations: workflow model, data mapping, conditions, engine, scheduler, planner, API."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from langchain_core.messages import AIMessage
from pydantic import ValidationError
from sqlalchemy import select

from app.automation import engine as engine_module
from app.automation import native, planner
from app.automation.conditions import evaluate
from app.automation.mapping import ReferenceUnavailable, resolve, to_text, unwrap
from app.automation.model import Condition, Workflow
from app.automation.native import text_to_doc
from app.automation.scheduler import next_occurrence
from app.core.exceptions import ValidationFailed
from app.tests.conftest import ORIGIN, signup
from app.tests.test_providers import CASES, connect_via_oauth
from app.tests.test_providers import vendor as vendor  # noqa: F401
from app.tests.vendor_mocks import VendorMock

API = "/api/v1/automations"


# --- helpers ----------------------------------------------------------------------------------


def action(
    step_id: str, action_id: str, inputs: dict[str, Any] | None = None, **extra: Any
) -> dict[str, Any]:
    return {"kind": "action", "id": step_id, "action": action_id, "inputs": inputs or {}, **extra}


def rule(left: str, operator: str, right: Any = None) -> dict[str, Any]:
    out: dict[str, Any] = {"left": left, "operator": operator}
    if right is not None:
        out["right"] = right
    return out


def body(steps: list[dict[str, Any]], **overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "name": "Test automation",
        "workflow": {"version": 2, "steps": steps},
        "schedule_kind": "daily",
        "schedule_config": {"time": "09:00"},
        "timezone": "UTC",
        "enabled": False,
    }
    values.update(overrides)
    return values


async def create(
    client: AsyncClient, steps: list[dict[str, Any]], **overrides: Any
) -> dict[str, Any]:
    response = await client.post(API, json=body(steps, **overrides), headers=ORIGIN)
    assert response.status_code == 201, response.text
    return dict(response.json()["data"])


async def run_detail(client: AsyncClient, automation_id: str, run_id: str) -> dict[str, Any]:
    response = await client.get(f"{API}/{automation_id}/runs/{run_id}")
    assert response.status_code == 200, response.text
    return dict(response.json()["data"])


async def run(client: AsyncClient, automation_id: str, **payload: Any) -> dict[str, Any]:
    response = await client.post(f"{API}/{automation_id}/run", json=payload, headers=ORIGIN)
    assert response.status_code == 202, response.text
    return await run_detail(client, automation_id, response.json()["data"]["id"])


async def dry_run(
    client: AsyncClient, automation_id: str, step_id: str | None = None
) -> dict[str, Any]:
    response = await client.post(
        f"{API}/{automation_id}/test", json={"step_id": step_id}, headers=ORIGIN
    )
    assert response.status_code == 202, response.text
    return await run_detail(client, automation_id, response.json()["data"]["id"])


def steps_by_id(detail: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {step["step_id"]: step for step in detail["steps"]}


class FakeModel:
    def __init__(self, respond: Callable[[str], str | Exception]) -> None:
        self.respond = respond
        self.prompts: list[str] = []

    async def ainvoke(self, messages: list[Any]) -> AIMessage:
        prompt = "\n".join(str(m.content) for m in messages)
        self.prompts.append(prompt)
        reply = self.respond(prompt)
        if isinstance(reply, Exception):
            raise reply
        return AIMessage(content=reply)


def fake_ai(
    monkeypatch: pytest.MonkeyPatch, respond: Callable[[str], str | Exception]
) -> FakeModel:
    model = FakeModel(respond)

    async def factory(_: Any) -> FakeModel:
        return model

    monkeypatch.setattr(native, "chat_model", factory)
    monkeypatch.setattr(planner, "chat_model", factory)
    monkeypatch.setattr(engine_module, "BACKOFF_SECONDS", (0.0, 0.0, 0.0))
    return model


def standard_ai(prompt: str) -> str:
    if "concrete things the user needs to do" in prompt:
        return json.dumps(
            {
                "action_items": [
                    {"title": "Prepare the pricing deck", "details": "", "due_date": "2026-09-30"},
                    {"title": "Email Bob", "details": "about Q4", "due_date": None},
                ]
            }
        )
    if "Summarize" in prompt:
        return json.dumps({"summary": "- Call Sam about pricing\n- Nothing else is urgent"})
    return json.dumps({"text": "ok"})


async def new_note(client: AsyncClient, title: str) -> dict[str, Any]:
    response = await client.post("/api/v1/notes", json={"title": title}, headers=ORIGIN)
    assert response.status_code == 201, response.text
    return dict(response.json()["data"])


async def new_task(client: AsyncClient, title: str) -> None:
    response = await client.post("/api/v1/tasks", json={"title": title}, headers=ORIGIN)
    assert response.status_code == 201, response.text


async def task_titles(client: AsyncClient) -> list[str]:
    return sorted(t["title"] for t in (await client.get("/api/v1/tasks")).json()["data"])


# --- workflow model ---------------------------------------------------------------------------


def test_workflow_rejects_duplicate_ids_and_data_used_too_early() -> None:
    with pytest.raises(ValidationError, match="share the id"):
        Workflow.model_validate(
            {
                "version": 2,
                "steps": [action("a", "notely.find_tasks"), action("a", "notely.find_notes")],
            }
        )
    with pytest.raises(ValidationError, match="before it is available"):
        Workflow.model_validate(
            {
                "version": 2,
                "steps": [
                    action("summary", "ai.summarize", {"data": "{{steps.tasks.output.tasks}}"}),
                    action("tasks", "notely.find_tasks"),
                ],
            }
        )
    with pytest.raises(ValidationError, match="not a valid piece of data"):
        Workflow.model_validate(
            {"version": 2, "steps": [action("a", "notely.notify", {"message": "{{secrets.key}}"})]}
        )


def test_branch_paths_cannot_see_each_other_but_later_steps_can() -> None:
    branch = {
        "kind": "branch",
        "id": "check",
        "condition": {"rules": [rule("{{steps.tasks.output.count}}", "greater_than", 0)]},
        "then": [action("yes", "notely.create_task", {"title": "Yes"})],
        "otherwise": [action("no", "notely.notify", {"message": "{{steps.yes.output.title}}"})],
    }
    with pytest.raises(ValidationError, match="before it is available"):
        Workflow.model_validate(
            {"version": 2, "steps": [action("tasks", "notely.find_tasks"), branch]}
        )
    branch["otherwise"] = [action("no", "notely.create_task", {"title": "No"})]
    after = action(
        "tell", "notely.notify", {"message": "{{steps.yes.output.title}} {{steps.no.output.title}}"}
    )
    Workflow.model_validate(
        {"version": 2, "steps": [action("tasks", "notely.find_tasks"), branch, after]}
    )


def test_version_1_workflows_are_upgraded() -> None:
    upgraded = Workflow.model_validate(
        {
            "version": 1,
            "steps": [
                {
                    "id": "mail",
                    "kind": "provider_tool",
                    "provider": "gmail",
                    "tool": "search_mail",
                    "arguments": {"query": "is:important"},
                },
                {
                    "id": "has_mail",
                    "kind": "condition",
                    "condition": {"path": "steps.mail.output.results", "operator": "has_data"},
                },
                {
                    "id": "summary",
                    "kind": "ai",
                    "arguments": {"prompt": "Summarize {{steps.mail.output.results}}"},
                },
                {
                    "id": "none",
                    "kind": "create_task",
                    "condition": {"path": "steps.has_mail.output.matched", "equals": False},
                    "arguments": {"title": "Inbox zero"},
                },
            ],
        }
    )
    dumped = upgraded.model_dump()
    assert [s["kind"] for s in dumped["steps"]] == ["action", "action", "branch"]
    assert dumped["steps"][0]["action"] == "gmail.search_mail"
    assert dumped["steps"][1]["action"] == "ai.ask"
    gate = dumped["steps"][2]
    assert gate["condition"]["negate"] is True  # "matched == False" became the negated check
    assert gate["condition"]["rules"][0]["operator"] == "is_not_empty"
    assert gate["then"][0]["action"] == "notely.create_task"


# --- data mapping -----------------------------------------------------------------------------

SCOPE: dict[str, Any] = {
    "steps": {
        "mail": {
            "status": "completed",
            "output": {"results": [{"subject": "Pricing", "from": "Bob"}, {"subject": "Hello"}]},
        },
        "skipped": {"status": "skipped", "output": None},
        "broken": {"status": "failed", "output": None},
    },
    "trigger": {"fired_at": "2026-09-23T09:00:00+00:00"},
    "automation": {"name": "Daily"},
}


def test_references_keep_types_alone_and_read_as_text_inside_sentences() -> None:
    assert (
        resolve("{{steps.mail.output.results}}", SCOPE)
        == SCOPE["steps"]["mail"]["output"]["results"]
    )
    assert resolve("{{steps.mail.output.results.count}}", SCOPE) == 2
    assert resolve("About {{steps.mail.output.results.0.subject}}", SCOPE) == "About Pricing"
    assert (
        resolve("Emails:\n{{steps.mail.output.results}}", SCOPE)
        == "Emails:\n- Pricing (from: Bob)\n- Hello"
    )
    assert resolve({"x": ["{{automation.name}}"]}, SCOPE) == {"x": ["Daily"]}
    assert resolve("{{trigger.fired_at}}", SCOPE).startswith("2026-09-23")


def test_missing_fields_and_skipped_steps_are_empty_but_failed_steps_are_errors() -> None:
    assert resolve("{{steps.mail.output.nothing}}", SCOPE) is None
    assert resolve("x{{steps.mail.output.nothing}}y", SCOPE) == "xy"
    assert resolve("{{steps.skipped.output.title}}", SCOPE) is None
    with pytest.raises(ReferenceUnavailable):
        resolve("{{steps.broken.output.title}}", SCOPE)


def test_connector_markup_is_removed_before_data_reaches_other_steps() -> None:
    wrapped = '<untrusted_content source="gmail:m1">\nQ4 Launch Pricing\n</untrusted_content>'
    assert unwrap({"results": [{"subject": wrapped}]}) == {
        "results": [{"subject": "Q4 Launch Pricing"}]
    }
    assert to_text(True) == "Yes"


@pytest.mark.parametrize(
    ("condition", "expected"),
    [
        ({"rules": [rule("{{steps.mail.output.results.count}}", "greater_than", 1)]}, True),
        ({"rules": [rule("{{steps.mail.output.results.count}}", "less_than", "2")]}, False),
        ({"rules": [rule("{{steps.mail.output.results}}", "contains", "pricing")]}, True),
        ({"rules": [rule("{{steps.mail.output.results}}", "not_contains", "invoice")]}, True),
        ({"rules": [rule("{{steps.mail.output.results.0.subject}}", "equals", "PRICING")]}, True),
        ({"rules": [rule("{{steps.mail.output.missing}}", "not_exists")]}, True),
        ({"rules": [rule("{{steps.skipped.output.x}}", "is_empty")]}, True),
        ({"rules": [rule("{{trigger.fired_at}}", "after", "2026-09-22T00:00:00Z")]}, True),
        ({"rules": [rule("Fri, 19 Sep 2026 10:00:00 +0000", "before", "2026-09-20")]}, True),
        (
            {
                "match": "any",
                "rules": [
                    rule("{{steps.mail.output.results.count}}", "equals", 5),
                    rule("a", "is_true"),
                ],
            },
            False,
        ),
        ({"negate": True, "rules": [rule("{{steps.mail.output.results}}", "is_not_empty")]}, False),
    ],
)
def test_conditions(condition: dict[str, Any], expected: bool) -> None:
    assert evaluate(Condition.model_validate(condition), SCOPE) is expected


def test_ai_text_becomes_a_structured_note() -> None:
    doc = text_to_doc(
        "## Today\n- Call Sam\n- **Pay** invoice\n- [ ] Review deck\n1. First", "Tuesday"
    )
    kinds = [block["type"] for block in doc["content"]]
    assert kinds == ["heading", "heading", "bulletList", "taskList", "orderedList"]
    assert doc["content"][2]["content"][1]["content"][0]["content"][0]["marks"] == [
        {"type": "bold"}
    ]


# --- scheduling -------------------------------------------------------------------------------


def test_schedule_calculations() -> None:
    saturday = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
    weekday = next_occurrence(
        "weekly", {"time": "09:00", "days": [0, 1, 2, 3, 4]}, "UTC", after=saturday
    )
    assert weekday == datetime(2026, 9, 21, 9, 0, tzinfo=UTC)
    february = next_occurrence(
        "monthly", {"time": "08:00", "day": 31}, "UTC", after=datetime(2026, 2, 1, tzinfo=UTC)
    )
    assert february == datetime(2026, 2, 28, 8, 0, tzinfo=UTC)
    quarter = next_occurrence(
        "interval", {"every_minutes": 15}, "UTC", after=datetime(2026, 9, 23, 10, 7, tzinfo=UTC)
    )
    assert quarter == datetime(2026, 9, 23, 10, 15, tzinfo=UTC)
    assert next_occurrence("manual", {}, "UTC") is None
    # 02:30 doesn't exist in New York on 2026-03-08; it runs at the first real instant after.
    dst = next_occurrence(
        "daily", {"time": "02:30"}, "America/New_York", after=datetime(2026, 3, 8, 5, 0, tzinfo=UTC)
    )
    assert dst == datetime(2026, 3, 8, 7, 30, tzinfo=UTC)
    with pytest.raises(ValidationFailed):
        next_occurrence("daily", {"time": "25:00"}, "UTC")
    with pytest.raises(ValidationFailed):
        next_occurrence("interval", {"every_minutes": 5}, "UTC")


# --- engine through the API -------------------------------------------------------------------


async def test_notely_and_ai_workflow_really_runs(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    ai = fake_ai(monkeypatch, standard_ai)
    await signup(client)
    note = await new_note(client, "Daily Email Summary")
    await new_task(client, "Call Sam about pricing")
    automation = await create(
        client,
        [
            action("open_tasks", "notely.find_tasks", {"status": "open"}),
            action("summary", "ai.summarize", {"data": "{{steps.open_tasks.output.tasks}}"}),
            action(
                "items", "ai.extract_action_items", {"data": "{{steps.open_tasks.output.tasks}}"}
            ),
            action(
                "make_tasks",
                "notely.create_tasks",
                {"items": "{{steps.items.output.action_items}}"},
            ),
            action(
                "save",
                "notely.update_note",
                {
                    "note": note["id"],
                    "content": "{{steps.summary.output.summary}}",
                    "mode": "append",
                },
            ),
        ],
    )
    assert automation["apps"] == ["notely", "ai"]
    detail = await run(client, automation["id"])
    assert detail["status"] == "completed", detail
    assert all("Call Sam about pricing" in prompt for prompt in ai.prompts)
    steps = steps_by_id(detail)
    assert steps["open_tasks"]["summary"] == "1 tasks found"
    assert steps["make_tasks"]["summary"] == "Created 2 tasks"
    assert steps["save"]["output"]["title"] == "Daily Email Summary"
    assert "Created 2 tasks" in detail["summary"] and "Updated note" in detail["summary"]
    tasks = (await client.get("/api/v1/tasks")).json()["data"]
    deck = next(t for t in tasks if t["title"] == "Prepare the pricing deck")
    assert deck["due_date"] == "2026-09-30"
    assert await task_titles(client) == [
        "Call Sam about pricing",
        "Email Bob",
        "Prepare the pricing deck",
    ]
    saved = (await client.get(f"/api/v1/notes/{note['id']}")).json()["data"]
    assert "Call Sam about pricing" in saved["plain_text"]
    assert saved["content_json"]["content"][-2]["type"] == "heading"  # the date heading
    assert saved["content_json"]["content"][-1]["type"] == "bulletList"
    listed = (await client.get(API)).json()["data"][0]
    assert listed["last_run"]["status"] == "completed" and listed["last_run"]["summary"]


async def test_a_filter_stops_the_run_without_failing_it(client: AsyncClient) -> None:
    await signup(client)
    automation = await create(
        client,
        [
            action("open_tasks", "notely.find_tasks", {"status": "open"}),
            {
                "kind": "filter",
                "id": "has_tasks",
                "name": "Only continue if there are open tasks",
                "condition": {
                    "rules": [rule("{{steps.open_tasks.output.count}}", "greater_than", 0)]
                },
            },
            action("never", "notely.create_task", {"title": "Should not exist"}),
        ],
    )
    detail = await run(client, automation["id"])
    assert detail["status"] == "stopped"
    steps = steps_by_id(detail)
    assert steps["has_tasks"]["output"] == {"passed": False}
    assert steps["never"]["status"] == "skipped"
    assert "wasn't met" in detail["summary"]
    assert await task_titles(client) == []


async def test_branches_take_one_path_and_the_workflow_continues(client: AsyncClient) -> None:
    await signup(client)
    automation = await create(
        client,
        [
            action("open_tasks", "notely.find_tasks", {"status": "open"}),
            {
                "kind": "branch",
                "id": "any_tasks",
                "condition": {
                    "rules": [rule("{{steps.open_tasks.output.count}}", "greater_than", 0)]
                },
                "then": [action("yes_task", "notely.create_task", {"title": "Yes path"})],
                "otherwise": [action("no_task", "notely.create_task", {"title": "No path"})],
            },
            action(
                "tell",
                "notely.notify",
                {"message": "Done: {{steps.no_task.output.title}}{{steps.yes_task.output.title}}"},
            ),
        ],
    )
    detail = await run(client, automation["id"])
    assert detail["status"] == "completed", detail
    steps = steps_by_id(detail)
    assert steps["any_tasks"]["output"] == {"path": "no"}
    assert steps["yes_task"]["status"] == "skipped"
    assert await task_titles(client) == ["No path"]
    notifications = (await client.get("/api/v1/notifications")).json()["data"]["items"]
    assert any(n["title"] == "Done: No path" and n["kind"] == "automation" for n in notifications)


async def test_test_runs_simulate_changes_and_later_steps_still_get_data(
    client: AsyncClient,
) -> None:
    await signup(client)
    note = await new_note(client, "Log")
    automation = await create(
        client,
        [
            action("make_task", "notely.create_task", {"title": "Follow up"}),
            action(
                "log",
                "notely.update_note",
                {"note": note["id"], "content": "Made: {{steps.make_task.output.title}}"},
            ),
        ],
    )
    detail = await dry_run(client, automation["id"])
    assert detail["status"] == "completed" and detail["run_mode"] == "test"
    steps = steps_by_id(detail)
    assert steps["make_task"]["status"] == "simulated"
    assert steps["log"]["input"]["content"] == "Made: Follow up"
    assert steps["log"]["summary"].startswith("Test run — would")
    assert await task_titles(client) == []
    assert (await client.get(f"/api/v1/notes/{note['id']}")).json()["data"]["plain_text"] == ""
    only_first = await dry_run(client, automation["id"], step_id="make_task")
    assert [s["step_id"] for s in only_first["steps"]] == ["make_task"]
    # Test runs never count as the automation's last run.
    assert (await client.get(API)).json()["data"][0]["last_run"] is None


async def test_incomplete_automations_save_as_drafts_but_cannot_be_switched_on(
    client: AsyncClient,
) -> None:
    await signup(client)
    steps = [action("save", "notely.update_note", {"content": "Hello"})]
    draft = await create(client, steps)
    assert draft["issues"][0]["field"] == "note"
    refused = await client.post(API, json=body(steps, enabled=True), headers=ORIGIN)
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "AUTOMATION_NOT_READY"
    assert refused.json()["error"]["details"]["issues"][0]["field"] == "note"
    switch_on = await client.post(
        f"{API}/{draft['id']}/enabled", json={"enabled": True}, headers=ORIGIN
    )
    assert switch_on.status_code == 422
    run_now = await client.post(f"{API}/{draft['id']}/run", json={}, headers=ORIGIN)
    assert run_now.status_code == 422
    unconnected = await create(client, [action("mail", "gmail.search_mail", {"query": "x"})])
    assert unconnected["issues"][0]["kind"] == "connect"
    assert unconnected["issues"][0]["fix_path"] == "/app/settings/connections/gmail"
    checked = await client.post(
        f"{API}/validate",
        json={"workflow": {"version": 2, "steps": [action("a", "nope.nothing")]}},
        headers=ORIGIN,
    )
    assert checked.json()["data"]["issues"][0]["kind"] == "unsupported"


@pytest.mark.parametrize("vendor", ["gmail"], indirect=True)
async def test_gmail_to_ai_to_notely(
    client: AsyncClient, vendor: VendorMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    ai = fake_ai(monkeypatch, standard_ai)
    await signup(client)
    await connect_via_oauth(client, "gmail", CASES["gmail"])
    note = await new_note(client, "Daily Email Summary")
    catalog = (await client.get(f"{API}/catalog")).json()["data"]
    search = next(a for a in catalog["actions"] if a["id"] == "gmail.search_mail")
    assert search["available"] and search["safety"] == "safe"
    assert search["outputs"][0]["key"] == "results"
    assert {f["key"] for f in search["outputs"][0]["fields"]} >= {"subject", "from"}
    send = next(a for a in catalog["actions"] if a["id"] == "gmail.send_mail")
    assert send["safety"] == "ask"
    automation = await create(
        client,
        [
            action("mail", "gmail.search_mail", {"query": "is:important", "limit": 10}),
            action("summary", "ai.summarize", {"data": "{{steps.mail.output.results}}"}),
            action(
                "save",
                "notely.update_note",
                {"note": note["id"], "content": "{{steps.summary.output.summary}}"},
            ),
            action(
                "reply_task",
                "notely.create_task",
                {
                    "title": "Reply to {{steps.mail.output.results.0.from}}: "
                    "{{steps.mail.output.results.0.subject}}"
                },
            ),
        ],
        enabled=True,
    )
    assert automation["enabled"] and automation["next_run_at"]
    detail = await run(client, automation["id"])
    assert detail["status"] == "completed", detail
    assert "Q4 Launch Pricing" in ai.prompts[0]
    assert "untrusted_content" not in ai.prompts[0]
    assert await task_titles(client) == ["Reply to Bob <bob@acme.io>: Q4 Launch Pricing"]
    assert steps_by_id(detail)["mail"]["summary"] == "1 emails found"
    saved = (await client.get(f"/api/v1/notes/{note['id']}")).json()["data"]
    assert "Call Sam about pricing" in saved["plain_text"]


@pytest.mark.parametrize("vendor", ["gmail"], indirect=True)
async def test_external_actions_wait_for_approval(client: AsyncClient, vendor: VendorMock) -> None:
    await signup(client)
    await connect_via_oauth(
        client, "gmail", CASES["gmail"], scopes=["https://www.googleapis.com/auth/gmail.send"]
    )
    send = action(
        "send", "gmail.send_mail", {"to": ["bob@acme.io"], "subject": "Hi", "body": "Hello"}
    )
    automation = await create(client, [send])
    waiting = await run(client, automation["id"])
    assert waiting["status"] == "waiting_for_approval"
    assert not any(r.url.path.endswith("/messages/send") for r in vendor.captured.requests)
    approval = waiting["approvals"][0]
    assert approval["status"] == "pending" and approval["proposal"]["app"] == "Gmail"
    notifications = (await client.get("/api/v1/notifications")).json()["data"]["items"]
    assert any("waiting for your approval" in n["title"] for n in notifications)
    assert (await client.get(API)).json()["data"][0]["pending_approvals"] == 1
    decided = await client.post(
        f"{API}/{automation['id']}/approvals/{approval['id']}",
        json={"approved": True},
        headers=ORIGIN,
    )
    assert decided.status_code == 202
    assert (await run_detail(client, automation["id"], waiting["id"]))["status"] == "completed"
    assert any(r.url.path.endswith("/messages/send") for r in vendor.captured.requests)

    second = await run(client, automation["id"])
    await client.post(
        f"{API}/{automation['id']}/approvals/{second['approvals'][0]['id']}",
        json={"approved": False},
        headers=ORIGIN,
    )
    rejected = await run_detail(client, automation["id"], second["id"])
    assert rejected["status"] == "failed" and "declined" in rejected["error"]

    automatic = await create(client, [{**send, "approval": "auto"}], name="Automatic send")
    assert (await run(client, automatic["id"]))["status"] == "completed"


async def test_a_failed_step_can_be_retried_without_redoing_earlier_steps(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = {"n": 0}

    def flaky(prompt: str) -> str | Exception:
        calls["n"] += 1
        if calls["n"] == 1:
            return RuntimeError("model overloaded")
        return standard_ai(prompt)

    fake_ai(monkeypatch, flaky)
    await signup(client)
    await new_task(client, "Call Sam about pricing")
    automation = await create(
        client,
        [
            action("open_tasks", "notely.find_tasks"),
            action(
                "summary", "ai.summarize", {"data": "{{steps.open_tasks.output.tasks}}"}, retries=0
            ),
            action("tell", "notely.notify", {"message": "{{steps.summary.output.summary}}"}),
        ],
    )
    failed = await run(client, automation["id"])
    assert failed["status"] == "failed"
    steps = steps_by_id(failed)
    assert (
        steps["summary"]["status"] == "failed" and "couldn't complete" in steps["summary"]["error"]
    )
    assert steps["summary"]["details"]["fix_path"] == "/app/settings/ai"
    finished_before = steps["open_tasks"]["finished_at"]
    retried = await client.post(
        f"{API}/{automation['id']}/runs/{failed['id']}/steps/summary/retry", json={}, headers=ORIGIN
    )
    assert retried.status_code == 202
    after = await run_detail(client, automation["id"], failed["id"])
    assert after["status"] == "completed", after
    assert steps_by_id(after)["open_tasks"]["finished_at"] == finished_before
    not_again = await client.post(
        f"{API}/{automation['id']}/runs/{failed['id']}/steps/summary/retry", json={}, headers=ORIGIN
    )
    assert not_again.status_code == 409


async def test_transient_ai_failures_retry_automatically(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = {"n": 0}

    def unstable(prompt: str) -> str | Exception:
        calls["n"] += 1
        return RuntimeError("timeout") if calls["n"] < 3 else standard_ai(prompt)

    fake_ai(monkeypatch, unstable)
    await signup(client)
    automation = await create(client, [action("summary", "ai.summarize", {"data": "anything"})])
    detail = await run(client, automation["id"])
    assert detail["status"] == "completed"
    assert steps_by_id(detail)["summary"]["attempts"] == 3


async def test_runs_are_idempotent_and_never_overlap(client: AsyncClient) -> None:
    await signup(client)
    automation = await create(client, [action("tell", "notely.notify", {"message": "Hi"})])
    first = await run(client, automation["id"], idempotency_key="run-once-0001")
    again = await run(client, automation["id"], idempotency_key="run-once-0001")
    assert first["id"] == again["id"]
    from app.db.session import get_session_factory
    from app.models.automation import AutomationExecution

    async with get_session_factory()() as db:
        db.add(
            AutomationExecution(
                automation_id=__import__("uuid").UUID(automation["id"]),
                occurrence_at=datetime.now(UTC) - timedelta(minutes=1),
                status="running",
                attempts=1,
                run_mode="manual",
                started_at=datetime.now(UTC),
                result={},
                context={},
            )
        )
        await db.commit()
    busy = await client.post(f"{API}/{automation['id']}/run", json={}, headers=ORIGIN)
    assert busy.status_code == 409


async def test_automations_are_private_to_their_owner(client: AsyncClient) -> None:
    await signup(client, email="owner@example.com")
    automation = await create(client, [action("tell", "notely.notify", {"message": "Hi"})])
    first = await run(client, automation["id"])
    await client.post("/api/v1/auth/logout", headers=ORIGIN)
    await signup(client, email="intruder@example.com")
    assert (await client.get(API)).json()["data"] == []
    for method, path in [
        ("get", f"{API}/{automation['id']}"),
        ("get", f"{API}/{automation['id']}/runs"),
        ("get", f"{API}/{automation['id']}/runs/{first['id']}"),
        ("post", f"{API}/{automation['id']}/run"),
        ("post", f"{API}/{automation['id']}/test"),
        ("post", f"{API}/{automation['id']}/duplicate"),
        ("delete", f"{API}/{automation['id']}"),
    ]:
        kwargs: dict[str, Any] = {"headers": ORIGIN}
        if method == "post":
            kwargs["json"] = {}
        response = await getattr(client, method)(path, **kwargs)
        assert response.status_code == 404, (path, response.text)


# --- scheduler --------------------------------------------------------------------------------


async def _make_due(automation_id: str) -> None:
    import uuid

    from app.db.session import get_session_factory
    from app.models.automation import Automation

    async with get_session_factory()() as db:
        row = await db.get(Automation, uuid.UUID(automation_id))
        assert row is not None
        row.next_run_at = datetime.now(UTC) - timedelta(minutes=2)
        await db.commit()


async def _automation(automation_id: str) -> Any:
    import uuid

    from app.db.session import get_session_factory
    from app.models.automation import Automation

    async with get_session_factory()() as db:
        return await db.get(Automation, uuid.UUID(automation_id))


async def test_scheduled_runs_happen_once_and_the_schedule_moves_on(client: AsyncClient) -> None:
    from app.workers.jobs.automations import run_due_automations

    await signup(client)
    automation = await create(
        client, [action("make", "notely.create_task", {"title": "Daily review"})], enabled=True
    )
    await _make_due(automation["id"])
    assert await run_due_automations({}) == 1
    assert await run_due_automations({}) == 0  # the occurrence was claimed; nothing is due
    assert await task_titles(client) == ["Daily review"]
    runs = (await client.get(f"{API}/{automation['id']}/runs")).json()["data"]
    assert [r["run_mode"] for r in runs] == ["scheduled"]
    assert runs[0]["trigger"]["type"] == "schedule"
    row = await _automation(automation["id"])
    upcoming = row.next_run_at if row.next_run_at.tzinfo else row.next_run_at.replace(tzinfo=UTC)
    assert upcoming > datetime.now(UTC)


async def test_failed_scheduled_runs_keep_the_schedule_and_pause_after_repeated_failures(
    client: AsyncClient,
) -> None:
    from app.automation.runner import PAUSE_AFTER_FAILURES
    from app.workers.jobs.automations import run_due_automations

    await signup(client)
    note = await new_note(client, "Target")
    automation = await create(
        client,
        [action("save", "notely.update_note", {"note": note["id"], "content": "Hi"})],
        enabled=True,
    )
    await client.delete(f"/api/v1/notes/{note['id']}", headers=ORIGIN)  # breaks the step
    for attempt in range(1, PAUSE_AFTER_FAILURES + 1):
        await _make_due(automation["id"])
        assert await run_due_automations({}) == 1
        row = await _automation(automation["id"])
        assert row.consecutive_failures == attempt
        if attempt < PAUSE_AFTER_FAILURES:
            assert row.enabled and row.next_run_at is not None
    assert row.enabled is False
    titles = [
        n["title"] for n in (await client.get("/api/v1/notifications")).json()["data"]["items"]
    ]
    assert any("didn't finish" in t for t in titles)
    assert any("was paused after" in t for t in titles)


async def test_interrupted_runs_are_recovered(client: AsyncClient) -> None:
    import uuid

    from app.automation.scheduler import recover_stale_runs
    from app.db.session import get_session_factory
    from app.models.automation import AutomationExecution

    await signup(client)
    automation = await create(client, [action("tell", "notely.notify", {"message": "Hi"})])
    async with get_session_factory()() as db:
        db.add(
            AutomationExecution(
                automation_id=uuid.UUID(automation["id"]),
                occurrence_at=datetime.now(UTC) - timedelta(hours=2),
                status="running",
                attempts=1,
                run_mode="scheduled",
                started_at=datetime.now(UTC) - timedelta(hours=2),
                result={},
                context={},
            )
        )
        await db.commit()
        assert await recover_stale_runs(db) == 1
        row = await db.scalar(select(AutomationExecution))
        assert row is not None and row.status == "failed" and "interrupted" in (row.error or "")
    # A crashed run no longer blocks "Run now".
    assert (await run(client, automation["id"]))["status"] == "completed"


# --- AI planner -------------------------------------------------------------------------------

DAILY_EMAIL_PROMPT = (
    "Every weekday at 9 AM, check my important Gmail, summarize anything that needs attention, "
    "create tasks for me, and save the summary to my Daily Email Summary note."
)


def planner_reply(note_id: str, **extra: Any) -> str:
    return json.dumps(
        {
            "name": "Daily email summary",
            "description": "Summarize important email every weekday.",
            "schedule": {"kind": "weekly", "time": "09:00", "days": [0, 1, 2, 3, 4]},
            "steps": [
                action(
                    "mail",
                    "gmail.search_mail",
                    {"query": "is:important newer_than:1d", "limit": 20},
                ),
                {
                    "kind": "filter",
                    "id": "has_mail",
                    "name": "Only continue if there are emails",
                    "condition": {
                        "rules": [rule("{{steps.mail.output.results.count}}", "greater_than", 0)]
                    },
                },
                action("summary", "ai.summarize", {"data": "{{steps.mail.output.results}}"}),
                action(
                    "items", "ai.extract_action_items", {"data": "{{steps.mail.output.results}}"}
                ),
                action(
                    "tasks", "notely.create_tasks", {"items": "{{steps.items.output.action_items}}"}
                ),
                action(
                    "save",
                    "notely.update_note",
                    {"note": note_id, "content": "{{steps.summary.output.summary}}"},
                ),
            ],
            "missing_apps": [],
            "unsupported": [],
            "questions": [],
            **extra,
        }
    )


@pytest.mark.parametrize("vendor", ["gmail"], indirect=True)
async def test_ai_builds_the_daily_email_workflow_and_names_the_missing_connection(
    client: AsyncClient, vendor: VendorMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    await signup(client)
    note = await new_note(client, "Daily Email Summary")
    model = fake_ai(monkeypatch, lambda _: planner_reply(note["id"]))
    draft = (
        await client.post(
            f"{API}/draft", json={"prompt": DAILY_EMAIL_PROMPT, "timezone": "UTC"}, headers=ORIGIN
        )
    ).json()["data"]
    # Gmail is offered but not connected: its actions are known (locked) and the gap is named.
    assert "gmail.search_mail" in model.prompts[0] and "Daily Email Summary" in model.prompts[0]
    assert draft["missing_apps"] == [
        {"app": "gmail", "name": "Gmail", "connect_path": "/app/settings/connections/gmail"}
    ]
    assert draft["schedule_kind"] == "weekly" and draft["schedule_config"]["days"] == [
        0,
        1,
        2,
        3,
        4,
    ]
    assert [s["id"] for s in draft["workflow"]["steps"]] == [
        "mail",
        "has_mail",
        "summary",
        "items",
        "tasks",
        "save",
    ]
    assert draft["issues"] == []

    # After connecting, the same workflow saves, switches on and runs.
    await connect_via_oauth(client, "gmail", CASES["gmail"])
    fake_ai(monkeypatch, standard_ai)
    saved = await create(
        client,
        draft["workflow"]["steps"],
        name=draft["name"],
        schedule_kind=draft["schedule_kind"],
        schedule_config=draft["schedule_config"],
        enabled=True,
    )
    detail = await run(client, saved["id"])
    assert detail["status"] == "completed", detail
    assert await task_titles(client) == ["Email Bob", "Prepare the pricing deck"]
    assert (
        "Call Sam about pricing"
        in (await client.get(f"/api/v1/notes/{note['id']}")).json()["data"]["plain_text"]
    )


async def test_ai_repairs_an_invalid_draft_once_and_reports_what_cannot_be_done(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await signup(client)
    replies = iter(
        [
            json.dumps(
                {
                    "schedule": {"kind": "daily", "time": "08:00"},
                    "steps": [
                        action("tell", "notely.notify", {"message": "{{steps.later.output.text}}"})
                    ],
                }
            ),
            json.dumps(
                {
                    "name": "Morning ping",
                    "schedule": {"kind": "daily", "time": "08:00"},
                    "steps": [action("tell", "notely.notify", {"message": "Good morning"})],
                    "unsupported": [
                        {
                            "request": "text me",
                            "reason": "Notely can't send SMS.",
                            "suggestion": "A Notely notification",
                        }
                    ],
                }
            ),
        ]
    )
    model = fake_ai(monkeypatch, lambda _: next(replies))
    draft = (
        await client.post(
            f"{API}/draft", json={"prompt": "Text me good morning at 8"}, headers=ORIGIN
        )
    ).json()["data"]
    assert len(model.prompts) == 2 and "before it is available" in model.prompts[1]
    assert draft["workflow"]["steps"][0]["inputs"]["message"] == "Good morning"
    assert draft["unsupported"][0]["reason"] == "Notely can't send SMS."

    invented = json.dumps({"steps": [action("fax", "fax.send_fax", {"to": "1"})]})
    fake_ai(monkeypatch, lambda _: invented)
    impossible = (
        await client.post(f"{API}/draft", json={"prompt": "Fax my boss"}, headers=ORIGIN)
    ).json()["data"]
    assert impossible["workflow"] is None and impossible["unsupported"]


@pytest.mark.parametrize("vendor", ["gmail"], indirect=True)
async def test_ai_edits_an_existing_workflow_and_never_grants_automatic_sending(
    client: AsyncClient, vendor: VendorMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    await signup(client)
    await connect_via_oauth(
        client, "gmail", CASES["gmail"], scopes=["https://www.googleapis.com/auth/gmail.send"]
    )
    current = {
        "name": "Mail digest",
        "workflow": {
            "version": 2,
            "steps": [action("mail", "gmail.search_mail", {"query": "is:unread"})],
        },
        "schedule_kind": "daily",
        "schedule_config": {"time": "09:00"},
        "timezone": "UTC",
    }
    edited = json.dumps(
        {
            "steps": [
                action("mail", "gmail.search_mail", {"query": "is:unread"}),
                {
                    "kind": "filter",
                    "id": "enough_mail",
                    "condition": {
                        "rules": [rule("{{steps.mail.output.results.count}}", "greater_than", 5)]
                    },
                },
                action(
                    "send",
                    "gmail.send_mail",
                    {"to": ["me@acme.io"], "subject": "Busy inbox", "body": "Lots of mail"},
                    approval="auto",
                ),
            ],
            "changes": [
                "Only continues when there are more than 5 unread emails",
                "Emails you a heads-up",
            ],
        }
    )
    model = fake_ai(monkeypatch, lambda _: edited)
    draft = (
        await client.post(
            f"{API}/draft",
            json={
                "prompt": "Add a condition so this only runs when I receive more than 5 emails",
                "current": current,
            },
            headers=ORIGIN,
        )
    ).json()["data"]
    assert "Current automation" in model.prompts[0]
    assert draft["name"] == "Mail digest" and draft["schedule_kind"] == "daily"
    assert [s["id"] for s in draft["workflow"]["steps"]] == ["mail", "enough_mail", "send"]
    assert draft["workflow"]["steps"][2]["approval"] == "ask"
    assert len(draft["changes"]) == 2


async def test_drafting_without_a_model_explains_how_to_fix_it(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.automation.actions import ActionError

    async def unavailable(_: Any) -> Any:
        raise ActionError("No AI model is available.")

    monkeypatch.setattr(planner, "chat_model", unavailable)
    await signup(client)
    response = await client.post(
        f"{API}/draft", json={"prompt": "Summarize my notes daily"}, headers=ORIGIN
    )
    assert response.status_code == 422
    assert response.json()["error"]["details"]["settings_path"] == "/app/settings/ai"


# --- templates & housekeeping -----------------------------------------------------------------


async def test_templates_duplicates_and_version_1_payloads(client: AsyncClient) -> None:
    await signup(client)
    templates = (await client.get(f"{API}/templates")).json()["data"]
    ids = {t["id"]: t for t in templates}
    assert ids["weekly-review"]["available"] and ids["task-nudge"]["available"]
    # Gmail isn't offered on this deployment (no OAuth client), so its template isn't shown.
    assert "daily-email-summary" not in ids
    for template in templates:
        Workflow.model_validate(template["workflow"])

    automation = await create(
        client, ids["weekly-review"]["workflow"]["steps"], name="Weekly review"
    )
    saved = await client.post(
        f"{API}/{automation['id']}/template", json={"name": "My review"}, headers=ORIGIN
    )
    assert saved.status_code == 200 and saved.json()["data"]["builtin"] is False
    mine = [t for t in (await client.get(f"{API}/templates")).json()["data"] if not t["builtin"]]
    assert [t["name"] for t in mine] == ["My review"]
    await client.delete(f"{API}/templates/{mine[0]['id']}", headers=ORIGIN)
    assert not [
        t for t in (await client.get(f"{API}/templates")).json()["data"] if not t["builtin"]
    ]

    copy = (
        await client.post(f"{API}/{automation['id']}/duplicate", json={}, headers=ORIGIN)
    ).json()["data"]
    assert copy["name"] == "Weekly review (copy)" and copy["enabled"] is False

    legacy = await client.post(
        API,
        json=body(
            [],
            workflow={
                "version": 1,
                "steps": [{"id": "t", "kind": "create_task", "arguments": {"title": "Old"}}],
            },
        ),
        headers=ORIGIN,
    )
    assert legacy.status_code == 201
    assert legacy.json()["data"]["workflow"]["steps"][0]["action"] == "notely.create_task"


@pytest.mark.parametrize("vendor", ["gmail"], indirect=True)
async def test_connector_to_connector_mapping(client: AsyncClient, vendor: VendorMock) -> None:
    import base64

    await signup(client)
    await connect_via_oauth(
        client, "gmail", CASES["gmail"], scopes=["https://www.googleapis.com/auth/gmail.compose"]
    )
    automation = await create(
        client,
        [
            action("mail", "gmail.search_mail", {"query": "is:important"}),
            action(
                "reply_draft",
                "gmail.draft_mail",
                {
                    "to": ["bob@acme.io"],
                    "subject": "Re: {{steps.mail.output.results.0.subject}}",
                    "body": "Following up on: {{steps.mail.output.results.0.snippet}}",
                },
                approval="auto",
            ),
        ],
    )
    detail = await run(client, automation["id"])
    assert detail["status"] == "completed", detail
    draft = next(r for r in vendor.captured.requests if r.url.path.endswith("/drafts"))
    raw = json.loads(draft.content)["message"]["raw"]
    message = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode()
    assert "Subject: Re: Q4 Launch Pricing" in message
    assert "Following up on: Let's finalize pricing" in message
    assert "untrusted_content" not in message


async def test_automations_stored_in_the_old_format_are_served_upgraded(
    client: AsyncClient,
) -> None:
    """Rows saved by the first version must never reach the browser in the old shape."""
    import uuid

    from app.db.session import get_session_factory
    from app.models.automation import Automation, AutomationAction, AutomationStatus
    from app.models.user import User

    await signup(client, email="legacy@example.com")
    async with get_session_factory()() as db:
        user = await db.scalar(select(User).where(User.email == "legacy@example.com"))
        assert user is not None
        row = Automation(
            id=uuid.uuid4(),
            tenant_id=user.tenant_id,
            user_id=user.id,
            name="Old planner",
            action=AutomationAction.workflow,
            action_config={
                "steps": [
                    {
                        "id": "plan",
                        "kind": "create_note",
                        "arguments": {"title": "Plan", "content": "x"},
                    },
                    {"id": "ping", "kind": "notify", "arguments": {"message": "Ready"}},
                ]
            },
            schedule_kind="daily",
            schedule_config={"time": "08:30"},
            timezone="UTC",
            status=AutomationStatus.paused,
            enabled=False,
        )
        db.add(row)
        await db.commit()
        automation_id = str(row.id)
    listed = (await client.get(API)).json()["data"][0]
    assert listed["workflow"]["version"] == 2
    assert [s["action"] for s in listed["workflow"]["steps"]] == [
        "notely.create_note",
        "notely.notify",
    ]
    detail = (await client.get(f"{API}/{automation_id}")).json()["data"]
    assert detail["workflow"]["steps"][0]["kind"] == "action"
    assert (await run(client, automation_id))["status"] == "completed"


def test_flat_ai_prose_becomes_a_readable_note() -> None:
    from app.automation.native import structure_prose

    prose = (
        "Summary: The emails cover service updates and verification issues. Key updates include "
        "a rejected application. Additionally, there are failed verification attempts. "
        "Actionable Items: 1. Title: Resubmit the application. Description: Add a valid URL. "
        "2. Title: Set up Brave Search API. Description: Generate an API key."
    )
    assert structure_prose(prose).splitlines() == [
        "## Summary",
        "- The emails cover service updates and verification issues.",
        "- Key updates include a rejected application.",
        "- Additionally, there are failed verification attempts.",
        "## Actionable Items",
        "1. **Resubmit the application** — Add a valid URL.",
        "2. **Set up Brave Search API** — Generate an API key.",
    ]
    doc = text_to_doc(prose)
    assert [b["type"] for b in doc["content"]] == [
        "heading",
        "bulletList",
        "heading",
        "orderedList",
    ]
    # Text that already has structure is never rearranged.
    assert structure_prose("## Today\n- one\n- two") == "## Today\n- one\n- two"
    assert structure_prose("A short answer.") == "A short answer."


def test_planner_details_only_the_apps_a_request_is_about() -> None:
    from app.automation.catalog import Catalog
    from app.automation.planner import relevant_apps

    apps = [
        {"id": app_id, "name": name}
        for app_id, name in [
            ("gmail", "Gmail"),
            ("google_sheets", "Google Sheets"),
            ("google_calendar", "Google Calendar"),
            ("slack", "Slack"),
            ("linear_mcp", "Linear"),
        ]
    ]
    catalog = Catalog(actions={}, apps=apps)
    assert relevant_apps("make daily random content and update in google sheet", catalog) == {
        "notely",
        "ai",
        "google_sheets",
    }
    assert relevant_apps("Summarize my inbox and post it to Slack", catalog) == {
        "notely",
        "ai",
        "gmail",
        "slack",
    }
    assert "linear_mcp" in relevant_apps("create a Linear issue", catalog)
    assert relevant_apps("tidy up", catalog, current=["google_calendar"]) == {
        "notely",
        "ai",
        "google_calendar",
    }


async def test_development_trusts_this_machine_on_any_port_but_not_other_sites(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Next.js moves to :3001 when :3000 is taken; that must not break writes in development."""
    from app.core.config import get_settings
    from app.main import create_app

    monkeypatch.setattr(get_settings(), "environment", "development")
    from httpx import ASGITransport

    async with AsyncClient(
        transport=ASGITransport(app=create_app(get_settings())), base_url="http://testserver"
    ) as dev:
        await signup(dev, email="port@example.com")
        local = await dev.post(
            API,
            json=body([action("t", "notely.notify", {"message": "hi"})]),
            headers={"Origin": "http://localhost:3001"},
        )
        assert local.status_code == 201, local.text
        foreign = await dev.post(
            API,
            json=body([action("t", "notely.notify", {"message": "hi"})]),
            headers={"Origin": "https://evil.example"},
        )
        assert foreign.status_code == 403


def test_google_api_turned_off_is_not_a_permission_problem() -> None:
    from app.integrations.base.errors import ProviderErrorKind, classify_http_status

    body = (
        '{"error":{"code":403,"message":"Google Sheets API has not been used in project 1234 '
        "before or it is disabled. Enable it by visiting https://console.developers.google.com"
        '/apis/api/sheets.googleapis.com/overview?project=1234 then retry.","status":'
        '"PERMISSION_DENIED"}}'
    )
    error = classify_http_status(403, provider="google_sheets", body_hint=body)
    assert error.kind == ProviderErrorKind.api_disabled
    assert error.detail == (
        "https://console.developers.google.com/apis/api/sheets.googleapis.com/overview?project=1234"
    )
    assert "Google Sheets API is turned off" in error.user_message()[1]
    plain = classify_http_status(403, provider="gmail", body_hint='{"error":"insufficient scope"}')
    assert plain.kind == ProviderErrorKind.permission_denied


def test_mapped_values_are_shaped_like_the_connector_expects() -> None:
    from app.automation.catalog import coerce

    rows = {"type": "array", "items": {"type": "array", "items": {"type": "string"}}}
    assert coerce("A fresh topic", rows) == [["A fresh topic"]]
    assert coerce(["Topic | 2026-09-23", "Other"], rows) == [["Topic", "2026-09-23"], ["Other"]]
    assert coerce([["x", 3]], rows) == [["x", "3"]]
    assert coerce("a\nb", {"type": "array", "items": {"type": "string"}}) == ["a", "b"]
    assert coerce("12", {"type": "integer"}) == 12
