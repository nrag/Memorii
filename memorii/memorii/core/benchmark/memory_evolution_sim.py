"""Deterministic latent-graph simulator for memory evolution benchmarks."""

from __future__ import annotations

import random
import re
from collections import Counter
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from memorii.core.llm_decision.models import LLMDecisionMode, LLMDecisionPoint, LLMDecisionStatus, LLMDecisionTrace
from memorii.core.llm_provider.models import LLMDecisionResult, LLMStructuredRequest, LLMStructuredResponse
from memorii.core.llm_trace.builder import build_llm_decision_trace_from_result


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


def sim_output_allowed_id_errors(*, scenario: LatentGraphScenario, output: SimSystemOutput) -> list[str]:
    visible_entities = {item for obs in scenario.observations for item in obs.exposed_entity_ids}
    visible_claims = {item for obs in scenario.observations for item in obs.exposed_claim_ids}
    visible_relations = {item for obs in scenario.observations for item in obs.exposed_relation_ids}
    errors: list[str] = []
    for field_name, actual, allowed in [
        ("entity_ids", output.entity_ids, visible_entities),
        ("selected_entity_ids", output.selected_entity_ids, visible_entities),
        ("rejected_entity_ids", output.rejected_entity_ids, visible_entities),
        ("context_entity_ids", output.context_entity_ids, visible_entities),
        ("claim_ids", output.claim_ids, visible_claims),
        ("selected_claim_ids", output.selected_claim_ids, visible_claims),
        ("supporting_claim_ids", output.supporting_claim_ids, visible_claims),
        ("rejected_claim_ids", output.rejected_claim_ids, visible_claims),
        ("context_claim_ids", output.context_claim_ids, visible_claims),
        ("relation_ids", output.relation_ids, visible_relations),
        ("selected_relation_ids", output.selected_relation_ids, visible_relations),
        ("supporting_relation_ids", output.supporting_relation_ids, visible_relations),
        ("rejected_relation_ids", output.rejected_relation_ids, visible_relations),
        ("context_relation_ids", output.context_relation_ids, visible_relations),
        ("belief_ranking_ids", output.belief_ranking_ids, visible_claims),
    ]:
        unknown = sorted(set(actual) - allowed)
        if unknown:
            errors.append(f"invalid_{field_name}:{','.join(unknown)}")
    event_ids = {obs.event_id for obs in scenario.observations}
    for field_name, actual in [
        ("citation_event_ids", output.citation_event_ids),
        ("supporting_citation_event_ids", output.supporting_citation_event_ids),
        ("rejection_citation_event_ids", output.rejection_citation_event_ids),
        ("context_citation_event_ids", output.context_citation_event_ids),
    ]:
        unknown_events = sorted(set(actual) - event_ids)
        if unknown_events:
            errors.append(f"invalid_{field_name}:{','.join(unknown_events)}")
    hidden_ids = {
        item.entity_id for item in scenario.entities if item.observability == ObservabilityLabel.HIDDEN
    } | {
        item.claim_id for item in scenario.claims if item.observability == ObservabilityLabel.HIDDEN
    } | {
        item.relation_id for item in scenario.relations if item.observability == ObservabilityLabel.HIDDEN
    }
    asserted = (
        set(output.entity_ids)
        | set(output.selected_entity_ids)
        | set(output.rejected_entity_ids)
        | set(output.context_entity_ids)
        | set(output.claim_ids)
        | set(output.selected_claim_ids)
        | set(output.supporting_claim_ids)
        | set(output.rejected_claim_ids)
        | set(output.context_claim_ids)
        | set(output.relation_ids)
        | set(output.selected_relation_ids)
        | set(output.supporting_relation_ids)
        | set(output.rejected_relation_ids)
        | set(output.context_relation_ids)
    )
    hallucinated = sorted(asserted & hidden_ids)
    if hallucinated:
        errors.append(f"hidden_ids_asserted:{','.join(hallucinated)}")
    answer_leaks = _hidden_answer_leaks(scenario, output)
    if answer_leaks:
        errors.append(f"hidden_answer_leak:{','.join(answer_leaks)}")
    return errors


def expected_sim_output_for_checkpoint(checkpoint: OracleCheckpoint) -> SimSystemOutput:
    operation: Literal["answer", "next_action", "graph_reconstruction", "abstain"]
    if checkpoint.expected_abstention:
        operation = "abstain"
    elif checkpoint.expected_next_action is not None:
        operation = "next_action"
    elif "graph_reconstruction" in _checkpoint_contract_for_type(checkpoint.checkpoint_type)["allowed_operations"]:
        operation = "graph_reconstruction"
    else:
        operation = "answer"
    rejected_claim_ids = list(checkpoint.expected_excluded_claim_ids)
    rejected_entity_ids = list(checkpoint.expected_excluded_entity_ids)
    rejected_relation_ids: list[str] = []
    context_claim_ids: list[str] = []
    context_entity_ids: list[str] = []
    context_relation_ids: list[str] = []
    if checkpoint.checkpoint_type in {"entity_reconstruction", "entity_split_repair", "claim_rekey", "conflict_audit"}:
        context_claim_ids = list(rejected_claim_ids)
        context_entity_ids = list(rejected_entity_ids)
        context_relation_ids = list(checkpoint.expected_relation_ids)
    selected_claim_ids = list(checkpoint.expected_claim_ids)
    selected_entity_ids = list(checkpoint.expected_entity_ids)
    selected_relation_ids = list(checkpoint.expected_relation_ids)
    supporting_claim_ids = list(checkpoint.expected_claim_ids)
    supporting_relation_ids = list(checkpoint.expected_relation_ids)
    if checkpoint.checkpoint_type == "source_trust_conflict":
        selected_relation_ids = []
        supporting_relation_ids = []
        context_relation_ids = _ordered_unique([*context_relation_ids, *checkpoint.expected_relation_ids])
    supporting_citation_event_ids = list(checkpoint.expected_citation_event_ids)
    return SimSystemOutput(
        operation=operation,
        entity_ids=_ordered_unique([*selected_entity_ids, *context_entity_ids, *rejected_entity_ids]),
        claim_ids=_ordered_unique([*selected_claim_ids, *supporting_claim_ids, *context_claim_ids, *rejected_claim_ids]),
        relation_ids=_ordered_unique([*selected_relation_ids, *supporting_relation_ids, *context_relation_ids, *rejected_relation_ids]),
        citation_event_ids=list(supporting_citation_event_ids),
        belief_ranking_ids=list(checkpoint.expected_claim_ids) if checkpoint.checkpoint_type == "belief_ranking" else [],
        selected_entity_ids=selected_entity_ids,
        selected_claim_ids=selected_claim_ids,
        selected_relation_ids=selected_relation_ids,
        supporting_claim_ids=supporting_claim_ids,
        supporting_relation_ids=supporting_relation_ids,
        supporting_citation_event_ids=supporting_citation_event_ids,
        rejected_entity_ids=rejected_entity_ids,
        rejected_claim_ids=rejected_claim_ids,
        rejected_relation_ids=rejected_relation_ids,
        rejection_citation_event_ids=[],
        context_entity_ids=context_entity_ids,
        context_claim_ids=context_claim_ids,
        context_relation_ids=context_relation_ids,
        context_citation_event_ids=[],
        answer=checkpoint.expected_answer,
        next_action=checkpoint.expected_next_action,
        uncertain_ids=list(checkpoint.expected_uncertain_ids),
        confidence=0.92 if not checkpoint.expected_abstention else 0.35,
        rationale="oracle-shaped dry-run graph reconstruction",
    )


