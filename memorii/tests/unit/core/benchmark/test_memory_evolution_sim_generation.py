from __future__ import annotations

from collections import Counter

import pytest
from memorii.core.benchmark.memory_evolution_sim import (
    MEMORY_EVOLUTION_SCENARIO_FAMILIES,
    generate_memory_evolution_sim_scenarios,
    sim_reconstruction_context_for_checkpoint,
)
from memorii.core.benchmark.memory_evolution_sim.schemas import LatentEntity, LatentGraphScenario
from memorii.core.memory_evolution.extraction import models_from_llm_output
from memorii.core.memory_evolution.models import ExtractionRunStatus, SourceObservation
from memorii.domain.enums import SourceModality, SourceType
from tests.unit.core.benchmark.memory_evolution_test_helpers import generate_scenario_by_family


def test_memory_evolution_sim_smoke_profile_has_required_families() -> None:
    scenarios = generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=10, seed=7)

    assert Counter(scenario.family for scenario in scenarios) == Counter(MEMORY_EVOLUTION_SCENARIO_FAMILIES)
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


def test_unverified_owner_surface_matches_hidden_project_claim() -> None:
    scenario = generate_scenario_by_family(
        profile="adversarial",
        family="entity_definition_before_role_claims",
        seed=7,
        noise_rate=0.35,
    )
    observation = next(
        item for item in scenario.observations if item.modality == "third_party_claim" and item.exposed_claim_ids
    )
    claim = next(item for item in scenario.claims if item.claim_id in observation.exposed_claim_ids)

    assert "Atlas billing migration" in observation.text
    assert "not verified" in observation.text
    assert claim.subject.entity_type == "project"
    assert claim.subject.canonical_name == "Atlas Billing Migration"
    assert claim.lifecycle.state.value == "invalidated"


def _surface_mentions_entity(text: str, entity: LatentEntity) -> bool:
    normalized = text.casefold()
    names = [entity.canonical_name, *(alias.alias_text for alias in entity.aliases)]
    return any(name.casefold() in normalized for name in names)


def _assert_surface_contract_is_textually_grounded(scenario: LatentGraphScenario) -> None:
    entities = {entity.entity_id: entity for entity in scenario.entities}
    claims = {claim.claim_id: claim for claim in scenario.claims}
    relations = {relation.relation_id: relation for relation in scenario.relations}

    for observation in scenario.observations:
        for entity_id in observation.exposed_entity_ids:
            assert _surface_mentions_entity(observation.text, entities[entity_id]), (
                scenario.family,
                observation.event_id,
                entity_id,
                observation.text,
            )
        for claim_id in observation.exposed_claim_ids:
            claim = claims[claim_id]
            assert _surface_mentions_entity(observation.text, entities[claim.subject.entity_id])
            if claim.object.entity_id is not None:
                assert _surface_mentions_entity(observation.text, entities[claim.object.entity_id])
            else:
                assert claim.object.value.casefold() in observation.text.casefold()
        for relation_id in observation.exposed_relation_ids:
            relation = relations[relation_id]
            if relation.relation_type not in {"alias_of", "split_from"}:
                continue
            assert relation.source.label.casefold() in observation.text.casefold()
            assert relation.target.label.casefold() in observation.text.casefold()


