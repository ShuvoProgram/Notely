"""ToolPolicyEngine — the mandatory gate between what the model proposes and what runs.

Input: who, which tool, which provider, what risk. Output: allowed? confirmation required?
The agent is never the final authority; this engine and the human approval step are.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.ai.tools.base import ToolArgumentError, ToolRegistry, ToolSpec
from app.models.ai import RiskLevel
from app.models.user import User


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    requires_confirmation: bool
    reason: str | None = None


@dataclass(frozen=True)
class ValidatedCall:
    call_id: str
    spec: ToolSpec
    args: Any  # parsed pydantic model
    decision: PolicyDecision


@dataclass(frozen=True)
class RejectedCall:
    call_id: str
    tool_name: str
    reason: str


# Defaults from the PRD. User preferences may tighten (never loosen) these.
_DEFAULT_CONFIRMATION: dict[RiskLevel, bool] = {
    RiskLevel.read: False,
    RiskLevel.write: True,
    RiskLevel.external_communication: True,
    RiskLevel.destructive: True,
}


class ToolPolicyEngine:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def evaluate(self, user: User, spec: ToolSpec) -> PolicyDecision:
        prefs = user.preferences.get("ai", {}) if isinstance(user.preferences, dict) else {}
        requires = _DEFAULT_CONFIRMATION[spec.risk]
        # A user may opt in to confirming reads as well; nothing can turn off write confirmation.
        if spec.risk == RiskLevel.read and prefs.get("confirm_reads") is True:
            requires = True
        if spec.risk in (RiskLevel.external_communication, RiskLevel.destructive):
            requires = True
        return PolicyDecision(allowed=True, requires_confirmation=requires)

    def validate_calls(
        self, user: User, tool_calls: list[dict[str, Any]]
    ) -> tuple[list[ValidatedCall], list[RejectedCall]]:
        """Resolve model tool calls against the registry, validate arguments, apply policy."""
        accepted: list[ValidatedCall] = []
        rejected: list[RejectedCall] = []
        for call in tool_calls:
            call_id = str(call.get("id") or "")
            name = str(call.get("name") or "")
            spec = self.registry.get(name)
            if spec is None:
                rejected.append(RejectedCall(call_id, name, f"Unknown tool '{name}'"))
                continue
            raw_args = call.get("args") or {}
            try:
                args = spec.parse_args(raw_args if isinstance(raw_args, dict) else {})
            except ToolArgumentError as exc:
                rejected.append(RejectedCall(call_id, name, f"Invalid arguments: {exc}"))
                continue
            decision = self.evaluate(user, spec)
            if not decision.allowed:
                rejected.append(RejectedCall(call_id, name, decision.reason or "Not allowed"))
                continue
            accepted.append(ValidatedCall(call_id, spec, args, decision))
        return accepted, rejected
