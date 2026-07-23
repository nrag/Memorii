from __future__ import annotations

import json
from datetime import UTC, datetime

from memorii.core.benchmark.bounded_semantic_repair import run_with_one_semantic_repair
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
from memorii.core.llm_validation import LLMValidationIssue, LLMValidationStage
from memorii.core.prompts.models import PromptModelDefaults
from pydantic import BaseModel, ConfigDict, Field


class _RepairContext(BaseModel):
    repaired: bool = False
    violation_codes: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


def _provider_result(
    *,
    request_id: str,
    output: dict[str, object] | None,
    success: bool = True,
    failure_mode: str | None = None,
) -> LLMDecisionResult:
    request = LLMStructuredRequest(
        request_id=request_id,
        prompt_ref="test:v1",
        prompt_hash="test",
        system="system",
        user="user",
        output_schema={},
        model_defaults=PromptModelDefaults(model="test-model"),
    )
    return LLMDecisionResult(
        request=request,
        response=LLMStructuredResponse(
            request_id=request_id,
            provider="fake",
            raw_text=json.dumps(output),
            parsed_json=output,
            valid_json=output is not None,
            schema_valid=output is not None,
            error=None if success else failure_mode,
        ),
        output=output,
        success=success,
        failure_mode=failure_mode,
    )


def _trace(*, valid: bool, violations: list[str]) -> LLMDecisionTrace:
    return LLMDecisionTrace(
        trace_id=f"trace:{len(violations)}",
        decision_point=LLMDecisionPoint.MEMORY_EVOLUTION_DECISION,
        mode=LLMDecisionMode.LLM,
        input_payload={},
        validation_issues=[
            LLMValidationIssue(
                stage=LLMValidationStage.SEMANTIC,
                code=code,
                message=code.replace("_", " "),
            )
            for code in violations
        ],
        final_output={},
        status=LLMDecisionStatus.SUCCEEDED if valid else LLMDecisionStatus.VALIDATION_FAILED,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _evaluate(
    result: LLMDecisionResult,
    _context: _RepairContext,
) -> tuple[dict[str, object], LLMDecisionTrace, bool, str | None]:
    if not result.success or result.output is None:
        return {}, _trace(valid=False, violations=[]), False, result.failure_mode
    valid = result.output.get("choice") == "valid"
    violations = [] if valid else ["invalid_choice"]
    return (
        result.output,
        _trace(valid=valid, violations=violations),
        valid,
        None if valid else "llm_semantic_validation_failed",
    )


def _repair_context(
    context: _RepairContext,
    _output: dict[str, object],
    violation_codes: list[str],
) -> _RepairContext:
    return context.model_copy(update={"repaired": True, "violation_codes": violation_codes})


def test_clean_primary_does_not_consume_repair_budget() -> None:
    calls: list[str] = []

    def decide(_context: _RepairContext, request_id: str, _metadata: dict[str, object]) -> LLMDecisionResult:
        calls.append(request_id)
        return _provider_result(request_id=request_id, output={"choice": "valid"})

    resolution = run_with_one_semantic_repair(
        context=_RepairContext(),
        request_id="request",
        metadata={},
        decide=decide,
        evaluate=_evaluate,
        build_repair_context=_repair_context,
    )

    assert calls == ["request"]
    assert len(resolution.attempts) == 1
    assert resolution.final_attempt.success is True
    assert resolution.final_context.repaired is False


def test_semantic_failure_gets_exactly_one_targeted_repair() -> None:
    calls: list[tuple[str, _RepairContext, dict[str, object]]] = []

    def decide(context: _RepairContext, request_id: str, metadata: dict[str, object]) -> LLMDecisionResult:
        calls.append((request_id, context, metadata))
        choice = "valid" if context.repaired else "invalid"
        return _provider_result(request_id=request_id, output={"choice": choice})

    resolution = run_with_one_semantic_repair(
        context=_RepairContext(),
        request_id="request",
        metadata={"suite": "test"},
        decide=decide,
        evaluate=_evaluate,
        build_repair_context=_repair_context,
    )

    assert [call[0] for call in calls] == ["request", "request:repair"]
    assert calls[1][1].violation_codes == ["invalid_choice"]
    assert calls[1][2]["semantic_repair_attempt"] == 1
    assert len(resolution.attempts) == 2
    assert resolution.final_attempt.success is True


def test_exhausted_repair_stops_after_two_attempts() -> None:
    calls: list[str] = []

    def decide(_context: _RepairContext, request_id: str, _metadata: dict[str, object]) -> LLMDecisionResult:
        calls.append(request_id)
        return _provider_result(request_id=request_id, output={"choice": "invalid"})

    resolution = run_with_one_semantic_repair(
        context=_RepairContext(),
        request_id="request",
        metadata={},
        decide=decide,
        evaluate=_evaluate,
        build_repair_context=_repair_context,
    )

    assert calls == ["request", "request:repair"]
    assert len(resolution.attempts) == 2
    assert resolution.final_attempt.success is False
    assert resolution.final_attempt.failure_mode == "llm_semantic_validation_failed"


def test_transport_failure_never_triggers_semantic_repair() -> None:
    calls: list[str] = []

    def decide(_context: _RepairContext, request_id: str, _metadata: dict[str, object]) -> LLMDecisionResult:
        calls.append(request_id)
        return _provider_result(
            request_id=request_id,
            output=None,
            success=False,
            failure_mode="provider_error",
        )

    resolution = run_with_one_semantic_repair(
        context=_RepairContext(),
        request_id="request",
        metadata={},
        decide=decide,
        evaluate=_evaluate,
        build_repair_context=_repair_context,
    )

    assert calls == ["request"]
    assert len(resolution.attempts) == 1
    assert resolution.final_attempt.failure_mode == "provider_error"
