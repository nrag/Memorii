from __future__ import annotations

from collections.abc import Iterable
from typing import Literal, TypeVar

from memorii.core.benchmark.memory_evolution_sim import (
    LatentClaim,
    LatentEntity,
    LatentGraphScenario,
    LatentRelation,
    OracleCheckpoint,
    generate_memory_evolution_sim_scenarios,
)


SimProfile = Literal["smoke", "adversarial", "long_horizon"]
T = TypeVar("T")


def generate_scenario_by_family(
    *,
    profile: SimProfile,
    family: str,
    seed: int = 7,
    scenario_count: int = 10,
    min_events: int | None = None,
    max_events: int | None = None,
    noise_rate: float = 0.0,
) -> LatentGraphScenario:
    scenarios = generate_memory_evolution_sim_scenarios(
        profile=profile,
        scenario_count=scenario_count,
        seed=seed,
        min_events=min_events,
        max_events=max_events,
        noise_rate=noise_rate,
    )
    return _single_by_value(
        scenarios,
        value=family,
        attr="family",
        label="scenario family",
    )


def checkpoint_by_type(
    scenario: LatentGraphScenario,
    checkpoint_type: str,
    *,
    index: int = 0,
) -> OracleCheckpoint:
    matches = [checkpoint for checkpoint in scenario.checkpoints if checkpoint.checkpoint_type == checkpoint_type]
    return _by_index(
        matches,
        index=index,
        label=f"checkpoint type {checkpoint_type!r}",
        available=[checkpoint.checkpoint_type for checkpoint in scenario.checkpoints],
    )


def entity_by_role(
    scenario: LatentGraphScenario,
    role: str,
    *,
    index: int = 0,
) -> LatentEntity:
    matches = [entity for entity in scenario.entities if role in entity.evaluation_roles]
    return _by_index(
        matches,
        index=index,
        label=f"entity role {role!r}",
        available=_available_roles(entity.evaluation_roles for entity in scenario.entities),
    )


def claim_by_role(
    scenario: LatentGraphScenario,
    role: str,
    *,
    index: int = 0,
) -> LatentClaim:
    matches = [claim for claim in scenario.claims if role in claim.evaluation_roles]
    return _by_index(
        matches,
        index=index,
        label=f"claim role {role!r}",
        available=_available_roles(claim.evaluation_roles for claim in scenario.claims),
    )


def relation_by_role(
    scenario: LatentGraphScenario,
    role: str,
    *,
    index: int = 0,
) -> LatentRelation:
    matches = [relation for relation in scenario.relations if role in relation.evaluation_roles]
    return _by_index(
        matches,
        index=index,
        label=f"relation role {role!r}",
        available=_available_roles(relation.evaluation_roles for relation in scenario.relations),
    )


def _single_by_value(
    items: Iterable[LatentGraphScenario],
    *,
    value: str,
    attr: str,
    label: str,
) -> LatentGraphScenario:
    item_list = list(items)
    matches = [item for item in item_list if getattr(item, attr) == value]
    if len(matches) != 1:
        available = sorted(str(getattr(item, attr)) for item in item_list)
        raise AssertionError(f"Expected exactly one {label} {value!r}, found {len(matches)}. Available: {available}")
    return matches[0]


def _by_index(
    items: list[T],
    *,
    index: int,
    label: str,
    available: list[str],
) -> T:
    if 0 <= index < len(items):
        return items[index]
    raise AssertionError(f"Missing {label} at index {index}. Available: {sorted(set(available))}")


def _available_roles(role_groups: Iterable[list[str]]) -> list[str]:
    return sorted({role for roles in role_groups for role in roles})