def normalize_sim_system_output_for_checkpoint(
    *,
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
) -> tuple[SimSystemOutput, SimOutputNormalization]:
    """Complete safe role-aware graph channels using visible scenario candidates.

    The normalizer repairs deterministic channel omissions, but intentionally does
    not remove selected/supporting pollution. Wrong-entity or stale evidence in
    supporting_* must still fail precision judges.
    """

    selected_entity_ids = list(output.selected_entity_ids)
    selected_claim_ids = list(output.selected_claim_ids)
    supporting_claim_ids = list(output.supporting_claim_ids)
    supporting_citation_event_ids = list(output.supporting_citation_event_ids)
    rejected_entity_ids = list(output.rejected_entity_ids)
    rejected_claim_ids = list(output.rejected_claim_ids)
    context_entity_ids = list(output.context_entity_ids)
    context_relation_ids = list(output.context_relation_ids)

    auto_selected_entities: list[str] = []
    auto_rejected_entities: list[str] = []
    auto_context_entities: list[str] = []
    auto_selected_claims: list[str] = []
    auto_supporting_claims: list[str] = []
    auto_supporting_events: list[str] = []
    auto_rejected_claims: list[str] = []
    auto_context_relations: list[str] = []
    reason_codes: list[str] = []

    def add_once(items: list[str], item: str, added: list[str], reason: str | None = None) -> None:
        if item not in items:
            items.append(item)
            added.append(item)
            if reason is not None:
                reason_codes.append(reason)

    visible_entities = {
        entity.entity_id for entity in scenario.entities if entity.observability != ObservabilityLabel.HIDDEN
    }
    visible_claims = {
        claim.claim_id
        for claim in scenario.claims
        if claim.observability != ObservabilityLabel.HIDDEN and _is_visible_claim(scenario, claim.claim_id)
    }
    visible_relations = {
        relation.relation_id
        for relation in scenario.relations
        if relation.observability != ObservabilityLabel.HIDDEN
        and any(relation.relation_id in observation.exposed_relation_ids for observation in scenario.observations)
    }
    selected_or_supporting_claims = set(selected_claim_ids) | set(supporting_claim_ids)

    # Negative modality-suppression answers still need the active current truth in
    # selected/supporting channels when the model only placed it in context.
    if checkpoint.checkpoint_type == "modality_suppression":
        for claim_id in checkpoint.expected_claim_ids:
            claim = _claim_by_id(scenario, claim_id)
            if claim is None or claim_id not in visible_claims:
                continue
            if claim_id in output.context_claim_ids and claim_id not in selected_or_supporting_claims:
                add_once(selected_claim_ids, claim_id, auto_selected_claims, "current_truth_promoted_from_context")
                add_once(supporting_claim_ids, claim_id, auto_supporting_claims, "current_truth_promoted_from_context")
                if claim.subject.entity_id in visible_entities:
                    add_once(selected_entity_ids, claim.subject.entity_id, auto_selected_entities, "current_truth_promoted_from_context")
                for event_id in claim.evidence.source_event_ids:
                    add_once(
                        supporting_citation_event_ids,
                        event_id,
                        auto_supporting_events,
                        "current_truth_promoted_from_context",
                    )

    # Graph reconstruction requires entity definition/type support for selected
    # role facts; complete it from visible definition claims.
    interim_for_definitions = output.model_copy(update={"selected_claim_ids": _ordered_unique(selected_claim_ids)})
    for claim_id in _required_definition_claim_ids_for_selected_claims(scenario, interim_for_definitions):
        claim = _claim_by_id(scenario, claim_id)
        if claim is None or claim_id not in visible_claims:
            continue
        if claim_id not in selected_claim_ids:
            add_once(selected_claim_ids, claim_id, auto_selected_claims, "definition_claim_completed")
        if claim_id not in supporting_claim_ids:
            add_once(supporting_claim_ids, claim_id, auto_supporting_claims, "definition_claim_completed")
        for event_id in claim.evidence.source_event_ids:
            add_once(supporting_citation_event_ids, event_id, auto_supporting_events, "definition_claim_completed")

    # Explicit wrong-role traps should be rejected/contextualized when visible,
    # unless the model used them as selected/supporting truth. In that case the
    # precision judges must still fail.
    if checkpoint.checkpoint_type in {"entity_disambiguation", "entity_split_repair"}:
        selected_or_supporting_claims = set(selected_claim_ids) | set(supporting_claim_ids)
        for claim_id in checkpoint.expected_excluded_claim_ids:
            if claim_id not in visible_claims or claim_id in selected_or_supporting_claims:
                continue
            if claim_id not in rejected_claim_ids and claim_id not in output.context_claim_ids:
                add_once(rejected_claim_ids, claim_id, auto_rejected_claims, "visible_excluded_claim_rejected")

    selected_required_output = output.model_copy(update={"selected_claim_ids": _ordered_unique(selected_claim_ids)})
    selected_required = _required_selected_entity_ids_for_policy(
        scenario=scenario,
        checkpoint=checkpoint,
        output=selected_required_output,
    )
    for entity_id in selected_required:
        if entity_id in visible_entities:
            add_once(selected_entity_ids, entity_id, auto_selected_entities, "selected_claim_subject_closed")

    for claim_id in rejected_claim_ids:
        claim = _claim_by_id(scenario, claim_id)
        if claim is None or claim.observability == ObservabilityLabel.HIDDEN:
            continue
        subject_entity_id = claim.subject.entity_id
        if subject_entity_id not in visible_entities:
            continue
        if subject_entity_id in selected_entity_ids:
            continue
        if subject_entity_id not in rejected_entity_ids and subject_entity_id not in context_entity_ids:
            add_once(rejected_entity_ids, subject_entity_id, auto_rejected_entities, "rejected_claim_subject_closed")

    for claim_id in output.context_claim_ids:
        claim = _claim_by_id(scenario, claim_id)
        if claim is None or claim.observability == ObservabilityLabel.HIDDEN:
            continue
        subject_entity_id = claim.subject.entity_id
        if subject_entity_id not in visible_entities:
            continue
        if subject_entity_id not in context_entity_ids:
            add_once(context_entity_ids, subject_entity_id, auto_context_entities, "context_claim_subject_closed")

    role_claim_ids = set(selected_claim_ids) | set(supporting_claim_ids) | set(rejected_claim_ids) | set(output.context_claim_ids)
    role_relation_ids = (
        set(output.selected_relation_ids)
        | set(output.supporting_relation_ids)
        | set(output.rejected_relation_ids)
        | set(context_relation_ids)
    )
    for relation in scenario.relations:
        if relation.relation_id not in visible_relations or relation.relation_id in role_relation_ids:
            continue
        if relation.relation_type not in {"contradicts", "corrects", "supersedes"}:
            continue
        if relation.source.endpoint_type != "claim" or relation.target.endpoint_type != "claim":
            continue
        if relation.source.endpoint_id in role_claim_ids and relation.target.endpoint_id in role_claim_ids:
            add_once(
                context_relation_ids,
                relation.relation_id,
                auto_context_relations,
                "visible_conflict_relation_closed_from_claim_channels",
            )

    normalized = output.model_copy(
        update={
            "selected_entity_ids": _ordered_unique(selected_entity_ids),
            "selected_claim_ids": _ordered_unique(selected_claim_ids),
            "supporting_claim_ids": _ordered_unique(supporting_claim_ids),
            "supporting_citation_event_ids": _ordered_unique(supporting_citation_event_ids),
            "rejected_entity_ids": _ordered_unique(rejected_entity_ids),
            "rejected_claim_ids": _ordered_unique(rejected_claim_ids),
            "context_entity_ids": _ordered_unique(context_entity_ids),
            "context_relation_ids": _ordered_unique(context_relation_ids),
        }
    )
    normalized = SimSystemOutput.model_validate(normalized.model_dump(mode="json"))
    summary = SimOutputNormalization(
        normalization_applied=bool(
            auto_selected_entities
            or auto_rejected_entities
            or auto_context_entities
            or auto_selected_claims
            or auto_supporting_claims
            or auto_supporting_events
            or auto_rejected_claims
            or auto_context_relations
        ),
        auto_closed_selected_entity_ids=_ordered_unique(auto_selected_entities),
        auto_closed_rejected_entity_ids=_ordered_unique(auto_rejected_entities),
        auto_closed_context_entity_ids=_ordered_unique(auto_context_entities),
        auto_closed_context_relation_ids=_ordered_unique(auto_context_relations),
        auto_promoted_selected_claim_ids=_ordered_unique(auto_selected_claims),
        auto_promoted_supporting_claim_ids=_ordered_unique(auto_supporting_claims),
        auto_promoted_supporting_citation_event_ids=_ordered_unique(auto_supporting_events),
        auto_rejected_claim_ids=_ordered_unique(auto_rejected_claims),
        normalization_reason_codes=_ordered_unique(reason_codes),
    )
    return normalized, summary


def fake_llm_result_for_memory_evolution_sim(
    *,
    request: LLMStructuredRequest,
    decision: SimSystemOutput,
    provider_name: str = "fake",
) -> LLMDecisionResult:
    import json

    output = decision.model_dump(mode="json")
    response = LLMStructuredResponse(
        request_id=request.request_id,
        provider=provider_name,
        model=request.model_defaults.model,
        raw_text=json.dumps(output, sort_keys=True),
        parsed_json=output,
        valid_json=True,
        schema_valid=True,
    )
    return LLMDecisionResult(request=request, response=response, output=output, success=True, failure_mode=None)


