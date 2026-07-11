from __future__ import annotations

from memorii.core.benchmark.memory_evolution_runtime import (
    _expected_action_alignment_rows as expected_action_alignment_rows,
    align_runtime_graph_to_oracle,
)
from tests.unit.core.benchmark.memory_evolution_runtime_test_helpers import (
    alignment_for,
    long_horizon_execution_scenario,
    runtime_action,
    runtime_claim,
    runtime_entity,
)
from tests.unit.core.benchmark.memory_evolution_test_helpers import generate_scenario_by_family


def test_runtime_claim_alignment_uses_entity_alias_for_service_owner() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="entity_definition_before_role_claims",
        seed=7,
    )
    graph_items = [
        runtime_entity(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:entity:atlas-service",
            canonical_id="ent:atlas-service",
            name="atlas service",
            entity_type="service",
            aliases=["Atlas service"],
            events=["event_00_003"],
        ),
        runtime_claim(
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

    service_owner = alignment_for(alignments, "claim_00_service_owner")
    ambiguous_project_owner = alignment_for(alignments, "claim_00_ambiguous_service_owner_atlas")
    assert service_owner.verdict.value == "aligned"
    assert "subject_entity" in service_owner.matched_on
    assert ambiguous_project_owner.verdict.value != "aligned"



def test_runtime_claim_alignment_uses_atlas_alias_for_historical_project_owner() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="current_vs_historical_truth",
        seed=7,
    )
    graph_items = [
        runtime_entity(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:entity:atlas",
            canonical_id="ent:atlas",
            name="atlas",
            entity_type="unknown",
            aliases=["Atlas"],
            events=["event_01_002"],
        ),
        runtime_claim(
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

    previous_owner = alignment_for(alignments, "claim_01_previous_owner_old")
    assert previous_owner.verdict.value == "aligned"
    assert "subject_entity" in previous_owner.matched_on



def test_runtime_action_semantically_aligns_to_oracle_action_with_native_id() -> None:
    scenario, checkpoint = long_horizon_execution_scenario()

    rows = expected_action_alignment_rows(
        scenario=scenario,
        expected_action_ids=checkpoint.expected_action_ids,
        graph_items=[runtime_action(target="ent:atlas-cleanup-branch-b", status="in_progress", events=["event_09_branch_b_progress"])],
        runtime_claim_by_oracle={},
    )

    assert rows[0]["verdict"] == "aligned"
    assert rows[0]["support_mode"] == "runtime_action_semantic"
    assert rows[0]["matched_on"] == ["target_entity", "status", "evidence_event", "lifecycle"]



def test_runtime_action_alignment_classifies_target_status_and_evidence_failures() -> None:
    scenario, checkpoint = long_horizon_execution_scenario()

    wrong_target = expected_action_alignment_rows(
        scenario=scenario,
        expected_action_ids=checkpoint.expected_action_ids,
        graph_items=[runtime_action(target="ent:atlas-cleanup-branch-a", status="in_progress", events=["event_09_branch_b_progress"])],
        runtime_claim_by_oracle={},
    )[0]
    wrong_status = expected_action_alignment_rows(
        scenario=scenario,
        expected_action_ids=checkpoint.expected_action_ids,
        graph_items=[runtime_action(target="ent:atlas-cleanup-branch-b", status="started", events=["event_09_branch_b_progress"])],
        runtime_claim_by_oracle={},
    )[0]
    missing_evidence = expected_action_alignment_rows(
        scenario=scenario,
        expected_action_ids=checkpoint.expected_action_ids,
        graph_items=[runtime_action(target="ent:atlas-cleanup-branch-b", status="in_progress", events=[])],
        runtime_claim_by_oracle={},
    )[0]

    assert wrong_target["verdict"] == "partial"
    assert wrong_target["failure_reason"] == "runtime_action_target_mismatch"
    assert wrong_status["failure_reason"] == "runtime_action_status_mismatch"
    assert missing_evidence["failure_reason"] == "runtime_action_evidence_missing"



def test_runtime_claim_alignment_does_not_merge_service_into_project() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="entity_definition_before_role_claims",
        seed=7,
    )
    graph_items = [
        runtime_entity(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:entity:atlas-service",
            canonical_id="ent:atlas-service",
            name="atlas service",
            entity_type="service",
            aliases=["Atlas service"],
            events=["event_00_003"],
        ),
        runtime_claim(
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

    ambiguous_project_owner = alignment_for(alignments, "claim_00_ambiguous_service_owner_atlas")
    assert ambiguous_project_owner.verdict.value != "aligned"


