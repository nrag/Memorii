"""Production retrieval orchestration for evolved memory.

This module owns query analysis, lifecycle filtering, ranking, and execution
continuation projection.  The mutation/evolution service supplies read-only
callbacks; it does not own retrieval policy.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from memorii.core.memory_evolution.execution import (
    ContinuationResolutionStatus,
    WorkStateSnapshot,
    resolve_continuation,
)
from memorii.core.memory_evolution.models import (
    ClaimState,
    EntityLinkState,
    ExtractedAction,
    RetrievalView,
)
from memorii.core.memory_evolution.predicates import PredicateRegistry
from memorii.core.memory_evolution.retrieval import (
    ExecutionRetrievalState,
    MemoryQueryRequest,
    ProductionRetrievalDecision,
    RetrievalPurpose,
    rank_claims,
    resolve_memory_query,
)
from memorii.core.memory_evolution.temporal import (
    QueryAnalyzer,
    QueryTemporalFrame,
    QueryTemporalKind,
    StructuredQueryConstraintError,
    TemporalAnchorCatalog,
    TemporalEntityCandidate,
    validate_query_analysis_constraints,
    validate_query_analysis_matches_authoritative_result,
    validate_temporal_frame_constraints,
)


class MemoryEvolutionRetrievalRuntime:
    """Read-only retrieval runtime composed around an evolution store."""

    def __init__(
        self,
        *,
        claim_reader: Callable[..., list[ClaimState]],
        entity_link_reader: Callable[[], list[EntityLinkState]],
        action_reader: Callable[[], list[ExtractedAction]],
        work_state_reader: Callable[[], WorkStateSnapshot],
        query_analyzer: QueryAnalyzer,
        temporal_anchor_catalog: TemporalAnchorCatalog,
        now_provider: Callable[[], datetime],
        predicate_registry: PredicateRegistry | None = None,
    ) -> None:
        self._claim_reader = claim_reader
        self._entity_link_reader = entity_link_reader
        self._action_reader = action_reader
        self._work_state_reader = work_state_reader
        self._query_analyzer = query_analyzer
        self._temporal_anchor_catalog = temporal_anchor_catalog
        self._now_provider = now_provider
        self._predicate_registry = predicate_registry or PredicateRegistry()

    def retrieve(self, request: MemoryQueryRequest) -> ProductionRetrievalDecision:
        if request.reference_time is None:
            request = request.model_copy(update={"reference_time": self._now_provider()})
        links = [
            link
            for link in self._entity_link_reader()
            if link.lifecycle_state.value != "invalidated"
        ]
        catalog = [
            TemporalEntityCandidate(
                entity_id=link.canonical_entity_id,
                names=sorted({link.mention_text, link.normalized_name, *link.aliases}),
                lifecycle_state=link.lifecycle_state.value,
                lineage_parent_entity_id=link.lineage_parent_entity_id,
                valid_from=link.valid_from,
                valid_to=link.valid_to,
            )
            for link in links
            if link.aliases or link.mention_text
        ]
        authoritative_analysis = None
        try:
            if request.predicate_id is not None and self._predicate_registry.get(request.predicate_id) is None:
                raise StructuredQueryConstraintError(
                    f"unknown predicate requested: {request.predicate_id}"
                )
            if request.subject_entity_id is not None and request.subject_entity_id not in {
                candidate.entity_id for candidate in catalog
            }:
                raise StructuredQueryConstraintError("unknown subject entity requested")
            if request.temporal_frame is not None:
                validate_temporal_frame_constraints(
                    request.temporal_frame,
                    entity_candidates=catalog,
                    anchor_catalog=self._temporal_anchor_catalog,
                    scope_key=request.scope_key,
                )
            authoritative_analysis = self._query_analyzer.analyze(
                query=request.query,
                language=request.query_language,
                reference_time=request.reference_time,
                scope_key=request.scope_key,
                entity_candidates=catalog,
                anchor_catalog=self._temporal_anchor_catalog,
            )
            authoritative_analysis = validate_query_analysis_constraints(
                authoritative_analysis,
                entity_candidates=catalog,
                anchor_catalog=self._temporal_anchor_catalog,
                scope_key=request.scope_key,
                predicate_registry=self._predicate_registry,
            )
            validate_query_analysis_matches_authoritative_result(
                requested_frame=request.temporal_frame,
                requested_analysis=request.query_analysis,
                authoritative_analysis=authoritative_analysis,
                reference_time=request.reference_time,
                scope_key=request.scope_key,
            )
            request = request.model_copy(
                update={
                    "temporal_frame": None,
                    "query_analysis": authoritative_analysis,
                    "predicate_id": (
                        request.predicate_id
                        if request.predicate_id is not None
                        else None
                        if request.purpose == RetrievalPurpose.GRAPH_AUDIT
                        else authoritative_analysis.predicate_id
                    ),
                    "subject_entity_id": request.subject_entity_id or authoritative_analysis.subject_entity_id,
                }
            )
        except StructuredQueryConstraintError as exc:
            frame = QueryTemporalFrame(
                temporal_kind=QueryTemporalKind.AMBIGUOUS,
                resolution_confidence=0.0,
                resolution_confidence_source="caller",
                ambiguity_reasons=[str(exc)],
            )
            return ProductionRetrievalDecision(
                query=request.query,
                temporal_frame=frame,
                query_analysis=authoritative_analysis or request.query_analysis,
                resolution_status="ambiguous",
                abstained=True,
                abstention_reason=f"structured_query_constraint_error:{exc}",
                confidence_status="abstained",
            )
        resolution = resolve_memory_query(request, entity_catalog=catalog)
        frame = resolution.frame
        if request.purpose == RetrievalPurpose.EXECUTION or frame.temporal_kind == QueryTemporalKind.EXECUTION:
            return self._retrieve_execution_decision(
                request=request,
                frame=frame,
                resolution_status=resolution.status,
            )
        states = self._claim_reader(
            view=(
                RetrievalView.ALL_VERSIONS
                if request.include_conflicts or request.purpose == RetrievalPurpose.GRAPH_AUDIT
                else RetrievalView.CURRENT
            ),
            temporal_frame=(
                None
                if request.include_conflicts or request.purpose == RetrievalPurpose.GRAPH_AUDIT
                else frame
            ),
            predicate_id=request.predicate_id,
            subject_entity_id=request.subject_entity_id,
        )
        entity_names_by_id = {
            link.canonical_entity_id: {link.mention_text, link.normalized_name, *link.aliases}
            for link in links
        }
        object_entity_by_claim: dict[str, str] = {}
        for state in states:
            if state.object_link_id is None:
                continue
            object_link = next(
                (
                    link
                    for link in links
                    if link.link_id == state.object_link_id or link.canonical_entity_id == state.object_link_id
                ),
                None,
            )
            if object_link is not None:
                object_entity_by_claim[state.claim_id] = object_link.canonical_entity_id
        return rank_claims(
            request=request,
            frame=frame,
            resolution_status=resolution.status,
            states=states,
            entity_names_by_id=entity_names_by_id,
            object_entity_by_claim=object_entity_by_claim,
        ).model_copy(update={"resolution_status": resolution.status})

    def _retrieve_execution_decision(
        self,
        *,
        request: MemoryQueryRequest,
        frame: QueryTemporalFrame,
        resolution_status: str,
    ) -> ProductionRetrievalDecision:
        snapshot = self._work_state_reader()
        actions = self._action_reader()
        continuation = resolve_continuation(
            snapshot,
            actions,
            requested_scope_key=request.scope_key or frame.scope_key,
            requested_task_id=request.task_id,
            requested_session_id=request.session_id,
            requested_user_id=request.user_id,
            target_entity_ids=frame.resolved_entity_ids,
        )
        selected_action = next(
            (action for action in actions if action.action_id == continuation.action_event_id),
            None,
        )
        selected_ids = [selected_action.action_id.removeprefix("action:")] if selected_action is not None else []
        context_ids = [
            action.action_id.removeprefix("action:")
            for action in actions
            if action.action_id.removeprefix("action:") not in selected_ids
        ]
        execution_state = ExecutionRetrievalState(work_state=snapshot, continuation=continuation)
        abstained = continuation.status != ContinuationResolutionStatus.RESOLVED
        return ProductionRetrievalDecision(
            query=request.query,
            temporal_frame=frame,
            query_analysis=request.query_analysis,
            resolution_status=resolution_status,
            selected_record_ids=selected_ids,
            supporting_record_ids=selected_ids,
            context_record_ids=context_ids,
            abstained=abstained,
            abstention_reason=(
                "ambiguous_active_continuation_branch"
                if continuation.status == ContinuationResolutionStatus.AMBIGUOUS
                else "no_active_continuation_branch"
                if continuation.status == ContinuationResolutionStatus.NONE
                else None
            ),
            execution_state=execution_state,
        )
