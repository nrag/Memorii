from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pytest

from memorii.core.llm_decision.models import EvalSnapshot, LLMDecisionPoint
from memorii.core.llm_eval.models import EvalCaseResult
from memorii.core.llm_judge.artifacts import JudgeArtifactPolicy, JudgeArtifactWriter
from memorii.core.llm_judge.models import JudgeDimension, JudgeVerdict, JuryVerdict
from memorii.core.llm_judge.runner import JudgeRunCaseResult, JudgeRunReport


FIXED_NOW = datetime(2026, 4, 28, 12, 0, tzinfo=timezone.utc)


def _case(idx: int, passed: bool, review: bool, disagreement: bool, golden: bool) -> JudgeRunCaseResult:
    verdict = JudgeVerdict(
        verdict_id=f"v{idx}",
        judge_id="j",
        dimension=JudgeDimension.ATTRIBUTION,
        passed=passed,
        score=0.9 if passed else 0.1,
        rationale="r",
        created_at=FIXED_NOW,
    )
    jury = JuryVerdict(
        jury_id="jury:abc",
        snapshot_id=f"s{idx}",
        trace_id=f"t{idx}",
        verdicts=[verdict],
        passed=passed,
        aggregate_score=0.9 if passed else 0.1,
        disagreement=disagreement,
        needs_human_review=review,
        created_at=FIXED_NOW,
    )
    return JudgeRunCaseResult(
        eval_snapshot_id=f"s{idx}",
        decision_point="promotion",
        eval_passed=passed,
        eval_requires_judge_review=False,
        judge_verdicts=[verdict],
        jury_verdict=jury,
        golden_candidate_reason="x" if golden else None,
    )


def _report() -> JudgeRunReport:
    return JudgeRunReport(
        run_id="judge-run:abc123",
        total_eval_cases=2,
        judged_cases=2,
        skipped_cases=0,
        jury_passed_cases=1,
        jury_failed_cases=1,
        disagreement_cases=1,
        human_review_cases=1,
        golden_candidate_cases=1,
        case_results=[_case(1, True, False, False, False), _case(2, False, True, True, True)],
    )


def test_writer_layout_and_filtering(tmp_path):
    writer = JudgeArtifactWriter(storage_root=tmp_path, date_provider=lambda: date(2026, 4, 28), datetime_provider=lambda: FIXED_NOW)
    result = writer.write_run_artifacts(
        judge_report=_report(),
        eval_cases=[EvalCaseResult(snapshot_id="s1", decision_point="promotion", passed=True, score=1.0, actual_output={})],
        snapshots=[EvalSnapshot(snapshot_id="s1", decision_point=LLMDecisionPoint.PROMOTION, input_payload={}, expected_output={}, source="test", created_at=FIXED_NOW)],
    )
    run_dir = tmp_path / "eval_runs/judge/2026-04-28/judge-run-abc123"
    assert "judge-run-abc123" in result.run_dir
    assert json.loads((run_dir / "report.json").read_text())["run_id"] == "judge-run:abc123"
    verdict_rows = [json.loads(v) for v in (run_dir / "verdicts.jsonl").read_text().strip().splitlines()]
    assert len(verdict_rows) == 1
    assert verdict_rows[0]["verdict_id"] == "v2"
    jury_rows = [json.loads(v) for v in (run_dir / "juries.jsonl").read_text().strip().splitlines()]
    assert len(jury_rows) == 1
    golden_row = json.loads((run_dir / "golden_candidates.jsonl").read_text().strip())
    assert golden_row["source_run_id"] == "judge-run:abc123"
    assert golden_row["created_at"] == FIXED_NOW.isoformat()

    review_failed_rows = [json.loads(v) for v in (tmp_path / "review/failed_cases.jsonl").read_text().strip().splitlines()]
    assert len(review_failed_rows) == 1
    assert review_failed_rows[0]["eval_snapshot_id"] == "s2"


def test_persist_passing_cases_true_includes_all(tmp_path):
    writer = JudgeArtifactWriter(
        storage_root=tmp_path,
        policy=JudgeArtifactPolicy(persist_passing_cases=True),
        date_provider=lambda: date(2026, 4, 28),
        datetime_provider=lambda: FIXED_NOW,
    )
    writer.write_run_artifacts(judge_report=_report(), eval_cases=[], snapshots=[])
    run_dir = tmp_path / "eval_runs/judge/2026-04-28/judge-run-abc123"
    assert len((run_dir / "verdicts.jsonl").read_text().strip().splitlines()) == 2
    assert len((run_dir / "juries.jsonl").read_text().strip().splitlines()) == 2


def test_policies_overwrite_and_append_only_review(tmp_path):
    report = _report()
    only_review = JudgeArtifactWriter(storage_root=tmp_path, policy=JudgeArtifactPolicy(persist_full_runs=False), datetime_provider=lambda: FIXED_NOW)
    res = only_review.write_run_artifacts(judge_report=report, eval_cases=[], snapshots=[])
    assert res.run_dir is None

    disabled = JudgeArtifactWriter(storage_root=tmp_path, policy=JudgeArtifactPolicy(persist_full_runs=False, write_review_queues=False))
    assert disabled.write_run_artifacts(judge_report=report, eval_cases=[], snapshots=[]).skipped_reason == "artifact_persistence_disabled"

    strict = JudgeArtifactWriter(storage_root=tmp_path, date_provider=lambda: date(2026, 4, 28), datetime_provider=lambda: FIXED_NOW)
    strict.write_run_artifacts(judge_report=report, eval_cases=[], snapshots=[])
    stale_file = tmp_path / "eval_runs/judge/2026-04-28/judge-run-abc123/stale.txt"
    stale_file.write_text("stale")
    with pytest.raises(FileExistsError):
        strict.write_run_artifacts(judge_report=report, eval_cases=[], snapshots=[])

    overwrite = JudgeArtifactWriter(storage_root=tmp_path, policy=JudgeArtifactPolicy(overwrite_existing_run=True), date_provider=lambda: date(2026, 4, 28), datetime_provider=lambda: FIXED_NOW)
    overwrite.write_run_artifacts(judge_report=report, eval_cases=[], snapshots=[])
    assert not stale_file.exists()

    overwrite.write_run_artifacts(judge_report=report, eval_cases=[], snapshots=[])
    golden_review_lines = (tmp_path / "review/golden_candidates.jsonl").read_text().strip().splitlines()
    assert len(golden_review_lines) >= 2


def test_policy_extra_forbidden() -> None:
    with pytest.raises(Exception):
        JudgeArtifactPolicy(extra_field=True)  # type: ignore[arg-type]
