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
        "model": "claude-sonnet-4-5",
        "api_key": "sk-ant-api03-super-secret-key-1234",
        **overrides,
    }
    return await client.put("/api/v1/ai/settings/model", json=payload, headers=ORIGIN)


async def test_settings_expose_provider_catalog_and_no_user_model(client: AsyncClient) -> None:
    await signup(client)
    data = (await client.get("/api/v1/ai/settings")).json()["data"]
    assert data["user_model"] is None
    assert data["encryption_available"] is True
    ids = [p["id"] for p in data["user_model_providers"]]
    assert ids == ["openai", "anthropic", "google", "openai_compatible"]
    compat = next(p for p in data["user_model_providers"] if p["id"] == "openai_compatible")
    assert compat["needs_base_url"] is True and compat["default_base_url"]


async def test_save_model_encrypts_key_and_returns_only_a_hint(client: AsyncClient) -> None:
    from app.db.session import get_session_factory

    await signup(client)
    resp = await put_model(client)
    assert resp.status_code == 200, resp.text
    out = resp.json()["data"]
    assert out == {
        "provider": "anthropic",
        "model": "claude-sonnet-4-5",
        "base_url": None,
        "key_hint": "…1234",
        "enabled": True,
        "verified_at": None,
        "last_error": None,
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
    again = await put_model(client, api_key="", model="claude-opus-4-1")
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
