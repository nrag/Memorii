from datetime import UTC, datetime

from memorii.core.belief.models import BeliefUpdateContext
from memorii.core.llm_decision.models import EvalSnapshot, LLMDecisionMode, LLMDecisionPoint
from memorii.core.llm_eval.runner import BeliefUpdateEngine, OfflineLLMEvalRunner, PromotionDecisionEngine
from memorii.core.llm_provider.models import LLMDecisionResult, LLMStructuredRequest, LLMStructuredResponse
from memorii.core.promotion.models import PromotionCandidateType, PromotionContext
from memorii.core.solver.abstention import SolverDecision




def _llm_result(*, request_id: str, success: bool, output: dict[str, object]) -> LLMDecisionResult:
    request = LLMStructuredRequest(request_id=request_id, prompt_ref="p:v1", prompt_hash="h", system="s", user="u", output_schema={}, model_defaults={})
    response = LLMStructuredResponse(request_id=request_id, provider="fake", raw_text="{}", parsed_json=output if success else None, valid_json=success, schema_valid=success)
    return LLMDecisionResult(request=request, response=response, output=output if success else None, success=success, failure_mode=None if success else "provider_error")

class StubPromotionAdapter:
    def __init__(self, *, success: bool, output: dict[str, object]):
        self.success = success
        self.output = output
        self.calls = 0

    def decide(self, *, context, request_id, metadata=None):
        self.calls += 1
        return _llm_result(request_id=request_id, success=self.success, output=self.output)


class StubBeliefAdapter:
    def __init__(self, *, success: bool, output: dict[str, object]):
        self.success = success
        self.output = output
        self.calls = 0

    def update(self, *, context, request_id, metadata=None):
        self.calls += 1
        return _llm_result(request_id=request_id, success=self.success, output=self.output)


def _promotion_context() -> PromotionContext:
    return PromotionContext(candidate_id="c1", candidate_type=PromotionCandidateType.SEMANTIC, content="fact", created_from="observation")


def _belief_context() -> BeliefUpdateContext:
    return BeliefUpdateContext(decision=SolverDecision.SUPPORTED, evidence_count=2)


def test_rule_mode_uses_only_rule_engine() -> None:
    adapter = StubPromotionAdapter(success=True, output={"promote": False, "confidence": 0.1, "rationale": "llm"})
    res = PromotionDecisionEngine(rule_engine=OfflineLLMEvalRunner()._promotion_provider, llm_adapter=adapter, mode=LLMDecisionMode.RULE).decide(_promotion_context(), "r1")
    assert res.llm_used is False and res.fallback_used is False and adapter.calls == 0 and res.decision["promote"] is False


def test_llm_mode_and_fallback_and_hybrid_disagreement() -> None:
    pctx = _promotion_context()
    llm_ok = StubPromotionAdapter(success=True, output={"promote": True, "target_plane": "semantic", "confidence": 0.95, "rationale": "llm"})
    res = PromotionDecisionEngine(rule_engine=OfflineLLMEvalRunner()._promotion_provider, llm_adapter=llm_ok, mode=LLMDecisionMode.LLM).decide(pctx, "r2")
    assert res.llm_used and res.llm_success and not res.fallback_used

    llm_fail = StubPromotionAdapter(success=False, output={})
    res2 = PromotionDecisionEngine(rule_engine=OfflineLLMEvalRunner()._promotion_provider, llm_adapter=llm_fail, mode=LLMDecisionMode.LLM).decide(pctx, "r3")
    assert res2.llm_success is False and res2.fallback_used is True

    res3 = PromotionDecisionEngine(rule_engine=OfflineLLMEvalRunner()._promotion_provider, llm_adapter=llm_ok, mode=LLMDecisionMode.HYBRID).decide(pctx, "r4")
    assert res3.disagreement is True


def test_belief_hybrid_runs_both_and_detects_disagreement() -> None:
    bctx = _belief_context().model_copy(update={"prior_belief": 0.8})
    adapter = StubBeliefAdapter(success=True, output={"belief": 0.01, "confidence": 0.9, "rationale": "llm"})
    res = BeliefUpdateEngine(rule_engine=OfflineLLMEvalRunner()._belief_update_provider, llm_adapter=adapter, mode=LLMDecisionMode.HYBRID).update(bctx, "b1")
    assert res.llm_used and res.llm_success and not res.fallback_used and res.disagreement


def test_eval_runner_runs_multiple_modes_and_emits_flags() -> None:
    snapshot = EvalSnapshot(snapshot_id="s1", decision_point=LLMDecisionPoint.PROMOTION, input_payload=_promotion_context().model_dump(mode="json"), expected_output=None, source="test", created_at=datetime(2026, 1, 1, tzinfo=UTC))
    runner = OfflineLLMEvalRunner(promotion_llm_adapter=StubPromotionAdapter(success=False, output={}))
    reports = runner.run_snapshots([snapshot], run_all_modes=True)
    assert isinstance(reports, dict)
    assert set(reports.keys()) == {"rule", "llm", "hybrid"}
    assert reports["llm"].results[0].decision_mode == "llm"
    assert reports["llm"].results[0].fallback_used is True


