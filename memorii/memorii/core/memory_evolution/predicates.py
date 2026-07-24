"""Predicate policy registry for memory evolution."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from memorii.core.memory_evolution.models import (
    ClaimValueType,
    PredicateCardinality,
    PredicateConflictPolicy,
    PredicateMergePolicy,
    PredicateTemporalPolicy,
    SourceModality,
)
from memorii.domain.enums import MemoryScope, SourceType


class LifecyclePrecedencePolicy(StrEnum):
    """Semantic arbitration order for a predicate's current value."""

    RECENCY_THEN_AUTHORITY = "recency_then_authority"
    AUTHORITY_THEN_RECENCY = "authority_then_recency"


class PredicatePolicy(BaseModel):
    predicate_id: str
    description: str
    value_type: ClaimValueType
    cardinality: PredicateCardinality
    conflict_policy: PredicateConflictPolicy
    merge_policy: PredicateMergePolicy
    default_scope: MemoryScope
    temporal_policy: PredicateTemporalPolicy
    trust_precedence: list[SourceType]
    modality_precedence: list[SourceModality]
    lifecycle_precedence: LifecyclePrecedencePolicy

    model_config = ConfigDict(extra="forbid")

    @property
    def is_single_value(self) -> bool:
        return self.cardinality == PredicateCardinality.SINGLE


class PredicateRegistry:
    def __init__(self, policies: list[PredicatePolicy] | None = None) -> None:
        self._policies = {policy.predicate_id: policy for policy in (policies or default_predicate_policies())}

    def require(self, predicate_id: str) -> PredicatePolicy:
        policy = self._policies.get(predicate_id)
        if policy is None:
            raise KeyError(f"unknown predicate policy: {predicate_id}")
        return policy

    def get(self, predicate_id: str) -> PredicatePolicy | None:
        return self._policies.get(predicate_id)

    def all(self) -> list[PredicatePolicy]:
        return list(self._policies.values())


