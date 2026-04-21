"""Benchmark acceptance and readiness validation."""

from __future__ import annotations

from memorii.core.benchmark.baselines import BASELINE_SYSTEMS
from memorii.core.benchmark.models import (
    BaselinePolicy,
    BenchmarkRunConfig,
    BenchmarkRunReport,
    BenchmarkScenarioFixture,
    BenchmarkScenarioType,
    CanonicalBenchmarkReport,
    ScenarioResult,
)
from memorii.core.benchmark.reproducibility import build_run_id

MIN_FIXTURES_BY_CATEGORY: dict[BenchmarkScenarioType, int] = {
    BenchmarkScenarioType.END_TO_END: 1,
    BenchmarkScenarioType.LONG_HORIZON_DEGRADATION: 1,
    BenchmarkScenarioType.IMPLICIT_RECALL: 1,
    BenchmarkScenarioType.CONFLICT_RESOLUTION: 1,
}

REQUIRED_METRICS_BY_CATEGORY: dict[BenchmarkScenarioType, tuple[str, ...]] = {
    BenchmarkScenarioType.TRANSCRIPT_RETRIEVAL: ("recall_at_k", "precision_at_k"),
    BenchmarkScenarioType.SEMANTIC_RETRIEVAL: ("recall_at_k", "precision_at_k"),
    BenchmarkScenarioType.EPISODIC_RETRIEVAL: ("recall_at_k", "precision_at_k"),
    BenchmarkScenarioType.ROUTING_CORRECTNESS: ("routing_accuracy", "blocked_write_accuracy"),
    BenchmarkScenarioType.EXECUTION_RESUME: ("execution_resume_correctness",),
    BenchmarkScenarioType.SOLVER_RESUME: (
        "solver_resume_correctness",
        "frontier_restore_correctness",
        "unresolved_restore_correctness",
    ),
    BenchmarkScenarioType.SOLVER_VALIDATION: (
        "unsupported_commitment_downgrade_rate",
        "invalid_output_rejection_rate",
        "abstention_preservation_rate",
    ),
    BenchmarkScenarioType.END_TO_END: ("scenario_success_rate", "writeback_candidate_correctness"),
    BenchmarkScenarioType.LEARNING_ACROSS_EPISODES: (
        "cross_episode_reuse_accuracy",
        "writeback_reuse_correctness",
        "writeback_candidate_correctness",
    ),
    BenchmarkScenarioType.LONG_HORIZON_DEGRADATION: (
        "retrieval_recall_degradation",
        "retrieval_latency_growth",
        "noise_resilience",
    ),
    BenchmarkScenarioType.CONFLICT_RESOLUTION: (
        "conflict_detection_rate",
        "correct_preference_for_newer_or_valid_memory",
        "stale_memory_rejection_rate",
        "contradictory_memory_handling_correctness",
    ),
    BenchmarkScenarioType.IMPLICIT_RECALL: (
        "implicit_recall_success_rate",
        "retrieval_plan_relevance_accuracy",
    ),
}


def validate_preflight(*, fixtures: list[BenchmarkScenarioFixture], config: BenchmarkRunConfig) -> None:
    _validate_min_fixture_counts(fixtures)
    _validate_baseline_skip_reasons(fixtures)
    _validate_reproducibility_check(config=config, fixtures=fixtures)


def validate_report(report: BenchmarkRunReport) -> None:
    _validate_required_metrics(report.scenario_results)


def validate_canonical_report(report: CanonicalBenchmarkReport) -> None:
    if not report.categories:
        raise ValueError("canonical benchmark report requires categories")
    if not report.scenarios:
        raise ValueError("canonical benchmark report requires scenarios")
    for scenario in report.scenarios:
        if scenario.expected is None:
            raise ValueError(f"{scenario.scenario_id} missing expected payload")
        if scenario.observed is None:
            raise ValueError(f"{scenario.scenario_id} missing observed payload")
        if scenario.metrics is None:
            raise ValueError(f"{scenario.scenario_id} missing metrics payload")
        if scenario.execution_type is None:
            raise ValueError(f"{scenario.scenario_id} missing execution_type")


def _validate_min_fixture_counts(fixtures: list[BenchmarkScenarioFixture]) -> None:
    counts: dict[BenchmarkScenarioType, int] = {}
    for fixture in fixtures:
        counts[fixture.category] = counts.get(fixture.category, 0) + 1
    for category, minimum in MIN_FIXTURES_BY_CATEGORY.items():
        if counts.get(category, 0) < minimum:
            raise ValueError(
                f"benchmark preflight failed: category {category.value} requires at least {minimum} fixture(s)"
            )


def _validate_baseline_skip_reasons(fixtures: list[BenchmarkScenarioFixture]) -> None:
    for fixture in fixtures:
        for baseline in BASELINE_SYSTEMS:
            policy = fixture.baseline_applicability.get(baseline)
            if policy is None:
                continue
            if policy.policy == BaselinePolicy.SKIP and not policy.skip_reason:
                raise ValueError(
                    f"benchmark preflight failed: {fixture.scenario_id} skips {baseline.value} without reason"
                )


def _validate_reproducibility_check(*, config: BenchmarkRunConfig, fixtures: list[BenchmarkScenarioFixture]) -> None:
    if not config.run_reproducibility_check:
        return
    run_id_a = build_run_id(config=config, fixtures=fixtures)
    run_id_b = build_run_id(config=config, fixtures=fixtures)
    if run_id_a != run_id_b:
        raise ValueError("benchmark preflight failed: reproducibility check produced unstable run_id")


def _validate_required_metrics(results: list[ScenarioResult]) -> None:
    for result in results:
        required_metrics = REQUIRED_METRICS_BY_CATEGORY.get(result.category, ())
        for metric_name in required_metrics:
            if getattr(result.metrics, metric_name) is None:
                raise ValueError(
                    f"benchmark report failed validation: "
                    f"{result.scenario_id}/{result.system.value} missing {metric_name}"
                )
