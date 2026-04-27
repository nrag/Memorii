from datetime import UTC, datetime

from memorii.core.solver import SolverFrontierPlanner
from memorii.core.decision_state.models import DecisionEvidencePolarity, DecisionStatus
from memorii.core.decision_state.service import DecisionStateService
from memorii.domain.common import SolverNodeMetadata
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.domain.enums import CommitStatus, MemoryDomain, SolverCreatedBy, SolverNodeStatus, SolverNodeType
from memorii.domain.solver_graph.nodes import SolverNode
from memorii.domain.solver_graph.overlays import SolverNodeOverlay, SolverOverlayVersion
from memorii.core.provider.models import ProviderOperation
from memorii.core.provider.service import ProviderMemoryService, _decision_evidence_ids
from memorii.core.work_state.models import WorkStateKind, WorkStateStatus
from memorii.core.work_state.service import WorkStateService
from memorii.stores.overlays import InMemoryOverlayStore
from memorii.stores.solver_graph import InMemorySolverGraphStore


NOW = datetime.now(UTC)


def _make_node(node_id: str, *, content: dict[str, object]) -> SolverNode:
    return SolverNode(
        id=node_id,
        type=SolverNodeType.ACTION,
        content=content,
        metadata=SolverNodeMetadata(
            created_at=NOW,
            created_by=SolverCreatedBy.SYSTEM,
            candidate_state=CommitStatus.COMMITTED,
        ),
    )


def _overlay(
    node_id: str,
    *,
    status: SolverNodeStatus = SolverNodeStatus.NEEDS_TEST,
    priority: float = 1.0,
    is_frontier: bool = True,
) -> SolverNodeOverlay:
    return SolverNodeOverlay(
        node_id=node_id,
        belief=0.5,
        status=status,
        frontier_priority=priority,
        is_frontier=is_frontier,
        updated_at=NOW,
    )


def _append_overlay(store: InMemoryOverlayStore, solver_run_id: str, overlays: list[SolverNodeOverlay]) -> None:
    store.append_overlay_version(
        SolverOverlayVersion(
            version_id=f"ov:{solver_run_id}:{len(store.list_versions(solver_run_id))}",
            solver_run_id=solver_run_id,
            created_at=NOW,
            committed=True,
            node_overlays=overlays,
        )
    )


def test_get_tool_schemas_includes_state_summary_and_next_step() -> None:
    provider = ProviderMemoryService()

    schemas = provider.get_tool_schemas()
    tool_names = {schema["name"] for schema in schemas}

    assert "memorii_get_state_summary" in tool_names
    assert "memorii_get_next_step" in tool_names
    assert "memorii_open_or_resume_work" in tool_names
    assert "memorii_record_progress" in tool_names
    assert "memorii_record_outcome" in tool_names
    assert "memorii_decision_add_option" in tool_names
    assert "memorii_decision_add_criterion" in tool_names
    assert "memorii_decision_add_evidence" in tool_names
    assert "memorii_decision_set_recommendation" in tool_names
    assert "memorii_decision_finalize" in tool_names

    next_step_schema = next(schema for schema in schemas if schema["name"] == "memorii_get_next_step")
    properties = next_step_schema["input_schema"]["properties"]
    assert "solver_run_id" in properties
    open_or_resume_schema = next(schema for schema in schemas if schema["name"] == "memorii_open_or_resume_work")
    assert open_or_resume_schema["input_schema"]["required"] == ["title"]
    assert "kind" in open_or_resume_schema["input_schema"]["properties"]
    record_progress_schema = next(schema for schema in schemas if schema["name"] == "memorii_record_progress")
    assert record_progress_schema["input_schema"]["required"] == ["content"]
    record_outcome_schema = next(schema for schema in schemas if schema["name"] == "memorii_record_outcome")
    assert record_outcome_schema["input_schema"]["required"] == ["outcome", "content"]
    add_evidence_schema = next(schema for schema in schemas if schema["name"] == "memorii_decision_add_evidence")
    assert add_evidence_schema["input_schema"]["required"] == [
        "decision_state_id",
        "evidence_id",
        "content",
        "polarity",
    ]
    finalize_schema = next(schema for schema in schemas if schema["name"] == "memorii_decision_finalize")
    assert finalize_schema["input_schema"]["required"] == ["decision_state_id", "final_decision"]


def test_decision_tools_without_decision_state_service_return_error() -> None:
    provider = ProviderMemoryService(decision_state_service=None)

    result = provider.handle_tool_call(
        "memorii_decision_add_option",
        {"decision_state_id": "decision:missing", "option_id": "opt:1", "label": "Option 1"},
    )

    assert result.ok is False
    assert result.error == "decision_state_service_not_configured"


def test_decision_add_option_succeeds() -> None:
    decision_state_service = DecisionStateService()
    decision = decision_state_service.open_decision(question="Which rollout?")
    provider = ProviderMemoryService(decision_state_service=decision_state_service)

    result = provider.handle_tool_call(
        "memorii_decision_add_option",
        {
            "decision_state_id": decision.decision_id,
            "option_id": "opt:canary",
            "label": "Canary rollout",
            "description": "Ship in phases",
        },
    )

    assert result.ok is True
    decision_state = result.result["decision_state"]
    assert decision_state["options"][0]["option_id"] == "opt:canary"


def test_decision_add_criterion_succeeds() -> None:
    decision_state_service = DecisionStateService()
    decision = decision_state_service.open_decision(question="Which storage?")
    provider = ProviderMemoryService(decision_state_service=decision_state_service)

    result = provider.handle_tool_call(
        "memorii_decision_add_criterion",
        {
            "decision_state_id": decision.decision_id,
            "criterion_id": "crit:cost",
            "label": "Cost",
            "weight": 2.5,
        },
    )

    assert result.ok is True
    decision_state = result.result["decision_state"]
    assert decision_state["criteria"][0]["criterion_id"] == "crit:cost"
    assert decision_state["criteria"][0]["weight"] == 2.5


