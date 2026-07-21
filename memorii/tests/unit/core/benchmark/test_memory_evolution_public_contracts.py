from __future__ import annotations

import importlib
import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest
from memorii.core.benchmark.artifact_rows import (
    AlignmentSummary,
    ArtifactJsonObject,
    BenchmarkReportSummary,
    RuntimeCheckpointResultRow,
    RuntimeExtractorOutput,
    RuntimeExtractorTracePayload,
    RuntimeExtractorTraceRow,
    RuntimeGraphAlignmentRow,
    RuntimeGraphSummary,
    RuntimeProviderHealth,
    SimCheckpointResultRow,
    WarningPolicyEntry,
)
from memorii.core.benchmark.artifact_validation import (
    ArtifactValidationError,
    write_json_atomic,
    write_typed_jsonl,
)
from memorii.core.benchmark.calibration.alignment import RuntimeGraphAlignment, RuntimeGraphAlignmentVerdict
from memorii.core.benchmark.calibration.models import CalibrationSlice
from memorii.core.benchmark.memory_evolution_runtime import (
    RuntimeSuiteRows,
    runtime_alignment_summary,
    runtime_summary_metrics,
)
from memorii.core.benchmark.memory_evolution_sim import (
    JudgeAggregate,
    JudgeVerdict,
    MemoryEvolutionSimReconstructionContext,
    OracleCheckpoint,
    SimCheckpointContract,
    SimSystemOutput,
    expected_sim_output_for_checkpoint,
    generate_memory_evolution_sim_scenarios,
    judge_sim_checkpoint,
    sim_reconstruction_context_for_checkpoint,
)
from memorii.tools.run_benchmark import main
from pydantic import ValidationError
from tests.unit.core.benchmark.checkpoint_artifact_test_helpers import checkpoint_diagnostics_payload


def test_json_writer_serializes_nested_typed_models_at_boundary(tmp_path: Path) -> None:
    path = tmp_path / "typed.json"
    rows = [CalibrationSlice(slice_key="profile", slice_values={"profile": "adversarial"}, n=1)]

    write_json_atomic(path, rows)

    assert json.loads(path.read_text(encoding="utf-8")) == [
        {
            "accuracy": None,
            "brier_score": None,
            "ece": None,
            "eligible_for_failure": False,
            "mean_confidence": None,
            "n": 1,
            "probability_event_count": 0,
            "response_level": "report_only",
            "scenario_count": 0,
            "slice_key": "profile",
            "slice_values": {"profile": "adversarial"},
            "wilson_high": None,
            "wilson_low": None,
        }
    ]


