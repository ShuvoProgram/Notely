# Notely AI

Capture thoughts. Connect your work. Let AI move things forward.

Notely is an AI-first notes workspace: a calm note-taking app with a powerful AI layer that can
read and act across your productivity tools — always with review before anything changes.

**Status:** Phases 1–6 complete — foundation, Notes, AI (LiteLLM gateway, LangGraph agent with
tool policy + human approval, streaming chat, note actions, tasks, audit log), the integration
framework (provider contract, OAuth/PKCE, encrypted credentials, connection status, capability
registry, MCP client, marketplace UI), the MVP providers (**Slack, Notion, Todoist, Asana, Jira,
Microsoft Teams, Outlook, Dropbox** plus a generic **MCP server**), unified search, and cross-app
AI: the agent plans multi-step work, reads across notes and connected apps, proposes every change
for one review, and **verifies each approved write with a read-back** before reporting it.
Phase 7 hardened it for production: security headers and body limits, per-user/tenant/IP/provider
rate limits, Prometheus metrics + request-scoped logs, categorised errors everywhere, index tuning,
a production config gate, and a TLS edge + runbook — see [docs/deployment.md](docs/deployment.md).
See [docs/architecture/overview.md](docs/architecture/overview.md) for what exists and what is next.

## Stack

| Layer     | Technology                                                                 |
| --------- | -------------------------------------------------------------------------- |
| Frontend  | Next.js 16 (App Router), React 19, TypeScript strict, Tailwind v4, shadcn/ui, TanStack Query, React Hook Form + Zod |
| API       | Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2 (async), Alembic          |
| Data      | PostgreSQL 17 + pgvector, Redis 7                                          |
| Jobs      | ARQ worker (Redis)                                                         |
| AI        | LiteLLM gateway (multi-provider), LangGraph agent runtime (Phase 3)        |
| Infra     | Docker Compose, multi-stage Dockerfiles                                    |

## Quick start (Docker)

```bash
cp .env.example .env
docker compose up --build
```

- Web: http://localhost:3000
- API: http://localhost:8000 (OpenAPI at `/docs` outside production)
- LiteLLM: http://localhost:4000

`migrate` runs `alembic upgrade head` before `api`/`worker` start.

> If a PostgreSQL already listens on `5432` on your machine, set `POSTGRES_PORT=55432` in `.env`;
> containers talk to each other on the internal network regardless.
>
> Running the Playwright suite signs up many accounts from one IP; set
> `RATE_LIMIT_AUTH_PER_MINUTE=200` for the API while running it locally (CI does this).

## Local development (without containers for app code)

Start only the data services:

```bash
docker compose up -d postgres redis
```

API:

