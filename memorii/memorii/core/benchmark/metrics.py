"""Deterministic metric computation for benchmark observations."""

from __future__ import annotations

from collections import defaultdict

from memorii.core.benchmark.models import ScenarioMetrics, ScenarioObservation


METRIC_FIELDS: tuple[str, ...] = (
    "recall_at_k",
    "precision_at_k",
    "retrieval_latency_ms",
    "routing_accuracy",
    "blocked_write_accuracy",
    "multi_domain_fanout_correctness",
    "execution_resume_correctness",
    "solver_resume_correctness",
    "frontier_restore_correctness",
    "unresolved_restore_correctness",
    "unsupported_commitment_downgrade_rate",
    "abstention_preservation_rate",
    "invalid_output_rejection_rate",
    "scenario_success_rate",
    "writeback_candidate_correctness",
    "semantic_pollution_rate",
    "user_memory_pollution_rate",
)


def _safe_ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return float(numerator) / float(denominator)


def compute_metrics(observation: ScenarioObservation) -> ScenarioMetrics:
    recall = None
    precision = None
    if observation.relevant_ids:
        hits = len(set(observation.retrieved_ids) & set(observation.relevant_ids))
        recall = _safe_ratio(hits, len(set(observation.relevant_ids)))
        precision = _safe_ratio(hits, len(observation.retrieved_ids))

    routing_accuracy = None
    blocked_write_accuracy = None
    fanout = None
    if observation.routed_domains or observation.blocked_domains:
        expected = set(observation.relevant_ids)
        routed = {item.value for item in observation.routed_domains}
        blocked_expected = set(observation.excluded_ids)
        blocked_observed = {item.value for item in observation.blocked_domains}
        routing_accuracy = 1.0 if expected == routed else 0.0
        blocked_write_accuracy = 1.0 if blocked_expected == blocked_observed else 0.0
        fanout = 1.0 if len(routed) > 1 else 0.0

    return ScenarioMetrics(
        recall_at_k=recall,
        precision_at_k=precision,
        retrieval_latency_ms=observation.retrieval_latency_ms if observation.retrieved_ids else None,
        routing_accuracy=routing_accuracy,
        blocked_write_accuracy=blocked_write_accuracy,
        multi_domain_fanout_correctness=fanout,
        execution_resume_correctness=_bool_metric(observation.execution_resume_correct),
        solver_resume_correctness=_bool_metric(observation.solver_resume_correct),
        frontier_restore_correctness=_bool_metric(observation.frontier_restore_correct),
        unresolved_restore_correctness=_bool_metric(observation.unresolved_restore_correct),
        unsupported_commitment_downgrade_rate=_bool_metric(observation.downgraded),
        abstention_preservation_rate=_bool_metric(observation.abstention_preserved),
        invalid_output_rejection_rate=_bool_metric(observation.invalid_output_rejected),
        scenario_success_rate=_bool_metric(observation.scenario_success),
        writeback_candidate_correctness=_bool_metric(
            observation.scenario_success and bool(observation.writeback_candidate_domains)
            if observation.scenario_success is not None
            else None
        ),
        semantic_pollution_rate=_bool_metric(False if observation.semantic_pollution is None else observation.semantic_pollution),
        user_memory_pollution_rate=_bool_metric(
            False if observation.user_memory_pollution is None else observation.user_memory_pollution
        ),
    )


def _bool_metric(value: bool | None) -> float | None:
    if value is None:
        return None
    return 1.0 if value else 0.0


def aggregate_metrics(observations: list[ScenarioObservation]) -> ScenarioMetrics:
    buckets: dict[str, list[float]] = defaultdict(list)
    for observation in observations:
        metrics = compute_metrics(observation)
        for field in METRIC_FIELDS:
            value = getattr(metrics, field)
            if value is not None:
                buckets[field].append(value)

    values = {
        field: (sum(bucket) / len(bucket) if bucket else None)
        for field, bucket in buckets.items()
    }
    return ScenarioMetrics(**values)
