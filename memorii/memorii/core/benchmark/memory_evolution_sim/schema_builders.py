"""Scenario generation for the memory evolution simulator."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from memorii.core.benchmark.memory_evolution_sim.schemas import (
    ClaimArgument,
    ClaimEvidence,
    ClaimLifecycle,
    ClaimObject,
    ClaimPredicate,
    ClaimProvenance,
    ClaimScope,
    EvidenceSupportType,
    LatentClaim,
    LatentConfidence,
    LatentEntity,
    LatentEntityAlias,
    LatentEvidenceSpan,
    ObservabilityLabel,
    SimLifecycleState,
)


def entity(
    entity_id: str,
    name: str,
    entity_type: Literal["project", "service"],
    created_at: datetime,
    event_id: str,
    defining_claim_id: str,
    relation_ids: list[str],
    *,
    include_ambiguous_alias: bool = False,
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
                evidence_spans=[span(event_id, name.split()[0], "direct_mention")],
                ambiguity_group_id="ambig_atlas",
            )
        ]
        + (
            [
                LatentEntityAlias(
                    alias_text="Atlas",
                    valid_from=created_at,
                    confidence=0.75,
                    evidence_spans=[span(event_id, "Atlas", "direct_mention")],
                    ambiguity_group_id="ambig_atlas",
                )
            ]
            if entity_type == "service" and include_ambiguous_alias
            else []
        ),
        created_at=created_at,
        defining_claim_ids=[defining_claim_id],
        relation_ids=relation_ids,
        evidence_spans=[span(event_id, name.split()[0], "direct_mention")],
        confidence=build_confidence(0.9),
        observability=ObservabilityLabel.OBSERVED,
        observability_reason="directly stated by surface observation",
        evaluation_roles=["entity_reconstruction", "entity_type_disambiguation"],
    )


def person(entity_id: str, name: str, created_at: datetime, event_id: str) -> LatentEntity:
    return LatentEntity(
        entity_id=entity_id,
        canonical_name=name,
        entity_type="person",
        description=f"{name} person entity",
        aliases=[],
        created_at=created_at,
        evidence_spans=[span(event_id, name, "direct_mention")],
        confidence=build_confidence(0.9),
        observability=ObservabilityLabel.OBSERVED,
        observability_reason="directly mentioned in surface observation",
        evaluation_roles=["entity_reconstruction"],
    )


def task_entity(
    entity_id: str, name: str, created_at: datetime, event_id: str, defining_claim_id: str
) -> LatentEntity:
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
                evidence_spans=[span(event_id, name, "direct_mention")],
            )
        ],
        created_at=created_at,
        defining_claim_ids=[defining_claim_id],
        evidence_spans=[span(event_id, name, "direct_mention")],
        confidence=build_confidence(0.85),
        observability=ObservabilityLabel.OBSERVED,
        observability_reason="directly mentioned in action-state surface observation",
        evaluation_roles=["execution_continuation", "action_state"],
    )


def hidden_person(entity_id: str, name: str, created_at: datetime) -> LatentEntity:
    return LatentEntity(
        entity_id=entity_id,
        canonical_name=name,
        entity_type="person",
        description=f"{name} hidden person entity",
        aliases=[],
        created_at=created_at,
        evidence_spans=[],
        confidence=build_confidence(0.35),
        observability=ObservabilityLabel.HIDDEN,
        observability_reason="latent hidden entity with no surface evidence",
        evaluation_roles=["hidden_hallucination_trap"],
    )


def claim(
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
    scope: ClaimScope | None = None,
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
        scope=scope or ClaimScope(scope_key="global", organization_unit="Finance Ops"),
        lifecycle=ClaimLifecycle(state=state, valid_from=timestamp, valid_to=valid_to),
        evidence=ClaimEvidence(
            source_event_ids=[event_id],
            spans=[
                span(event_id, quote, "subject_support"),
                span(event_id, quote, "predicate_support"),
                span(event_id, quote, "object_support"),
            ],
        ),
        provenance=ClaimProvenance(
            transition_id=transition_id,
            extraction_run_id="oracle",
            source_type="tool" if "org_directory" in quote else "user",
            source_modality="tool_result" if "org_directory" in quote else "assertion",
            source_trust=5 if "org_directory" in quote else 3,
        ),
        confidence=confidence or build_confidence(0.9 if state == SimLifecycleState.ACTIVE else 0.75),
        observability=observability,
        observability_reason="directly supported by surface text",
        evaluation_roles=roles,
    )


def hidden_claim(
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
        confidence=build_confidence(0.35),
        observability=ObservabilityLabel.HIDDEN,
        observability_reason="latent hidden claim with no surface evidence",
        evaluation_roles=["hidden_hallucination_trap"],
    )


def span(event_id: str, quote: str, support_type: EvidenceSupportType) -> LatentEvidenceSpan:
    return LatentEvidenceSpan(
        event_id=event_id,
        quote=quote,
        support_type=support_type,
    )


def build_confidence(score: float) -> LatentConfidence:
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
