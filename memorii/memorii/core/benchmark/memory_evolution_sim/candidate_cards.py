"""Visible candidate-card and reconstruction-context helpers."""

from __future__ import annotations

from memorii.core.benchmark.memory_evolution_sim.schemas import (
    LatentClaim,
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

_ACTIVE_ACTION_STATUSES = {
    "in_progress",
    "progressed",
    "continue",
    "continued",
    "resumed",
    "reopened",
}
_START_ACTION_STATUSES = {"start", "started"}
_SUPPRESSED_ACTION_STATUSES = {
    "blocked",
    "stuck",
    "abandoned",
    "dropped",
    "completed",
    "done",
    "failed",
    "superseded",
    "expired",
    "archived",
}
_SUPPRESSED_LIFECYCLES = {"superseded", "invalidated", "expired", "archived", "evidence_only"}


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
            is_definition_claim=_is_definition_claim(claim),
            is_action_state_claim=_is_action_state_claim(claim),
            is_current_active=_is_current_active_claim(claim),
            is_stale_or_invalidated=_is_stale_or_invalidated_claim(claim),
            is_low_trust_or_ambiguous=_is_low_trust_or_ambiguous_claim(claim),
            support_channel_hint=_support_channel_hint(claim, checkpoint=checkpoint),
            action_state_status=_action_state_status(claim),
            continuation_eligibility=_continuation_eligibility(claim),
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
            answer_projection_policy=checkpoint.answer_projection_policy,
            query_language=checkpoint.query_language,
            evidence_languages=list(checkpoint.evidence_languages),
            answer_language_policy=checkpoint.answer_language_policy,
            cross_lingual=checkpoint.cross_lingual,
            transliteration_policy=checkpoint.transliteration_policy,
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
            "checkpoint_contract": checkpoint_contract_payload(checkpoint),
            "channel_policy": checkpoint_channel_policy_payload(checkpoint),
            "long_horizon": {
                "horizon_distance": checkpoint.horizon_distance,
                "interference_count": checkpoint.interference_count,
                "source_event_age_days": checkpoint.source_event_age_days,
                "required_retrieval_view": checkpoint.required_retrieval_view,
                "stage_path": list(checkpoint.expected_stage_path),
            },
        },
    )

def checkpoint_contract_payload(checkpoint: OracleCheckpoint) -> dict[str, object]:
    return checkpoint.checkpoint_contract.model_dump(mode="json")


def checkpoint_channel_policy_payload(checkpoint: OracleCheckpoint) -> dict[str, object]:
    """Return non-oracle channel guidance for reconstruction prompts."""

    contract = checkpoint.checkpoint_contract
    if checkpoint.checkpoint_type == "historical_truth":
        selected_claim_policy = "historical_requested_truth"
    elif checkpoint.checkpoint_type == "execution_continuation":
        selected_claim_policy = "active_continuation_state"
    elif checkpoint.checkpoint_type in {"entity_reconstruction", "claim_rekey", "conflict_audit"}:
        selected_claim_policy = "active_graph_state"
    else:
        selected_claim_policy = "current_active_truth"
    return {
        "checkpoint_type": checkpoint.checkpoint_type,
        "selected_claim_policy": selected_claim_policy,
        "selected_entity_role_policy": contract.selected_entity_role_policy,
        "answer_required": contract.answer_required,
        "definition_claims_required_in_selected": contract.definition_claims_required_in_selected,
        "supporting_claim_policy": "direct_support_for_selected_claims_and_required_definitions",
        "rejected_claim_policy": "stale_superseded_lower_trust_wrong_entity_or_ambiguous_evidence",
        "context_claim_policy": "audit_context_not_direct_answer_support",
        "query_focus_policy": _query_focus_policy_payload(checkpoint),
        "citation_policy": (
            "supporting citations must directly evidence selected claims or required definition claims; "
            "rejection citations evidence rejected traps and should not be treated as answer support"
        ),
    }


def _query_focus_policy_payload(checkpoint: OracleCheckpoint) -> dict[str, object]:
    if checkpoint.checkpoint_type != "entity_split_repair":
        return {
            "supporting_subject_rule": "supporting facts must directly support selected claims",
            "contrastive_evidence_rule": "contrastive evidence belongs in rejected or context channels",
        }
    return {
        "supporting_subject_rule": (
            "for entity_split_repair, non-definition supporting claims must be about the selected subject entity"
        ),
        "definition_subject_rule": (
            "definition/type supporting claims must define the selected subject entity; sibling entity definitions are context"
        ),
        "sibling_entity_rule": (
            "same-name sibling entities are disambiguation evidence only unless the query asks about that sibling"
        ),
        "contrastive_evidence_rule": (
            "claims that explain what was ruled out belong in rejected or context channels, not supporting channels"
        ),
    }


def _is_definition_claim(claim: LatentClaim) -> bool:
    return claim.predicate.predicate_id == "entity_type"


def _is_action_state_claim(claim: LatentClaim) -> bool:
    return claim.claim_kind == "action_state" or claim.predicate.predicate_id == "action_state"


def _is_current_active_claim(claim: LatentClaim) -> bool:
    return claim.lifecycle.state.value == "active"


def _is_stale_or_invalidated_claim(claim: LatentClaim) -> bool:
    return claim.lifecycle.state.value in _SUPPRESSED_LIFECYCLES


def _is_low_trust_or_ambiguous_claim(claim: LatentClaim) -> bool:
    return claim.provenance.source_trust <= 1 or claim.observability.value == "ambiguous"


def _support_channel_hint(
    claim: LatentClaim,
    *,
    checkpoint: OracleCheckpoint,
) -> str:
    if _is_definition_claim(claim):
        return "definition_candidate"
    if _is_stale_or_invalidated_claim(claim) or _is_low_trust_or_ambiguous_claim(claim):
        return "rejection_or_context_candidate"
    if checkpoint.checkpoint_type == "entity_split_repair" and claim.predicate.predicate_id in {"owner", "approver", "api_owner"}:
        return "direct_answer_candidate"
    if claim.claim_kind == "action_state":
        return "direct_answer_candidate"
    return "context_only_candidate"


def _action_state_status(claim: LatentClaim) -> str | None:
    if claim.predicate.predicate_id != "action_state" and claim.claim_kind != "action_state":
        return None
    value = str(claim.object.value).strip().lower()
    if not value:
        return None
    normalized = value.replace("-", "_").replace(" ", "_")
    if normalized in {"inprogress"}:
        return "in_progress"
    if normalized in {"progress", "progressed", "continuing", "continue"}:
        return "in_progress"
    if normalized in {"resume", "resumed", "reopen", "reopened"}:
        return "resumed"
    if normalized in {"start", "started"}:
        return "started"
    if normalized in {"stuck", "blocked"}:
        return "blocked"
    if normalized in {"drop", "dropped", "abandon", "abandoned"}:
        return "abandoned"
    if normalized in {"complete", "completed", "done"}:
        return "completed"
    return normalized


def _continuation_eligibility(claim: LatentClaim) -> str:
    status = _action_state_status(claim)
    if status is None:
        return "not_applicable"
    lifecycle_value = claim.lifecycle.state.value.lower()
    if lifecycle_value in _SUPPRESSED_LIFECYCLES:
        return "suppressed_candidate"
    if status in _SUPPRESSED_ACTION_STATUSES:
        return "suppressed_candidate"
    if status in _ACTIVE_ACTION_STATUSES or status in _START_ACTION_STATUSES:
        return "active_candidate"
    return "audit_context"
