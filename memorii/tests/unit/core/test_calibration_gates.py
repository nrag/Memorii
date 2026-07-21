import pytest
from memorii.core.benchmark.artifact_rows import BenchmarkReportSummary, SimScenarioResultRow
from memorii.core.benchmark.calibration.gates import evaluate_live_gate
from memorii.core.benchmark.calibration.models import CalibrationReport, DecisionCostReport
from memorii.core.benchmark.calibration.simulation_models import (
    calibrated_logistic_normal_parameters,
    family_mixture_rate,
    simulation_model_moments,
)
from memorii.core.benchmark.calibration.statistics import (
    DEFAULT_SIMULATION_INTRASEED_CORRELATION_POINTS,
    GateSimulationModel,
    certify_scenario_interval_coverage,
    estimate_live_gate_power,
    estimate_scenario_interval_coverage,
    hierarchical_seed_scenario_bootstrap,
    seed_cluster_scenario_pass_interval,
)


def _report(
    seed: int,
    *,
    replicate: int = 0,
    successes: int = 3,
    families: tuple[str, ...] = ("current_truth",),
) -> BenchmarkReportSummary:
    scenario_rows = [
        SimScenarioResultRow(
            scenario_id=f"scenario_{index}",
            semantic_world_fingerprint=f"semantic-world-{seed}-{index}",
            family=families[index % len(families)],
            profile="long_horizon",
            decision_mode="hybrid",
            effective_decision_mode="hybrid",
            checkpoint_count=1,
            success=index < successes,
            failure_mode=None if index < successes else "checkpoint_failed",
            checkpoints_passed=1 if index < successes else 0,
            checkpoints_failed=0 if index < successes else 1,
        )
        for index in range(3)
    ]
    return BenchmarkReportSummary(
        suite="memory_evolution_sim_v1",
        mode="hybrid",
        profile="long_horizon",
        seed=seed,
        fixture_fingerprint="test-fixture",
        evaluation_fingerprint="test-evaluation",
        system_fingerprint="test-system",
        source_revision="revision:test",
        source_tree_digest="1" * 64,
        source_state="clean",
        report_content_digest="0" * 64,
        artifact_manifest_digest="2" * 64,
        inference_replicate=replicate,
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
        final_output_source_counts={"live_llm": 3},
        scenario_results=scenario_rows,
        calibration=CalibrationReport(event_count=0, labeled_event_count=0),
        decision_quality=DecisionCostReport(decision_cost_total=0, decision_cost_mean=0),
    ).with_content_digest()


def _updated_report(report: BenchmarkReportSummary, **updates: object) -> BenchmarkReportSummary:
    return report.model_copy(update=updates).with_content_digest()


def test_live_gate_uses_scenario_clusters_and_passes_clean_runs() -> None:
    summary = evaluate_live_gate(
        [_report(seed) for seed in (7, 11, 19)],
        suite="memory_evolution_sim_v1",
        mode="hybrid",
        profile="long_horizon",
        minimum_seed_count=3,
        minimum_scenarios_per_replicate=3,
        minimum_replicates_per_seed=1,
        minimum_pass_rate_lower_bound=0.5,
        bootstrap_resamples=200,
    )

    assert summary.passed is True
    assert summary.scenario_count == 9
    assert summary.scenario_pass_interval is not None
    assert summary.scenario_pass_interval.observation_count == 9


def test_live_gate_accepts_seed_replicates_with_one_configuration_fingerprint() -> None:
    summary = evaluate_live_gate(
        [
            _report(seed, replicate=replicate)
            for seed in (7, 11, 19, 23, 31, 37, 41, 43, 47, 53)
            for replicate in (0, 1)
        ],
        suite="memory_evolution_sim_v1",
        mode="hybrid",
        profile="long_horizon",
        minimum_seed_count=10,
        minimum_scenarios_per_replicate=3,
        minimum_pass_rate_lower_bound=0.5,
        bootstrap_resamples=100,
    )

    assert summary.passed is True
    assert "mixed_run_configurations" not in summary.failure_reasons


