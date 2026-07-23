from __future__ import annotations

from memorii.core.benchmark.memory_evolution_sim import (
    JudgeVerdict,
    expected_sim_output_for_checkpoint,
    judge_sim_checkpoint,
    rule_sim_output_for_checkpoint,
    sim_checkpoint_diagnostics,
    sim_reconstruction_context_for_checkpoint,
)
from tests.unit.core.benchmark.memory_evolution_test_helpers import (
    checkpoint_by_type,
    claim_by_role,
    generate_scenario_by_family,
)


def test_memory_evolution_sim_judges_pass_oracle_output_and_fail_rule_output() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="entity_definition_before_role_claims",
        seed=7,
    )
    checkpoint = checkpoint_by_type(scenario, "entity_reconstruction")

    oracle_output = expected_sim_output_for_checkpoint(checkpoint)
    oracle_aggregate = judge_sim_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
        output=oracle_output,
    )
    rule_aggregate = judge_sim_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
        output=rule_sim_output_for_checkpoint(scenario=scenario, checkpoint=checkpoint),
    )

    assert oracle_aggregate.verdict == JudgeVerdict.PASS
    assert oracle_aggregate.review_required is False
    assert rule_aggregate.verdict == JudgeVerdict.FAIL
    assert rule_aggregate.critical_failure_buckets


def test_scope_excluded_claim_must_be_hidden_but_never_selected() -> None:
    scenario = generate_scenario_by_family(
        profile="adversarial",
        family="global_vs_task_scoped_preference",
        seed=7,
    )
    checkpoint = checkpoint_by_type(scenario, "scoped_truth")
    task_claim_id = checkpoint.expected_excluded_claim_ids[0]
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={"rejected_claim_ids": [], "context_claim_ids": []}
    )

    aggregate = judge_sim_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
        output=output,
    )
    leaked = output.model_copy(
        update={
            "selected_claim_ids": [*output.selected_claim_ids, task_claim_id],
            "supporting_claim_ids": [*output.supporting_claim_ids, task_claim_id],
        }
    )
    leaked_aggregate = judge_sim_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
        output=leaked,
    )

    assert aggregate.verdict == JudgeVerdict.PASS
    assert leaked_aggregate.verdict == JudgeVerdict.FAIL
    assert "rejected_id_selected_as_truth" in leaked_aggregate.critical_failure_buckets


def test_memory_evolution_sim_alias_answer_passes_when_entity_is_correct() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="entity_split",
        seed=7,
    )
    checkpoint = checkpoint_by_type(scenario, "entity_split_repair", index=1)
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(update={"answer": "Atlas service"})

    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)
    diagnostics = sim_checkpoint_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        output=output,
        aggregate=aggregate,
    )

    assert aggregate.verdict == JudgeVerdict.PASS
    assert diagnostics.answer_match_type == "semantic_entity"


def test_memory_evolution_sim_execution_checkpoint_requires_next_action_shape() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="abandoned_then_resumed_work",
        seed=7,
    )
    checkpoint = checkpoint_by_type(scenario, "execution_continuation")
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={"operation": "answer", "answer": "continue cleanup", "next_action": None}
    )

    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)
    diagnostics = sim_checkpoint_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        output=output,
        aggregate=aggregate,
    )

    assert aggregate.verdict == JudgeVerdict.FAIL
    assert "abandoned_branch_selected" in aggregate.critical_failure_buckets
    assert "wrong_output_shape" in diagnostics.failure_classification


def test_memory_evolution_sim_missing_visible_relation_is_classified() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="source_trust_conflict",
        seed=7,
    )
    checkpoint = checkpoint_by_type(scenario, "source_trust_conflict")
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={
            "selected_relation_ids": [],
            "supporting_relation_ids": [],
            "rejected_relation_ids": [],
            "context_relation_ids": [],
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
    assert diagnostics.missing_expected_ids["relation_ids"] == checkpoint.expected_relation_ids
    assert "missing_visible_relation" in diagnostics.failure_classification


def test_memory_evolution_sim_belief_judge_uses_explicit_ranking_field() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="belief_dependency_and_reranking",
        seed=7,
    )
    checkpoint = checkpoint_by_type(scenario, "belief_ranking")
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(update={"belief_ranking_ids": []})

    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)

    assert aggregate.verdict == JudgeVerdict.FAIL
    assert "belief_ranking_error" in aggregate.critical_failure_buckets


