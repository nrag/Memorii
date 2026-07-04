from __future__ import annotations

import pytest
from pydantic import ValidationError

from memorii.core.benchmark.memory_evolution_sim import (
    JudgeVerdict,
    LatentGraphScenario,
    ObservabilityLabel,
    SimSystemOutput,
    expected_sim_output_for_checkpoint,
    generate_memory_evolution_sim_scenarios,
    judge_sim_checkpoint,
    normalize_sim_system_output_for_checkpoint,
    rule_sim_output_for_checkpoint,
    sim_checkpoint_diagnostics,
    sim_reconstruction_context_for_checkpoint,
)


def test_memory_evolution_sim_smoke_profile_has_required_families() -> None:
    scenarios = generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=10, seed=7)

    assert [scenario.family for scenario in scenarios] == [
        "entity_definition_before_role_claims",
        "current_vs_historical_truth",
        "same_entity_vocabulary_different_role",
        "source_trust_conflict",
        "modality_suppression",
        "global_vs_task_scoped_preference",
        "entity_alias_merge_and_relink",
        "entity_split",
        "belief_dependency_and_reranking",
        "abandoned_then_resumed_work",
    ]
    assert all(scenario.entities for scenario in scenarios)
    assert all(scenario.claims for scenario in scenarios)
    assert all(scenario.relations for scenario in scenarios)
    assert all(scenario.observations for scenario in scenarios)
    assert all(scenario.checkpoints for scenario in scenarios)


def test_memory_evolution_sim_generation_is_seed_deterministic() -> None:
    first = [
        scenario.model_dump(mode="json")
        for scenario in generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=10, seed=7)
    ]
    second = [
        scenario.model_dump(mode="json")
        for scenario in generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=10, seed=7)
    ]
    different = [
        scenario.model_dump(mode="json")
        for scenario in generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=10, seed=8)
    ]

    assert first == second
    assert first != different


def test_memory_evolution_sim_surface_observations_vary_by_seed() -> None:
    first = [
        observation.model_dump(mode="json")
        for scenario in generate_memory_evolution_sim_scenarios(
            profile="adversarial", scenario_count=10, seed=7, noise_rate=0.35
        )
        for observation in scenario.observations
    ]
    second = [
        observation.model_dump(mode="json")
        for scenario in generate_memory_evolution_sim_scenarios(
            profile="adversarial", scenario_count=10, seed=11, noise_rate=0.35
        )
        for observation in scenario.observations
    ]

    assert first != second


def test_memory_evolution_sim_noise_and_event_bounds_affect_observations() -> None:
    low_noise = generate_memory_evolution_sim_scenarios(
        profile="adversarial", scenario_count=1, seed=7, noise_rate=0.0, max_events=8
    )[0]
    high_noise = generate_memory_evolution_sim_scenarios(
        profile="adversarial", scenario_count=1, seed=7, noise_rate=0.35, max_events=8
    )[0]
    min_events = generate_memory_evolution_sim_scenarios(
        profile="adversarial", scenario_count=1, seed=7, noise_rate=0.0, min_events=7, max_events=8
    )[0]

    assert len(high_noise.observations) > len(low_noise.observations)
    assert len(min_events.observations) >= 7
    assert len(high_noise.observations) <= 8


def test_memory_evolution_sim_surface_text_does_not_leak_hidden_ids() -> None:
    scenarios = generate_memory_evolution_sim_scenarios(
        profile="adversarial", scenario_count=10, seed=7, noise_rate=0.35
    )
    for scenario in scenarios:
        hidden_ids = {
            item.entity_id for item in scenario.entities if item.observability == ObservabilityLabel.HIDDEN
        } | {
            item.claim_id for item in scenario.claims if item.observability == ObservabilityLabel.HIDDEN
        } | {
            item.relation_id for item in scenario.relations if item.observability == ObservabilityLabel.HIDDEN
        }
        hidden_names = {
            item.canonical_name for item in scenario.entities if item.observability == ObservabilityLabel.HIDDEN
        }
        for observation in scenario.observations:
            assert not any(hidden_id in observation.text for hidden_id in hidden_ids)
            assert not any(hidden_name in observation.text for hidden_name in hidden_names)


