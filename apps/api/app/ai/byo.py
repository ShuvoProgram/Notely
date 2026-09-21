"""Bring-your-own model: a user's own provider + API key, used instead of the workspace gateway.

The application never talks to a vendor SDK from the agent code; it only asks this module for a
`BaseChatModel`. Keys are stored encrypted (see AISettingsService) and never returned to the
browser — only a hint (last four characters) is. The model catalog lives in `app.ai.catalog`."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import asdict, dataclass
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field, SecretStr

from app.ai.catalog import (
    CATALOG,
    BYOProvider,
    ModelSpec,
    ProviderSpec,
    Status,
    price_for,
    provider_as_dict,
    provider_spec,
    spec_for,
)

__all__ = [
    "CATALOG",
    "BYOModel",
    "BYOProvider",
    "ModelSpec",
    "ModelTest",
    "ProviderSpec",
    "as_dict",
    "build_model",
    "classify_error",
    "key_hint",
    "list_models",
    "normalise_base_url",
    "provider_spec",
    "test_model",
]

log = logging.getLogger(__name__)

TEST_TIMEOUT_SECONDS = 25
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
# OpenRouter asks integrations to identify themselves; both headers are public, non-secret.
OPENROUTER_HEADERS = {"HTTP-Referer": "https://notely.app", "X-Title": "Notely AI"}
_OPENROUTER_CACHE_TTL = 60 * 60


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
    if config.provider in (
        BYOProvider.openai,
        BYOProvider.openai_compatible,
        BYOProvider.openrouter,
    ):
        from langchain_openai import ChatOpenAI

        extra: dict[str, Any] = {}
        base_url = config.base_url
        if config.provider == BYOProvider.openrouter:
            base_url = OPENROUTER_BASE_URL
            extra["default_headers"] = OPENROUTER_HEADERS
        return ChatOpenAI(
            model=config.model,
            api_key=SecretStr(config.api_key or "not-needed"),
            base_url=base_url,
            temperature=temperature,
            timeout=timeout,
            max_retries=2,
            stream_usage=streaming,
            **extra,
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
    # None = not probed; False = the endpoint answered but cannot call tools, so the assistant
    # can chat but not act (search notes, create tasks, ...).
    supports_tools: bool | None = None


class _Ping(BaseModel):
    """A no-op tool: binding it is how we learn whether an endpoint supports tool calls."""

    word: str = Field(description="Any word")


async def test_model(config: BYOModel) -> ModelTest:
    """One tiny completion, then (for endpoints where it is not a given) one tool-call probe.
    Errors are categorised for the user; raw vendor text and the key are never echoed."""
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
    supports_tools: bool | None = None
    if config.provider in (BYOProvider.openai_compatible, BYOProvider.openrouter):
        supports_tools = await _probe_tools(model)
    detail = f"{config.model} answered in {latency} ms."
    if supports_tools is False:
        detail += " It cannot call tools, so the assistant can chat but not search or act."
    return ModelTest(True, detail, latency, supports_tools)


async def _probe_tools(model: BaseChatModel) -> bool:
    """Not every OpenAI-compatible server implements `tools`. Bind one and see."""
    try:
        bound = model.bind_tools([_Ping])
        reply = await asyncio.wait_for(
            bound.ainvoke([HumanMessage(content="Call the _Ping tool with the word hello.")]),
            TEST_TIMEOUT_SECONDS,
        )
    except Exception:  # noqa: BLE001 — a 4xx or a schema error both mean "no tools"
        return False
    return bool(getattr(reply, "tool_calls", None))


def classify_error(exc: Exception) -> str:
    status = getattr(exc, "status_code", None) or getattr(
        getattr(exc, "response", None), "status_code", None
    )
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    if status == 401 or "authentication" in name or "api key" in text or "unauthorized" in text:
        return "The API key was rejected. Check the key and the provider."
    if status == 402 or "insufficient credits" in text or "payment" in text:
        return "The provider says this key has no credit for that model."
    if status == 403 or "permission" in name:
        return "The API key does not have access to this model."
    if status == 404 or "notfound" in name or "does not exist" in text or "not found" in text:
        return "That model name was not found at the provider."
    if status == 429 or "ratelimit" in name or "quota" in text:
        return "The provider is rate-limiting or out of quota for this key."
    if "timeout" in name or "timed out" in text:
        return "The provider did not answer in time."
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
    ":batch",
)


def _chat_like(model_id: str) -> bool:
    lowered = model_id.lower()
    return not any(marker in lowered for marker in _NOT_CHAT)


def _with_spec(provider: BYOProvider, model_id: str) -> ModelSpec:
    known = spec_for(provider, model_id)
    return known if known is not None else ModelSpec(id=model_id, name=model_id)


_openrouter_cache: tuple[float, list[ModelSpec]] | None = None


async def _openrouter_models(http: Any) -> list[ModelSpec]:
    """OpenRouter's public catalog with pricing and context, cached for an hour. Free models
    are classified from the price fields, not from a hand-kept list."""
    global _openrouter_cache
    now = time.monotonic()
    if _openrouter_cache and now - _openrouter_cache[0] < _OPENROUTER_CACHE_TTL:
        return _openrouter_cache[1]
    response = await http.get(f"{OPENROUTER_BASE_URL}/models", headers=OPENROUTER_HEADERS)
    response.raise_for_status()
    out: list[ModelSpec] = []
    for m in response.json().get("data", []):
        model_id = str(m.get("id", ""))
        arch = m.get("architecture") or {}
        modality = str(arch.get("modality") or "")
        params = m.get("supported_parameters") or []
        if not model_id or not _chat_like(model_id) or not modality.endswith("->text"):
            continue
        pricing = m.get("pricing") or {}
        try:
            prompt = float(pricing.get("prompt") or 0) * 1_000_000
            completion = float(pricing.get("completion") or 0) * 1_000_000
        except (TypeError, ValueError):
            prompt = completion = None  # type: ignore[assignment]
        status: Status = "deprecated" if m.get("expiration_date") else "current"
        out.append(
            ModelSpec(
                id=model_id,
                name=str(m.get("name") or model_id),
                context=int(m["context_length"]) if m.get("context_length") else None,
                price=price_for(completion, prompt),
                status=status,
                tools="tools" in params,
            )
        )
    # Free first (that is what most people come here for), then newest by name.
    out.sort(key=lambda s: (s.price != "free", s.name.lower()))
    _openrouter_cache = (now, out)
    return out


async def list_models(config: BYOModel) -> list[ModelSpec]:
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
    elif config.provider == BYOProvider.openrouter:
        async with httpx.AsyncClient(timeout=TEST_TIMEOUT_SECONDS) as http:
            return await _openrouter_models(http)
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
    return [_with_spec(config.provider, m) for m in sorted(out, reverse=True)]


def key_hint(api_key: str) -> str:
    tail = api_key[-4:] if len(api_key) >= 8 else ""
    return f"…{tail}" if tail else "set"


def normalise_base_url(url: str | None) -> str | None:
    if not url:
        return None
    url = url.strip().rstrip("/")
    if not url.startswith(("http://", "https://")):
        raise ValueError("Base URL must start with http:// or https://")
    if " " in url or "@" in url.split("//", 1)[1].split("/", 1)[0]:
        raise ValueError("Enter just the endpoint URL, e.g. http://localhost:11434/v1")
    return url


def as_dict(spec: ProviderSpec) -> dict[str, Any]:
    return provider_as_dict(spec)


def model_as_dict(spec: ModelSpec) -> dict[str, Any]:
    return asdict(spec)
