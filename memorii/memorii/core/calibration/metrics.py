"""Calibration metrics and slice construction."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from math import sqrt

from memorii.core.calibration.models import CalibrationEvent, CalibrationLabel, CalibrationLabelSource, CalibrationSlice
from memorii.core.calibration.policy import response_for_slice


def labeled_events(events: Iterable[CalibrationEvent]) -> list[CalibrationEvent]:
    return [event for event in events if event.label_source != CalibrationLabelSource.RUNTIME_UNKNOWN and event.label != CalibrationLabel.UNKNOWN]


def correctness(event: CalibrationEvent) -> float:
    if event.label == CalibrationLabel.CORRECT:
        return 1.0
    if event.label == CalibrationLabel.PARTIAL:
        return 0.5
    return 0.0


def expected_calibration_error(events: Iterable[CalibrationEvent], *, bins: int = 10) -> float | None:
    labeled = labeled_events(events)
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
        acc = sum(correctness(event) for event in bucket) / len(bucket)
        ece += abs(mean_conf - acc) * (len(bucket) / total)
    return ece


def brier_score(events: Iterable[CalibrationEvent]) -> float | None:
    labeled = labeled_events(events)
    if not labeled:
        return None
    return sum((event.confidence - correctness(event)) ** 2 for event in labeled) / len(labeled)


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


def rolling_window_metrics(events: list[CalibrationEvent], *, windows: tuple[int, ...] = (10, 25, 50)) -> dict[str, object]:
    labeled = labeled_events(events)
    result: dict[str, object] = {}
    for window in windows:
        rows = []
        for end in range(window, len(labeled) + 1):
            segment = labeled[end - window:end]
            current_ece = expected_calibration_error(segment)
            ow_rate = overconfident_wrong_count(segment) / window
            rows.append({
                "start_index": end - window,
                "end_index": end - 1,
                "ece": current_ece,
                "brier_score": brier_score(segment),
                "overconfident_wrong_rate": ow_rate,
                "drift_alerts": _drift_alerts(rows[-1] if rows else None, current_ece, ow_rate),
            })
        result[str(window)] = rows
    return result


def _slice_from_events(*, slice_key: str, slice_value: str, events: list[CalibrationEvent]) -> CalibrationSlice:
    n = len(events)
    positives = sum(correctness(event) for event in events)
    accuracy = positives / n if n else None
    mean_confidence = sum(event.confidence for event in events) / n if n else None
    ece = expected_calibration_error(events)
    brier = brier_score(events)
    wilson_low, wilson_high = wilson_interval(positives=positives, n=n)
    ow_rate = overconfident_wrong_count(events) / n if n else 0.0
    return CalibrationSlice(
        slice_key=slice_key,
        slice_values={slice_key: slice_value},
        n=n,
        accuracy=accuracy,
        mean_confidence=mean_confidence,
        ece=ece,
        brier_score=brier,
        wilson_low=wilson_low,
        wilson_high=wilson_high,
        eligible_for_failure=n >= 10,
        response_level=response_for_slice(
            n=n,
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


def _drift_alerts(previous: dict[str, object] | None, ece: float | None, overconfident_wrong_rate: float) -> list[str]:
    alerts: list[str] = []
    if previous is None:
        return alerts
    prev_ece = previous.get("ece")
    if isinstance(prev_ece, float) and ece is not None and ece - prev_ece >= 0.20:
        alerts.append("rolling_ece_increase")
    prev_owr = previous.get("overconfident_wrong_rate")
    if isinstance(prev_owr, float) and overconfident_wrong_rate > 0.10 and overconfident_wrong_rate >= 2 * max(prev_owr, 0.0001):
        alerts.append("overconfident_wrong_rate_drift")
    return alerts
