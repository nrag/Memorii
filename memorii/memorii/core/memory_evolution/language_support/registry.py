"""Immutable registry for extraction language capabilities."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from types import MappingProxyType

from memorii.core.memory_evolution.language import primary_language
from memorii.core.memory_evolution.language_support.contracts import ExtractionLanguageCapabilities
from memorii.core.memory_evolution.language_support.english import EnglishExtractionCapabilities
from memorii.core.memory_evolution.language_support.spanish import SpanishExtractionCapabilities


class ExtractionLanguageRegistry:
    """Resolve a BCP-47 tag only to an explicitly registered same-language pack."""

    def __init__(self, capabilities: Iterable[ExtractionLanguageCapabilities]) -> None:
        by_code: dict[str, ExtractionLanguageCapabilities] = {}
        for capability in capabilities:
            for code in capability.language_codes:
                normalized = primary_language(code)
                if normalized in by_code:
                    raise ValueError(f"duplicate extraction language capability:{normalized}")
                by_code[normalized] = capability
        self._by_code: Mapping[str, ExtractionLanguageCapabilities] = MappingProxyType(by_code)

    def resolve(self, language: str) -> ExtractionLanguageCapabilities | None:
        return self._by_code.get(primary_language(language))


DEFAULT_EXTRACTION_LANGUAGE_REGISTRY = ExtractionLanguageRegistry(
    (EnglishExtractionCapabilities(), SpanishExtractionCapabilities())
)