def test_decision_add_evidence_succeeds_with_enum_polarity() -> None:
    decision_state_service = DecisionStateService()
    decision = decision_state_service.open_decision(question="Which language?")
    provider = ProviderMemoryService(decision_state_service=decision_state_service)

    result = provider.handle_tool_call(
        "memorii_decision_add_evidence",
        {
            "decision_state_id": decision.decision_id,
            "evidence_id": "ev:1",
            "content": "Team has strong Python expertise",
            "polarity": DecisionEvidencePolarity.FOR_OPTION.value,
            "option_id": "opt:python",
            "source_ids": ["src:1"],
        },
    )

    assert result.ok is True
    decision_state = result.result["decision_state"]
    assert decision_state["evidence"][0]["polarity"] == DecisionEvidencePolarity.FOR_OPTION.value
    assert decision_state["evidence"][0]["source_ids"] == ["src:1"]


def test_decision_set_recommendation_succeeds() -> None:
    decision_state_service = DecisionStateService()
    decision = decision_state_service.open_decision(question="Which db?")
    provider = ProviderMemoryService(decision_state_service=decision_state_service)

    result = provider.handle_tool_call(
        "memorii_decision_set_recommendation",
        {
            "decision_state_id": decision.decision_id,
            "recommendation": "Prefer Postgres",
        },
    )

    assert result.ok is True
    assert result.result["decision_state"]["current_recommendation"] == "Prefer Postgres"


def test_decision_finalize_marks_decided() -> None:
    decision_state_service = DecisionStateService()
    decision = decision_state_service.open_decision(question="Which cache?")
    provider = ProviderMemoryService(decision_state_service=decision_state_service)

    result = provider.handle_tool_call(
        "memorii_decision_finalize",
        {
            "decision_state_id": decision.decision_id,
            "final_decision": "Use Redis",
        },
    )

    assert result.ok is True
    assert result.result["decision_state"]["status"] == DecisionStatus.DECIDED.value
    assert result.result["decision_state"]["final_decision"] == "Use Redis"
    assert result.result["work_state_outcome_recorded"] is False
    assert result.result["work_state_outcome_event"] is None
    assert "work_state_outcome_error" not in result.result


def test_decision_finalize_linked_decision_records_completed_work_state_outcome() -> None:
    work_state_service = WorkStateService()
    decision_state_service = DecisionStateService()
    work_state = work_state_service.open_or_resume_work(
        title="Choose cache",
        kind=WorkStateKind.DECISION,
        task_id="task:decision:outcome",
    )
    decision = decision_state_service.open_decision(
        question="Which cache?",
        work_state_id=work_state.work_state_id,
        task_id=work_state.task_id,
    )
    decision_state_service.add_evidence(
        decision_id=decision.decision_id,
        evidence_id="ev:cache:1",
        content="Current load profile is bursty",
        polarity=DecisionEvidencePolarity.NEUTRAL,
        source_ids=["src:load-profile"],
    )
    provider = ProviderMemoryService(
        work_state_service=work_state_service,
        decision_state_service=decision_state_service,
    )

    result = provider.handle_tool_call(
        "memorii_decision_finalize",
        {
            "decision_state_id": decision.decision_id,
            "final_decision": "Use Redis",
        },
    )

    assert result.ok is True
    assert result.result["decision_state"]["status"] == DecisionStatus.DECIDED.value
    assert result.result["work_state_outcome_recorded"] is True
    assert result.result["work_state_outcome_event"]["status"] == WorkStateStatus.RESOLVED.value
    assert "work_state_outcome_error" not in result.result
    events = work_state_service.list_work_state_events(work_state.work_state_id)
    assert events
    assert events[-1].content == "Decision finalized: Use Redis"


def test_decision_evidence_ids_dedupes_with_stable_order() -> None:
    decision_state_service = DecisionStateService()
    decision = decision_state_service.open_decision(question="Which db?")
    decision_state_service.add_evidence(
        decision_id=decision.decision_id,
        evidence_id="ev:1",
        content="first",
        polarity=DecisionEvidencePolarity.NEUTRAL,
        source_ids=["src:1", "src:2", "ev:1"],
    )
    decision_state_service.add_evidence(
        decision_id=decision.decision_id,
        evidence_id="src:2",
        content="second",
        polarity=DecisionEvidencePolarity.NEUTRAL,
        source_ids=["src:3", "src:1"],
    )
    updated = decision_state_service.get_decision(decision.decision_id)
    assert updated is not None

    assert _decision_evidence_ids(updated) == ["ev:1", "src:1", "src:2", "src:3"]


def test_decision_finalize_linked_outcome_records_deduped_evidence_ids() -> None:
    work_state_service = WorkStateService()
    decision_state_service = DecisionStateService()
    work_state = work_state_service.open_or_resume_work(title="Choose queue", kind=WorkStateKind.DECISION)
    decision = decision_state_service.open_decision(question="Which queue?", work_state_id=work_state.work_state_id)
    decision_state_service.add_evidence(
        decision_id=decision.decision_id,
        evidence_id="ev:1",
        content="evidence",
        polarity=DecisionEvidencePolarity.NEUTRAL,
        source_ids=["src:1", "src:1", "ev:1"],
    )
    provider = ProviderMemoryService(
        work_state_service=work_state_service,
        decision_state_service=decision_state_service,
    )

    result = provider.handle_tool_call(
        "memorii_decision_finalize",
        {"decision_state_id": decision.decision_id, "final_decision": "Use queue A"},
    )

    assert result.ok is True
    events = work_state_service.list_work_state_events(work_state.work_state_id)
    assert events[-1].evidence_ids == ["ev:1", "src:1"]


def test_decision_finalize_without_work_state_service_does_not_fail() -> None:
    decision_state_service = DecisionStateService()
    decision = decision_state_service.open_decision(question="Which cache?", work_state_id="ws:decision:missing")
    provider = ProviderMemoryService(
        work_state_service=None,
        decision_state_service=decision_state_service,
    )

    result = provider.handle_tool_call(
        "memorii_decision_finalize",
        {"decision_state_id": decision.decision_id, "final_decision": "Use Redis"},
    )

    assert result.ok is True
    assert result.result["decision_state"]["status"] == DecisionStatus.DECIDED.value
    assert result.result["work_state_outcome_recorded"] is False
    assert result.result["work_state_outcome_event"] is None
    assert "work_state_outcome_error" not in result.result


