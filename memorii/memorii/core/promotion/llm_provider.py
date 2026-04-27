"""LLM-backed promotion decision provider with safe fallback."""

from __future__ import annotations

from memorii.core.llm_decision.models import LLMDecisionPoint, LLMDecisionStatus, LLMDecisionTrace
from memorii.core.llm_decision.provider import LLMDecisionProvider
from memorii.core.promotion.models import PromotionContext, PromotionDecision
from memorii.core.promotion.rule_provider import RuleBasedPromotionDecisionProvider


class LLMPromotionDecisionProvider:
    def __init__(self, *, llm_provider: LLMDecisionProvider) -> None:
        self._llm_provider = llm_provider
        self._rule_provider = RuleBasedPromotionDecisionProvider()

    def decide(self, *, context: PromotionContext) -> tuple[PromotionDecision, LLMDecisionTrace]:
        input_payload = context.model_dump(mode="json")
        trace = self._llm_provider.decide(
            decision_point=LLMDecisionPoint.PROMOTION,
            input_payload=input_payload,
        )

        fallback_decision, _ = self._rule_provider.decide(context=context)

        if not trace.final_output:
            return fallback_decision, trace.model_copy(
                update={
                    "fallback_used": True,
                    "status": LLMDecisionStatus.FALLBACK_USED,
                    "final_output": fallback_decision.model_dump(mode="json"),
                    "parsed_output": fallback_decision.model_dump(mode="json"),
                    "validation_errors": ["empty llm output"],
                }
            )

        try:
            decision = PromotionDecision.model_validate(trace.final_output)
        except Exception as exc:
            return fallback_decision, trace.model_copy(
                update={
                    "fallback_used": True,
                    "status": LLMDecisionStatus.VALIDATION_FAILED,
                    "final_output": fallback_decision.model_dump(mode="json"),
                    "validation_errors": [str(exc)],
                }
            )

        return decision.model_copy(update={"trace_id": trace.trace_id}), trace
