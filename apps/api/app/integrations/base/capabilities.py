"""Unified capability model. Providers map their operations onto these; the agent reasons in
these terms, and risk is derived from them unless a provider says otherwise."""

from __future__ import annotations

import enum

from app.models.ai import RiskLevel


class Capability(enum.StrEnum):
    search = "search"
    read = "read"
    create = "create"
    update = "update"
    delete = "delete"
    draft = "draft"
    send = "send"
    schedule = "schedule"
    comment = "comment"
    attach = "attach"
    sync = "sync"


DEFAULT_RISK: dict[Capability, RiskLevel] = {
    Capability.search: RiskLevel.read,
    Capability.read: RiskLevel.read,
    Capability.create: RiskLevel.write,
    Capability.update: RiskLevel.write,
    Capability.draft: RiskLevel.write,
    Capability.schedule: RiskLevel.write,
    Capability.attach: RiskLevel.write,
    Capability.sync: RiskLevel.write,
    Capability.comment: RiskLevel.external_communication,
    Capability.send: RiskLevel.external_communication,
    Capability.delete: RiskLevel.destructive,
}


def risk_for(capability: Capability | str) -> RiskLevel:
    return DEFAULT_RISK[Capability(capability)]