def memory_evolution_sim_trace_for_rule(
    *,
    context: MemoryEvolutionSimReconstructionContext,
    decision: SimSystemOutput,
    mode: str,
) -> LLMDecisionTrace:
    from uuid import uuid4

    return LLMDecisionTrace(
        trace_id=f"trace:sim-rule:{uuid4().hex}",
        decision_point=LLMDecisionPoint.MEMORY_EVOLUTION_SIM_RECONSTRUCTION,
        mode=LLMDecisionMode(mode),
        input_payload=context.model_dump(mode="json"),
        parsed_output=decision.model_dump(mode="json"),
        final_output=decision.model_dump(mode="json"),
        status=LLMDecisionStatus.SUCCEEDED,
        created_at=datetime.now(UTC),
    )


def memory_evolution_sim_engine_result_from_llm(
    *,
    result: LLMDecisionResult,
    mode: LLMDecisionMode,
    scenario: LatentGraphScenario,
    rule_output: dict[str, object],
) -> tuple[dict[str, object], LLMDecisionTrace, bool, str | None]:
    if not result.success:
        trace = build_llm_decision_trace_from_result(
            decision_point=LLMDecisionPoint.MEMORY_EVOLUTION_SIM_RECONSTRUCTION,
            mode=mode,
            result=result,
            final_output=rule_output,
            fallback_used=True,
            status=LLMDecisionStatus.PROVIDER_ERROR,
        )
        return rule_output, trace, False, result.failure_mode or "llm_decision_failed"
    try:
        decision = SimSystemOutput.model_validate(result.output)
    except ValidationError:
        trace = build_llm_decision_trace_from_result(
            decision_point=LLMDecisionPoint.MEMORY_EVOLUTION_SIM_RECONSTRUCTION,
            mode=mode,
            result=result,
            final_output=rule_output,
            fallback_used=True,
            status=LLMDecisionStatus.VALIDATION_FAILED,
        )
        return rule_output, trace, False, "llm_decision_validation_failed"
    id_errors = sim_output_allowed_id_errors(scenario=scenario, output=decision)
    if id_errors:
        trace = build_llm_decision_trace_from_result(
            decision_point=LLMDecisionPoint.MEMORY_EVOLUTION_SIM_RECONSTRUCTION,
            mode=mode,
            result=result,
            final_output=rule_output,
            fallback_used=True,
            status=LLMDecisionStatus.VALIDATION_FAILED,
        )
        trace.validation_errors.extend(id_errors)
        return rule_output, trace, False, "llm_output_referenced_invalid_ids"
    output = decision.model_dump(mode="json")
    trace = build_llm_decision_trace_from_result(
        decision_point=LLMDecisionPoint.MEMORY_EVOLUTION_SIM_RECONSTRUCTION,
        mode=mode,
        result=result,
        final_output=output,
        fallback_used=False,
        status=LLMDecisionStatus.SUCCEEDED,
    )
    return output, trace, True, None


def rule_sim_output_for_checkpoint(
    *,
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
) -> SimSystemOutput:
    tokens = set(_norm(checkpoint.query_or_task).split())
    candidates = [event for event in scenario.observations if event.modality != "noise"]
    historical_intent = bool(tokens & {"january", "historical", "before", "previously", "earlier"})
    owner_intent = bool(tokens & {"owner", "owns", "owned", "ownership"})
    def owner_score(event: SurfaceObservation) -> int:
        event_tokens = set(_norm(event.text).split())
        return 1 if owner_intent and event_tokens & {"owner", "owns", "owned", "ownership"} else 0

    if historical_intent:
        ranked = sorted(
            candidates,
            key=lambda event: (
                -owner_score(event),
                -len(tokens & set(_norm(event.text).split())),
                event.timestamp.timestamp(),
                -event.trust_level,
                event.event_id,
            ),
        )
    else:
        ranked = sorted(
            candidates,
            key=lambda event: (
                -owner_score(event),
                -len(tokens & set(_norm(event.text).split())),
                -event.trust_level,
                -event.timestamp.timestamp(),
                event.event_id,
            ),
        )
    selected = ranked[0] if ranked else None
    return SimSystemOutput(
        operation="next_action" if checkpoint.expected_next_action else "answer",
        entity_ids=list(selected.exposed_entity_ids if selected else []),
        claim_ids=list(selected.exposed_claim_ids if selected else []),
        relation_ids=list(selected.exposed_relation_ids if selected else []),
        citation_event_ids=[selected.event_id] if selected else [],
        belief_ranking_ids=list(selected.exposed_claim_ids if selected and checkpoint.checkpoint_type == "belief_ranking" else []),
        selected_entity_ids=list(selected.exposed_entity_ids if selected else []),
        selected_claim_ids=list(selected.exposed_claim_ids if selected else []),
        selected_relation_ids=list(selected.exposed_relation_ids if selected else []),
        supporting_claim_ids=list(selected.exposed_claim_ids if selected else []),
        supporting_relation_ids=list(selected.exposed_relation_ids if selected else []),
        supporting_citation_event_ids=[selected.event_id] if selected else [],
        answer=_extract_rule_answer(selected.text) if selected else None,
        next_action=f"continue {selected.event_id}" if selected and checkpoint.expected_next_action else None,
        uncertain_ids=[],
        confidence=0.45,
        rationale="shallow lexical/recency reconstruction baseline",
    )


def judge_sim_checkpoint(
    *,
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
) -> JudgeAggregate:
    votes = [
        _set_judge(
            "entity_identity_judge",
            checkpoint,
            expected=checkpoint.expected_entity_ids,
            actual=output.selected_entity_ids,
            bucket="entity_alias_error",
        ),
        _set_judge(
            "entity_type_judge",
            checkpoint,
            expected=checkpoint.expected_entity_ids,
            actual=output.selected_entity_ids,
            bucket="entity_type_missing",
        ),
        _set_judge(
            "alias_resolution_judge",
            checkpoint,
            expected=checkpoint.expected_entity_ids,
            actual=output.selected_entity_ids,
            bucket="entity_alias_error",
        ),
        _selected_entity_role_judge(scenario, checkpoint, output),
        _set_judge(
            "claim_spo_judge",
            checkpoint,
            expected=checkpoint.expected_claim_ids,
            actual=output.selected_claim_ids,
            bucket=_claim_bucket(checkpoint),
        ),
        _set_judge(
            "claim_lifecycle_judge",
            checkpoint,
            expected=checkpoint.expected_claim_ids,
            actual=output.selected_claim_ids,
            bucket=_claim_bucket(checkpoint),
        ),
        _set_judge(
            "temporal_truth_judge",
            checkpoint,
            expected=checkpoint.expected_claim_ids,
            actual=output.selected_claim_ids,
            bucket="historical_truth_lost" if checkpoint.checkpoint_type == "historical_truth" else "wrong_current_truth",
        ),
        _set_judge(
            "source_trust_judge",
            checkpoint,
            expected=checkpoint.expected_claim_ids,
            actual=output.selected_claim_ids,
            bucket="source_trust_inversion",
        ),
        _set_judge(
            "modality_suppression_judge",
            checkpoint,
            expected=checkpoint.expected_claim_ids,
            actual=output.selected_claim_ids,
            bucket="modality_false_positive",
        ),
        _set_judge(
            "relation_directionality_judge",
            checkpoint,
            expected=checkpoint.expected_relation_ids,
            actual=_role_relation_ids(output),
            bucket=_relation_bucket(checkpoint),
        ),
        _set_judge(
            "support_contradiction_judge",
            checkpoint,
            expected=checkpoint.expected_relation_ids,
            actual=_role_relation_ids(output),
            bucket=_relation_bucket(checkpoint),
        ),
        _set_judge(
            "scope_judge",
            checkpoint,
            expected=checkpoint.expected_claim_ids,
            actual=output.selected_claim_ids,
            bucket="scope_leak",
        ),
        _set_judge(
            "belief_ranking_judge",
            checkpoint,
            expected=checkpoint.expected_claim_ids,
            actual=output.belief_ranking_ids if checkpoint.checkpoint_type == "belief_ranking" else output.claim_ids,
            bucket="belief_ranking_error",
        ),
        _execution_branch_judge(checkpoint, output),
        _set_judge(
            "provenance_judge",
            checkpoint,
            expected=checkpoint.expected_citation_event_ids,
            actual=output.supporting_citation_event_ids,
            bucket="missing_provenance",
        ),
        _selected_truth_precision_judge(scenario, checkpoint, output),
        _supporting_evidence_precision_judge(scenario, checkpoint, output),
        _rejection_classification_judge(scenario, checkpoint, output),
        _graph_context_judge(scenario, checkpoint, output),
        _definition_coverage_judge(scenario, checkpoint, output),
        _legacy_flattening_judge(checkpoint, output),
        _answer_judge(scenario, checkpoint, output),
        _hidden_hallucination_judge(scenario, checkpoint, output),
        _ambiguity_abstention_judge(checkpoint, output),
        _confidence_calibration_judge(checkpoint, output),
    ]
    required = set(checkpoint.required_judge_ids or _required_judge_ids_for_checkpoint(checkpoint))
    failed = [vote for vote in votes if vote.verdict == JudgeVerdict.FAIL]
    required_failed = [vote for vote in failed if vote.judge_id in required]
    required_abstained = [vote for vote in votes if vote.judge_id in required and vote.verdict == JudgeVerdict.ABSTAIN]
    optional_failed = [vote for vote in failed if vote.judge_id not in required]
    critical = sorted(
        {
            bucket
            for vote in [*required_failed, *required_abstained]
            for bucket in (vote.failure_buckets or ["judge_uncovered_case"])
        }
    )
    score = sum(vote.score for vote in votes) / len(votes)
    verdict = JudgeVerdict.FAIL if critical else JudgeVerdict.PASS
    verdict_set = {vote.verdict for vote in votes if vote.verdict != JudgeVerdict.ABSTAIN}
    review_required = bool(critical or optional_failed or len(verdict_set) > 1)
    return JudgeAggregate(
        checkpoint_id=checkpoint.checkpoint_id,
        verdict=verdict,
        score=score,
        confidence=max(0.0, min(1.0, 1.0 - len(required_failed) / max(1, len(required)))),
        votes=votes,
        required_judge_ids=sorted(required),
        critical_failure_buckets=critical,
        review_required=review_required,
        rationale="; ".join(vote.rationale for vote in [*required_failed, *required_abstained, *optional_failed]) or "required judges passed",
    )


