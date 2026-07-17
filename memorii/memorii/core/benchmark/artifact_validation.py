"""Validation and serialization for persisted memory-evolution artifacts.

The benchmark report is only one part of a run.  This module makes the JSONL
files part of the same contract so a green report cannot hide malformed or
inconsistent diagnostic artifacts.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from memorii.core.benchmark.artifact_rows import (
    AlignmentSummary,
    BenchmarkReportSummary,
    JudgeVoteRow,
    RuntimeCheckpointResultRow,
    RuntimeGraphAlignmentRow,
    SimCheckpointResultRow,
    WarningExampleRow,
)
from memorii.core.calibration.models import CalibrationEvent, CalibrationReport, DecisionCostReport

T = TypeVar("T", bound=BaseModel)


class ArtifactValidationError(ValueError):
    """Raised when one persisted benchmark artifact violates its contract."""


def write_typed_jsonl(path: Path, rows: Sequence[BaseModel | Mapping[str, object]], *, model_type: type[T]) -> None:
    """Validate every row before writing a JSONL artifact."""

    path.parent.mkdir(parents=True, exist_ok=True)
    serialized: list[str] = []
    for index, row in enumerate(rows):
        try:
            validated = row if isinstance(row, model_type) else model_type.model_validate(row)
        except (TypeError, ValidationError, ValueError) as exc:
            raise ArtifactValidationError(f"{path.name}[{index}] failed {model_type.__name__} validation: {exc}") from exc
        serialized.append(json.dumps(validated.model_dump(mode="json"), sort_keys=True))
    _atomic_write_text(path, "".join(f"{row}\n" for row in serialized))


def write_jsonl_atomic(path: Path, rows: Sequence[BaseModel | Mapping[str, object]]) -> None:
    """Write a JSONL artifact atomically after JSON serialization."""

    serialized: list[str] = []
    for row in rows:
        value = row.model_dump(mode="json") if isinstance(row, BaseModel) else dict(row)
        serialized.append(json.dumps(value, sort_keys=True))
    _atomic_write_text(path, "".join(f"{row}\n" for row in serialized))


def write_json_atomic(path: Path, value: object, *, indent: int = 2) -> None:
    """Write a JSON artifact atomically."""

    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    _atomic_write_text(path, json.dumps(value, indent=indent, sort_keys=True))


def write_text_atomic(path: Path, contents: str) -> None:
    """Write a text artifact atomically."""

    _atomic_write_text(path, contents)


def _atomic_write_text(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    rows: list[dict[str, object]] = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ArtifactValidationError(f"{path.name}[{index}] is not valid JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise ArtifactValidationError(f"{path.name}[{index}] must be a JSON object")
        rows.append(value)
    return rows


def _read_json_array(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ArtifactValidationError(f"{path.name} is not valid JSON: {exc}") from exc
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ArtifactValidationError(f"{path.name} must contain a JSON array of objects")
    return value


def _validate_jsonl(path: Path, model_type: type[T], *, required: bool = False) -> list[T]:
    if required and not path.exists():
        raise ArtifactValidationError(f"required artifact is missing: {path.name}")
    validated: list[T] = []
    for index, row in enumerate(_read_jsonl(path)):
        try:
            validated.append(model_type.model_validate(row))
        except ValidationError as exc:
            raise ArtifactValidationError(f"{path.name}[{index}] failed {model_type.__name__} validation: {exc}") from exc
    return validated


def _validate_json_array(path: Path, model_type: type[T], *, required: bool = False) -> list[T]:
    if required and not path.exists():
        raise ArtifactValidationError(f"required artifact is missing: {path.name}")
    validated: list[T] = []
    for index, row in enumerate(_read_json_array(path)):
        try:
            validated.append(model_type.model_validate(row))
        except ValidationError as exc:
            raise ArtifactValidationError(f"{path.name}[{index}] failed {model_type.__name__} validation: {exc}") from exc
    return validated


def _validate_json_object(path: Path, model_type: type[T], *, required: bool = False) -> T | None:
    if required and not path.exists():
        raise ArtifactValidationError(f"required artifact is missing: {path.name}")
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ArtifactValidationError(f"{path.name} must contain a JSON object")
        return model_type.model_validate(value)
    except ArtifactValidationError:
        raise
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise ArtifactValidationError(f"{path.name} failed {model_type.__name__} validation: {exc}") from exc


def _checkpoint_keys(rows: Sequence[BaseModel]) -> list[tuple[str, str]]:
    return [
        (str(values.get("scenario_id", "")), str(values.get("checkpoint_id", "")))
        for values in (row.model_dump(mode="python") for row in rows)
    ]


def validate_memory_evolution_run(run_dir: Path, *, suite: str) -> BenchmarkReportSummary:
    """Validate a complete simulator or runtime run directory."""

    # Import lazily because runtime models are re-exported by the runtime
    # package, whose artifact writer depends on this module.
    from memorii.core.benchmark.memory_evolution_runtime.models import RuntimeGraphItemRow, RuntimeGraphSnapshotRow

    report_path = run_dir / "report.json"
    if not report_path.exists():
        raise ArtifactValidationError(f"required artifact is missing: {report_path}")
    try:
        report = BenchmarkReportSummary.model_validate(json.loads(report_path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise ArtifactValidationError(f"{report_path} failed report validation: {exc}") from exc
    if report.suite != suite:
        raise ArtifactValidationError(f"report suite {report.suite!r} does not match requested suite {suite!r}")

    if suite == "memory_evolution_sim_v1":
        checkpoint_rows: list[BaseModel] = _validate_jsonl(
            run_dir / "sim_checkpoint_results.jsonl", SimCheckpointResultRow, required=True
        )
        _validate_jsonl(run_dir / "judge_votes.jsonl", JudgeVoteRow)
        _validate_jsonl(run_dir / "calibration_events.jsonl", CalibrationEvent)
        _validate_jsonl(run_dir / "sim_warning_examples.jsonl", WarningExampleRow)
        failure_rows: list[BaseModel] = _validate_jsonl(run_dir / "failures.jsonl", SimCheckpointResultRow)
        _validate_json_object(run_dir / "calibration_report.json", CalibrationReport, required=True)
        _validate_json_object(run_dir / "decision_quality_report.json", DecisionCostReport, required=True)
    elif suite == "memory_evolution_runtime_v1":
        checkpoint_rows = _validate_jsonl(
            run_dir / "runtime_checkpoint_results.jsonl", RuntimeCheckpointResultRow, required=True
        )
        graph_items = _validate_jsonl(run_dir / "runtime_graph_items.jsonl", RuntimeGraphItemRow, required=True)
        snapshot_rows = _validate_json_array(
            run_dir / "runtime_graph_snapshot.json", RuntimeGraphSnapshotRow, required=True
        )
        alignment_rows = _validate_jsonl(run_dir / "runtime_graph_alignments.jsonl", RuntimeGraphAlignmentRow)
        _validate_json_object(run_dir / "runtime_graph_alignments_summary.json", AlignmentSummary, required=True)
        failure_rows = _validate_jsonl(run_dir / "runtime_failures.jsonl", RuntimeCheckpointResultRow)
    else:
        raise ArtifactValidationError(f"unsupported memory-evolution suite: {suite}")

    checkpoint_keys = _checkpoint_keys(checkpoint_rows)
    if len(checkpoint_keys) != len(set(checkpoint_keys)):
        raise ArtifactValidationError("checkpoint artifact contains duplicate scenario/checkpoint identities")
    if len(checkpoint_rows) != report.checkpoint_count:
        raise ArtifactValidationError(
            f"checkpoint artifact count {len(checkpoint_rows)} does not match report {report.checkpoint_count}"
        )

    actual_verdict_counts = Counter(str(row.model_dump(mode="python").get("verdict")) for row in checkpoint_rows)
    actual_review_required_count = sum(
        1 for row in checkpoint_rows if row.model_dump(mode="python").get("review_required") is True
    )
    actual_failure_bucket_counts = Counter(
        str(bucket)
        for row in checkpoint_rows
        for bucket in (row.model_dump(mode="python").get("failure_buckets") or [])
    )
    report_checkpoint_keys = _checkpoint_keys(report.checkpoint_results)
    if report_checkpoint_keys and report_checkpoint_keys != checkpoint_keys:
        raise ArtifactValidationError("report checkpoint_results identities do not match checkpoint artifact")
    if report.checkpoint_results:
        report_rows_by_key = {
            key: row
            for key, row in zip(report_checkpoint_keys, report.checkpoint_results, strict=True)
        }
        for artifact_row in checkpoint_rows:
            key = (artifact_row.scenario_id, artifact_row.checkpoint_id)
            report_row = report_rows_by_key[key]
            if (
                report_row.verdict != artifact_row.verdict
                or report_row.score != artifact_row.score
                or report_row.review_required != artifact_row.review_required
                or report_row.failure_buckets != artifact_row.failure_buckets
            ):
                raise ArtifactValidationError(
                    f"report checkpoint row {key} disagrees with checkpoint artifact verdict fields"
                )
    if isinstance(report.runtime_graph_alignments_summary, AlignmentSummary):
        summary = report.runtime_graph_alignments_summary
        if dict(sorted(summary.checkpoint_scored_verdict_counts.items())) != dict(sorted(actual_verdict_counts.items())):
            raise ArtifactValidationError(
                "runtime checkpoint verdict counts do not match runtime_graph_alignments_summary"
            )
        if summary.checkpoint_scored_review_required_count != actual_review_required_count:
            raise ArtifactValidationError(
                "runtime checkpoint review count does not match runtime_graph_alignments_summary"
            )
        if dict(sorted(summary.checkpoint_scored_failure_bucket_counts.items())) != dict(sorted(actual_failure_bucket_counts.items())):
            raise ArtifactValidationError(
                "runtime checkpoint failure buckets do not match runtime_graph_alignments_summary"
            )

    if suite == "memory_evolution_runtime_v1":
        expected_scenario_ids = {row.scenario_id for row in checkpoint_rows}
        snapshot_scenario_ids = {row.scenario_id for row in snapshot_rows}
        if snapshot_scenario_ids != expected_scenario_ids:
            raise ArtifactValidationError(
                "runtime_graph_snapshot.json scenario identities do not match checkpoint results"
            )
        terminal_counts: dict[str, int] = {}
        for snapshot in snapshot_rows:
            if snapshot.is_terminal:
                terminal_counts[snapshot.scenario_id] = terminal_counts.get(snapshot.scenario_id, 0) + 1
        terminal_anomalies = {
            scenario_id: terminal_counts.get(scenario_id, 0)
            for scenario_id in expected_scenario_ids
            if terminal_counts.get(scenario_id, 0) != 1
        }
        if terminal_anomalies:
            raise ArtifactValidationError(
                f"runtime_graph_snapshot.json must contain exactly one terminal snapshot per scenario: {terminal_anomalies}"
            )
        graph_scenario_ids = {row.scenario_id for row in graph_items}
        if not graph_scenario_ids.issubset(expected_scenario_ids):
            raise ArtifactValidationError(
                "runtime_graph_items.jsonl contains a scenario absent from checkpoint results"
            )
        runtime_item_ids = {row.runtime_item_id for row in graph_items if row.runtime_item_id}
        for index, alignment in enumerate(alignment_rows):
            if alignment.runtime_id and alignment.runtime_id not in runtime_item_ids:
                raise ArtifactValidationError(
                    f"runtime_graph_alignments.jsonl[{index}] references unknown runtime item {alignment.runtime_id!r}"
                )

    failure_path = run_dir / ("failures.jsonl" if suite == "memory_evolution_sim_v1" else "runtime_failures.jsonl")
    known_keys = set(checkpoint_keys)
    failure_keys: set[tuple[str, str]] = set()
    for index, failure in enumerate(failure_rows):
        values = failure.model_dump(mode="python")
        key = (str(values.get("scenario_id", "")), str(values.get("checkpoint_id", "")))
        if key not in known_keys:
            raise ArtifactValidationError(f"{failure_path.name}[{index}] references unknown checkpoint {key}")
        if values.get("success") is not False:
            raise ArtifactValidationError(f"{failure_path.name}[{index}] must contain only unsuccessful checkpoints")
        if key in failure_keys:
            raise ArtifactValidationError(f"{failure_path.name} contains duplicate checkpoint {key}")
        failure_keys.add(key)
    expected_failure_keys = {
        (row.scenario_id, row.checkpoint_id)
        for row in checkpoint_rows
        if row.success is False
    }
    if failure_keys != expected_failure_keys:
        raise ArtifactValidationError(
            f"{failure_path.name} identities do not match non-pass checkpoint verdicts"
        )
    return report
