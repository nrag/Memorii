from __future__ import annotations

import json
from pathlib import Path

from memorii.tools.run_benchmark import main
from memorii.tools.validate_benchmark_artifacts import validate_reports


def test_validate_reports_rejects_fake_provider_success(tmp_path) -> None:
    report_dir = tmp_path / "memory_evolution_sim_v1" / "llm" / "run"
    report_dir.mkdir(parents=True)
    report = {
        "suite": "memory_evolution_sim_v1",
        "mode": "llm",
        "profile": "smoke",
        "seed": 7,
        "scenario_count": 1,
        "event_count": 1,
        "checkpoint_count": 1,
        "passed": 1,
        "failed": 0,
        "llm_calls": 1,
        "provider_successes": 1,
        "provider_failures": 0,
        "fallbacks": 0,
        "fake_calls": 1,
        "dry_run": True,
        "execution_source": "fake_oracle",
        "final_output_source_counts": {"fake_oracle": 1},
    }
    (report_dir / "report.json").write_text(json.dumps(report), encoding="utf-8")

    errors = validate_reports(tmp_path)

    assert errors
    assert "dry-run reports cannot contain provider successes" in errors[0]


def test_validate_reports_rejects_inconsistent_checkpoint_totals(tmp_path) -> None:
    report_dir = tmp_path / "memory_evolution_runtime_v1" / "llm" / "run"
    report_dir.mkdir(parents=True)
    report = {
        "suite": "memory_evolution_runtime_v1",
        "mode": "llm",
        "profile": "long_horizon",
        "seed": 7,
        "scenario_count": 1,
        "event_count": 1,
        "checkpoint_count": 2,
        "passed": 2,
        "failed": 1,
        "llm_calls": 2,
        "provider_successes": 0,
        "provider_failures": 0,
        "fallbacks": 0,
        "final_output_source_counts": {"fake_oracle": 2},
        "dry_run": True,
        "execution_source": "fake_oracle",
    }
    (report_dir / "report.json").write_text(json.dumps(report), encoding="utf-8")

    errors = validate_reports(tmp_path)

    assert errors
    assert "passed and failed counts must sum to scenario_count" in errors[0]


def test_validate_reports_reconciles_report_checkpoint_verdicts(tmp_path: Path) -> None:
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
    report_path = next(tmp_path.glob("benchmark_runs/memory_evolution_sim_v1/llm/bench-*/report.json"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["checkpoint_results"][0]["verdict"] = "fail"
    report["checkpoint_results"][0]["passed"] = False
    report_path.write_text(json.dumps(report), encoding="utf-8")

    errors = validate_reports(tmp_path / "benchmark_runs")

    assert errors
    assert "disagrees with checkpoint artifact verdict fields" in errors[0]
