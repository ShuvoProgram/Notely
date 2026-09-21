# OAuth setup: "Continue with Google" and one-click connectors

Notely never asks a user for credentials, client ids or tokens. A user presses **Continue with
Google** (sign-in) or **Connect** (a tool), approves on the vendor's own screen, and lands back
in the app. What an operator configures once, per environment, is described here.

## How the redirect URI works (why `redirect_uri_mismatch` happens)

Google only accepts redirect URIs that are registered on the OAuth client, byte for byte.
Notely therefore uses **exactly one redirect URI per vendor**, for every flow that vendor serves:

| Vendor app | Redirect URI | Serves |
|---|---|---|
| `OAUTH_GOOGLE_*` | `{FRONTEND_ORIGIN}/api/v1/oauth/google/callback` | Continue with Google **and** the Gmail, Google Calendar, Google Drive connectors |
| `OAUTH_MICROSOFT_*` | `{FRONTEND_ORIGIN}/api/v1/oauth/microsoft/callback` | Continue with Microsoft **and** Teams, Outlook, OneDrive |
| any other vendor | `{FRONTEND_ORIGIN}/api/v1/oauth/{provider}/callback` | that connector (`slack`, `notion`, `dropbox`, …) |
| MCP-server vendors (Notion, Jira, ClickUp, Stripe, PayPal) | registered automatically by dynamic client registration | nothing to configure |

The callback tells sign-in and connector flows apart by the server-side state record, so the
URI can never drift between them. `FRONTEND_ORIGIN` is the only input: the web app proxies
`/api/*` to the API, so the URI is always on the origin the user is browsing.

`redirect_uri_mismatch` means the URI in the table above is not in the client's
**Authorized redirect URIs** for the environment you are running. Copy it exactly (scheme, host,
port, path, no trailing slash). Google says changes can take "5 minutes to a few hours".

## Google Cloud Console, step by step

Do this once per environment. Use **separate projects or at least separate OAuth clients** for
development and production; never put a `localhost` URI on the production client.

1. **APIs & Services → Library**: enable *Gmail API*, *Google Calendar API*, *Google Drive API*
   (only the ones you offer as connectors; sign-in needs none of them).
2. **APIs & Services → OAuth consent screen** (now "Google Auth Platform → Branding/Audience"):
   - User type **External**.
   - App name, support email, logo, **Authorized domain** = your production domain,
     privacy-policy and terms URLs (required for publishing).
   - **Scopes**: add `openid`, `email`, `profile` plus the connector scopes you offer
     (`.../auth/gmail.readonly`, `.../auth/gmail.send`, `.../auth/calendar.readonly`,
     `.../auth/calendar.events`, `.../auth/drive.readonly`, `.../auth/drive.file`).
   - **Publishing status → In production** (see the next section). While it is *Testing*, only
     the listed test users can sign in — that is the "add every user manually" trap.
3. **APIs & Services → Credentials → Create credentials → OAuth client ID → Web application**:
   - Authorized JavaScript origins: `{FRONTEND_ORIGIN}` (e.g. `https://notes.example.com`).
   - Authorized redirect URIs: `{FRONTEND_ORIGIN}/api/v1/oauth/google/callback` — one line.
   - Copy the Client ID and Client secret into the API environment:
     `OAUTH_GOOGLE_CLIENT_ID`, `OAUTH_GOOGLE_CLIENT_SECRET`.

Restart the API. **Continue with Google** appears on the login/sign-up pages and Gmail,
Google Calendar and Google Drive appear in the connectors marketplace automatically — a provider
is offered only when its app is configured.

### Publishing and verification (so users are never "test users")

- **Sign-in only (`openid email profile`)**: press *Publish app*. No verification is needed;
  any Google account can sign in immediately.
- **Sensitive scopes** (`calendar.*`, `drive.file`, `gmail.send`): publishing works right away,
  but until Google verifies the app users see the *"Google hasn't verified this app"*
  interstitial (they can continue via *Advanced*), and the app is capped at 100 users. Submit
  for **brand + scope verification** from the consent-screen page; it needs the privacy policy,
  a demo video and the authorized domain. Typically days.
- **Restricted scopes** (`gmail.readonly`, `drive.readonly`): verification is mandatory for
  general availability and includes a third-party security assessment (CASA). Until it passes,
  the same 100-user cap applies. If you want Gmail reading without the assessment, Google
  Workspace *internal* apps (User type **Internal**) skip verification for your own organisation.

None of this is code: Notely's requests are already shaped for a published app (PKCE,
`access_type=offline` + `prompt=consent` for refresh tokens, `include_granted_scopes`, minimal
per-connector scopes chosen by the user on the consent card).

### "Access blocked: Notely has not completed the Google verification process" (403 access_denied)

This is not produced by Notely; it is Google's **Testing** publishing status. Only accounts on
the consent screen's test-user list may authorize an app in Testing. Fix it on the console,
never in code:

1. Google Auth Platform → **Audience** (older UI: OAuth consent screen): User type *External*,
   then **Publish app** → *Confirm*. Status becomes **In production**.
2. Any Google account can now authorize sign-in immediately. For connectors, users will see the
   *"Google hasn't verified this app"* interstitial until verification passes (they can still
   continue via *Advanced → Go to Notely*), with the 100-user cap described above.
3. Google Auth Platform → **Verification Center** → *Prepare for verification*: confirm branding
   (privacy policy on the authorized domain, homepage describing the app), justify each
   sensitive/restricted scope with a screen recording of the flow, and submit. Restricted Gmail
   and Drive scopes additionally trigger the CASA security assessment.