def test_decision_finalize_missing_linked_work_state_returns_error_but_succeeds() -> None:
    decision_state_service = DecisionStateService()
    decision = decision_state_service.open_decision(question="Which cache?", work_state_id="ws:decision:unknown")
    provider = ProviderMemoryService(
        work_state_service=WorkStateService(),
        decision_state_service=decision_state_service,
    )

    result = provider.handle_tool_call(
        "memorii_decision_finalize",
        {"decision_state_id": decision.decision_id, "final_decision": "Use Redis"},
    )

    assert result.ok is True
    assert result.result["decision_state"]["status"] == DecisionStatus.DECIDED.value
    assert result.result["work_state_outcome_recorded"] is False
    assert result.result["work_state_outcome_event"] is None
    assert result.result["work_state_outcome_error"] == "work_state_not_found"


def test_decision_tool_unknown_decision_id_returns_not_found() -> None:
    provider = ProviderMemoryService(decision_state_service=DecisionStateService())

    result = provider.handle_tool_call(
        "memorii_decision_add_option",
        {"decision_state_id": "decision:unknown", "option_id": "opt:1", "label": "Option"},
    )

    assert result.ok is False
    assert result.error == "decision_state_not_found"


def test_decision_tool_validation_rejects_extra_fields() -> None:
    decision_state_service = DecisionStateService()
    provider = ProviderMemoryService(decision_state_service=decision_state_service)
    decision = decision_state_service.open_decision(question="q")

    result = provider.handle_tool_call(
        "memorii_decision_add_option",
        {
            "decision_state_id": decision.decision_id,
            "option_id": "opt:1",
            "label": "Option",
            "extra_field": "not-allowed",
        },
    )

    assert result.ok is False
    assert "Validation error" in (result.error or "")


def test_handle_tool_call_unknown_tool_returns_error() -> None:
    provider = ProviderMemoryService()

    result = provider.handle_tool_call("not_a_tool", {})

    assert result.ok is False
    assert "not_a_tool" in (result.error or "")


def test_handle_tool_call_validation_error_returns_error() -> None:
    provider = ProviderMemoryService()

    result = provider.handle_tool_call("memorii_get_state_summary", {"task_id": 123})

    assert result.ok is False
    assert "Validation error" in (result.error or "")


def test_get_state_summary_without_work_state_service_returns_empty() -> None:
    provider = ProviderMemoryService()

    result = provider.handle_tool_call("memorii_get_state_summary", {"task_id": "task:none"})

    assert result.ok is True
    assert result.result["state_count"] == 0
    assert result.result["work_states"] == []


def test_open_or_resume_without_work_state_service_returns_error() -> None:
    provider = ProviderMemoryService()

    result = provider.handle_tool_call(
        "memorii_open_or_resume_work",
        {"title": "Resume parser task", "task_id": "task:none"},
    )

    assert result.ok is False
    assert result.error == "work_state_service_not_configured"


def test_record_progress_without_work_state_service_returns_error() -> None:
    provider = ProviderMemoryService()

    result = provider.handle_tool_call("memorii_record_progress", {"content": "implemented parser changes"})

    assert result.ok is False
    assert result.error == "work_state_service_not_configured"


def test_record_outcome_without_work_state_service_returns_error() -> None:
    provider = ProviderMemoryService()

    result = provider.handle_tool_call(
        "memorii_record_outcome",
        {"outcome": "completed", "content": "all acceptance tests passed"},
    )

    assert result.ok is False
    assert result.error == "work_state_service_not_configured"


def test_record_progress_by_work_state_id() -> None:
    work_state_service = WorkStateService()
    provider = ProviderMemoryService(work_state_service=work_state_service)
    created = work_state_service.open_or_resume_work(title="Implement parser", task_id="task:progress:ws")

    result = provider.handle_tool_call(
        "memorii_record_progress",
        {
            "work_state_id": created.work_state_id,
            "content": "Merged parser refactor and added tests",
            "evidence_ids": ["pr:123"],
        },
    )

    assert result.ok is True
    assert result.result["work_state_id"] == created.work_state_id
    assert result.result["status"] == "active"
    assert result.result["memory_candidate_created"] is True
    assert isinstance(result.result["memory_candidate_id"], str)


def test_record_progress_by_task_id() -> None:
    work_state_service = WorkStateService()
    provider = ProviderMemoryService(work_state_service=work_state_service)
    created = work_state_service.open_or_resume_work(title="Implement parser", task_id="task:progress:task")

    result = provider.handle_tool_call(
        "memorii_record_progress",
        {"task_id": "task:progress:task", "content": "Added failing case reproduction"},
    )

    assert result.ok is True
    assert result.result["work_state_id"] == created.work_state_id


def test_record_progress_returns_error_when_no_state_found() -> None:
    work_state_service = WorkStateService()
    provider = ProviderMemoryService(work_state_service=work_state_service)

    result = provider.handle_tool_call(
        "memorii_record_progress",
        {"task_id": "task:missing", "content": "progress with unknown state"},
    )

    assert result.ok is False
    assert result.error == "work_state_not_found"
    assert provider._memory_plane.list_records(status=CommitStatus.CANDIDATE, domains=[MemoryDomain.EPISODIC]) == []


def test_record_progress_creates_episodic_memory_candidate_with_work_state_event_metadata() -> None:
    work_state_service = WorkStateService()
    provider = ProviderMemoryService(work_state_service=work_state_service)
    created = work_state_service.open_or_resume_work(title="Emit candidate", task_id="task:progress:candidate")

    result = provider.handle_tool_call(
        "memorii_record_progress",
        {
            "work_state_id": created.work_state_id,
            "content": "Implemented deterministic promotion staging",
            "evidence_ids": ["ev:1"],
        },
    )

    assert result.ok is True
    assert result.result["memory_candidate_created"] is True
    candidate_id = str(result.result["memory_candidate_id"])
    candidate = provider._memory_plane.get_record(candidate_id)
    assert candidate is not None
    assert candidate.domain == MemoryDomain.EPISODIC
    assert candidate.content["work_state_event_id"] == result.result["event_id"]
    assert candidate.content["event_type"] == "progress"
    assert candidate.source_kind == "provider:work_state_event"


