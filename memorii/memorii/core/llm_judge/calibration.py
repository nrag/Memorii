"""Calibration runner and golden-candidate helpers for jury outcomes."""

from __future__ import annotations

from collections import Counter

from memorii.core.llm_judge.judge import SingleDimensionJudge, validate_single_dimension_judge
from memorii.core.llm_judge.models import CalibrationExample, JudgeCalibrationReport, JuryVerdict


class JudgeCalibrator:
    def run(
        self,
        *,
        judge: SingleDimensionJudge,
        examples: list[CalibrationExample],
    ) -> JudgeCalibrationReport:
        validate_single_dimension_judge(judge)

        false_positive_count = 0
        false_negative_count = 0
        ambiguous_count = 0
        passed_examples = 0
        failed_examples = 0
        agreement_count = 0
        failure_mode_counts: Counter[str] = Counter()

        for example in examples:
            if example.dimension != judge.dimension:
                raise ValueError("calibration example dimension must match judge dimension")

            verdict = judge.judge(input_payload=example.input_payload)

            if verdict.passed:
                passed_examples += 1
            else:
                failed_examples += 1

            if verdict.passed == example.expected_passed:
                agreement_count += 1
            elif verdict.passed and not example.expected_passed:
                false_positive_count += 1
            elif not verdict.passed and example.expected_passed:
                false_negative_count += 1

            score_outside_bounds = not (example.expected_score_min <= verdict.score <= example.expected_score_max)
            if score_outside_bounds or verdict.needs_human_review:
                ambiguous_count += 1

            if verdict.failure_mode:
                failure_mode_counts[verdict.failure_mode] += 1

        total_examples = len(examples)
        agreement_rate = agreement_count / total_examples if total_examples else 0.0

        return JudgeCalibrationReport(
            judge_id=judge.judge_id,
            dimension=judge.dimension,
            total_examples=total_examples,
            passed_examples=passed_examples,
            failed_examples=failed_examples,
            agreement_rate=agreement_rate,
            false_positive_count=false_positive_count,
            false_negative_count=false_negative_count,
            ambiguous_count=ambiguous_count,
            failure_mode_counts=dict(failure_mode_counts),
        )


def should_promote_to_golden_candidate_from_jury(jury: JuryVerdict) -> bool:
    return jury.disagreement or jury.needs_human_review or not jury.passed


def build_golden_candidate_reason_from_jury(jury: JuryVerdict) -> str:
    if jury.disagreement:
        return "judge_disagreement"
    if jury.needs_human_review:
        return "judge_human_review_required"
    if not jury.passed:
        return "judge_failed"
    return "judge_passed"
