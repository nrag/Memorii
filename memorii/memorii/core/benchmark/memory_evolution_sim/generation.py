"""Scenario generation for the memory evolution simulator."""

from __future__ import annotations

import random
import re
from datetime import UTC, datetime, timedelta

from memorii.core.benchmark.memory_evolution_sim.schemas import *  # noqa: F403


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
    families = [
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
    scenarios: list[LatentGraphScenario] = []
    for index in range(scenario_count):
        family = families[index % len(families)]
        scenarios.append(
            _build_family_scenario(
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
    return scenarios

def _build_family_scenario(
    *,
    family: str,
    profile: str,
    seed: int,
    index: int,
    rng: random.Random,
    min_events: int | None = None,
    max_events: int | None = None,
    noise_rate: float | None = None,
) -> LatentGraphScenario:
    base = datetime(2026, 1, 5, 9, tzinfo=UTC) + timedelta(days=index)
    suffix = f"{index:02d}"
    project = f"ent_{suffix}_atlas_migration"
    service = f"ent_{suffix}_atlas_service"
    alice = f"ent_{suffix}_previous_owner"
    bob = f"ent_{suffix}_current_owner"
    carol = f"ent_{suffix}_service_owner"
    old_owner_name = rng.choice(["Alice", "Priya", "Marta", "Eli"])
    current_owner_name = rng.choice(["Bob", "Nadia", "Owen", "Rina"])
    service_owner_name = rng.choice(["Carol", "Nikhil", "Sam", "Iris"])
    while current_owner_name == old_owner_name:
        current_owner_name = rng.choice(["Bob", "Nadia", "Owen", "Rina"])
    while service_owner_name in {old_owner_name, current_owner_name}:
        service_owner_name = rng.choice(["Carol", "Nikhil", "Sam", "Iris"])
    event_1 = f"event_{suffix}_001"
    event_2 = f"event_{suffix}_002"
    event_3 = f"event_{suffix}_003"
    event_4 = f"event_{suffix}_004"
    event_5 = f"event_{suffix}_005"
    claim_type_project = f"claim_{suffix}_project_type"
    claim_type_service = f"claim_{suffix}_service_type"
    claim_alice_owner = f"claim_{suffix}_previous_owner_old"
    claim_bob_owner = f"claim_{suffix}_current_owner"
    claim_carol_service = f"claim_{suffix}_service_owner"
    claim_ambiguous = f"claim_{suffix}_ambiguous_service_owner_atlas"
    branch_a = f"ent_{suffix}_branch_a"
    branch_b = f"ent_{suffix}_branch_b"
    claim_branch_a_started = f"claim_{suffix}_branch_a_started"
    claim_branch_a_blocked = f"claim_{suffix}_branch_a_blocked"
    claim_branch_b_started = f"claim_{suffix}_branch_b_started"
    claim_branch_b_progress = f"claim_{suffix}_branch_b_progress"
    relation_contradicts = f"rel_{suffix}_owner_conflict"
    relation_alias = f"rel_{suffix}_alias"

    observations = [
        SurfaceObservation(
            event_id=event_1,
            transition_id=f"transition_{suffix}_001",
            timestamp=base,
            source_type="user",
            modality="assertion",
            phase="setup",
            trust_level=3,
            text=rng.choice([
                "Atlas is the Q2 billing migration project for Finance Ops.",
                "Finance Ops tracks Atlas as the billing migration project for Q2.",
                "The Atlas workstream is the Q2 billing migration project owned by Finance Ops.",
            ]),
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
            trust_level=3,
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
            trust_level=3,
            text=f"Separate note: Atlas service is the internal platform service, and {service_owner_name} owns that service.",
            exposed_entity_ids=[service, carol],
            exposed_claim_ids=[claim_type_service, claim_carol_service],
        ),
        SurfaceObservation(
            event_id=event_4,
            transition_id=f"transition_{suffix}_004",
            timestamp=base + timedelta(days=46),
            source_type="user",
            modality="quoted_or_pasted",
            phase="interference",
            trust_level=1,
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
            trust_level=5,
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
                trust_level=1,
                text=f"In standup, someone said {service_owner_name} owns Atlas, but they may have meant the Atlas service.",
                exposed_entity_ids=[project, service, carol],
                exposed_claim_ids=[claim_ambiguous],
                exposed_relation_ids=[relation_contradicts],
            )
        )

    hidden_ids = _hidden_graph_ids_for_profile(profile=profile, suffix=suffix)
    if hidden_ids is not None:
        hidden_event_id = f"event_{suffix}_uncertainty_hint"
        observations.append(
            SurfaceObservation(
                event_id=hidden_event_id,
                transition_id=f"transition_{suffix}_uncertainty_hint",
                timestamp=base + timedelta(days=69),
                source_type="transcript",
                modality=rng.choice(["third_party_claim", "hypothetical", "noise"]),
                phase="interference",
                trust_level=rng.choice([0, 1]),
                text=rng.choice([
                    "Someone hinted there may be another Atlas owner, but no source confirmed who.",
                    "A private HR note was referenced but not shown, so no ownership change can be verified.",
                    "The migration owner might have changed again, but the directory lookup is unavailable.",
                ]),
                hidden_distractor_ids=[
                    hidden_ids["entity_id"],
                    hidden_ids["claim_id"],
                    hidden_ids["relation_id"],
                ],
            )
        )

    ambiguity_observation = next((obs for obs in observations if obs.event_id == f"event_{suffix}_006"), None)

    if profile == "long_horizon":
        if family == "abandoned_then_resumed_work":
            observations.extend(
                [
                    SurfaceObservation(
                        event_id=f"event_{suffix}_branch_a_started",
                        transition_id=f"transition_{suffix}_branch_a_started",
                        timestamp=base + timedelta(days=72),
                        source_type="user",
                        modality="assertion",
                        phase="setup",
                        trust_level=3,
                        text="Atlas cleanup Branch A started: re-open old owner notes.",
                        exposed_entity_ids=[branch_a, project],
                        exposed_claim_ids=[claim_branch_a_started],
                    ),
                    SurfaceObservation(
                        event_id=f"event_{suffix}_branch_a_blocked",
                        transition_id=f"transition_{suffix}_branch_a_blocked",
                        timestamp=base + timedelta(days=73),
                        source_type="user",
                        modality="assertion",
                        phase="interference",
                        trust_level=3,
                        text="Atlas cleanup Branch A blocked on stale onboarding notes.",
                        exposed_entity_ids=[branch_a, project],
                        exposed_claim_ids=[claim_branch_a_blocked],
                    ),
                    SurfaceObservation(
                        event_id=f"event_{suffix}_branch_b_started",
                        transition_id=f"transition_{suffix}_branch_b_started",
                        timestamp=base + timedelta(days=74),
                        source_type="user",
                        modality="assertion",
                        phase="evolution",
                        trust_level=3,
                        text="Atlas cleanup Branch B started: verify the org-directory owner path.",
                        exposed_entity_ids=[branch_b, project],
                        exposed_claim_ids=[claim_branch_b_started],
                    ),
                    SurfaceObservation(
                        event_id=f"event_{suffix}_branch_b_progress",
                        transition_id=f"transition_{suffix}_branch_b_progress",
                        timestamp=base + timedelta(days=75),
                        source_type="user",
                        modality="assertion",
                        phase="evolution",
                        trust_level=3,
                        text="Atlas cleanup Branch B in_progress: continue the org-directory owner cleanup.",
                        exposed_entity_ids=[branch_b, project],
                        exposed_claim_ids=[claim_branch_b_progress],
                    ),
                ]
            )
        observations.append(
            SurfaceObservation(
                event_id=f"event_{suffix}_late_stale_resurface",
                transition_id=f"transition_{suffix}_late_stale_resurface",
                timestamp=base + timedelta(days=92),
                source_type="transcript",
                modality="quoted_or_pasted",
                phase="dormancy",
                trust_level=1,
                text=f"Archived kickoff notes resurfaced and still list Atlas owner as {old_owner_name}; treat this as archival context unless verified.",
                exposed_entity_ids=[project, alice],
                exposed_claim_ids=[claim_alice_owner],
            )
        )
        observations.append(
            SurfaceObservation(
                event_id=f"event_{suffix}_late_scope_interference",
                transition_id=f"transition_{suffix}_late_scope_interference",
                timestamp=base + timedelta(days=96),
                source_type="assistant",
                modality="noise",
                phase="dormancy",
                trust_level=0,
                text="Scratchpad: incident-review formatting preferences should not leak into normal Atlas status updates.",
            )
        )

    _add_noise_observations(
        observations=observations,
        suffix=suffix,
        base=base,
        rng=rng,
        profile=profile,
        min_events=min_events,
        max_events=max_events,
        noise_rate=noise_rate,
    )

    transitions = [
        WorldTransition(
            transition_id=obs.transition_id,
            timestamp=obs.timestamp,
            transition_type="surface_observation",
            affected_entity_ids=obs.exposed_entity_ids,
            affected_claim_ids=obs.exposed_claim_ids,
            affected_relation_ids=obs.exposed_relation_ids,
            rationale=f"deterministic transition for {family}",
        )
        for obs in observations
    ]
    entities = [
        _entity(project, "Atlas Billing Migration", "project", base, event_1, claim_type_project, [relation_alias]),
        _entity(service, "Atlas Platform Service", "service", base + timedelta(days=4), event_3, claim_type_service, []),
        _person(alice, old_owner_name, base + timedelta(minutes=5), event_2),
        _person(bob, current_owner_name, base + timedelta(days=66), event_5),
        _person(carol, service_owner_name, base + timedelta(days=4), event_3),
    ]
    if profile == "long_horizon" and family == "abandoned_then_resumed_work":
        entities.extend(
            [
                _task_entity(branch_a, "Atlas Cleanup Branch A", base + timedelta(days=72), f"event_{suffix}_branch_a_started", claim_branch_a_started),
                _task_entity(branch_b, "Atlas Cleanup Branch B", base + timedelta(days=74), f"event_{suffix}_branch_b_started", claim_branch_b_started),
            ]
        )
    claims = [
        _claim(
            claim_id=claim_type_project,
            kind="entity_attribute",
            subject_id=project,
            subject_name="Atlas Billing Migration",
            subject_type="project",
            predicate_id="entity_type",
            object_value="project",
            event_id=event_1,
            quote=observations[0].text,
            transition_id=observations[0].transition_id,
            timestamp=base,
            state=SimLifecycleState.ACTIVE,
            roles=["entity_reconstruction", "entity_type_missing"],
        ),
        _claim(
            claim_id=claim_type_service,
            kind="entity_attribute",
            subject_id=service,
            subject_name="Atlas Platform Service",
            subject_type="service",
            predicate_id="entity_type",
            object_value="service",
            event_id=event_3,
            quote=observations[2].text,
            transition_id=observations[2].transition_id,
            timestamp=base + timedelta(days=4),
            state=SimLifecycleState.ACTIVE,
            roles=["entity_reconstruction", "entity_disambiguation"],
        ),
        _claim(
            claim_id=claim_alice_owner,
            kind="relationship_fact",
            subject_id=project,
            subject_name="Atlas Billing Migration",
            subject_type="project",
            predicate_id="owner",
            object_value=old_owner_name,
            object_entity_id=alice,
            event_id=event_2,
            quote=observations[1].text,
            transition_id=observations[1].transition_id,
            timestamp=base + timedelta(minutes=5),
            state=SimLifecycleState.SUPERSEDED,
            valid_to=base + timedelta(days=66),
            roles=["historical_truth"],
        ),
        _claim(
            claim_id=claim_bob_owner,
            kind="relationship_fact",
            subject_id=project,
            subject_name="Atlas Billing Migration",
            subject_type="project",
            predicate_id="owner",
            object_value=current_owner_name,
            object_entity_id=bob,
            event_id=event_5,
            quote=observations[4].text,
            transition_id=observations[4].transition_id,
            timestamp=base + timedelta(days=66),
            state=SimLifecycleState.ACTIVE,
            roles=["current_truth", "source_trust"],
        ),
        _claim(
            claim_id=claim_carol_service,
            kind="relationship_fact",
            subject_id=service,
            subject_name="Atlas Platform Service",
            subject_type="service",
            predicate_id="owner",
            object_value=service_owner_name,
            object_entity_id=carol,
            event_id=event_3,
            quote=observations[2].text,
            transition_id=observations[2].transition_id,
            timestamp=base + timedelta(days=4),
            state=SimLifecycleState.ACTIVE,
            roles=["entity_disambiguation"],
        ),
        _claim(
            claim_id=claim_ambiguous,
            kind="contradiction",
            subject_id=project,
            subject_name="Atlas Billing Migration",
            subject_type="project",
            predicate_id="owner",
            object_value=service_owner_name,
            object_entity_id=carol,
            event_id=ambiguity_observation.event_id if ambiguity_observation is not None else event_5,
            quote=ambiguity_observation.text if ambiguity_observation is not None else observations[4].text,
            transition_id=ambiguity_observation.transition_id if ambiguity_observation is not None else observations[4].transition_id,
            timestamp=ambiguity_observation.timestamp if ambiguity_observation is not None else observations[4].timestamp,
            state=SimLifecycleState.INVALIDATED,
            roles=["modality_suppression", "conflict_detection"],
            observability=ObservabilityLabel.AMBIGUOUS,
            confidence=_confidence(0.35),
        ),
    ]
    if profile == "long_horizon" and family == "abandoned_then_resumed_work":
        action_claim_specs = [
            (claim_branch_a_started, branch_a, "Atlas Cleanup Branch A", "started", f"event_{suffix}_branch_a_started", f"transition_{suffix}_branch_a_started", base + timedelta(days=72), "Atlas cleanup Branch A started: re-open old owner notes.", SimLifecycleState.SUPERSEDED),
            (claim_branch_a_blocked, branch_a, "Atlas Cleanup Branch A", "blocked", f"event_{suffix}_branch_a_blocked", f"transition_{suffix}_branch_a_blocked", base + timedelta(days=73), "Atlas cleanup Branch A blocked on stale onboarding notes.", SimLifecycleState.ACTIVE),
            (claim_branch_b_started, branch_b, "Atlas Cleanup Branch B", "started", f"event_{suffix}_branch_b_started", f"transition_{suffix}_branch_b_started", base + timedelta(days=74), "Atlas cleanup Branch B started: verify the org-directory owner path.", SimLifecycleState.SUPERSEDED),
            (claim_branch_b_progress, branch_b, "Atlas Cleanup Branch B", "in_progress", f"event_{suffix}_branch_b_progress", f"transition_{suffix}_branch_b_progress", base + timedelta(days=75), "Atlas cleanup Branch B in_progress: continue the org-directory owner cleanup.", SimLifecycleState.ACTIVE),
        ]
        for claim_id, subject_id, subject_name, object_value, event_id, transition_id, timestamp, quote, state in action_claim_specs:
            claims.append(
                _claim(
                    claim_id=claim_id,
                    kind="action_state",
                    subject_id=subject_id,
                    subject_name=subject_name,
                    subject_type="task",
                    predicate_id="action_state",
                    object_value=object_value,
                    event_id=event_id,
                    quote=quote,
                    transition_id=transition_id,
                    timestamp=timestamp,
                    state=state,
                    roles=["execution_continuation", "action_state"],
                )
            )
    if hidden_ids is not None:
        entities.append(_hidden_person(hidden_ids["entity_id"], hidden_ids["name"], base + timedelta(days=69)))
        claims.append(
            _hidden_claim(
                claim_id=hidden_ids["claim_id"],
                subject_id=project,
                subject_name="Atlas Billing Migration",
                object_entity_id=hidden_ids["entity_id"],
                object_value=hidden_ids["name"],
                timestamp=base + timedelta(days=69),
            )
        )
    relations = [
        LatentRelation(
            relation_id=relation_alias,
            relation_type="alias_of",
            source=RelationEndpoint(endpoint_id="alias:Atlas", endpoint_type="alias", label="Atlas"),
            target=RelationEndpoint(endpoint_id=project, endpoint_type="entity", label="Atlas Billing Migration"),
            directionality="directed",
            temporal=RelationTemporal(valid_from=base),
            lifecycle_state=SimLifecycleState.ACTIVE,
            evidence_spans=[_span(event_1, observations[0].text, "relation_support")],
            provenance=RelationProvenance(
                transition_id=observations[0].transition_id,
                source_event_ids=[event_1],
                source_modality="assertion",
                source_trust=3,
            ),
            confidence=_confidence(0.65),
            observability=ObservabilityLabel.AMBIGUOUS,
            observability_reason="Atlas alone is context sensitive until disambiguated",
            evaluation_roles=["entity_aliasing"],
        ),
        LatentRelation(
            relation_id=relation_contradicts,
            relation_type="contradicts",
            source=RelationEndpoint(
                endpoint_id=claim_ambiguous,
                endpoint_type="claim",
                label=f"{service_owner_name} may own Atlas migration",
            ),
            target=RelationEndpoint(
                endpoint_id=claim_bob_owner,
                endpoint_type="claim",
                label=f"{current_owner_name} owns Atlas migration",
            ),
            directionality="directed",
            temporal=RelationTemporal(valid_from=(ambiguity_observation.timestamp if ambiguity_observation is not None else observations[4].timestamp)),
            lifecycle_state=SimLifecycleState.ACTIVE,
            evidence_spans=[_span(
                ambiguity_observation.event_id if ambiguity_observation is not None else event_5,
                ambiguity_observation.text if ambiguity_observation is not None else observations[4].text,
                "contradiction_support",
            )],
            provenance=RelationProvenance(
                transition_id=ambiguity_observation.transition_id if ambiguity_observation is not None else observations[4].transition_id,
                source_event_ids=[ambiguity_observation.event_id if ambiguity_observation is not None else event_5],
                source_modality=ambiguity_observation.modality if ambiguity_observation is not None else observations[4].modality,
                source_trust=ambiguity_observation.trust_level if ambiguity_observation is not None else observations[4].trust_level,
            ),
            confidence=_confidence(0.8),
            observability=ObservabilityLabel.OBSERVED,
            observability_reason="directly supported by correction/ambiguity text",
            evaluation_roles=["claim_contradiction", "entity_split"],
        ),
    ]
    if hidden_ids is not None:
        relations.append(
            LatentRelation(
                relation_id=hidden_ids["relation_id"],
                relation_type="contradicts",
                source=RelationEndpoint(
                    endpoint_id=hidden_ids["claim_id"],
                    endpoint_type="claim",
                    label=f"unobserved hidden owner {hidden_ids['name']}",
                ),
                target=RelationEndpoint(
                    endpoint_id=claim_bob_owner,
                    endpoint_type="claim",
                    label=f"{current_owner_name} owns Atlas migration",
                ),
                directionality="directed",
                temporal=RelationTemporal(valid_from=base + timedelta(days=69)),
                lifecycle_state=SimLifecycleState.CANDIDATE,
                evidence_spans=[],
                provenance=RelationProvenance(
                    transition_id=f"transition_{suffix}_hidden_latent",
                    source_event_ids=[],
                    source_modality="hidden",
                    source_trust=0,
                ),
                confidence=_confidence(0.35),
                observability=ObservabilityLabel.HIDDEN,
                observability_reason="latent hidden relation with no surface evidence",
                evaluation_roles=["hidden_hallucination_trap"],
            )
        )

    checkpoint_time = base + timedelta(days=120 if profile == "long_horizon" else 68)
    checkpoints = [_checkpoint_for_family(
        family=family,
        suffix=suffix,
        timestamp=checkpoint_time,
        project=project,
        service=service,
        claim_type_project=claim_type_project,
        claim_type_service=claim_type_service,
        claim_alice_owner=claim_alice_owner,
        claim_bob_owner=claim_bob_owner,
            claim_carol_service=claim_carol_service,
            claim_ambiguous=claim_ambiguous,
            expected_action_claim_id=claim_branch_b_progress if profile == "long_horizon" and family == "abandoned_then_resumed_work" else None,
            relation_contradicts=relation_contradicts,
        event_1=event_1,
        event_2=event_2,
        event_3=event_3,
            event_5=event_5,
            current_owner_name=current_owner_name,
            old_owner_name=old_owner_name,
            service_owner_name=service_owner_name,
    )]
    if family == "current_vs_historical_truth":
        checkpoints.append(
            OracleCheckpoint(
                checkpoint_id=f"cp_{suffix}_historical_owner",
                timestamp=checkpoint_time,
                checkpoint_type="historical_truth",
                query_or_task="Who owned Atlas in January before the org-directory update?",
                expected_entity_ids=[project],
                expected_claim_ids=[claim_alice_owner],
                expected_citation_event_ids=[event_2],
                expected_excluded_claim_ids=[claim_bob_owner],
                expected_answer=old_owner_name,
                difficulty_tags=["historical_truth", "temporal_addressability"],
                severity="critical",
            )
        )
    if family == "entity_split":
        checkpoints.append(
            OracleCheckpoint(
                checkpoint_id=f"cp_{suffix}_service_owner",
                timestamp=checkpoint_time,
                checkpoint_type="entity_split_repair",
                query_or_task=f"What does {service_owner_name} own?",
                expected_entity_ids=[service],
                expected_claim_ids=[claim_carol_service],
                expected_citation_event_ids=[event_3],
                expected_excluded_entity_ids=[project],
                expected_excluded_claim_ids=[claim_ambiguous],
                expected_answer="Atlas Platform Service",
                difficulty_tags=["entity_split", "same_name_entity"],
                severity="critical",
            )
        )

    checkpoints = [
        _checkpoint_with_horizon_metadata(
            checkpoint=checkpoint,
            observations=observations,
        )
        for checkpoint in checkpoints
    ]

    return LatentGraphScenario(
        scenario_id=f"sim_{suffix}_{family}",
        family=family,
        profile=profile,
        seed=seed + rng.randint(0, 9999),
        entities=entities,
        claims=claims,
        relations=relations,
        transitions=transitions,
        observations=observations,
        checkpoints=checkpoints,
    )

def _checkpoint_for_family(
    *,
    family: str,
    suffix: str,
    timestamp: datetime,
    project: str,
    service: str,
    claim_type_project: str,
    claim_type_service: str,
    claim_alice_owner: str,
    claim_bob_owner: str,
    claim_carol_service: str,
    claim_ambiguous: str,
    expected_action_claim_id: str | None,
    relation_contradicts: str,
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
            query_or_task="Reconstruct the Atlas project and service ownership graph.",
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
            query_or_task="Who owns the Atlas billing migration now?",
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
            query_or_task="Which Atlas owner should be trusted today?",
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
            query_or_task="Should the pasted onboarding note make Alice the current Atlas owner?",
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
            query_or_task="Outside the incident, what ownership summary should be used for Atlas?",
            expected_entity_ids=[project],
            expected_claim_ids=[claim_bob_owner],
            expected_citation_event_ids=[event_5],
            expected_answer=current_owner_name,
            difficulty_tags=["scope_resolution"],
            severity="high",
        )
    if family == "entity_alias_merge_and_relink":
        return OracleCheckpoint(
            checkpoint_id=f"cp_{suffix}_alias",
            timestamp=timestamp,
            checkpoint_type="claim_rekey",
            query_or_task="Resolve Atlas migration ownership after alias confirmation.",
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
            query_or_task="Who owns the Atlas billing migration, not the service?",
            expected_entity_ids=[project],
            expected_claim_ids=[claim_bob_owner],
            expected_relation_ids=[relation_contradicts],
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
            query_or_task="Which Atlas ownership hypothesis should rank highest?",
            expected_entity_ids=[project],
            expected_claim_ids=[claim_bob_owner],
            expected_relation_ids=[relation_contradicts],
            expected_citation_event_ids=[event_5],
            expected_answer=f"{current_owner_name} owns Atlas Billing Migration",
            difficulty_tags=["belief_ranking", "belief_dependency"],
            severity="high",
        )
    if family == "abandoned_then_resumed_work":
        expected_claim_ids = [claim_bob_owner]
        expected_entity_ids = [project]
        expected_citation_event_ids = [event_5]
        expected_action_ids: list[str] = []
        expected_excluded_claim_ids: list[str] = []
        if expected_action_claim_id is not None:
            expected_claim_ids.append(expected_action_claim_id)
            expected_entity_ids.append(f"ent_{suffix}_branch_b")
            expected_citation_event_ids.append(f"event_{suffix}_branch_b_progress")
            expected_action_ids.append(f"action:{expected_action_claim_id}")
            expected_excluded_claim_ids.append(f"claim_{suffix}_branch_a_blocked")
        return OracleCheckpoint(
            checkpoint_id=f"cp_{suffix}_branch",
            timestamp=timestamp,
            checkpoint_type="execution_continuation",
            query_or_task="Continue the previous Atlas ownership cleanup.",
            expected_entity_ids=expected_entity_ids,
            expected_claim_ids=expected_claim_ids,
            expected_action_ids=expected_action_ids,
            expected_citation_event_ids=expected_citation_event_ids,
            expected_excluded_claim_ids=expected_excluded_claim_ids,
            expected_next_action=f"continue {current_owner_name} owner cleanup",
            difficulty_tags=["execution_continuation"],
            severity="high",
        )
    return OracleCheckpoint(
        checkpoint_id=f"cp_{suffix}_current",
        timestamp=timestamp,
        checkpoint_type="current_truth",
        query_or_task="Who owns the Atlas billing migration now?",
        expected_entity_ids=[project],
        expected_claim_ids=[claim_bob_owner],
        expected_citation_event_ids=[event_5],
        expected_excluded_claim_ids=[claim_alice_owner],
        expected_answer=current_owner_name,
        difficulty_tags=["current_truth"],
        severity="critical",
    )

def _add_noise_observations(
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
                modality=rng.choice(["noise", "quoted_or_pasted", "third_party_claim"]),
                phase="dormancy" if profile == "long_horizon" else "interference",
                trust_level=rng.choice([0, 1]),
                text=text,
                hidden_distractor_ids=[f"hidden_{suffix}_noise_{noise_index:02d}"],
            )
        )

def _checkpoint_with_horizon_metadata(
    *,
    checkpoint: OracleCheckpoint,
    observations: list[SurfaceObservation],
) -> OracleCheckpoint:
    event_by_id = {observation.event_id: observation for observation in observations}
    support_observations = [
        event_by_id[event_id]
        for event_id in checkpoint.expected_citation_event_ids
        if event_id in event_by_id
    ]
    if support_observations:
        earliest_support_time = min(observation.timestamp for observation in support_observations)
        latest_support_time = max(observation.timestamp for observation in support_observations)
        horizon_distance = sum(
            1
            for observation in observations
            if latest_support_time < observation.timestamp <= checkpoint.timestamp
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
            "required_retrieval_view": _retrieval_view_for_checkpoint_type(checkpoint.checkpoint_type),
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

def _retrieval_view_for_checkpoint_type(checkpoint_type: str) -> str:
    if checkpoint_type == "historical_truth":
        return "historical_at"
    if checkpoint_type in {"source_trust_conflict", "conflict_audit"}:
        return "conflicts"
    if checkpoint_type in {"entity_reconstruction", "claim_rekey", "entity_split_repair", "belief_ranking"}:
        return "all_versions"
    if checkpoint_type == "modality_suppression":
        return "evidence_only"
    return "current"

def _hidden_graph_ids_for_profile(*, profile: str, suffix: str) -> dict[str, str] | None:
    if profile not in {"adversarial", "long_horizon"}:
        return None
    return {
        "entity_id": f"ent_{suffix}_hidden_owner",
        "claim_id": f"claim_{suffix}_hidden_owner",
        "relation_id": f"rel_{suffix}_hidden_owner_conflict",
        "name": f"Hidden Owner {suffix}",
    }

def _entity(
    entity_id: str,
    name: str,
    entity_type: Literal["project", "service"],
    created_at: datetime,
    event_id: str,
    defining_claim_id: str,
    relation_ids: list[str],
) -> LatentEntity:
    return LatentEntity(
        entity_id=entity_id,
        canonical_name=name,
        entity_type=entity_type,
        description=f"{name} {entity_type}",
        aliases=[
            LatentEntityAlias(
                alias_text="Atlas" if entity_type == "project" else "Atlas service",
                valid_from=created_at,
                confidence=0.75 if entity_type == "project" else 0.95,
                evidence_spans=[_span(event_id, name.split()[0], "direct_mention")],
                ambiguity_group_id="ambig_atlas" if entity_type == "project" else None,
            )
        ],
        created_at=created_at,
        defining_claim_ids=[defining_claim_id],
        relation_ids=relation_ids,
        evidence_spans=[_span(event_id, name.split()[0], "direct_mention")],
        confidence=_confidence(0.9),
        observability=ObservabilityLabel.OBSERVED,
        observability_reason="directly stated by surface observation",
        evaluation_roles=["entity_reconstruction", "entity_type_disambiguation"],
    )

def _person(entity_id: str, name: str, created_at: datetime, event_id: str) -> LatentEntity:
    return LatentEntity(
        entity_id=entity_id,
        canonical_name=name,
        entity_type="person",
        description=f"{name} person entity",
        aliases=[],
        created_at=created_at,
        evidence_spans=[_span(event_id, name, "direct_mention")],
        confidence=_confidence(0.9),
        observability=ObservabilityLabel.OBSERVED,
        observability_reason="directly mentioned in surface observation",
        evaluation_roles=["entity_reconstruction"],
    )

def _task_entity(entity_id: str, name: str, created_at: datetime, event_id: str, defining_claim_id: str) -> LatentEntity:
    return LatentEntity(
        entity_id=entity_id,
        canonical_name=name,
        entity_type="task",
        description=f"{name} task branch",
        aliases=[
            LatentEntityAlias(
                alias_text=name,
                valid_from=created_at,
                confidence=0.9,
                evidence_spans=[_span(event_id, name, "direct_mention")],
            )
        ],
        created_at=created_at,
        defining_claim_ids=[defining_claim_id],
        evidence_spans=[_span(event_id, name, "direct_mention")],
        confidence=_confidence(0.85),
        observability=ObservabilityLabel.OBSERVED,
        observability_reason="directly mentioned in action-state surface observation",
        evaluation_roles=["execution_continuation", "action_state"],
    )

def _hidden_person(entity_id: str, name: str, created_at: datetime) -> LatentEntity:
    return LatentEntity(
        entity_id=entity_id,
        canonical_name=name,
        entity_type="person",
        description=f"{name} hidden person entity",
        aliases=[],
        created_at=created_at,
        evidence_spans=[],
        confidence=_confidence(0.35),
        observability=ObservabilityLabel.HIDDEN,
        observability_reason="latent hidden entity with no surface evidence",
        evaluation_roles=["hidden_hallucination_trap"],
    )

def _claim(
    *,
    claim_id: str,
    kind: Literal[
        "entity_attribute",
        "relationship_fact",
        "preference",
        "status",
        "action_state",
        "belief",
        "temporal_fact",
        "correction",
        "contradiction",
    ],
    subject_id: str,
    subject_name: str,
    subject_type: str,
    predicate_id: str,
    object_value: str,
    event_id: str,
    quote: str,
    transition_id: str,
    timestamp: datetime,
    state: SimLifecycleState,
    roles: list[str],
    object_entity_id: str | None = None,
    valid_to: datetime | None = None,
    observability: ObservabilityLabel = ObservabilityLabel.OBSERVED,
    confidence: LatentConfidence | None = None,
) -> LatentClaim:
    return LatentClaim(
        claim_id=claim_id,
        claim_kind=kind,
        subject=ClaimArgument(
            entity_id=subject_id,
            observed_text=subject_name.split()[0],
            canonical_name=subject_name,
            entity_type=subject_type,
            resolution_confidence=0.9,
        ),
        predicate=ClaimPredicate(
            predicate_id=predicate_id,
            observed_text=predicate_id.replace("_", " "),
            value_type="entity" if object_entity_id else "enum" if predicate_id == "entity_type" else "text",
            cardinality="single",
            conflict_policy="supersede" if state != SimLifecycleState.EVIDENCE_ONLY else "evidence_only",
            temporal_policy="current_value",
        ),
        object=ClaimObject(
            value=object_value,
            observed_text=object_value,
            normalized_value=object_value.lower(),
            entity_id=object_entity_id,
            resolution_confidence=0.9 if object_entity_id else None,
        ),
        scope=ClaimScope(scope_key="global", organization_unit="Finance Ops"),
        lifecycle=ClaimLifecycle(state=state, valid_from=timestamp, valid_to=valid_to),
        evidence=ClaimEvidence(
            source_event_ids=[event_id],
            spans=[
                _span(event_id, quote, "subject_support"),
                _span(event_id, quote, "predicate_support"),
                _span(event_id, quote, "object_support"),
            ],
        ),
        provenance=ClaimProvenance(
            transition_id=transition_id,
            extraction_run_id="oracle",
            source_type="tool" if "org_directory" in quote else "user",
            source_modality="tool_result" if "org_directory" in quote else "assertion",
            source_trust=5 if "org_directory" in quote else 3,
        ),
        confidence=confidence or _confidence(0.9 if state == SimLifecycleState.ACTIVE else 0.75),
        observability=observability,
        observability_reason="directly supported by surface text",
        evaluation_roles=roles,
    )

def _hidden_claim(
    *,
    claim_id: str,
    subject_id: str,
    subject_name: str,
    object_entity_id: str,
    object_value: str,
    timestamp: datetime,
) -> LatentClaim:
    return LatentClaim(
        claim_id=claim_id,
        claim_kind="relationship_fact",
        subject=ClaimArgument(
            entity_id=subject_id,
            observed_text=subject_name.split()[0],
            canonical_name=subject_name,
            entity_type="project",
            resolution_confidence=0.3,
        ),
        predicate=ClaimPredicate(
            predicate_id="owner",
            observed_text="owner",
            value_type="entity",
            cardinality="single",
            conflict_policy="evidence_only",
            temporal_policy="current_value",
        ),
        object=ClaimObject(
            value=object_value,
            observed_text=object_value,
            normalized_value=object_value.lower(),
            entity_id=object_entity_id,
            resolution_confidence=0.3,
        ),
        scope=ClaimScope(scope_key="global", organization_unit="Finance Ops"),
        lifecycle=ClaimLifecycle(state=SimLifecycleState.EVIDENCE_ONLY, valid_from=timestamp),
        evidence=ClaimEvidence(source_event_ids=[], spans=[]),
        provenance=ClaimProvenance(
            transition_id="hidden_latent_only",
            extraction_run_id="oracle_hidden",
            source_type="hidden",
            source_modality="hidden",
            source_trust=0,
        ),
        confidence=_confidence(0.35),
        observability=ObservabilityLabel.HIDDEN,
        observability_reason="latent hidden claim with no surface evidence",
        evaluation_roles=["hidden_hallucination_trap"],
    )

def _span(event_id: str, quote: str, support_type: str) -> LatentEvidenceSpan:
    return LatentEvidenceSpan(
        event_id=event_id,
        quote=quote,
        support_type=support_type,  # type: ignore[arg-type]
    )

def _confidence(score: float) -> LatentConfidence:
    return LatentConfidence(
        extraction=score,
        evidence=score,
        source_trust=score,
        agreement=max(0.0, score - 0.1),
        contradiction=max(0.0, 1.0 - score),
        temporal=score,
        entity_resolution=score,
        calibrated=score,
        band="low" if score < 0.40 else "medium" if score < 0.75 else "high",
        rationale="deterministic simulator confidence",
    )
