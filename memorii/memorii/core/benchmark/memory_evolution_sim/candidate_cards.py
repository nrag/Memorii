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
    entity_type_by_id = {entity.entity_id: entity.entity_type for entity in scenario.entities}
    visible_events = [
        VisibleEventCandidate(
            event_id=obs.event_id,
            timestamp=obs.timestamp,
            source_type=obs.source_type,
            modality=obs.modality,
            phase=obs.phase,
            trust_level=obs.trust_level,
            text=obs.text,
            task_id=obs.task_id,
            session_id=obs.session_id,
            user_id=obs.user_id,
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
            subject_entity_type=claim.subject.entity_type,
            predicate_id=claim.predicate.predicate_id,
            object_value=claim.object.value,
            object_entity_id=claim.object.entity_id,
            object_entity_type=entity_type_by_id.get(claim.object.entity_id) if claim.object.entity_id else None,
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
                task_id=obs.task_id,
                session_id=obs.session_id,
                user_id=obs.user_id,
                exposed_entity_ids=obs.exposed_entity_ids,
                exposed_claim_ids=obs.exposed_claim_ids,
                exposed_relation_ids=obs.exposed_relation_ids,
            )
            for obs in scenario.observations
        ],
        checkpoint=VisibleCheckpointCandidate(
            checkpoint_id=checkpoint.checkpoint_id,
            timestamp=checkpoint.timestamp,
            query_or_task=checkpoint.query_or_task,
            answer_projection_policy=checkpoint.answer_projection_policy,
            query_language=checkpoint.query_language,
            evidence_languages=list(checkpoint.evidence_languages),
            answer_language_policy=checkpoint.answer_language_policy,
            cross_lingual=checkpoint.cross_lingual,
            transliteration_policy=checkpoint.transliteration_policy,
        ),
        visible_entity_ids=visible_entity_ids,
        visible_claim_ids=visible_claim_ids,
        visible_relation_ids=visible_relation_ids,
        visible_events=visible_events,
        visible_entities=visible_entities,
        visible_claims=visible_claims,
        visible_relations=visible_relations,
    )
