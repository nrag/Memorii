from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path

import pytest

from memorii.core.llm_config import LLMRuntimeConfig
from memorii.core.llm_provider.models import LLMStructuredRequest, LLMStructuredResponse
from memorii.tools.run_benchmark import main
from tests.unit.tools.run_benchmark_test_helpers import (
    _jsonl_count,
    _latest_run_dir,
    _summary_fields,
)

HOTPOTQA_SAMPLE_PATH = files("memorii.core.benchmark.fixture_sets").joinpath("hotpotqa_sample.json")


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
