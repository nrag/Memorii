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


def test_execution_graph_benchmark_cli_runs_and_writes_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    _clear_llm_env(monkeypatch)

    assert main(["--suite", "execution_graph_v1", "--storage-root", str(tmp_path)]) == 0

    output = capsys.readouterr().out
    run_dir = _latest_run_dir(tmp_path, "execution_graph_v1")
    payload = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    fields = _summary_fields(output)

    assert fields["suite"] == "execution_graph_v1"
    assert int(fields["execution_cases"]) == len(payload["scenario_results"])
    assert int(fields["passed"]) == payload["passed"]
    assert int(fields["failed"]) == payload["failed"]
    assert int(fields["failed"]) > 0
    assert int(fields["llm_calls"]) == _jsonl_count(run_dir / "llm_traces.jsonl")
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
    run_dir = _latest_run_dir(tmp_path, "execution_graph_v1", "llm")
    payload = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    fields = _summary_fields(output)

    assert int(fields["execution_cases"]) == len(payload["scenario_results"])
    assert int(fields["failed"]) == payload["failed"] == 0
    assert int(fields["llm_calls"]) == _jsonl_count(run_dir / "llm_traces.jsonl")


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
    assert len([row for row in rows if row["fallback_used"] is True]) == len(rows)
    assert len([row for row in rows if row["success"] is False]) > 0


def test_execution_graph_benchmark_rejects_all_systems() -> None:
    with pytest.raises(SystemExit, match="memorii only"):
        main(["--suite", "execution_graph_v1", "--systems", "all"])