def test_live_gate_rejects_underpowered_or_critical_runs() -> None:
    report = _updated_report(
        _report(seed=7, successes=2),
        critical_failure_bucket_counts={"hidden_fact_answer_leak": 1},
    )

    summary = evaluate_live_gate(
        [report],
        suite="memory_evolution_sim_v1",
        mode="hybrid",
        profile="long_horizon",
        minimum_seed_count=2,
        minimum_scenarios_per_replicate=3,
        minimum_replicates_per_seed=1,
        minimum_pass_rate_lower_bound=0.9,
        bootstrap_resamples=200,
    )

    assert summary.passed is False
    assert "insufficient_seed_count:1<2" in summary.failure_reasons
    assert "critical_failure_buckets_present" in summary.failure_reasons
    assert summary.critical_failure_bucket_counts == {"hidden_fact_answer_leak": 1}


def test_live_gate_fails_closed_for_new_critical_bucket() -> None:
    report = _updated_report(
        _report(seed=7), critical_failure_bucket_counts={"new_semantic_failure": 1}
    )

    summary = evaluate_live_gate(
        [report],
        suite="memory_evolution_sim_v1",
        mode="hybrid",
        profile="long_horizon",
        minimum_seed_count=1,
        minimum_scenarios_per_replicate=3,
        minimum_replicates_per_seed=1,
        minimum_pass_rate_lower_bound=0.0,
        bootstrap_resamples=50,
    )

    assert summary.passed is False
    assert "critical_failure_buckets_present" in summary.failure_reasons
    assert summary.critical_failure_bucket_counts == {"new_semantic_failure": 1}


def test_live_gate_rejects_provider_failures_above_declared_budget() -> None:
    report = _updated_report(_report(seed=7), provider_successes=9, provider_failures=1)

    summary = evaluate_live_gate(
        [report],
        suite="memory_evolution_sim_v1",
        mode="hybrid",
        profile="long_horizon",
        minimum_seed_count=1,
        minimum_scenarios_per_replicate=3,
        minimum_replicates_per_seed=1,
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
        suite="memory_evolution_sim_v1",
        mode="hybrid",
        profile="long_horizon",
        minimum_seed_count=1,
        minimum_scenarios_per_replicate=3,
        minimum_replicates_per_seed=1,
        minimum_pass_rate_lower_bound=0.0,
        bootstrap_resamples=100,
    )

    assert summary.passed is False
    assert "duplicate_seed_replicate:7:0" in summary.failure_reasons


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


def test_hierarchical_bootstrap_does_not_overweight_extra_replicates() -> None:
    interval = hierarchical_seed_scenario_bootstrap(
        {
            7: {"same_scenario": [1.0, 1.0, 1.0]},
            11: {"same_scenario": [0.0]},
        },
        seed=7,
        resamples=100,
    )

    assert interval is not None
    assert interval.estimate == 0.5
    assert interval.scenario_count == 2
    assert interval.observation_count == 4


def test_live_gate_weights_seeds_equally_when_replicate_counts_differ() -> None:
    reports = [
        _report(7, replicate=0, successes=3),
        _report(7, replicate=1, successes=3),
        _report(7, replicate=2, successes=3),
        _report(11, replicate=0, successes=0),
    ]

    summary = evaluate_live_gate(
        reports,
        suite="memory_evolution_sim_v1",
        mode="hybrid",
        profile="long_horizon",
        minimum_seed_count=2,
        minimum_scenarios_per_replicate=3,
        minimum_replicates_per_seed=1,
        minimum_pass_rate_lower_bound=0.0,
        bootstrap_resamples=100,
    )

    assert summary.scenario_pass_rate == 0.5
    assert summary.scenario_count == 6
    assert summary.scenario_pass_interval is not None
    assert summary.scenario_pass_interval.observation_count == 12


