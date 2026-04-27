"""Hybrid belief updater that applies deterministic routing to rule or LLM paths."""

from __future__ import annotations

from memorii.core.belief.llm_provider import LLMBeliefUpdateProvider
from memorii.core.belief.models import BeliefUpdateContext, BeliefUpdateDecision
from memorii.core.belief.rule_provider import RuleBasedBeliefUpdateProvider
from memorii.core.llm_decision.models import LLMDecisionMode, LLMDecisionStatus, LLMDecisionTrace


class HybridBeliefUpdateProvider:
    def __init__(self, *, llm_provider: LLMBeliefUpdateProvider) -> None:
        self._rule_provider = RuleBasedBeliefUpdateProvider()
        self._llm_provider = llm_provider

    def update(self, *, context: BeliefUpdateContext) -> tuple[BeliefUpdateDecision, LLMDecisionTrace]:
        rule_decision, rule_trace = self._rule_provider.update(context=context)
        if self._is_simple_low_risk(context=context):
            return rule_decision, rule_trace

        llm_decision, llm_trace = self._llm_provider.update(context=context)
        if llm_trace.status in {
            LLMDecisionStatus.PROVIDER_ERROR,
            LLMDecisionStatus.VALIDATION_FAILED,
            LLMDecisionStatus.FALLBACK_USED,
        }:
            return rule_decision.model_copy(update={"fallback_used": True}), rule_trace.model_copy(
                update={
                    "mode": LLMDecisionMode.HYBRID,
                    "status": LLMDecisionStatus.FALLBACK_USED,
                    "fallback_used": True,
                    "final_output": rule_decision.model_dump(mode="json"),
                    "validation_errors": llm_trace.validation_errors,
                }
            )

        return llm_decision, llm_trace

    @staticmethod
    def _is_simple_low_risk(*, context: BeliefUpdateContext) -> bool:
        return (
            context.verifier_downgraded is False
            and context.conflict_count == 0
            and context.missing_evidence_count <= 1
            and context.evidence_count >= 1
        )
