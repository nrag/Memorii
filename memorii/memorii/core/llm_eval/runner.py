"""Deterministic offline eval runner for LLM decision snapshots."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from pydantic import ValidationError

from memorii.core.belief.models import BeliefUpdateContext, BeliefUpdateDecision
from memorii.core.belief.rule_provider import RuleBasedBeliefUpdateProvider
from memorii.core.llm_decision.models import EvalSnapshot, LLMDecisionMode, LLMDecisionPoint
from memorii.core.llm_decision.trace import LLMDecisionTraceStore
from memorii.core.llm_eval.comparators import compare_belief_update, compare_promotion
from memorii.core.llm_eval.models import EvalCaseResult, EvalRunReport
from memorii.core.promotion.models import PromotionContext, PromotionDecision
from memorii.core.promotion.rule_provider import RuleBasedPromotionDecisionProvider


class PromotionLLMAdapter(Protocol):
    def decide(self, *, context: PromotionContext, request_id: str, metadata: dict[str, object] | None = None): ...


class BeliefLLMAdapter(Protocol):
    def update(self, *, context: BeliefUpdateContext, request_id: str, metadata: dict[str, object] | None = None): ...


class PromotionDecisionEngine:
    def __init__(self, *, rule_engine: RuleBasedPromotionDecisionProvider, llm_adapter: PromotionLLMAdapter | None, mode: LLMDecisionMode) -> None:
        self._rule_engine = rule_engine
        self._llm_adapter = llm_adapter
        self._mode = mode

    def decide(self, context: PromotionContext, request_id: str) -> tuple[PromotionDecision, object, bool, bool | None, bool, bool, list[str]]:
        rule_decision, rule_trace = self._rule_engine.decide(context=context)
        if self._mode == LLMDecisionMode.RULE:
            return rule_decision, rule_trace, False, None, False, False, []
        if self._llm_adapter is None:
            fallback_used = self._mode == LLMDecisionMode.LLM
            return rule_decision, rule_trace, False, False, fallback_used, False, ["llm_adapter_missing"]

        llm_result = self._llm_adapter.decide(context=context, request_id=request_id)
        if not llm_result.success:
            return rule_decision, rule_trace, True, False, True, False, ["llm_decision_failed"]
        try:
            llm_decision = PromotionDecision.model_validate(llm_result.output)
        except ValidationError:
            return rule_decision, rule_trace, True, False, True, False, ["llm_decision_validation_failed"]
        if self._mode == LLMDecisionMode.LLM:
            # TODO: add native LLM trace object once adapter contracts expose one.
            return llm_decision, rule_trace, True, True, False, False, []
        disagreement = (llm_decision.promote != rule_decision.promote) or (llm_decision.target_plane != rule_decision.target_plane)
        # TODO: add native LLM trace object for HYBRID mode without dropping rule trace.
        return llm_decision, rule_trace, True, True, False, disagreement, []


class BeliefUpdateEngine:
    def __init__(self, *, rule_engine: RuleBasedBeliefUpdateProvider, llm_adapter: BeliefLLMAdapter | None, mode: LLMDecisionMode) -> None:
        self._rule_engine = rule_engine
        self._llm_adapter = llm_adapter
        self._mode = mode

    def update(self, context: BeliefUpdateContext, request_id: str) -> tuple[BeliefUpdateDecision, object, bool, bool | None, bool, bool, list[str]]:
        rule_decision, rule_trace = self._rule_engine.update(context=context)
        if self._mode == LLMDecisionMode.RULE:
            return rule_decision, rule_trace, False, None, False, False, []
        if self._llm_adapter is None:
            fallback_used = self._mode == LLMDecisionMode.LLM
            return rule_decision, rule_trace, False, False, fallback_used, False, ["llm_adapter_missing"]

        llm_result = self._llm_adapter.update(context=context, request_id=request_id)
        if not llm_result.success:
            return rule_decision, rule_trace, True, False, True, False, ["llm_decision_failed"]
        try:
            llm_decision = BeliefUpdateDecision.model_validate(llm_result.output)
        except ValidationError:
            return rule_decision, rule_trace, True, False, True, False, ["llm_decision_validation_failed"]
        if self._mode == LLMDecisionMode.LLM:
            # TODO: add native LLM trace object once adapter contracts expose one.
            return llm_decision, rule_trace, True, True, False, False, []
        def _direction(v: float, prior: float | None) -> str:
            if prior is None:
                return "stable"
            if v > prior + 0.05:
                return "increase"
            if v < prior - 0.05:
                return "decrease"
            return "stable"

        def _band(confidence: float) -> str:
            if confidence < 0.4:
                return "low"
            if confidence <= 0.7:
                return "medium"
            return "high"

        disagreement = (_direction(llm_decision.belief, context.prior_belief) != _direction(rule_decision.belief, context.prior_belief)) or (_band(llm_decision.confidence) != _band(rule_decision.confidence))
        # TODO: add native LLM trace object for HYBRID mode without dropping rule trace.
        return llm_decision, rule_trace, True, True, False, disagreement, []


class OfflineLLMEvalRunner:
    def __init__(self, *, promotion_provider: RuleBasedPromotionDecisionProvider | None = None, belief_update_provider: RuleBasedBeliefUpdateProvider | None = None, promotion_llm_adapter: PromotionLLMAdapter | None = None, belief_llm_adapter: BeliefLLMAdapter | None = None, decision_mode: LLMDecisionMode = LLMDecisionMode.RULE, trace_store: LLMDecisionTraceStore | None = None) -> None:
        self._promotion_provider = promotion_provider or RuleBasedPromotionDecisionProvider()
        self._belief_update_provider = belief_update_provider or RuleBasedBeliefUpdateProvider()
        self._promotion_llm_adapter = promotion_llm_adapter
        self._belief_llm_adapter = belief_llm_adapter
        self._decision_mode = decision_mode
        self._trace_store = trace_store

    def run_snapshots(self, snapshots: list[EvalSnapshot], *, run_all_modes: bool = False) -> EvalRunReport | dict[str, EvalRunReport]:
        if run_all_modes:
            return {mode.value: self._run_snapshots_for_mode(snapshots=snapshots, decision_mode=mode) for mode in (LLMDecisionMode.RULE, LLMDecisionMode.LLM, LLMDecisionMode.HYBRID)}
        return self._run_snapshots_for_mode(snapshots=snapshots, decision_mode=self._decision_mode)

    def _run_snapshots_for_mode(self, *, snapshots: list[EvalSnapshot], decision_mode: LLMDecisionMode) -> EvalRunReport:
        results: list[EvalCaseResult] = []
        for snapshot in snapshots:
            if snapshot.decision_point == LLMDecisionPoint.PROMOTION:
                results.append(self._run_promotion(snapshot=snapshot, mode=decision_mode))
            elif snapshot.decision_point == LLMDecisionPoint.BELIEF_UPDATE:
                results.append(self._run_belief_update(snapshot=snapshot, mode=decision_mode))
            else:
                requires_review = bool(snapshot.expected_output is None or snapshot.expected_output.get("requires_judge_review") is True)
                results.append(EvalCaseResult(snapshot_id=snapshot.snapshot_id, decision_point=snapshot.decision_point.value, passed=False, score=0.0, errors=["unsupported_decision_point"], actual_output={}, expected_output=snapshot.expected_output, requires_judge_review=requires_review, decision_mode=decision_mode.value))

        total_cases = len(snapshots)
        passed_cases = sum(1 for result in results if result.passed)
        count_by_decision_point: dict[str, int] = {}
        passed_by_decision_point: dict[str, int] = {}
        for result in results:
            count_by_decision_point[result.decision_point] = count_by_decision_point.get(result.decision_point, 0) + 1
            if result.passed:
                passed_by_decision_point[result.decision_point] = passed_by_decision_point.get(result.decision_point, 0) + 1
        return EvalRunReport(run_id=f"eval-run:{decision_mode.value}:{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}-{uuid4().hex[:10]}", total_cases=total_cases, passed_cases=passed_cases, failed_cases=total_cases - passed_cases, average_score=(sum(result.score for result in results) / total_cases) if total_cases else 0.0, results=results, count_by_decision_point=count_by_decision_point, pass_rate_by_decision_point={k: passed_by_decision_point.get(k, 0) / v for k, v in count_by_decision_point.items()})

    def _run_promotion(self, *, snapshot: EvalSnapshot, mode: LLMDecisionMode) -> EvalCaseResult:
        try:
            context = PromotionContext.model_validate(snapshot.input_payload)
        except ValidationError as exc:
            return EvalCaseResult(snapshot_id=snapshot.snapshot_id, decision_point=snapshot.decision_point.value, passed=False, score=0.0, errors=[f"validation_error:{exc.errors()[0]['type']}"] if exc.errors() else ["validation_error"], actual_output={}, expected_output=snapshot.expected_output, requires_judge_review=bool(snapshot.expected_output is None), decision_mode=mode.value)
        engine = PromotionDecisionEngine(rule_engine=self._promotion_provider, llm_adapter=self._promotion_llm_adapter, mode=mode)
        decision, trace, llm_used, llm_success, fallback_used, disagreement, engine_errors = engine.decide(context=context, request_id=f"eval:{snapshot.snapshot_id}")
        if self._trace_store is not None:
            self._trace_store.append_trace(trace)

        comparison = compare_promotion(actual=decision, expected_output=snapshot.expected_output)
        return EvalCaseResult(snapshot_id=snapshot.snapshot_id, decision_point=snapshot.decision_point.value, passed=comparison.passed, score=comparison.score, errors=[*comparison.errors, *engine_errors], actual_output=decision.model_dump(mode="json"), expected_output=snapshot.expected_output, trace_id=trace.trace_id, requires_judge_review=comparison.requires_judge_review, decision_mode=mode.value, llm_used=llm_used, llm_success=llm_success, fallback_used=fallback_used, disagreement=disagreement)

    def _run_belief_update(self, *, snapshot: EvalSnapshot, mode: LLMDecisionMode) -> EvalCaseResult:
        try:
            context = BeliefUpdateContext.model_validate(snapshot.input_payload)
        except ValidationError as exc:
            return EvalCaseResult(snapshot_id=snapshot.snapshot_id, decision_point=snapshot.decision_point.value, passed=False, score=0.0, errors=[f"validation_error:{exc.errors()[0]['type']}"] if exc.errors() else ["validation_error"], actual_output={}, expected_output=snapshot.expected_output, requires_judge_review=bool(snapshot.expected_output is None), decision_mode=mode.value)
        engine = BeliefUpdateEngine(rule_engine=self._belief_update_provider, llm_adapter=self._belief_llm_adapter, mode=mode)
        decision, trace, llm_used, llm_success, fallback_used, disagreement, engine_errors = engine.update(context=context, request_id=f"eval:{snapshot.snapshot_id}")
        if self._trace_store is not None:
            self._trace_store.append_trace(trace)

        comparison = compare_belief_update(context=context, actual=decision, expected_output=snapshot.expected_output)
        return EvalCaseResult(snapshot_id=snapshot.snapshot_id, decision_point=snapshot.decision_point.value, passed=comparison.passed, score=comparison.score, errors=[*comparison.errors, *engine_errors], actual_output=decision.model_dump(mode="json"), expected_output=snapshot.expected_output, trace_id=trace.trace_id, requires_judge_review=comparison.requires_judge_review, decision_mode=mode.value, llm_used=llm_used, llm_success=llm_success, fallback_used=fallback_used, disagreement=disagreement)
