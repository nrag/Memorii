from memorii.core.benchmark.baselines import BASELINE_SYSTEMS
from memorii.core.benchmark.harness import BenchmarkHarness
from memorii.core.benchmark.models import BenchmarkSystem
from tests.fixtures.benchmarks.benchmark_minimal import load_benchmark_fixture_set


def test_all_required_baselines_present() -> None:
    assert len(BASELINE_SYSTEMS) == 3


def test_baseline_comparison_contains_all_baselines() -> None:
    report = BenchmarkHarness().run(fixtures=load_benchmark_fixture_set())
    deltas = report.baseline_comparison["retrieval_transcript_verbatim"]
    assert {delta.baseline for delta in deltas} == set(BASELINE_SYSTEMS)
    assert all(delta.skipped is False for delta in deltas)

    memorii = [item for item in report.scenario_results if item.system == BenchmarkSystem.MEMORII]
    assert memorii


def test_baseline_skip_is_explicitly_reported() -> None:
    report = BenchmarkHarness().run(fixtures=load_benchmark_fixture_set())
    deltas = report.baseline_comparison["implicit_recall_solver_baseline_skip"]
    skipped = [delta for delta in deltas if delta.baseline == BenchmarkSystem.TRANSCRIPT_ONLY_BASELINE][0]
    assert skipped.skipped is True
    assert skipped.skip_reason