def test_memory_evolution_sim_current_truth_fails_when_stale_claim_is_selected() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="current_vs_historical_truth",
        seed=7,
    )
    checkpoint = checkpoint_by_type(scenario, "current_truth")
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={
            "selected_claim_ids": [*checkpoint.expected_claim_ids, *checkpoint.expected_excluded_claim_ids],
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
    assert "selected_truth_precision_error" in aggregate.critical_failure_buckets
    assert diagnostics.selected_noncurrent_claim_ids == checkpoint.expected_excluded_claim_ids
    assert "selected_noncurrent_claim" in diagnostics.precision_failure_classification


def test_memory_evolution_sim_current_truth_fails_when_stale_claim_is_supporting() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="current_vs_historical_truth",
        seed=7,
    )
    checkpoint = checkpoint_by_type(scenario, "current_truth")
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={
            "supporting_claim_ids": [*checkpoint.expected_claim_ids, *checkpoint.expected_excluded_claim_ids],
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
    assert "supporting_noncurrent_claim_selected" in aggregate.critical_failure_buckets
    assert diagnostics.supporting_excluded_ids["claim_ids"] == checkpoint.expected_excluded_claim_ids
    assert "supporting_excluded_id" in diagnostics.precision_failure_classification


def test_memory_evolution_sim_current_truth_fails_when_selected_claim_lacks_support_closure() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="current_vs_historical_truth",
        seed=7,
    )
    checkpoint = checkpoint_by_type(scenario, "current_truth")
    selected_claim_id = checkpoint.expected_claim_ids[0]
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={
            "selected_claim_ids": [selected_claim_id],
            "supporting_claim_ids": [],
            "supporting_citation_event_ids": [],
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
    assert "selected_claim_support_missing" in aggregate.critical_failure_buckets
    assert "selected_claim_provenance_missing" in aggregate.critical_failure_buckets
    assert diagnostics.selected_claim_ids_missing_support == [selected_claim_id]
    assert diagnostics.selected_claim_evidence_event_ids_missing_support
    assert "selected_claim_support_missing" in diagnostics.precision_failure_classification


def test_memory_evolution_sim_current_truth_fails_when_selected_claim_lacks_direct_citation() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="current_vs_historical_truth",
        seed=7,
    )
    checkpoint = checkpoint_by_type(scenario, "current_truth")
    selected_claim_id = checkpoint.expected_claim_ids[0]
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={
            "selected_claim_ids": [selected_claim_id],
            "supporting_claim_ids": [selected_claim_id],
            "supporting_citation_event_ids": [],
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
    assert "selected_claim_support_missing" not in aggregate.critical_failure_buckets
    assert "selected_claim_provenance_missing" in aggregate.critical_failure_buckets
    assert diagnostics.selected_claim_ids_missing_support == []
    closure_errors = diagnostics.selected_claim_support_closure_errors
    assert len(closure_errors) == 1
    closure_error = closure_errors[0]
    assert closure_error.claim_id == selected_claim_id
    assert closure_error.missing_supporting_claim is False
    assert closure_error.expected_event_ids == diagnostics.selected_claim_evidence_event_ids_missing_support
    assert closure_error.present_event_ids == []
    assert closure_error.missing_event_ids == diagnostics.selected_claim_evidence_event_ids_missing_support
    assert closure_error.is_action_state is False
    assert "selected_claim_provenance_missing" in diagnostics.precision_failure_classification


def test_memory_evolution_sim_current_truth_passes_when_stale_claim_is_rejected() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="current_vs_historical_truth",
        seed=7,
    )
    checkpoint = checkpoint_by_type(scenario, "current_truth")
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
    assert diagnostics.precision_failure_classification == []


