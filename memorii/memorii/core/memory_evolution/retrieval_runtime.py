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
    action_event_from_extracted,
    reduce_work_states,
    resolve_continuation,
)
from memorii.core.memory_evolution.graph_constraint_resolution import resolve_graph_constraints
from memorii.core.memory_evolution.models import (
    ClaimState,
    EntityLinkState,
    ExtractedAction,
    MemoryScope,
    RecordLifecycleState,
    RetrievalView,
)
from memorii.core.memory_evolution.predicates import PredicateRegistry
from memorii.core.memory_evolution.query_analysis import (
    QueryAnalyzer,
    StructuredQueryConstraintError,
    validate_query_analysis_constraints,
)
from memorii.core.memory_evolution.query_graph import (
    GraphPatternResolutionStatus,
    GraphResolutionMethod,
)
from memorii.core.memory_evolution.retrieval import rank_claims, reconcile_memory_query
from memorii.core.memory_evolution.retrieval_contracts import (
    MemoryQueryInput,
    ProductionRetrievalDecision,
    ResolvedMemoryQuery,
    RetrievalPurpose,
    ScopedExecutionView,
    SemanticFrameStatus,
)
from memorii.core.memory_evolution.temporal_contracts import (
    QueryResolutionConfidenceSource,
    QueryTemporalFrame,
    QueryTemporalKind,
    TemporalAnchorCatalog,
    TemporalEntityCandidate,
)


