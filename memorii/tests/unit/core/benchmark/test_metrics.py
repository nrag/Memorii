from memorii.core.benchmark.metrics import aggregate_metrics, compute_metrics
from memorii.core.benchmark.models import BenchmarkScenarioType, BenchmarkSystem, ScenarioObservation
from memorii.domain.enums import MemoryDomain


def test_metrics_compute_recall_precision_and_routing() -> None:
    observation = ScenarioObservation(
        scenario_id="s1",
        category=BenchmarkScenarioType.TRANSCRIPT_RETRIEVAL,
        system=BenchmarkSystem.MEMORII,
        retrieved_ids=["a", "b"],
        relevant_ids=["a", "c"],
        retrieval_latency_ms=10.0,
    )

    metrics = compute_metrics(observation)
    assert metrics.recall_at_k == 0.5
    assert metrics.precision_at_k == 0.5
    assert metrics.retrieval_latency_ms == 10.0


def test_metrics_compute_extended_benchmark_fields() -> None:
    observation = ScenarioObservation(
        scenario_id="benchmark_eval",
        category=BenchmarkScenarioType.LEARNING_ACROSS_EPISODES,
        system=BenchmarkSystem.MEMORII,
        cross_episode_reuse_correct=True,
        performance_improvement_over_baseline=1.0,
        writeback_reuse_correct=True,
        retrieval_recall_degradation=0.25,
        retrieval_latency_growth=5.0,
        resume_correctness_under_scale=True,
        noise_resilience=0.66,
        conflict_detected=True,
        conflict_resolution_correct=True,
        stale_memory_rejected=True,
        contradictory_handling_correct=True,
        implicit_recall_success=True,
        retrieval_plan_relevance_accuracy=True,
        false_positive_retrieval_rate=0.2,
        precision_at_1=1.0,
        hard_distractor_outrank_rate=0.0,
    )
    metrics = compute_metrics(observation)
    assert metrics.cross_episode_reuse_accuracy == 1.0
    assert metrics.performance_improvement_over_baseline == 1.0
    assert metrics.writeback_reuse_correctness == 1.0
    assert metrics.retrieval_recall_degradation == 0.25
    assert metrics.retrieval_latency_growth == 5.0
    assert metrics.resume_correctness_under_scale == 1.0
    assert metrics.noise_resilience == 0.66
    assert metrics.conflict_detection_rate == 1.0
    assert metrics.correct_preference_for_newer_or_valid_memory == 1.0
    assert metrics.stale_memory_rejection_rate == 1.0
    assert metrics.contradictory_memory_handling_correctness == 1.0
    assert metrics.implicit_recall_success_rate == 1.0
    assert metrics.retrieval_plan_relevance_accuracy == 1.0
    assert metrics.false_positive_retrieval_rate == 0.2
    assert metrics.precision_at_1 == 1.0
    assert metrics.hard_distractor_outrank_rate == 0.0


def test_metrics_use_explicit_routing_and_writeback_expectations() -> None:
    observation = ScenarioObservation(
        scenario_id="routing_writeback_expectation",
        category=BenchmarkScenarioType.END_TO_END,
        system=BenchmarkSystem.MEMORII,
        routed_domains=[MemoryDomain.TRANSCRIPT, MemoryDomain.EXECUTION],
        blocked_domains=[MemoryDomain.SEMANTIC],
        expected_routed_domains=[MemoryDomain.TRANSCRIPT, MemoryDomain.EXECUTION],
        expected_blocked_domains=[MemoryDomain.SEMANTIC],
        writeback_candidate_domains=[MemoryDomain.EPISODIC],
        expected_writeback_candidate_domains=[MemoryDomain.EPISODIC],
        writeback_candidate_ids=["wb:1"],
        expected_writeback_candidate_ids=["wb:1"],
    )
    metrics = compute_metrics(observation)
    assert metrics.routing_accuracy == 1.0
    assert metrics.blocked_write_accuracy == 1.0
    assert metrics.writeback_candidate_correctness == 1.0


def test_routing_metrics_score_zero_for_empty_observed_with_expectations() -> None:
    observation = ScenarioObservation(
        scenario_id="routing_miss",
        category=BenchmarkScenarioType.ROUTING_CORRECTNESS,
        system=BenchmarkSystem.MEMORII,
        routed_domains=[],
        blocked_domains=[],
        expected_routed_domains=[MemoryDomain.TRANSCRIPT],
        expected_blocked_domains=[MemoryDomain.SEMANTIC],
    )

    metrics = compute_metrics(observation)
    assert metrics.routing_accuracy == 0.0
    assert metrics.blocked_write_accuracy == 0.0


