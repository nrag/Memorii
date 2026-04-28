from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from memorii.core.llm_judge.calibration import (
    JudgeCalibrator,
    build_golden_candidate_reason_from_jury,
    should_promote_to_golden_candidate_from_jury,
)
from memorii.core.llm_judge.judge import FakeSingleDimensionJudge, validate_single_dimension_judge
from memorii.core.llm_judge.jury import JuryAggregator
from memorii.core.llm_judge.models import (
    CalibrationExample,
    JudgeDimension,
    JudgeRubric,
    JudgeVerdict,
    JuryVerdict,
)


def _rubric(*, judge_id: str = "judge:test", dimension: JudgeDimension = JudgeDimension.ATTRIBUTION) -> JudgeRubric:
    return JudgeRubric(
        judge_id=judge_id,
        dimension=dimension,
        name="Test Rubric",
        description="Checks a single dimension.",
        score_1_anchor="Clearly passes",
        score_0_5_anchor="Ambiguous",
        score_0_anchor="Clearly fails",
        pass_threshold=0.7,
    )


def _verdict(
    *,
    verdict_id: str,
    passed: bool,
    score: float,
    needs_human_review: bool = False,
) -> JudgeVerdict:
    return JudgeVerdict(
        verdict_id=verdict_id,
        judge_id="judge:test",
        dimension=JudgeDimension.ATTRIBUTION,
        passed=passed,
        score=score,
        rationale="ok",
        needs_human_review=needs_human_review,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _fake_judge(
    *,
    dimension: JudgeDimension = JudgeDimension.ATTRIBUTION,
    rubric_dimension: JudgeDimension | None = None,
) -> FakeSingleDimensionJudge:
    rubric = _rubric(dimension=rubric_dimension or dimension)
    return FakeSingleDimensionJudge(
        judge_id="judge:test",
        dimension=dimension,
        rubric=rubric,
        default_score=0.8,
        default_rationale="Deterministic fake verdict.",
    )


def test_judge_verdict_rejects_score_outside_range() -> None:
    with pytest.raises(ValidationError):
        JudgeVerdict(
            verdict_id="v:bad",
            judge_id="judge:test",
            dimension=JudgeDimension.ATTRIBUTION,
            passed=True,
            score=1.1,
            rationale="bad",
            created_at=datetime.now(UTC),
        )


def test_judge_rubric_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        JudgeRubric(
            judge_id="judge:test",
            dimension=JudgeDimension.ATTRIBUTION,
            name="Rubric",
            description="desc",
            score_1_anchor="1",
            score_0_5_anchor="0.5",
            score_0_anchor="0",
            unexpected="nope",
        )


def test_validate_single_dimension_judge_passes_valid_fake_judge() -> None:
    validate_single_dimension_judge(_fake_judge())


def test_validate_single_dimension_judge_fails_dimension_mismatch() -> None:
    with pytest.raises(ValueError, match="dimension"):
        validate_single_dimension_judge(
            _fake_judge(
                dimension=JudgeDimension.ATTRIBUTION,
                rubric_dimension=JudgeDimension.BELIEF_DIRECTION,
            )
        )


def test_jury_aggregator_aggregates_all_passing_verdicts() -> None:
    aggregator = JuryAggregator()

    jury = aggregator.aggregate(
        verdicts=[
            _verdict(verdict_id="v:1", passed=True, score=0.8),
            _verdict(verdict_id="v:2", passed=True, score=0.9),
        ],
        snapshot_id="snap:1",
    )

    assert jury.passed is True
    assert jury.disagreement is False
    assert jury.needs_human_review is False
    assert jury.aggregate_score == pytest.approx(0.85)


def test_jury_aggregator_detects_pass_fail_disagreement() -> None:
    aggregator = JuryAggregator()

    jury = aggregator.aggregate(
        verdicts=[
            _verdict(verdict_id="v:1", passed=True, score=0.8),
            _verdict(verdict_id="v:2", passed=False, score=0.7),
        ]
    )

    assert jury.passed is False
    assert jury.disagreement is True
    assert jury.needs_human_review is True


def test_jury_aggregator_detects_score_range_disagreement() -> None:
    aggregator = JuryAggregator()

    jury = aggregator.aggregate(
        verdicts=[
            _verdict(verdict_id="v:1", passed=True, score=0.9),
            _verdict(verdict_id="v:2", passed=True, score=0.4),
        ]
    )

    assert jury.passed is True
    assert jury.disagreement is True
    assert jury.needs_human_review is True


def test_jury_aggregator_marks_empty_verdict_list_as_human_review() -> None:
    aggregator = JuryAggregator()

    jury = aggregator.aggregate(verdicts=[])

    assert jury.passed is False
    assert jury.aggregate_score == 0.0
    assert jury.needs_human_review is True


def test_judge_calibrator_computes_agreement_rate() -> None:
    calibrator = JudgeCalibrator()
    judge = _fake_judge()
    examples = [
        CalibrationExample(
            example_id="e:1",
            dimension=JudgeDimension.ATTRIBUTION,
            input_payload={},
            expected_passed=True,
            expected_score_min=0.7,
            expected_score_max=0.9,
        ),
        CalibrationExample(
            example_id="e:2",
            dimension=JudgeDimension.ATTRIBUTION,
            input_payload={"fail": True},
            expected_passed=False,
            expected_score_min=0.0,
            expected_score_max=0.69,
        ),
    ]

    judge.score_by_input_key["fail"] = 0.3
    report = calibrator.run(judge=judge, examples=examples)

    assert report.agreement_rate == pytest.approx(1.0)
    assert report.total_examples == 2


def test_judge_calibrator_counts_false_positives_and_false_negatives() -> None:
    calibrator = JudgeCalibrator()
    judge = _fake_judge()
    judge.score_by_input_key = {"high": 0.9, "low": 0.1}

    examples = [
        CalibrationExample(
            example_id="e:fp",
            dimension=JudgeDimension.ATTRIBUTION,
            input_payload={"high": True},
            expected_passed=False,
            expected_score_min=0.0,
            expected_score_max=1.0,
        ),
        CalibrationExample(
            example_id="e:fn",
            dimension=JudgeDimension.ATTRIBUTION,
            input_payload={"low": True},
            expected_passed=True,
            expected_score_min=0.0,
            expected_score_max=1.0,
        ),
    ]

    report = calibrator.run(judge=judge, examples=examples)

    assert report.false_positive_count == 1
    assert report.false_negative_count == 1


def test_judge_calibrator_counts_ambiguous_score_cases() -> None:
    calibrator = JudgeCalibrator()
    judge = _fake_judge()
    judge.score_by_input_key = {"ambiguous": 0.2}

    examples = [
        CalibrationExample(
            example_id="e:amb",
            dimension=JudgeDimension.ATTRIBUTION,
            input_payload={"ambiguous": True},
            expected_passed=False,
            expected_score_min=0.5,
            expected_score_max=0.7,
        )
    ]

    report = calibrator.run(judge=judge, examples=examples)

    assert report.ambiguous_count == 1


def test_should_promote_to_golden_candidate_from_jury_flags_key_conditions() -> None:
    disagreement = JuryVerdict(
        jury_id="jury:1",
        verdicts=[_verdict(verdict_id="v:1", passed=True, score=0.8)],
        passed=True,
        aggregate_score=0.8,
        disagreement=True,
        created_at=datetime.now(UTC),
    )
    human_review = JuryVerdict(
        jury_id="jury:2",
        verdicts=[_verdict(verdict_id="v:2", passed=True, score=0.8)],
        passed=True,
        aggregate_score=0.8,
        needs_human_review=True,
        created_at=datetime.now(UTC),
    )
    failed = JuryVerdict(
        jury_id="jury:3",
        verdicts=[_verdict(verdict_id="v:3", passed=False, score=0.2)],
        passed=False,
        aggregate_score=0.2,
        created_at=datetime.now(UTC),
    )

    assert should_promote_to_golden_candidate_from_jury(disagreement) is True
    assert should_promote_to_golden_candidate_from_jury(human_review) is True
    assert should_promote_to_golden_candidate_from_jury(failed) is True


def test_build_golden_candidate_reason_from_jury_returns_stable_reason_strings() -> None:
    base = {
        "jury_id": "jury:x",
        "verdicts": [_verdict(verdict_id="v:1", passed=True, score=0.8)],
        "aggregate_score": 0.8,
        "created_at": datetime.now(UTC),
    }

    disagreement = JuryVerdict(**base, passed=True, disagreement=True)
    human_review = JuryVerdict(**base, passed=True, needs_human_review=True)
    failed = JuryVerdict(**base, passed=False)

    assert build_golden_candidate_reason_from_jury(disagreement) == "judge_disagreement"
    assert build_golden_candidate_reason_from_jury(human_review) == "judge_human_review_required"
    assert build_golden_candidate_reason_from_jury(failed) == "judge_failed"


def test_fake_single_dimension_judge_can_be_used_without_llm_calls() -> None:
    judge = FakeSingleDimensionJudge(
        judge_id="judge:test",
        dimension=JudgeDimension.ATTRIBUTION,
        rubric=_rubric(),
        default_score=0.9,
        default_rationale="Fake judge",
        score_by_input_key={"bad": 0.2},
        failure_mode_by_input_key={"bad": "missing_evidence"},
    )

    passing = judge.judge(input_payload={"ok": True}, snapshot_id="snap:1")
    failing = judge.judge(input_payload={"bad": True}, trace_id="trace:1")

    assert passing.passed is True
    assert failing.passed is False
    assert failing.failure_mode == "missing_evidence"
