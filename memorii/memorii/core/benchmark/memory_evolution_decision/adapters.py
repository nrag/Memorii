"""LLM and trace adapters for hand-authored memory-evolution decisions."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import ValidationError

from memorii.core.benchmark.memory_evolution_decision.contracts import (
    MemoryEvolutionDecision,
    MemoryEvolutionDecisionContext,
    MemoryEvolutionSemanticDecision,
)
from memorii.core.benchmark.memory_evolution_decision.semantic_pipeline import (
    compile_memory_evolution_decision,
    render_memory_evolution_answer,
    validate_memory_evolution_semantic_decision,
)
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
from memorii.core.llm_validation import LLMValidationIssue, LLMValidationStage


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
    context: MemoryEvolutionDecisionContext,
    rule_output: dict[str, object],
) -> tuple[dict[str, object], LLMDecisionTrace, bool, str | None]:
    if not result.success:
        failure_status = (
            LLMDecisionStatus.PROVIDER_ERROR
            if result.failure_mode == "provider_error"
            else LLMDecisionStatus.VALIDATION_FAILED
        )
        trace = build_llm_decision_trace_from_result(
            decision_point=LLMDecisionPoint.MEMORY_EVOLUTION_DECISION,
            mode=mode,
            result=result,
            final_output=rule_output,
            fallback_used=True,
            status=failure_status,
        )
        return rule_output, trace, False, result.failure_mode or "llm_decision_failed"
    try:
        semantic = MemoryEvolutionSemanticDecision.model_validate(result.output)
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
    validation = validate_memory_evolution_semantic_decision(context=context, semantic=semantic)
    if not validation.valid:
        trace = build_llm_decision_trace_from_result(
            decision_point=LLMDecisionPoint.MEMORY_EVOLUTION_DECISION,
            mode=mode,
            result=result,
            final_output=rule_output,
            fallback_used=True,
            status=LLMDecisionStatus.VALIDATION_FAILED,
        )
        trace.validation_issues.extend(
            LLMValidationIssue(
                stage=LLMValidationStage.SEMANTIC,
                code=code.value,
                message=code.value.replace("_", " "),
            )
            for code in validation.violation_codes
        )
        return rule_output, trace, False, "llm_semantic_validation_failed"
    decision = render_memory_evolution_answer(
        decision=compile_memory_evolution_decision(context=context, semantic=semantic),
        semantic=semantic,
    )
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
    decision: MemoryEvolutionSemanticDecision,
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
