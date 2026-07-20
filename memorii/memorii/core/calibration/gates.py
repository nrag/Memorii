"""Statistical acceptance gates for live memory-evolution benchmark runs."""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.benchmark.artifact_rows import BenchmarkReportSummary
from memorii.core.benchmark.artifact_validation import validate_memory_evolution_run
from memorii.core.calibration.models import GateCoverageCertificate, GatePowerEstimate, ScenarioPassInterval
from memorii.core.calibration.simulation_models import GateSimulationModel
from memorii.core.calibration.statistics import (
    certify_scenario_interval_coverage,
    estimate_live_gate_power,
    seed_cluster_scenario_pass_interval,
)

NonNegativeCount: TypeAlias = Annotated[int, Field(ge=0)]
CountMap: TypeAlias = dict[str, NonNegativeCount]


class PairedDifferenceInterval(BaseModel):
    """Percentile interval for paired candidate-minus-baseline outcomes."""

    estimate: float
    lower: float
    upper: float
    pair_count: int = Field(ge=1)
    confidence_level: float = Field(gt=0.0, lt=1.0)
    resamples: int = Field(ge=1)
    seed: int = Field(ge=0)

    model_config = ConfigDict(extra="forbid")


class LiveGateSummary(BaseModel):
    """Auditable result of a multi-seed live benchmark gate."""

    suite: str
    mode: str
    profile: str
    run_count: int = Field(ge=0)
    seed_count: int = Field(ge=0)
    replicate_count: int = Field(ge=0)
    scenario_count: int = Field(ge=0)
    minimum_seed_count: int = Field(ge=1)
    minimum_scenarios_per_replicate: int = Field(ge=1)
    minimum_replicates_per_seed: int = Field(ge=1)
    scenario_pass_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    scenario_pass_interval: ScenarioPassInterval | None = None
    family_pass_intervals: dict[str, ScenarioPassInterval] = Field(default_factory=dict)
    family_scenario_counts: CountMap = Field(default_factory=dict)
    required_families: list[str] = Field(default_factory=list)
    baseline_difference_interval: PairedDifferenceInterval | None = None
    minimum_pass_rate_lower_bound: float = Field(ge=0.0, le=1.0)
    minimum_family_pass_rate_lower_bound: float = Field(ge=0.0, le=1.0)
    minimum_family_scenarios_per_seed: int = Field(ge=1)
    minimum_seed_pass_rate: float = Field(ge=0.0, le=1.0)
    confidence_level: float = Field(gt=0.0, lt=1.0)
    intraseed_correlation: float = Field(ge=0.0, lt=1.0)
    seed_pass_rates: dict[str, float] = Field(default_factory=dict)
    leave_one_seed_out_lower_bounds: dict[str, float] = Field(default_factory=dict)
    design_power_estimates: list[GatePowerEstimate] = Field(default_factory=list)
    null_acceptance_estimates: list[GatePowerEstimate] = Field(default_factory=list)
    interval_coverage_certificate: GateCoverageCertificate | None = None
    source_revision: str | None = None
    source_tree_digest: str | None = None
    source_state: Literal["clean"] | None = None
    minimum_design_power: float = Field(ge=0.0, le=1.0)
    maximum_null_acceptance_probability: float = Field(ge=0.0, le=1.0)
    minimum_interval_coverage: float = Field(ge=0.0, le=1.0)
    maximum_provider_failure_rate: float = Field(ge=0.0, le=1.0)
    maximum_fallback_rate: float = Field(ge=0.0, le=1.0)
    provider_failure_rate: float = Field(ge=0.0, le=1.0)
    fallback_rate: float = Field(ge=0.0, le=1.0)
    critical_failure_bucket_counts: CountMap = Field(default_factory=dict)
    failure_reasons: list[str] = Field(default_factory=list)
    passed: bool

    model_config = ConfigDict(extra="forbid")


def load_live_reports(
    root: Path,
    *,
    suite: str,
    mode: str,
    profile: str,
) -> list[BenchmarkReportSummary]:
    reports: list[BenchmarkReportSummary] = []
    for report_path in sorted(root.glob(f"{suite}/{mode}/**/report.json")):
        report = validate_memory_evolution_run(report_path.parent, suite=suite)
        if report.profile != profile:
            continue
        if report.dry_run or report.execution_source == "fake_oracle":
            raise ValueError(f"live gate received a dry-run/fake-oracle report: {report_path}")
        if report.execution_source != "live_llm":
            raise ValueError(f"live gate requires execution_source=live_llm: {report_path}")
        if report.provider_successes + report.provider_failures <= 0:
            raise ValueError(f"live gate report contains no provider calls: {report_path}")
        if report.mode != mode:
            raise ValueError(f"report mode {report.mode!r} does not match requested mode {mode!r}: {report_path}")
        reports.append(report)
    return reports


