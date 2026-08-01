"""Scenario generation for the memory evolution simulator."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from memorii.core.benchmark.memory_evolution_sim.contracts import (
    entity_split_contract,
    execution_contract,
    graph_contract,
    modality_suppression_contract,
    source_trust_contract,
    truth_contract,
)
from memorii.core.benchmark.memory_evolution_sim.schemas import (
    OracleCheckpoint,
    SurfaceObservation,
)


def checkpoint_for_family(
    *,
    rng: random.Random,
    family: str,
    suffix: str,
    timestamp: datetime,
    project: str,
    service: str,
    claim_type_project: str,
    claim_type_service: str,
    claim_alice_owner: str,
    claim_bob_owner: str,
    claim_task_owner: str,
    claim_carol_service: str,
    claim_ambiguous: str,
    expected_action_claim_id: str | None,
    relation_contradicts: str,
    relation_split: str,
    event_1: str,
    event_2: str,
    event_3: str,
    event_5: str,
    current_owner_name: str,
    old_owner_name: str,
    service_owner_name: str,
) -> OracleCheckpoint:
    if family == "entity_definition_before_role_claims":
        return OracleCheckpoint(
            checkpoint_id=f"cp_{suffix}_graph_shape",
            timestamp=timestamp,
            checkpoint_type="entity_reconstruction",
            query_or_task=rng.choice(
                [
                    "Reconstruct the Atlas project and service ownership graph.",
                    "Build the ownership graph for the Atlas project and the Atlas service.",
                ]
            ),
            task_contract=graph_contract(definition_claim_placement="selected_and_supporting_required"),
            expected_entity_ids=[project, service],
            expected_claim_ids=[claim_type_project, claim_type_service, claim_bob_owner, claim_carol_service],
            expected_relation_ids=[relation_contradicts],
            expected_citation_event_ids=[event_1, event_3, event_5],
            expected_excluded_claim_ids=[claim_ambiguous],
            expected_answer=f"{current_owner_name} owns Atlas Billing Migration; {service_owner_name} owns Atlas Platform Service",
            difficulty_tags=["entity_reconstruction", "entity_type_disambiguation"],
            severity="critical",
        )
    if family == "same_entity_vocabulary_different_role":
        return OracleCheckpoint(
            checkpoint_id=f"cp_{suffix}_current_owner",
            timestamp=timestamp,
            checkpoint_type="entity_disambiguation",
            query_or_task=rng.choice(
                [
                    "Who owns the Atlas billing migration now?",
                    "Who is the current owner of the Atlas billing migration?",
                ]
            ),
            task_contract=truth_contract(),
            expected_entity_ids=[project],
            expected_claim_ids=[claim_bob_owner],
            expected_citation_event_ids=[event_5],
            expected_excluded_entity_ids=[service],
            expected_excluded_claim_ids=[claim_carol_service, claim_ambiguous],
            expected_answer=current_owner_name,
            difficulty_tags=["same_entity_role_confusion"],
            severity="critical",
        )
    if family == "source_trust_conflict":
        return OracleCheckpoint(
            checkpoint_id=f"cp_{suffix}_trust_winner",
            timestamp=timestamp,
            checkpoint_type="source_trust_conflict",
            query_or_task=rng.choice(
                [
                    "Which Atlas migration owner should be trusted today?",
                    "Who is the trusted current owner for the Atlas migration?",
                ]
            ),
            task_contract=source_trust_contract(),
            expected_entity_ids=[project],
            expected_claim_ids=[claim_bob_owner],
            expected_relation_ids=[relation_contradicts],
            expected_citation_event_ids=[event_5],
            expected_excluded_claim_ids=[claim_ambiguous],
            expected_answer=current_owner_name,
            difficulty_tags=["source_trust", "conflict_resolution"],
            severity="critical",
        )
    if family == "modality_suppression":
        return OracleCheckpoint(
            checkpoint_id=f"cp_{suffix}_pasted_doc",
            timestamp=timestamp,
            checkpoint_type="modality_suppression",
            query_or_task=rng.choice(
                [
                    "Should the pasted onboarding note make Alice the current Atlas migration owner?",
                    "Does the stale pasted note change the current Atlas migration owner to Alice?",
                ]
            ),
            task_contract=modality_suppression_contract(),
            expected_entity_ids=[project],
            expected_claim_ids=[claim_bob_owner],
            expected_citation_event_ids=[event_5],
            expected_excluded_claim_ids=[claim_alice_owner],
            expected_answer="No",
            difficulty_tags=["quoted_or_pasted", "stale_memory"],
            severity="critical",
        )
    if family == "global_vs_task_scoped_preference":
        return OracleCheckpoint(
            checkpoint_id=f"cp_{suffix}_scope",
            timestamp=timestamp,
            checkpoint_type="scoped_truth",
            query_or_task=rng.choice(
                [
                    "Outside the incident, what ownership summary should be used for the Atlas migration?",
                    "At global scope, who should be treated as the Atlas migration owner?",
                ]
            ),
            task_contract=truth_contract().model_copy(
                update={"excluded_ids_must_be_rejected_or_contextualized": False}
            ),
            expected_entity_ids=[project],
            expected_claim_ids=[claim_bob_owner],
            expected_citation_event_ids=[event_5],
            expected_excluded_claim_ids=[claim_task_owner],
            expected_answer=current_owner_name,
            request_scope_key="global",
            difficulty_tags=["scope_resolution"],
            severity="high",
        )
    if family == "entity_alias_merge_and_relink":
        return OracleCheckpoint(
            checkpoint_id=f"cp_{suffix}_alias",
            timestamp=timestamp,
            checkpoint_type="claim_rekey",
            query_or_task=rng.choice(
                [
                    "Resolve Atlas migration ownership after alias confirmation.",
                    "After confirming the alias, reconstruct the Atlas migration owner.",
                ]
            ),
            task_contract=graph_contract(definition_claim_placement="selected_and_supporting_required"),
            expected_entity_ids=[project],
            expected_claim_ids=[claim_type_project, claim_bob_owner],
            expected_citation_event_ids=[event_1, event_5],
            expected_answer=current_owner_name,
            difficulty_tags=["alias_resolution", "claim_rekey"],
            severity="critical",
        )
    if family == "entity_split":
        return OracleCheckpoint(
            checkpoint_id=f"cp_{suffix}_split_owner",
            timestamp=timestamp,
            checkpoint_type="entity_split_repair",
            query_or_task=rng.choice(
                [
                    "Who owns the Atlas billing migration, not the service?",
                    "Identify the current owner of the Atlas project rather than the Atlas service.",
                ]
            ),
            task_contract=entity_split_contract(),
            expected_entity_ids=[project],
            expected_claim_ids=[claim_bob_owner],
            expected_relation_ids=[relation_split],
            expected_citation_event_ids=[event_5],
            expected_excluded_entity_ids=[service],
            expected_excluded_claim_ids=[claim_carol_service, claim_ambiguous],
            expected_answer=current_owner_name,
            difficulty_tags=["entity_split", "same_name_entity"],
            severity="critical",
        )
    if family == "belief_dependency_and_reranking":
        return OracleCheckpoint(
            checkpoint_id=f"cp_{suffix}_belief",
            timestamp=timestamp,
            checkpoint_type="belief_ranking",
            query_or_task=rng.choice(
                [
                    "Which Atlas migration ownership hypothesis should rank highest?",
                    "Rank the competing Atlas migration owner claims and select the strongest.",
                ]
            ),
            task_contract=graph_contract(belief_ranking_policy="required"),
            expected_entity_ids=[project],
            expected_claim_ids=[claim_bob_owner],
            expected_relation_ids=[relation_contradicts],
            expected_citation_event_ids=[event_5],
            expected_answer=f"{current_owner_name} owns Atlas Billing Migration",
            difficulty_tags=["belief_ranking", "belief_dependency"],
            severity="high",
        )
    if family == "abandoned_then_resumed_work":
        expected_action_ids: list[str] = []
        expected_execution_claim_ids: list[str] = []
        expected_execution_entity_ids: list[str] = []
        expected_execution_citation_event_ids: list[str] = []
        expected_excluded_entity_ids: list[str] = []
        expected_excluded_claim_ids: list[str] = []
        if expected_action_claim_id is not None:
            expected_execution_claim_ids.append(expected_action_claim_id)
            expected_execution_entity_ids.append(f"ent_{suffix}_branch_b")
            expected_execution_citation_event_ids.append(f"event_{suffix}_branch_b_progress")
            expected_action_ids.append(f"action:{expected_action_claim_id}")
            expected_excluded_entity_ids.append(f"ent_{suffix}_branch_a")
            expected_excluded_claim_ids.append(f"claim_{suffix}_branch_a_blocked")
        return OracleCheckpoint(
            checkpoint_id=f"cp_{suffix}_branch",
            timestamp=timestamp,
            checkpoint_type="execution_continuation",
            query_or_task=rng.choice(
                [
                    "Continue the previous Atlas migration ownership cleanup.",
                    "Resume the active branch of the Atlas owner cleanup.",
                ]
            ),
            task_contract=execution_contract(),
            expected_entity_ids=[],
            expected_claim_ids=[],
            expected_action_ids=expected_action_ids,
            expected_citation_event_ids=[],
            expected_excluded_entity_ids=expected_excluded_entity_ids,
            expected_execution_entity_ids=expected_execution_entity_ids,
            expected_execution_claim_ids=expected_execution_claim_ids,
            expected_execution_citation_event_ids=expected_execution_citation_event_ids,
            expected_excluded_claim_ids=expected_excluded_claim_ids,
            expected_next_action=f"continue {current_owner_name} owner cleanup",
            difficulty_tags=["execution_continuation"],
            severity="high",
        )
    return OracleCheckpoint(
        checkpoint_id=f"cp_{suffix}_current",
        timestamp=timestamp,
        checkpoint_type="current_truth",
        query_or_task=rng.choice(
            [
                "Who owns the Atlas billing migration now?",
                "Who is the current owner of the Atlas billing migration?",
            ]
        ),
        task_contract=truth_contract(),
        expected_entity_ids=[project],
        expected_claim_ids=[claim_bob_owner],
        expected_citation_event_ids=[event_5],
        expected_excluded_claim_ids=[claim_alice_owner],
        expected_answer=current_owner_name,
        difficulty_tags=["current_truth"],
        severity="critical",
    )


def add_noise_observations(
    *,
    observations: list[SurfaceObservation],
    suffix: str,
    base: datetime,
    rng: random.Random,
    profile: str,
    min_events: int | None,
    max_events: int | None,
    noise_rate: float | None,
) -> None:
    base_count = len(observations)
    if max_events is not None and max_events < base_count:
        raise ValueError(f"sim_max_events={max_events} is below required base event count {base_count}")
    requested_noise = int(round(max(0.0, noise_rate or 0.0) * 10))
    if noise_rate and noise_rate > 0:
        requested_noise = max(1, requested_noise)
    target_count = max(base_count + requested_noise, min_events or 0)
    if max_events is not None:
        target_count = min(target_count, max_events)
    templates = [
        "Noise: Atlas the dashboard color changed to {color}; this is unrelated to ownership.",
        "Someone pasted a vacation note about {person}; it is not a project ownership update.",
        "The word Atlas appears in a travel document about {place}, not the billing migration.",
        "Debug scratchpad says owner maybe TBD, but no source confirms it.",
        "Calendar reminder: review Atlas docs after lunch; no factual change stated.",
    ]
    colors = ["blue", "green", "gray", "violet"]
    people = ["Morgan", "Lee", "Quinn", "Avery"]
    places = ["a mountain range", "a map index", "a browser tab", "a book title"]
    noise_index = 0
    while len(observations) < target_count:
        template = rng.choice(templates)
        text = template.format(color=rng.choice(colors), person=rng.choice(people), place=rng.choice(places))
        noise_index += 1
        observations.append(
            SurfaceObservation(
                event_id=f"event_{suffix}_noise_{noise_index:02d}",
                transition_id=f"transition_{suffix}_noise_{noise_index:02d}",
                timestamp=base + timedelta(days=97 if profile == "long_horizon" else 70, minutes=noise_index),
                source_type=rng.choice(["user", "transcript", "assistant"]),
                # Preserve the random-stream schema used by captured opaque-ID
                # replays; every option is noise because this generator emits
                # explicitly non-factual distractors.
                modality=rng.choice(["noise", "noise", "noise"]),
                phase="dormancy" if profile == "long_horizon" else "interference",
                trust_level=rng.choice([0, 1]),
                text=text,
                hidden_distractor_ids=[f"hidden_{suffix}_noise_{noise_index:02d}"],
            )
        )


def checkpoint_with_horizon_metadata(
    *,
    checkpoint: OracleCheckpoint,
    observations: list[SurfaceObservation],
) -> OracleCheckpoint:
    event_by_id = {observation.event_id: observation for observation in observations}
    expected_event_ids = (
        checkpoint.expected_execution_citation_event_ids
        if checkpoint.checkpoint_type == "execution_continuation"
        else checkpoint.expected_citation_event_ids
    )
    support_observations = [event_by_id[event_id] for event_id in expected_event_ids if event_id in event_by_id]
    if support_observations:
        earliest_support_time = min(observation.timestamp for observation in support_observations)
        latest_support_time = max(observation.timestamp for observation in support_observations)
        horizon_distance = sum(
            1 for observation in observations if latest_support_time < observation.timestamp <= checkpoint.timestamp
        )
        source_event_age_days = max(
            0.0,
            (checkpoint.timestamp - earliest_support_time).total_seconds() / 86400.0,
        )
        interference_count = sum(
            1
            for observation in observations
            if earliest_support_time < observation.timestamp <= checkpoint.timestamp
            and observation.phase in {"interference", "dormancy"}
        )
    else:
        horizon_distance = 0
        source_event_age_days = 0.0
        interference_count = sum(1 for observation in observations if observation.phase in {"interference", "dormancy"})
    return checkpoint.model_copy(
        update={
            "horizon_distance": horizon_distance,
            "interference_count": interference_count,
            "source_event_age_days": round(source_event_age_days, 3),
            "required_retrieval_view": retrieval_view_for_checkpoint_type(checkpoint.checkpoint_type),
            "expected_stage_path": [
                "extraction",
                "validation",
                "lifecycle_evolution",
                "graph_projection",
                "alignment",
                "retrieval_decision",
            ],
        }
    )


def retrieval_view_for_checkpoint_type(checkpoint_type: str) -> str:
    if checkpoint_type == "historical_truth":
        return "historical_at"
    if checkpoint_type in {"source_trust_conflict", "conflict_audit"}:
        return "conflicts"
    if checkpoint_type in {"entity_reconstruction", "claim_rekey", "entity_split_repair", "belief_ranking"}:
        return "all_versions"
    if checkpoint_type == "modality_suppression":
        return "evidence_only"
    return "current"


def hidden_graph_ids_for_profile(*, profile: str, suffix: str) -> dict[str, str] | None:
    if profile not in {"adversarial", "long_horizon"}:
        return None
    return {
        "entity_id": f"ent_{suffix}_hidden_owner",
        "claim_id": f"claim_{suffix}_hidden_owner",
        "relation_id": f"rel_{suffix}_hidden_owner_conflict",
        "name": f"Hidden Owner {suffix}",
    }