```bash
cd apps/api
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

Worker: `uv run arq app.workers.main.WorkerSettings`

Web:

```bash
pnpm install
pnpm --filter web dev
```

The web app proxies `/api/*` to `API_INTERNAL_URL` (default `http://localhost:8000`) so the
HttpOnly session cookie is first-party.

## Tests

```bash
# API: unit/integration tests run against an isolated SQLite database, no services needed
cd apps/api && uv run pytest
uv run ruff check app && uv run mypy app

# Web: unit tests
pnpm --filter web test
pnpm --filter web typecheck && pnpm --filter web lint

# Web: end-to-end (needs a running stack on :3000/:8000)
pnpm --filter web test:e2e
```

## AI

Model calls go through the LiteLLM gateway (`infra/litellm/config.yaml` maps the `notely-*`
aliases to providers). Put at least one provider key in `.env` (`ANTHROPIC_API_KEY` or
`OPENAI_API_KEY`) and the assistant works end to end. Without a key, set `AI_PROVIDER=fake` for a
scripted model — tests and the e2e suite use it; production refuses it.

Write actions (create note/task, complete task) always pause for review; reads run automatically.
Every tool execution is recorded at `/app/settings/activity` → `GET /api/v1/audit`.

> Windows dev: the Postgres checkpointer needs a selector event loop — run uvicorn with
> `--reload` (as `.claude/launch.json` does) or use Docker.

### Cross-app workflows

Ask for something that spans apps ("Prepare the follow-up from my launch plan") and the assistant
declares a plan (`plan_steps`), searches notes and every connected app at once
(`search_everything`), reads what it needs, and proposes all changes together. After you approve,
each write is **read back** from the app (task exists, page exists, message is in the channel…)
and the result is shown as *Verified*, *Unverified* (the app gave nothing to read back) or
*Check failed* — the model is told the same outcome and cannot claim otherwise. Every source the
answer relied on is listed with the app it came from and when it was fetched.

Agent behaviour evals (tool/provider selection, approval enforcement, prompt-injection and
hallucination resistance) live in `apps/api/app/tests/evals/` and run against a live model:

```bash
cd apps/api && AI_EVAL=1 AI_PROVIDER=litellm LITELLM_API_BASE=http://localhost:4000 uv run pytest -m eval app/tests/evals
```

### Your own model (bring your own key)

Settings → AI → **Your own model**: pick OpenAI, Anthropic, Google Gemini or any OpenAI-compatible
endpoint (Ollama, LM Studio, OpenRouter, Groq…), type a model name, paste an API key and press
**Test**. The key is encrypted with `ENCRYPTION_KEY`, never returned to the browser (only a
`…last4` hint), and used only for that user's requests; the test runs a real one-token completion
and reports categorised failures (rejected key, unknown model, unreachable endpoint). Untick "Use
this model" to fall back to the workspace LiteLLM gateway without losing the key.

## Integrations

Settings → Connections lists providers from the backend registry (`apps/api/app/integrations/registry.py`).
Each provider implements `IntegrationProvider` (manifest, OAuth config, connect/test/refresh/revoke,
tools, search, sync, webhooks). Credentials are Fernet-encrypted with `ENCRYPTION_KEY`.

Try it locally with the bundled MCP server:

```bash
cd apps/api && uv run python scripts/demo_mcp_server.py --port 8765
```

then connect `http://127.0.0.1:8765/mcp` under Connections → MCP server (it needs no sign-in).
Its tools show up in the assistant; reads run automatically, writes ask for approval.

### Vendor providers

Fourteen adapters share one contract (`apps/api/app/integrations/<provider>/`): Slack, Notion,
Todoist, Asana, Jira, Microsoft Teams, Outlook, OneDrive, Gmail, Google Calendar, Google Drive,
ClickUp, Stripe, PayPal, plus any custom MCP server. Every one passes the same end-to-end
contract test against a mocked vendor API.

**Connecting is one click, always OAuth.** Press *Connect*, read the consent card (what Notely
can do, the risks, what the vendor receives), press *Continue with Notely* and approve on the
vendor's own screen — exactly like a ChatGPT connector. There is no token to paste, ever. Two
doors, tried in this order:

1. **The deployment's OAuth app** — `OAUTH_<PROVIDER>_CLIENT_ID` / `_SECRET` (Teams, Outlook and
   OneDrive share `OAUTH_MICROSOFT_*`; Gmail, Calendar and Drive share `OAUTH_GOOGLE_*`).
   Redirect URI: `{API_PUBLIC_URL}/api/v1/oauth/{provider}/callback`.
2. **The vendor's official MCP server** — no app registration at all. Notely discovers the
   server's authorization server (RFC 9728/8414), registers itself once per deployment (RFC 7591
   dynamic client registration) and runs a PKCE flow. Notion, Jira/Atlassian, ClickUp, Stripe and
   PayPal connect this way out of the box; any custom MCP server URL goes through the same
   discovery, and public servers connect instantly.

Vendors with neither door open on a deployment (no OAuth app registered, no official MCP server)
show *Not available on this deployment* until an administrator registers the app.

Provider ids: `slack`, `notion`, `todoist`, `asana`, `jira`, `microsoft_teams`, `outlook`,
`onedrive`, `dropbox`, `gmail`, `google_calendar`, `google_drive`, `clickup`, `stripe`, `paypal`,
`mcp_server`.
Tokens are stored encrypted, refreshed by the worker and never reach the browser. Every adapter
passes the same end-to-end test (`apps/api/app/tests/test_providers.py`) against a mocked vendor
API: OAuth exchange in the vendor's own token style, identity, health test, unified search, one
auto-run read tool and one approval-gated write tool, all audited.

## Production

`docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d` runs the hardened stack:
an nginx edge (TLS, SSE-safe proxying) is the only published port, `ENVIRONMENT=production`
turns on the startup configuration gate, `/metrics` is bearer-protected, and `/health/ready`
checks Postgres, Redis, configuration and the model gateway. The full checklist — secrets,
migrations, health/metrics, backups, scaling — is in [docs/deployment.md](docs/deployment.md).

## Secrets

Never commit `.env`. In production `SESSION_SECRET` and `ENCRYPTION_KEY` are mandatory; the API
refuses to start otherwise. Generate an encryption key with:

```bash
cd apps/api && uv run python -m app.core.crypto
```

## Repository layout

```
apps/web        Next.js application (app/, components/, features/, lib/, tests/)
apps/api        FastAPI application (app/api, core, db, models, schemas, services,
                repositories, workers, tests) + alembic/
packages/       shared-types, ui, config (populated as they gain content)
infra/          docker/, litellm/, nginx/, monitoring/
docs/           architecture/, decisions/, integrations/, api/
```
