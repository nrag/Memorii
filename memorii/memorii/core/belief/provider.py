"""Provider interface for explicit solver belief updates."""

from __future__ import annotations

from typing import Protocol

from memorii.core.belief.models import BeliefUpdateContext, BeliefUpdateDecision
from memorii.core.llm_decision.models import LLMDecisionTrace


class BeliefUpdateProvider(Protocol):
    def update(
        self,
        *,
        context: BeliefUpdateContext,
    ) -> tuple[BeliefUpdateDecision, LLMDecisionTrace]: ...
