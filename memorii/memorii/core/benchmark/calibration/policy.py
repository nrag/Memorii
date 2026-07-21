"""Calibration response policy for report-only benchmark diagnostics."""

from __future__ import annotations

from memorii.core.benchmark.calibration.models import CalibrationResponseLevel

DEFAULT_DECISION_COSTS: dict[str, int] = {
    "hidden_fact_hallucinated": 100,
    "hidden_fact_answer_leak": 100,
    "wrong_current_truth": 50,
    "source_trust_inversion": 40,
    "scope_leak": 35,
    "stale_memory_selected": 30,
    "wrong_entity_support_used": 30,
    "historical_truth_lost": 25,
    "missing_provenance": 10,
    "missing_conflict_relation": 20,
    "missing_relation": 10,
    "extra_provenance_noise": 2,
    "extra_context_provenance": 2,
}


def response_for_failure_buckets(failure_buckets: list[str]) -> CalibrationResponseLevel:
    critical = {
        "hidden_fact_hallucinated",
        "hidden_fact_answer_leak",
        "wrong_current_truth",
        "source_trust_inversion",
        "scope_leak",
        "stale_memory_selected",
    }
    review = {
        "missing_conflict_relation",
        "missing_relation",
        "ambiguous_fact_overcommitted",
        "overconfident_wrong_answer",
        "wrong_entity_support_used",
        "historical_truth_lost",
        "missing_provenance",
    }
    buckets = set(failure_buckets)
    if buckets & critical:
        return CalibrationResponseLevel.BENCHMARK_FAIL
    if buckets & review:
        return CalibrationResponseLevel.REVIEW
    return CalibrationResponseLevel.REPORT_ONLY


def response_for_slice(
    *,
    n: int,
    ece: float | None,
    overconfident_wrong_rate: float = 0.0,
    accuracy: float | None = None,
    mean_confidence: float | None = None,
    wilson_high: float | None = None,
) -> CalibrationResponseLevel:
    if ece is None:
        return CalibrationResponseLevel.REPORT_ONLY
    materially_overconfident = (
        accuracy is not None
        and mean_confidence is not None
        and wilson_high is not None
        and mean_confidence > wilson_high + 0.05
    )
    threshold_exceeded = ece > 0.25 or overconfident_wrong_rate > 0.10
    if n >= 10 and threshold_exceeded and (materially_overconfident or overconfident_wrong_rate > 0.10):
        return CalibrationResponseLevel.BENCHMARK_FAIL
    if n >= 5 and threshold_exceeded:
        return CalibrationResponseLevel.REVIEW
    return CalibrationResponseLevel.REPORT_ONLY
