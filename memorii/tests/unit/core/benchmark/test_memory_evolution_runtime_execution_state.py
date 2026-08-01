from __future__ import annotations

from dataclasses import dataclass

from memorii.core.benchmark.memory_evolution_runtime import (
    normalize_action_status,
    project_runtime_checkpoint,
    runtime_failure_buckets,
)
from memorii.core.benchmark.memory_evolution_runtime.models import RuntimeGraphItemRow
from memorii.core.benchmark.memory_evolution_sim import LatentGraphScenario
from memorii.core.memory_evolution.execution import (
    ActionEventType,
    ContinuationDecision,
    ContinuationResolutionStatus,
    WorkState,
    WorkStateSnapshot,
    WorkStateStatus,
)
from memorii.core.memory_evolution.models import MemoryGraphSnapshot
from memorii.core.memory_evolution.retrieval_contracts import (
    ProductionRetrievalDecision,
    ScopedExecutionView,
    SemanticFrameStatus,
)
from memorii.core.memory_evolution.temporal_contracts import QueryTemporalFrame, QueryTemporalKind
from tests.unit.core.benchmark.memory_evolution_runtime_test_helpers import (
    action_claim_by_state,
    claim_event_id,
    long_horizon_execution_scenario,
    runtime_action,
    runtime_execution_base_items,
)


@dataclass(frozen=True)
class _ExecutionOracle:
    progress_claim_id: str
    progress_event_id: str
    blocked_claim_id: str
    blocked_event_id: str
    blocked_entity_id: str
    branch_a_started_event_id: str
    branch_b_started_event_id: str


def _execution_oracle(scenario: LatentGraphScenario) -> _ExecutionOracle:
    progress = action_claim_by_state(scenario, "in_progress", subject_name="Atlas Cleanup Branch B")
    blocked = action_claim_by_state(scenario, "blocked", subject_name="Atlas Cleanup Branch A")
    branch_a_started = action_claim_by_state(scenario, "started", subject_name="Atlas Cleanup Branch A")
    branch_b_started = action_claim_by_state(scenario, "started", subject_name="Atlas Cleanup Branch B")
    return _ExecutionOracle(
        progress_claim_id=progress.claim_id,
        progress_event_id=claim_event_id(progress),
        blocked_claim_id=blocked.claim_id,
        blocked_event_id=claim_event_id(blocked),
        blocked_entity_id=blocked.subject.entity_id,
        branch_a_started_event_id=claim_event_id(branch_a_started),
        branch_b_started_event_id=claim_event_id(branch_b_started),
    )


