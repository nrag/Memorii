"""Cluster-aware uncertainty estimates for benchmark calibration."""

from __future__ import annotations

import random
from collections.abc import Callable, Mapping, Sequence
from math import comb, exp, lgamma, sqrt
from statistics import NormalDist
from typing import TypeVar

from memorii.core.calibration.models import (
    GateCoverageAlgorithmVersion,
    GateCoverageCertificate,
    GateCoverageConfiguration,
    GateCoverageEstimate,
    GatePowerEstimate,
    ScenarioClusterInterval,
    ScenarioPassInterval,
)
from memorii.core.calibration.simulation_models import (
    GateSimulationModel,
    family_mixture_rate,
    sample_seed_rate,
    simulation_model_moments,
)


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
        sum(values) / len(values) for _scenario_id, values in sorted(values_by_scenario.items()) if values
    ]
    if not scenario_means:
        return None
    estimate = sum(scenario_means) / len(scenario_means)
    rng = random.Random(seed)
    bootstrap_means = [
        sum(rng.choice(scenario_means) for _ in scenario_means) / len(scenario_means) for _ in range(resamples)
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


SeedKey = TypeVar("SeedKey", int, str)


def hierarchical_seed_scenario_bootstrap(
    values_by_seed: Mapping[SeedKey, Mapping[str, Sequence[float]]],
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
        run_seed: {scenario_id: list(values) for scenario_id, values in sorted(scenarios.items()) if values}
        for run_seed, scenarios in sorted(values_by_seed.items())
    }
    seed_groups = {run_seed: scenarios for run_seed, scenarios in seed_groups.items() if scenarios}
    if not seed_groups:
        return None

    seed_means = [
        sum(sum(values) / len(values) for values in scenarios.values()) / len(scenarios)
        for scenarios in seed_groups.values()
    ]
    estimate = sum(seed_means) / len(seed_means)
    rng = random.Random(seed)
    seed_ids = list(seed_groups)
    bootstrap_means: list[float] = []
    for _ in range(resamples):
        sampled_seed_means: list[float] = []
        for _ in seed_ids:
            sampled_seed = rng.choice(seed_ids)
            scenarios = seed_groups[sampled_seed]
            scenario_ids = list(scenarios)
            sampled_scenario_means: list[float] = []
            for _ in scenario_ids:
                sampled_scenario = rng.choice(scenario_ids)
                observations = scenarios[sampled_scenario]
                sampled_observations = [rng.choice(observations) for _ in observations]
                sampled_scenario_means.append(sum(sampled_observations) / len(sampled_observations))
            sampled_seed_means.append(sum(sampled_scenario_means) / len(sampled_scenario_means))
        bootstrap_means.append(sum(sampled_seed_means) / len(sampled_seed_means))
    bootstrap_means.sort()
    alpha = (1.0 - confidence_level) / 2.0
    return ScenarioClusterInterval(
        estimate=estimate,
        lower=_percentile(bootstrap_means, alpha),
        upper=_percentile(bootstrap_means, 1.0 - alpha),
        scenario_count=sum(len(scenarios) for scenarios in seed_groups.values()),
        observation_count=sum(len(values) for scenarios in values_by_seed.values() for values in scenarios.values()),
        confidence_level=confidence_level,
        resamples=resamples,
        seed=seed,
        method="hierarchical_seed_scenario_bootstrap_percentile",
    )


def seed_cluster_scenario_pass_interval(
    values_by_seed: Mapping[SeedKey, Mapping[str, Sequence[float]]],
    *,
    confidence_level: float = 0.95,
    intraseed_correlation: float = 0.05,
) -> ScenarioPassInterval | None:
    """Return a boundary-safe interval over seed-clustered scenario outcomes.

    Repeated inference calls for one generated scenario are deliberately not
    independent observations. A scenario succeeds only when every declared
    replicate succeeds. A beta-binomial seed model then yields exact one-sided
    bounds under the predeclared intraseed correlation assumption. The
    effective sample size is retained only as an interpretable design
    diagnostic; it does not determine the interval.
    """

    if not 0.0 < confidence_level < 1.0:
        raise ValueError("confidence_level must be between 0 and 1")
    if not 0.0 <= intraseed_correlation < 1.0:
        raise ValueError("intraseed_correlation must be in [0, 1)")
    scenario_outcomes: list[float] = []
    cluster_success_counts: list[int] = []
    scenario_counts_by_seed: list[int] = []
    observation_count = 0
    for scenarios in values_by_seed.values():
        seed_scenario_count = 0
        for values in scenarios.values():
            observations = list(values)
            if not observations:
                continue
            if any(value not in {0.0, 1.0} for value in observations):
                raise ValueError("live-gate outcomes must be binary")
            observation_count += len(observations)
            scenario_outcomes.append(1.0 if all(value == 1.0 for value in observations) else 0.0)
            seed_scenario_count += 1
        if seed_scenario_count:
            scenario_counts_by_seed.append(seed_scenario_count)
            cluster_success_counts.append(int(sum(scenario_outcomes[-seed_scenario_count:])))
    if not scenario_outcomes:
        return None

    scenario_count = len(scenario_outcomes)
    seed_count = len(scenario_counts_by_seed)
    success_count = int(sum(scenario_outcomes))
    estimate = success_count / scenario_count
    mean_cluster_size = scenario_count / seed_count
    design_effect = 1.0 + (mean_cluster_size - 1.0) * intraseed_correlation
    effective_sample_size = max(1.0, scenario_count / design_effect)
    lower, upper = _beta_binomial_cluster_interval(
        cluster_success_counts=cluster_success_counts,
        cluster_sizes=scenario_counts_by_seed,
        confidence_level=confidence_level,
        intraseed_correlation=intraseed_correlation,
    )
    return ScenarioPassInterval(
        estimate=estimate,
        lower=lower,
        upper=upper,
        success_count=success_count,
        scenario_count=scenario_count,
        seed_count=seed_count,
        observation_count=observation_count,
        effective_sample_size=effective_sample_size,
        intraseed_correlation=intraseed_correlation,
        confidence_level=confidence_level,
    )


def estimate_scenario_interval_coverage(
    *,
    true_scenario_reliability: float,
    seed_count: int,
    scenarios_per_seed: int,
    replicates_per_scenario: int = 2,
    interval_intraseed_correlation: float = 0.05,
    simulation_intraseed_correlation: float = 0.05,
    trials: int = 500,
    interval_confidence_level: float = 0.95,
    coverage_confidence_level: float = 0.95,
    seed: int = 0,
    simulation_model: GateSimulationModel = GateSimulationModel.BETA_BINOMIAL,
) -> GateCoverageEstimate:
    """Audit lower-bound coverage under the gate's declared seed model."""

    _validate_gate_design(
        true_scenario_reliability=true_scenario_reliability,
        seed_count=seed_count,
        scenarios_per_seed=scenarios_per_seed,
        replicates_per_scenario=replicates_per_scenario,
        intraseed_correlation=interval_intraseed_correlation,
        trials=trials,
        confidence_level=interval_confidence_level,
    )
    if not 0.0 <= simulation_intraseed_correlation < 1.0:
        raise ValueError("simulation_intraseed_correlation must be in [0, 1)")
    if not 0.0 < coverage_confidence_level < 1.0:
        raise ValueError("coverage_confidence_level must be between 0 and 1")
    rng = random.Random(seed)
    covered = 0
    for _ in range(trials):
        values = _simulate_gate_outcomes(
            rng,
            true_scenario_reliability=true_scenario_reliability,
            seed_count=seed_count,
            scenarios_per_seed=scenarios_per_seed,
            replicates_per_scenario=replicates_per_scenario,
            intraseed_correlation=simulation_intraseed_correlation,
            simulation_model=simulation_model,
        )
        interval = seed_cluster_scenario_pass_interval(
            values,
            confidence_level=interval_confidence_level,
            intraseed_correlation=interval_intraseed_correlation,
        )
        if interval is not None and interval.lower <= true_scenario_reliability:
            covered += 1
    probability = covered / trials
    coverage_lower = _wilson_one_sided_lower_bound(
        covered,
        trials,
        confidence_level=coverage_confidence_level,
    )
    moments = simulation_model_moments(
        mean=true_scenario_reliability,
        correlation=simulation_intraseed_correlation,
        simulation_model=simulation_model,
    )
    return GateCoverageEstimate(
        true_scenario_reliability=true_scenario_reliability,
        seed_count=seed_count,
        scenarios_per_seed=scenarios_per_seed,
        replicates_per_scenario=replicates_per_scenario,
        interval_intraseed_correlation=interval_intraseed_correlation,
        target_simulation_intraseed_correlation=simulation_intraseed_correlation,
        realized_simulation_intraseed_correlation=moments.intraseed_correlation,
        realized_marginal_reliability=moments.marginal_reliability,
        dependence_parameterization=moments.dependence_parameterization,
        estimated_lower_bound_coverage=probability,
        coverage_lower_confidence_bound=coverage_lower,
        monte_carlo_standard_error=sqrt(probability * (1.0 - probability) / trials),
        trials=trials,
        interval_confidence_level=interval_confidence_level,
        coverage_confidence_level=coverage_confidence_level,
        seed=seed,
        simulation_model=simulation_model,
    )


def certify_scenario_interval_coverage(
    *,
    reliability_points: Sequence[float],
    seed_count: int,
    scenarios_per_seed: int,
    replicates_per_scenario: int = 2,
    interval_intraseed_correlation: float = 0.05,
    simulation_intraseed_correlation_points: Sequence[float] = (0.05,),
    trials: int = 500,
    interval_confidence_level: float = 0.95,
    certificate_confidence_level: float = 0.95,
    seed: int = 0,
    simulation_models: Sequence[GateSimulationModel] = tuple(GateSimulationModel),
    source_revision: str,
    source_tree_digest: str,
    source_state: str,
    input_report_content_digests: Sequence[str],
) -> GateCoverageCertificate:
    """Certify coverage over a predeclared reliability-by-DGP grid."""

    points = sorted(set(reliability_points))
    models = sorted(set(simulation_models), key=lambda model: model.value)
    correlation_points = sorted(set(simulation_intraseed_correlation_points))
    report_digests = sorted(input_report_content_digests)
    if not points or not models or not correlation_points:
        raise ValueError(
            "coverage certificate requires reliability, correlation, and simulation-model points"
        )
    if source_revision != source_revision.strip() or not source_revision:
        raise ValueError("coverage certificate requires source and input-report provenance")
    if len(source_tree_digest) != 64 or any(
        character not in "0123456789abcdef" for character in source_tree_digest
    ):
        raise ValueError("coverage certificate requires a lowercase source-tree SHA-256 digest")
    if source_state != "clean":
        raise ValueError("coverage certificate requires a clean source tree")
    if any(
        len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest)
        for digest in report_digests
    ):
        raise ValueError("input report content digests must be lowercase SHA-256 values")
    if len(report_digests) != len(set(report_digests)):
        raise ValueError("input report content digests must be unique")
    design_point_count = len(points) * len(models) * len(correlation_points)
    design_point_coverage_confidence_level = 1.0 - (
        (1.0 - certificate_confidence_level) / design_point_count
    )
    estimates = [
        estimate_scenario_interval_coverage(
            true_scenario_reliability=reliability,
            seed_count=seed_count,
            scenarios_per_seed=scenarios_per_seed,
            replicates_per_scenario=replicates_per_scenario,
            interval_intraseed_correlation=interval_intraseed_correlation,
            simulation_intraseed_correlation=simulation_correlation,
            trials=trials,
            interval_confidence_level=interval_confidence_level,
            coverage_confidence_level=design_point_coverage_confidence_level,
            seed=(
                seed
                + point_index * len(models) * len(correlation_points)
                + correlation_index * len(models)
                + model_index
            ),
            simulation_model=model,
        )
        for point_index, reliability in enumerate(points)
        for correlation_index, simulation_correlation in enumerate(correlation_points)
        for model_index, model in enumerate(models)
    ]
    configuration = GateCoverageConfiguration(
        algorithm_version=GateCoverageAlgorithmVersion.SCENARIO_COVERAGE_GRID_2,
        source_revision=source_revision,
        source_tree_digest=source_tree_digest,
        source_state="clean",
        input_report_content_digests=report_digests,
        seed=seed,
        seed_count=seed_count,
        scenarios_per_seed=scenarios_per_seed,
        replicates_per_scenario=replicates_per_scenario,
        trials_per_design_point=trials,
        interval_confidence_level=interval_confidence_level,
        certificate_confidence_level=certificate_confidence_level,
        interval_intraseed_correlation=interval_intraseed_correlation,
        simulation_models=models,
        reliability_points=points,
        simulation_intraseed_correlation_points=correlation_points,
    )
    return GateCoverageCertificate(
        configuration=configuration,
        configuration_digest=configuration.digest(),
        estimates=estimates,
        minimum_coverage_lower_confidence_bound=min(
            estimate.coverage_lower_confidence_bound for estimate in estimates
        ),
        design_point_coverage_confidence_level=design_point_coverage_confidence_level,
    )


