import pytest

from memorii.core.benchmark.harness import BenchmarkHarness
from memorii.core.benchmark.models import (
    BaselineApplicability,
    BaselinePolicy,
    BenchmarkRunConfig,
    BenchmarkScenarioFixture,
    BenchmarkSystem,
)
from memorii.core.benchmark.validation import validate_report
from tests.fixtures.benchmarks.benchmark_minimal import load_benchmark_fixture_set


def test_preflight_rejects_baseline_skip_without_reason() -> None:
    fixtures = load_benchmark_fixture_set()
    target = next(item for item in fixtures if item.scenario_id == "retrieval_transcript_verbatim")
    invalid = BenchmarkScenarioFixture.model_validate(
        {
            **target.model_dump(mode="python"),
            "baseline_applicability": {
                BenchmarkSystem.TRANSCRIPT_ONLY_BASELINE: BaselineApplicability(policy=BaselinePolicy.SKIP).model_dump(
                    mode="python"
                )
            },
        }
    )
    with pytest.raises(ValueError):
        BenchmarkHarness().run(fixtures=[invalid] + [f for f in fixtures if f.scenario_id != target.scenario_id])


def test_preflight_reproducibility_check_runs() -> None:
    fixtures = load_benchmark_fixture_set()
    report = BenchmarkHarness().run(fixtures=fixtures, config=BenchmarkRunConfig(run_reproducibility_check=True))
    assert report.run_id


def test_validate_report_rejects_missing_required_harness_metrics() -> None:
    fixtures = load_benchmark_fixture_set()
    report = BenchmarkHarness().run(fixtures=fixtures)
    semantic_result = next(
        result
        for result in report.scenario_results
        if result.scenario_id == "retrieval_semantic_validated" and result.system == BenchmarkSystem.MEMORII
    )
    semantic_result.metrics.scenario_success_rate = None

    with pytest.raises(ValueError, match="missing scenario_success_rate"):
        validate_report(report)


def test_validate_report_rejects_missing_transcript_scenario_success_rate() -> None:
    fixtures = load_benchmark_fixture_set()
    report = BenchmarkHarness().run(fixtures=fixtures)
    transcript_result = next(
        result
        for result in report.scenario_results
        if result.scenario_id == "retrieval_transcript_verbatim" and result.system == BenchmarkSystem.MEMORII
    )
    transcript_result.metrics.scenario_success_rate = None

    with pytest.raises(ValueError, match="missing scenario_success_rate"):
        validate_report(report)


def test_validate_report_rejects_missing_episodic_scenario_success_rate() -> None:
    fixtures = load_benchmark_fixture_set()
    report = BenchmarkHarness().run(fixtures=fixtures)
    episodic_result = next(
        result
        for result in report.scenario_results
        if result.scenario_id == "retrieval_episodic_prior_case" and result.system == BenchmarkSystem.MEMORII
    )
    episodic_result.metrics.scenario_success_rate = None

    with pytest.raises(ValueError, match="missing scenario_success_rate"):
        validate_report(report)
