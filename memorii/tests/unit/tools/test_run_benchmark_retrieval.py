from __future__ import annotations

import json
from pathlib import Path

import pytest
from memorii.core.llm_config import LLMRuntimeConfig
from memorii.core.llm_provider.models import LLMStructuredRequest, LLMStructuredResponse
from memorii.tools.run_benchmark import main
from tests.unit.tools.run_benchmark_test_helpers import (
    _clear_llm_env,
    _jsonl_count,
    _latest_run_dir,
    _summary_fields,
)


def test_retrieval_corruption_benchmark_cli_runs_and_writes_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    _clear_llm_env(monkeypatch)
    assert main(["--suite", "retrieval_corruption_v1", "--storage-root", str(tmp_path)]) == 0

    output = capsys.readouterr().out
    run_dir = _latest_run_dir(tmp_path, "retrieval_corruption_v1")
    payload = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    fields = _summary_fields(output)

    assert fields["suite"] == "retrieval_corruption_v1"
    assert int(fields["scenarios"]) == payload["summary"]["scenario_fixtures_total"]
    assert int(fields["memorii_runs"]) == payload["summary"]["memorii_runs_total"]
    assert int(fields["memorii_runs_passed"]) == payload["summary"]["memorii_runs_passed"]
    assert int(fields["memorii_runs_failed"]) == payload["summary"]["memorii_runs_failed"]
    assert int(fields["llm_calls"]) == _jsonl_count(run_dir / "llm_traces.jsonl")
    assert _jsonl_count(run_dir / "retrieval_relevance_traces.jsonl") == payload["summary"]["memorii_runs_total"]

    memorii_metrics = payload["summary"]["aggregate_metrics"]["memorii"]
    assert memorii_metrics["precision_at_1"] == 1.0
    assert memorii_metrics["hard_distractor_outrank_rate"] == 0.0
    assert 0.0 < memorii_metrics["scenario_success_rate"] < 1.0


def test_retrieval_corruption_benchmark_systems_all_is_discriminatory(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    _clear_llm_env(monkeypatch)
    assert main(["--suite", "retrieval_corruption_v1", "--systems", "all", "--storage-root", str(tmp_path)]) == 0

    output = capsys.readouterr().out
    run_dir = _latest_run_dir(tmp_path, "retrieval_corruption_v1")
    payload = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    fields = _summary_fields(output)
    metrics = payload["summary"]["aggregate_metrics"]

    assert int(fields["scenarios"]) == payload["summary"]["scenario_fixtures_total"]
    assert int(fields["memorii_runs"]) == payload["summary"]["memorii_runs_total"]
    assert int(fields["baseline_runs"]) == payload["summary"]["baseline_runs_total"]
    assert int(fields["baseline_runs_passed"]) == (
        payload["summary"]["baseline_runs_total"] - payload["summary"]["baseline_runs_failed"]
    )
    assert int(fields["baseline_runs_failed"]) == payload["summary"]["baseline_runs_failed"]
    assert 0.0 < metrics["memorii"]["scenario_success_rate"] < 1.0
    assert payload["summary"]["baseline_runs_failed"] > 0
    assert payload["summary"]["baseline_runs_failed"] < payload["summary"]["baseline_runs_total"]


def test_retrieval_corruption_benchmark_dry_run_llm_makes_traced_calls(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    assert main(
        [
            "--suite",
            "retrieval_corruption_v1",
            "--mode",
            "llm",
            "--dry-run",
            "--storage-root",
            str(tmp_path),
        ]
    ) == 0

    output = capsys.readouterr().out
    run_dir = sorted((tmp_path / "benchmark_runs" / "retrieval_corruption_v1" / "llm").glob("bench-*"))[-1]
    payload = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    fields = _summary_fields(output)

    assert int(fields["llm_calls"]) == _jsonl_count(run_dir / "llm_traces.jsonl")
    assert int(fields["llm_calls"]) == _jsonl_count(run_dir / "retrieval_relevance_traces.jsonl")
    assert payload["summary"]["memorii_runs_failed"] == 0


def test_retrieval_corruption_hybrid_falls_back_to_rule_on_invalid_llm_output(
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
    monkeypatch.setenv("MEMORII_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    assert main(
        [
            "--suite",
            "retrieval_corruption_v1",
            "--mode",
            "hybrid",
            "--dry-run",
            "--storage-root",
            str(tmp_path),
        ]
    ) == 0

    run_dir = sorted((tmp_path / "benchmark_runs" / "retrieval_corruption_v1" / "hybrid").glob("bench-*"))[-1]
    rows = [
        json.loads(line)
        for line in (run_dir / "retrieval_relevance_traces.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    fallback_rows = [row for row in rows if row["fallback_used"] is True]
    failed_rows = [row for row in rows if row["retrieval_relevance_assertion_passed"] is False]
    assert len(fallback_rows) == len(rows)
    assert failed_rows
    assert {row["transition_type"] for row in failed_rows} == {"retrieval_relevance"}


