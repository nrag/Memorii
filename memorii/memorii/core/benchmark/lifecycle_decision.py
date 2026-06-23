"""Benchmark-only lifecycle decision models and deterministic providers."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from memorii.core.benchmark.models import BenchmarkScenarioFixture, MemoryLifecycleFamily
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


DISCRIMINATIVE_LIFECYCLE_FAMILIES = {
    MemoryLifecycleFamily.HISTORICAL_TRUTH_RETRIEVAL,
    MemoryLifecycleFamily.CURRENT_TRUTH_RETRIEVAL,
    MemoryLifecycleFamily.COMPETING_BELIEF_RERANKING,
    MemoryLifecycleFamily.PARTIAL_MERGE_PRESERVE_UNIQUE_FACTS,
    MemoryLifecycleFamily.HIGH_SIMILARITY_ACTIVE_DISTRACTOR,
}


class LifecycleDecisionCandidate(BaseModel):
    candidate_id: str
    text: str
    domain: str
    validity_status: str
    valid_from: str | None = None
    valid_to: str | None = None

    model_config = ConfigDict(extra="forbid")


class LifecycleDecisionContext(BaseModel):
    scenario_id: str
    family: MemoryLifecycleFamily
    query: str
    operation: str
    temporal_target: str | None = None
    candidates: list[LifecycleDecisionCandidate] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class LifecycleBeliefScore(BaseModel):
    memory_id: str
    belief: float = Field(ge=0.0, le=1.0)

    model_config = ConfigDict(extra="forbid")


class LifecycleDecision(BaseModel):
    selected_retrieval_ids: list[str] = Field(default_factory=list)
    active_memory_ids: list[str] = Field(default_factory=list)
    inactive_memory_ids: list[str] = Field(default_factory=list)
    archived_memory_ids: list[str] = Field(default_factory=list)
    belief_scores: list[LifecycleBeliefScore] = Field(default_factory=list)
    merged_summary: str | None = None
    confidence: float
    rationale: str
    failure_mode: str | None = None
    requires_judge_review: bool = False

    model_config = ConfigDict(extra="forbid")


def lifecycle_family_requires_decision(family: MemoryLifecycleFamily | None) -> bool:
    return family in DISCRIMINATIVE_LIFECYCLE_FAMILIES


def lifecycle_context_for_fixture(fixture: BenchmarkScenarioFixture) -> LifecycleDecisionContext:
    if fixture.lifecycle is None:
        raise ValueError("lifecycle fixture is required")

    query = ""
    raw_candidates = []
    if fixture.retrieval is not None:
        query = fixture.retrieval.query
        raw_candidates = list(fixture.retrieval.corpus)
    elif fixture.implicit_recall is not None:
        query = fixture.implicit_recall.query
        raw_candidates = list(fixture.implicit_recall.corpus)
    elif fixture.long_horizon_degradation is not None:
        query = fixture.long_horizon_degradation.delayed_retrieval.query
        raw_candidates = list(fixture.long_horizon_degradation.delayed_retrieval.corpus)

    candidates = [
        LifecycleDecisionCandidate(
            candidate_id=item.item_id,
            text=item.text,
            domain=item.domain.value,
            validity_status=item.validity_status.value,
            valid_from=item.valid_from.isoformat() if item.valid_from is not None else None,
            valid_to=item.valid_to.isoformat() if item.valid_to is not None else None,
        )
        for item in raw_candidates
    ]
    return LifecycleDecisionContext(
        scenario_id=fixture.scenario_id,
        family=fixture.lifecycle.family,
        query=query,
        operation=_operation_for_family(fixture.lifecycle.family),
        temporal_target=_temporal_target_for_family(fixture.lifecycle.family),
        candidates=candidates,
        metadata={"category": fixture.category.value},
    )


def expected_lifecycle_decision_for_fixture(fixture: BenchmarkScenarioFixture) -> LifecycleDecision:
    if fixture.lifecycle is None:
        raise ValueError("lifecycle fixture is required")
    lifecycle = fixture.lifecycle
    belief_scores = [
        LifecycleBeliefScore(memory_id=memory_id, belief=max(0.0, 1.0 - (index * 0.2)))
        for index, memory_id in enumerate(lifecycle.expected_belief_ranking)
    ]
    return LifecycleDecision(
        selected_retrieval_ids=list(lifecycle.expected_retrieval_ids),
        active_memory_ids=list(lifecycle.expected_active_memory_ids),
        inactive_memory_ids=list(lifecycle.expected_inactive_memory_ids),
        archived_memory_ids=list(lifecycle.expected_archived_memory_ids),
        belief_scores=belief_scores,
        merged_summary=" ".join(lifecycle.expected_merged_fact_tokens) or None,
        confidence=0.9,
        rationale="expected benchmark lifecycle decision",
        failure_mode=None,
        requires_judge_review=False,
    )


def rule_lifecycle_decision_for_fixture(fixture: BenchmarkScenarioFixture) -> LifecycleDecision:
    context = lifecycle_context_for_fixture(fixture)
    ranked = _rank_candidates_by_shallow_overlap(context)
    candidate_ids = [candidate.candidate_id for candidate in ranked]
    selected = candidate_ids[:1]

    belief_scores = [
        LifecycleBeliefScore(memory_id=memory_id, belief=0.5)
        for memory_id in candidate_ids
    ]
    return LifecycleDecision(
        selected_retrieval_ids=selected,
        active_memory_ids=selected,
        inactive_memory_ids=[],
        archived_memory_ids=[],
        belief_scores=belief_scores,
        merged_summary=None,
        confidence=0.45,
        rationale="rule lifecycle provider uses shallow token overlap and corpus order; it does not reason over temporal windows, semantic roles, belief competition, or partial merges",
        failure_mode="rule_limit",
        requires_judge_review=True,
    )


def lifecycle_assertion_passed(
    *,
    fixture: BenchmarkScenarioFixture,
    decision: dict[str, object],
) -> bool:
    try:
        parsed = LifecycleDecision.model_validate(decision)
    except ValidationError:
        return False
    if fixture.lifecycle is None:
        return True

    lifecycle = fixture.lifecycle
    selected_ids = list(parsed.selected_retrieval_ids)
    selected = set(selected_ids)
    expected_retrieval = list(lifecycle.expected_retrieval_ids)
    if lifecycle.require_lifecycle_decision and expected_retrieval:
        if selected_ids != expected_retrieval:
            return False
    elif not set(expected_retrieval).issubset(selected):
        return False
    if selected & set(lifecycle.expected_excluded_retrieval_ids):
        return False
    if not set(lifecycle.expected_active_memory_ids).issubset(
        set(parsed.active_memory_ids) | selected
    ):
        return False
    if set(lifecycle.expected_inactive_memory_ids) & (
        set(parsed.active_memory_ids) | selected
    ):
        return False
    if lifecycle.expected_belief_ranking:
        score_by_memory_id = {
            score.memory_id: score.belief
            for score in parsed.belief_scores
        }
        if not set(lifecycle.expected_belief_ranking).issubset(score_by_memory_id):
            return False
        ranked = sorted(
            score_by_memory_id,
            key=lambda key: (-score_by_memory_id[key], key),
        )
        if ranked[: len(lifecycle.expected_belief_ranking)] != lifecycle.expected_belief_ranking:
            return False
    if lifecycle.expect_partial_merge:
        merged = (parsed.merged_summary or "").lower()
        if not all(token.lower() in merged for token in lifecycle.expected_merged_fact_tokens):
            return False
        inactive = set(parsed.inactive_memory_ids) | set(parsed.archived_memory_ids)
        if not set(lifecycle.expected_inactive_memory_ids).issubset(inactive):
            return False
    if lifecycle.expect_temporal_addressability and expected_retrieval:
        if selected_ids != expected_retrieval:
            return False
    return True


def lifecycle_trace_for_rule(
    *,
    context: LifecycleDecisionContext,
    decision: LifecycleDecision,
    mode: str,
) -> LLMDecisionTrace:
    return LLMDecisionTrace(
        trace_id=f"trace:{uuid4().hex}",
        decision_point=LLMDecisionPoint.LIFECYCLE_DECISION,
        mode=LLMDecisionMode(mode),
        input_payload=context.model_dump(mode="json"),
        parsed_output=decision.model_dump(mode="json"),
        final_output=decision.model_dump(mode="json"),
        status=LLMDecisionStatus.SUCCEEDED,
        created_at=datetime.now(UTC),
    )


def lifecycle_engine_result_from_llm(
    *,
    result: LLMDecisionResult,
    mode: LLMDecisionMode,
    rule_output: dict[str, object],
) -> tuple[dict[str, object], LLMDecisionTrace, bool, str | None]:
    if not result.success:
        trace = build_llm_decision_trace_from_result(
            decision_point=LLMDecisionPoint.LIFECYCLE_DECISION,
            mode=mode,
            result=result,
            final_output=rule_output,
            fallback_used=True,
            status=LLMDecisionStatus.PROVIDER_ERROR,
        )
        return rule_output, trace, False, "llm_decision_failed"
    try:
        decision = LifecycleDecision.model_validate(result.output)
    except ValidationError:
        trace = build_llm_decision_trace_from_result(
            decision_point=LLMDecisionPoint.LIFECYCLE_DECISION,
            mode=mode,
            result=result,
            final_output=rule_output,
            fallback_used=True,
            status=LLMDecisionStatus.VALIDATION_FAILED,
        )
        return rule_output, trace, False, "llm_decision_validation_failed"
    output = decision.model_dump(mode="json")
    trace = build_llm_decision_trace_from_result(
        decision_point=LLMDecisionPoint.LIFECYCLE_DECISION,
        mode=mode,
        result=result.model_copy(update={"output": output}),
        final_output=output,
        fallback_used=False,
        status=LLMDecisionStatus.SUCCEEDED,
    )
    return output, trace, True, None


def fake_llm_result_for_lifecycle(
    *,
    request: LLMStructuredRequest,
    decision: LifecycleDecision,
    provider_name: str = "fake",
) -> LLMDecisionResult:
    output = decision.model_dump(mode="json")
    response = LLMStructuredResponse(
        request_id=request.request_id,
        provider=provider_name,
        raw_text="",
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


def _operation_for_family(family: MemoryLifecycleFamily) -> str:
    if family in {
        MemoryLifecycleFamily.HISTORICAL_TRUTH_RETRIEVAL,
        MemoryLifecycleFamily.CURRENT_TRUTH_RETRIEVAL,
        MemoryLifecycleFamily.HIGH_SIMILARITY_ACTIVE_DISTRACTOR,
    }:
        return "select_retrieval"
    if family == MemoryLifecycleFamily.COMPETING_BELIEF_RERANKING:
        return "rank_beliefs"
    if family == MemoryLifecycleFamily.PARTIAL_MERGE_PRESERVE_UNIQUE_FACTS:
        return "partial_merge"
    return "lifecycle_decision"


def _temporal_target_for_family(family: MemoryLifecycleFamily) -> str | None:
    if family == MemoryLifecycleFamily.HISTORICAL_TRUTH_RETRIEVAL:
        return "historical"
    if family == MemoryLifecycleFamily.CURRENT_TRUTH_RETRIEVAL:
        return "current"
    return None


def _rank_candidates_by_shallow_overlap(
    context: LifecycleDecisionContext,
) -> list[LifecycleDecisionCandidate]:
    query_tokens = _tokens(context.query)
    scored: list[tuple[int, int, LifecycleDecisionCandidate]] = []
    for index, candidate in enumerate(context.candidates):
        score = len(query_tokens & _tokens(candidate.text))
        scored.append((-score, index, candidate))
    return [candidate for _, _, candidate in sorted(scored)]


def _tokens(text: str) -> set[str]:
    return {
        token.strip(".,:;!?()[]{}\"'").lower()
        for token in text.split()
        if token.strip(".,:;!?()[]{}\"'")
    }
