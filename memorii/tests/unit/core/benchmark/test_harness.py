from memorii.core.benchmark.harness import BenchmarkHarness
from memorii.core.benchmark.models import BenchmarkRunConfig, BenchmarkScenarioFixture, BenchmarkSystem
from memorii.core.benchmark.reporting import to_markdown
from tests.fixtures.benchmarks.benchmark_minimal import load_benchmark_fixture_set


def test_harness_executes_all_scenarios_for_all_systems() -> None:
    fixtures = load_benchmark_fixture_set()
    report = BenchmarkHarness().run(fixtures=fixtures, config=BenchmarkRunConfig(seed=11, run_label="benchmark-test"))

    assert report.run_id
    skipped_baselines = 1
    assert len(report.scenario_results) == (len(fixtures) * 4) - skipped_baselines
    assert BenchmarkSystem.MEMORII in report.aggregate_by_system
    assert "retrieval_transcript_verbatim" in report.baseline_comparison
    assert report.aggregate_by_category


def test_report_includes_execution_level_marker() -> None:
    report = BenchmarkHarness().run(fixtures=load_benchmark_fixture_set())
    markdown = to_markdown(report)
    assert "system_level" in markdown


def test_retrieval_scenario_fails_when_excluded_item_is_retrieved() -> None:
    fixtures = load_benchmark_fixture_set()
    source = next(item for item in fixtures if item.scenario_id == "retrieval_semantic_validated")
    failing_fixture = BenchmarkScenarioFixture.model_validate(
        {
            **source.model_dump(mode="python"),
            "retrieval": {
                **source.retrieval.model_dump(mode="python"),
                "query": "null pointer dependency uninitialized unvalidated guess root cause",
                "top_k": 4,
            },
        }
    )
    report = BenchmarkHarness().run(
        fixtures=[failing_fixture] + [item for item in fixtures if item.scenario_id != source.scenario_id]
    )
    memorii_result = next(
        result
        for result in report.scenario_results
        if result.system == BenchmarkSystem.MEMORII and result.scenario_id == source.scenario_id
    )
    assert "sem:speculative" in memorii_result.observation.retrieved_ids
    assert memorii_result.observation.scenario_success is False
