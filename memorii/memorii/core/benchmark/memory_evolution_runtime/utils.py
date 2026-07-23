"""Shared helpers for runtime benchmark modules."""

from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from memorii.core.benchmark.memory_evolution_sim import LatentClaim, LatentEntity, LatentGraphScenario, LatentRelation


def entity_by_id(scenario: LatentGraphScenario, entity_id: str | None) -> LatentEntity | None:
    if entity_id is None:
        return None
    return next((entity for entity in scenario.entities if entity.entity_id == entity_id), None)

def claim_by_id(scenario: LatentGraphScenario, claim_id: str) -> LatentClaim | None:
    return next((claim for claim in scenario.claims if claim.claim_id == claim_id), None)

def relation_by_id(scenario: LatentGraphScenario, relation_id: str) -> LatentRelation | None:
    return next((relation for relation in scenario.relations if relation.relation_id == relation_id), None)

def stable_id(prefix: str, value: str) -> str:
    return f"{prefix}:{uuid5(NAMESPACE_URL, value)}"

def text_key(text: str) -> str:
    return " ".join(text.strip().split())

def ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
