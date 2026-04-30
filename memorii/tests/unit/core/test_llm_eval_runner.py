from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from memorii.core.llm_decision.models import EvalSnapshot, LLMDecisionMode, LLMDecisionPoint
from memorii.core.llm_decision.trace import InMemoryLLMDecisionTraceStore
from memorii.core.llm_eval.models import EvalCaseResult
from memorii.core.llm_eval.report import summarize_eval_report
from memorii.core.llm_eval.runner import OfflineLLMEvalRunner
from memorii.core.promotion.models import PromotionCandidateType
from memorii.core.solver.abstention import SolverDecision


def _snapshot(
    *,
    snapshot_id: str,
    decision_point: LLMDecisionPoint,
    input_payload: dict[str, object],
    expected_output: dict[str, object] | None,
) -> EvalSnapshot:
    return EvalSnapshot(
        snapshot_id=snapshot_id,
        decision_point=decision_point,
        input_payload=input_payload,
        expected_output=expected_output,
        source="offline_golden",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _promotion_input(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "candidate_id": "cand:1",
        "candidate_type": PromotionCandidateType.EPISODIC.value,
        "content": "event",
        "created_from": "decision_finalized",
    }
    base.update(overrides)
    return base


def _belief_input(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "prior_belief": 0.4,
        "decision": SolverDecision.SUPPORTED.value,
        "evidence_count": 2,
        "missing_evidence_count": 0,
        "verifier_downgraded": False,
        "conflict_count": 0,
    }
    base.update(overrides)
    return base


def test_promotion_snapshot_passes_expected_promote_true() -> None:
    runner = OfflineLLMEvalRunner()
    report = runner.run_snapshots(
        [
            _snapshot(
                snapshot_id="snap:promo:pass",
                decision_point=LLMDecisionPoint.PROMOTION,
                input_payload=_promotion_input(),
                expected_output={"promote": True},
            )
        ]
    )

    assert report.passed_cases == 1
    assert report.results[0].passed is True


def test_promotion_snapshot_fails_wrong_target_plane() -> None:
    runner = OfflineLLMEvalRunner()
    report = runner.run_snapshots(
        [
            _snapshot(
                snapshot_id="snap:promo:fail-target",
                decision_point=LLMDecisionPoint.PROMOTION,
                input_payload=_promotion_input(),
                expected_output={"target_plane": "semantic"},
            )
        ]
    )

    assert report.failed_cases == 1
    assert "target_plane_mismatch" in report.results[0].errors


def test_belief_snapshot_passes_belief_range() -> None:
    runner = OfflineLLMEvalRunner()
    report = runner.run_snapshots(
        [
            _snapshot(
                snapshot_id="snap:belief:range",
                decision_point=LLMDecisionPoint.BELIEF_UPDATE,
                input_payload=_belief_input(prior_belief=0.4),
                expected_output={"min_belief": 0.6, "max_belief": 1.0},
            )
        ]
    )

    assert report.passed_cases == 1
    assert report.results[0].passed is True


@pytest.mark.parametrize(
    ("decision", "expected_direction"),
    [
        (SolverDecision.SUPPORTED.value, "increase"),
        (SolverDecision.REFUTED.value, "decrease"),
    ],
)
def test_belief_snapshot_passes_direction_increase_decrease(decision: str, expected_direction: str) -> None:
    runner = OfflineLLMEvalRunner()
    report = runner.run_snapshots(
        [
            _snapshot(
                snapshot_id=f"snap:belief:{expected_direction}",
                decision_point=LLMDecisionPoint.BELIEF_UPDATE,
                input_payload=_belief_input(prior_belief=0.5, decision=decision),
                expected_output={"direction": expected_direction},
            )
        ]
    )

    assert report.passed_cases == 1
    assert report.results[0].passed is True


def test_invalid_snapshot_input_fails_with_validation_error() -> None:
    runner = OfflineLLMEvalRunner()
    report = runner.run_snapshots(
        [
            _snapshot(
                snapshot_id="snap:invalid",
                decision_point=LLMDecisionPoint.PROMOTION,
                input_payload={"candidate_id": "only-one-field"},
                expected_output={"promote": True},
            )
        ]
    )

    assert report.failed_cases == 1
    assert report.results[0].errors[0].startswith("validation_error:")


def test_unsupported_decision_point_fails_cleanly() -> None:
    runner = OfflineLLMEvalRunner()
    report = runner.run_snapshots(
        [
            _snapshot(
                snapshot_id="snap:unsupported",
                decision_point=LLMDecisionPoint.MEMORY_EXTRACTION,
                input_payload={"event": "x"},
                expected_output={"foo": "bar"},
            )
        ]
    )

    assert report.failed_cases == 1
    assert report.results[0].errors == ["unsupported_decision_point"]


def test_trace_store_appends_provider_traces() -> None:
    trace_store = InMemoryLLMDecisionTraceStore()
    runner = OfflineLLMEvalRunner(trace_store=trace_store)

    runner.run_snapshots(
        [
            _snapshot(
                snapshot_id="snap:promo:trace",
                decision_point=LLMDecisionPoint.PROMOTION,
                input_payload=_promotion_input(),
                expected_output={"promote": True},
            ),
            _snapshot(
                snapshot_id="snap:belief:trace",
                decision_point=LLMDecisionPoint.BELIEF_UPDATE,
                input_payload=_belief_input(),
                expected_output={"min_belief": 0.0},
            ),
        ]
    )

    traces = trace_store.list_traces()
    assert len(traces) == 2


def test_report_aggregates_pass_rates() -> None:
    runner = OfflineLLMEvalRunner()
    report = runner.run_snapshots(
        [
            _snapshot(
                snapshot_id="snap:promo:pass2",
                decision_point=LLMDecisionPoint.PROMOTION,
                input_payload=_promotion_input(),
                expected_output={"promote": True},
            ),
            _snapshot(
                snapshot_id="snap:promo:fail2",
                decision_point=LLMDecisionPoint.PROMOTION,
                input_payload=_promotion_input(),
                expected_output={"target_plane": "semantic"},
            ),
            _snapshot(
                snapshot_id="snap:belief:pass2",
                decision_point=LLMDecisionPoint.BELIEF_UPDATE,
                input_payload=_belief_input(),
                expected_output={"min_belief": 0.0},
            ),
        ]
    )

    assert report.count_by_decision_point["promotion"] == 2
    assert report.count_by_decision_point["belief_update"] == 1
    assert report.pass_rate_by_decision_point["promotion"] == 0.5
    assert report.pass_rate_by_decision_point["belief_update"] == 1.0


def test_summarize_eval_report_includes_failed_ids() -> None:
    runner = OfflineLLMEvalRunner()
    report = runner.run_snapshots(
        [
            _snapshot(
                snapshot_id="snap:summary:failed",
                decision_point=LLMDecisionPoint.PROMOTION,
                input_payload=_promotion_input(),
                expected_output={"target_plane": "semantic"},
            )
        ]
    )

    summary = summarize_eval_report(report)
    assert "failed_snapshot_ids: snap:summary:failed" in summary


def test_strict_model_validation_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        EvalCaseResult(
            snapshot_id="snap:strict",
            decision_point="promotion",
            passed=True,
            score=1.0,
            errors=[],
            actual_output={},
            expected_output=None,
            extra_field="nope",
        )


def test_expected_output_none_marks_requires_judge_review_true() -> None:
    runner = OfflineLLMEvalRunner()
    report = runner.run_snapshots(
        [
            _snapshot(
                snapshot_id="snap:judge:none",
                decision_point=LLMDecisionPoint.PROMOTION,
                input_payload=_promotion_input(),
                expected_output=None,
            )
        ]
    )

    assert report.results[0].requires_judge_review is True


def test_expected_output_requires_judge_review_flag_propagates() -> None:
    runner = OfflineLLMEvalRunner()
    report = runner.run_snapshots(
        [
            _snapshot(
                snapshot_id="snap:judge:flag",
                decision_point=LLMDecisionPoint.BELIEF_UPDATE,
                input_payload=_belief_input(),
                expected_output={"requires_judge_review": True, "min_belief": 0.0},
            )
        ]
    )

    assert report.results[0].requires_judge_review is True


def test_judge_verdict_refs_defaults_to_empty_list() -> None:
    result = EvalCaseResult(
        snapshot_id="snap:default-judges",
        decision_point="promotion",
        passed=True,
        score=1.0,
        actual_output={"promote": True},
    )

    assert result.judge_verdict_refs == []


def test_trace_store_rule_mode_appends_one_trace() -> None:
    trace_store = InMemoryLLMDecisionTraceStore()
    snapshot = _snapshot(snapshot_id="snap:trace:rule", decision_point=LLMDecisionPoint.PROMOTION, input_payload=_promotion_input(), expected_output={"promote": True})
    report = OfflineLLMEvalRunner(decision_mode=LLMDecisionMode.RULE, trace_store=trace_store).run_snapshots([snapshot])
    assert report.total_cases == 1
    assert len(trace_store.list_traces()) == 1


def test_trace_store_llm_failure_fallback_appends_rule_trace() -> None:
    from types import SimpleNamespace

    class _FailAdapter:
        def decide(self, *, context, request_id, metadata=None):
            return SimpleNamespace(success=False, output={})

    trace_store = InMemoryLLMDecisionTraceStore()
    snapshot = _snapshot(snapshot_id="snap:trace:fallback", decision_point=LLMDecisionPoint.PROMOTION, input_payload=_promotion_input(), expected_output=None)
    report = OfflineLLMEvalRunner(decision_mode=LLMDecisionMode.LLM, promotion_llm_adapter=_FailAdapter(), trace_store=trace_store).run_snapshots([snapshot])
    assert report.results[0].fallback_used is True
    assert len(trace_store.list_traces()) == 1


def test_trace_store_hybrid_appends_rule_trace() -> None:
    from types import SimpleNamespace

    class _OkAdapter:
        def decide(self, *, context, request_id, metadata=None):
            return SimpleNamespace(success=True, output={"promote": True, "target_plane": "semantic", "confidence": 0.9, "rationale": "ok"})

    trace_store = InMemoryLLMDecisionTraceStore()
    snapshot = _snapshot(snapshot_id="snap:trace:hybrid", decision_point=LLMDecisionPoint.PROMOTION, input_payload=_promotion_input(), expected_output=None)
    OfflineLLMEvalRunner(decision_mode=LLMDecisionMode.HYBRID, promotion_llm_adapter=_OkAdapter(), trace_store=trace_store).run_snapshots([snapshot])
    assert len(trace_store.list_traces()) == 1
