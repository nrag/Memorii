"""Promotion decision policy interfaces."""

from __future__ import annotations

from typing import Protocol

from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.promotion.legacy_models import LegacyPromotionContext as PromotionContext, LegacyPromotionDecision as PromotionDecision


class PromotionDecider(Protocol):
    """Policy contract for promotion decisions."""

    def evaluate(
        self,
        *,
        candidate: CanonicalMemoryRecord,
        context: PromotionContext,
    ) -> PromotionDecision:
        """Produce a decision without mutating storage."""
