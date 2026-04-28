from datetime import UTC, datetime

from memorii.core.llm_judge.calibration import JudgeCalibrator
from memorii.core.llm_judge.judge import validate_single_dimension_judge
from memorii.core.llm_judge.judges.promotion_precision import (
    PromotionPrecisionJudge,
    promotion_precision_calibration_v1,
    promotion_precision_rubric,
)
from memorii.core.llm_judge.models import JudgeDimension
from memorii.core.promotion.models import PromotionCandidateType


def _payload(
    *,
    candidate_id: str = "cand:test",
    candidate_type: PromotionCandidateType = PromotionCandidateType.EPISODIC,
    content: str = "default content",
    created_from: str = "observation",
    repeated_across_episodes: int = 0,
    explicit_user_memory_request: bool = False,
    related_memory_ids: list[str] | None = None,
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "candidate_type": candidate_type.value,
        "content": content,
        "source_ids": ["src:test"],
        "related_memory_ids": related_memory_ids or [],
        "repeated_across_episodes": repeated_across_episodes,
        "explicit_user_memory_request": explicit_user_memory_request,
        "created_from": created_from,
        "metadata": metadata or {},
    }


def test_rubric_has_dimension_promotion_precision() -> None:
    rubric = promotion_precision_rubric()
    assert rubric.dimension == JudgeDimension.PROMOTION_PRECISION


def test_rubric_anchors_are_non_empty() -> None:
    rubric = promotion_precision_rubric()
    assert rubric.score_1_anchor.strip()
    assert rubric.score_0_5_anchor.strip()
    assert rubric.score_0_anchor.strip()


def test_judge_validates_with_single_dimension_contract() -> None:
    judge = PromotionPrecisionJudge()
    validate_single_dimension_judge(judge)


def test_explicit_user_memory_scores_pass() -> None:
    verdict = PromotionPrecisionJudge().judge(
        input_payload=_payload(
            candidate_type=PromotionCandidateType.USER_MEMORY,
            explicit_user_memory_request=True,
        )
    )
    assert verdict.passed is True
    assert verdict.score == 1.0


def test_task_outcome_scores_pass() -> None:
    verdict = PromotionPrecisionJudge().judge(
        input_payload=_payload(created_from="task_outcome", content="Completed migration and validated outputs.")
    )
    assert verdict.passed is True
    assert verdict.score == 1.0


def test_decision_finalized_scores_pass() -> None:
    verdict = PromotionPrecisionJudge().judge(
        input_payload=_payload(created_from="decision_finalized", content="Finalized architecture decision.")
    )
    assert verdict.passed is True
    assert verdict.score == 1.0


def test_noisy_observation_fails() -> None:
    verdict = PromotionPrecisionJudge().judge(
        input_payload=_payload(content="User asked if tests are green.", repeated_across_episodes=1)
    )
    assert verdict.passed is False
    assert verdict.score == 0.0
    assert verdict.failure_mode == "noise"


def test_one_off_user_preference_fails() -> None:
    verdict = PromotionPrecisionJudge().judge(
        input_payload=_payload(
            candidate_type=PromotionCandidateType.USER_MEMORY,
            content="For this trip I prefer window seat",
            repeated_across_episodes=1,
        )
    )
    assert verdict.passed is False
    assert verdict.score == 0.0
    assert verdict.failure_mode == "one_off_preference"


def test_repeated_inferred_user_preference_scores_ambiguous() -> None:
    verdict = PromotionPrecisionJudge().judge(
        input_payload=_payload(
            candidate_type=PromotionCandidateType.USER_MEMORY,
            content="User repeatedly asks for concise responses.",
            repeated_across_episodes=3,
        )
    )
    assert verdict.passed is False
    assert verdict.score == 0.5
    assert verdict.failure_mode == "ambiguous_scope"


