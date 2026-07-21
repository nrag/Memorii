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
    assert report["passed"] + report["failed"] == report["scenario_count"]
    assert int(fields["passed"]) == report["passed"]
    assert int(fields["failed"]) == report["failed"]
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
    runtime_graph = runtime["runtime_graph_summary"]
    assert report["runtime_graph_summary"] == runtime_graph
    alignment_summary = report["runtime_graph_alignments_summary"]
    assert alignment_summary["checkpoint_expected_alignment_audit_count"] > 0
    assert "checkpoint_required_alignment_count" not in alignment_summary
    assert "checkpoint_required_alignment_counts" not in alignment_summary
    assert "checkpoint_required_alignment_counts_by_item_type" not in alignment_summary
    assert sum(alignment_summary["checkpoint_scored_verdict_counts"].values()) == report["checkpoint_count"]
    assert set(alignment_summary["checkpoint_scored_verdict_counts"]) == {"pass", "fail"}
    assert all(count >= 0 for count in alignment_summary["checkpoint_scored_verdict_counts"].values())
    assert isinstance(alignment_summary["checkpoint_scored_failure_bucket_counts"], dict)
    assert "alignment_summary_policy" in alignment_summary
    assert report["warning_policy"]["extra_provenance_noise"]["level"] == "warning_only"
    assert report["warning_policy"]["extra_context_provenance"]["level"] == "warning_only"
    assert report["warning_policy"]["graph_answer_optional_missing"]["level"] == "warning_only"
    assert report["warning_policy"]["role_channel_context_overlap"]["level"] == "warning_only"
    assert runtime["runtime_graph_item_count"] > 0
    assert runtime_graph["source_observation_count"] > 0
    assert runtime_graph["claim_count"] > 0
    assert runtime_graph["graph_edge_count"] > 0
    assert runtime_graph["evidence_edge_count"] > 0
    assert runtime_graph["active_claim_with_subject_rate"] == 1.0
    assert runtime_graph["active_claim_with_object_or_literal_rate"] == 1.0
    assert runtime_graph["active_claim_with_scope_rate"] == 1.0
    assert runtime_graph["active_claim_with_observed_in_rate"] == 1.0
    assert "runtime_graph_item_counts_by_type" in runtime_graph
    assert "graph_edge_counts_by_type" in runtime_graph
    assert report["metrics"]["runtime_graph_item_count"] == runtime["runtime_graph_item_count"]
    assert (run_dir / "runtime_graph_snapshot.json").exists()
    assert (run_dir / "runtime_graph_items.jsonl").exists()
    assert (run_dir / "runtime_graph_alignments.jsonl").exists()
    runtime_graph_rows = [
        json.loads(line)
        for line in (run_dir / "runtime_graph_items.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
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
    checkpoint_rows = [
        json.loads(line)
        for line in (run_dir / "runtime_checkpoint_results.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    scoped_row = next(row for row in checkpoint_rows if row["checkpoint_type"] == "scoped_truth")
    scoped_output = scoped_row["output"]
    surfaced_claim_ids = {
        claim_id
        for field_name in (
            "selected_claim_ids",
            "supporting_claim_ids",
            "rejected_claim_ids",
            "context_claim_ids",
        )
        for claim_id in scoped_output[field_name]
    }
    excluded_claim_ids = set(scoped_row["expected"]["expected_excluded_claim_ids"])
    assert not excluded_claim_ids.intersection(surfaced_claim_ids)
    scoped_runtime_claim = next(
        row
        for row in runtime_graph_rows
        if row["scenario_id"] == scoped_row["scenario_id"]
        and row["item_type"] == "claim"
        and row["scope"] != "global"
    )
    assert scoped_runtime_claim["scope"].startswith("task:oid_")
    assert scoped_runtime_claim["lifecycle_state"] == "active"
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
    failed_checkpoint_rows = [row for row in runtime_checkpoint_rows if row["passed"] is False]
    assert failed_checkpoint_rows
    assert all(row["runtime_failure_buckets"] for row in failed_checkpoint_rows)
    assert all(row["runtime_failure_classification"] for row in failed_checkpoint_rows)
    warning_rows = [
        json.loads(line)
        for line in (run_dir / "sim_warning_examples.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert warning_rows
    assert all(row.get("warning_buckets") for row in warning_rows)
