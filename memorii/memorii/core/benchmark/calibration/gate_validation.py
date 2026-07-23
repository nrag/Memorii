"""Input validation for live-certification gate evaluation."""

from __future__ import annotations

from collections.abc import Sequence

from memorii.core.benchmark.calibration.simulation_models import GateSimulationModel


def validate_live_gate_configuration(
    *,
    minimum_seed_count: int,
    minimum_scenarios_per_replicate: int,
    minimum_replicates_per_seed: int,
    minimum_pass_rate_lower_bound: float,
    minimum_family_pass_rate_lower_bound: float,
    minimum_family_scenarios_per_seed: int,
    minimum_seed_pass_rate: float,
    maximum_provider_failure_rate: float,
    maximum_fallback_rate: float,
    confidence_level: float,
    design_target_scenario_reliability: float,
    minimum_design_power: float,
    maximum_null_acceptance_probability: float,
    minimum_interval_coverage: float,
    intraseed_correlation: float,
    simulation_intraseed_correlation_points: Sequence[float],
    simulation_models: Sequence[GateSimulationModel],
    coverage_reliability_points: Sequence[float],
) -> tuple[tuple[float, ...], tuple[GateSimulationModel, ...], tuple[float, ...]]:
    probability_values = {
        "minimum_pass_rate_lower_bound": minimum_pass_rate_lower_bound,
        "minimum_family_pass_rate_lower_bound": minimum_family_pass_rate_lower_bound,
        "minimum_seed_pass_rate": minimum_seed_pass_rate,
        "maximum_provider_failure_rate": maximum_provider_failure_rate,
        "maximum_fallback_rate": maximum_fallback_rate,
        "design_target_scenario_reliability": design_target_scenario_reliability,
        "minimum_design_power": minimum_design_power,
        "maximum_null_acceptance_probability": maximum_null_acceptance_probability,
        "minimum_interval_coverage": minimum_interval_coverage,
    }
    for name, value in probability_values.items():
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} must be between 0 and 1")
    if not 0.0 < confidence_level < 1.0:
        raise ValueError("confidence_level must be between 0 and 1")
    if not 0.0 <= intraseed_correlation < 1.0:
        raise ValueError("intraseed_correlation must be in [0, 1)")
    if minimum_family_scenarios_per_seed < 1:
        raise ValueError("minimum_family_scenarios_per_seed must be positive")
    if minimum_seed_count < 1 or minimum_scenarios_per_replicate < 1 or minimum_replicates_per_seed < 1:
        raise ValueError("minimum seed, replicate, and scenario counts must be positive")

    correlation_points = tuple(sorted(set(simulation_intraseed_correlation_points)))
    declared_models = tuple(sorted(set(simulation_models), key=lambda item: item.value))
    reliability_points = tuple(sorted(set(coverage_reliability_points)))
    if not correlation_points or not declared_models or not reliability_points:
        raise ValueError("statistical design grids must be non-empty")
    if max(correlation_points) > intraseed_correlation:
        raise ValueError("interval correlation must cover every simulated dependence point")
    return correlation_points, declared_models, reliability_points


def resolve_live_gate_source_binding(
    *,
    report_revisions: set[str],
    report_tree_digests: set[str],
    report_states: set[str],
    requested_revision: str | None,
) -> tuple[str | None, str, bool]:
    if len(report_revisions) > 1:
        raise ValueError(f"live gate input reports contain mixed source revisions: {sorted(report_revisions)!r}")
    report_revision = next(iter(report_revisions), None)
    if requested_revision is not None and report_revision is not None and requested_revision != report_revision:
        raise ValueError(
            "live gate source revision does not match input reports: "
            f"requested={requested_revision!r} report={report_revision!r}"
        )
    if len(report_tree_digests) != 1:
        raise ValueError(
            "live gate input reports contain mixed source-tree digests: "
            f"{sorted(report_tree_digests)!r}"
        )
    return (
        requested_revision or report_revision,
        next(iter(report_tree_digests)),
        report_states == {"clean"},
    )