def evaluate_live_gate(
    reports: Sequence[BenchmarkReportSummary],
    *,
    suite: str,
    mode: str,
    profile: str,
    minimum_seed_count: int = 10,
    minimum_scenarios_per_replicate: int = 25,
    minimum_replicates_per_seed: int = 2,
    minimum_pass_rate_lower_bound: float = 0.90,
    minimum_family_pass_rate_lower_bound: float = 0.75,
    minimum_family_scenarios_per_seed: int = 2,
    minimum_seed_pass_rate: float = 0.0,
    maximum_provider_failure_rate: float = 0.05,
    maximum_fallback_rate: float = 0.05,
    baseline_reports: Sequence[BenchmarkReportSummary] = (),
    bootstrap_seed: int = 0,
    bootstrap_resamples: int = 2000,
    confidence_level: float = 0.95,
    design_target_scenario_reliability: float = 0.98,
    minimum_design_power: float = 0.0,
    maximum_null_acceptance_probability: float = 1.0,
    minimum_interval_coverage: float = 0.0,
    design_trials: int = 200,
    intraseed_correlation: float = 0.05,
    required_families: Sequence[str] = (),
    source_revision: str | None = None,
) -> LiveGateSummary:
    if not 0.0 <= minimum_pass_rate_lower_bound <= 1.0:
        raise ValueError("minimum_pass_rate_lower_bound must be between 0 and 1")
    if not 0.0 < confidence_level < 1.0:
        raise ValueError("confidence_level must be between 0 and 1")
    for name, value in (
        ("minimum_seed_pass_rate", minimum_seed_pass_rate),
        ("design_target_scenario_reliability", design_target_scenario_reliability),
        ("minimum_design_power", minimum_design_power),
        ("maximum_null_acceptance_probability", maximum_null_acceptance_probability),
        ("minimum_interval_coverage", minimum_interval_coverage),
    ):
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} must be between 0 and 1")
    if not 0.0 <= intraseed_correlation < 1.0:
        raise ValueError("intraseed_correlation must be in [0, 1)")
    if not 0.0 <= minimum_family_pass_rate_lower_bound <= 1.0:
        raise ValueError("minimum_family_pass_rate_lower_bound must be between 0 and 1")
    if minimum_family_scenarios_per_seed < 1:
        raise ValueError("minimum_family_scenarios_per_seed must be positive")
    if not 0.0 <= maximum_provider_failure_rate <= 1.0:
        raise ValueError("maximum_provider_failure_rate must be between 0 and 1")
    if not 0.0 <= maximum_fallback_rate <= 1.0:
        raise ValueError("maximum_fallback_rate must be between 0 and 1")
    if minimum_seed_count < 1 or minimum_scenarios_per_replicate < 1 or minimum_replicates_per_seed < 1:
        raise ValueError("minimum seed, replicate, and scenario counts must be positive")
    by_run: dict[str, list[dict[str, object]]] = {}
    runs_by_seed: dict[int, set[int]] = {}
    failure_counts: dict[str, int] = {}
    provider_failures = 0
    provider_calls = 0
    fallbacks = 0
    fixture_fingerprints: set[str] = set()
    evaluation_fingerprints: set[str] = set()
    system_fingerprints: set[str] = set()
    report_content_digests: set[str] = set()
    report_source_revisions: set[str] = set()
    report_source_tree_digests: set[str] = set()
    report_source_states: set[str] = set()
    failure_reasons: list[str] = []
    required_family_set = set(required_families)
    families_by_run: dict[str, dict[str, int]] = {}
    for report in reports:
        if report.suite != suite or report.mode != mode or report.profile != profile:
            raise ValueError(f"report identity does not match gate: {report.suite}/{report.mode}/{report.profile}")
        if report.dry_run or report.execution_source != "live_llm":
            failure_reasons.append("non_live_execution_source")
        if not report.has_valid_content_digest():
            raise ValueError(f"report content digest is invalid: {report.run_id}")
        if report.report_content_digest in report_content_digests:
            failure_reasons.append(f"duplicate_report_content_digest:{report.report_content_digest}")
        report_content_digests.add(report.report_content_digest)
        report_source_revisions.add(report.source_revision)
        report_source_tree_digests.add(report.source_tree_digest)
        report_source_states.add(report.source_state)
        rows = [row.model_dump(mode="python") for row in report.scenario_results]
        run_key = f"{report.seed}:{report.inference_replicate}"
        if run_key in by_run:
            failure_reasons.append(f"duplicate_seed_replicate:{run_key}")
        by_run.setdefault(run_key, []).extend(rows)
        run_family_counts = families_by_run.setdefault(run_key, {})
        for row in rows:
            family = str(row.get("family", ""))
            if family:
                run_family_counts[family] = run_family_counts.get(family, 0) + 1
        runs_by_seed.setdefault(report.seed, set()).add(report.inference_replicate)
        fixture_fingerprints.add(report.fixture_fingerprint)
        evaluation_fingerprints.add(report.evaluation_fingerprint)
        system_fingerprints.add(report.system_fingerprint)
        for bucket, count in report.critical_failure_bucket_counts.items():
            failure_counts[bucket] = failure_counts.get(bucket, 0) + count
        provider_failures += report.provider_failures
        provider_calls += report.provider_successes + report.provider_failures
        fallbacks += report.fallbacks
    if len(report_source_revisions) > 1:
        raise ValueError(f"live gate input reports contain mixed source revisions: {sorted(report_source_revisions)!r}")
    report_source_revision = next(iter(report_source_revisions), None)
    if source_revision is not None and report_source_revision is not None and source_revision != report_source_revision:
        raise ValueError(
            "live gate source revision does not match input reports: "
            f"requested={source_revision!r} report={report_source_revision!r}"
        )
    bound_source_revision = source_revision or report_source_revision
    if report_source_states != {"clean"}:
        failure_reasons.append(
            "non_certifying_source_state:" + ",".join(sorted(report_source_states))
        )
    if len(report_source_tree_digests) != 1:
        raise ValueError(
            "live gate input reports contain mixed source-tree digests: "
            f"{sorted(report_source_tree_digests)!r}"
        )
    bound_source_tree_digest = next(iter(report_source_tree_digests), None)

    values_by_seed_scenario: dict[int, dict[str, list[float]]] = {}
    family_values: dict[str, dict[int, dict[str, list[float]]]] = {}
    duplicate_scenario_keys: set[str] = set()
    semantic_world_units: dict[str, set[tuple[int, str]]] = {}
    for run_key, rows in by_run.items():
        seed_text, _replicate_text = run_key.split(":", maxsplit=1)
        seed_scenarios = values_by_seed_scenario.setdefault(int(seed_text), {})
        seen_scenarios: set[str] = set()
        for row in rows:
            scenario_id = str(row.get("scenario_id", ""))
            if not scenario_id:
                raise ValueError(f"live report run {run_key} contains a scenario without an ID")
            if scenario_id in seen_scenarios:
                duplicate_scenario_keys.add(f"{run_key}:{scenario_id}")
                continue
            seen_scenarios.add(scenario_id)
            semantic_world_fingerprint = str(row.get("semantic_world_fingerprint", ""))
            if not semantic_world_fingerprint:
                raise ValueError(f"live report run {run_key} contains a scenario without a semantic-world fingerprint")
            semantic_world_units.setdefault(semantic_world_fingerprint, set()).add((int(seed_text), scenario_id))
            seed_scenarios.setdefault(scenario_id, []).append(1.0 if row.get("success") is True else 0.0)
            family = str(row.get("family", ""))
            if family:
                family_values.setdefault(family, {}).setdefault(int(seed_text), {}).setdefault(scenario_id, []).append(
                    1.0 if row.get("success") is True else 0.0
                )
    family_count = len(required_family_set or family_values)
    endpoint_count = max(1, family_count + 1)
    simultaneous_confidence = 1.0 - ((1.0 - confidence_level) / endpoint_count)
    interval = seed_cluster_scenario_pass_interval(
        values_by_seed_scenario,
        confidence_level=simultaneous_confidence,
        intraseed_correlation=intraseed_correlation,
    )
    scenario_pass_rate = interval.estimate if interval else None
    family_intervals = {
        family: family_interval
        for family, values in sorted(family_values.items())
        if (
            family_interval := seed_cluster_scenario_pass_interval(
                values,
                confidence_level=simultaneous_confidence,
                intraseed_correlation=intraseed_correlation,
            )
        )
        is not None
    }
    family_scenario_counts = {
        family: sum(len(scenarios) for scenarios in values.values()) for family, values in sorted(family_values.items())
    }
    seed_pass_rates: dict[str, float] = {}
    for run_seed, scenarios in sorted(values_by_seed_scenario.items()):
        seed_interval = seed_cluster_scenario_pass_interval(
            {run_seed: scenarios},
            confidence_level=confidence_level,
            intraseed_correlation=0.0,
        )
        if seed_interval is not None:
            seed_pass_rates[str(run_seed)] = seed_interval.estimate
            if seed_interval.estimate < minimum_seed_pass_rate:
                failure_reasons.append(
                    f"seed_pass_rate:{run_seed}:{seed_interval.estimate:.4f}<{minimum_seed_pass_rate:.4f}"
                )
    leave_one_seed_out_lower_bounds: dict[str, float] = {}
    if len(values_by_seed_scenario) > 1:
        for omitted_seed in sorted(values_by_seed_scenario):
            reduced = {seed: scenarios for seed, scenarios in values_by_seed_scenario.items() if seed != omitted_seed}
            sensitivity_interval = seed_cluster_scenario_pass_interval(
                reduced,
                confidence_level=confidence_level,
                intraseed_correlation=intraseed_correlation,
            )
            if sensitivity_interval is not None:
                leave_one_seed_out_lower_bounds[str(omitted_seed)] = sensitivity_interval.lower
    for run_key, counts in sorted(families_by_run.items()):
        missing = sorted(required_family_set - set(counts))
        if missing:
            failure_reasons.append(f"missing_required_families:{run_key}:{','.join(missing)}")
        unexpected = sorted(set(counts) - required_family_set) if required_family_set else []
        if unexpected:
            failure_reasons.append(f"unexpected_scenario_families:{run_key}:{','.join(unexpected)}")
    for family in sorted(required_family_set):
        values = family_values.get(family, {})
        underpowered = sorted(
            seed for seed in runs_by_seed if len(values.get(seed, {})) < minimum_family_scenarios_per_seed
        )
        if underpowered:
            failure_reasons.append(
                f"insufficient_family_scenarios_per_seed:{family}:" + ",".join(str(seed) for seed in underpowered)
            )
        family_interval = family_intervals.get(family)
        if family_interval is None:
            failure_reasons.append(f"no_family_outcomes:{family}")
        elif family_interval.lower < minimum_family_pass_rate_lower_bound:
            failure_reasons.append(
                f"family_pass_rate_lower_bound:{family}:"
                f"{family_interval.lower:.4f}<{minimum_family_pass_rate_lower_bound:.4f}"
            )
    if len(runs_by_seed) < minimum_seed_count:
        failure_reasons.append(f"insufficient_seed_count:{len(runs_by_seed)}<{minimum_seed_count}")
    under_replicated_seeds = sorted(
        seed for seed, replicates in runs_by_seed.items() if len(replicates) < minimum_replicates_per_seed
    )
    if under_replicated_seeds:
        failure_reasons.append(
            "insufficient_replicates_per_seed:" + ",".join(str(seed) for seed in under_replicated_seeds)
        )
    if duplicate_scenario_keys:
        failure_reasons.append("duplicate_scenario_outcomes")
    duplicate_semantic_worlds = sorted(
        fingerprint for fingerprint, units in semantic_world_units.items() if len(units) > 1
    )
    if duplicate_semantic_worlds:
        failure_reasons.append("duplicate_semantic_worlds")
    if len(fixture_fingerprints) > 1:
        failure_reasons.append("mixed_fixture_configurations")
    if len(evaluation_fingerprints) > 1:
        failure_reasons.append("mixed_evaluation_configurations")
    if len(system_fingerprints) > 1:
        failure_reasons.append("mixed_system_configurations")
    underpowered_seeds = sorted(
        run_key for run_key, rows in by_run.items() if len(rows) < minimum_scenarios_per_replicate
    )
    if underpowered_seeds:
        failure_reasons.append("insufficient_scenarios_per_replicate:" + ",".join(underpowered_seeds))
    if interval is None:
        failure_reasons.append("no_scenario_outcomes")
    elif interval.lower < minimum_pass_rate_lower_bound:
        failure_reasons.append(f"pass_rate_lower_bound:{interval.lower:.4f}<{minimum_pass_rate_lower_bound:.4f}")
    if failure_counts:
        failure_reasons.append("critical_failure_buckets_present")

    baseline_interval: PairedDifferenceInterval | None = None
    if baseline_reports:
        candidate_outcomes = _scenario_outcomes(reports)
        baseline_outcomes = _scenario_outcomes(baseline_reports)
        if set(candidate_outcomes) != set(baseline_outcomes):
            failure_reasons.append("baseline_incomplete_pairing")
        baseline_fixture_fingerprints = {report.fixture_fingerprint for report in baseline_reports}
        baseline_evaluation_fingerprints = {report.evaluation_fingerprint for report in baseline_reports}
        if baseline_fixture_fingerprints != fixture_fingerprints:
            failure_reasons.append("baseline_fixture_configuration_mismatch")
        elif baseline_evaluation_fingerprints != evaluation_fingerprints:
            failure_reasons.append("baseline_evaluation_configuration_mismatch")
        elif set(candidate_outcomes) == set(baseline_outcomes):
            baseline_interval = _paired_baseline_interval(
                reports,
                baseline_reports,
                seed=bootstrap_seed,
                resamples=bootstrap_resamples,
                confidence_level=confidence_level,
            )
            if baseline_interval is None:
                failure_reasons.append("baseline_pairing_unavailable")
    if baseline_interval is not None and baseline_interval.lower < -0.05:
        failure_reasons.append(f"baseline_noninferiority:{baseline_interval.lower:.4f}<-0.0500")
    provider_failure_rate = provider_failures / max(1, provider_calls)
    fallback_rate = fallbacks / max(1, provider_calls)
    if provider_calls == 0:
        failure_reasons.append("no_live_provider_calls")
    if provider_failure_rate > maximum_provider_failure_rate:
        failure_reasons.append(f"provider_failure_rate:{provider_failure_rate:.4f}>{maximum_provider_failure_rate:.4f}")
    if fallback_rate > maximum_fallback_rate:
        failure_reasons.append(f"fallback_rate:{fallback_rate:.4f}>{maximum_fallback_rate:.4f}")
    design_power_estimates: list[GatePowerEstimate] = []
    null_acceptance_estimates: list[GatePowerEstimate] = []
    interval_coverage_certificate: GateCoverageCertificate | None = None
    design_is_enforced = (
        minimum_design_power > 0.0
        or maximum_null_acceptance_probability < 1.0
        or minimum_interval_coverage > 0.0
    )
    if design_is_enforced and values_by_seed_scenario and report_source_states == {"clean"}:
        if bound_source_revision is None:
            raise ValueError("design certification requires a source-bound input report")
        planned_seed_count = minimum_seed_count
        scenarios_per_seed = minimum_scenarios_per_replicate
        replicates_per_scenario = minimum_replicates_per_seed
        simulation_models = sorted(GateSimulationModel, key=lambda item: item.value)
        decision_point_count = len(simulation_models) * 2
        decision_confidence_level = 1.0 - ((1.0 - confidence_level) / decision_point_count)
        power_args = {
            "minimum_pass_rate_lower_bound": minimum_pass_rate_lower_bound,
            "seed_count": planned_seed_count,
            "scenarios_per_seed": scenarios_per_seed,
            "replicates_per_scenario": replicates_per_scenario,
            "intraseed_correlation": intraseed_correlation,
            "trials": design_trials,
            "confidence_level": confidence_level,
            "decision_confidence_level": decision_confidence_level,
        }
        design_power_estimates = [
            estimate_live_gate_power(
                true_scenario_reliability=design_target_scenario_reliability,
                simulation_model=simulation_model,
                seed=bootstrap_seed + index,
                **power_args,
            )
            for index, simulation_model in enumerate(simulation_models)
        ]
        null_acceptance_estimates = [
            estimate_live_gate_power(
                true_scenario_reliability=minimum_pass_rate_lower_bound,
                simulation_model=simulation_model,
                seed=bootstrap_seed + len(simulation_models) + index,
                **power_args,
            )
            for index, simulation_model in enumerate(simulation_models)
        ]
        interval_coverage_certificate = certify_scenario_interval_coverage(
            reliability_points=sorted(
                {
                    0.50,
                    minimum_pass_rate_lower_bound,
                    design_target_scenario_reliability,
                }
            ),
            seed_count=planned_seed_count,
            scenarios_per_seed=scenarios_per_seed,
            replicates_per_scenario=replicates_per_scenario,
            interval_intraseed_correlation=intraseed_correlation,
            simulation_intraseed_correlation_points=[intraseed_correlation],
            trials=design_trials,
            interval_confidence_level=confidence_level,
            certificate_confidence_level=confidence_level,
            seed=bootstrap_seed,
            source_revision=bound_source_revision,
            source_tree_digest=bound_source_tree_digest or "",
            source_state="clean" if report_source_states == {"clean"} else "dirty",
            input_report_content_digests=sorted(report_content_digests),
        )
        minimum_power_lower_bound = min(
            estimate.acceptance_probability_lower_bound for estimate in design_power_estimates
        )
        maximum_null_upper_bound = max(
            estimate.acceptance_probability_upper_bound for estimate in null_acceptance_estimates
        )
        if minimum_power_lower_bound < minimum_design_power:
            failure_reasons.append(
                "insufficient_design_power:"
                f"{minimum_power_lower_bound:.4f}<{minimum_design_power:.4f}"
            )
        if maximum_null_upper_bound > maximum_null_acceptance_probability:
            failure_reasons.append(
                "excess_null_acceptance_probability:"
                f"{maximum_null_upper_bound:.4f}>"
                f"{maximum_null_acceptance_probability:.4f}"
            )
        if (
            interval_coverage_certificate.minimum_coverage_lower_confidence_bound
            < minimum_interval_coverage
        ):
            failure_reasons.append(
                "insufficient_interval_coverage:"
                f"{interval_coverage_certificate.minimum_coverage_lower_confidence_bound:.4f}<"
                f"{minimum_interval_coverage:.4f}"
            )
    return LiveGateSummary(
        suite=suite,
        mode=mode,
        profile=profile,
        run_count=len(reports),
        seed_count=len(runs_by_seed),
        replicate_count=len(by_run),
        scenario_count=interval.scenario_count if interval is not None else 0,
        minimum_seed_count=minimum_seed_count,
        minimum_scenarios_per_replicate=minimum_scenarios_per_replicate,
        minimum_replicates_per_seed=minimum_replicates_per_seed,
        scenario_pass_rate=scenario_pass_rate,
        scenario_pass_interval=interval,
        family_pass_intervals=family_intervals,
        family_scenario_counts=family_scenario_counts,
        required_families=sorted(required_family_set),
        baseline_difference_interval=baseline_interval,
        minimum_pass_rate_lower_bound=minimum_pass_rate_lower_bound,
        minimum_family_pass_rate_lower_bound=minimum_family_pass_rate_lower_bound,
        minimum_family_scenarios_per_seed=minimum_family_scenarios_per_seed,
        minimum_seed_pass_rate=minimum_seed_pass_rate,
        confidence_level=confidence_level,
        intraseed_correlation=intraseed_correlation,
        seed_pass_rates=seed_pass_rates,
        leave_one_seed_out_lower_bounds=leave_one_seed_out_lower_bounds,
        design_power_estimates=design_power_estimates,
        null_acceptance_estimates=null_acceptance_estimates,
        interval_coverage_certificate=interval_coverage_certificate,
        source_revision=bound_source_revision,
        source_tree_digest=bound_source_tree_digest,
        source_state="clean" if report_source_states == {"clean"} else None,
        minimum_design_power=minimum_design_power,
        maximum_null_acceptance_probability=maximum_null_acceptance_probability,
        minimum_interval_coverage=minimum_interval_coverage,
        maximum_provider_failure_rate=maximum_provider_failure_rate,
        maximum_fallback_rate=maximum_fallback_rate,
        provider_failure_rate=provider_failure_rate,
        fallback_rate=fallback_rate,
        critical_failure_bucket_counts=dict(sorted(failure_counts.items())),
        failure_reasons=failure_reasons,
        passed=not failure_reasons,
    )


