"""Typed provider-tool dispatch and work-state orchestration."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from memorii.core.decision_state.models import DecisionState, DecisionStatus
from memorii.core.decision_state.service import DecisionStateService
from memorii.core.decision_state.summary import DecisionStateSummary, summarize_decision_state
from memorii.core.next_step import NextStepEngine, NextStepRequest
from memorii.core.provider.tools import (
    DecisionAddCriterionInput,
    DecisionAddEvidenceInput,
    DecisionAddOptionInput,
    DecisionFinalizeInput,
    DecisionSetRecommendationInput,
    GetNextStepInput,
    GetStateSummaryInput,
    OpenOrResumeWorkInput,
    ProviderToolCallResult,
    RecordOutcomeInput,
    RecordProgressInput,
)
from memorii.core.provider.work_state_projection import WorkStateMemoryProjector
from memorii.core.recall import summarize_work_states
from memorii.core.work_state.models import WorkStateEvent, WorkStateKind, WorkStateRecord
from memorii.core.work_state.selector import WorkStateSelector
from memorii.core.work_state.service import WorkStateService

InputT = TypeVar("InputT", bound=BaseModel)
ToolHandler = Callable[[dict[str, object]], ProviderToolCallResult]


class ProviderToolDispatcher:
    """Validate and execute provider tools against runtime-owned services."""

    def __init__(
        self,
        *,
        decision_state_service: DecisionStateService | None,
        work_state_service: WorkStateService | None,
        work_state_selector: WorkStateSelector,
        next_step_engine: NextStepEngine,
        work_state_memory_projector: WorkStateMemoryProjector,
    ) -> None:
        self._decision_state_service = decision_state_service
        self._work_state_service = work_state_service
        self._work_state_selector = work_state_selector
        self._next_step_engine = next_step_engine
        self._work_state_memory_projector = work_state_memory_projector
        self._handlers: dict[str, ToolHandler] = {
            "memorii_decision_add_option": self._add_decision_option,
            "memorii_decision_add_criterion": self._add_decision_criterion,
            "memorii_decision_add_evidence": self._add_decision_evidence,
            "memorii_decision_set_recommendation": self._set_decision_recommendation,
            "memorii_decision_finalize": self._finalize_decision,
            "memorii_get_state_summary": self._get_state_summary,
            "memorii_get_next_step": self._get_next_step,
            "memorii_open_or_resume_work": self._open_or_resume_work,
            "memorii_record_progress": self._record_progress,
            "memorii_record_outcome": self._record_outcome,
        }

    def handle(self, tool_name: str, arguments: dict[str, object]) -> ProviderToolCallResult:
        handler = self._handlers.get(tool_name)
        if handler is None:
            return ProviderToolCallResult(
                tool_name=tool_name,
                ok=False,
                error=f"Unknown provider tool: {tool_name}",
            )
        return handler(arguments)

    def list_events_by_work_state_id(
        self,
        work_states: list[WorkStateRecord],
    ) -> dict[str, list[WorkStateEvent]]:
        if self._work_state_service is None:
            return {}
        return {
            state.work_state_id: self._work_state_service.list_work_state_events(state.work_state_id)
            for state in work_states
        }

    def decision_summary_by_work_state_id(
        self,
        work_states: list[WorkStateRecord],
    ) -> dict[str, DecisionStateSummary]:
        if self._decision_state_service is None:
            return {}
        summaries: dict[str, DecisionStateSummary] = {}
        for state in work_states:
            if state.kind != WorkStateKind.DECISION:
                continue
            decisions = self._decision_state_service.list_decisions(
                work_state_id=state.work_state_id,
                statuses=[DecisionStatus.OPEN, DecisionStatus.DECIDED],
            )
            selected = next((item for item in decisions if item.status == DecisionStatus.OPEN), None)
            if selected is None:
                selected = next((item for item in decisions if item.status == DecisionStatus.DECIDED), None)
            if selected is not None:
                summaries[state.work_state_id] = summarize_decision_state(selected)
        return summaries

    def _add_decision_option(self, arguments: dict[str, object]) -> ProviderToolCallResult:
        tool_name = "memorii_decision_add_option"
        tool_input = _parse_input(tool_name, DecisionAddOptionInput, arguments)
        if isinstance(tool_input, ProviderToolCallResult):
            return tool_input
        service = self._decision_state_service
        if service is None:
            return _service_unavailable(tool_name, "decision_state_service_not_configured")
        state = service.add_option(
            decision_id=tool_input.decision_state_id,
            option_id=tool_input.option_id,
            label=tool_input.label,
            description=tool_input.description,
        )
        return _decision_result(tool_name, state)

    def _add_decision_criterion(self, arguments: dict[str, object]) -> ProviderToolCallResult:
        tool_name = "memorii_decision_add_criterion"
        tool_input = _parse_input(tool_name, DecisionAddCriterionInput, arguments)
        if isinstance(tool_input, ProviderToolCallResult):
            return tool_input
        service = self._decision_state_service
        if service is None:
            return _service_unavailable(tool_name, "decision_state_service_not_configured")
        state = service.add_criterion(
            decision_id=tool_input.decision_state_id,
            criterion_id=tool_input.criterion_id,
            label=tool_input.label,
            weight=tool_input.weight,
        )
        return _decision_result(tool_name, state)

    def _add_decision_evidence(self, arguments: dict[str, object]) -> ProviderToolCallResult:
        tool_name = "memorii_decision_add_evidence"
        tool_input = _parse_input(tool_name, DecisionAddEvidenceInput, arguments)
        if isinstance(tool_input, ProviderToolCallResult):
            return tool_input
        service = self._decision_state_service
        if service is None:
            return _service_unavailable(tool_name, "decision_state_service_not_configured")
        state = service.add_evidence(
            decision_id=tool_input.decision_state_id,
            evidence_id=tool_input.evidence_id,
            content=tool_input.content,
            polarity=tool_input.polarity,
            option_id=tool_input.option_id,
            source_ids=tool_input.source_ids,
        )
        return _decision_result(tool_name, state)

    def _set_decision_recommendation(self, arguments: dict[str, object]) -> ProviderToolCallResult:
        tool_name = "memorii_decision_set_recommendation"
        tool_input = _parse_input(tool_name, DecisionSetRecommendationInput, arguments)
        if isinstance(tool_input, ProviderToolCallResult):
            return tool_input
        service = self._decision_state_service
        if service is None:
            return _service_unavailable(tool_name, "decision_state_service_not_configured")
        state = service.update_recommendation(
            decision_id=tool_input.decision_state_id,
            recommendation=tool_input.recommendation,
        )
        return _decision_result(tool_name, state)

    def _finalize_decision(self, arguments: dict[str, object]) -> ProviderToolCallResult:
        tool_name = "memorii_decision_finalize"
        tool_input = _parse_input(tool_name, DecisionFinalizeInput, arguments)
        if isinstance(tool_input, ProviderToolCallResult):
            return tool_input
        service = self._decision_state_service
        if service is None:
            return _service_unavailable(tool_name, "decision_state_service_not_configured")
        decision_state = service.record_final_decision(
            decision_id=tool_input.decision_state_id,
            final_decision=tool_input.final_decision,
        )
        if decision_state is None:
            return _service_unavailable(tool_name, "decision_state_not_found")
        outcome_result, outcome_state, outcome_event = self._record_decision_work_state_outcome(decision_state)
        candidate_result: dict[str, object] = {}
        if outcome_state is not None and outcome_event is not None:
            candidate_result = self._work_state_memory_projector.stage_event_candidate(
                state=outcome_state,
                event=outcome_event,
                event_type="decision_finalized",
                outcome="completed",
                task_id=decision_state.task_id,
                session_id=decision_state.session_id,
                solver_run_id=None,
                execution_node_id=None,
            )
        return ProviderToolCallResult(
            tool_name=tool_name,
            ok=True,
            result={
                "decision_state": decision_state.model_dump(mode="json"),
                **outcome_result,
                **candidate_result,
            },
        )

    def _get_state_summary(self, arguments: dict[str, object]) -> ProviderToolCallResult:
        tool_name = "memorii_get_state_summary"
        tool_input = _parse_input(tool_name, GetStateSummaryInput, arguments)
        if isinstance(tool_input, ProviderToolCallResult):
            return tool_input
        selected = self._work_state_selector.select_recall_work_states(
            session_id=tool_input.session_id,
            task_id=tool_input.task_id,
            user_id=tool_input.user_id,
        )
        summaries = summarize_work_states(
            selected,
            events_by_state_id=self.list_events_by_work_state_id(selected),
            decision_summary_by_state_id=self.decision_summary_by_work_state_id(selected),
        )
        return ProviderToolCallResult(
            tool_name=tool_name,
            ok=True,
            result={
                "work_states": [summary.model_dump(mode="json") for summary in summaries],
                "state_count": len(summaries),
                "scope": {
                    "task_id": tool_input.task_id,
                    "session_id": tool_input.session_id,
                    "user_id": tool_input.user_id,
                },
            },
        )

    def _get_next_step(self, arguments: dict[str, object]) -> ProviderToolCallResult:
        tool_name = "memorii_get_next_step"
        tool_input = _parse_input(tool_name, GetNextStepInput, arguments)
        if isinstance(tool_input, ProviderToolCallResult):
            return tool_input
        result = self._next_step_engine.get_next_step(
            NextStepRequest(
                query=tool_input.query,
                session_id=tool_input.session_id,
                task_id=tool_input.task_id,
                user_id=tool_input.user_id,
                solver_run_id=tool_input.solver_run_id,
            )
        )
        return ProviderToolCallResult(tool_name=tool_name, ok=True, result=result.model_dump(mode="json"))

    def _open_or_resume_work(self, arguments: dict[str, object]) -> ProviderToolCallResult:
        tool_name = "memorii_open_or_resume_work"
        tool_input = _parse_input(tool_name, OpenOrResumeWorkInput, arguments)
        if isinstance(tool_input, ProviderToolCallResult):
            return tool_input
        service = self._work_state_service
        if service is None:
            return _service_unavailable(tool_name, "work_state_service_not_configured")
        state = service.open_or_resume_work(
            title=tool_input.title,
            summary=tool_input.summary,
            kind=tool_input.kind,
            session_id=tool_input.session_id,
            task_id=tool_input.task_id,
            user_id=tool_input.user_id,
            work_state_id=tool_input.work_state_id,
            execution_node_id=tool_input.execution_node_id,
            solver_run_id=tool_input.solver_run_id,
        )
        decision_state_id = self._ensure_decision_state_for_work(state, tool_input)
        binding = None
        if tool_input.solver_run_id is not None or tool_input.execution_node_id is not None:
            bindings = service.list_bindings(work_state_id=state.work_state_id)
            if bindings:
                latest = max(bindings, key=lambda item: item.updated_at)
                binding = {
                    "binding_id": latest.binding_id,
                    "solver_run_id": latest.solver_run_id,
                    "execution_node_id": latest.execution_node_id,
                }
        return ProviderToolCallResult(
            tool_name=tool_name,
            ok=True,
            result={
                "work_state": {
                    "work_state_id": state.work_state_id,
                    "kind": state.kind.value,
                    "status": state.status.value,
                    "title": state.title,
                    "summary": state.summary,
                    "confidence": state.confidence,
                    "task_id": state.task_id,
                    "session_id": state.session_id,
                    "user_id": state.user_id,
                },
                "binding": binding,
                "decision_state_id": decision_state_id,
            },
        )

    def _record_progress(self, arguments: dict[str, object]) -> ProviderToolCallResult:
        tool_name = "memorii_record_progress"
        tool_input = _parse_input(tool_name, RecordProgressInput, arguments)
        if isinstance(tool_input, ProviderToolCallResult):
            return tool_input
        service = self._work_state_service
        if service is None:
            return _service_unavailable(tool_name, "work_state_service_not_configured")
        state, event = service.record_progress(
            work_state_id=tool_input.work_state_id,
            task_id=tool_input.task_id,
            session_id=tool_input.session_id,
            content=tool_input.content,
            evidence_ids=tool_input.evidence_ids,
            solver_run_id=tool_input.solver_run_id,
            execution_node_id=tool_input.execution_node_id,
        )
        return self._work_event_result(tool_name, tool_input, state, event, event_type="progress")

    def _record_outcome(self, arguments: dict[str, object]) -> ProviderToolCallResult:
        tool_name = "memorii_record_outcome"
        tool_input = _parse_input(tool_name, RecordOutcomeInput, arguments)
        if isinstance(tool_input, ProviderToolCallResult):
            return tool_input
        service = self._work_state_service
        if service is None:
            return _service_unavailable(tool_name, "work_state_service_not_configured")
        state, event = service.record_outcome(
            work_state_id=tool_input.work_state_id,
            task_id=tool_input.task_id,
            session_id=tool_input.session_id,
            outcome=tool_input.outcome.value,
            content=tool_input.content,
            evidence_ids=tool_input.evidence_ids,
            solver_run_id=tool_input.solver_run_id,
            execution_node_id=tool_input.execution_node_id,
        )
        return self._work_event_result(
            tool_name,
            tool_input,
            state,
            event,
            event_type="outcome",
            outcome=tool_input.outcome.value,
        )

    def _work_event_result(
        self,
        tool_name: str,
        tool_input: RecordProgressInput | RecordOutcomeInput,
        state: WorkStateRecord | None,
        event: WorkStateEvent | None,
        *,
        event_type: str,
        outcome: str | None = None,
    ) -> ProviderToolCallResult:
        if state is None or event is None:
            return _service_unavailable(tool_name, "work_state_not_found")
        candidate_result = self._work_state_memory_projector.stage_event_candidate(
            state=state,
            event=event,
            event_type=event_type,
            outcome=outcome,
            task_id=tool_input.task_id,
            session_id=tool_input.session_id,
            solver_run_id=tool_input.solver_run_id,
            execution_node_id=tool_input.execution_node_id,
        )
        return ProviderToolCallResult(
            tool_name=tool_name,
            ok=True,
            result={
                "work_state_id": state.work_state_id,
                "event_id": event.event_id,
                "status": state.status.value,
                "recorded": True,
                **candidate_result,
            },
        )

    def _ensure_decision_state_for_work(
        self,
        work_state: WorkStateRecord,
        tool_input: OpenOrResumeWorkInput,
    ) -> str | None:
        service = self._decision_state_service
        if work_state.kind != WorkStateKind.DECISION or service is None:
            return None
        existing = service.list_decisions(
            work_state_id=work_state.work_state_id,
            statuses=[DecisionStatus.OPEN],
        )
        if existing:
            return existing[0].decision_id
        return service.open_decision(
            question=tool_input.title,
            work_state_id=work_state.work_state_id,
            session_id=tool_input.session_id,
            task_id=tool_input.task_id,
            user_id=tool_input.user_id,
        ).decision_id

    def _record_decision_work_state_outcome(
        self,
        decision_state: DecisionState,
    ) -> tuple[dict[str, object], WorkStateRecord | None, WorkStateEvent | None]:
        service = self._work_state_service
        if service is None or decision_state.work_state_id is None:
            return _unrecorded_outcome(), None, None
        state, event = service.record_outcome(
            work_state_id=decision_state.work_state_id,
            outcome="completed",
            content=f"Decision finalized: {decision_state.final_decision}",
            evidence_ids=_decision_evidence_ids(decision_state),
        )
        if state is None or event is None:
            return {**_unrecorded_outcome(), "work_state_outcome_error": "work_state_not_found"}, None, None
        return (
            {
                "work_state_outcome_recorded": True,
                "work_state_outcome_event": {
                    "work_state_id": state.work_state_id,
                    "event_id": event.event_id,
                    "status": state.status.value,
                },
            },
            state,
            event,
        )


def _parse_input(
    tool_name: str,
    model: type[InputT],
    arguments: dict[str, object],
) -> InputT | ProviderToolCallResult:
    try:
        return model.model_validate(arguments)
    except ValidationError as exc:
        return ProviderToolCallResult(
            tool_name=tool_name,
            ok=False,
            error=f"Validation error for tool '{tool_name}': {exc}",
        )


def _decision_result(tool_name: str, state: DecisionState | None) -> ProviderToolCallResult:
    if state is None:
        return _service_unavailable(tool_name, "decision_state_not_found")
    return ProviderToolCallResult(
        tool_name=tool_name,
        ok=True,
        result={"decision_state": state.model_dump(mode="json")},
    )


def _service_unavailable(tool_name: str, error: str) -> ProviderToolCallResult:
    return ProviderToolCallResult(tool_name=tool_name, ok=False, error=error)


def _unrecorded_outcome() -> dict[str, object]:
    return {
        "work_state_outcome_recorded": False,
        "work_state_outcome_event": None,
    }


def _decision_evidence_ids(decision_state: DecisionState) -> list[str]:
    evidence_ids: list[str] = []
    seen: set[str] = set()
    for evidence in decision_state.evidence:
        for candidate in [evidence.evidence_id, *evidence.source_ids]:
            if candidate not in seen:
                seen.add(candidate)
                evidence_ids.append(candidate)
    return evidence_ids
