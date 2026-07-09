"""Shared helpers for memory evolution simulator modules."""

from __future__ import annotations

import re

from memorii.core.benchmark.memory_evolution_sim.schemas import *  # noqa: F403


def _ordered_unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered

def _role_relation_ids(output: SimSystemOutput) -> list[str]:
    return _ordered_unique([
        *output.selected_relation_ids,
        *output.supporting_relation_ids,
        *output.rejected_relation_ids,
        *output.context_relation_ids,
    ])

def _claim_by_id(scenario: LatentGraphScenario, claim_id: str) -> LatentClaim | None:
    return next((claim for claim in scenario.claims if claim.claim_id == claim_id), None)

def _required_definition_claim_ids_for_selected_claims(
    scenario: LatentGraphScenario,
    output: SimSystemOutput,
) -> list[str]:
    selected_subjects: set[str] = set()
    for claim_id in output.selected_claim_ids:
        claim = _claim_by_id(scenario, claim_id)
        if claim is None or claim.predicate.predicate_id == "entity_type":
            continue
        selected_subjects.add(claim.subject.entity_id)
    required: list[str] = []
    for claim in scenario.claims:
        if claim.predicate.predicate_id != "entity_type":
            continue
        if claim.subject.entity_id in selected_subjects and _is_visible_claim(scenario, claim.claim_id):
            required.append(claim.claim_id)
    return _ordered_unique(required)

def _observation_by_id(scenario: LatentGraphScenario, event_id: str) -> SurfaceObservation | None:
    return next((observation for observation in scenario.observations if observation.event_id == event_id), None)

def _is_visible_claim(scenario: LatentGraphScenario, claim_id: str) -> bool:
    return any(claim_id in observation.exposed_claim_ids for observation in scenario.observations)

def _is_visible_entity(scenario: LatentGraphScenario, entity_id: str) -> bool:
    return any(entity_id in observation.exposed_entity_ids for observation in scenario.observations)

def _selected_noncurrent_claim_ids(
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
) -> list[str]:
    if checkpoint.checkpoint_type in {"historical_truth", "conflict_audit"}:
        return []
    bad_states = {
        SimLifecycleState.SUPERSEDED,
        SimLifecycleState.INVALIDATED,
        SimLifecycleState.EXPIRED,
        SimLifecycleState.EVIDENCE_ONLY,
        SimLifecycleState.ARCHIVED,
    }
    bad: list[str] = []
    for claim_id in output.selected_claim_ids:
        claim = _claim_by_id(scenario, claim_id)
        if claim is not None and claim.lifecycle.state in bad_states:
            bad.append(claim_id)
    return bad

def _claim_is_bad_support(
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    claim_id: str,
) -> bool:
    if checkpoint.checkpoint_type == "historical_truth" and claim_id in checkpoint.expected_claim_ids:
        return False
    if claim_id in checkpoint.expected_claim_ids:
        return False
    claim = _claim_by_id(scenario, claim_id)
    if claim is None:
        return False
    return (
        claim.lifecycle.state
        in {
            SimLifecycleState.SUPERSEDED,
            SimLifecycleState.INVALIDATED,
            SimLifecycleState.EXPIRED,
            SimLifecycleState.EVIDENCE_ONLY,
            SimLifecycleState.ARCHIVED,
        }
        or claim.observability == ObservabilityLabel.AMBIGUOUS
    )

def _bad_supporting_event_ids(
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    event_ids: list[str],
) -> list[str]:
    if checkpoint.checkpoint_type in {"historical_truth", "conflict_audit"}:
        return []
    bad_modalities = {"noise", "quoted_or_pasted", "third_party_claim", "hypothetical"}
    bad: list[str] = []
    for event_id in event_ids:
        if event_id in checkpoint.expected_citation_event_ids:
            continue
        observation = _observation_by_id(scenario, event_id)
        if observation is not None and observation.modality in bad_modalities:
            bad.append(event_id)
    return bad

def _context_only_noise_event_ids(scenario: LatentGraphScenario, output: SimSystemOutput) -> list[str]:
    bad: list[str] = []
    for event_id in output.context_citation_event_ids:
        observation = _observation_by_id(scenario, event_id)
        if observation is not None and (observation.modality == "noise" or "_noise_" in observation.event_id):
            bad.append(event_id)
    return bad

def _hidden_answer_leaks(scenario: LatentGraphScenario, output: SimSystemOutput) -> list[str]:
    text = _norm(" ".join(item for item in [output.answer, output.next_action, output.rationale] if item))
    if not text:
        return []
    leaks: list[str] = []
    for entity in scenario.entities:
        if entity.observability != ObservabilityLabel.HIDDEN:
            continue
        names = [entity.canonical_name, *[alias.alias_text for alias in entity.aliases]]
        if any(_norm(name) and _norm(name) in text for name in names):
            leaks.append(entity.entity_id)
    for claim in scenario.claims:
        if claim.observability != ObservabilityLabel.HIDDEN:
            continue
        if _norm(claim.object.value) and _norm(claim.object.value) in text:
            leaks.append(claim.claim_id)
    return _ordered_unique(leaks)

def _relation_bucket(checkpoint: OracleCheckpoint) -> str:
    if checkpoint.checkpoint_type == "source_trust_conflict":
        return "missing_conflict_relation"
    if checkpoint.checkpoint_type == "belief_ranking":
        return "belief_dependency_not_degraded"
    if checkpoint.checkpoint_type in {"entity_reconstruction", "claim_rekey"}:
        return "claim_rekey_error"
    return "missing_relation"

def _claim_bucket(checkpoint: OracleCheckpoint) -> str:
    return {
        "current_truth": "wrong_current_truth",
        "historical_truth": "historical_truth_lost",
        "source_trust_conflict": "source_trust_inversion",
        "modality_suppression": "modality_false_positive",
        "entity_disambiguation": "same_entity_role_confusion",
        "entity_split_repair": "entity_split_error",
        "claim_rekey": "claim_rekey_error",
        "belief_ranking": "belief_ranking_error",
        "execution_continuation": "abandoned_branch_selected",
    }.get(checkpoint.checkpoint_type, "claim_rekey_error")

def _answer_bucket(checkpoint: OracleCheckpoint) -> str:
    return "abandoned_branch_selected" if checkpoint.expected_next_action else _claim_bucket(checkpoint)

def _norm(value: str | None) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).split())

def _extract_rule_answer(text: str) -> str:
    for separator in [" = ", " is ", " owns "]:
        if separator in text:
            return text.split(separator, 1)[-1].strip().rstrip(".")
    return text.strip().rstrip(".")
