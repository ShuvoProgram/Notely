"""Cooperative cancellation flag for agent runs (Redis/KV, checked between steps)."""

from __future__ import annotations

import uuid

CANCEL_TTL = 3600


def cancel_key(run_id: uuid.UUID) -> str:
    return f"ai:cancel:{run_id}"
