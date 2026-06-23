from __future__ import annotations

import json
from pathlib import Path

import pytest

from memorii.core.llm_config import LLMRuntimeConfig
from memorii.core.llm_provider.models import LLMStructuredRequest, LLMStructuredResponse
from memorii.tools.run_benchmark import main


def _clear_llm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in [
        "MEMORII_LLM_PROVIDER",
        "MEMORII_LLM_MODEL",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "MEMORII_DECISION_MODE",
    ]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("MEMORII_LLM_PROVIDER", "none")


def _latest_run_dir(storage_root: Path, suite: str, mode: str = "auto") -> Path:
    return sorted((storage_root / "benchmark_runs" / suite / mode).glob("bench-*"))[-1]


def test_memory_lifecycle_benchmark_cli_runs_and_writes_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    _clear_llm_env(monkeypatch)
    assert main(["--suite", "memory_lifecycle_v1", "--storage-root", str(tmp_path)]) == 0

    output = capsys.readouterr().out
    assert "suite=memory_lifecycle_v1" in output
    assert "mode=auto" in output
    assert "scenarios=11" in output
    assert "memorii_runs=11" in output
    assert "lifecycle_cases=11" in output
    assert "lifecycle_failed=0" in output
    assert "llm_calls=0" in output

    run_dir = _latest_run_dir(tmp_path, "memory_lifecycle_v1")
    for relative_path in [
        "report.json",
        "report.md",
        "baseline.json",
        "fixtures.json",
        "lifecycle_traces.jsonl",
        "llm_traces.jsonl",
        "failures.jsonl",
    ]:
        assert (run_dir / relative_path).exists()


