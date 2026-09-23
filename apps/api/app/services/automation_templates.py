"""Built-in starting points. Templates are plain workflow data using real catalog actions;
the dashboard only offers the ones whose apps the user has connected."""

from __future__ import annotations

from typing import Any


def _action(step_id: str, action: str, inputs: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {"kind": "action", "id": step_id, "action": action, "inputs": inputs, **extra}


BUILTIN_TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "daily-email-summary",
        "name": "Daily email summary",
        "description": (
            "Every weekday morning, summarize important Gmail, create tasks for the action "
            "items and add the summary to a note."
        ),
        "schedule_kind": "weekly",
        "schedule_config": {"time": "09:00", "days": [0, 1, 2, 3, 4]},
        "prompt": (
            "Every weekday at 9 AM, check my important Gmail, summarize anything that needs "
            "attention, create tasks for the action items, and add the summary to a note."
        ),
        "workflow": {
            "version": 2,
            "steps": [
                _action(
                    "important_mail",
                    "gmail.search_mail",
                    {"query": "is:important newer_than:1d", "limit": 20},
                ),
                {
                    "kind": "filter",
                    "id": "has_mail",
                    "name": "Only continue if there are emails",
                    "condition": {
                        "match": "all",
                        "rules": [
                            {
                                "left": "{{steps.important_mail.output.results.count}}",
                                "operator": "greater_than",
                                "right": 0,
                            }
                        ],
                    },
                },
                _action(
                    "summary",
                    "ai.summarize",
                    {
                        "data": "{{steps.important_mail.output.results}}",
                        "focus": "anything that needs a reply or a decision",
                    },
                ),
                _action(
                    "action_items",
                    "ai.extract_action_items",
                    {"data": "{{steps.important_mail.output.results}}"},
                ),
                _action(
                    "tasks",
                    "notely.create_tasks",
                    {"items": "{{steps.action_items.output.action_items}}"},
                ),
                _action(
                    "save_summary",
                    "notely.update_note",
                    {"note": "", "content": "{{steps.summary.output.summary}}", "mode": "append"},
                ),
            ],
        },
    },
    {
        "id": "morning-agenda",
        "name": "Morning agenda",
        "description": "Each morning, get a short notification summarizing today's meetings.",
        "schedule_kind": "daily",
        "schedule_config": {"time": "08:00"},
        "prompt": "Every morning at 8, summarize today's Google Calendar events and notify me.",
        "workflow": {
            "version": 2,
            "steps": [
                _action("todays_events", "google_calendar.list_events", {"days": 1, "limit": 20}),
                _action(
                    "agenda",
                    "ai.summarize",
                    {
                        "data": "{{steps.todays_events.output.events}}",
                        "focus": "times, who is attending, and anything to prepare",
                    },
                ),
                _action(
                    "tell_me",
                    "notely.notify",
                    {"message": "Today's agenda\n{{steps.agenda.output.summary}}"},
                ),
            ],
        },
    },
    {
        "id": "weekly-review",
        "name": "Weekly review",
        "description": "Every Friday, write a review note from your open tasks and recent notes.",
        "schedule_kind": "weekly",
        "schedule_config": {"time": "16:00", "days": [4]},
        "prompt": (
            "Every Friday at 4 PM, review my open tasks and recent notes and write a weekly "
            "review note."
        ),
        "workflow": {
            "version": 2,
            "steps": [
                _action("open_tasks", "notely.find_tasks", {"status": "open", "limit": 50}),
                _action("recent_notes", "notely.find_notes", {"limit": 20}),
                _action(
                    "review",
                    "ai.ask",
                    {
                        "instructions": (
                            "Write a short weekly review: what moved forward, what is still "
                            "open, and the three most important things for next week."
                        ),
                        "data": (
                            "Open tasks:\n{{steps.open_tasks.output.tasks}}\n\n"
                            "Recent notes:\n{{steps.recent_notes.output.notes}}"
                        ),
                    },
                ),
                _action(
                    "review_note",
                    "notely.create_note",
                    {
                        "title": "Weekly review",
                        "content": "{{steps.review.output.text}}",
                    },
                ),
            ],
        },
    },
    {
        "id": "task-nudge",
        "name": "Task nudge",
        "description": "Every afternoon, if you have open tasks, get told which ones matter most.",
        "schedule_kind": "daily",
        "schedule_config": {"time": "14:00"},
        "prompt": (
            "Every day at 2 PM, if I have open tasks, tell me which three matter most right now."
        ),
        "workflow": {
            "version": 2,
            "steps": [
                _action("open_tasks", "notely.find_tasks", {"status": "open", "limit": 50}),
                {
                    "kind": "filter",
                    "id": "has_tasks",
                    "name": "Only continue if there are open tasks",
                    "condition": {
                        "match": "all",
                        "rules": [
                            {
                                "left": "{{steps.open_tasks.output.count}}",
                                "operator": "greater_than",
                                "right": 0,
                            }
                        ],
                    },
                },
                _action(
                    "priorities",
                    "ai.ask",
                    {
                        "instructions": (
                            "Pick the three tasks that matter most right now and say why in "
                            "one line each."
                        ),
                        "data": "{{steps.open_tasks.output.tasks}}",
                    },
                ),
                _action(
                    "tell_me",
                    "notely.notify",
                    {"message": "Focus for this afternoon\n{{steps.priorities.output.text}}"},
                ),
            ],
        },
    },
]
