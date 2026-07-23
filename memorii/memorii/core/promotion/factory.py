"""Promotion execution-policy factory and registration surface."""

from __future__ import annotations

from memorii.core.promotion.interfaces import PromotionExecutionPolicy
from memorii.core.promotion.rule_based import RuleBasedPromotionExecutionPolicy

SUPPORTED_PROMOTION_EXECUTION_POLICIES: tuple[str, ...] = ("rule_based_v1",)


def build_promotion_execution_policy(kind: str) -> PromotionExecutionPolicy:
    """Construct a promotion execution policy by explicit kind."""
    if kind == "rule_based_v1":
        return RuleBasedPromotionExecutionPolicy()
    supported = ", ".join(SUPPORTED_PROMOTION_EXECUTION_POLICIES)
    raise ValueError(f"unsupported promotion execution policy: {kind}. Supported kinds: {supported}")
