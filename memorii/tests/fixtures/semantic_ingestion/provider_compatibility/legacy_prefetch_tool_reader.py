"""Frozen independent reader for pre-attention legacy provider bytes."""

from __future__ import annotations

import json

PREFETCH_FIELDS = ("context", "selected_channel", "canonical", "evolution", "evolution_decision")
TOOL_FIELDS = ("tool_name", "ok", "result", "error")

def _object(raw: bytes) -> dict[str, object]:
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("legacy payload must be object")
    return value

def read_prefetch(raw: bytes) -> dict[str, object]:
    value = _object(raw)
    if tuple(value) != PREFETCH_FIELDS:
        raise ValueError("legacy prefetch field order changed")
    if value["selected_channel"] not in {"canonical", "evolution", "none"}:
        raise ValueError("legacy prefetch changed")
    return value

def read_tool(raw: bytes) -> dict[str, object]:
    value = _object(raw)
    if (
        tuple(value) != TOOL_FIELDS
        or not isinstance(value["tool_name"], str)
        or not isinstance(value["ok"], bool)
        or not isinstance(value["result"], dict)
    ):
        raise ValueError("legacy tool changed")
    return value
