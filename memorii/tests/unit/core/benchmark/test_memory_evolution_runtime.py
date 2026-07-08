from memorii.core.benchmark.memory_evolution_runtime import (
    RuntimeSuiteRows,
    _expected_action_alignment_rows,
    align_runtime_graph_to_oracle,
    normalize_action_status,
    project_runtime_checkpoint,
    runtime_graph_completeness_metrics,
    runtime_summary_metrics,
)
from memorii.core.benchmark.memory_evolution_sim import generate_memory_evolution_sim_scenarios
from memorii.core.memory_evolution.models import MemoryGraphSnapshot


def _runtime_entity(*, scenario_id: str, runtime_id: str, canonical_id: str, name: str, entity_type: str, aliases: list[str], events: list[str]) -> dict[str, object]:
    return {
        "scenario_id": scenario_id,
        "runtime_item_id": runtime_id,
        "item_type": "entity",
        "canonical_name": name,
        "canonical_id": canonical_id,
        "entity_type": entity_type,
        "aliases": aliases,
        "lifecycle_state": "active",
        "confidence": 0.9,
        "evidence_event_ids": events,
    }


def _runtime_claim(*, scenario_id: str, runtime_id: str, subject_id: str, subject: str, predicate: str, obj: str, event: str) -> dict[str, object]:
    return {
        "scenario_id": scenario_id,
        "runtime_item_id": runtime_id,
        "item_type": "claim",
        "claim_id": runtime_id,
        "subject": subject,
        "subject_entity_id": subject_id,
        "predicate": predicate,
        "object": obj,
        "object_value": obj,
        "scope": "global",
        "valid_from": "",
        "valid_to": "",
        "lifecycle_state": "active",
        "confidence": 0.9,
        "evidence_event_ids": [event],
    }


def _alignment_for(alignments, oracle_id: str):
    return next(item for item in alignments if item.oracle_item_id == oracle_id and item.item_type == "claim")


def _long_horizon_execution_scenario():
    scenarios = generate_memory_evolution_sim_scenarios(
        profile="long_horizon",
        scenario_count=10,
        seed=7,
        min_events=25,
        max_events=60,
        noise_rate=0.35,
    )
    scenario = next(item for item in scenarios if item.family == "abandoned_then_resumed_work")
    return scenario, scenario.checkpoints[0]


def _runtime_action(*, target: str, status: str, events: list[str]) -> dict[str, object]:
    return {
        "scenario_id": "sim_09_abandoned_then_resumed_work",
        "runtime_item_id": f"graph:node:action:uuid-{target}-{status}",
        "item_type": "action",
        "action_id": f"action:uuid-{target}-{status}",
        "action_type": "update_status",
        "status": status,
        "target_entity_ids": [target],
        "lifecycle_state": "active",
        "confidence": 0.8,
        "evidence_event_ids": events,
    }


def test_runtime_claim_alignment_uses_entity_alias_for_service_owner() -> None:
    scenario = generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=1, seed=7)[0]
    graph_items = [
        _runtime_entity(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:entity:atlas-service",
            canonical_id="ent:atlas-service",
            name="atlas service",
            entity_type="service",
            aliases=["Atlas service"],
            events=["event_00_003"],
        ),
        _runtime_claim(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:claim:service-owner",
            subject_id="ent:atlas-service",
            subject="atlas service",
            predicate="owner",
            obj="Iris",
            event="event_00_003",
        ),
    ]

    alignments = align_runtime_graph_to_oracle(scenario=scenario, graph_items=graph_items)

    service_owner = _alignment_for(alignments, "claim_00_service_owner")
    ambiguous_project_owner = _alignment_for(alignments, "claim_00_ambiguous_service_owner_atlas")
    assert service_owner.verdict.value == "aligned"
    assert "subject_entity" in service_owner.matched_on
    assert ambiguous_project_owner.verdict.value != "aligned"


def test_runtime_claim_alignment_uses_atlas_alias_for_historical_project_owner() -> None:
    scenario = generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=2, seed=7)[1]
    graph_items = [
        _runtime_entity(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:entity:atlas",
            canonical_id="ent:atlas",
            name="atlas",
            entity_type="unknown",
            aliases=["Atlas"],
            events=["event_01_002"],
        ),
        _runtime_claim(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:claim:previous-owner",
            subject_id="ent:atlas",
            subject="atlas",
            predicate="owner",
            obj="Alice",
            event="event_01_002",
        ),
    ]

    alignments = align_runtime_graph_to_oracle(scenario=scenario, graph_items=graph_items)

    previous_owner = _alignment_for(alignments, "claim_01_previous_owner_old")
    assert previous_owner.verdict.value == "aligned"
    assert "subject_entity" in previous_owner.matched_on


