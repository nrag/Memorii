from __future__ import annotations

from memorii.core.benchmark.memory_evolution_sim import (
    JudgeVerdict,
    ObservabilityLabel,
    expected_sim_output_for_checkpoint,
    judge_sim_checkpoint,
    sim_checkpoint_diagnostics,
)
from tests.unit.core.benchmark.memory_evolution_test_helpers import (
    checkpoint_by_type,
    generate_scenario_by_family,
)


def test_memory_evolution_sim_noisy_support_citation_fails_precision() -> None:
    scenario = generate_scenario_by_family(
        profile="adversarial",
        family="same_entity_vocabulary_different_role",
        seed=7,
        noise_rate=0.35,
    )
    checkpoint = checkpoint_by_type(scenario, "entity_disambiguation")
    noise_event = next(observation.event_id for observation in scenario.observations if observation.modality == "noise")
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={
            "supporting_citation_event_ids": [*checkpoint.expected_citation_event_ids, noise_event],
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
    assert diagnostics.supporting_noisy_citation_event_ids == [noise_event]


def test_memory_evolution_sim_noisy_context_citation_does_not_fail_answer_support() -> None:
    scenario = generate_scenario_by_family(
        profile="adversarial",
        family="same_entity_vocabulary_different_role",
        seed=7,
        noise_rate=0.35,
    )
    checkpoint = checkpoint_by_type(scenario, "entity_disambiguation")
    noise_event = next(observation.event_id for observation in scenario.observations if observation.modality == "noise")
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={
            "context_citation_event_ids": [noise_event],
            "supporting_citation_event_ids": list(checkpoint.expected_citation_event_ids),
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
    assert diagnostics.context_only_noise_event_ids == [noise_event]
    assert diagnostics.supporting_noisy_citation_event_ids == []


def test_memory_evolution_sim_hidden_id_in_selected_channel_fails_judge() -> None:
    scenario = generate_scenario_by_family(
        profile="adversarial",
        family="entity_definition_before_role_claims",
        seed=7,
        noise_rate=0.35,
    )
    checkpoint = checkpoint_by_type(scenario, "entity_reconstruction")
    hidden_claim = next(item.claim_id for item in scenario.claims if item.observability == ObservabilityLabel.HIDDEN)
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={"selected_claim_ids": [*checkpoint.expected_claim_ids, hidden_claim]}
    )

    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)

    assert aggregate.verdict == JudgeVerdict.FAIL
    assert "hidden_fact_hallucinated" in aggregate.critical_failure_buckets


def test_memory_evolution_sim_hidden_id_in_context_channel_fails_judge() -> None:
    scenario = generate_scenario_by_family(
        profile="adversarial",
        family="entity_definition_before_role_claims",
        seed=7,
        noise_rate=0.35,
    )
    checkpoint = checkpoint_by_type(scenario, "entity_reconstruction")
    hidden_claim = next(item.claim_id for item in scenario.claims if item.observability == ObservabilityLabel.HIDDEN)
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(update={"context_claim_ids": [hidden_claim]})

    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)

    assert aggregate.verdict == JudgeVerdict.FAIL
    assert "hidden_fact_hallucinated" in aggregate.critical_failure_buckets


def test_memory_evolution_sim_hidden_name_in_answer_fails_judge() -> None:
    scenario = generate_scenario_by_family(
        profile="adversarial",
        family="entity_definition_before_role_claims",
        seed=7,
        noise_rate=0.35,
    )
    checkpoint = checkpoint_by_type(scenario, "entity_reconstruction")
    hidden_entity = next(item for item in scenario.entities if item.observability == ObservabilityLabel.HIDDEN)
    output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={"answer": f"{hidden_entity.canonical_name} secretly owns Atlas."}
    )

    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)

    assert aggregate.verdict == JudgeVerdict.FAIL
    assert "hidden_fact_answer_leak" in aggregate.critical_failure_buckets


def test_memory_evolution_sim_oracle_output_never_contains_hidden_ids() -> None:
    scenario = generate_scenario_by_family(
        profile="adversarial",
        family="entity_definition_before_role_claims",
        seed=7,
        noise_rate=0.35,
    )
    checkpoint = checkpoint_by_type(scenario, "entity_reconstruction")
    hidden_ids = (
        {item.entity_id for item in scenario.entities if item.observability == ObservabilityLabel.HIDDEN}
        | {item.claim_id for item in scenario.claims if item.observability == ObservabilityLabel.HIDDEN}
        | {item.relation_id for item in scenario.relations if item.observability == ObservabilityLabel.HIDDEN}
    )
    output = expected_sim_output_for_checkpoint(checkpoint)

    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=output)
    serialized = str(output.model_dump(mode="json"))

    assert aggregate.verdict == JudgeVerdict.PASS
    assert not any(hidden_id in serialized for hidden_id in hidden_ids)
