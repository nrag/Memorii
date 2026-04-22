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
    "cross_episode_reuse_accuracy",
    "performance_improvement_over_baseline",
    "writeback_reuse_correctness",
    "retrieval_recall_degradation",
    "retrieval_latency_growth",
    "resume_correctness_under_scale",
    "noise_resilience",
    "conflict_detection_rate",
    "correct_preference_for_newer_or_valid_memory",
    "stale_memory_rejection_rate",
    "contradictory_memory_handling_correctness",
    "implicit_recall_success_rate",
    "retrieval_plan_relevance_accuracy",
    "false_positive_retrieval_rate",
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
    expected = {item.value for item in observation.expected_routed_domains}
    routed = {item.value for item in observation.routed_domains}
    blocked_expected = {item.value for item in observation.expected_blocked_domains}
    blocked_observed = {item.value for item in observation.blocked_domains}
    is_routing_correctness = observation.category.value == "routing_correctness"
    if observation.expected_routed_domains or is_routing_correctness:
        routing_accuracy = 1.0 if expected == routed else 0.0
    if observation.expected_blocked_domains or is_routing_correctness:
        blocked_write_accuracy = 1.0 if blocked_expected == blocked_observed else 0.0
    if len(observation.expected_routed_domains) > 1:
        fanout = 1.0 if expected == routed else 0.0

    writeback_correctness = None
    expected_writeback_domains = {domain.value for domain in observation.expected_writeback_candidate_domains}
    observed_writeback_domains = {domain.value for domain in observation.writeback_candidate_domains}
    expected_writeback_ids = set(observation.expected_writeback_candidate_ids)
    observed_writeback_ids = set(observation.writeback_candidate_ids)
    if expected_writeback_domains or expected_writeback_ids:
        domains_ok = expected_writeback_domains == observed_writeback_domains if expected_writeback_domains else True
        ids_ok = expected_writeback_ids == observed_writeback_ids if expected_writeback_ids else True
        writeback_correctness = _bool_metric(domains_ok and ids_ok)

    scenario_success_rate = _bool_metric(observation.scenario_success)
    if observation.runtime_observability_status == "unsupported":
        scenario_success_rate = None

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
        scenario_success_rate=scenario_success_rate,
        writeback_candidate_correctness=writeback_correctness,
        semantic_pollution_rate=_bool_metric(False if observation.semantic_pollution is None else observation.semantic_pollution),
        user_memory_pollution_rate=_bool_metric(
            False if observation.user_memory_pollution is None else observation.user_memory_pollution
        ),
        cross_episode_reuse_accuracy=_bool_metric(observation.cross_episode_reuse_correct),
        performance_improvement_over_baseline=observation.performance_improvement_over_baseline,
        writeback_reuse_correctness=_bool_metric(observation.writeback_reuse_correct),
        retrieval_recall_degradation=observation.retrieval_recall_degradation,
        retrieval_latency_growth=observation.retrieval_latency_growth,
        resume_correctness_under_scale=_bool_metric(observation.resume_correctness_under_scale),
        noise_resilience=observation.noise_resilience,
        conflict_detection_rate=_bool_metric(observation.conflict_detected),
        correct_preference_for_newer_or_valid_memory=_bool_metric(observation.conflict_resolution_correct),
        stale_memory_rejection_rate=_bool_metric(observation.stale_memory_rejected),
        contradictory_memory_handling_correctness=_bool_metric(observation.contradictory_handling_correct),
        implicit_recall_success_rate=_bool_metric(observation.implicit_recall_success),
        retrieval_plan_relevance_accuracy=_bool_metric(observation.retrieval_plan_relevance_accuracy),
        false_positive_retrieval_rate=observation.false_positive_retrieval_rate,
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
