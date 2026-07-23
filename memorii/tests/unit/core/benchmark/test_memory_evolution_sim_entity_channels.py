from __future__ import annotations

from memorii.core.benchmark.memory_evolution_sim import (
    JudgeVerdict,
    expected_sim_output_for_checkpoint,
    judge_sim_checkpoint,
    sim_checkpoint_diagnostics,
    sim_reconstruction_context_for_checkpoint,
)
from tests.unit.core.benchmark.memory_evolution_test_helpers import (
    checkpoint_by_type,
    generate_scenario_by_family,
)


def test_memory_evolution_sim_entity_split_fails_when_service_owner_supports_project_owner() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="entity_split",
        seed=7,
    )
    checkpoint = checkpoint_by_type(scenario, "entity_split_repair")
    service_owner_claim = checkpoint.expected_excluded_claim_ids[0]
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={
            "supporting_claim_ids": [*checkpoint.expected_claim_ids, service_owner_claim],
        }
    )

    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)
    diagnostics = sim_checkpoint_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        output=output,
        aggregate=aggregate,
    )

    assert aggregate.verdict == JudgeVerdict.FAIL
    assert "supporting_excluded_id" in aggregate.critical_failure_buckets
    assert "supporting_role_violation" in aggregate.critical_failure_buckets
    assert "wrong_entity_support_used" in aggregate.critical_failure_buckets
    assert "disambiguation_evidence_used_as_support" in aggregate.critical_failure_buckets
    assert diagnostics.supporting_excluded_ids["claim_ids"] == [service_owner_claim]
    assert diagnostics.supporting_role_violations == {
        "rejection_support": [service_owner_claim],
        "wrong_subject_support": [service_owner_claim],
    }
    assert diagnostics.supporting_wrong_subject_claim_ids == [service_owner_claim]
    assert "disambiguation_evidence_used_as_support" in diagnostics.precision_failure_classification


def test_memory_evolution_sim_entity_split_fails_when_sibling_definition_supports_project_owner() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="entity_split",
        seed=7,
    )
    checkpoint = checkpoint_by_type(scenario, "entity_split_repair")
    service_owner_claim = next(
        claim for claim in scenario.claims if claim.claim_id == checkpoint.expected_excluded_claim_ids[0]
    )
    service_type_claim = next(
        claim
        for claim in scenario.claims
        if claim.subject.entity_id == service_owner_claim.subject.entity_id
        and claim.predicate.predicate_id == "entity_type"
    )
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={
            "supporting_claim_ids": [*checkpoint.expected_claim_ids, service_type_claim.claim_id],
        }
    )

    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)
    diagnostics = sim_checkpoint_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        output=output,
        aggregate=aggregate,
    )

    assert aggregate.verdict == JudgeVerdict.FAIL
    assert "supporting_role_violation" in aggregate.critical_failure_buckets
    assert diagnostics.supporting_wrong_subject_claim_ids == [service_type_claim.claim_id]
    assert diagnostics.supporting_wrong_subject_entity_ids == [service_type_claim.subject.entity_id]
    assert diagnostics.supporting_disambiguation_claim_ids == [service_type_claim.claim_id]


def test_memory_evolution_sim_entity_split_context_marks_sibling_claims_as_context_candidates() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="entity_split",
        seed=7,
    )
    checkpoint = checkpoint_by_type(scenario, "entity_split_repair")
    context = sim_reconstruction_context_for_checkpoint(scenario=scenario, checkpoint=checkpoint)
    service_owner_card = next(
        claim for claim in context.visible_claims if claim.claim_id == checkpoint.expected_excluded_claim_ids[0]
    )
    service_type_card = next(
        claim
        for claim in context.visible_claims
        if claim.subject_entity_id == service_owner_card.subject_entity_id and claim.predicate_id == "entity_type"
    )

    assert "metadata" not in context.model_dump(mode="json")
    assert service_owner_card.subject_entity_type == "service"
    assert service_owner_card.object_entity_type == "person"
    assert service_owner_card.predicate_id == "owner"
    assert service_type_card.predicate_id == "entity_type"


def test_memory_evolution_sim_entity_split_requires_wrong_entity_subject_rejection() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="entity_split",
        seed=7,
    )
    checkpoint = checkpoint_by_type(scenario, "entity_split_repair")
    service_entity = checkpoint.expected_excluded_entity_ids[0]
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={
            "rejected_entity_ids": [],
            "context_entity_ids": [],
        }
    )

    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)
    diagnostics = sim_checkpoint_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        output=output,
        aggregate=aggregate,
    )

    assert aggregate.verdict == JudgeVerdict.FAIL
    assert "missing_rejected_id" in aggregate.critical_failure_buckets
    assert diagnostics.missing_rejected_claim_subject_entity_ids == [service_entity]
    assert "missing_rejected_claim_subject_entity" in diagnostics.precision_failure_classification


def test_memory_evolution_sim_rejected_object_entity_does_not_replace_wrong_entity_subject() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="entity_split",
        seed=7,
    )
    checkpoint = checkpoint_by_type(scenario, "entity_split_repair")
    service_entity = checkpoint.expected_excluded_entity_ids[0]
    service_owner_claim = next(
        claim for claim in scenario.claims if claim.claim_id == checkpoint.expected_excluded_claim_ids[0]
    )
    assert service_owner_claim.subject.entity_id == service_entity
    assert service_owner_claim.object.entity_id is not None
    assert service_owner_claim.object.entity_id != service_entity
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={
            "rejected_entity_ids": [service_owner_claim.object.entity_id],
            "context_entity_ids": [],
        }
    )

    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)
    diagnostics = sim_checkpoint_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        output=output,
        aggregate=aggregate,
    )

    assert aggregate.verdict == JudgeVerdict.FAIL
    assert diagnostics.missing_rejected_claim_subject_entity_ids == [service_entity]
    assert "missing_rejected_claim_subject_entity" in diagnostics.precision_failure_classification