def _paired_baseline_interval(
    reports: Sequence[BenchmarkReportSummary],
    baseline_reports: Sequence[BenchmarkReportSummary],
    *,
    seed: int,
    resamples: int,
    confidence_level: float,
) -> PairedDifferenceInterval | None:
    if not baseline_reports:
        return None
    candidate_by_run = _scenario_outcomes_by_run(reports)
    baseline_by_run = _scenario_outcomes_by_run(baseline_reports)
    if candidate_by_run.keys() != baseline_by_run.keys():
        return None
    for run_key in sorted(candidate_by_run):
        if candidate_by_run[run_key].keys() != baseline_by_run[run_key].keys():
            return None

    candidate = _collapse_scenario_outcomes(candidate_by_run)
    baseline = _collapse_scenario_outcomes(baseline_by_run)
    if candidate.keys() != baseline.keys():
        return None
    differences_by_seed_scenario: dict[int, dict[str, float]] = {}
    for seed_id in sorted(candidate):
        if candidate[seed_id].keys() != baseline[seed_id].keys():
            return None
        differences_by_seed_scenario[seed_id] = {
            scenario_id: candidate[seed_id][scenario_id] - baseline[seed_id][scenario_id]
            for scenario_id in sorted(candidate[seed_id])
        }
    differences = [
        difference for scenarios in differences_by_seed_scenario.values() for difference in scenarios.values()
    ]
    if not differences or not differences_by_seed_scenario:
        return None
    seed_means = [sum(scenarios.values()) / len(scenarios) for scenarios in differences_by_seed_scenario.values()]
    rng = random.Random(seed)
    seed_ids = sorted(differences_by_seed_scenario)
    bootstrap: list[float] = []
    for _ in range(resamples):
        sampled_seed_means = []
        for _ in seed_ids:
            sampled_seed = rng.choice(seed_ids)
            scenarios = differences_by_seed_scenario[sampled_seed]
            scenario_ids = sorted(scenarios)
            sampled_scenario_differences: list[float] = []
            for _ in scenario_ids:
                sampled_scenario = rng.choice(scenario_ids)
                sampled_scenario_differences.append(scenarios[sampled_scenario])
            sampled_seed_means.append(sum(sampled_scenario_differences) / len(sampled_scenario_differences))
        bootstrap.append(sum(sampled_seed_means) / len(sampled_seed_means))
    bootstrap.sort()
    alpha = (1.0 - confidence_level) / 2.0
    return PairedDifferenceInterval(
        estimate=sum(seed_means) / len(seed_means),
        lower=_percentile(bootstrap, alpha),
        upper=_percentile(bootstrap, 1.0 - alpha),
        pair_count=len(differences),
        confidence_level=confidence_level,
        resamples=resamples,
        seed=seed,
    )


