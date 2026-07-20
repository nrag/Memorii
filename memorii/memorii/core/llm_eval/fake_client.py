"""Deterministic structured client for offline LLM evaluation paths."""

from __future__ import annotations

import json

from memorii.core.belief.models import BeliefUpdateContext
from memorii.core.belief.rule_provider import RuleBasedBeliefUpdateProvider
from memorii.core.llm_config import LLMRuntimeConfig
from memorii.core.llm_provider.models import LLMStructuredRequest, LLMStructuredResponse
from memorii.core.promotion.assessment import PromotionAssessmentContext
from memorii.core.promotion.rule_provider import RuleBasedPromotionAssessmentProvider


def _extract_context_json(*, label: str, text: str) -> dict[str, object]:
    prefix = f"{label}: "
    for line in text.splitlines():
        if line.startswith(prefix):
            parsed = json.loads(line.removeprefix(prefix))
            if isinstance(parsed, dict):
                return parsed
    raise ValueError(f"Missing {label} payload")


class EvalFakeClient:
    """Return rule-derived decisions through the structured-client protocol."""

    provider_name = "fake"

    def complete_structured(
        self,
        request: LLMStructuredRequest,
        *,
        config: LLMRuntimeConfig,
    ) -> LLMStructuredResponse:
        del config
        if request.prompt_ref == "promotion_decision:v1":
            context = PromotionAssessmentContext.model_validate(
                _extract_context_json(label="PromotionAssessmentContext", text=request.user)
            )
            decision, _ = RuleBasedPromotionAssessmentProvider().decide(context=context)
            output = {
                "promote": decision.promote,
                "target_plane": decision.target_plane,
                "confidence": decision.confidence,
                "reason_code": decision.tags[0] if decision.tags else "observation_not_promoted",
                "rationale": decision.rationale,
                "failure_mode": None,
                "requires_judge_review": True,
            }
        elif request.prompt_ref == "belief_update:v1":
            context = BeliefUpdateContext.model_validate(
                _extract_context_json(label="BeliefUpdateContext", text=request.user)
            )
            decision, _ = RuleBasedBeliefUpdateProvider().update(context=context)
            output = {
                "belief": decision.belief,
                "confidence": decision.confidence,
                "rationale": decision.rationale,
                "failure_mode": None,
                "requires_judge_review": True,
            }
        else:
            output = {}

        return LLMStructuredResponse(
            request_id=request.request_id,
            provider=self.provider_name,
            raw_text=json.dumps(output, sort_keys=True),
            valid_json=False,
            schema_valid=False,
        )
