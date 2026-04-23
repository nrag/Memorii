"""Placeholder hybrid promotion decider contract.

Future intent:
- Keep fast deterministic rule handling for obvious safe decisions.
- Delegate ambiguous cases to an LLM-backed decider.
- Return the same PromotionDecision contract regardless of internal strategy.
"""

from __future__ import annotations

from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.promotion.models import PromotionContext, PromotionDecision


class HybridPromotionDecider:
    """Stub implementation to make planned hybrid integration explicit."""

    def evaluate(self, *, candidate: CanonicalMemoryRecord, context: PromotionContext) -> PromotionDecision:
        raise NotImplementedError("hybrid_v1 decider is not implemented yet")
