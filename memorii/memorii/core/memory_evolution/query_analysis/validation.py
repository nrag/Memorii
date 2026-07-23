"""Server-owned validation for structured query proposals."""

from __future__ import annotations

from memorii.core.memory_evolution.models import MemoryScope
from memorii.core.memory_evolution.predicates import PredicateRegistry
from memorii.core.memory_evolution.query_analysis.contracts import StructuredQueryConstraintError
from memorii.core.memory_evolution.query_graph import (
    AmbiguousEntityReference,
    ExplicitEntitySet,
    ResolvedEntityReference,
)
from memorii.core.memory_evolution.temporal_contracts import (
    QueryAnalysis,
    QueryScopeKind,
    QueryTemporalFrame,
    TemporalAnchorCatalog,
    TemporalEntityCandidate,
)


def validate_temporal_frame_constraints(
    frame: QueryTemporalFrame,
    *,
    entity_candidates: list[TemporalEntityCandidate],
    anchor_catalog: TemporalAnchorCatalog,
    request_scope: MemoryScope | None = None,
) -> QueryTemporalFrame:
    """Validate a structured frame against server-owned retrieval catalogs.

    A validated Pydantic object is not sufficient: its identifiers and anchor
    interval must also belong to the current runtime catalog.
    """

    candidate_by_id = {candidate.entity_id: candidate for candidate in entity_candidates}
    unknown_ids = set(frame.resolved_entity_ids) - set(candidate_by_id)
    if unknown_ids:
        raise StructuredQueryConstraintError("structured query selected unknown entity candidates")
    effective_scope = request_scope or MemoryScope()
    expected_frame_scope_key = effective_scope.scope_key
    if frame.scope_key is None:
        frame = frame.with_scope(
            expected_frame_scope_key,
            scope_kind=query_scope_kind(effective_scope),
        )
    if frame.scope_key != expected_frame_scope_key:
        raise StructuredQueryConstraintError("structured query selected an out-of-scope frame")
    for entity_id in frame.resolved_entity_ids:
        if not effective_scope.can_read(candidate_by_id[entity_id].scope):
            raise StructuredQueryConstraintError("structured query selected an out-of-scope entity")
    if frame.anchor_id is not None:
        anchor = next((item for item in anchor_catalog.anchors if item.anchor_id == frame.anchor_id), None)
        if anchor is None:
            raise StructuredQueryConstraintError("structured query selected an unknown temporal anchor")
        if frame.valid_from != anchor.valid_from or frame.valid_to != anchor.valid_to:
            raise StructuredQueryConstraintError("structured query changed the registered anchor interval")
        if not effective_scope.can_read(anchor.scope):
            raise StructuredQueryConstraintError("structured query selected an out-of-scope temporal anchor")
    return frame


def query_scope_kind(scope: MemoryScope) -> QueryScopeKind:
    if scope.task_id is not None:
        return QueryScopeKind.TASK
    if scope.session_id is not None:
        return QueryScopeKind.SESSION
    if scope.user_id is not None:
        return QueryScopeKind.USER
    return QueryScopeKind.GLOBAL


def validate_query_analysis_constraints(
    analysis: QueryAnalysis,
    *,
    entity_candidates: list[TemporalEntityCandidate],
    anchor_catalog: TemporalAnchorCatalog,
    request_scope: MemoryScope | None = None,
    predicate_registry: PredicateRegistry | None = None,
) -> QueryAnalysis:
    """Validate structured query identifiers at the retrieval trust boundary."""

    if analysis.temporal_frame is None:
        raise StructuredQueryConstraintError("structured query analysis must return a temporal frame")
    requested_ids = set(analysis.temporal_frame.resolved_entity_ids)
    if analysis.subject_entity_id is not None:
        requested_ids.add(analysis.subject_entity_id)
    for pattern in analysis.graph_patterns:
        requested_ids.update(_reference_entity_ids(pattern.subject))
        if pattern.object is not None and pattern.object.entity is not None:
            requested_ids.update(_reference_entity_ids(pattern.object.entity))
    candidate_by_id = {candidate.entity_id: candidate for candidate in entity_candidates}
    unknown_ids = requested_ids - set(candidate_by_id)
    if unknown_ids:
        raise StructuredQueryConstraintError("structured query selected unknown entity candidates")
    effective_scope = request_scope or MemoryScope()
    for entity_id in requested_ids:
        if not effective_scope.can_read(candidate_by_id[entity_id].scope):
            raise StructuredQueryConstraintError("structured query selected an out-of-scope entity")
    frame = validate_temporal_frame_constraints(
        analysis.temporal_frame,
        entity_candidates=entity_candidates,
        anchor_catalog=anchor_catalog,
        request_scope=request_scope,
    )
    if (
        analysis.predicate_id is not None
        and predicate_registry is not None
        and predicate_registry.get(analysis.predicate_id) is None
    ):
        raise StructuredQueryConstraintError(f"structured query selected unknown predicate: {analysis.predicate_id}")
    for pattern in analysis.graph_patterns:
        if analysis.predicate_id is not None and pattern.predicate_id not in {None, analysis.predicate_id}:
            raise StructuredQueryConstraintError("structured query predicate conflicts with graph pattern")
        if (
            analysis.subject_entity_id is not None
            and isinstance(pattern.subject, ResolvedEntityReference)
            and pattern.subject.entity_id != analysis.subject_entity_id
        ):
            raise StructuredQueryConstraintError("structured query subject conflicts with graph pattern")
        if (
            pattern.predicate_id is not None
            and predicate_registry is not None
            and predicate_registry.get(pattern.predicate_id) is None
        ):
            raise StructuredQueryConstraintError(
                f"structured query selected unknown predicate: {pattern.predicate_id}"
            )
        for reference in (
            pattern.subject,
            pattern.object.entity if pattern.object is not None else None,
        ):
            if reference is None or not reference.expected_entity_types:
                continue
            mismatched = {
                entity_id
                for entity_id in _reference_entity_ids(reference)
                if candidate_by_id[entity_id].entity_type not in reference.expected_entity_types
            }
            if mismatched:
                raise StructuredQueryConstraintError(
                    "structured query entity candidates violate declared type constraints"
                )
    return analysis.model_copy(update={"temporal_frame": frame})


def _reference_entity_ids(reference: object) -> set[str]:
    if isinstance(reference, ResolvedEntityReference):
        return {reference.entity_id}
    if isinstance(reference, AmbiguousEntityReference):
        return set(reference.candidate_entity_ids)
    if isinstance(reference, ExplicitEntitySet):
        return set(reference.entity_ids)
    return set()
