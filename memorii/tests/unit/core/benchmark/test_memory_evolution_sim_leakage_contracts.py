from __future__ import annotations

from pathlib import Path

from memorii.core.benchmark.memory_evolution_sim import (
    ObservabilityLabel,
    generate_memory_evolution_sim_scenarios,
    sim_reconstruction_context_for_checkpoint,
)
from memorii.core.prompts.registry import PromptRegistry
from memorii.core.prompts.render import PromptRenderer
from tests.unit.core.benchmark.memory_evolution_test_helpers import (
    checkpoint_by_type,
    generate_scenario_by_family,
)

PROMPT_ROOT = Path(__file__).resolve().parents[4] / "prompts"


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


def test_memory_evolution_sim_reconstruction_context_does_not_leak_hidden_identifiers() -> None:
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
    contract = PromptRegistry(prompt_root=PROMPT_ROOT).load("memory_evolution_sim_reconstruction:v1")
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
