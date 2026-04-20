from memorii.core.benchmark.harness import BenchmarkHarness
from memorii.core.benchmark.models import BenchmarkRunConfig
from tests.fixtures.benchmarks.phase7_minimal import load_phase7_fixture_set


def test_run_id_is_stable_for_same_config_and_fixtures() -> None:
    fixtures = load_phase7_fixture_set()
    config = BenchmarkRunConfig(seed=99, run_label="stable")
    harness = BenchmarkHarness()

    report1 = harness.run(fixtures=fixtures, config=config)
    report2 = harness.run(fixtures=fixtures, config=config)

    assert report1.run_id == report2.run_id


def test_seed_changes_run_id() -> None:
    fixtures = load_phase7_fixture_set()
    harness = BenchmarkHarness()

    report1 = harness.run(fixtures=fixtures, config=BenchmarkRunConfig(seed=1, run_label="stable"))
    report2 = harness.run(fixtures=fixtures, config=BenchmarkRunConfig(seed=2, run_label="stable"))

    assert report1.run_id != report2.run_id
