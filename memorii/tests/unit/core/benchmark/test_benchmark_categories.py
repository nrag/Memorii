from memorii.core.benchmark.harness import BenchmarkHarness
from memorii.core.benchmark.models import BenchmarkScenarioType, BenchmarkSystem
from tests.fixtures.benchmarks.benchmark_minimal import load_benchmark_fixture_set


def _result(report, scenario_id: str, system: BenchmarkSystem):
    for item in report.scenario_results:
        if item.scenario_id == scenario_id and item.system == system:
            return item
    return None


def test_learning_across_episodes_benchmark_execution() -> None:
    report = BenchmarkHarness().run(fixtures=load_benchmark_fixture_set())
    result = _result(report, "learning_reuse_preference", BenchmarkSystem.MEMORII)
    assert result is not None
    assert result.category == BenchmarkScenarioType.LEARNING_ACROSS_EPISODES
    assert result.metrics.cross_episode_reuse_accuracy == 1.0
    assert result.metrics.writeback_reuse_correctness == 1.0


def test_long_horizon_benchmark_execution() -> None:
    report = BenchmarkHarness().run(fixtures=load_benchmark_fixture_set())
    result = _result(report, "long_horizon_noise_and_delay", BenchmarkSystem.MEMORII)
    assert result is not None
    assert result.category == BenchmarkScenarioType.LONG_HORIZON_DEGRADATION
    assert result.metrics.retrieval_latency_growth is not None
    assert result.metrics.noise_resilience is not None


def test_conflict_resolution_benchmark_execution() -> None:
    report = BenchmarkHarness().run(fixtures=load_benchmark_fixture_set())
    result = _result(report, "conflict_newer_fact_wins", BenchmarkSystem.MEMORII)
    assert result is not None
    assert result.category == BenchmarkScenarioType.CONFLICT_RESOLUTION
    assert result.metrics.conflict_detection_rate == 1.0
    assert result.metrics.correct_preference_for_newer_or_valid_memory == 1.0


def test_implicit_recall_benchmark_execution() -> None:
    report = BenchmarkHarness().run(fixtures=load_benchmark_fixture_set())
    result = _result(report, "implicit_recall_structural_match", BenchmarkSystem.MEMORII)
    assert result is not None
    assert result.category == BenchmarkScenarioType.IMPLICIT_RECALL
    assert result.metrics.implicit_recall_success_rate == 1.0
    assert result.metrics.retrieval_plan_relevance_accuracy == 1.0


def test_semantic_retrieval_scenario_success_tracks_excluded_items() -> None:
    report = BenchmarkHarness().run(fixtures=load_benchmark_fixture_set())
    pass_result = _result(report, "retrieval_semantic_validated", BenchmarkSystem.MEMORII)
    assert pass_result is not None
    assert pass_result.observation.scenario_success is True
    assert pass_result.metrics.scenario_success_rate == 1.0