def _decision_for_action(
    graph_items: list[RuntimeGraphItemRow], *, status: str = "in_progress"
) -> ProductionRetrievalDecision:
    action = next(
        item
        for item in graph_items
        if item.item_type == "action" and (item.status == status or item.action_type == status)
    )
    action_id = action.action_id
    target = next(iter(action.target_entity_ids))
    suppressed = sorted(
        {
            str(target_id)
            for item in graph_items
            if item.item_type == "action"
            for target_id in item.target_entity_ids
            if target_id != target
        }
    )
    return ProductionRetrievalDecision(
        query="continue the previous fix",
        semantic_frame_status=SemanticFrameStatus.MATCHED,
        temporal_frame=QueryTemporalFrame(temporal_kind=QueryTemporalKind.EXECUTION),
        selected_record_ids=[action_id.removeprefix("action:")],
        supporting_record_ids=[action_id.removeprefix("action:")],
        execution_state=ScopedExecutionView(
            work_state=WorkStateSnapshot(
                states=[
                    WorkState(
                        branch_id=target,
                        scope_key="global",
                        status=WorkStateStatus.IN_PROGRESS,
                        active=True,
                        last_event_id=action_id,
                        last_event_type=ActionEventType.PROGRESS,
                    )
                ],
                active_branch_ids=[target],
                suppressed_branch_ids=suppressed,
            ),
            continuation=ContinuationDecision(
                status=ContinuationResolutionStatus.RESOLVED,
                branch_id=target,
                candidate_branch_ids=[target],
                rationale="test",
            ),
            readable_action_event_ids=[action_id],
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
    oracle = _execution_oracle(scenario)
    graph_items = [
        *runtime_execution_base_items(scenario=scenario),
        runtime_action(target="runtime:branch-b", status="in_progress", events=[oracle.progress_event_id]),
        runtime_action(
            target="runtime:branch-a", status="started", events=[oracle.branch_a_started_event_id]
        ),
        runtime_action(target="runtime:branch-a", status="blocked", events=[oracle.blocked_event_id]),
    ]

    projection = project_runtime_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
        graph_snapshot=MemoryGraphSnapshot(snapshot_id="test"),
        graph_items=graph_items,
        source_id_to_event_id={},
        retrieval_decision=_decision_for_action(graph_items),
    )

    assert oracle.progress_claim_id in projection.output.selected_claim_ids
    assert oracle.progress_claim_id in projection.output.supporting_claim_ids
    assert oracle.progress_event_id in projection.output.supporting_citation_event_ids
    assert oracle.blocked_claim_id not in projection.output.rejected_claim_ids
    assert oracle.blocked_entity_id not in projection.output.rejected_entity_ids
    assert projection.execution_state.active_continuation_branch == "runtime:branch-b"
    assert "runtime:branch-a" in projection.execution_state.suppressed_branch_ids


def test_runtime_projection_never_selects_an_action_without_production_decision() -> None:
    scenario, checkpoint = long_horizon_execution_scenario()
    oracle = _execution_oracle(scenario)
    graph_items = [
        *runtime_execution_base_items(scenario=scenario),
        runtime_action(target="runtime:branch-b", status="in_progress", events=[oracle.progress_event_id]),
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
    assert projection.execution_state.status == "unavailable"
    assert projection.execution_state.reason == "production_retrieval_decision_required"


def test_runtime_projection_does_not_count_unselected_aligned_action_as_support() -> None:
    scenario, checkpoint = long_horizon_execution_scenario()
    oracle = _execution_oracle(scenario)
    graph_items = [
        *runtime_execution_base_items(scenario=scenario),
        runtime_action(target="runtime:branch-b", status="in_progress", events=[oracle.progress_event_id]),
    ]

    projection = project_runtime_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
        graph_snapshot=MemoryGraphSnapshot(snapshot_id="test"),
        graph_items=graph_items,
        source_id_to_event_id={},
        retrieval_decision=ProductionRetrievalDecision(
            query="continue the previous fix",
            semantic_frame_status=SemanticFrameStatus.MATCHED,
            temporal_frame=QueryTemporalFrame(temporal_kind=QueryTemporalKind.EXECUTION),
            selected_record_ids=["action:unrelated"],
            supporting_record_ids=["action:unrelated"],
        ),
    )

    assert projection.action_support == {}
    assert projection.output.supporting_citation_event_ids == []
    assert "production_retrieval_missing_expected_action" in runtime_failure_buckets(
        checkpoint=checkpoint,
        output=projection.output,
        projection=projection,
        graph_snapshot=projection.graph_snapshot,
    )


def test_runtime_execution_projection_derives_active_progress_from_action_type() -> None:
    scenario, checkpoint = long_horizon_execution_scenario()
    oracle = _execution_oracle(scenario)
    graph_items = [
        *runtime_execution_base_items(scenario=scenario),
        runtime_action(
            target="runtime:branch-b",
            status="started",
            action_type="in_progress",
            events=[oracle.progress_event_id],
        ),
        runtime_action(target="runtime:branch-a", status="blocked", events=[oracle.blocked_event_id]),
    ]

    projection = project_runtime_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
        graph_snapshot=MemoryGraphSnapshot(snapshot_id="test"),
        graph_items=graph_items,
        source_id_to_event_id={},
        retrieval_decision=_decision_for_action(graph_items),
    )

    assert projection.action_support[f"action:{oracle.progress_claim_id}"] == "runtime_action_semantic"
    assert oracle.progress_claim_id in projection.output.selected_claim_ids
    assert oracle.progress_event_id in projection.output.supporting_citation_event_ids
    assert projection.execution_state.active_continuation_branch == "runtime:branch-b"
    assert projection.execution_state.continuation_decision is not None
    assert projection.execution_state.continuation_decision.status == "resolved"


def test_runtime_execution_projection_accepts_opaque_targets_through_entity_alignment() -> None:
    scenario, checkpoint = long_horizon_execution_scenario()
    oracle = _execution_oracle(scenario)
    graph_items = [
        *runtime_execution_base_items(scenario=scenario),
        runtime_action(target="runtime:branch-b", status="in_progress", events=[oracle.progress_event_id]),
        runtime_action(target="runtime:branch-a", status="blocked", events=[oracle.blocked_event_id]),
    ]

    projection = project_runtime_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
        graph_snapshot=MemoryGraphSnapshot(snapshot_id="test"),
        graph_items=graph_items,
        source_id_to_event_id={},
        retrieval_decision=_decision_for_action(graph_items),
    )

    assert projection.action_support[f"action:{oracle.progress_claim_id}"] == "runtime_action_semantic"
    assert oracle.progress_claim_id in projection.output.selected_claim_ids
    assert oracle.blocked_claim_id not in projection.output.rejected_claim_ids
    assert oracle.blocked_entity_id not in projection.output.rejected_entity_ids
    assert projection.execution_state.active_continuation_branch == "runtime:branch-b"
    assert projection.execution_state.suppressed_branch_ids == ["runtime:branch-a"]


