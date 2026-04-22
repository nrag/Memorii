import json
from pathlib import Path

from memorii.core.benchmark.harness import BenchmarkHarness
from memorii.core.benchmark.models import BenchmarkScenarioFixture, BenchmarkSystem
from tests.fixtures.benchmarks.benchmark_minimal import load_benchmark_fixture_set
from tests.fixtures.benchmarks.long_horizon_templates import render_fact_statement


def _load_multilingual_fixtures() -> list[BenchmarkScenarioFixture]:
    path = Path(__file__).resolve().parents[3] / "fixtures" / "benchmarks" / "long_horizon_multilingual_sample.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [BenchmarkScenarioFixture.model_validate(raw) for raw in payload]


def test_template_renderer_for_en_es_fr() -> None:
    assert "now uses Postgres" in render_fact_statement(
        language="en",
        entity="Atlas",
        attribute="database",
        value="Postgres",
        template_id="current_fact_statement",
    )
    assert "ahora usa Postgres" in render_fact_statement(
        language="es",
        entity="Atlas",
        attribute="base de datos",
        value="Postgres",
        template_id="current_fact_statement",
    )
    assert "utilise maintenant Postgres" in render_fact_statement(
        language="fr",
        entity="Atlas",
        attribute="base de données",
        value="Postgres",
        template_id="current_fact_statement",
    )


def test_multilingual_long_horizon_scenarios_run_in_benchmark_harness() -> None:
    fixtures = load_benchmark_fixture_set() + _load_multilingual_fixtures()
    report = BenchmarkHarness().run(fixtures=fixtures)
    scenario_ids = {
        "long_horizon_multilingual_en_atlas_db",
        "long_horizon_multilingual_es_atlas_db",
        "long_horizon_multilingual_fr_atlas_db",
    }
    for scenario_id in scenario_ids:
        result = next(
            item
            for item in report.scenario_results
            if item.system == BenchmarkSystem.MEMORII and item.scenario_id == scenario_id
        )
        assert result.observation.precision_at_1 is not None
        assert result.observation.hard_distractor_outrank_rate is not None


def test_multilingual_fixture_file_is_self_contained() -> None:
    fixtures = _load_multilingual_fixtures()
    for fixture in fixtures:
        long_horizon = fixture.long_horizon_degradation
        assert long_horizon is not None
        assert long_horizon.delayed_retrieval.corpus
        assert len(long_horizon.delayed_retrieval.corpus) >= 50
