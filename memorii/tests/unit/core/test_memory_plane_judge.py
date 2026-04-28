from datetime import UTC, datetime

from memorii.core.llm_judge.calibration import JudgeCalibrator
from memorii.core.llm_judge.judge import validate_single_dimension_judge
from memorii.core.llm_judge.judges.memory_plane import MemoryPlaneJudge, memory_plane_calibration_v1, memory_plane_rubric
from memorii.core.llm_judge.models import JudgeDimension


def _payload(ctype: str, content: str, created_from: str = "observation") -> dict[str, object]:
    return {
        "candidate_id": "cand:mp",
        "candidate_type": ctype,
        "content": content,
        "source_ids": ["src:1"],
        "related_memory_ids": [],
        "repeated_across_episodes": 3,
        "explicit_user_memory_request": ctype == "user_memory",
        "created_from": created_from,
        "metadata": {},
    }


def test_memory_plane_contract_and_cases() -> None:
    rubric = memory_plane_rubric()
    assert rubric.dimension == JudgeDimension.MEMORY_PLANE
    assert rubric.score_1_anchor and rubric.score_0_5_anchor and rubric.score_0_anchor
    judge = MemoryPlaneJudge()
    validate_single_dimension_judge(judge)
    assert judge.judge(input_payload={"context": _payload("user_memory", "remember this"), "actual_output": {"target_plane": "user_memory"}}).score == 1.0
    assert judge.judge(input_payload={"context": _payload("semantic", "general fact"), "actual_output": {"target_plane": "project_fact"}}).score == 0.0
    assert judge.judge(input_payload={"context": _payload("user_memory", "inferred"), "actual_output": {"target_plane": "user_memory"}}).score in {0.5, 1.0}
    assert judge.judge(input_payload={"context": _payload("project_fact", "customer contract requires SSO"), "actual_output": {}}).score == 0.5


def test_memory_plane_stability_created_and_snapshot() -> None:
    fixed = datetime(2026, 1, 1, tzinfo=UTC)
    judge = MemoryPlaneJudge(created_at_factory=lambda: fixed)
    payload = {"context": _payload("semantic", "general parser rule"), "actual_output": {"target_plane": "semantic"}}
    first = judge.judge(input_payload=payload, snapshot_id="s", trace_id="t")
    second = judge.judge(input_payload=payload, snapshot_id="s", trace_id="t")
    assert first.verdict_id == second.verdict_id
    assert first.created_at == fixed
    assert judge.judge(input_payload={"input_payload": _payload("semantic", "general rule"), "actual_output": {"target_plane": "semantic"}}).score == 1.0


def test_memory_plane_calibration_quality() -> None:
    examples = memory_plane_calibration_v1()
    assert len(examples) >= 30
    assert any(e.expected_passed for e in examples)
    assert any(e.expected_score_min == 0.5 for e in examples)
    report = JudgeCalibrator().run(judge=MemoryPlaneJudge(), examples=examples)
    assert report.agreement_rate >= 0.8
    assert report.false_positive_count <= 3
    assert report.false_negative_count <= 3
    represented = {e.expected_failure_mode for e in examples if e.expected_failure_mode}
    assert "ambiguous_plane" in represented
    assert "should_be_project_fact" in represented
    assert "should_be_user_memory" in represented
    assert report.total_examples > 0