def test_memory_evolution_sim_adversarial_profile_creates_hidden_latent_items() -> None:
    scenarios = generate_memory_evolution_sim_scenarios(
        profile="adversarial", scenario_count=10, seed=7, noise_rate=0.35
    )

    for scenario in scenarios:
        hidden_entities = [item for item in scenario.entities if item.observability == ObservabilityLabel.HIDDEN]
        hidden_claims = [item for item in scenario.claims if item.observability == ObservabilityLabel.HIDDEN]
        hidden_relations = [item for item in scenario.relations if item.observability == ObservabilityLabel.HIDDEN]
        assert len(hidden_entities) >= 1
        assert len(hidden_claims) >= 1
        assert len(hidden_relations) >= 1
        assert all(not claim.evidence.spans for claim in hidden_claims)
        assert all(not claim.evidence.source_event_ids for claim in hidden_claims)
        expected_ids = {hidden_entities[0].entity_id, hidden_claims[0].claim_id, hidden_relations[0].relation_id}
        exposed_ids = {
            item
            for observation in scenario.observations
            for item in [
                *observation.exposed_entity_ids,
                *observation.exposed_claim_ids,
                *observation.exposed_relation_ids,
            ]
        }
        assert not expected_ids & exposed_ids


def test_memory_evolution_sim_smoke_profile_does_not_create_hidden_latent_items() -> None:
    scenarios = generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=10, seed=7)

    hidden_ids = {
        item.entity_id for scenario in scenarios for item in scenario.entities if item.observability == ObservabilityLabel.HIDDEN
    } | {
        item.claim_id for scenario in scenarios for item in scenario.claims if item.observability == ObservabilityLabel.HIDDEN
    } | {
        item.relation_id
        for scenario in scenarios
        for item in scenario.relations
        if item.observability == ObservabilityLabel.HIDDEN
    }

    assert hidden_ids == set()


def test_memory_evolution_sim_uses_role_stable_ids_not_seeded_names() -> None:
    scenarios = generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=10, seed=19)
    all_ids = [
        item_id
        for scenario in scenarios
        for item_id in [
            *[entity.entity_id for entity in scenario.entities],
            *[claim.claim_id for claim in scenario.claims],
            *[relation.relation_id for relation in scenario.relations],
        ]
    ]

    assert not any("_alice" in item_id or "_bob" in item_id or "_carol" in item_id for item_id in all_ids)
    assert any("_current_owner" in item_id for item_id in all_ids)
    assert any("_service_owner" in item_id for item_id in all_ids)


def test_memory_evolution_sim_context_exposes_candidate_cards_without_oracle_fields() -> None:
    scenario = generate_memory_evolution_sim_scenarios(
        profile="adversarial", scenario_count=4, seed=7, noise_rate=0.35
    )[3]
    checkpoint = scenario.checkpoints[0]

    context = sim_reconstruction_context_for_checkpoint(scenario=scenario, checkpoint=checkpoint)
    payload = context.model_dump(mode="json")

    assert context.visible_events
    assert context.visible_entities
    assert context.visible_claims
    assert context.visible_relations
    relation = context.visible_relations[0]
    assert relation.relation_type
    assert relation.source_id
    assert relation.target_id
    assert relation.directionality
    assert relation.evidence_quote
    assert not any(key.startswith("expected_") for key in payload["checkpoint"])
    serialized = str(payload)
    assert "hidden_distractor_ids" not in serialized
    assert payload["metadata"]["checkpoint_contract"]["allowed_operations"]
    assert payload["metadata"]["checkpoint_contract"]["selected_entity_role_policy"] == "subject"
    hidden_ids = {
        item.entity_id for item in scenario.entities if item.observability == ObservabilityLabel.HIDDEN
    } | {
        item.claim_id for item in scenario.claims if item.observability == ObservabilityLabel.HIDDEN
    } | {
        item.relation_id for item in scenario.relations if item.observability == ObservabilityLabel.HIDDEN
    }
    assert not any(hidden_id in serialized for hidden_id in hidden_ids)


