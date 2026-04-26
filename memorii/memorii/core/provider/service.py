"""Provider-oriented memory service for Hermes-style hooks."""

from __future__ import annotations

from datetime import UTC, datetime

from memorii.core.memory_plane import MemoryPlaneService
from memorii.core.provider.classifier import build_event_id, make_event
from memorii.core.provider.models import (
    ProviderEvent,
    ProviderOperation,
    ProviderStoredRecord,
    ProviderSyncResult,
    ProviderWriteDecision,
)
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

    def sync_event(self, *, operation: ProviderOperation, content: str, role: str | None = None,
                   target: str | None = None, action: str | None = None, session_id: str | None = None,
                   task_id: str | None = None, user_id: str | None = None) -> ProviderSyncResult:
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
        filtered_states = self._select_recall_work_states(session_id=session_id, task_id=task_id, user_id=user_id)
        work_state_summaries = summarize_work_states(filtered_states)
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
