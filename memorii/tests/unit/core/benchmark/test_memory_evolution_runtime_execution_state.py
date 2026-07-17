from __future__ import annotations

from memorii.core.benchmark.memory_evolution_runtime import (
    normalize_action_status,
    project_runtime_checkpoint,
)
from memorii.core.memory_evolution.execution import (
    ContinuationDecision,
    ContinuationResolutionStatus,
    WorkStateSnapshot,
)
from memorii.core.memory_evolution.models import MemoryGraphSnapshot
from memorii.core.memory_evolution.retrieval import ExecutionRetrievalState, ProductionRetrievalDecision
from memorii.core.memory_evolution.temporal import QueryTemporalFrame, QueryTemporalKind
from tests.unit.core.benchmark.memory_evolution_runtime_test_helpers import (
    long_horizon_execution_scenario,
    runtime_action,
    runtime_execution_base_items,
)


def _decision_for_action(graph_items: list[dict[str, object]], *, status: str = "in_progress") -> ProductionRetrievalDecision:
    action = next(
        item
        for item in graph_items
        if item.get("item_type") == "action"
        and (item.get("status") == status or item.get("action_type") == status)
    )
    action_id = str(action["action_id"])
    target = str(next(iter(action["target_entity_ids"])))
    suppressed = sorted(
        {
            str(target_id)
            for item in graph_items
            if item.get("item_type") == "action"
            for target_id in item.get("target_entity_ids", [])
            if str(target_id) != target
        }
    )
    return ProductionRetrievalDecision(
        query="continue the previous fix",
        temporal_frame=QueryTemporalFrame(temporal_kind=QueryTemporalKind.EXECUTION),
        selected_record_ids=[action_id.removeprefix("action:")],
        supporting_record_ids=[action_id.removeprefix("action:")],
        execution_state=ExecutionRetrievalState(
            work_state=WorkStateSnapshot(
                active_branch_ids=[target],
                suppressed_branch_ids=suppressed,
            ),
            continuation=ContinuationDecision(
                status=ContinuationResolutionStatus.RESOLVED,
                branch_id=target,
                candidate_branch_ids=[target],
                rationale="test",
            ),
        ),
    )


def test_action_status_normalization_uses_stable_execution_states() -> None:
    assert normalize_action_status("in progress") == "in_progress"
    assert normalize_action_status("in_progress") == "in_progress"
    assert normalize_action_status("progressed") == "in_progress"
    assert normalize_action_status("start") == "started"
    assert normalize_action_status("stuck") == "blocked"
    assert normalize_action_status("waiting_on_review") == "waiting_on_review"


def test_runtime_execution_projection_selects_action_backed_continuation_state() -> None:
    scenario, checkpoint = long_horizon_execution_scenario()
    graph_items = [
        *runtime_execution_base_items(scenario_id=scenario.scenario_id),
        runtime_action(target="ent:atlas-cleanup-branch-b", status="in_progress", events=["event_09_branch_b_progress"]),
        runtime_action(target="ent:atlas-cleanup-branch-a", status="started", events=["event_09_branch_a_started"]),
        runtime_action(target="ent:atlas-cleanup", status="blocked", events=["event_09_branch_a_blocked"]),
    ]

    projection = project_runtime_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
        graph_snapshot=MemoryGraphSnapshot(snapshot_id="test"),
        graph_items=graph_items,
        source_id_to_event_id={},
        retrieval_decision=_decision_for_action(graph_items),
    )

    assert "claim_09_branch_b_progress" in projection.output.selected_claim_ids
    assert "claim_09_branch_b_progress" in projection.output.supporting_claim_ids
    assert "event_09_branch_b_progress" in projection.output.supporting_citation_event_ids
    assert "claim_09_branch_a_blocked" in projection.output.rejected_claim_ids
    assert "ent_09_branch_a" in projection.output.rejected_entity_ids
    assert projection.execution_state["active_continuation_branch"] == "ent:atlas-cleanup-branch-b"
    assert "ent:atlas-cleanup-branch-a" in projection.execution_state["suppressed_branch_ids"]


