from __future__ import annotations

import json
from pathlib import Path

import pytest
from memorii.core.llm_config import LLMRuntimeConfig
from memorii.core.llm_provider.base import LLMProviderError
from memorii.core.llm_provider.models import LLMStructuredRequest, LLMStructuredResponse
from memorii.tools.benchmark_suites.memory_evolution import memory_evolution_artifact_run_metadata
from memorii.tools.run_benchmark import main
from tests.unit.tools.run_benchmark_test_helpers import (
    _application_with_fake_client,
    _clear_llm_env,
    _jsonl_count,
    _latest_run_dir,
    _summary_fields,
)


def test_memory_evolution_benchmark_cli_runs_and_writes_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    _clear_llm_env(monkeypatch)

    assert main(["--suite", "memory_evolution_v1", "--storage-root", str(tmp_path)]) == 0

    output = capsys.readouterr().out
    run_dir = _latest_run_dir(tmp_path, "memory_evolution_v1")
    payload = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    fields = _summary_fields(output)

    assert fields["suite"] == "memory_evolution_v1"
    assert int(fields["scenarios"]) == payload["scenarios"] == 10
    assert int(fields["checkpoints"]) == payload["checkpoints"]
    assert int(fields["passed"]) == payload["passed"]
    assert int(fields["failed"]) == payload["failed"]
    assert int(fields["failed"]) >= 5
    assert int(fields["llm_calls"]) == _jsonl_count(run_dir / "llm_traces.jsonl")
    for relative_path in [
        "report.json",
        "report.md",
        "memory_evolution_report.json",
        "memory_evolution_report.md",
        "fixtures.json",
        "memory_evolution_traces.jsonl",
        "memory_evolution_checkpoint_traces.jsonl",
        "llm_traces.jsonl",
        "failures.jsonl",
    ]:
        assert (run_dir / relative_path).exists()