def test_record_outcome_completed_marks_state_resolved() -> None:
    work_state_service = WorkStateService()
    provider = ProviderMemoryService(work_state_service=work_state_service)
    created = work_state_service.open_or_resume_work(title="Complete parser", task_id="task:outcome:completed")

    result = provider.handle_tool_call(
        "memorii_record_outcome",
        {"work_state_id": created.work_state_id, "outcome": "completed", "content": "Done"},
    )

    assert result.ok is True
    assert result.result["status"] == "resolved"
    assert result.result["memory_candidate_created"] is True


def test_record_outcome_creates_episodic_memory_candidate() -> None:
    work_state_service = WorkStateService()
    provider = ProviderMemoryService(work_state_service=work_state_service)
    created = work_state_service.open_or_resume_work(title="Outcome candidate", task_id="task:outcome:candidate")

    result = provider.handle_tool_call(
        "memorii_record_outcome",
        {"work_state_id": created.work_state_id, "outcome": "completed", "content": "Completed with tests"},
    )

    assert result.ok is True
    assert result.result["memory_candidate_created"] is True
    candidate_id = str(result.result["memory_candidate_id"])
    candidate = provider._memory_plane.get_record(candidate_id)
    assert candidate is not None
    assert candidate.domain == MemoryDomain.EPISODIC
    assert candidate.content["event_type"] == "outcome"
    assert candidate.content["outcome"] == "completed"
    assert candidate.content["work_state_status"] == "resolved"


def test_record_outcome_abandoned_marks_state_abandoned() -> None:
    work_state_service = WorkStateService()
    provider = ProviderMemoryService(work_state_service=work_state_service)
    created = work_state_service.open_or_resume_work(title="Deprecated path", task_id="task:outcome:abandoned")

    result = provider.handle_tool_call(
        "memorii_record_outcome",
        {"work_state_id": created.work_state_id, "outcome": "abandoned", "content": "No longer needed"},
    )

    assert result.ok is True
    assert result.result["status"] == "abandoned"


def test_record_outcome_blocked_marks_state_paused() -> None:
    work_state_service = WorkStateService()
    provider = ProviderMemoryService(work_state_service=work_state_service)
    created = work_state_service.open_or_resume_work(title="Blocked work", task_id="task:outcome:blocked")

    result = provider.handle_tool_call(
        "memorii_record_outcome",
        {"work_state_id": created.work_state_id, "outcome": "blocked", "content": "Waiting on dependency"},
    )

    assert result.ok is True
    assert result.result["status"] == "paused"


def test_record_outcome_needs_followup_keeps_state_active() -> None:
    work_state_service = WorkStateService()
    provider = ProviderMemoryService(work_state_service=work_state_service)
    created = work_state_service.open_or_resume_work(title="Followup needed", task_id="task:outcome:followup")

    result = provider.handle_tool_call(
        "memorii_record_outcome",
        {"work_state_id": created.work_state_id, "outcome": "needs_followup", "content": "Need another validation step"},
    )

    assert result.ok is True
    assert result.result["status"] == "active"


def test_record_progress_preserves_evidence_ids() -> None:
    work_state_service = WorkStateService()
    provider = ProviderMemoryService(work_state_service=work_state_service)
    created = work_state_service.open_or_resume_work(title="Evidence tracking", task_id="task:evidence")

    result = provider.handle_tool_call(
        "memorii_record_progress",
        {
            "work_state_id": created.work_state_id,
            "content": "Observed passing integration tests",
            "evidence_ids": ["test:integration:1", "artifact:log:2"],
        },
    )

    assert result.ok is True
    events = work_state_service.list_work_state_events(created.work_state_id)
    assert events[-1].evidence_ids == ["test:integration:1", "artifact:log:2"]


def test_record_progress_with_candidate_emission_disabled_returns_recorded_without_candidate() -> None:
    work_state_service = WorkStateService()
    provider = ProviderMemoryService(
        work_state_service=work_state_service,
        emit_work_state_event_candidates=False,
    )
    created = work_state_service.open_or_resume_work(title="No candidate", task_id="task:no-candidate")

    result = provider.handle_tool_call(
        "memorii_record_progress",
        {
            "work_state_id": created.work_state_id,
            "content": "Progress without candidate",
        },
    )

    assert result.ok is True
    assert result.result["memory_candidate_created"] is False
    assert "memory_candidate_error" not in result.result
    staged = provider._memory_plane.list_records(status=CommitStatus.CANDIDATE, domains=[MemoryDomain.EPISODIC])
    assert staged == []


class _FailingStageMemoryPlaneService(MemoryPlaneService):
    def stage_record(self, record: CanonicalMemoryRecord) -> None:
        raise RuntimeError("stage failure")


def test_record_progress_candidate_stage_failure_does_not_fail_tool_call() -> None:
    work_state_service = WorkStateService()
    provider = ProviderMemoryService(
        memory_plane=_FailingStageMemoryPlaneService(),
        work_state_service=work_state_service,
    )
    created = work_state_service.open_or_resume_work(title="Stage failure", task_id="task:stage-failure")

    result = provider.handle_tool_call(
        "memorii_record_progress",
        {
            "work_state_id": created.work_state_id,
            "content": "Progress survives candidate failure",
        },
    )

    assert result.ok is True
    assert result.result["recorded"] is True
    assert result.result["memory_candidate_created"] is False
    assert result.result["memory_candidate_error"] == "stage failure"


def test_record_progress_with_solver_run_binding_updates_resolution() -> None:
    work_state_service = WorkStateService()
    provider = ProviderMemoryService(work_state_service=work_state_service)
    created = work_state_service.open_or_resume_work(
        title="Binding update",
        task_id="task:binding:update",
        solver_run_id="solver:old",
    )

    result = provider.handle_tool_call(
        "memorii_record_progress",
        {
            "work_state_id": created.work_state_id,
            "content": "Progress with newer solver binding",
            "solver_run_id": "solver:new",
            "execution_node_id": "exec:new",
        },
    )

    assert result.ok is True
    assert work_state_service.resolve_solver_run_id(task_id="task:binding:update") == "solver:new"