def test_end_to_end_without_routing_expectations_keeps_routing_metrics_unset() -> None:
    observation = ScenarioObservation(
        scenario_id="e2e_without_routing_expectations",
        category=BenchmarkScenarioType.END_TO_END,
        system=BenchmarkSystem.MEMORII,
        routed_domains=[],
        blocked_domains=[],
        expected_routed_domains=[],
        expected_blocked_domains=[],
    )

    metrics = compute_metrics(observation)
    assert metrics.routing_accuracy is None
    assert metrics.blocked_write_accuracy is None


def test_explicit_routed_expectation_with_empty_observed_scores_zero() -> None:
    observation = ScenarioObservation(
        scenario_id="explicit_routed_expectation",
        category=BenchmarkScenarioType.END_TO_END,
        system=BenchmarkSystem.MEMORII,
        routed_domains=[],
        expected_routed_domains=[MemoryDomain.TRANSCRIPT],
    )
    metrics = compute_metrics(observation)
    assert metrics.routing_accuracy == 0.0


def test_explicit_blocked_expectation_with_empty_observed_scores_zero() -> None:
    observation = ScenarioObservation(
        scenario_id="explicit_blocked_expectation",
        category=BenchmarkScenarioType.END_TO_END,
        system=BenchmarkSystem.MEMORII,
        blocked_domains=[],
        expected_blocked_domains=[MemoryDomain.SEMANTIC],
    )
    metrics = compute_metrics(observation)
    assert metrics.blocked_write_accuracy == 0.0


def test_multi_domain_fanout_only_applies_when_expected_fanout_is_multidomain() -> None:
    single_domain_observation = ScenarioObservation(
        scenario_id="fanout_single_domain",
        category=BenchmarkScenarioType.ROUTING_CORRECTNESS,
        system=BenchmarkSystem.MEMORII,
        routed_domains=[MemoryDomain.TRANSCRIPT],
        expected_routed_domains=[MemoryDomain.TRANSCRIPT],
    )
    multi_domain_observation = ScenarioObservation(
        scenario_id="fanout_multi_domain_miss",
        category=BenchmarkScenarioType.ROUTING_CORRECTNESS,
        system=BenchmarkSystem.MEMORII,
        routed_domains=[MemoryDomain.TRANSCRIPT],
        expected_routed_domains=[MemoryDomain.TRANSCRIPT, MemoryDomain.EXECUTION],
    )

    single_metrics = compute_metrics(single_domain_observation)
    multi_metrics = compute_metrics(multi_domain_observation)
    assert single_metrics.multi_domain_fanout_correctness is None
    assert multi_metrics.multi_domain_fanout_correctness == 0.0


def test_unsupported_observation_excludes_scenario_success_rate() -> None:
    unsupported = ScenarioObservation(
        scenario_id="e2e-unsupported",
        category=BenchmarkScenarioType.END_TO_END,
        system=BenchmarkSystem.MEMORII,
        scenario_success=False,
        runtime_observability_status="unsupported",
    )
    supported = ScenarioObservation(
        scenario_id="e2e-supported",
        category=BenchmarkScenarioType.END_TO_END,
        system=BenchmarkSystem.MEMORII,
        scenario_success=True,
        runtime_observability_status="supported",
    )
    unsupported_metrics = compute_metrics(unsupported)
    assert unsupported_metrics.scenario_success_rate is None

    aggregate = aggregate_metrics([unsupported, supported])
    assert aggregate.scenario_success_rate == 1.0


def test_all_unsupported_observations_yield_none_success_rate() -> None:
    observations = [
        ScenarioObservation(
            scenario_id="e2e-unsupported-1",
            category=BenchmarkScenarioType.END_TO_END,
            system=BenchmarkSystem.MEMORII,
            scenario_success=False,
            runtime_observability_status="unsupported",
        ),
        ScenarioObservation(
            scenario_id="e2e-unsupported-2",
            category=BenchmarkScenarioType.END_TO_END,
            system=BenchmarkSystem.MEMORII,
            scenario_success=False,
            runtime_observability_status="unsupported",
        ),
    ]
    aggregate = aggregate_metrics(observations)
    assert aggregate.scenario_success_rate is None
