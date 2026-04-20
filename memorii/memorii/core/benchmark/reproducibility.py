"""Helpers for deterministic benchmark runs."""

from __future__ import annotations

import hashlib
import random

from memorii.core.benchmark.models import BenchmarkRunConfig, BenchmarkScenarioFixture


def apply_seed(seed: int) -> None:
    random.seed(seed)


def build_run_id(*, config: BenchmarkRunConfig, fixtures: list[BenchmarkScenarioFixture]) -> str:
    fixture_key = "|".join(sorted(f"{fixture.scenario_id}:{fixture.category.value}" for fixture in fixtures))
    raw = f"{config.run_label}:{config.seed}:{fixture_key}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"bench-{digest}"