def test_runtime_execution_projection_bridges_subtask_progress_to_active_branch() -> None:
    scenario, checkpoint = long_horizon_execution_scenario()
    oracle = _execution_oracle(scenario)
    graph_items = [
        *runtime_execution_base_items(scenario=scenario, branch_b_events=[oracle.branch_b_started_event_id]),
        runtime_action(
            target="runtime:branch-b", status="started", events=[oracle.branch_b_started_event_id]
        ),
        runtime_action(
            target="ent:org-directory-owner-cleanup", status="in_progress", events=[oracle.progress_event_id]
        ),
        runtime_action(target="runtime:branch-a", status="blocked", events=[oracle.blocked_event_id]),
    ]

    projection = project_runtime_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
        graph_snapshot=MemoryGraphSnapshot(snapshot_id="test"),
        graph_items=graph_items,
        source_id_to_event_id={},
        retrieval_decision=_decision_for_action(graph_items),
    )

    assert projection.action_support[f"action:{oracle.progress_claim_id}"] == "runtime_action_work_state_bridge"
    assert oracle.progress_claim_id in projection.output.selected_claim_ids
    assert oracle.progress_event_id in projection.output.supporting_citation_event_ids
    assert oracle.blocked_claim_id not in projection.output.rejected_claim_ids
    assert oracle.blocked_entity_id not in projection.output.rejected_entity_ids
    assert projection.execution_state.active_continuation_branch == "ent:org-directory-owner-cleanup"
    assert projection.execution_state.suppressed_branch_ids == [
        "runtime:branch-a",
        "runtime:branch-b",
    ]
    assert projection.action_alignment_rows[0].bridged_target_entity_id == checkpoint.expected_execution_entity_ids[0]


def test_hidden_expected_rejections_cannot_author_runtime_output() -> None:
    scenario, checkpoint = long_horizon_execution_scenario()
    oracle = _execution_oracle(scenario)
    graph_items = [
        *runtime_execution_base_items(scenario=scenario),
        runtime_action(target="runtime:branch-b", status="in_progress", events=[oracle.progress_event_id]),
        runtime_action(target="runtime:branch-a", status="blocked", events=[oracle.blocked_event_id]),
    ]
    decision = _decision_for_action(graph_items)

    original = project_runtime_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
        graph_snapshot=MemoryGraphSnapshot(snapshot_id="test"),
        graph_items=graph_items,
        source_id_to_event_id={},
        retrieval_decision=decision,
    )
    mutated = project_runtime_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint.model_copy(update={"expected_excluded_claim_ids": []}),
        graph_snapshot=MemoryGraphSnapshot(snapshot_id="test"),
        graph_items=graph_items,
        source_id_to_event_id={},
        retrieval_decision=decision,
    )

    assert mutated.output == original.output
    assert mutated.production_channels == original.production_channels

    without_expected_actions = project_runtime_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint.model_copy(update={"expected_action_ids": []}),
        graph_snapshot=MemoryGraphSnapshot(snapshot_id="test"),
        graph_items=graph_items,
        source_id_to_event_id={},
        retrieval_decision=decision,
    )

    assert without_expected_actions.production_channels == original.production_channels
    assert any(
        row.verdict == "unmatched_runtime"
        and row.runtime_action_id in without_expected_actions.production_channels.selected_action_ids
        for row in without_expected_actions.action_alignment_rows
    )
    assert "production_retrieval_unexpected_selected_action" in runtime_failure_buckets(
        checkpoint=checkpoint.model_copy(update={"expected_action_ids": []}),
        output=without_expected_actions.output,
        projection=without_expected_actions,
        graph_snapshot=without_expected_actions.graph_snapshot,
    )


def test_runtime_execution_projection_does_not_bridge_subtask_without_branch_history() -> None:
    scenario, checkpoint = long_horizon_execution_scenario()
    oracle = _execution_oracle(scenario)
    base_items = runtime_execution_base_items(scenario=scenario)
    graph_items = [
        *base_items[:1],
        *base_items[2:],
        runtime_action(
            target="ent:org-directory-owner-cleanup", status="in_progress", events=[oracle.progress_event_id]
        ),
    ]

    projection = project_runtime_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
        graph_snapshot=MemoryGraphSnapshot(snapshot_id="test"),
        graph_items=graph_items,
        source_id_to_event_id={},
    )

    assert f"action:{oracle.progress_claim_id}" not in projection.action_support
    assert oracle.progress_claim_id not in projection.output.selected_claim_ids


def test_runtime_execution_projection_does_not_reject_active_or_wrong_branch() -> None:
    scenario, checkpoint = long_horizon_execution_scenario()
    oracle = _execution_oracle(scenario)
    base_items = [
        *runtime_execution_base_items(scenario=scenario),
        runtime_action(target="runtime:branch-b", status="in_progress", events=[oracle.progress_event_id]),
    ]

    active_branch_a = project_runtime_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
        graph_snapshot=MemoryGraphSnapshot(snapshot_id="test"),
        graph_items=[
            *base_items,
            runtime_action(target="runtime:branch-a", status="in_progress", events=[oracle.blocked_event_id]),
        ],
        source_id_to_event_id={},
    )
    wrong_branch = project_runtime_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
        graph_snapshot=MemoryGraphSnapshot(snapshot_id="test"),
        graph_items=[
            *base_items,
            runtime_action(target="ent:branch-c", status="blocked", events=[oracle.blocked_event_id]),
        ],
        source_id_to_event_id={},
    )

    assert oracle.blocked_claim_id not in active_branch_a.output.rejected_claim_ids
    assert oracle.blocked_claim_id not in wrong_branch.output.rejected_claim_ids
