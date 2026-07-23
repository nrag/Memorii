"""Independent process-level audit of the live certification design."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
from scipy.signal import fftconvolve
from scipy.stats import betabinom, binom


def _run_policy_command(command: str) -> dict[str, object]:
    package_root = Path(__file__).parents[2]
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(package_root)
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "memorii.tools.live_certification_policy",
            command,
        ],
        cwd=package_root,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def _clustered_count_distribution(
    *,
    reliability: float,
    correlation: float,
    seed_count: int,
    scenarios_per_seed: int,
) -> np.ndarray:
    if correlation == 0.0:
        total = seed_count * scenarios_per_seed
        return np.asarray(binom.pmf(np.arange(total + 1), total, reliability))
    concentration = (1.0 / correlation) - 1.0
    one_seed = np.asarray(
        betabinom.pmf(
            np.arange(scenarios_per_seed + 1),
            scenarios_per_seed,
            reliability * concentration,
            (1.0 - reliability) * concentration,
        )
    )
    distribution = np.asarray([1.0])
    for _ in range(seed_count):
        distribution = fftconvolve(distribution, one_seed)
    distribution = np.maximum(distribution, 0.0)
    return distribution / distribution.sum()


def _critical_success_count(
    distribution: np.ndarray,
    *,
    tail_probability: float,
    strict: bool = False,
) -> int | None:
    upper_tails = np.cumsum(distribution[::-1])[::-1]
    qualifying = np.flatnonzero(
        upper_tails < tail_probability
        if strict
        else upper_tails <= tail_probability
    )
    return int(qualifying[0]) if len(qualifying) else None


def _independent_reference_audit(policy: dict[str, object]) -> dict[str, float | bool]:
    seeds = policy["seeds"]
    correlations = policy["simulation_intraseed_correlation_points"]
    coverage_points = policy["coverage_reliability_points"]
    required_families = policy["required_families"]
    assert isinstance(seeds, list)
    assert isinstance(correlations, list)
    assert isinstance(coverage_points, list)
    assert isinstance(required_families, list)

    seed_count = len(seeds)
    scenarios_per_seed = int(policy["scenarios_per_replicate"])
    confidence_level = float(policy["confidence_level"])
    threshold = float(policy["minimum_pass_rate_lower_bound"])
    target = float(policy["design_target_scenario_reliability"])
    tail_probability = (1.0 - confidence_level) / (len(required_families) + 1)

    powers: list[float] = []
    null_acceptance_probabilities: list[float] = []
    coverages: list[float] = []
    for correlation_value in correlations:
        correlation = float(correlation_value)
        null_distribution = _clustered_count_distribution(
            reliability=threshold,
            correlation=correlation,
            seed_count=seed_count,
            scenarios_per_seed=scenarios_per_seed,
        )
        critical_count = _critical_success_count(
            null_distribution,
            tail_probability=tail_probability,
        )
        target_distribution = _clustered_count_distribution(
            reliability=target,
            correlation=correlation,
            seed_count=seed_count,
            scenarios_per_seed=scenarios_per_seed,
        )
        powers.append(
            0.0
            if critical_count is None
            else float(target_distribution[critical_count:].sum())
        )
        null_acceptance_probabilities.append(
            0.0
            if critical_count is None
            else float(null_distribution[critical_count:].sum())
        )
        for reliability_value in coverage_points:
            reliability = float(reliability_value)
            true_distribution = _clustered_count_distribution(
                reliability=reliability,
                correlation=correlation,
                seed_count=seed_count,
                scenarios_per_seed=scenarios_per_seed,
            )
            first_noncovering_count = _critical_success_count(
                true_distribution,
                tail_probability=tail_probability,
                strict=True,
            )
            noncoverage = (
                0.0
                if first_noncovering_count is None
                else float(true_distribution[first_noncovering_count:].sum())
            )
            coverages.append(1.0 - noncoverage)

    minimum_power = min(powers)
    maximum_null = max(null_acceptance_probabilities)
    minimum_coverage = min(coverages)
    return {
        "minimum_power_lower_bound": minimum_power,
        "maximum_null_acceptance_upper_bound": maximum_null,
        "minimum_coverage_lower_bound": minimum_coverage,
        "passed": (
            minimum_power >= float(policy["minimum_design_power"])
            and maximum_null <= float(policy["maximum_null_acceptance_probability"])
            and minimum_coverage >= float(policy["minimum_interval_coverage"])
        ),
    }


def test_live_certification_policy_has_complete_unique_matrix() -> None:
    description = _run_policy_command("describe")
    matrix = _run_policy_command("github-matrix")

    policy = description["policy"]
    assert isinstance(policy, dict)
    seeds = policy["seeds"]
    replicates = policy["replicates"]
    assert isinstance(seeds, list)
    assert isinstance(replicates, list)
    expected = {
        (seed, replicate)
        for seed in seeds
        for replicate in replicates
    }
    rows = matrix["include"]
    assert isinstance(rows, list)
    observed = {(row["seed"], row["replicate"]) for row in rows}
    assert observed == expected
    assert len(rows) == len(observed)


def test_live_certification_design_accepts_reliable_system_and_rejects_null() -> None:
    description = _run_policy_command("describe")
    audit = _run_policy_command("preflight")

    policy = description["policy"]
    assert isinstance(policy, dict)
    assert audit["policy_digest"] == description["digest"]
    assert audit["passed"] is True
    assert audit["failure_reasons"] == []
    assert audit["minimum_power_lower_bound"] >= policy["minimum_design_power"]
    assert (
        audit["maximum_null_acceptance_upper_bound"]
        <= policy["maximum_null_acceptance_probability"]
    )
    assert (
        audit["minimum_coverage_lower_bound"]
        >= policy["minimum_interval_coverage"]
    )
    design_points = len(policy["simulation_models"]) * len(
        policy["simulation_intraseed_correlation_points"]
    )
    coverage_points = design_points * len(policy["coverage_reliability_points"])
    assert len(audit["power_estimates"]) == design_points
    assert len(audit["null_acceptance_estimates"]) == design_points
    assert len(audit["coverage_estimates"]) == coverage_points


def test_live_certification_design_passes_independent_seed_cluster_reference() -> None:
    description = _run_policy_command("describe")
    policy = description["policy"]
    assert isinstance(policy, dict)

    audit = _independent_reference_audit(policy)

    assert audit["passed"] is True
    assert audit["minimum_power_lower_bound"] >= policy["minimum_design_power"]
    assert (
        audit["maximum_null_acceptance_upper_bound"]
        <= policy["maximum_null_acceptance_probability"]
    )
    assert audit["minimum_coverage_lower_bound"] >= policy["minimum_interval_coverage"]


def test_independent_seed_cluster_reference_rejects_underpowered_design() -> None:
    description = _run_policy_command("describe")
    policy = description["policy"]
    assert isinstance(policy, dict)
    policy["seeds"] = policy["seeds"][:5]

    audit = _independent_reference_audit(policy)

    assert audit["passed"] is False
    assert audit["minimum_power_lower_bound"] < policy["minimum_design_power"]
