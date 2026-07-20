"""Compilation of analyzer graph IR into executable server-side constraints."""

from __future__ import annotations

from memorii.core.memory_evolution.query_graph import (
    AmbiguousEntityReference,
    ExecutableGraphPattern,
    ExecutableGraphQuery,
    ExecutableObjectConstraint,
    ExplicitEntitySet,
    GraphCompilationFailure,
    GraphCompilationFailureCode,
    ResolvedEntityReference,
    UnresolvedEntityReference,
)
from memorii.core.memory_evolution.temporal_contracts import QueryAnalysis


def compile_graph_query(
    analysis: QueryAnalysis,
) -> ExecutableGraphQuery | GraphCompilationFailure | None:
    """Compile structured graph patterns without resolving uncertainty heuristically."""

    if not analysis.graph_patterns:
        return None
    compiled: list[ExecutableGraphPattern] = []
    for pattern in analysis.graph_patterns:
        effective_predicate_id = pattern.predicate_id or analysis.predicate_id
        source_pattern = (
            pattern
            if pattern.predicate_id is not None or effective_predicate_id is None
            else pattern.model_copy(update={"predicate_id": effective_predicate_id})
        )
        subject_entity_id: str | None = None
        if isinstance(pattern.subject, AmbiguousEntityReference):
            return GraphCompilationFailure(
                code=GraphCompilationFailureCode.AMBIGUOUS_SUBJECT,
                pattern=source_pattern,
                rationale="structured graph subject remains ambiguous",
            )
        if isinstance(pattern.subject, ResolvedEntityReference):
            subject_entity_id = pattern.subject.entity_id

        object_constraint: ExecutableObjectConstraint | None = None
        if pattern.object is not None:
            reference = pattern.object.entity
            if isinstance(reference, AmbiguousEntityReference):
                return GraphCompilationFailure(
                    code=GraphCompilationFailureCode.AMBIGUOUS_OBJECT,
                    pattern=source_pattern,
                    rationale="structured graph object remains ambiguous",
                )
            if isinstance(reference, UnresolvedEntityReference):
                return GraphCompilationFailure(
                    code=GraphCompilationFailureCode.UNRESOLVED_OBJECT,
                    pattern=source_pattern,
                    rationale="structured graph object was not resolved",
                )
            entity_ids: list[str] = []
            if isinstance(reference, ResolvedEntityReference):
                entity_ids = [reference.entity_id]
            elif isinstance(reference, ExplicitEntitySet):
                entity_ids = reference.entity_ids
            object_constraint = ExecutableObjectConstraint(
                operator=pattern.object.operator,
                entity_ids=entity_ids,
                literal_value=pattern.object.normalized_literal or pattern.object.literal_value,
            )
        compiled.append(
            ExecutableGraphPattern(
                source_pattern=source_pattern,
                subject_entity_id=subject_entity_id,
                predicate_id=effective_predicate_id,
                object_constraint=object_constraint,
            )
        )
    return ExecutableGraphQuery(patterns=compiled)
