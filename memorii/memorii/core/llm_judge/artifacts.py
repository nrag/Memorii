"""Artifact writer for offline judge runs with selective persistence policy."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

from pydantic import BaseModel, ConfigDict

from memorii.core.llm_decision.models import EvalSnapshot
from memorii.core.llm_eval.models import EvalCaseResult
from memorii.core.llm_judge.runner import JudgeRunCaseResult, JudgeRunReport


class JudgeArtifactPolicy(BaseModel):
    persist_full_runs: bool = True
    persist_passing_cases: bool = False
    persist_failed_cases: bool = True
    persist_human_review_cases: bool = True
    persist_disagreement_cases: bool = True
    persist_golden_candidates: bool = True
    write_review_queues: bool = True
    overwrite_existing_run: bool = False

    model_config = ConfigDict(extra="forbid")


class JudgeArtifactWriteResult(BaseModel):
    run_dir: str | None
    written_files: list[str]
    review_queue_files: list[str]
    skipped_reason: str | None = None

    model_config = ConfigDict(extra="forbid")


class JudgeArtifactWriter:
    def __init__(
        self,
        *,
        storage_root: str | Path,
        policy: JudgeArtifactPolicy | None = None,
        date_provider: Callable[[], date] | None = None,
    ) -> None:
        self._storage_root = Path(storage_root)
        self._policy = policy or JudgeArtifactPolicy()
        self._date_provider = date_provider or (lambda: datetime.now(timezone.utc).date())

    def write_run_artifacts(
        self,
        *,
        judge_report: JudgeRunReport,
        eval_cases: list[EvalCaseResult],
        snapshots: list[EvalSnapshot],
    ) -> JudgeArtifactWriteResult:
        if not self._policy.persist_full_runs and not self._policy.write_review_queues:
            return JudgeArtifactWriteResult(
                run_dir=None,
                written_files=[],
                review_queue_files=[],
                skipped_reason="artifact_persistence_disabled",
            )

        written_files: list[str] = []
        review_files: list[str] = []
        run_dir: Path | None = None
        filtered_case_results = self._filter_case_results(judge_report.case_results)

        if self._policy.persist_full_runs:
            run_dir = self._run_dir(judge_report.run_id)
            if run_dir.exists() and not self._policy.overwrite_existing_run:
                raise FileExistsError(f"Run directory already exists: {run_dir}")
            run_dir.mkdir(parents=True, exist_ok=True)

            written_files.append(self._write_json(run_dir / "report.json", judge_report.model_dump(mode="json")))
            written_files.append(self._write_text(run_dir / "summary.txt", self._build_summary(judge_report, run_dir)))

            verdicts = [
                verdict
                for case in filtered_case_results
                for verdict in case.judge_verdicts
            ]
            juries = [case.jury_verdict for case in filtered_case_results]

            written_files.append(self._write_jsonl(run_dir / "verdicts.jsonl", [v.model_dump(mode="json") for v in verdicts]))
            written_files.append(self._write_jsonl(run_dir / "juries.jsonl", [j.model_dump(mode="json") for j in juries]))
            written_files.extend(self._write_filtered_case_files(run_dir, judge_report.case_results))

            inputs_dir = run_dir / "inputs"
            inputs_dir.mkdir(parents=True, exist_ok=True)
            written_files.append(
                self._write_jsonl(inputs_dir / "eval_cases.jsonl", [case.model_dump(mode="json") for case in eval_cases])
            )
            written_files.append(
                self._write_jsonl(inputs_dir / "snapshots.jsonl", [snapshot.model_dump(mode="json") for snapshot in snapshots])
            )

        if self._policy.write_review_queues:
            review_files.extend(self._write_review_queues(judge_report.case_results))

        return JudgeArtifactWriteResult(
            run_dir=str(run_dir) if run_dir is not None else None,
            written_files=written_files,
            review_queue_files=review_files,
        )

    def _write_filtered_case_files(self, run_dir: Path, case_results: list[JudgeRunCaseResult]) -> list[str]:
        outputs: list[str] = []
        failed = [c for c in case_results if not c.jury_verdict.passed]
        human_review = [c for c in case_results if c.jury_verdict.needs_human_review]
        disagreement = [c for c in case_results if c.jury_verdict.disagreement]
        golden = [c for c in case_results if c.golden_candidate_reason is not None]

        if self._policy.persist_failed_cases:
            outputs.append(self._write_jsonl(run_dir / "failed_cases.jsonl", [c.model_dump(mode="json") for c in failed]))
        if self._policy.persist_human_review_cases:
            outputs.append(
                self._write_jsonl(run_dir / "human_review_cases.jsonl", [c.model_dump(mode="json") for c in human_review])
            )
        if self._policy.persist_disagreement_cases:
            outputs.append(
                self._write_jsonl(run_dir / "disagreement_cases.jsonl", [c.model_dump(mode="json") for c in disagreement])
            )
        if self._policy.persist_golden_candidates:
            outputs.append(
                self._write_jsonl(run_dir / "golden_candidates.jsonl", [self._golden_record(c) for c in golden])
            )
        return outputs

    def _write_review_queues(self, case_results: list[JudgeRunCaseResult]) -> list[str]:
        review_dir = self._storage_root / "review"
        review_dir.mkdir(parents=True, exist_ok=True)
        outputs: list[str] = []

        if self._policy.persist_human_review_cases:
            data = [c.model_dump(mode="json") for c in case_results if c.jury_verdict.needs_human_review]
            outputs.append(self._append_jsonl(review_dir / "human_review_candidates.jsonl", data))
        if self._policy.persist_golden_candidates:
            data = [self._golden_record(c) for c in case_results if c.golden_candidate_reason is not None]
            outputs.append(self._append_jsonl(review_dir / "golden_candidates.jsonl", data))
        if self._policy.persist_disagreement_cases:
            data = [c.model_dump(mode="json") for c in case_results if c.jury_verdict.disagreement]
            outputs.append(self._append_jsonl(review_dir / "judge_disagreements.jsonl", data))
        if self._policy.persist_failed_cases:
            data = [c.model_dump(mode="json") for c in case_results if not c.jury_verdict.passed]
            outputs.append(self._append_jsonl(review_dir / "failed_cases.jsonl", data))

        return outputs

    def _filter_case_results(self, case_results: list[JudgeRunCaseResult]) -> list[JudgeRunCaseResult]:
        if self._policy.persist_passing_cases:
            return case_results
        return [
            case
            for case in case_results
            if (not case.jury_verdict.passed)
            or case.jury_verdict.needs_human_review
            or case.jury_verdict.disagreement
            or case.golden_candidate_reason is not None
        ]

    def _run_dir(self, run_id: str) -> Path:
        run_date = self._date_provider().isoformat()
        sanitized = re.sub(r"[^a-zA-Z0-9._-]", "-", run_id)
        return self._storage_root / "eval_runs" / "judge" / run_date / sanitized

    def _build_summary(self, report: JudgeRunReport, run_dir: Path) -> str:
        lines = [
            f"run_id: {report.run_id}",
            f"total_eval_cases: {report.total_eval_cases}",
            f"judged_cases: {report.judged_cases}",
            f"skipped_cases: {report.skipped_cases}",
            f"jury_passed_cases: {report.jury_passed_cases}",
            f"jury_failed_cases: {report.jury_failed_cases}",
            f"disagreement_cases: {report.disagreement_cases}",
            f"human_review_cases: {report.human_review_cases}",
            f"golden_candidate_cases: {report.golden_candidate_cases}",
            f"run_dir: {run_dir}",
        ]
        return "\n".join(lines) + "\n"

    def _golden_record(self, case_result: JudgeRunCaseResult) -> dict[str, object]:
        now = datetime.now(timezone.utc).isoformat()
        return {
            "candidate_id": f"golden-candidate:{case_result.eval_snapshot_id}:{case_result.jury_verdict.trace_id or 'none'}",
            "source_run_id": case_result.jury_verdict.jury_id.split(":")[0] if ":" in case_result.jury_verdict.jury_id else "unknown",
            "snapshot_id": case_result.eval_snapshot_id,
            "trace_id": case_result.jury_verdict.trace_id,
            "decision_point": case_result.decision_point,
            "reason": case_result.golden_candidate_reason,
            "judge_verdict_refs": [v.verdict_id for v in case_result.judge_verdicts],
            "created_at": now,
        }

    def _write_json(self, path: Path, payload: object) -> str:
        path.write_text(json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return str(path)

    def _write_text(self, path: Path, text: str) -> str:
        path.write_text(text, encoding="utf-8")
        return str(path)

    def _write_jsonl(self, path: Path, rows: list[object]) -> str:
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
        return str(path)

    def _append_jsonl(self, path: Path, rows: list[object]) -> str:
        with path.open("a", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
        return str(path)
