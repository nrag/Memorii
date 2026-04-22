"""Deterministic normalization helpers for benchmark retrieval scoring."""

from __future__ import annotations

import unicodedata


def normalize_text(text: str) -> str:
    """Apply Unicode-safe deterministic normalization."""
    return unicodedata.normalize("NFKC", text).casefold()
