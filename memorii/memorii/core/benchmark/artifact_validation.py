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
from typing import Literal, TypeAlias, TypeVar, cast

from pydantic import BaseModel, TypeAdapter, ValidationError
from pydantic_core import to_jsonable_python

from memorii.core.benchmark.artifact_rows import (
    AlignmentSummary,
    ArtifactManifest,
    ArtifactManifestEntry,
    BenchmarkReportSummary,
    CuratedMemoryEvolutionLLMTraceRow,
    JudgeVoteRow,
    RuntimeCheckpointResultRow,
    RuntimeGraphAlignmentRow,
    SimCheckpointResultRow,
    SimLLMTraceRow,
    WarningExampleRow,
    execution_source_from_counts,
)
from memorii.core.benchmark.calibration.models import CalibrationEvent, CalibrationReport, DecisionCostReport
from memorii.core.benchmark.reproducibility import file_sha256

T = TypeVar("T", bound=BaseModel)
U = TypeVar("U")
CheckpointArtifactRow: TypeAlias = SimCheckpointResultRow | RuntimeCheckpointResultRow
ArtifactMediaType: TypeAlias = Literal[
    "application/json",
    "application/jsonl",
    "text/markdown",
]


class ArtifactValidationError(ValueError):
    """Raised when one persisted benchmark artifact violates its contract."""


_PROVENANCE_EXCLUDED_ARTIFACTS = {"artifact_manifest.json", "report.json"}


