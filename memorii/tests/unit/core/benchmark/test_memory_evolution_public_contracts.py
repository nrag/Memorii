from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from memorii.core.benchmark.artifact_rows import (
    BenchmarkReportSummary,
    RuntimeCheckpointResultRow,
    RuntimeGraphAlignmentRow,
    SimCheckpointResultRow,
)
from memorii.core.benchmark.memory_evolution_runtime import (
    RuntimeSuiteRows,
    runtime_alignment_summary,
    runtime_summary_metrics,
)
from memorii.core.benchmark.memory_evolution_sim import (
    expected_sim_output_for_checkpoint,
    generate_memory_evolution_sim_scenarios,
    judge_sim_checkpoint,
    normalize_sim_system_output_for_checkpoint,
    sim_reconstruction_context_for_checkpoint,
)
from memorii.tools.run_benchmark import main


def _runtime_graph_summary_payload() -> dict[str, object]:
    return {
        "source_observation_count": 1,
        "entity_count": 1,
        "claim_count": 3,
        "action_count": 0,
        "relation_item_count": 0,
        "action_item_count": 0,
        "graph_edge_count": 4,
        "graph_edge_counts_by_type": {"observed_in": 1},
        "runtime_graph_node_counts_by_type": {"claim": 3},
        "runtime_graph_item_counts_by_type": {"claim": 3},
        "runtime_relation_support_modes": {},
        "evidence_edge_count": 1,
        "active_claim_count": 1,
        "active_claim_with_subject_count": 1,
        "active_claim_with_object_or_literal_count": 1,
        "active_claim_with_scope_count": 1,
        "active_claim_with_observed_in_count": 1,
        "active_action_count": 0,
        "active_action_with_observed_in_count": 0,
        "active_claim_with_subject_rate": 1.0,
        "active_claim_with_object_or_literal_rate": 1.0,
        "active_claim_with_scope_rate": 1.0,
        "active_claim_with_observed_in_rate": 1.0,
        "active_action_with_observed_in_rate": 0.0,
        "runtime_graph_validation_error_count": 0,
    }


def _alignment_summary_payload() -> dict[str, object]:
    return {
        "alignment_summary_policy": {"checkpoint_scored": "authoritative"},
        "checkpoint_expected_alignment_audit_count": 1,
        "checkpoint_expected_alignment_audit_counts": {"aligned": 1},
        "checkpoint_expected_alignment_audit_counts_by_item_type": {"claim:aligned": 1},
        "checkpoint_scored_verdict_counts": {"pass": 2},
        "checkpoint_scored_review_required_count": 0,
        "checkpoint_scored_failure_bucket_counts": {},
        "full_graph_audit_alignment_count": 1,
        "full_graph_audit_alignment_counts": {"aligned": 1},
        "full_graph_audit_alignment_counts_by_item_type": {"claim:aligned": 1},
    }


def _calibration_report_payload() -> dict[str, object]:
    return {
        "event_count": 0,
        "labeled_event_count": 0,
        "overall_accuracy": None,
        "ece": 0.0,
        "brier_score": 0.0,
        "overconfident_wrong_count": 0,
        "low_confidence_correct_count": 0,
        "hidden_hallucination_rate": 0.0,
        "ambiguous_overcommit_rate": 0.0,
        "worst_slices": [],
        "rolling_windows": {},
        "response_recommendations": {},
        "label_source_counts": {},
        "hierarchy_layer_counts": {},
    }


def _decision_quality_payload() -> dict[str, object]:
    return {
        "decision_cost_total": 0.0,
        "decision_cost_mean": 0.0,
        "cost_by_failure_bucket": {},
        "cost_by_checkpoint_type": {},
        "cost_by_source_modality": {},
        "cost_by_decision_action": {},
        "regret_total": 0.0,
        "regret_mean": 0.0,
    }


