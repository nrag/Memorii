"""Deterministic runtime-owned identity helpers for memory extraction."""

from __future__ import annotations

import re
from uuid import NAMESPACE_URL, uuid5


def normalize_extracted_name(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip(" .:")).lower()


def stable_extraction_id(prefix: str, value: str) -> str:
    return f"{prefix}:{uuid5(NAMESPACE_URL, value)}"


def stable_entity_id(value: str) -> str:
    return f"ent:{normalize_extracted_name(value).replace(' ', '-')}"