def test_memory_evolution_sim_legacy_fields_are_derived_from_role_channels() -> None:
    output = SimSystemOutput(
        operation="answer",
        entity_ids=["legacy_entity"],
        claim_ids=["legacy_claim"],
        relation_ids=["legacy_relation"],
        citation_event_ids=["legacy_event"],
        selected_entity_ids=["ent_current"],
        selected_claim_ids=["claim_current"],
        selected_relation_ids=["rel_current"],
        supporting_claim_ids=["claim_support"],
        supporting_relation_ids=["rel_support"],
        supporting_citation_event_ids=["event_support"],
        rejected_entity_ids=["ent_rejected"],
        rejected_claim_ids=["claim_rejected"],
        rejected_relation_ids=["rel_rejected"],
        rejection_citation_event_ids=["event_rejected"],
        context_entity_ids=["ent_context"],
        context_claim_ids=["claim_context"],
        context_relation_ids=["rel_context"],
        context_citation_event_ids=["event_context"],
        answer="Nadia",
        next_action=None,
        uncertain_ids=[],
        confidence=0.8,
        rationale="role-aware fields are canonical",
    )

    assert output.entity_ids == ["ent_current", "ent_context", "ent_rejected"]
    assert output.claim_ids == ["claim_current", "claim_support", "claim_context", "claim_rejected"]
    assert output.relation_ids == ["rel_current", "rel_support", "rel_context", "rel_rejected"]
    assert output.citation_event_ids == ["event_support", "event_context", "event_rejected"]


def test_memory_evolution_sim_hidden_items_cannot_be_expected() -> None:
    scenario = generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=1, seed=7)[0]
    payload = scenario.model_dump(mode="json")
    payload["claims"][0]["observability"] = ObservabilityLabel.HIDDEN.value
    payload["claims"][0]["evidence"]["spans"] = []
    payload["checkpoints"][0]["expected_claim_ids"] = [payload["claims"][0]["claim_id"]]

    with pytest.raises(ValidationError, match="requires hidden ids"):
        LatentGraphScenario.model_validate(payload)


def test_memory_evolution_sim_oracle_checkpoints_do_not_require_hidden_ids() -> None:
    scenarios = generate_memory_evolution_sim_scenarios(
        profile="adversarial", scenario_count=10, seed=7, noise_rate=0.35
    )

    for scenario in scenarios:
        hidden_ids = {
            item.entity_id for item in scenario.entities if item.observability == ObservabilityLabel.HIDDEN
        } | {
            item.claim_id for item in scenario.claims if item.observability == ObservabilityLabel.HIDDEN
        } | {
            item.relation_id for item in scenario.relations if item.observability == ObservabilityLabel.HIDDEN
        }
        for checkpoint in scenario.checkpoints:
            expected_ids = {
                *checkpoint.expected_entity_ids,
                *checkpoint.expected_claim_ids,
                *checkpoint.expected_relation_ids,
                *checkpoint.expected_excluded_entity_ids,
                *checkpoint.expected_excluded_claim_ids,
                *checkpoint.expected_uncertain_ids,
            }
            assert not expected_ids & hidden_ids


def test_memory_evolution_sim_observed_claims_require_spo_evidence() -> None:
    scenario = generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=1, seed=7)[0]
    payload = scenario.model_dump(mode="json")
    payload["claims"][0]["evidence"]["spans"] = [
        payload["claims"][0]["evidence"]["spans"][0],
    ]

    with pytest.raises(ValidationError, match="subject, predicate, and object evidence"):
        LatentGraphScenario.model_validate(payload)


def test_memory_evolution_sim_judges_pass_oracle_output_and_fail_rule_output() -> None:
    scenario = generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=1, seed=7)[0]
    checkpoint = scenario.checkpoints[0]

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


