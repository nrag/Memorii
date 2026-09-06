"""Deterministic route selection for one prepared segment.

Concrete fastText loading belongs in an adapter.  This pure owner closes the
threshold/margin decision and never silently selects an unsupported resource.
"""

from __future__ import annotations

from memorii.core.semantic_ingestion.contracts import LanguageCandidate


def select_language(
    *, candidates: tuple[LanguageCandidate, ...], supported_languages: tuple[str, ...],
    minimum_probability_ppm: int, minimum_margin_ppm: int,
) -> tuple[str | None, str]:
    """Return ``(language, decision)`` without consulting mutable registry state."""

    if not candidates:
        return None, "uncertain"
    ordered = tuple(sorted(candidates, key=lambda item: (-item.probability_ppm, item.language)))
    lead = ordered[0]
    runner_up = ordered[1].probability_ppm if len(ordered) > 1 else 0
    if lead.language not in supported_languages:
        return None, "unsupported"
    if lead.probability_ppm < minimum_probability_ppm or lead.probability_ppm - runner_up < minimum_margin_ppm:
        return None, "uncertain"
    return lead.language, "selected"


__all__ = ["select_language"]