def test_live_gate_rejects_baseline_with_mismatched_evaluation_fingerprint() -> None:
    candidate = _report(seed=7)
    baseline = _updated_report(_report(seed=7), evaluation_fingerprint="other-evaluation")

    summary = evaluate_live_gate(
        [candidate],
        suite="memory_evolution_sim_v1",
        mode="hybrid",
        profile="long_horizon",
        minimum_seed_count=1,
        minimum_scenarios_per_replicate=3,
        minimum_replicates_per_seed=1,
        minimum_pass_rate_lower_bound=0.0,
        baseline_reports=[baseline],
        bootstrap_resamples=100,
    )

    assert summary.passed is False
    assert "baseline_evaluation_configuration_mismatch" in summary.failure_reasons
    assert summary.baseline_difference_interval is None


def test_live_gate_rejects_incomplete_baseline_replicate_pairing() -> None:
    candidates = [_report(seed=7, replicate=0), _report(seed=7, replicate=1)]
    baseline = [_report(seed=7, replicate=0)]

    summary = evaluate_live_gate(
        candidates,
        suite="memory_evolution_sim_v1",
        mode="hybrid",
        profile="long_horizon",
        minimum_seed_count=1,
        minimum_scenarios_per_replicate=3,
        minimum_replicates_per_seed=1,
        minimum_pass_rate_lower_bound=0.0,
        baseline_reports=baseline,
        bootstrap_resamples=50,
    )

    assert summary.passed is False
    assert "baseline_incomplete_pairing" in summary.failure_reasons
    assert summary.baseline_difference_interval is None


def test_live_gate_allows_paired_baseline_from_different_system() -> None:
    candidate = _report(seed=7)
    baseline = _updated_report(_report(seed=7), system_fingerprint="baseline-system")

    summary = evaluate_live_gate(
        [candidate],
        suite="memory_evolution_sim_v1",
        mode="hybrid",
        profile="long_horizon",
        minimum_seed_count=1,
        minimum_scenarios_per_replicate=3,
        minimum_replicates_per_seed=1,
        minimum_pass_rate_lower_bound=0.0,
        baseline_reports=[baseline],
        bootstrap_resamples=50,
    )

    assert summary.passed is True
    assert summary.baseline_difference_interval is not None
    assert summary.baseline_difference_interval.estimate == 0.0


def test_paired_baseline_uses_conservative_unique_scenario_outcomes() -> None:
    candidates = [
        _report(seed=7, replicate=0, successes=3),
        _report(seed=7, replicate=1, successes=2),
    ]
    baselines = [
        _report(seed=7, replicate=0, successes=3),
        _report(seed=7, replicate=1, successes=3),
    ]

    summary = evaluate_live_gate(
        candidates,
        suite="memory_evolution_sim_v1",
        mode="hybrid",
        profile="long_horizon",
        minimum_seed_count=1,
        minimum_scenarios_per_replicate=3,
        minimum_replicates_per_seed=2,
        minimum_pass_rate_lower_bound=0.0,
        baseline_reports=baselines,
        bootstrap_resamples=100,
        confidence_level=0.90,
    )

    interval = summary.baseline_difference_interval
    assert interval is not None
    assert interval.estimate == -1 / 3
    assert interval.pair_count == 3
    assert interval.confidence_level == 0.90


def test_live_gate_rejects_semantically_duplicated_worlds_across_seeds() -> None:
    first = _report(seed=7)
    duplicate_rows = [
        row.model_copy(update={"semantic_world_fingerprint": f"semantic-world-7-{index}"})
        for index, row in enumerate(_report(seed=11).scenario_results)
    ]
    second = _updated_report(_report(seed=11), scenario_results=duplicate_rows)

    summary = evaluate_live_gate(
        [first, second],
        suite="memory_evolution_sim_v1",
        mode="hybrid",
        profile="long_horizon",
        minimum_seed_count=2,
        minimum_scenarios_per_replicate=3,
        minimum_replicates_per_seed=1,
        minimum_pass_rate_lower_bound=0.0,
        bootstrap_resamples=50,
    )

    assert summary.passed is False
    assert "duplicate_semantic_worlds" in summary.failure_reasons


