from __future__ import annotations

import json
import shutil
from pathlib import Path

from memorii.core.benchmark.artifact_rows import BenchmarkReportSummary
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
        "fixture_fingerprint": "fixture-test",
        "evaluation_fingerprint": "evaluation-test",
        "system_fingerprint": "system-test",
        "source_revision": "revision:test",
        "source_tree_digest": "1" * 64,
        "source_state": "clean",
        "report_content_digest": "2" * 64,
        "artifact_manifest_digest": "3" * 64,
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
        "fixture_fingerprint": "fixture-test",
        "evaluation_fingerprint": "evaluation-test",
        "system_fingerprint": "system-test",
        "source_revision": "revision:test",
        "source_tree_digest": "1" * 64,
        "source_state": "clean",
        "report_content_digest": "2" * 64,
        "artifact_manifest_digest": "3" * 64,
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


def test_validate_reports_rejects_tampered_report_bytes(tmp_path: Path) -> None:
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
    report_path = next(tmp_path.glob("benchmark_runs/memory_evolution_sim_v1/llm/bench-*/report.json"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["checkpoint_results"][0]["verdict"] = "fail"
    report["checkpoint_results"][0]["passed"] = False
    report["checkpoint_results"][0]["success"] = False
    report["checkpoint_results"][0]["review_required"] = True
    report["checkpoint_results"][0]["score"] = 0.0
    report_path.write_text(json.dumps(report), encoding="utf-8")

    errors = validate_reports(tmp_path / "benchmark_runs")

    assert errors
    assert "report content digest does not match report.json" in errors[0]


def test_validate_reports_reconciles_report_checkpoint_verdicts(tmp_path: Path) -> None:
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
    report_path = next(tmp_path.glob("benchmark_runs/memory_evolution_sim_v1/llm/bench-*/report.json"))
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    payload["checkpoint_results"][0]["verdict"] = "fail"
    payload["checkpoint_results"][0]["passed"] = False
    payload["checkpoint_results"][0]["success"] = False
    payload["checkpoint_results"][0]["review_required"] = True
    payload["checkpoint_results"][0]["score"] = 0.0
    report = BenchmarkReportSummary.model_validate(payload).with_content_digest()
    report_path.write_text(json.dumps(report.model_dump(mode="json")), encoding="utf-8")

    errors = validate_reports(tmp_path / "benchmark_runs")

    assert errors
    assert "disagrees with checkpoint artifact verdict fields" in errors[0]


def test_validate_reports_enforces_exact_byte_manifest_coverage(tmp_path: Path) -> None:
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
    source_root = tmp_path / "benchmark_runs"

    tampered_root = tmp_path / "tampered-bytes"
    shutil.copytree(source_root, tampered_root)
    checkpoint_path = next(tampered_root.glob("memory_evolution_sim_v1/llm/bench-*/sim_checkpoint_results.jsonl"))
    checkpoint_path.write_bytes(checkpoint_path.read_bytes() + b"\n")
    errors = validate_reports(tampered_root)
    assert errors
    assert "manifest entry does not match persisted bytes" in errors[0]

    missing_root = tmp_path / "missing-artifact"
    shutil.copytree(source_root, missing_root)
    next(missing_root.glob("memory_evolution_sim_v1/llm/bench-*/sim_checkpoint_results.jsonl")).unlink()
    errors = validate_reports(missing_root)
    assert errors
    assert "manifest does not exactly cover the run directory" in errors[0]

    injected_root = tmp_path / "injected-artifact"
    shutil.copytree(source_root, injected_root)
    run_dir = next(injected_root.glob("memory_evolution_sim_v1/llm/bench-*"))
    (run_dir / "unexpected.json").write_text("{}", encoding="utf-8")
    errors = validate_reports(injected_root)
    assert errors
    assert "manifest does not exactly cover the run directory" in errors[0]
