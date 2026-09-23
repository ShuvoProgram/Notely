"""The action contract every automation capability implements.

An action is described for people (label, input fields, output fields, safety) and for the
engine (a handler that takes resolved inputs and returns output data). Notely built-ins,
AI steps and connector tools all become ``ActionDefinition``s.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from app.ai.tools.base import OutputField

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.config import Settings
    from app.models.user import User
    from app.services.connection_service import ConnectionService

Safety = Literal["safe", "ask", "always_ask"]
Group = Literal["find", "do", "ai"]

SAFETY_TEXT: dict[str, str] = {
    "safe": "Safe to run automatically",
    "ask": "Asks you first unless you allow it to run automatically",
    "always_ask": "Always asks you first",
}


class ActionError(Exception):
    """A failure explained in plain language. `details` may carry a fix-it link."""

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message)
        self.message = message
        self.details = {key: value for key, value in details.items() if value is not None}


@dataclass(frozen=True)
class InputField:
    key: str
    label: str
    # text | long_text | number | boolean | choice | list | date | datetime | note | email
    type: str = "text"
    required: bool = False
    help: str | None = None
    options: tuple[tuple[str, str], ...] = ()  # (value, label)
    default: Any = None
    placeholder: str | None = None
    # When false the field cannot take data from earlier steps (e.g. a fixed choice).
    mappable: bool = True

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "key": self.key,
            "label": self.label,
            "type": self.type,
            "required": self.required,
            "mappable": self.mappable,
        }
        if self.help:
            out["help"] = self.help
        if self.options:
            out["options"] = [{"value": v, "label": label} for v, label in self.options]
        if self.default is not None:
            out["default"] = self.default
        if self.placeholder:
            out["placeholder"] = self.placeholder
        return out


@dataclass
class ActionContext:
    db: AsyncSession
    user: User
    settings: Settings
    connections: ConnectionService
    test: bool = False
    # The automation's time zone: dates written into notes use the user's clock.
    timezone: str = "UTC"


Handler = Callable[[ActionContext, dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class ActionDefinition:
    id: str  # "<app>.<name>", e.g. "gmail.search_mail"
    app: str
    label: str
    description: str
    group: Group
    safety: Safety
    handler: Handler
    inputs: tuple[InputField, ...] = ()
    outputs: tuple[OutputField, ...] = ()
    # Changes data somewhere. Test runs simulate these instead of performing them.
    writes: bool = False
    # How to describe the planned action in a test run / approval ("Create task “…”").
    describe: Callable[[dict[str, Any]], str] | None = None
    keywords: tuple[str, ...] = field(default_factory=tuple)
    # False for actions of apps the user hasn't connected (shown locked, never executed).
    available: bool = True

    def to_dict(self, app_name: str, app_logo: str | None) -> dict[str, Any]:
        return {
            "available": self.available,
            "id": self.id,
            "app": self.app,
            "app_name": app_name,
            "app_logo": app_logo,
            "label": self.label,
            "description": self.description,
            "group": self.group,
            "safety": self.safety,
            "safety_text": SAFETY_TEXT[self.safety],
            "writes": self.writes,
            "inputs": [f.to_dict() for f in self.inputs],
            "outputs": [f.to_dict() for f in self.outputs],
        }

    def summary_of(self, inputs: dict[str, Any]) -> str:
        if self.describe is not None:
            try:
                return self.describe(inputs)
            except Exception:  # noqa: BLE001 — a description must never break a run
                pass
        return self.label
