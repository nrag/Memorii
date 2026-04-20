from memorii.core.benchmark.metrics import compute_metrics
from memorii.core.benchmark.models import BenchmarkScenarioType, BenchmarkSystem, ScenarioObservation


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