def test_memory_evolution_sim_alias_answer_passes_when_entity_is_correct() -> None:
    scenario = generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=8, seed=7)[7]
    checkpoint = scenario.checkpoints[1]
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(update={"answer": "Atlas service"})

    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)
    diagnostics = sim_checkpoint_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        output=output,
        aggregate=aggregate,
    )

    assert aggregate.verdict == JudgeVerdict.PASS
    assert diagnostics["answer_match_type"] == "semantic_entity"


def test_memory_evolution_sim_execution_checkpoint_requires_next_action_shape() -> None:
    scenario = generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=10, seed=7)[9]
    checkpoint = scenario.checkpoints[0]
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
    assert "wrong_output_shape" in diagnostics["failure_classification"]


def test_memory_evolution_sim_missing_visible_relation_is_classified() -> None:
    scenario = generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=4, seed=7)[3]
    checkpoint = scenario.checkpoints[0]
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={
            "relation_ids": [],
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
    assert diagnostics["missing_expected_ids"]["relation_ids"] == checkpoint.expected_relation_ids
    assert "missing_visible_relation" in diagnostics["failure_classification"]


def test_memory_evolution_sim_belief_judge_uses_explicit_ranking_field() -> None:
    scenario = generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=9, seed=7)[8]
    checkpoint = scenario.checkpoints[0]
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(update={"belief_ranking_ids": []})

    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)

    assert aggregate.verdict == JudgeVerdict.FAIL
    assert "belief_ranking_error" in aggregate.critical_failure_buckets


def test_memory_evolution_sim_current_truth_fails_when_stale_claim_is_selected() -> None:
    scenario = generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=2, seed=7)[1]
    checkpoint = scenario.checkpoints[0]
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={
            "selected_claim_ids": [*checkpoint.expected_claim_ids, *checkpoint.expected_excluded_claim_ids],
            "claim_ids": [*checkpoint.expected_claim_ids, *checkpoint.expected_excluded_claim_ids],
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
    assert diagnostics["selected_noncurrent_claim_ids"] == checkpoint.expected_excluded_claim_ids
    assert "selected_noncurrent_claim" in diagnostics["precision_failure_classification"]


def test_memory_evolution_sim_current_truth_fails_when_stale_claim_is_supporting() -> None:
    scenario = generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=2, seed=7)[1]
    checkpoint = scenario.checkpoints[0]
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
    assert diagnostics["supporting_excluded_ids"]["claim_ids"] == checkpoint.expected_excluded_claim_ids
    assert "supporting_excluded_id" in diagnostics["precision_failure_classification"]


def test_memory_evolution_sim_current_truth_passes_when_stale_claim_is_rejected() -> None:
    scenario = generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=2, seed=7)[1]
    checkpoint = scenario.checkpoints[0]
    output = expected_sim_output_for_checkpoint(checkpoint)

    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)
    diagnostics = sim_checkpoint_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        output=output,
        aggregate=aggregate,
    )

    assert aggregate.verdict == JudgeVerdict.PASS
    assert diagnostics["rejected_expected_ids"]["claim_ids"] == checkpoint.expected_excluded_claim_ids
    assert diagnostics["precision_failure_classification"] == []


def test_memory_evolution_sim_historical_truth_allows_superseded_selected_claim() -> None:
    scenario = generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=2, seed=7)[1]
    checkpoint = scenario.checkpoints[1]
    output = expected_sim_output_for_checkpoint(checkpoint)

    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)

    assert aggregate.verdict == JudgeVerdict.PASS


def test_memory_evolution_sim_historical_truth_requires_selected_claim_subject_entity() -> None:
    scenario = generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=2, seed=7)[1]
    checkpoint = scenario.checkpoints[1]
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
    assert diagnostics["selected_entity_role_mismatches"] == [claim.subject.entity_id]
    assert diagnostics["missing_selected_subject_entity_ids"] == [claim.subject.entity_id]
    assert "entity_role_mismatch" in diagnostics["precision_failure_classification"]
    assert "entity_role_mismatch" in diagnostics["failure_classification"]