def estimate_live_gate_power(
    *,
    true_scenario_reliability: float,
    minimum_pass_rate_lower_bound: float,
    seed_count: int,
    scenarios_per_seed: int,
    replicates_per_scenario: int = 2,
    intraseed_correlation: float = 0.05,
    trials: int = 500,
    confidence_level: float = 0.95,
    decision_confidence_level: float = 0.95,
    seed: int = 0,
    simulation_model: GateSimulationModel = GateSimulationModel.BETA_BINOMIAL,
) -> GatePowerEstimate:
    """Estimate acceptance probability for the production live gate.

    A beta-binomial seed effect represents generator-seed difficulty. The
    simulation parameter is the exact all-replicates-pass scenario estimand
    used by the production gate, rather than a per-inference probability.
    """

    _validate_gate_design(
        true_scenario_reliability=true_scenario_reliability,
        seed_count=seed_count,
        scenarios_per_seed=scenarios_per_seed,
        replicates_per_scenario=replicates_per_scenario,
        intraseed_correlation=intraseed_correlation,
        trials=trials,
        confidence_level=confidence_level,
    )
    if not 0.0 <= minimum_pass_rate_lower_bound <= 1.0:
        raise ValueError("minimum_pass_rate_lower_bound must be between 0 and 1")
    if not 0.0 < decision_confidence_level < 1.0:
        raise ValueError("decision_confidence_level must be between 0 and 1")

    rng = random.Random(seed)
    accepted = 0
    for _ in range(trials):
        values_by_seed = _simulate_gate_outcomes(
            rng,
            true_scenario_reliability=true_scenario_reliability,
            seed_count=seed_count,
            scenarios_per_seed=scenarios_per_seed,
            replicates_per_scenario=replicates_per_scenario,
            intraseed_correlation=intraseed_correlation,
            simulation_model=simulation_model,
        )
        interval = seed_cluster_scenario_pass_interval(
            values_by_seed,
            confidence_level=confidence_level,
            intraseed_correlation=intraseed_correlation,
        )
        if interval is not None and interval.lower >= minimum_pass_rate_lower_bound:
            accepted += 1

    probability = accepted / trials
    decision_lower, decision_upper = _beta_binomial_cluster_interval(
        cluster_success_counts=[accepted],
        cluster_sizes=[trials],
        confidence_level=decision_confidence_level,
        intraseed_correlation=0.0,
    )
    return GatePowerEstimate(
        true_scenario_reliability=true_scenario_reliability,
        minimum_pass_rate_lower_bound=minimum_pass_rate_lower_bound,
        seed_count=seed_count,
        scenarios_per_seed=scenarios_per_seed,
        replicates_per_scenario=replicates_per_scenario,
        intraseed_correlation=intraseed_correlation,
        simulation_model=simulation_model,
        accepted_trials=accepted,
        estimated_acceptance_probability=probability,
        acceptance_probability_lower_bound=decision_lower,
        acceptance_probability_upper_bound=decision_upper,
        monte_carlo_standard_error=sqrt(probability * (1.0 - probability) / trials),
        trials=trials,
        confidence_level=confidence_level,
        decision_confidence_level=decision_confidence_level,
        seed=seed,
    )


