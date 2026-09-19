"""Success envelope: every API response is {"data": ..., "meta": {...}}."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Envelope[T](BaseModel):
    data: T
    meta: dict[str, Any] = Field(default_factory=dict)


def ok(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"data": data, "meta": meta or {}}
