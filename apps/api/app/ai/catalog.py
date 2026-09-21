"""The central model catalog for "bring your own model".

One place to update when vendors ship or retire models; nothing in the UI hardcodes a model
name. The static entries here are *suggestions* — shown before a key is entered and used to
attach display metadata — while the authoritative list always comes from the vendor at
request time (`byo.list_models`), so a name a key cannot use is never offered as usable.

Last reviewed against the vendors' live model listings on 2026-09-21. Pricing categories are
by output price per million tokens (free / budget < $2 / standard < $12 / premium).
"""

from __future__ import annotations

import enum
from dataclasses import asdict, dataclass
from typing import Any, Literal

Tier = Literal["flagship", "balanced", "fast"]
Price = Literal["free", "budget", "standard", "premium", "unknown"]
Status = Literal["current", "preview", "deprecated"]


class BYOProvider(enum.StrEnum):
    openai = "openai"
    anthropic = "anthropic"
    google = "google"
    openrouter = "openrouter"
    openai_compatible = "openai_compatible"  # Ollama, LM Studio, vLLM, Groq, Azure-compatible, ...


@dataclass(frozen=True)
class ModelSpec:
    id: str
    name: str
    tier: Tier = "balanced"
    context: int | None = None
    price: Price = "unknown"
    status: Status = "current"
    tools: bool = True
    note: str = ""


@dataclass(frozen=True)
class ProviderSpec:
    id: BYOProvider
    label: str
    tagline: str
    key_placeholder: str
    docs_url: str
    models: tuple[ModelSpec, ...]
    needs_base_url: bool = False
    default_base_url: str | None = None
    base_url_fixed: bool = False  # the endpoint is the vendor's, not user-editable
    key_optional: bool = False  # local servers usually run without one
    live_models: bool = True  # whether list_models can ask the vendor


def price_for(output_per_million: float | None, input_per_million: float | None = None) -> Price:
    if output_per_million is None:
        return "unknown"
    if output_per_million == 0 and (input_per_million or 0) == 0:
        return "free"
    if output_per_million < 2:
        return "budget"
    if output_per_million < 12:
        return "standard"
    return "premium"


CATALOG: tuple[ProviderSpec, ...] = (
    ProviderSpec(
        BYOProvider.openai,
        "OpenAI",
        "GPT models with your OpenAI key",
        "sk-…",
        "https://platform.openai.com/api-keys",
        (
            ModelSpec("gpt-5.6-luna", "GPT-5.6 Luna", "balanced", 1_050_000, "budget"),
            ModelSpec("gpt-5.5", "GPT-5.5", "flagship", 1_050_000, "premium"),
            ModelSpec("gpt-5.4", "GPT-5.4", "flagship", 1_050_000, "premium"),
            ModelSpec("gpt-5.4-mini", "GPT-5.4 Mini", "balanced", 400_000, "standard"),
            ModelSpec("gpt-5.4-nano", "GPT-5.4 Nano", "fast", 400_000, "budget"),
            ModelSpec("gpt-5.2", "GPT-5.2", "balanced", 400_000, "premium"),
            ModelSpec("gpt-5.1", "GPT-5.1", "balanced", 400_000, "standard"),
            ModelSpec("gpt-4.1", "GPT-4.1", "balanced", 1_047_576, "standard"),
        ),
    ),
    ProviderSpec(
        BYOProvider.anthropic,
        "Anthropic",
        "Claude models with your Anthropic key",
        "sk-ant-…",
        "https://console.anthropic.com/settings/keys",
        (
            ModelSpec("claude-sonnet-5", "Claude Sonnet 5", "balanced", 1_000_000, "standard"),
            ModelSpec("claude-opus-5", "Claude Opus 5", "flagship", 1_000_000, "premium"),
            ModelSpec("claude-fable-5-1", "Claude Fable 5.1", "flagship", 1_000_000, "premium"),
            ModelSpec("claude-haiku-4-5-20251001", "Claude Haiku 4.5", "fast", 200_000, "standard"),
        ),
    ),
    ProviderSpec(
        BYOProvider.google,
        "Google Gemini",
        "Gemini models with a Google AI Studio key",
        "AIza…",
        "https://aistudio.google.com/app/apikey",
        (
            ModelSpec("gemini-3.8-flash", "Gemini 3.8 Flash", "balanced", 1_048_576, "standard"),
            ModelSpec(
                "gemini-3.5-flash-lite", "Gemini 3.5 Flash Lite", "fast", 1_048_576, "standard"
            ),
            ModelSpec(
                "gemini-3.1-pro-preview",
                "Gemini 3.1 Pro (preview)",
                "flagship",
                1_048_576,
                "premium",
                "preview",
            ),
            ModelSpec(
                "gemini-3.1-flash-lite", "Gemini 3.1 Flash Lite", "fast", 1_048_576, "budget"
            ),
        ),
    ),
    ProviderSpec(
        BYOProvider.openrouter,
        "OpenRouter",
        "One key for hundreds of models, including free ones",
        "sk-or-…",
        "https://openrouter.ai/settings/keys",
        (),  # always live: OpenRouter publishes its catalog with pricing
        needs_base_url=True,
        default_base_url="https://openrouter.ai/api/v1",
        base_url_fixed=True,
    ),
    ProviderSpec(
        BYOProvider.openai_compatible,
        "OpenAI-compatible endpoint",
        "Ollama, LM Studio, vLLM, Groq or any server speaking the OpenAI API",
        "API key (optional for local servers)",
        "https://github.com/ollama/ollama/blob/main/docs/openai.md",
        (),  # whatever the server reports; there is no meaningful static list
        needs_base_url=True,
        default_base_url="http://localhost:11434/v1",
        key_optional=True,
    ),
)


def provider_spec(provider: BYOProvider) -> ProviderSpec:
    return next(p for p in CATALOG if p.id == provider)


def spec_for(provider: BYOProvider, model_id: str) -> ModelSpec | None:
    return next((m for m in provider_spec(provider).models if m.id == model_id), None)


def provider_as_dict(spec: ProviderSpec) -> dict[str, Any]:
    return {
        "id": spec.id.value,
        "label": spec.label,
        "tagline": spec.tagline,
        "key_placeholder": spec.key_placeholder,
        "docs_url": spec.docs_url,
        "models": [asdict(m) for m in spec.models],
        "needs_base_url": spec.needs_base_url,
        "default_base_url": spec.default_base_url,
        "base_url_fixed": spec.base_url_fixed,
        "key_optional": spec.key_optional,
        "live_models": spec.live_models,
    }
