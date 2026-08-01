"""Runtime checkpoint answer projection and failure classification."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from memorii.core.benchmark.memory_evolution_runtime.graph_items import title_from_normalized
from memorii.core.benchmark.memory_evolution_runtime.models import (
    RuntimeClaimGraphItemRow,
    RuntimeGraphItem,
    RuntimeProjection,
)
from memorii.core.benchmark.memory_evolution_runtime.utils import ordered_unique
from memorii.core.benchmark.memory_evolution_sim import OracleCheckpoint, SimSystemOutput
from memorii.core.memory_evolution import MemoryGraphSnapshot

if TYPE_CHECKING:
    from memorii.core.benchmark.memory_evolution_runtime.extractors import RecordedExtractionRun


def runtime_failure_buckets(
    *,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
    projection: RuntimeProjection,
    graph_snapshot: MemoryGraphSnapshot,
    recorded_runs: Sequence[RecordedExtractionRun] = (),
    ingestion_blocked: bool = False,
) -> list[str]:
    buckets: list[str] = [
        *projection.stage_failure_buckets,
        *runtime_ingestion_failure_buckets(recorded_runs),
    ]
    if graph_snapshot.validation_errors:
        buckets.append("production_semantic_graph_validation_error")
    if ingestion_blocked:
        return sorted(set(buckets))
    if projection.semantic_comparison is None:
        buckets.append("benchmark_semantic_comparison_missing")
    else:
        buckets.extend(projection.semantic_comparison.failure_buckets)
    if checkpoint.horizon_distance >= 10 and ("production_retrieval_missing_expected_claim" in buckets):
        buckets.append("production_retrieval_long_horizon_miss")
    return sorted(set(buckets))


def runtime_ingestion_failure_buckets(
    recorded_runs: Sequence[RecordedExtractionRun],
) -> list[str]:
    """Classify commit-path failures before retrieval and oracle comparison."""

    buckets: list[str] = []
    for run in recorded_runs:
        if run.extraction_status.value in {"failed", "partial"}:
            failure_code = run.failure_code.value if run.failure_code is not None else "unknown"
            buckets.append(f"production_ingestion_extraction_{run.extraction_status.value}_{failure_code}")
        if run.fallback_outcome.value != "not_used":
            buckets.append(f"production_ingestion_fallback_{run.fallback_outcome.value}")
        if run.operation_failure_code is not None:
            buckets.append(f"production_ingestion_operation_{run.operation_failure_code.value}")
    return sorted(set(buckets))


def runtime_answer_for_checkpoint(
    *,
    checkpoint: OracleCheckpoint,
    selected_claim_ids: list[str],
    runtime_claim_by_oracle: Mapping[str, str | None],
    item_by_id: Mapping[str, RuntimeGraphItem],
) -> str | None:
    if checkpoint.expected_abstention:
        return None
    if checkpoint.answer_projection_policy in {"none", "next_action", "graph_channels_only"}:
        return None
    if not selected_claim_ids:
        return None
    runtime_id = runtime_claim_by_oracle.get(selected_claim_ids[0])
    if runtime_id is None:
        return None
    item = item_by_id.get(runtime_id)
    if not isinstance(item, RuntimeClaimGraphItemRow):
        return None
    if checkpoint.answer_projection_policy == "claim_subject":
        return title_from_normalized(item.subject) or None
    if item.object_entity_id:
        return title_from_normalized(item.object) or None
    return item.object_value or item.object or None


def mean_runtime_confidence(
    *,
    selected_claim_ids: list[str],
    runtime_claim_by_oracle: Mapping[str, str | None],
    item_by_id: Mapping[str, RuntimeGraphItem],
) -> float:
    values = [
        item.confidence
        for claim_id in selected_claim_ids
        if (runtime_id := runtime_claim_by_oracle.get(claim_id)) is not None
        if (item := item_by_id.get(runtime_id)) is not None
        if isinstance(item, RuntimeClaimGraphItemRow)
    ]
    if not values:
        return 0.35
    return max(0.0, min(1.0, sum(values) / len(values)))


def supporting_events_for_claims(
    *,
    claim_ids: list[str],
    runtime_claim_by_oracle: Mapping[str, str | None],
    item_by_id: Mapping[str, RuntimeGraphItem],
    expected_event_ids: list[str],
) -> list[str]:
    events: list[str] = []
    for claim_id in claim_ids:
        runtime_id = runtime_claim_by_oracle.get(claim_id)
        if runtime_id is None or not isinstance(item := item_by_id.get(runtime_id), RuntimeClaimGraphItemRow):
            continue
        evidence = list(item.evidence_event_ids)
        preferred = [event_id for event_id in evidence if event_id in expected_event_ids]
        events.extend(preferred or evidence)
    return ordered_unique(events)
