from memorii.core.benchmark.harness import BenchmarkHarness
from memorii.core.benchmark.models import BenchmarkSystem
from tests.fixtures.benchmarks.phase7_minimal import load_phase7_fixture_set


def test_end_to_end_scenario_success_and_pollution_signals() -> None:
    report = BenchmarkHarness().run(fixtures=load_phase7_fixture_set())
    by_system = {
        result.system: result
        for result in report.scenario_results
        if result.scenario_id == "e2e_fail_debug_resolve"
    }

    assert by_system[BenchmarkSystem.MEMORII].observation.scenario_success is True
    assert by_system[BenchmarkSystem.FLAT_RETRIEVAL_BASELINE].observation.semantic_pollution is True
    assert by_system[BenchmarkSystem.FLAT_RETRIEVAL_BASELINE].observation.user_memory_pollution is True
