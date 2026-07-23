"""Projection of provider work-state events into episodic memory candidates."""

from __future__ import annotations

from datetime import UTC, datetime

from memorii.core.evidence_quality import EvidenceQualitySignals
from memorii.core.llm_decision.trace import LLMDecisionTraceStore
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.promotion.assessment import PromotionAssessmentContext, PromotionCandidateType
from memorii.core.promotion.provider import PromotionAssessmentProvider, PromotionAssessmentProviderError
from memorii.core.provider.models import ProviderEvent
from memorii.core.work_state.models import (
    AgentEventEnvelope,
    WorkStateEvent,
    WorkStateKind,
    WorkStateRecord,
)
from memorii.core.work_state.service import WorkStateService
from memorii.domain.enums import CommitStatus, MemoryDomain


class WorkStateMemoryProjector:
    """Own work-state ingestion and promotion-aware candidate projection."""

    def __init__(
        self,
        *,
        memory_plane: MemoryPlaneService,
        work_state_service: WorkStateService | None,
        promotion_provider: PromotionAssessmentProvider | None,
        trace_store: LLMDecisionTraceStore | None,
        emit_candidates: bool,
    ) -> None:
        self._memory_plane = memory_plane
        self._work_state_service = work_state_service
        self._promotion_provider = promotion_provider
        self._trace_store = trace_store
        self._emit_candidates = emit_candidates

    def ingest_provider_event(self, event: ProviderEvent) -> None:
        if self._work_state_service is None:
            return
        self._work_state_service.ingest_event(_agent_event_from_provider_event(event))

    def stage_event_candidate(
        self,
        *,
        state: WorkStateRecord,
        event: WorkStateEvent,
        event_type: str,
        outcome: str | None,
        task_id: str | None,
        session_id: str | None,
        solver_run_id: str | None,
        execution_node_id: str | None,
    ) -> dict[str, object]:
        if not self._emit_candidates:
            return _candidate_result(created=False)
        try:
            memory_id = f"cand:episodic:work_state_event:{event.event_id}"
            scoped_task_id = task_id or state.task_id
            scoped_session_id = session_id or state.session_id
            event_solver_run_id, event_execution_node_id = self._bound_execution_scope(
                state=state,
                solver_run_id=solver_run_id,
                execution_node_id=execution_node_id,
            )
            memory_text = _work_state_event_memory_text(
                state=state,
                event=event,
                event_type=event_type,
                outcome=outcome,
            )
            record = CanonicalMemoryRecord(
                memory_id=memory_id,
                domain=MemoryDomain.EPISODIC,
                text=memory_text,
                content={
                    "text": memory_text,
                    "work_state_id": state.work_state_id,
                    "work_state_event_id": event.event_id,
                    "event_type": event_type,
                    "task_id": scoped_task_id,
                    "session_id": scoped_session_id,
                    "solver_run_id": event_solver_run_id,
                    "execution_node_id": event_execution_node_id,
                    "outcome": outcome,
                    "work_state_status": state.status.value,
                },
                status=CommitStatus.CANDIDATE,
                source_kind="provider:work_state_event",
                timestamp=event.created_at,
                session_id=scoped_session_id,
                task_id=scoped_task_id,
                execution_node_id=event_execution_node_id,
                solver_run_id=event_solver_run_id,
                user_id=state.user_id,
                is_raw_event=False,
                promotion_state="staged",
            )
            self._memory_plane.stage_record(record)
            promotion_result = self._apply_promotion_decision(
                work_state=state,
                event=event,
                candidate_record=record,
            )
            self._memory_plane.upsert_record(record)
            result = _candidate_result(created=True, memory_id=memory_id)
            result.update(promotion_result)
            return result
        except OSError as exc:  # storage boundary returns a typed provider payload
            return _candidate_result(created=False, error=str(exc))

    def _bound_execution_scope(
        self,
        *,
        state: WorkStateRecord,
        solver_run_id: str | None,
        execution_node_id: str | None,
    ) -> tuple[str | None, str | None]:
        if self._work_state_service is None:
            return solver_run_id, execution_node_id
        bindings = self._work_state_service.list_bindings(work_state_id=state.work_state_id)
        if not bindings:
            return solver_run_id, execution_node_id
        latest = max(bindings, key=lambda item: item.updated_at)
        return solver_run_id or latest.solver_run_id, execution_node_id or latest.execution_node_id

    def _apply_promotion_decision(
        self,
        *,
        work_state: WorkStateRecord,
        event: WorkStateEvent,
        candidate_record: CanonicalMemoryRecord,
    ) -> dict[str, object]:
        if self._promotion_provider is None:
            return _promotion_result(applied=False)
        try:
            context = _promotion_context(
                work_state=work_state,
                event=event,
                candidate_record=candidate_record,
            )
            decision, trace = self._promotion_provider.decide(context=context)
            if self._trace_store is not None:
                self._trace_store.append_trace(trace)
            payload = {
                "promote": decision.promote,
                "target_plane": decision.target_plane,
                "confidence": decision.confidence,
                "rationale": decision.rationale,
                "merge_with_memory_id": decision.merge_with_memory_id,
                "supersede_memory_id": decision.supersede_memory_id,
                "tags": list(decision.tags),
                "trace_id": decision.trace_id,
            }
            candidate_record.content["promotion_decision"] = payload
            candidate_record.content["promotion_trace_id"] = trace.trace_id
            return _promotion_result(applied=True, trace_id=trace.trace_id, decision=payload)
        except PromotionAssessmentProviderError as exc:
            candidate_record.content["promotion_decision_error"] = str(exc)
            return _promotion_result(applied=False, error=str(exc))


