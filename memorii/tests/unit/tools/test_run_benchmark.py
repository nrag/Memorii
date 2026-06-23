from __future__ import annotations

import json
from pathlib import Path

import pytest

from memorii.core.benchmark.lifecycle_decision import lifecycle_family_requires_decision
from memorii.core.llm_config import LLMRuntimeConfig
from memorii.core.llm_provider.models import LLMStructuredRequest, LLMStructuredResponse
from memorii.tools.run_benchmark import main
from tests.fixtures.benchmarks.execution_graph_v1 import load_execution_graph_v1_fixture_set
from tests.fixtures.benchmarks.memory_lifecycle_v1 import load_memory_lifecycle_v1_fixture_set


MEMORY_LIFECYCLE_CASE_COUNT = len(load_memory_lifecycle_v1_fixture_set())
EXECUTION_GRAPH_CASE_COUNT = len(load_execution_graph_v1_fixture_set())
EXECUTION_GRAPH_DISCRIMINATIVE_CASE_COUNT = sum(
    1 for scenario in load_execution_graph_v1_fixture_set() if scenario.expectation.discriminative
)
DISCRIMINATIVE_CASE_COUNT = sum(
    1
    for fixture in load_memory_lifecycle_v1_fixture_set()
    if fixture.lifecycle is not None
    and lifecycle_family_requires_decision(fixture.lifecycle.family)
)


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