def test_memory_evolution_sim_current_truth_requires_selected_claim_subject_entity() -> None:
    scenario = generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=2, seed=7)[1]
    checkpoint = scenario.checkpoints[0]
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
    scenario = generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=1, seed=7)[0]
    checkpoint = scenario.checkpoints[0]
    context = sim_reconstruction_context_for_checkpoint(scenario=scenario, checkpoint=checkpoint)
    output = expected_sim_output_for_checkpoint(checkpoint)

    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)

    assert context.metadata["checkpoint_contract"]["selected_entity_role_policy"] == "active_graph_subjects"
    assert aggregate.verdict == JudgeVerdict.PASS


def test_memory_evolution_sim_graph_reconstruction_answer_is_optional_by_contract() -> None:
    scenario = generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=1, seed=7)[0]
    checkpoint = scenario.checkpoints[0]
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

    assert context.metadata["checkpoint_contract"]["answer_required"] is False
    assert aggregate.verdict == JudgeVerdict.PASS
    assert diagnostics["answer_match_type"] == "optional_missing"


def test_memory_evolution_sim_entity_reconstruction_requires_subject_definition_claims() -> None:
    scenario = generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=1, seed=7)[0]
    checkpoint = scenario.checkpoints[0]
    service_type_claim = checkpoint.expected_claim_ids[1]
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={
            "selected_claim_ids": [claim_id for claim_id in checkpoint.expected_claim_ids if claim_id != service_type_claim],
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
    assert "missing_definition_claim" in diagnostics["failure_classification"]


def test_memory_evolution_sim_normalization_promotes_modality_current_truth_from_context() -> None:
    scenario = generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=5, seed=7)[4]
    checkpoint = scenario.checkpoints[0]
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
    scenario = generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=1, seed=7)[0]
    checkpoint = scenario.checkpoints[0]
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
    scenario = generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=3, seed=7)[2]
    checkpoint = scenario.checkpoints[0]
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
    scenario = generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=8, seed=7)[7]
    checkpoint = scenario.checkpoints[0]
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


def test_memory_evolution_sim_entity_split_fails_when_service_owner_supports_project_owner() -> None:
    scenario = generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=8, seed=7)[7]
    checkpoint = scenario.checkpoints[0]
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
    assert diagnostics["supporting_excluded_ids"]["claim_ids"] == [service_owner_claim]


def test_memory_evolution_sim_entity_split_requires_wrong_entity_subject_rejection() -> None:
    scenario = generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=8, seed=7)[7]
    checkpoint = scenario.checkpoints[0]
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
    assert diagnostics["missing_rejected_claim_subject_entity_ids"] == [service_entity]
    assert "missing_rejected_claim_subject_entity" in diagnostics["precision_failure_classification"]


def test_memory_evolution_sim_rejected_claim_subject_closure_is_normalized() -> None:
    scenario = generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=8, seed=7)[7]
    checkpoint = scenario.checkpoints[0]
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


def test_memory_evolution_sim_rejected_object_entity_does_not_replace_wrong_entity_subject() -> None:
    scenario = generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=8, seed=7)[7]
    checkpoint = scenario.checkpoints[0]
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
    assert diagnostics["missing_rejected_claim_subject_entity_ids"] == [service_entity]
    assert "missing_rejected_claim_subject_entity" in diagnostics["precision_failure_classification"]


def test_memory_evolution_sim_inverse_ownership_requires_owned_subject_entity() -> None:
    scenario = generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=8, seed=7)[7]
    checkpoint = scenario.checkpoints[1]
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


def test_memory_evolution_sim_inverse_ownership_passes_with_owned_subject_entity() -> None:
    scenario = generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=8, seed=7)[7]
    checkpoint = scenario.checkpoints[1]
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
    scenario = generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=7, seed=7)[6]
    checkpoint = scenario.checkpoints[0]
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={
            "selected_claim_ids": checkpoint.expected_claim_ids[1:],
            "claim_ids": checkpoint.expected_claim_ids[1:],
        }
    )

    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)

    assert aggregate.verdict == JudgeVerdict.FAIL
    assert "claim_rekey_error" in aggregate.critical_failure_buckets


