"""Provider interface for explicit promotion decisions."""

from __future__ import annotations

from typing import Protocol

from memorii.core.llm_decision.models import LLMDecisionTrace
from memorii.core.promotion.assessment import PromotionAssessment, PromotionAssessmentContext


class PromotionAssessmentProviderError(RuntimeError):
    """Expected operational failure from a promotion provider."""


class PromotionAssessmentProvider(Protocol):
    def decide(
        self,
        *,
        context: PromotionAssessmentContext,
    ) -> tuple[PromotionAssessment, LLMDecisionTrace]: ...