def test_runtime_projection_never_selects_an_action_without_production_decision() -> None:
    scenario, checkpoint = long_horizon_execution_scenario()
    graph_items = [
        *runtime_execution_base_items(scenario_id=scenario.scenario_id),
        runtime_action(target="ent:atlas-cleanup-branch-b", status="in_progress", events=["event_09_branch_b_progress"]),
    ]

    projection = project_runtime_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
        graph_snapshot=MemoryGraphSnapshot(snapshot_id="test"),
        graph_items=graph_items,
        source_id_to_event_id={},
    )

    assert projection.output.selected_claim_ids == []
    assert projection.output.supporting_claim_ids == []
    assert projection.execution_state["status"] == "unavailable"
    assert projection.execution_state["reason"] == "production_retrieval_decision_required"


def test_runtime_projection_does_not_count_unselected_aligned_action_as_support() -> None:
    scenario, checkpoint = long_horizon_execution_scenario()
    graph_items = [
        *runtime_execution_base_items(scenario_id=scenario.scenario_id),
        runtime_action(target="ent:atlas-cleanup-branch-b", status="in_progress", events=["event_09_branch_b_progress"]),
    ]

    projection = project_runtime_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
        graph_snapshot=MemoryGraphSnapshot(snapshot_id="test"),
        graph_items=graph_items,
        source_id_to_event_id={},
        retrieval_decision=ProductionRetrievalDecision(
            query="continue the previous fix",
            temporal_frame=QueryTemporalFrame(temporal_kind=QueryTemporalKind.EXECUTION),
            selected_record_ids=["action:unrelated"],
            supporting_record_ids=["action:unrelated"],
        ),
    )

    assert projection.action_support == {}
    assert projection.output.supporting_citation_event_ids == []


def test_runtime_execution_projection_derives_active_progress_from_action_type() -> None:
    scenario, checkpoint = long_horizon_execution_scenario()
    graph_items = [
        *runtime_execution_base_items(scenario_id=scenario.scenario_id),
        runtime_action(
            target="ent:atlas-cleanup-branch-b",
            status="started",
            action_type="in_progress",
            events=["event_09_branch_b_progress"],
        ),
        runtime_action(target="ent:atlas-cleanup-branch-a", status="blocked", events=["event_09_branch_a_blocked"]),
    ]

    projection = project_runtime_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
        graph_snapshot=MemoryGraphSnapshot(snapshot_id="test"),
        graph_items=graph_items,
        source_id_to_event_id={},
        retrieval_decision=_decision_for_action(graph_items),
    )

    assert projection.action_support["action:claim_09_branch_b_progress"] == "runtime_action_semantic"
    assert "claim_09_branch_b_progress" in projection.output.selected_claim_ids
    assert "event_09_branch_b_progress" in projection.output.supporting_citation_event_ids
    assert projection.execution_state["active_continuation_branch"] == "ent:atlas-cleanup-branch-b"
    assert projection.execution_state["continuation_decision"]["status"] == "resolved"


def test_runtime_execution_projection_rejects_semantic_short_branch_id() -> None:
    scenario, checkpoint = long_horizon_execution_scenario()
    graph_items = [
        *runtime_execution_base_items(scenario_id=scenario.scenario_id),
        runtime_action(target="ent:branch-b", status="in_progress", events=["event_09_branch_b_progress"]),
        runtime_action(target="ent:branch-a", status="blocked", events=["event_09_branch_a_blocked"]),
    ]

    projection = project_runtime_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
        graph_snapshot=MemoryGraphSnapshot(snapshot_id="test"),
        graph_items=graph_items,
        source_id_to_event_id={},
        retrieval_decision=_decision_for_action(graph_items),
    )

    assert projection.action_support["action:claim_09_branch_b_progress"] == "runtime_action_semantic"
    assert "claim_09_branch_b_progress" in projection.output.selected_claim_ids
    assert "claim_09_branch_a_blocked" in projection.output.rejected_claim_ids
    assert "ent_09_branch_a" in projection.output.rejected_entity_ids
    assert projection.execution_state["active_continuation_branch"] == "ent:branch-b"
    assert projection.execution_state["suppressed_branch_ids"] == ["ent:branch-a"]


