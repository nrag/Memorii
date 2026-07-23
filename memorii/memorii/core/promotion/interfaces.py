"""Policies that plan promotion mutations without applying them."""

from __future__ import annotations

from typing import Protocol

from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.promotion.execution_contracts import PromotionExecutionContext, PromotionExecutionPlan


class PromotionExecutionPolicy(Protocol):
    """Policy contract for planning promotion execution."""

    def evaluate(
        self,
        *,
        candidate: CanonicalMemoryRecord,
        context: PromotionExecutionContext,
    ) -> PromotionExecutionPlan:
        """Produce an execution plan without mutating storage."""
        ...
