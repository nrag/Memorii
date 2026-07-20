"""Benchmark retrieval relevance decision models and providers."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from memorii.core.benchmark.models import BenchmarkScenarioFixture, RetrievalFixtureMemoryItem
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


class RetrievalRelevanceCandidate(BaseModel):
    candidate_id: str
    text: str
    domain: str
    role: str | None = None
    distractor_type: str | None = None
    task_id: str | None = None
    execution_node_id: str | None = None
    solver_run_id: str | None = None
    status: str
    validity_status: str
    valid_from: str | None = None
    valid_to: str | None = None
    entity_tags: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class RetrievalRelevanceContext(BaseModel):
    scenario_id: str
    query: str
    intent: str
    scope: dict[str, object]
    temporal_target: str | None = None
    candidates: list[RetrievalRelevanceCandidate] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class RetrievalRelevanceDecision(BaseModel):
    selected_ids: list[str] = Field(default_factory=list)
    excluded_ids: list[str] = Field(default_factory=list)
    ranking: list[str] = Field(default_factory=list)
    abstain: bool = False
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    failure_mode: str | None = None
    requires_judge_review: bool = False

    model_config = ConfigDict(extra="forbid")


class RetrievalRelevanceOutput(RetrievalRelevanceDecision):
    """Strict provider response for retrieval relevance decisions."""

    selected_ids: list[str]
    excluded_ids: list[str]
    ranking: list[str]
    abstain: bool
    failure_mode: str | None
    requires_judge_review: bool


def retrieval_relevance_context_for_fixture(fixture: BenchmarkScenarioFixture) -> RetrievalRelevanceContext:
    if fixture.retrieval is None:
        raise ValueError("retrieval fixture is required")
    retrieval = fixture.retrieval
    return RetrievalRelevanceContext(
        scenario_id=fixture.scenario_id,
        query=retrieval.query,
        intent=retrieval.intent.value,
        scope=retrieval.scope.model_dump(mode="json"),
        temporal_target=getattr(retrieval, "temporal_target", None),
        candidates=[_candidate_for_item(item) for item in retrieval.corpus],
        metadata={"category": fixture.category.value},
    )


def expected_retrieval_relevance_decision_for_fixture(
    fixture: BenchmarkScenarioFixture,
) -> RetrievalRelevanceDecision:
    if fixture.retrieval is None:
        raise ValueError("retrieval fixture is required")
    retrieval = fixture.retrieval
    excluded = _ordered_unique(
        [
            *retrieval.expected_excluded_ids,
            *retrieval.expected_hard_distractor_ids,
            *[
                item.item_id
                for item in retrieval.corpus
                if item.item_id not in set(retrieval.expected_relevant_ids)
            ],
        ]
    )
    ranking = _ordered_unique(
        [
            *retrieval.expected_relevant_ids,
            *[
                item.item_id
                for item in retrieval.corpus
                if item.item_id not in set(retrieval.expected_relevant_ids)
            ],
        ]
    )
    return RetrievalRelevanceDecision(
        selected_ids=list(retrieval.expected_relevant_ids),
        excluded_ids=excluded,
        ranking=ranking,
        abstain=not bool(retrieval.expected_relevant_ids),
        confidence=0.9,
        rationale="expected benchmark retrieval relevance decision",
        failure_mode=None,
        requires_judge_review=False,
    )


def rule_retrieval_relevance_decision_for_fixture(
    fixture: BenchmarkScenarioFixture,
) -> RetrievalRelevanceDecision:
    context = retrieval_relevance_context_for_fixture(fixture)
    ranked = _rank_candidates_by_shallow_overlap(context)
    selected = [ranked[0].candidate_id] if ranked else []
    ranking = [candidate.candidate_id for candidate in ranked]
    return RetrievalRelevanceDecision(
        selected_ids=selected,
        excluded_ids=ranking[1:],
        ranking=ranking,
        abstain=False,
        confidence=0.45,
        rationale="rule retrieval relevance provider uses shallow token overlap only; it does not reason over temporal intent, source trust, scope semantics, role semantics, or abstention",
        failure_mode="rule_limit",
        requires_judge_review=True,
    )


def retrieval_relevance_assertion_passed(
    *,
    fixture: BenchmarkScenarioFixture,
    decision: dict[str, object],
) -> bool:
    try:
        parsed = RetrievalRelevanceDecision.model_validate(decision)
    except ValidationError:
        return False
    if fixture.retrieval is None:
        return True

    retrieval = fixture.retrieval
    expected_relevant = list(retrieval.expected_relevant_ids)
    if bool(parsed.abstain) != (not bool(expected_relevant)):
        return False
    if list(parsed.selected_ids) != expected_relevant:
        return False
    selected = set(parsed.selected_ids)
    excluded = set(parsed.excluded_ids)
    hard = set(retrieval.expected_hard_distractor_ids)
    explicit_excluded = set(retrieval.expected_excluded_ids)
    if selected & (hard | explicit_excluded):
        return False
    if not (hard | explicit_excluded).issubset(excluded):
        return False
    if expected_relevant:
        ranking = list(parsed.ranking)
        if not ranking:
            return False
        first_relevant_index = _first_index(ranking, set(expected_relevant))
        if first_relevant_index is None:
            return False
        for distractor_id in hard:
            distractor_index = _first_index(ranking, {distractor_id})
            if distractor_index is not None and distractor_index < first_relevant_index:
                return False
    return True


def retrieval_relevance_trace_for_rule(
    *,
    context: RetrievalRelevanceContext,
    decision: RetrievalRelevanceDecision,
    mode: str,
) -> LLMDecisionTrace:
    return LLMDecisionTrace(
        trace_id=f"trace:{uuid4().hex}",
        decision_point=LLMDecisionPoint.RETRIEVAL_RELEVANCE,
        mode=LLMDecisionMode(mode),
        input_payload=context.model_dump(mode="json"),
        parsed_output=decision.model_dump(mode="json"),
        final_output=decision.model_dump(mode="json"),
        status=LLMDecisionStatus.SUCCEEDED,
        created_at=datetime.now(UTC),
    )


def retrieval_relevance_engine_result_from_llm(
    *,
    result: LLMDecisionResult,
    mode: LLMDecisionMode,
    rule_output: dict[str, object],
) -> tuple[dict[str, object], LLMDecisionTrace, bool, str | None]:
    if not result.success:
        trace = build_llm_decision_trace_from_result(
            decision_point=LLMDecisionPoint.RETRIEVAL_RELEVANCE,
            mode=mode,
            result=result,
            final_output=rule_output,
            fallback_used=True,
            status=LLMDecisionStatus.PROVIDER_ERROR,
        )
        return rule_output, trace, False, "llm_decision_failed"
    try:
        decision = RetrievalRelevanceDecision.model_validate(result.output)
    except ValidationError:
        trace = build_llm_decision_trace_from_result(
            decision_point=LLMDecisionPoint.RETRIEVAL_RELEVANCE,
            mode=mode,
            result=result,
            final_output=rule_output,
            fallback_used=True,
            status=LLMDecisionStatus.VALIDATION_FAILED,
        )
        return rule_output, trace, False, "llm_decision_validation_failed"
    output = decision.model_dump(mode="json")
    trace = build_llm_decision_trace_from_result(
        decision_point=LLMDecisionPoint.RETRIEVAL_RELEVANCE,
        mode=mode,
        result=result.model_copy(update={"output": output}),
        final_output=output,
        fallback_used=False,
        status=LLMDecisionStatus.SUCCEEDED,
    )
    return output, trace, True, None


def fake_llm_result_for_retrieval_relevance(
    *,
    request: LLMStructuredRequest,
    decision: RetrievalRelevanceDecision,
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


def _candidate_for_item(item: RetrievalFixtureMemoryItem) -> RetrievalRelevanceCandidate:
    return RetrievalRelevanceCandidate(
        candidate_id=item.item_id,
        text=item.text,
        domain=item.domain.value,
        role=item.role,
        distractor_type=item.distractor_type,
        task_id=item.task_id,
        execution_node_id=item.execution_node_id,
        solver_run_id=item.solver_run_id,
        status=item.status.value,
        validity_status=item.validity_status.value,
        valid_from=item.valid_from.isoformat() if item.valid_from is not None else None,
        valid_to=item.valid_to.isoformat() if item.valid_to is not None else None,
        entity_tags=list(item.entity_tags),
    )


def _rank_candidates_by_shallow_overlap(
    context: RetrievalRelevanceContext,
) -> list[RetrievalRelevanceCandidate]:
    query_tokens = _tokens(context.query)
    scored: list[tuple[int, int, str, RetrievalRelevanceCandidate]] = []
    for index, candidate in enumerate(context.candidates):
        score = len(query_tokens & _tokens(candidate.text))
        scored.append((-score, index, candidate.candidate_id, candidate))
    return [candidate for _, _, _, candidate in sorted(scored)]


def _tokens(text: str) -> set[str]:
    return {
        token.strip(".,:;!?()[]{}\"'").lower()
        for token in text.split()
        if token.strip(".,:;!?()[]{}\"'")
    }


def _first_index(items: list[str], values: set[str]) -> int | None:
    for index, item in enumerate(items):
        if item in values:
            return index
    return None


def _ordered_unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output
