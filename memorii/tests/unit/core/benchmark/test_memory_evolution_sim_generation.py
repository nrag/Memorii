from __future__ import annotations

from memorii.core.benchmark.memory_evolution_sim import generate_memory_evolution_sim_scenarios
from tests.unit.core.benchmark.memory_evolution_test_helpers import generate_scenario_by_family


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
    low_noise = generate_scenario_by_family(
        profile="adversarial",
        family="entity_definition_before_role_claims",
        scenario_count=10,
        seed=7,
        noise_rate=0.0,
        max_events=8,
    )
    high_noise = generate_scenario_by_family(
        profile="adversarial",
        family="entity_definition_before_role_claims",
        scenario_count=10,
        seed=7,
        noise_rate=0.35,
        max_events=8,
    )
    min_events = generate_scenario_by_family(
        profile="adversarial",
        family="entity_definition_before_role_claims",
        scenario_count=10,
        seed=7,
        noise_rate=0.0,
        min_events=7,
        max_events=8,
    )

    assert len(high_noise.observations) > len(low_noise.observations)
    assert len(min_events.observations) >= 7
    assert len(high_noise.observations) <= 8
