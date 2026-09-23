# Automations

Notely automations let anyone describe useful work once and have it happen on a schedule,
across Notely and every connected app. This document records the audit of the first
implementation and the architecture that replaced it.

## 1. Audit of the first implementation (September 2026)

The first version (migrations 0015–0017) worked for the one flow it was tuned for
(Gmail → AI → note) and broke in predictable ways for anything else. Most of the reported
symptoms trace back to five architectural gaps, not isolated bugs.

### Root cause A — no capability model

Actions were four unrelated things: native kinds hard-coded in the executor
(`create_task`, `create_note`, `update_note`, `notify`, `ai`), provider tools addressed by
`provider` + `tool`, a hand-written list in the planner prompt, and a separate hard-coded list
in the builder. Nothing described an action's **outputs**. Consequences:

- *Missing data mapping.* The builder's "Insert data" only knew Gmail `search_mail` fields and
  AI `text`; every other step offered "Full result".
- *Incomplete AI workflows.* The planner could not know what fields a step produces, so it
  guessed paths; an 800-line alias normaliser tried to repair its guesses.
- *Gmail-specific behaviour.* Prompts, examples, templates and the UI all special-cased Gmail.

### Root cause B — provider output was passed through unmodified

Connector outputs wrap user-authored text in `<untrusted_content>` markers (correct for the
chat assistant). The engine stored and forwarded those strings verbatim, so mapping an email
subject into a task title saved the markup, and AI prompts double-wrapped content.

### Root cause C — run state mixed into the automation's status

`Automation.status` held both "is it switched on" and "how did the last run go"
(`running`, `failed`, `needs_attention`). The scheduler only picked `status == active`, and
failed or approval-paused runs did not advance `next_run_at`. **One failed run silently stopped
the schedule forever.** A worker crash left `status = running`, after which *Run now* returned
"already running" permanently.

### Root cause D — synchronous execution inside the HTTP request

*Run now* and *Test* executed the whole workflow (Gmail + model calls) inside the request. The
web app proxies `/api` through Next.js, whose proxy times out after 30 seconds, so longer runs
failed in the browser while continuing on the server.

### Root cause E — a linear list pretending to branch

Branches were emulated by gating each later step on `steps.<decision>.output.matched`.
There was no "stop here", no paths, no "does not contain", "is empty", or item counts
("more than 5 emails"), and two condition dialects (`operator` vs. `exists/equals/min_items`).

### Other findings

| Area | Status | Finding |
|---|---|---|
| Data model, ownership checks | Correct | Every query is scoped to the user; approvals are checked through the owning automation. |
| Scheduling maths | Correct | Time zones, DST and month ends are handled; kept as is. |
| Token refresh / connector auth | Correct | Reused `ConnectionService.refresh_if_needed`; permissions honoured per tool. |
| AI model choice | Broken | `resolve()` returning `None` means "use the workspace gateway", but the engine and planner read it as "no model", so AI steps and drafting failed for everyone without a personal key. |
| Approvals | Partial | Worked, but only for provider writes; no notification that a run was waiting. |
| Test mode | Broken | Simulated writes produced no output, so any later step that used them failed. |
| Execution history | Partial | Full outputs lived in one ever-growing `context` blob; step rows kept a whitelist summary. |
| Retries | Weak | Manual retry only; transient rate limits / 5xx failed the run immediately. |
| Duplicate prevention | Partial | Unique occurrence per automation was good; row locks were released after the first commit. |
| Failure recovery | Missing | No stale-run recovery, no pause after repeated failures, no failure notification. |
| Templates | Weak | "Templates" were paused automations flagged inside `action_config`. |
| Builder UX | Weak | Step IDs and a raw JSON editor exposed by default; native `<select>`s; no paths. |
| AI editing | Missing | The planner could only create new drafts, not change an existing one. |
| Triggers | Partial | Daily/weekly/monthly/once only; no "every N minutes" and no "only when I run it". |
| Rate limits | Missing | Draft generation (model calls) was unlimited. |

## 2. Architecture

```text
Connector (manifest + tools)          Notely built-ins          AI actions
          │                                   │                     │
          └──────────────► Capability catalog ◄─────────────────────┘
                                   │  (per user: connected, permitted, input + output fields)
             ┌─────────────────────┼──────────────────────┐
             ▼                     ▼                      ▼
        AI planner            Visual builder         Workflow engine
   (validated against)    (renders fields from)   (executes actions from)
```

### Capability catalog — `app/automation/catalog.py`

