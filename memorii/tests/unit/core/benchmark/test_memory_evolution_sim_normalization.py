from __future__ import annotations

from memorii.core.benchmark.memory_evolution_sim import (
    JudgeVerdict,
    ObservabilityLabel,
    SimSystemOutput,
    expected_sim_output_for_checkpoint,
    judge_sim_checkpoint,
    normalize_sim_system_output_for_checkpoint,
    rule_sim_output_for_checkpoint,
    sim_checkpoint_diagnostics,
    sim_reconstruction_context_for_checkpoint,
)
from tests.unit.core.benchmark.memory_evolution_test_helpers import (
    checkpoint_by_type,
    generate_scenario_by_family,
)


def test_memory_evolution_sim_normalization_promotes_modality_current_truth_from_context() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="modality_suppression",
        seed=7,
    )
    checkpoint = checkpoint_by_type(scenario, "modality_suppression")
    current_claim = checkpoint.expected_claim_ids[0]
    current_event = checkpoint.expected_citation_event_ids[0]
    current_subject = checkpoint.expected_entity_ids[0]
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={
            "selected_entity_ids": [],
            "selected_claim_ids": [],
            "supporting_claim_ids": [],
            "supporting_citation_event_ids": [],
            "context_entity_ids": [current_subject],
            "context_claim_ids": [current_claim],
            "context_citation_event_ids": [current_event],
        }
    )

    normalized, normalization = normalize_sim_system_output_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
        output=output,
    )
    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=normalized)

    assert normalization.normalization_applied is True
    assert "current_truth_promoted_from_context" in normalization.normalization_reason_codes
    assert current_claim in normalization.auto_promoted_selected_claim_ids
    assert current_claim in normalization.auto_promoted_supporting_claim_ids
    assert current_event in normalization.auto_promoted_supporting_citation_event_ids
    assert current_subject in normalized.selected_entity_ids
    assert aggregate.verdict == JudgeVerdict.PASS


def test_memory_evolution_sim_normalization_completes_selected_definition_claims() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="entity_definition_before_role_claims",
        seed=7,
    )
    checkpoint = checkpoint_by_type(scenario, "entity_reconstruction")
    service_type_claim = checkpoint.expected_claim_ids[1]
    service_type_event = checkpoint.expected_citation_event_ids[1]
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={
            "selected_claim_ids": [claim_id for claim_id in checkpoint.expected_claim_ids if claim_id != service_type_claim],
            "supporting_claim_ids": [
                claim_id for claim_id in checkpoint.expected_claim_ids if claim_id != service_type_claim
            ],
            "supporting_citation_event_ids": [
                event_id for event_id in checkpoint.expected_citation_event_ids if event_id != service_type_event
            ],
        }
    )

    raw_aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)
    normalized, normalization = normalize_sim_system_output_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
        output=output,
    )
    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=normalized)

    assert raw_aggregate.verdict == JudgeVerdict.FAIL
    assert normalization.normalization_applied is True
    assert "definition_claim_completed" in normalization.normalization_reason_codes
    assert service_type_claim in normalization.auto_promoted_selected_claim_ids
    assert service_type_claim in normalization.auto_promoted_supporting_claim_ids
    assert service_type_event in normalization.auto_promoted_supporting_citation_event_ids
    assert aggregate.verdict == JudgeVerdict.PASS