def test_live_gate_rejects_non_live_or_zero_call_reports() -> None:
    non_live = _updated_report(
        _report(seed=7),
        execution_source="mixed",
        final_output_source_counts={"live_llm": 2, "rule": 1},
    )
    summary = evaluate_live_gate(
        [non_live],
        suite="memory_evolution_sim_v1",
        mode="hybrid",
        profile="long_horizon",
        minimum_seed_count=1,
        minimum_scenarios_per_replicate=3,
        minimum_replicates_per_seed=1,
        minimum_pass_rate_lower_bound=0.0,
        bootstrap_resamples=50,
    )
    assert summary.passed is False
    assert "non_live_execution_source" in summary.failure_reasons

    no_calls = _updated_report(
        _report(seed=7), provider_successes=0, provider_failures=0, llm_calls=0
    )
    summary = evaluate_live_gate(
        [no_calls],
        suite="memory_evolution_sim_v1",
        mode="hybrid",
        profile="long_horizon",
        minimum_seed_count=1,
        minimum_scenarios_per_replicate=3,
        minimum_replicates_per_seed=1,
        minimum_pass_rate_lower_bound=0.0,
        bootstrap_resamples=50,
    )
    assert summary.passed is False
    assert "no_live_provider_calls" in summary.failure_reasons


def test_live_gate_rejects_mixed_or_stale_source_provenance() -> None:
    mixed_revision = _updated_report(_report(seed=11), source_revision="revision:other")
    with pytest.raises(ValueError, match="mixed source revisions"):
        evaluate_live_gate(
            [_report(seed=7), mixed_revision],
            suite="memory_evolution_sim_v1",
            mode="hybrid",
            profile="long_horizon",
            minimum_seed_count=1,
            minimum_scenarios_per_replicate=3,
            minimum_replicates_per_seed=1,
            minimum_pass_rate_lower_bound=0.0,
        )

    stale_digest = _report(seed=7).model_copy(update={"fixture_fingerprint": "mutated"})
    with pytest.raises(ValueError, match="content digest is invalid"):
        evaluate_live_gate(
            [stale_digest],
            suite="memory_evolution_sim_v1",
            mode="hybrid",
            profile="long_horizon",
            minimum_seed_count=1,
            minimum_scenarios_per_replicate=3,
            minimum_replicates_per_seed=1,
            minimum_pass_rate_lower_bound=0.0,
        )

    with pytest.raises(ValueError, match="source revision does not match"):
        evaluate_live_gate(
            [_report(seed=7)],
            suite="memory_evolution_sim_v1",
            mode="hybrid",
            profile="long_horizon",
            minimum_seed_count=1,
            minimum_scenarios_per_replicate=3,
            minimum_replicates_per_seed=1,
            minimum_pass_rate_lower_bound=0.0,
            source_revision="revision:other",
        )

    dirty = _updated_report(_report(seed=7), source_state="dirty")
    summary = evaluate_live_gate(
        [dirty],
        suite="memory_evolution_sim_v1",
        mode="hybrid",
        profile="long_horizon",
        minimum_seed_count=1,
        minimum_scenarios_per_replicate=3,
        minimum_replicates_per_seed=1,
        minimum_pass_rate_lower_bound=0.0,
    )
    assert summary.passed is False
    assert "non_certifying_source_state:dirty" in summary.failure_reasons

    mixed_digest = _updated_report(_report(seed=11), source_tree_digest="2" * 64)
    with pytest.raises(ValueError, match="mixed source-tree digests"):
        evaluate_live_gate(
            [_report(seed=7), mixed_digest],
            suite="memory_evolution_sim_v1",
            mode="hybrid",
            profile="long_horizon",
            minimum_seed_count=1,
            minimum_scenarios_per_replicate=3,
            minimum_replicates_per_seed=1,
            minimum_pass_rate_lower_bound=0.0,
        )


