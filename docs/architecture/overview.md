# Architecture overview

```
Browser ──► Next.js (apps/web) ──/api/* proxy──► FastAPI (apps/api) ──► PostgreSQL (+pgvector)
                                                        │                └► Redis (rate limits, OAuth state, jobs)
                                                        └► ARQ worker (apps/api/app/workers)
                                                        └► LiteLLM gateway ──► model providers   (Phase 3)
```

FastAPI owns all business logic. Next.js is the UI/BFF layer: it renders, gates protected routes
server-side, and proxies API calls so the session cookie stays first-party. No business logic
lives in Next.js route handlers.

## Request conventions

- Success: `{ "data": ..., "meta": {} }` — `app/core/responses.py`
- Error: `{ "error": { "code", "message", "details" } }` — `app/core/exceptions.py`.
  Raise `APIError` subclasses in services; handlers render them. Unhandled exceptions become
  `INTERNAL_ERROR` with no Python detail leaked.
- Validation errors carry `details.fields: { field: [messages] }`; the web client maps them onto
  form fields (`ApiError.fieldErrors`).
- Every response has `X-Request-ID`; access logs are structured JSON with secrets redacted.

## Authentication & sessions

- Email/password with argon2id (`pwdlib`). Login timing is equalised for unknown emails.
- Session = 256-bit random token in an `HttpOnly; SameSite=Lax` cookie. The database stores an
  HMAC(SESSION_SECRET) of the token, so a database leak cannot forge sessions. Sessions slide
  (7 days) and are refreshed at most every 5 minutes.
- Password change revokes all other sessions. Users can list and revoke sessions.
- CSRF: `CSRFOriginMiddleware` rejects unsafe requests whose `Origin`/`Sec-Fetch-Site` indicate a
  foreign site. See ADR-0002.
- Federated sign-in (Google, Microsoft) uses the shared OAuth client (`app/core/oauth.py`,
  PKCE + server-side single-use state + id_token verification via JWKS). Providers are enabled
  only when configured; `/auth/providers` tells the UI what to show. Account linking by email
  requires the provider to assert `email_verified`.

## Multi-tenancy

Every user belongs to a tenant (personal tenant created at signup). User-owned tables carry
`tenant_id` and `user_id`; repositories take the owning ids explicitly and filter on them.
Identity is always derived from the session, never from client input.

## Rate limiting

`rate_limit(scope, per_minute)` dependency, fixed window, keyed by user id (when authenticated)
or client IP. Counters live in Redis via the `KV` abstraction, which degrades to in-process memory
(with a warning) if Redis is unreachable.

## Background jobs

ARQ worker with cron jobs. Phase 1 ships `cleanup_expired_sessions`. Never run large sync work
inside an HTTP request.

## Health

- `GET /health`, `/health/live` — process is up.
- `GET /health/ready` — PostgreSQL, Redis and configuration; 503 when degraded. Never exposes
  configuration values.

## Frontend structure

- `app/` routes: `/`, `/login`, `/signup`, `/app`, `/app/settings/{profile,security}`.
  `app/app/layout.tsx` gates on the server and renders `AppShell`.
- `features/<area>/` — API bindings, hooks, schemas and components per feature.
- `lib/api/` — typed client (`client.ts`), server helpers that forward cookies (`server.ts`),
  and DTO types mirrored from the API (`types.ts`).
- `lib/navigation.ts` — single source for nav items; the shell never links to routes that don't
  exist yet.
- Design tokens in `app/globals.css` (dark-first, green AI accent). shadcn/ui components in
  `components/ui`.

## Notes (Phase 2)

- Tables: `folders` (self-referential, cycle-checked in the service), `tags`, `notes`,
  `note_tags`. `notes.content_json` is canonical TipTap JSON; `plain_text` is derived server-side
  (`services/rich_text.py`) for search/AI. `notes.search_vector` is a generated `tsvector`
  (title weight A, body weight B) with a GIN index; the ORM never writes it.
- Lifecycle: `archived_at` and `deleted_at` (trash) are independent; purge requires trash first;
  the worker purges trash after 30 days.
- Autosave: `PATCH /notes/{id}` with `expected_version` → `409 NOTE_VERSION_CONFLICT` carrying
  `current_version`. Metadata edits (favorite, folder, tags, archive) don't bump the version.
  The web hook (`features/notes/use-autosave.ts`) debounces 900 ms, mirrors every change to
  `localStorage` first, clears the mirror on confirmed save, and restores a draft on load when it
  was based on the current server version. Conflicts show "Load latest / Keep mine".
- Lists use keyset pagination (`meta.next_cursor` over `(updated_at, id)`) with `view`,
  `folder_id`, `tag_id`, `q` filters. `/search` is the unified search endpoint; hits always carry
  a `source` so provider results can join later without UI changes.

## What Phase 3+ adds

AI (LiteLLM client, LangGraph runs, approval system), integration framework (provider contract, connection storage using
`app/core/crypto.py`, capability registry, MCP client, tool policy engine), providers, cross-app
AI, hardening. Each phase reuses the foundations above rather than adding parallel mechanisms.
