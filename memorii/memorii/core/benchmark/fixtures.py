"""Fixture utilities for benchmark execution."""

from __future__ import annotations

from memorii.core.benchmark.models import BenchmarkScenarioFixture


def normalize_fixtures(fixtures: list[BenchmarkScenarioFixture]) -> list[BenchmarkScenarioFixture]:
    return sorted(fixtures, key=lambda fixture: fixture.scenario_id)
