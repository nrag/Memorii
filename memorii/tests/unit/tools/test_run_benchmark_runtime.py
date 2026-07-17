from __future__ import annotations

import json
from pathlib import Path

import pytest
from memorii.tools.run_benchmark import main
from tests.unit.tools.run_benchmark_test_helpers import (
    _jsonl_count,
    _latest_run_dir,
    _summary_fields,
)


def test_memory_evolution_runtime_benchmark_dry_run_writes_runtime_artifacts(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
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
            "adversarial",
            "--sim-scenario-count",
            "10",
            "--sim-noise-rate",
            "0.35",
            "--seed",
            "7",
        ]
    ) == 0

    output = capsys.readouterr().out
    run_dir = _latest_run_dir(tmp_path, "memory_evolution_runtime_v1", "llm")
    report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    fields = _summary_fields(output)

    assert fields["suite"] == "memory_evolution_runtime_v1"
    assert fields["mode"] == "llm"
    assert int(fields["scenarios"]) == report["scenario_count"] == 10
    assert int(fields["checkpoints"]) == report["checkpoint_count"]
    assert report["passed"] == 10
    assert report["failed"] == 0
    assert report["final_output_source_counts"] == {"fake_oracle": report["checkpoint_count"]}
    assert report["runtime_provider_health"]["status"] == "not_applicable"
    assert report["runtime_provider_health"]["clean_runtime_gate"] is True
    assert report["runtime_provider_health"]["provider_success_rate"] is None
    assert report["runtime_provider_health"]["provider_successes"] == 0
    assert report["runtime_provider_health"]["fake_extractor_calls"] == report["checkpoint_count"]
    assert report["runtime_provider_health"]["execution_source"] == "fake_oracle"
    assert report["validation_scenario_catalog"]
    assert (run_dir / "validation_scenario_catalog.json").exists()
    runtime = report["runtime"]
    assert report["runtime_graph_summary"]["graph_edge_count"] == runtime["graph_edge_count"]
    alignment_summary = report["runtime_graph_alignments_summary"]
    assert alignment_summary["checkpoint_expected_alignment_audit_count"] > 0
    assert "checkpoint_required_alignment_count" not in alignment_summary
    assert "checkpoint_required_alignment_counts" not in alignment_summary
    assert "checkpoint_required_alignment_counts_by_item_type" not in alignment_summary
    assert alignment_summary["checkpoint_scored_verdict_counts"] == {"pass": report["checkpoint_count"]}
    assert alignment_summary["checkpoint_scored_review_required_count"] == 0
    assert alignment_summary["checkpoint_scored_failure_bucket_counts"] == {}
    assert "alignment_summary_policy" in alignment_summary
    assert report["warning_policy"]["extra_provenance_noise"]["level"] == "warning_only"
    assert report["warning_policy"]["extra_context_provenance"]["level"] == "warning_only"
    assert report["warning_policy"]["graph_answer_optional_missing"]["level"] == "warning_only"
    assert runtime["runtime_graph_item_count"] > 0
    assert runtime["source_observation_count"] > 0
    assert runtime["claim_count"] > 0
    assert runtime["graph_edge_count"] > 0
    assert runtime["evidence_edge_count"] > 0
    assert runtime["active_claim_with_subject_rate"] == 1.0
    assert runtime["active_claim_with_object_or_literal_rate"] == 1.0
    assert runtime["active_claim_with_scope_rate"] == 1.0
    assert runtime["active_claim_with_observed_in_rate"] == 1.0
    assert "runtime_graph_item_counts_by_type" in runtime
    assert "graph_edge_counts_by_type" in runtime
    assert report["metrics"]["runtime_graph_item_count"] == runtime["runtime_graph_item_count"]
    assert (run_dir / "runtime_graph_snapshot.json").exists()
    assert (run_dir / "runtime_graph_items.jsonl").exists()
    assert (run_dir / "runtime_graph_alignments.jsonl").exists()
    runtime_alignment_rows = [
        json.loads(line)
        for line in (run_dir / "runtime_graph_alignments.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert runtime_alignment_rows
    for row in runtime_alignment_rows:
        for field_name in ["scenario_id", "checkpoint_id", "item_type", "verdict", "score"]:
            assert row.get(field_name) is not None
    assert (run_dir / "runtime_checkpoint_results.jsonl").exists()
    assert _jsonl_count(run_dir / "runtime_checkpoint_results.jsonl") == report["checkpoint_count"]
    assert (run_dir / "runtime_graph_alignments_summary.json").exists()
    alignment_summary_artifact = json.loads((run_dir / "runtime_graph_alignments_summary.json").read_text(encoding="utf-8"))
    assert alignment_summary_artifact == alignment_summary
    runtime_checkpoint_rows = [
        json.loads(line)
        for line in (run_dir / "runtime_checkpoint_results.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    sim_checkpoint_rows = [
        json.loads(line)
        for line in (run_dir / "sim_checkpoint_results.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    for row in [*runtime_checkpoint_rows, *sim_checkpoint_rows]:
        assert row["passed"] is not None
        assert row["verdict"] in {"pass", "fail", "abstain"}
        assert row["score"] is not None
        assert row["review_required"] is not None
        for field_name in [
            "scenario_id",
            "checkpoint_id",
            "checkpoint_type",
            "success",
            "failure_buckets",
            "warning_buckets",
            "diagnostics",
            "output",
        ]:
            assert row.get(field_name) is not None
    for row in runtime_checkpoint_rows:
        for field_name in [
            "runtime_failure_buckets",
            "runtime_failure_classification",
            "final_output_source",
            "scenario_provider_successes",
            "scenario_provider_failures",
            "scenario_fallbacks",
            "provider_count_scope",
            "provider_successes",
            "provider_failures",
            "fallbacks",
        ]:
            assert row.get(field_name) is not None
        assert row["provider_count_scope"] == "scenario_extractor_calls"
    warning_rows = [
        json.loads(line)
        for line in (run_dir / "sim_warning_examples.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert warning_rows
    assert all(row.get("warning_buckets") for row in warning_rows)
