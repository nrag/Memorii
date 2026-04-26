"""Provider-oriented memory service for Hermes-style hooks."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import ValidationError

from memorii.core.memory_plane import MemoryPlaneService
from memorii.core.provider.classifier import build_event_id, make_event
from memorii.core.provider.models import (
    ProviderEvent,
    ProviderOperation,
    ProviderStoredRecord,
    ProviderSyncResult,
    ProviderWriteDecision,
)
from memorii.core.provider.tools import (
    GetNextStepInput,
    GetStateSummaryInput,
    OpenOrResumeWorkInput,
    ProviderToolCallResult,
    RecordOutcomeInput,
    RecordProgressInput,
)
from memorii.core.recall import RecallStateBundle, WorkStateSummary, summarize_work_states
from memorii.core.solver import SolverFrontierPlanner
from memorii.core.work_state.models import AgentEventEnvelope, WorkStateKind, WorkStateRecord, WorkStateStatus
from memorii.core.work_state.service import WorkStateService
from memorii.stores.base.interfaces import OverlayStore, SolverGraphStore


class ProviderMemoryService:
    """Thin provider adapter over the canonical MemoryPlaneService."""

    def __init__(
        self,
        memory_plane: MemoryPlaneService | None = None,
        work_state_service: WorkStateService | None = None,
        solver_frontier_planner: SolverFrontierPlanner | None = None,
        solver_store: SolverGraphStore | None = None,
        overlay_store: OverlayStore | None = None,
    ) -> None:
        self._memory_plane = memory_plane or MemoryPlaneService()
        self._work_state_service = work_state_service
        self._solver_frontier_planner = solver_frontier_planner
        self._solver_store = solver_store
        self._overlay_store = overlay_store
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
        work_state_summaries = summarize_work_states(
            self._select_recall_work_states(session_id=session_id, task_id=task_id, user_id=user_id)
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
                result=self._build_next_step_result(
                    query=tool_input.query,
                    session_id=tool_input.session_id,
                    task_id=tool_input.task_id,
                    user_id=tool_input.user_id,
                    solver_run_id=tool_input.solver_run_id,
                ),
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
            return ProviderToolCallResult(
                tool_name=tool_name,
                ok=True,
                result={
                    "work_state_id": state.work_state_id,
                    "event_id": event.event_id,
                    "status": state.status.value,
                    "recorded": True,
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
            return ProviderToolCallResult(
                tool_name=tool_name,
                ok=True,
                result={
                    "work_state_id": state.work_state_id,
                    "event_id": event.event_id,
                    "status": state.status.value,
                    "recorded": True,
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
        work_state_summaries = summarize_work_states(
            self._select_recall_work_states(session_id=session_id, task_id=task_id, user_id=user_id)
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

    def _build_next_step_result(
        self,
        *,
        query: str | None,
        session_id: str | None,
        task_id: str | None,
        user_id: str | None,
        solver_run_id: str | None = None,
    ) -> dict[str, object]:
        del query  # query is accepted for future frontier-planning support.
        scope = {
            "task_id": task_id,
            "session_id": session_id,
            "user_id": user_id,
        }
        effective_solver_run_id, solver_run_resolution_source = self._resolve_effective_solver_run_id(
            solver_run_id=solver_run_id,
            task_id=task_id,
            session_id=session_id,
        )

        if effective_solver_run_id is not None:
            if self._planner_dependencies_ready():
                frontier_plan = self._solver_frontier_planner.select_next_frontier(
                    solver_run_id=effective_solver_run_id,
                    solver_store=self._solver_store,
                    overlay_store=self._overlay_store,
                )
                if frontier_plan.selected_node_id is not None:
                    next_step: dict[str, object]
                    if frontier_plan.next_test_action is not None:
                        next_step = {
                            "action_type": frontier_plan.next_test_action.action_type,
                            "description": frontier_plan.next_test_action.description,
                            "confidence": 0.6,
                            "reason": frontier_plan.reason.value,
                            "evidence_ids": [],
                            "expected_evidence": frontier_plan.next_test_action.expected_evidence,
                            "success_condition": frontier_plan.next_test_action.success_condition,
                            "failure_condition": frontier_plan.next_test_action.failure_condition,
                            "required_tool": frontier_plan.next_test_action.required_tool,
                            "target_ref": frontier_plan.next_test_action.target_ref,
                        }
                    elif frontier_plan.next_best_test:
                        next_step = {
                            "action_type": "run_test",
                            "description": frontier_plan.next_best_test,
                            "confidence": 0.55,
                            "reason": frontier_plan.reason.value,
                            "evidence_ids": [],
                        }
                    else:
                        next_step = {
                            "action_type": "inspect_frontier",
                            "description": "Inspect the selected solver frontier node before continuing.",
                            "confidence": 0.45,
                            "reason": frontier_plan.reason.value,
                            "evidence_ids": [],
                        }
                    return {
                        "next_step": next_step,
                        "based_on_solver_run_id": effective_solver_run_id,
                        "based_on_solver_node_id": frontier_plan.selected_node_id,
                        "based_on_work_state_id": None,
                        "planner_used": True,
                        "planner_reason": frontier_plan.reason.value,
                        "candidate_frontier_node_ids": frontier_plan.candidate_frontier_node_ids,
                        "requested_solver_run_id": solver_run_id,
                        "resolved_solver_run_id": effective_solver_run_id,
                        "solver_run_resolution_source": solver_run_resolution_source,
                        "scope": scope,
                    }
                fallback_result = self._build_work_state_next_step_fallback(
                    session_id=session_id,
                    task_id=task_id,
                    user_id=user_id,
                    scope=scope,
                )
                fallback_result["based_on_solver_run_id"] = effective_solver_run_id
                fallback_result["based_on_solver_node_id"] = None
                fallback_result["planner_used"] = False
                fallback_result["planner_reason"] = "no_frontier_found"
                fallback_result["candidate_frontier_node_ids"] = frontier_plan.candidate_frontier_node_ids
                fallback_result["requested_solver_run_id"] = solver_run_id
                fallback_result["resolved_solver_run_id"] = effective_solver_run_id
                fallback_result["solver_run_resolution_source"] = solver_run_resolution_source
                return fallback_result

            fallback_result = self._build_work_state_next_step_fallback(
                session_id=session_id,
                task_id=task_id,
                user_id=user_id,
                scope=scope,
            )
            fallback_result["based_on_solver_run_id"] = effective_solver_run_id
            fallback_result["based_on_solver_node_id"] = None
            fallback_result["planner_used"] = False
            fallback_result["planner_reason"] = "planner_not_configured"
            fallback_result["candidate_frontier_node_ids"] = []
            fallback_result["requested_solver_run_id"] = solver_run_id
            fallback_result["resolved_solver_run_id"] = effective_solver_run_id
            fallback_result["solver_run_resolution_source"] = solver_run_resolution_source
            return fallback_result

        fallback_result = self._build_work_state_next_step_fallback(
            session_id=session_id,
            task_id=task_id,
            user_id=user_id,
            scope=scope,
        )
        fallback_result["based_on_solver_run_id"] = None
        fallback_result["based_on_solver_node_id"] = None
        fallback_result["planner_used"] = False
        fallback_result["planner_reason"] = "no_solver_run_resolved"
        fallback_result["candidate_frontier_node_ids"] = []
        fallback_result["requested_solver_run_id"] = solver_run_id
        fallback_result["resolved_solver_run_id"] = None
        fallback_result["solver_run_resolution_source"] = solver_run_resolution_source
        return fallback_result

    def _build_work_state_next_step_fallback(
        self,
        *,
        session_id: str | None,
        task_id: str | None,
        user_id: str | None,
        scope: dict[str, str | None],
    ) -> dict[str, object]:
        work_state_summaries = summarize_work_states(
            self._select_recall_work_states(session_id=session_id, task_id=task_id, user_id=user_id)
        )
        if not work_state_summaries:
            return {
                "next_step": {
                    "action_type": "ask_user",
                    "description": "No active work state found. Ask the user what they want to do next.",
                    "confidence": 0.2,
                    "reason": "no_active_work_state",
                    "evidence_ids": [],
                },
                "based_on_work_state_id": None,
                "scope": scope,
            }

        selected_state = work_state_summaries[0]
        action_type = "continue_research"
        description = "Continue collecting evidence and summarize what changed."
        if selected_state.kind == WorkStateKind.TASK_EXECUTION:
            action_type = "continue_task"
            description = "Continue the active task and record progress when a meaningful step completes."
        elif selected_state.kind == WorkStateKind.INVESTIGATION:
            action_type = "inspect_failure"
            description = "Inspect the latest failure or missing evidence before committing a conclusion."
        elif selected_state.kind == WorkStateKind.DECISION:
            action_type = "clarify_decision_criteria"
            description = "Clarify options, criteria, and constraints before choosing."

        return {
            "next_step": {
                "action_type": action_type,
                "description": description,
                "confidence": 0.4,
                "reason": "frontier_planner_not_yet_enabled",
                "evidence_ids": list(selected_state.source_event_ids),
            },
            "based_on_work_state_id": selected_state.work_state_id,
            "scope": scope,
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
        }

    def _select_recall_work_states(
        self,
        *,
        session_id: str | None,
        task_id: str | None,
        user_id: str | None,
    ) -> list[WorkStateRecord]:
        if self._work_state_service is None:
            return []

        included_statuses = [
            WorkStateStatus.ACTIVE,
            WorkStateStatus.CANDIDATE,
            WorkStateStatus.PAUSED,
        ]
        if task_id is not None:
            return self._work_state_service.list_states(task_id=task_id, statuses=included_statuses)
        if session_id is not None:
            return self._work_state_service.list_states(session_id=session_id, statuses=included_statuses)
        if user_id is not None:
            return self._work_state_service.list_states(user_id=user_id, statuses=included_statuses)
        return self._work_state_service.list_states(statuses=included_statuses)

    @staticmethod
    def _format_work_state_section(work_states: list[WorkStateSummary]) -> str:
        lines = ["Current work state:"]
        for state in work_states:
            lines.append(f"- [{state.kind.value}:{state.status.value}] {state.title}")
            lines.append(f"  Summary: {state.summary}")
            lines.append(f"  Confidence: {state.confidence:.2f}")
        return "\n".join(lines)

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

    def _planner_dependencies_ready(self) -> bool:
        return (
            self._solver_frontier_planner is not None
            and self._solver_store is not None
            and self._overlay_store is not None
        )

    def _resolve_effective_solver_run_id(
        self,
        *,
        solver_run_id: str | None,
        task_id: str | None,
        session_id: str | None,
    ) -> tuple[str | None, str]:
        if solver_run_id is not None:
            return solver_run_id, "explicit"
        if self._work_state_service is None:
            return None, "none"
        if task_id is not None:
            resolved_by_task = self._work_state_service.resolve_solver_run_id(task_id=task_id)
            if resolved_by_task is not None:
                return resolved_by_task, "task_binding"
        if session_id is not None:
            resolved_by_session = self._work_state_service.resolve_solver_run_id(session_id=session_id)
            if resolved_by_session is not None:
                return resolved_by_session, "session_binding"
        return None, "none"