4. Leave the test-user list empty in production. Use it only on the **development** client,
   whose consent screen may stay in Testing.

Notely records this outcome on the connection ("… app is still in testing mode …") and shows it
on the connector page, so users know to contact the operator instead of retrying.

## Microsoft (Entra ID) in brief

App registrations → New registration → *Accounts in any organizational directory and personal
Microsoft accounts* → Authentication → Web → Redirect URI
`{FRONTEND_ORIGIN}/api/v1/oauth/microsoft/callback` → Certificates & secrets → new secret →
API permissions → delegated Graph scopes you offer. Set `OAUTH_MICROSOFT_CLIENT_ID/SECRET`
(`OAUTH_MICROSOFT_TENANT=common` for multi-tenant).

## Environments

| | Development | Staging | Production |
|---|---|---|---|
| `ENVIRONMENT` | `development` | `production` | `production` |
| `FRONTEND_ORIGIN` | `http://localhost:3000` | `https://staging.notes.example.com` | `https://notes.example.com` |
| Redirect URI to register | `http://localhost:3000/api/v1/oauth/google/callback` | `https://staging…/api/v1/oauth/google/callback` | `https://notes.example.com/api/v1/oauth/google/callback` |
| Google OAuth client | dev client (Testing status is fine; you are the test user) | own client, published | own client, published + verified |
| Where the values live | `apps/api/.env` (git-ignored) | secret store → env | secret store → env |

Rules the API enforces in production (`ENVIRONMENT=production`): `https://` origins, secure
cookies, `SESSION_SECRET` and `ENCRYPTION_KEY` set, and a startup gate that refuses to boot
otherwise (`docs/deployment.md`).

## What happens on the user's side

1. **Continue with Google** → Google account chooser → back to `/app`, signed in. First time,
   the account is created from the Google profile (verified email, name, avatar); afterwards the
   same Google subject always resolves to that account. Cancel or an expired link comes back
   to the login page with a plain-language reason.
2. **Connections → Gmail → Connect** → consent card (what Notely can do, what Google receives)
   → **Continue with Notely** → Google's consent screen for *just* the scopes picked → back to
   the Gmail page showing *Connected as you@gmail.com*. Tokens are stored encrypted
   (`ENCRYPTION_KEY`, Fernet) against the user's connection row; refresh is automatic.
3. **Disconnect** revokes and deletes the tokens; **Reconnect** runs the same one-click flow.

## Token lifecycle (why a connection can say "Needs attention")

Access tokens are short-lived (Google: 1 hour). Notely refreshes them server-side, on demand,
right before any call that needs one (search, assistant tools, calendar sync, health checks)
and on a 5-minute cron in the worker; concurrent callers share one refresh per connection.
A vendor outage during refresh is reported as **Connection unavailable → Try again** and the
tokens are kept. Only a rejected grant (`invalid_grant`) becomes **Needs attention → Reconnect**.

Google-specific: while the OAuth consent screen is in **Testing** status, Google expires refresh
tokens after 7 days, so users will genuinely have to reconnect weekly until the app is published
(see "Publishing status" above).

## Google Sheets, Google Docs and Google Meet

They share the Google OAuth client with Gmail/Calendar/Drive (same `OAUTH_GOOGLE_*`, same
redirect URI `{FRONTEND_ORIGIN}/api/v1/oauth/google/callback`). Two extra steps in the Google
Cloud project:

1. **Enable the APIs**: Google Sheets API, Google Docs API, Google Meet REST API, and Google
   Drive API (used only to list a user's spreadsheets/documents by name).
2. **Add the scopes to the consent screen** so they appear on the verification form:

   | Connector | Scopes | Sensitivity |
   |---|---|---|
   | Sheets | `drive.metadata.readonly`, `spreadsheets.readonly`, `spreadsheets` (optional) | sensitive |
   | Docs | `drive.metadata.readonly`, `documents.readonly`, `documents` (optional) | sensitive |
   | Meet | `userinfo.email`, `meetings.space.readonly`, `meetings.space.created` (optional) | non-sensitive / sensitive |

   None of these is a *restricted* scope, so verification does not require a CASA security
   assessment (Drive's `drive.readonly` — used by the Drive connector — does).

Google Meet has no search and no "schedule a Meet" endpoint of its own: creating a meeting
link is `spaces.create`; putting one on a calendar is the Google Calendar connector's job.

## Zoom

Create a **General app** (user-managed) at https://marketplace.zoom.us/develop/create, set
the redirect URL to `{FRONTEND_ORIGIN}/api/v1/oauth/zoom/callback`, and add these granular
scopes: `user:read:user`, `meeting:read:list_meetings`, `meeting:read:meeting`, and (for the
write tools) `meeting:write:meeting`, `meeting:update:meeting`, `meeting:delete:meeting`.
Copy the client id/secret to `OAUTH_ZOOM_CLIENT_ID` / `OAUTH_ZOOM_CLIENT_SECRET`.

Zoom does not take a scope parameter on the authorize URL — the app's configured scopes are
what the user grants — so Notely reads the granted list from the token response and only
offers the assistant tools the token actually covers. Until the app passes Zoom's review and
is published, only users of the developer's own Zoom account can authorize it.

## Microsoft Teams

`ChannelMessage.Read.All` and `ChannelMessage.Send` are delegated permissions that many
tenants require an administrator to consent to. When Microsoft answers with an admin-consent
error, the connection shows **Needs attention → Reconnect** with that reason; the tenant admin
grants consent once in Entra ID and users reconnect.