def test_live_gate_controls_aggregate_and_family_endpoints_simultaneously() -> None:
    summary = evaluate_live_gate(
        [_report(seed=7)],
        suite="memory_evolution_sim_v1",
        mode="hybrid",
        profile="long_horizon",
        minimum_seed_count=1,
        minimum_scenarios_per_replicate=3,
        minimum_replicates_per_seed=1,
        minimum_pass_rate_lower_bound=0.0,
        minimum_family_pass_rate_lower_bound=0.0,
        minimum_family_scenarios_per_seed=1,
        required_families=("current_truth",),
        confidence_level=0.95,
    )

    assert summary.scenario_pass_interval is not None
    assert summary.scenario_pass_interval.confidence_level == pytest.approx(0.975)
    assert summary.family_pass_intervals["current_truth"].confidence_level == pytest.approx(0.975)


def test_live_gate_certifies_every_predeclared_simulation_model() -> None:
    summary = evaluate_live_gate(
        [_report(seed=7)],
        suite="memory_evolution_sim_v1",
        mode="hybrid",
        profile="long_horizon",
        minimum_seed_count=1,
        minimum_scenarios_per_replicate=3,
        minimum_replicates_per_seed=1,
        minimum_pass_rate_lower_bound=0.0,
        minimum_design_power=0.01,
        maximum_null_acceptance_probability=0.99,
        minimum_interval_coverage=0.01,
        design_trials=12,
        source_revision="revision:test",
    )

    expected_models = set(GateSimulationModel)
    assert {estimate.simulation_model for estimate in summary.design_power_estimates} == expected_models
    assert {estimate.simulation_model for estimate in summary.null_acceptance_estimates} == expected_models
    assert all(
        estimate.acceptance_probability_lower_bound <= estimate.estimated_acceptance_probability
        <= estimate.acceptance_probability_upper_bound
        for estimate in [*summary.design_power_estimates, *summary.null_acceptance_estimates]
    )
    assert summary.interval_coverage_certificate is not None
    assert summary.interval_coverage_certificate.configuration.input_report_content_digests == [
        _report(seed=7).report_content_digest
    ]
    assert summary.interval_coverage_certificate.configuration.simulation_intraseed_correlation_points == list(
        DEFAULT_SIMULATION_INTRASEED_CORRELATION_POINTS
    )


def test_live_gate_requires_exact_family_catalog_per_replicate() -> None:
    summary = evaluate_live_gate(
        [_report(seed=7, families=("current_truth", "unexpected"))],
        suite="memory_evolution_sim_v1",
        mode="hybrid",
        profile="long_horizon",
        minimum_seed_count=1,
        minimum_scenarios_per_replicate=3,
        minimum_replicates_per_seed=1,
        minimum_pass_rate_lower_bound=0.0,
        minimum_family_pass_rate_lower_bound=0.0,
        minimum_family_scenarios_per_seed=1,
        required_families=("current_truth", "source_trust_conflict"),
        bootstrap_resamples=50,
    )

    assert summary.passed is False
    assert "missing_required_families:7:0:source_trust_conflict" in summary.failure_reasons
    assert "unexpected_scenario_families:7:0:unexpected" in summary.failure_reasons


def test_live_gate_rejects_weak_family_even_when_aggregate_is_healthy() -> None:
    report = _report(
        seed=7,
        successes=2,
        families=("healthy", "healthy", "weak"),
    )
    summary = evaluate_live_gate(
        [report],
        suite="memory_evolution_sim_v1",
        mode="hybrid",
        profile="long_horizon",
        minimum_seed_count=1,
        minimum_scenarios_per_replicate=3,
        minimum_replicates_per_seed=1,
        minimum_pass_rate_lower_bound=0.0,
        minimum_family_pass_rate_lower_bound=0.5,
        minimum_family_scenarios_per_seed=1,
        required_families=("healthy", "weak"),
        bootstrap_resamples=100,
    )

    assert summary.scenario_pass_rate == 2 / 3
    assert any(reason.startswith("family_pass_rate_lower_bound:weak:") for reason in summary.failure_reasons)


