import pytest

from memorii.core.benchmark.harness import BenchmarkHarness
from memorii.core.benchmark.models import (
    BaselineApplicability,
    BaselinePolicy,
    BenchmarkRunConfig,
    BenchmarkScenarioFixture,
    BenchmarkSystem,
)
from tests.fixtures.benchmarks.benchmark_minimal import load_benchmark_fixture_set


def test_preflight_rejects_baseline_skip_without_reason() -> None:
    fixtures = load_benchmark_fixture_set()
    target = next(item for item in fixtures if item.scenario_id == "retrieval_transcript_verbatim")
    invalid = BenchmarkScenarioFixture.model_validate(
        {
            **target.model_dump(mode="python"),
            "baseline_applicability": {
                BenchmarkSystem.TRANSCRIPT_ONLY_BASELINE: BaselineApplicability(policy=BaselinePolicy.SKIP).model_dump(
                    mode="python"
                )
            },
        }
    )
    with pytest.raises(ValueError):
        BenchmarkHarness().run(fixtures=[invalid] + [f for f in fixtures if f.scenario_id != target.scenario_id])


def test_preflight_reproducibility_check_runs() -> None:
    fixtures = load_benchmark_fixture_set()
    report = BenchmarkHarness().run(fixtures=fixtures, config=BenchmarkRunConfig(run_reproducibility_check=True))
    assert report.run_id
