"""A failed model call tells the user *why*, so the right person can fix it."""

from __future__ import annotations

from typing import Any

import httpx2
import openai
import pytest
from httpx import AsyncClient
from langchain_core.messages import AIMessage
from sqlalchemy.exc import OperationalError

from app.ai.errors import ModelErrorKind, classify, own_key_message, workspace_message
from app.ai.llm import ScriptedChatModel, set_fake_script
from app.tests.conftest import ORIGIN, read_sse, signup

_REQ = httpx2.Request("POST", "http://litellm:4000/v1/chat/completions")


def status_error(cls: type[openai.APIStatusError], status: int, text: str) -> Exception:
    return cls(text, response=httpx2.Response(status, request=_REQ), body=None)


@pytest.mark.parametrize(
    ("exc", "kind"),
    [
        (
            status_error(
                openai.AuthenticationError,
                401,
                "litellm.AuthenticationError: AnthropicException - invalid x-api-key",
            ),
            ModelErrorKind.auth,
        ),
        (
            status_error(
                openai.BadRequestError,
                400,
                "AnthropicException - Your credit balance is too low to access the API.",
            ),
            ModelErrorKind.billing,
        ),
        (
            status_error(
                openai.BadRequestError, 400, "prompt is too long: 210000 tokens > 200000 maximum"
            ),
            ModelErrorKind.context_too_long,
        ),
        (
            status_error(openai.NotFoundError, 404, "model: claude-x not found"),
            ModelErrorKind.model_not_found,
        ),
        (
            status_error(openai.PermissionDeniedError, 403, "no access"),
            ModelErrorKind.forbidden,
        ),
        (openai.APIConnectionError(request=_REQ), ModelErrorKind.unreachable),
        (openai.APITimeoutError(request=_REQ), ModelErrorKind.timeout),
        (
            status_error(openai.BadRequestError, 400, "bad tool schema"),
            ModelErrorKind.provider_error,
        ),
        # Our own bugs are never blamed on the provider, even when they mention a connection.
        (
            OperationalError("SELECT 1", {}, Exception("connection refused")),
            ModelErrorKind.internal,
        ),
        (KeyError("messages"), ModelErrorKind.internal),
    ],
)
def test_classify(exc: Exception, kind: ModelErrorKind) -> None:
    assert classify(exc).kind is kind


def test_messages_never_echo_provider_text() -> None:
    exc = status_error(openai.AuthenticationError, 401, "invalid x-api-key sk-ant-SECRET123")
    for message in (workspace_message(exc), own_key_message(exc)):
        assert "SECRET" not in message and "sk-" not in message
    assert "rejected this server's API key" in workspace_message(exc)


async def test_a_failed_chat_says_why(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    await signup(client)
    set_fake_script([AIMessage(content="unused")])

    def out_of_credit(self: Any, *args: Any, **kwargs: Any) -> Any:
        raise status_error(
            openai.BadRequestError, 400, "AnthropicException - Your credit balance is too low"
        )

    monkeypatch.setattr(ScriptedChatModel, "_generate", out_of_credit)
    resp = await client.post("/api/v1/ai/chat", json={"message": "hey"}, headers=ORIGIN)
    events = await read_sse(resp)
    error = next(e for e in events if e["type"] == "error")
    assert error["code"] == "AI_RUN_FAILED"
    assert "out of credit" in error["message"]
    assert events[-1]["status"] == "failed"

    # A reloaded conversation shows the same reason, not a generic one.
    thread = (await client.get("/api/v1/ai/threads")).json()["data"][0]
    detail = (await client.get(f"/api/v1/ai/threads/{thread['id']}")).json()["data"]
    assert "out of credit" in detail["last_run"]["error"]