def test_memory_lifecycle_benchmark_report_contains_lifecycle_metrics(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _clear_llm_env(monkeypatch)
    main(["--suite", "memory_lifecycle_v1", "--storage-root", str(tmp_path)])

    run_dir = _latest_run_dir(tmp_path, "memory_lifecycle_v1")
    payload = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    memorii_metrics = payload["summary"]["aggregate_metrics"]["memorii"]

    assert payload["summary"]["scenario_fixtures_total"] == 11
    assert memorii_metrics["lifecycle_success_rate"] == 1.0
    assert memorii_metrics["retrieval_currentness_accuracy"] == 1.0


def test_run_benchmark_rejects_unknown_suite() -> None:
    with pytest.raises(SystemExit):
        main(["--suite", "unknown"])


def test_memory_lifecycle_benchmark_is_memorii_only_for_now() -> None:
    with pytest.raises(SystemExit, match="memorii only"):
        main(["--suite", "memory_lifecycle_v1", "--systems", "all"])


def test_retrieval_corruption_benchmark_cli_runs_and_writes_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    _clear_llm_env(monkeypatch)
    assert main(["--suite", "retrieval_corruption_v1", "--storage-root", str(tmp_path)]) == 0

    output = capsys.readouterr().out
    assert "suite=retrieval_corruption_v1" in output
    assert "scenarios=10" in output
    assert "memorii_runs=10" in output
    assert "memorii_runs_passed=10" in output
    assert "llm_calls=0" in output

    run_dir = _latest_run_dir(tmp_path, "retrieval_corruption_v1")
    payload = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    memorii_metrics = payload["summary"]["aggregate_metrics"]["memorii"]
    assert memorii_metrics["precision_at_1"] == 1.0
    assert memorii_metrics["hard_distractor_outrank_rate"] == 0.0


def test_retrieval_corruption_benchmark_systems_all_is_discriminatory(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    _clear_llm_env(monkeypatch)
    assert main(["--suite", "retrieval_corruption_v1", "--systems", "all", "--storage-root", str(tmp_path)]) == 0

    output = capsys.readouterr().out
    assert "scenarios=10" in output
    assert "memorii_runs=10" in output
    assert "baseline_runs=30" in output
    assert "baseline_runs_passed=13" in output
    assert "baseline_runs_failed=17" in output

    run_dir = _latest_run_dir(tmp_path, "retrieval_corruption_v1")
    payload = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    metrics = payload["summary"]["aggregate_metrics"]

    assert metrics["memorii"]["scenario_success_rate"] == 1.0
    assert metrics["flat_retrieval_baseline"]["scenario_success_rate"] == 0.5
    assert metrics["no_solver_graph_baseline"]["scenario_success_rate"] == 0.8
    assert metrics["transcript_only_baseline"]["scenario_success_rate"] == 0.0
    assert payload["summary"]["baseline_runs_failed"] == 17


def test_memory_lifecycle_benchmark_dry_run_llm_makes_traced_calls(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    assert main(
        [
            "--suite",
            "memory_lifecycle_v1",
            "--mode",
            "llm",
            "--dry-run",
            "--storage-root",
            str(tmp_path),
        ]
    ) == 0

    output = capsys.readouterr().out
    assert "mode=llm" in output
    assert "llm_calls=11" in output
    run_dir = sorted((tmp_path / "benchmark_runs" / "memory_lifecycle_v1" / "llm").glob("bench-*"))[-1]
    assert len((run_dir / "llm_traces.jsonl").read_text(encoding="utf-8").splitlines()) == 11
    assert len((run_dir / "lifecycle_traces.jsonl").read_text(encoding="utf-8").splitlines()) == 11


def test_memory_lifecycle_hybrid_falls_back_to_rule_on_invalid_llm_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class InvalidFakeClient:
        provider_name = "fake-invalid"

        def complete_structured(
            self,
            request: LLMStructuredRequest,
            *,
            config: LLMRuntimeConfig,
        ) -> LLMStructuredResponse:
            del config
            return LLMStructuredResponse(
                request_id=request.request_id,
                provider=self.provider_name,
                raw_text="{}",
                valid_json=False,
                schema_valid=False,
            )

    monkeypatch.setattr("memorii.tools.run_benchmark.EvalFakeClient", InvalidFakeClient)

    assert main(
        [
            "--suite",
            "memory_lifecycle_v1",
            "--mode",
            "hybrid",
            "--dry-run",
            "--storage-root",
            str(tmp_path),
        ]
    ) == 0

    run_dir = sorted((tmp_path / "benchmark_runs" / "memory_lifecycle_v1" / "hybrid").glob("bench-*"))[-1]
    rows = [
        json.loads(line)
        for line in (run_dir / "lifecycle_traces.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert rows
    assert all(row["fallback_used"] is True for row in rows)
    assert all(row["final_output_source"] == "rule" for row in rows)
    assert all(row["transition_assertion_passed"] is True for row in rows)


def test_memory_lifecycle_llm_fails_on_invalid_llm_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class InvalidFakeClient:
        provider_name = "fake-invalid"

        def complete_structured(
            self,
            request: LLMStructuredRequest,
            *,
            config: LLMRuntimeConfig,
        ) -> LLMStructuredResponse:
            del config
            return LLMStructuredResponse(
                request_id=request.request_id,
                provider=self.provider_name,
                raw_text="{}",
                valid_json=False,
                schema_valid=False,
            )

    monkeypatch.setattr("memorii.tools.run_benchmark.EvalFakeClient", InvalidFakeClient)

    main(
        [
            "--suite",
            "memory_lifecycle_v1",
            "--mode",
            "llm",
            "--dry-run",
            "--storage-root",
            str(tmp_path),
        ]
    )

    run_dir = sorted((tmp_path / "benchmark_runs" / "memory_lifecycle_v1" / "llm").glob("bench-*"))[-1]
    failures = [
        json.loads(line)
        for line in (run_dir / "failures.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert failures
    assert all(row["success"] is False for row in failures)


def test_memory_lifecycle_benchmark_auto_uses_hybrid_when_llm_configured(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MEMORII_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    assert main(["--suite", "memory_lifecycle_v1", "--dry-run", "--storage-root", str(tmp_path)]) == 0

    output = capsys.readouterr().out
    assert "mode=auto" in output
    assert "llm_calls=11" in output
    run_dir = _latest_run_dir(tmp_path, "memory_lifecycle_v1")
    row = json.loads((run_dir / "lifecycle_traces.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert row["effective_decision_mode"] == "hybrid"
    assert row["final_output_source"] == "llm"


def test_memory_lifecycle_benchmark_llm_requires_live_gate() -> None:
    with pytest.raises(SystemExit, match="Refusing"):
        main(["--suite", "memory_lifecycle_v1", "--mode", "llm"])
