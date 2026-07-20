"""Scenario generation for the memory evolution simulator."""

from __future__ import annotations

import random

from memorii.core.benchmark.memory_evolution_sim.family_scenarios import build_family_scenario
from memorii.core.benchmark.memory_evolution_sim.opaque_ids import opaque_generated_scenario_ids
from memorii.core.benchmark.memory_evolution_sim.schemas import (
    LatentGraphScenario,
)

MEMORY_EVOLUTION_SCENARIO_FAMILIES = (
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
)


def generate_memory_evolution_sim_scenarios(
    *,
    profile: str = "smoke",
    scenario_count: int = 10,
    seed: int = 7,
    min_events: int | None = None,
    max_events: int | None = None,
    noise_rate: float | None = None,
) -> list[LatentGraphScenario]:
    rng = random.Random(seed)
    families = MEMORY_EVOLUTION_SCENARIO_FAMILIES
    scenarios: list[LatentGraphScenario] = []
    for index in range(scenario_count):
        family = families[index % len(families)]
        scenarios.append(
            opaque_generated_scenario_ids(
                build_family_scenario(
                    family=family,
                    profile=profile,
                    seed=seed,
                    index=index,
                    rng=rng,
                    min_events=min_events,
                    max_events=max_events,
                    noise_rate=noise_rate,
                )
            )
        )
    return scenarios
