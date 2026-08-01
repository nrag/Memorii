"""LLM-backed promotion decision provider with safe fallback."""

from __future__ import annotations

from pydantic import ValidationError

from memorii.core.llm_decision.models import LLMDecisionPoint, LLMDecisionStatus, LLMDecisionTrace
from memorii.core.llm_decision.provider import LLMDecisionProvider, LLMDecisionProviderError
from memorii.core.llm_validation import (
    LLMValidationStage,
    domain_validation_issue,
    validation_issues_from_pydantic,
)
from memorii.core.promotion.assessment import PromotionAssessment, PromotionAssessmentContext
from memorii.core.promotion.rule_provider import RuleBasedPromotionAssessmentProvider


class LLMPromotionAssessmentProvider:
    def __init__(self, *, llm_provider: LLMDecisionProvider) -> None:
        self._llm_provider = llm_provider
        self._rule_provider = RuleBasedPromotionAssessmentProvider()

    def decide(self, *, context: PromotionAssessmentContext) -> tuple[PromotionAssessment, LLMDecisionTrace]:
        input_payload = context.prompt_payload()
        try:
            trace = self._llm_provider.decide(
                decision_point=LLMDecisionPoint.PROMOTION,
                input_payload=input_payload,
            )
        except LLMDecisionProviderError:
            fallback_decision, fallback_trace = self._rule_provider.decide(context=context)
            return fallback_decision, fallback_trace.model_copy(
                update={
                    "status": LLMDecisionStatus.PROVIDER_ERROR,
                    "fallback_used": True,
                    "final_output": fallback_decision.model_dump(mode="json"),
                    "parsed_output": fallback_decision.model_dump(mode="json"),
                    "validation_issues": [
                        domain_validation_issue(
                            "promotion provider failed",
                            code="provider_error",
                        )
                    ],
                }
            )

        fallback_decision, _ = self._rule_provider.decide(context=context)

        if not trace.final_output:
            return fallback_decision, trace.model_copy(
                update={
                    "fallback_used": True,
                    "status": LLMDecisionStatus.FALLBACK_USED,
                    "final_output": fallback_decision.model_dump(mode="json"),
                    "parsed_output": fallback_decision.model_dump(mode="json"),
                    "validation_issues": [
                        domain_validation_issue("empty llm output", code="empty_output")
                    ],
                }
            )

        try:
            decision = PromotionAssessment.model_validate(trace.final_output)
        except ValidationError as exc:
            return fallback_decision, trace.model_copy(
                update={
                    "fallback_used": True,
                    "status": LLMDecisionStatus.VALIDATION_FAILED,
                    "final_output": fallback_decision.model_dump(mode="json"),
                    "validation_issues": list(
                        validation_issues_from_pydantic(
                            exc,
                            stage=LLMValidationStage.DOMAIN,
                        )
                    ),
                }
            )

        return decision.model_copy(update={"trace_id": trace.trace_id}), trace
