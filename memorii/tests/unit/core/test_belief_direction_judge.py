from datetime import UTC, datetime

from memorii.core.llm_judge.calibration import JudgeCalibrator
from memorii.core.llm_judge.judge import validate_single_dimension_judge
from memorii.core.llm_judge.judges.belief_direction import (
    BeliefDirectionJudge,
    belief_direction_calibration_v1,
    belief_direction_rubric,
)
from memorii.core.llm_judge.models import JudgeDimension


def _ctx(decision: str, prior: float = 0.4, *, conflicts: int = 0, downgraded: bool = False) -> dict[str, object]:
    return {
        "prior_belief": prior,
        "decision": decision,
        "evidence_count": 2,
        "missing_evidence_count": 0,
        "verifier_downgraded": downgraded,
        "conflict_count": conflicts,
        "evidence_ids": ["e:1"],
        "missing_evidence": [],
        "metadata": {},
    }


def test_belief_direction_contract_and_cases() -> None:
    assert belief_direction_rubric().dimension == JudgeDimension.BELIEF_DIRECTION
    judge = BeliefDirectionJudge()
    validate_single_dimension_judge(judge)
    assert judge.judge(input_payload={"context": _ctx("SUPPORTED"), "actual_output": {"belief": 0.8}}).score == 1.0
    assert judge.judge(input_payload={"context": _ctx("REFUTED", prior=0.7), "actual_output": {"belief": 0.8}}).score == 0.0
    assert judge.judge(input_payload={"context": _ctx("SUPPORTED", conflicts=1), "actual_output": {"belief": 0.43}}).score == 0.5


def test_belief_direction_stability_created_and_snapshot() -> None:
    fixed = datetime(2026, 1, 1, tzinfo=UTC)
    judge = BeliefDirectionJudge(created_at_factory=lambda: fixed)
    payload = {"context": _ctx("SUPPORTED"), "actual_output": {"belief": 0.8}}
    one = judge.judge(input_payload=payload, snapshot_id="s", trace_id="t")
    two = judge.judge(input_payload=payload, snapshot_id="s", trace_id="t")
    assert one.verdict_id == two.verdict_id
    assert one.created_at == fixed
    snap = {"input_payload": _ctx("SUPPORTED"), "actual_output": {"belief": 0.8}}
    assert judge.judge(input_payload=snap).score == 1.0


def test_belief_direction_calibration_quality() -> None:
    examples = belief_direction_calibration_v1()
    assert len(examples) >= 30
    report = JudgeCalibrator().run(judge=BeliefDirectionJudge(), examples=examples)
    assert report.agreement_rate >= 0.8
    assert report.false_positive_count <= 3
    assert report.false_negative_count <= 3
    represented = {e.expected_failure_mode for e in examples if e.expected_failure_mode}
    assert set(belief_direction_rubric().failure_modes).intersection(represented)
    assert report.total_examples > 0
