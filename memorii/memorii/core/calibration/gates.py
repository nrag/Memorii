"""Statistical acceptance gates for live memory-evolution benchmark runs."""

from __future__ import annotations

import random
from collections.abc import Iterable, Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.benchmark.artifact_rows import BenchmarkReportSummary
from memorii.core.benchmark.artifact_validation import validate_memory_evolution_run
from memorii.core.calibration.models import ScenarioClusterInterval
from memorii.core.calibration.statistics import hierarchical_seed_scenario_bootstrap


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
    scenario_count: int = Field(ge=0)
    minimum_seed_count: int = Field(ge=1)
    minimum_scenarios_per_seed: int = Field(ge=1)
    scenario_pass_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    scenario_pass_interval: ScenarioClusterInterval | None = None
    baseline_difference_interval: PairedDifferenceInterval | None = None
    minimum_pass_rate_lower_bound: float = Field(ge=0.0, le=1.0)
    maximum_provider_failure_rate: float = Field(ge=0.0, le=1.0)
    maximum_fallback_rate: float = Field(ge=0.0, le=1.0)
    provider_failure_rate: float = Field(ge=0.0, le=1.0)
    fallback_rate: float = Field(ge=0.0, le=1.0)
    critical_failure_bucket_counts: dict[str, int] = Field(default_factory=dict)
    failure_reasons: list[str] = Field(default_factory=list)
    passed: bool

    model_config = ConfigDict(extra="forbid")


