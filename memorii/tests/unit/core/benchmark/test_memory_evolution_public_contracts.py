from __future__ import annotations

import importlib
import json
from pathlib import Path

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


def _latest_run_dir(storage_root: Path, suite: str, mode: str) -> Path:
    return sorted((storage_root / "benchmark_runs" / suite / mode).glob("bench-*"))[-1]


def _jsonl_rows(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_memory_evolution_public_imports_remain_compatible() -> None:
    modules = [
        "memorii.core.benchmark.memory_evolution_sim",
        "memorii.core.benchmark.memory_evolution_runtime",
        "memorii.tools.run_benchmark",
    ]

    for module_name in modules:
        assert importlib.import_module(module_name)


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
    rows = RuntimeSuiteRows(
        scenario_rows=[],
        checkpoint_rows=[
            {
                "passed": True,
                "verdict": "pass",
                "review_required": False,
                "failure_buckets": [],
                "runtime_failure_buckets": [],
                "runtime_failure_classification": [],
                "runtime_action_alignments": [],
                "final_output_source": "fake_oracle",
                "provider_successes": 1,
                "provider_failures": 0,
                "fallbacks": 0,
            }
        ],
        judge_rows=[],
        llm_rows=[],
        alignments=[
            {
                "checkpoint_required": True,
                "verdict": "aligned",
                "item_type": "claim",
            }
        ],
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
