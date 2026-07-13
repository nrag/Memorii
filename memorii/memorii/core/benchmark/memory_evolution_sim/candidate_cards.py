"""Visible candidate-card and reconstruction-context helpers."""

from __future__ import annotations

from memorii.core.benchmark.memory_evolution_sim.schemas import (
    LatentGraphScenario,
    MemoryEvolutionSimReconstructionContext,
    OracleCheckpoint,
    VisibleCheckpointCandidate,
    VisibleClaimCandidate,
    VisibleEntityCandidate,
    VisibleEventCandidate,
    VisibleRelationCandidate,
    VisibleSurfaceObservation,
)


def sim_reconstruction_context_for_checkpoint(
    *,
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
) -> MemoryEvolutionSimReconstructionContext:
    visible_entity_ids = sorted({item for obs in scenario.observations for item in obs.exposed_entity_ids})
    visible_claim_ids = sorted({item for obs in scenario.observations for item in obs.exposed_claim_ids})
    visible_relation_ids = sorted({item for obs in scenario.observations for item in obs.exposed_relation_ids})
    visible_event_ids = {obs.event_id for obs in scenario.observations}
    visible_events = [
        VisibleEventCandidate(
            event_id=obs.event_id,
            timestamp=obs.timestamp,
            source_type=obs.source_type,
            modality=obs.modality,
            phase=obs.phase,
            trust_level=obs.trust_level,
            text=obs.text,
        )
        for obs in sorted(scenario.observations, key=lambda item: item.event_id)
    ]
    visible_entities = [
        VisibleEntityCandidate(
            entity_id=entity.entity_id,
            canonical_name=entity.canonical_name,
            entity_type=entity.entity_type,
            aliases=[alias.alias_text for alias in entity.aliases],
            lifecycle_state=entity.lifecycle_state,
            evidence_event_ids=sorted({span.event_id for span in entity.evidence_spans if span.event_id in visible_event_ids}),
        )
        for entity in sorted(scenario.entities, key=lambda item: item.entity_id)
        if entity.entity_id in visible_entity_ids
    ]
    visible_claims = [
        VisibleClaimCandidate(
            claim_id=claim.claim_id,
            subject_entity_id=claim.subject.entity_id,
            subject_name=claim.subject.canonical_name,
            predicate_id=claim.predicate.predicate_id,
            object_value=claim.object.value,
            object_entity_id=claim.object.entity_id,
            scope_key=claim.scope.scope_key,
            lifecycle_state=claim.lifecycle.state.value,
            valid_from=claim.lifecycle.valid_from,
            valid_to=claim.lifecycle.valid_to,
            source_trust=claim.provenance.source_trust,
            source_modality=claim.provenance.source_modality,
            evidence_event_ids=[event_id for event_id in claim.evidence.source_event_ids if event_id in visible_event_ids],
            evidence_quote=claim.evidence.spans[0].quote if claim.evidence.spans else "",
            contradicts_claim_ids=list(claim.contradicts_claim_ids),
        )
        for claim in sorted(scenario.claims, key=lambda item: item.claim_id)
        if claim.claim_id in visible_claim_ids
    ]
    visible_relations = [
        VisibleRelationCandidate(
            relation_id=relation.relation_id,
            relation_type=relation.relation_type,
            source_id=relation.source.endpoint_id,
            source_type=relation.source.endpoint_type,
            source_label=relation.source.label,
            target_id=relation.target.endpoint_id,
            target_type=relation.target.endpoint_type,
            target_label=relation.target.label,
            directionality=relation.directionality,
            lifecycle_state=relation.lifecycle_state.value,
            evidence_event_ids=[
                event_id
                for event_id in relation.provenance.source_event_ids
                if event_id in visible_event_ids
            ],
            evidence_quote=relation.evidence_spans[0].quote if relation.evidence_spans else "",
        )
        for relation in sorted(scenario.relations, key=lambda item: item.relation_id)
        if relation.relation_id in visible_relation_ids
    ]
    return MemoryEvolutionSimReconstructionContext(
        scenario_id=scenario.scenario_id,
        family=scenario.family,
        profile=scenario.profile,
        surface_observations=[
            VisibleSurfaceObservation(
                event_id=obs.event_id,
                transition_id=obs.transition_id,
                timestamp=obs.timestamp,
                source_type=obs.source_type,
                modality=obs.modality,
                phase=obs.phase,
                trust_level=obs.trust_level,
                text=obs.text,
                exposed_entity_ids=obs.exposed_entity_ids,
                exposed_claim_ids=obs.exposed_claim_ids,
                exposed_relation_ids=obs.exposed_relation_ids,
            )
            for obs in scenario.observations
        ],
        checkpoint=VisibleCheckpointCandidate(
            checkpoint_id=checkpoint.checkpoint_id,
            timestamp=checkpoint.timestamp,
            checkpoint_type=checkpoint.checkpoint_type,
            query_or_task=checkpoint.query_or_task,
            difficulty_tags=checkpoint.difficulty_tags,
            severity=checkpoint.severity,
            horizon_distance=checkpoint.horizon_distance,
            interference_count=checkpoint.interference_count,
            source_event_age_days=checkpoint.source_event_age_days,
            required_retrieval_view=checkpoint.required_retrieval_view,
            stage_path=list(checkpoint.expected_stage_path),
        ),
        difficulty_tags=checkpoint.difficulty_tags,
        visible_entity_ids=visible_entity_ids,
        visible_claim_ids=visible_claim_ids,
        visible_relation_ids=visible_relation_ids,
        visible_events=visible_events,
        visible_entities=visible_entities,
        visible_claims=visible_claims,
        visible_relations=visible_relations,
        metadata={
            "discriminative": scenario.discriminative,
            "checkpoint_contract": _checkpoint_contract_for_type(checkpoint.checkpoint_type),
            "long_horizon": {
                "horizon_distance": checkpoint.horizon_distance,
                "interference_count": checkpoint.interference_count,
                "source_event_age_days": checkpoint.source_event_age_days,
                "required_retrieval_view": checkpoint.required_retrieval_view,
                "stage_path": list(checkpoint.expected_stage_path),
            },
        },
    )

