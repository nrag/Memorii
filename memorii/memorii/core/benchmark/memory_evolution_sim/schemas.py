"""Schemas for the deterministic latent-graph memory evolution simulator."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

class ObservabilityLabel(str, Enum):
    OBSERVED = "observed"
    INFERABLE = "inferable"
    AMBIGUOUS = "ambiguous"
    HIDDEN = "hidden"


class SimLifecycleState(str, Enum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    INVALIDATED = "invalidated"
    EXPIRED = "expired"
    ARCHIVED = "archived"
    EVIDENCE_ONLY = "evidence_only"


class JudgeVerdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    ABSTAIN = "abstain"


class LatentEvidenceSpan(BaseModel):
    event_id: str
    quote: str
    char_start: int | None = None
    char_end: int | None = None
    support_type: Literal[
        "direct_mention",
        "subject_support",
        "predicate_support",
        "object_support",
        "relation_support",
        "temporal_support",
        "scope_support",
        "contradiction_support",
        "inference_support",
    ]

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_span(self) -> "LatentEvidenceSpan":
        if not self.quote:
            raise ValueError("evidence quote must be non-empty")
        if (self.char_start is None) != (self.char_end is None):
            raise ValueError("char_start and char_end must be provided together")
        if self.char_start is not None and self.char_end is not None and self.char_start > self.char_end:
            raise ValueError("char_start must be <= char_end")
        return self


class LatentConfidence(BaseModel):
    extraction: float = Field(ge=0.0, le=1.0)
    evidence: float = Field(ge=0.0, le=1.0)
    source_trust: float = Field(ge=0.0, le=1.0)
    agreement: float = Field(ge=0.0, le=1.0)
    contradiction: float = Field(ge=0.0, le=1.0)
    temporal: float = Field(ge=0.0, le=1.0)
    entity_resolution: float = Field(ge=0.0, le=1.0)
    calibrated: float = Field(ge=0.0, le=1.0)
    band: Literal["low", "medium", "high"]
    rationale: str

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_band(self) -> "LatentConfidence":
        expected = "low" if self.calibrated < 0.40 else "medium" if self.calibrated < 0.75 else "high"
        if self.band != expected:
            raise ValueError(f"confidence band {self.band!r} does not match calibrated score")
        if not self.rationale:
            raise ValueError("confidence rationale is required")
        return self


class LatentEntityAlias(BaseModel):
    alias_text: str
    valid_from: datetime
    valid_to: datetime | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_spans: list[LatentEvidenceSpan] = Field(default_factory=list)
    ambiguity_group_id: str | None = None

    model_config = ConfigDict(extra="forbid")


class LatentEntity(BaseModel):
    entity_id: str
    canonical_name: str
    entity_type: Literal[
        "project",
        "service",
        "person",
        "team",
        "task",
        "incident",
        "document",
        "preference",
        "organization",
        "api",
        "database",
        "unknown",
    ]
    description: str
    aliases: list[LatentEntityAlias] = Field(default_factory=list)
    parent_entity_ids: list[str] = Field(default_factory=list)
    child_entity_ids: list[str] = Field(default_factory=list)
    lifecycle_state: Literal["active", "merged", "split", "retired", "ambiguous"] = "active"
    created_at: datetime
    retired_at: datetime | None = None
    merge_target_entity_id: str | None = None
    split_from_entity_id: str | None = None
    defining_claim_ids: list[str] = Field(default_factory=list)
    relation_ids: list[str] = Field(default_factory=list)
    evidence_spans: list[LatentEvidenceSpan] = Field(default_factory=list)
    confidence: LatentConfidence
    observability: ObservabilityLabel
    observability_reason: str
    evaluation_roles: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_entity_support(self) -> "LatentEntity":
        if self.observability != ObservabilityLabel.HIDDEN and not (
            self.evidence_spans or self.defining_claim_ids or self.relation_ids
        ):
            raise ValueError("non-hidden entities require evidence, a defining claim, or an inferable relation")
        return self


class ClaimArgument(BaseModel):
    entity_id: str
    observed_text: str
    canonical_name: str
    entity_type: str
    resolution_confidence: float = Field(ge=0.0, le=1.0)

    model_config = ConfigDict(extra="forbid")


class ClaimPredicate(BaseModel):
    predicate_id: str
    observed_text: str
    value_type: Literal["text", "entity", "boolean", "number", "date", "enum"]
    cardinality: Literal["single", "multi"]
    conflict_policy: Literal["supersede", "accumulate", "contradict", "evidence_only"]
    temporal_policy: Literal["current_value", "historical_event", "expiring_value"]

    model_config = ConfigDict(extra="forbid")


class ClaimObject(BaseModel):
    value: str
    observed_text: str
    normalized_value: str
    entity_id: str | None = None
    resolution_confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    model_config = ConfigDict(extra="forbid")


class ClaimScope(BaseModel):
    scope_key: str = "global"
    task_id: str | None = None
    session_id: str | None = None
    organization_unit: str | None = None

    model_config = ConfigDict(extra="forbid")


class ClaimLifecycle(BaseModel):
    state: SimLifecycleState
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    supersedes_claim_ids: list[str] = Field(default_factory=list)
    superseded_by_claim_id: str | None = None
    conflict_with_claim_ids: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class ClaimEvidence(BaseModel):
    source_event_ids: list[str] = Field(default_factory=list)
    spans: list[LatentEvidenceSpan] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class ClaimProvenance(BaseModel):
    transition_id: str
    extraction_run_id: str
    source_type: str
    source_modality: str
    source_trust: int = Field(ge=0, le=5)

    model_config = ConfigDict(extra="forbid")


class LatentClaim(BaseModel):
    claim_id: str
    claim_kind: Literal[
        "entity_attribute",
        "relationship_fact",
        "preference",
        "status",
        "action_state",
        "belief",
        "temporal_fact",
        "correction",
        "contradiction",
    ]
    subject: ClaimArgument
    predicate: ClaimPredicate
    object: ClaimObject
    scope: ClaimScope
    lifecycle: ClaimLifecycle
    evidence: ClaimEvidence
    provenance: ClaimProvenance
    confidence: LatentConfidence
    supporting_claim_ids: list[str] = Field(default_factory=list)
    contradicts_claim_ids: list[str] = Field(default_factory=list)
    depends_on_claim_ids: list[str] = Field(default_factory=list)
    derived_from_claim_ids: list[str] = Field(default_factory=list)
    observability: ObservabilityLabel
    observability_reason: str
    evaluation_roles: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_claim_support(self) -> "LatentClaim":
        if self.observability == ObservabilityLabel.OBSERVED:
            support_types = {span.support_type for span in self.evidence.spans}
            required = {"subject_support", "predicate_support", "object_support"}
            if not required.issubset(support_types):
                raise ValueError("observed claims require subject, predicate, and object evidence")
        if self.observability == ObservabilityLabel.HIDDEN and self.evidence.spans:
            raise ValueError("hidden claims must not have direct evidence spans")
        return self


class RelationEndpoint(BaseModel):
    endpoint_id: str
    endpoint_type: Literal["entity", "claim", "belief", "task_branch", "source_event", "alias"]
    label: str

    model_config = ConfigDict(extra="forbid")


class RelationTemporal(BaseModel):
    valid_from: datetime | None = None
    valid_to: datetime | None = None

    model_config = ConfigDict(extra="forbid")


class RelationProvenance(BaseModel):
    transition_id: str
    source_event_ids: list[str] = Field(default_factory=list)
    source_modality: str
    source_trust: int = Field(ge=0, le=5)

    model_config = ConfigDict(extra="forbid")


class LatentRelation(BaseModel):
    relation_id: str
    relation_type: Literal[
        "alias_of",
        "same_as",
        "part_of",
        "owned_by",
        "approved_by",
        "supports",
        "contradicts",
        "scoped_to",
        "depends_on",
        "blocks",
        "caused_by",
        "corrects",
        "supersedes",
        "split_from",
        "merged_into",
        "rekeyed_from",
        "observed_in",
    ]
    source: RelationEndpoint
    target: RelationEndpoint
    directionality: Literal["directed", "undirected"]
    temporal: RelationTemporal
    lifecycle_state: SimLifecycleState
    evidence_spans: list[LatentEvidenceSpan] = Field(default_factory=list)
    provenance: RelationProvenance
    confidence: LatentConfidence
    observability: ObservabilityLabel
    observability_reason: str
    evaluation_roles: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_relation_support(self) -> "LatentRelation":
        if self.observability == ObservabilityLabel.OBSERVED and not self.evidence_spans:
            raise ValueError("observed relations require evidence")
        if self.relation_type in {"supports", "contradicts"}:
            valid = {"claim", "belief"}
            if self.source.endpoint_type not in valid or self.target.endpoint_type not in valid:
                raise ValueError("support and contradiction relations must connect claims or beliefs")
        return self


class SurfaceObservation(BaseModel):
    event_id: str
    transition_id: str
    timestamp: datetime
    source_type: Literal["user", "assistant", "tool", "verified_observation", "transcript"]
    modality: str
    phase: Literal["setup", "interference", "evolution", "dormancy", "checkpoint"] = "setup"
    trust_level: int = Field(ge=0, le=5)
    text: str
    exposed_entity_ids: list[str] = Field(default_factory=list)
    exposed_claim_ids: list[str] = Field(default_factory=list)
    exposed_relation_ids: list[str] = Field(default_factory=list)
    hidden_distractor_ids: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class VisibleSurfaceObservation(BaseModel):
    event_id: str
    transition_id: str
    timestamp: datetime
    source_type: Literal["user", "assistant", "tool", "verified_observation", "transcript"]
    modality: str
    phase: Literal["setup", "interference", "evolution", "dormancy", "checkpoint"] = "setup"
    trust_level: int = Field(ge=0, le=5)
    text: str
    exposed_entity_ids: list[str] = Field(default_factory=list)
    exposed_claim_ids: list[str] = Field(default_factory=list)
    exposed_relation_ids: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class WorldTransition(BaseModel):
    transition_id: str
    timestamp: datetime
    transition_type: str
    affected_entity_ids: list[str] = Field(default_factory=list)
    affected_claim_ids: list[str] = Field(default_factory=list)
    affected_relation_ids: list[str] = Field(default_factory=list)
    rationale: str

    model_config = ConfigDict(extra="forbid")


class OracleCheckpoint(BaseModel):
    checkpoint_id: str
    timestamp: datetime
    checkpoint_type: Literal[
        "entity_reconstruction",
        "current_truth",
        "historical_truth",
        "scoped_truth",
        "source_trust_conflict",
        "modality_suppression",
        "entity_disambiguation",
        "entity_split_repair",
        "claim_rekey",
        "belief_ranking",
        "execution_continuation",
        "conflict_audit",
        "abstention",
    ]
    query_or_task: str
    expected_entity_ids: list[str] = Field(default_factory=list)
    expected_claim_ids: list[str] = Field(default_factory=list)
    expected_relation_ids: list[str] = Field(default_factory=list)
    expected_action_ids: list[str] = Field(default_factory=list)
    expected_citation_event_ids: list[str] = Field(default_factory=list)
    expected_excluded_entity_ids: list[str] = Field(default_factory=list)
    expected_excluded_claim_ids: list[str] = Field(default_factory=list)
    expected_uncertain_ids: list[str] = Field(default_factory=list)
    expected_answer: str | None = None
    expected_next_action: str | None = None
    expected_abstention: bool = False
    difficulty_tags: list[str] = Field(default_factory=list)
    required_judge_ids: list[str] = Field(default_factory=list)
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    horizon_distance: int = 0
    interference_count: int = 0
    source_event_age_days: float = 0.0
    required_retrieval_view: Literal["current", "historical_at", "all_versions", "conflicts", "evidence_only"] = "current"
    expected_stage_path: list[Literal["extraction", "validation", "lifecycle_evolution", "graph_projection", "alignment", "retrieval_decision"]] = Field(
        default_factory=lambda: [
            "extraction",
            "validation",
            "lifecycle_evolution",
            "graph_projection",
            "alignment",
            "retrieval_decision",
        ]
    )

    model_config = ConfigDict(extra="forbid")


class SimOutputNormalization(BaseModel):
    normalization_applied: bool = False
    auto_closed_selected_entity_ids: list[str] = Field(default_factory=list)
    auto_closed_rejected_entity_ids: list[str] = Field(default_factory=list)
    auto_closed_context_entity_ids: list[str] = Field(default_factory=list)
    auto_closed_context_relation_ids: list[str] = Field(default_factory=list)
    auto_promoted_selected_claim_ids: list[str] = Field(default_factory=list)
    auto_promoted_supporting_claim_ids: list[str] = Field(default_factory=list)
    auto_promoted_supporting_citation_event_ids: list[str] = Field(default_factory=list)
    auto_rejected_claim_ids: list[str] = Field(default_factory=list)
    normalization_reason_codes: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


def _ordered_unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


class SimSystemOutput(BaseModel):
    operation: Literal["answer", "next_action", "graph_reconstruction", "abstain"] = "answer"
    entity_ids: list[str] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    relation_ids: list[str] = Field(default_factory=list)
    citation_event_ids: list[str] = Field(default_factory=list)
    belief_ranking_ids: list[str] = Field(default_factory=list)
    selected_entity_ids: list[str] = Field(default_factory=list)
    selected_claim_ids: list[str] = Field(default_factory=list)
    selected_relation_ids: list[str] = Field(default_factory=list)
    supporting_claim_ids: list[str] = Field(default_factory=list)
    supporting_relation_ids: list[str] = Field(default_factory=list)
    supporting_citation_event_ids: list[str] = Field(default_factory=list)
    rejected_entity_ids: list[str] = Field(default_factory=list)
    rejected_claim_ids: list[str] = Field(default_factory=list)
    rejected_relation_ids: list[str] = Field(default_factory=list)
    rejection_citation_event_ids: list[str] = Field(default_factory=list)
    context_entity_ids: list[str] = Field(default_factory=list)
    context_claim_ids: list[str] = Field(default_factory=list)
    context_relation_ids: list[str] = Field(default_factory=list)
    context_citation_event_ids: list[str] = Field(default_factory=list)
    answer: str | None = None
    next_action: str | None = None
    uncertain_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    rationale: str

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def populate_legacy_and_role_views(self) -> "SimSystemOutput":
        role_channels_empty = not any(
            [
                self.selected_entity_ids,
                self.selected_claim_ids,
                self.selected_relation_ids,
                self.supporting_claim_ids,
                self.supporting_relation_ids,
                self.supporting_citation_event_ids,
                self.rejected_entity_ids,
                self.rejected_claim_ids,
                self.rejected_relation_ids,
                self.rejection_citation_event_ids,
                self.context_entity_ids,
                self.context_claim_ids,
                self.context_relation_ids,
                self.context_citation_event_ids,
            ]
        )
        if role_channels_empty and not self.selected_entity_ids and self.entity_ids:
            self.selected_entity_ids = list(self.entity_ids)
        if role_channels_empty and not self.selected_claim_ids and self.claim_ids:
            self.selected_claim_ids = list(self.claim_ids)
        if role_channels_empty and not self.selected_relation_ids and self.relation_ids:
            self.selected_relation_ids = list(self.relation_ids)
        if role_channels_empty and not self.supporting_citation_event_ids and self.citation_event_ids:
            self.supporting_citation_event_ids = list(self.citation_event_ids)
        self.entity_ids = _ordered_unique([
            *self.selected_entity_ids,
            *self.context_entity_ids,
            *self.rejected_entity_ids,
        ])
        self.claim_ids = _ordered_unique([
            *self.selected_claim_ids,
            *self.supporting_claim_ids,
            *self.context_claim_ids,
            *self.rejected_claim_ids,
        ])
        self.relation_ids = _ordered_unique([
            *self.selected_relation_ids,
            *self.supporting_relation_ids,
            *self.context_relation_ids,
            *self.rejected_relation_ids,
        ])
        self.citation_event_ids = _ordered_unique([
            *self.supporting_citation_event_ids,
            *self.context_citation_event_ids,
            *self.rejection_citation_event_ids,
        ])
        return self


class VisibleEventCandidate(BaseModel):
    event_id: str
    timestamp: datetime
    source_type: str
    modality: str
    phase: str = "setup"
    trust_level: int
    text: str

    model_config = ConfigDict(extra="forbid")


class VisibleEntityCandidate(BaseModel):
    entity_id: str
    canonical_name: str
    entity_type: str
    aliases: list[str] = Field(default_factory=list)
    lifecycle_state: str
    evidence_event_ids: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class VisibleClaimCandidate(BaseModel):
    claim_id: str
    subject_entity_id: str
    subject_name: str
    predicate_id: str
    object_value: str
    object_entity_id: str | None = None
    scope_key: str
    lifecycle_state: str
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    source_trust: int
    source_modality: str
    evidence_event_ids: list[str] = Field(default_factory=list)
    evidence_quote: str
    contradicts_claim_ids: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class VisibleRelationCandidate(BaseModel):
    relation_id: str
    relation_type: str
    source_id: str
    source_type: str
    source_label: str
    target_id: str
    target_type: str
    target_label: str
    directionality: str
    lifecycle_state: str
    evidence_event_ids: list[str] = Field(default_factory=list)
    evidence_quote: str

    model_config = ConfigDict(extra="forbid")


class VisibleCheckpointCandidate(BaseModel):
    checkpoint_id: str
    timestamp: datetime
    checkpoint_type: str
    query_or_task: str
    difficulty_tags: list[str] = Field(default_factory=list)
    severity: str
    horizon_distance: int = 0
    interference_count: int = 0
    source_event_age_days: float = 0.0
    required_retrieval_view: str = "current"
    stage_path: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class MemoryEvolutionSimReconstructionContext(BaseModel):
    scenario_id: str
    family: str
    profile: str
    surface_observations: list[VisibleSurfaceObservation]
    checkpoint: VisibleCheckpointCandidate
    difficulty_tags: list[str] = Field(default_factory=list)
    visible_entity_ids: list[str] = Field(default_factory=list)
    visible_claim_ids: list[str] = Field(default_factory=list)
    visible_relation_ids: list[str] = Field(default_factory=list)
    visible_events: list[VisibleEventCandidate] = Field(default_factory=list)
    visible_entities: list[VisibleEntityCandidate] = Field(default_factory=list)
    visible_claims: list[VisibleClaimCandidate] = Field(default_factory=list)
    visible_relations: list[VisibleRelationCandidate] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class JudgeVote(BaseModel):
    judge_id: str
    checkpoint_id: str
    verdict: JudgeVerdict
    score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    covered_ids: list[str] = Field(default_factory=list)
    failed_ids: list[str] = Field(default_factory=list)
    abstained_ids: list[str] = Field(default_factory=list)
    failure_buckets: list[str] = Field(default_factory=list)
    rationale: str

    model_config = ConfigDict(extra="forbid")


class JudgeAggregate(BaseModel):
    checkpoint_id: str
    verdict: JudgeVerdict
    score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    votes: list[JudgeVote] = Field(default_factory=list)
    required_judge_ids: list[str] = Field(default_factory=list)
    critical_failure_buckets: list[str] = Field(default_factory=list)
    review_required: bool = False
    rationale: str

    model_config = ConfigDict(extra="forbid")


class LatentGraphScenario(BaseModel):
    scenario_id: str
    family: str
    profile: str
    seed: int
    entities: list[LatentEntity]
    claims: list[LatentClaim]
    relations: list[LatentRelation]
    transitions: list[WorldTransition]
    observations: list[SurfaceObservation]
    checkpoints: list[OracleCheckpoint]
    discriminative: bool = True

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_references(self) -> "LatentGraphScenario":
        entity_ids = {item.entity_id for item in self.entities}
        claim_ids = {item.claim_id for item in self.claims}
        relation_ids = {item.relation_id for item in self.relations}
        event_ids = {item.event_id for item in self.observations}
        exposed_claims_by_event: dict[str, set[str]] = {}
        exposed_relations_by_event: dict[str, set[str]] = {}
        for observation in self.observations:
            for claim_id in observation.exposed_claim_ids:
                exposed_claims_by_event.setdefault(claim_id, set()).add(observation.event_id)
            for relation_id in observation.exposed_relation_ids:
                exposed_relations_by_event.setdefault(relation_id, set()).add(observation.event_id)
        for claim in self.claims:
            if claim.observability == ObservabilityLabel.HIDDEN:
                continue
            exposed_events = exposed_claims_by_event.get(claim.claim_id, set())
            evidence_events = set(claim.evidence.source_event_ids)
            if exposed_events and not (evidence_events & exposed_events):
                raise ValueError(
                    f"claim {claim.claim_id} evidence does not reference an observation that exposes it"
                )
        for relation in self.relations:
            if relation.observability == ObservabilityLabel.HIDDEN:
                continue
            exposed_events = exposed_relations_by_event.get(relation.relation_id, set())
            evidence_events = set(relation.provenance.source_event_ids)
            if exposed_events and not (evidence_events & exposed_events):
                raise ValueError(
                    f"relation {relation.relation_id} evidence does not reference an observation that exposes it"
                )
        for checkpoint in self.checkpoints:
            if set(checkpoint.expected_entity_ids) - entity_ids:
                raise ValueError(f"checkpoint {checkpoint.checkpoint_id} references unknown entities")
            if set(checkpoint.expected_claim_ids) - claim_ids:
                raise ValueError(f"checkpoint {checkpoint.checkpoint_id} references unknown claims")
            if set(checkpoint.expected_relation_ids) - relation_ids:
                raise ValueError(f"checkpoint {checkpoint.checkpoint_id} references unknown relations")
            if set(checkpoint.expected_citation_event_ids) - event_ids:
                raise ValueError(f"checkpoint {checkpoint.checkpoint_id} references unknown observations")
            required_ids = [
                *checkpoint.expected_entity_ids,
                *checkpoint.expected_claim_ids,
                *checkpoint.expected_relation_ids,
            ]
            hidden_required = [
                item_id
                for item_id in required_ids
                if self._observability_for(item_id) == ObservabilityLabel.HIDDEN
            ]
            if hidden_required:
                raise ValueError(f"checkpoint {checkpoint.checkpoint_id} requires hidden ids: {hidden_required}")
        return self

    def _observability_for(self, item_id: str) -> ObservabilityLabel | None:
        for item in self.entities:
            if item.entity_id == item_id:
                return item.observability
        for item in self.claims:
            if item.claim_id == item_id:
                return item.observability
        for item in self.relations:
            if item.relation_id == item_id:
                return item.observability
        return None