def _assert_exposed_claims_satisfy_production_ingestion(scenario: LatentGraphScenario) -> None:
    entities = {entity.entity_id: entity for entity in scenario.entities}
    claims = {claim.claim_id: claim for claim in scenario.claims}

    for observation in scenario.observations:
        exposed_claims = [claims[claim_id] for claim_id in observation.exposed_claim_ids]
        if not exposed_claims:
            continue
        entity_ids = list(
            dict.fromkeys(
                entity_id
                for claim in exposed_claims
                for entity_id in (claim.subject.entity_id, claim.object.entity_id)
                if entity_id is not None
            )
        )
        entity_refs = {entity_id: f"entity_{index}" for index, entity_id in enumerate(entity_ids)}
        source_id = f"source:{observation.event_id}"
        output = {
            "entities": [
                {
                    "entity_ref": entity_refs[entity_id],
                    "mention_text": entities[entity_id].canonical_name,
                    "aliases": [alias.alias_text for alias in entities[entity_id].aliases],
                    "entity_type": entities[entity_id].entity_type,
                    "source_id": source_id,
                    "quote": observation.text,
                    "confidence": 1.0,
                }
                for entity_id in entity_ids
            ],
            "claims": [
                {
                    "subject_entity_ref": entity_refs[claim.subject.entity_id],
                    "predicate_id": claim.predicate.predicate_id,
                    "object_value": (
                        entities[claim.object.entity_id].canonical_name
                        if claim.object.entity_id is not None
                        else claim.object.value
                    ),
                    "object_entity_ref": (
                        entity_refs[claim.object.entity_id] if claim.object.entity_id is not None else None
                    ),
                    "source_id": source_id,
                    "quote": observation.text,
                    "confidence": 1.0,
                }
                for claim in exposed_claims
            ],
            "actions": [],
        }

        proposal = models_from_llm_output(
            run_id=f"run:{observation.event_id}",
            provider="test",
            model="test-model",
            prompt_hash="test-prompt",
            observations=[
                SourceObservation(
                    source_id=source_id,
                    text=observation.text,
                    source_type=(
                        SourceType.TOOL
                        if observation.source_type == "tool" or observation.modality == "tool_result"
                        else SourceType.USER
                    ),
                    timestamp=observation.timestamp,
                    task_id=observation.task_id,
                    session_id=observation.session_id,
                    user_id=observation.user_id,
                    modality=SourceModality(observation.modality),
                )
            ],
            output=output,
        )

        assert proposal.run.status == ExtractionRunStatus.SUCCEEDED, (
            scenario.profile,
            scenario.family,
            observation.event_id,
            observation.text,
            proposal.run.errors,
        )
        assert proposal.run.errors == []


@pytest.mark.parametrize("profile", ["smoke", "adversarial", "long_horizon"])
@pytest.mark.parametrize("seed", [7, 11, 19, 23, 31])
def test_generated_surface_contracts_are_textually_grounded(profile: str, seed: int) -> None:
    scenarios = generate_memory_evolution_sim_scenarios(
        profile=profile,
        scenario_count=len(MEMORY_EVOLUTION_SCENARIO_FAMILIES),
        seed=seed,
        noise_rate=0.35,
    )

    for scenario in scenarios:
        _assert_surface_contract_is_textually_grounded(scenario)


@pytest.mark.parametrize("profile", ["smoke", "adversarial", "long_horizon"])
@pytest.mark.parametrize("seed", [7, 11, 19, 23, 31])
def test_generated_claims_satisfy_production_ingestion_contract(profile: str, seed: int) -> None:
    scenarios = generate_memory_evolution_sim_scenarios(
        profile=profile,
        scenario_count=len(MEMORY_EVOLUTION_SCENARIO_FAMILIES),
        seed=seed,
        noise_rate=0.35,
    )

    for scenario in scenarios:
        _assert_exposed_claims_satisfy_production_ingestion(scenario)


def test_checkpoint_paraphrases_vary_without_changing_contracts() -> None:
    first = generate_memory_evolution_sim_scenarios(
        profile="long_horizon",
        scenario_count=10,
        seed=7,
    )
    second = generate_memory_evolution_sim_scenarios(
        profile="long_horizon",
        scenario_count=10,
        seed=11,
    )

    first_queries = [checkpoint.query_or_task for scenario in first for checkpoint in scenario.checkpoints]
    second_queries = [checkpoint.query_or_task for scenario in second for checkpoint in scenario.checkpoints]
    first_contracts = [
        (
            scenario.family,
            checkpoint.checkpoint_type,
            checkpoint.task_contract.model_dump(mode="json"),
            checkpoint.difficulty_tags,
            checkpoint.severity,
        )
        for scenario in first
        for checkpoint in scenario.checkpoints
    ]
    second_contracts = [
        (
            scenario.family,
            checkpoint.checkpoint_type,
            checkpoint.task_contract.model_dump(mode="json"),
            checkpoint.difficulty_tags,
            checkpoint.severity,
        )
        for scenario in second
        for checkpoint in scenario.checkpoints
    ]

    assert first_queries != second_queries
    assert first_contracts == second_contracts


