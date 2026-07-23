"""Typed policy contracts for calibration and live certification."""

from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.benchmark.calibration.models import CalibrationResponseLevel
from memorii.core.benchmark.calibration.simulation_models import GateSimulationModel
from memorii.core.benchmark.memory_evolution_sim.generation import (
    MEMORY_EVOLUTION_SCENARIO_FAMILIES,
)

DEFAULT_DECISION_COSTS: dict[str, int] = {
    "hidden_fact_hallucinated": 100,
    "hidden_fact_answer_leak": 100,
    "wrong_current_truth": 50,
    "source_trust_inversion": 40,
    "scope_leak": 35,
    "stale_memory_selected": 30,
    "wrong_entity_support_used": 30,
    "historical_truth_lost": 25,
    "missing_provenance": 10,
    "missing_conflict_relation": 20,
    "missing_relation": 10,
    "extra_provenance_noise": 2,
    "extra_context_provenance": 2,
}


class LiveCertificationPolicy(BaseModel):
    """Single source of truth for the live runtime certification design."""

    suite: str = "memory_evolution_runtime_v1"
    mode: str = "hybrid"
    profile: str = "long_horizon"
    seeds: tuple[int, ...]
    replicates: tuple[int, ...] = (0, 1)
    scenarios_per_replicate: int = Field(default=25, ge=1)
    minimum_events: int = Field(default=25, ge=1)
    maximum_events: int = Field(default=60, ge=1)
    noise_rate: float = Field(default=0.35, ge=0.0, le=1.0)
    minimum_pass_rate_lower_bound: float = Field(default=0.90, ge=0.0, le=1.0)
    minimum_family_pass_rate_lower_bound: float = Field(default=0.75, ge=0.0, le=1.0)
    minimum_family_scenarios_per_seed: int = Field(default=2, ge=1)
    minimum_seed_pass_rate: float = Field(default=0.80, ge=0.0, le=1.0)
    confidence_level: float = Field(default=0.95, gt=0.0, lt=1.0)
    design_target_scenario_reliability: float = Field(default=0.98, ge=0.0, le=1.0)
    minimum_design_power: float = Field(default=0.80, ge=0.0, le=1.0)
    maximum_null_acceptance_probability: float = Field(default=0.05, ge=0.0, le=1.0)
    minimum_interval_coverage: float = Field(default=0.90, ge=0.0, le=1.0)
    monte_carlo_trials: int = Field(default=2500, ge=1)
    interval_intraseed_correlation: float = Field(default=0.30, ge=0.0, lt=1.0)
    simulation_intraseed_correlation_points: tuple[float, ...] = (
        0.0,
        0.05,
        0.10,
        0.20,
        0.30,
    )
    simulation_models: tuple[GateSimulationModel, ...] = tuple(
        sorted(GateSimulationModel, key=lambda item: item.value)
    )
    coverage_reliability_points: tuple[float, ...] = (0.50, 0.90, 0.98)
    required_families: tuple[str, ...] = MEMORY_EVOLUTION_SCENARIO_FAMILIES
    maximum_provider_failure_rate: float = Field(default=0.05, ge=0.0, le=1.0)
    maximum_fallback_rate: float = Field(default=0.05, ge=0.0, le=1.0)
    bootstrap_seed: int = Field(default=0, ge=0)
    bootstrap_resamples: int = Field(default=2000, ge=1)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_canonical_design(self) -> LiveCertificationPolicy:
        if not self.seeds or tuple(sorted(set(self.seeds))) != self.seeds:
            raise ValueError("certification seeds must be non-empty, unique, and sorted")
        if not self.replicates or tuple(sorted(set(self.replicates))) != self.replicates:
            raise ValueError("certification replicates must be non-empty, unique, and sorted")
        if self.maximum_events < self.minimum_events:
            raise ValueError("maximum_events must be greater than or equal to minimum_events")
        if tuple(sorted(set(self.simulation_intraseed_correlation_points))) != (
            self.simulation_intraseed_correlation_points
        ):
            raise ValueError("simulation correlations must be non-empty, unique, and sorted")
        if not self.simulation_intraseed_correlation_points:
            raise ValueError("at least one simulation correlation is required")
        if max(self.simulation_intraseed_correlation_points) > self.interval_intraseed_correlation:
            raise ValueError("the interval correlation must cover every simulated dependence point")
        if tuple(sorted(set(self.simulation_models), key=lambda item: item.value)) != self.simulation_models:
            raise ValueError("simulation models must be non-empty, unique, and sorted")
        if not self.simulation_models:
            raise ValueError("at least one simulation model is required")
        if tuple(sorted(set(self.coverage_reliability_points))) != self.coverage_reliability_points:
            raise ValueError("coverage reliability points must be non-empty, unique, and sorted")
        if not self.coverage_reliability_points:
            raise ValueError("at least one coverage reliability point is required")
        if tuple(sorted(set(self.required_families))) != tuple(sorted(self.required_families)):
            raise ValueError("required families must be unique")
        return self

    def digest(self) -> str:
        payload = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def github_matrix(self) -> dict[str, list[dict[str, int]]]:
        return {
            "include": [
                {"seed": seed, "replicate": replicate}
                for seed in self.seeds
                for replicate in self.replicates
            ]
        }


DEFAULT_LIVE_CERTIFICATION_POLICY = LiveCertificationPolicy(
    seeds=(
        7,
        11,
        19,
        23,
        31,
        37,
        41,
        43,
        47,
        53,
        59,
        61,
        67,
        71,
        73,
        79,
        83,
        89,
        97,
        101,
        103,
        107,
        109,
        113,
        127,
        131,
        137,
        139,
        149,
        151,
        157,
        163,
        167,
        173,
        179,
        181,
        191,
        193,
        197,
        199,
    )
)


def response_for_failure_buckets(failure_buckets: list[str]) -> CalibrationResponseLevel:
    critical = {
        "hidden_fact_hallucinated",
        "hidden_fact_answer_leak",
        "wrong_current_truth",
        "source_trust_inversion",
        "scope_leak",
        "stale_memory_selected",
    }
    review = {
        "missing_conflict_relation",
        "missing_relation",
        "ambiguous_fact_overcommitted",
        "overconfident_wrong_answer",
        "wrong_entity_support_used",
        "historical_truth_lost",
        "missing_provenance",
    }
    buckets = set(failure_buckets)
    if buckets & critical:
        return CalibrationResponseLevel.BENCHMARK_FAIL
    if buckets & review:
        return CalibrationResponseLevel.REVIEW
    return CalibrationResponseLevel.REPORT_ONLY


def response_for_slice(
    *,
    n: int,
    ece: float | None,
    overconfident_wrong_rate: float = 0.0,
    accuracy: float | None = None,
    mean_confidence: float | None = None,
    wilson_high: float | None = None,
) -> CalibrationResponseLevel:
    if ece is None:
        return CalibrationResponseLevel.REPORT_ONLY
    materially_overconfident = (
        accuracy is not None
        and mean_confidence is not None
        and wilson_high is not None
        and mean_confidence > wilson_high + 0.05
    )
    threshold_exceeded = ece > 0.25 or overconfident_wrong_rate > 0.10
    if n >= 10 and threshold_exceeded and (materially_overconfident or overconfident_wrong_rate > 0.10):
        return CalibrationResponseLevel.BENCHMARK_FAIL
    if n >= 5 and threshold_exceeded:
        return CalibrationResponseLevel.REVIEW
    return CalibrationResponseLevel.REPORT_ONLY