class MemoryEvolutionRetrievalRuntime:
    """Read-only retrieval runtime composed around an evolution store."""

    def __init__(
        self,
        *,
        claim_reader: Callable[..., list[ClaimState]],
        entity_link_reader: Callable[[], list[EntityLinkState]],
        action_reader: Callable[[], list[ExtractedAction]],
        query_analyzer: QueryAnalyzer,
        temporal_anchor_catalog: TemporalAnchorCatalog,
        now_provider: Callable[[], datetime],
        predicate_registry: PredicateRegistry | None = None,
    ) -> None:
        self._claim_reader = claim_reader
        self._entity_link_reader = entity_link_reader
        self._action_reader = action_reader
        self._query_analyzer = query_analyzer
        self._temporal_anchor_catalog = temporal_anchor_catalog
        self._now_provider = now_provider
        self._predicate_registry = predicate_registry or PredicateRegistry()

    def retrieve(self, request: MemoryQueryInput) -> ProductionRetrievalDecision:
        if request.reference_time is None:
            request = request.model_copy(update={"reference_time": self._now_provider()})
        request_scope = request.scope
        readable_links = [
            link
            for link in self._entity_link_reader()
            if link.lifecycle_state.value != "invalidated" and request_scope.can_read(link.scope)
        ]
        most_specific_scope_by_identity: dict[tuple[str, str], int] = {}
        for link in readable_links:
            identity = (link.normalized_name, link.canonical_entity_id)
            most_specific_scope_by_identity[identity] = max(
                link.scope.specificity,
                most_specific_scope_by_identity.get(identity, -1),
            )
        links = [
            link
            for link in readable_links
            if link.scope.specificity
            == most_specific_scope_by_identity[(link.normalized_name, link.canonical_entity_id)]
        ]
        catalog = [
            TemporalEntityCandidate(
                entity_id=link.canonical_entity_id,
                names=sorted({link.mention_text, link.normalized_name, *link.aliases}),
                entity_type=link.entity_type.value,
                scope=link.scope,
                lifecycle_state=RecordLifecycleState(link.lifecycle_state.value),
                lineage_parent_entity_id=link.lineage_parent_entity_id,
                valid_from=link.valid_from,
                valid_to=link.valid_to,
            )
            for link in links
            if link.aliases or link.mention_text
        ]
        visible_anchor_catalog = TemporalAnchorCatalog(
            anchors=[anchor for anchor in self._temporal_anchor_catalog.anchors if request_scope.can_read(anchor.scope)]
        )
        analysis = None
        try:
            analysis = self._query_analyzer.analyze(
                query=request.query,
                language=request.query_language,
                reference_time=request.reference_time,
                request_scope=request_scope,
                entity_candidates=catalog,
                anchor_catalog=visible_anchor_catalog,
            )
            analysis = validate_query_analysis_constraints(
                analysis,
                entity_candidates=catalog,
                anchor_catalog=visible_anchor_catalog,
                request_scope=request_scope,
                predicate_registry=self._predicate_registry,
            )
            if analysis.temporal_frame is None:
                raise StructuredQueryConstraintError("query analysis omitted a temporal frame")
            request_payload = request.model_dump(mode="python")
            resolved_request = ResolvedMemoryQuery(
                **request_payload,
                query_analysis=analysis,
                temporal_frame=analysis.temporal_frame,
                predicate_id=(None if request.purpose == RetrievalPurpose.GRAPH_AUDIT else analysis.predicate_id),
                subject_entity_id=analysis.subject_entity_id,
            )
        except StructuredQueryConstraintError as exc:
            frame = QueryTemporalFrame(
                temporal_kind=QueryTemporalKind.AMBIGUOUS,
                resolution_confidence=0.0,
                resolution_confidence_source=QueryResolutionConfidenceSource.CALLER,
                ambiguity_reasons=[str(exc)],
            )
            return ProductionRetrievalDecision(
                query=request.query,
                semantic_frame_status=(
                    SemanticFrameStatus.UNSUPPORTED
                    if analysis is not None
                    and (
                        analysis.failure_code is not None or analysis.analysis_source in {"language_guard", "provider"}
                    )
                    else SemanticFrameStatus.AMBIGUOUS
                ),
                temporal_frame=frame,
                query_analysis=analysis,
                resolution_status="ambiguous",
                abstained=True,
                abstention_reason=f"structured_query_constraint_error:{exc}",
                confidence_status="abstained",
            )
        frame = resolved_request.temporal_frame
        if resolved_request.purpose == RetrievalPurpose.EXECUTION or frame.temporal_kind == QueryTemporalKind.EXECUTION:
            resolution = reconcile_memory_query(resolved_request)
            return self._retrieve_execution_decision(
                request=resolved_request,
                frame=resolution.frame,
                resolution_status=resolution.status,
            )
        # Selection and rejection are two outputs of the same lifecycle
        # arbitration. Reading only CURRENT here makes the answer look right
        # while erasing the superseded candidates that explain the decision.
        # The reader still applies predicate and scope prefilters; rank_claims
        # performs entity and temporal relevance checks before disclosure.
        states = self._claim_reader(
            view=RetrievalView.ALL_VERSIONS,
            temporal_frame=None,
            predicate_id=resolved_request.predicate_id,
            subject_entity_id=None,
            request_scope=resolved_request.scope,
        )
        entity_names_by_id = {
            link.canonical_entity_id: {link.mention_text, link.normalized_name, *link.aliases} for link in links
        }
        link_by_id = {link.link_id: link for link in readable_links}
        for state in states:
            subject_link = link_by_id.get(state.subject_link_id or "")
            if subject_link is not None:
                entity_names_by_id.setdefault(state.claim_key.subject_entity_id, set()).update(
                    {subject_link.mention_text, subject_link.normalized_name, *subject_link.aliases}
                )
        object_entity_by_claim: dict[str, str] = {}
        subject_entity_by_claim: dict[str, str] = {}
        for state in states:
            subject_link = link_by_id.get(state.subject_link_id or "")
            subject_entity_by_claim[state.claim_id] = (
                subject_link.canonical_entity_id if subject_link is not None else state.claim_key.subject_entity_id
            )
            if state.object_link_id is None:
                continue
            object_link = next(
                (link for link in readable_links if link.link_id == state.object_link_id),
                None,
            )
            if object_link is not None:
                object_entity_by_claim[state.claim_id] = object_link.canonical_entity_id
        if (
            resolved_request.purpose != RetrievalPurpose.GRAPH_AUDIT
            and frame.temporal_kind != QueryTemporalKind.AMBIGUOUS
        ):
            pattern_resolution = resolve_graph_constraints(
                query=resolved_request.query,
                analysis=analysis,
                temporal_frame=frame,
                states=states,
                entity_links=readable_links,
            )
            if pattern_resolution.status == GraphPatternResolutionStatus.RESOLVED:
                subject_entity_id = pattern_resolution.subject_entity_id
                if subject_entity_id is None:
                    raise RuntimeError("resolved graph pattern omitted subject entity")
                structured_resolution = (
                    pattern_resolution.resolution_method == GraphResolutionMethod.STRUCTURED_CONSTRAINT
                )
                resolution_source = (
                    QueryResolutionConfidenceSource.GRAPH_CONSTRAINT
                    if structured_resolution
                    else QueryResolutionConfidenceSource(pattern_resolution.resolution_method.value)
                )
                frame = frame.model_copy(
                    update={
                        "resolved_entity_ids": [subject_entity_id],
                        "resolution_confidence": 1.0 if structured_resolution else 0.65,
                        "resolution_confidence_source": resolution_source,
                        "resolution_confidence_is_calibrated": False,
                        "ambiguity_reasons": [],
                    }
                )
                analysis = analysis.model_copy(
                    update={
                        "temporal_frame": frame,
                        "subject_entity_id": subject_entity_id,
                        "graph_patterns": [pattern_resolution.pattern],
                        "confidence_source": resolution_source,
                        "confidence_is_calibrated": False,
                    }
                )
            else:
                frame = frame.model_copy(
                    update={
                        "resolution_confidence": 0.0,
                        "resolution_confidence_source": QueryResolutionConfidenceSource.GRAPH_CONSTRAINT,
                        "ambiguity_reasons": list(
                            dict.fromkeys(
                                [
                                    *frame.ambiguity_reasons,
                                    *pattern_resolution.ambiguity_reasons,
                                ]
                            )
                        ),
                    }
                )
            resolved_request = resolved_request.model_copy(
                update={
                    "query_analysis": analysis,
                    "temporal_frame": frame,
                    "subject_entity_id": pattern_resolution.subject_entity_id,
                    "graph_pattern_resolution": pattern_resolution,
                }
            )
        resolution = reconcile_memory_query(resolved_request)
        frame = resolution.frame
        return rank_claims(
            request=resolved_request,
            frame=frame,
            resolution_status=resolution.status,
            states=states,
            entity_names_by_id=entity_names_by_id,
            subject_entity_by_claim=subject_entity_by_claim,
            object_entity_by_claim=object_entity_by_claim,
        ).model_copy(update={"resolution_status": resolution.status})

    def _retrieve_execution_decision(
        self,
        *,
        request: ResolvedMemoryQuery,
        frame: QueryTemporalFrame,
        resolution_status: str,
    ) -> ProductionRetrievalDecision:
        actions = [action for action in self._action_reader() if request.scope.can_read(_scope_for_action(action))]
        snapshot = reduce_work_states(action_event_from_extracted(action) for action in actions)
        continuation = resolve_continuation(
            snapshot,
            actions,
            requested_scope_key=request.scope_key or frame.scope_key,
            requested_task_id=request.task_id,
            requested_session_id=request.session_id,
            requested_user_id=request.user_id,
            # A lexical fallback match identifies retrieval context, not an
            # explicit work-branch constraint. Only a structured/caller
            # analysis may narrow continuation by entity ID; otherwise a
            # project-name match can incorrectly suppress its active branch.
            target_entity_ids=(
                frame.resolved_entity_ids if request.query_analysis.analysis_source != "heuristic" else []
            ),
        )
        selected_action = next(
            (action for action in actions if action.action_id == continuation.action_event_id),
            None,
        )
        selected_ids = [selected_action.action_id.removeprefix("action:")] if selected_action is not None else []
        relevant_branch_ids = {
            *continuation.candidate_branch_ids,
            *snapshot.suppressed_branch_ids,
        }
        context_ids = [
            action.action_id.removeprefix("action:")
            for action in actions
            if action.action_id.removeprefix("action:") not in selected_ids
            and relevant_branch_ids.intersection(action.target_entity_ids)
        ]
        execution_state = ScopedExecutionView(
            work_state=snapshot,
            continuation=continuation,
            readable_action_event_ids=[action.action_id for action in actions],
        )
        abstained = continuation.status != ContinuationResolutionStatus.RESOLVED
        return ProductionRetrievalDecision(
            query=request.query,
            semantic_frame_status=SemanticFrameStatus.MATCHED,
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


def _scope_for_action(action: ExtractedAction) -> MemoryScope:
    return action.scope