DEFAULT_CRITICAL_FAILURE_BUCKETS = frozenset(
    {
        "hidden_fact_hallucinated",
        "hidden_fact_answer_leak",
        "stale_fact_resurfaced",
        "scope_leak",
        "wrong_entity_selected",
        "runtime_execution_state_ambiguous",
        "runtime_execution_state_missing",
    }
)


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
    minimum_scenarios_per_seed: int = 25,
    minimum_pass_rate_lower_bound: float = 0.90,
    maximum_provider_failure_rate: float = 0.05,
    maximum_fallback_rate: float = 0.05,
    critical_failure_buckets: Iterable[str] = DEFAULT_CRITICAL_FAILURE_BUCKETS,
    baseline_reports: Sequence[BenchmarkReportSummary] = (),
    bootstrap_seed: int = 0,
    bootstrap_resamples: int = 2000,
) -> LiveGateSummary:
    if not 0.0 <= minimum_pass_rate_lower_bound <= 1.0:
        raise ValueError("minimum_pass_rate_lower_bound must be between 0 and 1")
    if not 0.0 <= maximum_provider_failure_rate <= 1.0:
        raise ValueError("maximum_provider_failure_rate must be between 0 and 1")
    if not 0.0 <= maximum_fallback_rate <= 1.0:
        raise ValueError("maximum_fallback_rate must be between 0 and 1")
    if minimum_seed_count < 1 or minimum_scenarios_per_seed < 1:
        raise ValueError("minimum seed and scenario counts must be positive")
    critical = set(critical_failure_buckets)
    by_seed: dict[int, list[dict[str, object]]] = {}
    failure_counts: dict[str, int] = {}
    provider_failures = 0
    provider_calls = 0
    fallbacks = 0
    config_fingerprints: set[str] = set()
    missing_config_fingerprint = False
    failure_reasons: list[str] = []
    for report in reports:
        if report.suite != suite or report.mode != mode or report.profile != profile:
            raise ValueError(
                f"report identity does not match gate: {report.suite}/{report.mode}/{report.profile}"
            )
        if report.dry_run or report.execution_source != "live_llm":
            failure_reasons.append("non_live_execution_source")
        rows = [row.model_dump(mode="python") for row in report.scenario_results]
        by_seed.setdefault(report.seed, []).extend(rows)
        if report.run_config_fingerprint:
            config_fingerprints.add(report.run_config_fingerprint)
        else:
            missing_config_fingerprint = True
        for bucket, count in report.critical_failure_bucket_counts.items():
            if bucket in critical:
                failure_counts[bucket] = failure_counts.get(bucket, 0) + count
        provider_failures += report.provider_failures
        provider_calls += report.provider_successes + report.provider_failures
        fallbacks += report.fallbacks

    values_by_seed_scenario: dict[int, dict[str, list[float]]] = {}
    duplicate_scenario_keys: set[str] = set()
    for seed, rows in by_seed.items():
        values_by_seed_scenario[seed] = {}
        for row in rows:
            scenario_id = str(row.get("scenario_id", ""))
            if not scenario_id:
                raise ValueError(f"live report seed {seed} contains a scenario without an ID")
            if scenario_id in values_by_seed_scenario[seed]:
                duplicate_scenario_keys.add(f"{seed}:{scenario_id}")
                continue
            values_by_seed_scenario[seed][scenario_id] = [
                1.0 if row.get("success") is True else 0.0
            ]
    interval = hierarchical_seed_scenario_bootstrap(
        values_by_seed_scenario,
        seed=bootstrap_seed,
        resamples=bootstrap_resamples,
    )
    scenario_pass_rate = interval.estimate if interval else None
    if len(by_seed) < minimum_seed_count:
        failure_reasons.append(f"insufficient_seed_count:{len(by_seed)}<{minimum_seed_count}")
    if len(by_seed) != len(reports):
        failure_reasons.append("duplicate_seed_reports")
    if duplicate_scenario_keys:
        failure_reasons.append("duplicate_scenario_outcomes")
    if missing_config_fingerprint:
        failure_reasons.append("missing_run_config_fingerprint")
    if len(config_fingerprints) > 1:
        failure_reasons.append("mixed_run_configurations")
    underpowered_seeds = sorted(
        seed for seed, rows in by_seed.items() if len(rows) < minimum_scenarios_per_seed
    )
    if underpowered_seeds:
        failure_reasons.append(
            "insufficient_scenarios_per_seed:" + ",".join(str(seed) for seed in underpowered_seeds)
        )
    if interval is None:
        failure_reasons.append("no_scenario_outcomes")
    elif interval.lower < minimum_pass_rate_lower_bound:
        failure_reasons.append(
            f"pass_rate_lower_bound:{interval.lower:.4f}<{minimum_pass_rate_lower_bound:.4f}"
        )
    if failure_counts:
        failure_reasons.append("critical_failure_buckets_present")

    baseline_interval: PairedDifferenceInterval | None = None
    if baseline_reports:
        candidate_outcomes = _scenario_outcomes(reports)
        baseline_outcomes = _scenario_outcomes(baseline_reports)
        if set(candidate_outcomes) != set(baseline_outcomes):
            failure_reasons.append("baseline_incomplete_pairing")
        baseline_fingerprints = {
            report.run_config_fingerprint
            for report in baseline_reports
            if report.run_config_fingerprint
        }
        if any(not report.run_config_fingerprint for report in baseline_reports):
            failure_reasons.append("baseline_missing_run_configuration")
        elif config_fingerprints and baseline_fingerprints != config_fingerprints:
            failure_reasons.append("baseline_run_configuration_mismatch")
        elif set(candidate_outcomes) == set(baseline_outcomes):
            baseline_interval = _paired_baseline_interval(
                reports,
                baseline_reports,
                seed=bootstrap_seed,
                resamples=bootstrap_resamples,
            )
    if baseline_interval is not None and baseline_interval.lower < -0.05:
        failure_reasons.append(f"baseline_noninferiority:{baseline_interval.lower:.4f}<-0.0500")
    provider_failure_rate = provider_failures / max(1, provider_calls)
    fallback_rate = fallbacks / max(1, provider_calls)
    if provider_calls == 0:
        failure_reasons.append("no_live_provider_calls")
    if provider_failure_rate > maximum_provider_failure_rate:
        failure_reasons.append(
            f"provider_failure_rate:{provider_failure_rate:.4f}>{maximum_provider_failure_rate:.4f}"
        )
    if fallback_rate > maximum_fallback_rate:
        failure_reasons.append(f"fallback_rate:{fallback_rate:.4f}>{maximum_fallback_rate:.4f}")
    return LiveGateSummary(
        suite=suite,
        mode=mode,
        profile=profile,
        run_count=len(reports),
        seed_count=len(by_seed),
        scenario_count=sum(len(scenarios) for scenarios in values_by_seed_scenario.values()),
        minimum_seed_count=minimum_seed_count,
        minimum_scenarios_per_seed=minimum_scenarios_per_seed,
        scenario_pass_rate=scenario_pass_rate,
        scenario_pass_interval=interval,
        baseline_difference_interval=baseline_interval,
        minimum_pass_rate_lower_bound=minimum_pass_rate_lower_bound,
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
) -> PairedDifferenceInterval | None:
    if not baseline_reports:
        return None
    candidate = _scenario_outcomes_by_seed(reports)
    baseline = _scenario_outcomes_by_seed(baseline_reports)
    shared_seeds = sorted(candidate.keys() & baseline.keys())
    differences_by_seed: dict[int, list[float]] = {}
    for seed in shared_seeds:
        shared_scenarios = sorted(candidate[seed].keys() & baseline[seed].keys())
        if len(shared_scenarios) != len(candidate[seed]) or len(shared_scenarios) != len(baseline[seed]):
            return None
        differences_by_seed[seed] = [
            candidate[seed][scenario_id] - baseline[seed][scenario_id]
            for scenario_id in shared_scenarios
        ]
    differences = [difference for values in differences_by_seed.values() for difference in values]
    if not differences or not differences_by_seed:
        return None
    rng = random.Random(seed)
    seed_ids = sorted(differences_by_seed)
    bootstrap: list[float] = []
    for _ in range(resamples):
        sampled_seed_means = []
        for _ in seed_ids:
            sampled_seed = rng.choice(seed_ids)
            sampled_differences = differences_by_seed[sampled_seed]
            sampled_seed_values = [rng.choice(sampled_differences) for _ in sampled_differences]
            sampled_seed_means.append(sum(sampled_seed_values) / len(sampled_seed_values))
        bootstrap.append(sum(sampled_seed_means) / len(sampled_seed_means))
    bootstrap.sort()
    return PairedDifferenceInterval(
        estimate=sum(sum(values) / len(values) for values in differences_by_seed.values()) / len(differences_by_seed),
        lower=_percentile(bootstrap, 0.025),
        upper=_percentile(bootstrap, 0.975),
        pair_count=len(differences),
        confidence_level=0.95,
        resamples=resamples,
        seed=seed,
    )


def _scenario_outcomes(reports: Sequence[BenchmarkReportSummary]) -> dict[str, float]:
    outcomes: dict[str, float] = {}
    for report in reports:
        for row in report.scenario_results:
            key = f"{report.seed}:{row.scenario_id}"
            outcomes[key] = 1.0 if row.success else 0.0
    return outcomes


def _scenario_outcomes_by_seed(
    reports: Sequence[BenchmarkReportSummary],
) -> dict[int, dict[str, float]]:
    outcomes: dict[int, dict[str, float]] = {}
    for report in reports:
        seed_outcomes = outcomes.setdefault(report.seed, {})
        for row in report.scenario_results:
            scenario_id = row.scenario_id
            if scenario_id in seed_outcomes:
                raise ValueError(f"duplicate scenario outcome for seed {report.seed}: {scenario_id}")
            seed_outcomes[scenario_id] = 1.0 if row.success else 0.0
    return outcomes


def _percentile(values: Sequence[float], probability: float) -> float:
    position = (len(values) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    fraction = position - lower
    return values[lower] + (values[upper] - values[lower]) * fraction
