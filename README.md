# Notely AI

Capture thoughts. Connect your work. Let AI move things forward.

Notely is an AI-first notes workspace: a calm note-taking app with a powerful AI layer that can
read and act across your productivity tools — always with review before anything changes.

**Status:** Phases 1–2 complete — foundation (monorepo, PostgreSQL + Alembic, auth/sessions, API
conventions, shell, design system, Docker, health checks) and Notes (TipTap editor, version-checked
autosave with local draft recovery, folders, tags, favorites/archive/trash, full-text search).
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
