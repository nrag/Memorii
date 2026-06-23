from memorii.core.benchmark.fixtures import normalize_fixtures
from memorii.core.benchmark.lifecycle_decision import lifecycle_family_requires_decision
from memorii.core.benchmark.metrics import aggregate_metrics, compute_metrics
from memorii.core.benchmark.models import BenchmarkSystem, MemoryLifecycleFamily
from memorii.core.benchmark.scenarios import ScenarioExecutor
from tests.fixtures.benchmarks.memory_lifecycle_v1 import load_memory_lifecycle_v1_fixture_set


def test_memory_lifecycle_v1_covers_all_lifecycle_families() -> None:
    fixtures = normalize_fixtures(load_memory_lifecycle_v1_fixture_set())

    observed_families = {fixture.lifecycle.family for fixture in fixtures if fixture.lifecycle is not None}

    assert len(fixtures) >= 10
    assert observed_families == set(MemoryLifecycleFamily)
    assert all(fixture.lifecycle is not None for fixture in fixtures)


def test_memory_lifecycle_v1_memorii_baseline_passes_lifecycle_expectations() -> None:
    fixtures = normalize_fixtures(load_memory_lifecycle_v1_fixture_set())
    executor = ScenarioExecutor()

    stable_fixtures = [
        fixture
        for fixture in fixtures
        if fixture.lifecycle is None
        or not lifecycle_family_requires_decision(fixture.lifecycle.family)
    ]
    observations = [
        executor.run(fixture=fixture, system=BenchmarkSystem.MEMORII)
        for fixture in stable_fixtures
    ]

    assert all(observation.scenario_success is True for observation in observations)
    assert all(observation.lifecycle_success is True for observation in observations)
    assert all(compute_metrics(observation).lifecycle_success_rate == 1.0 for observation in observations)


def test_memory_lifecycle_v1_aggregate_metrics_include_lifecycle_axes() -> None:
    fixtures = normalize_fixtures(load_memory_lifecycle_v1_fixture_set())
    executor = ScenarioExecutor()
    stable_fixtures = [
        fixture
        for fixture in fixtures
        if fixture.lifecycle is None
        or not lifecycle_family_requires_decision(fixture.lifecycle.family)
    ]
    observations = [
        executor.run(fixture=fixture, system=BenchmarkSystem.MEMORII)
        for fixture in stable_fixtures
    ]

    aggregate = aggregate_metrics(observations)

    assert aggregate.lifecycle_success_rate == 1.0
    assert aggregate.active_memory_accuracy == 1.0
    assert aggregate.retrieval_currentness_accuracy == 1.0
    assert aggregate.pollution_avoidance_accuracy == 1.0