def test_memory_evolution_sim_normalization_rejects_visible_omitted_wrong_role_claim() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="same_entity_vocabulary_different_role",
        seed=7,
    )
    checkpoint = checkpoint_by_type(scenario, "entity_disambiguation")
    service_owner_claim = checkpoint.expected_excluded_claim_ids[0]
    service_entity = checkpoint.expected_excluded_entity_ids[0]
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={
            "rejected_claim_ids": [claim_id for claim_id in checkpoint.expected_excluded_claim_ids if claim_id != service_owner_claim],
            "rejected_entity_ids": [],
            "context_claim_ids": [],
            "context_entity_ids": [],
        }
    )

    raw_aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)
    normalized, normalization = normalize_sim_system_output_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
        output=output,
    )
    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=normalized)

    assert raw_aggregate.verdict == JudgeVerdict.FAIL
    assert normalization.normalization_applied is True
    assert "visible_excluded_claim_rejected" in normalization.normalization_reason_codes
    assert service_owner_claim in normalization.auto_rejected_claim_ids
    assert service_entity in normalization.auto_closed_rejected_entity_ids
    assert service_owner_claim in normalized.rejected_claim_ids
    assert service_entity in normalized.rejected_entity_ids
    assert aggregate.verdict == JudgeVerdict.PASS


def test_memory_evolution_sim_normalization_does_not_rescue_supporting_wrong_entity_claim() -> None:
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
            "rejected_entity_ids": [],
            "context_entity_ids": [],
        }
    )

    normalized, normalization = normalize_sim_system_output_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
        output=output,
    )
    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=normalized)
    diagnostics = sim_checkpoint_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        output=normalized,
        aggregate=aggregate,
    )

    assert normalization.normalization_applied is True
    assert aggregate.verdict == JudgeVerdict.FAIL
    assert "supporting_excluded_id" in aggregate.critical_failure_buckets
    assert diagnostics["supporting_wrong_entity_claim_ids"] == [service_owner_claim]


def test_memory_evolution_sim_rejected_claim_subject_closure_is_normalized() -> None:
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

    raw_aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)
    normalized, normalization = normalize_sim_system_output_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
        output=output,
    )
    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=normalized)
    diagnostics = sim_checkpoint_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        output=normalized,
        aggregate=aggregate,
    )

    assert raw_aggregate.verdict == JudgeVerdict.FAIL
    assert normalization.normalization_applied is True
    assert normalization.auto_closed_rejected_entity_ids == [service_entity]
    assert service_entity in normalized.rejected_entity_ids
    assert aggregate.verdict == JudgeVerdict.PASS
    assert diagnostics["missing_rejected_claim_subject_entity_ids"] == []


def test_memory_evolution_sim_legacy_flattening_is_normalized_before_judging() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="current_vs_historical_truth",
        seed=7,
    )
    checkpoint = checkpoint_by_type(scenario, "historical_truth")
    payload = expected_sim_output_for_checkpoint(checkpoint).model_dump(mode="json")
    payload["claim_ids"] = []
    payload["entity_ids"] = []
    payload["citation_event_ids"] = []
    output = SimSystemOutput.model_validate(payload)

    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)
    legacy_votes = [vote for vote in aggregate.votes if vote.judge_id == "legacy_flattening_judge"]

    assert aggregate.verdict == JudgeVerdict.PASS
    assert aggregate.review_required is False
    assert legacy_votes[0].verdict == JudgeVerdict.PASS
    assert legacy_votes[0].failure_buckets == []


def test_memory_evolution_sim_legacy_claim_ids_do_not_backfill_when_role_channels_exist() -> None:
    output = SimSystemOutput(
        operation="next_action",
        entity_ids=[],
        claim_ids=["legacy_stale_claim"],
        relation_ids=[],
        citation_event_ids=[],
        belief_ranking_ids=[],
        selected_entity_ids=[],
        selected_claim_ids=[],
        selected_relation_ids=[],
        supporting_claim_ids=[],
        supporting_relation_ids=[],
        supporting_citation_event_ids=[],
        rejected_entity_ids=[],
        rejected_claim_ids=[],
        rejected_relation_ids=[],
        rejection_citation_event_ids=[],
        context_entity_ids=[],
        context_claim_ids=["context_current_claim"],
        context_relation_ids=[],
        context_citation_event_ids=[],
        answer=None,
        next_action="continue current branch",
        uncertain_ids=[],
        confidence=0.8,
        rationale="legacy fields are compatibility-only when role channels exist",
    )

    assert output.selected_claim_ids == []
    assert output.claim_ids == ["context_current_claim"]