def test_runtime_summary_reports_long_horizon_slice_counts() -> None:
    rows = RuntimeSuiteRows(
        scenario_rows=[],
        checkpoint_rows=[
            {
                "checkpoint_type": "current_truth",
                "phase": "checkpoint",
                "horizon_distance_bucket": "long",
                "interference_count_bucket": "medium",
                "source_event_age_days_bucket": "old",
                "required_retrieval_view": "current",
                "runtime_failure_buckets": [],
                "failure_buckets": [],
                "verdict": "pass",
                "review_required": False,
            }
        ],
        judge_rows=[],
        llm_rows=[],
    )

    summary = runtime_summary_metrics(rows)

    assert summary["long_horizon_slice_counts"]["horizon_distance_bucket"] == {"long": 1}
    assert summary["long_horizon_slice_counts"]["interference_count_bucket"] == {"medium": 1}
    assert summary["runtime_graph_alignments_summary"]["checkpoint_scored_verdict_counts"] == {"pass": 1}


def test_action_status_normalization_uses_stable_execution_states() -> None:
    assert normalize_action_status("in progress") == "in_progress"
    assert normalize_action_status("in_progress") == "in_progress"
    assert normalize_action_status("progressed") == "in_progress"
    assert normalize_action_status("start") == "started"
    assert normalize_action_status("stuck") == "blocked"
    assert normalize_action_status("waiting_on_review") == "waiting_on_review"


def test_runtime_action_semantically_aligns_to_oracle_action_with_native_id() -> None:
    scenario, checkpoint = _long_horizon_execution_scenario()

    rows = _expected_action_alignment_rows(
        scenario=scenario,
        expected_action_ids=checkpoint.expected_action_ids,
        graph_items=[_runtime_action(target="ent:atlas-cleanup-branch-b", status="in_progress", events=["event_09_branch_b_progress"])],
        runtime_claim_by_oracle={},
    )

    assert rows[0]["verdict"] == "aligned"
    assert rows[0]["support_mode"] == "runtime_action_semantic"
    assert rows[0]["matched_on"] == ["target_entity", "status", "evidence_event", "lifecycle"]


def test_runtime_action_alignment_classifies_target_status_and_evidence_failures() -> None:
    scenario, checkpoint = _long_horizon_execution_scenario()

    wrong_target = _expected_action_alignment_rows(
        scenario=scenario,
        expected_action_ids=checkpoint.expected_action_ids,
        graph_items=[_runtime_action(target="ent:atlas-cleanup-branch-a", status="in_progress", events=["event_09_branch_b_progress"])],
        runtime_claim_by_oracle={},
    )[0]
    wrong_status = _expected_action_alignment_rows(
        scenario=scenario,
        expected_action_ids=checkpoint.expected_action_ids,
        graph_items=[_runtime_action(target="ent:atlas-cleanup-branch-b", status="started", events=["event_09_branch_b_progress"])],
        runtime_claim_by_oracle={},
    )[0]
    missing_evidence = _expected_action_alignment_rows(
        scenario=scenario,
        expected_action_ids=checkpoint.expected_action_ids,
        graph_items=[_runtime_action(target="ent:atlas-cleanup-branch-b", status="in_progress", events=[])],
        runtime_claim_by_oracle={},
    )[0]

    assert wrong_target["verdict"] == "partial"
    assert wrong_target["failure_reason"] == "runtime_action_target_mismatch"
    assert wrong_status["failure_reason"] == "runtime_action_status_mismatch"
    assert missing_evidence["failure_reason"] == "runtime_action_evidence_missing"


