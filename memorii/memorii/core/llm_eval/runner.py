"""Deterministic offline eval runner for LLM decision snapshots."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import ValidationError

from memorii.core.belief.models import BeliefUpdateContext
from memorii.core.belief.provider import BeliefUpdateProvider
from memorii.core.belief.rule_provider import RuleBasedBeliefUpdateProvider
from memorii.core.llm_decision.models import EvalSnapshot, LLMDecisionPoint
from memorii.core.llm_decision.trace import LLMDecisionTraceStore
from memorii.core.llm_eval.comparators import compare_belief_update, compare_promotion
from memorii.core.llm_eval.models import EvalCaseResult, EvalRunReport
from memorii.core.promotion.models import PromotionContext
from memorii.core.promotion.provider import PromotionDecisionProvider
from memorii.core.promotion.rule_provider import RuleBasedPromotionDecisionProvider


class OfflineLLMEvalRunner:
    def __init__(
        self,
        *,
        promotion_provider: PromotionDecisionProvider | None = None,
        belief_update_provider: BeliefUpdateProvider | None = None,
        trace_store: LLMDecisionTraceStore | None = None,
    ) -> None:
        self._promotion_provider = promotion_provider or RuleBasedPromotionDecisionProvider()
        self._belief_update_provider = belief_update_provider or RuleBasedBeliefUpdateProvider()
        self._trace_store = trace_store

    def run_snapshots(self, snapshots: list[EvalSnapshot]) -> EvalRunReport:
        results: list[EvalCaseResult] = []

        for snapshot in snapshots:
            if snapshot.decision_point == LLMDecisionPoint.PROMOTION:
                results.append(self._run_promotion(snapshot=snapshot))
            elif snapshot.decision_point == LLMDecisionPoint.BELIEF_UPDATE:
                results.append(self._run_belief_update(snapshot=snapshot))
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
                            or (snapshot.expected_output or {}).get("requires_judge_review") is True
                        ),
                    )
                )

        total_cases = len(results)
        passed_cases = sum(1 for result in results if result.passed)
        failed_cases = total_cases - passed_cases
        average_score = (sum(result.score for result in results) / total_cases) if total_cases else 0.0

        count_by_decision_point: dict[str, int] = {}
        passed_by_decision_point: dict[str, int] = {}
        for result in results:
            count_by_decision_point[result.decision_point] = count_by_decision_point.get(result.decision_point, 0) + 1
            if result.passed:
                passed_by_decision_point[result.decision_point] = passed_by_decision_point.get(result.decision_point, 0) + 1

        pass_rate_by_decision_point: dict[str, float] = {
            decision_point: passed_by_decision_point.get(decision_point, 0) / count
            for decision_point, count in count_by_decision_point.items()
        }

        return EvalRunReport(
            run_id=f"eval-run:{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}-{uuid4().hex[:10]}",
            total_cases=total_cases,
            passed_cases=passed_cases,
            failed_cases=failed_cases,
            average_score=average_score,
            results=results,
            count_by_decision_point=count_by_decision_point,
            pass_rate_by_decision_point=pass_rate_by_decision_point,
        )

    def _run_promotion(self, *, snapshot: EvalSnapshot) -> EvalCaseResult:
        try:
            context = PromotionContext.model_validate(snapshot.input_payload)
        except ValidationError as exc:
            return EvalCaseResult(
                snapshot_id=snapshot.snapshot_id,
                decision_point=snapshot.decision_point.value,
                passed=False,
                score=0.0,
                errors=[f"validation_error:{exc.errors()[0]['type']}"] if exc.errors() else ["validation_error"],
                actual_output={},
                expected_output=snapshot.expected_output,
                requires_judge_review=bool(snapshot.expected_output is None),
            )

        decision, trace = self._promotion_provider.decide(context=context)
        if self._trace_store is not None:
            self._trace_store.append_trace(trace)

        comparison = compare_promotion(actual=decision, expected_output=snapshot.expected_output)
        return EvalCaseResult(
            snapshot_id=snapshot.snapshot_id,
            decision_point=snapshot.decision_point.value,
            passed=comparison.passed,
            score=comparison.score,
            errors=comparison.errors,
            actual_output=decision.model_dump(mode="json"),
            expected_output=snapshot.expected_output,
            trace_id=trace.trace_id,
            requires_judge_review=comparison.requires_judge_review,
        )

    def _run_belief_update(self, *, snapshot: EvalSnapshot) -> EvalCaseResult:
        try:
            context = BeliefUpdateContext.model_validate(snapshot.input_payload)
        except ValidationError as exc:
            return EvalCaseResult(
                snapshot_id=snapshot.snapshot_id,
                decision_point=snapshot.decision_point.value,
                passed=False,
                score=0.0,
                errors=[f"validation_error:{exc.errors()[0]['type']}"] if exc.errors() else ["validation_error"],
                actual_output={},
                expected_output=snapshot.expected_output,
                requires_judge_review=bool(snapshot.expected_output is None),
            )

        decision, trace = self._belief_update_provider.update(context=context)
        if self._trace_store is not None:
            self._trace_store.append_trace(trace)

        comparison = compare_belief_update(context=context, actual=decision, expected_output=snapshot.expected_output)
        return EvalCaseResult(
            snapshot_id=snapshot.snapshot_id,
            decision_point=snapshot.decision_point.value,
            passed=comparison.passed,
            score=comparison.score,
            errors=comparison.errors,
            actual_output=decision.model_dump(mode="json"),
            expected_output=snapshot.expected_output,
            trace_id=trace.trace_id,
            requires_judge_review=comparison.requires_judge_review,
        )
