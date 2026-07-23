"""Calibration metrics and slice construction."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from math import sqrt

from memorii.core.benchmark.calibration.models import (
    CalibrationEvent,
    CalibrationLabel,
    CalibrationLabelSource,
    CalibrationRollingWindow,
    CalibrationSlice,
    RiskCoveragePoint,
    ScenarioClusterInterval,
)
from memorii.core.benchmark.calibration.policy import response_for_slice
from memorii.core.benchmark.calibration.statistics import scenario_cluster_bootstrap


def labeled_events(events: Iterable[CalibrationEvent]) -> list[CalibrationEvent]:
    return [event for event in events if event.label_source != CalibrationLabelSource.RUNTIME_UNKNOWN and event.label != CalibrationLabel.UNKNOWN]


def correctness(event: CalibrationEvent) -> float:
    if event.label == CalibrationLabel.CORRECT:
        return 1.0
    if event.label == CalibrationLabel.PARTIAL:
        return 0.5
    return 0.0


def binary_correctness(event: CalibrationEvent) -> float:
    """Binary correctness used by probabilistic metrics and intervals."""

    return 1.0 if event.label == CalibrationLabel.CORRECT else 0.0


def probability_events(events: Iterable[CalibrationEvent]) -> list[CalibrationEvent]:
    """Return events with binary labels suitable for probability metrics."""

    return [event for event in events if event.label in {CalibrationLabel.CORRECT, CalibrationLabel.INCORRECT}]


def expected_calibration_error(events: Iterable[CalibrationEvent], *, bins: int = 10) -> float | None:
    labeled = probability_events(events)
    if not labeled:
        return None
    total = len(labeled)
    ece = 0.0
    for index in range(bins):
        low = index / bins
        high = (index + 1) / bins
        bucket = [event for event in labeled if event.confidence >= low and (event.confidence < high or (index == bins - 1 and event.confidence <= high))]
        if not bucket:
            continue
        mean_conf = sum(event.confidence for event in bucket) / len(bucket)
        acc = sum(binary_correctness(event) for event in bucket) / len(bucket)
        ece += abs(mean_conf - acc) * (len(bucket) / total)
    return ece


def brier_score(events: Iterable[CalibrationEvent]) -> float | None:
    labeled = probability_events(events)
    if not labeled:
        return None
    return sum((event.confidence - binary_correctness(event)) ** 2 for event in labeled) / len(labeled)


def scenario_cluster_accuracy_interval(
    events: Iterable[CalibrationEvent],
    *,
    seed: int = 0,
    resamples: int = 2000,
) -> ScenarioClusterInterval | None:
    """Return a scenario-weighted accuracy interval for labeled events."""

    grouped: dict[str, list[float]] = defaultdict(list)
    for event in probability_events(events):
        grouped[event.scenario_id].append(binary_correctness(event))
    return scenario_cluster_bootstrap(grouped, seed=seed, resamples=resamples)


def wilson_interval(*, positives: float, n: int, z: float = 1.96) -> tuple[float | None, float | None]:
    if n <= 0:
        return None, None
    phat = positives / n
    denominator = 1 + z**2 / n
    center = (phat + z**2 / (2 * n)) / denominator
    margin = z * sqrt((phat * (1 - phat) + z**2 / (4 * n)) / n) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def overconfident_wrong_count(events: Iterable[CalibrationEvent], *, threshold: float = 0.75) -> int:
    return sum(1 for event in labeled_events(events) if event.confidence >= threshold and correctness(event) == 0.0)


def low_confidence_correct_count(events: Iterable[CalibrationEvent], *, threshold: float = 0.5) -> int:
    return sum(1 for event in labeled_events(events) if event.confidence < threshold and correctness(event) == 1.0)


def risk_coverage_curve(events: Iterable[CalibrationEvent]) -> list[RiskCoveragePoint]:
    """Return a deterministic selective-risk curve over labeled decisions."""

    labeled = sorted(probability_events(events), key=lambda event: (-event.confidence, event.event_id))
    if not labeled:
        return []
    points: list[RiskCoveragePoint] = []
    accepted_correctness = 0.0
    for index, event in enumerate(labeled, start=1):
        accepted_correctness += binary_correctness(event)
        coverage = index / len(labeled)
        points.append(
            RiskCoveragePoint(
                accepted_count=index,
                labeled_count=len(labeled),
                coverage=coverage,
                selective_risk=max(0.0, min(1.0, 1.0 - accepted_correctness / index)),
                mean_confidence=sum(item.confidence for item in labeled[:index]) / index,
                threshold=event.confidence,
                abstention_rate=1.0 - coverage,
            )
        )
    return points


def build_calibration_slices(events: list[CalibrationEvent]) -> list[CalibrationSlice]:
    specs = [
        ("predicate_id", lambda e: e.predicate_id or "unknown"),
        ("source_modality", lambda e: e.source_modality or "unknown"),
        ("source_trust_band", lambda e: _source_trust_band(e.source_trust)),
        ("lifecycle_state", lambda e: e.lifecycle_state or "unknown"),
        ("retrieval_view", lambda e: e.retrieval_view or "unknown"),
        ("scope_type", lambda e: _scope_type(e.scope_key)),
        ("decision_channel", lambda e: e.decision_channel.value),
        ("hierarchy_layer", lambda e: e.hierarchy_layer.value),
        ("label_source", lambda e: e.label_source.value),
        ("checkpoint_type", lambda e: e.metadata.get("checkpoint_type", "unknown")),
        ("phase", lambda e: e.metadata.get("phase", "unknown")),
        ("horizon_distance_bucket", lambda e: e.metadata.get("horizon_distance_bucket", "unknown")),
        ("interference_count_bucket", lambda e: e.metadata.get("interference_count_bucket", "unknown")),
        ("source_event_age_days_bucket", lambda e: e.metadata.get("source_event_age_days_bucket", "unknown")),
        ("entity_ambiguity", lambda e: e.entity_ambiguity or "unknown"),
        ("profile", lambda e: e.metadata.get("profile", "unknown")),
        ("predicate_id+source_modality", lambda e: f"{e.predicate_id or 'unknown'}|{e.source_modality or 'unknown'}"),
        ("predicate_id+lifecycle_state", lambda e: f"{e.predicate_id or 'unknown'}|{e.lifecycle_state or 'unknown'}"),
        ("checkpoint_type+decision_channel", lambda e: f"{e.metadata.get('checkpoint_type', 'unknown')}|{e.decision_channel.value}"),
        ("horizon_distance+checkpoint_type", lambda e: f"{e.metadata.get('horizon_distance_bucket', 'unknown')}|{e.metadata.get('checkpoint_type', 'unknown')}"),
        ("interference_count+decision_channel", lambda e: f"{e.metadata.get('interference_count_bucket', 'unknown')}|{e.decision_channel.value}"),
        ("source_modality+decision_channel", lambda e: f"{e.source_modality or 'unknown'}|{e.decision_channel.value}"),
        ("hierarchy_layer+decision_channel", lambda e: f"{e.hierarchy_layer.value}|{e.decision_channel.value}"),
        ("label_source+hierarchy_layer", lambda e: f"{e.label_source.value}|{e.hierarchy_layer.value}"),
    ]
    slices: list[CalibrationSlice] = []
    labeled = labeled_events(events)
    for key, value_fn in specs:
        grouped: dict[str, list[CalibrationEvent]] = defaultdict(list)
        for event in labeled:
            grouped[value_fn(event)].append(event)
        for value, rows in grouped.items():
            slices.append(_slice_from_events(slice_key=key, slice_value=value, events=rows))
    return sorted(slices, key=lambda item: (item.response_level.value, -(item.ece or 0.0), -item.n, item.slice_key, str(item.slice_values)))


def rolling_window_metrics(
    events: list[CalibrationEvent],
    *,
    windows: tuple[int, ...] = (10, 25, 50),
) -> dict[str, list[CalibrationRollingWindow]]:
    labeled = sorted(probability_events(events), key=lambda event: (event.timestamp, event.event_id))
    result: dict[str, list[CalibrationRollingWindow]] = {}
    for window in windows:
        rows: list[CalibrationRollingWindow] = []
        for end in range(window, len(labeled) + 1):
            segment = labeled[end - window:end]
            current_ece = expected_calibration_error(segment)
            ow_rate = overconfident_wrong_count(segment) / len(segment)
            rows.append(
                CalibrationRollingWindow(
                    start_index=end - window,
                    end_index=end - 1,
                    ece=current_ece,
                    brier_score=brier_score(segment),
                    overconfident_wrong_rate=ow_rate,
                    drift_alerts=_drift_alerts(rows[-1] if rows else None, current_ece, ow_rate),
                )
            )
        result[str(window)] = rows
    return result


def _slice_from_events(*, slice_key: str, slice_value: str, events: list[CalibrationEvent]) -> CalibrationSlice:
    n = len(events)
    probability_labeled = probability_events(events)
    probability_count = len(probability_labeled)
    positives = sum(binary_correctness(event) for event in probability_labeled)
    accuracy = positives / probability_count if probability_count else None
    mean_confidence = (
        sum(event.confidence for event in probability_labeled) / probability_count
        if probability_count
        else None
    )
    ece = expected_calibration_error(events)
    brier = brier_score(events)
    wilson_low, wilson_high = wilson_interval(positives=positives, n=probability_count)
    ow_rate = overconfident_wrong_count(events) / probability_count if probability_count else 0.0
    return CalibrationSlice(
        slice_key=slice_key,
        slice_values={slice_key: slice_value},
        n=n,
        scenario_count=len({event.scenario_id for event in events}),
        probability_event_count=probability_count,
        accuracy=accuracy,
        mean_confidence=mean_confidence,
        ece=ece,
        brier_score=brier,
        wilson_low=wilson_low,
        wilson_high=wilson_high,
        eligible_for_failure=probability_count >= 10 and len({event.scenario_id for event in events}) >= 5,
        response_level=response_for_slice(
            n=probability_count,
            ece=ece,
            overconfident_wrong_rate=ow_rate,
            accuracy=accuracy,
            mean_confidence=mean_confidence,
            wilson_high=wilson_high,
        ),
    )


def _source_trust_band(source_trust: int | None) -> str:
    if source_trust is None:
        return "unknown"
    if source_trust <= 1:
        return "low"
    if source_trust <= 3:
        return "medium"
    return "high"


def _scope_type(scope_key: str | None) -> str:
    if scope_key is None:
        return "unknown"
    if scope_key == "global":
        return "global"
    if scope_key.startswith("task:"):
        return "task"
    return "custom"


def _drift_alerts(
    previous: CalibrationRollingWindow | None,
    ece: float | None,
    overconfident_wrong_rate: float,
) -> list[str]:
    alerts: list[str] = []
    if previous is None:
        return alerts
    prev_ece = previous.ece
    if prev_ece is not None and ece is not None and ece - prev_ece >= 0.20:
        alerts.append("rolling_ece_increase")
    prev_owr = previous.overconfident_wrong_rate
    if overconfident_wrong_rate > 0.10 and overconfident_wrong_rate >= 2 * max(prev_owr, 0.0001):
        alerts.append("overconfident_wrong_rate_drift")
    return alerts
