"""Deterministic passive work-state detector (v1)."""

from __future__ import annotations

from memorii.core.work_state.models import (
    AgentEventEnvelope,
    WorkStateDetectionAction,
    WorkStateDetectionDecision,
    WorkStateKind,
    WorkStateReasonCode,
    WorkStateRecord,
    WorkStateStatus,
)

_ERROR_TERMS = ("failed", "error", "exception", "traceback", "test failed", "build failed")
_TASK_TERMS = ("implement", "fix", "update", "add", "merge", "review pr", "run benchmark", "write tests")
_DECISION_TERMS = ("decide", "choose", "compare options", "should we", "recommendation", "tradeoff")
_RESEARCH_TERMS = ("literature search", "paper", "analyze", "research", "learn about")


class WorkStateDetector:
    """Conservative heuristic detector for passive work-state updates."""

    def detect(
        self,
        *,
        event: AgentEventEnvelope,
        active_states: list[WorkStateRecord],
    ) -> WorkStateDetectionDecision:
        content = f"{event.content} {event.assistant_content or ''}".strip().lower()
        metadata = " ".join(f"{key}:{value}" for key, value in sorted(event.metadata.items())).lower()
        text = f"{content} {metadata}".strip()

        kind = WorkStateKind.NONE
        confidence = 0.15
        reasons = [WorkStateReasonCode.GENERIC_CHAT]

        if any(term in text for term in _ERROR_TERMS):
            kind = WorkStateKind.INVESTIGATION
            confidence = 0.75
            reasons = [WorkStateReasonCode.TOOL_FAILURE_OR_ERROR]
        elif any(term in text for term in _TASK_TERMS):
            kind = WorkStateKind.TASK_EXECUTION
            confidence = 0.65
            reasons = [WorkStateReasonCode.EXPLICIT_TASK_LANGUAGE]
        elif any(term in text for term in _DECISION_TERMS):
            kind = WorkStateKind.DECISION
            confidence = 0.65
            reasons = [WorkStateReasonCode.DECISION_LANGUAGE]
        elif any(term in text for term in _RESEARCH_TERMS):
            kind = WorkStateKind.RESEARCH
            confidence = 0.60
            reasons = [WorkStateReasonCode.RESEARCH_LANGUAGE]

        if kind == WorkStateKind.NONE:
            return WorkStateDetectionDecision(
                action=WorkStateDetectionAction.NO_STATE_UPDATE,
                kind=kind,
                confidence=confidence,
                task_id=event.task_id,
                reason_codes=reasons,
                evidence_event_ids=[event.event_id],
            )

        matched = self._find_matching_state(event=event, active_states=active_states, kind=kind)
        action = (
            WorkStateDetectionAction.UPDATE_EXISTING_STATE
            if matched is not None
            else WorkStateDetectionAction.CREATE_CANDIDATE_STATE
        )
        return WorkStateDetectionDecision(
            action=action,
            kind=kind,
            confidence=confidence,
            task_id=event.task_id,
            work_state_id=matched.work_state_id if matched else None,
            title=self._title_for(kind),
            summary=(event.content or "")[:240],
            reason_codes=reasons,
            evidence_event_ids=[event.event_id],
        )

    def _find_matching_state(
        self,
        *,
        event: AgentEventEnvelope,
        active_states: list[WorkStateRecord],
        kind: WorkStateKind,
    ) -> WorkStateRecord | None:
        eligible = [state for state in active_states if state.status in (WorkStateStatus.CANDIDATE, WorkStateStatus.ACTIVE)]
        if event.task_id:
            for state in eligible:
                if state.task_id == event.task_id and state.kind == kind:
                    return state
        for state in eligible:
            if state.session_id == event.session_id and state.kind == kind:
                return state
        return None

    @staticmethod
    def _title_for(kind: WorkStateKind) -> str:
        if kind == WorkStateKind.INVESTIGATION:
            return "Investigation in progress"
        if kind == WorkStateKind.DECISION:
            return "Decision work in progress"
        if kind == WorkStateKind.RESEARCH:
            return "Research in progress"
        return "Task execution in progress"