def _scenario_outcomes(reports: Sequence[BenchmarkReportSummary]) -> dict[str, float]:
    outcomes: dict[str, float] = {}
    for report in reports:
        for row in report.scenario_results:
            key = f"{report.seed}:{report.inference_replicate}:{row.scenario_id}"
            outcomes[key] = 1.0 if row.success else 0.0
    return outcomes


def _scenario_outcomes_by_run(
    reports: Sequence[BenchmarkReportSummary],
) -> dict[tuple[int, int], dict[str, float]]:
    outcomes: dict[tuple[int, int], dict[str, float]] = {}
    for report in reports:
        run_key = (report.seed, report.inference_replicate)
        run_outcomes = outcomes.setdefault(run_key, {})
        for row in report.scenario_results:
            scenario_id = row.scenario_id
            if scenario_id in run_outcomes:
                raise ValueError(f"duplicate scenario outcome for run {run_key}: {scenario_id}")
            run_outcomes[scenario_id] = 1.0 if row.success else 0.0
    return outcomes


def _collapse_scenario_outcomes(
    outcomes_by_run: Mapping[tuple[int, int], Mapping[str, float]],
) -> dict[int, dict[str, float]]:
    """Collapse inference repeats to the gate's unique scenario estimand."""

    outcomes_by_seed: dict[int, dict[str, list[float]]] = {}
    for (seed, _replicate), scenarios in outcomes_by_run.items():
        seed_scenarios = outcomes_by_seed.setdefault(seed, {})
        for scenario_id, outcome in scenarios.items():
            seed_scenarios.setdefault(scenario_id, []).append(outcome)
    return {
        seed: {
            scenario_id: 1.0 if all(value == 1.0 for value in values) else 0.0
            for scenario_id, values in scenarios.items()
        }
        for seed, scenarios in outcomes_by_seed.items()
    }


def _percentile(values: Sequence[float], probability: float) -> float:
    position = (len(values) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    fraction = position - lower
    return values[lower] + (values[upper] - values[lower]) * fraction
