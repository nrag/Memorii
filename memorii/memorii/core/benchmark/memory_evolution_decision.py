"""Benchmark-only memory evolution decision models and deterministic providers."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from enum import Enum
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
    checkpoint: MemoryEvolutionCheckpoint
    metadata: dict[str, object] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class MemoryEvolutionDecision(BaseModel):
    selected_memory_ids: list[str] = Field(default_factory=list)
    answer: str | None = None
    next_action: str | None = None
    citation_memory_ids: list[str] = Field(default_factory=list)
    active_memory_ids: list[str] = Field(default_factory=list)
    inactive_memory_ids: list[str] = Field(default_factory=list)
    archived_memory_ids: list[str] = Field(default_factory=list)
    belief_scores: list[MemoryEvolutionBeliefScore] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    failure_mode: str | None = None
    requires_judge_review: bool = False

    model_config = ConfigDict(extra="forbid")


def memory_evolution_context_for_checkpoint(
    *,
    scenario: MemoryEvolutionScenario,
    checkpoint: MemoryEvolutionCheckpoint,
) -> MemoryEvolutionDecisionContext:
    return MemoryEvolutionDecisionContext(
        scenario_id=scenario.scenario_id,
        family=scenario.family,
        events=scenario.events,
        checkpoint=checkpoint,
        metadata={"discriminative": scenario.discriminative},
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
    try:
        parsed = MemoryEvolutionDecision.model_validate(decision)
    except ValidationError:
        return False

    if checkpoint.expected_answer is not None and not _answer_matches_expected(
        actual=parsed.answer,
        expected=checkpoint.expected_answer,
    ):
        return False
    if checkpoint.expected_next_action is not None:
        action = _norm(parsed.next_action)
        if not all(token in action.split() for token in _norm(checkpoint.expected_next_action).split()):
            return False

    selected_ids = list(parsed.selected_memory_ids)
    selected = set(selected_ids)
    expected_retrieval = list(checkpoint.expected_retrieval_ids)
    is_belief_ranking = bool(checkpoint.expected_belief_ranking)
    if scenario.discriminative and expected_retrieval and not is_belief_ranking:
        if selected_ids != expected_retrieval:
            return False
    elif expected_retrieval:
        retrieved = selected | set(parsed.active_memory_ids)
        if is_belief_ranking:
            retrieved |= {score.memory_id for score in parsed.belief_scores}
        if not set(expected_retrieval).issubset(retrieved):
            return False

    if selected & set(checkpoint.expected_excluded_memory_ids):
        return False
    if checkpoint.expected_citation_ids:
        if scenario.discriminative:
            if list(parsed.citation_memory_ids) != list(checkpoint.expected_citation_ids):
                return False
        elif not set(checkpoint.expected_citation_ids).issubset(set(parsed.citation_memory_ids)):
            return False
    if not set(checkpoint.expected_active_memory_ids).issubset(
        set(parsed.active_memory_ids) | selected
    ):
        return False
    if set(checkpoint.expected_inactive_memory_ids) & set(parsed.active_memory_ids):
        return False
    if not set(checkpoint.expected_archived_memory_ids).issubset(set(parsed.archived_memory_ids)):
        return False
    if checkpoint.expected_belief_ranking:
        score_by_id = {score.memory_id: score.belief for score in parsed.belief_scores}
        if not set(checkpoint.expected_belief_ranking).issubset(score_by_id):
            return False
        ranked = sorted(score_by_id, key=lambda key: (-score_by_id[key], key))
        if ranked[: len(checkpoint.expected_belief_ranking)] != checkpoint.expected_belief_ranking:
            return False
    if checkpoint.expected_belief_scores:
        score_by_id = {score.memory_id: score.belief for score in parsed.belief_scores}
        for memory_id, expected in checkpoint.expected_belief_scores.items():
            actual = score_by_id.get(memory_id)
            if actual is None or abs(actual - expected) > 0.05:
                return False
    return True


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


def _answer_matches_expected(*, actual: str | None, expected: str) -> bool:
    actual_norm = _norm(actual)
    expected_norm = _norm(expected)
    if actual_norm == expected_norm:
        return True
    actual_tokens = set(actual_norm.split())
    expected_tokens = set(expected_norm.split())
    if not expected_tokens:
        return True
    return expected_tokens.issubset(actual_tokens)