def _benchmark_report_payload() -> dict[str, object]:
    return {
        "suite": "memory_evolution_runtime_v1",
        "mode": "hybrid",
        "profile": "long_horizon",
        "seed": 7,
        "scenario_count": 1,
        "event_count": 10,
        "checkpoint_count": 2,
        "passed": 1,
        "failed": 0,
        "llm_calls": 10,
        "provider_successes": 10,
        "provider_failures": 0,
        "fallbacks": 0,
        "final_output_source_counts": {"fake_oracle": 2},
        "metrics": {"hidden_hallucination_rate": 0.0},
        "fixture_hashes": {"surface_observations": "abc"},
        "calibration": _calibration_report_payload(),
        "decision_quality": _decision_quality_payload(),
        "runtime": {"runtime_checkpoint_count": 2},
        "runtime_graph_summary": _runtime_graph_summary_payload(),
        "runtime_graph_alignments_summary": _alignment_summary_payload(),
        "warning_policy": {"extra_context_provenance": {"level": "warning_only"}},
        "unknown_future_field": "kept",
    }


def _latest_run_dir(storage_root: Path, suite: str, mode: str) -> Path:
    return sorted((storage_root / "benchmark_runs" / suite / mode).glob("bench-*"))[-1]


def _jsonl_rows(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _runtime_checkpoint_row(**legacy_fields: object) -> RuntimeCheckpointResultRow:
    return RuntimeCheckpointResultRow(
        scenario_id=str(legacy_fields.pop("scenario_id", "scenario_1")),
        checkpoint_id=str(legacy_fields.pop("checkpoint_id", "checkpoint_1")),
        checkpoint_type=str(legacy_fields.pop("checkpoint_type", "current_truth")),
        success=bool(legacy_fields.pop("success", True)),
        passed=bool(legacy_fields.pop("passed", True)),
        verdict=str(legacy_fields.pop("verdict", "pass")),
        score=float(legacy_fields.pop("score", 1.0)),
        review_required=bool(legacy_fields.pop("review_required", False)),
        failure_buckets=list(legacy_fields.pop("failure_buckets", [])),
        warning_buckets=list(legacy_fields.pop("warning_buckets", [])),
        diagnostics=dict(legacy_fields.pop("diagnostics", {})),
        output=dict(legacy_fields.pop("output", {})),
        profile=str(legacy_fields.pop("profile", "long_horizon")),
        family=str(legacy_fields.pop("family", "current_truth")),
        decision_mode=str(legacy_fields.pop("decision_mode", "llm")),
        effective_decision_mode=str(legacy_fields.pop("effective_decision_mode", "llm")),
        final_output_source=str(legacy_fields.pop("final_output_source", "fake_oracle")),
        runtime_failure_buckets=list(legacy_fields.pop("runtime_failure_buckets", [])),
        runtime_failure_classification=list(legacy_fields.pop("runtime_failure_classification", [])),
        scenario_provider_successes=int(legacy_fields.pop("scenario_provider_successes", 0)),
        scenario_provider_failures=int(legacy_fields.pop("scenario_provider_failures", 0)),
        scenario_fallbacks=int(legacy_fields.pop("scenario_fallbacks", 0)),
        provider_count_scope=str(legacy_fields.pop("provider_count_scope", "scenario_extractor_calls")),
        legacy_fields=legacy_fields,
    )


def test_artifact_row_models_are_strict_but_flat_json_compatible() -> None:
    row = SimCheckpointResultRow.from_flat_row(
        {
            "scenario_id": "scenario_1",
            "checkpoint_id": "checkpoint_1",
            "checkpoint_type": "current_truth",
            "success": True,
            "passed": True,
            "verdict": "pass",
            "score": 1.0,
            "review_required": False,
            "failure_buckets": [],
            "warning_buckets": [],
            "diagnostics": {},
            "output": {},
            "profile": "smoke",
            "family": "current_truth",
            "decision_mode": "llm",
            "effective_decision_mode": "llm",
            "final_output_source": "fake_oracle",
            "legacy_flat_field": "kept",
        }
    )

    assert row.legacy_fields == {"legacy_flat_field": "kept"}
    assert row.to_json_row()["legacy_flat_field"] == "kept"
    with pytest.raises(ValueError):
        row.model_copy(update={"legacy_fields": {"passed": None}}).to_json_row()
    with pytest.raises(ValidationError):
        SimCheckpointResultRow.model_validate(
            {
                "scenario_id": "scenario_1",
                "checkpoint_id": "checkpoint_1",
                "checkpoint_type": "current_truth",
                "success": True,
                "passed": True,
                "verdict": "pass",
                "score": 1.0,
                "review_required": False,
                "output": {},
                "profile": "smoke",
                "family": "current_truth",
                "decision_mode": "llm",
                "effective_decision_mode": "llm",
                "final_output_source": "fake_oracle",
                "unexpected": "rejected",
            }
        )
    with pytest.raises(ValidationError):
        SimCheckpointResultRow.from_flat_row(
            {
                "scenario_id": "scenario_1",
                "checkpoint_id": "checkpoint_1",
                "checkpoint_type": "current_truth",
                "success": True,
                "passed": True,
                "verdict": "pas",
                "score": 1.0,
                "review_required": False,
                "output": {},
                "profile": "smoke",
                "family": "current_truth",
                "decision_mode": "llm",
                "effective_decision_mode": "llm",
                "final_output_source": "fake_oracle",
            }
        )
    with pytest.raises(ValidationError):
        SimCheckpointResultRow.from_flat_row(
            {
                "scenario_id": "scenario_1",
                "checkpoint_id": "checkpoint_1",
                "checkpoint_type": "current_truth",
                "success": True,
                "passed": True,
                "verdict": "pass",
                "score": 1.1,
                "review_required": False,
                "output": {},
                "profile": "smoke",
                "family": "current_truth",
                "decision_mode": "llm",
                "effective_decision_mode": "llm",
                "final_output_source": "fake_oracle",
            }
        )


def test_runtime_alignment_row_requires_runtime_and_oracle_identity_contract() -> None:
    row = RuntimeGraphAlignmentRow.from_runtime_alignment(
        {
            "scenario_id": "scenario_1",
            "checkpoint_id": "checkpoint_1",
            "oracle_item_id": "claim_expected",
            "runtime_item_id": "graph:node:claim:runtime",
            "item_type": "claim",
            "verdict": "aligned",
            "score": 1.0,
            "matched_on": ["subject", "predicate", "object"],
            "rationale": "matched",
        }
    )

    assert row.oracle_id == "claim_expected"
    assert row.runtime_id == "graph:node:claim:runtime"
    json_row = row.to_json_row()
    assert json_row["oracle_id"] == "claim_expected"
    assert json_row["runtime_id"] == "graph:node:claim:runtime"
    assert json_row["oracle_item_id"] == "claim_expected"
    assert json_row["runtime_item_id"] == "graph:node:claim:runtime"
    with pytest.raises(ValidationError):
        RuntimeGraphAlignmentRow.model_validate(
            {
                "scenario_id": "scenario_1",
                "checkpoint_id": "checkpoint_1",
                "item_type": "claim",
                "verdict": "aligned",
                "score": 1.0,
                "matched_on": [],
                "failure_reason": "",
            }
        )
    with pytest.raises(ValidationError):
        RuntimeGraphAlignmentRow.from_runtime_alignment(
            {
                "scenario_id": "scenario_1",
                "checkpoint_id": "checkpoint_1",
                "oracle_item_id": "claim_expected",
                "item_type": "claim",
                "verdict": "aligned",
                "score": 1.0,
                "matched_on": ["subject"],
                "rationale": "runtime item was accidentally omitted",
            }
        )


def test_benchmark_report_summary_types_runtime_and_calibration_sections() -> None:
    payload = _benchmark_report_payload()
    report = BenchmarkReportSummary.from_flat_row(payload)

    assert report.fixture_hashes == {"surface_observations": "abc"}
    assert report.calibration.model_dump(mode="json") == _calibration_report_payload()
    assert report.decision_quality.model_dump(mode="json") == _decision_quality_payload()
    assert report.runtime == {"runtime_checkpoint_count": 2}
    assert report.runtime_graph_summary.to_json_row() == _runtime_graph_summary_payload()
    assert report.runtime_graph_alignments_summary.to_json_row() == _alignment_summary_payload()
    assert report.warning_policy == {"extra_context_provenance": {"level": "warning_only"}}
    assert report.legacy_fields == {"unknown_future_field": "kept"}

    missing_calibration = {**payload}
    missing_calibration.pop("calibration")
    with pytest.raises(ValidationError, match="requires calibration"):
        BenchmarkReportSummary.from_flat_row(missing_calibration)

    missing_decision_quality = {**payload}
    missing_decision_quality.pop("decision_quality")
    with pytest.raises(ValidationError, match="requires decision_quality"):
        BenchmarkReportSummary.from_flat_row(missing_decision_quality)

    malformed_runtime_summary = {**payload, "runtime_graph_summary": {"claim_count": 3}}
    with pytest.raises(ValidationError):
        BenchmarkReportSummary.from_flat_row(malformed_runtime_summary)


def test_memory_evolution_public_imports_remain_compatible() -> None:
    modules = [
        "memorii.core.benchmark.memory_evolution_sim",
        "memorii.core.benchmark.memory_evolution_runtime",
        "memorii.tools.run_benchmark",
    ]

    for module_name in modules:
        assert importlib.import_module(module_name)


def test_memory_evolution_split_submodule_imports_remain_compatible() -> None:
    expected_symbols = {
        "memorii.core.benchmark.memory_evolution_sim.schemas": "SimSystemOutput",
        "memorii.core.benchmark.memory_evolution_sim.generation": "generate_memory_evolution_sim_scenarios",
        "memorii.core.benchmark.memory_evolution_sim.candidate_cards": "sim_reconstruction_context_for_checkpoint",
        "memorii.core.benchmark.memory_evolution_sim.normalization": "normalize_sim_system_output_for_checkpoint",
        "memorii.core.benchmark.memory_evolution_sim.judges": "judge_sim_checkpoint",
        "memorii.core.benchmark.memory_evolution_sim.diagnostics": "sim_checkpoint_diagnostics",
        "memorii.core.benchmark.memory_evolution_sim.metrics": "sim_metrics_from_rows",
        "memorii.core.benchmark.memory_evolution_runtime.ingestion": "ingest_scenario_surface_observations",
        "memorii.core.benchmark.memory_evolution_runtime.graph_items": "graph_items_from_snapshot",
        "memorii.core.benchmark.memory_evolution_runtime.alignment": "align_runtime_graph_to_oracle",
        "memorii.core.benchmark.memory_evolution_runtime.checkpoint_projection": "project_runtime_checkpoint",
        "memorii.core.benchmark.memory_evolution_runtime.execution_state_projection": "RuntimeProjection",
        "memorii.core.benchmark.memory_evolution_runtime.artifacts": "write_runtime_artifacts",
        "memorii.core.benchmark.memory_evolution_runtime.runner": "run_runtime_scenarios",
    }

    for module_name, symbol_name in expected_symbols.items():
        module = importlib.import_module(module_name)
        assert hasattr(module, symbol_name), f"{module_name} must export {symbol_name}"


def test_memory_evolution_sim_public_checkpoint_contract() -> None:
    scenario = generate_memory_evolution_sim_scenarios(
        profile="adversarial",
        scenario_count=1,
        seed=7,
        noise_rate=0.35,
    )[0]
    checkpoint = scenario.checkpoints[0]

    context = sim_reconstruction_context_for_checkpoint(scenario=scenario, checkpoint=checkpoint)
    expected = expected_sim_output_for_checkpoint(checkpoint)
    normalized, normalization = normalize_sim_system_output_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
        output=expected,
    )
    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=normalized)

    assert context.checkpoint.checkpoint_id == checkpoint.checkpoint_id
    assert isinstance(normalization.normalization_applied, bool)
    assert aggregate.verdict.value == "pass"
    assert aggregate.score >= 0.99


