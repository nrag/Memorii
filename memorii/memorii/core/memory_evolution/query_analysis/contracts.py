"""Public contracts for semantic query analysis."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from memorii.core.memory_evolution.models import MemoryScope
from memorii.core.memory_evolution.temporal_contracts import (
    QueryAnalysis,
    QueryScopeKind,
    TemporalAnchorCatalog,
    TemporalEntityCandidate,
    TemporalInterpretationProposal,
    TemporalResolution,
)


class QueryAnalyzer(Protocol):
    def analyze(
        self,
        *,
        query: str,
        language: str,
        reference_time: datetime | None,
        entity_candidates: list[TemporalEntityCandidate],
        anchor_catalog: TemporalAnchorCatalog,
        request_scope: MemoryScope | None = None,
    ) -> QueryAnalysis: ...


class LexicalQueryResolver(Protocol):
    """Locale-specific deterministic fallback used only when explicitly supported."""

    def supports(self, language: str) -> bool: ...

    def infer_predicate_id(self, query: str) -> str | None: ...

    def resolve_temporal_frame(
        self,
        query: str,
        *,
        reference_time: datetime | None,
        entity_candidates: list[TemporalEntityCandidate],
        language: str,
        anchor_catalog: TemporalAnchorCatalog,
        request_scope: MemoryScope | None,
    ) -> TemporalResolution: ...


class StructuredQueryAnalysisProvider(Protocol):
    """Provider boundary for structured semantic query analysis.

    Providers may return a validated model or a JSON-like mapping. They must
    not manufacture entity IDs; the analyzer validates all IDs against the
    server-provided candidate catalog.
    """

    def __call__(
        self,
        *,
        query: str,
        language: str,
        reference_time: datetime | None,
        entity_candidates: list[TemporalEntityCandidate],
        anchor_catalog: TemporalAnchorCatalog,
        request_scope: MemoryScope,
    ) -> TemporalInterpretationProposal | Mapping[str, object]: ...


class StructuredQueryProviderError(Exception):
    """Expected transport/provider failure at the structured-query boundary."""


class StructuredQueryConstraintError(ValueError):
    """Expected semantic constraint violation in provider output."""


class VisibleEntityCatalogEntry(BaseModel):
    entity_id: str
    names: list[str]
    entity_type: str | None

    model_config = ConfigDict(extra="forbid", frozen=True)


class VisibleAnchorCatalogEntry(BaseModel):
    anchor_id: str
    names: list[str]

    model_config = ConfigDict(extra="forbid", frozen=True)


class VisiblePredicateCatalogEntry(BaseModel):
    predicate_id: str
    description: str
    value_type: str

    model_config = ConfigDict(extra="forbid", frozen=True)


class StructuredQueryVisibleContext(BaseModel):
    language: str
    reference_time: datetime | None
    scope_kind: QueryScopeKind
    entities: list[VisibleEntityCatalogEntry]
    temporal_anchors: list[VisibleAnchorCatalogEntry]
    predicates: list[VisiblePredicateCatalogEntry]
    graph_operators: list[str]

    model_config = ConfigDict(extra="forbid", frozen=True)
