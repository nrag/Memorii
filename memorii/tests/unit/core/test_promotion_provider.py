from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from memorii.core.llm_decision.models import (
    LLMDecisionMode,
    LLMDecisionPoint,
    LLMDecisionStatus,
    LLMDecisionTrace,
)
from memorii.core.llm_decision.provider import DisabledLLMDecisionProvider
from memorii.core.promotion.hybrid_provider import HybridPromotionDecisionProvider
from memorii.core.promotion.llm_provider import LLMPromotionDecisionProvider
from memorii.core.promotion.models import PromotionCandidateType, PromotionContext
from memorii.core.promotion.rule_provider import RuleBasedPromotionDecisionProvider


class FakeLLMProvider:
    def __init__(self, *, final_output: dict[str, object], status: LLMDecisionStatus = LLMDecisionStatus.SUCCEEDED) -> None:
        self.calls = 0
        self._final_output = final_output
        self._status = status

    def decide(
        self,
        *,
        decision_point: LLMDecisionPoint,
        input_payload: dict[str, object],
        prompt_version: str | None = None,
    ) -> LLMDecisionTrace:
        self.calls += 1
        return LLMDecisionTrace(
            trace_id=f"trace:fake:{self.calls}",
            decision_point=decision_point,
            mode=LLMDecisionMode.LLM,
            input_payload=input_payload,
            final_output=self._final_output,
            status=self._status,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )


def _context(**overrides: object) -> PromotionContext:
    base: dict[str, object] = {
        "candidate_id": "cand:1",
        "candidate_type": PromotionCandidateType.EPISODIC,
        "content": "something happened",
        "created_from": "observation",
    }
    base.update(overrides)
    return PromotionContext.model_validate(base)


def test_decision_finalized_always_promotes() -> None:
    provider = RuleBasedPromotionDecisionProvider()
    decision, _ = provider.decide(context=_context(created_from="decision_finalized"))
    assert decision.promote is True
    assert decision.rationale == "decision_finalized"


def test_task_outcome_promotes() -> None:
    provider = RuleBasedPromotionDecisionProvider()
    decision, _ = provider.decide(context=_context(created_from="task_outcome"))
    assert decision.promote is True


def test_explicit_user_memory_promotes() -> None:
    provider = RuleBasedPromotionDecisionProvider()
    decision, _ = provider.decide(
        context=_context(
            candidate_type=PromotionCandidateType.USER_MEMORY,
            explicit_user_memory_request=True,
        )
    )
    assert decision.promote is True
    assert decision.confidence == 0.9


def test_repeated_across_episodes_promotes() -> None:
    provider = RuleBasedPromotionDecisionProvider()
    decision, _ = provider.decide(
        context=_context(
            candidate_type=PromotionCandidateType.SEMANTIC,
            repeated_across_episodes=3,
        )
    )
    assert decision.promote is True
    assert decision.rationale == "repeated_across_episodes"


def test_observation_alone_not_promoted() -> None:
    provider = RuleBasedPromotionDecisionProvider()
    decision, _ = provider.decide(context=_context(created_from="observation"))
    assert decision.promote is False
    assert decision.rationale == "observation_not_promoted"


def test_llm_provider_with_disabled_provider_falls_back_safely() -> None:
    provider = LLMPromotionDecisionProvider(llm_provider=DisabledLLMDecisionProvider())
    decision, trace = provider.decide(context=_context())
    assert decision.promote is False
    assert trace.fallback_used is True


def test_malformed_llm_output_falls_back_to_rule_provider() -> None:
    provider = LLMPromotionDecisionProvider(llm_provider=FakeLLMProvider(final_output={"promote": "not_bool"}))
    decision, trace = provider.decide(context=_context())
    assert decision.promote is False
    assert trace.status == LLMDecisionStatus.VALIDATION_FAILED


def test_hybrid_skips_llm_for_strong_rule_decision() -> None:
    fake_llm = FakeLLMProvider(final_output={"promote": False, "confidence": 0.2, "rationale": "llm"})
    hybrid = HybridPromotionDecisionProvider(llm_provider=LLMPromotionDecisionProvider(llm_provider=fake_llm))

    decision, _ = hybrid.decide(
        context=_context(
            candidate_type=PromotionCandidateType.USER_MEMORY,
            explicit_user_memory_request=True,
        )
    )
    assert decision.promote is True
    assert fake_llm.calls == 0


def test_hybrid_uses_llm_for_weak_rule_decision() -> None:
    fake_llm = FakeLLMProvider(
        final_output={
            "promote": True,
            "target_plane": "semantic",
            "confidence": 0.88,
            "rationale": "llm_override",
        }
    )
    hybrid = HybridPromotionDecisionProvider(llm_provider=LLMPromotionDecisionProvider(llm_provider=fake_llm))

    decision, trace = hybrid.decide(context=_context(candidate_type=PromotionCandidateType.SEMANTIC))
    assert decision.promote is True
    assert trace.mode == LLMDecisionMode.LLM
    assert fake_llm.calls == 1


def test_trace_always_returned() -> None:
    decision, trace = RuleBasedPromotionDecisionProvider().decide(context=_context())
    assert decision.trace_id == trace.trace_id


def test_strict_model_validation_works() -> None:
    with pytest.raises(ValidationError):
        PromotionContext(
            candidate_id="cand:strict",
            candidate_type=PromotionCandidateType.EPISODIC,
            content="x",
            created_from="observation",
            extra_field="nope",
        )