def _required_judge_ids_for_checkpoint(checkpoint: OracleCheckpoint) -> list[str]:
    required = {
        "entity_identity_judge",
        "claim_spo_judge",
        "provenance_judge",
        "answer_judge",
        "hidden_hallucination_judge",
        "confidence_calibration_judge",
    }
    by_type = {
        "entity_reconstruction": {"entity_type_judge", "alias_resolution_judge", "relation_directionality_judge", "graph_context_judge", "definition_coverage_judge", "selected_truth_precision_judge"},
        "current_truth": {"temporal_truth_judge", "claim_lifecycle_judge", "selected_entity_role_judge", "selected_truth_precision_judge", "supporting_evidence_precision_judge"},
        "historical_truth": {"temporal_truth_judge", "claim_lifecycle_judge", "selected_entity_role_judge", "supporting_evidence_precision_judge"},
        "scoped_truth": {"scope_judge", "selected_entity_role_judge", "selected_truth_precision_judge", "supporting_evidence_precision_judge"},
        "source_trust_conflict": {"source_trust_judge", "support_contradiction_judge", "relation_directionality_judge", "selected_entity_role_judge", "selected_truth_precision_judge", "supporting_evidence_precision_judge"},
        "modality_suppression": {"modality_suppression_judge", "selected_entity_role_judge", "selected_truth_precision_judge", "supporting_evidence_precision_judge"},
        "entity_disambiguation": {"alias_resolution_judge", "selected_entity_role_judge", "selected_truth_precision_judge", "supporting_evidence_precision_judge"},
        "entity_split_repair": {"alias_resolution_judge", "graph_context_judge", "selected_entity_role_judge", "selected_truth_precision_judge", "supporting_evidence_precision_judge"},
        "claim_rekey": {"alias_resolution_judge", "claim_lifecycle_judge", "graph_context_judge", "definition_coverage_judge", "selected_entity_role_judge", "selected_truth_precision_judge"},
        "belief_ranking": {"belief_ranking_judge", "support_contradiction_judge", "selected_truth_precision_judge"},
        "execution_continuation": {"execution_branch_judge"},
        "abstention": {"ambiguity_abstention_judge"},
    }
    required.update(by_type.get(checkpoint.checkpoint_type, set()))
    if checkpoint.expected_uncertain_ids:
        required.add("ambiguity_abstention_judge")
    if checkpoint.expected_relation_ids:
        required.add("relation_directionality_judge")
    if checkpoint.expected_excluded_claim_ids or checkpoint.expected_excluded_entity_ids:
        required.add("rejection_classification_judge")
    return sorted(required)


def sim_metrics_from_rows(rows: list[dict[str, object]]) -> dict[str, float]:
    if not rows:
        return {}
    total = len(rows)
    passed = sum(1 for row in rows if row.get("success") is True)
    bucket_counts = Counter(
        bucket
        for row in rows
        for bucket in row.get("failure_buckets", [])
    )
    return {
        "checkpoint_accuracy": passed / total,
        "judge_review_required_rate": sum(1 for row in rows if row.get("review_required")) / total,
        "hidden_hallucination_rate": bucket_counts["hidden_fact_hallucinated"] / total,
        "ambiguous_overcommit_rate": bucket_counts["ambiguous_fact_overcommitted"] / total,
        "selection_precision": sum(
            1
            for row in rows
            if not row.get("selected_excluded_ids")
            and not row.get("selected_noncurrent_claim_ids")
            and not row.get("selected_entity_role_mismatches")
        )
        / total,
        "provenance_precision": sum(1 for row in rows if not row.get("supporting_noisy_citation_event_ids")) / total,
        "excluded_selection_rate": sum(1 for row in rows if row.get("selected_excluded_ids") or row.get("supporting_excluded_ids")) / total,
        "noise_provenance_rate": sum(1 for row in rows if row.get("supporting_noisy_citation_event_ids")) / total,
        "precision_review_required_rate": sum(1 for row in rows if row.get("precision_failure_classification")) / total,
    }


def _set_judge(
    judge_id: str,
    checkpoint: OracleCheckpoint,
    *,
    expected: list[str],
    actual: list[str],
    bucket: str,
) -> JudgeVote:
    if not expected:
        return JudgeVote(
            judge_id=judge_id,
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.ABSTAIN,
            score=1.0,
            confidence=0.2,
            rationale="judge uncovered for this checkpoint",
            failure_buckets=["judge_uncovered_case"],
        )
    missing = [item for item in expected if item not in actual]
    extra = [item for item in actual if item not in expected]
    if missing:
        return JudgeVote(
            judge_id=judge_id,
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.FAIL,
            score=0.0,
            confidence=0.9,
            covered_ids=[item for item in expected if item in actual],
            failed_ids=missing,
            failure_buckets=[bucket],
            rationale=f"missing expected ids: {missing}",
        )
    score = 1.0 if not extra else max(0.6, len(expected) / (len(expected) + len(extra)))
    return JudgeVote(
        judge_id=judge_id,
        checkpoint_id=checkpoint.checkpoint_id,
        verdict=JudgeVerdict.PASS,
        score=score,
        confidence=0.85,
        covered_ids=list(expected),
        failure_buckets=["extra_provenance_noise"] if judge_id == "provenance_judge" and extra else [],
        rationale="expected ids covered",
    )


def _selected_entity_role_judge(
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
) -> JudgeVote:
    policy = str(_checkpoint_contract_for_type(checkpoint.checkpoint_type).get("selected_entity_role_policy", "subject"))
    if policy == "audit_graph_entities":
        return JudgeVote(
            judge_id="selected_entity_role_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.PASS,
            score=1.0,
            confidence=0.8,
            rationale="audit graph entity role policy allows broader selected graph entities",
        )
    required_ids = _required_selected_entity_ids_for_policy(
        scenario=scenario,
        checkpoint=checkpoint,
        output=output,
        policy=policy,
    )
    if not required_ids:
        if checkpoint.expected_claim_ids:
            return JudgeVote(
                judge_id="selected_entity_role_judge",
                checkpoint_id=checkpoint.checkpoint_id,
                verdict=JudgeVerdict.FAIL,
                score=0.0,
                confidence=0.85,
                failed_ids=list(checkpoint.expected_entity_ids),
                failure_buckets=["entity_role_mismatch"],
                rationale="selected claims do not expose the entity role required by checkpoint contract",
            )
        return JudgeVote(
            judge_id="selected_entity_role_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.ABSTAIN,
            score=1.0,
            confidence=0.2,
            rationale="judge uncovered for this checkpoint",
            failure_buckets=["judge_uncovered_case"],
        )
    missing = [entity_id for entity_id in required_ids if entity_id not in output.selected_entity_ids]
    if missing:
        return JudgeVote(
            judge_id="selected_entity_role_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.FAIL,
            score=0.0,
            confidence=0.9,
            covered_ids=[entity_id for entity_id in required_ids if entity_id in output.selected_entity_ids],
            failed_ids=missing,
            failure_buckets=["entity_role_mismatch"],
            rationale=f"selected_entity_ids must include {policy} entity ids for selected claims: {missing}",
        )
    return JudgeVote(
        judge_id="selected_entity_role_judge",
        checkpoint_id=checkpoint.checkpoint_id,
        verdict=JudgeVerdict.PASS,
        score=1.0,
        confidence=0.9,
        covered_ids=required_ids,
        rationale="selected entity roles match selected claim roles",
    )