def _validate_gate_design(
    *,
    true_scenario_reliability: float,
    seed_count: int,
    scenarios_per_seed: int,
    replicates_per_scenario: int,
    intraseed_correlation: float,
    trials: int,
    confidence_level: float,
) -> None:
    if not 0.0 <= true_scenario_reliability <= 1.0:
        raise ValueError("true_scenario_reliability must be between 0 and 1")
    if seed_count < 1 or scenarios_per_seed < 1 or replicates_per_scenario < 1:
        raise ValueError("seed, scenario, and replicate counts must be positive")
    if not 0.0 <= intraseed_correlation < 1.0:
        raise ValueError("intraseed_correlation must be in [0, 1)")
    if trials < 1:
        raise ValueError("trial count must be positive")
    if not 0.0 < confidence_level < 1.0:
        raise ValueError("confidence_level must be between 0 and 1")


def _simulate_gate_outcomes(
    rng: random.Random,
    *,
    true_scenario_reliability: float,
    seed_count: int,
    scenarios_per_seed: int,
    replicates_per_scenario: int,
    intraseed_correlation: float,
    simulation_model: GateSimulationModel = GateSimulationModel.BETA_BINOMIAL,
) -> dict[int, dict[str, list[float]]]:
    values_by_seed: dict[int, dict[str, list[float]]] = {}
    for run_seed in range(seed_count):
        seed_pass_rate = sample_seed_rate(
            rng,
            mean=true_scenario_reliability,
            correlation=intraseed_correlation,
            simulation_model=simulation_model,
        )
        scenarios: dict[str, list[float]] = {}
        for scenario_index in range(scenarios_per_seed):
            scenario_rate = seed_pass_rate
            if simulation_model == GateSimulationModel.FAMILY_MIXTURE:
                scenario_rate = family_mixture_rate(
                    seed_pass_rate,
                    scenario_index=scenario_index,
                    scenario_count=scenarios_per_seed,
                )
            scenario_passed = 1.0 if rng.random() < scenario_rate else 0.0
            scenarios[f"scenario_{scenario_index}"] = [scenario_passed] * replicates_per_scenario
        values_by_seed[run_seed] = scenarios
    return values_by_seed


