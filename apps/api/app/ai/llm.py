"""Chat model factory.

Every model call goes through the LiteLLM gateway using its OpenAI-compatible API, so the
application never depends on a specific vendor. Model *aliases* (`notely-default`, ...) are
resolved by LiteLLM's config, not here.

The `fake` provider is a scripted model for tests and offline development. It is refused in
production by `Settings.validate_for_runtime()`.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator, Sequence
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, ToolCallChunk
from langchain_core.outputs import ChatGenerationChunk
from langchain_openai import ChatOpenAI

from app.ai.byo import BYOModel, build_model
from app.core.config import Settings, get_settings

# Every prompt the fake model received, for assertions about what reached the model.
captured_prompts: list[list[BaseMessage]] = []


class ScriptedChatModel(FakeMessagesListChatModel):
    """Returns pre-scripted AIMessages in order; `bind_tools` is a no-op so agent code paths
    that attach tools keep working.

    With `stream_delay` > 0 text replies stream word by word (AI_FAKE_STREAM_DELAY_MS), so
    concurrent runs can be exercised offline. A user message starting with `!fail` raises, to
    exercise per-thread error handling. Both only exist on the fake provider (never in prod)."""

    stream_delay: float = 0.0

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> ScriptedChatModel:
        return self

    def _generate(self, messages: list[BaseMessage], *args: Any, **kwargs: Any) -> Any:
        captured_prompts.append(list(messages))
        last_human = next((m for m in reversed(messages) if m.type == "human"), None)
        if last_human is not None and str(last_human.content).startswith("!fail"):
            raise RuntimeError("scripted failure")
        return super()._generate(messages, *args, **kwargs)

    async def _astream(
        self, messages: list[BaseMessage], *args: Any, **kwargs: Any
    ) -> AsyncIterator[ChatGenerationChunk]:
        message = self._generate(messages).generations[0].message
        assert isinstance(message, AIMessage)
        tool_chunks = [
            ToolCallChunk(name=tc["name"], args=json.dumps(tc["args"]), id=tc["id"], index=i)
            for i, tc in enumerate(message.tool_calls)
        ]
        text = message.text
        if self.stream_delay <= 0 or tool_chunks or not text:
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content=message.content,
                    tool_call_chunks=tool_chunks,
                    usage_metadata=message.usage_metadata,
                    id=message.id,
                )
            )
            return
        for i, word in enumerate(re.findall(r"\S+\s*|\s+", text)):
            if i:
                await asyncio.sleep(self.stream_delay)
            yield ChatGenerationChunk(message=AIMessageChunk(content=word, id=message.id))


# Scripts consumed by the fake provider, keyed by user id (so parallel sessions don't collide).
# The `None` key is the shared default used by unit tests.
_fake_scripts: dict[str | None, list[AIMessage]] = {}


def set_fake_script(messages: list[AIMessage], *, user_id: str | None = None) -> None:
    _fake_scripts[user_id] = list(messages)
    captured_prompts.clear()


def _has_script(user_id: str | None) -> bool:
    return bool(_fake_scripts.get(user_id) or _fake_scripts.get(None))


# What the scripted model says when nothing was scripted: an honest hint rather than silence.
UNSCRIPTED_REPLY = (
    "This deployment runs the scripted `fake` AI provider and no reply was scripted. "
    "Add your own model under Settings → AI, or point AI_PROVIDER at a real gateway."
)


def _script_for(user_id: str | None) -> list[AIMessage]:
    return (
        _fake_scripts.get(user_id)
        or _fake_scripts.get(None)
        or [AIMessage(content=UNSCRIPTED_REPLY)]
    )


def resolve_model_alias(settings: Settings, preference: str | None) -> str:
    """Only aliases known to the gateway config are accepted; anything else falls back."""
    allowed = {settings.ai_model_default, settings.ai_model_fast}
    return preference if preference in allowed else settings.ai_model_default


def get_chat_model(
    model: str | None = None,
    *,
    settings: Settings | None = None,
    temperature: float = 0.2,
    script_key: str | None = None,
    byo: BYOModel | None = None,
) -> BaseChatModel:
    """The model to run with: the scripted model in tests/dev, else the user's own provider
    (`byo`) when they configured one, else the workspace LiteLLM gateway."""
    settings = settings or get_settings()
    # The scripted model stands in for the *workspace gateway* only. A user who brought their
    # own key gets their real vendor even on a `fake` deployment — unless a test scripted the
    # reply for them, which is how the BYO plumbing itself is tested offline.
    if settings.ai_provider == "fake" and (byo is None or _has_script(script_key)):
        if settings.is_production:
            raise RuntimeError("fake AI provider is not permitted in production")
        return ScriptedChatModel(
            responses=_script_for(script_key),
            stream_delay=settings.ai_fake_stream_delay_ms / 1000,
        )
    if byo is not None:
        return build_model(
            byo, temperature=temperature, timeout=settings.ai_request_timeout_seconds
        )
    return ChatOpenAI(
        model=model or settings.ai_model_default,
        base_url=settings.litellm_api_base.rstrip("/"),
        api_key=settings.litellm_api_key or "sk-not-set",
        temperature=temperature,
        timeout=settings.ai_request_timeout_seconds,
        max_retries=2,
        stream_usage=True,
    )


def provider_name(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    return "fake" if settings.ai_provider == "fake" else "litellm"
