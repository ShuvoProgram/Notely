"""Bring-your-own model: a user's own provider + API key, used instead of the workspace gateway.

The application never talks to a vendor SDK from the agent code; it only asks this module for a
`BaseChatModel`. Keys are stored encrypted (see AISettingsService) and never returned to the
browser — only a hint (last four characters) is."""

from __future__ import annotations

import asyncio
import enum
import time
from dataclasses import dataclass
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from pydantic import SecretStr

TEST_TIMEOUT_SECONDS = 25


class BYOProvider(enum.StrEnum):
    openai = "openai"
    anthropic = "anthropic"
    google = "google"
    openai_compatible = "openai_compatible"  # Ollama, OpenRouter, Groq, Azure-compatible, ...


@dataclass(frozen=True)
class ProviderInfo:
    id: BYOProvider
    label: str
    key_placeholder: str
    docs_url: str
    models: tuple[str, ...]
    needs_base_url: bool = False
    default_base_url: str | None = None


# Fallback suggestions per provider, shown until a key is entered; with a key, the real list
# comes from the vendor (`list_models`). The model field stays free text either way.
PROVIDER_CATALOG: tuple[ProviderInfo, ...] = (
    ProviderInfo(
        BYOProvider.openai,
        "OpenAI",
        "sk-…",
        "https://platform.openai.com/api-keys",
        ("gpt-5.2", "gpt-5.1", "gpt-5-mini", "gpt-5-nano", "gpt-4.1"),
    ),
    ProviderInfo(
        BYOProvider.anthropic,
        "Anthropic",
        "sk-ant-…",
        "https://console.anthropic.com/settings/keys",
        (
            "claude-opus-5",
            "claude-sonnet-5",
            "claude-haiku-4-5-20251001",
            "claude-sonnet-4-5",
        ),
    ),
    ProviderInfo(
        BYOProvider.google,
        "Google Gemini",
        "AIza…",
        "https://aistudio.google.com/app/apikey",
        ("gemini-3.1-pro-preview", "gemini-3-flash-preview", "gemini-2.5-pro", "gemini-2.5-flash"),
    ),
    ProviderInfo(
        BYOProvider.openai_compatible,
        "OpenAI-compatible endpoint",
        "API key (optional for local servers)",
        "https://github.com/ollama/ollama/blob/main/docs/openai.md",
        ("llama3.3", "qwen3", "gemma3", "mistral"),
        needs_base_url=True,
        default_base_url="http://localhost:11434/v1",
    ),
)


def provider_info(provider: BYOProvider) -> ProviderInfo:
    return next(p for p in PROVIDER_CATALOG if p.id == provider)


@dataclass(frozen=True)
class BYOModel:
    """A resolved user model configuration (key already decrypted, in memory only)."""

    provider: BYOProvider
    model: str
    api_key: str
    base_url: str | None = None

    @property
    def label(self) -> str:
        return f"byo:{self.provider.value}"


def build_model(
    config: BYOModel, *, temperature: float = 0.2, timeout: float = 90, streaming: bool = True
) -> BaseChatModel:
    """Vendor client for the user's configuration. Tool calling works on every branch."""
    if config.provider in (BYOProvider.openai, BYOProvider.openai_compatible):
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=config.model,
            api_key=SecretStr(config.api_key or "not-needed"),
            base_url=config.base_url,
            temperature=temperature,
            timeout=timeout,
            max_retries=2,
            stream_usage=streaming,
        )
    if config.provider == BYOProvider.anthropic:
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=config.model,
            api_key=SecretStr(config.api_key),
            temperature=temperature,
            timeout=timeout,
            max_retries=2,
            max_tokens=4096,
        )
    if config.provider == BYOProvider.google:
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=config.model,
            google_api_key=SecretStr(config.api_key),
            temperature=temperature,
            timeout=timeout,
            max_retries=2,
        )
    raise ValueError(f"unsupported provider {config.provider}")


@dataclass(frozen=True)
class ModelTest:
    ok: bool
    detail: str
    latency_ms: int | None = None


