"""Benchmark-only memory evolution decision models and deterministic providers."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from enum import Enum
from typing import TypeVar
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from memorii.core.llm_decision.models import (
    LLMDecisionMode,
    LLMDecisionPoint,
    LLMDecisionStatus,
    LLMDecisionTrace,
)
from memorii.core.llm_provider.models import (
    LLMDecisionResult,
    LLMStructuredRequest,
    LLMStructuredResponse,
)
from memorii.core.llm_trace.builder import build_llm_decision_trace_from_result


BucketT = TypeVar("BucketT", bound=str)


class MemoryEvolutionSourceType(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    VERIFIED_OBSERVATION = "verified_observation"
    TRANSCRIPT = "transcript"


class MemoryEvolutionEvent(BaseModel):
    event_id: str
    timestamp: datetime
    source_type: MemoryEvolutionSourceType
    content: str
    entity_ids: list[str] = Field(default_factory=list)
    task_id: str | None = None
    scope: str | None = None
    trust_level: int = Field(default=1, ge=0, le=5)

    model_config = ConfigDict(extra="forbid")


class MemoryEvolutionBeliefScore(BaseModel):
    memory_id: str
    belief: float = Field(ge=0.0, le=1.0)

    model_config = ConfigDict(extra="forbid")


class MemoryEvolutionCheckpoint(BaseModel):
    checkpoint_id: str
    timestamp: datetime
    query_or_task: str
    expected_answer: str | None = None
    expected_next_action: str | None = None
    expected_retrieval_ids: list[str] = Field(default_factory=list)
    expected_citation_ids: list[str] = Field(default_factory=list)
    expected_excluded_memory_ids: list[str] = Field(default_factory=list)
    expected_active_memory_ids: list[str] = Field(default_factory=list)
    expected_inactive_memory_ids: list[str] = Field(default_factory=list)
    expected_archived_memory_ids: list[str] = Field(default_factory=list)
    expected_belief_ranking: list[str] = Field(default_factory=list)
    expected_belief_scores: dict[str, float] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class MemoryEvolutionVisibleCheckpoint(BaseModel):
    checkpoint_id: str
    timestamp: datetime
    query_or_task: str

    model_config = ConfigDict(extra="forbid")


class MemoryEvolutionMemoryKind(str, Enum):
    FACT = "fact"
    BELIEF = "belief"
    EVIDENCE = "evidence"
    ACTION = "action"
    UNKNOWN = "unknown"


class MemoryEvolutionEvidenceEffectBasis(str, Enum):
    SURFACE_TEXT_PATTERN = "surface_text_pattern"


class MemoryEvolutionVisibleMemoryCard(BaseModel):
    memory_id: str
    memory_kind: MemoryEvolutionMemoryKind
    statement: str
    timestamp: datetime
    source_type: MemoryEvolutionSourceType
    trust_level: int = Field(ge=0, le=5)
    entity_ids: list[str] = Field(default_factory=list)
    task_id: str | None = None
    scope: str | None = None

    model_config = ConfigDict(extra="forbid")


class MemoryEvolutionEvidenceEffectCard(BaseModel):
    evidence_memory_id: str
    supports_memory_ids: list[str] = Field(default_factory=list)
    weakens_memory_ids: list[str] = Field(default_factory=list)
    falsifies_memory_ids: list[str] = Field(default_factory=list)
    dependency_memory_ids: list[str] = Field(default_factory=list)
    extraction_basis: MemoryEvolutionEvidenceEffectBasis = MemoryEvolutionEvidenceEffectBasis.SURFACE_TEXT_PATTERN

    model_config = ConfigDict(extra="forbid")


class MemoryEvolutionCheckpointKind(str, Enum):
    CURRENT_TRUTH = "current_truth"
    HISTORICAL_TRUTH = "historical_truth"
    BELIEF_RANKING = "belief_ranking"
    BELIEF_DEGRADATION = "belief_degradation"
    EXECUTION_CONTINUATION = "execution_continuation"


class MemoryEvolutionCitationPolicy(str, Enum):
    DIRECT_ONLY = "direct_only"
    DIRECT_WITH_CONTEXT_WARNING = "direct_with_context_warning"


class MemoryEvolutionLifecyclePolicy(str, Enum):
    EXACT = "exact"
    WARNING = "warning"


class MemoryEvolutionBeliefScorePolicy(str, Enum):
    NONE = "none"
    RANKING_ONLY = "ranking_only"
    DEGRADED_THRESHOLD = "degraded_threshold"
    EXACT = "exact"


class MemoryEvolutionNextActionPolicy(str, Enum):
    NONE = "none"
    NONEMPTY_STRUCTURED = "nonempty_structured"


class MemoryEvolutionCheckpointContract(BaseModel):
    checkpoint_kind: MemoryEvolutionCheckpointKind
    citation_policy: MemoryEvolutionCitationPolicy = MemoryEvolutionCitationPolicy.DIRECT_ONLY
    lifecycle_policy: MemoryEvolutionLifecyclePolicy = MemoryEvolutionLifecyclePolicy.EXACT
    belief_score_policy: MemoryEvolutionBeliefScorePolicy = MemoryEvolutionBeliefScorePolicy.NONE
    next_action_policy: MemoryEvolutionNextActionPolicy = MemoryEvolutionNextActionPolicy.NONE

    model_config = ConfigDict(extra="forbid")


class MemoryEvolutionScenario(BaseModel):
    scenario_id: str
    family: str
    events: list[MemoryEvolutionEvent]
    checkpoints: list[MemoryEvolutionCheckpoint]
    discriminative: bool = False

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_references(self) -> "MemoryEvolutionScenario":
        event_ids = {event.event_id for event in self.events}
        if len(self.events) < 2:
            raise ValueError("memory evolution scenarios require at least two events")
        if not self.checkpoints:
            raise ValueError("memory evolution scenarios require at least one checkpoint")
        for checkpoint in self.checkpoints:
            referenced = [
                *checkpoint.expected_retrieval_ids,
                *checkpoint.expected_citation_ids,
                *checkpoint.expected_excluded_memory_ids,
                *checkpoint.expected_active_memory_ids,
                *checkpoint.expected_inactive_memory_ids,
                *checkpoint.expected_archived_memory_ids,
                *checkpoint.expected_belief_ranking,
                *checkpoint.expected_belief_scores.keys(),
            ]
            missing = sorted({item for item in referenced if item not in event_ids})
            if missing:
                raise ValueError(
                    f"checkpoint {checkpoint.checkpoint_id} references unknown event ids: {missing}"
                )
        return self


class MemoryEvolutionDecisionContext(BaseModel):
    scenario_id: str
    family: str
    events: list[MemoryEvolutionEvent]
    checkpoint: MemoryEvolutionVisibleCheckpoint
    visible_memory_cards: list[MemoryEvolutionVisibleMemoryCard] = Field(default_factory=list)
    evidence_effect_cards: list[MemoryEvolutionEvidenceEffectCard] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class MemoryEvolutionDecision(BaseModel):
    selected_memory_ids: list[str] = Field(default_factory=list)
    answer: str | None = None
    next_action: str | None = None
    citation_memory_ids: list[str] = Field(default_factory=list)
    supporting_memory_ids: list[str] = Field(default_factory=list)
    context_memory_ids: list[str] = Field(default_factory=list)
    rejected_memory_ids: list[str] = Field(default_factory=list)
    evaluated_belief_ids: list[str] = Field(default_factory=list)
    context_citation_memory_ids: list[str] = Field(default_factory=list)
    active_memory_ids: list[str] = Field(default_factory=list)
    inactive_memory_ids: list[str] = Field(default_factory=list)
    archived_memory_ids: list[str] = Field(default_factory=list)
    belief_scores: list[MemoryEvolutionBeliefScore] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    failure_mode: str | None = None
    requires_judge_review: bool = False

    model_config = ConfigDict(extra="forbid")


class MemoryEvolutionFailureBucket(str, Enum):
    SCHEMA_VALIDATION_FAILED = "schema_validation_failed"
    ANSWER_MISMATCH = "answer_mismatch"
    NEXT_ACTION_MISMATCH = "next_action_mismatch"
    SELECTED_MEMORY_MISMATCH = "selected_memory_mismatch"
    EXPECTED_RETRIEVAL_MISSING = "expected_retrieval_missing"
    EXCLUDED_MEMORY_SELECTED = "excluded_memory_selected"
    EXPECTED_CITATION_MISSING = "expected_citation_missing"
    CITATION_CHANNEL_POLLUTION = "citation_channel_pollution"
    BELIEF_ID_USED_AS_CITATION = "belief_id_used_as_citation"
    EXPECTED_ACTIVE_MEMORY_MISSING = "expected_active_memory_missing"
    INACTIVE_MEMORY_MARKED_ACTIVE = "inactive_memory_marked_active"
    EXPECTED_ARCHIVED_MEMORY_MISSING = "expected_archived_memory_missing"
    BELIEF_RANKING_MISSING_SCORE = "belief_ranking_missing_score"
    BELIEF_RANKING_WRONG_ORDER = "belief_ranking_wrong_order"
    WEAKENED_BELIEF_RANKED_ABOVE_NEUTRAL = "weakened_belief_ranked_above_neutral"
    BELIEF_SCORE_MISMATCH = "belief_score_mismatch"
    BELIEF_CONFIDENCE_NOT_DEGRADED = "belief_confidence_not_degraded"


class MemoryEvolutionWarningBucket(str, Enum):
    ACTIVE_CHANNEL_POLLUTION = "active_channel_pollution"
    BELIEF_CANDIDATE_MARKED_ACTIVE = "belief_candidate_marked_active"
    BELIEF_SCORE_CALIBRATION_DRIFT = "belief_score_calibration_drift"
    LIFECYCLE_CHANNEL_DRIFT = "lifecycle_channel_drift"
    CONTEXT_CITATION_IN_DIRECT_CHANNEL = "context_citation_in_direct_channel"
    EXTRA_ACTIVE_MEMORY_IDS = "extra_active_memory_ids"
    EXTRA_SELECTED_EVALUATED_BELIEF_IDS = "extra_selected_evaluated_belief_ids"
    BELIEF_SCORES_ON_NON_BELIEF_CHECKPOINT = "belief_scores_on_non_belief_checkpoint"


class MemoryEvolutionDecisionDiagnostics(BaseModel):
    assertion_passed: bool
    failure_buckets: list[MemoryEvolutionFailureBucket] = Field(default_factory=list)
    warning_buckets: list[MemoryEvolutionWarningBucket] = Field(default_factory=list)
    missing_retrieval_ids: list[str] = Field(default_factory=list)
    extra_selected_ids: list[str] = Field(default_factory=list)
    missing_citation_ids: list[str] = Field(default_factory=list)
    extra_citation_ids: list[str] = Field(default_factory=list)
    belief_ids_used_as_citations: list[str] = Field(default_factory=list)
    belief_ids_marked_active: list[str] = Field(default_factory=list)
    evaluated_belief_ids: list[str] = Field(default_factory=list)
    extra_active_ids: list[str] = Field(default_factory=list)
    lifecycle_drift_ids: list[str] = Field(default_factory=list)
    expected_belief_ranking: list[str] = Field(default_factory=list)
    actual_belief_ranking: list[str] = Field(default_factory=list)
    score_mismatch_ids: list[str] = Field(default_factory=list)
    belief_effect_order_errors: list[str] = Field(default_factory=list)
    rationale: str

    model_config = ConfigDict(extra="forbid")


def memory_evolution_context_for_checkpoint(
    *,
    scenario: MemoryEvolutionScenario,
    checkpoint: MemoryEvolutionCheckpoint,
) -> MemoryEvolutionDecisionContext:
    contract = memory_evolution_checkpoint_contract(scenario=scenario, checkpoint=checkpoint)
    visible_events = _visible_events_for_checkpoint(scenario=scenario, checkpoint=checkpoint)
    visible_memory_cards = _visible_memory_cards_for_events(visible_events)
    evidence_effect_cards = _evidence_effect_cards_for_events(visible_events)
    metadata: dict[str, object] = {
        "discriminative": scenario.discriminative,
        "checkpoint_contract": contract.model_dump(mode="json"),
        "output_channel_contract": _output_channel_contract(contract),
        "evidence_effect_policy": _evidence_effect_policy(contract),
    }
    return MemoryEvolutionDecisionContext(
        scenario_id=scenario.scenario_id,
        family=scenario.family,
        events=visible_events,
        checkpoint=MemoryEvolutionVisibleCheckpoint(
            checkpoint_id=checkpoint.checkpoint_id,
            timestamp=checkpoint.timestamp,
            query_or_task=checkpoint.query_or_task,
        ),
        visible_memory_cards=visible_memory_cards,
        evidence_effect_cards=evidence_effect_cards,
        metadata=metadata,
    )


def expected_memory_evolution_decision_for_checkpoint(
    *,
    scenario: MemoryEvolutionScenario,
    checkpoint: MemoryEvolutionCheckpoint,
) -> MemoryEvolutionDecision:
    del scenario
    return MemoryEvolutionDecision(
        selected_memory_ids=list(checkpoint.expected_retrieval_ids),
        answer=checkpoint.expected_answer,
        next_action=checkpoint.expected_next_action,
        citation_memory_ids=list(checkpoint.expected_citation_ids),
        supporting_memory_ids=list(checkpoint.expected_retrieval_ids),
        rejected_memory_ids=list(checkpoint.expected_inactive_memory_ids),
        evaluated_belief_ids=_expected_belief_ids(checkpoint),
        active_memory_ids=list(checkpoint.expected_active_memory_ids),
        inactive_memory_ids=list(checkpoint.expected_inactive_memory_ids),
        archived_memory_ids=list(checkpoint.expected_archived_memory_ids),
        belief_scores=[
            MemoryEvolutionBeliefScore(memory_id=memory_id, belief=belief)
            for memory_id, belief in checkpoint.expected_belief_scores.items()
        ]
        or [
            MemoryEvolutionBeliefScore(memory_id=memory_id, belief=max(0.0, 1.0 - index * 0.2))
            for index, memory_id in enumerate(checkpoint.expected_belief_ranking)
        ],
        confidence=0.9,
        rationale="expected benchmark memory evolution decision",
        failure_mode=None,
        requires_judge_review=False,
    )


def rule_memory_evolution_decision_for_checkpoint(
    *,
    scenario: MemoryEvolutionScenario,
    checkpoint: MemoryEvolutionCheckpoint,
) -> MemoryEvolutionDecision:
    ranked = _rank_events_by_shallow_overlap(scenario=scenario, checkpoint=checkpoint)
    selected = [ranked[0].event_id] if ranked else []
    selected_event = ranked[0] if ranked else None
    eligible_events = [event for event in scenario.events if event.timestamp <= checkpoint.timestamp]
    latest_event = max(eligible_events, key=lambda event: event.timestamp, default=None)
    active_ids = [latest_event.event_id] if latest_event is not None else []
    archived_ids = (
        [event.event_id for event in eligible_events if latest_event is not None and event.event_id != latest_event.event_id]
        if latest_event is not None and "archived" in latest_event.content.lower()
        else []
    )
    answer = _extract_shallow_answer(selected_event.content) if selected_event is not None else None
    next_action = f"continue {selected[0]}" if selected else None
    belief_scores = [
        MemoryEvolutionBeliefScore(memory_id=event.event_id, belief=0.5)
        for event in ranked[:3]
    ]
    return MemoryEvolutionDecision(
        selected_memory_ids=selected,
        answer=answer,
        next_action=next_action,
        citation_memory_ids=selected,
        supporting_memory_ids=selected,
        active_memory_ids=active_ids,
        inactive_memory_ids=[],
        archived_memory_ids=archived_ids,
        belief_scores=belief_scores,
        confidence=0.45,
        rationale=(
            "rule memory evolution provider uses shallow token overlap and recency; "
            "it does not reason over temporal addressability, trust hierarchy, semantic roles, "
            "belief dependency, scoped preferences, or abandoned work"
        ),
        failure_mode="rule_limit" if scenario.discriminative else None,
        requires_judge_review=scenario.discriminative,
    )


def memory_evolution_assertion_passed(
    *,
    scenario: MemoryEvolutionScenario,
    checkpoint: MemoryEvolutionCheckpoint,
    decision: dict[str, object],
) -> bool:
    diagnostics = memory_evolution_decision_diagnostics(
        scenario=scenario,
        checkpoint=checkpoint,
        decision=decision,
    )
    return diagnostics.assertion_passed


def memory_evolution_decision_diagnostics(
    *,
    scenario: MemoryEvolutionScenario,
    checkpoint: MemoryEvolutionCheckpoint,
    decision: dict[str, object],
) -> MemoryEvolutionDecisionDiagnostics:
    failure_buckets: list[MemoryEvolutionFailureBucket] = []
    warning_buckets: list[MemoryEvolutionWarningBucket] = []
    try:
        parsed = MemoryEvolutionDecision.model_validate(decision)
    except ValidationError as exc:
        return MemoryEvolutionDecisionDiagnostics(
            assertion_passed=False,
            failure_buckets=[MemoryEvolutionFailureBucket.SCHEMA_VALIDATION_FAILED],
            rationale=f"MemoryEvolutionDecision schema validation failed: {exc.errors()}",
        )

    contract = memory_evolution_checkpoint_contract(scenario=scenario, checkpoint=checkpoint)
    score_by_id = {score.memory_id: score.belief for score in parsed.belief_scores}
    selected_ids = list(parsed.selected_memory_ids)
    selected = set(selected_ids)
    supporting = set(parsed.supporting_memory_ids)
    evaluated_belief_ids = _dedupe_string_ids(
        [
            *parsed.evaluated_belief_ids,
            *[score.memory_id for score in parsed.belief_scores if _is_belief_memory_id(score.memory_id, checkpoint=checkpoint)],
        ]
    )

    if checkpoint.expected_answer is not None and not _answer_matches_expected(
        actual=parsed.answer,
        expected=checkpoint.expected_answer,
    ):
        failure_buckets.append(MemoryEvolutionFailureBucket.ANSWER_MISMATCH)

    if checkpoint.expected_next_action is not None and not _next_action_matches_expected(
        actual=parsed.next_action,
        expected=checkpoint.expected_next_action,
        checkpoint=checkpoint,
        parsed=parsed,
        contract=contract,
    ):
        failure_buckets.append(MemoryEvolutionFailureBucket.NEXT_ACTION_MISMATCH)

    expected_retrieval = list(checkpoint.expected_retrieval_ids)
    expected_retrieval_set = set(expected_retrieval)
    retrieval_surface = selected | supporting | set(parsed.active_memory_ids)
    if contract.checkpoint_kind == MemoryEvolutionCheckpointKind.BELIEF_RANKING:
        retrieval_surface |= set(evaluated_belief_ids)
    if contract.checkpoint_kind == MemoryEvolutionCheckpointKind.BELIEF_DEGRADATION:
        retrieval_surface |= set(parsed.citation_memory_ids)

    missing_retrieval_ids: list[str] = []
    extra_selected_ids: list[str] = []
    if scenario.discriminative and expected_retrieval and _requires_exact_selected_memory(contract):
        if selected_ids != expected_retrieval:
            missing_retrieval_ids = _ordered_missing(expected_retrieval, selected)
            extra_selected_ids = _ordered_extra(selected_ids, expected_retrieval_set)
            failure_buckets.append(MemoryEvolutionFailureBucket.SELECTED_MEMORY_MISMATCH)
    elif expected_retrieval and not expected_retrieval_set.issubset(retrieval_surface):
        missing_retrieval_ids = _ordered_missing(expected_retrieval, retrieval_surface)
        failure_buckets.append(MemoryEvolutionFailureBucket.EXPECTED_RETRIEVAL_MISSING)

    if contract.checkpoint_kind == MemoryEvolutionCheckpointKind.BELIEF_DEGRADATION:
        extra_belief_selected = [
            memory_id
            for memory_id in _ordered_extra(selected_ids, expected_retrieval_set)
            if _is_belief_memory_id(memory_id, checkpoint=checkpoint)
        ]
        if extra_belief_selected:
            extra_selected_ids = _dedupe_string_ids([*extra_selected_ids, *extra_belief_selected])
            warning_buckets.append(MemoryEvolutionWarningBucket.EXTRA_SELECTED_EVALUATED_BELIEF_IDS)

    if selected & set(checkpoint.expected_excluded_memory_ids):
        failure_buckets.append(MemoryEvolutionFailureBucket.EXCLUDED_MEMORY_SELECTED)

    missing_citation_ids: list[str] = []
    extra_citation_ids: list[str] = []
    belief_ids_used_as_citations: list[str] = []
    if checkpoint.expected_citation_ids:
        expected_citations = set(checkpoint.expected_citation_ids)
        actual_citations = list(parsed.citation_memory_ids)
        missing_citation_ids = _ordered_missing(checkpoint.expected_citation_ids, set(actual_citations))
        extra_citation_ids = _ordered_extra(actual_citations, expected_citations)
        if missing_citation_ids:
            failure_buckets.append(MemoryEvolutionFailureBucket.EXPECTED_CITATION_MISSING)
        if extra_citation_ids:
            if _extra_direct_citations_are_warning_only(
                extra_citation_ids=extra_citation_ids,
                checkpoint=checkpoint,
                contract=contract,
            ):
                warning_buckets.append(MemoryEvolutionWarningBucket.CONTEXT_CITATION_IN_DIRECT_CHANNEL)
            else:
                failure_buckets.append(MemoryEvolutionFailureBucket.CITATION_CHANNEL_POLLUTION)
        belief_ids_used_as_citations = [
            memory_id
            for memory_id in actual_citations
            if _is_belief_memory_id(memory_id, checkpoint=checkpoint)
        ]
        if belief_ids_used_as_citations:
            if contract.checkpoint_kind == MemoryEvolutionCheckpointKind.BELIEF_DEGRADATION and not missing_citation_ids:
                warning_buckets.append(MemoryEvolutionWarningBucket.CONTEXT_CITATION_IN_DIRECT_CHANNEL)
            else:
                failure_buckets.append(MemoryEvolutionFailureBucket.BELIEF_ID_USED_AS_CITATION)

    expected_active = set(checkpoint.expected_active_memory_ids)
    active_surface = set(parsed.active_memory_ids) | selected | supporting
    if contract.checkpoint_kind == MemoryEvolutionCheckpointKind.BELIEF_DEGRADATION:
        active_surface |= set(parsed.citation_memory_ids)
    missing_active = _ordered_missing(checkpoint.expected_active_memory_ids, active_surface)
    if missing_active:
        if contract.lifecycle_policy == MemoryEvolutionLifecyclePolicy.EXACT:
            failure_buckets.append(MemoryEvolutionFailureBucket.EXPECTED_ACTIVE_MEMORY_MISSING)
        else:
            warning_buckets.append(MemoryEvolutionWarningBucket.LIFECYCLE_CHANNEL_DRIFT)

    if set(checkpoint.expected_inactive_memory_ids) & set(parsed.active_memory_ids):
        failure_buckets.append(MemoryEvolutionFailureBucket.INACTIVE_MEMORY_MARKED_ACTIVE)

    missing_archived = _ordered_missing(checkpoint.expected_archived_memory_ids, set(parsed.archived_memory_ids))
    if missing_archived:
        if contract.lifecycle_policy == MemoryEvolutionLifecyclePolicy.EXACT:
            failure_buckets.append(MemoryEvolutionFailureBucket.EXPECTED_ARCHIVED_MEMORY_MISSING)
        else:
            warning_buckets.append(MemoryEvolutionWarningBucket.LIFECYCLE_CHANNEL_DRIFT)

    extra_active_ids = _ordered_extra(parsed.active_memory_ids, expected_active | expected_retrieval_set)
    if extra_active_ids:
        warning_buckets.append(MemoryEvolutionWarningBucket.EXTRA_ACTIVE_MEMORY_IDS)

    belief_ids_marked_active = [
        memory_id
        for memory_id in parsed.active_memory_ids
        if _is_belief_memory_id(memory_id, checkpoint=checkpoint)
    ]
    if belief_ids_marked_active and not checkpoint.expected_active_memory_ids:
        warning_buckets.extend(
            [
                MemoryEvolutionWarningBucket.ACTIVE_CHANNEL_POLLUTION,
                MemoryEvolutionWarningBucket.BELIEF_CANDIDATE_MARKED_ACTIVE,
            ]
        )

    if parsed.belief_scores and contract.belief_score_policy == MemoryEvolutionBeliefScorePolicy.NONE:
        warning_buckets.append(MemoryEvolutionWarningBucket.BELIEF_SCORES_ON_NON_BELIEF_CHECKPOINT)

    expected_belief_ranking: list[str] = []
    actual_belief_ranking: list[str] = []
    score_mismatch_ids: list[str] = []
    belief_effect_order_errors: list[str] = []
    if checkpoint.expected_belief_ranking:
        if not set(checkpoint.expected_belief_ranking).issubset(score_by_id):
            failure_buckets.append(MemoryEvolutionFailureBucket.BELIEF_RANKING_MISSING_SCORE)
        ranked = sorted(score_by_id, key=lambda key: (-score_by_id[key], key))
        expected_belief_ranking = list(checkpoint.expected_belief_ranking)
        actual_belief_ranking = ranked[: len(checkpoint.expected_belief_ranking)]
        if actual_belief_ranking != expected_belief_ranking:
            failure_buckets.append(MemoryEvolutionFailureBucket.BELIEF_RANKING_WRONG_ORDER)
            belief_effect_order_errors = _belief_effect_order_errors(
                scenario=scenario,
                checkpoint=checkpoint,
                score_by_id=score_by_id,
            )
            if belief_effect_order_errors:
                failure_buckets.append(MemoryEvolutionFailureBucket.WEAKENED_BELIEF_RANKED_ABOVE_NEUTRAL)

    if checkpoint.expected_belief_scores:
        for memory_id, expected in checkpoint.expected_belief_scores.items():
            actual = score_by_id.get(memory_id)
            if actual is None:
                score_mismatch_ids.append(memory_id)
                continue
            if contract.belief_score_policy == MemoryEvolutionBeliefScorePolicy.DEGRADED_THRESHOLD:
                if expected <= 0.35 and actual > 0.35:
                    score_mismatch_ids.append(memory_id)
                    failure_buckets.append(MemoryEvolutionFailureBucket.BELIEF_CONFIDENCE_NOT_DEGRADED)
                elif abs(actual - expected) > 0.05:
                    score_mismatch_ids.append(memory_id)
                    warning_buckets.append(MemoryEvolutionWarningBucket.BELIEF_SCORE_CALIBRATION_DRIFT)
            elif contract.belief_score_policy == MemoryEvolutionBeliefScorePolicy.RANKING_ONLY:
                if abs(actual - expected) > 0.05:
                    score_mismatch_ids.append(memory_id)
                    warning_buckets.append(MemoryEvolutionWarningBucket.BELIEF_SCORE_CALIBRATION_DRIFT)
            elif contract.belief_score_policy == MemoryEvolutionBeliefScorePolicy.EXACT and abs(actual - expected) > 0.05:
                score_mismatch_ids.append(memory_id)
                failure_buckets.append(MemoryEvolutionFailureBucket.BELIEF_SCORE_MISMATCH)
        if any(memory_id not in score_by_id for memory_id in checkpoint.expected_belief_scores):
            failure_buckets.append(MemoryEvolutionFailureBucket.BELIEF_SCORE_MISMATCH)

    lifecycle_drift_ids = _dedupe_string_ids([*missing_active, *missing_archived])
    failure_buckets = _dedupe_preserving_order(failure_buckets)
    warning_buckets = _dedupe_preserving_order(warning_buckets)
    return MemoryEvolutionDecisionDiagnostics(
        assertion_passed=not failure_buckets,
        failure_buckets=failure_buckets,
        warning_buckets=warning_buckets,
        missing_retrieval_ids=missing_retrieval_ids,
        extra_selected_ids=extra_selected_ids,
        missing_citation_ids=missing_citation_ids,
        extra_citation_ids=extra_citation_ids,
        belief_ids_used_as_citations=belief_ids_used_as_citations,
        belief_ids_marked_active=belief_ids_marked_active,
        evaluated_belief_ids=evaluated_belief_ids,
        extra_active_ids=extra_active_ids,
        lifecycle_drift_ids=lifecycle_drift_ids,
        expected_belief_ranking=expected_belief_ranking,
        actual_belief_ranking=actual_belief_ranking,
        score_mismatch_ids=_dedupe_string_ids(score_mismatch_ids),
        belief_effect_order_errors=belief_effect_order_errors,
        rationale="memory evolution assertion diagnostics",
    )


def memory_evolution_checkpoint_contract(
    *,
    scenario: MemoryEvolutionScenario,
    checkpoint: MemoryEvolutionCheckpoint,
) -> MemoryEvolutionCheckpointContract:
    if scenario.family == "belief_dependency_degradation":
        return MemoryEvolutionCheckpointContract(
            checkpoint_kind=MemoryEvolutionCheckpointKind.BELIEF_DEGRADATION,
            citation_policy=MemoryEvolutionCitationPolicy.DIRECT_WITH_CONTEXT_WARNING,
            lifecycle_policy=MemoryEvolutionLifecyclePolicy.EXACT,
            belief_score_policy=MemoryEvolutionBeliefScorePolicy.DEGRADED_THRESHOLD,
            next_action_policy=MemoryEvolutionNextActionPolicy.NONE,
        )
    if checkpoint.expected_belief_ranking:
        return MemoryEvolutionCheckpointContract(
            checkpoint_kind=MemoryEvolutionCheckpointKind.BELIEF_RANKING,
            citation_policy=MemoryEvolutionCitationPolicy.DIRECT_ONLY,
            lifecycle_policy=MemoryEvolutionLifecyclePolicy.WARNING,
            belief_score_policy=MemoryEvolutionBeliefScorePolicy.RANKING_ONLY,
            next_action_policy=MemoryEvolutionNextActionPolicy.NONE,
        )
    if scenario.family == "abandoned_then_resumed_work":
        return MemoryEvolutionCheckpointContract(
            checkpoint_kind=MemoryEvolutionCheckpointKind.EXECUTION_CONTINUATION,
            citation_policy=MemoryEvolutionCitationPolicy.DIRECT_WITH_CONTEXT_WARNING,
            lifecycle_policy=MemoryEvolutionLifecyclePolicy.WARNING,
            belief_score_policy=MemoryEvolutionBeliefScorePolicy.NONE,
            next_action_policy=MemoryEvolutionNextActionPolicy.NONEMPTY_STRUCTURED,
        )
    if scenario.family == "expired_fact_historical_query":
        return MemoryEvolutionCheckpointContract(
            checkpoint_kind=(
                MemoryEvolutionCheckpointKind.HISTORICAL_TRUTH
                if "was" in _norm(checkpoint.query_or_task).split()
                else MemoryEvolutionCheckpointKind.CURRENT_TRUTH
            ),
            citation_policy=MemoryEvolutionCitationPolicy.DIRECT_ONLY,
            lifecycle_policy=MemoryEvolutionLifecyclePolicy.WARNING,
            belief_score_policy=MemoryEvolutionBeliefScorePolicy.NONE,
            next_action_policy=MemoryEvolutionNextActionPolicy.NONE,
        )
    return MemoryEvolutionCheckpointContract(
        checkpoint_kind=MemoryEvolutionCheckpointKind.CURRENT_TRUTH,
        citation_policy=MemoryEvolutionCitationPolicy.DIRECT_ONLY,
        lifecycle_policy=MemoryEvolutionLifecyclePolicy.EXACT,
        belief_score_policy=MemoryEvolutionBeliefScorePolicy.NONE,
        next_action_policy=MemoryEvolutionNextActionPolicy.NONE,
    )


def _evidence_effect_policy(contract: MemoryEvolutionCheckpointContract) -> dict[str, str]:
    if contract.checkpoint_kind != MemoryEvolutionCheckpointKind.BELIEF_RANKING:
        return {}
    return {
        "source": "surface-derived evidence_effect_cards",
        "ranking_order": "supported > neutral > weakened > falsified",
        "neutral_rule": "A visible hypothesis with no support or weakening outranks an explicitly weakened hypothesis.",
    }


def _output_channel_contract(contract: MemoryEvolutionCheckpointContract) -> dict[str, str]:
    base = {
        "selected_memory_ids": "Final answer/current winner memories only; do not put audit context here.",
        "supporting_memory_ids": "Memories that directly support the selected answer or next action.",
        "citation_memory_ids": "Direct evidence/source memory ids only.",
        "context_memory_ids": "Useful audit context that is neither final truth nor direct support.",
        "rejected_memory_ids": "Stale, blocked, falsified, lower-trust, wrong-scope, or wrong-entity memories considered and ruled out.",
        "context_citation_memory_ids": "Citation-like context that explains rejection or audit state but is not direct answer support.",
        "active_memory_ids": "Current active factual/action memories at the checkpoint timestamp.",
        "inactive_memory_ids": "Known false, suppressed, blocked, or lower-trust memories.",
        "archived_memory_ids": "Superseded or expired historical memories retained for audit/history.",
    }
    if contract.belief_score_policy != MemoryEvolutionBeliefScorePolicy.NONE:
        base["belief_scores"] = "Rank/evaluate belief ids; probabilities may be calibrated estimates unless an exact rubric is provided."
        base["evaluated_belief_ids"] = "Belief candidates being ranked or degraded; do not use this as answer support."
    if contract.checkpoint_kind == MemoryEvolutionCheckpointKind.BELIEF_DEGRADATION:
        base["selected_memory_ids"] = "Select the falsifying/current evidence when no belief remains confident; degraded beliefs belong in evaluated/rejected/inactive channels."
    if contract.checkpoint_kind == MemoryEvolutionCheckpointKind.EXECUTION_CONTINUATION:
        base["selected_memory_ids"] = "Select the active continuation branch/action, not blocked or abandoned branches."
        base["next_action"] = "Non-empty action phrase for the selected active branch; exact wording is less important than branch state."
    return base


def _requires_exact_selected_memory(contract: MemoryEvolutionCheckpointContract) -> bool:
    return contract.checkpoint_kind not in {
        MemoryEvolutionCheckpointKind.BELIEF_RANKING,
        MemoryEvolutionCheckpointKind.BELIEF_DEGRADATION,
    }


def _expected_belief_ids(checkpoint: MemoryEvolutionCheckpoint) -> list[str]:
    return _dedupe_string_ids([*checkpoint.expected_belief_ranking, *checkpoint.expected_belief_scores.keys()])


def _extra_direct_citations_are_warning_only(
    *,
    extra_citation_ids: list[str],
    checkpoint: MemoryEvolutionCheckpoint,
    contract: MemoryEvolutionCheckpointContract,
) -> bool:
    if contract.citation_policy != MemoryEvolutionCitationPolicy.DIRECT_WITH_CONTEXT_WARNING:
        return False
    if contract.checkpoint_kind == MemoryEvolutionCheckpointKind.EXECUTION_CONTINUATION:
        return True
    if contract.checkpoint_kind == MemoryEvolutionCheckpointKind.BELIEF_DEGRADATION:
        return all(_is_belief_memory_id(memory_id, checkpoint=checkpoint) for memory_id in extra_citation_ids)
    return False


def _next_action_matches_expected(
    *,
    actual: str | None,
    expected: str,
    checkpoint: MemoryEvolutionCheckpoint,
    parsed: MemoryEvolutionDecision,
    contract: MemoryEvolutionCheckpointContract,
) -> bool:
    if contract.next_action_policy == MemoryEvolutionNextActionPolicy.NONEMPTY_STRUCTURED:
        if not _norm(actual):
            return False
        expected_active = set(checkpoint.expected_active_memory_ids) | set(checkpoint.expected_retrieval_ids)
        selected_state = set(parsed.selected_memory_ids) | set(parsed.active_memory_ids) | set(parsed.supporting_memory_ids)
        return bool(expected_active & selected_state)
    action = _norm(actual)
    return all(token in action.split() for token in _norm(expected).split())


def _dedupe_string_ids(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def memory_evolution_trace_for_rule(
    *,
    context: MemoryEvolutionDecisionContext,
    decision: MemoryEvolutionDecision,
    mode: str,
) -> LLMDecisionTrace:
    return LLMDecisionTrace(
        trace_id=f"trace:{uuid4().hex}",
        decision_point=LLMDecisionPoint.MEMORY_EVOLUTION_DECISION,
        mode=LLMDecisionMode(mode),
        input_payload=context.model_dump(mode="json"),
        parsed_output=decision.model_dump(mode="json"),
        final_output=decision.model_dump(mode="json"),
        status=LLMDecisionStatus.SUCCEEDED,
        created_at=datetime.now(UTC),
    )


def memory_evolution_engine_result_from_llm(
    *,
    result: LLMDecisionResult,
    mode: LLMDecisionMode,
    rule_output: dict[str, object],
) -> tuple[dict[str, object], LLMDecisionTrace, bool, str | None]:
    if not result.success:
        trace = build_llm_decision_trace_from_result(
            decision_point=LLMDecisionPoint.MEMORY_EVOLUTION_DECISION,
            mode=mode,
            result=result,
            final_output=rule_output,
            fallback_used=True,
            status=LLMDecisionStatus.PROVIDER_ERROR,
        )
        return rule_output, trace, False, "llm_decision_failed"
    try:
        decision = MemoryEvolutionDecision.model_validate(result.output)
    except ValidationError:
        trace = build_llm_decision_trace_from_result(
            decision_point=LLMDecisionPoint.MEMORY_EVOLUTION_DECISION,
            mode=mode,
            result=result,
            final_output=rule_output,
            fallback_used=True,
            status=LLMDecisionStatus.VALIDATION_FAILED,
        )
        return rule_output, trace, False, "llm_decision_validation_failed"
    output = decision.model_dump(mode="json")
    trace = build_llm_decision_trace_from_result(
        decision_point=LLMDecisionPoint.MEMORY_EVOLUTION_DECISION,
        mode=mode,
        result=result,
        final_output=output,
        fallback_used=False,
        status=LLMDecisionStatus.SUCCEEDED,
    )
    return output, trace, True, None


def fake_llm_result_for_memory_evolution(
    *,
    request: LLMStructuredRequest,
    decision: MemoryEvolutionDecision,
    provider_name: str = "fake",
) -> LLMDecisionResult:
    output = decision.model_dump(mode="json")
    response = LLMStructuredResponse(
        request_id=request.request_id,
        provider=provider_name,
        raw_text=json.dumps(output, sort_keys=True),
        parsed_json=output,
        valid_json=True,
        schema_valid=True,
    )
    return LLMDecisionResult(
        request=request,
        response=response,
        output=output,
        success=True,
        failure_mode=None,
    )



def _visible_events_for_checkpoint(
    *,
    scenario: MemoryEvolutionScenario,
    checkpoint: MemoryEvolutionCheckpoint,
) -> list[MemoryEvolutionEvent]:
    return [event for event in scenario.events if event.timestamp <= checkpoint.timestamp]


def _visible_memory_cards_for_events(events: list[MemoryEvolutionEvent]) -> list[MemoryEvolutionVisibleMemoryCard]:
    return [
        MemoryEvolutionVisibleMemoryCard(
            memory_id=event.event_id,
            memory_kind=_memory_kind_for_event(event),
            statement=event.content,
            timestamp=event.timestamp,
            source_type=event.source_type,
            trust_level=event.trust_level,
            entity_ids=list(event.entity_ids),
            task_id=event.task_id,
            scope=event.scope,
        )
        for event in events
    ]


def _memory_kind_for_event(event: MemoryEvolutionEvent) -> MemoryEvolutionMemoryKind:
    if event.event_id.startswith("belief:"):
        return MemoryEvolutionMemoryKind.BELIEF
    if event.event_id.startswith("evidence:"):
        return MemoryEvolutionMemoryKind.EVIDENCE
    if event.event_id.startswith("exec:"):
        return MemoryEvolutionMemoryKind.ACTION
    if event.event_id.startswith("mem:"):
        return MemoryEvolutionMemoryKind.FACT
    return MemoryEvolutionMemoryKind.UNKNOWN


def _evidence_effect_cards_for_events(events: list[MemoryEvolutionEvent]) -> list[MemoryEvolutionEvidenceEffectCard]:
    label_to_memory_id = _belief_label_map(events)
    cards: list[MemoryEvolutionEvidenceEffectCard] = []
    for event in events:
        supports = _effect_ids_for_verbs(
            event.content,
            label_to_memory_id,
            ["supports", "support", "confirms", "backs", "strengthens"],
        )
        supports.extend(
            _effect_ids_for_label_predicates(
                event.content,
                label_to_memory_id,
                ["supported", "confirmed", "backed", "strengthened"],
            )
        )
        weakens = _effect_ids_for_verbs(
            event.content,
            label_to_memory_id,
            ["weakens", "weaken", "downgrades", "degrades", "undermines", "leaves", "makes", "renders"],
        )
        weakens.extend(
            _effect_ids_for_label_predicates(
                event.content,
                label_to_memory_id,
                ["weakened", "downgraded", "degraded", "less likely", "weaker", "unsupported"],
            )
        )
        falsifies = _effect_ids_for_verbs(
            event.content,
            label_to_memory_id,
            ["falsifies", "falsify", "refutes", "disproves", "invalidates"],
        )
        falsifies.extend(
            _effect_ids_for_label_predicates(
                event.content,
                label_to_memory_id,
                ["falsified", "refuted", "disproved", "invalidated", "ruled out"],
            )
        )
        dependencies = _dependency_ids_for_text(event.content, label_to_memory_id)
        supports = _dedupe_string_ids(supports)
        weakens = _dedupe_string_ids(weakens)
        falsifies = _dedupe_string_ids(falsifies)
        if not (supports or weakens or falsifies or dependencies):
            continue
        cards.append(
            MemoryEvolutionEvidenceEffectCard(
                evidence_memory_id=event.event_id,
                supports_memory_ids=supports,
                weakens_memory_ids=weakens,
                falsifies_memory_ids=falsifies,
                dependency_memory_ids=dependencies,
            )
        )
    return cards


def _belief_label_map(events: list[MemoryEvolutionEvent]) -> dict[str, str]:
    label_to_memory_id: dict[str, str] = {}
    for event in events:
        if not event.event_id.startswith("belief:"):
            continue
        for match in re.finditer(r"\b(?:hypothesis|belief)\s+([a-z])\b", event.content, flags=re.IGNORECASE):
            label_to_memory_id.setdefault(match.group(1).upper(), event.event_id)
        event_id_match = re.match(r"belief:([a-z])-", event.event_id, flags=re.IGNORECASE)
        if event_id_match is not None:
            label_to_memory_id.setdefault(event_id_match.group(1).upper(), event.event_id)
    return label_to_memory_id


def _effect_ids_for_verbs(content: str, label_to_memory_id: dict[str, str], verbs: list[str]) -> list[str]:
    ids: list[str] = []
    for verb in verbs:
        for match in re.finditer(rf"\b{re.escape(verb)}\s+([a-z])\b", content, flags=re.IGNORECASE):
            memory_id = label_to_memory_id.get(match.group(1).upper())
            if memory_id is not None:
                ids.append(memory_id)
    return _dedupe_string_ids(ids)


def _effect_ids_for_label_predicates(
    content: str,
    label_to_memory_id: dict[str, str],
    predicates: list[str],
) -> list[str]:
    ids: list[str] = []
    predicate_pattern = "|".join(re.escape(predicate) for predicate in predicates)
    for match in re.finditer(
        rf"\b([a-z])\b\s+(?:is|was|looks|seems|becomes|became)?\s*(?:now\s+)?(?:more\s+)?(?:{predicate_pattern})\b",
        content,
        flags=re.IGNORECASE,
    ):
        memory_id = label_to_memory_id.get(match.group(1).upper())
        if memory_id is not None:
            ids.append(memory_id)
    return _dedupe_string_ids(ids)


def _dependency_ids_for_text(content: str, label_to_memory_id: dict[str, str]) -> list[str]:
    ids: list[str] = []
    for match in re.finditer(r"\bdepends\s+on\s+([a-z])\b", content, flags=re.IGNORECASE):
        memory_id = label_to_memory_id.get(match.group(1).upper())
        if memory_id is not None:
            ids.append(memory_id)
    return _dedupe_string_ids(ids)


def _belief_effect_order_errors(
    *,
    scenario: MemoryEvolutionScenario,
    checkpoint: MemoryEvolutionCheckpoint,
    score_by_id: dict[str, float],
) -> list[str]:
    if not checkpoint.expected_belief_ranking:
        return []
    visible_events = _visible_events_for_checkpoint(scenario=scenario, checkpoint=checkpoint)
    effect_cards = _evidence_effect_cards_for_events(visible_events)
    supported: set[str] = set()
    weakened: set[str] = set()
    falsified: set[str] = set()
    for card in effect_cards:
        supported.update(card.supports_memory_ids)
        weakened.update(card.weakens_memory_ids)
        falsified.update(card.falsifies_memory_ids)
    candidates = list(checkpoint.expected_belief_ranking)
    neutral = [memory_id for memory_id in candidates if memory_id not in supported | weakened | falsified]
    errors: list[str] = []
    for weakened_id in sorted(weakened & set(candidates)):
        if weakened_id not in score_by_id:
            continue
        for neutral_id in neutral:
            if neutral_id not in score_by_id:
                continue
            if score_by_id[weakened_id] > score_by_id[neutral_id]:
                errors.append(f"{weakened_id}>{neutral_id}")
    return errors

def _rank_events_by_shallow_overlap(
    *,
    scenario: MemoryEvolutionScenario,
    checkpoint: MemoryEvolutionCheckpoint,
) -> list[MemoryEvolutionEvent]:
    query_tokens = set(_norm(checkpoint.query_or_task).split())
    eligible = [event for event in scenario.events if event.timestamp <= checkpoint.timestamp]
    return sorted(
        eligible,
        key=lambda event: (
            -len(query_tokens & set(_norm(event.content).split())),
            -event.timestamp.timestamp(),
            event.event_id,
        ),
    )


def _extract_shallow_answer(content: str) -> str:
    for separator in [" is ", " = ", ":"]:
        if separator in content:
            return content.split(separator, 1)[1].strip().rstrip(".")
    return content.strip().rstrip(".")


def _norm(value: str | None) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).split())


def _ordered_missing(expected_ids: list[str], actual_ids: set[str]) -> list[str]:
    return [memory_id for memory_id in expected_ids if memory_id not in actual_ids]


def _ordered_extra(actual_ids: list[str], expected_ids: set[str]) -> list[str]:
    return [memory_id for memory_id in actual_ids if memory_id not in expected_ids]


def _is_belief_memory_id(memory_id: str, *, checkpoint: MemoryEvolutionCheckpoint) -> bool:
    return (
        memory_id.startswith("belief:")
        or memory_id in checkpoint.expected_belief_ranking
        or memory_id in checkpoint.expected_belief_scores
    )


def _dedupe_preserving_order(values: list[BucketT]) -> list[BucketT]:
    seen: set[BucketT] = set()
    result: list[BucketT] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _answer_matches_expected(*, actual: str | None, expected: str) -> bool:
    actual_norm = _norm(actual)
    expected_norm = _norm(expected)
    if actual_norm == expected_norm:
        return True
    actual_tokens = set(actual_norm.split())
    expected_tokens = set(expected_norm.split())
    if not expected_tokens:
        return True
    if expected_tokens.issubset(actual_tokens):
        return True
    if "no" in expected_tokens and ({"no", "none", "neither", "zero"} & actual_tokens):
        return (expected_tokens - {"no"}).issubset(actual_tokens)
    return False
