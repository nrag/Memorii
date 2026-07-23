"""Typed calibration telemetry models."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.benchmark.calibration.simulation_models import (
    GateDependenceParameterization,
    GateSimulationModel,
)


class CalibrationItemType(StrEnum):
    SOURCE_OBSERVATION = "source_observation"
    ENTITY = "entity"
    CLAIM = "claim"
    RELATION = "relation"
    ACTION = "action"
    GRAPH_NODE = "graph_node"
    GRAPH_EDGE = "graph_edge"
    ANSWER = "answer"


class CalibrationHierarchyLayer(StrEnum):
    OBSERVATION = "observation"
    EXTRACTION = "extraction"
    VALIDATION = "validation"
    EVOLUTION = "evolution"
    GRAPH = "graph"
    RETRIEVAL_DECISION = "retrieval_decision"


class CalibrationDecisionChannel(StrEnum):
    SELECTED = "selected"
    SUPPORTING = "supporting"
    REJECTED = "rejected"
    CONTEXT = "context"
    ABSTAINED = "abstained"


class CalibrationLabel(StrEnum):
    CORRECT = "correct"
    INCORRECT = "incorrect"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class CalibrationLabelSource(StrEnum):
    LATENT_ORACLE = "latent_oracle"
    PROGRAMMATIC_JUDGE = "programmatic_judge"
    HUMAN_REVIEW = "human_review"
    RUNTIME_UNKNOWN = "runtime_unknown"


class CalibrationResponseLevel(StrEnum):
    REPORT_ONLY = "report_only"
    REVIEW = "review"
    CONFIDENCE_CAP = "confidence_cap"
    ABSTAIN_THRESHOLD = "abstain_threshold"
    BENCHMARK_FAIL = "benchmark_fail"


class CalibrationStabilityStatus(StrEnum):
    ELIGIBLE = "eligible"
    INSUFFICIENT_COVERAGE = "insufficient_coverage"


class GateCoverageAlgorithmVersion(StrEnum):
    SCENARIO_COVERAGE_GRID_2 = "scenario-coverage-grid-2"


class GateCoverageCertificateVersion(StrEnum):
    CERTIFICATE_3 = "gate-coverage-certificate-3"


class DecisionAction(StrEnum):
    ANSWER_CURRENT_TRUTH = "answer_current_truth"
    ANSWER_HISTORICAL_TRUTH = "answer_historical_truth"
    SELECT_SUPPORT = "select_support"
    REJECT_STALE_FACT = "reject_stale_fact"
    EXPOSE_CONFLICT = "expose_conflict"
    ABSTAIN = "abstain"
    CONTINUE_EXECUTION_BRANCH = "continue_execution_branch"
    RECONSTRUCT_GRAPH = "reconstruct_graph"


class CalibrationLabelRecord(BaseModel):
    label: CalibrationLabel
    label_source: CalibrationLabelSource
    label_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    label_rationale: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(extra="forbid")


class CalibrationEvent(BaseModel):
    event_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    suite: str
    scenario_id: str
    checkpoint_id: str
    item_id: str
    item_type: CalibrationItemType
    hierarchy_layer: CalibrationHierarchyLayer
    decision_channel: CalibrationDecisionChannel
    confidence: float = Field(ge=0.0, le=1.0)
    label: CalibrationLabel
    label_source: CalibrationLabelSource
    label_sources: list[CalibrationLabelSource] = Field(default_factory=list)
    label_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    label_rationale: str
    label_history: list[CalibrationLabelRecord] = Field(default_factory=list)
    failure_buckets: list[str] = Field(default_factory=list)
    source_modality: str | None = None
    source_trust: int | None = None
    predicate_id: str | None = None
    scope_key: str | None = None
    lifecycle_state: str | None = None
    retrieval_view: str | None = None
    entity_ambiguity: str | None = None
    evidence_event_ids: list[str] = Field(default_factory=list)
    judge_ids: list[str] = Field(default_factory=list)
    decision_action: DecisionAction | None = None
    metadata: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")

    def model_post_init(self, __context: object) -> None:
        if not self.label_sources:
            self.label_sources.append(self.label_source)
        if not self.label_history:
            self.label_history.append(
                CalibrationLabelRecord(
                    label=self.label,
                    label_source=self.label_source,
                    label_confidence=self.label_confidence,
                    label_rationale=self.label_rationale,
                )
            )


class CalibrationSlice(BaseModel):
    slice_key: str
    slice_values: dict[str, str]
    n: int = Field(ge=0)
    scenario_count: int = Field(default=0, ge=0)
    probability_event_count: int = Field(default=0, ge=0)
    accuracy: float | None = None
    mean_confidence: float | None = None
    ece: float | None = None
    brier_score: float | None = None
    wilson_low: float | None = None
    wilson_high: float | None = None
    eligible_for_failure: bool = False
    response_level: CalibrationResponseLevel = CalibrationResponseLevel.REPORT_ONLY

    model_config = ConfigDict(extra="forbid")


class ScenarioClusterInterval(BaseModel):
    """Cluster-bootstrap uncertainty for scenario-weighted calibration."""

    estimate: float = Field(ge=0.0, le=1.0)
    lower: float = Field(ge=0.0, le=1.0)
    upper: float = Field(ge=0.0, le=1.0)
    scenario_count: int = Field(ge=1)
    observation_count: int = Field(ge=1)
    confidence_level: float = Field(default=0.95, gt=0.0, lt=1.0)
    resamples: int = Field(ge=1)
    seed: int = Field(ge=0)
    method: str = "scenario_cluster_bootstrap_percentile"

    model_config = ConfigDict(extra="forbid")


class ScenarioPassInterval(BaseModel):
    """One-sided interval for all-replicates-pass scenario reliability."""

    estimate: float = Field(ge=0.0, le=1.0)
    lower: float = Field(ge=0.0, le=1.0)
    upper: float = Field(ge=0.0, le=1.0)
    success_count: int = Field(ge=0)
    scenario_count: int = Field(ge=1)
    seed_count: int = Field(ge=1)
    observation_count: int = Field(ge=1)
    effective_sample_size: float = Field(ge=1.0)
    intraseed_correlation: float = Field(ge=0.0, lt=1.0)
    confidence_level: float = Field(default=0.95, gt=0.0, lt=1.0)
    replicate_policy: str = "all_replicates_must_pass"
    estimand: str = "scenario_all_replicates_pass_probability"
    method: str = "one_sided_beta_binomial_seed_cluster_exact"

    model_config = ConfigDict(extra="forbid")


class GatePowerEstimate(BaseModel):
    """Monte Carlo acceptance probability for a declared live-gate design."""

    true_scenario_reliability: float = Field(ge=0.0, le=1.0)
    minimum_pass_rate_lower_bound: float = Field(ge=0.0, le=1.0)
    seed_count: int = Field(ge=1)
    scenarios_per_seed: int = Field(ge=1)
    replicates_per_scenario: int = Field(ge=1)
    interval_intraseed_correlation: float = Field(ge=0.0, lt=1.0)
    target_simulation_intraseed_correlation: float = Field(ge=0.0, lt=1.0)
    realized_simulation_intraseed_correlation: float | None = Field(default=None, ge=0.0, le=1.0)
    realized_marginal_reliability: float = Field(ge=0.0, le=1.0)
    dependence_parameterization: GateDependenceParameterization
    simulation_model: GateSimulationModel
    accepted_trials: int = Field(ge=0)
    estimated_acceptance_probability: float = Field(ge=0.0, le=1.0)
    acceptance_probability_lower_bound: float = Field(ge=0.0, le=1.0)
    acceptance_probability_upper_bound: float = Field(ge=0.0, le=1.0)
    monte_carlo_standard_error: float = Field(ge=0.0)
    trials: int = Field(ge=1)
    estimand: str = "scenario_all_replicates_pass_probability"
    interval_method: str = "one_sided_beta_binomial_seed_cluster_exact"
    confidence_level: float = Field(gt=0.0, lt=1.0)
    decision_confidence_level: float = Field(gt=0.0, lt=1.0)
    seed: int = Field(ge=0)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_binomial_decision_interval(self) -> GatePowerEstimate:
        if self.accepted_trials > self.trials:
            raise ValueError("accepted_trials cannot exceed trials")
        expected = self.accepted_trials / self.trials
        if abs(self.estimated_acceptance_probability - expected) > 1e-12:
            raise ValueError("acceptance estimate must equal accepted_trials / trials")
        if not (
            self.acceptance_probability_lower_bound
            <= self.estimated_acceptance_probability
            <= self.acceptance_probability_upper_bound
        ):
            raise ValueError("acceptance estimate must lie inside its decision interval")
        expected_parameterization = {
            GateSimulationModel.BETA_BINOMIAL: GateDependenceParameterization.BETA_BINOMIAL_EXCHANGEABLE,
            GateSimulationModel.LOGISTIC_NORMAL: GateDependenceParameterization.CALIBRATED_LOGISTIC_NORMAL,
            GateSimulationModel.FAMILY_MIXTURE: GateDependenceParameterization.FAMILY_MIXTURE_NONEXCHANGEABLE,
        }[self.simulation_model]
        if self.dependence_parameterization != expected_parameterization:
            raise ValueError("dependence parameterization does not match simulation model")
        if abs(self.realized_marginal_reliability - self.true_scenario_reliability) > 1e-6:
            raise ValueError("realized marginal reliability does not match the declared estimand")
        return self


class GateCoverageEstimate(BaseModel):
    """Monte Carlo coverage audit for the declared lower confidence bound."""

    true_scenario_reliability: float = Field(ge=0.0, le=1.0)
    seed_count: int = Field(ge=1)
    scenarios_per_seed: int = Field(ge=1)
    replicates_per_scenario: int = Field(ge=1)
    interval_intraseed_correlation: float = Field(ge=0.0, lt=1.0)
    target_simulation_intraseed_correlation: float = Field(ge=0.0, lt=1.0)
    realized_simulation_intraseed_correlation: float | None = Field(default=None, ge=0.0, le=1.0)
    realized_marginal_reliability: float = Field(ge=0.0, le=1.0)
    dependence_parameterization: GateDependenceParameterization
    estimated_lower_bound_coverage: float = Field(ge=0.0, le=1.0)
    coverage_lower_confidence_bound: float = Field(ge=0.0, le=1.0)
    monte_carlo_standard_error: float = Field(ge=0.0)
    trials: int = Field(ge=1)
    interval_confidence_level: float = Field(gt=0.0, lt=1.0)
    coverage_confidence_level: float = Field(gt=0.0, lt=1.0)
    seed: int = Field(ge=0)
    estimand: str = "scenario_all_replicates_pass_probability"
    interval_method: str = "one_sided_beta_binomial_seed_cluster_exact"
    simulation_model: GateSimulationModel

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_simulation_moments(self) -> GateCoverageEstimate:
        expected_parameterization = {
            GateSimulationModel.BETA_BINOMIAL: GateDependenceParameterization.BETA_BINOMIAL_EXCHANGEABLE,
            GateSimulationModel.LOGISTIC_NORMAL: GateDependenceParameterization.CALIBRATED_LOGISTIC_NORMAL,
            GateSimulationModel.FAMILY_MIXTURE: GateDependenceParameterization.FAMILY_MIXTURE_NONEXCHANGEABLE,
        }[self.simulation_model]
        if self.dependence_parameterization != expected_parameterization:
            raise ValueError("dependence parameterization does not match simulation model")
        if abs(self.realized_marginal_reliability - self.true_scenario_reliability) > 1e-6:
            raise ValueError("realized marginal reliability does not match the declared estimand")
        correlation_is_defined = (
            self.simulation_model != GateSimulationModel.FAMILY_MIXTURE
            and self.true_scenario_reliability not in {0.0, 1.0}
        )
        if correlation_is_defined != (self.realized_simulation_intraseed_correlation is not None):
            raise ValueError("realized intraseed correlation has invalid definedness")
        return self


class GateCoverageConfiguration(BaseModel):
    """Canonical, digestible configuration for a coverage audit."""

    algorithm_version: GateCoverageAlgorithmVersion
    source_revision: str = Field(min_length=1)
    source_tree_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_state: Literal["clean"]
    input_report_content_digests: list[str] = Field(min_length=1)
    policy_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    seed: int = Field(ge=0)
    seed_count: int = Field(ge=1)
    scenarios_per_seed: int = Field(ge=1)
    replicates_per_scenario: int = Field(ge=1)
    trials_per_design_point: int = Field(ge=1)
    interval_confidence_level: float = Field(gt=0.0, lt=1.0)
    certificate_confidence_level: float = Field(gt=0.0, lt=1.0)
    interval_intraseed_correlation: float = Field(ge=0.0, lt=1.0)
    simulation_models: list[GateSimulationModel] = Field(min_length=1)
    reliability_points: list[float] = Field(min_length=1)
    simulation_intraseed_correlation_points: list[float] = Field(min_length=1)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_canonical_configuration(self) -> GateCoverageConfiguration:
        if self.source_revision != self.source_revision.strip():
            raise ValueError("source_revision must not contain surrounding whitespace")
        if any(len(value) != 64 or any(char not in "0123456789abcdef" for char in value) for value in self.input_report_content_digests):
            raise ValueError("input report content digests must be lowercase SHA-256 values")
        if self.input_report_content_digests != sorted(set(self.input_report_content_digests)):
            raise ValueError("input report content digests must be unique and sorted")
        if self.simulation_models != sorted(set(self.simulation_models), key=lambda item: item.value):
            raise ValueError("simulation models must be unique and sorted")
        if self.reliability_points != sorted(set(self.reliability_points)):
            raise ValueError("reliability points must be unique and sorted")
        if self.simulation_intraseed_correlation_points != sorted(
            set(self.simulation_intraseed_correlation_points)
        ):
            raise ValueError("simulation correlation points must be unique and sorted")
        return self

    def digest(self) -> str:
        payload = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


class GateCoverageCertificate(BaseModel):
    """Versioned robustness audit across reliability points and DGPs."""

    certificate_version: GateCoverageCertificateVersion = GateCoverageCertificateVersion.CERTIFICATE_3
    configuration: GateCoverageConfiguration
    configuration_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    estimates: list[GateCoverageEstimate] = Field(min_length=1)
    minimum_coverage_lower_confidence_bound: float = Field(ge=0.0, le=1.0)
    design_point_coverage_confidence_level: float = Field(gt=0.0, lt=1.0)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_design_grid(self) -> GateCoverageCertificate:
        if self.configuration_digest != self.configuration.digest():
            raise ValueError("configuration digest does not match the canonical configuration")
        expected_grid = Counter(
            (model, reliability, correlation)
            for model in self.configuration.simulation_models
            for reliability in self.configuration.reliability_points
            for correlation in self.configuration.simulation_intraseed_correlation_points
        )
        observed_grid = Counter(
            (
                estimate.simulation_model,
                estimate.true_scenario_reliability,
                estimate.target_simulation_intraseed_correlation,
            )
            for estimate in self.estimates
        )
        if observed_grid != expected_grid:
            raise ValueError("coverage estimates do not exactly span the declared design grid")
        expected_seeds = {
            (model, reliability, correlation): self.configuration.seed + index
            for index, (reliability, correlation, model) in enumerate(
                (reliability, correlation, model)
                for reliability in self.configuration.reliability_points
                for correlation in self.configuration.simulation_intraseed_correlation_points
                for model in self.configuration.simulation_models
            )
        }
        if any(
            estimate.seed
            != expected_seeds[
                (
                    estimate.simulation_model,
                    estimate.true_scenario_reliability,
                    estimate.target_simulation_intraseed_correlation,
                )
            ]
            for estimate in self.estimates
        ):
            raise ValueError("coverage estimate seeds do not match the canonical design grid")
        if any(
            estimate.seed_count != self.configuration.seed_count
            or estimate.scenarios_per_seed != self.configuration.scenarios_per_seed
            or estimate.replicates_per_scenario != self.configuration.replicates_per_scenario
            or estimate.interval_intraseed_correlation
            != self.configuration.interval_intraseed_correlation
            for estimate in self.estimates
        ):
            raise ValueError("coverage estimate design does not match the certificate configuration")
        if any(
            estimate.trials != self.configuration.trials_per_design_point
            for estimate in self.estimates
        ):
            raise ValueError("coverage estimate trial counts do not match the certificate")
        if any(
            estimate.interval_confidence_level != self.configuration.interval_confidence_level
            for estimate in self.estimates
        ):
            raise ValueError("interval confidence levels do not match the certificate")
        if any(
            estimate.coverage_confidence_level
            != self.design_point_coverage_confidence_level
            for estimate in self.estimates
        ):
            raise ValueError("coverage confidence levels do not match the certificate")
        observed_minimum = min(
            estimate.coverage_lower_confidence_bound for estimate in self.estimates
        )
        if abs(observed_minimum - self.minimum_coverage_lower_confidence_bound) > 1e-12:
            raise ValueError("minimum coverage bound does not match the estimates")
        expected_design_confidence = 1.0 - (
            (1.0 - self.configuration.certificate_confidence_level) / len(expected_grid)
        )
        if abs(expected_design_confidence - self.design_point_coverage_confidence_level) > 1e-12:
            raise ValueError("design-point confidence does not match the certificate configuration")
        return self


class RiskCoveragePoint(BaseModel):
    """Selective-prediction operating point for a confidence threshold."""

    accepted_count: int = Field(ge=1)
    labeled_count: int = Field(ge=1)
    coverage: float = Field(ge=0.0, le=1.0)
    selective_risk: float = Field(ge=0.0, le=1.0)
    mean_confidence: float = Field(ge=0.0, le=1.0)
    threshold: float = Field(ge=0.0, le=1.0)
    abstention_rate: float = Field(ge=0.0, le=1.0)

    model_config = ConfigDict(extra="forbid")


class CalibrationRollingWindow(BaseModel):
    """One typed calibration-drift observation over a fixed event window."""

    start_index: int = Field(ge=0)
    end_index: int = Field(ge=0)
    ece: float | None = Field(default=None, ge=0.0, le=1.0)
    brier_score: float | None = Field(default=None, ge=0.0, le=1.0)
    overconfident_wrong_rate: float = Field(ge=0.0, le=1.0)
    drift_alerts: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class CalibrationReport(BaseModel):
    event_count: int = Field(ge=0)
    labeled_event_count: int = Field(ge=0)
    probability_event_count: int = Field(default=0, ge=0)
    partial_event_count: int = Field(default=0, ge=0)
    overall_accuracy: float | None = None
    ece: float | None = None
    brier_score: float | None = None
    overconfident_wrong_count: int = Field(default=0, ge=0)
    low_confidence_correct_count: int = Field(default=0, ge=0)
    hidden_hallucination_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    ambiguous_overcommit_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    worst_slices: list[CalibrationSlice] = Field(default_factory=list)
    rolling_windows: dict[str, list[CalibrationRollingWindow]] = Field(default_factory=dict)
    response_recommendations: dict[str, int] = Field(default_factory=dict)
    label_source_counts: dict[str, int] = Field(default_factory=dict)
    hierarchy_layer_counts: dict[str, int] = Field(default_factory=dict)
    scenario_cluster_intervals: dict[str, ScenarioClusterInterval] = Field(default_factory=dict)
    risk_coverage: list[RiskCoveragePoint] = Field(default_factory=list)
    abstention_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    selective_risk_at_full_coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    input_telemetry_count: int = Field(default=0, ge=0)
    input_telemetry_by_type: dict[str, int] = Field(default_factory=dict)
    scenario_count: int = Field(default=0, ge=0)
    minimum_scenario_count: int = Field(default=30, ge=1)
    stability_status: CalibrationStabilityStatus = CalibrationStabilityStatus.INSUFFICIENT_COVERAGE

    model_config = ConfigDict(extra="forbid")


class DecisionCostReport(BaseModel):
    decision_cost_total: float
    decision_cost_mean: float
    cost_by_failure_bucket: dict[str, float] = Field(default_factory=dict)
    cost_by_checkpoint_type: dict[str, float] = Field(default_factory=dict)
    cost_by_source_modality: dict[str, float] = Field(default_factory=dict)
    cost_by_decision_action: dict[str, float] = Field(default_factory=dict)
    regret_total: float = 0.0
    regret_mean: float = 0.0

    model_config = ConfigDict(extra="forbid")
