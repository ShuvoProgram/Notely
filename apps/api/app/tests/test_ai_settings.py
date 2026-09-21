"""Bring-your-own model: per-user provider + API key, encrypted, never returned, used by runs."""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from langchain_core.messages import AIMessage
from sqlalchemy import select

from app.ai import byo
from app.ai.llm import set_fake_script
from app.core.config import get_settings
from app.models.ai import UserAISetting
from app.tests.conftest import ORIGIN, signup
from app.tests.test_ai import chat


async def put_model(client: AsyncClient, **overrides: Any) -> Any:
    payload = {
        "provider": "anthropic",
        "model": "claude-sonnet-5",
        "api_key": "sk-ant-api03-super-secret-key-1234",
        "verify": False,  # most tests are about storage; verification has its own tests
        **overrides,
    }
    return await client.put("/api/v1/ai/settings/model", json=payload, headers=ORIGIN)


async def test_settings_expose_provider_catalog_and_no_user_model(client: AsyncClient) -> None:
    await signup(client)
    data = (await client.get("/api/v1/ai/settings")).json()["data"]
    assert data["user_model"] is None
    assert data["encryption_available"] is True
    ids = [p["id"] for p in data["user_model_providers"]]
    assert ids == ["openai", "anthropic", "google", "openrouter", "openai_compatible"]
    compat = next(p for p in data["user_model_providers"] if p["id"] == "openai_compatible")
    assert compat["needs_base_url"] is True and compat["default_base_url"]
    assert compat["key_optional"] is True and compat["models"] == []
    router = next(p for p in data["user_model_providers"] if p["id"] == "openrouter")
    assert router["base_url_fixed"] is True and router["models"] == []
    openai = next(p for p in data["user_model_providers"] if p["id"] == "openai")
    # Catalog entries carry display metadata, and none of them is a retired model.
    assert {"id", "name", "tier", "context", "price", "status"} <= set(openai["models"][0])
    assert not any(m["id"].startswith(("gpt-4o", "gpt-3.5", "o1", "o3")) for m in openai["models"])


async def test_save_model_encrypts_key_and_returns_only_a_hint(client: AsyncClient) -> None:
    from app.db.session import get_session_factory

    await signup(client)
    resp = await put_model(client)
    assert resp.status_code == 200, resp.text
    out = resp.json()["data"]
    assert out == {
        "provider": "anthropic",
        "model": "claude-sonnet-5",
        "base_url": None,
        "key_hint": "…1234",
        "enabled": True,
        "verified_at": None,
        "last_error": None,
        "supports_tools": None,
    }
    assert "super-secret" not in resp.text
    async with get_session_factory()() as db:
        row = await db.scalar(select(UserAISetting))
    assert row is not None and row.api_key_encrypted
    assert "super-secret" not in row.api_key_encrypted
    # Settings never include the key either.
    settings_body = (await client.get("/api/v1/ai/settings")).text
    assert "super-secret" not in settings_body and "…1234" in settings_body

    # Updating without a key keeps the stored one; changing the model resets verification.
    again = await put_model(client, api_key="", model="claude-opus-5")
    assert again.status_code == 200 and again.json()["data"]["key_hint"] == "…1234"


async def test_validation_rules(client: AsyncClient) -> None:
    await signup(client)
    missing_key = await put_model(client, api_key=None)
    assert missing_key.status_code == 422
    assert missing_key.json()["error"]["details"]["fields"] == {"api_key": ["Required"]}
    bad_provider = await put_model(client, provider="mistral-cloud")
    assert bad_provider.status_code == 422
    needs_base = await put_model(client, provider="openai_compatible", api_key="")
    assert needs_base.status_code == 422
    assert needs_base.json()["error"]["details"]["fields"] == {"base_url": ["Required"]}
    bad_url = await put_model(client, provider="openai_compatible", base_url="localhost:11434")
    assert bad_url.status_code == 422
    # Local servers need no key.
    local = await put_model(
        client, provider="openai_compatible", base_url="http://localhost:11434/v1/", api_key=""
    )
    assert local.status_code == 200
    assert local.json()["data"]["base_url"] == "http://localhost:11434/v1"


