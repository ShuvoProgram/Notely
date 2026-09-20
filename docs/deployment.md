# Deploying Notely

```
CDN / TLS edge (nginx)
   ├── /api, /health, /metrics ──► FastAPI (api)  ──► Redis ◄── worker (ARQ)
   └── everything else ─────────► Next.js (web)      └──► PostgreSQL (+pgvector)
                                                   FastAPI ──► LiteLLM ──► model providers
                                                   Agent   ──► MCP client ──► MCP / vendor APIs
```

Everything below assumes the compose deployment (`docker-compose.yml` + `docker-compose.prod.yml`).
The same containers run unchanged on any orchestrator; only the edge and secrets wiring differ.

## 1. Configuration checklist

Copy `.env.example` to `.env` on the host (never commit it) and set:

| Variable | Notes |
|---|---|
| `ENVIRONMENT=production` | Turns on the startup gate below and secure cookies. |
| `SESSION_SECRET` | ≥ 32 random bytes. Rotating it signs everyone out. |
| `ENCRYPTION_KEY` | Fernet key from `uv run python -m app.core.crypto`. Rotating it invalidates stored provider tokens (users reconnect). |
| `POSTGRES_PASSWORD` | Used by the compose Postgres and the `DATABASE_URL` it builds. |
| `FRONTEND_ORIGIN`, `ALLOWED_ORIGINS`, `API_PUBLIC_URL` | All `https://…`. With the bundled edge they are the same host (`https://notes.example.com`). |
| `LITELLM_MASTER_KEY` + `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` | Model providers, configured in `infra/litellm/config.yaml`. |
| `OAUTH_*_CLIENT_ID/SECRET` | One pair per integration you enable; redirect URI `https://<host>/api/v1/oauth/<provider>/callback`. |
| `METRICS_TOKEN` | Bearer token Prometheus presents to `/metrics`. Required in production. |
| `TRUST_PROXY_HEADERS=true` | Only behind a proxy that sets `X-Forwarded-For` (the bundled edge does). |
| `WEB_SECURE=true` | Bakes HSTS into the web build. |
| `TLS_CERT_DIR` | Directory with `fullchain.pem` + `privkey.pem` for the edge. |

The API **refuses to start** in production when any of these are wrong (`Settings.validate_for_runtime`):
development session secret, missing/invalid `ENCRYPTION_KEY`, `DEBUG`, `AI_PROVIDER=fake`,
memory checkpointer, missing `METRICS_TOKEN`, non-https public URLs. `/health/ready` reports the
same problems as `configuration: false` without revealing values.

## 2. First deploy

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml build
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps   # migrate exits 0, others healthy
curl -fsS https://<host>/health/ready
```

`migrate` runs `alembic upgrade head` before `api`/`worker` start and is the **only** way the schema
changes (PRD 66). Never edit the production schema by hand.

## 3. Upgrades

```bash
git pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml build
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d   # runs new migrations first
```

Migrations are written to be forward-only in production; every migration has a tested
`downgrade()` (CI runs `downgrade base && upgrade head` and `alembic check`) so a rollback is
`alembic downgrade <rev>` followed by deploying the previous image.

Approval pauses survive restarts (LangGraph checkpoints in Postgres, `durability="sync"`), so a
rolling restart of `api` never loses an in-flight review.

## 4. Health, readiness, metrics

| Endpoint | Purpose |
|---|---|
| `GET /health` / `/health/live` | Process is up. Container `HEALTHCHECK` and edge probe. |
| `GET /health/ready` | 200 only when Postgres, Redis, configuration and the LiteLLM gateway are all OK; 503 with per-check booleans otherwise. Use it for load-balancer readiness. |
| `GET /metrics` | Prometheus exposition, `Authorization: Bearer $METRICS_TOKEN`. `infra/monitoring/prometheus.yml` + `alerts.yml` are a starting point. |

The worker's health is `arq --check` (wired as its container `HEALTHCHECK`); queue depth and job
outcomes are on `/metrics` (`notely_queue_depth`, `notely_jobs_total`).

What is measured (PRD 51): request latency/error rate by route template, DB statement latency,
queue depth, job outcomes; AI runs by model/status, run latency, tokens, tool calls and
failures, approval decisions, verification outcomes; provider API latency, provider error kinds,
OAuth failures, webhook deliveries, connections by status. Labels never contain user ids, paths
with ids, or content.

Logs are JSON on stdout with `request_id` and `user_id` on every line of a request; secrets and
tokens are redacted by key name. Ship them with your usual collector.

## 5. Security posture (what the deployment relies on)

- Opaque server-side sessions in `HttpOnly; Secure; SameSite=Lax` cookies; CSRF via origin checks.
- Provider tokens encrypted at rest (Fernet), never sent to the browser, never logged.
- OAuth: server-side single-use state, PKCE where the vendor supports it, per-IP rate limit.
- Rate limits per user, tenant, IP and provider on auth, AI, search, OAuth and webhooks; `Retry-After` on 429.
- Request bodies capped (`MAX_REQUEST_BYTES`, `MAX_WEBHOOK_BYTES`); 413 before parsing.
- Security headers on both apps (CSP, HSTS, COOP/CORP, Permissions-Policy, nosniff, frame-ancestors none).
- Every AI write is policy-checked, approved by a human, executed server-side, verified and audited.
- Containers run as non-root users; only the edge publishes ports.

Keep the edge and OS patched; CI runs `pip-audit` / `pnpm audit` and a secret scan on every push.

## 6. Backups and data

- **PostgreSQL** is the source of truth: `pg_dump` the `notely` database on a schedule (daily + WAL
  archiving for point-in-time recovery). Restore = restore the dump, then `docker compose up -d`
  (migrations are idempotent).
- **Redis** holds only rate-limit counters, OAuth state, the job queue and cancellation flags;
  losing it costs nothing durable.
- Disconnecting an integration revokes tokens; "purge" deletes the indexed copies (`external_items`).

## 7. Scaling

- `api` is stateless: scale replicas behind the edge. SSE streams are long-lived; keep
  `proxy_read_timeout` ≥ the AI request timeout (`AI_REQUEST_TIMEOUT_SECONDS`, default 90 s).
- `worker` scales independently (`max_jobs` per process = 10).
- Postgres pool per API process: `DB_POOL_SIZE` (10) + `DB_MAX_OVERFLOW` (20) — size the database
  `max_connections` accordingly.
- Put a CDN in front of the edge for `/_next/static/*` (immutable, hashed) and TLS offload; keep
  `/api` uncached (`Cache-Control: no-store` is set by the API).
