# Deploying Notely on Coolify (Hostinger VPS)

Notely ships a Coolify-ready compose file, `docker-compose.coolify.yml`: Postgres (pgvector),
Redis, LiteLLM, the API, the worker and the web app, with Coolify's Traefik doing TLS and
routing. Nothing but `web` is reachable from the internet; `/api` and `/health` are proxied to
the API on the private network by Next.js (same origin, first-party cookie, SSE works).

## 0. What you need

- A Hostinger **KVM VPS** with the Coolify template (or Ubuntu 22.04/24.04 with Coolify
  installed). 8 GB RAM is comfortable; 4 GB works (LiteLLM + Postgres + Node + Python).
- A domain / subdomain pointed at the VPS (`A` record → the VPS IP), e.g. `notes.yourdomain.com`.
- The GitHub repo (`ShuvoProgram/Notely`) and, for AI features, at least one model provider key
  (OpenAI / Anthropic / Google) — or users can bring their own key in Settings → AI.

## 1. Prepare the VPS

Hostinger → VPS → **Operating system** → choose **Ubuntu 24.04 with Coolify** (or install with
`curl -fsSL https://cdn.coollabs.io/coolify/install.sh | bash` on a plain Ubuntu).

Open Coolify at `http://<VPS-IP>:8000`, create the admin account, and in **Settings**:

- set **Instance domain** (e.g. `coolify.yourdomain.com`) so the dashboard gets TLS;
- keep the default proxy (**Traefik**); ports 80/443 must be open in Hostinger's firewall.

## 2. Connect GitHub

Coolify → **Sources** → **+ Add** → **GitHub App** → follow the wizard (it creates a GitHub App
scoped to your account; pick the `Notely` repository). This gives Coolify pull access and a
webhook for auto-deploys on push.

## 3. Create the project and resource

1. **Projects** → **+ Add** → `Notely` → environment `production`.
2. **+ New Resource** → **Docker Compose** → source: your GitHub App → repository
   `ShuvoProgram/Notely`, branch `main`.
3. **Docker Compose location**: `/docker-compose.coolify.yml`. Click **Continue**; Coolify
   parses the file and lists the services.
4. On the `web` service set the **domain**: `https://notes.yourdomain.com` (Coolify fills
   `SERVICE_FQDN_WEB` from it; the compose file already maps port 3000). Leave every other
   service without a domain.

## 4. Environment variables

Resource → **Environment Variables**. Coolify already generated `SERVICE_PASSWORD_POSTGRES`
and `SERVICE_FQDN_WEB`; add these (**Build Variable** unticked — they are runtime values):

| Variable | Value |
|---|---|
| `PUBLIC_URL` | `https://notes.yourdomain.com` — the exact domain you set on the `web` service. **Required**: the API refuses to start without an https origin (this is the usual cause of "container api is unhealthy"). |
| `SESSION_SECRET` | `openssl rand -base64 48` |
| `ENCRYPTION_KEY` | Fernet key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `LITELLM_MASTER_KEY` | `sk-` + `openssl rand -hex 24` |
| `METRICS_TOKEN` | `openssl rand -hex 24` |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` | at least one, matching `infra/litellm/config.yaml` |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM` | optional — note invitations by email (`docs/email-setup.md`) |
| `OAUTH_GOOGLE_CLIENT_ID`, `OAUTH_GOOGLE_CLIENT_SECRET` | optional — Google sign-in + Gmail/Calendar/Drive/Sheets/Docs/Meet (`docs/oauth-setup.md`) |
| other `OAUTH_*` pairs | only for vendors you enable |

Rotating `SESSION_SECRET` signs everyone out; rotating `ENCRYPTION_KEY` invalidates stored
provider tokens and BYO API keys (users reconnect).

## 5. Deploy

Click **Deploy**. The first build takes 5–10 minutes (two images: API and web). Order:
`postgres` → `migrate` (runs `alembic upgrade head`, exits 0) → `api`, `worker` → `web`.

Verify:

```bash
curl -fsS https://notes.yourdomain.com/health          # {"status":"ok"}
curl -fsS https://notes.yourdomain.com/api/v1/auth/providers
```

Then open `https://notes.yourdomain.com/signup`, create an account, write a note, and ask the
assistant something. `Settings → AI` shows the workspace gateway provider.

The API refuses to start in production with a weak `SESSION_SECRET`, missing `ENCRYPTION_KEY`
or `METRICS_TOKEN`, or non-https URLs — check the `api` container logs in Coolify if `web` stays
unhealthy.

## 6. OAuth redirect URIs (Google, Microsoft, Slack, Zoom, …)

One URI per vendor family, all on the web domain:

```
https://notes.yourdomain.com/api/v1/oauth/google/callback
https://notes.yourdomain.com/api/v1/oauth/microsoft/callback
https://notes.yourdomain.com/api/v1/oauth/slack/callback
https://notes.yourdomain.com/api/v1/oauth/zoom/callback
https://notes.yourdomain.com/api/v1/oauth/<provider_id>/callback   # notion, todoist, …
```

Publishing status, verification and per-vendor notes: `docs/oauth-setup.md`.

## 7. Day-2 operations

- **Auto-deploy**: Resource → **Webhooks** is wired by the GitHub App; every push to `main`
  rebuilds and redeploys (migrations run first, the previous containers stay up until the new
  ones are healthy).
- **Backups**: Coolify → the `postgres` service → **Backups** → schedule to local storage or
  S3-compatible storage (Hostinger's object storage works). Redis holds only queues/rate-limit
  state; no backup needed.
- **Logs**: Resource → service → **Logs**. API and worker log JSON; `/metrics` (bearer
  `METRICS_TOKEN`) exposes Prometheus metrics.
- **Scaling**: raise the VPS plan; Postgres and the API are the memory users. LiteLLM can be
  pointed at an external gateway later by changing `LITELLM_API_BASE` and removing the service.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `web` unhealthy, `api` restarting | Missing/invalid secret — see `api` logs: `SESSION_SECRET is using the development default`, `ENCRYPTION_KEY is not a valid Fernet key`, … |
| Google sign-in `redirect_uri_mismatch` | Add the exact URI from §6 to the Google Cloud client. |
| Connector says *Connection needs attention* right after connecting | Google consent screen still in **Testing** (7-day refresh tokens) or a Microsoft tenant needing admin consent — `docs/oauth-setup.md`. |
| Invitations say *Unable to send invitation* | `SMTP_*` not set; the message shows the exact variables. |
| Assistant answers "not configured" | No model provider key for LiteLLM; set one in §4 or use *Your own model* in Settings → AI. |