def finalize_memory_evolution_run(run_dir: Path) -> BenchmarkReportSummary:
    """Bind a completed run directory into its manifest and final report."""

    report_path = run_dir / "report.json"
    try:
        report = BenchmarkReportSummary.model_validate(json.loads(report_path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise ArtifactValidationError(f"cannot finalize invalid report: {exc}") from exc
    manifest = ArtifactManifest(
        run_id=report.run_id,
        source_revision=report.source_revision,
        source_tree_digest=report.source_tree_digest,
        source_state=report.source_state,
        entries=[_manifest_entry(path, run_dir=run_dir) for path in _manifest_paths(run_dir)],
    )
    write_json_atomic(run_dir / "artifact_manifest.json", manifest)
    bound_report = report.model_copy(update={"artifact_manifest_digest": manifest.digest()}).with_content_digest()
    write_json_atomic(report_path, bound_report)
    return bound_report


def _manifest_paths(run_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in run_dir.rglob("*")
        if path.is_file()
        and path.relative_to(run_dir).as_posix() not in _PROVENANCE_EXCLUDED_ARTIFACTS
        and not path.name.startswith(".")
    )


def _manifest_entry(path: Path, *, run_dir: Path) -> ArtifactManifestEntry:
    suffix = path.suffix.casefold()
    media_types: dict[str, ArtifactMediaType] = {
        ".json": "application/json",
        ".jsonl": "application/jsonl",
        ".md": "text/markdown",
    }
    media_type = media_types.get(suffix)
    if media_type is None:
        raise ArtifactValidationError(f"unsupported benchmark artifact type: {path.name}")
    return ArtifactManifestEntry(
        relative_path=path.relative_to(run_dir).as_posix(),
        media_type=media_type,
        size_bytes=path.stat().st_size,
        sha256=file_sha256(path),
    )


def _validate_artifact_manifest(run_dir: Path, report: BenchmarkReportSummary) -> None:
    manifest = _validate_json_object(
        run_dir / "artifact_manifest.json",
        ArtifactManifest,
        required=True,
    )
    assert manifest is not None
    if manifest.digest() != report.artifact_manifest_digest:
        raise ArtifactValidationError("artifact manifest digest does not match report.json")
    if manifest.run_id != report.run_id:
        raise ArtifactValidationError("artifact manifest run_id does not match report.json")
    if manifest.source_revision != report.source_revision:
        raise ArtifactValidationError("artifact manifest source revision does not match report.json")
    if manifest.source_tree_digest != report.source_tree_digest:
        raise ArtifactValidationError("artifact manifest source tree digest does not match report.json")
    if manifest.source_state != report.source_state:
        raise ArtifactValidationError("artifact manifest source state does not match report.json")
    actual_paths = [path.relative_to(run_dir).as_posix() for path in _manifest_paths(run_dir)]
    expected_paths = [entry.relative_path for entry in manifest.entries]
    if actual_paths != expected_paths:
        raise ArtifactValidationError("artifact manifest does not exactly cover the run directory")
    for expected in manifest.entries:
        actual = _manifest_entry(run_dir / expected.relative_path, run_dir=run_dir)
        if actual != expected:
            raise ArtifactValidationError(
                f"artifact manifest entry does not match persisted bytes: {expected.relative_path}"
            )


def write_typed_jsonl(path: Path, rows: Sequence[T], *, model_type: type[T]) -> None:
    """Serialize rows that were already validated at their construction boundary."""

    path.parent.mkdir(parents=True, exist_ok=True)
    serialized: list[str] = []
    for index, row in enumerate(rows):
        if not isinstance(row, model_type):
            raise ArtifactValidationError(f"{path.name}[{index}] must be a validated {model_type.__name__}")
        serialized.append(json.dumps(row.model_dump(mode="json"), sort_keys=True))
    _atomic_write_text(path, "".join(f"{row}\n" for row in serialized))


def write_jsonl_atomic(path: Path, rows: Sequence[BaseModel | Mapping[str, object]]) -> None:
    """Write a JSONL artifact atomically after JSON serialization."""

    serialized: list[str] = []
    for row in rows:
        value = row.model_dump(mode="json") if isinstance(row, BaseModel) else dict(row)
        serialized.append(json.dumps(value, sort_keys=True))
    _atomic_write_text(path, "".join(f"{row}\n" for row in serialized))


def write_json_atomic(path: Path, value: object, *, indent: int = 2) -> None:
    """Write a recursively JSON-safe artifact at the persistence boundary."""

    _atomic_write_text(
        path,
        json.dumps(to_jsonable_python(value), indent=indent, sort_keys=True),
    )


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


def _validate_jsonl(
    path: Path,
    model_type: type[T] | TypeAdapter[T],
    *,
    required: bool = False,
) -> list[T]:
    if required and not path.exists():
        raise ArtifactValidationError(f"required artifact is missing: {path.name}")
    validated: list[T] = []
    for index, row in enumerate(_read_jsonl(path)):
        try:
            validated.append(
                model_type.validate_python(row)
                if isinstance(model_type, TypeAdapter)
                else model_type.model_validate(row)
            )
        except ValidationError as exc:
            model_name = "typed union" if isinstance(model_type, TypeAdapter) else model_type.__name__
            raise ArtifactValidationError(f"{path.name}[{index}] failed {model_name} validation: {exc}") from exc
    return validated


def _validate_json_array(path: Path, model_type: type[T], *, required: bool = False) -> list[T]:
    if required and not path.exists():
        raise ArtifactValidationError(f"required artifact is missing: {path.name}")
    validated: list[T] = []
    for index, row in enumerate(_read_json_array(path)):
        try:
            validated.append(model_type.model_validate(row))
        except ValidationError as exc:
            raise ArtifactValidationError(
                f"{path.name}[{index}] failed {model_type.__name__} validation: {exc}"
            ) from exc
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


def _required_value(row: Mapping[str, object], field: str, expected_type: type[U], *, location: str) -> U:
    value = row.get(field)
    if expected_type is int and type(value) is not int:
        raise ArtifactValidationError(f"{location}.{field} must be int")
    if not isinstance(value, expected_type):
        raise ArtifactValidationError(f"{location}.{field} must be {expected_type.__name__}")
    return cast(U, value)


def _required_bool(row: Mapping[str, object], field: str, *, location: str) -> bool:
    value = row.get(field)
    if type(value) is not bool:
        raise ArtifactValidationError(f"{location}.{field} must be bool")
    return value


def _required_count(report: Mapping[str, object], field: str) -> int:
    value = report.get(field)
    if type(value) is not int or value < 0:
        raise ArtifactValidationError(f"report.json.{field} must be a non-negative integer")
    return value


def _required_count_map(report: Mapping[str, object], field: str) -> dict[str, int]:
    value = report.get(field)
    if not isinstance(value, dict) or any(
        not isinstance(key, str) or type(count) is not int or count < 0
        for key, count in value.items()
    ):
        raise ArtifactValidationError(f"report.json.{field} must be a string-to-count object")
    return dict(value)


def _assert_count(report: Mapping[str, object], field: str, actual: int) -> None:
    expected = _required_count(report, field)
    if expected != actual:
        raise ArtifactValidationError(f"report.json.{field}={expected} does not match artifact rows ({actual})")


def _assert_count_map(report: Mapping[str, object], field: str, actual: Counter[str]) -> None:
    expected = _required_count_map(report, field)
    normalized = dict(sorted(actual.items()))
    if expected != normalized:
        raise ArtifactValidationError(f"report.json.{field} does not match artifact rows")


def _load_curated_report(run_dir: Path) -> dict[str, object]:
    report_path = run_dir / "report.json"
    duplicate_path = run_dir / "memory_evolution_report.json"
    if not report_path.exists():
        raise ArtifactValidationError(f"required artifact is missing: {report_path}")
    if not duplicate_path.exists():
        raise ArtifactValidationError(f"required artifact is missing: {duplicate_path}")
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        duplicate = json.loads(duplicate_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactValidationError(f"curated report is not valid JSON: {exc}") from exc
    if not isinstance(report, dict) or not isinstance(duplicate, dict):
        raise ArtifactValidationError("curated reports must contain JSON objects")
    if report != duplicate:
        raise ArtifactValidationError("memory_evolution_report.json disagrees with report.json")
    if report.get("suite") != "memory_evolution_v1":
        raise ArtifactValidationError("report.json does not describe memory_evolution_v1")
    if report.get("artifact_version") != "memory_evolution_v1_artifacts:4":
        raise ArtifactValidationError("unsupported curated memory-evolution artifact version")
    return report


def validate_curated_memory_evolution_run(run_dir: Path) -> dict[str, object]:
    """Validate curated memory-evolution artifacts by recomputing report evidence."""

    report = _load_curated_report(run_dir)
    required_jsonl = (
        "memory_evolution_traces.jsonl",
        "memory_evolution_checkpoint_traces.jsonl",
        "llm_traces.jsonl",
        "failures.jsonl",
    )
    for name in required_jsonl:
        if not (run_dir / name).exists():
            raise ArtifactValidationError(f"required artifact is missing: {name}")
    scenario_rows = _read_jsonl(run_dir / "memory_evolution_traces.jsonl")
    checkpoint_rows = _read_jsonl(run_dir / "memory_evolution_checkpoint_traces.jsonl")
    failure_rows = _read_jsonl(run_dir / "failures.jsonl")
    trace_rows = _validate_jsonl(
        run_dir / "llm_traces.jsonl",
        CuratedMemoryEvolutionLLMTraceRow,
        required=True,
    )

    report_scenarios = report.get("scenario_results")
    report_checkpoints = report.get("checkpoint_results")
    if report_scenarios != scenario_rows:
        raise ArtifactValidationError("report scenario_results disagree with memory_evolution_traces.jsonl")
    if report_checkpoints != checkpoint_rows:
        raise ArtifactValidationError(
            "report checkpoint_results disagree with memory_evolution_checkpoint_traces.jsonl"
        )

    scenario_ids: list[str] = []
    scenario_by_id: dict[str, dict[str, object]] = {}
    for index, row in enumerate(scenario_rows):
        location = f"memory_evolution_traces.jsonl[{index}]"
        scenario_id = _required_value(row, "scenario_id", str, location=location)
        scenario_ids.append(scenario_id)
        scenario_by_id[scenario_id] = row
        _required_bool(row, "success", location=location)
        _required_bool(row, "functional_success", location=location)
    if len(scenario_ids) != len(set(scenario_ids)):
        raise ArtifactValidationError("memory_evolution_traces.jsonl contains duplicate scenario IDs")

    checkpoint_keys: list[tuple[str, str]] = []
    checkpoint_by_key: dict[tuple[str, str], dict[str, object]] = {}
    for index, row in enumerate(checkpoint_rows):
        location = f"memory_evolution_checkpoint_traces.jsonl[{index}]"
        scenario_id = _required_value(row, "scenario_id", str, location=location)
        checkpoint_id = _required_value(row, "checkpoint_id", str, location=location)
        if scenario_id not in scenario_by_id:
            raise ArtifactValidationError(f"{location} references unknown scenario {scenario_id!r}")
        key = (scenario_id, checkpoint_id)
        checkpoint_keys.append(key)
        checkpoint_by_key[key] = row
        success = _required_bool(row, "success", location=location)
        model_success = _required_bool(row, "model_success", location=location)
        functional_success = _required_bool(row, "functional_success", location=location)
        fallback_used = _required_bool(row, "fallback_used", location=location)
        fallback_assisted = _required_bool(row, "fallback_assisted_success", location=location)
        if success != model_success:
            raise ArtifactValidationError(f"{location}.success must equal model_success")
        final_accepted = row.get("final_output_accepted")
        if final_accepted is not None and type(final_accepted) is not bool:
            raise ArtifactValidationError(f"{location}.final_output_accepted must be bool or null")
        expected_assisted = bool(functional_success and fallback_used and final_accepted is False)
        if fallback_assisted != expected_assisted:
            raise ArtifactValidationError(
                f"{location}.fallback_assisted_success is inconsistent with checkpoint provenance"
            )
    if len(checkpoint_keys) != len(set(checkpoint_keys)):
        raise ArtifactValidationError(
            "memory_evolution_checkpoint_traces.jsonl contains duplicate scenario/checkpoint identities"
        )

    for scenario_id, scenario in scenario_by_id.items():
        rows = [row for key, row in checkpoint_by_key.items() if key[0] == scenario_id]
        location = f"scenario {scenario_id!r}"
        checkpoint_count = _required_value(scenario, "checkpoint_count", int, location=location)
        if checkpoint_count != len(rows):
            raise ArtifactValidationError(f"{location} checkpoint_count does not match checkpoint rows")
        successes = sum(_required_bool(row, "success", location=location) for row in rows)
        functional_successes = sum(
            _required_bool(row, "functional_success", location=location) for row in rows
        )
        if scenario.get("checkpoints_passed") != successes:
            raise ArtifactValidationError(f"{location} checkpoints_passed does not match checkpoint rows")
        if scenario.get("checkpoints_failed") != len(rows) - successes:
            raise ArtifactValidationError(f"{location} checkpoints_failed does not match checkpoint rows")
        if scenario.get("success") != (successes == len(rows)):
            raise ArtifactValidationError(f"{location} success does not match checkpoint rows")
        if scenario.get("functional_success") != (functional_successes == len(rows)):
            raise ArtifactValidationError(f"{location} functional_success does not match checkpoint rows")

    trace_by_key = {(row.scenario_id, row.checkpoint_id): row for row in trace_rows}
    if len(trace_by_key) != len(trace_rows):
        raise ArtifactValidationError("llm_traces.jsonl contains duplicate scenario/checkpoint identities")
    llm_checkpoint_keys = {
        key
        for key, row in checkpoint_by_key.items()
        if _required_bool(row, "llm_call_made", location=f"checkpoint {key!r}")
    }
    if set(trace_by_key) != llm_checkpoint_keys:
        raise ArtifactValidationError("llm_traces.jsonl identities do not match checkpoints with LLM calls")
    for key, trace_row in trace_by_key.items():
        checkpoint = checkpoint_by_key[key]
        location = f"checkpoint {key!r}"
        if checkpoint.get("final_output_accepted") != trace_row.final_output_accepted:
            raise ArtifactValidationError(f"{location} final-output acceptance disagrees with LLM trace")
        if checkpoint.get("final_output_source") != trace_row.final_output_source:
            raise ArtifactValidationError(f"{location} final-output source disagrees with LLM trace")
        fallback_used = trace_row.fallback_outcome.value != "not_used"
        if checkpoint.get("fallback_used") != fallback_used:
            raise ArtifactValidationError(f"{location} fallback provenance disagrees with LLM trace")
        if checkpoint.get("output") != trace_row.output.model_dump(mode="json"):
            raise ArtifactValidationError(
                f"{location} judged output disagrees with persisted LLM output"
            )

    failure_by_key = {
        (
            _required_value(row, "scenario_id", str, location=f"failures.jsonl[{index}]"),
            _required_value(row, "checkpoint_id", str, location=f"failures.jsonl[{index}]"),
        ): row
        for index, row in enumerate(failure_rows)
    }
    expected_failure_keys = {
        key
        for key, row in checkpoint_by_key.items()
        if not _required_bool(row, "success", location=f"checkpoint {key!r}")
    }
    if len(failure_by_key) != len(failure_rows) or set(failure_by_key) != expected_failure_keys:
        raise ArtifactValidationError("failures.jsonl identities do not match unsuccessful checkpoints")
    if any(failure_by_key[key] != checkpoint_by_key[key] for key in expected_failure_keys):
        raise ArtifactValidationError("failures.jsonl rows disagree with checkpoint artifacts")

    _assert_count(report, "scenarios", len(scenario_rows))
    _assert_count(report, "checkpoints", len(checkpoint_rows))
    _assert_count(report, "passed", sum(row["success"] is True for row in scenario_rows))
    _assert_count(report, "failed", sum(row["success"] is False for row in scenario_rows))
    _assert_count(report, "functional_passed", sum(row["functional_success"] is True for row in scenario_rows))
    _assert_count(report, "functional_failed", sum(row["functional_success"] is False for row in scenario_rows))
    _assert_count(
        report,
        "functional_checkpoints_passed",
        sum(row["functional_success"] is True for row in checkpoint_rows),
    )
    _assert_count(
        report,
        "functional_checkpoints_failed",
        sum(row["functional_success"] is False for row in checkpoint_rows),
    )
    provider_attempts = [
        attempt
        for row in trace_rows
        for attempt in row.provider_attempts
    ]
    _assert_count(report, "llm_calls", len(provider_attempts))
    _assert_count(
        report,
        "final_outputs_accepted",
        sum(row.final_output_accepted for row in trace_rows),
    )
    _assert_count(
        report,
        "final_outputs_rejected",
        sum(not row.final_output_accepted for row in trace_rows),
    )
    _assert_count(
        report,
        "fallback_assisted_passes",
        sum(row["fallback_assisted_success"] is True for row in checkpoint_rows),
    )
    _assert_count_map(
        report,
        "provider_attempt_counts",
        Counter(attempt.provider_attempt_status.value for attempt in provider_attempts),
    )
    _assert_count_map(
        report,
        "semantic_validation_counts",
        Counter(attempt.semantic_validation_status for attempt in provider_attempts),
    )
    _assert_count_map(
        report,
        "fallback_outcome_counts",
        Counter(row.fallback_outcome.value for row in trace_rows),
    )
    _assert_count_map(
        report,
        "final_output_source_counts",
        Counter(row.final_output_source for row in trace_rows),
    )
    local_certification_passed = (
        None
        if not trace_rows
        else bool(
            all(row["success"] is True for row in checkpoint_rows)
            and all(row.final_output_accepted for row in trace_rows)
            and not any(row["fallback_assisted_success"] is True for row in checkpoint_rows)
        )
    )
    if report.get("local_certification_passed") is not local_certification_passed:
        raise ArtifactValidationError("report.json.local_certification_passed does not match artifact rows")
    return report


def validate_memory_evolution_run(run_dir: Path, *, suite: str) -> BenchmarkReportSummary:
    """Validate a complete simulator or runtime run directory."""

    # Import lazily because runtime models are re-exported by the runtime
    # package, whose artifact writer depends on this module.
    from memorii.core.benchmark.memory_evolution_runtime.ingestion_oracle import (
        IngestionPrefixAuditRow,
    )
    from memorii.core.benchmark.memory_evolution_runtime.models import (
        RUNTIME_GRAPH_ITEM_ADAPTER,
        RuntimeGraphSnapshotRow,
        RuntimeIngestionTraceRow,
    )

    report_path = run_dir / "report.json"
    if not report_path.exists():
        raise ArtifactValidationError(f"required artifact is missing: {report_path}")
    try:
        report = BenchmarkReportSummary.model_validate(json.loads(report_path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise ArtifactValidationError(f"{report_path} failed report validation: {exc}") from exc
    if report.suite != suite:
        raise ArtifactValidationError(f"report suite {report.suite!r} does not match requested suite {suite!r}")
    if not report.has_valid_content_digest():
        raise ArtifactValidationError("report content digest does not match report.json")
    _validate_artifact_manifest(run_dir, report)

    if suite == "memory_evolution_sim_v1":
        sim_checkpoint_rows = _validate_jsonl(
            run_dir / "sim_checkpoint_results.jsonl", SimCheckpointResultRow, required=True
        )
        checkpoint_rows: Sequence[CheckpointArtifactRow] = sim_checkpoint_rows
        _validate_jsonl(run_dir / "judge_votes.jsonl", JudgeVoteRow)
        _validate_jsonl(run_dir / "calibration_events.jsonl", CalibrationEvent)
        _validate_jsonl(run_dir / "sim_warning_examples.jsonl", WarningExampleRow)
        failure_rows: Sequence[CheckpointArtifactRow] = _validate_jsonl(
            run_dir / "failures.jsonl", SimCheckpointResultRow
        )
        _validate_json_object(run_dir / "calibration_report.json", CalibrationReport, required=True)
        _validate_json_object(run_dir / "decision_quality_report.json", DecisionCostReport, required=True)
        sim_trace_rows = _validate_jsonl(
            run_dir / "llm_traces.jsonl",
            SimLLMTraceRow,
            required=True,
        )
    elif suite == "memory_evolution_runtime_v1":
        runtime_checkpoint_rows = _validate_jsonl(
            run_dir / "runtime_checkpoint_results.jsonl", RuntimeCheckpointResultRow, required=True
        )
        checkpoint_rows = runtime_checkpoint_rows
        graph_items = _validate_jsonl(
            run_dir / "runtime_graph_items.jsonl",
            RUNTIME_GRAPH_ITEM_ADAPTER,
            required=True,
        )
        snapshot_rows = _validate_json_array(
            run_dir / "runtime_graph_snapshot.json", RuntimeGraphSnapshotRow, required=True
        )
        alignment_rows = _validate_jsonl(run_dir / "runtime_graph_alignments.jsonl", RuntimeGraphAlignmentRow)
        prefix_audit_rows = _validate_jsonl(
            run_dir / "runtime_ingestion_prefix_audits.jsonl",
            IngestionPrefixAuditRow,
            required=True,
        )
        ingestion_trace_rows = _validate_jsonl(
            run_dir / "runtime_ingestion_traces.jsonl",
            RuntimeIngestionTraceRow,
            required=True,
        )
        standalone_alignment_summary = _validate_json_object(
            run_dir / "runtime_graph_alignments_summary.json",
            AlignmentSummary,
            required=True,
        )
        failure_rows = _validate_jsonl(run_dir / "runtime_failures.jsonl", RuntimeCheckpointResultRow)
        unknown_prefix_scenarios = sorted(
            {row.scenario_id for row in prefix_audit_rows}
            - {row.scenario_id for row in runtime_checkpoint_rows}
        )
        if unknown_prefix_scenarios:
            raise ArtifactValidationError(
                "runtime ingestion-prefix audits reference unknown scenarios: "
                f"{unknown_prefix_scenarios}"
            )
        prefix_indexes: dict[str, list[int]] = {}
        for row in prefix_audit_rows:
            prefix_indexes.setdefault(row.scenario_id, []).append(row.observation_index)
        noncontiguous_prefixes = {
            scenario_id: indexes
            for scenario_id, indexes in prefix_indexes.items()
            if sorted(indexes) != list(range(len(indexes)))
        }
        if noncontiguous_prefixes:
            raise ArtifactValidationError(
                "runtime ingestion-prefix audits must have one contiguous zero-based "
                f"observation sequence per scenario: {noncontiguous_prefixes}"
            )
        for index, row in enumerate(ingestion_trace_rows):
            traced_source_ids = [observation.source_id for observation in row.input_observations]
            if traced_source_ids != row.input_source_ids:
                raise ArtifactValidationError(
                    "runtime_ingestion_traces.jsonl"
                    f"[{index}] source metadata does not match input_source_ids"
                )
            expected_counts = (
                len(row.proposed_entities),
                len(row.proposed_claims),
                len(row.proposed_actions),
            )
            recorded_counts = (
                row.entity_count,
                row.claim_count,
                row.action_count,
            )
            if recorded_counts != expected_counts:
                raise ArtifactValidationError(
                    "runtime_ingestion_traces.jsonl"
                    f"[{index}] proposal counts do not match proposal rows"
                )
            expected_ids = (
                [entity.entity_id for entity in row.proposed_entities],
                [claim.claim_id for claim in row.proposed_claims],
                [action.action_id for action in row.proposed_actions],
            )
            recorded_ids = (
                row.entity_ids,
                row.claim_ids,
                row.action_ids,
            )
            if recorded_ids != expected_ids:
                raise ArtifactValidationError(
                    "runtime_ingestion_traces.jsonl"
                    f"[{index}] proposal IDs do not match proposal rows"
                )
    else:
        raise ArtifactValidationError(f"unsupported memory-evolution suite: {suite}")

    checkpoint_keys = _checkpoint_keys(checkpoint_rows)
    if len(checkpoint_keys) != len(set(checkpoint_keys)):
        raise ArtifactValidationError("checkpoint artifact contains duplicate scenario/checkpoint identities")
    if len(checkpoint_rows) != report.checkpoint_count:
        raise ArtifactValidationError(
            f"checkpoint artifact count {len(checkpoint_rows)} does not match report {report.checkpoint_count}"
        )
    if suite == "memory_evolution_sim_v1":
        trace_by_key = {
            (row.scenario_id, row.checkpoint_id): row
            for row in sim_trace_rows
        }
        if len(trace_by_key) != len(sim_trace_rows):
            raise ArtifactValidationError(
                "llm_traces.jsonl contains duplicate simulator checkpoint identities"
            )
        llm_checkpoint_keys = {
            (row.scenario_id, row.checkpoint_id)
            for row in checkpoint_rows
            if row.llm_call_made
        }
        if set(trace_by_key) != llm_checkpoint_keys:
            raise ArtifactValidationError(
                "llm_traces.jsonl identities do not match simulator checkpoints with LLM calls"
            )
        for row in checkpoint_rows:
            key = (row.scenario_id, row.checkpoint_id)
            trace_row = trace_by_key.get(key)
            if trace_row is None:
                continue
            if trace_row.output.model_dump(mode="json") != row.output.model_dump(
                mode="json"
            ):
                raise ArtifactValidationError(
                    f"simulator checkpoint {key!r} judged output disagrees with persisted LLM output"
                )
            if trace_row.final_output_source != row.final_output_source:
                raise ArtifactValidationError(
                    f"simulator checkpoint {key!r} final output source disagrees with LLM trace"
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
    actual_source_counts = Counter(str(row.final_output_source) for row in checkpoint_rows)
    if dict(sorted(actual_source_counts.items())) != dict(sorted(report.final_output_source_counts.items())):
        raise ArtifactValidationError("checkpoint output sources do not match report final_output_source_counts")
    if report.execution_source != execution_source_from_counts(actual_source_counts):
        raise ArtifactValidationError("report execution_source is not derived from checkpoint rows")
    if report.dry_run and actual_source_counts.get("live_llm", 0):
        raise ArtifactValidationError("dry-run checkpoint artifact contains live LLM provenance")
    if not report.dry_run and actual_source_counts.get("fake_oracle", 0):
        raise ArtifactValidationError("live checkpoint artifact contains fake provenance")
    report_checkpoint_keys = _checkpoint_keys(report.checkpoint_results)
    if report_checkpoint_keys and report_checkpoint_keys != checkpoint_keys:
        raise ArtifactValidationError("report checkpoint_results identities do not match checkpoint artifact")
    if report.checkpoint_results:
        report_rows_by_key: dict[tuple[str, str], CheckpointArtifactRow] = {
            key: row for key, row in zip(report_checkpoint_keys, report.checkpoint_results, strict=True)
        }
        for artifact_row in checkpoint_rows:
            key = (artifact_row.scenario_id, artifact_row.checkpoint_id)
            report_row = report_rows_by_key[key]
            if (
                report_row.verdict != artifact_row.verdict
                or report_row.score != artifact_row.score
                or report_row.review_required != artifact_row.review_required
                or report_row.failure_buckets != artifact_row.failure_buckets
                or report_row.final_output_source != artifact_row.final_output_source
            ):
                raise ArtifactValidationError(
                    f"report checkpoint row {key} disagrees with checkpoint artifact verdict fields"
                )
    if isinstance(report.runtime_graph_alignments_summary, AlignmentSummary):
        summary = report.runtime_graph_alignments_summary
        actual_verdict_counts = Counter(
            {"pass": actual_verdict_counts["pass"], "fail": actual_verdict_counts["fail"]}
        )
        if dict(sorted(summary.checkpoint_scored_verdict_counts.items())) != dict(
            sorted(actual_verdict_counts.items())
        ):
            raise ArtifactValidationError(
                "runtime checkpoint verdict counts do not match runtime_graph_alignments_summary"
            )
        if summary.checkpoint_scored_review_required_count != actual_review_required_count:
            raise ArtifactValidationError(
                "runtime checkpoint review count does not match runtime_graph_alignments_summary"
            )
        if dict(sorted(summary.checkpoint_scored_failure_bucket_counts.items())) != dict(
            sorted(actual_failure_bucket_counts.items())
        ):
            raise ArtifactValidationError(
                "runtime checkpoint failure buckets do not match runtime_graph_alignments_summary"
            )

    if suite == "memory_evolution_runtime_v1":
        if report.runtime_graph_alignments_summary != standalone_alignment_summary:
            raise ArtifactValidationError("runtime_graph_alignments_summary.json disagrees with report.json")
        assert standalone_alignment_summary is not None
        full_counts = Counter(str(row.verdict) for row in alignment_rows)
        full_item_counts = Counter(f"{row.item_type}:{row.verdict}" for row in alignment_rows)
        if standalone_alignment_summary.full_graph_audit_alignment_count != len(alignment_rows):
            raise ArtifactValidationError("full graph alignment count disagrees with raw alignment rows")
        if standalone_alignment_summary.full_graph_audit_alignment_counts != dict(sorted(full_counts.items())):
            raise ArtifactValidationError("full graph alignment verdict counts disagree with raw alignment rows")
        if standalone_alignment_summary.full_graph_audit_alignment_counts_by_item_type != dict(
            sorted(full_item_counts.items())
        ):
            raise ArtifactValidationError("full graph alignment item counts disagree with raw alignment rows")
        checkpoint_expected_ids: dict[tuple[str, str], set[str]] = {}
        for checkpoint_row in runtime_checkpoint_rows:
            expected = checkpoint_row.expected
            expected_ids = {
                item
                for values in (
                    expected.expected_entity_ids,
                    expected.expected_claim_ids,
                    expected.expected_relation_ids,
                    expected.expected_action_ids,
                    expected.expected_citation_event_ids,
                    expected.expected_execution_entity_ids,
                    expected.expected_execution_claim_ids,
                    expected.expected_execution_citation_event_ids,
                )
                for item in values
            }
            checkpoint_expected_ids[(checkpoint_row.scenario_id, checkpoint_row.checkpoint_id)] = expected_ids
        checkpoint_alignment_rows = [
            row
            for row in alignment_rows
            if row.oracle_id
            and row.oracle_id in checkpoint_expected_ids.get((row.scenario_id, row.checkpoint_id), set())
        ]
        checkpoint_counts = Counter(str(row.verdict) for row in checkpoint_alignment_rows)
        checkpoint_item_counts = Counter(f"{row.item_type}:{row.verdict}" for row in checkpoint_alignment_rows)
        if standalone_alignment_summary.checkpoint_expected_alignment_audit_count != len(checkpoint_alignment_rows):
            raise ArtifactValidationError("checkpoint expected alignment count disagrees with raw alignment rows")
        if standalone_alignment_summary.checkpoint_expected_alignment_audit_counts != dict(
            sorted(checkpoint_counts.items())
        ):
            raise ArtifactValidationError(
                "checkpoint expected alignment verdict counts disagree with raw alignment rows"
            )
        if standalone_alignment_summary.checkpoint_expected_alignment_audit_counts_by_item_type != dict(
            sorted(checkpoint_item_counts.items())
        ):
            raise ArtifactValidationError("checkpoint expected alignment item counts disagree with raw alignment rows")
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
    expected_failure_keys = {(row.scenario_id, row.checkpoint_id) for row in checkpoint_rows if row.success is False}
    if failure_keys != expected_failure_keys:
        raise ArtifactValidationError(f"{failure_path.name} identities do not match non-pass checkpoint verdicts")
    return report