async def test_model(config: BYOModel) -> ModelTest:
    """One tiny completion. Errors are categorised for the user; raw vendor text is not shown."""
    started = time.perf_counter()
    try:
        model = build_model(config, temperature=0, timeout=TEST_TIMEOUT_SECONDS, streaming=False)
        reply = await asyncio.wait_for(
            model.ainvoke([HumanMessage(content="Reply with the single word OK.")]),
            TEST_TIMEOUT_SECONDS + 5,
        )
    except TimeoutError:
        return ModelTest(False, "The provider did not answer in time.")
    except Exception as exc:  # noqa: BLE001 — vendor SDKs raise many types; classify by shape
        return ModelTest(False, classify_error(exc))
    latency = int((time.perf_counter() - started) * 1000)
    text = reply.text if hasattr(reply, "text") else str(reply.content)
    if not str(text).strip():
        return ModelTest(False, "The model answered with empty output.", latency)
    return ModelTest(True, f"{config.model} answered in {latency} ms.", latency)


def classify_error(exc: Exception) -> str:
    status = getattr(exc, "status_code", None) or getattr(
        getattr(exc, "response", None), "status_code", None
    )
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    if status == 401 or "authentication" in name or "api key" in text or "unauthorized" in text:
        return "The API key was rejected. Check the key and the provider."
    if status == 403 or "permission" in name:
        return "The API key does not have access to this model."
    if status == 404 or "notfound" in name or "does not exist" in text or "not found" in text:
        return "That model name was not found at the provider."
    if status == 429 or "ratelimit" in name or "quota" in text:
        return "The provider is rate-limiting or out of quota for this key."
    if "connect" in name or "connection" in text or "resolve" in text or status in (502, 503):
        return "Could not reach the provider. Check the base URL and your network."
    return "The provider returned an error. Check the model name and try again."


# Model ids that are not chat models and would only confuse the picker.
_NOT_CHAT = (
    "embed",
    "embedding",
    "tts",
    "whisper",
    "transcribe",
    "audio",
    "realtime",
    "dall-e",
    "image",
    "imagen",
    "veo",
    "lyria",
    "moderation",
    "aqa",
    "computer-use",
    "search",
    "-live",
)


def _chat_like(model_id: str) -> bool:
    lowered = model_id.lower()
    return not any(marker in lowered for marker in _NOT_CHAT)


async def list_models(config: BYOModel) -> list[str]:
    """The models this key can actually use, straight from the vendor's list endpoint, so the
    picker never shows a name the provider will reject. `config.model` may be empty here."""
    import httpx

    headers: dict[str, str] = {}
    if config.provider == BYOProvider.openai:
        url = "https://api.openai.com/v1/models"
        headers["Authorization"] = f"Bearer {config.api_key}"
    elif config.provider == BYOProvider.openai_compatible:
        url = f"{(config.base_url or '').rstrip('/')}/models"
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"
    elif config.provider == BYOProvider.anthropic:
        url = "https://api.anthropic.com/v1/models?limit=100"
        headers["x-api-key"] = config.api_key
        headers["anthropic-version"] = "2023-06-01"
    else:
        url = "https://generativelanguage.googleapis.com/v1beta/models?pageSize=200"
        headers["x-goog-api-key"] = config.api_key
    async with httpx.AsyncClient(timeout=TEST_TIMEOUT_SECONDS) as http:
        response = await http.get(url, headers=headers)
    response.raise_for_status()
    body = response.json()
    ids: list[str] = []
    if config.provider == BYOProvider.google:
        for m in body.get("models", []):
            if "generateContent" not in (m.get("supportedGenerationMethods") or []):
                continue
            ids.append(str(m.get("name", "")).removeprefix("models/"))
    else:
        ids = [str(m.get("id", "")) for m in body.get("data", [])]
    seen: set[str] = set()
    out: list[str] = []
    for model_id in ids:
        if model_id and _chat_like(model_id) and model_id not in seen:
            seen.add(model_id)
            out.append(model_id)
    # Newest first is the most useful order; vendors mostly follow a version-in-name convention.
    return sorted(out, reverse=True)


def key_hint(api_key: str) -> str:
    tail = api_key[-4:] if len(api_key) >= 8 else ""
    return f"…{tail}" if tail else "set"


def normalise_base_url(url: str | None) -> str | None:
    if not url:
        return None
    url = url.strip().rstrip("/")
    if not url.startswith(("http://", "https://")):
        raise ValueError("Base URL must start with http:// or https://")
    return url


def as_dict(info: ProviderInfo) -> dict[str, Any]:
    return {
        "id": info.id.value,
        "label": info.label,
        "key_placeholder": info.key_placeholder,
        "docs_url": info.docs_url,
        "models": list(info.models),
        "needs_base_url": info.needs_base_url,
        "default_base_url": info.default_base_url,
    }