def test_open_or_resume_creates_active_state() -> None:
    work_state_service = WorkStateService()
    provider = ProviderMemoryService(work_state_service=work_state_service)

    result = provider.handle_tool_call(
        "memorii_open_or_resume_work",
        {"title": "Implement parser updates", "kind": "task_execution", "task_id": "task:open:1"},
    )

    assert result.ok is True
    assert result.result["work_state"]["status"] == "active"
    states = work_state_service.list_states(task_id="task:open:1")
    assert len(states) == 1
    assert states[0].status == WorkStateStatus.ACTIVE
    assert result.result["decision_state_id"] is None


def test_open_or_resume_decision_work_creates_decision_state() -> None:
    work_state_service = WorkStateService()
    provider = ProviderMemoryService(work_state_service=work_state_service)

    result = provider.handle_tool_call(
        "memorii_open_or_resume_work",
        {"title": "Choose deployment strategy", "kind": "decision", "task_id": "task:decision:create"},
    )

    assert result.ok is True
    decision_state_id = result.result["decision_state_id"]
    assert isinstance(decision_state_id, str)
    assert decision_state_id


def test_open_or_resume_decision_reuses_existing_decision_state_without_duplicates() -> None:
    work_state_service = WorkStateService()
    decision_state_service = DecisionStateService()
    provider = ProviderMemoryService(
        work_state_service=work_state_service,
        decision_state_service=decision_state_service,
    )

    first = provider.handle_tool_call(
        "memorii_open_or_resume_work",
        {"title": "Pick API design", "kind": "decision", "task_id": "task:decision:reuse"},
    )
    second = provider.handle_tool_call(
        "memorii_open_or_resume_work",
        {"title": "Pick API design", "kind": "decision", "task_id": "task:decision:reuse"},
    )

    assert first.ok is True
    assert second.ok is True
    assert first.result["decision_state_id"] == second.result["decision_state_id"]
    decisions = decision_state_service.list_decisions(work_state_id=first.result["work_state"]["work_state_id"])
    assert len(decisions) == 1


def test_open_or_resume_resumes_existing_task_state_without_duplicate() -> None:
    work_state_service = WorkStateService()
    existing = work_state_service.open_or_resume_work(
        title="Old title",
        summary="Old summary",
        kind=WorkStateKind.TASK_EXECUTION,
        task_id="task:resume:1",
    )
    provider = ProviderMemoryService(work_state_service=work_state_service)

    result = provider.handle_tool_call(
        "memorii_open_or_resume_work",
        {
            "title": "New title",
            "summary": "New summary",
            "kind": "task_execution",
            "task_id": "task:resume:1",
        },
    )

    assert result.ok is True
    assert result.result["work_state"]["work_state_id"] == existing.work_state_id
    assert result.result["work_state"]["title"] == "New title"
    assert result.result["work_state"]["summary"] == "New summary"
    assert result.result["decision_state_id"] is None
    states = work_state_service.list_states(task_id="task:resume:1")
    assert len(states) == 1


def test_open_or_resume_explicit_work_state_id_updates_exact_state() -> None:
    work_state_service = WorkStateService()
    target = work_state_service.open_or_resume_work(
        title="Target",
        kind=WorkStateKind.INVESTIGATION,
        task_id="task:exact:original",
    )
    work_state_service.open_or_resume_work(
        title="Other",
        kind=WorkStateKind.INVESTIGATION,
        task_id="task:exact:other",
    )
    provider = ProviderMemoryService(work_state_service=work_state_service)

    result = provider.handle_tool_call(
        "memorii_open_or_resume_work",
        {
            "title": "Updated target",
            "summary": "Updated target summary",
            "kind": "investigation",
            "task_id": "task:exact:new",
            "work_state_id": target.work_state_id,
        },
    )

    assert result.ok is True
    assert result.result["work_state"]["work_state_id"] == target.work_state_id
    assert result.result["work_state"]["task_id"] == "task:exact:new"
    assert result.result["decision_state_id"] is None


def test_open_or_resume_decision_resume_by_work_state_id_reuses_decision_state() -> None:
    work_state_service = WorkStateService()
    decision_state_service = DecisionStateService()
    target = work_state_service.open_or_resume_work(
        title="Initial decision title",
        kind=WorkStateKind.DECISION,
        task_id="task:decision:explicit",
    )
    existing = decision_state_service.open_decision(
        question="Initial decision title",
        work_state_id=target.work_state_id,
        task_id="task:decision:explicit",
    )
    provider = ProviderMemoryService(
        work_state_service=work_state_service,
        decision_state_service=decision_state_service,
    )

    result = provider.handle_tool_call(
        "memorii_open_or_resume_work",
        {
            "title": "Updated decision title",
            "kind": "decision",
            "work_state_id": target.work_state_id,
            "task_id": "task:decision:explicit",
        },
    )

    assert result.ok is True
    assert result.result["decision_state_id"] == existing.decision_id
    decisions = decision_state_service.list_decisions(work_state_id=target.work_state_id)
    assert len(decisions) == 1


def test_open_or_resume_decision_with_disabled_decision_state_service_returns_none() -> None:
    work_state_service = WorkStateService()
    provider = ProviderMemoryService(
        work_state_service=work_state_service,
        decision_state_service=None,
    )

    result = provider.handle_tool_call(
        "memorii_open_or_resume_work",
        {"title": "Select rollout plan", "kind": "decision", "task_id": "task:decision:disabled"},
    )

    assert result.ok is True
    assert result.result["decision_state_id"] is None


def test_open_or_resume_creates_binding_when_solver_run_supplied() -> None:
    work_state_service = WorkStateService()
    provider = ProviderMemoryService(work_state_service=work_state_service)

    result = provider.handle_tool_call(
        "memorii_open_or_resume_work",
        {
            "title": "Bound task",
            "task_id": "task:binding:tool",
            "solver_run_id": "solver:binding:tool",
        },
    )

    assert result.ok is True
    assert result.result["binding"] is not None
    assert work_state_service.resolve_solver_run_id(task_id="task:binding:tool") == "solver:binding:tool"


