"""Lifecycle- and query-temporal filtering for persisted claim state."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from memorii.core.memory_evolution.models import ClaimLifecycleState, ClaimState, MemoryScope, RetrievalView
from memorii.core.memory_evolution.state_repository import EvolutionStateRepository
from memorii.core.memory_evolution.temporal_contracts import (
    QueryTemporalFrame,
    QueryTemporalKind,
    evaluate_temporal_eligibility,
)


class ClaimStateQueryService:
    """Apply retrieval-time lifecycle, scope, entity, and temporal constraints."""

    def __init__(
        self,
        *,
        repository: EvolutionStateRepository,
        now_provider: Callable[[], datetime],
    ) -> None:
        self._repository = repository
        self._now_provider = now_provider

    def retrieve(
        self,
        *,
        view: RetrievalView = RetrievalView.CURRENT,
        valid_at: datetime | None = None,
        predicate_id: str | None = None,
        subject_entity_id: str | None = None,
        temporal_frame: QueryTemporalFrame | None = None,
        request_scope: MemoryScope | None = None,
    ) -> list[ClaimState]:
        frame = self._resolved_frame(temporal_frame=temporal_frame, view=view)
        states = self._repository.list_claim_states()
        if predicate_id is not None:
            states = [state for state in states if state.claim_key.predicate_id == predicate_id]
        if subject_entity_id is not None:
            states = [state for state in states if state.claim_key.subject_entity_id == subject_entity_id]
        if request_scope is not None:
            states = [state for state in states if request_scope.can_read(state.claim_key.scope)]
        elif frame is not None and frame.scope_key is not None:
            states = [state for state in states if state.claim_key.scope_key in {frame.scope_key, "global"}]
        if frame is not None and frame.resolved_entity_ids:
            resolved_entity_ids = set(frame.resolved_entity_ids)
            links_by_id = {
                link.link_id: link.canonical_entity_id for link in self._repository.list_entity_links()
            }
            states = [
                state
                for state in states
                if state.claim_key.subject_entity_id in resolved_entity_ids
                or links_by_id.get(state.object_link_id or "", state.object_link_id) in resolved_entity_ids
            ]
        if frame is not None:
            framed = self._filter_by_frame(states, frame)
            if framed is not None:
                return framed
        return self._filter_by_view(states, view=view, valid_at=valid_at)

    def _resolved_frame(
        self,
        *,
        temporal_frame: QueryTemporalFrame | None,
        view: RetrievalView,
    ) -> QueryTemporalFrame | None:
        frame = temporal_frame
        if frame is None and view == RetrievalView.CURRENT:
            frame = QueryTemporalFrame(
                temporal_kind=QueryTemporalKind.CURRENT,
                evaluation_time=self._now_provider(),
            )
        if (
            frame is not None
            and frame.temporal_kind
            in {QueryTemporalKind.CURRENT, QueryTemporalKind.EXECUTION, QueryTemporalKind.BELIEF}
            and frame.evaluation_time is None
        ):
            return frame.model_copy(update={"evaluation_time": self._now_provider()})
        return frame

    @staticmethod
    def _filter_by_frame(
        states: list[ClaimState],
        frame: QueryTemporalFrame,
    ) -> list[ClaimState] | None:
        if frame.temporal_kind in {
            QueryTemporalKind.CURRENT,
            QueryTemporalKind.EXECUTION,
            QueryTemporalKind.BELIEF,
        }:
            if frame.evaluation_time is None:
                return None
            return [
                state
                for state in states
                if evaluate_temporal_eligibility(
                    lifecycle_state=state.lifecycle_state,
                    valid_from=state.valid_from,
                    valid_to=state.valid_to,
                    temporal_kind=frame.temporal_kind,
                    evaluation_time=frame.evaluation_time,
                ).eligible
            ]
        if frame.temporal_kind in {QueryTemporalKind.HISTORICAL, QueryTemporalKind.INTERVAL}:
            return [
                state
                for state in states
                if evaluate_temporal_eligibility(
                    lifecycle_state=state.lifecycle_state,
                    valid_from=state.valid_from,
                    valid_to=state.valid_to,
                    temporal_kind=frame.temporal_kind,
                    requested_from=frame.valid_from,
                    requested_to=frame.valid_to,
                ).eligible
            ]
        if frame.temporal_kind == QueryTemporalKind.AMBIGUOUS:
            return []
        return None

    def _filter_by_view(
        self,
        states: list[ClaimState],
        *,
        view: RetrievalView,
        valid_at: datetime | None,
    ) -> list[ClaimState]:
        if view == RetrievalView.CURRENT:
            evaluation_time = self._now_provider()
            return [
                state
                for state in states
                if evaluate_temporal_eligibility(
                    lifecycle_state=state.lifecycle_state,
                    valid_from=state.valid_from,
                    valid_to=state.valid_to,
                    temporal_kind=QueryTemporalKind.CURRENT,
                    evaluation_time=evaluation_time,
                ).eligible
            ]
        if view == RetrievalView.HISTORICAL_AT:
            if valid_at is None:
                raise ValueError("valid_at is required for historical_at retrieval")
            return [
                state
                for state in states
                if evaluate_temporal_eligibility(
                    lifecycle_state=state.lifecycle_state,
                    valid_from=state.valid_from,
                    valid_to=state.valid_to,
                    temporal_kind=QueryTemporalKind.CURRENT,
                    evaluation_time=valid_at,
                ).eligible
            ]
        if view == RetrievalView.CONFLICTS:
            return [
                state
                for state in states
                if state.conflict_with_claim_ids or state.lifecycle_state == ClaimLifecycleState.INVALIDATED
            ]
        if view == RetrievalView.EVIDENCE_ONLY:
            return [state for state in states if state.evidence_spans]
        return states
