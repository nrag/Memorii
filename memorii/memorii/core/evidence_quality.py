"""Typed, model-visible evidence quality signals used by decision providers."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class EntityAttribution(StrEnum):
    ALIGNED = "aligned"
    MISALIGNED = "misaligned"
    UNKNOWN = "unknown"


class EvidenceIndependence(StrEnum):
    INDEPENDENT = "independent"
    CORRELATED = "correlated"
    UNKNOWN = "unknown"


class EvidenceFreshness(StrEnum):
    CURRENT = "current"
    STALE = "stale"
    SUPERSEDED = "superseded"
    UNKNOWN = "unknown"


class EvidenceObservability(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"
    UNKNOWN = "unknown"


class EvidenceQualitySignals(BaseModel):
    """Structured facts about evidence quality; unknown is explicit, never inferred."""

    entity_attribution: EntityAttribution = EntityAttribution.UNKNOWN
    independence: EvidenceIndependence = EvidenceIndependence.UNKNOWN
    freshness: EvidenceFreshness = EvidenceFreshness.UNKNOWN
    observability: EvidenceObservability = EvidenceObservability.UNKNOWN
    source_count: int = Field(default=0, ge=0)
    oscillation_detected: bool = False

    model_config = ConfigDict(extra="forbid", frozen=True)