def test_open_or_resume_binding_used_by_next_step_planner() -> None:
    solver_store = InMemorySolverGraphStore()
    overlay_store = InMemoryOverlayStore()
    solver_frontier_planner = SolverFrontierPlanner()
    work_state_service = WorkStateService()
    provider = ProviderMemoryService(
        work_state_service=work_state_service,
        solver_frontier_planner=solver_frontier_planner,
        solver_store=solver_store,
        overlay_store=overlay_store,
    )

    solver_run_id = "solver:open-resume-next-step"
    task_id = "task:open-resume-next-step"
    node_id = "node:open-resume-next-step"
    solver_store.create_solver_run(solver_run_id, "exec-1")
    solver_store.upsert_node(solver_run_id, _make_node(node_id, content={"next_best_test": "run planner via binding"}))
    _append_overlay(overlay_store, solver_run_id, [_overlay(node_id)])

    open_result = provider.handle_tool_call(
        "memorii_open_or_resume_work",
        {"title": "Open + bind", "task_id": task_id, "solver_run_id": solver_run_id},
    )
    assert open_result.ok is True

    next_step_result = provider.handle_tool_call("memorii_get_next_step", {"task_id": task_id})
    assert next_step_result.ok is True
    assert next_step_result.result["planner_used"] is True


def test_get_state_summary_with_matching_state_returns_state() -> None:
    work_state_service = WorkStateService()
    provider = ProviderMemoryService(work_state_service=work_state_service)

    provider.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="please implement parser updates and write tests",
        session_id="session:tool:1",
        task_id="task:tool:1",
        user_id="user:tool:1",
    )

    result = provider.handle_tool_call("memorii_get_state_summary", {"task_id": "task:tool:1"})

    assert result.ok is True
    assert result.result["state_count"] == 1
    work_states = result.result["work_states"]
    assert isinstance(work_states, list)
    assert work_states[0]["task_id"] == "task:tool:1"


def test_get_state_summary_includes_recent_work_state_events() -> None:
    work_state_service = WorkStateService()
    provider = ProviderMemoryService(work_state_service=work_state_service)
    created = work_state_service.open_or_resume_work(title="Summary events", task_id="task:tool:events")
    work_state_service.record_progress(work_state_id=created.work_state_id, content="Progress item for summary")

    result = provider.handle_tool_call("memorii_get_state_summary", {"task_id": "task:tool:events"})

    assert result.ok is True
    work_states = result.result["work_states"]
    assert isinstance(work_states, list)
    assert work_states[0]["recent_events"]
    assert work_states[0]["latest_progress"] == "Progress item for summary"
    assert "latest_outcome" in work_states[0]


def test_get_state_summary_for_decision_work_includes_decision_block_open() -> None:
    work_state_service = WorkStateService()
    decision_state_service = DecisionStateService()
    provider = ProviderMemoryService(work_state_service=work_state_service, decision_state_service=decision_state_service)
    work_state = work_state_service.open_or_resume_work(
        title="Select vector database",
        kind=WorkStateKind.DECISION,
        task_id="task:decision:summary:open",
    )
    decision = decision_state_service.open_decision(
        question="Which vector DB should we use?",
        work_state_id=work_state.work_state_id,
        task_id="task:decision:summary:open",
        unresolved_questions=["cost under sustained load"],
    )
    decision_state_service.add_option(decision_id=decision.decision_id, option_id="opt:qdrant", label="Qdrant")
    decision_state_service.add_option(decision_id=decision.decision_id, option_id="opt:weaviate", label="Weaviate")
    decision_state_service.add_criterion(decision_id=decision.decision_id, criterion_id="crit:latency", label="latency")
    decision_state_service.add_criterion(
        decision_id=decision.decision_id,
        criterion_id="crit:ops",
        label="operational simplicity",
    )
    decision_state_service.update_recommendation(decision_id=decision.decision_id, recommendation="Qdrant")

    result = provider.handle_tool_call("memorii_get_state_summary", {"task_id": "task:decision:summary:open"})

    assert result.ok is True
    summary = result.result["work_states"][0]["decision_state"]
    assert summary["question"] == "Which vector DB should we use?"
    assert summary["status"] == DecisionStatus.OPEN.value
    assert summary["option_labels"] == ["Qdrant", "Weaviate"]
    assert summary["criteria_labels"] == ["latency", "operational simplicity"]
    assert summary["recommendation"] == "Qdrant"
    assert summary["unresolved_questions"] == ["cost under sustained load"]


def test_get_state_summary_for_decision_work_includes_final_decision_when_decided() -> None:
    work_state_service = WorkStateService()
    decision_state_service = DecisionStateService()
    provider = ProviderMemoryService(work_state_service=work_state_service, decision_state_service=decision_state_service)
    work_state = work_state_service.open_or_resume_work(
        title="Select cache",
        kind=WorkStateKind.DECISION,
        task_id="task:decision:summary:decided",
    )
    decision = decision_state_service.open_decision(
        question="Which cache should we use?",
        work_state_id=work_state.work_state_id,
        task_id="task:decision:summary:decided",
    )
    decision_state_service.record_final_decision(decision_id=decision.decision_id, final_decision="Redis")

    result = provider.handle_tool_call("memorii_get_state_summary", {"task_id": "task:decision:summary:decided"})

    assert result.ok is True
    summary = result.result["work_states"][0]["decision_state"]
    assert summary["status"] == DecisionStatus.DECIDED.value
    assert summary["final_decision"] == "Redis"


def test_get_state_summary_for_decision_work_without_linked_decision_state_skips_section() -> None:
    work_state_service = WorkStateService()
    provider = ProviderMemoryService(work_state_service=work_state_service, decision_state_service=DecisionStateService())
    work_state_service.open_or_resume_work(
        title="Choose strategy",
        kind=WorkStateKind.DECISION,
        task_id="task:decision:summary:none",
    )

    result = provider.handle_tool_call("memorii_get_state_summary", {"task_id": "task:decision:summary:none"})

    assert result.ok is True
    assert result.result["work_states"][0]["decision_state"] is None


def test_get_state_summary_for_non_decision_work_remains_unchanged() -> None:
    work_state_service = WorkStateService()
    provider = ProviderMemoryService(work_state_service=work_state_service, decision_state_service=DecisionStateService())
    work_state_service.open_or_resume_work(
        title="Implement parser updates",
        kind=WorkStateKind.TASK_EXECUTION,
        task_id="task:summary:non-decision",
    )

    result = provider.handle_tool_call("memorii_get_state_summary", {"task_id": "task:summary:non-decision"})

    assert result.ok is True
    assert result.result["work_states"][0]["kind"] == WorkStateKind.TASK_EXECUTION.value
    assert result.result["work_states"][0]["decision_state"] is None


