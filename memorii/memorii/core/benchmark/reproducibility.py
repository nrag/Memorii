"""Helpers for deterministic benchmark runs."""

from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Mapping

from memorii.core.benchmark.models import BenchmarkRunConfig, BenchmarkScenarioFixture


def apply_seed(seed: int) -> None:
    random.seed(seed)


def build_run_id(*, config: BenchmarkRunConfig, fixtures: list[BenchmarkScenarioFixture]) -> str:
    fixture_key = "|".join(sorted(f"{fixture.scenario_id}:{fixture.category.value}" for fixture in fixtures))
    raw = f"{config.run_label}:{config.seed}:{fixture_key}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"bench-{digest}"


def build_run_config_fingerprint(config: Mapping[str, object]) -> str:
    """Return a stable fingerprint for the gate-relevant run configuration.

    The seed is intentionally excluded by callers so repeated seeds can be
    compared as replicates while still rejecting mixed benchmark settings.
    """

    payload = json.dumps(dict(config), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