def test_memory_evolution_sim_definition_support_overlap_is_warning_not_failure() -> None:
    scenario = generate_scenario_by_family(
        profile="long_horizon",
        family="global_vs_task_scoped_preference",
        seed=7,
        noise_rate=0.35,
    )
    checkpoint = checkpoint_by_type(scenario, "scoped_truth")
    current_owner_claim = claim_by_role(scenario, "current_truth")
    project_type_claim = claim_by_role(scenario, "entity_type_missing")
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={
            "selected_claim_ids": [current_owner_claim.claim_id, project_type_claim.claim_id],
            "supporting_claim_ids": [current_owner_claim.claim_id, project_type_claim.claim_id],
            "supporting_citation_event_ids": [
                current_owner_claim.evidence.source_event_ids[0],
                project_type_claim.evidence.source_event_ids[0],
            ],
            "rejection_citation_event_ids": [project_type_claim.evidence.source_event_ids[0]],
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
    assert diagnostics.allowed_definition_selected_ids == {
        "claim_ids": [project_type_claim.claim_id],
        "citation_event_ids": [project_type_claim.evidence.source_event_ids[0]],
    }
    assert diagnostics.channel_overlap.critical == []
    assert diagnostics.channel_overlap.warning == ["role_channel_context_overlap"]
    assert diagnostics.precision_failure_classification == []


def test_memory_evolution_sim_required_definition_claim_in_rejected_channel_fails() -> None:
    scenario = generate_scenario_by_family(
        profile="long_horizon",
        family="current_vs_historical_truth",
        seed=7,
        noise_rate=0.35,
    )
    checkpoint = checkpoint_by_type(scenario, "historical_truth")
    required_definition_claim = claim_by_role(scenario, "entity_type_missing")
    required_definition_claim_id = required_definition_claim.claim_id
    required_definition_event_id = required_definition_claim.evidence.source_event_ids[0]
    oracle_output = expected_sim_output_for_checkpoint(checkpoint)
    output = oracle_output.model_copy(
        update={
            "selected_claim_ids": [*oracle_output.selected_claim_ids, required_definition_claim_id],
            "supporting_claim_ids": [*oracle_output.supporting_claim_ids, required_definition_claim_id],
            "supporting_citation_event_ids": [
                *oracle_output.supporting_citation_event_ids,
                required_definition_event_id,
            ],
            "rejected_claim_ids": [
                *oracle_output.rejected_claim_ids,
                required_definition_claim_id,
            ],
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
    assert "definition_claim_rejected" in aggregate.critical_failure_buckets
    assert diagnostics.rejected_required_definition_claim_ids == [required_definition_claim_id]
    assert "definition_claim_rejected" in diagnostics.precision_failure_classification


def test_memory_evolution_sim_historical_truth_allows_superseded_selected_claim() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="current_vs_historical_truth",
        seed=7,
    )
    checkpoint = checkpoint_by_type(scenario, "historical_truth")
    output = expected_sim_output_for_checkpoint(checkpoint)

    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)

    assert aggregate.verdict == JudgeVerdict.PASS


def test_memory_evolution_sim_historical_truth_requires_selected_claim_subject_entity() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="current_vs_historical_truth",
        seed=7,
    )
    checkpoint = checkpoint_by_type(scenario, "historical_truth")
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
    assert diagnostics.selected_entity_role_mismatches == [claim.subject.entity_id]
    assert diagnostics.missing_selected_subject_entity_ids == [claim.subject.entity_id]
    assert "entity_role_mismatch" in diagnostics.precision_failure_classification
    assert "entity_role_mismatch" in diagnostics.failure_classification


def test_memory_evolution_sim_current_truth_requires_selected_claim_subject_entity() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="current_vs_historical_truth",
        seed=7,
    )
    checkpoint = checkpoint_by_type(scenario, "current_truth")
    claim = next(item for item in scenario.claims if item.claim_id == checkpoint.expected_claim_ids[0])
    assert claim.object.entity_id is not None
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={
            "selected_entity_ids": [claim.object.entity_id],
            "context_entity_ids": [claim.subject.entity_id],
        }
    )

    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)

    assert aggregate.verdict == JudgeVerdict.FAIL
    assert "entity_role_mismatch" in aggregate.critical_failure_buckets


def test_memory_evolution_sim_graph_reconstruction_uses_graph_entity_role_policy() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="entity_definition_before_role_claims",
        seed=7,
    )
    checkpoint = checkpoint_by_type(scenario, "entity_reconstruction")
    context = sim_reconstruction_context_for_checkpoint(scenario=scenario, checkpoint=checkpoint)
    output = expected_sim_output_for_checkpoint(checkpoint)

    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)

    assert checkpoint.checkpoint_contract.selected_entity_role_policy == "active_graph_subjects"
    assert "selected_entity_role_policy" not in context.model_dump_json()
    assert aggregate.verdict == JudgeVerdict.PASS


def test_memory_evolution_sim_graph_reconstruction_answer_is_optional_by_contract() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="entity_definition_before_role_claims",
        seed=7,
    )
    checkpoint = checkpoint_by_type(scenario, "entity_reconstruction")
    context = sim_reconstruction_context_for_checkpoint(scenario=scenario, checkpoint=checkpoint)
    assert checkpoint.expected_answer is not None
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(update={"answer": None})

    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)
    diagnostics = sim_checkpoint_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        output=output,
        aggregate=aggregate,
    )

    assert checkpoint.checkpoint_contract.answer_required is False
    assert "answer_required" not in context.model_dump_json()
    assert aggregate.verdict == JudgeVerdict.PASS
    assert diagnostics.answer_match_type == "optional_missing"


def test_memory_evolution_sim_entity_reconstruction_requires_subject_definition_claims() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="entity_definition_before_role_claims",
        seed=7,
    )
    checkpoint = checkpoint_by_type(scenario, "entity_reconstruction")
    service_type_claim = checkpoint.expected_claim_ids[1]
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={
            "selected_claim_ids": [
                claim_id for claim_id in checkpoint.expected_claim_ids if claim_id != service_type_claim
            ],
            "supporting_claim_ids": [
                claim_id for claim_id in checkpoint.expected_claim_ids if claim_id != service_type_claim
            ],
            "supporting_citation_event_ids": checkpoint.expected_citation_event_ids,
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
    assert "missing_definition_claim" in diagnostics.failure_classification