def test_memory_evolution_runtime_public_summary_contract() -> None:
    with pytest.raises(TypeError, match="checkpoint_rows must contain RuntimeCheckpointResultRow"):
        RuntimeSuiteRows(
            scenario_rows=[],
            checkpoint_rows=[{"verdict": "pass"}],
            judge_rows=[],
            llm_rows=[],
        )

    rows = RuntimeSuiteRows(
        scenario_rows=[],
        checkpoint_rows=[
            _runtime_checkpoint_row(runtime_action_alignments=[])
        ],
        judge_rows=[],
        llm_rows=[
            {
                "success": True,
                "fallback_used": False,
            }
        ],
        alignments=[],
    )

    metrics = runtime_summary_metrics(rows)
    alignment_summary = runtime_alignment_summary(rows)

    assert metrics["provider_successes"] == 1
    assert metrics["provider_failures"] == 0
    assert metrics["fallbacks"] == 0
    assert metrics["final_output_source_counts"] == {"fake_oracle": 1}
    assert alignment_summary["checkpoint_expected_alignment_audit_count"] == 0
    assert alignment_summary["checkpoint_scored_verdict_counts"] == {"pass": 1}
    assert "checkpoint_required_alignment_count" not in alignment_summary

    canonical_alignment_rows = RuntimeSuiteRows(
        scenario_rows=[],
        checkpoint_rows=[
            _runtime_checkpoint_row(expected={"expected_claim_ids": ["claim_expected"]}, runtime_action_alignments=[])
        ],
        judge_rows=[],
        llm_rows=[],
        alignments=[
            RuntimeGraphAlignmentRow.model_validate(
                {
                    "scenario_id": "scenario_1",
                    "checkpoint_id": "checkpoint_1",
                    "oracle_id": "claim_expected",
                    "runtime_id": "graph:node:claim:runtime",
                    "item_type": "claim",
                    "verdict": "aligned",
                    "score": 1.0,
                    "matched_on": ["subject", "predicate", "object"],
                    "failure_reason": "",
                }
            )
        ],
    )

    canonical_summary = runtime_alignment_summary(canonical_alignment_rows)
    assert canonical_summary["checkpoint_expected_alignment_audit_count"] == 1
    assert canonical_summary["checkpoint_expected_alignment_audit_counts"] == {"aligned": 1}