def test_runtime_execution_projection_selects_action_backed_continuation_state() -> None:
    scenario, checkpoint = _long_horizon_execution_scenario()
    graph_items = [
        _runtime_entity(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:entity:atlas-migration",
            canonical_id="ent:atlas-billing-migration",
            name="Atlas Billing Migration",
            entity_type="project",
            aliases=["Atlas Billing Migration"],
            events=["event_09_001"],
        ),
        _runtime_entity(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:entity:branch-b",
            canonical_id="ent:atlas-cleanup-branch-b",
            name="Atlas Cleanup Branch B",
            entity_type="task",
            aliases=["Atlas cleanup Branch B"],
            events=["event_09_branch_b_progress"],
        ),
        _runtime_claim(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:claim:project-type",
            subject_id="ent:atlas-billing-migration",
            subject="Atlas Billing Migration",
            predicate="entity_type",
            obj="project",
            event="event_09_001",
        ),
        _runtime_claim(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:claim:current-owner",
            subject_id="ent:atlas-billing-migration",
            subject="Atlas Billing Migration",
            predicate="owner",
            obj="Bob",
            event="event_09_005",
        ),
        _runtime_action(target="ent:atlas-cleanup-branch-b", status="in_progress", events=["event_09_branch_b_progress"]),
        _runtime_action(target="ent:atlas-cleanup-branch-a", status="started", events=["event_09_branch_a_started"]),
        _runtime_action(target="ent:atlas-cleanup", status="blocked", events=["event_09_branch_a_blocked"]),
    ]

    projection = project_runtime_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
        graph_snapshot=MemoryGraphSnapshot(snapshot_id="test"),
        graph_items=graph_items,
        source_id_to_event_id={},
    )

    assert "claim_09_branch_b_progress" in projection.output.selected_claim_ids
    assert "claim_09_branch_b_progress" in projection.output.supporting_claim_ids
    assert "event_09_branch_b_progress" in projection.output.supporting_citation_event_ids
    assert "claim_09_branch_a_blocked" in projection.output.rejected_claim_ids
    assert "ent_09_branch_a" in projection.output.rejected_entity_ids
    assert projection.execution_state["active_continuation_branch"] == "ent_09_branch_b"
    assert "ent_09_branch_a" in projection.execution_state["suppressed_branch_ids"]


def test_runtime_execution_projection_rejects_semantic_short_branch_id() -> None:
    scenario, checkpoint = _long_horizon_execution_scenario()
    graph_items = [
        _runtime_entity(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:entity:atlas-migration",
            canonical_id="ent:atlas-billing-migration",
            name="Atlas Billing Migration",
            entity_type="project",
            aliases=["Atlas Billing Migration"],
            events=["event_09_001"],
        ),
        _runtime_entity(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:entity:branch-b",
            canonical_id="ent:atlas-cleanup-branch-b",
            name="Atlas Cleanup Branch B",
            entity_type="task",
            aliases=["Atlas cleanup Branch B"],
            events=["event_09_branch_b_progress"],
        ),
        _runtime_claim(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:claim:project-type",
            subject_id="ent:atlas-billing-migration",
            subject="Atlas Billing Migration",
            predicate="entity_type",
            obj="project",
            event="event_09_001",
        ),
        _runtime_claim(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:claim:current-owner",
            subject_id="ent:atlas-billing-migration",
            subject="Atlas Billing Migration",
            predicate="owner",
            obj="Bob",
            event="event_09_005",
        ),
        _runtime_action(target="ent:branch-b", status="in_progress", events=["event_09_branch_b_progress"]),
        _runtime_action(target="ent:branch-a", status="blocked", events=["event_09_branch_a_blocked"]),
    ]

    projection = project_runtime_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
        graph_snapshot=MemoryGraphSnapshot(snapshot_id="test"),
        graph_items=graph_items,
        source_id_to_event_id={},
    )

    assert projection.action_support["action:claim_09_branch_b_progress"] == "runtime_action_semantic"
    assert "claim_09_branch_b_progress" in projection.output.selected_claim_ids
    assert "claim_09_branch_a_blocked" in projection.output.rejected_claim_ids
    assert "ent_09_branch_a" in projection.output.rejected_entity_ids
    assert projection.execution_state["active_continuation_branch"] == "ent_09_branch_b"
    assert projection.execution_state["suppressed_branch_ids"] == ["ent_09_branch_a"]