One list of **actions** per user. Each action has an id (`gmail.search_mail`,
`notely.create_task`, `ai.summarize`), the app it belongs to, a plain-language label, a
safety level, **input fields** (derived from the tool's argument schema) and **output fields**
(declared by the connector, and otherwise discovered from a test run's real data). Connector
tools are only listed when the connection is usable and the scope that tool needs was granted.
Adding a connector adds its actions everywhere — planner, builder and engine — with no
automation code changes.

Safety levels:

| Level | Examples | Behaviour |
|---|---|---|
| `safe` | Reading anything, creating a Notely task or note | Runs automatically |
| `ask` | Sending email, posting to Slack, writing to Sheets | Asks first by default; the user may choose *Do this automatically* |
| `always_ask` | Deleting or cancelling anything | Always asks; cannot be made automatic |

AI-generated workflows always start with `ask` for anything that is not `safe`.

### Workflow model (version 2) — `app/automation/model.py`

```text
steps: [ action | filter | branch ]
action  { id, action: "gmail.search_mail", inputs: {…}, approval, on_error, retries }
filter  { id, condition }                 — "Only continue if…"
branch  { id, condition, then: [...], otherwise: [...] }   — "Split into paths"
condition { match: all|any, rules: [{ left, operator, right }] }
```

Inputs reference earlier data with `{{steps.<id>.output.<field>}}`, `{{trigger.fired_at}}`
and `{{trigger.previous_run_at}}`. Paths support list indexes and `.count`.
Version 1 definitions are upgraded on read.

### Engine — `app/automation/engine.py`

- Every step persists its resolved input, **full output** (size-capped) and a one-line
  human summary ("10 emails found", "Updated *Daily Email Summary*").
- Test runs execute reads and AI for real and simulate writes; simulated outputs echo the
  planned inputs so later steps still resolve.
- Transient connector failures retry automatically with backoff; a failed step can be retried
  from history, reusing the outputs of the steps that already succeeded.
- Runs happen in the background worker; the API only creates the run and enqueues it.

### Scheduler — `app/automation/scheduler.py`

A due automation is **claimed by advancing `next_run_at` first**, then executed, so the
schedule always moves on, and two workers can never run the same occurrence (the unique
occurrence constraint is a second guard). Runs stuck in `running` for 30 minutes are marked
interrupted. Five consecutive failed scheduled runs pause the automation and notify the user.

### AI planner — `app/automation/planner.py`

The model receives the catalog (connected actions, *and* the actions of offered-but-unconnected
apps as "locked"), the user's notes and the workflow format, and must answer with one JSON
object. The answer is validated with the same workflow model and catalog checks as a hand-built
workflow; if it is invalid, the model gets the list of problems once to fix them. Anything still
impossible is reported under `unsupported`, apps that need connecting under `missing_apps`, and
nothing is invented. Any `approval` the model sets is discarded — Notely decides what runs
without asking. With `current`, the planner edits that automation (keeping step ids) and lists
its `changes`; the builder shows them before applying.

AI steps and drafting use the same model as the assistant: the user's own key when set,
otherwise the workspace gateway.

## 3. Builder (web)

`/app/automations` answers *what can I automate, what have I automated, is it working, what
happened last time*. `/app/automations/new` and `/app/automations/<id>` are the builder:

- **When this happens** — the schedule in plain words.
- **Then do this** — step cards: *Find / Think / Do / Check / Decide*. Each card is a sentence
  when collapsed and the full editor when opened. "+" between steps adds an action, an *Only
  continue if…* check, or *Yes / No paths*.
- **Insert data** — earlier steps' outputs by name ("Gmail · First email · Subject"); in text
  fields they appear as chips, never as `{{…}}`.
- **Test** (safe) and **Run now** (real) both run in the background; the side panel follows the
  run step by step, with *Retry step*, *Reconnect*/*Set up AI* links and *View details*.
- **Ask AI to change this** previews AI edits before applying them.

## 4. Adding a connector's actions

Nothing in `app/automation` changes. In the connector's `build_tools()`:

1. Declare each tool's argument model (it becomes the step's fields — give fields `description`s
   and sensible defaults; long text fields named `body`/`content`/`message` get a text area).
2. Declare what read tools return with `outputs=` (see `app/integrations/base/outputs.py`), so
   "Insert data" can offer named fields before anyone has tested the step. Without it, fields are
   discovered from a test run.
3. Map the tool's `Capability` correctly: it sets the safety level (`send`/`comment` ask first,
   `delete` always asks).

## 5. Running it

The worker executes every run and the schedule (`run_due_automations` every minute). Locally:

```bash
cd apps/api && uv run arq app.workers.main.WorkerSettings
```

Without Redis (tests), runs execute inline. Tests: `app/tests/test_automations.py` (engine,
mapping, conditions, scheduler, planner, API, isolation) and `apps/web/tests/e2e/automations.spec.ts`.