def test_no_api_key_required_fake_path() -> None:
    runner = OfflineLLMEvalRunner()
    report = runner.run_snapshots([])
    assert not isinstance(report, dict)
    assert report.total_cases == 0


def test_unsupported_decision_point_is_reported() -> None:
    snapshot = EvalSnapshot(snapshot_id="s2", decision_point=LLMDecisionPoint.MEMORY_EXTRACTION, input_payload={}, expected_output=None, source="test", created_at=datetime(2026, 1, 1, tzinfo=UTC))
    report = OfflineLLMEvalRunner().run_snapshots([snapshot])
    assert not isinstance(report, dict)
    assert report.total_cases == 1
    assert report.results[0].errors == ["unsupported_decision_point"]


def test_llm_mode_without_adapter_marks_fallback() -> None:
    snapshot = EvalSnapshot(snapshot_id="s3", decision_point=LLMDecisionPoint.PROMOTION, input_payload=_promotion_context().model_dump(mode="json"), expected_output=None, source="test", created_at=datetime(2026, 1, 1, tzinfo=UTC))
    report = OfflineLLMEvalRunner(decision_mode=LLMDecisionMode.LLM).run_snapshots([snapshot])
    assert not isinstance(report, dict)
    assert report.results[0].fallback_used is True
    assert report.results[0].llm_success is False
    assert "llm_adapter_missing" in report.results[0].errors


def test_validation_failure_from_llm_falls_back() -> None:
    snapshot = EvalSnapshot(snapshot_id="s4", decision_point=LLMDecisionPoint.BELIEF_UPDATE, input_payload=_belief_context().model_dump(mode="json"), expected_output=None, source="test", created_at=datetime(2026, 1, 1, tzinfo=UTC))
    bad = StubBeliefAdapter(success=True, output={"bad": "shape"})
    report = OfflineLLMEvalRunner(decision_mode=LLMDecisionMode.LLM, belief_llm_adapter=bad).run_snapshots([snapshot])
    assert not isinstance(report, dict)
    assert report.results[0].fallback_used is True
    assert "llm_decision_validation_failed" in report.results[0].errors


def test_hybrid_mode_without_adapter_does_not_claim_fallback_or_llm_use() -> None:
    snapshot = EvalSnapshot(snapshot_id="s5", decision_point=LLMDecisionPoint.PROMOTION, input_payload=_promotion_context().model_dump(mode="json"), expected_output=None, source="test", created_at=datetime(2026, 1, 1, tzinfo=UTC))
    report = OfflineLLMEvalRunner(decision_mode=LLMDecisionMode.HYBRID).run_snapshots([snapshot])
    assert not isinstance(report, dict)
    assert report.results[0].llm_used is False
    assert report.results[0].fallback_used is False
    assert report.results[0].disagreement is False
    assert "llm_adapter_missing" in report.results[0].errors


def test_hybrid_disagreement_ignores_promotion_rationale_text() -> None:
    pctx = _promotion_context()
    adapter = StubPromotionAdapter(success=True, output={"promote": False, "target_plane": None, "confidence": 0.95, "rationale": "different text"})
    res = PromotionDecisionEngine(rule_engine=OfflineLLMEvalRunner()._promotion_provider, llm_adapter=adapter, mode=LLMDecisionMode.HYBRID).decide(pctx, "r5")
    assert res.disagreement is False


def test_hybrid_belief_disagreement_uses_direction_and_confidence_band() -> None:
    bctx = _belief_context().model_copy(update={"prior_belief": 0.8})
    tiny = StubBeliefAdapter(success=True, output={"belief": 0.9, "confidence": 0.79, "rationale": "tiny diff"})
    res_tiny = BeliefUpdateEngine(rule_engine=OfflineLLMEvalRunner()._belief_update_provider, llm_adapter=tiny, mode=LLMDecisionMode.HYBRID).update(bctx, "b2")
    assert res_tiny.disagreement is False

    opposite = StubBeliefAdapter(success=True, output={"belief": 0.1, "confidence": 0.79, "rationale": "opposite"})
    res_opp = BeliefUpdateEngine(rule_engine=OfflineLLMEvalRunner()._belief_update_provider, llm_adapter=opposite, mode=LLMDecisionMode.HYBRID).update(bctx, "b3")
    assert res_opp.disagreement is True


def test_internal_validation_error_falls_back_for_promotion_without_crash() -> None:
    snapshot = EvalSnapshot(snapshot_id="s6", decision_point=LLMDecisionPoint.PROMOTION, input_payload=_promotion_context().model_dump(mode="json"), expected_output=None, source="test", created_at=datetime(2026, 1, 1, tzinfo=UTC))
    bad = StubPromotionAdapter(success=True, output={"bad": "shape"})
    report = OfflineLLMEvalRunner(decision_mode=LLMDecisionMode.LLM, promotion_llm_adapter=bad).run_snapshots([snapshot])
    assert not isinstance(report, dict)
    assert report.results[0].fallback_used is True
    assert report.results[0].llm_used is True
    assert report.results[0].llm_success is False
    assert "llm_decision_validation_failed" in report.results[0].errors
