# Admin console

A staff-only console at `/admin`, backed by `/api/v1/admin`. It reuses Notely's sessions,
database and design system. The only new infrastructure is three tables and a role column.

## Authorization

- **Role**: `users.role` is one of `user | viewer | support | admin`. It's stored as text, so
  adding a role needs no enum migration. Permissions come from `app/core/permissions.py`.
- **Every admin route** depends on `require(<permission>)` (`app/api/admin_deps.py`), which checks
  on the server, in this order:
  1. a valid session with any second factor completed;
  2. a staff role, read from the database on every request;
  3. a session younger than `ADMIN_SESSION_MAX_AGE_HOURS`;
  4. 2FA turned on, when `ADMIN_REQUIRE_2FA=true`;
  5. the route's permission.
- **Refusals**: signed-in non-staff callers get 403 `ADMIN_ONLY`, and the attempt is audited
  (throttled to one row per person every 10 minutes). The web gate (`app/admin/layout.tsx`)
  returns 404 so the area isn't advertised.
- **Guard rails** (`app/services/admin_users.py`):
  - nobody can act on their own account from the admin area;
  - support can only act on lower roles;
  - the last active admin can't be suspended or demoted;
  - demoting someone ends their sessions.
- **CSRF**: the existing Origin/Sec-Fetch-Site middleware covers admin writes.
- **Rate limits**: 240 reads/min and 30 writes/min per staff member. Responses are
  `Cache-Control: no-store`.
- **First admin**: granted only from the server with
  `python -m app.manage set-role <email> admin`. The change is audited with the actor `cli`.

## Data model (migration 0022)

| Table / column | Purpose |
| --- | --- |
| `users.role`, `suspended_at`, `suspension_reason` | RBAC and suspension. Suspension reuses `is_active`, which sign-in already enforces. |
| `users.last_active_at` | Refreshed with the sliding session (every 5 minutes at most). It survives session cleanup, unlike `user_sessions`. |
| `admin_audit_events` | Admin actions and refused attempts. Deployment-wide; actor and target are kept as an email snapshot, with foreign keys `SET NULL`. Never purged. |
| `platform_events` | Durable error, security and usage events that per-process Prometheus counters lose on restart. Purged after 90 days. |
| `platform_settings` | Runtime switches, validated against a fixed spec (`app/services/platform_settings.py`) and cached for 5 seconds per process. |

The migration also adds time-range indexes for the analytics: `created_at` on users, notes, tasks,
AI runs and tool calls, and `started_at` / `(status, started_at)` on automation executions.

## Where each metric comes from

| Metric | Source |
| --- | --- |
| Users: total, new, suspended, growth | `users` |
| Active users (day, week, 30 days) | `users.last_active_at` |
| Notes and tasks | `notes`, `tasks` (`completed_at` for completed tasks) |
| AI requests, failures, models, tokens | `ai_runs` (`status`, `model`, `provider`, `token_usage`) |
| AI latency | `completed_at - started_at` of completed runs that never paused for approval |
| Tool calls | `ai_tool_calls` |
| AI workflow drafts | `platform_events` `ai_automation_draft[_failed]`, recorded by `POST /automations/draft` |
| Automation runs, durations, retries | `automation_executions` (`attempts`, `run_mode`) |
| Automation failure causes | `automation_execution_steps.result.kind`: the provider error kind, `declined`, or a generic step error |
| Connector accounts and states | `user_connections.status` / `last_error_code` |
| Connector API failures | `audit_events` rows with `status = failed` for that provider |
| OAuth and connector auth failures | `platform_events` `oauth_failed` / `connector_auth_failed` |
| API errors (5xx) | `platform_events` `api_error`, recorded by the unhandled-exception handler |
| Background job failures | `platform_events` `job_failed`, recorded by the job instrumentation wrapper |
| Security events | `platform_events` with category `security`: sign-in, failed sign-in, blocked sign-in, password and 2FA changes, admin actions |

## Privacy

Reports carry metadata only: counts, statuses, timings and error codes.
- **Never exposed**: password hashes, TOTP material, OAuth tokens, API keys and session tokens.
- **Not shown**: note or AI message content, and automation step inputs and outputs. For inputs,
  only the field names appear.
- **IP addresses** are masked to /24.
- **Stored messages** are scrubbed of anything that looks like a credential, and audit metadata
  drops secret-named keys.

## Known limits

- **Cost**: shown only if runs record `cost_usd`. Nothing writes it today, so cost reads "not
  tracked". Any cost shown would be an estimate, never the provider's invoice.
- **Vendor status**: connector health is derived from Notely's own observations. There is no
  vendor status feed.
- **Active users over time**: history isn't stored. Only current day, week and 30-day counts are
  shown, from `last_active_at`.
- **Error and incident history**: 5xx and job-failure history starts when this feature is
  deployed. Earlier failures exist only in logs and metrics.
- **Queue depth and worker health**: not shown. They live in Redis and Prometheus, not the
  database.
