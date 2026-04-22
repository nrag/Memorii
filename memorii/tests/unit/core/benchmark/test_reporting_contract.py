from __future__ import annotations

import json
from pathlib import Path

import pytest

from memorii.core.benchmark.harness import BenchmarkHarness
from memorii.core.benchmark.models import CanonicalBenchmarkReport
from memorii.core.benchmark.reporting import to_canonical_report, to_markdown, write_artifacts
from memorii.core.benchmark.validation import validate_canonical_report
from tests.fixtures.benchmarks.benchmark_minimal import load_benchmark_fixture_set


def test_canonical_report_has_required_top_level_sections() -> None:
    fixtures = load_benchmark_fixture_set()
    report = BenchmarkHarness().run(fixtures=fixtures)
    canonical = to_canonical_report(report, fixtures=fixtures, dataset="fixture_set", fixture_source="tests")

    payload = canonical.model_dump(mode="json")
    assert set(payload.keys()) == {"metadata", "config", "summary", "categories", "scenarios", "baselines", "errors"}


def test_canonical_scenario_entries_include_expected_observed_metrics_and_execution_type() -> None:
    fixtures = load_benchmark_fixture_set()
    report = BenchmarkHarness().run(fixtures=fixtures)
    canonical = to_canonical_report(report, fixtures=fixtures)

    assert canonical.scenarios
    for entry in canonical.scenarios:
        assert entry.expected is not None
        assert entry.observed is not None
        assert entry.metrics is not None
        assert entry.execution_type.value in {"component_level", "system_level"}


def test_baseline_summary_is_machine_readable() -> None:
    fixtures = load_benchmark_fixture_set()
    report = BenchmarkHarness().run(fixtures=fixtures)
    canonical = to_canonical_report(report, fixtures=fixtures)

    assert canonical.summary.baseline_comparison_summary
    serialized = json.dumps(canonical.summary.baseline_comparison_summary, sort_keys=True)
    assert isinstance(serialized, str)


def test_markdown_is_derived_from_canonical_report() -> None:
    fixtures = load_benchmark_fixture_set()
    report = BenchmarkHarness().run(fixtures=fixtures)
    markdown = to_markdown(report, fixtures=fixtures)
    canonical = to_canonical_report(report, fixtures=fixtures)

    assert canonical.metadata.run_id in markdown
    assert "## Scenarios" in markdown


def test_canonical_reporting_marks_semantic_retrieval_as_passed_when_success_true() -> None:
    fixtures = load_benchmark_fixture_set()
    report = BenchmarkHarness().run(fixtures=fixtures)
    canonical = to_canonical_report(report, fixtures=fixtures)
    semantic_entry = next(
        entry
        for entry in canonical.scenarios
        if entry.scenario_id == "retrieval_semantic_validated" and entry.system.value == "memorii"
    )
    assert semantic_entry.passed is True


def test_expected_payload_prefers_fixture_contract_over_observation_shadow_data() -> None:
    fixtures = load_benchmark_fixture_set()
    report = BenchmarkHarness().run(fixtures=fixtures)
    target = next(
        result
        for result in report.scenario_results
        if result.scenario_id == "e2e_fail_debug_resolve" and result.system.value == "memorii"
    )
    target.observation.expected_routed_domains = []
    target.observation.expected_writeback_candidate_domains = []
    canonical = to_canonical_report(report, fixtures=fixtures)
    entry = next(
        item
        for item in canonical.scenarios
        if item.scenario_id == "e2e_fail_debug_resolve" and item.system.value == "memorii"
    )
    assert entry.expected["expected_routed_domains"] == ["transcript", "execution", "solver"]
    assert entry.expected["expected_writeback_candidate_domains"] == ["episodic"]


def test_malformed_canonical_report_fails_validation() -> None:
    fixtures = load_benchmark_fixture_set()
    report = BenchmarkHarness().run(fixtures=fixtures)
    canonical = to_canonical_report(report, fixtures=fixtures)
    malformed = canonical.model_copy(update={"scenarios": []})

    with pytest.raises(ValueError, match="requires scenarios"):
        validate_canonical_report(malformed)


def test_canonical_report_is_deterministic_except_timestamp() -> None:
    fixtures = load_benchmark_fixture_set()
    harness = BenchmarkHarness()
    report_a = harness.run(fixtures=fixtures)
    report_b = harness.run(fixtures=fixtures)
    canonical_a = to_canonical_report(report_a, fixtures=fixtures).model_dump(mode="json")
    canonical_b = to_canonical_report(report_b, fixtures=fixtures).model_dump(mode="json")

    assert canonical_a["metadata"]["run_id"] == canonical_b["metadata"]["run_id"]
    canonical_a["metadata"]["timestamp"] = "normalized"
    canonical_b["metadata"]["timestamp"] = "normalized"
    assert canonical_a == canonical_b


def test_write_artifacts_outputs_expected_contract_files(tmp_path: Path) -> None:
    fixtures = load_benchmark_fixture_set()
    report = BenchmarkHarness().run(fixtures=fixtures)
    run_dir = write_artifacts(
        report,
        fixtures=fixtures,
        dataset="fixture_set",
        fixture_source="tests/fixtures/benchmarks/benchmark_minimal.py",
        subset_size=len(fixtures),
        root_dir=str(tmp_path / "artifacts" / "benchmarks"),
    )

    report_json = run_dir / "report.json"
    report_md = run_dir / "report.md"
    baseline_json = run_dir / "baseline.json"
    fixtures_json = run_dir / "fixtures.json"
    assert report_json.exists()
    assert report_md.exists()
    assert baseline_json.exists()
    assert fixtures_json.exists()

    payload = json.loads(report_json.read_text(encoding="utf-8"))
    CanonicalBenchmarkReport.model_validate(payload)


def test_canonical_reporting_marks_unsupported_without_counting_as_failed() -> None:
    fixtures = load_benchmark_fixture_set()
    report = BenchmarkHarness().run(fixtures=fixtures)
    target = next(
        result
        for result in report.scenario_results
        if result.scenario_id == "e2e_fail_debug_resolve" and result.system.value == "memorii"
    )
    target.observation.runtime_observability_status = "unsupported"
    target.observation.scenario_success = False
    target.metrics.scenario_success_rate = None

    canonical = to_canonical_report(report, fixtures=fixtures)
    entry = next(
        item
        for item in canonical.scenarios
        if item.scenario_id == "e2e_fail_debug_resolve" and item.system.value == "memorii"
    )
    assert entry.outcome_status.value == "unsupported"
    assert entry.passed is False
    assert canonical.summary.failed == sum(1 for item in canonical.scenarios if item.outcome_status.value == "failed")
