"""Surface-observation construction for generated simulator families."""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Literal, TypeAlias

from memorii.core.benchmark.memory_evolution_sim.checkpoints import (
    add_noise_observations,
    hidden_graph_ids_for_profile,
)
from memorii.core.benchmark.memory_evolution_sim.schemas import SurfaceObservation

ActionObservationSpec: TypeAlias = tuple[
    str,
    datetime,
    Literal["setup", "interference", "evolution"],
    str,
    str,
    str,
]


def build_family_observations(
    *,
    family: str,
    profile: str,
    suffix: str,
    base: datetime,
    rng: random.Random,
    project: str,
    service: str,
    alice: str,
    bob: str,
    carol: str,
    old_owner_name: str,
    current_owner_name: str,
    service_owner_name: str,
    setup_trust: int,
    service_trust: int,
    stale_trust: int,
    tool_trust: int,
    ambiguity_trust: int,
    event_1: str,
    event_2: str,
    event_3: str,
    event_4: str,
    event_5: str,
    claim_type_project: str,
    claim_type_service: str,
    claim_alice_owner: str,
    claim_bob_owner: str,
    claim_task_owner: str,
    claim_carol_service: str,
    claim_ambiguous: str,
    branch_a: str,
    branch_b: str,
    claim_branch_a_started: str,
    claim_branch_a_blocked: str,
    claim_branch_b_started: str,
    claim_branch_b_progress: str,
    branch_a_started_time: datetime,
    branch_a_blocked_time: datetime,
    branch_b_started_time: datetime,
    branch_b_progress_time: datetime,
    relation_contradicts: str,
    relation_alias: str,
    relation_split: str,
    incident_task_id: str,
    min_events: int | None,
    max_events: int | None,
    noise_rate: float | None,
) -> tuple[list[SurfaceObservation], dict[str, str] | None, SurfaceObservation | None]:
    observations = [
        SurfaceObservation(
            event_id=event_1,
            transition_id=f"transition_{suffix}_001",
            timestamp=base,
            source_type="user",
            modality="assertion",
            phase="setup",
            trust_level=setup_trust,
            text=rng.choice(
                [
                    "Atlas is the Q2 billing migration project for Finance Ops.",
                    "Finance Ops tracks Atlas as the billing migration project for Q2.",
                    "The Atlas workstream is the Q2 billing migration project owned by Finance Ops.",
                ]
            ),
            exposed_entity_ids=[project],
            exposed_claim_ids=[claim_type_project],
            exposed_relation_ids=[relation_alias],
        ),
        SurfaceObservation(
            event_id=event_2,
            transition_id=f"transition_{suffix}_002",
            timestamp=base + timedelta(minutes=5),
            source_type="user",
            modality="assertion",
            phase="setup",
            trust_level=setup_trust,
            text=f"{old_owner_name} owns Atlas for now.",
            exposed_entity_ids=[project, alice],
            exposed_claim_ids=[claim_alice_owner],
        ),
        SurfaceObservation(
            event_id=event_3,
            transition_id=f"transition_{suffix}_003",
            timestamp=base + timedelta(days=4),
            source_type="user",
            modality="assertion",
            phase="interference",
            trust_level=service_trust,
            text=(
                f"Separate note: Atlas service is the internal platform service, and "
                f"{service_owner_name} owns that service."
            ),
            exposed_entity_ids=[service, carol],
            exposed_claim_ids=[claim_type_service, claim_carol_service],
            exposed_relation_ids=[relation_split] if family == "entity_split" else [],
        ),
        SurfaceObservation(
            event_id=event_4,
            transition_id=f"transition_{suffix}_004",
            timestamp=base + timedelta(days=46),
            source_type="user",
            modality="quoted_or_pasted",
            phase="interference",
            trust_level=stale_trust,
            text=f"Pasting old onboarding notes: Atlas owner is {old_owner_name}. This might be stale.",
            exposed_entity_ids=[project, alice],
            exposed_claim_ids=[claim_alice_owner],
        ),
        SurfaceObservation(
            event_id=event_5,
            transition_id=f"transition_{suffix}_005",
            timestamp=base + timedelta(days=66),
            source_type="tool",
            modality="tool_result",
            phase="evolution",
            trust_level=tool_trust,
            text=f"org_directory result: Atlas billing migration owner = {current_owner_name}.",
            exposed_entity_ids=[project, bob],
            exposed_claim_ids=[claim_bob_owner],
        ),
    ]
    if family in {
        "same_entity_vocabulary_different_role",
        "entity_split",
        "source_trust_conflict",
        "entity_definition_before_role_claims",
        "belief_dependency_and_reranking",
    }:
        observations.append(
            SurfaceObservation(
                event_id=f"event_{suffix}_006",
                transition_id=f"transition_{suffix}_006",
                timestamp=base + timedelta(days=67),
                source_type="transcript",
                modality="third_party_claim",
                phase="interference",
                trust_level=ambiguity_trust,
                text=(
                    f"In standup, someone said {service_owner_name} owns Atlas, "
                    "but they may have meant the Atlas service."
                ),
                exposed_entity_ids=[project, service, carol],
                exposed_claim_ids=[claim_ambiguous],
                exposed_relation_ids=[relation_contradicts],
            )
        )

    if family == "global_vs_task_scoped_preference":
        observations.append(
            SurfaceObservation(
                event_id=f"event_{suffix}_task_scope",
                transition_id=f"transition_{suffix}_task_scope",
                timestamp=base + timedelta(days=67),
                source_type="user",
                modality="assertion",
                phase="interference",
                trust_level=3,
                text=(
                    f"For incident task {incident_task_id}, {old_owner_name} is the temporary Atlas "
                    "migration owner; this assignment is task-local."
                ),
                task_id=incident_task_id,
                exposed_entity_ids=[project, alice],
                exposed_claim_ids=[claim_task_owner],
            )
        )

    hidden_ids = hidden_graph_ids_for_profile(profile=profile, suffix=suffix)
    if hidden_ids is not None:
        observations.append(
            SurfaceObservation(
                event_id=f"event_{suffix}_uncertainty_hint",
                transition_id=f"transition_{suffix}_uncertainty_hint",
                timestamp=base + timedelta(days=69),
                source_type="transcript",
                modality=rng.choice(["third_party_claim", "hypothetical", "noise"]),
                phase="interference",
                trust_level=rng.choice([0, 1]),
                text=rng.choice(
                    [
                        "Someone hinted there may be another Atlas owner, but no source confirmed who.",
                        "A private HR note was referenced but not shown, so no ownership change can be verified.",
                        "The migration owner might have changed again, but the directory lookup is unavailable.",
                    ]
                ),
                hidden_distractor_ids=[
                    hidden_ids["entity_id"],
                    hidden_ids["claim_id"],
                    hidden_ids["relation_id"],
                ],
            )
        )

    ambiguity_observation = next(
        (observation for observation in observations if observation.event_id == f"event_{suffix}_006"),
        None,
    )
    if family == "abandoned_then_resumed_work":
        action_observations: tuple[ActionObservationSpec, ...] = (
            (
                "branch_a_started",
                branch_a_started_time,
                "setup",
                "Atlas cleanup Branch A started: re-open old owner notes.",
                branch_a,
                claim_branch_a_started,
            ),
            (
                "branch_a_blocked",
                branch_a_blocked_time,
                "interference",
                "Atlas cleanup Branch A blocked on stale onboarding notes.",
                branch_a,
                claim_branch_a_blocked,
            ),
            (
                "branch_b_started",
                branch_b_started_time,
                "evolution",
                "Atlas cleanup Branch B started: verify the org-directory owner path.",
                branch_b,
                claim_branch_b_started,
            ),
            (
                "branch_b_progress",
                branch_b_progress_time,
                "evolution",
                "Atlas cleanup Branch B in_progress: continue the org-directory owner cleanup.",
                branch_b,
                claim_branch_b_progress,
            ),
        )
        observations.extend(
            SurfaceObservation(
                event_id=f"event_{suffix}_{label}",
                transition_id=f"transition_{suffix}_{label}",
                timestamp=timestamp,
                source_type="user",
                modality="assertion",
                phase=phase,
                trust_level=3,
                text=text,
                exposed_entity_ids=[branch, project],
                exposed_claim_ids=[claim_id],
            )
            for label, timestamp, phase, text, branch, claim_id in action_observations
        )

    if profile == "long_horizon":
        observations.extend(
            [
                SurfaceObservation(
                    event_id=f"event_{suffix}_late_stale_resurface",
                    transition_id=f"transition_{suffix}_late_stale_resurface",
                    timestamp=base + timedelta(days=92),
                    source_type="transcript",
                    modality="quoted_or_pasted",
                    phase="dormancy",
                    trust_level=1,
                    text=(
                        f"Archived kickoff notes resurfaced and still list Atlas owner as {old_owner_name}; "
                        "treat this as archival context unless verified."
                    ),
                    exposed_entity_ids=[project, alice],
                    exposed_claim_ids=[claim_alice_owner],
                ),
                SurfaceObservation(
                    event_id=f"event_{suffix}_late_scope_interference",
                    transition_id=f"transition_{suffix}_late_scope_interference",
                    timestamp=base + timedelta(days=96),
                    source_type="assistant",
                    modality="noise",
                    phase="dormancy",
                    trust_level=0,
                    text=(
                        "Scratchpad: incident-review formatting preferences should not leak into normal "
                        "Atlas status updates."
                    ),
                ),
            ]
        )

    add_noise_observations(
        observations=observations,
        suffix=suffix,
        base=base,
        rng=rng,
        profile=profile,
        min_events=min_events,
        max_events=max_events,
        noise_rate=noise_rate,
    )
    return observations, hidden_ids, ambiguity_observation
