"""Calibrated data-generating processes for live-gate design audits."""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from math import exp, log
from statistics import NormalDist


class GateSimulationModel(StrEnum):
    BETA_BINOMIAL = "beta_binomial"
    LOGISTIC_NORMAL = "logistic_normal"
    FAMILY_MIXTURE = "family_mixture"


class GateDependenceParameterization(StrEnum):
    BETA_BINOMIAL_EXCHANGEABLE = "beta_binomial_exchangeable_seed_effect"
    CALIBRATED_LOGISTIC_NORMAL = "calibrated_logistic_normal_seed_effect"
    FAMILY_MIXTURE_NONEXCHANGEABLE = (
        "beta_seed_effect_plus_balanced_nonexchangeable_family_heterogeneity"
    )


@dataclass(frozen=True)
class SimulationModelMoments:
    marginal_reliability: float
    intraseed_correlation: float | None
    dependence_parameterization: GateDependenceParameterization


def sample_seed_rate(
    rng: random.Random,
    *,
    mean: float,
    correlation: float,
    simulation_model: GateSimulationModel,
) -> float:
    """Sample a seed-level pass rate from a calibrated DGP."""

    if simulation_model in {
        GateSimulationModel.BETA_BINOMIAL,
        GateSimulationModel.FAMILY_MIXTURE,
    }:
        return _sample_beta_rate(rng, mean=mean, correlation=correlation)
    if mean in {0.0, 1.0} or correlation == 0.0:
        return mean
    intercept, sigma = calibrated_logistic_normal_parameters(mean, correlation)
    return _sigmoid(intercept + rng.gauss(0.0, sigma))


def simulation_model_moments(
    *,
    mean: float,
    correlation: float,
    simulation_model: GateSimulationModel,
) -> SimulationModelMoments:
    """Return population moments the DGP actually represents.

    The family-mixture model deliberately adds scenario-family heterogeneity,
    so one exchangeable within-seed ICC is not a valid summary for that DGP.
    """

    if simulation_model == GateSimulationModel.LOGISTIC_NORMAL:
        if mean in {0.0, 1.0}:
            return SimulationModelMoments(
                marginal_reliability=mean,
                intraseed_correlation=None,
                dependence_parameterization=GateDependenceParameterization.CALIBRATED_LOGISTIC_NORMAL,
            )
        if correlation == 0.0:
            return SimulationModelMoments(
                marginal_reliability=mean,
                intraseed_correlation=0.0,
                dependence_parameterization=GateDependenceParameterization.CALIBRATED_LOGISTIC_NORMAL,
            )
        intercept, sigma = calibrated_logistic_normal_parameters(mean, correlation)
        marginal, realized_correlation = _logistic_normal_moments(intercept, sigma)
        return SimulationModelMoments(
            marginal_reliability=marginal,
            intraseed_correlation=realized_correlation,
            dependence_parameterization=GateDependenceParameterization.CALIBRATED_LOGISTIC_NORMAL,
        )
    if simulation_model == GateSimulationModel.FAMILY_MIXTURE:
        return SimulationModelMoments(
            marginal_reliability=mean,
            intraseed_correlation=None,
            dependence_parameterization=GateDependenceParameterization.FAMILY_MIXTURE_NONEXCHANGEABLE,
        )
    realized_correlation = None if mean in {0.0, 1.0} else correlation
    return SimulationModelMoments(
        marginal_reliability=mean,
        intraseed_correlation=realized_correlation,
        dependence_parameterization=GateDependenceParameterization.BETA_BINOMIAL_EXCHANGEABLE,
    )


@lru_cache(maxsize=256)
def calibrated_logistic_normal_parameters(mean: float, correlation: float) -> tuple[float, float]:
    """Solve logistic-normal parameters for marginal mean and Bernoulli ICC."""

    if not 0.0 < mean < 1.0:
        raise ValueError("logistic-normal calibration requires a mean strictly between zero and one")
    if not 0.0 <= correlation < 1.0:
        raise ValueError("correlation must be in [0, 1)")
    if correlation == 0.0:
        return log(mean / (1.0 - mean)), 0.0

    low_sigma = 0.0
    high_sigma = 1.0
    while _correlation_for(mean, high_sigma) < correlation:
        high_sigma *= 2.0
        if high_sigma > 64.0:
            raise ValueError("requested logistic-normal correlation could not be calibrated")
    for _ in range(60):
        sigma = (low_sigma + high_sigma) / 2.0
        if _correlation_for(mean, sigma) < correlation:
            low_sigma = sigma
        else:
            high_sigma = sigma
    sigma = (low_sigma + high_sigma) / 2.0
    return _calibrated_intercept(mean, sigma), sigma


def family_mixture_rate(
    seed_rate: float,
    *,
    scenario_index: int,
    scenario_count: int,
) -> float:
    """Return balanced family rates whose finite-grid mean equals the seed rate."""

    if scenario_count % 2 == 1 and scenario_index == scenario_count - 1:
        return seed_rate
    offset = min(0.15, seed_rate, 1.0 - seed_rate)
    return seed_rate + (offset if scenario_index % 2 else -offset)


def _sample_beta_rate(rng: random.Random, *, mean: float, correlation: float) -> float:
    if mean in {0.0, 1.0} or correlation == 0.0:
        return mean
    concentration = (1.0 / correlation) - 1.0
    return rng.betavariate(mean * concentration, (1.0 - mean) * concentration)


@lru_cache(maxsize=512)
def _calibrated_intercept(mean: float, sigma: float) -> float:
    low, high = -40.0, 40.0
    for _ in range(70):
        midpoint = (low + high) / 2.0
        marginal, _correlation = _logistic_normal_moments(midpoint, sigma)
        if marginal < mean:
            low = midpoint
        else:
            high = midpoint
    return (low + high) / 2.0


def _correlation_for(mean: float, sigma: float) -> float:
    intercept = _calibrated_intercept(mean, sigma)
    _marginal, correlation = _logistic_normal_moments(intercept, sigma)
    return correlation


def _logistic_normal_moments(intercept: float, sigma: float) -> tuple[float, float]:
    probabilities = [_sigmoid(intercept + sigma * value) for value in _normal_quantiles()]
    marginal = sum(probabilities) / len(probabilities)
    second_moment = sum(value * value for value in probabilities) / len(probabilities)
    denominator = marginal * (1.0 - marginal)
    correlation = 0.0 if denominator == 0.0 else (second_moment - marginal * marginal) / denominator
    return marginal, min(1.0, max(0.0, correlation))


@lru_cache(maxsize=1)
def _normal_quantiles() -> tuple[float, ...]:
    normal = NormalDist()
    return tuple(normal.inv_cdf((index + 0.5) / 512.0) for index in range(512))


def _sigmoid(value: float) -> float:
    if value >= 0.0:
        inverse = exp(-value)
        return 1.0 / (1.0 + inverse)
    positive = exp(value)
    return positive / (1.0 + positive)
