from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pytest

from memorii.core.llm_decision.models import EvalSnapshot, LLMDecisionPoint
from memorii.core.llm_eval.models import EvalCaseResult
from memorii.core.llm_judge.artifacts import JudgeArtifactPolicy, JudgeArtifactWriter
from memorii.core.llm_judge.models import JudgeDimension, JudgeVerdict, JuryVerdict
from memorii.core.llm_judge.runner import JudgeRunCaseResult, JudgeRunReport


def _case(idx: int, passed: bool, review: bool, disagreement: bool, golden: bool) -> JudgeRunCaseResult:
    verdict = JudgeVerdict(verdict_id=f"v{idx}", judge_id="j", dimension=JudgeDimension.ATTRIBUTION, passed=passed, score=0.9 if passed else 0.1, rationale="r", created_at=datetime.now(timezone.utc))
    jury = JuryVerdict(jury_id="jury:run1", snapshot_id=f"s{idx}", trace_id=f"t{idx}", verdicts=[verdict], passed=passed, aggregate_score=0.9 if passed else 0.1, disagreement=disagreement, needs_human_review=review, created_at=datetime.now(timezone.utc))
    return JudgeRunCaseResult(eval_snapshot_id=f"s{idx}", decision_point="promotion", eval_passed=passed, eval_requires_judge_review=False, judge_verdicts=[verdict], jury_verdict=jury, golden_candidate_reason="x" if golden else None)


def _report() -> JudgeRunReport:
    cases = [_case(1, True, False, False, False), _case(2, False, True, True, True)]
    return JudgeRunReport(run_id="judge-run:abc123", total_eval_cases=2, judged_cases=2, skipped_cases=0, jury_passed_cases=1, jury_failed_cases=1, disagreement_cases=1, human_review_cases=1, golden_candidate_cases=1, case_results=cases)


def test_writer_layout_and_content(tmp_path):
    writer = JudgeArtifactWriter(storage_root=tmp_path, date_provider=lambda: date(2026, 4, 28))
    report = _report()
    eval_cases = [EvalCaseResult(snapshot_id="s1", decision_point="promotion", passed=True, score=1.0, actual_output={}), EvalCaseResult(snapshot_id="s2", decision_point="promotion", passed=False, score=0.0, actual_output={})]
    snapshots = [EvalSnapshot(snapshot_id="s1", decision_point=LLMDecisionPoint.PROMOTION, input_payload={}, expected_output={}, source="t", created_at=datetime.now(timezone.utc))]
    result = writer.write_run_artifacts(judge_report=report, eval_cases=eval_cases, snapshots=snapshots)
    assert "judge-run-abc123" in result.run_dir
    run_dir = tmp_path / "eval_runs/judge/2026-04-28/judge-run-abc123"
    assert (run_dir / "report.json").exists()
    assert json.loads((run_dir / "report.json").read_text())["run_id"] == "judge-run:abc123"
    summary = (run_dir / "summary.txt").read_text()
    assert "jury_failed_cases: 1" in summary
    assert (run_dir / "verdicts.jsonl").exists()
    assert (run_dir / "juries.jsonl").exists()
    assert (run_dir / "failed_cases.jsonl").exists()
    assert (run_dir / "human_review_cases.jsonl").exists()
    assert (run_dir / "disagreement_cases.jsonl").exists()
    assert (run_dir / "golden_candidates.jsonl").exists()
    assert (run_dir / "inputs/eval_cases.jsonl").exists()
    assert (run_dir / "inputs/snapshots.jsonl").exists()
    assert (tmp_path / "review/human_review_candidates.jsonl").exists()


def test_policies_and_overwrite(tmp_path):
    report = _report()
    writer = JudgeArtifactWriter(storage_root=tmp_path, policy=JudgeArtifactPolicy(persist_full_runs=False), date_provider=lambda: date(2026, 4, 28))
    res = writer.write_run_artifacts(judge_report=report, eval_cases=[], snapshots=[])
    assert res.run_dir is None
    assert (tmp_path / "review/failed_cases.jsonl").exists()

    writer_none = JudgeArtifactWriter(storage_root=tmp_path, policy=JudgeArtifactPolicy(persist_full_runs=False, write_review_queues=False))
    res_none = writer_none.write_run_artifacts(judge_report=report, eval_cases=[], snapshots=[])
    assert res_none.skipped_reason == "artifact_persistence_disabled"

    strict = JudgeArtifactWriter(storage_root=tmp_path, date_provider=lambda: date(2026, 4, 28))
    strict.write_run_artifacts(judge_report=report, eval_cases=[], snapshots=[])
    with pytest.raises(FileExistsError):
        strict.write_run_artifacts(judge_report=report, eval_cases=[], snapshots=[])
    overwrite = JudgeArtifactWriter(storage_root=tmp_path, policy=JudgeArtifactPolicy(overwrite_existing_run=True), date_provider=lambda: date(2026, 4, 28))
    overwrite.write_run_artifacts(judge_report=report, eval_cases=[], snapshots=[])


def test_passing_case_filtered_and_policy_extra_forbidden(tmp_path):
    report = _report()
    writer = JudgeArtifactWriter(storage_root=tmp_path, date_provider=lambda: date(2026, 4, 28))
    writer.write_run_artifacts(judge_report=report, eval_cases=[], snapshots=[])
    lines = (tmp_path / "eval_runs/judge/2026-04-28/judge-run-abc123/verdicts.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1
    with pytest.raises(Exception):
        JudgeArtifactPolicy(extra_field=True)  # type: ignore[arg-type]