def _wilson_one_sided_lower_bound(
    successes: int,
    trials: int,
    *,
    confidence_level: float,
) -> float:
    if trials < 1:
        raise ValueError("trials must be positive")
    probability = successes / trials
    z = NormalDist().inv_cdf(confidence_level)
    denominator = 1.0 + (z * z / trials)
    center = probability + (z * z / (2.0 * trials))
    radius = z * sqrt((probability * (1.0 - probability) / trials) + (z * z / (4.0 * trials * trials)))
    return max(0.0, (center - radius) / denominator)


def _beta_binomial_cluster_interval(
    *,
    cluster_success_counts: Sequence[int],
    cluster_sizes: Sequence[int],
    confidence_level: float,
    intraseed_correlation: float,
) -> tuple[float, float]:
    observed = sum(cluster_success_counts)
    total = sum(cluster_sizes)
    alpha = 1.0 - confidence_level
    lower = 0.0 if observed == 0 else _bisect_probability(
        lambda probability: sum(
            _clustered_total_pmf(cluster_sizes, probability, intraseed_correlation)[observed:]
        ),
        target=alpha,
        increasing=True,
    )
    upper = 1.0 if observed == total else _bisect_probability(
        lambda probability: sum(
            _clustered_total_pmf(cluster_sizes, probability, intraseed_correlation)[: observed + 1]
        ),
        target=alpha,
        increasing=False,
    )
    return lower, upper