def _runtime_graph_summary_payload() -> dict[str, object]:
    return {
        "source_observation_count": 1,
        "entity_count": 1,
        "claim_count": 3,
        "action_count": 0,
        "relation_item_count": 0,
        "action_item_count": 0,
        "graph_edge_count": 4,
        "graph_edge_counts_by_type": {
            "has_literal_object": 1,
            "has_scope": 1,
            "has_subject": 1,
            "observed_in": 1,
        },
        "runtime_graph_node_counts_by_type": {"claim": 3, "entity": 1},
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
        "snapshot_count": 0,
        "aggregation_scope": "final_snapshot_per_scenario",
        "cumulative_graph_edge_count": 0,
        "cumulative_validation_error_count": 0,
        "terminal_snapshot_count": 0,
        "terminal_snapshot_anomaly_count": 0,
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
        "probability_event_count": 0,
        "partial_event_count": 0,
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
        "scenario_cluster_intervals": {},
        "risk_coverage": [],
        "abstention_rate": None,
        "selective_risk_at_full_coverage": None,
        "input_telemetry_count": 0,
        "input_telemetry_by_type": {},
        "scenario_count": 0,
        "minimum_scenario_count": 30,
        "stability_status": "insufficient_coverage",
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
    graph_summary = _runtime_graph_summary_payload()
    alignment_summary = _alignment_summary_payload()
    provider_health = {
        "effective_decision_mode": "hybrid",
        "attempted_calls": 10,
        "provider_successes": 10,
        "provider_failures": 0,
        "fallbacks": 0,
        "provider_success_rate": 1.0,
        "status": "pass",
        "clean_runtime_gate": True,
        "failure_buckets": [],
        "failure_classification_counts": {},
        "execution_source": "live_llm",
        "dry_run": False,
        "fake_extractor_calls": 0,
        "provider_metadata": {},
        "policy": {"provider_successes": "authoritative"},
    }
    runtime = {
        "runtime_checkpoint_count": 2,
        "runtime_failure_bucket_counts": {},
        "provider_successes": 10,
        "provider_failures": 0,
        "fallbacks": 0,
        "final_output_source_counts": {"live_llm": 2},
        "runtime_alignment_count": 1,
        "runtime_graph_item_count": 3,
        "runtime_graph_item_observation_count": 1,
        "runtime_graph_summary": graph_summary,
        "runtime_graph_alignments_summary": alignment_summary,
        "long_horizon_slice_counts": {},
        "runtime_provider_health": provider_health,
    }
    return {
        "suite": "memory_evolution_runtime_v1",
        "mode": "hybrid",
        "profile": "long_horizon",
        "seed": 7,
        "fixture_fingerprint": "fixture-abc",
        "evaluation_fingerprint": "evaluation-abc",
        "system_fingerprint": "system-abc",
        "source_revision": "revision:test",
        "source_tree_digest": "1" * 64,
        "source_state": "clean",
        "report_content_digest": "2" * 64,
        "artifact_manifest_digest": "3" * 64,
        "scenario_count": 1,
        "event_count": 10,
        "checkpoint_count": 2,
        "passed": 1,
        "failed": 0,
        "llm_calls": 10,
        "provider_successes": 10,
        "provider_failures": 0,
        "fallbacks": 0,
        "dry_run": False,
        "execution_source": "live_llm",
        "final_output_source_counts": {"live_llm": 2},
        "metrics": {"hidden_hallucination_rate": 0.0},
        "fixture_hashes": {"surface_observations": "abc"},
        "calibration": _calibration_report_payload(),
        "decision_quality": _decision_quality_payload(),
        "runtime": runtime,
        "runtime_graph_summary": graph_summary,
        "runtime_graph_alignments_summary": alignment_summary,
        "runtime_provider_health": provider_health,
        "warning_policy": {"extra_context_provenance": {"level": "warning_only"}},
    }


def _latest_run_dir(storage_root: Path, suite: str, mode: str) -> Path:
    return sorted((storage_root / "benchmark_runs" / suite / mode).glob("bench-*"))[-1]


def _jsonl_rows(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _runtime_checkpoint_row(**row_fields: object) -> RuntimeCheckpointResultRow:
    expected_payload = dict(row_fields.pop("expected", {}))
    output_payload = dict(row_fields.pop("output", {}))
    candidate_payload = dict(row_fields.pop("candidate_cards", {}))
    raw_output_payload = dict(row_fields.pop("raw_output", output_payload))
    judge_payload = dict(row_fields.pop("judge_aggregate", {}))
    return RuntimeCheckpointResultRow(
        scenario_id=str(row_fields.pop("scenario_id", "scenario_1")),
        checkpoint_id=str(row_fields.pop("checkpoint_id", "checkpoint_1")),
        checkpoint_type=str(row_fields.pop("checkpoint_type", "current_truth")),
        success=bool(row_fields.pop("success", True)),
        passed=bool(row_fields.pop("passed", True)),
        verdict=str(row_fields.pop("verdict", "pass")),
        score=float(row_fields.pop("score", 1.0)),
        review_required=bool(row_fields.pop("review_required", False)),
        failure_buckets=list(row_fields.pop("failure_buckets", [])),
        warning_buckets=list(row_fields.pop("warning_buckets", [])),
        output=SimSystemOutput.model_validate(output_payload or {"operation": "abstain", "rationale": "test"}),
        profile=str(row_fields.pop("profile", "long_horizon")),
        family=str(row_fields.pop("family", "current_truth")),
        decision_mode=str(row_fields.pop("decision_mode", "llm")),
        effective_decision_mode=str(row_fields.pop("effective_decision_mode", "llm")),
        final_output_source=str(row_fields.pop("final_output_source", "fake_oracle")),
        runtime_failure_buckets=list(row_fields.pop("runtime_failure_buckets", [])),
        runtime_failure_classification=list(row_fields.pop("runtime_failure_classification", [])),
        scenario_provider_successes=int(row_fields.pop("scenario_provider_successes", 0)),
        scenario_provider_failures=int(row_fields.pop("scenario_provider_failures", 0)),
        scenario_fallbacks=int(row_fields.pop("scenario_fallbacks", 0)),
        provider_count_scope=str(row_fields.pop("provider_count_scope", "scenario_extractor_calls")),
        confidence=float(row_fields.pop("confidence", 1.0)),
        provider_successes=int(row_fields.pop("provider_successes", 0)),
        provider_failures=int(row_fields.pop("provider_failures", 0)),
        fallbacks=int(row_fields.pop("fallbacks", 0)),
        phase=str(row_fields.pop("phase", "checkpoint")),
        horizon_distance=int(row_fields.pop("horizon_distance", 0)),
        horizon_distance_bucket=str(row_fields.pop("horizon_distance_bucket", "short")),
        interference_count=int(row_fields.pop("interference_count", 0)),
        interference_count_bucket=str(row_fields.pop("interference_count_bucket", "none")),
        source_event_age_days=float(row_fields.pop("source_event_age_days", 0.0)),
        source_event_age_days_bucket=str(row_fields.pop("source_event_age_days_bucket", "fresh")),
        required_retrieval_view=str(row_fields.pop("required_retrieval_view", "current")),
        query_or_task=str(row_fields.pop("query_or_task", "")),
        expected=OracleCheckpoint.model_validate(
            {
                "checkpoint_id": "checkpoint_1",
                "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
                "checkpoint_type": "current_truth",
                "query_or_task": "",
                "checkpoint_contract": SimCheckpointContract().model_dump(mode="json"),
                **expected_payload,
            }
        ),
        candidate_cards=MemoryEvolutionSimReconstructionContext.model_validate(
            {
                "scenario_id": "scenario_1",
                "surface_observations": [],
                "checkpoint": {
                    "checkpoint_id": "checkpoint_1",
                    "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
                    "query_or_task": "",
                },
                **candidate_payload,
            }
        ),
        raw_output=SimSystemOutput.model_validate(raw_output_payload or {"operation": "abstain", "rationale": "test"}),
        judge_aggregate=JudgeAggregate.model_validate(
            {
                "checkpoint_id": "checkpoint_1",
                "verdict": JudgeVerdict.PASS,
                "score": 1.0,
                "confidence": 1.0,
                "votes": [],
                "required_judge_ids": [],
                "critical_failure_buckets": [],
                "review_required": False,
                "rationale": "test",
                **judge_payload,
            }
        ),
        diagnostics=checkpoint_diagnostics_payload(
            **dict(row_fields.pop("diagnostics", {})),
            **row_fields,
        ),
    )


def test_artifact_row_models_are_strict_and_serialize_flat_json() -> None:
    row = SimCheckpointResultRow.model_validate(
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
            "diagnostics": checkpoint_diagnostics_payload().model_dump(mode="json"),
            "output": {"operation": "abstain", "rationale": "test"},
            "raw_output": {"operation": "abstain", "rationale": "test"},
            "expected": {
                "checkpoint_id": "checkpoint_1",
                "timestamp": "2026-01-01T00:00:00Z",
                "checkpoint_type": "current_truth",
                "query_or_task": "",
                "checkpoint_contract": {},
            },
            "candidate_cards": {
                "scenario_id": "scenario_1",
                "surface_observations": [],
                "checkpoint": {
                    "checkpoint_id": "checkpoint_1",
                    "timestamp": "2026-01-01T00:00:00Z",
                    "query_or_task": "",
                },
            },
            "judge_aggregate": {
                "checkpoint_id": "checkpoint_1",
                "verdict": "pass",
                "score": 1.0,
                "confidence": 1.0,
                "rationale": "test",
            },
            "profile": "smoke",
            "family": "current_truth",
            "decision_mode": "llm",
            "effective_decision_mode": "llm",
            "final_output_source": "fake_oracle",
        }
    )

    assert "legacy_fields" not in row.model_dump()
    assert "legacy_flat_field" not in row.to_json_row()
    with pytest.raises(ValidationError):
        SimCheckpointResultRow.model_validate({**row.to_json_row(), "unknown_field": "rejected"})
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
        SimCheckpointResultRow.model_validate(
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
        SimCheckpointResultRow.model_validate(
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
    row = RuntimeGraphAlignmentRow.from_alignment(
        RuntimeGraphAlignment(
            oracle_item_id="claim_expected",
            runtime_item_id="graph:node:claim:runtime",
            item_type="claim",
            verdict=RuntimeGraphAlignmentVerdict.ALIGNED,
            score=1.0,
            matched_on=["subject", "predicate", "object"],
            rationale="matched",
        ),
        scenario_id="scenario_1",
        checkpoint_id="checkpoint_1",
    )

    assert row.oracle_id == "claim_expected"
    assert row.runtime_id == "graph:node:claim:runtime"
    json_row = row.to_json_row()
    assert json_row["oracle_id"] == "claim_expected"
    assert json_row["runtime_id"] == "graph:node:claim:runtime"
    assert "oracle_item_id" not in json_row
    assert "runtime_item_id" not in json_row
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
        RuntimeGraphAlignmentRow.from_alignment(
            RuntimeGraphAlignment(
                oracle_item_id="claim_expected",
                item_type="claim",
                verdict=RuntimeGraphAlignmentVerdict.ALIGNED,
                score=1.0,
                matched_on=["subject"],
                rationale="runtime item was accidentally omitted",
            ),
            scenario_id="scenario_1",
            checkpoint_id="checkpoint_1",
        )


def test_benchmark_report_summary_types_runtime_and_calibration_sections() -> None:
    payload = _benchmark_report_payload()
    report = BenchmarkReportSummary.model_validate(payload)

    assert report.fixture_hashes == {"surface_observations": "abc"}
    assert report.calibration.model_dump(mode="json") == _calibration_report_payload()
    assert report.decision_quality.model_dump(mode="json") == _decision_quality_payload()
    assert report.runtime is not None
    assert report.runtime.runtime_checkpoint_count == 2
    assert isinstance(report.runtime_graph_summary, RuntimeGraphSummary)
    assert isinstance(report.runtime_graph_alignments_summary, AlignmentSummary)
    assert isinstance(report.runtime_provider_health, (RuntimeProviderHealth, ArtifactJsonObject))
    assert report.runtime_graph_summary.to_json_row() == _runtime_graph_summary_payload()
    assert report.runtime_graph_alignments_summary.to_json_row() == _alignment_summary_payload()
    warning_policy = report.warning_policy["extra_context_provenance"]
    assert isinstance(warning_policy, WarningPolicyEntry)
    assert warning_policy.model_dump(mode="json") == {"level": "warning_only", "rationale": ""}


def test_dynamic_report_sections_are_json_only() -> None:
    payload = _benchmark_report_payload()
    payload["metrics"] = {"nested": [{"count": 2, "ok": True}]}
    report = BenchmarkReportSummary.model_validate(payload)

    assert report.metrics == payload["metrics"]
    with pytest.raises(ValidationError):
        BenchmarkReportSummary.model_validate({**payload, "metrics": {"bad": object()}})
    with pytest.raises(ValidationError):
        BenchmarkReportSummary.model_validate({**payload, "unknown_future_field": "rejected"})

    missing_calibration = {**payload}
    missing_calibration.pop("calibration")
    with pytest.raises(ValidationError, match="requires calibration"):
        BenchmarkReportSummary.model_validate(missing_calibration)

    missing_decision_quality = {**payload}
    missing_decision_quality.pop("decision_quality")
    with pytest.raises(ValidationError, match="requires decision_quality"):
        BenchmarkReportSummary.model_validate(missing_decision_quality)

    malformed_runtime_summary = {**payload, "runtime_graph_summary": {"claim_count": 3}}
    with pytest.raises(ValidationError):
        BenchmarkReportSummary.model_validate(malformed_runtime_summary)


@pytest.mark.parametrize(
    ("mutate", "error"),
    [
        (
            lambda payload: payload["runtime"].__setitem__("provider_successes", 9),
            "runtime provider_successes must match provider health",
        ),
        (
            lambda payload: payload["runtime"].__setitem__("runtime_alignment_count", 2),
            "runtime alignment count must match full graph alignment count",
        ),
        (
            lambda payload: payload["runtime"].__setitem__("runtime_graph_item_count", 4),
            "runtime graph item count must match graph summary item counts",
        ),
        (
            lambda payload: payload.update(
                {
                    "final_output_source_counts": {"live_llm": 1, "rule": 1},
                    "execution_source": "mixed",
                }
            ),
            "nested and top-level output source counts disagree",
        ),
    ],
)
def test_runtime_report_rejects_cross_section_drift(mutate, error: str) -> None:
    payload = deepcopy(_benchmark_report_payload())
    mutate(payload)

    with pytest.raises(ValidationError, match=error):
        BenchmarkReportSummary.model_validate(payload)


def test_report_count_maps_reject_negative_counts() -> None:
    payload = deepcopy(_benchmark_report_payload())
    payload["critical_failure_bucket_counts"] = {"impossible_negative_count": -1}

    with pytest.raises(ValidationError):
        BenchmarkReportSummary.model_validate(payload)


def test_report_rejects_empty_layer_fingerprints() -> None:
    payload = deepcopy(_benchmark_report_payload())
    payload["evaluation_fingerprint"] = ""

    with pytest.raises(ValidationError):
        BenchmarkReportSummary.model_validate(payload)


def test_typed_jsonl_writer_rejects_unvalidated_mapping(tmp_path: Path) -> None:
    with pytest.raises(ArtifactValidationError, match="must be a validated SimCheckpointResultRow"):
        write_typed_jsonl(
            tmp_path / "sim_checkpoint_results.jsonl",
            [{}],
            model_type=SimCheckpointResultRow,
        )


def test_memory_evolution_public_imports_resolve() -> None:
    modules = [
        "memorii.core.benchmark.memory_evolution_sim",
        "memorii.core.benchmark.memory_evolution_runtime",
        "memorii.tools.run_benchmark",
    ]

    for module_name in modules:
        assert importlib.import_module(module_name)


def test_memory_evolution_owned_submodule_imports_resolve() -> None:
    expected_symbols = {
        "memorii.core.benchmark.memory_evolution_sim.schemas": "SimSystemOutput",
        "memorii.core.benchmark.memory_evolution_sim.generation": "generate_memory_evolution_sim_scenarios",
        "memorii.core.benchmark.memory_evolution_sim.candidate_cards": "sim_reconstruction_context_for_checkpoint",
        "memorii.core.benchmark.memory_evolution_sim.decisions": "expected_sim_output_for_checkpoint",
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
    aggregate = judge_sim_checkpoint(scenario=scenario, checkpoint=checkpoint, output=expected)

    assert context.checkpoint.checkpoint_id == checkpoint.checkpoint_id
    assert context.checkpoint.answer_projection_policy == checkpoint.answer_projection_policy
    assert "expected_claim_ids" not in context.model_dump(mode="json")
    assert aggregate.verdict.value == "pass"
    assert aggregate.score >= 0.99


def test_memory_evolution_sim_checkpoint_contract_is_single_source_for_all_generated_profiles() -> None:
    scenarios = [
        *generate_memory_evolution_sim_scenarios(
            profile="adversarial",
            scenario_count=10,
            seed=7,
            noise_rate=0.35,
        ),
        *generate_memory_evolution_sim_scenarios(
            profile="long_horizon",
            scenario_count=10,
            seed=7,
            noise_rate=0.35,
        ),
    ]

    for scenario in scenarios:
        for checkpoint in scenario.checkpoints:
            context = sim_reconstruction_context_for_checkpoint(
                scenario=scenario,
                checkpoint=checkpoint,
            )
            contract = checkpoint.checkpoint_contract.model_dump(mode="json")

            assert context.checkpoint.answer_projection_policy == contract["answer_projection_policy"]
            rendered_context = context.model_dump(mode="json")
            assert "allowed_operations" not in rendered_context
            assert "required_judge_ids" not in rendered_context


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
        checkpoint_rows=[_runtime_checkpoint_row(runtime_action_alignments=[])],
        judge_rows=[],
        llm_rows=[
            RuntimeExtractorTraceRow(
                scenario_id="scenario:test",
                transition_type="runtime_memory_extraction",
                decision_mode="llm",
                effective_decision_mode="llm",
                final_output_source="fake_oracle",
                trace=RuntimeExtractorTracePayload(
                    provider="fake_oracle",
                    scenario_id="scenario:test",
                    call_index=0,
                    entity_count=0,
                    claim_count=0,
                    action_count=0,
                ),
                success=True,
                fallback_used=False,
                output=RuntimeExtractorOutput(),
            )
        ],
        alignments=[],
        dry_run=True,
    )

    metrics = runtime_summary_metrics(rows)
    alignment_summary = runtime_alignment_summary(rows)

    assert metrics.provider_successes == 0
    assert metrics.provider_failures == 0
    assert metrics.fallbacks == 0
    assert metrics.final_output_source_counts == {"fake_oracle": 1}
    assert alignment_summary.checkpoint_expected_alignment_audit_count == 0
    assert alignment_summary.checkpoint_scored_verdict_counts == {"pass": 1}
    assert "checkpoint_required_alignment_count" not in type(alignment_summary).model_fields

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
    assert canonical_summary.checkpoint_expected_alignment_audit_count == 1
    assert canonical_summary.checkpoint_expected_alignment_audit_counts == {"aligned": 1}


@pytest.mark.parametrize(
    ("field_name", "invalid_row", "expected_type"),
    [
        ("scenario_rows", {}, "SimScenarioResultRow"),
        ("judge_rows", {}, "JudgeAggregate"),
        ("llm_rows", {}, "RuntimeExtractorTraceRow"),
        ("graph_snapshots", {}, "RuntimeGraphSnapshotRow"),
        ("graph_items", {}, "Runtime.*GraphItemRow"),
        ("alignments", {}, "RuntimeGraphAlignmentRow"),
        ("runtime_failures", {}, "RuntimeCheckpointResultRow"),
    ],
)
def test_runtime_suite_rows_reject_untyped_artifact_rows(
    field_name: str,
    invalid_row: dict[str, object],
    expected_type: str,
) -> None:
    kwargs: dict[str, object] = {
        "scenario_rows": [],
        "checkpoint_rows": [],
        "judge_rows": [],
        "llm_rows": [],
    }
    kwargs[field_name] = [invalid_row]

    with pytest.raises(TypeError, match=expected_type):
        RuntimeSuiteRows(**kwargs)


def test_runtime_extractor_trace_cannot_masquerade_fallback_as_success() -> None:
    with pytest.raises(ValidationError, match="cannot report fallback"):
        RuntimeExtractorTraceRow(
            scenario_id="scenario:test",
            transition_type="runtime_memory_extraction",
            decision_mode="llm",
            effective_decision_mode="llm",
            final_output_source="rule",
            trace=RuntimeExtractorTracePayload(
                provider="provider",
                scenario_id="scenario:test",
                call_index=0,
                entity_count=0,
                claim_count=0,
                action_count=0,
            ),
            success=True,
            fallback_used=True,
            output=RuntimeExtractorOutput(),
        )


def test_memory_evolution_sim_dry_run_artifact_public_shape(tmp_path: Path) -> None:
    assert (
        main(
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
        )
        == 0
    )

    run_dir = _latest_run_dir(tmp_path, "memory_evolution_sim_v1", "llm")
    report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    checkpoint_rows = _jsonl_rows(run_dir / "sim_checkpoint_results.jsonl")

    assert report["suite"] == "memory_evolution_sim_v1"
    assert report["passed"] == 10
    assert report["failed"] == 0
    assert report["final_output_source_counts"] == {"fake_oracle": report["checkpoint_count"]}
    assert "runtime_failure_buckets" not in report["checkpoint_results"][0]
    assert (run_dir / "calibration_report.json").exists()
    assert (run_dir / "decision_quality_report.json").exists()
    assert checkpoint_rows
    for row in checkpoint_rows:
        assert row["passed"] is not None
        assert row["verdict"] in {"pass", "fail", "abstain"}
        assert row["score"] is not None
        assert row["review_required"] is not None


def test_memory_evolution_runtime_dry_run_artifact_public_shape(tmp_path: Path) -> None:
    assert (
        main(
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
        )
        == 0
    )

    run_dir = _latest_run_dir(tmp_path, "memory_evolution_runtime_v1", "llm")
    report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    runtime_rows = _jsonl_rows(run_dir / "runtime_checkpoint_results.jsonl")
    alignment_summary = json.loads((run_dir / "runtime_graph_alignments_summary.json").read_text(encoding="utf-8"))

    assert report["suite"] == "memory_evolution_runtime_v1"
    assert report["passed"] + report["failed"] == report["scenario_count"]
    assert report["final_output_source_counts"] == {"fake_oracle": report["checkpoint_count"]}
    assert "runtime_failure_buckets" in report["checkpoint_results"][0]
    assert (run_dir / "calibration_report.json").exists()
    assert (run_dir / "decision_quality_report.json").exists()
    assert sum(alignment_summary["checkpoint_scored_verdict_counts"].values()) == report["checkpoint_count"]
    assert alignment_summary["checkpoint_scored_review_required_count"] >= 0
    assert "checkpoint_required_alignment_count" not in alignment_summary
    assert runtime_rows
    for row in runtime_rows:
        assert row["passed"] is not None
        assert row["verdict"] in {"pass", "fail", "abstain"}
        assert row["score"] is not None
        assert row["review_required"] is not None
        assert "runtime_failure_buckets" in row
        assert "runtime_failure_classification" in row
