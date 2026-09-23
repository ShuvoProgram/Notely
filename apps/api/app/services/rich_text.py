"""TipTap/ProseMirror JSON helpers. The API stores TipTap JSON as canonical rich text and
derives plain text from it for search, AI context and indexing."""

from __future__ import annotations

import copy
from typing import Any

BLOCK_NODES = {
    "paragraph",
    "heading",
    "blockquote",
    "codeBlock",
    "listItem",
    "taskItem",
    "bulletList",
    "orderedList",
    "taskList",
    "horizontalRule",
    "table",
    "tableRow",
}

EMPTY_DOC: dict[str, Any] = {"type": "doc", "content": [{"type": "paragraph"}]}

MAX_PLAIN_TEXT = 500_000


def is_valid_doc(doc: Any) -> bool:
    return (
        isinstance(doc, dict)
        and doc.get("type") == "doc"
        and isinstance(doc.get("content", []), list)
    )


def plain_text_doc(value: str) -> dict[str, Any]:
    """Convert trustworthy workflow output into the editor's canonical document format."""
    lines = [line.strip() for line in value.replace("\r\n", "\n").split("\n") if line.strip()]
    if not lines:
        return copy.deepcopy(EMPTY_DOC)
    return {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": line}]} for line in lines
        ],
    }


def merge_docs(existing: dict[str, Any], incoming: dict[str, Any], mode: str) -> dict[str, Any]:
    """Safely insert one valid TipTap document into another without mutating either input."""
    if mode == "replace":
        return copy.deepcopy(incoming)
    existing_content = copy.deepcopy(existing.get("content") or [])
    incoming_content = copy.deepcopy(incoming.get("content") or [])
    if mode == "prepend":
        content = incoming_content + existing_content
    else:
        content = existing_content + incoming_content
    return {"type": "doc", "content": content or copy.deepcopy(EMPTY_DOC["content"])}


def to_plain_text(doc: dict[str, Any] | None) -> str:
    """Flatten a TipTap document to newline-separated plain text."""
    if not doc:
        return ""
    parts: list[str] = []

    def walk(node: dict[str, Any]) -> None:
        node_type = node.get("type")
        if node_type == "text":
            parts.append(str(node.get("text", "")))
            return
        if node_type == "hardBreak":
            parts.append("\n")
            return
        for child in node.get("content", []) or []:
            if isinstance(child, dict):
                walk(child)
        if node_type in BLOCK_NODES:
            parts.append("\n")

    walk(doc)
    text = "".join(parts)
    lines = (line.strip() for line in text.split("\n"))
    return "\n".join(line for line in lines if line)[:MAX_PLAIN_TEXT]


def checklist_progress(doc: dict[str, Any] | None) -> tuple[int, int]:
    """(checked, total) task items anywhere in the document; (0, 0) when there are none."""
    done = total = 0

    def walk(node: Any) -> None:
        nonlocal done, total
        if not isinstance(node, dict):
            return
        if node.get("type") == "taskItem":
            total += 1
            if (node.get("attrs") or {}).get("checked"):
                done += 1
        for child in node.get("content") or []:
            walk(child)

    walk(doc)
    return done, total


def excerpt(text: str, length: int = 160) -> str:
    text = " ".join(text.split())
    return text if len(text) <= length else text[: length - 1].rstrip() + "…"