async def test_runs_record_the_users_model_and_provider(client: AsyncClient) -> None:
    await signup(client)
    await put_model(client, provider="openai", model="gpt-4.1-mini", api_key="sk-proj-abcdefgh")
    set_fake_script([AIMessage(content="hi")])
    events = await chat(client, "hello")
    run = (await client.get(f"/api/v1/ai/runs/{events[0]['run_id']}")).json()["data"]
    assert run["provider"] == "byo:openai" and run["model"] == "gpt-4.1-mini"

    # Disabled → back to the workspace gateway.
    await put_model(client, provider="openai", model="gpt-4.1-mini", api_key="", enabled=False)
    set_fake_script([AIMessage(content="hi")])
    events = await chat(client, "hello again")
    run = (await client.get(f"/api/v1/ai/runs/{events[0]['run_id']}")).json()["data"]
    assert run["provider"] == "fake" and run["model"] == "notely-default"


async def test_test_endpoint_reports_categorised_failures(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await signup(client)
    nothing = await client.post("/api/v1/ai/settings/model/test", headers=ORIGIN)
    assert nothing.status_code == 422
    await put_model(client)

    class Rejected(Exception):
        status_code = 401

    async def fake_test(config: byo.BYOModel) -> byo.ModelTest:
        assert config.api_key == "sk-ant-api03-super-secret-key-1234"
        return byo.ModelTest(False, byo.classify_error(Rejected("nope")))

    monkeypatch.setattr("app.services.ai_settings_service.test_model", fake_test)
    resp = await client.post("/api/v1/ai/settings/model/test", headers=ORIGIN)
    assert resp.json()["data"] == {
        "ok": False,
        "detail": "The API key was rejected. Check the key and the provider.",
        "latency_ms": None,
        "supports_tools": None,
    }
    saved = (await client.get("/api/v1/ai/settings")).json()["data"]["user_model"]
    assert saved["verified_at"] is None and "rejected" in saved["last_error"]

    async def ok_test(config: byo.BYOModel) -> byo.ModelTest:
        return byo.ModelTest(True, "answered", 120)

    monkeypatch.setattr("app.services.ai_settings_service.test_model", ok_test)
    resp = await client.post("/api/v1/ai/settings/model/test", headers=ORIGIN)
    assert resp.json()["data"]["ok"] is True
    saved = (await client.get("/api/v1/ai/settings")).json()["data"]["user_model"]
    assert saved["verified_at"] and saved["last_error"] is None

    assert (await client.delete("/api/v1/ai/settings/model", headers=ORIGIN)).status_code == 200
    assert (await client.get("/api/v1/ai/settings")).json()["data"]["user_model"] is None


async def test_without_encryption_key_saving_is_refused(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await signup(client)
    monkeypatch.setattr(get_settings(), "encryption_key", "")
    resp = await put_model(client)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "ENCRYPTION_NOT_CONFIGURED"
    assert (await client.get("/api/v1/ai/settings")).json()["data"]["encryption_available"] is False


def test_build_model_uses_the_users_credentials() -> None:
    openai = byo.build_model(byo.BYOModel(byo.BYOProvider.openai, "gpt-4.1", "sk-x"))
    assert type(openai).__name__ == "ChatOpenAI"
    assert openai.model_name == "gpt-4.1"  # type: ignore[attr-defined]
    compat = byo.build_model(
        byo.BYOModel(byo.BYOProvider.openai_compatible, "llama3.1", "", "http://ollama:11434/v1")
    )
    assert str(compat.openai_api_base) == "http://ollama:11434/v1"  # type: ignore[attr-defined]
    anthropic = byo.build_model(byo.BYOModel(byo.BYOProvider.anthropic, "claude-sonnet-4-5", "k"))
    assert type(anthropic).__name__ == "ChatAnthropic"
    assert anthropic.model == "claude-sonnet-4-5"  # type: ignore[attr-defined]
    google = byo.build_model(byo.BYOModel(byo.BYOProvider.google, "gemini-2.5-flash", "AIza"))
    assert type(google).__name__ == "ChatGoogleGenerativeAI"
    # Every branch supports tool binding (the agent depends on it).
    for model in (openai, compat, anthropic, google):
        assert callable(getattr(model, "bind_tools", None))
    assert byo.key_hint("sk-ant-1234") == "…1234" and byo.key_hint("short") == "set"


async def test_models_are_listed_live_from_the_vendor(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The picker asks the vendor which models the key can use, filtering out non-chat ids."""
    import httpx

    calls: list[tuple[str, dict[str, str]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((str(request.url), dict(request.headers)))
        if request.url.host == "generativelanguage.googleapis.com":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "name": "models/gemini-3.1-pro-preview",
                            "supportedGenerationMethods": ["generateContent"],
                        },
                        {
                            "name": "models/gemini-2.5-flash",
                            "supportedGenerationMethods": ["generateContent"],
                        },
                        {
                            "name": "models/gemini-embedding-001",
                            "supportedGenerationMethods": ["embedContent"],
                        },
                        {"name": "models/veo-3", "supportedGenerationMethods": ["predict"]},
                    ]
                },
            )
        if request.headers.get("authorization") != "Bearer sk-live":
            return httpx.Response(401, json={"error": {"message": "bad key"}})
        return httpx.Response(
            200,
            json={
                "data": [
                    {"id": "gpt-5.2"},
                    {"id": "gpt-5-mini"},
                    {"id": "text-embedding-3-large"},
                    {"id": "whisper-1"},
                    {"id": "gpt-5.2"},
                ]
            },
        )

    real_client = httpx.AsyncClient

    def patched(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched)
    await signup(client)

    # A key being typed (not stored yet) is used directly and never persisted.
    resp = await client.post(
        "/api/v1/ai/settings/model/models",
        json={"provider": "google", "api_key": "AIza-typed"},
        headers=ORIGIN,
    )
    assert resp.status_code == 200, resp.text
    listed = resp.json()["data"]["models"]
    assert [m["id"] for m in listed] == ["gemini-3.1-pro-preview", "gemini-2.5-flash"]
    # Known ids pick up catalog metadata; unknown ones still list (name = id).
    assert (
        listed[0]["name"] == "Gemini 3.1 Pro (preview)" and listed[1]["name"] == "gemini-2.5-flash"
    )
    assert calls[-1][1]["x-goog-api-key"] == "AIza-typed"
    assert (await client.get("/api/v1/ai/settings")).json()["data"]["user_model"] is None

    # With a key stored for the provider, omitting api_key uses the stored one.
    await put_model(client, provider="openai", model="gpt-5.2", api_key="sk-live")
    resp = await client.post(
        "/api/v1/ai/settings/model/models", json={"provider": "openai"}, headers=ORIGIN
    )
    assert resp.status_code == 200, resp.text
    assert [m["id"] for m in resp.json()["data"]["models"]] == ["gpt-5.2", "gpt-5-mini"]

    # A rejected key surfaces the same friendly message as the Test button.
    resp = await client.post(
        "/api/v1/ai/settings/model/models",
        json={"provider": "openai", "api_key": "sk-wrong"},
        headers=ORIGIN,
    )
    assert resp.status_code == 422
    assert "rejected" in resp.json()["error"]["message"]

    # No key at all (and none stored for that provider) is a field error, not a vendor call.
    resp = await client.post(
        "/api/v1/ai/settings/model/models", json={"provider": "anthropic"}, headers=ORIGIN
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["details"]["fields"]["api_key"] == ["Required"]


async def test_saving_verifies_first_and_keeps_the_working_configuration(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify-then-write: a draft that fails never replaces what is saved; a draft that passes
    is stored already verified, with what the probe learned about tool support."""
    await signup(client)
    assert (await put_model(client)).status_code == 200  # verify=False: plain storage

    async def rejected(config: byo.BYOModel) -> byo.ModelTest:
        assert config.api_key == "sk-or-new-key-9999"  # the draft key is what gets tested
        return byo.ModelTest(False, "That model name was not found at the provider.")

    monkeypatch.setattr("app.services.ai_settings_service.test_model", rejected)
    resp = await put_model(
        client,
        provider="openrouter",
        model="nobody/no-such-model",
        api_key="sk-or-new-key-9999",
        verify=True,
    )
    assert resp.status_code == 422 and resp.json()["error"]["code"] == "MODEL_TEST_FAILED"
    assert "not found" in resp.json()["error"]["message"]
    saved = (await client.get("/api/v1/ai/settings")).json()["data"]["user_model"]
    assert saved["provider"] == "anthropic" and saved["key_hint"] == "…1234"  # untouched

    async def accepted(config: byo.BYOModel) -> byo.ModelTest:
        return byo.ModelTest(True, "answered", 90, supports_tools=False)

    monkeypatch.setattr("app.services.ai_settings_service.test_model", accepted)
    # Drafts can be tested without saving; the key in the body is used once and forgotten.
    draft = await client.post(
        "/api/v1/ai/settings/model/test",
        json={
            "provider": "openrouter",
            "model": "z-ai/glm-5.2:free",
            "api_key": "sk-or-new-key-9999",
        },
        headers=ORIGIN,
    )
    assert draft.status_code == 200 and draft.json()["data"]["supports_tools"] is False
    assert (await client.get("/api/v1/ai/settings")).json()["data"]["user_model"][
        "provider"
    ] == "anthropic"

    ok_save = await put_model(
        client,
        provider="openrouter",
        model="z-ai/glm-5.2:free",
        api_key="sk-or-new-key-9999",
        verify=True,
    )
    assert ok_save.status_code == 200, ok_save.text
    out = ok_save.json()["data"]
    assert out["verified_at"] and out["supports_tools"] is False and out["key_hint"] == "…9999"
    assert out["base_url"] == "https://openrouter.ai/api/v1"
    assert "sk-or-new-key" not in ok_save.text


async def test_openrouter_models_come_with_pricing(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "openrouter.ai"
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "z-ai/glm-5.2:free",
                        "name": "Z.ai: GLM 5.2 (free)",
                        "context_length": 200000,
                        "architecture": {"modality": "text->text"},
                        "pricing": {"prompt": "0", "completion": "0"},
                        "supported_parameters": ["tools"],
                    },
                    {
                        "id": "openai/gpt-5.5",
                        "name": "OpenAI: GPT-5.5",
                        "context_length": 1050000,
                        "architecture": {"modality": "text+image->text"},
                        "pricing": {"prompt": "0.000005", "completion": "0.00003"},
                        "supported_parameters": ["tools"],
                    },
                    {
                        "id": "some/tts-model",
                        "name": "Speech",
                        "architecture": {"modality": "text->audio"},
                        "pricing": {"prompt": "0", "completion": "0"},
                    },
                    {
                        "id": "openai/gpt-5.5:batch",
                        "name": "batch",
                        "architecture": {"modality": "text->text"},
                        "pricing": {"prompt": "0", "completion": "0"},
                    },
                ]
            },
        )

    real_client = httpx.AsyncClient

    def patched(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched)
    monkeypatch.setattr(byo, "_openrouter_cache", None)
    await signup(client)
    resp = await client.post(
        "/api/v1/ai/settings/model/models", json={"provider": "openrouter"}, headers=ORIGIN
    )
    assert resp.status_code == 200, resp.text
    models = resp.json()["data"]["models"]
    assert [(m["id"], m["price"]) for m in models] == [
        ("z-ai/glm-5.2:free", "free"),
        ("openai/gpt-5.5", "premium"),
    ]
    assert models[0]["context"] == 200000 and models[0]["tools"] is True