def _bisect_probability(
    function: Callable[[float], float],
    *,
    target: float,
    increasing: bool,
    iterations: int = 50,
) -> float:
    low, high = 0.0, 1.0
    for _ in range(iterations):
        midpoint = (low + high) / 2.0
        value = function(midpoint)
        if (value < target) == increasing:
            low = midpoint
        else:
            high = midpoint
    return (low + high) / 2.0


def _clustered_total_pmf(
    cluster_sizes: Sequence[int],
    probability: float,
    intraseed_correlation: float,
) -> list[float]:
    distribution = [1.0]
    for cluster_size in cluster_sizes:
        cluster = _beta_binomial_pmf(cluster_size, probability, intraseed_correlation)
        combined = [0.0] * (len(distribution) + cluster_size)
        for left_index, left_probability in enumerate(distribution):
            for right_index, right_probability in enumerate(cluster):
                combined[left_index + right_index] += left_probability * right_probability
        distribution = combined
    total = sum(distribution)
    return [value / total for value in distribution]


def _beta_binomial_pmf(size: int, probability: float, correlation: float) -> list[float]:
    if probability <= 0.0:
        return [1.0, *([0.0] * size)]
    if probability >= 1.0:
        return [*([0.0] * size), 1.0]
    if correlation == 0.0:
        return [
            comb(size, success) * probability**success * (1.0 - probability) ** (size - success)
            for success in range(size + 1)
        ]
    concentration = (1.0 / correlation) - 1.0
    alpha = probability * concentration
    beta = (1.0 - probability) * concentration
    log_beta_denominator = lgamma(alpha) + lgamma(beta) - lgamma(alpha + beta)
    return [
        exp(
            lgamma(size + 1)
            - lgamma(success + 1)
            - lgamma(size - success + 1)
            + lgamma(success + alpha)
            + lgamma(size - success + beta)
            - lgamma(size + alpha + beta)
            - log_beta_denominator
        )
        for success in range(size + 1)
    ]


def _percentile(values: Sequence[float], probability: float) -> float:
    if not values:
        raise ValueError("percentile requires values")
    position = (len(values) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    fraction = position - lower
    return values[lower] + (values[upper] - values[lower]) * fraction