def test_memory_evolution_sim_dry_run_artifact_public_shape(tmp_path: Path) -> None:
    assert main(
        [
            "--suite",
            "memory_evolution_sim_v1",
            "--mode",
            "llm",
            "--dry-run",
            "--storage-root",
            str(tmp_path),
            "--sim-profile",
            "adversarial",
            "--sim-scenario-count",
            "10",
            "--sim-noise-rate",
            "0.35",
            "--seed",
            "7",
        ]
    ) == 0

    run_dir = _latest_run_dir(tmp_path, "memory_evolution_sim_v1", "llm")
    report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    checkpoint_rows = _jsonl_rows(run_dir / "sim_checkpoint_results.jsonl")

    assert report["suite"] == "memory_evolution_sim_v1"
    assert report["passed"] == 10
    assert report["failed"] == 0
    assert report["final_output_source_counts"] == {"fake_oracle": report["checkpoint_count"]}
    assert (run_dir / "calibration_report.json").exists()
    assert (run_dir / "decision_quality_report.json").exists()
    assert checkpoint_rows
    for row in checkpoint_rows:
        assert row["passed"] is not None
        assert row["verdict"] in {"pass", "fail", "abstain"}
        assert row["score"] is not None
        assert row["review_required"] is not None


def test_memory_evolution_runtime_dry_run_artifact_public_shape(tmp_path: Path) -> None:
    assert main(
        [
            "--suite",
            "memory_evolution_runtime_v1",
            "--mode",
            "llm",
            "--dry-run",
            "--storage-root",
            str(tmp_path),
            "--sim-profile",
            "long_horizon",
            "--sim-scenario-count",
            "10",
            "--sim-noise-rate",
            "0.35",
            "--seed",
            "7",
        ]
    ) == 0

    run_dir = _latest_run_dir(tmp_path, "memory_evolution_runtime_v1", "llm")
    report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    runtime_rows = _jsonl_rows(run_dir / "runtime_checkpoint_results.jsonl")
    alignment_summary = json.loads((run_dir / "runtime_graph_alignments_summary.json").read_text(encoding="utf-8"))

    assert report["suite"] == "memory_evolution_runtime_v1"
    assert report["passed"] == 10
    assert report["failed"] == 0
    assert report["final_output_source_counts"] == {"fake_oracle": report["checkpoint_count"]}
    assert (run_dir / "calibration_report.json").exists()
    assert (run_dir / "decision_quality_report.json").exists()
    assert alignment_summary["checkpoint_scored_verdict_counts"] == {"pass": report["checkpoint_count"]}
    assert alignment_summary["checkpoint_scored_review_required_count"] == 0
    assert "checkpoint_required_alignment_count" not in alignment_summary
    assert runtime_rows
    for row in runtime_rows:
        assert row["passed"] is not None
        assert row["verdict"] in {"pass", "fail", "abstain"}
        assert row["score"] is not None
        assert row["review_required"] is not None
        assert "runtime_failure_buckets" in row
        assert "runtime_failure_classification" in row
