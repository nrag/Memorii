"""Fixture utilities for benchmark execution."""

from __future__ import annotations

from memorii.core.benchmark.models import BenchmarkScenarioFixture


def validate_fixture_set(fixtures: list[BenchmarkScenarioFixture]) -> list[BenchmarkScenarioFixture]:
    validated = [BenchmarkScenarioFixture.model_validate(fixture.model_dump(mode="python")) for fixture in fixtures]
    for fixture in validated:
        if fixture.long_horizon_degradation is not None:
            _validate_long_horizon_fixture(fixture)
    return validated


def _validate_long_horizon_fixture(fixture: BenchmarkScenarioFixture) -> None:
    long_horizon = fixture.long_horizon_degradation
    if long_horizon is None:
        return

    delayed_total = len(long_horizon.delayed_retrieval.corpus)
    if delayed_total < 50:
        raise ValueError(
            f"{fixture.scenario_id} delayed_retrieval must contain at least 50 items; got {delayed_total}"
        )

    relevant_count = len(set(long_horizon.delayed_retrieval.expected_relevant_ids))
    relevance_ratio = float(relevant_count) / float(delayed_total)
    if relevance_ratio > 0.2:
        raise ValueError(
            f"{fixture.scenario_id} delayed_retrieval relevant ratio must be <= 0.2; got {relevance_ratio:.4f}"
        )
    if not long_horizon.delayed_depends_on_early_context:
        raise ValueError(
            f"{fixture.scenario_id} must set delayed_depends_on_early_context=True for long-horizon rigor"
        )


def normalize_fixtures(fixtures: list[BenchmarkScenarioFixture]) -> list[BenchmarkScenarioFixture]:
    validated = validate_fixture_set(fixtures)
    return sorted(validated, key=lambda fixture: fixture.scenario_id)
