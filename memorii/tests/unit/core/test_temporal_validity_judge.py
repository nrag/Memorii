from datetime import UTC, datetime

from memorii.core.llm_judge.calibration import JudgeCalibrator
from memorii.core.llm_judge.judge import validate_single_dimension_judge
from memorii.core.llm_judge.judges.temporal_validity import (
    TemporalValidityJudge,
    temporal_validity_calibration_v1,
    temporal_validity_rubric,
)
from memorii.core.llm_judge.models import JudgeDimension


def _payload(content: str, *, ctype: str = "project_fact", metadata: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "candidate_id": "cand:tv",
        "candidate_type": ctype,
        "content": content,
        "source_ids": ["src:1"],
        "related_memory_ids": [],
        "repeated_across_episodes": 4,
        "explicit_user_memory_request": "remember" in content.lower(),
        "created_from": "observation",
        "metadata": metadata or {},
    }


def test_temporal_validity_contract_and_scoring() -> None:
    rubric = temporal_validity_rubric()
    assert rubric.dimension == JudgeDimension.TEMPORAL_VALIDITY
    assert rubric.score_1_anchor and rubric.score_0_5_anchor and rubric.score_0_anchor
    judge = TemporalValidityJudge()
    validate_single_dimension_judge(judge)
    assert judge.judge(input_payload=_payload("Remember this permanent preference.", ctype="user_memory")).score == 1.0
    assert judge.judge(input_payload=_payload("Use workaround for now this sprint.")).score == 0.5
    assert judge.judge(input_payload=_payload("already obsolete and no longer applies")).score == 0.0


def test_temporal_validity_stable_id_and_created_at_and_snapshot_support() -> None:
    fixed = datetime(2026, 1, 1, tzinfo=UTC)
    judge = TemporalValidityJudge(created_at_factory=lambda: fixed)
    payload = _payload("Finalized stable fact")
    first = judge.judge(input_payload=payload, snapshot_id="s", trace_id="t")
    second = judge.judge(input_payload=payload, snapshot_id="s", trace_id="t")
    assert first.verdict_id == second.verdict_id
    assert first.created_at == fixed
    snap = {"input_payload": payload}
    assert judge.judge(input_payload=snap).score == 1.0


def test_temporal_validity_calibration_quality() -> None:
    examples = temporal_validity_calibration_v1()
    assert len(examples) >= 30
    assert any(e.expected_passed for e in examples)
    assert any((not e.expected_passed) and e.expected_score_min == 0.0 for e in examples)
    assert any(e.expected_score_min == 0.5 for e in examples)
    tags = {t for e in examples for t in e.tags}
    required = {
        "domain:personal_assistant",
        "domain:product_project_planning",
        "domain:incident_debugging",
        "domain:architecture_decisions",
        "domain:customer_support",
    }
    assert required.issubset(tags)
    report = JudgeCalibrator().run(judge=TemporalValidityJudge(), examples=examples)
    assert report.total_examples >= 30
    assert report.agreement_rate >= 0.8
    assert report.false_positive_count <= 3
    assert report.false_negative_count <= 3
    expected_modes = set(temporal_validity_rubric().failure_modes)
    represented = {e.expected_failure_mode for e in examples if e.expected_failure_mode}
    assert expected_modes.issubset(represented)
    assert report.total_examples > 0