def _checkpoint_contract_for_type(checkpoint_type: str) -> dict[str, object]:
    defaults: dict[str, object] = {
        "allowed_operations": ["answer"],
        "answer_required": True,
        "selected_entity_role_policy": "subject",
        "allow_stale_selected_claims": False,
        "excluded_ids_must_be_rejected_or_contextualized": True,
        "definition_claims_required_in_selected": False,
        "supporting_citations_must_be_direct_current_evidence": True,
        "conflict_relation_ids_belong_in": ["context_relation_ids"],
    }
    overrides: dict[str, dict[str, object]] = {
        "entity_reconstruction": {
            "allowed_operations": ["graph_reconstruction"],
            "answer_required": False,
            "selected_entity_role_policy": "active_graph_subjects",
            "definition_claims_required_in_selected": True,
        },
        "historical_truth": {
            "allow_stale_selected_claims": True,
            "supporting_citations_must_be_direct_current_evidence": False,
        },
        "entity_split_repair": {
            "wrong_entity_claims_belong_in": ["rejected", "context"],
        },
        "source_trust_conflict": {
            "conflict_relation_ids_belong_in": ["context_relation_ids", "supporting_relation_ids"],
        },
        "claim_rekey": {
            "allowed_operations": ["graph_reconstruction"],
            "answer_required": False,
            "selected_entity_role_policy": "active_graph_subjects",
            "definition_claims_required_in_selected": True,
        },
        "belief_ranking": {
            "allowed_operations": ["graph_reconstruction"],
            "answer_required": False,
            "selected_entity_role_policy": "active_graph_subjects",
            "requires_belief_ranking_ids": True,
        },
        "conflict_audit": {
            "allowed_operations": ["graph_reconstruction"],
            "answer_required": False,
            "selected_entity_role_policy": "audit_graph_entities",
        },
        "execution_continuation": {
            "allowed_operations": ["next_action"],
            "answer_required": False,
            "requires_next_action": True,
        },
        "abstention": {
            "allowed_operations": ["abstain"],
        },
    }
    return {**defaults, **overrides.get(checkpoint_type, {})}
