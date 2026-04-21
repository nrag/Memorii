"""Benchmark harness for deterministic scenario execution and baseline comparison."""

from __future__ import annotations

from datetime import UTC, datetime

from memorii.core.benchmark.baselines import BASELINE_SYSTEMS, all_systems
from memorii.core.benchmark.fixtures import normalize_fixtures
from memorii.core.benchmark.metrics import compute_metrics, aggregate_metrics, METRIC_FIELDS
from memorii.core.benchmark.models import (
    BaselinePolicy,
    BaselineDelta,
    BenchmarkRunConfig,
    BenchmarkRunReport,
    BenchmarkScenarioFixture,
    BenchmarkScenarioType,
    BenchmarkSystem,
    ScenarioResult,
)
from memorii.core.benchmark.reproducibility import apply_seed, build_run_id
from memorii.core.benchmark.scenarios import ScenarioExecutor
from memorii.core.benchmark.validation import validate_preflight, validate_report


class BenchmarkHarness:
    def __init__(self) -> None:
        self._executor = ScenarioExecutor()

    def run(
        self,
        *,
        fixtures: list[BenchmarkScenarioFixture],
        config: BenchmarkRunConfig | None = None,
    ) -> BenchmarkRunReport:
        run_config = config or BenchmarkRunConfig()
        apply_seed(run_config.seed)
        normalized = normalize_fixtures(fixtures)
        validate_preflight(fixtures=normalized, config=run_config)
        run_id = build_run_id(config=run_config, fixtures=normalized)

        results: list[ScenarioResult] = []
        for fixture in normalized:
            for system in all_systems():
                if system in BASELINE_SYSTEMS:
                    policy = fixture.baseline_applicability.get(system)
                    if policy is not None and policy.policy == BaselinePolicy.SKIP:
                        continue
                observation = self._executor.run(fixture=fixture, system=system)
                metrics = compute_metrics(observation)
                results.append(
                    ScenarioResult(
                        scenario_id=fixture.scenario_id,
                        category=fixture.category,
                        system=system,
                        observation=observation,
                        metrics=metrics,
                    )
                )

        aggregate = self._aggregate_by_system(results)
        aggregate_by_category = self._aggregate_by_category(results)
        baseline = self._compute_baseline_delta(results)
        report = BenchmarkRunReport(
            run_id=run_id,
            generated_at=datetime.now(UTC),
            config=run_config,
            scenario_results=results,
            aggregate_by_system=aggregate,
            aggregate_by_category=aggregate_by_category,
            baseline_comparison=baseline,
        )
        validate_report(report)
        return report

    def _aggregate_by_system(self, results: list[ScenarioResult]) -> dict[BenchmarkSystem, object]:
        per_system: dict[BenchmarkSystem, list[object]] = {system: [] for system in all_systems()}
        for result in results:
            per_system[result.system].append(result.observation)
        return {system: aggregate_metrics(observations) for system, observations in per_system.items()}

    def _aggregate_by_category(
        self,
        results: list[ScenarioResult],
    ) -> dict[BenchmarkScenarioType, dict[BenchmarkSystem, object]]:
        grouped: dict[BenchmarkScenarioType, dict[BenchmarkSystem, list[object]]] = {}
        for result in results:
            if result.category not in grouped:
                grouped[result.category] = {system: [] for system in all_systems()}
            grouped[result.category][result.system].append(result.observation)

        return {
            category: {
                system: aggregate_metrics(observations)
                for system, observations in per_system.items()
            }
            for category, per_system in grouped.items()
        }

    def _compute_baseline_delta(self, results: list[ScenarioResult]) -> dict[str, list[BaselineDelta]]:
        grouped: dict[str, dict[BenchmarkSystem, ScenarioResult]] = {}
        for result in results:
            grouped.setdefault(result.scenario_id, {})[result.system] = result

        comparison: dict[str, list[BaselineDelta]] = {}
        for scenario_id, by_system in grouped.items():
            memorii_result = by_system.get(BenchmarkSystem.MEMORII)
            if memorii_result is None:
                continue

            deltas: list[BaselineDelta] = []
            for baseline_system in BASELINE_SYSTEMS:
                baseline_result = by_system.get(baseline_system)
                if baseline_result is None:
                    deltas.append(
                        BaselineDelta(
                            baseline=baseline_system,
                            metric_deltas={},
                            skipped=True,
                            skip_reason="baseline skipped by scenario policy or not available",
                        )
                    )
                    continue
                metric_deltas: dict[str, float] = {}
                for field in METRIC_FIELDS:
                    memorii_value = getattr(memorii_result.metrics, field)
                    baseline_value = getattr(baseline_result.metrics, field)
                    if memorii_value is None or baseline_value is None:
                        continue
                    metric_deltas[field] = float(memorii_value - baseline_value)
                deltas.append(BaselineDelta(baseline=baseline_system, metric_deltas=metric_deltas))
            comparison[scenario_id] = deltas
        return comparison
