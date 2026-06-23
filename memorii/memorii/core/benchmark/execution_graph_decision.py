"""Benchmark-only execution graph decision models and providers."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

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
from memorii.domain.execution_graph.edges import ExecutionEdge
from memorii.domain.execution_graph.nodes import ExecutionNode


class ExecutionGraphExpectation(BaseModel):
    selected_node_ids: list[str] = Field(default_factory=list)
    active_frontier_node_ids: list[str] = Field(default_factory=list)
    blocked_node_ids: list[str] = Field(default_factory=list)
    abandoned_node_ids: list[str] = Field(default_factory=list)
    stale_node_ids: list[str] = Field(default_factory=list)
    resumed_node_id: str | None = None
    next_action_tokens: list[str] = Field(default_factory=list)
    require_resumed_node: bool = False
    require_next_action_tokens: bool = False
    discriminative: bool = False

    model_config = ConfigDict(extra="forbid")


class ExecutionGraphScenario(BaseModel):
    scenario_id: str
    task: str
    family: str
    nodes: list[ExecutionNode]
    edges: list[ExecutionEdge] = Field(default_factory=list)
    recent_events: list[str] = Field(default_factory=list)
    expectation: ExecutionGraphExpectation

    model_config = ConfigDict(extra="forbid")


class ExecutionGraphDecisionContext(BaseModel):
    scenario_id: str
    task: str
    family: str
    nodes: list[ExecutionNode]
    edges: list[ExecutionEdge] = Field(default_factory=list)
    recent_events: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class ExecutionGraphDecision(BaseModel):
    selected_node_ids: list[str] = Field(default_factory=list)
    active_frontier_node_ids: list[str] = Field(default_factory=list)
    blocked_node_ids: list[str] = Field(default_factory=list)
    abandoned_node_ids: list[str] = Field(default_factory=list)
    stale_node_ids: list[str] = Field(default_factory=list)
    resumed_node_id: str | None = None
    next_action: str
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    failure_mode: str | None = None
    requires_judge_review: bool = False

    model_config = ConfigDict(extra="forbid")


def execution_graph_context_for_scenario(
    scenario: ExecutionGraphScenario,
) -> ExecutionGraphDecisionContext:
    return ExecutionGraphDecisionContext(
        scenario_id=scenario.scenario_id,
        task=scenario.task,
        family=scenario.family,
        nodes=scenario.nodes,
        edges=scenario.edges,
        recent_events=scenario.recent_events,
    )


def expected_execution_graph_decision_for_scenario(
    scenario: ExecutionGraphScenario,
) -> ExecutionGraphDecision:
    expected = scenario.expectation
    return ExecutionGraphDecision(
        selected_node_ids=list(expected.selected_node_ids),
        active_frontier_node_ids=list(expected.active_frontier_node_ids),
        blocked_node_ids=list(expected.blocked_node_ids),
        abandoned_node_ids=list(expected.abandoned_node_ids),
        stale_node_ids=list(expected.stale_node_ids),
        resumed_node_id=expected.resumed_node_id,
        next_action=" ".join(expected.next_action_tokens) or "continue selected execution graph work",
        confidence=0.9,
        rationale="expected benchmark execution graph decision",
        failure_mode=None,
        requires_judge_review=False,
    )


def rule_execution_graph_decision_for_scenario(
    scenario: ExecutionGraphScenario,
) -> ExecutionGraphDecision:
    ranked = sorted(
        scenario.nodes,
        key=lambda node: (
            _status_rank(node.status.value),
            -node.updated_at.timestamp(),
            node.id,
        ),
    )
    selected = [ranked[0].id] if ranked else []
    blocked = [
        node.id
        for node in scenario.nodes
        if node.status.value in {"BLOCKED", "WAITING"}
    ]
    return ExecutionGraphDecision(
        selected_node_ids=selected,
        active_frontier_node_ids=selected,
        blocked_node_ids=blocked,
        abandoned_node_ids=[],
        stale_node_ids=[],
        resumed_node_id=selected[0] if selected else None,
        next_action=f"continue {selected[0]}" if selected else "no execution node selected",
        confidence=0.45,
        rationale="rule execution graph provider uses status and recency only; it does not reason over semantic branch state, dependency direction, abandonment, or task handoff",
        failure_mode="rule_limit" if scenario.expectation.discriminative else None,
        requires_judge_review=scenario.expectation.discriminative,
    )


def execution_graph_assertion_passed(
    *,
    scenario: ExecutionGraphScenario,
    decision: dict[str, object],
) -> bool:
    try:
        parsed = ExecutionGraphDecision.model_validate(decision)
    except ValidationError:
        return False

    expected = scenario.expectation
    if list(parsed.selected_node_ids) != list(expected.selected_node_ids):
        return False
    if list(parsed.active_frontier_node_ids) != list(expected.active_frontier_node_ids):
        return False
    selected_or_frontier = set(parsed.selected_node_ids) | set(parsed.active_frontier_node_ids)
    expected_blocked = set(expected.blocked_node_ids)
    expected_suppressed = set(expected.abandoned_node_ids) | set(expected.stale_node_ids)
    if not expected_blocked.issubset(set(parsed.blocked_node_ids)):
        return False
    if expected_blocked & selected_or_frontier:
        return False
    if expected_suppressed & selected_or_frontier:
        return False
    if not expected_suppressed.issubset(
        set(parsed.abandoned_node_ids) | set(parsed.stale_node_ids) | set(parsed.blocked_node_ids)
    ):
        return False
    if expected.require_resumed_node and parsed.resumed_node_id != expected.resumed_node_id:
        return False
    action = f"{parsed.next_action} {' '.join(parsed.selected_node_ids)}".lower()
    if expected.require_next_action_tokens and not all(
        token.lower() in action for token in expected.next_action_tokens
    ):
        return False
    return True


def execution_graph_trace_for_rule(
    *,
    context: ExecutionGraphDecisionContext,
    decision: ExecutionGraphDecision,
    mode: str,
) -> LLMDecisionTrace:
    return LLMDecisionTrace(
        trace_id=f"trace:{uuid4().hex}",
        decision_point=LLMDecisionPoint.EXECUTION_GRAPH_DECISION,
        mode=LLMDecisionMode(mode),
        input_payload=context.model_dump(mode="json"),
        parsed_output=decision.model_dump(mode="json"),
        final_output=decision.model_dump(mode="json"),
        status=LLMDecisionStatus.SUCCEEDED,
        created_at=datetime.now(UTC),
    )


def execution_graph_engine_result_from_llm(
    *,
    result: LLMDecisionResult,
    mode: LLMDecisionMode,
    rule_output: dict[str, object],
) -> tuple[dict[str, object], LLMDecisionTrace, bool, str | None]:
    if not result.success:
        trace = build_llm_decision_trace_from_result(
            decision_point=LLMDecisionPoint.EXECUTION_GRAPH_DECISION,
            mode=mode,
            result=result,
            final_output=rule_output,
            fallback_used=True,
            status=LLMDecisionStatus.PROVIDER_ERROR,
        )
        return rule_output, trace, False, "llm_decision_failed"
    try:
        decision = ExecutionGraphDecision.model_validate(result.output)
    except ValidationError:
        trace = build_llm_decision_trace_from_result(
            decision_point=LLMDecisionPoint.EXECUTION_GRAPH_DECISION,
            mode=mode,
            result=result,
            final_output=rule_output,
            fallback_used=True,
            status=LLMDecisionStatus.VALIDATION_FAILED,
        )
        return rule_output, trace, False, "llm_decision_validation_failed"
    output = decision.model_dump(mode="json")
    trace = build_llm_decision_trace_from_result(
        decision_point=LLMDecisionPoint.EXECUTION_GRAPH_DECISION,
        mode=mode,
        result=result.model_copy(update={"output": output}),
        final_output=output,
        fallback_used=False,
        status=LLMDecisionStatus.SUCCEEDED,
    )
    return output, trace, True, None


def fake_llm_result_for_execution_graph(
    *,
    request: LLMStructuredRequest,
    decision: ExecutionGraphDecision,
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


def _status_rank(status: str) -> int:
    if status == "RUNNING":
        return 0
    if status == "READY":
        return 1
    if status == "WAITING":
        return 2
    if status == "BLOCKED":
        return 3
    if status == "NOT_STARTED":
        return 4
    if status == "FAILED":
        return 5
    if status == "DONE":
        return 6
    return 7
