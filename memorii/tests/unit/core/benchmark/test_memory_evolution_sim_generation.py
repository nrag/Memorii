from __future__ import annotations

from collections import Counter

import pytest
from memorii.core.benchmark.memory_evolution_sim import (
    MEMORY_EVOLUTION_SCENARIO_FAMILIES,
    generate_memory_evolution_sim_scenarios,
    sim_reconstruction_context_for_checkpoint,
)
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
