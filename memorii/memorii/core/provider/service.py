"""Provider-oriented memory service for Hermes-style hooks."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import ValidationError

from memorii.core.decision_state.models import DecisionState, DecisionStatus
from memorii.core.decision_state.service import DecisionStateService
from memorii.core.decision_state.summary import DecisionStateSummary, summarize_decision_state
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane import MemoryPlaneService
from memorii.core.next_step import NextStepEngine, NextStepRequest
from memorii.core.provider.classifier import build_event_id, make_event
from memorii.core.llm_decision.trace import LLMDecisionTraceStore
from memorii.core.promotion.models import PromotionCandidateType, PromotionContext
from memorii.core.promotion.provider import PromotionDecisionProvider
from memorii.core.promotion.rule_provider import RuleBasedPromotionDecisionProvider
from memorii.core.provider.models import (
    ProviderEvent,
    ProviderOperation,
    ProviderStoredRecord,
    ProviderSyncResult,
    ProviderWriteDecision,
)
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
from memorii.core.recall import RecallStateBundle, WorkStateSummary, summarize_work_states
from memorii.core.solver import SolverFrontierPlanner
from memorii.domain.enums import CommitStatus, MemoryDomain
from memorii.core.work_state.models import (
    AgentEventEnvelope,
    WorkStateEvent,
    WorkStateKind,
    WorkStateRecord,
    WorkStateStatus,
)
from memorii.core.work_state.service import WorkStateService
from memorii.core.work_state.selector import WorkStateSelector
from memorii.stores.base.interfaces import OverlayStore, SolverGraphStore


class ProviderMemoryService:
    """Thin provider adapter over the canonical MemoryPlaneService."""

    _DEFAULT_DECISION_STATE_SERVICE = object()
    _DEFAULT_PROMOTION_DECISION_PROVIDER = object()

    def __init__(
        self,
        memory_plane: MemoryPlaneService | None = None,
        work_state_service: WorkStateService | None = None,
        decision_state_service: DecisionStateService | None | object = _DEFAULT_DECISION_STATE_SERVICE,
        promotion_decision_provider: PromotionDecisionProvider | None | object = _DEFAULT_PROMOTION_DECISION_PROVIDER,
        llm_decision_trace_store: LLMDecisionTraceStore | None = None,
        solver_frontier_planner: SolverFrontierPlanner | None = None,
        solver_store: SolverGraphStore | None = None,
        overlay_store: OverlayStore | None = None,
        emit_work_state_event_candidates: bool = True,
    ) -> None:
        self._memory_plane = memory_plane or MemoryPlaneService()
        self._work_state_service = work_state_service
        self._work_state_selector = WorkStateSelector(work_state_service)
        self._solver_frontier_planner = solver_frontier_planner
        self._solver_store = solver_store
        self._overlay_store = overlay_store
        if decision_state_service is self._DEFAULT_DECISION_STATE_SERVICE:
            self._decision_state_service: DecisionStateService | None = DecisionStateService()
        else:
            self._decision_state_service = decision_state_service
        if promotion_decision_provider is self._DEFAULT_PROMOTION_DECISION_PROVIDER:
            self._promotion_decision_provider: PromotionDecisionProvider | None = RuleBasedPromotionDecisionProvider()
        else:
            self._promotion_decision_provider = promotion_decision_provider
        self._llm_decision_trace_store = llm_decision_trace_store
        self._next_step_engine = NextStepEngine(
            work_state_service=work_state_service,
            decision_state_service=self._decision_state_service,
            solver_frontier_planner=solver_frontier_planner,
            solver_store=solver_store,
            overlay_store=overlay_store,
        )
        self._emit_work_state_event_candidates = emit_work_state_event_candidates
        self._sequence = 0
        self._last_recall_bundle: RecallStateBundle | None = None

    def sync_event(
        self,
        *,
        operation: ProviderOperation,
        content: str,
        role: str | None = None,
        target: str | None = None,
        action: str | None = None,
        session_id: str | None = None,
        task_id: str | None = None,
        user_id: str | None = None,
    ) -> ProviderSyncResult:
        self._sequence += 1
        event = make_event(
            event_id=build_event_id(operation.value, session_id=session_id, task_id=task_id, sequence=self._sequence),
            operation=operation,
            content=content,
            role=role,
            target=target,
            action=action,
            session_id=session_id,
            task_id=task_id,
            user_id=user_id,
            timestamp=datetime.now(UTC),
        )
        result = self._memory_plane.ingest_provider_event(event)
        self._ingest_work_state(self._agent_event_from_provider_event(event=event))
        return result

    def apply_memory_write(
        self,
        *,
        operation: ProviderOperation,
        content: str,
        session_id: str | None,
        task_id: str | None,
        user_id: str | None,
        action: str,
        target: str,
    ) -> ProviderWriteDecision:
        self._sequence += 1
        event = make_event(
            event_id=build_event_id("write", session_id=session_id, task_id=task_id, sequence=self._sequence),
            operation=operation,
            content=content,
            action=action,
            target=target,
            session_id=session_id,
            task_id=task_id,
            user_id=user_id,
        )
        decision = self._memory_plane.apply_provider_memory_write(event=event)
        self._ingest_work_state(self._agent_event_from_provider_event(event=event))
        return decision

    def prefetch(
        self,
        query: str,
        *,
        session_id: str | None = None,
        task_id: str | None = None,
        user_id: str | None = None,
        top_k: int = 6,
    ) -> str:
        memory_context = self._memory_plane.prefetch_provider_context(
            query,
            session_id=session_id,
            task_id=task_id,
            user_id=user_id,
            top_k=top_k,
        )
        selected_work_states = self._work_state_selector.select_recall_work_states(
            session_id=session_id,
            task_id=task_id,
            user_id=user_id,
        )
        work_state_summaries = summarize_work_states(
            selected_work_states,
            events_by_state_id=self._list_events_by_work_state_id(selected_work_states),
            decision_summary_by_state_id=self._decision_summary_by_work_state_id(selected_work_states),
        )
        bundle = RecallStateBundle(
            query=query,
            memory_context=memory_context,
            work_states=work_state_summaries,
            trace={
                "work_state_count": len(work_state_summaries),
                "work_state_ids": [state.work_state_id for state in work_state_summaries],
                "included_statuses": sorted({state.status.value for state in work_state_summaries}),
            },
        )
        self._last_recall_bundle = bundle
        if not work_state_summaries:
            return memory_context
        return f"{memory_context}\n\n{self._format_work_state_section(work_state_summaries[:3])}"

    def get_tool_schemas(self) -> list[dict[str, object]]:
        return [
            {
                "name": "memorii_decision_add_option",
                "description": "Add an option to an existing decision state.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "decision_state_id": {"type": "string"},
                        "option_id": {"type": "string"},
                        "label": {"type": "string"},
                        "description": {"type": "string"},
                    },
                    "required": ["decision_state_id", "option_id", "label"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "memorii_decision_add_criterion",
                "description": "Add a weighted criterion to an existing decision state.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "decision_state_id": {"type": "string"},
                        "criterion_id": {"type": "string"},
                        "label": {"type": "string"},
                        "weight": {"type": "number"},
                    },
                    "required": ["decision_state_id", "criterion_id", "label"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "memorii_decision_add_evidence",
                "description": "Add evidence for/against an option (or neutral) in a decision state.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "decision_state_id": {"type": "string"},
                        "evidence_id": {"type": "string"},
                        "content": {"type": "string"},
                        "polarity": {"type": "string", "enum": ["for_option", "against_option", "neutral"]},
                        "option_id": {"type": "string"},
                        "source_ids": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["decision_state_id", "evidence_id", "content", "polarity"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "memorii_decision_set_recommendation",
                "description": "Set or clear the recommendation on a decision state.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "decision_state_id": {"type": "string"},
                        "recommendation": {"type": ["string", "null"]},
                    },
                    "required": ["decision_state_id", "recommendation"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "memorii_decision_finalize",
                "description": "Record the final decision and mark the decision state as decided.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "decision_state_id": {"type": "string"},
                        "final_decision": {"type": "string"},
                    },
                    "required": ["decision_state_id", "final_decision"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "memorii_get_state_summary",
                "description": "Return Memorii's current work-state summary for the given session/task/user scope.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "task_id": {"type": "string"},
                        "user_id": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
            },
            {
                "name": "memorii_get_next_step",
                "description": (
                    "Return a simple next-step recommendation based on current work state. "
                    "This is a placeholder until frontier planning is implemented."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "session_id": {"type": "string"},
                        "task_id": {"type": "string"},
                        "user_id": {"type": "string"},
                        "solver_run_id": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
            },
            {
                "name": "memorii_open_or_resume_work",
                "description": (
                    "Explicitly open or resume structured work state and optionally create solver/execution bindings."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "summary": {"type": "string"},
                        "kind": {
                            "type": "string",
                            "enum": [kind.value for kind in WorkStateKind],
                        },
                        "session_id": {"type": "string"},
                        "task_id": {"type": "string"},
                        "user_id": {"type": "string"},
                        "work_state_id": {"type": "string"},
                        "execution_node_id": {"type": "string"},
                        "solver_run_id": {"type": "string"},
                    },
                    "required": ["title"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "memorii_record_progress",
                "description": "Record meaningful progress against an active work state.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "work_state_id": {"type": "string"},
                        "task_id": {"type": "string"},
                        "session_id": {"type": "string"},
                        "title": {"type": "string"},
                        "content": {"type": "string"},
                        "evidence_ids": {"type": "array", "items": {"type": "string"}},
                        "solver_run_id": {"type": "string"},
                        "execution_node_id": {"type": "string"},
                    },
                    "required": ["content"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "memorii_record_outcome",
                "description": "Record a terminal or semi-terminal outcome for a work state.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "work_state_id": {"type": "string"},
                        "task_id": {"type": "string"},
                        "session_id": {"type": "string"},
                        "outcome": {
                            "type": "string",
                            "enum": ["completed", "blocked", "abandoned", "needs_followup"],
                        },
                        "content": {"type": "string"},
                        "evidence_ids": {"type": "array", "items": {"type": "string"}},
                        "solver_run_id": {"type": "string"},
                        "execution_node_id": {"type": "string"},
                    },
                    "required": ["outcome", "content"],
                    "additionalProperties": False,
                },
            },
        ]

    def handle_tool_call(self, tool_name: str, arguments: dict[str, object]) -> ProviderToolCallResult:
        if tool_name == "memorii_decision_add_option":
            try:
                tool_input = DecisionAddOptionInput.model_validate(arguments)
            except ValidationError as exc:
                return ProviderToolCallResult(
                    tool_name=tool_name,
                    ok=False,
                    error=f"Validation error for tool '{tool_name}': {exc}",
                )
            if self._decision_state_service is None:
                return ProviderToolCallResult(tool_name=tool_name, ok=False, error="decision_state_service_not_configured")
            decision_state = self._decision_state_service.add_option(
                decision_id=tool_input.decision_state_id,
                option_id=tool_input.option_id,
                label=tool_input.label,
                description=tool_input.description,
            )
            if decision_state is None:
                return ProviderToolCallResult(tool_name=tool_name, ok=False, error="decision_state_not_found")
            return ProviderToolCallResult(
                tool_name=tool_name,
                ok=True,
                result={"decision_state": decision_state.model_dump(mode="json")},
            )

        if tool_name == "memorii_decision_add_criterion":
            try:
                tool_input = DecisionAddCriterionInput.model_validate(arguments)
            except ValidationError as exc:
                return ProviderToolCallResult(
                    tool_name=tool_name,
                    ok=False,
                    error=f"Validation error for tool '{tool_name}': {exc}",
                )
            if self._decision_state_service is None:
                return ProviderToolCallResult(tool_name=tool_name, ok=False, error="decision_state_service_not_configured")
            decision_state = self._decision_state_service.add_criterion(
                decision_id=tool_input.decision_state_id,
                criterion_id=tool_input.criterion_id,
                label=tool_input.label,
                weight=tool_input.weight,
            )
            if decision_state is None:
                return ProviderToolCallResult(tool_name=tool_name, ok=False, error="decision_state_not_found")
            return ProviderToolCallResult(
                tool_name=tool_name,
                ok=True,
                result={"decision_state": decision_state.model_dump(mode="json")},
            )

        if tool_name == "memorii_decision_add_evidence":
            try:
                tool_input = DecisionAddEvidenceInput.model_validate(arguments)
            except ValidationError as exc:
                return ProviderToolCallResult(
                    tool_name=tool_name,
                    ok=False,
                    error=f"Validation error for tool '{tool_name}': {exc}",
                )
            if self._decision_state_service is None:
                return ProviderToolCallResult(tool_name=tool_name, ok=False, error="decision_state_service_not_configured")
            decision_state = self._decision_state_service.add_evidence(
                decision_id=tool_input.decision_state_id,
                evidence_id=tool_input.evidence_id,
                content=tool_input.content,
                polarity=tool_input.polarity,
                option_id=tool_input.option_id,
                source_ids=tool_input.source_ids,
            )
            if decision_state is None:
                return ProviderToolCallResult(tool_name=tool_name, ok=False, error="decision_state_not_found")
            return ProviderToolCallResult(
                tool_name=tool_name,
                ok=True,
                result={"decision_state": decision_state.model_dump(mode="json")},
            )

        if tool_name == "memorii_decision_set_recommendation":
            try:
                tool_input = DecisionSetRecommendationInput.model_validate(arguments)
            except ValidationError as exc:
                return ProviderToolCallResult(
                    tool_name=tool_name,
                    ok=False,
                    error=f"Validation error for tool '{tool_name}': {exc}",
                )
            if self._decision_state_service is None:
                return ProviderToolCallResult(tool_name=tool_name, ok=False, error="decision_state_service_not_configured")
            decision_state = self._decision_state_service.update_recommendation(
                decision_id=tool_input.decision_state_id,
                recommendation=tool_input.recommendation,
            )
            if decision_state is None:
                return ProviderToolCallResult(tool_name=tool_name, ok=False, error="decision_state_not_found")
            return ProviderToolCallResult(
                tool_name=tool_name,
                ok=True,
                result={"decision_state": decision_state.model_dump(mode="json")},
            )

        if tool_name == "memorii_decision_finalize":
            try:
                tool_input = DecisionFinalizeInput.model_validate(arguments)
            except ValidationError as exc:
                return ProviderToolCallResult(
                    tool_name=tool_name,
                    ok=False,
                    error=f"Validation error for tool '{tool_name}': {exc}",
                )
            if self._decision_state_service is None:
                return ProviderToolCallResult(tool_name=tool_name, ok=False, error="decision_state_service_not_configured")
            decision_state = self._decision_state_service.record_final_decision(
                decision_id=tool_input.decision_state_id,
                final_decision=tool_input.final_decision,
            )
            if decision_state is None:
                return ProviderToolCallResult(tool_name=tool_name, ok=False, error="decision_state_not_found")
            outcome_result, outcome_state, outcome_event = self._record_decision_work_state_outcome(decision_state=decision_state)
            candidate_result: dict[str, object] = {}
            if outcome_state is not None and outcome_event is not None:
                candidate_result = self._stage_work_state_event_candidate(
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
                    "work_state_outcome_recorded": outcome_result["work_state_outcome_recorded"],
                    "work_state_outcome_event": outcome_result["work_state_outcome_event"],
                    **candidate_result,
                    **(
                        {"work_state_outcome_error": outcome_result["work_state_outcome_error"]}
                        if "work_state_outcome_error" in outcome_result
                        else {}
                    ),
                },
            )

        if tool_name == "memorii_get_state_summary":
            try:
                tool_input = GetStateSummaryInput.model_validate(arguments)
            except ValidationError as exc:
                return ProviderToolCallResult(
                    tool_name=tool_name,
                    ok=False,
                    error=f"Validation error for tool '{tool_name}': {exc}",
                )
            return ProviderToolCallResult(
                tool_name=tool_name,
                ok=True,
                result=self._build_state_summary_result(
                    session_id=tool_input.session_id,
                    task_id=tool_input.task_id,
                    user_id=tool_input.user_id,
                ),
            )

        if tool_name == "memorii_get_next_step":
            try:
                tool_input = GetNextStepInput.model_validate(arguments)
            except ValidationError as exc:
                return ProviderToolCallResult(
                    tool_name=tool_name,
                    ok=False,
                    error=f"Validation error for tool '{tool_name}': {exc}",
                )
            return ProviderToolCallResult(
                tool_name=tool_name,
                ok=True,
                result=self._next_step_engine.get_next_step(
                    NextStepRequest(
                        query=tool_input.query,
                        session_id=tool_input.session_id,
                        task_id=tool_input.task_id,
                        user_id=tool_input.user_id,
                        solver_run_id=tool_input.solver_run_id,
                    )
                ).model_dump(mode="json"),
            )

        if tool_name == "memorii_open_or_resume_work":
            try:
                tool_input = OpenOrResumeWorkInput.model_validate(arguments)
            except ValidationError as exc:
                return ProviderToolCallResult(
                    tool_name=tool_name,
                    ok=False,
                    error=f"Validation error for tool '{tool_name}': {exc}",
                )
            if self._work_state_service is None:
                return ProviderToolCallResult(
                    tool_name=tool_name,
                    ok=False,
                    error="work_state_service_not_configured",
                )
            return ProviderToolCallResult(
                tool_name=tool_name,
                ok=True,
                result=self._build_open_or_resume_work_result(
                    title=tool_input.title,
                    summary=tool_input.summary,
                    kind=tool_input.kind,
                    session_id=tool_input.session_id,
                    task_id=tool_input.task_id,
                    user_id=tool_input.user_id,
                    work_state_id=tool_input.work_state_id,
                    execution_node_id=tool_input.execution_node_id,
                    solver_run_id=tool_input.solver_run_id,
                ),
            )

        if tool_name == "memorii_record_progress":
            try:
                tool_input = RecordProgressInput.model_validate(arguments)
            except ValidationError as exc:
                return ProviderToolCallResult(
                    tool_name=tool_name,
                    ok=False,
                    error=f"Validation error for tool '{tool_name}': {exc}",
                )
            if self._work_state_service is None:
                return ProviderToolCallResult(tool_name=tool_name, ok=False, error="work_state_service_not_configured")
            state, event = self._work_state_service.record_progress(
                work_state_id=tool_input.work_state_id,
                task_id=tool_input.task_id,
                session_id=tool_input.session_id,
                content=tool_input.content,
                evidence_ids=tool_input.evidence_ids,
                solver_run_id=tool_input.solver_run_id,
                execution_node_id=tool_input.execution_node_id,
            )
            if state is None or event is None:
                return ProviderToolCallResult(tool_name=tool_name, ok=False, error="work_state_not_found")
            candidate_result = self._stage_work_state_event_candidate(
                state=state,
                event=event,
                event_type="progress",
                outcome=None,
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

        if tool_name == "memorii_record_outcome":
            try:
                tool_input = RecordOutcomeInput.model_validate(arguments)
            except ValidationError as exc:
                return ProviderToolCallResult(
                    tool_name=tool_name,
                    ok=False,
                    error=f"Validation error for tool '{tool_name}': {exc}",
                )
            if self._work_state_service is None:
                return ProviderToolCallResult(tool_name=tool_name, ok=False, error="work_state_service_not_configured")
            state, event = self._work_state_service.record_outcome(
                work_state_id=tool_input.work_state_id,
                task_id=tool_input.task_id,
                session_id=tool_input.session_id,
                outcome=tool_input.outcome.value,
                content=tool_input.content,
                evidence_ids=tool_input.evidence_ids,
                solver_run_id=tool_input.solver_run_id,
                execution_node_id=tool_input.execution_node_id,
            )
            if state is None or event is None:
                return ProviderToolCallResult(tool_name=tool_name, ok=False, error="work_state_not_found")
            candidate_result = self._stage_work_state_event_candidate(
                state=state,
                event=event,
                event_type="outcome",
                outcome=tool_input.outcome.value,
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

        return ProviderToolCallResult(
            tool_name=tool_name,
            ok=False,
            error=f"Unknown provider tool: {tool_name}",
        )

    def seed_committed_record(self, record: ProviderStoredRecord) -> None:
        self._memory_plane.seed_provider_committed_record(record)

    def candidate_records(self) -> list[ProviderStoredRecord]:
        return self._memory_plane.provider_candidate_records()

    def transcript_records(self) -> list[ProviderStoredRecord]:
        return self._memory_plane.provider_transcript_records()

    def last_prefetch_trace(self):
        return self._memory_plane.last_provider_prefetch_trace()

    def last_recall_bundle(self) -> RecallStateBundle | None:
        return self._last_recall_bundle

    def list_work_states(
        self,
        *,
        session_id: str | None = None,
        task_id: str | None = None,
        user_id: str | None = None,
        kinds: list[WorkStateKind] | None = None,
        statuses: list[WorkStateStatus] | None = None,
    ) -> list[WorkStateRecord]:
        if self._work_state_service is None:
            return []
        return self._work_state_service.list_states(
            session_id=session_id,
            task_id=task_id,
            user_id=user_id,
            kinds=kinds,
            statuses=statuses,
        )

    def _build_state_summary_result(
        self,
        *,
        session_id: str | None,
        task_id: str | None,
        user_id: str | None,
    ) -> dict[str, object]:
        selected_work_states = self._work_state_selector.select_recall_work_states(
            session_id=session_id,
            task_id=task_id,
            user_id=user_id,
        )
        work_state_summaries = summarize_work_states(
            selected_work_states,
            events_by_state_id=self._list_events_by_work_state_id(selected_work_states),
            decision_summary_by_state_id=self._decision_summary_by_work_state_id(selected_work_states),
        )
        return {
            "work_states": [summary.model_dump(mode="json") for summary in work_state_summaries],
            "state_count": len(work_state_summaries),
            "scope": {
                "task_id": task_id,
                "session_id": session_id,
                "user_id": user_id,
            },
        }

    def _build_open_or_resume_work_result(
        self,
        *,
        title: str,
        summary: str | None,
        kind: WorkStateKind,
        session_id: str | None,
        task_id: str | None,
        user_id: str | None,
        work_state_id: str | None,
        execution_node_id: str | None,
        solver_run_id: str | None,
    ) -> dict[str, object]:
        if self._work_state_service is None:
            return {"error": "work_state_service_not_configured"}
        work_state = self._work_state_service.open_or_resume_work(
            title=title,
            summary=summary,
            kind=kind,
            session_id=session_id,
            task_id=task_id,
            user_id=user_id,
            work_state_id=work_state_id,
            execution_node_id=execution_node_id,
            solver_run_id=solver_run_id,
        )
        decision_state_id = None
        if work_state.kind == WorkStateKind.DECISION:
            decision_state_id = self._ensure_decision_state_for_work(
                work_state=work_state,
                title=title,
                session_id=session_id,
                task_id=task_id,
                user_id=user_id,
            )
        binding = None
        if solver_run_id is not None or execution_node_id is not None:
            bindings = self._work_state_service.list_bindings(work_state_id=work_state.work_state_id)
            if bindings:
                latest = max(bindings, key=lambda item: item.updated_at)
                binding = {
                    "binding_id": latest.binding_id,
                    "solver_run_id": latest.solver_run_id,
                    "execution_node_id": latest.execution_node_id,
                }

        return {
            "work_state": {
                "work_state_id": work_state.work_state_id,
                "kind": work_state.kind.value,
                "status": work_state.status.value,
                "title": work_state.title,
                "summary": work_state.summary,
                "confidence": work_state.confidence,
                "task_id": work_state.task_id,
                "session_id": work_state.session_id,
                "user_id": work_state.user_id,
            },
            "binding": binding,
            "decision_state_id": decision_state_id,
        }

    def _ensure_decision_state_for_work(
        self,
        *,
        work_state: WorkStateRecord,
        title: str,
        session_id: str | None,
        task_id: str | None,
        user_id: str | None,
    ) -> str | None:
        if self._decision_state_service is None:
            return None
        existing_open_decisions = self._decision_state_service.list_decisions(
            work_state_id=work_state.work_state_id,
            statuses=[DecisionStatus.OPEN],
        )
        if existing_open_decisions:
            return existing_open_decisions[0].decision_id
        created = self._decision_state_service.open_decision(
            question=title,
            work_state_id=work_state.work_state_id,
            session_id=session_id,
            task_id=task_id,
            user_id=user_id,
        )
        return created.decision_id

    def _record_decision_work_state_outcome(
        self,
        *,
        decision_state: DecisionState,
    ) -> tuple[dict[str, object], WorkStateRecord | None, WorkStateEvent | None]:
        if self._work_state_service is None:
            return {
                "work_state_outcome_recorded": False,
                "work_state_outcome_event": None,
            }, None, None
        if decision_state.work_state_id is None:
            return {
                "work_state_outcome_recorded": False,
                "work_state_outcome_event": None,
            }, None, None
        state, event = self._work_state_service.record_outcome(
            work_state_id=decision_state.work_state_id,
            outcome="completed",
            content=f"Decision finalized: {decision_state.final_decision}",
            evidence_ids=_decision_evidence_ids(decision_state),
        )
        if state is None or event is None:
            return {
                "work_state_outcome_recorded": False,
                "work_state_outcome_event": None,
                "work_state_outcome_error": "work_state_not_found",
            }, None, None
        return {
            "work_state_outcome_recorded": True,
            "work_state_outcome_event": {
                "work_state_id": state.work_state_id,
                "event_id": event.event_id,
                "status": state.status.value,
            },
        }, state, event

    @staticmethod
    def _format_work_state_section(work_states: list[WorkStateSummary]) -> str:
        lines = ["Current work state:"]
        for state in work_states:
            lines.append(f"- [{state.kind.value}:{state.status.value}] {state.title}")
            lines.append(f"  Summary: {state.summary}")
            if state.latest_progress:
                lines.append(f"  Latest progress: {state.latest_progress}")
            if state.latest_outcome:
                lines.append(f"  Latest outcome: {state.latest_outcome}")
            if state.decision_state is not None:
                lines.extend(ProviderMemoryService._format_decision_state_section(state.decision_state))
            lines.append(f"  Confidence: {state.confidence:.2f}")
        return "\n".join(lines)

    @staticmethod
    def _format_decision_state_section(decision_summary: DecisionStateSummary) -> list[str]:
        lines = [
            "  Decision state:",
            f"  Question: {decision_summary.question}",
            f"  Status: {decision_summary.status}",
        ]
        if decision_summary.option_labels:
            lines.append("  Options:")
            lines.extend([f"  - {option_label}" for option_label in decision_summary.option_labels])
        if decision_summary.criteria_labels:
            lines.append("  Criteria:")
            lines.extend([f"  - {criteria_label}" for criteria_label in decision_summary.criteria_labels])
        if decision_summary.recommendation is not None:
            lines.extend(["  Current recommendation:", f"  {decision_summary.recommendation}"])
        if decision_summary.unresolved_questions:
            lines.append("  Unresolved questions:")
            lines.extend([f"  - {question}" for question in decision_summary.unresolved_questions])
        if decision_summary.final_decision is not None:
            lines.extend(["  Final decision:", f"  {decision_summary.final_decision}"])
        return lines

    def _list_events_by_work_state_id(
        self, work_states: list[WorkStateRecord]
    ) -> dict[str, list[WorkStateEvent]]:
        if self._work_state_service is None:
            return {}
        return {
            state.work_state_id: self._work_state_service.list_work_state_events(state.work_state_id)
            for state in work_states
        }

    def _decision_summary_by_work_state_id(
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
            selected_decision = next((decision for decision in decisions if decision.status == DecisionStatus.OPEN), None)
            if selected_decision is None:
                selected_decision = next(
                    (decision for decision in decisions if decision.status == DecisionStatus.DECIDED),
                    None,
                )
            if selected_decision is None:
                continue
            summaries[state.work_state_id] = summarize_decision_state(selected_decision)
        return summaries

    def _ingest_work_state(self, event: AgentEventEnvelope) -> None:
        if self._work_state_service is None:
            return
        self._work_state_service.ingest_event(event)

    def _agent_event_from_provider_event(self, *, event: ProviderEvent) -> AgentEventEnvelope:
        provider_metadata = getattr(event, "metadata", None)
        solver_run_id = getattr(event, "solver_run_id", None)
        execution_node_id = getattr(event, "execution_node_id", None)
        metadata = {
            "role": event.role,
            "target": event.target,
            "action": event.action,
        }
        if isinstance(provider_metadata, dict):
            if "solver_run_id" in provider_metadata:
                metadata["solver_run_id"] = provider_metadata["solver_run_id"]
            if "execution_node_id" in provider_metadata:
                metadata["execution_node_id"] = provider_metadata["execution_node_id"]
        if solver_run_id is not None:
            metadata["solver_run_id"] = solver_run_id
        if execution_node_id is not None:
            metadata["execution_node_id"] = execution_node_id
        return AgentEventEnvelope(
            event_id=event.event_id,
            provider="provider_memory_service",
            operation=event.operation.value,
            session_id=event.session_id,
            user_id=event.user_id,
            task_id=event.task_id,
            content=event.content or "",
            metadata=metadata,
            timestamp=event.timestamp or datetime.now(UTC),
        )

    def _stage_work_state_event_candidate(
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
        if not self._emit_work_state_event_candidates:
            return {
                "memory_candidate_created": False,
                "promotion_decision_applied": False,
                "promotion_trace_id": None,
                "promotion_decision": None,
                "promotion_decision_error": None,
            }
        try:
            memory_id = f"cand:episodic:work_state_event:{event.event_id}"
            scoped_task_id = task_id or state.task_id
            scoped_session_id = session_id or state.session_id
            event_solver_run_id = solver_run_id
            event_execution_node_id = execution_node_id
            if self._work_state_service is not None:
                bindings = self._work_state_service.list_bindings(work_state_id=state.work_state_id)
                if bindings:
                    latest = max(bindings, key=lambda item: item.updated_at)
                    event_solver_run_id = event_solver_run_id or latest.solver_run_id
                    event_execution_node_id = event_execution_node_id or latest.execution_node_id
            memory_text = self._build_work_state_event_memory_text(
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
            promotion_result = self._apply_promotion_decision_to_candidate(
                work_state=state,
                event=event,
                candidate_record=record,
            )
            return {
                "memory_candidate_created": True,
                "memory_candidate_id": memory_id,
                **promotion_result,
            }
        except Exception as exc:  # pragma: no cover - covered via injected failure tests
            return {
                "memory_candidate_created": False,
                "memory_candidate_error": str(exc),
                "promotion_decision_applied": False,
                "promotion_trace_id": None,
                "promotion_decision": None,
                "promotion_decision_error": None,
            }

    def _apply_promotion_decision_to_candidate(
        self,
        *,
        work_state: WorkStateRecord,
        event: WorkStateEvent,
        candidate_record: CanonicalMemoryRecord,
    ) -> dict[str, object]:
        if self._promotion_decision_provider is None:
            return {
                "promotion_decision_applied": False,
                "promotion_trace_id": None,
                "promotion_decision": None,
                "promotion_decision_error": None,
            }
        try:
            promotion_context = self._build_promotion_context_for_work_state_event(
                work_state=work_state,
                event=event,
                candidate_record=candidate_record,
                source_metadata=dict(candidate_record.content),
            )
            decision, trace = self._promotion_decision_provider.decide(context=promotion_context)
            if self._llm_decision_trace_store is not None:
                self._llm_decision_trace_store.append_trace(trace)
            promotion_decision_payload = {
                "promote": decision.promote,
                "target_plane": decision.target_plane,
                "confidence": decision.confidence,
                "rationale": decision.rationale,
                "merge_with_memory_id": decision.merge_with_memory_id,
                "supersede_memory_id": decision.supersede_memory_id,
                "tags": list(decision.tags),
                "trace_id": decision.trace_id,
            }
            candidate_record.content["promotion_decision"] = promotion_decision_payload
            candidate_record.content["promotion_trace_id"] = trace.trace_id
            return {
                "promotion_decision_applied": True,
                "promotion_trace_id": trace.trace_id,
                "promotion_decision": promotion_decision_payload,
                "promotion_decision_error": None,
            }
        except Exception as exc:
            candidate_record.content["promotion_decision_error"] = str(exc)
            return {
                "promotion_decision_applied": False,
                "promotion_trace_id": None,
                "promotion_decision": None,
                "promotion_decision_error": str(exc),
            }

    def _build_promotion_context_for_work_state_event(
        self,
        *,
        work_state: WorkStateRecord,
        event: WorkStateEvent,
        candidate_record: CanonicalMemoryRecord,
        source_metadata: dict[str, object],
    ) -> PromotionContext:
        repeated_across_episodes = int(source_metadata.get("repeated_across_episodes", 0) or 0)
        explicit_user_memory_request = bool(source_metadata.get("explicit_user_memory_request", False))
        candidate_type = self._promotion_candidate_type_for_work_state_event(
            event=event,
            source_metadata=source_metadata,
            explicit_user_memory_request=explicit_user_memory_request,
        )
        return PromotionContext(
            candidate_id=candidate_record.memory_id,
            candidate_type=candidate_type,
            content=candidate_record.text,
            source_ids=list(event.evidence_ids),
            related_memory_ids=[],
            repeated_across_episodes=repeated_across_episodes,
            explicit_user_memory_request=explicit_user_memory_request,
            created_from=self._promotion_created_from_for_work_state_event(work_state=work_state, event=candidate_record.content),
            metadata=dict(candidate_record.content),
        )

    @staticmethod
    def _promotion_candidate_type_for_work_state_event(
        *,
        event: WorkStateEvent,
        source_metadata: dict[str, object],
        explicit_user_memory_request: bool,
    ) -> PromotionCandidateType:
        if explicit_user_memory_request:
            return PromotionCandidateType.USER_MEMORY
        if bool(source_metadata.get("repeated_across_episodes", False)):
            semantic_target = source_metadata.get("semantic_target")
            if semantic_target == PromotionCandidateType.PROJECT_FACT.value:
                return PromotionCandidateType.PROJECT_FACT
            return PromotionCandidateType.SEMANTIC
        if event.event_type.value == "outcome":
            return PromotionCandidateType.EPISODIC
        return PromotionCandidateType.EPISODIC

    @staticmethod
    def _promotion_created_from_for_work_state_event(
        *,
        work_state: WorkStateRecord,
        event: dict[str, object],
    ) -> str:
        event_type = str(event.get("event_type", "progress"))
        outcome = str(event.get("outcome") or "")
        if event_type == "progress":
            return "observation"
        if event_type == "decision_finalized":
            return "decision_finalized"
        if outcome == "completed":
            return "task_outcome"
        if outcome == "blocked":
            if work_state.kind == WorkStateKind.INVESTIGATION:
                return "investigation_conclusion"
            return "task_outcome"
        return "task_outcome"

    @staticmethod
    def _build_work_state_event_memory_text(
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


def _decision_evidence_ids(decision_state: DecisionState) -> list[str]:
    evidence_ids: list[str] = []
    seen: set[str] = set()

    for decision_evidence in decision_state.evidence:
        for candidate in [decision_evidence.evidence_id, *decision_evidence.source_ids]:
            if candidate in seen:
                continue
            seen.add(candidate)
            evidence_ids.append(candidate)
    return evidence_ids
