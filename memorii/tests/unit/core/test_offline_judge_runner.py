from __future__ import annotations

from datetime import UTC, datetime

from memorii.core.llm_decision.models import EvalSnapshot, LLMDecisionPoint
from memorii.core.llm_eval.models import EvalCaseResult, EvalRunReport
from memorii.core.llm_judge import OfflineJudgeRunner, attach_judge_refs_to_eval_cases
from memorii.core.llm_judge.models import JudgeDimension, JudgeRubric


def _snapshot(*, snapshot_id: str, decision_point: LLMDecisionPoint, input_payload: dict[str, object]) -> EvalSnapshot:
    return EvalSnapshot(
        snapshot_id=snapshot_id,
        decision_point=decision_point,
        input_payload=input_payload,
        expected_output={},
        source="test",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _eval_case(
    *,
    snapshot_id: str,
    decision_point: str,
    passed: bool,
    requires_judge_review: bool,
    actual_output: dict[str, object] | None = None,
    trace_id: str | None = None,
) -> EvalCaseResult:
    return EvalCaseResult(
        snapshot_id=snapshot_id,
        decision_point=decision_point,
        passed=passed,
        score=1.0 if passed else 0.0,
        errors=[] if passed else ["failed"],
        actual_output=actual_output or {},
        expected_output={},
        requires_judge_review=requires_judge_review,
        trace_id=trace_id,
    )


def _promotion_payload() -> dict[str, object]:
    return {
        "candidate_id": "cand:1",
        "candidate_type": "project_fact",
        "content": "Current workaround for now this sprint",
        "source_ids": ["src:1"],
        "related_memory_ids": [],
        "repeated_across_episodes": 3,
        "explicit_user_memory_request": False,
        "created_from": "observation",
        "metadata": {"source_actor": "tool", "source_kind": "tool", "asserted_by": "tool"},
    }


def _belief_payload() -> dict[str, object]:
    return {
        "prior_belief": 0.5,
        "decision": "SUPPORTED",
        "evidence_count": 2,
        "missing_evidence_count": 0,
        "verifier_downgraded": False,
        "conflict_count": 0,
        "evidence_ids": ["ev:1"],
        "missing_evidence": [],
        "metadata": {},
    }


def test_default_runner_validates_wave1_judges() -> None:
    runner = OfflineJudgeRunner()

    assert [judge.judge_id for judge in runner._promotion_judges] == [
        "promotion_precision:v1",
        "temporal_validity:v1",
        "attribution:v1",
        "memory_plane:v1",
    ]
    assert [judge.judge_id for judge in runner._belief_judges] == ["attribution:v1", "belief_direction:v1"]


def test_promotion_case_routes_to_promotion_wave1_judges() -> None:
    runner = OfflineJudgeRunner()
    case = _eval_case(snapshot_id="snap:promo", decision_point="promotion", passed=False, requires_judge_review=False)
    snapshot = _snapshot(snapshot_id="snap:promo", decision_point=LLMDecisionPoint.PROMOTION, input_payload=_promotion_payload())

    report = runner.run_cases([case], snapshots_by_id={snapshot.snapshot_id: snapshot})

    assert [v.judge_id for v in report.case_results[0].judge_verdicts] == [
        "promotion_precision:v1",
        "temporal_validity:v1",
        "attribution:v1",
        "memory_plane:v1",
    ]


def test_belief_case_routes_to_belief_direction_only_when_attribution_missing() -> None:
    runner = OfflineJudgeRunner()
    case = _eval_case(
        snapshot_id="snap:belief",
        decision_point="belief_update",
        passed=False,
        requires_judge_review=False,
        actual_output={"belief": 0.8},
    )
    snapshot = _snapshot(snapshot_id="snap:belief", decision_point=LLMDecisionPoint.BELIEF_UPDATE, input_payload=_belief_payload())

    report = runner.run_cases([case], snapshots_by_id={snapshot.snapshot_id: snapshot})

    assert [v.judge_id for v in report.case_results[0].judge_verdicts] == ["belief_direction:v1"]


def test_belief_case_routes_to_attribution_when_fields_present() -> None:
    runner = OfflineJudgeRunner()
    case = _eval_case(
        snapshot_id="snap:belief:attr",
        decision_point="belief_update",
        passed=False,
        requires_judge_review=False,
        actual_output={"belief": 0.8},
    )
    payload = _belief_payload()
    payload["metadata"] = {"source_actor": "tool", "source_kind": "tool", "asserted_by": "tool"}
    snapshot = _snapshot(snapshot_id="snap:belief:attr", decision_point=LLMDecisionPoint.BELIEF_UPDATE, input_payload=payload)

    report = runner.run_cases([case], snapshots_by_id={snapshot.snapshot_id: snapshot})

    assert [v.judge_id for v in report.case_results[0].judge_verdicts] == ["attribution:v1", "belief_direction:v1"]


def test_passing_non_review_case_is_skipped_by_default() -> None:
    runner = OfflineJudgeRunner()

    report = runner.run_cases(
        [_eval_case(snapshot_id="snap:skip", decision_point="promotion", passed=True, requires_judge_review=False)],
        snapshots_by_id={},
    )

    assert report.judged_cases == 0
    assert report.skipped_cases == 1


def test_failed_case_is_judged() -> None:
    runner = OfflineJudgeRunner()
    case = _eval_case(snapshot_id="snap:failed", decision_point="promotion", passed=False, requires_judge_review=False)
    snapshot = _snapshot(snapshot_id="snap:failed", decision_point=LLMDecisionPoint.PROMOTION, input_payload=_promotion_payload())

    report = runner.run_cases([case], snapshots_by_id={snapshot.snapshot_id: snapshot})

    assert report.judged_cases == 1


def test_requires_judge_review_case_is_judged() -> None:
    runner = OfflineJudgeRunner()
    case = _eval_case(snapshot_id="snap:review", decision_point="promotion", passed=True, requires_judge_review=True)
    snapshot = _snapshot(snapshot_id="snap:review", decision_point=LLMDecisionPoint.PROMOTION, input_payload=_promotion_payload())

    report = runner.run_cases([case], snapshots_by_id={snapshot.snapshot_id: snapshot})

    assert report.judged_cases == 1


def test_judge_all_cases_judges_passing_cases_too() -> None:
    runner = OfflineJudgeRunner(judge_all_cases=True)
    case = _eval_case(snapshot_id="snap:all", decision_point="promotion", passed=True, requires_judge_review=False)
    snapshot = _snapshot(snapshot_id="snap:all", decision_point=LLMDecisionPoint.PROMOTION, input_payload=_promotion_payload())

    report = runner.run_cases([case], snapshots_by_id={snapshot.snapshot_id: snapshot})

    assert report.judged_cases == 1
    assert report.skipped_cases == 0


def test_missing_snapshot_creates_human_review_golden_candidate_case() -> None:
    runner = OfflineJudgeRunner()

    report = runner.run_cases(
        [_eval_case(snapshot_id="snap:missing", decision_point="promotion", passed=False, requires_judge_review=False)],
        snapshots_by_id={},
    )

    case_result = report.case_results[0]
    assert case_result.judge_verdicts == []
    assert case_result.jury_verdict.needs_human_review is True
    assert case_result.golden_candidate_reason == "missing_snapshot"
    assert report.human_review_cases == 1
    assert report.golden_candidate_cases == 1


def test_unsupported_decision_point_is_skipped() -> None:
    runner = OfflineJudgeRunner(judge_all_cases=True)

    report = runner.run_cases(
        [_eval_case(snapshot_id="snap:unsupported", decision_point="memory_extraction", passed=False, requires_judge_review=True)],
        snapshots_by_id={},
    )

    assert report.judged_cases == 0
    assert report.skipped_cases == 1


def test_jury_disagreement_produces_golden_candidate_reason() -> None:
    runner = OfflineJudgeRunner()
    case = _eval_case(snapshot_id="snap:disagree", decision_point="promotion", passed=False, requires_judge_review=False)
    snapshot = _snapshot(snapshot_id="snap:disagree", decision_point=LLMDecisionPoint.PROMOTION, input_payload=_promotion_payload())

    report = runner.run_cases([case], snapshots_by_id={snapshot.snapshot_id: snapshot})

    assert report.case_results[0].jury_verdict.disagreement is True
    assert report.case_results[0].golden_candidate_reason is not None


def test_report_counts_are_correct() -> None:
    runner = OfflineJudgeRunner()

    case_skip = _eval_case(snapshot_id="snap:skip2", decision_point="promotion", passed=True, requires_judge_review=False)
    case_pass = _eval_case(snapshot_id="snap:pass", decision_point="belief_update", passed=False, requires_judge_review=False, actual_output={"belief": 0.8})
    case_missing = _eval_case(snapshot_id="snap:missing2", decision_point="promotion", passed=False, requires_judge_review=False)

    snapshot_pass = _snapshot(snapshot_id="snap:pass", decision_point=LLMDecisionPoint.BELIEF_UPDATE, input_payload=_belief_payload())

    report = runner.run_cases(
        [case_skip, case_pass, case_missing],
        snapshots_by_id={snapshot_pass.snapshot_id: snapshot_pass},
    )

    assert report.total_eval_cases == 3
    assert report.judged_cases == 2
    assert report.skipped_cases == 1
    assert report.jury_passed_cases + report.jury_failed_cases == report.judged_cases
    assert report.human_review_cases >= 1
    assert report.golden_candidate_cases >= 1


def test_run_id_is_stable_for_same_inputs() -> None:
    runner = OfflineJudgeRunner()
    cases = [
        _eval_case(snapshot_id="snap:a", decision_point="promotion", passed=False, requires_judge_review=False),
        _eval_case(snapshot_id="snap:b", decision_point="promotion", passed=True, requires_judge_review=False),
    ]
    snapshot_a = _snapshot(snapshot_id="snap:a", decision_point=LLMDecisionPoint.PROMOTION, input_payload=_promotion_payload())

    first = runner.run_cases(cases, snapshots_by_id={snapshot_a.snapshot_id: snapshot_a})
    second = runner.run_cases(cases, snapshots_by_id={snapshot_a.snapshot_id: snapshot_a})

    assert first.run_id == second.run_id


def test_run_id_changes_when_case_payload_changes() -> None:
    runner = OfflineJudgeRunner()

    first_cases = [
        _eval_case(
            snapshot_id="snap:same",
            decision_point="belief_update",
            passed=False,
            requires_judge_review=False,
            actual_output={"belief": 0.7},
            trace_id="trace:1",
        )
    ]
    second_cases = [
        _eval_case(
            snapshot_id="snap:same",
            decision_point="belief_update",
            passed=False,
            requires_judge_review=False,
            actual_output={"belief": 0.9},
            trace_id="trace:1",
        )
    ]

    first = runner.run_cases(first_cases, snapshots_by_id={})
    second = runner.run_cases(second_cases, snapshots_by_id={})

    assert first.run_id != second.run_id


def test_attach_judge_refs_to_eval_cases_returns_new_cases_without_mutating_original() -> None:
    runner = OfflineJudgeRunner()
    original_case = _eval_case(snapshot_id="snap:refs", decision_point="promotion", passed=False, requires_judge_review=False)
    snapshot = _snapshot(snapshot_id="snap:refs", decision_point=LLMDecisionPoint.PROMOTION, input_payload=_promotion_payload())

    judge_report = runner.run_cases([original_case], snapshots_by_id={snapshot.snapshot_id: snapshot})
    updated_cases = attach_judge_refs_to_eval_cases([original_case], judge_report)

    assert updated_cases[0] is not original_case
    assert original_case.judge_verdict_refs == []


def test_attached_judge_verdict_refs_match_produced_verdict_ids() -> None:
    runner = OfflineJudgeRunner()
    case = _eval_case(snapshot_id="snap:refs2", decision_point="belief_update", passed=False, requires_judge_review=False, actual_output={"belief": 0.8})
    snapshot = _snapshot(snapshot_id="snap:refs2", decision_point=LLMDecisionPoint.BELIEF_UPDATE, input_payload=_belief_payload())

    judge_report = runner.run_cases([case], snapshots_by_id={snapshot.snapshot_id: snapshot})
    updated = attach_judge_refs_to_eval_cases([case], judge_report)

    expected_verdict_ids = [verdict.verdict_id for verdict in judge_report.case_results[0].judge_verdicts]
    assert updated[0].judge_verdict_refs == expected_verdict_ids


def test_attach_judge_refs_uses_snapshot_and_trace_id() -> None:
    runner = OfflineJudgeRunner(judge_all_cases=True)
    shared_snapshot = _snapshot(
        snapshot_id="snap:shared",
        decision_point=LLMDecisionPoint.PROMOTION,
        input_payload=_promotion_payload(),
    )
    case_one = _eval_case(
        snapshot_id="snap:shared",
        decision_point="promotion",
        passed=False,
        requires_judge_review=False,
        trace_id="trace:1",
    )
    case_two = _eval_case(
        snapshot_id="snap:shared",
        decision_point="promotion",
        passed=False,
        requires_judge_review=False,
        trace_id="trace:2",
    )

    report = runner.run_cases([case_one, case_two], snapshots_by_id={"snap:shared": shared_snapshot})
    updated = attach_judge_refs_to_eval_cases([case_one, case_two], report)

    assert updated[0].judge_verdict_refs != updated[1].judge_verdict_refs


class _ExplodingJudge:
    judge_id = "exploding:test"
    dimension = JudgeDimension.ATTRIBUTION
    rubric = JudgeRubric(
        judge_id="exploding:test",
        dimension=JudgeDimension.ATTRIBUTION,
        name="Exploding",
        description="Explodes on judge call.",
        score_1_anchor="pass",
        score_0_5_anchor="amb",
        score_0_anchor="fail",
    )

    def judge(self, *, input_payload: dict[str, object], snapshot_id: str | None = None, trace_id: str | None = None):
        raise RuntimeError("boom")


def test_judge_exception_becomes_human_review_case() -> None:
    runner = OfflineJudgeRunner(
        promotion_judges=[_ExplodingJudge()],
        belief_judges=[_ExplodingJudge()],
    )
    case = _eval_case(snapshot_id="snap:error", decision_point="promotion", passed=False, requires_judge_review=False)
    snapshot = _snapshot(snapshot_id="snap:error", decision_point=LLMDecisionPoint.PROMOTION, input_payload=_promotion_payload())

    report = runner.run_cases([case], snapshots_by_id={snapshot.snapshot_id: snapshot})

    assert report.case_results[0].golden_candidate_reason == "judge_execution_error"
    assert report.case_results[0].judge_verdicts == []
    assert report.human_review_cases == 1


def test_no_live_llm_calls_are_required() -> None:
    runner = OfflineJudgeRunner()
    case = _eval_case(snapshot_id="snap:offline", decision_point="promotion", passed=False, requires_judge_review=False)
    snapshot = _snapshot(snapshot_id="snap:offline", decision_point=LLMDecisionPoint.PROMOTION, input_payload=_promotion_payload())
    eval_report = EvalRunReport(
        run_id="eval-run:test",
        total_cases=1,
        passed_cases=0,
        failed_cases=1,
        average_score=0.0,
        results=[case],
        count_by_decision_point={"promotion": 1},
        pass_rate_by_decision_point={"promotion": 0.0},
    )

    report = runner.run_eval_report(eval_report, snapshots_by_id={snapshot.snapshot_id: snapshot})

    assert report.judged_cases == 1
    assert report.case_results[0].judge_verdicts
