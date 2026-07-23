"""Hybrid promotion provider that uses rule-first short-circuiting."""

from __future__ import annotations

from memorii.core.llm_decision.models import LLMDecisionMode, LLMDecisionStatus, LLMDecisionTrace
from memorii.core.promotion.assessment import PromotionAssessment, PromotionAssessmentContext
from memorii.core.promotion.llm_provider import LLMPromotionAssessmentProvider
from memorii.core.promotion.rule_provider import RuleBasedPromotionAssessmentProvider


class HybridPromotionAssessmentProvider:
    def __init__(
        self,
        *,
        llm_provider: LLMPromotionAssessmentProvider,
        strong_rule_threshold: float = 0.8,
    ) -> None:
        self._rule_provider = RuleBasedPromotionAssessmentProvider()
        self._llm_provider = llm_provider
        self._strong_rule_threshold = strong_rule_threshold

    def decide(self, *, context: PromotionAssessmentContext) -> tuple[PromotionAssessment, LLMDecisionTrace]:
        rule_decision, rule_trace = self._rule_provider.decide(context=context)
        if rule_decision.confidence >= self._strong_rule_threshold:
            return rule_decision, rule_trace

        llm_decision, llm_trace = self._llm_provider.decide(context=context)
        if llm_trace.status in {LLMDecisionStatus.PROVIDER_ERROR, LLMDecisionStatus.VALIDATION_FAILED}:
            return rule_decision, rule_trace.model_copy(
                update={
                    "mode": LLMDecisionMode.HYBRID,
                    "status": LLMDecisionStatus.FALLBACK_USED,
                    "fallback_used": True,
                    "final_output": rule_decision.model_dump(mode="json"),
                }
            )
        return llm_decision, llm_trace
