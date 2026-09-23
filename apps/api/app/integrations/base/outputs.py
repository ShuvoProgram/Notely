"""Output descriptions shared by connectors, for automation data mapping.

A connector declares what a tool returns with `ProviderTool(..., outputs=...)`; automations
then offer "Insert data → Gmail · Emails found · Subject" instead of raw data.
"""

from __future__ import annotations

from app.ai.tools.base import OutputField as F


def listing(key: str, label: str, *fields: F) -> F:
    return F(key, label, "list", tuple(fields))


# The shape of `IntegrationProvider.search()` hits, which many search tools return as-is.
HIT_FIELDS = (
    F("title", "Title"),
    F("snippet", "Preview"),
    F("url", "Link", "url"),
    F("updated_at", "Last updated", "date"),
)
SEARCH_RESULTS = (listing("results", "Results", *HIT_FIELDS),)