def _required_selected_entity_ids_for_policy(
    *,
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
    policy: str | None = None,
) -> list[str]:
    selected_policy = policy or str(
        _checkpoint_contract_for_type(checkpoint.checkpoint_type).get("selected_entity_role_policy", "subject")
    )
    if selected_policy == "audit_graph_entities":
        return []
    required: list[str] = []
    for claim_id in output.selected_claim_ids:
        claim = _claim_by_id(scenario, claim_id)
        if claim is None:
            continue
        if selected_policy in {"subject", "subject_and_object", "active_graph_subjects"}:
            required.append(claim.subject.entity_id)
        if selected_policy in {"object", "subject_and_object"} and claim.object.entity_id:
            required.append(claim.object.entity_id)
    return _ordered_unique(required)


def _selected_truth_precision_judge(
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
) -> JudgeVote:
    bad_claims = _selected_noncurrent_claim_ids(scenario, checkpoint, output)
    selected_excluded_claims = [item for item in checkpoint.expected_excluded_claim_ids if item in output.selected_claim_ids]
    selected_excluded_entities = [item for item in checkpoint.expected_excluded_entity_ids if item in output.selected_entity_ids]
    failed = _ordered_unique([*bad_claims, *selected_excluded_claims, *selected_excluded_entities])
    if failed:
        return JudgeVote(
            judge_id="selected_truth_precision_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.FAIL,
            score=0.0,
            confidence=0.9,
            failed_ids=failed,
            failure_buckets=["selected_truth_precision_error"],
            rationale=f"selected channel contains non-current or excluded ids: {failed}",
        )
    return JudgeVote(
        judge_id="selected_truth_precision_judge",
        checkpoint_id=checkpoint.checkpoint_id,
        verdict=JudgeVerdict.PASS,
        score=1.0,
        confidence=0.85,
        rationale="selected channel contains no excluded or non-current ids",
    )


def _supporting_evidence_precision_judge(
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
) -> JudgeVote:
    excluded_support_claims = [
        item for item in checkpoint.expected_excluded_claim_ids if item in output.supporting_claim_ids
    ]
    bad_claims = [
        item
        for item in [*output.supporting_claim_ids, *output.selected_claim_ids]
        if _claim_is_bad_support(scenario, checkpoint, item)
    ]
    bad_events = _bad_supporting_event_ids(scenario, checkpoint, output.supporting_citation_event_ids)
    failed = _ordered_unique([*excluded_support_claims, *bad_claims, *bad_events])
    if failed:
        buckets = []
        if excluded_support_claims:
            buckets.append("supporting_excluded_id")
        if bad_claims:
            buckets.append("supporting_noncurrent_claim_selected")
        if bad_events:
            buckets.append("supporting_noisy_or_stale_provenance")
        return JudgeVote(
            judge_id="supporting_evidence_precision_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.FAIL,
            score=0.0,
            confidence=0.9,
            failed_ids=failed,
            failure_buckets=buckets,
            rationale=f"supporting channel contains invalid support ids: {failed}",
        )
    return JudgeVote(
        judge_id="supporting_evidence_precision_judge",
        checkpoint_id=checkpoint.checkpoint_id,
        verdict=JudgeVerdict.PASS,
        score=1.0,
        confidence=0.85,
        rationale="supporting channel contains clean answer support",
    )


def _rejection_classification_judge(
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
) -> JudgeVote:
    expected_rejected_claims = [
        item
        for item in checkpoint.expected_excluded_claim_ids
        if _is_visible_claim(scenario, item)
    ]
    expected_rejected_entities = [
        item
        for item in checkpoint.expected_excluded_entity_ids
        if _is_visible_entity(scenario, item)
    ]
    expected_rejected_entities = _ordered_unique([
        *expected_rejected_entities,
        *_expected_rejected_claim_subject_entity_ids(scenario, checkpoint),
    ])
    selected_or_supporting = set(output.selected_claim_ids) | set(output.supporting_claim_ids) | set(output.selected_entity_ids)
    bad_selected = [item for item in [*expected_rejected_claims, *expected_rejected_entities] if item in selected_or_supporting]
    missing_rejected = [
        item
        for item in expected_rejected_claims
        if item not in output.rejected_claim_ids and item not in output.context_claim_ids
    ] + [
        item
        for item in expected_rejected_entities
        if item not in output.rejected_entity_ids and item not in output.context_entity_ids
    ]
    if bad_selected or missing_rejected:
        buckets = []
        if bad_selected:
            buckets.append("rejected_id_selected_as_truth")
        if missing_rejected:
            buckets.append("missing_rejected_id")
        return JudgeVote(
            judge_id="rejection_classification_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.FAIL,
            score=0.0,
            confidence=0.9,
            failed_ids=_ordered_unique([*bad_selected, *missing_rejected]),
            failure_buckets=buckets,
            rationale="excluded ids must be rejected/contextualized, not selected as truth",
        )
    if not expected_rejected_claims and not expected_rejected_entities:
        return JudgeVote(
            judge_id="rejection_classification_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.ABSTAIN,
            score=1.0,
            confidence=0.2,
            failure_buckets=["judge_uncovered_case"],
            rationale="no explicit rejection expectation",
        )
    return JudgeVote(
        judge_id="rejection_classification_judge",
        checkpoint_id=checkpoint.checkpoint_id,
        verdict=JudgeVerdict.PASS,
        score=1.0,
        confidence=0.85,
        covered_ids=[*expected_rejected_claims, *expected_rejected_entities],
        rationale="excluded ids were rejected or contextualized",
    )


def _expected_rejected_claim_subject_entity_ids(
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
) -> list[str]:
    expected_entities = set(checkpoint.expected_entity_ids)
    required: list[str] = []
    for claim_id in checkpoint.expected_excluded_claim_ids:
        claim = _claim_by_id(scenario, claim_id)
        if claim is None:
            continue
        subject_entity_id = claim.subject.entity_id
        if subject_entity_id in expected_entities:
            continue
        if _is_visible_entity(scenario, subject_entity_id):
            required.append(subject_entity_id)
    return _ordered_unique(required)


def _graph_context_judge(
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
) -> JudgeVote:
    if checkpoint.checkpoint_type not in {"entity_reconstruction", "entity_split_repair", "claim_rekey", "conflict_audit"}:
        return JudgeVote(
            judge_id="graph_context_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.ABSTAIN,
            score=1.0,
            confidence=0.2,
            failure_buckets=["judge_uncovered_case"],
            rationale="no graph context expectation",
        )
    invalid_selected = _selected_noncurrent_claim_ids(scenario, checkpoint, output)
    if invalid_selected:
        return JudgeVote(
            judge_id="graph_context_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.FAIL,
            score=0.0,
            confidence=0.9,
            failed_ids=invalid_selected,
            failure_buckets=["graph_context_selected_as_truth"],
            rationale="contextual graph facts were selected as current truth",
        )
    return JudgeVote(
        judge_id="graph_context_judge",
        checkpoint_id=checkpoint.checkpoint_id,
        verdict=JudgeVerdict.PASS,
        score=1.0,
        confidence=0.85,
        rationale="graph context did not pollute selected truth",
    )


def _definition_coverage_judge(
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
) -> JudgeVote:
    contract = _checkpoint_contract_for_type(checkpoint.checkpoint_type)
    if not contract.get("definition_claims_required_in_selected"):
        return JudgeVote(
            judge_id="definition_coverage_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.ABSTAIN,
            score=1.0,
            confidence=0.2,
            failure_buckets=["judge_uncovered_case"],
            rationale="definition coverage is not required for this checkpoint",
        )
    required = _required_definition_claim_ids_for_selected_claims(scenario, output)
    missing_selected = [claim_id for claim_id in required if claim_id not in output.selected_claim_ids]
    missing_supporting = [claim_id for claim_id in required if claim_id not in output.supporting_claim_ids]
    failed = _ordered_unique([*missing_selected, *missing_supporting])
    if failed:
        buckets = ["claim_rekey_error"]
        if missing_supporting:
            buckets.append("missing_provenance")
        return JudgeVote(
            judge_id="definition_coverage_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.FAIL,
            score=0.0,
            confidence=0.9,
            covered_ids=[claim_id for claim_id in required if claim_id in output.selected_claim_ids],
            failed_ids=failed,
            failure_buckets=_ordered_unique(buckets),
            rationale="selected graph role claims require selected/supporting entity definition claims",
        )
    return JudgeVote(
        judge_id="definition_coverage_judge",
        checkpoint_id=checkpoint.checkpoint_id,
        verdict=JudgeVerdict.PASS,
        score=1.0,
        confidence=0.9,
        covered_ids=required,
        rationale="selected graph role claims include subject definition coverage",
    )