def test_runtime_execution_projection_bridges_subtask_progress_to_active_branch() -> None:
    scenario, checkpoint = _long_horizon_execution_scenario()
    graph_items = [
        _runtime_entity(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:entity:atlas-migration",
            canonical_id="ent:atlas-billing-migration",
            name="Atlas Billing Migration",
            entity_type="project",
            aliases=["Atlas Billing Migration"],
            events=["event_09_001"],
        ),
        _runtime_entity(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:entity:branch-b",
            canonical_id="ent:atlas-cleanup-branch-b",
            name="Atlas Cleanup Branch B",
            entity_type="task",
            aliases=["Atlas cleanup Branch B"],
            events=["event_09_branch_b_started"],
        ),
        _runtime_claim(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:claim:project-type",
            subject_id="ent:atlas-billing-migration",
            subject="Atlas Billing Migration",
            predicate="entity_type",
            obj="project",
            event="event_09_001",
        ),
        _runtime_claim(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:claim:current-owner",
            subject_id="ent:atlas-billing-migration",
            subject="Atlas Billing Migration",
            predicate="owner",
            obj="Bob",
            event="event_09_005",
        ),
        _runtime_action(target="ent:atlas-cleanup-branch-b", status="started", events=["event_09_branch_b_started"]),
        _runtime_action(target="ent:org-directory-owner-cleanup", status="in_progress", events=["event_09_branch_b_progress"]),
        _runtime_action(target="ent:atlas-cleanup-branch-a", status="blocked", events=["event_09_branch_a_blocked"]),
    ]

    projection = project_runtime_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
        graph_snapshot=MemoryGraphSnapshot(snapshot_id="test"),
        graph_items=graph_items,
        source_id_to_event_id={},
    )

    assert projection.action_support["action:claim_09_branch_b_progress"] == "runtime_action_work_state_bridge"
    assert "claim_09_branch_b_progress" in projection.output.selected_claim_ids
    assert "event_09_branch_b_progress" in projection.output.supporting_citation_event_ids
    assert "claim_09_branch_a_blocked" in projection.output.rejected_claim_ids
    assert "ent_09_branch_a" in projection.output.rejected_entity_ids
    assert projection.execution_state["active_continuation_branch"] == "ent_09_branch_b"
    assert projection.execution_state["suppressed_branch_ids"] == ["ent_09_branch_a"]
    assert projection.action_alignment_rows[0]["bridged_target_entity_id"] == "ent_09_branch_b"


def test_runtime_execution_projection_does_not_bridge_subtask_without_branch_history() -> None:
    scenario, checkpoint = _long_horizon_execution_scenario()
    graph_items = [
        _runtime_entity(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:entity:atlas-migration",
            canonical_id="ent:atlas-billing-migration",
            name="Atlas Billing Migration",
            entity_type="project",
            aliases=["Atlas Billing Migration"],
            events=["event_09_001"],
        ),
        _runtime_claim(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:claim:project-type",
            subject_id="ent:atlas-billing-migration",
            subject="Atlas Billing Migration",
            predicate="entity_type",
            obj="project",
            event="event_09_001",
        ),
        _runtime_claim(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:claim:current-owner",
            subject_id="ent:atlas-billing-migration",
            subject="Atlas Billing Migration",
            predicate="owner",
            obj="Bob",
            event="event_09_005",
        ),
        _runtime_action(target="ent:org-directory-owner-cleanup", status="in_progress", events=["event_09_branch_b_progress"]),
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
    scenario, checkpoint = _long_horizon_execution_scenario()
    base_items = [
        _runtime_entity(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:entity:atlas-migration",
            canonical_id="ent:atlas-billing-migration",
            name="Atlas Billing Migration",
            entity_type="project",
            aliases=["Atlas Billing Migration"],
            events=["event_09_001"],
        ),
        _runtime_entity(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:entity:branch-b",
            canonical_id="ent:atlas-cleanup-branch-b",
            name="Atlas Cleanup Branch B",
            entity_type="task",
            aliases=["Atlas cleanup Branch B"],
            events=["event_09_branch_b_progress"],
        ),
        _runtime_claim(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:claim:project-type",
            subject_id="ent:atlas-billing-migration",
            subject="Atlas Billing Migration",
            predicate="entity_type",
            obj="project",
            event="event_09_001",
        ),
        _runtime_claim(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:claim:current-owner",
            subject_id="ent:atlas-billing-migration",
            subject="Atlas Billing Migration",
            predicate="owner",
            obj="Bob",
            event="event_09_005",
        ),
        _runtime_action(target="ent:branch-b", status="in_progress", events=["event_09_branch_b_progress"]),
    ]

    active_branch_a = project_runtime_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
        graph_snapshot=MemoryGraphSnapshot(snapshot_id="test"),
        graph_items=[*base_items, _runtime_action(target="ent:branch-a", status="in_progress", events=["event_09_branch_a_blocked"])],
        source_id_to_event_id={},
    )
    wrong_branch = project_runtime_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
        graph_snapshot=MemoryGraphSnapshot(snapshot_id="test"),
        graph_items=[*base_items, _runtime_action(target="ent:branch-c", status="blocked", events=["event_09_branch_a_blocked"])],
        source_id_to_event_id={},
    )

    assert "claim_09_branch_a_blocked" not in active_branch_a.output.rejected_claim_ids
    assert "claim_09_branch_a_blocked" not in wrong_branch.output.rejected_claim_ids


