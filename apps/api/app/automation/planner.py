"""Natural language → a reviewable workflow, using only what the catalog says is possible.

The model sees the user's actions (connected and locked), their inputs and outputs, the
user's notes and the workflow format. Its answer is validated with the same model and
catalog checks as a hand-built workflow; if it's invalid the model gets one chance to fix
the listed problems. Anything still impossible is reported, never faked.

With `current` set, the model edits that workflow (keeping step ids) and lists its changes.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from app.automation.actions import ActionContext, ActionDefinition, ActionError
from app.automation.catalog import Catalog, build_catalog
from app.automation.model import ActionStep, Workflow, iter_steps
from app.automation.native import chat_model, parse_json_reply
from app.automation.validation import normalise, validate
from app.core.exceptions import ValidationFailed
from app.core.logging import get_logger
from app.schemas.automations import DraftOut, DraftRequest, IssueOut, MissingApp, Unsupported
from app.schemas.notes import NoteListQuery
from app.services.note_service import NoteService

log = get_logger(__name__)

_DAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
_KINDS = {"once", "daily", "weekly", "monthly", "custom", "interval", "manual"}

FORMAT = """
Reply with ONE JSON object and nothing else:
{
  "name": "short name",
  "description": "one sentence",
  "schedule": {"kind": "daily|weekly|monthly|once|interval|custom|manual",
               "time": "HH:MM", "days": [0-6, Monday=0], "day": 1-31,
               "every_minutes": 15-1440, "interval_days": N, "starts_at": "ISO datetime"},
  "steps": [ ...steps... ],
  "missing_apps": ["app ids from NOT CONNECTED that the request needs"],
  "unsupported": [{"request": "what the user asked", "reason": "why Notely can't",
                   "suggestion": "closest thing it can do"}],
  "questions": ["only if something essential is missing"],
  "changes": ["when editing: each change in plain words"]
}
Step shapes:
- {"kind": "action", "id": "snake_case_id", "action": "<action id>", "inputs": {...}}
- {"kind": "filter", "id": "...", "name": "Only continue if …", "condition": COND}
- {"kind": "branch", "id": "...", "name": "…?", "condition": COND,
   "then": [steps], "otherwise": [steps]}
COND = {"match": "all|any",
        "rules": [{"left": "{{steps.x.output.field}}", "operator": OP, "right": value}]}
OP = equals | not_equals | contains | not_contains | greater_than | less_than | exists |
     not_exists | is_empty | is_not_empty | is_true | is_false | before | after
Data from earlier steps: "{{steps.<id>.output.<field>}}"; a list's size is "<list>.count";
the first item is "<list>.0.<field>". Also "{{trigger.fired_at}}", "{{trigger.previous_run_at}}".
"""

RULES = """
Rules:
1. Use ONLY action ids listed under ACTIONS, NOT CONNECTED or OTHER ACTIONS. Never invent
   actions, apps, fields, recipients or message text the user didn't give.
2. If the request needs an app under NOT CONNECTED, still build the workflow with its actions and
   list the app id in missing_apps.
3. If something is impossible with these actions, leave it out and explain it in unsupported.
4. Pass data between steps with references. AI steps must get the data they work on in "data".
   Use the whole output ("{{steps.x.output}}") when an action's outputs are not listed.
5. "Create tasks for action items" = ai.extract_action_items then notely.create_tasks with
   items "{{steps.<that id>.output.action_items}}".
6. For "only when there are results" add a filter (e.g. "<list>.count" greater_than 0).
   For "if … otherwise …" use a branch. For judgement calls ("is it urgent?") use ai.decide and
   check its "answer" with is_true.
7. For a note input use the id of one of the user's NOTES. If the user named a note that isn't
   listed, use notely.create_note if they asked to create it; otherwise leave "note" empty and ask
   which note to use.
8. "Every weekday" = weekly with days [0,1,2,3,4]. Times are in the user's time zone. No trigger
   other than a schedule or manual exists; for "when X happens" use an interval schedule that
   checks for new items and say so in description.
9. Keep it minimal: no steps the user didn't ask for. Never set "approval" — Notely decides.
10. A scheduled automation runs again and again. Never create a new spreadsheet, document, page
   or note on every run just to write into it: write into one existing place (a search/find
   step for the name the user gave, or leave the id empty and ask which one). Create something
   new only when the user asks for a new one each time.
