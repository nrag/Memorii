"""Unicode-aware text primitives shared by query analyzers and anchors."""

from __future__ import annotations

import re
import unicodedata


def normalize_query_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def contains_query_phrase(normalized_query: str, phrase: str) -> bool:
    """Match a normalized phrase without substring collisions such as Q1/Q10."""

    normalized_phrase = normalize_query_text(phrase)
    if not normalized_phrase:
        return False
    pattern = rf"(?<!\w){re.escape(normalized_phrase)}(?!\w)"
    return re.search(pattern, normalized_query, flags=re.UNICODE) is not None