def test_memory_evolution_benchmark_dry_run_llm_passes_all_cases(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    assert main(
        [
            "--suite",
            "memory_evolution_v1",
            "--mode",
            "llm",
            "--dry-run",
            "--storage-root",
            str(tmp_path),
        ]
    ) == 0

    output = capsys.readouterr().out
    run_dir = _latest_run_dir(tmp_path, "memory_evolution_v1", "llm")
    payload = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    fields = _summary_fields(output)

    assert int(fields["failed"]) == payload["failed"] == 0
    assert int(fields["llm_calls"]) == payload["checkpoints"]
    assert int(fields["llm_calls"]) == _jsonl_count(run_dir / "llm_traces.jsonl")
    assert payload["run_id"] == payload["benchmark_key"]
    assert payload["dry_run"] is True
    assert payload["live_run"] is False
    assert payload["artifact_version"] == "memory_evolution_v1_artifacts:2"
    for report_field in [
        "failure_bucket_counts",
        "warning_bucket_counts",
        "answer_failure_counts",
        "temporal_frame_failure_counts",
        "temporal_frame_warning_counts",
        "scope_canonicalization_failure_counts",
        "belief_lifecycle_failure_counts",
        "lifecycle_snapshot_failure_counts",
        "channel_hygiene_failure_counts",
        "discriminative_scenarios",
        "non_discriminative_scenarios",
        "discriminative_passed",
        "discriminative_failed",
        "non_discriminative_passed",
        "non_discriminative_failed",
        "lifecycle_expectation_scope_counts",
    ]:
        assert report_field in payload
    assert payload["discriminative_scenarios"] + payload["non_discriminative_scenarios"] == payload["scenarios"]
    assert payload["discriminative_passed"] + payload["discriminative_failed"] == payload["discriminative_scenarios"]
    assert payload["non_discriminative_passed"] + payload["non_discriminative_failed"] == payload["non_discriminative_scenarios"]
    checkpoint_rows = [
        json.loads(line)
        for line in (run_dir / "memory_evolution_checkpoint_traces.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert all("diagnostics" in row for row in checkpoint_rows)
    assert all("failure_buckets" in row for row in checkpoint_rows)
    assert all("warning_buckets" in row for row in checkpoint_rows)


def test_memory_evolution_live_artifact_run_id_uses_resolved_effective_mode() -> None:
    scenario_rows = [
        {
            "scenario_id": "scenario",
            "decision_mode": "auto",
            "effective_decision_mode": "llm",
            "success": True,
        }
    ]
    checkpoint_rows = [
        {
            "checkpoint_id": "checkpoint",
            "decision_mode": "auto",
            "effective_decision_mode": "llm",
            "success": True,
        }
    ]

    metadata = memory_evolution_artifact_run_metadata(
        suite="memory_evolution_v1",
        mode="auto",
        scenario_rows=scenario_rows,
        checkpoint_rows=checkpoint_rows,
        dry_run=False,
        allow_live=True,
    )

    assert metadata["effective_decision_modes"] == ["llm"]
    assert metadata["live_run"] is True
    assert metadata["dry_run"] is False
    assert str(metadata["run_id"]).startswith(str(metadata["benchmark_key"]) + "-")


def test_memory_evolution_hybrid_falls_back_to_rule_on_invalid_llm_output(
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

    app = _application_with_fake_client(InvalidFakeClient)
    monkeypatch.setenv("MEMORII_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    assert app.run(
        [
            "--suite",
            "memory_evolution_v1",
            "--mode",
            "hybrid",
            "--dry-run",
            "--storage-root",
            str(tmp_path),
        ]
    ) == 0

    run_dir = _latest_run_dir(tmp_path, "memory_evolution_v1", "hybrid")
    rows = [
        json.loads(line)
        for line in (run_dir / "memory_evolution_checkpoint_traces.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len([row for row in rows if row["fallback_used"] is True]) == len(rows)
    assert len([row for row in rows if row["success"] is False]) >= 5


def test_memory_evolution_llm_provider_error_is_not_reported_as_llm_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class ProviderErrorFakeClient:
        provider_name = "fake-provider-error"

        def complete_structured(
            self,
            request: LLMStructuredRequest,
            *,
            config: LLMRuntimeConfig,
        ) -> LLMStructuredResponse:
            del request, config
            raise LLMProviderError("synthetic provider failure")

    app = _application_with_fake_client(ProviderErrorFakeClient)
    monkeypatch.setenv("MEMORII_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    assert app.run(
        [
            "--suite",
            "memory_evolution_v1",
            "--mode",
            "llm",
            "--dry-run",
            "--storage-root",
            str(tmp_path),
        ]
    ) == 0

    run_dir = _latest_run_dir(tmp_path, "memory_evolution_v1", "llm")
    rows = [
        json.loads(line)
        for line in (run_dir / "memory_evolution_checkpoint_traces.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert rows
    assert all(row["fallback_used"] is True for row in rows)
    assert all(row["fallback_reason"] == "provider_error" for row in rows)
    assert all(row["final_output_source"] == "rule" for row in rows)


def test_memory_evolution_llm_programming_error_propagates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class BrokenClient:
        provider_name = "broken-client"

        def complete_structured(
            self,
            request: LLMStructuredRequest,
            *,
            config: LLMRuntimeConfig,
        ) -> LLMStructuredResponse:
            del request, config
            raise RuntimeError("programming defect")

    app = _application_with_fake_client(BrokenClient)
    monkeypatch.setenv("MEMORII_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    with pytest.raises(RuntimeError, match="programming defect"):
        app.run(
            [
                "--suite",
                "memory_evolution_v1",
                "--mode",
                "llm",
                "--dry-run",
                "--storage-root",
                str(tmp_path),
            ]
        )


def test_memory_evolution_benchmark_rejects_all_systems() -> None:
    with pytest.raises(SystemExit, match="memorii only"):
        main(["--suite", "memory_evolution_v1", "--systems", "all"])