def _agent_event_from_provider_event(event: ProviderEvent) -> AgentEventEnvelope:
    return AgentEventEnvelope(
        event_id=event.event_id,
        provider="provider_memory_service",
        operation=event.operation.value,
        session_id=event.session_id,
        user_id=event.user_id,
        task_id=event.task_id,
        content=event.content or "",
        metadata={
            "role": event.role,
            "target": event.target,
            "action": event.action,
        },
        timestamp=event.timestamp or datetime.now(UTC),
    )


def _promotion_context(
    *,
    work_state: WorkStateRecord,
    event: WorkStateEvent,
    candidate_record: CanonicalMemoryRecord,
) -> PromotionAssessmentContext:
    metadata = dict(candidate_record.content)
    repeated_value = metadata.get("repeated_across_episodes", 0)
    repeated_across_episodes = int(repeated_value) if isinstance(repeated_value, (int, float, str)) else 0
    explicit_user_memory_request = bool(metadata.get("explicit_user_memory_request", False))
    return PromotionAssessmentContext(
        candidate_id=candidate_record.memory_id,
        candidate_type=_promotion_candidate_type(
            event=event,
            metadata=metadata,
            explicit_user_memory_request=explicit_user_memory_request,
        ),
        content=candidate_record.text,
        source_ids=list(event.evidence_ids),
        related_memory_ids=[],
        repeated_across_episodes=repeated_across_episodes,
        explicit_user_memory_request=explicit_user_memory_request,
        created_from=_promotion_created_from(work_state=work_state, metadata=metadata),
        evidence_quality=EvidenceQualitySignals.model_validate(metadata.get("evidence_quality", {})),
        metadata=metadata,
    )


def _promotion_candidate_type(
    *,
    event: WorkStateEvent,
    metadata: dict[str, object],
    explicit_user_memory_request: bool,
) -> PromotionCandidateType:
    if explicit_user_memory_request:
        return PromotionCandidateType.USER_MEMORY
    if bool(metadata.get("repeated_across_episodes", False)):
        if metadata.get("semantic_target") == PromotionCandidateType.PROJECT_FACT.value:
            return PromotionCandidateType.PROJECT_FACT
        return PromotionCandidateType.SEMANTIC
    return PromotionCandidateType.EPISODIC


def _promotion_created_from(*, work_state: WorkStateRecord, metadata: dict[str, object]) -> str:
    event_type = str(metadata.get("event_type", "progress"))
    outcome = str(metadata.get("outcome") or "")
    if event_type == "progress":
        return "observation"
    if event_type == "decision_finalized":
        return "decision_finalized"
    if outcome == "blocked" and work_state.kind == WorkStateKind.INVESTIGATION:
        return "investigation_conclusion"
    return "task_outcome"


def _work_state_event_memory_text(
    *,
    state: WorkStateRecord,
    event: WorkStateEvent,
    event_type: str,
    outcome: str | None,
) -> str:
    if event_type == "progress":
        return "\n".join(
            [
                "Work state progress:",
                f"Title: {state.title}",
                f"Kind: {state.kind.value}",
                f"Status: {state.status.value}",
                f"Content: {event.content}",
                f"Evidence: {event.evidence_ids}",
            ]
        )
    return "\n".join(
        [
            "Work state outcome:",
            f"Title: {state.title}",
            f"Outcome status: {outcome or 'unknown'}",
            f"Final status: {state.status.value}",
            f"Content: {event.content}",
        ]
    )


def _candidate_result(
    *,
    created: bool,
    memory_id: str | None = None,
    error: str | None = None,
    **promotion: object,
) -> dict[str, object]:
    result: dict[str, object] = {
        "memory_candidate_created": created,
        "promotion_decision_applied": False,
        "promotion_trace_id": None,
        "promotion_decision": None,
        "promotion_decision_error": None,
    }
    if memory_id is not None:
        result["memory_candidate_id"] = memory_id
    if error is not None:
        result["memory_candidate_error"] = error
    result.update(promotion)
    return result


def _promotion_result(
    *,
    applied: bool,
    trace_id: str | None = None,
    decision: dict[str, object] | None = None,
    error: str | None = None,
) -> dict[str, object]:
    return {
        "promotion_decision_applied": applied,
        "promotion_trace_id": trace_id,
        "promotion_decision": decision,
        "promotion_decision_error": error,
    }