def default_predicate_policies() -> list[PredicatePolicy]:
    strong_sources = [
        SourceType.USER,
        SourceType.TOOL,
        SourceType.ENVIRONMENT,
        SourceType.DERIVED,
        SourceType.AGENT,
        SourceType.SYSTEM,
    ]
    strong_modalities = [
        SourceModality.CORRECTION,
        SourceModality.TOOL_RESULT,
        SourceModality.ASSERTION,
        SourceModality.THIRD_PARTY_CLAIM,
        SourceModality.ASSISTANT_CLAIM,
        SourceModality.QUOTED_OR_PASTED,
        SourceModality.INSTRUCTION,
        SourceModality.HYPOTHETICAL,
        SourceModality.QUESTION,
        SourceModality.NOISE,
    ]
    recency_first = LifecyclePrecedencePolicy.RECENCY_THEN_AUTHORITY
    authority_first = LifecyclePrecedencePolicy.AUTHORITY_THEN_RECENCY
    return [
        PredicatePolicy(
            predicate_id="owner",
            description="The owner or directly responsible party for an entity.",
            value_type=ClaimValueType.TEXT,
            cardinality=PredicateCardinality.SINGLE,
            conflict_policy=PredicateConflictPolicy.SUPERSEDE_BY_TRUST_AND_TIME,
            merge_policy=PredicateMergePolicy.REINFORCE_SAME_VALUE,
            default_scope=MemoryScope.TASK,
            temporal_policy=PredicateTemporalPolicy.CURRENT_VALUE,
            trust_precedence=strong_sources,
            modality_precedence=strong_modalities,
            lifecycle_precedence=recency_first,
        ),
        PredicatePolicy(
            predicate_id="approver",
            description="An approver or reviewer role for an entity.",
            value_type=ClaimValueType.TEXT,
            cardinality=PredicateCardinality.SINGLE,
            conflict_policy=PredicateConflictPolicy.SUPERSEDE_BY_TRUST_AND_TIME,
            merge_policy=PredicateMergePolicy.REINFORCE_SAME_VALUE,
            default_scope=MemoryScope.TASK,
            temporal_policy=PredicateTemporalPolicy.CURRENT_VALUE,
            trust_precedence=strong_sources,
            modality_precedence=strong_modalities,
            lifecycle_precedence=recency_first,
        ),
        PredicatePolicy(
            predicate_id="api_owner",
            description="The owner of an API surface.",
            value_type=ClaimValueType.TEXT,
            cardinality=PredicateCardinality.SINGLE,
            conflict_policy=PredicateConflictPolicy.SUPERSEDE_BY_TRUST_AND_TIME,
            merge_policy=PredicateMergePolicy.REINFORCE_SAME_VALUE,
            default_scope=MemoryScope.TASK,
            temporal_policy=PredicateTemporalPolicy.CURRENT_VALUE,
            trust_precedence=strong_sources,
            modality_precedence=strong_modalities,
            lifecycle_precedence=recency_first,
        ),
        PredicatePolicy(
            predicate_id="status",
            description="Current status or state for an entity.",
            value_type=ClaimValueType.TEXT,
            cardinality=PredicateCardinality.SINGLE,
            conflict_policy=PredicateConflictPolicy.SUPERSEDE_BY_TRUST_AND_TIME,
            merge_policy=PredicateMergePolicy.REINFORCE_SAME_VALUE,
            default_scope=MemoryScope.TASK,
            temporal_policy=PredicateTemporalPolicy.CURRENT_VALUE,
            trust_precedence=strong_sources,
            modality_precedence=strong_modalities,
            lifecycle_precedence=authority_first,
        ),
        PredicatePolicy(
            predicate_id="preference",
            description="A user preference, optionally scoped to a task or project.",
            value_type=ClaimValueType.TEXT,
            cardinality=PredicateCardinality.MULTI,
            conflict_policy=PredicateConflictPolicy.ACCUMULATE,
            merge_policy=PredicateMergePolicy.MERGE_UNIQUE_VALUES,
            default_scope=MemoryScope.USER,
            temporal_policy=PredicateTemporalPolicy.CURRENT_VALUE,
            trust_precedence=[SourceType.USER, SourceType.DERIVED, SourceType.AGENT, SourceType.SYSTEM],
            modality_precedence=strong_modalities,
            lifecycle_precedence=authority_first,
        ),
        PredicatePolicy(
            predicate_id="dependency",
            description="A dependency or support relationship between facts/actions.",
            value_type=ClaimValueType.TEXT,
            cardinality=PredicateCardinality.MULTI,
            conflict_policy=PredicateConflictPolicy.ACCUMULATE,
            merge_policy=PredicateMergePolicy.MERGE_UNIQUE_VALUES,
            default_scope=MemoryScope.TASK,
            temporal_policy=PredicateTemporalPolicy.HISTORICAL_EVENT,
            trust_precedence=strong_sources,
            modality_precedence=strong_modalities,
            lifecycle_precedence=recency_first,
        ),
        PredicatePolicy(
            predicate_id="action_state",
            description="Execution state for an action or work item.",
            value_type=ClaimValueType.TEXT,
            cardinality=PredicateCardinality.SINGLE,
            conflict_policy=PredicateConflictPolicy.SUPERSEDE_BY_TRUST_AND_TIME,
            merge_policy=PredicateMergePolicy.REINFORCE_SAME_VALUE,
            default_scope=MemoryScope.TASK,
            temporal_policy=PredicateTemporalPolicy.CURRENT_VALUE,
            trust_precedence=strong_sources,
            modality_precedence=strong_modalities,
            lifecycle_precedence=authority_first,
        ),
        PredicatePolicy(
            predicate_id="belief",
            description="A hypothesis, belief, or candidate explanation.",
            value_type=ClaimValueType.TEXT,
            cardinality=PredicateCardinality.MULTI,
            conflict_policy=PredicateConflictPolicy.CONTRADICT,
            merge_policy=PredicateMergePolicy.MERGE_UNIQUE_VALUES,
            default_scope=MemoryScope.TASK,
            temporal_policy=PredicateTemporalPolicy.CURRENT_VALUE,
            trust_precedence=strong_sources,
            modality_precedence=strong_modalities,
            lifecycle_precedence=authority_first,
        ),
        PredicatePolicy(
            predicate_id="correction",
            description="A correction or contradiction of prior memory.",
            value_type=ClaimValueType.TEXT,
            cardinality=PredicateCardinality.MULTI,
            conflict_policy=PredicateConflictPolicy.CONTRADICT,
            merge_policy=PredicateMergePolicy.NO_MERGE,
            default_scope=MemoryScope.TASK,
            temporal_policy=PredicateTemporalPolicy.HISTORICAL_EVENT,
            trust_precedence=[SourceType.USER, SourceType.TOOL, SourceType.ENVIRONMENT, SourceType.DERIVED],
            modality_precedence=strong_modalities,
            lifecycle_precedence=authority_first,
        ),
        PredicatePolicy(
            predicate_id="entity_type",
            description="The semantic type of an entity, such as project, service, or person.",
            value_type=ClaimValueType.TEXT,
            cardinality=PredicateCardinality.SINGLE,
            conflict_policy=PredicateConflictPolicy.SUPERSEDE_BY_TRUST_AND_TIME,
            merge_policy=PredicateMergePolicy.REINFORCE_SAME_VALUE,
            default_scope=MemoryScope.GLOBAL,
            temporal_policy=PredicateTemporalPolicy.CURRENT_VALUE,
            trust_precedence=strong_sources,
            modality_precedence=strong_modalities,
            lifecycle_precedence=authority_first,
        ),
        PredicatePolicy(
            predicate_id="semantic_fact",
            description="A generic source-grounded factual relationship.",
            value_type=ClaimValueType.TEXT,
            cardinality=PredicateCardinality.MULTI,
            conflict_policy=PredicateConflictPolicy.ACCUMULATE,
            merge_policy=PredicateMergePolicy.MERGE_UNIQUE_VALUES,
            default_scope=MemoryScope.TASK,
            temporal_policy=PredicateTemporalPolicy.HISTORICAL_EVENT,
            trust_precedence=strong_sources,
            modality_precedence=strong_modalities,
            lifecycle_precedence=recency_first,
        ),
    ]


def source_trust_rank(policy: PredicatePolicy, source_type: SourceType) -> int:
    try:
        return len(policy.trust_precedence) - policy.trust_precedence.index(source_type)
    except ValueError:
        return 0


def modality_trust_rank(policy: PredicatePolicy, modality: SourceModality) -> int:
    try:
        return len(policy.modality_precedence) - policy.modality_precedence.index(modality)
    except ValueError:
        return 0
