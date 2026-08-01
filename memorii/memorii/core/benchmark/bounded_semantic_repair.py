"""Mechanically bounded repair orchestration for benchmark semantic decisions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

from pydantic import BaseModel

from memorii.core.llm_decision.models import LLMDecisionTrace
from memorii.core.llm_provider.models import LLMDecisionResult

ContextT = TypeVar("ContextT", bound=BaseModel)


@dataclass(frozen=True)
class SemanticDecisionAttempt:
    provider_result: LLMDecisionResult
    output: dict[str, object]
    trace: LLMDecisionTrace
    success: bool
    failure_mode: str | None


@dataclass(frozen=True)
class BoundedSemanticDecisionResult(Generic[ContextT]):
    attempts: tuple[SemanticDecisionAttempt, ...]
    final_context: ContextT

    @property
    def final_attempt(self) -> SemanticDecisionAttempt:
        return self.attempts[-1]


def run_with_one_semantic_repair(
    *,
    context: ContextT,
    request_id: str,
    metadata: dict[str, object],
    decide: Callable[[ContextT, str, dict[str, object]], LLMDecisionResult],
    evaluate: Callable[
        [LLMDecisionResult, ContextT],
        tuple[dict[str, object], LLMDecisionTrace, bool, str | None],
    ],
    build_repair_context: Callable[[ContextT, dict[str, object], list[str]], ContextT],
) -> BoundedSemanticDecisionResult[ContextT]:
    """Run a primary decision and at most one targeted semantic repair."""

    primary = decide(context, request_id, metadata)
    output, trace, success, failure_mode = evaluate(primary, context)
    attempts = [
        SemanticDecisionAttempt(
            provider_result=primary,
            output=output,
            trace=trace,
            success=success,
            failure_mode=failure_mode,
        )
    ]
    final_context = context
    if failure_mode == "llm_semantic_validation_failed" and primary.success and primary.output is not None:
        final_context = build_repair_context(
            context,
            primary.output,
            [issue.code for issue in trace.validation_issues],
        )
        repair = decide(
            final_context,
            f"{request_id}:repair",
            {**metadata, "semantic_repair_attempt": 1},
        )
        output, trace, success, failure_mode = evaluate(repair, final_context)
        attempts.append(
            SemanticDecisionAttempt(
                provider_result=repair,
                output=output,
                trace=trace,
                success=success,
                failure_mode=failure_mode,
            )
        )
    return BoundedSemanticDecisionResult(
        attempts=tuple(attempts),
        final_context=final_context,
    )
