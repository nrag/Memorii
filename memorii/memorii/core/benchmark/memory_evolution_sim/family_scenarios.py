"""Scenario generation for the memory evolution simulator."""

from __future__ import annotations

import hashlib
import json
import random
from datetime import UTC, datetime, timedelta

from memorii.core.benchmark.memory_evolution_sim.checkpoints import (
    checkpoint_for_family,
    checkpoint_with_horizon_metadata,
)
from memorii.core.benchmark.memory_evolution_sim.contracts import (
    entity_split_contract,
    truth_contract,
)
from memorii.core.benchmark.memory_evolution_sim.family_observations import build_family_observations
from memorii.core.benchmark.memory_evolution_sim.schema_builders import (
    build_confidence,
    claim,
    entity,
    hidden_claim,
    hidden_person,
    person,
    span,
    task_entity,
)
from memorii.core.benchmark.memory_evolution_sim.schemas import (
    ClaimScope,
    LatentGraphScenario,
    LatentRelation,
    ObservabilityLabel,
    OracleCheckpoint,
    RelationEndpoint,
    RelationProvenance,
    RelationTemporal,
    SimLifecycleState,
    WorldTransition,
)


def build_family_scenario(
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
    world_variant = rng.randrange(0, 2**31)
    # Historical checkpoints explicitly refer to January. Vary the year and
    # day within January so worlds remain distinct without changing the
    # temporal meaning of those queries.
    base = datetime(2026 + (world_variant % 20), 1, 5, 9, tzinfo=UTC) + timedelta(days=index % 20)
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
    setup_trust = rng.choice([3, 4])
    service_trust = rng.choice([3, 4])
    stale_trust = rng.choice([0, 1])
    tool_trust = rng.choice([4, 5])
    ambiguity_trust = rng.choice([0, 1])
    event_1 = f"event_{suffix}_001"
    event_2 = f"event_{suffix}_002"
    event_3 = f"event_{suffix}_003"
    event_4 = f"event_{suffix}_004"
    event_5 = f"event_{suffix}_005"
    claim_type_project = f"claim_{suffix}_project_type"
    claim_type_service = f"claim_{suffix}_service_type"
    claim_alice_owner = f"claim_{suffix}_previous_owner_old"
    claim_bob_owner = f"claim_{suffix}_current_owner"
    claim_task_owner = f"claim_{suffix}_incident_owner"
    claim_carol_service = f"claim_{suffix}_service_owner"
    claim_ambiguous = f"claim_{suffix}_ambiguous_service_owner_atlas"
    branch_a = f"ent_{suffix}_branch_a"
    branch_b = f"ent_{suffix}_branch_b"
    claim_branch_a_started = f"claim_{suffix}_branch_a_started"
    claim_branch_a_blocked = f"claim_{suffix}_branch_a_blocked"
    claim_branch_b_started = f"claim_{suffix}_branch_b_started"
    claim_branch_b_progress = f"claim_{suffix}_branch_b_progress"
    branch_a_started_time = base + timedelta(
        days=72 if profile == "long_horizon" else 66, hours=0 if profile == "long_horizon" else 3
    )
    branch_a_blocked_time = base + timedelta(
        days=73 if profile == "long_horizon" else 66, hours=0 if profile == "long_horizon" else 8
    )
    branch_b_started_time = base + timedelta(
        days=74 if profile == "long_horizon" else 67, hours=0 if profile == "long_horizon" else 1
    )
    branch_b_progress_time = base + timedelta(
        days=75 if profile == "long_horizon" else 67, hours=0 if profile == "long_horizon" else 6
    )
    relation_contradicts = f"rel_{suffix}_owner_conflict"
    relation_alias = f"rel_{suffix}_alias"
    relation_split = f"rel_{suffix}_service_split_from_project"
    incident_task_id = f"task:{suffix}:incident"

    observations, hidden_ids, ambiguity_observation = build_family_observations(
        family=family,
        profile=profile,
        suffix=suffix,
        base=base,
        rng=rng,
        project=project,
        service=service,
        alice=alice,
        bob=bob,
        carol=carol,
        old_owner_name=old_owner_name,
        current_owner_name=current_owner_name,
        service_owner_name=service_owner_name,
        setup_trust=setup_trust,
        service_trust=service_trust,
        stale_trust=stale_trust,
        tool_trust=tool_trust,
        ambiguity_trust=ambiguity_trust,
        event_1=event_1,
        event_2=event_2,
        event_3=event_3,
        event_4=event_4,
        event_5=event_5,
        claim_type_project=claim_type_project,
        claim_type_service=claim_type_service,
        claim_alice_owner=claim_alice_owner,
        claim_bob_owner=claim_bob_owner,
        claim_task_owner=claim_task_owner,
        claim_carol_service=claim_carol_service,
        claim_ambiguous=claim_ambiguous,
        branch_a=branch_a,
        branch_b=branch_b,
        claim_branch_a_started=claim_branch_a_started,
        claim_branch_a_blocked=claim_branch_a_blocked,
        claim_branch_b_started=claim_branch_b_started,
        claim_branch_b_progress=claim_branch_b_progress,
        branch_a_started_time=branch_a_started_time,
        branch_a_blocked_time=branch_a_blocked_time,
        branch_b_started_time=branch_b_started_time,
        branch_b_progress_time=branch_b_progress_time,
        relation_contradicts=relation_contradicts,
        relation_alias=relation_alias,
        relation_split=relation_split,
        incident_task_id=incident_task_id,
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
        entity(project, "Atlas Billing Migration", "project", base, event_1, claim_type_project, [relation_alias]),
        entity(
            service,
            "Atlas Platform Service",
            "service",
            base + timedelta(days=4),
            event_3,
            claim_type_service,
            [],
            include_ambiguous_alias=family == "entity_split",
        ),
        person(alice, old_owner_name, base + timedelta(minutes=5), event_2),
        person(bob, current_owner_name, base + timedelta(days=66), event_5),
        person(carol, service_owner_name, base + timedelta(days=4), event_3),
    ]
    if family == "abandoned_then_resumed_work":
        entities.extend(
            [
                task_entity(
                    branch_a,
                    "Atlas Cleanup Branch A",
                    branch_a_started_time,
                    f"event_{suffix}_branch_a_started",
                    claim_branch_a_started,
                ),
                task_entity(
                    branch_b,
                    "Atlas Cleanup Branch B",
                    branch_b_started_time,
                    f"event_{suffix}_branch_b_started",
                    claim_branch_b_started,
                ),
            ]
        )
    claims = [
        claim(
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
        claim(
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
        claim(
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
        claim(
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
        claim(
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
        claim(
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
            transition_id=ambiguity_observation.transition_id
            if ambiguity_observation is not None
            else observations[4].transition_id,
            timestamp=ambiguity_observation.timestamp
            if ambiguity_observation is not None
            else observations[4].timestamp,
            state=SimLifecycleState.INVALIDATED,
            roles=["modality_suppression", "conflict_detection"],
            observability=ObservabilityLabel.AMBIGUOUS,
            confidence=build_confidence(0.35),
        ),
    ]
    if family == "global_vs_task_scoped_preference":
        task_observation = next(
            observation for observation in observations if observation.event_id == f"event_{suffix}_task_scope"
        )
        claims.append(
            claim(
                claim_id=claim_task_owner,
                kind="relationship_fact",
                subject_id=project,
                subject_name="Atlas Billing Migration",
                subject_type="project",
                predicate_id="owner",
                object_value=old_owner_name,
                object_entity_id=alice,
                event_id=task_observation.event_id,
                quote=task_observation.text,
                transition_id=task_observation.transition_id,
                timestamp=task_observation.timestamp,
                state=SimLifecycleState.ACTIVE,
                roles=["scoped_truth", "scope_isolation"],
                scope=ClaimScope(
                    scope_key=incident_task_id,
                    task_id=incident_task_id,
                    organization_unit="Finance Ops",
                ),
            )
        )
    if family == "abandoned_then_resumed_work":
        action_claim_specs = [
            (
                claim_branch_a_started,
                branch_a,
                "Atlas Cleanup Branch A",
                "started",
                f"event_{suffix}_branch_a_started",
                f"transition_{suffix}_branch_a_started",
                branch_a_started_time,
                "Atlas cleanup Branch A started: re-open old owner notes.",
                SimLifecycleState.SUPERSEDED,
            ),
            (
                claim_branch_a_blocked,
                branch_a,
                "Atlas Cleanup Branch A",
                "blocked",
                f"event_{suffix}_branch_a_blocked",
                f"transition_{suffix}_branch_a_blocked",
                branch_a_blocked_time,
                "Atlas cleanup Branch A blocked on stale onboarding notes.",
                SimLifecycleState.ACTIVE,
            ),
            (
                claim_branch_b_started,
                branch_b,
                "Atlas Cleanup Branch B",
                "started",
                f"event_{suffix}_branch_b_started",
                f"transition_{suffix}_branch_b_started",
                branch_b_started_time,
                "Atlas cleanup Branch B started: verify the org-directory owner path.",
                SimLifecycleState.SUPERSEDED,
            ),
            (
                claim_branch_b_progress,
                branch_b,
                "Atlas Cleanup Branch B",
                "in_progress",
                f"event_{suffix}_branch_b_progress",
                f"transition_{suffix}_branch_b_progress",
                branch_b_progress_time,
                "Atlas cleanup Branch B in_progress: continue the org-directory owner cleanup.",
                SimLifecycleState.ACTIVE,
            ),
        ]
        for (
            claim_id,
            subject_id,
            subject_name,
            object_value,
            event_id,
            transition_id,
            timestamp,
            quote,
            state,
        ) in action_claim_specs:
            claims.append(
                claim(
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
        entities.append(hidden_person(hidden_ids["entity_id"], hidden_ids["name"], base + timedelta(days=69)))
        claims.append(
            hidden_claim(
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
            evidence_spans=[span(event_1, observations[0].text, "relation_support")],
            provenance=RelationProvenance(
                transition_id=observations[0].transition_id,
                source_event_ids=[event_1],
                source_modality="assertion",
                source_trust=3,
            ),
            confidence=build_confidence(0.65),
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
            temporal=RelationTemporal(
                valid_from=(
                    ambiguity_observation.timestamp if ambiguity_observation is not None else observations[4].timestamp
                )
            ),
            lifecycle_state=SimLifecycleState.ACTIVE,
            evidence_spans=[
                span(
                    ambiguity_observation.event_id if ambiguity_observation is not None else event_5,
                    ambiguity_observation.text if ambiguity_observation is not None else observations[4].text,
                    "contradiction_support",
                )
            ],
            provenance=RelationProvenance(
                transition_id=ambiguity_observation.transition_id
                if ambiguity_observation is not None
                else observations[4].transition_id,
                source_event_ids=[ambiguity_observation.event_id if ambiguity_observation is not None else event_5],
                source_modality=ambiguity_observation.modality
                if ambiguity_observation is not None
                else observations[4].modality,
                source_trust=ambiguity_observation.trust_level
                if ambiguity_observation is not None
                else observations[4].trust_level,
            ),
            confidence=build_confidence(0.8),
            observability=ObservabilityLabel.OBSERVED,
            observability_reason="directly supported by correction/ambiguity text",
            evaluation_roles=["claim_contradiction", "entity_split"],
        ),
    ]
    if family == "entity_split":
        relations.append(
            LatentRelation(
                relation_id=relation_split,
                relation_type="split_from",
                source=RelationEndpoint(
                    endpoint_id=service,
                    endpoint_type="entity",
                    label="Atlas Platform Service",
                ),
                target=RelationEndpoint(
                    endpoint_id=project,
                    endpoint_type="entity",
                    label="Atlas Billing Migration",
                ),
                directionality="directed",
                temporal=RelationTemporal(valid_from=base + timedelta(days=4)),
                lifecycle_state=SimLifecycleState.ACTIVE,
                evidence_spans=[span(event_3, observations[2].text, "relation_support")],
                provenance=RelationProvenance(
                    transition_id=observations[2].transition_id,
                    source_event_ids=[event_3],
                    source_modality=observations[2].modality,
                    source_trust=observations[2].trust_level,
                ),
                confidence=build_confidence(0.8),
                observability=ObservabilityLabel.OBSERVED,
                observability_reason="the source explicitly distinguishes the service from the project",
                evaluation_roles=["entity_split_lineage"],
            )
        )
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
                confidence=build_confidence(0.35),
                observability=ObservabilityLabel.HIDDEN,
                observability_reason="latent hidden relation with no surface evidence",
                evaluation_roles=["hidden_hallucination_trap"],
            )
        )

    checkpoint_time = base + timedelta(days=120 if profile == "long_horizon" else 68)
    checkpoints = [
        checkpoint_for_family(
            rng=rng,
            family=family,
            suffix=suffix,
            timestamp=checkpoint_time,
            project=project,
            service=service,
            claim_type_project=claim_type_project,
            claim_type_service=claim_type_service,
            claim_alice_owner=claim_alice_owner,
            claim_bob_owner=claim_bob_owner,
            claim_task_owner=claim_task_owner,
            claim_carol_service=claim_carol_service,
            claim_ambiguous=claim_ambiguous,
            expected_action_claim_id=claim_branch_b_progress if family == "abandoned_then_resumed_work" else None,
            relation_contradicts=relation_contradicts,
            relation_split=relation_split,
            event_1=event_1,
            event_2=event_2,
            event_3=event_3,
            event_5=event_5,
            current_owner_name=current_owner_name,
            old_owner_name=old_owner_name,
            service_owner_name=service_owner_name,
        )
    ]
    if family == "current_vs_historical_truth":
        checkpoints.append(
            OracleCheckpoint(
                checkpoint_id=f"cp_{suffix}_historical_owner",
                timestamp=checkpoint_time,
                checkpoint_type="historical_truth",
                query_or_task=rng.choice(
                    [
                        "Who owned the Atlas migration in January before the org-directory update?",
                        "Before the directory correction, who was the Atlas migration owner in January?",
                    ]
                ),
                checkpoint_contract=truth_contract(historical=True),
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
                query_or_task=rng.choice(
                    [
                        f"What does {service_owner_name} own?",
                        f"Which Atlas entity is owned by {service_owner_name}?",
                    ]
                ),
                checkpoint_contract=entity_split_contract(answer_projection_policy="claim_subject"),
                expected_entity_ids=[service],
                expected_claim_ids=[claim_carol_service],
                expected_relation_ids=[relation_split],
                expected_citation_event_ids=[event_3],
                expected_excluded_entity_ids=[project],
                expected_excluded_claim_ids=[claim_ambiguous],
                expected_answer="Atlas Platform Service",
                difficulty_tags=["entity_split", "same_name_entity"],
                severity="critical",
            )
        )

    checkpoints = [
        checkpoint_with_horizon_metadata(
            checkpoint=checkpoint,
            observations=observations,
        )
        for checkpoint in checkpoints
    ]

    world_parameters: dict[str, str | int] = {
        "schema": "memory_evolution_semantic_world_1",
        "family": family,
        "profile": profile,
        "base_time": base.isoformat(),
        "old_owner": old_owner_name,
        "current_owner": current_owner_name,
        "service_owner": service_owner_name,
        "setup_trust": setup_trust,
        "service_trust": service_trust,
        "stale_trust": stale_trust,
        "tool_trust": tool_trust,
        "ambiguity_trust": ambiguity_trust,
    }
    semantic_world_fingerprint = hashlib.sha256(
        json.dumps(world_parameters, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return LatentGraphScenario(
        scenario_id=f"sim_{suffix}_{family}",
        semantic_world_fingerprint=semantic_world_fingerprint,
        world_parameters=world_parameters,
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