def test_hierarchical_gate_power_tracks_true_performance() -> None:
    common = {
        "minimum_pass_rate_lower_bound": 0.75,
        "seed_count": 5,
        "scenarios_per_seed": 10,
        "replicates_per_scenario": 2,
        "intraseed_correlation": 0.05,
        "trials": 40,
        "seed": 7,
    }

    strong = estimate_live_gate_power(true_scenario_reliability=0.98, **common)
    weak = estimate_live_gate_power(true_scenario_reliability=0.70, **common)

    assert strong.estimated_acceptance_probability > weak.estimated_acceptance_probability
    assert strong.monte_carlo_standard_error >= 0.0


def test_live_gate_interval_does_not_claim_certainty_for_finite_perfect_sample() -> None:
    interval = seed_cluster_scenario_pass_interval(
        {seed: {f"scenario_{index}": [1.0, 1.0] for index in range(25)} for seed in range(10)}
    )

    assert interval is not None
    assert interval.estimate == 1.0
    assert 0.0 < interval.lower < 1.0
    assert interval.upper == 1.0
    assert interval.scenario_count == 250
    assert interval.observation_count == 500


def test_live_gate_interval_requires_every_replicate_to_pass() -> None:
    interval = seed_cluster_scenario_pass_interval(
        {7: {"stable": [1.0, 1.0], "unstable": [1.0, 0.0]}}
    )

    assert interval is not None
    assert interval.success_count == 1
    assert interval.scenario_count == 2
    assert interval.estimate == 0.5


def test_seed_correlation_widens_exact_scenario_reliability_interval() -> None:
    values = {seed: {f"scenario_{index}": [1.0, 1.0] for index in range(10)} for seed in range(5)}

    independent = seed_cluster_scenario_pass_interval(values, intraseed_correlation=0.0)
    clustered = seed_cluster_scenario_pass_interval(values, intraseed_correlation=0.30)

    assert independent is not None
    assert clustered is not None
    assert clustered.lower < independent.lower
    assert clustered.effective_sample_size < independent.effective_sample_size
    assert clustered.method == "one_sided_beta_binomial_seed_cluster_exact"


def test_seed_cluster_interval_has_empirical_lower_bound_coverage() -> None:
    estimate = estimate_scenario_interval_coverage(
        true_scenario_reliability=0.90,
        seed_count=5,
        scenarios_per_seed=8,
        replicates_per_scenario=2,
        interval_intraseed_correlation=0.10,
        simulation_intraseed_correlation=0.10,
        trials=100,
        interval_confidence_level=0.95,
        coverage_confidence_level=0.95,
        seed=7,
    )

    assert estimate.estimated_lower_bound_coverage >= 0.90
    assert estimate.interval_method == "one_sided_beta_binomial_seed_cluster_exact"
    assert estimate.estimand == "scenario_all_replicates_pass_probability"


