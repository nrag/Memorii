from __future__ import annotations

import json
from pathlib import Path

import pytest

from memorii.core.llm_config import LLMRuntimeConfig
from memorii.core.llm_provider.models import LLMStructuredRequest, LLMStructuredResponse
from memorii.tools.run_benchmark import main

HOTPOTQA_SAMPLE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "benchmarks" / "hotpotqa_sample.json"


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

    assert payload["summary"]["scenario_fixtures_total"] == payload["summary"]["memorii_runs_total"]
    assert memorii_metrics["lifecycle_success_rate"] is not None
    assert 0.0 <= memorii_metrics["lifecycle_success_rate"] <= 1.0
    assert memorii_metrics["retrieval_currentness_accuracy"] is not None


def test_run_benchmark_rejects_unknown_suite() -> None:
    with pytest.raises(SystemExit):
        main(["--suite", "unknown"])


def test_memory_lifecycle_benchmark_is_memorii_only_for_now() -> None:
    with pytest.raises(SystemExit, match="memorii only"):
        main(["--suite", "memory_lifecycle_v1", "--systems", "all"])


def test_hotpotqa_benchmark_cli_runs_and_writes_metadata(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    assert main(
        [
            "--suite",
            "hotpotqa_v1",
            "--storage-root",
            str(tmp_path),
            "--hotpotqa-dataset",
            str(HOTPOTQA_SAMPLE_PATH),
            "--hotpotqa-subset-size",
            "2",
        ]
    ) == 0

    output = capsys.readouterr().out
    run_dir = _latest_run_dir(tmp_path, "hotpotqa_v1")
    payload = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    metadata = json.loads((run_dir / "hotpotqa_metadata.json").read_text(encoding="utf-8"))
    fields = _summary_fields(output)

    assert fields["suite"] == "hotpotqa_v1"
    assert fields["mode"] == "auto"
    assert int(fields["scenarios"]) == payload["summary"]["scenario_fixtures_total"]
    assert int(fields["memorii_runs"]) == payload["summary"]["memorii_runs_total"]
    assert int(fields["llm_calls"]) == 0
    assert metadata["dataset_path"] == str(HOTPOTQA_SAMPLE_PATH)
    assert metadata["subset_size_requested"] == 2
    assert metadata["selected_example_ids"]


def test_hotpotqa_benchmark_question_type_filter(
    tmp_path: Path,
) -> None:
    assert main(
        [
            "--suite",
            "hotpotqa_v1",
            "--storage-root",
            str(tmp_path),
            "--hotpotqa-dataset",
            str(HOTPOTQA_SAMPLE_PATH),
            "--hotpotqa-question-type",
            "bridge",
        ]
    ) == 0

    run_dir = _latest_run_dir(tmp_path, "hotpotqa_v1")
    metadata = json.loads((run_dir / "hotpotqa_metadata.json").read_text(encoding="utf-8"))
    assert metadata["question_type"] == "bridge"
    assert metadata["selected_example_ids"] == ["hp2"]


def test_hotpotqa_benchmark_rejects_llm_modes() -> None:
    with pytest.raises(SystemExit, match="deterministic modes"):
        main(["--suite", "hotpotqa_v1", "--mode", "llm"])


def test_hotpotqa_official_benchmark_dry_run_llm_writes_predictions_and_metrics(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    assert main(
        [
            "--suite",
            "hotpotqa_official_v1",
            "--mode",
            "llm",
            "--dry-run",
            "--storage-root",
            str(tmp_path),
            "--hotpotqa-dataset",
            str(HOTPOTQA_SAMPLE_PATH),
            "--hotpotqa-subset-size",
            "2",
        ]
    ) == 0

    output = capsys.readouterr().out
    run_dir = _latest_run_dir(tmp_path, "hotpotqa_official_v1", "llm")
    report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    predictions = json.loads((run_dir / "predictions.json").read_text(encoding="utf-8"))
    metrics = json.loads((run_dir / "official_metrics.json").read_text(encoding="utf-8"))
    analysis = json.loads((run_dir / "hotpotqa_error_analysis.json").read_text(encoding="utf-8"))
    stage_diagnostics = json.loads((run_dir / "hotpotqa_stage_diagnostics.json").read_text(encoding="utf-8"))
    metadata = json.loads((run_dir / "hotpotqa_metadata.json").read_text(encoding="utf-8"))
    answer_rows = [
        json.loads(line)
        for line in (run_dir / "hotpotqa_answer_traces.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    fields = _summary_fields(output)

    assert fields["suite"] == "hotpotqa_official_v1"
    assert fields["mode"] == "llm"
    assert int(fields["examples"]) == report["examples"]
    assert int(fields["llm_calls"]) == _jsonl_count(run_dir / "llm_traces.jsonl")
    assert int(fields["llm_calls"]) == report["examples"] * 3
    assert int(fields["llm_successes"]) == int(fields["llm_calls"])
    assert int(fields["llm_failures"]) == 0
    assert int(fields["fallbacks"]) == 0
    assert int(fields["provider_errors"]) == 0
    assert report["llm_successes"] == report["llm_calls"]
    assert report["llm_failures"] == 0
    assert report["llm_fallbacks"] == 0
    assert report["provider_errors"] == 0
    assert set(predictions) == {"answer", "sp"}
    assert metrics["f1"] == 1.0
    assert metrics["sp_f1"] == 1.0
    assert metrics["joint_f1"] == 1.0
    assert analysis["summary"]["examples"] == report["examples"]
    assert stage_diagnostics["summary"]["examples"] == report["examples"]
    assert metadata["benchmark_key"].startswith("bench-")
    assert metadata["run_id"].startswith(metadata["benchmark_key"])
    assert answer_rows
    assert {
        "raw_answer",
        "final_answer",
        "exported_answer",
        "scores",
        "predicted_supporting_facts",
        "proof_supporting_facts",
        "required_proof_supporting_facts",
        "role_eligible_proof_supporting_facts",
        "answer_supporting_facts",
        "verified_supporting_facts",
        "final_supporting_facts",
        "answer_format_diagnostic",
        "proof_citation_candidate_ids",
        "required_proof_citation_candidate_ids",
        "role_eligible_proof_citation_candidate_ids",
        "answer_citation_candidate_ids",
        "verified_citation_candidate_ids",
        "citation_candidate_ids",
        "evidence_selection",
        "grounded_answer",
        "answer_verification",
        "question_constraints",
        "provenance_reconciliation",
        "answer_finalization",
    }.issubset(answer_rows[0])
    assert answer_rows[0]["evidence_selection"]["proof_steps"]
    assert answer_rows[0]["evidence_selection"]["proof_steps"][0]["required_candidate_ids"]
    assert answer_rows[0]["evidence_selection"]["proof_steps"][0]["citations"]
    assert answer_rows[0]["grounded_answer"]["candidate_answers_considered"]
    assert "question" in answer_rows[0]
    assert answer_rows[0]["question_constraints"]
    assert answer_rows[0]["answer_verification"]["question_constraints"] == answer_rows[0]["question_constraints"]
    assert answer_rows[0]["provenance_reconciliation"]["final_citation_candidate_ids"] == answer_rows[0]["citation_candidate_ids"]
    assert answer_rows[0]["answer_finalization"]["final_answer"] == answer_rows[0]["exported_answer"]
    assert set(answer_rows[0]["verified_citation_candidate_ids"]).issubset(set(answer_rows[0]["citation_candidate_ids"]))
    assert answer_rows[0]["final_supporting_facts"] == answer_rows[0]["predicted_supporting_facts"]
    assert "citation_view_metrics" in stage_diagnostics["summary"]
    assert "role_eligible_proof" in stage_diagnostics["summary"]["citation_view_metrics"]
    assert predictions["answer"][answer_rows[0]["example_id"]] == answer_rows[0]["exported_answer"]
    for relative_path in [
        "predictions.json",
        "official_metrics.json",
        "hotpotqa_error_analysis.json",
        "hotpotqa_stage_diagnostics.json",
        "hotpotqa_stage_diagnostics.jsonl",
        "hotpotqa_answer_traces.jsonl",
        "hotpotqa_retrieval_traces.jsonl",
        "evidence_selection_traces.jsonl",
        "grounded_answer_traces.jsonl",
        "answer_verification_traces.jsonl",
        "hotpotqa_metadata.json",
    ]:
        assert (run_dir / relative_path).exists()


def test_hotpotqa_official_benchmark_rule_mode_has_no_llm_calls(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    assert main(
        [
            "--suite",
            "hotpotqa_official_v1",
            "--mode",
            "rule",
            "--storage-root",
            str(tmp_path),
            "--hotpotqa-dataset",
            str(HOTPOTQA_SAMPLE_PATH),
            "--hotpotqa-subset-size",
            "2",
        ]
    ) == 0

    output = capsys.readouterr().out
    run_dir = _latest_run_dir(tmp_path, "hotpotqa_official_v1", "rule")
    fields = _summary_fields(output)
    predictions = json.loads((run_dir / "predictions.json").read_text(encoding="utf-8"))

    assert int(fields["llm_calls"]) == 0
    assert _jsonl_count(run_dir / "llm_traces.jsonl") == 0
    assert set(predictions) == {"answer", "sp"}


def test_hotpotqa_official_oracle_diagnostics_are_opt_in(
    tmp_path: Path,
) -> None:
    assert main(
        [
            "--suite",
            "hotpotqa_official_v1",
            "--mode",
            "llm",
            "--dry-run",
            "--storage-root",
            str(tmp_path),
            "--hotpotqa-dataset",
            str(HOTPOTQA_SAMPLE_PATH),
            "--hotpotqa-subset-size",
            "1",
        ]
    ) == 0
    run_dir = _latest_run_dir(tmp_path, "hotpotqa_official_v1", "llm")
    assert not (run_dir / "hotpotqa_oracle_diagnostics.json").exists()

    assert main(
        [
            "--suite",
            "hotpotqa_official_v1",
            "--mode",
            "llm",
            "--dry-run",
            "--storage-root",
            str(tmp_path),
            "--hotpotqa-dataset",
            str(HOTPOTQA_SAMPLE_PATH),
            "--hotpotqa-subset-size",
            "1",
            "--hotpotqa-diagnostics",
            "oracle",
        ]
    ) == 0
    run_dir = _latest_run_dir(tmp_path, "hotpotqa_official_v1", "llm")
    diagnostics = json.loads((run_dir / "hotpotqa_oracle_diagnostics.json").read_text(encoding="utf-8"))
    predictions = json.loads((run_dir / "predictions.json").read_text(encoding="utf-8"))

    assert set(predictions) == {"answer", "sp"}
    assert "gold_evidence_to_answer" in diagnostics
    assert "llm_proof_gold_final_citations" in diagnostics
    assert "llm_proof_to_answer_without_reconciliation_loss" in diagnostics
    assert "llm_evidence_selection_only" in diagnostics
    assert (run_dir / "hotpotqa_oracle_gold_evidence_answer_traces.jsonl").exists()
    assert (run_dir / "hotpotqa_oracle_llm_traces.jsonl").exists()


def test_hotpotqa_official_run_id_includes_selected_examples(
    tmp_path: Path,
) -> None:
    assert main(
        [
            "--suite",
            "hotpotqa_official_v1",
            "--mode",
            "rule",
            "--storage-root",
            str(tmp_path),
            "--hotpotqa-dataset",
            str(HOTPOTQA_SAMPLE_PATH),
            "--hotpotqa-subset-size",
            "1",
        ]
    ) == 0
    first_run_dir = _latest_run_dir(tmp_path, "hotpotqa_official_v1", "rule")

    assert main(
        [
            "--suite",
            "hotpotqa_official_v1",
            "--mode",
            "rule",
            "--storage-root",
            str(tmp_path),
            "--hotpotqa-dataset",
            str(HOTPOTQA_SAMPLE_PATH),
            "--hotpotqa-subset-size",
            "2",
        ]
    ) == 0
    second_run_dir = _latest_run_dir(tmp_path, "hotpotqa_official_v1", "rule")

    assert first_run_dir != second_run_dir


def test_hotpotqa_official_llm_fails_traceably_on_invalid_llm_output(
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
            "hotpotqa_official_v1",
            "--mode",
            "llm",
            "--dry-run",
            "--storage-root",
            str(tmp_path),
            "--hotpotqa-dataset",
            str(HOTPOTQA_SAMPLE_PATH),
            "--hotpotqa-subset-size",
            "2",
        ]
    ) == 0

    run_dir = _latest_run_dir(tmp_path, "hotpotqa_official_v1", "llm")
    failures = [
        json.loads(line)
        for line in (run_dir / "failures.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    llm_rows = [
        json.loads(line)
        for line in (run_dir / "llm_traces.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert failures
    assert all(row["success"] is False for row in failures)
    assert all(row["fallback_used"] is True for row in llm_rows)
    report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    assert report["llm_failures"] == report["llm_calls"]
    assert report["llm_fallbacks"] == report["llm_calls"]


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
    run_dir = sorted((tmp_path / "benchmark_runs" / "memory_lifecycle_v1" / "llm").glob("bench-*"))[-1]
    fields = _summary_fields(output)
    assert int(fields["llm_calls"]) == _jsonl_count(run_dir / "llm_traces.jsonl")
    assert int(fields["lifecycle_cases"]) == _jsonl_count(run_dir / "lifecycle_traces.jsonl")


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
    assert len(fallback_rows) == len(rows)
    assert all(row["final_output_source"] == "rule" for row in fallback_rows)
    assert failed_rows
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

    monkeypatch.setattr("memorii.tools.run_benchmark.EvalFakeClient", InvalidFakeClient)
    monkeypatch.setenv("MEMORII_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    assert main(
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


def test_memory_evolution_benchmark_rejects_all_systems() -> None:
    with pytest.raises(SystemExit, match="memorii only"):
        main(["--suite", "memory_evolution_v1", "--systems", "all"])


def test_memory_evolution_sim_benchmark_cli_runs_and_writes_judge_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    _clear_llm_env(monkeypatch)

    assert main(
        [
            "--suite",
            "memory_evolution_sim_v1",
            "--storage-root",
            str(tmp_path),
            "--sim-profile",
            "smoke",
        ]
    ) == 0

    output = capsys.readouterr().out
    run_dir = _latest_run_dir(tmp_path, "memory_evolution_sim_v1")
    payload = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    fields = _summary_fields(output)

    assert fields["suite"] == "memory_evolution_sim_v1"
    assert fields["profile"] == "smoke"
    assert int(fields["scenarios"]) == payload["scenario_count"] == 10
    assert int(fields["events"]) == payload["event_count"]
    assert int(fields["checkpoints"]) == payload["checkpoint_count"]
    assert int(fields["passed"]) == payload["passed"]
    assert int(fields["failed"]) == payload["failed"]
    assert int(fields["failed"]) > 0
    assert int(fields["llm_calls"]) == _jsonl_count(run_dir / "llm_traces.jsonl")
    for relative_path in [
        "report.json",
        "report.md",
        "latent_graphs.json",
        "world_transitions.jsonl",
        "surface_observations.jsonl",
        "oracle_checkpoints.jsonl",
        "candidate_cards.jsonl",
        "judge_votes.jsonl",
        "judge_aggregate.json",
        "judge_conflicts.jsonl",
        "judge_coverage.json",
        "sim_checkpoint_results.jsonl",
        "sim_failure_buckets.json",
        "sim_warning_examples.jsonl",
        "fixtures.json",
        "llm_traces.jsonl",
        "failures.jsonl",
        "review_candidates.jsonl",
    ]:
        assert (run_dir / relative_path).exists()


def test_memory_evolution_sim_dry_run_llm_passes_and_records_calls(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    assert main(
        [
            "--suite",
            "memory_evolution_sim_v1",
            "--mode",
            "llm",
            "--dry-run",
            "--storage-root",
            str(tmp_path),
        ]
    ) == 0

    output = capsys.readouterr().out
    run_dir = _latest_run_dir(tmp_path, "memory_evolution_sim_v1", "llm")
    payload = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    fields = _summary_fields(output)

    assert int(fields["failed"]) == payload["failed"] == 0
    assert int(fields["llm_calls"]) == payload["checkpoint_count"]
    assert int(fields["llm_calls"]) == _jsonl_count(run_dir / "llm_traces.jsonl")
    assert payload["llm_calls"] == payload["checkpoint_count"]
    assert payload["provider_successes"] == payload["checkpoint_count"]
    assert payload["final_output_source_counts"] == {"fake_oracle": payload["checkpoint_count"]}
    assert "critical_failure_bucket_counts" in payload
    assert "warning_bucket_counts" in payload
    assert "review_bucket_counts" in payload
    for metric_name in [
        "graph_answer_optional_missing_count",
        "extra_context_provenance_count",
        "extra_context_provenance_rate",
        "supporting_pollution_count",
        "selected_pollution_count",
    ]:
        assert metric_name in payload["metrics"]
    assert (run_dir / "sim_warning_examples.jsonl").exists()
    assert (run_dir / "review_candidates.jsonl").read_text(encoding="utf-8") == ""
    candidate_card = json.loads((run_dir / "candidate_cards.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert not any(key.startswith("expected_") for key in candidate_card["checkpoint"])
    first_row = json.loads((run_dir / "sim_checkpoint_results.jsonl").read_text(encoding="utf-8").splitlines()[0])
    for field_name in [
        "selected_excluded_ids",
        "supporting_excluded_ids",
        "rejected_expected_ids",
        "missing_rejected_ids",
        "selected_noncurrent_claim_ids",
        "supporting_noisy_citation_event_ids",
        "context_only_noise_event_ids",
        "required_definition_claim_ids",
        "missing_definition_claim_ids",
        "missing_definition_support_claim_ids",
        "selected_graph_entity_overbreadth",
        "role_misclassification",
        "precision_failure_classification",
    ]:
        assert field_name in first_row
    first_trace = json.loads((run_dir / "llm_traces.jsonl").read_text(encoding="utf-8").splitlines()[0])
    trace_payload = first_trace["trace"]
    assert trace_payload["prompt_version"] == "memory_evolution_sim_reconstruction:v1"
    assert trace_payload["input_payload"]["provider"] == "fake"


def test_memory_evolution_sim_adversarial_artifacts_include_hidden_pressure_without_prompt_leak(
    tmp_path: Path,
) -> None:
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
            "2",
            "--sim-noise-rate",
            "0.35",
            "--seed",
            "7",
        ]
    ) == 0

    run_dir = _latest_run_dir(tmp_path, "memory_evolution_sim_v1", "llm")
    payload = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    latent = json.loads((run_dir / "latent_graphs.json").read_text(encoding="utf-8"))
    candidate_cards = (run_dir / "candidate_cards.jsonl").read_text(encoding="utf-8")
    surface_observations = (run_dir / "surface_observations.jsonl").read_text(encoding="utf-8")

    hidden_ids = {
        item["entity_id"]
        for scenario in latent
        for item in scenario["entities"]
        if item["observability"] == "hidden"
    } | {
        item["claim_id"]
        for scenario in latent
        for item in scenario["claims"]
        if item["observability"] == "hidden"
    } | {
        item["relation_id"]
        for scenario in latent
        for item in scenario["relations"]
        if item["observability"] == "hidden"
    }
    hidden_names = {
        item["canonical_name"]
        for scenario in latent
        for item in scenario["entities"]
        if item["observability"] == "hidden"
    }

    assert payload["metrics"]["hidden_item_count"] > 0
    assert payload["metrics"]["hidden_pressure_checkpoint_count"] == payload["checkpoint_count"]
    assert payload["metrics"]["hidden_hallucination_rate"] == 0.0
    assert payload["metrics"]["hidden_answer_leak_rate"] == 0.0
    assert hidden_ids
    assert "hidden_distractor_ids" not in candidate_cards
    assert not any(hidden_id in candidate_cards for hidden_id in hidden_ids)
    assert not any(hidden_name in candidate_cards for hidden_name in hidden_names)
    assert "hidden_distractor_ids" in surface_observations
    assert (run_dir / "review_candidates.jsonl").read_text(encoding="utf-8") == ""


def test_memory_evolution_sim_live_llm_uses_live_adapter_not_oracle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class StubLiveClient:
        provider_name = "stub-live"

        def complete_structured(self, request: LLMStructuredRequest, *, config: LLMRuntimeConfig) -> LLMStructuredResponse:
            del config
            output = {
                "operation": "answer",
                "entity_ids": [],
                "claim_ids": [],
                "relation_ids": [],
                "citation_event_ids": [],
                "belief_ranking_ids": [],
                "selected_entity_ids": [],
                "selected_claim_ids": [],
                "selected_relation_ids": [],
                "supporting_claim_ids": [],
                "supporting_relation_ids": [],
                "supporting_citation_event_ids": [],
                "rejected_entity_ids": [],
                "rejected_claim_ids": [],
                "rejected_relation_ids": [],
                "rejection_citation_event_ids": [],
                "context_entity_ids": [],
                "context_claim_ids": [],
                "context_relation_ids": [],
                "context_citation_event_ids": [],
                "answer": "not the oracle answer",
                "next_action": None,
                "uncertain_ids": [],
                "confidence": 0.5,
                "rationale": "valid live-shaped response, intentionally not oracle",
            }
            return LLMStructuredResponse(
                request_id=request.request_id,
                provider=self.provider_name,
                model="stub-model",
                raw_text=json.dumps(output),
                parsed_json=output,
                valid_json=True,
                schema_valid=True,
            )

    monkeypatch.setenv("MEMORII_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("MEMORII_ENABLE_LIVE_LLM_TESTS", "true")
    monkeypatch.setattr("memorii.tools.run_benchmark.LLMClientFactory.from_config", lambda config: StubLiveClient())

    assert main(
        [
            "--suite",
            "memory_evolution_sim_v1",
            "--mode",
            "llm",
            "--allow-live",
            "--storage-root",
            str(tmp_path),
            "--sim-scenario-count",
            "1",
        ]
    ) == 0

    run_dir = _latest_run_dir(tmp_path, "memory_evolution_sim_v1", "llm")
    payload = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    rows = [
        json.loads(line)
        for line in (run_dir / "sim_checkpoint_results.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    traces = [
        json.loads(line)
        for line in (run_dir / "llm_traces.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert payload["final_output_source_counts"] == {"live_llm": payload["checkpoint_count"]}
    assert payload["failed"] > 0
    assert rows[0]["output"]["answer"] == "not the oracle answer"
    assert traces[0]["trace"]["input_payload"]["provider"] == "stub-live"
    assert traces[0]["trace"]["prompt_version"] == "memory_evolution_sim_reconstruction:v1"


def test_memory_evolution_sim_hybrid_falls_back_to_rule_on_invalid_llm_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class InvalidFakeClient:
        provider_name = "fake-invalid"

    monkeypatch.setattr("memorii.tools.run_benchmark.EvalFakeClient", InvalidFakeClient)
    monkeypatch.setenv("MEMORII_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    assert main(
        [
            "--suite",
            "memory_evolution_sim_v1",
            "--mode",
            "hybrid",
            "--dry-run",
            "--storage-root",
            str(tmp_path),
        ]
    ) == 0

    run_dir = _latest_run_dir(tmp_path, "memory_evolution_sim_v1", "hybrid")
    rows = [
        json.loads(line)
        for line in (run_dir / "sim_checkpoint_results.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len([row for row in rows if row["fallback_used"] is True]) == len(rows)
    assert len([row for row in rows if row["success"] is False]) > 0


def test_memory_evolution_sim_benchmark_rejects_all_systems() -> None:
    with pytest.raises(SystemExit, match="memorii only"):
        main(["--suite", "memory_evolution_sim_v1", "--systems", "all"])
