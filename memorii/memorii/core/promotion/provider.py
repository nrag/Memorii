"""Provider interface for explicit promotion decisions."""

from __future__ import annotations

from typing import Protocol

from memorii.core.llm_decision.models import LLMDecisionTrace
from memorii.core.promotion.models import PromotionContext, PromotionDecision


class PromotionDecisionProvider(Protocol):
    def decide(
        self,
        *,
        context: PromotionContext,
    ) -> tuple[PromotionDecision, LLMDecisionTrace]: ...
