from memorii.core.benchmark.baselines import BASELINE_SYSTEMS
from memorii.core.benchmark.harness import BenchmarkHarness
from memorii.core.benchmark.models import BenchmarkSystem
from tests.fixtures.benchmarks.phase7_minimal import load_phase7_fixture_set


def test_all_required_baselines_present() -> None:
    assert len(BASELINE_SYSTEMS) == 3


def test_baseline_comparison_contains_all_baselines() -> None:
    report = BenchmarkHarness().run(fixtures=load_phase7_fixture_set())
    deltas = report.baseline_comparison["retrieval_transcript_verbatim"]
    assert {delta.baseline for delta in deltas} == set(BASELINE_SYSTEMS)

    memorii = [item for item in report.scenario_results if item.system == BenchmarkSystem.MEMORII]
    assert memorii
