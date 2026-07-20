from __future__ import annotations

from memorii.core.benchmark.memory_evolution_runtime import (
    _expected_action_alignment_rows as expected_action_alignment_rows,
)
from memorii.core.benchmark.memory_evolution_runtime import (
    align_runtime_graph_to_oracle,
)
from memorii.core.benchmark.memory_evolution_runtime.checkpoint_projection import (
    _runtime_answer_for_checkpoint as runtime_answer_for_checkpoint,
)
from tests.unit.core.benchmark.memory_evolution_runtime_test_helpers import (
    action_claim_by_state,
    alignment_for,
    claim_event_id,
    long_horizon_execution_scenario,
    runtime_action,
    runtime_claim,
    runtime_entity,
)
from tests.unit.core.benchmark.memory_evolution_test_helpers import claim_by_role, generate_scenario_by_family


def test_runtime_claim_alignment_uses_entity_alias_for_service_owner() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="entity_definition_before_role_claims",
        seed=7,
    )
    service_owner_claim = next(
        claim
        for claim in scenario.claims
        if "entity_disambiguation" in claim.evaluation_roles and claim.predicate.predicate_id == "owner"
    )
    ambiguous_project_claim = claim_by_role(scenario, "conflict_detection")
    evidence_event_id = claim_event_id(service_owner_claim)
    graph_items = [
        runtime_entity(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:entity:atlas-service",
            canonical_id="ent:atlas-service",
            name="atlas service",
            entity_type="service",
            aliases=["Atlas service"],
            events=[evidence_event_id],
        ),
        runtime_claim(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:claim:service-owner",
            subject_id="ent:atlas-service",
            subject="atlas service",
            predicate="owner",
            obj=service_owner_claim.object.value,
            event=evidence_event_id,
        ),
    ]

    alignments = align_runtime_graph_to_oracle(scenario=scenario, graph_items=graph_items)

    service_owner = alignment_for(alignments, service_owner_claim.claim_id)
    ambiguous_project_owner = alignment_for(alignments, ambiguous_project_claim.claim_id)
    assert service_owner.verdict.value == "aligned"
    assert "subject_entity" in service_owner.matched_on
    assert ambiguous_project_owner.verdict.value != "aligned"


def test_runtime_claim_alignment_uses_atlas_alias_for_historical_project_owner() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="current_vs_historical_truth",
        seed=7,
    )
    previous_owner_claim = claim_by_role(scenario, "historical_truth")
    evidence_event_id = claim_event_id(previous_owner_claim)
    graph_items = [
        runtime_entity(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:entity:atlas",
            canonical_id="ent:atlas",
            name="atlas",
            entity_type="unknown",
            aliases=["Atlas"],
            events=[evidence_event_id],
        ),
        runtime_claim(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:claim:previous-owner",
            subject_id="ent:atlas",
            subject="atlas",
            predicate="owner",
            obj="Alice",
            event=evidence_event_id,
        ),
    ]

    alignments = align_runtime_graph_to_oracle(scenario=scenario, graph_items=graph_items)

    previous_owner = alignment_for(alignments, previous_owner_claim.claim_id)
    assert previous_owner.verdict.value == "aligned"
    assert "subject_entity" in previous_owner.matched_on


def test_runtime_action_semantically_aligns_to_oracle_action_with_native_id() -> None:
    scenario, checkpoint = long_horizon_execution_scenario()
    progress = action_claim_by_state(scenario, "in_progress", subject_name="Atlas Cleanup Branch B")

    rows = expected_action_alignment_rows(
        scenario=scenario,
        expected_action_ids=checkpoint.expected_action_ids,
        graph_items=[
            runtime_action(target="ent:atlas-cleanup-branch-b", status="in_progress", events=[claim_event_id(progress)])
        ],
        runtime_claim_by_oracle={},
    )

    assert rows[0]["verdict"] == "aligned"
    assert rows[0]["support_mode"] == "runtime_action_semantic"
    assert rows[0]["matched_on"] == ["target_entity", "status", "evidence_event", "lifecycle"]