def test_time_bound_planning_scores_ambiguous() -> None:
    verdict = PromotionPrecisionJudge().judge(
        input_payload=_payload(
            candidate_type=PromotionCandidateType.PROJECT_FACT,
            content="Use temporary config for now during this sprint.",
            repeated_across_episodes=5,
        )
    )
    assert verdict.passed is False
    assert verdict.score == 0.5
    assert verdict.failure_mode == "transient_context"


def test_duplicate_prone_candidate_scores_ambiguous() -> None:
    verdict = PromotionPrecisionJudge().judge(
        input_payload=_payload(
            candidate_type=PromotionCandidateType.SEMANTIC,
            content="Known retry policy",
            repeated_across_episodes=4,
            related_memory_ids=["mem:123"],
        )
    )
    assert verdict.passed is False
    assert verdict.score == 0.5
    assert verdict.failure_mode == "ambiguous_scope"


def test_verdict_id_is_stable_for_same_input() -> None:
    judge = PromotionPrecisionJudge()
    payload = _payload(candidate_type=PromotionCandidateType.USER_MEMORY, explicit_user_memory_request=True)
    first = judge.judge(input_payload=payload, snapshot_id="snap:1", trace_id="trace:1")
    second = judge.judge(input_payload=payload, snapshot_id="snap:1", trace_id="trace:1")
    assert first.verdict_id == second.verdict_id


def test_created_at_factory_makes_timestamp_deterministic() -> None:
    fixed = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
    judge = PromotionPrecisionJudge(created_at_factory=lambda: fixed)
    verdict = judge.judge(input_payload=_payload())
    assert verdict.created_at == fixed


def test_eval_snapshot_shaped_payload_is_supported() -> None:
    payload = {
        "snapshot_id": "promotion:snap:1",
        "decision_point": "promotion",
        "input_payload": _payload(candidate_type=PromotionCandidateType.USER_MEMORY, explicit_user_memory_request=True),
        "expected_output": None,
        "source": "offline_golden",
        "tags": ["test"],
        "created_at": "2026-01-01T00:00:00Z",
    }
    verdict = PromotionPrecisionJudge().judge(input_payload=payload)
    assert verdict.passed is True


def test_calibration_set_has_at_least_30_examples() -> None:
    examples = promotion_precision_calibration_v1()
    assert len(examples) >= 30


def test_calibration_set_has_pass_fail_ambiguous_coverage() -> None:
    examples = promotion_precision_calibration_v1()
    scores = {example.expected_score_min for example in examples}
    assert any(example.expected_passed for example in examples)
    assert any(not example.expected_passed for example in examples)
    assert 0.5 in scores


def test_calibration_examples_cover_required_domains() -> None:
    examples = promotion_precision_calibration_v1()
    tags = {tag for example in examples for tag in example.tags}
    required = {
        "domain:software_engineering",
        "domain:product_project_planning",
        "domain:customer_support",
        "domain:personal_assistant",
        "domain:research",
        "domain:incident_debugging",
        "domain:architecture_decisions",
    }
    assert required.issubset(tags)


def test_judge_calibrator_runs_on_calibration_set() -> None:
    report = JudgeCalibrator().run(judge=PromotionPrecisionJudge(), examples=promotion_precision_calibration_v1())
    assert report.total_examples >= 30


def test_calibration_agreement_rate_is_at_least_point_8() -> None:
    report = JudgeCalibrator().run(judge=PromotionPrecisionJudge(), examples=promotion_precision_calibration_v1())
    assert report.agreement_rate >= 0.8


def test_false_positive_count_is_low() -> None:
    report = JudgeCalibrator().run(judge=PromotionPrecisionJudge(), examples=promotion_precision_calibration_v1())
    assert report.false_positive_count <= 2


def test_false_negative_count_is_low() -> None:
    report = JudgeCalibrator().run(judge=PromotionPrecisionJudge(), examples=promotion_precision_calibration_v1())
    assert report.false_negative_count <= 2


def test_no_live_llm_calls_are_required() -> None:
    report = JudgeCalibrator().run(judge=PromotionPrecisionJudge(), examples=promotion_precision_calibration_v1())
    assert report.total_examples > 0
