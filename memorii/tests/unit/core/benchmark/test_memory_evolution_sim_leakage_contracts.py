from __future__ import annotations

import pytest
from memorii.core.benchmark.llm_adapters import LLMMemoryEvolutionSimReconstructionAdapter
from memorii.core.benchmark.memory_evolution_sim import (
    MEMORY_EVOLUTION_SCENARIO_FAMILIES,
    JudgeVerdict,
    ObservabilityLabel,
    expected_sim_output_for_checkpoint,
    generate_memory_evolution_sim_scenarios,
    judge_sim_checkpoint,
    opaque_ids,
    remap_scenario_ids,
    sim_reconstruction_context_for_checkpoint,
)
from memorii.core.prompts.registry import PromptRegistry, default_prompt_root
from memorii.core.prompts.render import PromptRenderer
from memorii.core.prompts.runtime_manifest import PromptOwner
from tests.unit.core.benchmark.memory_evolution_test_helpers import (
    checkpoint_by_type,
    generate_scenario_by_family,
)

PROMPT_ROOT = default_prompt_root()


def test_memory_evolution_sim_reconstruction_prompt_examples_are_role_abstract() -> None:
    prompt_text = (PROMPT_ROOT / "memory_evolution_sim_reconstruction" / "v1.yaml").read_text()

    for fixture_term in ("Atlas", "Iris", "Rina", "billing migration"):
        assert fixture_term not in prompt_text


def test_memory_evolution_sim_surface_text_does_not_leak_hidden_ids() -> None:
    scenarios = generate_memory_evolution_sim_scenarios(
        profile="adversarial", scenario_count=10, seed=7, noise_rate=0.35
    )
    for scenario in scenarios:
        hidden_ids = (
            {item.entity_id for item in scenario.entities if item.observability == ObservabilityLabel.HIDDEN}
            | {item.claim_id for item in scenario.claims if item.observability == ObservabilityLabel.HIDDEN}
            | {item.relation_id for item in scenario.relations if item.observability == ObservabilityLabel.HIDDEN}
        )
        hidden_names = {
            item.canonical_name for item in scenario.entities if item.observability == ObservabilityLabel.HIDDEN
        }
        for observation in scenario.observations:
            assert not any(hidden_id in observation.text for hidden_id in hidden_ids)
            assert not any(hidden_name in observation.text for hidden_name in hidden_names)


def test_memory_evolution_sim_reconstruction_context_does_not_leak_hidden_identifiers() -> None:
    scenarios = generate_memory_evolution_sim_scenarios(
        profile="adversarial", scenario_count=10, seed=7, noise_rate=0.35
    )
    for scenario in scenarios:
        hidden_ids = (
            {item.entity_id for item in scenario.entities if item.observability == ObservabilityLabel.HIDDEN}
            | {item.claim_id for item in scenario.claims if item.observability == ObservabilityLabel.HIDDEN}
            | {item.relation_id for item in scenario.relations if item.observability == ObservabilityLabel.HIDDEN}
        )
        for checkpoint in scenario.checkpoints:
            payload = sim_reconstruction_context_for_checkpoint(
                scenario=scenario,
                checkpoint=checkpoint,
            ).model_dump(mode="json")
            payload_text = str(payload)
            assert "hidden_distractor_ids" not in payload_text
            assert "_hidden_" not in payload_text
            assert not any(hidden_id in payload_text for hidden_id in hidden_ids)


def test_memory_evolution_sim_context_exposes_candidate_cards_without_oracle_fields() -> None:
    scenario = generate_scenario_by_family(
        profile="adversarial",
        family="source_trust_conflict",
        scenario_count=10,
        seed=7,
        noise_rate=0.35,
    )
    checkpoint = checkpoint_by_type(scenario, "source_trust_conflict")

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
    assert "metadata" not in payload
    assert "checkpoint_type" not in payload["checkpoint"]
    assert "severity" not in payload["checkpoint"]
    assert all("is_current_active" not in claim for claim in payload["visible_claims"])
    hidden_ids = (
        {item.entity_id for item in scenario.entities if item.observability == ObservabilityLabel.HIDDEN}
        | {item.claim_id for item in scenario.claims if item.observability == ObservabilityLabel.HIDDEN}
        | {item.relation_id for item in scenario.relations if item.observability == ObservabilityLabel.HIDDEN}
    )
    assert not any(hidden_id in serialized for hidden_id in hidden_ids)


