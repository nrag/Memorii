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