def _legacy_flattening_judge(checkpoint: OracleCheckpoint, output: SimSystemOutput) -> JudgeVote:
    expected_claims = set(output.selected_claim_ids) | set(output.supporting_claim_ids) | set(output.context_claim_ids) | set(output.rejected_claim_ids)
    expected_entities = set(output.selected_entity_ids) | set(output.context_entity_ids) | set(output.rejected_entity_ids)
    expected_relations = set(output.selected_relation_ids) | set(output.supporting_relation_ids) | set(output.context_relation_ids) | set(output.rejected_relation_ids)
    expected_events = set(output.supporting_citation_event_ids) | set(output.context_citation_event_ids) | set(output.rejection_citation_event_ids)
    mismatches = []
    if not expected_claims.issubset(set(output.claim_ids)):
        mismatches.append("claim_ids")
    if not expected_entities.issubset(set(output.entity_ids)):
        mismatches.append("entity_ids")
    if not expected_relations.issubset(set(output.relation_ids)):
        mismatches.append("relation_ids")
    if not expected_events.issubset(set(output.citation_event_ids)):
        mismatches.append("citation_event_ids")
    if mismatches:
        return JudgeVote(
            judge_id="legacy_flattening_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.PASS,
            score=0.8,
            confidence=0.8,
            failed_ids=mismatches,
            failure_buckets=["legacy_flattening_mismatch"],
            rationale=f"legacy fields were normalized from role-aware views: {mismatches}",
        )
    return JudgeVote(
        judge_id="legacy_flattening_judge",
        checkpoint_id=checkpoint.checkpoint_id,
        verdict=JudgeVerdict.PASS,
        score=1.0,
        confidence=0.7,
        rationale="legacy flattened fields include role-aware views",
    )


def _execution_branch_judge(checkpoint: OracleCheckpoint, output: SimSystemOutput) -> JudgeVote:
    if checkpoint.checkpoint_type != "execution_continuation":
        return JudgeVote(
            judge_id="execution_branch_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.ABSTAIN,
            score=1.0,
            confidence=0.2,
            rationale="no execution continuation expectation",
            failure_buckets=["judge_uncovered_case"],
        )
    if output.operation != "next_action" or not output.next_action:
        return JudgeVote(
            judge_id="execution_branch_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.FAIL,
            score=0.0,
            confidence=0.9,
            failed_ids=[checkpoint.checkpoint_id],
            failure_buckets=["abandoned_branch_selected"],
            rationale="execution checkpoint requires operation=next_action and next_action",
        )
    missing_claims = [claim_id for claim_id in checkpoint.expected_claim_ids if claim_id not in output.selected_claim_ids]
    missing_support = [claim_id for claim_id in checkpoint.expected_claim_ids if claim_id not in output.supporting_claim_ids]
    missing_events = [
        event_id for event_id in checkpoint.expected_citation_event_ids if event_id not in output.supporting_citation_event_ids
    ]
    failed = _ordered_unique([*missing_claims, *missing_support, *missing_events])
    if failed:
        return JudgeVote(
            judge_id="execution_branch_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.FAIL,
            score=0.0,
            confidence=0.9,
            failed_ids=failed,
            failure_buckets=["abandoned_branch_selected"],
            rationale="execution continuation requires selected and supported active continuation state",
        )
    return JudgeVote(
        judge_id="execution_branch_judge",
        checkpoint_id=checkpoint.checkpoint_id,
        verdict=JudgeVerdict.PASS,
        score=1.0,
        confidence=0.9,
        covered_ids=[*checkpoint.expected_claim_ids, *checkpoint.expected_citation_event_ids],
        rationale="execution continuation selected and supported the active state",
    )


def _answer_judge(scenario: LatentGraphScenario, checkpoint: OracleCheckpoint, output: SimSystemOutput) -> JudgeVote:
    if not bool(_checkpoint_contract_for_type(checkpoint.checkpoint_type).get("answer_required", True)):
        return JudgeVote(
            judge_id="answer_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.PASS,
            score=1.0,
            confidence=0.7,
            failure_buckets=["graph_answer_optional_missing"] if not output.answer and checkpoint.expected_answer else [],
            rationale="answer text is diagnostic for this checkpoint; structured graph/action state is authoritative",
        )
    if checkpoint.expected_abstention:
        verdict = JudgeVerdict.PASS if output.answer in {None, "unknown"} or output.uncertain_ids else JudgeVerdict.FAIL
        return JudgeVote(
            judge_id="ambiguity_answer_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=verdict,
            score=1.0 if verdict == JudgeVerdict.PASS else 0.0,
            confidence=0.8,
            failed_ids=[] if verdict == JudgeVerdict.PASS else checkpoint.expected_uncertain_ids,
            failure_buckets=[] if verdict == JudgeVerdict.PASS else ["ambiguous_fact_overcommitted"],
            rationale="abstention expectation checked",
        )
    if checkpoint.expected_answer is None and checkpoint.expected_next_action is None:
        return JudgeVote(
            judge_id="answer_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.ABSTAIN,
            score=1.0,
            confidence=0.2,
            failure_buckets=["judge_uncovered_case"],
            rationale="no answer expectation",
        )
    expected = checkpoint.expected_answer or checkpoint.expected_next_action or ""
    if checkpoint.expected_next_action is not None:
        actual = output.next_action or ""
    else:
        actual = output.answer or ""
    passed = _answer_matches_expected(scenario, checkpoint, actual, expected)
    return JudgeVote(
        judge_id="answer_judge",
        checkpoint_id=checkpoint.checkpoint_id,
        verdict=JudgeVerdict.PASS if passed else JudgeVerdict.FAIL,
        score=1.0 if passed else 0.0,
        confidence=0.9,
        failed_ids=[] if passed else [checkpoint.checkpoint_id],
        failure_buckets=[] if passed else [_answer_bucket(checkpoint)],
        rationale="answer matched" if passed else f"answer {actual!r} did not match {expected!r}",
    )


def _answer_matches_expected(
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    actual: str,
    expected: str,
) -> bool:
    actual_norm = _norm(actual)
    expected_norm = _norm(expected)
    if expected_norm in actual_norm or actual_norm in expected_norm:
        return True
    expected_entity_ids = set(checkpoint.expected_entity_ids)
    for entity in scenario.entities:
        if entity.entity_id not in expected_entity_ids:
            continue
        names = {entity.canonical_name, *[alias.alias_text for alias in entity.aliases]}
        if any(_norm(name) and _norm(name) in actual_norm for name in names):
            return True
    return False