def test_runtime_action_alignment_classifies_target_status_and_evidence_failures() -> None:
    scenario, checkpoint = long_horizon_execution_scenario()
    progress = action_claim_by_state(scenario, "in_progress", subject_name="Atlas Cleanup Branch B")
    progress_event = claim_event_id(progress)

    wrong_target = expected_action_alignment_rows(
        scenario=scenario,
        expected_action_ids=checkpoint.expected_action_ids,
        graph_items=[
            runtime_action(target="ent:atlas-cleanup-branch-a", status="in_progress", events=[progress_event])
        ],
        runtime_claim_by_oracle={},
    )[0]
    wrong_status = expected_action_alignment_rows(
        scenario=scenario,
        expected_action_ids=checkpoint.expected_action_ids,
        graph_items=[runtime_action(target="ent:atlas-cleanup-branch-b", status="started", events=[progress_event])],
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


def test_runtime_action_alignment_derives_progress_status_from_action_type() -> None:
    scenario, checkpoint = long_horizon_execution_scenario()
    progress = action_claim_by_state(scenario, "in_progress", subject_name="Atlas Cleanup Branch B")

    rows = expected_action_alignment_rows(
        scenario=scenario,
        expected_action_ids=checkpoint.expected_action_ids,
        graph_items=[
            runtime_action(
                target="ent:atlas-cleanup-branch-b",
                status="started",
                action_type="in_progress",
                events=[claim_event_id(progress)],
            )
        ],
        runtime_claim_by_oracle={},
    )

    assert rows[0]["verdict"] == "aligned"
    assert rows[0]["status"] == "in_progress"
    assert rows[0]["status_derived_from"] == "action_type"


def test_runtime_action_alignment_prefers_explicit_progress_over_resume_verb() -> None:
    scenario, checkpoint = long_horizon_execution_scenario()
    progress = action_claim_by_state(scenario, "in_progress", subject_name="Atlas Cleanup Branch B")

    rows = expected_action_alignment_rows(
        scenario=scenario,
        expected_action_ids=checkpoint.expected_action_ids,
        graph_items=[
            runtime_action(
                target="ent:atlas-cleanup-branch-b",
                status="in_progress",
                action_type="resume",
                events=[claim_event_id(progress)],
            )
        ],
        runtime_claim_by_oracle={},
    )

    assert rows[0]["verdict"] == "aligned"
    assert rows[0]["status"] == "in_progress"
    assert rows[0]["status_derived_from"] == "status"


def test_runtime_claim_alignment_requires_provenance_even_when_claim_id_matches() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="current_vs_historical_truth",
        seed=7,
    )
    previous_owner_claim = claim_by_role(scenario, "historical_truth")
    graph_item = runtime_claim(
        scenario_id=scenario.scenario_id,
        runtime_id=previous_owner_claim.claim_id,
        subject_id="ent:atlas",
        subject="atlas",
        predicate="owner",
        obj="Alice",
        event=claim_event_id(previous_owner_claim),
    )
    graph_item = graph_item.model_copy(update={"evidence_event_ids": []})

    alignment = alignment_for(
        align_runtime_graph_to_oracle(scenario=scenario, graph_items=[graph_item]),
        previous_owner_claim.claim_id,
    )

    assert alignment.verdict.value == "partial"
    assert alignment.rationale == "claim id matches but provenance is missing"


def test_runtime_alignment_enforces_one_to_one_oracle_claim_mapping() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="current_vs_historical_truth",
        seed=7,
    )
    previous_owner_claim = claim_by_role(scenario, "historical_truth")
    first = runtime_claim(
        scenario_id=scenario.scenario_id,
        runtime_id=previous_owner_claim.claim_id,
        subject_id="ent:atlas",
        subject="atlas",
        predicate="owner",
        obj="Alice",
        event=claim_event_id(previous_owner_claim),
    )
    duplicate = first.model_copy(update={"runtime_item_id": "rt:duplicate-previous-owner"})
    alignments = align_runtime_graph_to_oracle(scenario=scenario, graph_items=[first, duplicate])
    claim_rows = [
        row
        for row in alignments
        if row.item_type == "claim"
        and row.runtime_item_id in {previous_owner_claim.claim_id, "rt:duplicate-previous-owner"}
    ]

    assert sum(row.verdict.value == "aligned" for row in claim_rows) == 1
    assert sum(row.verdict.value == "unmatched_runtime" for row in claim_rows) == 1


def test_runtime_claim_alignment_does_not_merge_service_into_project() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="entity_definition_before_role_claims",
        seed=7,
    )
    service_owner_claim = next(
        claim
        for claim in scenario.claims
        if "entity_disambiguation" in claim.evaluation_roles and claim.predicate.predicate_id == "owner"
    )
    ambiguous_project_claim = claim_by_role(scenario, "conflict_detection")
    evidence_event_id = claim_event_id(service_owner_claim)
    graph_items = [
        runtime_entity(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:entity:atlas-service",
            canonical_id="ent:atlas-service",
            name="atlas service",
            entity_type="service",
            aliases=["Atlas service"],
            events=[evidence_event_id],
        ),
        runtime_claim(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:claim:service-owner",
            subject_id="ent:atlas-service",
            subject="atlas service",
            predicate="owner",
            obj="Iris",
            event=evidence_event_id,
        ),
    ]

    alignments = align_runtime_graph_to_oracle(scenario=scenario, graph_items=graph_items)

    ambiguous_project_owner = alignment_for(alignments, ambiguous_project_claim.claim_id)
    assert ambiguous_project_owner.verdict.value != "aligned"


def test_runtime_answer_projection_uses_checkpoint_policy_not_english_query_text() -> None:
    scenario = generate_scenario_by_family(profile="adversarial", family="entity_split", seed=7)
    checkpoint = next(item for item in scenario.checkpoints if item.answer_projection_policy == "claim_subject")
    runtime_claim_id = "rt:claim:service-owner"
    claim = next(item for item in scenario.claims if item.claim_id == checkpoint.expected_claim_ids[0])
    runtime_item = runtime_claim(
        scenario_id=scenario.scenario_id,
        runtime_id=runtime_claim_id,
        subject_id=claim.subject.entity_id,
        subject="atlas platform service",
        predicate=claim.predicate.predicate_id,
        obj="Iris",
        event=claim_event_id(claim),
    )
    answer = runtime_answer_for_checkpoint(
        checkpoint=checkpoint,
        selected_claim_ids=list(checkpoint.expected_claim_ids),
        runtime_claim_by_oracle={checkpoint.expected_claim_ids[0]: runtime_claim_id},
        item_by_id={runtime_claim_id: runtime_item},
    )

    assert checkpoint.answer_projection_policy == "claim_subject"
    assert answer == "Atlas Platform Service"
