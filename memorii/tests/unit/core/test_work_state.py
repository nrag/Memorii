from datetime import UTC, datetime

from memorii.core.provider.models import ProviderOperation
from memorii.core.provider.service import ProviderMemoryService
from memorii.core.work_state.models import (
    AgentEventEnvelope,
    WorkStateDetectionAction,
    WorkStateKind,
    WorkStateReasonCode,
    WorkStateStatus,
)
from memorii.core.work_state.service import WorkStateService


def _event(
    event_id: str,
    content: str,
    *,
    session_id: str = "s:1",
    task_id: str | None = None,
    metadata: dict[str, object] | None = None,
) -> AgentEventEnvelope:
    return AgentEventEnvelope(
        event_id=event_id,
        provider="test",
        operation="sync_turn",
        session_id=session_id,
        task_id=task_id,
        user_id="u:1",
        content=content,
        metadata=metadata or {},
        timestamp=datetime.now(UTC),
    )


def test_generic_chat_creates_no_state() -> None:
    service = WorkStateService()
    decision = service.ingest_event(_event("e1", "thanks, that makes sense"))
    assert decision.action == WorkStateDetectionAction.NO_STATE_UPDATE
    assert service.list_states() == []


def test_explicit_task_language_creates_candidate_task_state() -> None:
    service = WorkStateService()
    decision = service.ingest_event(_event("e2", "let's implement BM25 reranking and add tests", task_id="task:1"))
    states = service.list_states()
    assert decision.kind == WorkStateKind.TASK_EXECUTION
    assert decision.action == WorkStateDetectionAction.CREATE_CANDIDATE_STATE
    assert len(states) == 1
    assert states[0].status == WorkStateStatus.CANDIDATE


def test_tool_failure_creates_candidate_investigation() -> None:
    service = WorkStateService()
    decision = service.ingest_event(_event("e3", "build failed on CI", task_id="task:2"))
    states = service.list_states()
    assert decision.kind == WorkStateKind.INVESTIGATION
    assert WorkStateReasonCode.TOOL_FAILURE_OR_ERROR in decision.reason_codes
    assert states[0].kind == WorkStateKind.INVESTIGATION


def test_failing_language_prefers_investigation_over_task_execution() -> None:
    service = WorkStateService()
    decision = service.ingest_event(_event("e3b", "fix the failing benchmark", task_id="task:2b"))
    assert decision.kind == WorkStateKind.INVESTIGATION
    assert (
        WorkStateReasonCode.TOOL_FAILURE_OR_ERROR in decision.reason_codes
        or WorkStateReasonCode.DEBUGGING_LANGUAGE in decision.reason_codes
    )


def test_second_related_task_event_updates_existing_state() -> None:
    service = WorkStateService()
    first = service.ingest_event(_event("e4", "let's implement parser update", session_id="s:2"))
    second = service.ingest_event(_event("e5", "add tests for parser update", session_id="s:2"))
    states = service.list_states()
    assert first.work_state_id is not None
    assert second.action == WorkStateDetectionAction.UPDATE_EXISTING_STATE
    assert second.work_state_id == first.work_state_id
    assert len(states) == 1
    assert states[0].source_event_ids == ["e4", "e5"]


def test_decision_language_creates_candidate_decision_state() -> None:
    service = WorkStateService()
    decision = service.ingest_event(_event("e6", "should we choose LoCoMo or build our own benchmark?"))
    assert decision.kind == WorkStateKind.DECISION
    assert decision.action == WorkStateDetectionAction.CREATE_CANDIDATE_STATE


def test_provider_integration_without_work_state_service_is_optional() -> None:
    provider_service = ProviderMemoryService()
    result = provider_service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="hello there",
        session_id="s:3",
        task_id="task:3",
        user_id="u:3",
    )
    assert result.transcript_ids
    assert provider_service.list_work_states(task_id="task:3") == []


def test_provider_integration_records_state_when_service_supplied() -> None:
    work_state_service = WorkStateService()
    provider_service = ProviderMemoryService(work_state_service=work_state_service)
    provider_service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="please implement parser updates and write tests",
        session_id="s:4",
        task_id="task:4",
        user_id="u:4",
    )
    states = work_state_service.list_states(task_id="task:4")
    assert len(states) == 1
    assert states[0].status == WorkStateStatus.CANDIDATE


def test_ingest_event_with_solver_metadata_creates_binding() -> None:
    service = WorkStateService()

    service.ingest_event(
        _event(
            "e7",
            "investigate failing branch and capture evidence",
            session_id="s:binding",
            task_id="task:binding",
            metadata={"solver_run_id": "solver:binding", "execution_node_id": "exec:binding"},
        )
    )

    bindings = service.list_bindings(task_id="task:binding")
    assert len(bindings) == 1
    assert bindings[0].solver_run_id == "solver:binding"
    assert bindings[0].execution_node_id == "exec:binding"
