from memorii.core.benchmark.harness import BenchmarkHarness
from memorii.core.benchmark.models import BenchmarkRunConfig
from tests.fixtures.benchmarks.benchmark_minimal import load_benchmark_fixture_set


def test_run_id_is_stable_for_same_config_and_fixtures() -> None:
    fixtures = load_benchmark_fixture_set()
    config = BenchmarkRunConfig(seed=99, run_label="stable")
    harness = BenchmarkHarness()

    report1 = harness.run(fixtures=fixtures, config=config)
    report2 = harness.run(fixtures=fixtures, config=config)

    assert report1.run_id == report2.run_id


def test_seed_changes_run_id() -> None:
    fixtures = load_benchmark_fixture_set()
    harness = BenchmarkHarness()

    report1 = harness.run(fixtures=fixtures, config=BenchmarkRunConfig(seed=1, run_label="stable"))
    report2 = harness.run(fixtures=fixtures, config=BenchmarkRunConfig(seed=2, run_label="stable"))

    assert report1.run_id != report2.run_id


def test_reproducible_scenario_outputs_for_same_seed() -> None:
    fixtures = load_benchmark_fixture_set()
    harness = BenchmarkHarness()
    config = BenchmarkRunConfig(seed=7, run_label="benchmark_eval")

    report1 = harness.run(fixtures=fixtures, config=config)
    report2 = harness.run(fixtures=fixtures, config=config)

    fingerprint1 = [
        (item.scenario_id, item.system.value, item.metrics.model_dump(exclude_none=True))
        for item in sorted(report1.scenario_results, key=lambda r: (r.scenario_id, r.system.value))
    ]
    fingerprint2 = [
        (item.scenario_id, item.system.value, item.metrics.model_dump(exclude_none=True))
        for item in sorted(report2.scenario_results, key=lambda r: (r.scenario_id, r.system.value))
    ]
    assert fingerprint1 == fingerprint2
