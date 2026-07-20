from __future__ import annotations

from memorii.core.belief.hybrid_provider import HybridBeliefUpdateProvider
from memorii.core.belief.rule_provider import RuleBasedBeliefUpdateProvider
from memorii.core.llm_decision.runtime_factory import (
    build_belief_update_provider_from_env,
    build_promotion_decision_provider_from_env,
)
from memorii.core.promotion.hybrid_provider import HybridPromotionAssessmentProvider
from memorii.core.promotion.rule_provider import RuleBasedPromotionAssessmentProvider


def _set_process_env(monkeypatch, **values: str) -> None:
    for key in [
        "MEMORII_SECRET_SOURCE",
        "MEMORII_LLM_PROVIDER",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "MEMORII_DECISION_MODE",
    ]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("MEMORII_SECRET_SOURCE", "process")
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_runtime_factory_auto_uses_rule_without_llm_config(monkeypatch) -> None:
    _set_process_env(monkeypatch, MEMORII_LLM_PROVIDER="none")

    assert isinstance(build_promotion_decision_provider_from_env(), RuleBasedPromotionAssessmentProvider)
    assert isinstance(build_belief_update_provider_from_env(), RuleBasedBeliefUpdateProvider)


def test_runtime_factory_auto_uses_hybrid_with_llm_config(monkeypatch) -> None:
    _set_process_env(monkeypatch, MEMORII_LLM_PROVIDER="openai", OPENAI_API_KEY="test-key")

    assert isinstance(build_promotion_decision_provider_from_env(), HybridPromotionAssessmentProvider)
    assert isinstance(build_belief_update_provider_from_env(), HybridBeliefUpdateProvider)


def test_runtime_factory_explicit_hybrid_falls_back_to_rule_without_llm_config(monkeypatch) -> None:
    _set_process_env(monkeypatch, MEMORII_LLM_PROVIDER="none", MEMORII_DECISION_MODE="hybrid")

    assert isinstance(build_promotion_decision_provider_from_env(), RuleBasedPromotionAssessmentProvider)
    assert isinstance(build_belief_update_provider_from_env(), RuleBasedBeliefUpdateProvider)
