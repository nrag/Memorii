"""Language capability helpers for deterministic memory evolution."""

from __future__ import annotations


def primary_language(language: str) -> str:
    """Return a normalized BCP-47 primary language subtag."""

    return language.strip().casefold().replace("_", "-").partition("-")[0]


def supports_english_rules(language: str) -> bool:
    """Return whether English-only deterministic rules may inspect the text."""

    return primary_language(language) in {"en", "eng"}