def test_memory_evolution_sim_inverse_ownership_requires_owned_subject_entity() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="entity_split",
        seed=7,
    )
    checkpoint = checkpoint_by_type(scenario, "entity_split_repair", index=1)
    claim = next(item for item in scenario.claims if item.claim_id == checkpoint.expected_claim_ids[0])
    assert claim.object.entity_id is not None
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={
            "selected_entity_ids": [claim.object.entity_id],
            "context_entity_ids": [claim.subject.entity_id],
        }
    )

    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)
    diagnostics = sim_checkpoint_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        output=output,
        aggregate=aggregate,
    )

    assert aggregate.verdict == JudgeVerdict.FAIL
    assert "entity_role_mismatch" in aggregate.critical_failure_buckets
    assert "supporting_role_violation" not in aggregate.critical_failure_buckets
    assert "wrong_entity_support_used" not in aggregate.critical_failure_buckets
    assert (
        "disambiguation_evidence_used_as_support"
        not in aggregate.critical_failure_buckets
    )
    assert diagnostics.supporting_wrong_subject_claim_ids == []
    assert diagnostics.supporting_disambiguation_claim_ids == []


def test_memory_evolution_sim_inverse_ownership_passes_with_owned_subject_entity() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="entity_split",
        seed=7,
    )
    checkpoint = checkpoint_by_type(scenario, "entity_split_repair", index=1)
    claim = next(item for item in scenario.claims if item.claim_id == checkpoint.expected_claim_ids[0])
    assert claim.object.entity_id is not None
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={
            "selected_entity_ids": [claim.subject.entity_id],
            "context_entity_ids": [claim.object.entity_id],
        }
    )

    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)

    assert aggregate.verdict == JudgeVerdict.PASS


def test_memory_evolution_sim_claim_rekey_requires_defining_claim() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="entity_alias_merge_and_relink",
        seed=7,
    )
    checkpoint = checkpoint_by_type(scenario, "claim_rekey")
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={
            "selected_claim_ids": checkpoint.expected_claim_ids[1:],
        }
    )

    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)

    assert aggregate.verdict == JudgeVerdict.FAIL
    assert "claim_rekey_error" in aggregate.critical_failure_buckets


def test_memory_evolution_sim_claim_rekey_classifies_definition_left_in_context() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="entity_alias_merge_and_relink",
        seed=7,
    )
    checkpoint = checkpoint_by_type(scenario, "claim_rekey")
    defining_claim, current_claim = checkpoint.expected_claim_ids
    defining_event, current_event = checkpoint.expected_citation_event_ids
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={
            "selected_claim_ids": [current_claim],
            "supporting_claim_ids": [current_claim],
            "supporting_citation_event_ids": [current_event],
            "context_claim_ids": [defining_claim],
            "context_citation_event_ids": [defining_event],
        }
    )

    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)
    diagnostics = sim_checkpoint_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        output=output,
        aggregate=aggregate,
    )

    assert aggregate.verdict == JudgeVerdict.FAIL
    assert "claim_rekey_error" in aggregate.critical_failure_buckets
    assert "missing_provenance" in aggregate.critical_failure_buckets
    assert "missing_required_defining_claim" in diagnostics.failure_classification
    assert "missing_required_defining_provenance" in diagnostics.failure_classification


def test_memory_evolution_sim_claim_rekey_passes_with_defining_claim_and_current_fact() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="entity_alias_merge_and_relink",
        seed=7,
    )
    checkpoint = checkpoint_by_type(scenario, "claim_rekey")
    context = sim_reconstruction_context_for_checkpoint(scenario=scenario, checkpoint=checkpoint)
    output = expected_sim_output_for_checkpoint(checkpoint)

    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)

    assert checkpoint.task_contract.allowed_operations == ["graph_reconstruction"]
    assert checkpoint.task_contract.selected_entity_role_policy == "active_graph_subjects"
    assert context.checkpoint.task_contract.allowed_operations == ["graph_reconstruction"]
    assert output.operation == "graph_reconstruction"
    assert aggregate.verdict == JudgeVerdict.PASS


def test_memory_evolution_sim_active_graph_subjects_reports_overbroad_selected_entities() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="entity_alias_merge_and_relink",
        seed=7,
    )
    checkpoint = checkpoint_by_type(scenario, "claim_rekey")
    current_owner_claim = next(
        claim for claim in scenario.claims if claim.claim_id == checkpoint.expected_claim_ids[-1]
    )
    assert current_owner_claim.object.entity_id is not None
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={
            "selected_entity_ids": [*checkpoint.expected_entity_ids, current_owner_claim.object.entity_id],
        }
    )

    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)
    diagnostics = sim_checkpoint_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        output=output,
        aggregate=aggregate,
    )

    assert aggregate.verdict == JudgeVerdict.PASS
    assert diagnostics.selected_nonrequired_graph_entity_ids == [current_owner_claim.object.entity_id]
    assert diagnostics.selected_graph_entity_overbreadth == [current_owner_claim.object.entity_id]


def test_memory_evolution_sim_graph_reconstruction_allows_invalidated_claim_as_rejected_context() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="entity_definition_before_role_claims",
        seed=7,
    )
    checkpoint = checkpoint_by_type(scenario, "entity_reconstruction")
    output = expected_sim_output_for_checkpoint(checkpoint)

    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)
    diagnostics = sim_checkpoint_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        output=output,
        aggregate=aggregate,
    )

    assert aggregate.verdict == JudgeVerdict.PASS
    assert diagnostics.rejected_expected_ids["claim_ids"] == checkpoint.expected_excluded_claim_ids
