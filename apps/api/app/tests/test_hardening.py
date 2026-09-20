"""Phase 7 — production hardening: security headers, request limits, rate-limit identities,
categorised provider errors, metrics and log context."""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest
from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient

from app.core import metrics
from app.core.config import Settings, get_settings
from app.core.exceptions import PROVIDER_STATUS
from app.core.logging import ContextFilter, RedactingFilter
from app.integrations.base.errors import ProviderError, ProviderErrorKind
from app.main import create_app
from app.tests.conftest import ORIGIN, signup

# --- security headers -----------------------------------------------------------------------------


async def test_security_headers_on_every_response(client: AsyncClient) -> None:
    resp = await client.get("/health")
    h = resp.headers
    assert h["x-content-type-options"] == "nosniff"
    assert h["x-frame-options"] == "DENY"
    assert h["cross-origin-opener-policy"] == "same-origin"
    assert h["cross-origin-resource-policy"] == "same-origin"
    assert "camera=()" in h["permissions-policy"]
    assert h["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"
    assert h["cache-control"] == "no-store"
    # HSTS only when cookies are secure (TLS); the test settings are plain http.
    assert "strict-transport-security" not in h


async def test_hsts_sent_when_cookies_are_secure(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "session_cookie_secure", True)
    app = create_app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.get("/health")
    assert resp.headers["strict-transport-security"].startswith("max-age=63072000")


# --- request limits -----------------------------------------------------------------------------


async def test_oversized_body_is_rejected_before_parsing(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await signup(client)
    settings = get_settings()
    monkeypatch.setattr(settings, "max_request_bytes", 1024)
    app = create_app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
        c.cookies = client.cookies
        big = {"title": "x", "content_json": {"type": "doc", "content": [], "pad": "y" * 5000}}
        resp = await c.post("/api/v1/notes", json=big, headers=ORIGIN)
    assert resp.status_code == 413
    assert resp.json()["error"] == {
        "code": "PAYLOAD_TOO_LARGE",
        "message": "The request body is too large.",
        "details": {"max_bytes": 1024},
    }


# --- rate limiting identities ------------------------------------------------------------------


async def test_tenant_rate_limit_is_shared_by_a_tenant_and_ip_limit_is_not_spoofable(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.rate_limit import client_ip, identity_for

    class Req:
        def __init__(self, headers: dict[str, str], user: str | None, tenant: str | None) -> None:
            self.headers = headers
            self.path_params = {"provider_id": "slack"}
            self.state = type("S", (), {})()
            if user:
                self.state.user_id = user
            if tenant:
                self.state.tenant_id = tenant
            self.client = type("C", (), {"host": "10.0.0.9"})()

    spoofed = Req({"x-forwarded-for": "1.2.3.4"}, None, None)
    # Forwarded headers are ignored unless the deployment is declared to sit behind a proxy.
    assert client_ip(spoofed) == "10.0.0.9"  # type: ignore[arg-type]
    monkeypatch.setattr(get_settings(), "trust_proxy_headers", True)
    assert client_ip(spoofed) == "1.2.3.4"  # type: ignore[arg-type]

    r = Req({}, "u1", "t1")
    assert identity_for(r, "user") == "u:u1"  # type: ignore[arg-type]
    assert identity_for(r, "tenant") == "t:t1"  # type: ignore[arg-type]
    assert identity_for(r, "provider") == "slack:10.0.0.9"  # type: ignore[arg-type]
    assert identity_for(Req({}, None, None), "tenant") == "10.0.0.9"  # type: ignore[arg-type]


async def test_search_and_oauth_routes_are_rate_limited(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await signup(client)
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_search_per_minute", 2)
    monkeypatch.setattr(settings, "rate_limit_oauth_per_minute", 1)
    codes = [(await client.get("/api/v1/search", params={"q": "x"})).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    first = await client.get("/api/v1/oauth/slack/start")
    second = await client.get("/api/v1/oauth/slack/start")
    assert first.status_code != 429 and second.status_code == 429
    assert second.headers["retry-after"].isdigit()


# --- provider errors are categorised, never raw -------------------------------------------------


async def test_provider_errors_map_to_one_error_envelope(client: AsyncClient) -> None:
    app = create_app(get_settings())
    router = APIRouter()

    @router.get("/_boom/{kind}")
    async def boom(kind: str) -> None:
        raise ProviderError(ProviderErrorKind(kind), "raw detail", provider="slack", retry_after=7)

    app.include_router(router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        for kind in ProviderErrorKind:
            resp = await c.get(f"/_boom/{kind.value}")
            assert resp.status_code == PROVIDER_STATUS[kind.value], kind
            body = resp.json()["error"]
            assert body["code"] == f"PROVIDER_{kind.value.upper()}"
            assert "raw detail" not in json.dumps(body)  # only the categorised message
            assert body["details"]["provider"] == "slack"
            assert body["details"]["retryable"] == (
                kind in (ProviderErrorKind.rate_limited, ProviderErrorKind.unavailable)
            )
        assert (await c.get("/_boom/rate_limited")).headers["retry-after"] == "7"


async def test_unhandled_exception_never_leaks(client: AsyncClient) -> None:
    app = create_app(get_settings())
    router = APIRouter()

    @router.get("/_crash")
    async def crash() -> None:
        raise RuntimeError("database password is hunter2")

    app.include_router(router)
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        resp = await c.get("/_crash")
    assert resp.status_code == 500
    assert resp.json() == {
        "error": {
            "code": "INTERNAL_ERROR",
            "message": "Something went wrong on our side.",
            "details": {},
        }
    }
    assert "hunter2" not in resp.text


# --- observability ------------------------------------------------------------------------------


async def test_metrics_endpoint_requires_token_when_set(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await signup(client)
    await client.get("/api/v1/notes")
    await client.get("/api/v1/notes/00000000-0000-0000-0000-000000000000")
    body = (await client.get("/metrics")).text
    assert "notely_http_requests_total" in body
    assert 'route="/api/v1/notes"' in body
    assert 'route="/api/v1/notes/{note_id}"' in body
    assert "00000000-0000" not in body
    assert "notely_db_query_seconds" in body
    # Labels are route templates, never raw paths with ids, and never user ids.
    assert "ada@example.com" not in body

    monkeypatch.setattr(get_settings(), "metrics_token", "scrape-secret")
    assert (await client.get("/metrics")).status_code == 401
    ok = await client.get("/metrics", headers={"Authorization": "Bearer scrape-secret"})
    assert ok.status_code == 200 and ok.headers["content-type"].startswith("text/plain")


async def test_ai_and_provider_metrics_are_recorded(client: AsyncClient) -> None:
    from langchain_core.messages import AIMessage

    from app.ai.llm import set_fake_script
    from app.tests.test_ai import chat, tool_call

    await signup(client)
    before = metrics.ai_tool_calls.labels("notely", "search_notes", "completed")._value.get()  # noqa: SLF001
    set_fake_script(
        [
            AIMessage(content="", tool_calls=[tool_call("search_notes", {"query": "x"}, "c1")]),
            AIMessage(content="none"),
        ]
    )
    await chat(client, "find x")
    after = metrics.ai_tool_calls.labels("notely", "search_notes", "completed")._value.get()  # noqa: SLF001
    assert after == before + 1
    body = (await client.get("/metrics")).text
    assert 'notely_ai_runs_total{model="notely-default",status="completed"}' in body


def test_log_records_carry_request_context_and_redact_secrets() -> None:
    from app.core.logging import request_id_var, user_id_var

    record = logging.LogRecord("t", logging.INFO, "f", 1, "msg", None, None)
    record.__dict__["access_token"] = "xoxp-secret"
    record.__dict__["password"] = "hunter2"
    request_id_var.set("req-1")
    user_id_var.set("user-1")
    assert RedactingFilter().filter(record) and ContextFilter().filter(record)
    assert record.__dict__["access_token"] == "[redacted]"
    assert record.__dict__["password"] == "[redacted]"
    assert record.request_id == "req-1" and record.user_id == "user-1"  # type: ignore[attr-defined]


# --- production configuration gate ---------------------------------------------------------------


def test_production_settings_refuse_insecure_configuration() -> None:
    settings = Settings(
        environment="production",
        session_secret="dev-only-session-secret-change-me",
        encryption_key="",
        api_public_url="http://api.example.com",
        frontend_origin="http://app.example.com",
        metrics_enabled=True,
        metrics_token="",
        ai_provider="fake",
    )
    problems = "\n".join(settings.validate_for_runtime())
    for expected in (
        "SESSION_SECRET",
        "ENCRYPTION_KEY",
        "AI_PROVIDER=fake",
        "METRICS_TOKEN",
        "API_PUBLIC_URL must be https",
        "FRONTEND_ORIGIN must be https",
    ):
        assert expected in problems, expected


def test_worker_jobs_are_instrumented() -> None:
    import asyncio

    from app.workers.instrument import instrumented

    async def flaky(ctx: dict[str, Any], fail: bool) -> str:
        if fail:
            raise RuntimeError("boom")
        return "ok"

    wrapped = instrumented(flaky)
    assert wrapped.__name__ == "flaky"
    ok_before = metrics.jobs.labels("flaky", "completed")._value.get()  # noqa: SLF001
    fail_before = metrics.jobs.labels("flaky", "failed")._value.get()  # noqa: SLF001

    async def run(fail: bool) -> str:
        return await wrapped({}, fail)

    assert asyncio.run(run(False)) == "ok"
    with pytest.raises(RuntimeError):
        asyncio.run(run(True))
    assert metrics.jobs.labels("flaky", "completed")._value.get() == ok_before + 1  # noqa: SLF001
    assert metrics.jobs.labels("flaky", "failed")._value.get() == fail_before + 1  # noqa: SLF001
