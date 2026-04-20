from memorii.core.benchmark.harness import BenchmarkHarness
from memorii.core.benchmark.models import BenchmarkRunConfig, BenchmarkSystem
from tests.fixtures.benchmarks.phase7_minimal import load_phase7_fixture_set


def test_harness_executes_all_scenarios_for_all_systems() -> None:
    fixtures = load_phase7_fixture_set()
    report = BenchmarkHarness().run(fixtures=fixtures, config=BenchmarkRunConfig(seed=11, run_label="phase7-test"))

    assert report.run_id
    assert len(report.scenario_results) == len(fixtures) * 4
    assert BenchmarkSystem.MEMORII in report.aggregate_by_system
    assert "retrieval_transcript_verbatim" in report.baseline_comparison
