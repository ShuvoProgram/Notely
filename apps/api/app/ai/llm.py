"""Chat model factory.

Every model call goes through the LiteLLM gateway using its OpenAI-compatible API, so the
application never depends on a specific vendor. Model *aliases* (`notely-default`, ...) are
resolved by LiteLLM's config, not here.

The `fake` provider is a scripted model for tests and offline development. It is refused in
production by `Settings.validate_for_runtime()`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_openai import ChatOpenAI

from app.core.config import Settings, get_settings

# Every prompt the fake model received, for assertions about what reached the model.
captured_prompts: list[list[BaseMessage]] = []


class ScriptedChatModel(FakeMessagesListChatModel):
    """Returns pre-scripted AIMessages in order; `bind_tools` is a no-op so agent code paths
    that attach tools keep working."""

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> ScriptedChatModel:
        return self

    def _generate(self, messages: list[BaseMessage], *args: Any, **kwargs: Any) -> Any:
        captured_prompts.append(list(messages))
        return super()._generate(messages, *args, **kwargs)


# Scripts consumed by the fake provider, keyed by user id (so parallel sessions don't collide).
# The `None` key is the shared default used by unit tests.
_fake_scripts: dict[str | None, list[AIMessage]] = {}


def set_fake_script(messages: list[AIMessage], *, user_id: str | None = None) -> None:
    _fake_scripts[user_id] = list(messages)
    captured_prompts.clear()


def _script_for(user_id: str | None) -> list[AIMessage]:
    return _fake_scripts.get(user_id) or _fake_scripts.get(None) or [AIMessage(content="")]


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
) -> BaseChatModel:
    settings = settings or get_settings()
    if settings.ai_provider == "fake":
        if settings.is_production:
            raise RuntimeError("fake AI provider is not permitted in production")
        return ScriptedChatModel(responses=_script_for(script_key))
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