def test_memory_evolution_sim_execution_cards_expose_evidence_not_derived_eligibility_labels() -> None:
    scenario = generate_scenario_by_family(
        profile="long_horizon",
        family="abandoned_then_resumed_work",
        scenario_count=10,
        seed=7,
        noise_rate=0.35,
    )
    checkpoint = checkpoint_by_type(scenario, "execution_continuation")

    context = sim_reconstruction_context_for_checkpoint(scenario=scenario, checkpoint=checkpoint)
    progress = next(claim for claim in context.visible_claims if claim.object_value.lower() == "in_progress")
    blocked = next(claim for claim in context.visible_claims if claim.object_value.lower() == "blocked")

    assert progress.claim_id.startswith("oid_")
    assert blocked.claim_id.startswith("oid_")
    payload = context.model_dump(mode="json")
    assert "continuation_eligibility" not in str(payload)
    assert "action_state_status" not in str(payload)


def test_memory_evolution_sim_id_permutation_preserves_semantics_and_judgment() -> None:
    scenario = generate_scenario_by_family(
        profile="long_horizon",
        family="current_vs_historical_truth",
        seed=7,
        noise_rate=0.35,
    )
    checkpoint = checkpoint_by_type(scenario, "current_truth")
    permuted = remap_scenario_ids(scenario, permutation_seed="metamorphic-permutation")
    permuted_checkpoint = checkpoint_by_type(permuted, "current_truth")

    original_context = sim_reconstruction_context_for_checkpoint(scenario=scenario, checkpoint=checkpoint)
    permuted_context = sim_reconstruction_context_for_checkpoint(
        scenario=permuted,
        checkpoint=permuted_checkpoint,
    )
    assert [item.text for item in original_context.surface_observations] == [
        item.text for item in permuted_context.surface_observations
    ]
    assert original_context.checkpoint.query_or_task == permuted_context.checkpoint.query_or_task
    assert set(original_context.visible_claim_ids).isdisjoint(permuted_context.visible_claim_ids)
    assert set(original_context.visible_entity_ids).isdisjoint(permuted_context.visible_entity_ids)

    original = judge_sim_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
        output=expected_sim_output_for_checkpoint(checkpoint),
    )
    remapped = judge_sim_checkpoint(
        scenario=permuted,
        checkpoint=permuted_checkpoint,
        output=expected_sim_output_for_checkpoint(permuted_checkpoint),
    )
    assert original.verdict == remapped.verdict == JudgeVerdict.PASS
    assert original.score == remapped.score

    wrong_original_output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={
            "selected_claim_ids": checkpoint.expected_excluded_claim_ids,
            "supporting_claim_ids": checkpoint.expected_excluded_claim_ids,
        }
    )
    wrong_permuted_output = expected_sim_output_for_checkpoint(permuted_checkpoint).model_copy(
        update={
            "selected_claim_ids": permuted_checkpoint.expected_excluded_claim_ids,
            "supporting_claim_ids": permuted_checkpoint.expected_excluded_claim_ids,
        }
    )
    wrong_original = judge_sim_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
        output=wrong_original_output,
    )
    wrong_remapped = judge_sim_checkpoint(
        scenario=permuted,
        checkpoint=permuted_checkpoint,
        output=wrong_permuted_output,
    )
    assert wrong_original.verdict == wrong_remapped.verdict == JudgeVerdict.FAIL
    assert wrong_original.score == wrong_remapped.score


@pytest.mark.parametrize("profile", ["smoke", "adversarial", "long_horizon"])
@pytest.mark.parametrize("seed", [7, 19])
def test_id_permutation_is_metamorphic_across_every_generated_family(
    profile: str,
    seed: int,
) -> None:
    scenarios = generate_memory_evolution_sim_scenarios(
        profile=profile,
        scenario_count=len(MEMORY_EVOLUTION_SCENARIO_FAMILIES),
        seed=seed,
        noise_rate=0.35,
    )

    for scenario in scenarios:
        permuted = remap_scenario_ids(
            scenario,
            permutation_seed=f"metamorphic:{profile}:{seed}:{scenario.family}",
        )
        assert [item.text for item in scenario.observations] == [item.text for item in permuted.observations]
        assert [item.query_or_task for item in scenario.checkpoints] == [
            item.query_or_task for item in permuted.checkpoints
        ]

        for checkpoint, permuted_checkpoint in zip(
            scenario.checkpoints,
            permuted.checkpoints,
            strict=True,
        ):
            original = judge_sim_checkpoint(
                scenario=scenario,
                checkpoint=checkpoint,
                output=expected_sim_output_for_checkpoint(checkpoint),
            )
            remapped = judge_sim_checkpoint(
                scenario=permuted,
                checkpoint=permuted_checkpoint,
                output=expected_sim_output_for_checkpoint(permuted_checkpoint),
            )
            assert original.verdict == remapped.verdict == JudgeVerdict.PASS
            assert original.score == remapped.score