def test_runtime_claim_alignment_does_not_merge_service_into_project() -> None:
    scenario = generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=1, seed=7)[0]
    graph_items = [
        _runtime_entity(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:entity:atlas-service",
            canonical_id="ent:atlas-service",
            name="atlas service",
            entity_type="service",
            aliases=["Atlas service"],
            events=["event_00_003"],
        ),
        _runtime_claim(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:claim:service-owner",
            subject_id="ent:atlas-service",
            subject="atlas service",
            predicate="owner",
            obj="Iris",
            event="event_00_003",
        ),
    ]

    alignments = align_runtime_graph_to_oracle(scenario=scenario, graph_items=graph_items)

    ambiguous_project_owner = _alignment_for(alignments, "claim_00_ambiguous_service_owner_atlas")
    assert ambiguous_project_owner.verdict.value != "aligned"


def test_runtime_graph_completeness_metrics_report_claim_provenance_and_edge_counts() -> None:
    rows = RuntimeSuiteRows(
        scenario_rows=[],
        checkpoint_rows=[
            {
                "runtime_relation_support": [
                    {"relation_id": "rel_claim_derived", "support_mode": "claim_derived"},
                    {"relation_id": "rel_item", "support_mode": "runtime_relation_item"},
                ]
            }
        ],
        judge_rows=[],
        llm_rows=[],
        graph_items=[
            {"item_type": "claim"},
            {"item_type": "entity"},
            {"item_type": "relation"},
            {"item_type": "action"},
        ],
        graph_snapshots=[
            {
                "validation_errors": [],
                "nodes": [
                    {"node_id": "source:1", "node_type": "source_observation"},
                    {"node_id": "claim:1", "node_type": "claim", "lifecycle_state": "active"},
                    {"node_id": "action:1", "node_type": "action", "lifecycle_state": "active"},
                    {"node_id": "entity:1", "node_type": "entity"},
                    {"node_id": "literal:1", "node_type": "literal"},
                    {"node_id": "scope:global", "node_type": "scope"},
                ],
                "edges": [
                    {"edge_type": "has_subject", "source_node_id": "claim:1", "target_node_id": "entity:1"},
                    {"edge_type": "has_literal_object", "source_node_id": "claim:1", "target_node_id": "literal:1"},
                    {"edge_type": "has_scope", "source_node_id": "claim:1", "target_node_id": "scope:global"},
                    {"edge_type": "observed_in", "source_node_id": "claim:1", "target_node_id": "source:1"},
                    {"edge_type": "observed_in", "source_node_id": "action:1", "target_node_id": "source:1"},
                ],
            }
        ],
    )

    metrics = runtime_graph_completeness_metrics(rows)

    assert metrics["source_observation_count"] == 1
    assert metrics["entity_count"] == 1
    assert metrics["claim_count"] == 1
    assert metrics["relation_item_count"] == 1
    assert metrics["action_item_count"] == 1
    assert metrics["evidence_edge_count"] == 2
    assert metrics["active_claim_with_subject_rate"] == 1.0
    assert metrics["active_claim_with_object_or_literal_rate"] == 1.0
    assert metrics["active_claim_with_scope_rate"] == 1.0
    assert metrics["active_claim_with_observed_in_rate"] == 1.0
    assert metrics["action_count"] == 1
    assert metrics["active_action_count"] == 1
    assert metrics["active_action_with_observed_in_rate"] == 1.0
    assert metrics["runtime_relation_support_modes"] == {
        "claim_derived": 1,
        "runtime_relation_item": 1,
    }
