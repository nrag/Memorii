"""Offline statistical audit for the repository-owned live gate design."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.benchmark.calibration.models import GateCoverageEstimate, GatePowerEstimate
from memorii.core.benchmark.calibration.policy import LiveCertificationPolicy
from memorii.core.benchmark.calibration.statistics import (
    estimate_live_gate_power,
    estimate_scenario_interval_coverage,
)


class LiveCertificationDesignAudit(BaseModel):
    policy_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    interval_confidence_level: float = Field(gt=0.0, lt=1.0)
    decision_point_confidence_level: float = Field(gt=0.0, lt=1.0)
    coverage_point_confidence_level: float = Field(gt=0.0, lt=1.0)
    power_estimates: list[GatePowerEstimate]
    null_acceptance_estimates: list[GatePowerEstimate]
    coverage_estimates: list[GateCoverageEstimate]
    minimum_power_lower_bound: float = Field(ge=0.0, le=1.0)
    maximum_null_acceptance_upper_bound: float = Field(ge=0.0, le=1.0)
    minimum_coverage_lower_bound: float = Field(ge=0.0, le=1.0)
    failure_reasons: list[str]
    passed: bool

    model_config = ConfigDict(extra="forbid")


def audit_live_certification_design(
    policy: LiveCertificationPolicy,
) -> LiveCertificationDesignAudit:
    """Pre-certify every declared power, null, and coverage design point."""

    interval_confidence = 1.0 - (
        (1.0 - policy.confidence_level) / (len(policy.required_families) + 1)
    )
    decision_point_count = (
        len(policy.simulation_models)
        * len(policy.simulation_intraseed_correlation_points)
        * 2
    )
    decision_confidence = 1.0 - (
        (1.0 - policy.confidence_level) / decision_point_count
    )
    decision_grid = tuple(
        (correlation, model)
        for correlation in policy.simulation_intraseed_correlation_points
        for model in policy.simulation_models
    )
    common_power = {
        "minimum_pass_rate_lower_bound": policy.minimum_pass_rate_lower_bound,
        "seed_count": len(policy.seeds),
        "scenarios_per_seed": policy.scenarios_per_replicate,
        "replicates_per_scenario": len(policy.replicates),
        "interval_intraseed_correlation": policy.interval_intraseed_correlation,
        "trials": policy.monte_carlo_trials,
        "confidence_level": interval_confidence,
        "decision_confidence_level": decision_confidence,
    }
    power_estimates = [
        estimate_live_gate_power(
            true_scenario_reliability=policy.design_target_scenario_reliability,
            simulation_intraseed_correlation=correlation,
            simulation_model=model,
            seed=policy.bootstrap_seed + index,
            **common_power,
        )
        for index, (correlation, model) in enumerate(decision_grid)
    ]
    null_acceptance_estimates = [
        estimate_live_gate_power(
            true_scenario_reliability=policy.minimum_pass_rate_lower_bound,
            simulation_intraseed_correlation=correlation,
            simulation_model=model,
            seed=policy.bootstrap_seed + len(decision_grid) + index,
            **common_power,
        )
        for index, (correlation, model) in enumerate(decision_grid)
    ]
    coverage_grid = tuple(
        (reliability, correlation, model)
        for reliability in policy.coverage_reliability_points
        for correlation in policy.simulation_intraseed_correlation_points
        for model in policy.simulation_models
    )
    coverage_confidence = 1.0 - (
        (1.0 - policy.confidence_level) / len(coverage_grid)
    )
    coverage_estimates = [
        estimate_scenario_interval_coverage(
            true_scenario_reliability=reliability,
            seed_count=len(policy.seeds),
            scenarios_per_seed=policy.scenarios_per_replicate,
            replicates_per_scenario=len(policy.replicates),
            interval_intraseed_correlation=policy.interval_intraseed_correlation,
            simulation_intraseed_correlation=correlation,
            trials=policy.monte_carlo_trials,
            interval_confidence_level=interval_confidence,
            coverage_confidence_level=coverage_confidence,
            seed=policy.bootstrap_seed + index,
            simulation_model=model,
        )
        for index, (reliability, correlation, model) in enumerate(coverage_grid)
    ]
    minimum_power = min(
        estimate.acceptance_probability_lower_bound for estimate in power_estimates
    )
    maximum_null = max(
        estimate.acceptance_probability_upper_bound
        for estimate in null_acceptance_estimates
    )
    minimum_coverage = min(
        estimate.coverage_lower_confidence_bound for estimate in coverage_estimates
    )
    failure_reasons: list[str] = []
    if minimum_power < policy.minimum_design_power:
        failure_reasons.append(
            f"insufficient_design_power:{minimum_power:.4f}<{policy.minimum_design_power:.4f}"
        )
    if maximum_null > policy.maximum_null_acceptance_probability:
        failure_reasons.append(
            "excess_null_acceptance_probability:"
            f"{maximum_null:.4f}>{policy.maximum_null_acceptance_probability:.4f}"
        )
    if minimum_coverage < policy.minimum_interval_coverage:
        failure_reasons.append(
            "insufficient_interval_coverage:"
            f"{minimum_coverage:.4f}<{policy.minimum_interval_coverage:.4f}"
        )
    return LiveCertificationDesignAudit(
        policy_digest=policy.digest(),
        interval_confidence_level=interval_confidence,
        decision_point_confidence_level=decision_confidence,
        coverage_point_confidence_level=coverage_confidence,
        power_estimates=power_estimates,
        null_acceptance_estimates=null_acceptance_estimates,
        coverage_estimates=coverage_estimates,
        minimum_power_lower_bound=minimum_power,
        maximum_null_acceptance_upper_bound=maximum_null,
        minimum_coverage_lower_bound=minimum_coverage,
        failure_reasons=failure_reasons,
        passed=not failure_reasons,
    )
