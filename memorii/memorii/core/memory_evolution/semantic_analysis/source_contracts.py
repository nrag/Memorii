"""Canonical Step-2 source-contract owner.

The strict wire models live in the established semantic-ingestion contract
module today.  This owner is intentionally a narrow import boundary while the
remaining analysis contracts migrate; it avoids a second representation.
"""

from memorii.core.semantic_ingestion.contracts import (
    BootstrapDeclaredSegmentLanguageRoute,
    PreparedSegment,
    PreparedSource,
    SegmentLanguageRoute,
    SegmentLanguageRouteSet,
    TextPreparationPolicy,
    TextPreparationRequest,
)

__all__ = [
    "PreparedSegment",
    "PreparedSource",
    "BootstrapDeclaredSegmentLanguageRoute",
    "SegmentLanguageRoute",
    "SegmentLanguageRouteSet",
    "TextPreparationPolicy",
    "TextPreparationRequest",
]
