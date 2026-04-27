from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from memorii.core.belief.hybrid_provider import HybridBeliefUpdateProvider
from memorii.core.belief.llm_provider import LLMBeliefUpdateProvider
from memorii.core.belief.models import BeliefUpdateContext
from memorii.core.belief.rule_provider import RuleBasedBeliefUpdateProvider
from memorii.core.llm_decision.models import (
    LLMDecisionMode,
    LLMDecisionPoint,
    LLMDecisionStatus,
    LLMDecisionTrace,
)
from memorii.core.llm_decision.provider import DisabledLLMDecisionProvider
from memorii.core.solver.abstention import SolverDecision
from memorii.core.solver.belief import update_solver_belief


class FakeLLMProvider:
    def __init__(
        self,
        *,
        final_output: dict[str, object] | None = None,
        status: LLMDecisionStatus = LLMDecisionStatus.SUCCEEDED,
        raise_error: bool = False,
    ) -> None:
        self.calls = 0
        self._final_output = final_output if final_output is not None else {}
        self._status = status
        self._raise_error = raise_error

    def decide(
        self,
        *,
        decision_point: LLMDecisionPoint,
        input_payload: dict[str, object],
        prompt_version: str | None = None,
    ) -> LLMDecisionTrace:
        self.calls += 1
        if self._raise_error:
            raise RuntimeError("provider exploded")
        return LLMDecisionTrace(
            trace_id=f"trace:belief:{self.calls}",
            decision_point=decision_point,
            mode=LLMDecisionMode.LLM,
            input_payload=input_payload,
            final_output=self._final_output,
            status=self._status,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )


def _context(**overrides: object) -> BeliefUpdateContext:
    base: dict[str, object] = {
        "prior_belief": 0.5,
        "decision": SolverDecision.SUPPORTED,
        "evidence_count": 1,
        "missing_evidence_count": 0,
        "verifier_downgraded": False,
        "conflict_count": 0,
    }
    base.update(overrides)
    return BeliefUpdateContext.model_validate(base)


def test_rule_provider_matches_update_solver_belief_output() -> None:
    context = _context(
        prior_belief=0.45,
        decision=SolverDecision.NEEDS_TEST,
        evidence_count=2,
        missing_evidence_count=1,
        conflict_count=1,
    )

    decision, _ = RuleBasedBeliefUpdateProvider().update(context=context)

    expected = update_solver_belief(
        prior_belief=context.prior_belief,
        decision=context.decision,
        evidence_count=context.evidence_count,
        missing_evidence_count=context.missing_evidence_count,
        verifier_downgraded=context.verifier_downgraded,
        conflict_count=context.conflict_count,
    )
    assert decision.belief == expected


def test_rule_provider_returns_trace_with_belief_update_decision_point() -> None:
    decision, trace = RuleBasedBeliefUpdateProvider().update(context=_context())
    assert decision.trace_id == trace.trace_id
    assert trace.decision_point == LLMDecisionPoint.BELIEF_UPDATE


def test_disabled_llm_provider_falls_back_safely() -> None:
    provider = LLMBeliefUpdateProvider(llm_provider=DisabledLLMDecisionProvider())
    decision, trace = provider.update(context=_context())
    assert decision.fallback_used is True
    assert trace.fallback_used is True


def test_malformed_llm_output_falls_back_to_rule_provider() -> None:
    provider = LLMBeliefUpdateProvider(
        llm_provider=FakeLLMProvider(
            final_output={"belief": "bad", "confidence": 0.9, "rationale": "bad-output"}
        )
    )

    decision, trace = provider.update(context=_context())
    assert decision.fallback_used is True
    assert trace.status == LLMDecisionStatus.VALIDATION_FAILED


def test_llm_output_clamps_belief_and_confidence() -> None:
    provider = LLMBeliefUpdateProvider(
        llm_provider=FakeLLMProvider(
            final_output={"belief": 1.9, "confidence": -0.4, "rationale": "needs-clamp"}
        )
    )

    decision, trace = provider.update(context=_context())
    assert decision.belief == 1.0
    assert decision.confidence == 0.0
    assert trace.decision_point == LLMDecisionPoint.BELIEF_UPDATE


def test_hybrid_skips_llm_for_simple_low_risk_context() -> None:
    fake_llm = FakeLLMProvider(final_output={"belief": 0.2, "confidence": 0.2, "rationale": "llm"})
    hybrid = HybridBeliefUpdateProvider(llm_provider=LLMBeliefUpdateProvider(llm_provider=fake_llm))

    hybrid.update(context=_context(evidence_count=2, missing_evidence_count=1, conflict_count=0, verifier_downgraded=False))
    assert fake_llm.calls == 0


def test_hybrid_calls_llm_for_verifier_downgrade() -> None:
    fake_llm = FakeLLMProvider(final_output={"belief": 0.3, "confidence": 0.7, "rationale": "llm"})
    hybrid = HybridBeliefUpdateProvider(llm_provider=LLMBeliefUpdateProvider(llm_provider=fake_llm))

    decision, trace = hybrid.update(context=_context(verifier_downgraded=True))
    assert fake_llm.calls == 1
    assert decision.rationale == "llm"
    assert trace.mode == LLMDecisionMode.LLM


def test_hybrid_calls_llm_for_conflicts() -> None:
    fake_llm = FakeLLMProvider(final_output={"belief": 0.4, "confidence": 0.7, "rationale": "llm-conflict"})
    hybrid = HybridBeliefUpdateProvider(llm_provider=LLMBeliefUpdateProvider(llm_provider=fake_llm))

    decision, _ = hybrid.update(context=_context(conflict_count=2))
    assert fake_llm.calls == 1
    assert decision.rationale == "llm-conflict"


def test_trace_always_returned() -> None:
    rule_decision, rule_trace = RuleBasedBeliefUpdateProvider().update(context=_context())
    assert rule_decision.trace_id == rule_trace.trace_id

    llm_decision, llm_trace = LLMBeliefUpdateProvider(llm_provider=DisabledLLMDecisionProvider()).update(context=_context())
    assert llm_trace.trace_id
    assert llm_decision.fallback_used is True


def test_strict_model_validation_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        BeliefUpdateContext(
            decision=SolverDecision.SUPPORTED,
            extra_field="not-allowed",
        )
