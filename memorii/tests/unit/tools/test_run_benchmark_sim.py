from __future__ import annotations

import json
from pathlib import Path

import pytest
from memorii.tools.run_benchmark import main
from tests.unit.tools.run_benchmark_test_helpers import (
    _clear_llm_env,
    _jsonl_count,
    _latest_run_dir,
    _summary_fields,
)


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
        "calibration_events.jsonl",
        "calibration_report.json",
        "slice_calibration_report.json",
        "decision_quality_report.json",
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
            "--inference-replicate",
            "3",
            "--storage-root",
            str(tmp_path),
        ]
    ) == 0

    output = capsys.readouterr().out
    run_dir = _latest_run_dir(tmp_path, "memory_evolution_sim_v1", "llm")
    payload = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    fields = _summary_fields(output)

    assert payload["inference_replicate"] == 3
    assert payload["run_id"] == f"{payload['benchmark_key']}-rep3"
    assert int(fields["failed"]) == payload["failed"] == 0
    assert int(fields["llm_calls"]) == payload["checkpoint_count"]
    assert int(fields["llm_calls"]) == _jsonl_count(run_dir / "llm_traces.jsonl")
    assert payload["llm_calls"] == payload["checkpoint_count"]
    assert payload["provider_successes"] == 0
    assert payload["fake_calls"] == payload["checkpoint_count"]
    assert payload["final_output_source_counts"] == {"fake_oracle": payload["checkpoint_count"]}
    assert "critical_failure_bucket_counts" in payload
    assert "warning_bucket_counts" in payload
    assert payload["warning_policy"]["role_channel_context_overlap"]["level"] == "warning_only"
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
        "scenario_id",
        "checkpoint_id",
        "checkpoint_type",
        "success",
        "passed",
        "verdict",
        "score",
        "review_required",
        "failure_buckets",
        "warning_buckets",
        "diagnostics",
        "output",
    ]:
        assert first_row.get(field_name) is not None
    for field_name in [
        "selected_excluded_ids",
        "supporting_excluded_ids",
        "allowed_definition_selected_ids",
        "allowed_context_selected_ids",
        "forbidden_selected_ids",
        "rejected_expected_ids",
        "missing_rejected_ids",
        "selected_noncurrent_claim_ids",
        "supporting_noisy_citation_event_ids",
        "supporting_wrong_subject_claim_ids",
        "supporting_wrong_subject_entity_ids",
        "supporting_disambiguation_claim_ids",
        "missing_wrong_entity_rejection_claim_ids",
        "missing_wrong_entity_rejection_subject_ids",
        "supporting_role_violations",
        "supporting_rejection_provenance_overlap",
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
    assert payload["hidden_item_count"] == payload["metrics"]["hidden_item_count"]
    assert payload["hidden_hallucination_rate"] == payload["metrics"]["hidden_hallucination_rate"]
    assert payload["hidden_answer_leak_rate"] == payload["metrics"]["hidden_answer_leak_rate"]
    assert hidden_ids
    assert "hidden_distractor_ids" not in candidate_cards
    assert not any(hidden_id in candidate_cards for hidden_id in hidden_ids)
    assert not any(hidden_name in candidate_cards for hidden_name in hidden_names)
    assert "hidden_distractor_ids" in surface_observations
    assert (run_dir / "review_candidates.jsonl").read_text(encoding="utf-8") == ""


def test_memory_evolution_sim_benchmark_rejects_all_systems() -> None:
    with pytest.raises(SystemExit, match="memorii only"):
        main(["--suite", "memory_evolution_sim_v1", "--systems", "all"])