def test_generated_semantic_worlds_are_unique_and_surface_id_independent() -> None:
    scenarios = generate_memory_evolution_sim_scenarios(
        profile="long_horizon",
        scenario_count=25,
        seed=7,
        noise_rate=0.35,
    )

    fingerprints = [scenario.semantic_world_fingerprint for scenario in scenarios]
    assert len(fingerprints) == len(set(fingerprints))
    assert all(len(fingerprint) == 64 for fingerprint in fingerprints)
    assert all(scenario.scenario_id not in scenario.semantic_world_fingerprint for scenario in scenarios)


@pytest.mark.parametrize("profile", ["smoke", "adversarial", "long_horizon"])
@pytest.mark.parametrize("seed", [7, 11, 19])
def test_every_generated_family_has_a_closed_visible_task_contract(
    profile: str,
    seed: int,
) -> None:
    scenarios = generate_memory_evolution_sim_scenarios(
        profile=profile,
        scenario_count=len(MEMORY_EVOLUTION_SCENARIO_FAMILIES),
        seed=seed,
        noise_rate=0.35,
    )

    assert Counter(scenario.family for scenario in scenarios) == Counter(MEMORY_EVOLUTION_SCENARIO_FAMILIES)
    assert len({scenario.semantic_world_fingerprint for scenario in scenarios}) == len(scenarios)
    for scenario in scenarios:
        for checkpoint in scenario.checkpoints:
            context = sim_reconstruction_context_for_checkpoint(
                scenario=scenario,
                checkpoint=checkpoint,
            )
            assert set(checkpoint.expected_entity_ids) <= set(context.visible_entity_ids)
            assert set(checkpoint.expected_claim_ids) <= set(context.visible_claim_ids)
            assert set(checkpoint.expected_relation_ids) <= set(context.visible_relation_ids)
            assert set(checkpoint.expected_execution_entity_ids) <= set(context.visible_entity_ids)
            assert set(checkpoint.expected_execution_claim_ids) <= set(context.visible_claim_ids)


@pytest.mark.parametrize("profile", ["smoke", "adversarial", "long_horizon"])
@pytest.mark.parametrize("seed", [7, 11, 19, 23, 31])
def test_historical_query_anchor_matches_expected_claim_interval(
    profile: str,
    seed: int,
) -> None:
    scenario = generate_scenario_by_family(
        profile=profile,
        family="current_vs_historical_truth",
        seed=seed,
        noise_rate=0.35,
    )
    checkpoint = next(item for item in scenario.checkpoints if item.checkpoint_type == "historical_truth")
    claims = {claim.claim_id: claim for claim in scenario.claims}

    assert "january" in checkpoint.query_or_task.casefold()
    assert all(claims[claim_id].lifecycle.valid_from.month == 1 for claim_id in checkpoint.expected_claim_ids)


def test_memory_evolution_sim_noise_and_event_bounds_affect_observations() -> None:
    low_noise = generate_scenario_by_family(
        profile="adversarial",
        family="entity_definition_before_role_claims",
        scenario_count=10,
        seed=7,
        noise_rate=0.0,
        max_events=10,
    )
    high_noise = generate_scenario_by_family(
        profile="adversarial",
        family="entity_definition_before_role_claims",
        scenario_count=10,
        seed=7,
        noise_rate=0.35,
        max_events=10,
    )
    min_events = generate_scenario_by_family(
        profile="adversarial",
        family="entity_definition_before_role_claims",
        scenario_count=10,
        seed=7,
        noise_rate=0.0,
        min_events=7,
        max_events=10,
    )

    assert len(high_noise.observations) > len(low_noise.observations)
    assert len(min_events.observations) >= 7
    assert len(high_noise.observations) <= 10


def test_scoped_family_contains_a_task_local_conflict_and_global_checkpoint() -> None:
    scenario = generate_scenario_by_family(
        profile="adversarial",
        family="global_vs_task_scoped_preference",
        scenario_count=10,
        seed=7,
        noise_rate=0.35,
    )
    checkpoint = scenario.checkpoints[0]
    task_claims = [claim for claim in scenario.claims if claim.scope.task_id is not None]

    assert len(task_claims) == 1
    assert task_claims[0].lifecycle.state.value == "active"
    assert task_claims[0].claim_id in checkpoint.expected_excluded_claim_ids
    assert checkpoint.request_scope_key == "global"
    task_observation = next(
        observation for observation in scenario.observations if task_claims[0].claim_id in observation.exposed_claim_ids
    )
    assert task_observation.task_id == task_claims[0].scope.task_id