def test_memory_evolution_sim_claim_rekey_classifies_definition_left_in_context() -> None:
    scenario = generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=7, seed=7)[6]
    checkpoint = scenario.checkpoints[0]
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
    assert "missing_required_defining_claim" in diagnostics["failure_classification"]
    assert "missing_required_defining_provenance" in diagnostics["failure_classification"]


def test_memory_evolution_sim_claim_rekey_passes_with_defining_claim_and_current_fact() -> None:
    scenario = generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=7, seed=7)[6]
    checkpoint = scenario.checkpoints[0]
    context = sim_reconstruction_context_for_checkpoint(scenario=scenario, checkpoint=checkpoint)
    output = expected_sim_output_for_checkpoint(checkpoint)

    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)

    assert context.metadata["checkpoint_contract"]["allowed_operations"] == ["graph_reconstruction"]
    assert context.metadata["checkpoint_contract"]["selected_entity_role_policy"] == "active_graph_subjects"
    assert output.operation == "graph_reconstruction"
    assert aggregate.verdict == JudgeVerdict.PASS


def test_memory_evolution_sim_active_graph_subjects_reports_overbroad_selected_entities() -> None:
    scenario = generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=7, seed=7)[6]
    checkpoint = scenario.checkpoints[0]
    current_owner_claim = next(claim for claim in scenario.claims if claim.claim_id == checkpoint.expected_claim_ids[-1])
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
    assert diagnostics["selected_nonrequired_graph_entity_ids"] == [current_owner_claim.object.entity_id]
    assert diagnostics["selected_graph_entity_overbreadth"] == [current_owner_claim.object.entity_id]


def test_memory_evolution_sim_legacy_flattening_is_normalized_before_judging() -> None:
    scenario = generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=2, seed=7)[1]
    checkpoint = scenario.checkpoints[1]
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


def test_memory_evolution_sim_execution_continuation_requires_selected_state() -> None:
    scenario = generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=10, seed=7)[9]
    checkpoint = scenario.checkpoints[0]
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={
            "selected_entity_ids": [],
            "selected_claim_ids": [],
            "supporting_claim_ids": [],
            "supporting_citation_event_ids": [],
            "context_entity_ids": checkpoint.expected_entity_ids,
            "context_claim_ids": checkpoint.expected_claim_ids,
            "context_citation_event_ids": checkpoint.expected_citation_event_ids,
        }
    )

    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)

    assert aggregate.verdict == JudgeVerdict.FAIL
    assert "abandoned_branch_selected" in aggregate.critical_failure_buckets
    assert "missing_provenance" in aggregate.critical_failure_buckets


def test_memory_evolution_sim_execution_continuation_allows_different_next_action_wording() -> None:
    scenario = generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=10, seed=7)[9]
    checkpoint = scenario.checkpoints[0]
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={
            "next_action": "Verify the current owner in the directory and continue the active cleanup branch.",
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
    assert diagnostics["answer_match_type"] == "diagnostic_only"


def test_memory_evolution_sim_graph_reconstruction_allows_invalidated_claim_as_rejected_context() -> None:
    scenario = generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=1, seed=7)[0]
    checkpoint = scenario.checkpoints[0]
    output = expected_sim_output_for_checkpoint(checkpoint)

    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)
    diagnostics = sim_checkpoint_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        output=output,
        aggregate=aggregate,
    )

    assert aggregate.verdict == JudgeVerdict.PASS
    assert diagnostics["rejected_expected_ids"]["claim_ids"] == checkpoint.expected_excluded_claim_ids


