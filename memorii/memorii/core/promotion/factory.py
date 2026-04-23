"""Promotion decider factory and registration surface."""

from __future__ import annotations

from memorii.core.promotion.interfaces import PromotionDecider
from memorii.core.promotion.rule_based import RuleBasedPromotionDecider

SUPPORTED_PROMOTION_DECIDERS: tuple[str, ...] = ("rule_based_v1", "llm_v1", "hybrid_v1")


def build_promotion_decider(kind: str) -> PromotionDecider:
    """Construct a promotion decider by explicit kind.

    `llm_v1` and `hybrid_v1` are intentionally reserved for future implementations.
    """
    if kind == "rule_based_v1":
        return RuleBasedPromotionDecider()
    if kind in {"llm_v1", "hybrid_v1"}:
        raise ValueError(
            f"promotion decider '{kind}' is not implemented yet; use 'rule_based_v1' for now"
        )
    supported = ", ".join(SUPPORTED_PROMOTION_DECIDERS)
    raise ValueError(f"unsupported promotion decider kind: {kind}. Supported kinds: {supported}")
