"""LLM-backed belief update provider skeleton with safe deterministic fallback."""

from __future__ import annotations

from pydantic import ValidationError

from memorii.core.belief.models import BeliefUpdateContext, BeliefUpdateDecision
from memorii.core.belief.provider import BeliefUpdateProvider
from memorii.core.belief.rule_provider import RuleBasedBeliefUpdateProvider
from memorii.core.llm_decision.models import LLMDecisionMode, LLMDecisionPoint, LLMDecisionStatus, LLMDecisionTrace
from memorii.core.llm_decision.provider import LLMDecisionProvider, LLMDecisionProviderError


class LLMBeliefUpdateProvider:
    def __init__(
        self,
        *,
        llm_provider: LLMDecisionProvider,
        fallback_provider: BeliefUpdateProvider | None = None,
    ) -> None:
        self._llm_provider = llm_provider
        self._fallback_provider = fallback_provider or RuleBasedBeliefUpdateProvider()

    def update(self, *, context: BeliefUpdateContext) -> tuple[BeliefUpdateDecision, LLMDecisionTrace]:
        input_payload = context.prompt_payload()

        try:
            trace = self._llm_provider.decide(
                decision_point=LLMDecisionPoint.BELIEF_UPDATE,
                input_payload=input_payload,
            )
        except LLMDecisionProviderError as exc:
            fallback_decision, fallback_trace = self._fallback_provider.update(context=context)
            return fallback_decision.model_copy(update={"fallback_used": True}), fallback_trace.model_copy(
                update={
                    "mode": LLMDecisionMode.LLM,
                    "status": LLMDecisionStatus.PROVIDER_ERROR,
                    "fallback_used": True,
                    "validation_errors": [str(exc)],
                    "final_output": fallback_decision.model_dump(mode="json"),
                    "parsed_output": fallback_decision.model_dump(mode="json"),
                }
            )

        fallback_decision, _ = self._fallback_provider.update(context=context)
        if not trace.final_output:
            return fallback_decision.model_copy(update={"fallback_used": True}), trace.model_copy(
                update={
                    "fallback_used": True,
                    "status": LLMDecisionStatus.FALLBACK_USED,
                    "final_output": fallback_decision.model_dump(mode="json"),
                    "parsed_output": fallback_decision.model_dump(mode="json"),
                    "validation_errors": ["empty llm output"],
                }
            )

        try:
            parsed = BeliefUpdateDecision.model_validate(trace.final_output)
        except ValidationError as exc:
            return fallback_decision.model_copy(update={"fallback_used": True}), trace.model_copy(
                update={
                    "fallback_used": True,
                    "status": LLMDecisionStatus.VALIDATION_FAILED,
                    "final_output": fallback_decision.model_dump(mode="json"),
                    "parsed_output": fallback_decision.model_dump(mode="json"),
                    "validation_errors": [str(exc)],
                }
            )

        decision = parsed.model_copy(update={"trace_id": trace.trace_id})

        return decision, trace.model_copy(update={"parsed_output": decision.model_dump(mode="json")})
