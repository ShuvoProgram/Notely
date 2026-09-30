"""Inline AI edits on a selection: streamed suggestion only, permissions enforced."""

from __future__ import annotations

from typing import Any

from httpx import ASGITransport, AsyncClient
from langchain_core.messages import AIMessage

from app.ai.inline_edit import InlineEditRequest, task_text
from app.ai.llm import captured_prompts, set_fake_script
from app.core.config import get_settings
from app.main import create_app
from app.tests.conftest import ORIGIN, read_sse, signup


async def edit(client: AsyncClient, **body: Any) -> Any:
    return await client.post("/api/v1/ai/edit", json=body, headers=ORIGIN)


async def test_suggests_a_replacement_for_the_selection_only(client: AsyncClient) -> None:
    await signup(client)
    note = (await client.post("/api/v1/notes", json={"title": "Launch"}, headers=ORIGIN)).json()[
        "data"
    ]
    set_fake_script([AIMessage(content='"We ship on Friday."')])
    resp = await edit(
        client,
        note_id=note["id"],
        operation="fix_grammar",
        selection="we ships on friday",
        before="Plan:",
        after="Then celebrate.",
    )
    assert resp.status_code == 200, resp.text
    events = await read_sse(resp)
    assert events[0] == {"type": "start", "operation": "fix_grammar", "mode": "replace"}
    assert events[-1] == {"type": "done", "text": "We ship on Friday.", "mode": "replace"}
    prompt = "\n".join(str(m.content) for m in captured_prompts[-1])
    assert "Fix spelling, grammar" in prompt and "Note title: Launch" in prompt
    assert "we ships on friday" in prompt and "Then celebrate." in prompt
    # Suggest-only: the note itself is untouched.
    assert (await client.get(f"/api/v1/notes/{note['id']}")).json()["data"]["version"] == 1


async def test_modes_and_validation(client: AsyncClient) -> None:
    await signup(client)
    nid = (await client.post("/api/v1/notes", json={"title": "N"}, headers=ORIGIN)).json()["data"][
        "id"
    ]
    set_fake_script([AIMessage(content="More text.")])
    events = await read_sse(await edit(client, note_id=nid, operation="continue", selection="Hi"))
    assert events[-1]["mode"] == "insert_after"
    set_fake_script([AIMessage(content="It means hello.")])
    events = await read_sse(await edit(client, note_id=nid, operation="explain", selection="Hi"))
    assert events[-1]["mode"] == "explain"
    assert (await edit(client, note_id=nid, operation="custom", selection="Hi")).status_code == 422
    assert (await edit(client, note_id=nid, operation="tone", selection="Hi")).status_code == 422
    assert (await edit(client, note_id=nid, operation="improve", selection="  ")).status_code == 422
    req = InlineEditRequest.model_validate(
        {"note_id": nid, "operation": "custom", "selection": "x", "instruction": "Be formal"}
    )
    assert "SELECTION only" in task_text(req) and "Be formal" in task_text(req)


async def test_viewers_can_only_explain_and_strangers_nothing(client: AsyncClient) -> None:
    await signup(client, email="ada@example.com")
    nid = (await client.post("/api/v1/notes", json={"title": "Shared"}, headers=ORIGIN)).json()[
        "data"
    ]["id"]
    transport = ASGITransport(app=create_app(get_settings()))
    async with AsyncClient(transport=transport, base_url="http://testserver") as bob:
        await signup(bob, email="bob@example.com")
        assert (await edit(bob, note_id=nid, operation="improve", selection="x")).status_code == 404
        await client.post(
            f"/api/v1/notes/{nid}/collaborators",
            json={"email": "bob@example.com", "role": "viewer"},
            headers=ORIGIN,
        )
        denied = await edit(bob, note_id=nid, operation="improve", selection="x")
        assert denied.status_code == 409 and denied.json()["error"]["code"] == "NOTE_READ_ONLY"
        set_fake_script([AIMessage(content="Explained.")])
        assert (await edit(bob, note_id=nid, operation="explain", selection="x")).status_code == 200