def _summary_fields(output: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for part in output.strip().split():
        if "=" not in part:
            continue
        key, value = part.split("=", maxsplit=1)
        fields[key] = value
    return fields


def _jsonl_count(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    return len(text.splitlines()) if text else 0


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
    assert f"memorii_cases={MEMORY_LIFECYCLE_CASE_COUNT}" in output
    assert f"lifecycle_cases={MEMORY_LIFECYCLE_CASE_COUNT}" in output
    assert f"lifecycle_failed={DISCRIMINATIVE_CASE_COUNT}" in output
    assert "llm_calls=0" in output

    run_dir = _latest_run_dir(tmp_path, "memory_lifecycle_v1")
    payload = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    fields = _summary_fields(output)

    assert fields["suite"] == "memory_lifecycle_v1"
    assert fields["mode"] == "auto"
    assert int(fields["scenarios"]) == payload["summary"]["scenario_fixtures_total"]
    assert int(fields["memorii_runs"]) == payload["summary"]["memorii_runs_total"]
    assert int(fields["memorii_runs_passed"]) == payload["summary"]["memorii_runs_passed"]
    assert int(fields["memorii_runs_failed"]) == payload["summary"]["memorii_runs_failed"]
    assert int(fields["lifecycle_cases"]) == _jsonl_count(run_dir / "lifecycle_traces.jsonl")
    assert int(fields["lifecycle_failed"]) == _jsonl_count(run_dir / "failures.jsonl")
    assert int(fields["llm_calls"]) == _jsonl_count(run_dir / "llm_traces.jsonl")

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

    assert payload["summary"]["scenario_fixtures_total"] == MEMORY_LIFECYCLE_CASE_COUNT
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
    run_dir = _latest_run_dir(tmp_path, "retrieval_corruption_v1")
    payload = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    fields = _summary_fields(output)

    assert fields["suite"] == "retrieval_corruption_v1"
    assert int(fields["scenarios"]) == payload["summary"]["scenario_fixtures_total"]
    assert int(fields["memorii_runs"]) == payload["summary"]["memorii_runs_total"]
    assert int(fields["memorii_runs_passed"]) == payload["summary"]["memorii_runs_passed"]
    assert int(fields["memorii_runs_failed"]) == payload["summary"]["memorii_runs_failed"]
    assert int(fields["llm_calls"]) == _jsonl_count(run_dir / "llm_traces.jsonl")

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
    assert metrics["memorii"]["scenario_success_rate"] == 1.0
    assert payload["summary"]["baseline_runs_failed"] > 0
    assert payload["summary"]["baseline_runs_failed"] < payload["summary"]["baseline_runs_total"]


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

    assert f"llm_calls={MEMORY_LIFECYCLE_CASE_COUNT}" in output
    run_dir = sorted((tmp_path / "benchmark_runs" / "memory_lifecycle_v1" / "llm").glob("bench-*"))[-1]
    assert len((run_dir / "llm_traces.jsonl").read_text(encoding="utf-8").splitlines()) == MEMORY_LIFECYCLE_CASE_COUNT
    assert len((run_dir / "lifecycle_traces.jsonl").read_text(encoding="utf-8").splitlines()) == MEMORY_LIFECYCLE_CASE_COUNT


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
    monkeypatch.setenv("MEMORII_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

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
    fallback_rows = [row for row in rows if row["fallback_used"] is True]
    failed_rows = [row for row in rows if row["transition_assertion_passed"] is False]
    assert len(fallback_rows) == MEMORY_LIFECYCLE_CASE_COUNT
    assert all(row["final_output_source"] == "rule" for row in fallback_rows)
    assert len(failed_rows) == DISCRIMINATIVE_CASE_COUNT
    assert {row["transition_type"] for row in failed_rows} == {"lifecycle_decision"}


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

    assert f"llm_calls={MEMORY_LIFECYCLE_CASE_COUNT}" in output
    run_dir = _latest_run_dir(tmp_path, "memory_lifecycle_v1")
    fields = _summary_fields(output)
    assert int(fields["llm_calls"]) == _jsonl_count(run_dir / "llm_traces.jsonl")
    row = json.loads((run_dir / "lifecycle_traces.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert row["effective_decision_mode"] == "hybrid"
    assert row["final_output_source"] == "llm"


def test_memory_lifecycle_benchmark_llm_requires_live_gate() -> None:
    with pytest.raises(SystemExit, match="Refusing"):
        main(["--suite", "memory_lifecycle_v1", "--mode", "llm"])


def test_execution_graph_benchmark_cli_runs_and_writes_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    _clear_llm_env(monkeypatch)

    assert main(["--suite", "execution_graph_v1", "--storage-root", str(tmp_path)]) == 0

    output = capsys.readouterr().out
    assert "suite=execution_graph_v1" in output
    assert f"execution_cases={EXECUTION_GRAPH_CASE_COUNT}" in output
    assert f"failed={EXECUTION_GRAPH_DISCRIMINATIVE_CASE_COUNT}" in output
    assert "llm_calls=0" in output
    run_dir = _latest_run_dir(tmp_path, "execution_graph_v1")
    for relative_path in [
        "report.json",
        "report.md",
        "baseline.json",
        "fixtures.json",
        "execution_graph_traces.jsonl",
        "llm_traces.jsonl",
        "failures.jsonl",
    ]:
        assert (run_dir / relative_path).exists()


def test_execution_graph_benchmark_dry_run_llm_passes_all_cases(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    assert main(
        [
            "--suite",
            "execution_graph_v1",
            "--mode",
            "llm",
            "--dry-run",
            "--storage-root",
            str(tmp_path),
        ]
    ) == 0

    output = capsys.readouterr().out
    assert f"execution_cases={EXECUTION_GRAPH_CASE_COUNT}" in output
    assert "failed=0" in output
    assert f"llm_calls={EXECUTION_GRAPH_CASE_COUNT}" in output
    run_dir = _latest_run_dir(tmp_path, "execution_graph_v1", "llm")
    assert len((run_dir / "llm_traces.jsonl").read_text(encoding="utf-8").splitlines()) == EXECUTION_GRAPH_CASE_COUNT


def test_execution_graph_hybrid_falls_back_to_rule_on_invalid_llm_output(
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
            "execution_graph_v1",
            "--mode",
            "hybrid",
            "--dry-run",
            "--storage-root",
            str(tmp_path),
        ]
    ) == 0

    run_dir = _latest_run_dir(tmp_path, "execution_graph_v1", "hybrid")
    rows = [
        json.loads(line)
        for line in (run_dir / "execution_graph_traces.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len([row for row in rows if row["fallback_used"] is True]) == EXECUTION_GRAPH_CASE_COUNT
    assert len([row for row in rows if row["success"] is False]) == EXECUTION_GRAPH_DISCRIMINATIVE_CASE_COUNT


def test_execution_graph_benchmark_rejects_all_systems() -> None:
    with pytest.raises(SystemExit, match="memorii only"):
        main(["--suite", "execution_graph_v1", "--systems", "all"])