@pytest.mark.parametrize("profile", ["smoke", "adversarial", "long_horizon"])
def test_unrelated_observation_order_does_not_change_oracle_judgment(profile: str) -> None:
    scenarios = generate_memory_evolution_sim_scenarios(
        profile=profile,
        scenario_count=len(MEMORY_EVOLUTION_SCENARIO_FAMILIES),
        seed=11,
        noise_rate=0.35,
    )

    for scenario in scenarios:
        reordered = scenario.model_copy(update={"observations": list(reversed(scenario.observations))})
        for checkpoint in scenario.checkpoints:
            decision = expected_sim_output_for_checkpoint(checkpoint)
            original = judge_sim_checkpoint(
                scenario=scenario,
                checkpoint=checkpoint,
                output=decision,
            )
            after_reordering = judge_sim_checkpoint(
                scenario=reordered,
                checkpoint=checkpoint,
                output=decision,
            )
            assert original.verdict == after_reordering.verdict == JudgeVerdict.PASS
            assert original.score == after_reordering.score


def test_memory_evolution_sim_ids_cannot_support_answer_label_shortcuts() -> None:
    scenario = generate_scenario_by_family(
        profile="adversarial",
        family="current_vs_historical_truth",
        seed=19,
        noise_rate=0.35,
    )
    context = sim_reconstruction_context_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint_by_type(scenario, "current_truth"),
    )
    machine_ids = [
        context.scenario_id,
        context.checkpoint.checkpoint_id,
        *context.visible_entity_ids,
        *context.visible_claim_ids,
        *context.visible_relation_ids,
        *[item.event_id for item in context.visible_events],
    ]
    semantic_shortcuts = {"current", "previous", "owner", "service", "branch", "blocked", "progress"}
    assert not any(token in item.casefold() for item in machine_ids for token in semantic_shortcuts)


def test_opaque_ids_preserve_only_structural_scope_namespaces() -> None:
    scenario = generate_scenario_by_family(
        profile="adversarial",
        family="global_vs_task_scoped_preference",
        seed=7,
        noise_rate=0.35,
    )
    scoped_claim = next(claim for claim in scenario.claims if claim.scope.task_id is not None)

    assert scoped_claim.scope.task_id is not None
    assert scoped_claim.scope.task_id.startswith("task:oid_")
    assert scoped_claim.scope.scope_key == scoped_claim.scope.task_id
    assert "incident" not in scoped_claim.scope.task_id


def test_opaque_id_transform_fails_closed_for_new_identifier_fields() -> None:
    with pytest.raises(ValueError, match="unclassified benchmark identifier field"):
        opaque_ids._collect_ids({"new_machine_id": "answer_bearing_value"})


def test_memory_evolution_sim_rendered_reconstruction_prompt_rejects_adversarial_oracle_leakage() -> None:
    scenario = generate_scenario_by_family(
        profile="adversarial",
        family="entity_definition_before_role_claims",
        scenario_count=10,
        seed=7,
        noise_rate=0.35,
    )
    checkpoint = checkpoint_by_type(scenario, "entity_reconstruction").model_copy(
        update={
            "expected_answer": "ORACLE_EXPECTED_SHOULD_NOT_RENDER",
            "expected_claim_ids": ["ORACLE_EXPECTED_SHOULD_NOT_RENDER"],
            "expected_excluded_claim_ids": ["ORACLE_EXPECTED_SHOULD_NOT_RENDER"],
        }
    )
    observations = [
        scenario.observations[0].model_copy(update={"hidden_distractor_ids": ["HIDDEN_ID_SHOULD_NOT_RENDER"]}),
        *scenario.observations[1:],
    ]
    hidden_entities = [
        entity.model_copy(update={"canonical_name": "HIDDEN_NAME_SHOULD_NOT_RENDER"})
        if entity.observability == ObservabilityLabel.HIDDEN
        else entity
        for entity in scenario.entities
    ]
    adversarial_scenario = scenario.model_copy(update={"observations": observations, "entities": hidden_entities})
    context = sim_reconstruction_context_for_checkpoint(scenario=adversarial_scenario, checkpoint=checkpoint)
    contract = PromptRegistry(prompt_root=PROMPT_ROOT).load(
        "memory_evolution_sim_reconstruction:v1",
        owner=PromptOwner.LLM_MEMORY_EVOLUTION_SIM_RECONSTRUCTION_ADAPTER,
        output_model=LLMMemoryEvolutionSimReconstructionAdapter.output_model,
    )
    rendered = PromptRenderer().render(
        contract=contract,
        variables={"context_json": context.model_dump(mode="json"), "query": checkpoint.query_or_task},
    )
    rendered_text = f"{rendered.system}\n{rendered.user}"

    for forbidden in (
        "expected_answer",
        "expected_claim_ids",
        "expected_excluded_claim_ids",
        "hidden_distractor_ids",
        "ORACLE_EXPECTED_SHOULD_NOT_RENDER",
        "HIDDEN_ID_SHOULD_NOT_RENDER",
        "HIDDEN_NAME_SHOULD_NOT_RENDER",
    ):
        assert forbidden not in rendered_text