def sim_checkpoint_diagnostics(
    *,
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
    aggregate: JudgeAggregate,
) -> dict[str, object]:
    expected_by_type = {
        "entity_ids": checkpoint.expected_entity_ids,
        "claim_ids": checkpoint.expected_claim_ids,
        "relation_ids": checkpoint.expected_relation_ids,
        "citation_event_ids": checkpoint.expected_citation_event_ids,
    }
    actual_by_type = {
        "entity_ids": output.entity_ids,
        "claim_ids": output.claim_ids,
        "relation_ids": output.relation_ids,
        "citation_event_ids": output.citation_event_ids,
    }
    missing = {
        key: [item for item in expected if item not in actual_by_type[key]]
        for key, expected in expected_by_type.items()
        if [item for item in expected if item not in actual_by_type[key]]
    }
    extra = {
        key: [item for item in actual_by_type[key] if item not in expected_by_type[key]]
        for key in actual_by_type
        if [item for item in actual_by_type[key] if item not in expected_by_type[key]]
    }
    answer_match_type = _answer_match_type(scenario, checkpoint, output)
    classifications = _failure_classifications(
        scenario=scenario,
        checkpoint=checkpoint,
        output=output,
        aggregate=aggregate,
        missing=missing,
        answer_match_type=answer_match_type,
    )
    selected_excluded_ids = {
        "claim_ids": [item for item in checkpoint.expected_excluded_claim_ids if item in output.selected_claim_ids],
        "entity_ids": [item for item in checkpoint.expected_excluded_entity_ids if item in output.selected_entity_ids],
    }
    supporting_excluded_ids = {
        "claim_ids": [item for item in checkpoint.expected_excluded_claim_ids if item in output.supporting_claim_ids],
        "entity_ids": [item for item in checkpoint.expected_excluded_entity_ids if item in output.selected_entity_ids],
    }
    rejected_expected_ids = {
        "claim_ids": [item for item in checkpoint.expected_excluded_claim_ids if item in output.rejected_claim_ids or item in output.context_claim_ids],
        "entity_ids": [
            item
            for item in _ordered_unique([
                *checkpoint.expected_excluded_entity_ids,
                *_expected_rejected_claim_subject_entity_ids(scenario, checkpoint),
            ])
            if item in output.rejected_entity_ids or item in output.context_entity_ids
        ],
    }
    missing_rejected_ids = {
        "claim_ids": [
            item
            for item in checkpoint.expected_excluded_claim_ids
            if item not in output.rejected_claim_ids and item not in output.context_claim_ids
        ],
        "entity_ids": [
            item
            for item in _ordered_unique([
                *checkpoint.expected_excluded_entity_ids,
                *_expected_rejected_claim_subject_entity_ids(scenario, checkpoint),
            ])
            if item not in output.rejected_entity_ids and item not in output.context_entity_ids
        ],
    }
    missing_rejected_claim_subject_entity_ids = [
        item
        for item in _expected_rejected_claim_subject_entity_ids(scenario, checkpoint)
        if item not in output.rejected_entity_ids and item not in output.context_entity_ids
    ]
    supporting_wrong_entity_claim_ids = [
        item for item in checkpoint.expected_excluded_claim_ids if item in output.supporting_claim_ids
    ]
    selected_noncurrent_claim_ids = _selected_noncurrent_claim_ids(scenario, checkpoint, output)
    required_definition_claim_ids = _required_definition_claim_ids_for_selected_claims(scenario, output)
    missing_definition_claim_ids = [
        claim_id for claim_id in required_definition_claim_ids if claim_id not in output.selected_claim_ids
    ]
    missing_definition_support_claim_ids = [
        claim_id for claim_id in required_definition_claim_ids if claim_id not in output.supporting_claim_ids
    ]
    required_selected_entity_ids = _required_selected_entity_ids_for_policy(
        scenario=scenario,
        checkpoint=checkpoint,
        output=output,
    )
    missing_selected_entity_role_ids = [
        entity_id for entity_id in required_selected_entity_ids if entity_id not in output.selected_entity_ids
    ]
    selected_object_entity_instead_of_subject_ids = _selected_object_entity_instead_of_subject_ids(
        scenario=scenario,
        output=output,
        missing_subject_entity_ids=missing_selected_entity_role_ids,
    )
    selected_nonrequired_graph_entity_ids = _selected_nonrequired_graph_entity_ids(
        scenario=scenario,
        checkpoint=checkpoint,
        output=output,
        required_selected_entity_ids=required_selected_entity_ids,
    )
    selected_context_only_entity_ids = [
        entity_id for entity_id in output.selected_entity_ids if entity_id in output.context_entity_ids
    ]
    selected_rejected_or_context_entity_ids = _ordered_unique([
        *[entity_id for entity_id in output.selected_entity_ids if entity_id in output.rejected_entity_ids],
        *selected_context_only_entity_ids,
    ])
    missing_selected_subject_entity_ids = []
    if str(_checkpoint_contract_for_type(checkpoint.checkpoint_type).get("selected_entity_role_policy")) in {
        "subject",
        "subject_and_object",
        "active_graph_subjects",
    }:
        missing_selected_subject_entity_ids = missing_selected_entity_role_ids
    supporting_noisy_citation_event_ids = _bad_supporting_event_ids(
        scenario,
        checkpoint,
        output.supporting_citation_event_ids,
    )
    context_only_noise_event_ids = _context_only_noise_event_ids(scenario, output)
    precision_failure_classification = _precision_failure_classifications(
        selected_excluded_ids=selected_excluded_ids,
        supporting_excluded_ids=supporting_excluded_ids,
        missing_rejected_ids=missing_rejected_ids,
        missing_rejected_claim_subject_entity_ids=missing_rejected_claim_subject_entity_ids,
        selected_noncurrent_claim_ids=selected_noncurrent_claim_ids,
        supporting_noisy_citation_event_ids=supporting_noisy_citation_event_ids,
        selected_entity_role_mismatches=missing_selected_entity_role_ids,
    )
    return {
        "missing_expected_ids": missing,
        "extra_selected_ids": extra,
        "answer_match_type": answer_match_type,
        "failure_classification": classifications,
        "selected_excluded_ids": {key: value for key, value in selected_excluded_ids.items() if value},
        "supporting_excluded_ids": {key: value for key, value in supporting_excluded_ids.items() if value},
        "rejected_expected_ids": {key: value for key, value in rejected_expected_ids.items() if value},
        "missing_rejected_ids": {key: value for key, value in missing_rejected_ids.items() if value},
        "missing_rejected_claim_subject_entity_ids": missing_rejected_claim_subject_entity_ids,
        "supporting_wrong_entity_claim_ids": supporting_wrong_entity_claim_ids,
        "selected_noncurrent_claim_ids": selected_noncurrent_claim_ids,
        "required_definition_claim_ids": required_definition_claim_ids,
        "missing_definition_claim_ids": missing_definition_claim_ids,
        "missing_definition_support_claim_ids": missing_definition_support_claim_ids,
        "selected_entity_role_mismatches": missing_selected_entity_role_ids,
        "missing_selected_subject_entity_ids": missing_selected_subject_entity_ids,
        "selected_object_entity_instead_of_subject_ids": selected_object_entity_instead_of_subject_ids,
        "selected_graph_entity_overbreadth": selected_nonrequired_graph_entity_ids,
        "selected_nonrequired_graph_entity_ids": selected_nonrequired_graph_entity_ids,
        "selected_context_only_entity_ids": selected_context_only_entity_ids,
        "selected_rejected_or_context_entity_ids": selected_rejected_or_context_entity_ids,
        "supporting_noisy_citation_event_ids": supporting_noisy_citation_event_ids,
        "context_only_noise_event_ids": context_only_noise_event_ids,
        "role_misclassification": bool(
            selected_noncurrent_claim_ids
            or missing_selected_entity_role_ids
            or supporting_noisy_citation_event_ids
            or any(selected_excluded_ids.values())
            or any(supporting_excluded_ids.values())
        ),
        "precision_failure_classification": precision_failure_classification,
        "required_judge_ids": aggregate.required_judge_ids,
    }


def _precision_failure_classifications(
    *,
    selected_excluded_ids: dict[str, list[str]],
    supporting_excluded_ids: dict[str, list[str]],
    missing_rejected_ids: dict[str, list[str]],
    missing_rejected_claim_subject_entity_ids: list[str],
    selected_noncurrent_claim_ids: list[str],
    supporting_noisy_citation_event_ids: list[str],
    selected_entity_role_mismatches: list[str],
) -> list[str]:
    classifications: set[str] = set()
    if any(selected_excluded_ids.values()):
        classifications.add("selected_excluded_id")
    if any(supporting_excluded_ids.values()):
        classifications.add("supporting_excluded_id")
    if any(missing_rejected_ids.values()):
        classifications.add("missing_rejected_id")
    if missing_rejected_claim_subject_entity_ids:
        classifications.add("missing_rejected_claim_subject_entity")
    if selected_noncurrent_claim_ids:
        classifications.add("selected_noncurrent_claim")
    if selected_entity_role_mismatches:
        classifications.add("entity_role_mismatch")
    if supporting_noisy_citation_event_ids:
        classifications.add("supporting_noisy_or_stale_provenance")
    return sorted(classifications)


def _selected_object_entity_instead_of_subject_ids(
    *,
    scenario: LatentGraphScenario,
    output: SimSystemOutput,
    missing_subject_entity_ids: list[str],
) -> list[str]:
    if not missing_subject_entity_ids:
        return []
    object_ids: list[str] = []
    for claim_id in output.selected_claim_ids:
        claim = _claim_by_id(scenario, claim_id)
        if claim is None or claim.object.entity_id is None:
            continue
        if claim.subject.entity_id in missing_subject_entity_ids and claim.object.entity_id in output.selected_entity_ids:
            object_ids.append(claim.object.entity_id)
    return _ordered_unique(object_ids)


