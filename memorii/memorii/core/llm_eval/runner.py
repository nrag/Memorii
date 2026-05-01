"""Deterministic offline eval runner for LLM decision snapshots."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from pydantic import ValidationError

from memorii.core.belief.models import BeliefUpdateContext, BeliefUpdateDecision
from memorii.core.belief.rule_provider import RuleBasedBeliefUpdateProvider
from memorii.core.llm_decision.models import (
    EvalSnapshot,
    LLMDecisionMode,
    LLMDecisionPoint,
)
from memorii.core.llm_decision.trace import LLMDecisionTraceStore
from memorii.core.llm_eval.comparators import compare_belief_update, compare_promotion
from memorii.core.llm_eval.engine_result import DecisionEngineResult
from memorii.core.llm_eval.models import EvalCaseResult, EvalRunReport
from memorii.core.llm_provider.models import LLMDecisionResult
from memorii.core.llm_trace.builder import build_llm_decision_trace_from_result
from memorii.core.llm_trace.policy import LLMTracePolicy
from memorii.core.promotion.models import PromotionContext, PromotionDecision
from memorii.core.promotion.rule_provider import RuleBasedPromotionDecisionProvider


class PromotionLLMAdapter(Protocol):
    def decide(
        self,
        *,
        context: PromotionContext,
        request_id: str,
        metadata: dict[str, object] | None = None,
    ) -> LLMDecisionResult: ...


class BeliefLLMAdapter(Protocol):
    def update(
        self,
        *,
        context: BeliefUpdateContext,
        request_id: str,
        metadata: dict[str, object] | None = None,
    ) -> LLMDecisionResult: ...


class PromotionDecisionEngine:
    def __init__(
        self,
        *,
        rule_engine: RuleBasedPromotionDecisionProvider,
        llm_adapter: PromotionLLMAdapter | None,
        mode: LLMDecisionMode,
    ) -> None:
        self._rule_engine = rule_engine
        self._llm_adapter = llm_adapter
        self._mode = mode

    def decide(self, context: PromotionContext, request_id: str) -> DecisionEngineResult:
        rule_decision, rule_trace = self._rule_engine.decide(context=context)
        rule_output = rule_decision.model_dump(mode="json")

        if self._mode == LLMDecisionMode.RULE:
            return DecisionEngineResult(decision=rule_output, rule_trace=rule_trace)

        if self._llm_adapter is None:
            return DecisionEngineResult(
                decision=rule_output,
                rule_trace=rule_trace,
                llm_success=False,
                fallback_used=(self._mode == LLMDecisionMode.LLM),
                errors=["llm_adapter_missing"],
            )

        llm_result = self._llm_adapter.decide(context=context, request_id=request_id)

        if not llm_result.success:
            llm_trace = build_llm_decision_trace_from_result(
                decision_point=LLMDecisionPoint.PROMOTION,
                mode=self._mode,
                result=llm_result,
                final_output=rule_output,
                fallback_used=True,
            )
            return DecisionEngineResult(
                decision=rule_output,
                rule_trace=rule_trace,
                llm_trace=llm_trace,
                llm_used=True,
                llm_success=False,
                fallback_used=True,
                errors=["llm_decision_failed"],
            )

        try:
            llm_decision = PromotionDecision.model_validate(llm_result.output)
        except ValidationError:
            llm_trace = build_llm_decision_trace_from_result(
                decision_point=LLMDecisionPoint.PROMOTION,
                mode=self._mode,
                result=llm_result,
                final_output=rule_output,
                fallback_used=True,
            )
            return DecisionEngineResult(
                decision=rule_output,
                rule_trace=rule_trace,
                llm_trace=llm_trace,
                llm_used=True,
                llm_success=False,
                fallback_used=True,
                errors=["llm_decision_validation_failed"],
            )

        llm_output = llm_decision.model_dump(mode="json")
        llm_trace = build_llm_decision_trace_from_result(
            decision_point=LLMDecisionPoint.PROMOTION,
            mode=self._mode,
            result=llm_result,
            final_output=llm_output,
            fallback_used=False,
        )

        if self._mode == LLMDecisionMode.LLM:
            return DecisionEngineResult(
                decision=llm_output,
                llm_trace=llm_trace,
                llm_used=True,
                llm_success=True,
            )

        disagreement = (llm_decision.promote != rule_decision.promote) or (
            llm_decision.target_plane != rule_decision.target_plane
        )
        return DecisionEngineResult(
            decision=llm_output,
            rule_trace=rule_trace,
            llm_trace=llm_trace,
            llm_used=True,
            llm_success=True,
            disagreement=disagreement,
        )


class BeliefUpdateEngine:
    def __init__(
        self,
        *,
        rule_engine: RuleBasedBeliefUpdateProvider,
        llm_adapter: BeliefLLMAdapter | None,
        mode: LLMDecisionMode,
    ) -> None:
        self._rule_engine = rule_engine
        self._llm_adapter = llm_adapter
        self._mode = mode

    def update(self, context: BeliefUpdateContext, request_id: str) -> DecisionEngineResult:
        rule_decision, rule_trace = self._rule_engine.update(context=context)
        rule_output = rule_decision.model_dump(mode="json")

        if self._mode == LLMDecisionMode.RULE:
            return DecisionEngineResult(decision=rule_output, rule_trace=rule_trace)

        if self._llm_adapter is None:
            return DecisionEngineResult(
                decision=rule_output,
                rule_trace=rule_trace,
                llm_success=False,
                fallback_used=(self._mode == LLMDecisionMode.LLM),
                errors=["llm_adapter_missing"],
            )

        llm_result = self._llm_adapter.update(context=context, request_id=request_id)

        if not llm_result.success:
            llm_trace = build_llm_decision_trace_from_result(
                decision_point=LLMDecisionPoint.BELIEF_UPDATE,
                mode=self._mode,
                result=llm_result,
                final_output=rule_output,
                fallback_used=True,
            )
            return DecisionEngineResult(
                decision=rule_output,
                rule_trace=rule_trace,
                llm_trace=llm_trace,
                llm_used=True,
                llm_success=False,
                fallback_used=True,
                errors=["llm_decision_failed"],
            )

        try:
            llm_decision = BeliefUpdateDecision.model_validate(llm_result.output)
        except ValidationError:
            llm_trace = build_llm_decision_trace_from_result(
                decision_point=LLMDecisionPoint.BELIEF_UPDATE,
                mode=self._mode,
                result=llm_result,
                final_output=rule_output,
                fallback_used=True,
            )
            return DecisionEngineResult(
                decision=rule_output,
                rule_trace=rule_trace,
                llm_trace=llm_trace,
                llm_used=True,
                llm_success=False,
                fallback_used=True,
                errors=["llm_decision_validation_failed"],
            )

        llm_output = llm_decision.model_dump(mode="json")
        llm_trace = build_llm_decision_trace_from_result(
            decision_point=LLMDecisionPoint.BELIEF_UPDATE,
            mode=self._mode,
            result=llm_result,
            final_output=llm_output,
            fallback_used=False,
        )

        if self._mode == LLMDecisionMode.LLM:
            return DecisionEngineResult(
                decision=llm_output,
                llm_trace=llm_trace,
                llm_used=True,
                llm_success=True,
            )

        disagreement = _belief_disagreement(
            context=context,
            llm_decision=llm_decision,
            rule_decision=rule_decision,
        )
        return DecisionEngineResult(
            decision=llm_output,
            rule_trace=rule_trace,
            llm_trace=llm_trace,
            llm_used=True,
            llm_success=True,
            disagreement=disagreement,
        )


def _belief_disagreement(
    *,
    context: BeliefUpdateContext,
    llm_decision: BeliefUpdateDecision,
    rule_decision: BeliefUpdateDecision,
) -> bool:
    def _direction(value: float, prior: float | None) -> str:
        if prior is None:
            return "stable"
        if value > prior + 0.05:
            return "increase"
        if value < prior - 0.05:
            return "decrease"
        return "stable"

    def _band(confidence: float) -> str:
        if confidence < 0.4:
            return "low"
        if confidence <= 0.7:
            return "medium"
        return "high"

    return (
        _direction(llm_decision.belief, context.prior_belief)
        != _direction(rule_decision.belief, context.prior_belief)
    ) or (_band(llm_decision.confidence) != _band(rule_decision.confidence))


class OfflineLLMEvalRunner:
    def __init__(
        self,
        *,
        promotion_provider: RuleBasedPromotionDecisionProvider | None = None,
        belief_update_provider: RuleBasedBeliefUpdateProvider | None = None,
        promotion_llm_adapter: PromotionLLMAdapter | None = None,
        belief_llm_adapter: BeliefLLMAdapter | None = None,
        decision_mode: LLMDecisionMode = LLMDecisionMode.RULE,
        trace_store: LLMDecisionTraceStore | None = None,
        trace_policy: LLMTracePolicy | None = None,
    ) -> None:
        self._promotion_provider = promotion_provider or RuleBasedPromotionDecisionProvider()
        self._belief_update_provider = (
            belief_update_provider or RuleBasedBeliefUpdateProvider()
        )
        self._promotion_llm_adapter = promotion_llm_adapter
        self._belief_llm_adapter = belief_llm_adapter
        self._decision_mode = decision_mode
        self._trace_store = trace_store
        self._trace_policy = trace_policy or LLMTracePolicy()

    def run_snapshots(
        self,
        snapshots: list[EvalSnapshot],
        *,
        run_all_modes: bool = False,
    ) -> EvalRunReport | dict[str, EvalRunReport]:
        if run_all_modes:
            return {
                mode.value: self._run_snapshots_for_mode(
                    snapshots=snapshots,
                    decision_mode=mode,
                )
                for mode in (
                    LLMDecisionMode.RULE,
                    LLMDecisionMode.LLM,
                    LLMDecisionMode.HYBRID,
                )
            }
        return self._run_snapshots_for_mode(
            snapshots=snapshots,
            decision_mode=self._decision_mode,
        )

    def _run_snapshots_for_mode(
        self,
        *,
        snapshots: list[EvalSnapshot],
        decision_mode: LLMDecisionMode,
    ) -> EvalRunReport:
        results: list[EvalCaseResult] = []
        for snapshot in snapshots:
            if snapshot.decision_point == LLMDecisionPoint.PROMOTION:
                results.append(self._run_promotion(snapshot=snapshot, mode=decision_mode))
            elif snapshot.decision_point == LLMDecisionPoint.BELIEF_UPDATE:
                results.append(self._run_belief_update(snapshot=snapshot, mode=decision_mode))
            else:
                results.append(
                    EvalCaseResult(
                        snapshot_id=snapshot.snapshot_id,
                        decision_point=snapshot.decision_point.value,
                        passed=False,
                        score=0.0,
                        errors=["unsupported_decision_point"],
                        actual_output={},
                        expected_output=snapshot.expected_output,
                        requires_judge_review=bool(
                            snapshot.expected_output is None
                            or snapshot.expected_output.get("requires_judge_review") is True
                        ),
                        decision_mode=decision_mode.value,
                    )
                )

        total_cases = len(snapshots)
        passed_cases = sum(1 for result in results if result.passed)
        count_by_decision_point: dict[str, int] = {}
        passed_by_decision_point: dict[str, int] = {}
        for result in results:
            count_by_decision_point[result.decision_point] = (
                count_by_decision_point.get(result.decision_point, 0) + 1
            )
            if result.passed:
                passed_by_decision_point[result.decision_point] = (
                    passed_by_decision_point.get(result.decision_point, 0) + 1
                )

        return EvalRunReport(
            run_id=(
                f"eval-run:{decision_mode.value}:"
                f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}-{uuid4().hex[:10]}"
            ),
            total_cases=total_cases,
            passed_cases=passed_cases,
            failed_cases=total_cases - passed_cases,
            average_score=(sum(result.score for result in results) / total_cases)
            if total_cases
            else 0.0,
            results=results,
            count_by_decision_point=count_by_decision_point,
            pass_rate_by_decision_point={
                point: passed_by_decision_point.get(point, 0) / count
                for point, count in count_by_decision_point.items()
            },
        )

    def _persist_traces(
        self,
        *,
        mode: LLMDecisionMode,
        engine_result: DecisionEngineResult,
        requires_judge_review: bool,
        judge_score: float | None,
    ) -> str | None:
        if self._trace_store is None:
            return None

        persisted_rule_trace = None
        persisted_llm_trace = None

        should_persist_rule_trace = (
            engine_result.rule_trace is not None
            and (
                mode == LLMDecisionMode.RULE
                or engine_result.fallback_used
                or mode == LLMDecisionMode.HYBRID
            )
        )
        if should_persist_rule_trace:
            self._trace_store.append_trace(engine_result.rule_trace)
            persisted_rule_trace = engine_result.rule_trace

        should_persist_llm_trace = (
            engine_result.llm_trace is not None
            and self._trace_policy.should_persist(
                llm_used=engine_result.llm_used,
                llm_success=engine_result.llm_success,
                fallback_used=engine_result.fallback_used,
                disagreement=engine_result.disagreement,
                requires_judge_review=requires_judge_review,
                judge_score=judge_score,
            )
        )
        if should_persist_llm_trace:
            self._trace_store.append_trace(engine_result.llm_trace)
            persisted_llm_trace = engine_result.llm_trace

        if persisted_llm_trace is not None:
            return persisted_llm_trace.trace_id
        if persisted_rule_trace is not None:
            return persisted_rule_trace.trace_id
        return None

    def _run_promotion(
        self,
        *,
        snapshot: EvalSnapshot,
        mode: LLMDecisionMode,
    ) -> EvalCaseResult:
        try:
            context = PromotionContext.model_validate(snapshot.input_payload)
        except ValidationError as exc:
            return EvalCaseResult(
                snapshot_id=snapshot.snapshot_id,
                decision_point=snapshot.decision_point.value,
                passed=False,
                score=0.0,
                errors=[f"validation_error:{exc.errors()[0]['type']}"]
                if exc.errors()
                else ["validation_error"],
                actual_output={},
                expected_output=snapshot.expected_output,
                requires_judge_review=bool(snapshot.expected_output is None),
                decision_mode=mode.value,
            )

        engine_result = PromotionDecisionEngine(
            rule_engine=self._promotion_provider,
            llm_adapter=self._promotion_llm_adapter,
            mode=mode,
        ).decide(context=context, request_id=f"eval:{snapshot.snapshot_id}")

        comparison = compare_promotion(
            actual=PromotionDecision.model_validate(engine_result.decision),
            expected_output=snapshot.expected_output,
        )

        trace_id = self._persist_traces(
            mode=mode,
            engine_result=engine_result,
            requires_judge_review=comparison.requires_judge_review,
            judge_score=comparison.score,
        )

        return EvalCaseResult(
            snapshot_id=snapshot.snapshot_id,
            decision_point=snapshot.decision_point.value,
            passed=comparison.passed,
            score=comparison.score,
            errors=[*comparison.errors, *engine_result.errors],
            actual_output=engine_result.decision,
            expected_output=snapshot.expected_output,
            trace_id=trace_id,
            requires_judge_review=comparison.requires_judge_review,
            decision_mode=mode.value,
            llm_used=engine_result.llm_used,
            llm_success=engine_result.llm_success,
            fallback_used=engine_result.fallback_used,
            disagreement=engine_result.disagreement,
        )

    def _run_belief_update(
        self,
        *,
        snapshot: EvalSnapshot,
        mode: LLMDecisionMode,
    ) -> EvalCaseResult:
        try:
            context = BeliefUpdateContext.model_validate(snapshot.input_payload)
        except ValidationError as exc:
            return EvalCaseResult(
                snapshot_id=snapshot.snapshot_id,
                decision_point=snapshot.decision_point.value,
                passed=False,
                score=0.0,
                errors=[f"validation_error:{exc.errors()[0]['type']}"]
                if exc.errors()
                else ["validation_error"],
                actual_output={},
                expected_output=snapshot.expected_output,
                requires_judge_review=bool(snapshot.expected_output is None),
                decision_mode=mode.value,
            )

        engine_result = BeliefUpdateEngine(
            rule_engine=self._belief_update_provider,
            llm_adapter=self._belief_llm_adapter,
            mode=mode,
        ).update(context=context, request_id=f"eval:{snapshot.snapshot_id}")

        comparison = compare_belief_update(
            context=context,
            actual=BeliefUpdateDecision.model_validate(engine_result.decision),
            expected_output=snapshot.expected_output,
        )

        trace_id = self._persist_traces(
            mode=mode,
            engine_result=engine_result,
            requires_judge_review=comparison.requires_judge_review,
            judge_score=comparison.score,
        )

        return EvalCaseResult(
            snapshot_id=snapshot.snapshot_id,
            decision_point=snapshot.decision_point.value,
            passed=comparison.passed,
            score=comparison.score,
            errors=[*comparison.errors, *engine_result.errors],
            actual_output=engine_result.decision,
            expected_output=snapshot.expected_output,
            trace_id=trace_id,
            requires_judge_review=comparison.requires_judge_review,
            decision_mode=mode.value,
            llm_used=engine_result.llm_used,
            llm_success=engine_result.llm_success,
            fallback_used=engine_result.fallback_used,
            disagreement=engine_result.disagreement,
        )
