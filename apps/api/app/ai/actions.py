"""Note AI actions: summarize, improve, key points, extract tasks, custom instruction.

These are single model calls over one note (or a selection). They only *suggest*: the client
previews the result and the user chooses Insert / Replace / Copy. Nothing is written here.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import AsyncIterator
from datetime import date
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm import get_chat_model, resolve_model_alias
from app.ai.prompts import NOTE_ACTION_INSTRUCTIONS, NOTE_ACTION_SYSTEM_PROMPT, SUMMARY_LENGTHS
from app.ai.tools.base import untrusted
from app.core.config import Settings
from app.core.exceptions import ValidationFailed
from app.models.task import TaskPriority
from app.models.user import User
from app.services.note_service import NoteService

NoteAction = Literal["summarize", "improve", "key_points", "extract_tasks", "custom"]
MAX_INPUT_CHARS = 40_000


class ExtractedTask(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    due_date: date | None = None
    priority: TaskPriority = TaskPriority.none


class NoteActionRequest(BaseModel):
    note_id: uuid.UUID
    action: NoteAction
    instruction: str | None = Field(default=None, max_length=2000)
    selection: str | None = Field(default=None, max_length=MAX_INPUT_CHARS)


def _instruction(action: NoteAction, *, instruction: str | None, prefs: dict[str, Any]) -> str:
    if action == "custom":
        if not instruction or not instruction.strip():
            raise ValidationFailed("Tell the assistant what to do with the note.")
        return NOTE_ACTION_INSTRUCTIONS["custom"].format(instruction=instruction.strip())
    if action == "summarize":
        length = SUMMARY_LENGTHS.get(
            str(prefs.get("summary_length", "medium")), SUMMARY_LENGTHS["medium"]
        )
        return NOTE_ACTION_INSTRUCTIONS["summarize"].format(length=length)
    return NOTE_ACTION_INSTRUCTIONS[action]


def parse_tasks(raw: str) -> list[ExtractedTask]:
    """Tolerant JSON extraction: models sometimes wrap JSON in prose or code fences."""
    match = re.search(r"\[.*\]", raw, flags=re.S)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except ValueError:
        return []
    tasks: list[ExtractedTask] = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        try:
            tasks.append(
                ExtractedTask.model_validate({**item, "priority": item.get("priority") or "none"})
            )
        except ValidationError:
            continue
    return tasks[:50]


class NoteActionService:
    def __init__(self, db: AsyncSession, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    async def run(self, user: User, request: NoteActionRequest) -> AsyncIterator[dict[str, Any]]:
        note = await NoteService(self.db).get_note(user, request.note_id)
        prefs = (user.preferences or {}).get("ai", {}) if isinstance(user.preferences, dict) else {}
        source_text = (request.selection or note.plain_text)[:MAX_INPUT_CHARS]
        if not source_text.strip():
            raise ValidationFailed("This note is empty, so there is nothing to work with.")

        from app.services.ai_settings_service import AISettingsService

        byo = await AISettingsService(self.db, self.settings).resolve(user)
        model = get_chat_model(
            resolve_model_alias(
                self.settings, prefs.get("model") if isinstance(prefs, dict) else None
            ),
            settings=self.settings,
            temperature=0.3,
            script_key=str(user.id),
            byo=byo,
        )
        instruction = _instruction(request.action, instruction=request.instruction, prefs=prefs)
        messages = [
            SystemMessage(content=NOTE_ACTION_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    f"{instruction}\n\n"
                    f"Note title: {note.title or 'Untitled'}\n"
                    f"{untrusted(source_text, source=f'note:{note.id}')}"
                )
            ),
        ]
        yield {"type": "start", "action": request.action, "note_id": str(note.id)}
        parts: list[str] = []
        async for chunk in model.astream(messages):
            text = (
                chunk.content
                if isinstance(chunk.content, str)
                else "".join(p.get("text", "") for p in chunk.content if isinstance(p, dict))
            )
            if text:
                parts.append(text)
                if request.action != "extract_tasks":
                    yield {"type": "token", "text": text}
        result = "".join(parts).strip()
        if request.action == "extract_tasks":
            tasks = parse_tasks(result)
            yield {"type": "tasks", "tasks": [t.model_dump(mode="json") for t in tasks]}
        yield {"type": "done", "content": result, "action": request.action}