def test_memory_evolution_sim_noisy_support_citation_fails_precision() -> None:
    scenario = generate_memory_evolution_sim_scenarios(
        profile="adversarial", scenario_count=3, seed=7, noise_rate=0.35
    )[2]
    checkpoint = scenario.checkpoints[0]
    noise_event = next(observation.event_id for observation in scenario.observations if "_noise_" in observation.event_id)
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={
            "supporting_citation_event_ids": [*checkpoint.expected_citation_event_ids, noise_event],
            "citation_event_ids": [*checkpoint.expected_citation_event_ids, noise_event],
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
    assert "supporting_noisy_or_stale_provenance" in aggregate.critical_failure_buckets
    assert diagnostics["supporting_noisy_citation_event_ids"] == [noise_event]


def test_memory_evolution_sim_noisy_context_citation_does_not_fail_answer_support() -> None:
    scenario = generate_memory_evolution_sim_scenarios(
        profile="adversarial", scenario_count=3, seed=7, noise_rate=0.35
    )[2]
    checkpoint = scenario.checkpoints[0]
    noise_event = next(observation.event_id for observation in scenario.observations if "_noise_" in observation.event_id)
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={
            "context_citation_event_ids": [noise_event],
            "citation_event_ids": [*checkpoint.expected_citation_event_ids, noise_event],
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
    assert diagnostics["context_only_noise_event_ids"] == [noise_event]
    assert diagnostics["supporting_noisy_citation_event_ids"] == []


def test_memory_evolution_sim_hidden_id_in_selected_channel_fails_judge() -> None:
    scenario = generate_memory_evolution_sim_scenarios(
        profile="adversarial", scenario_count=1, seed=7, noise_rate=0.35
    )[0]
    checkpoint = scenario.checkpoints[0]
    hidden_claim = next(item.claim_id for item in scenario.claims if item.observability == ObservabilityLabel.HIDDEN)
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={"selected_claim_ids": [*checkpoint.expected_claim_ids, hidden_claim]}
    )

    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)

    assert aggregate.verdict == JudgeVerdict.FAIL
    assert "hidden_fact_hallucinated" in aggregate.critical_failure_buckets


def test_memory_evolution_sim_hidden_id_in_context_channel_fails_judge() -> None:
    scenario = generate_memory_evolution_sim_scenarios(
        profile="adversarial", scenario_count=1, seed=7, noise_rate=0.35
    )[0]
    checkpoint = scenario.checkpoints[0]
    hidden_claim = next(item.claim_id for item in scenario.claims if item.observability == ObservabilityLabel.HIDDEN)
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(update={"context_claim_ids": [hidden_claim]})

    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)

    assert aggregate.verdict == JudgeVerdict.FAIL
    assert "hidden_fact_hallucinated" in aggregate.critical_failure_buckets


def test_memory_evolution_sim_hidden_name_in_answer_fails_judge() -> None:
    scenario = generate_memory_evolution_sim_scenarios(
        profile="adversarial", scenario_count=1, seed=7, noise_rate=0.35
    )[0]
    checkpoint = scenario.checkpoints[0]
    hidden_entity = next(item for item in scenario.entities if item.observability == ObservabilityLabel.HIDDEN)
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={"answer": f"{hidden_entity.canonical_name} secretly owns Atlas."}
    )

    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)

    assert aggregate.verdict == JudgeVerdict.FAIL
    assert "hidden_fact_answer_leak" in aggregate.critical_failure_buckets


def test_memory_evolution_sim_oracle_output_never_contains_hidden_ids() -> None:
    scenario = generate_memory_evolution_sim_scenarios(
        profile="adversarial", scenario_count=1, seed=7, noise_rate=0.35
    )[0]
    checkpoint = scenario.checkpoints[0]
    hidden_ids = {
        item.entity_id for item in scenario.entities if item.observability == ObservabilityLabel.HIDDEN
    } | {
        item.claim_id for item in scenario.claims if item.observability == ObservabilityLabel.HIDDEN
    } | {
        item.relation_id for item in scenario.relations if item.observability == ObservabilityLabel.HIDDEN
    }
    output = expected_sim_output_for_checkpoint(checkpoint)

    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)
    serialized = str(output.model_dump(mode="json"))

    assert aggregate.verdict == JudgeVerdict.PASS
    assert not any(hidden_id in serialized for hidden_id in hidden_ids)