def test_get_state_summary_prefers_open_decision_when_open_and_decided_exist() -> None:
    work_state_service = WorkStateService()
    decision_state_service = DecisionStateService()
    provider = ProviderMemoryService(work_state_service=work_state_service, decision_state_service=decision_state_service)
    work_state = work_state_service.open_or_resume_work(
        title="Choose framework",
        kind=WorkStateKind.DECISION,
        task_id="task:decision:summary:prefer-open",
    )
    decided = decision_state_service.open_decision(
        question="Old decision",
        work_state_id=work_state.work_state_id,
        task_id="task:decision:summary:prefer-open",
    )
    decision_state_service.record_final_decision(decision_id=decided.decision_id, final_decision="Option A")
    decision_state_service.open_decision(
        question="Current decision",
        work_state_id=work_state.work_state_id,
        task_id="task:decision:summary:prefer-open",
    )

    result = provider.handle_tool_call("memorii_get_state_summary", {"task_id": "task:decision:summary:prefer-open"})

    assert result.ok is True
    summary = result.result["work_states"][0]["decision_state"]
    assert summary["question"] == "Current decision"
    assert summary["status"] == DecisionStatus.OPEN.value


def test_get_next_step_without_state_returns_ask_user_stub() -> None:
    provider = ProviderMemoryService()

    result = provider.handle_tool_call("memorii_get_next_step", {"task_id": "task:none"})

    assert result.ok is True
    next_step = result.result["next_step"]
    assert next_step["action_type"] == "ask_user"
    assert next_step["reason"] == "no_active_work_state"
    assert result.result["planner_used"] is False
    assert result.result["planner_reason"] == "no_solver_run_resolved"
    assert result.result["solver_run_resolution_source"] == "none"


def test_get_next_step_with_task_state_returns_continue_task_stub() -> None:
    work_state_service = WorkStateService()
    provider = ProviderMemoryService(work_state_service=work_state_service)

    provider.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="please implement parser updates and write tests",
        session_id="session:tool:2",
        task_id="task:tool:2",
        user_id="user:tool:2",
    )

    summary_result = provider.handle_tool_call("memorii_get_state_summary", {"task_id": "task:tool:2"})
    work_state_id = summary_result.result["work_states"][0]["work_state_id"]

    result = provider.handle_tool_call("memorii_get_next_step", {"task_id": "task:tool:2"})

    assert result.ok is True
    assert result.result["next_step"]["action_type"] == "continue_task"
    assert result.result["based_on_work_state_id"] == work_state_id


def test_get_next_step_with_investigation_state_returns_inspect_failure_stub() -> None:
    work_state_service = WorkStateService()
    provider = ProviderMemoryService(work_state_service=work_state_service)

    provider.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="build failed on CI while running tests",
        session_id="session:tool:3",
        task_id="task:tool:3",
        user_id="user:tool:3",
    )

    result = provider.handle_tool_call("memorii_get_next_step", {"task_id": "task:tool:3"})

    assert result.ok is True
    assert result.result["next_step"]["action_type"] == "inspect_failure"


def test_get_next_step_with_solver_run_and_no_planner_dependencies_falls_back() -> None:
    provider = ProviderMemoryService()

    result = provider.handle_tool_call("memorii_get_next_step", {"solver_run_id": "solver:missing", "task_id": "task:none"})

    assert result.ok is True
    assert result.result["planner_used"] is False
    assert result.result["planner_reason"] == "planner_not_configured"
    assert result.result["solver_run_resolution_source"] == "explicit"
    assert result.result["next_step"]["action_type"] == "ask_user"


def test_get_next_step_with_solver_run_and_no_frontier_falls_back() -> None:
    solver_store = InMemorySolverGraphStore()
    overlay_store = InMemoryOverlayStore()
    solver_frontier_planner = SolverFrontierPlanner()
    provider = ProviderMemoryService(
        solver_frontier_planner=solver_frontier_planner,
        solver_store=solver_store,
        overlay_store=overlay_store,
    )

    solver_store.create_solver_run("solver:no-frontier", "exec-1")
    result = provider.handle_tool_call("memorii_get_next_step", {"solver_run_id": "solver:no-frontier", "task_id": "task:none"})

    assert result.ok is True
    assert result.result["planner_used"] is False
    assert result.result["planner_reason"] == "no_frontier_found"
    assert result.result["solver_run_resolution_source"] == "explicit"
    assert result.result["next_step"]["action_type"] == "ask_user"


def test_get_next_step_returns_structured_frontier_action() -> None:
    solver_store = InMemorySolverGraphStore()
    overlay_store = InMemoryOverlayStore()
    solver_frontier_planner = SolverFrontierPlanner()
    provider = ProviderMemoryService(
        solver_frontier_planner=solver_frontier_planner,
        solver_store=solver_store,
        overlay_store=overlay_store,
    )

    solver_run_id = "solver:structured-next-step"
    node_id = "node:structured"
    solver_store.create_solver_run(solver_run_id, "exec-1")
    solver_store.upsert_node(
        solver_run_id,
        _make_node(
            node_id,
            content={
                "next_test_action": {
                    "action_type": "run_command",
                    "description": "Run targeted command with verbose mode",
                    "expected_evidence": "stderr includes timeout source",
                    "required_tool": "shell",
                }
            },
        ),
    )
    _append_overlay(overlay_store, solver_run_id, [_overlay(node_id)])

    result = provider.handle_tool_call("memorii_get_next_step", {"solver_run_id": solver_run_id})

    assert result.ok is True
    assert result.result["planner_used"] is True
    assert result.result["based_on_solver_node_id"] == node_id
    assert result.result["next_step"]["action_type"] == "run_command"
    assert result.result["next_step"]["description"] == "Run targeted command with verbose mode"
    assert result.result["next_step"]["expected_evidence"] == "stderr includes timeout source"
    assert result.result["next_step"]["required_tool"] == "shell"
    assert result.result["solver_run_resolution_source"] == "explicit"


