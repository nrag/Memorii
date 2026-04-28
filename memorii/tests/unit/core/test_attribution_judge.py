from datetime import UTC, datetime

from memorii.core.llm_judge.calibration import JudgeCalibrator
from memorii.core.llm_judge.judge import validate_single_dimension_judge
from memorii.core.llm_judge.judges.attribution import AttributionJudge, attribution_calibration_v1, attribution_rubric
from memorii.core.llm_judge.models import JudgeDimension


def test_attribution_contract_scoring_snapshot_and_stability() -> None:
    rubric = attribution_rubric()
    assert rubric.dimension == JudgeDimension.ATTRIBUTION
    assert rubric.score_1_anchor and rubric.score_0_5_anchor and rubric.score_0_anchor
    fixed = datetime(2026, 1, 1, tzinfo=UTC)
    judge = AttributionJudge(created_at_factory=lambda: fixed)
    validate_single_dimension_judge(judge)

    pass_payload = {"candidate_type": "user_memory", "source_actor": "user", "asserted_by": "user", "content": "remember this"}
    assert judge.judge(input_payload=pass_payload).score == 1.0
    assert judge.judge(input_payload={"candidate_type": "user_memory", "source_actor": "agent", "content": "remember this"}).score == 0.0
    assert judge.judge(input_payload={"candidate_type": "project_fact", "source_kind": "tool", "content": "status"}).score == 0.5
    first = judge.judge(input_payload=pass_payload, snapshot_id="s", trace_id="t")
    second = judge.judge(input_payload=pass_payload, snapshot_id="s", trace_id="t")
    assert first.verdict_id == second.verdict_id
    assert first.created_at == fixed
    assert judge.judge(input_payload={"input_payload": pass_payload}).score == 1.0


def test_attribution_calibration_quality() -> None:
    examples = attribution_calibration_v1()
    assert len(examples) >= 30
    assert any(e.expected_passed for e in examples)
    assert any((not e.expected_passed) and e.expected_score_min == 0.0 for e in examples)
    assert any(e.expected_score_min == 0.5 for e in examples)
    report = JudgeCalibrator().run(judge=AttributionJudge(), examples=examples)
    assert report.agreement_rate >= 0.8
    assert report.false_positive_count <= 3
    assert report.false_negative_count <= 3
    represented = {e.expected_failure_mode for e in examples if e.expected_failure_mode}
    assert set(attribution_rubric().failure_modes).issubset(represented)
    assert report.total_examples > 0