def _selected_nonrequired_graph_entity_ids(
    *,
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
    required_selected_entity_ids: list[str],
) -> list[str]:
    policy = str(_checkpoint_contract_for_type(checkpoint.checkpoint_type).get("selected_entity_role_policy"))
    if policy != "active_graph_subjects":
        return []
    required = set(required_selected_entity_ids)
    return [
        entity_id
        for entity_id in output.selected_entity_ids
        if entity_id not in required and _is_visible_entity(scenario, entity_id)
    ]


def _answer_match_type(
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
) -> str:
    if not bool(_checkpoint_contract_for_type(checkpoint.checkpoint_type).get("answer_required", True)):
        expected = checkpoint.expected_next_action if checkpoint.expected_next_action is not None else checkpoint.expected_answer
        actual = output.next_action if checkpoint.expected_next_action is not None else output.answer
        if expected and not actual:
            return "optional_missing"
        return "diagnostic_only"
    expected = checkpoint.expected_next_action if checkpoint.expected_next_action is not None else checkpoint.expected_answer
    if expected is None:
        return "not_applicable"
    actual = output.next_action if checkpoint.expected_next_action is not None else output.answer
    if not actual:
        return "missing"
    actual_norm = _norm(actual)
    expected_norm = _norm(expected)
    if actual_norm == expected_norm:
        return "exact"
    if expected_norm in actual_norm or actual_norm in expected_norm:
        return "substring"
    expected_entity_ids = set(checkpoint.expected_entity_ids)
    for entity in scenario.entities:
        if entity.entity_id not in expected_entity_ids:
            continue
        names = {entity.canonical_name, *[alias.alias_text for alias in entity.aliases]}
        if any(_norm(name) and _norm(name) in actual_norm for name in names):
            return "semantic_entity"
    return "mismatch"


def _failure_classifications(
    *,
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
    aggregate: JudgeAggregate,
    missing: dict[str, list[str]],
    answer_match_type: str,
) -> list[str]:
    if aggregate.verdict == JudgeVerdict.PASS:
        return []
    classifications: set[str] = set()
    if sim_output_allowed_id_errors(scenario=scenario, output=output):
        classifications.add("hidden_or_expected_leakage")
    if checkpoint.checkpoint_type == "execution_continuation" and (
        output.operation != "next_action" or not output.next_action
    ):
        classifications.add("wrong_output_shape")
    if missing.get("relation_ids"):
        visible_relations = {item for obs in scenario.observations for item in obs.exposed_relation_ids}
        if checkpoint.checkpoint_type == "source_trust_conflict":
            classifications.add("missing_conflict_relation")
        if all(item in visible_relations for item in missing["relation_ids"]):
            classifications.add("missing_visible_relation")
        else:
            classifications.add("relation_context_under_specified")
    if answer_match_type in {"mismatch", "missing"}:
        classifications.add("model_wrong_fact")
    if answer_match_type == "optional_missing":
        classifications.add("graph_answer_optional_missing")
    if answer_match_type == "semantic_entity":
        classifications.add("judge_brittle_answer_match")
    if any("entity_role_mismatch" in vote.failure_buckets for vote in aggregate.votes):
        classifications.add("entity_role_mismatch")
        required_entity_ids = _required_selected_entity_ids_for_policy(
            scenario=scenario,
            checkpoint=checkpoint,
            output=output,
        )
        missing_entity_ids = [
            entity_id for entity_id in required_entity_ids if entity_id not in output.selected_entity_ids
        ]
        if _selected_object_entity_instead_of_subject_ids(
            scenario=scenario,
            output=output,
            missing_subject_entity_ids=missing_entity_ids,
        ):
            classifications.add("object_subject_confusion")
    if checkpoint.checkpoint_type == "claim_rekey":
        if any("claim_rekey_error" in vote.failure_buckets for vote in aggregate.votes):
            classifications.add("missing_required_defining_claim")
        if any("missing_provenance" in vote.failure_buckets for vote in aggregate.votes):
            classifications.add("missing_required_defining_provenance")
    if any("supporting_excluded_id" in vote.failure_buckets for vote in aggregate.votes):
        classifications.add("wrong_entity_support_used")
    if any("supporting_noncurrent_claim_selected" in vote.failure_buckets for vote in aggregate.votes):
        classifications.add("wrong_entity_support_used")
    if checkpoint.checkpoint_type == "execution_continuation" and answer_match_type in {
        "diagnostic_only",
        "optional_missing",
    }:
        classifications.add("execution_text_mismatch_only")
    if any(
        vote.judge_id == "definition_coverage_judge" and vote.verdict == JudgeVerdict.FAIL
        for vote in aggregate.votes
    ):
        classifications.add("missing_definition_claim")
    for item in [*output.entity_ids, *output.claim_ids, *output.relation_ids]:
        if re.search(r"_(alice|bob|carol)(_|$)", item):
            classifications.add("fixture_name_id_mismatch")
    if not classifications:
        classifications.add("unclassified_failure")
    return sorted(classifications)


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


def _hidden_hallucination_judge(
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
) -> JudgeVote:
    hidden_ids = {
        item.entity_id for item in scenario.entities if item.observability == ObservabilityLabel.HIDDEN
    } | {
        item.claim_id for item in scenario.claims if item.observability == ObservabilityLabel.HIDDEN
    } | {
        item.relation_id for item in scenario.relations if item.observability == ObservabilityLabel.HIDDEN
    }
    asserted = (
        set(output.entity_ids)
        | set(output.selected_entity_ids)
        | set(output.rejected_entity_ids)
        | set(output.context_entity_ids)
        | set(output.claim_ids)
        | set(output.selected_claim_ids)
        | set(output.supporting_claim_ids)
        | set(output.rejected_claim_ids)
        | set(output.context_claim_ids)
        | set(output.relation_ids)
        | set(output.selected_relation_ids)
        | set(output.supporting_relation_ids)
        | set(output.rejected_relation_ids)
        | set(output.context_relation_ids)
    )
    hallucinated = sorted(asserted & hidden_ids)
    answer_leaks = _hidden_answer_leaks(scenario, output)
    failed = [*hallucinated, *answer_leaks]
    buckets = []
    if hallucinated:
        buckets.append("hidden_fact_hallucinated")
    if answer_leaks:
        buckets.append("hidden_fact_answer_leak")
    return JudgeVote(
        judge_id="hidden_hallucination_judge",
        checkpoint_id=checkpoint.checkpoint_id,
        verdict=JudgeVerdict.FAIL if failed else JudgeVerdict.PASS,
        score=0.0 if failed else 1.0,
        confidence=0.9,
        failed_ids=failed,
        failure_buckets=buckets,
        rationale="hidden facts asserted" if failed else "no hidden facts asserted",
    )


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


def _ambiguity_abstention_judge(checkpoint: OracleCheckpoint, output: SimSystemOutput) -> JudgeVote:
    if not checkpoint.expected_uncertain_ids:
        return JudgeVote(
            judge_id="ambiguity_abstention_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.ABSTAIN,
            score=1.0,
            confidence=0.2,
            failure_buckets=["judge_uncovered_case"],
            rationale="no ambiguity expectation",
        )
    overcommitted = [
        item for item in checkpoint.expected_uncertain_ids
        if item in output.entity_ids or item in output.claim_ids or item in output.relation_ids
    ]
    if output.confidence >= 0.75 and overcommitted:
        return JudgeVote(
            judge_id="ambiguity_abstention_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.FAIL,
            score=0.0,
            confidence=0.85,
            failed_ids=overcommitted,
            failure_buckets=["ambiguous_fact_overcommitted"],
            rationale="high-confidence assertion of ambiguous ids",
        )
    return JudgeVote(
        judge_id="ambiguity_abstention_judge",
        checkpoint_id=checkpoint.checkpoint_id,
        verdict=JudgeVerdict.PASS,
        score=1.0,
        confidence=0.75,
        covered_ids=checkpoint.expected_uncertain_ids,
        rationale="ambiguous ids were not overcommitted",
    )


def _confidence_calibration_judge(checkpoint: OracleCheckpoint, output: SimSystemOutput) -> JudgeVote:
    if checkpoint.expected_abstention and output.confidence > 0.55:
        return JudgeVote(
            judge_id="confidence_calibration_judge",
            checkpoint_id=checkpoint.checkpoint_id,
            verdict=JudgeVerdict.FAIL,
            score=0.0,
            confidence=0.8,
            failure_buckets=["overconfident_wrong_answer"],
            rationale="abstention checkpoint returned high confidence",
        )
    return JudgeVote(
        judge_id="confidence_calibration_judge",
        checkpoint_id=checkpoint.checkpoint_id,
        verdict=JudgeVerdict.PASS,
        score=1.0,
        confidence=0.7,
        rationale="confidence is within expected range",
    )


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