def test_get_next_step_returns_legacy_frontier_action() -> None:
    solver_store = InMemorySolverGraphStore()
    overlay_store = InMemoryOverlayStore()
    solver_frontier_planner = SolverFrontierPlanner()
    provider = ProviderMemoryService(
        solver_frontier_planner=solver_frontier_planner,
        solver_store=solver_store,
        overlay_store=overlay_store,
    )

    solver_run_id = "solver:legacy-next-step"
    node_id = "node:legacy"
    solver_store.create_solver_run(solver_run_id, "exec-1")
    solver_store.upsert_node(solver_run_id, _make_node(node_id, content={"next_best_test": "rerun flaky test with seed"}))
    _append_overlay(overlay_store, solver_run_id, [_overlay(node_id)])

    result = provider.handle_tool_call("memorii_get_next_step", {"solver_run_id": solver_run_id})

    assert result.ok is True
    assert result.result["planner_used"] is True
    assert result.result["next_step"]["action_type"] == "run_test"
    assert result.result["next_step"]["description"] == "rerun flaky test with seed"
    assert result.result["solver_run_resolution_source"] == "explicit"


def test_get_next_step_returns_inspect_frontier_when_node_has_no_action() -> None:
    solver_store = InMemorySolverGraphStore()
    overlay_store = InMemoryOverlayStore()
    solver_frontier_planner = SolverFrontierPlanner()
    provider = ProviderMemoryService(
        solver_frontier_planner=solver_frontier_planner,
        solver_store=solver_store,
        overlay_store=overlay_store,
    )

    solver_run_id = "solver:inspect-frontier"
    node_id = "node:inspect"
    solver_store.create_solver_run(solver_run_id, "exec-1")
    solver_store.upsert_node(solver_run_id, _make_node(node_id, content={}))
    _append_overlay(overlay_store, solver_run_id, [_overlay(node_id)])

    result = provider.handle_tool_call("memorii_get_next_step", {"solver_run_id": solver_run_id})

    assert result.ok is True
    assert result.result["planner_used"] is True
    assert result.result["next_step"]["action_type"] == "inspect_frontier"
    assert result.result["solver_run_resolution_source"] == "explicit"


def test_get_next_step_uses_task_binding() -> None:
    solver_store = InMemorySolverGraphStore()
    overlay_store = InMemoryOverlayStore()
    solver_frontier_planner = SolverFrontierPlanner()
    work_state_service = WorkStateService()
    provider = ProviderMemoryService(
        work_state_service=work_state_service,
        solver_frontier_planner=solver_frontier_planner,
        solver_store=solver_store,
        overlay_store=overlay_store,
    )

    solver_run_id = "solver:task-binding"
    node_id = "node:task-binding"
    task_id = "task:binding:1"
    solver_store.create_solver_run(solver_run_id, "exec-1")
    solver_store.upsert_node(solver_run_id, _make_node(node_id, content={"next_best_test": "run task-bound test"}))
    _append_overlay(overlay_store, solver_run_id, [_overlay(node_id)])
    work_state_service.bind_state(task_id=task_id, solver_run_id=solver_run_id)

    result = provider.handle_tool_call("memorii_get_next_step", {"task_id": task_id})

    assert result.ok is True
    assert result.result["planner_used"] is True
    assert result.result["resolved_solver_run_id"] == solver_run_id
    assert result.result["solver_run_resolution_source"] == "task_binding"


def test_get_next_step_uses_session_binding() -> None:
    solver_store = InMemorySolverGraphStore()
    overlay_store = InMemoryOverlayStore()
    solver_frontier_planner = SolverFrontierPlanner()
    work_state_service = WorkStateService()
    provider = ProviderMemoryService(
        work_state_service=work_state_service,
        solver_frontier_planner=solver_frontier_planner,
        solver_store=solver_store,
        overlay_store=overlay_store,
    )

    solver_run_id = "solver:session-binding"
    node_id = "node:session-binding"
    session_id = "session:binding:1"
    solver_store.create_solver_run(solver_run_id, "exec-1")
    solver_store.upsert_node(solver_run_id, _make_node(node_id, content={"next_best_test": "run session-bound test"}))
    _append_overlay(overlay_store, solver_run_id, [_overlay(node_id)])
    work_state_service.bind_state(session_id=session_id, solver_run_id=solver_run_id)

    result = provider.handle_tool_call("memorii_get_next_step", {"session_id": session_id})

    assert result.ok is True
    assert result.result["planner_used"] is True
    assert result.result["resolved_solver_run_id"] == solver_run_id
    assert result.result["solver_run_resolution_source"] == "session_binding"


def test_get_next_step_explicit_solver_run_id_overrides_bindings() -> None:
    solver_store = InMemorySolverGraphStore()
    overlay_store = InMemoryOverlayStore()
    solver_frontier_planner = SolverFrontierPlanner()
    work_state_service = WorkStateService()
    provider = ProviderMemoryService(
        work_state_service=work_state_service,
        solver_frontier_planner=solver_frontier_planner,
        solver_store=solver_store,
        overlay_store=overlay_store,
    )

    explicit_solver_run_id = "solver:explicit-win"
    bound_solver_run_id = "solver:bound-lose"
    node_id = "node:explicit-win"
    task_id = "task:binding:override"
    solver_store.create_solver_run(explicit_solver_run_id, "exec-1")
    solver_store.upsert_node(explicit_solver_run_id, _make_node(node_id, content={"next_best_test": "run explicit test"}))
    _append_overlay(overlay_store, explicit_solver_run_id, [_overlay(node_id)])
    work_state_service.bind_state(task_id=task_id, solver_run_id=bound_solver_run_id)

    result = provider.handle_tool_call(
        "memorii_get_next_step",
        {"task_id": task_id, "solver_run_id": explicit_solver_run_id},
    )

    assert result.ok is True
    assert result.result["planner_used"] is True
    assert result.result["resolved_solver_run_id"] == explicit_solver_run_id
    assert result.result["solver_run_resolution_source"] == "explicit"


def test_get_next_step_without_binding_falls_back_with_no_solver_run_resolved() -> None:
    provider = ProviderMemoryService(work_state_service=WorkStateService())

    result = provider.handle_tool_call("memorii_get_next_step", {"task_id": "task:no-binding"})

    assert result.ok is True
    assert result.result["planner_used"] is False
    assert result.result["planner_reason"] == "no_solver_run_resolved"
