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
from memorii.core.provider.tools import GetNextStepInput, GetStateSummaryInput, ProviderToolCallResult
from memorii.core.recall import RecallStateBundle, WorkStateSummary, summarize_work_states
from memorii.core.work_state.models import AgentEventEnvelope, WorkStateKind, WorkStateRecord, WorkStateStatus
from memorii.core.work_state.service import WorkStateService


class ProviderMemoryService:
    """Thin provider adapter over the canonical MemoryPlaneService."""

    def __init__(
        self,
        memory_plane: MemoryPlaneService | None = None,
        work_state_service: WorkStateService | None = None,
    ) -> None:
        self._memory_plane = memory_plane or MemoryPlaneService()
        self._work_state_service = work_state_service
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
                    },
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
                ),
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
    ) -> dict[str, object]:
        del query  # query is accepted for future frontier-planning support.
        work_state_summaries = summarize_work_states(
            self._select_recall_work_states(session_id=session_id, task_id=task_id, user_id=user_id)
        )
        scope = {
            "task_id": task_id,
            "session_id": session_id,
            "user_id": user_id,
        }
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
