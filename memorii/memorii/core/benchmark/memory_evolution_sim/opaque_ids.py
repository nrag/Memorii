"""Deterministic, semantics-free identifiers for generated benchmark worlds."""

from __future__ import annotations

import hashlib
import random
from collections.abc import Mapping, Sequence
from typing import Any

from memorii.core.benchmark.memory_evolution_sim.schemas import LatentGraphScenario

_SINGLE_ID_FIELDS = frozenset(
    {
        "ambiguity_group_id",
        "checkpoint_id",
        "claim_id",
        "endpoint_id",
        "entity_id",
        "event_id",
        "extraction_run_id",
        "merge_target_entity_id",
        "relation_id",
        "request_scope_key",
        "request_session_id",
        "request_subject_entity_id",
        "request_task_id",
        "request_user_id",
        "scenario_id",
        "scope_key",
        "session_id",
        "split_from_entity_id",
        "superseded_by_claim_id",
        "task_id",
        "transition_id",
        "user_id",
    }
)

_SEMANTIC_ID_FIELDS = frozenset(
    {
        "predicate_id",
        "required_judge_ids",
        "belief_ranking_policy",
        "definition_claim_placement",
    }
)

_ID_SEQUENCE_FIELDS = frozenset(
    {
        "affected_claim_ids",
        "affected_entity_ids",
        "affected_relation_ids",
        "belief_ranking_ids",
        "child_entity_ids",
        "conflict_with_claim_ids",
        "context_claim_ids",
        "context_citation_event_ids",
        "context_entity_ids",
        "context_relation_ids",
        "contradicts_claim_ids",
        "defining_claim_ids",
        "depends_on_claim_ids",
        "derived_from_claim_ids",
        "evidence_event_ids",
        "expected_action_ids",
        "expected_citation_event_ids",
        "expected_claim_ids",
        "expected_entity_ids",
        "expected_excluded_claim_ids",
        "expected_excluded_entity_ids",
        "expected_execution_citation_event_ids",
        "expected_execution_claim_ids",
        "expected_execution_entity_ids",
        "expected_relation_ids",
        "expected_uncertain_ids",
        "exposed_claim_ids",
        "exposed_entity_ids",
        "exposed_relation_ids",
        "hidden_distractor_ids",
        "parent_entity_ids",
        "rejected_claim_ids",
        "rejected_entity_ids",
        "rejected_relation_ids",
        "rejection_citation_event_ids",
        "relation_ids",
        "selected_claim_ids",
        "selected_entity_ids",
        "selected_relation_ids",
        "source_event_ids",
        "supporting_citation_event_ids",
        "supporting_claim_ids",
        "supporting_relation_ids",
        "supersedes_claim_ids",
        "uncertain_ids",
        "visible_claim_ids",
        "visible_entity_ids",
        "visible_relation_ids",
    }
)


def _is_global_scope(value: object) -> bool:
    return value == "global"


def _collect_ids(value: object, *, field_name: str | None = None) -> set[str]:
    if field_name in _SEMANTIC_ID_FIELDS:
        return set()
    if field_name in _SINGLE_ID_FIELDS:
        if isinstance(value, str) and value and not _is_global_scope(value):
            return {value}
        return set()
    if field_name in _ID_SEQUENCE_FIELDS:
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            return set()
        return {item for item in value if isinstance(item, str) and item and not _is_global_scope(item)}
    if field_name is not None and (
        field_name.endswith("_id") or field_name.endswith("_ids")
    ):
        raise ValueError(f"unclassified benchmark identifier field: {field_name}")
    if isinstance(value, Mapping):
        collected: set[str] = set()
        for key, item in value.items():
            collected.update(_collect_ids(item, field_name=str(key)))
        return collected
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        collected = set()
        for item in value:
            collected.update(_collect_ids(item))
        return collected
    return set()


def _opaque_mapping(ids: set[str], *, permutation_seed: str) -> dict[str, str]:
    ordered = sorted(ids)
    rng_seed = int.from_bytes(hashlib.sha256(permutation_seed.encode("utf-8")).digest(), "big")
    rng = random.Random(rng_seed)
    rng.shuffle(ordered)
    mapping: dict[str, str] = {}
    for ordinal, source_id in enumerate(ordered):
        token = hashlib.sha256(f"{permutation_seed}:{ordinal}".encode()).hexdigest()[:20]
        opaque_id = f"oid_{token}"
        namespace = source_id.partition(":")[0]
        mapping[source_id] = (
            f"{namespace}:{opaque_id}"
            if namespace in {"task", "session", "user"}
            else opaque_id
        )
    for source_id in ordered:
        if source_id.startswith("action:") and source_id.removeprefix("action:") in mapping:
            mapping[source_id] = f"action:{mapping[source_id.removeprefix('action:')]}"
    return mapping


def _replace_ids(value: Any, *, mapping: Mapping[str, str], field_name: str | None = None) -> Any:
    if field_name in _SINGLE_ID_FIELDS:
        return mapping.get(value, value) if isinstance(value, str) else value
    if field_name in _ID_SEQUENCE_FIELDS:
        if not isinstance(value, list):
            return value
        return [mapping.get(item, item) if isinstance(item, str) else item for item in value]
    if isinstance(value, dict):
        return {
            key: _replace_ids(item, mapping=mapping, field_name=str(key))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_replace_ids(item, mapping=mapping) for item in value]
    return value


def remap_scenario_ids(
    scenario: LatentGraphScenario,
    *,
    permutation_seed: str,
) -> LatentGraphScenario:
    """Return an equivalent scenario with all machine identifiers permuted.

    The mapping is intentionally not retained on the scenario. Judges consume
    the same remapped graph, so no decoder or semantic identifier side channel
    is required in live benchmark execution.
    """

    payload = scenario.model_dump(mode="python")
    mapping = _opaque_mapping(_collect_ids(payload), permutation_seed=permutation_seed)
    remapped = _replace_ids(payload, mapping=mapping)
    return LatentGraphScenario.model_validate(remapped)


def opaque_generated_scenario_ids(scenario: LatentGraphScenario) -> LatentGraphScenario:
    """Apply the stable presentation permutation used by generated scenarios."""

    return remap_scenario_ids(
        scenario,
        permutation_seed=f"memory-evolution:{scenario.seed}:{scenario.scenario_id}",
    )