def test_coverage_certificate_is_conservative_across_misspecified_generators() -> None:
    certificate = certify_scenario_interval_coverage(
        reliability_points=[0.5, 0.9],
        seed_count=4,
        scenarios_per_seed=6,
        replicates_per_scenario=2,
        interval_intraseed_correlation=0.1,
        simulation_intraseed_correlation_points=[0.05, 0.1],
        trials=60,
        interval_confidence_level=0.95,
        certificate_confidence_level=0.95,
        seed=7,
        source_revision="revision:test",
        source_tree_digest="1" * 64,
        source_state="clean",
        input_report_content_digests=["1" * 64, "2" * 64, "3" * 64],
    )

    assert set(certificate.configuration.simulation_models) == set(GateSimulationModel)
    assert len(certificate.estimates) == 12
    assert (
        certificate.design_point_coverage_confidence_level
        > certificate.configuration.certificate_confidence_level
    )
    assert certificate.configuration.interval_confidence_level == 0.95
    assert all(estimate.interval_confidence_level == 0.95 for estimate in certificate.estimates)
    assert all(
        estimate.coverage_confidence_level
        == certificate.design_point_coverage_confidence_level
        for estimate in certificate.estimates
    )
    assert certificate.configuration.source_revision == "revision:test"
    assert len(certificate.configuration_digest) == 64
    assert certificate.minimum_coverage_lower_confidence_bound == min(
        estimate.coverage_lower_confidence_bound for estimate in certificate.estimates
    )
    assert all(
        estimate.coverage_lower_confidence_bound <= estimate.estimated_lower_bound_coverage
        for estimate in certificate.estimates
    )

    inconsistent = certificate.model_dump(mode="json")
    inconsistent["minimum_coverage_lower_confidence_bound"] = 1.0
    with pytest.raises(ValueError, match="minimum coverage bound"):
        type(certificate).model_validate(inconsistent)

    stale_digest = certificate.model_dump(mode="json")
    stale_digest["configuration"]["seed"] += 1
    with pytest.raises(ValueError, match="configuration digest"):
        type(certificate).model_validate(stale_digest)

    duplicate_design_point = certificate.model_dump(mode="json")
    duplicate_design_point["estimates"][-1] = duplicate_design_point["estimates"][0]
    with pytest.raises(ValueError, match="exactly span"):
        type(certificate).model_validate(duplicate_design_point)

    unknown_certificate_version = certificate.model_dump(mode="json")
    unknown_certificate_version["certificate_version"] = "gate-coverage-certificate-unknown"
    with pytest.raises(ValueError):
        type(certificate).model_validate(unknown_certificate_version)

    unknown_algorithm_version = certificate.model_dump(mode="json")
    unknown_algorithm_version["configuration"]["algorithm_version"] = "scenario-coverage-grid-unknown"
    with pytest.raises(ValueError):
        type(certificate).model_validate(unknown_algorithm_version)


@pytest.mark.parametrize(
    ("source_revision", "report_digests", "message"),
    [
        (" revision:test ", ["1" * 64], "source and input-report provenance"),
        ("revision:test", ["not-a-digest"], "lowercase SHA-256"),
        ("revision:test", ["1" * 64, "1" * 64], "must be unique"),
    ],
)
def test_coverage_certificate_rejects_ambiguous_provenance(
    source_revision: str,
    report_digests: list[str],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        certify_scenario_interval_coverage(
            reliability_points=[0.9],
            seed_count=2,
            scenarios_per_seed=2,
            trials=2,
            source_revision=source_revision,
            source_tree_digest="1" * 64,
            source_state="clean",
            input_report_content_digests=report_digests,
        )


def test_coverage_generators_preserve_the_declared_marginal_reliability() -> None:
    seed_rate = 0.82
    family_rates = [
        family_mixture_rate(
            seed_rate,
            scenario_index=index,
            scenario_count=5,
        )
        for index in range(5)
    ]
    assert sum(family_rates) / len(family_rates) == seed_rate

    target_correlation = 0.10
    intercept, sigma = calibrated_logistic_normal_parameters(seed_rate, target_correlation)
    assert intercept != 0.0
    assert sigma > 0.0
    moments = simulation_model_moments(
        mean=seed_rate,
        correlation=target_correlation,
        simulation_model=GateSimulationModel.LOGISTIC_NORMAL,
    )
    assert moments.marginal_reliability == pytest.approx(seed_rate, abs=1e-10)
    assert moments.intraseed_correlation == pytest.approx(target_correlation, abs=1e-8)

    family_moments = simulation_model_moments(
        mean=seed_rate,
        correlation=target_correlation,
        simulation_model=GateSimulationModel.FAMILY_MIXTURE,
    )
    assert family_moments.marginal_reliability == seed_rate
    assert family_moments.intraseed_correlation is None


@pytest.mark.parametrize("mean", [0.0, 1.0])
@pytest.mark.parametrize(
    "simulation_model",
    [GateSimulationModel.BETA_BINOMIAL, GateSimulationModel.LOGISTIC_NORMAL],
)
def test_degenerate_reliability_reports_intraseed_correlation_as_undefined(
    mean: float,
    simulation_model: GateSimulationModel,
) -> None:
    moments = simulation_model_moments(
        mean=mean,
        correlation=0.25,
        simulation_model=simulation_model,
    )

    assert moments.marginal_reliability == mean
    assert moments.intraseed_correlation is None
