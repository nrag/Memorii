"""Cluster-aware uncertainty estimates for benchmark calibration."""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence

from memorii.core.calibration.models import ScenarioClusterInterval


def scenario_cluster_bootstrap(
    values_by_scenario: Mapping[str, Sequence[float]],
    *,
    seed: int = 0,
    resamples: int = 2000,
    confidence_level: float = 0.95,
) -> ScenarioClusterInterval | None:
    """Estimate a scenario-weighted mean and percentile interval.

    Resampling scenario means, rather than individual checkpoint rows, keeps
    correlated checkpoints from a single scenario from being treated as
    independent observations. Empty scenarios are ignored because they carry
    no estimand for this metric.
    """

    if not 0.0 < confidence_level < 1.0:
        raise ValueError("confidence_level must be between 0 and 1")
    if resamples < 1:
        raise ValueError("resamples must be positive")
    scenario_means = [
        sum(values) / len(values)
        for _scenario_id, values in sorted(values_by_scenario.items())
        if values
    ]
    if not scenario_means:
        return None
    estimate = sum(scenario_means) / len(scenario_means)
    rng = random.Random(seed)
    bootstrap_means = [
        sum(rng.choice(scenario_means) for _ in scenario_means) / len(scenario_means)
        for _ in range(resamples)
    ]
    bootstrap_means.sort()
    alpha = (1.0 - confidence_level) / 2.0
    return ScenarioClusterInterval(
        estimate=estimate,
        lower=_percentile(bootstrap_means, alpha),
        upper=_percentile(bootstrap_means, 1.0 - alpha),
        scenario_count=len(scenario_means),
        observation_count=sum(len(values) for values in values_by_scenario.values()),
        confidence_level=confidence_level,
        resamples=resamples,
        seed=seed,
    )


def hierarchical_seed_scenario_bootstrap(
    values_by_seed: Mapping[int, Mapping[str, Sequence[float]]],
    *,
    seed: int = 0,
    resamples: int = 2000,
    confidence_level: float = 0.95,
) -> ScenarioClusterInterval | None:
    """Bootstrap live-gate outcomes at both the seed and scenario levels.

    Live gates commonly repeat the same scenario family under multiple seeds.
    Resampling ``seed:scenario`` pairs as independent observations makes the
    confidence interval too narrow when scenario identities repeat. This
    two-stage bootstrap treats seeds as the outer replication unit and the
    scenarios within each seed as the inner unit, giving each seed equal
    weight.
    """

    if not 0.0 < confidence_level < 1.0:
        raise ValueError("confidence_level must be between 0 and 1")
    if resamples < 1:
        raise ValueError("resamples must be positive")
    seed_groups = {
        run_seed: [
            sum(values) / len(values)
            for _scenario_id, values in sorted(scenarios.items())
            if values
        ]
        for run_seed, scenarios in sorted(values_by_seed.items())
    }
    seed_groups = {run_seed: means for run_seed, means in seed_groups.items() if means}
    if not seed_groups:
        return None

    seed_means = [sum(means) / len(means) for means in seed_groups.values()]
    estimate = sum(seed_means) / len(seed_means)
    rng = random.Random(seed)
    seed_ids = list(seed_groups)
    bootstrap_means: list[float] = []
    for _ in range(resamples):
        sampled_seed_means: list[float] = []
        for _ in seed_ids:
            sampled_seed = rng.choice(seed_ids)
            scenario_means = seed_groups[sampled_seed]
            sampled_scenarios = [rng.choice(scenario_means) for _ in scenario_means]
            sampled_seed_means.append(sum(sampled_scenarios) / len(sampled_scenarios))
        bootstrap_means.append(sum(sampled_seed_means) / len(sampled_seed_means))
    bootstrap_means.sort()
    alpha = (1.0 - confidence_level) / 2.0
    return ScenarioClusterInterval(
        estimate=estimate,
        lower=_percentile(bootstrap_means, alpha),
        upper=_percentile(bootstrap_means, 1.0 - alpha),
        scenario_count=sum(len(means) for means in seed_groups.values()),
        observation_count=sum(
            len(values)
            for scenarios in values_by_seed.values()
            for values in scenarios.values()
        ),
        confidence_level=confidence_level,
        resamples=resamples,
        seed=seed,
        method="hierarchical_seed_scenario_bootstrap_percentile",
    )


def _percentile(values: Sequence[float], probability: float) -> float:
    if not values:
        raise ValueError("percentile requires values")
    position = (len(values) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    fraction = position - lower
    return values[lower] + (values[upper] - values[lower]) * fraction
