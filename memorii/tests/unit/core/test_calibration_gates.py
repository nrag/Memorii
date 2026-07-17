from memorii.core.benchmark.artifact_rows import BenchmarkReportSummary, SimScenarioResultRow
from memorii.core.calibration.gates import evaluate_live_gate
from memorii.core.calibration.models import CalibrationReport, DecisionCostReport
from memorii.core.calibration.statistics import hierarchical_seed_scenario_bootstrap


def _report(seed: int, *, successes: int = 3) -> BenchmarkReportSummary:
    scenario_rows = [
        SimScenarioResultRow(
            scenario_id=f"scenario_{index}",
            family="current_truth",
            profile="long_horizon",
            decision_mode="hybrid",
            effective_decision_mode="hybrid",
            checkpoint_count=1,
            success=index < successes,
            checkpoints_passed=1 if index < successes else 0,
            checkpoints_failed=0 if index < successes else 1,
        )
        for index in range(3)
    ]
    return BenchmarkReportSummary(
        suite="memory_evolution_runtime_v1",
        mode="hybrid",
        profile="long_horizon",
        seed=seed,
        run_config_fingerprint="test-config",
        scenario_count=3,
        event_count=3,
        checkpoint_count=3,
        passed=successes,
        failed=3 - successes,
        llm_calls=3,
        provider_successes=3,
        provider_failures=0,
        fallbacks=0,
        dry_run=False,
        execution_source="live_llm",
        scenario_results=scenario_rows,
        calibration=CalibrationReport(event_count=0, labeled_event_count=0),
        decision_quality=DecisionCostReport(decision_cost_total=0, decision_cost_mean=0),
    )


def test_live_gate_uses_scenario_clusters_and_passes_clean_runs() -> None:
    summary = evaluate_live_gate(
        [_report(seed) for seed in (7, 11, 19)],
        suite="memory_evolution_runtime_v1",
        mode="hybrid",
        profile="long_horizon",
        minimum_seed_count=3,
        minimum_scenarios_per_seed=3,
        minimum_pass_rate_lower_bound=0.5,
        bootstrap_resamples=200,
    )

    assert summary.passed is True
    assert summary.scenario_count == 9
    assert summary.scenario_pass_interval is not None
    assert summary.scenario_pass_interval.observation_count == 9


def test_live_gate_accepts_seed_replicates_with_one_configuration_fingerprint() -> None:
    summary = evaluate_live_gate(
        [_report(seed) for seed in (7, 11, 19, 23, 31, 37, 41, 43, 47, 53)],
        suite="memory_evolution_runtime_v1",
        mode="hybrid",
        profile="long_horizon",
        minimum_seed_count=10,
        minimum_scenarios_per_seed=3,
        minimum_pass_rate_lower_bound=0.5,
        bootstrap_resamples=100,
    )

    assert summary.passed is True
    assert "mixed_run_configurations" not in summary.failure_reasons


def test_live_gate_rejects_underpowered_or_critical_runs() -> None:
    report = _report(seed=7, successes=2).model_copy(
        update={"critical_failure_bucket_counts": {"hidden_fact_answer_leak": 1}}
    )

    summary = evaluate_live_gate(
        [report],
        suite="memory_evolution_runtime_v1",
        mode="hybrid",
        profile="long_horizon",
        minimum_seed_count=2,
        minimum_scenarios_per_seed=3,
        minimum_pass_rate_lower_bound=0.9,
        bootstrap_resamples=200,
    )

    assert summary.passed is False
    assert "insufficient_seed_count:1<2" in summary.failure_reasons
    assert "critical_failure_buckets_present" in summary.failure_reasons
    assert summary.critical_failure_bucket_counts == {"hidden_fact_answer_leak": 1}


def test_live_gate_rejects_provider_failures_above_declared_budget() -> None:
    report = _report(seed=7).model_copy(update={"provider_successes": 9, "provider_failures": 1})

    summary = evaluate_live_gate(
        [report],
        suite="memory_evolution_runtime_v1",
        mode="hybrid",
        profile="long_horizon",
        minimum_seed_count=1,
        minimum_scenarios_per_seed=3,
        minimum_pass_rate_lower_bound=0.0,
        maximum_provider_failure_rate=0.05,
        bootstrap_resamples=100,
    )

    assert summary.passed is False
    assert summary.provider_failure_rate == 0.1
    assert "provider_failure_rate:0.1000>0.0500" in summary.failure_reasons


def test_live_gate_rejects_duplicate_seed_reports() -> None:
    summary = evaluate_live_gate(
        [_report(seed=7), _report(seed=7)],
        suite="memory_evolution_runtime_v1",
        mode="hybrid",
        profile="long_horizon",
        minimum_seed_count=1,
        minimum_scenarios_per_seed=3,
        minimum_pass_rate_lower_bound=0.0,
        bootstrap_resamples=100,
    )

    assert summary.passed is False
    assert "duplicate_seed_reports" in summary.failure_reasons


def test_hierarchical_bootstrap_weights_seed_replicates_equally() -> None:
    interval = hierarchical_seed_scenario_bootstrap(
        {
            7: {"a": [1.0]},
            11: {"a": [0.0], "b": [0.0], "c": [0.0]},
        },
        seed=7,
        resamples=100,
    )

    assert interval is not None
    assert interval.estimate == 0.5
    assert interval.scenario_count == 4
    assert interval.observation_count == 4


def test_live_gate_rejects_baseline_without_configuration_fingerprint() -> None:
    candidate = _report(seed=7)
    baseline = _report(seed=7).model_copy(update={"run_config_fingerprint": ""})

    summary = evaluate_live_gate(
        [candidate],
        suite="memory_evolution_runtime_v1",
        mode="hybrid",
        profile="long_horizon",
        minimum_seed_count=1,
        minimum_scenarios_per_seed=3,
        minimum_pass_rate_lower_bound=0.0,
        baseline_reports=[baseline],
        bootstrap_resamples=100,
    )

    assert summary.passed is False
    assert "baseline_missing_run_configuration" in summary.failure_reasons
    assert summary.baseline_difference_interval is None


def test_live_gate_rejects_non_live_or_zero_call_reports() -> None:
    non_live = _report(seed=7).model_copy(update={"execution_source": "mixed"})
    summary = evaluate_live_gate(
        [non_live],
        suite="memory_evolution_runtime_v1",
        mode="hybrid",
        profile="long_horizon",
        minimum_seed_count=1,
        minimum_scenarios_per_seed=3,
        minimum_pass_rate_lower_bound=0.0,
        bootstrap_resamples=50,
    )
    assert summary.passed is False
    assert "non_live_execution_source" in summary.failure_reasons

    no_calls = _report(seed=7).model_copy(
        update={"provider_successes": 0, "provider_failures": 0, "llm_calls": 0}
    )
    summary = evaluate_live_gate(
        [no_calls],
        suite="memory_evolution_runtime_v1",
        mode="hybrid",
        profile="long_horizon",
        minimum_seed_count=1,
        minimum_scenarios_per_seed=3,
        minimum_pass_rate_lower_bound=0.0,
        bootstrap_resamples=50,
    )
    assert summary.passed is False
    assert "no_live_provider_calls" in summary.failure_reasons