11. To avoid repeats ("only if it's new"), order the steps: generate the content, read the
   existing entries from the same place the automation writes to, check, then write.
"""


def _compact(action: ActionDefinition, catalog: Catalog) -> dict[str, Any]:
    def fields(outs: Any) -> list[Any]:
        return [{o.key: fields(o.fields)} if o.fields else f"{o.key}:{o.type}" for o in outs]

    return {
        "id": action.id,
        "app": catalog.app_info(action.app)["name"],
        "does": action.description or action.label,
        "inputs": {
            f.key: f.type
            + ("*" if f.required else "")
            + (f"({'|'.join(v for v, _ in f.options)})" if f.options else "")
            for f in action.inputs
        },
        "outputs": fields(action.outputs) if action.outputs else "not listed",
    }


def _schedule(raw: Any) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(raw, dict):
        return {}, []
    kind = str(raw.get("kind") or "").lower()
    if kind in ("weekday", "weekdays"):
        kind, raw = "weekly", {**raw, "days": [0, 1, 2, 3, 4]}
    if kind not in _KINDS:
        return {}, ["How often should this run?"]
    config: dict[str, Any] = {}
    time = str(raw.get("time") or "").strip()
    if kind not in ("interval", "manual", "once"):
        matched = re.fullmatch(r"(\d{1,2}):(\d{2})", time)
        if not matched or int(matched.group(1)) > 23 or int(matched.group(2)) > 59:
            return {"schedule_kind": kind}, ["What time should it run?"]
        config["time"] = f"{int(matched.group(1)):02d}:{matched.group(2)}"
    if kind == "weekly":
        days = []
        for day in raw.get("days") or []:
            value = _DAYS.get(str(day).lower()[:3], day)
            if isinstance(value, int) and value in range(7):
                days.append(value)
        if not days:
            return {"schedule_kind": kind}, ["Which days of the week?"]
        config["days"] = sorted(set(days))
    if kind == "monthly":
        config["day"] = max(1, min(31, int(raw.get("day") or 1)))
    if kind == "interval":
        config["every_minutes"] = max(15, min(1440, int(raw.get("every_minutes") or 60)))
    if kind == "custom":
        config["interval_days"] = max(1, int(raw.get("interval_days") or 1))
    out: dict[str, Any] = {"schedule_kind": kind, "schedule_config": config}
    if kind == "once":
        try:
            out["starts_at"] = datetime.fromisoformat(str(raw.get("starts_at")))
        except (TypeError, ValueError):
            return {"schedule_kind": kind}, ["When should it run?"]
    return out, []


def _strip_approval(steps: Any) -> Any:
    """The model must not decide what runs without asking; Notely does."""
    if isinstance(steps, list):
        for step in steps:
            if isinstance(step, dict):
                step.pop("approval", None)
                _strip_approval(step.get("then"))
                _strip_approval(step.get("otherwise"))
    return steps


# Everyday words that point at an app ("my spreadsheet" → Google Sheets). Used only to decide
# which apps' actions the model sees in full; every app stays listed by name.
_APP_WORDS: dict[str, tuple[str, ...]] = {
    "gmail": ("gmail", "email", "emails", "mail", "inbox"),
    "outlook": ("outlook", "email", "emails", "mail", "inbox"),
    "google_sheets": ("sheet", "sheets", "spreadsheet", "spreadsheets", "row", "rows"),
    "google_docs": ("doc", "docs", "document", "documents"),
    "google_calendar": ("calendar", "meeting", "meetings", "event", "events", "agenda"),
    "google_drive": ("drive", "file", "files"),
    "google_meet": ("meet", "meeting", "meetings"),
    "slack": ("slack", "channel"),
    "microsoft_teams": ("teams",),
    "zoom": ("zoom", "meeting", "meetings"),
    "notion": ("notion",),
    "jira": ("jira", "issue", "issues", "ticket", "tickets"),
}


def relevant_apps(prompt: str, catalog: Catalog, current: list[str] | None = None) -> set[str]:
    """Apps the request is about: named, hinted at by everyday words, or already in use."""
    words = set(re.findall(r"[a-z0-9]+", prompt.lower()))
    wanted = {"notely", "ai", *(current or [])}
    for app in catalog.apps:
        names = set(re.findall(r"[a-z0-9]+", str(app["name"]).lower())) - {"google", "microsoft"}
        hints = set(_APP_WORDS.get(app["id"], ())) | (
            {app["id"]} if "_" not in app["id"] else set()
        )
        if (names and names <= words) or hints & words:
            wanted.add(app["id"])
    return wanted


class AutomationPlanner:
    def __init__(self, ctx: ActionContext) -> None:
        self.ctx = ctx

    async def _system(self, catalog: Catalog, timezone: str, focus: set[str] | None = None) -> str:
        """The planner prompt. Apps in `focus` get full action details; the rest are listed by
        action id only, which keeps the prompt small (and the model fast) for users with many
        connected tools."""
        notes, _ = await NoteService(self.ctx.db).list_notes(
            self.ctx.user, NoteListQuery(view="active", limit=60)
        )
        now = datetime.now(UTC).astimezone(ZoneInfo(timezone))

        def detailed(actions: Any) -> list[dict[str, Any]]:
            return [_compact(a, catalog) for a in actions if focus is None or a.app in focus]

        others: dict[str, list[str]] = {}
        for action in [*catalog.actions.values(), *catalog.locked.values()]:
            if focus is not None and action.app not in focus:
                others.setdefault(catalog.app_info(action.app)["name"], []).append(action.id)
        available = detailed(catalog.actions.values())
        locked = detailed(catalog.locked.values())
        not_connected = [
            {"id": a["id"], "name": a["name"]}
            for a in catalog.apps
            if a["status"] in ("not_connected", "needs_attention")
        ]
        return "\n".join(
            [
                "You design automations for Notely, a notes and tasks app, for people who are not",
                "technical. Turn the request into a workflow Notely can really run.",
                RULES,
                FORMAT,
                f"Now: {now:%A %Y-%m-%d %H:%M} ({timezone}).",
                "ACTIONS: " + json.dumps(available, ensure_ascii=False),
                "NOT CONNECTED apps: " + json.dumps(not_connected, ensure_ascii=False),
                "NOT CONNECTED actions: " + json.dumps(locked, ensure_ascii=False),
                "OTHER ACTIONS (ids only; use one only if the request clearly needs it): "
                + json.dumps(others, ensure_ascii=False),
                "NOTES: "
                + json.dumps(
                    [{"id": str(n.id), "title": n.title} for n in notes], ensure_ascii=False
                ),
            ]
        )

    async def _ask(self, messages: list[Any]) -> tuple[dict[str, Any], Any]:
        from app.ai.byo import classify_error

        try:
            model = await chat_model(self.ctx)
            reply = await model.ainvoke(messages)
        except ActionError as exc:
            raise ValidationFailed(
                exc.message, code="AI_MODEL_REQUIRED", details={"settings_path": "/app/settings/ai"}
            ) from exc
        except Exception as exc:  # noqa: BLE001 — providers raise heterogeneous errors
            raise ValidationFailed(
                f"The AI couldn't draft this: {classify_error(exc)}",
                code="AI_DRAFT_FAILED",
                details={"settings_path": "/app/settings/ai"},
            ) from exc
        parsed = parse_json_reply(getattr(reply, "content", reply))
        if parsed is None:
            raise ValidationFailed(
                "The AI's answer couldn't be read. Try again, or describe it a little differently.",
                code="AI_DRAFT_INVALID",
            )
        return parsed, reply

    def _problems(
        self, parsed: dict[str, Any], catalog: Catalog
    ) -> tuple[Workflow | None, list[str]]:
        steps = _strip_approval(parsed.get("steps"))
        if not isinstance(steps, list) or not steps:
            return None, ["There were no steps."]
        try:
            workflow = Workflow.model_validate({"version": 2, "steps": steps})
        except ValidationError as exc:
            return None, [
                ".".join(str(p) for p in e["loc"])
                + ": "
                + str(e["msg"]).removeprefix("Value error, ")
                for e in exc.errors()[:6]
            ]
        unknown = [
            s.action
            for s in iter_steps(workflow.steps)
            if isinstance(s, ActionStep)
            and s.action not in catalog.actions
            and s.action not in catalog.locked
        ]
        if unknown:
            return workflow, [
                f"Action '{a}' does not exist; use only listed action ids." for a in unknown
            ]
        return workflow, []

    async def draft(self, request: DraftRequest) -> DraftOut:
        catalog = await build_catalog(self.ctx)
        prefs = self.ctx.user.preferences if isinstance(self.ctx.user.preferences, dict) else {}
        timezone = (
            request.timezone
            or (request.current.timezone if request.current else None)
            or str(prefs.get("timezone") or "UTC")
        )
        try:
            ZoneInfo(timezone)
        except Exception:  # noqa: BLE001
            timezone = "UTC"
        prompt = request.prompt
        if request.current is not None:
            prompt = (
                "Change this existing automation as asked. Keep its step ids and everything "
                "the user didn't ask to change; return the complete updated automation and "
                'list each change in "changes".\n'
                f"Current automation: {json.dumps(request.current.model_dump(mode='json'))}\n"
                f"Requested change: {request.prompt}"
            )
        messages: list[Any] = [
            SystemMessage(
                content=await self._system(
                    catalog,
                    timezone,
                    relevant_apps(
                        request.prompt,
                        catalog,
                        [
                            s.action.split(".", 1)[0]
                            for s in iter_steps(
                                Workflow.model_validate(request.current.workflow).steps
                            )
                            if isinstance(s, ActionStep)
                        ]
                        if request.current is not None
                        else None,
                    ),
                )
            ),
            HumanMessage(content=prompt),
        ]
        parsed, reply = await self._ask(messages)
        workflow, problems = self._problems(parsed, catalog)
        if problems:
            log.info("automation_draft_repair", extra={"problems": problems[:3]})
            messages += [
                reply,
                HumanMessage(
                    content="That workflow has problems:\n- "
                    + "\n- ".join(problems)
                    + "\nReturn the corrected JSON object only."
                ),
            ]
            parsed, _ = await self._ask(messages)
            workflow, problems = self._problems(parsed, catalog)

        schedule, questions = _schedule(parsed.get("schedule"))
        if request.current is not None and not schedule and request.current.schedule_kind:
            schedule = {
                "schedule_kind": request.current.schedule_kind,
                "schedule_config": request.current.schedule_config,
            }
        questions += [str(q) for q in parsed.get("questions") or [] if str(q).strip()][:4]
        missing_ids = [str(a) for a in parsed.get("missing_apps") or []]
        unsupported = [
            Unsupported(
                request=str(u.get("request") or ""),
                reason=str(u.get("reason") or ""),
                suggestion=(str(u["suggestion"]) if u.get("suggestion") else None),
            )
            for u in parsed.get("unsupported") or []
            if isinstance(u, dict) and u.get("reason")
        ]
        issues: list[IssueOut] = []
        if workflow is not None and problems:
            # Still referring to actions that don't exist after the repair round.
            unsupported.append(
                Unsupported(
                    request="Part of this automation",
                    reason="Notely can't do one of the steps the AI suggested yet.",
                    suggestion="Build it step by step, or describe it differently.",
                )
            )
            workflow = None
        if workflow is None and problems and not unsupported:
            questions.append("Could you describe what should happen step by step?")
        if workflow is not None:
            workflow = normalise(workflow, catalog)
            for step in iter_steps(workflow.steps):
                if isinstance(step, ActionStep) and step.action in catalog.locked:
                    missing_ids.append(step.action.split(".", 1)[0])
            issues = [
                IssueOut(**i.to_dict())
                for i in await validate(self.ctx, workflow, catalog)
                if i.kind != "connect"
            ]
        missing: list[MissingApp] = []
        for app_id in dict.fromkeys(missing_ids):
            app = next((a for a in catalog.apps if a["id"] == app_id), None)
            if app is not None and not app.get("connected"):
                missing.append(
                    MissingApp(app=app_id, name=app["name"], connect_path=app["connect_path"])
                )
        name = str(parsed.get("name") or "").strip()[:160] or (
            request.current.name if request.current else None
        )
        return DraftOut(
            name=name or "New automation",
            description=str(parsed.get("description") or "").strip()[:500] or None,
            workflow=workflow.model_dump() if workflow else None,
            timezone=timezone,
            questions=list(dict.fromkeys(questions))[:5],
            missing_apps=missing,
            unsupported=unsupported,
            changes=[str(c) for c in parsed.get("changes") or []][:10],
            issues=issues,
            **schedule,
        )


async def draft_automation(ctx: ActionContext, request: DraftRequest) -> DraftOut:
    return await AutomationPlanner(ctx).draft(request)