def test_runtime_execution_projection_bridges_subtask_progress_to_active_branch() -> None:
    scenario, checkpoint = long_horizon_execution_scenario()
    graph_items = [
        *runtime_execution_base_items(scenario_id=scenario.scenario_id, branch_b_events=["event_09_branch_b_started"]),
        runtime_action(target="ent:atlas-cleanup-branch-b", status="started", events=["event_09_branch_b_started"]),
        runtime_action(target="ent:org-directory-owner-cleanup", status="in_progress", events=["event_09_branch_b_progress"]),
        runtime_action(target="ent:atlas-cleanup-branch-a", status="blocked", events=["event_09_branch_a_blocked"]),
    ]

    projection = project_runtime_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
        graph_snapshot=MemoryGraphSnapshot(snapshot_id="test"),
        graph_items=graph_items,
        source_id_to_event_id={},
        retrieval_decision=_decision_for_action(graph_items),
    )

    assert projection.action_support["action:claim_09_branch_b_progress"] == "runtime_action_work_state_bridge"
    assert "claim_09_branch_b_progress" in projection.output.selected_claim_ids
    assert "event_09_branch_b_progress" in projection.output.supporting_citation_event_ids
    assert "claim_09_branch_a_blocked" in projection.output.rejected_claim_ids
    assert "ent_09_branch_a" in projection.output.rejected_entity_ids
    assert projection.execution_state["active_continuation_branch"] == "ent:org-directory-owner-cleanup"
    assert projection.execution_state["suppressed_branch_ids"] == ["ent:atlas-cleanup-branch-a", "ent:atlas-cleanup-branch-b"]
    assert projection.action_alignment_rows[0]["bridged_target_entity_id"] == "ent_09_branch_b"


def test_runtime_execution_projection_does_not_bridge_subtask_without_branch_history() -> None:
    scenario, checkpoint = long_horizon_execution_scenario()
    base_items = runtime_execution_base_items(scenario_id=scenario.scenario_id)
    graph_items = [
        *base_items[:1],
        *base_items[2:],
        runtime_action(target="ent:org-directory-owner-cleanup", status="in_progress", events=["event_09_branch_b_progress"]),
    ]

    projection = project_runtime_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
        graph_snapshot=MemoryGraphSnapshot(snapshot_id="test"),
        graph_items=graph_items,
        source_id_to_event_id={},
    )

    assert "action:claim_09_branch_b_progress" not in projection.action_support
    assert "claim_09_branch_b_progress" not in projection.output.selected_claim_ids


def test_runtime_execution_projection_does_not_reject_active_or_wrong_branch() -> None:
    scenario, checkpoint = long_horizon_execution_scenario()
    base_items = [
        *runtime_execution_base_items(scenario_id=scenario.scenario_id),
        runtime_action(target="ent:branch-b", status="in_progress", events=["event_09_branch_b_progress"]),
    ]

    active_branch_a = project_runtime_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
        graph_snapshot=MemoryGraphSnapshot(snapshot_id="test"),
        graph_items=[*base_items, runtime_action(target="ent:branch-a", status="in_progress", events=["event_09_branch_a_blocked"])],
        source_id_to_event_id={},
    )
    wrong_branch = project_runtime_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
        graph_snapshot=MemoryGraphSnapshot(snapshot_id="test"),
        graph_items=[*base_items, runtime_action(target="ent:branch-c", status="blocked", events=["event_09_branch_a_blocked"])],
        source_id_to_event_id={},
    )

    assert "claim_09_branch_a_blocked" not in active_branch_a.output.rejected_claim_ids
    assert "claim_09_branch_a_blocked" not in wrong_branch.output.rejected_claim_ids
