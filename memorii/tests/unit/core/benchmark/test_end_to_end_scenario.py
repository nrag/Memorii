from memorii.core.benchmark.harness import BenchmarkHarness
from memorii.core.benchmark.models import BenchmarkScenarioFixture, BenchmarkSystem, ScenarioExecutionLevel
from tests.fixtures.benchmarks.benchmark_minimal import load_benchmark_fixture_set


def test_end_to_end_scenario_success_and_pollution_signals() -> None:
    report = BenchmarkHarness().run(fixtures=load_benchmark_fixture_set())
    by_system = {
        result.system: result
        for result in report.scenario_results
        if result.scenario_id == "e2e_fail_debug_resolve"
    }

    assert by_system[BenchmarkSystem.MEMORII].observation.scenario_success is True
    assert by_system[BenchmarkSystem.MEMORII].observation.execution_level == ScenarioExecutionLevel.SYSTEM_LEVEL
    assert by_system[BenchmarkSystem.MEMORII].metrics.writeback_candidate_correctness == 1.0
    assert by_system[BenchmarkSystem.MEMORII].observation.writeback_candidate_ids == [
        "wb:solver:task:1:exec:task:1:root:evt:tool:failed"
    ]
    assert by_system[BenchmarkSystem.FLAT_RETRIEVAL_BASELINE].observation.semantic_pollution is True
    assert by_system[BenchmarkSystem.FLAT_RETRIEVAL_BASELINE].observation.user_memory_pollution is True


def test_end_to_end_observation_carries_expected_routing_fields() -> None:
    report = BenchmarkHarness().run(fixtures=load_benchmark_fixture_set())
    memorii_result = next(
        result
        for result in report.scenario_results
        if result.scenario_id == "e2e_fail_debug_resolve" and result.system == BenchmarkSystem.MEMORII
    )
    assert memorii_result.observation.expected_routed_domains
    assert memorii_result.observation.expected_blocked_domains == []


def test_end_to_end_scenario_fails_when_routing_expectation_is_wrong() -> None:
    fixtures = load_benchmark_fixture_set()
    target = next(item for item in fixtures if item.scenario_id == "e2e_fail_debug_resolve")
    wrong_routing_fixture = BenchmarkScenarioFixture.model_validate(
        {
            **target.model_dump(mode="python"),
            "routing": {
                **target.routing.model_dump(mode="python"),
                "expected_domains": ["transcript"],
            },
        }
    )
    report = BenchmarkHarness().run(
        fixtures=[wrong_routing_fixture] + [item for item in fixtures if item.scenario_id != target.scenario_id]
    )
    memorii_result = next(
        result
        for result in report.scenario_results
        if result.system == BenchmarkSystem.MEMORII and result.scenario_id == target.scenario_id
    )
    assert memorii_result.observation.scenario_success is False
