"""Runtime checkpoint answer projection and failure classification."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from memorii.core.benchmark.calibration.alignment import RuntimeGraphAlignmentVerdict
from memorii.core.benchmark.memory_evolution_runtime.execution_state_projection import (
    action_alignment_failure_reason,
)
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
) -> list[str]:
    buckets: list[str] = [
        *projection.stage_failure_buckets,
        *runtime_ingestion_failure_buckets(recorded_runs),
    ]
    expected_claim_ids = (
        list(checkpoint.expected_execution_claim_ids)
        if checkpoint.checkpoint_type == "execution_continuation"
        else list(checkpoint.expected_claim_ids)
    )
    expected_entity_ids = (
        list(checkpoint.expected_execution_entity_ids)
        if checkpoint.checkpoint_type == "execution_continuation"
        else list(checkpoint.expected_entity_ids)
    )
    expected_event_ids = (
        list(checkpoint.expected_execution_citation_event_ids)
        if checkpoint.checkpoint_type == "execution_continuation"
        else list(checkpoint.expected_citation_event_ids)
    )
    if graph_snapshot.validation_errors:
        buckets.append("production_semantic_graph_validation_error")
    for row in projection.channel_alignment_rows:
        if row.channel != "selected" or row.verdict == "aligned":
            continue
        if row.verdict == "unmatched_runtime":
            buckets.append(f"production_retrieval_unexpected_selected_{row.item_type}")
        elif row.verdict == "ambiguous_alignment":
            buckets.append(f"benchmark_alignment_ambiguous_selected_{row.item_type}")
        else:
            buckets.append(f"production_semantic_graph_partial_selected_{row.item_type}")
    selected_action_ids = {
        *projection.production_channels.selected_action_ids,
        *projection.production_channels.selected_action_runtime_ids,
    }
    for row in projection.action_alignment_rows:
        if (
            row.verdict == "aligned"
            or not selected_action_ids.intersection({row.runtime_action_id, row.runtime_item_id})
        ):
            continue
        if row.verdict == "unmatched_runtime":
            buckets.append("production_retrieval_unexpected_selected_action")
        elif row.verdict == "ambiguous_alignment":
            buckets.append("production_retrieval_execution_state_ambiguous")
        else:
            buckets.append(
                f"production_semantic_graph_{row.failure_reason or 'partial_selected_action'}"
            )
    selected = set(output.selected_claim_ids)
    missing_claims = [claim_id for claim_id in expected_claim_ids if claim_id not in selected]
    for claim_id in missing_claims:
        buckets.append(
            _missing_expected_bucket(
                projection=projection,
                item_type="claim",
                oracle_id=claim_id,
            )
        )
    if missing_claims and checkpoint.horizon_distance >= 10 and any(
        bucket == "production_retrieval_missing_expected_claim" for bucket in buckets
    ):
        buckets.append("production_retrieval_long_horizon_miss")
    for entity_id in expected_entity_ids:
        if entity_id not in output.selected_entity_ids:
            buckets.append(
                _missing_expected_bucket(
                    projection=projection,
                    item_type="entity",
                    oracle_id=entity_id,
                )
            )
    missing_relations = [
        relation_id
        for relation_id in checkpoint.expected_relation_ids
        if relation_id not in output.selected_relation_ids
        and relation_id not in output.context_relation_ids
        and relation_id not in output.supporting_relation_ids
    ]
    for relation_id in missing_relations:
        buckets.append(
            _missing_expected_bucket(
                projection=projection,
                item_type="relation",
                oracle_id=relation_id,
            )
        )
    missing_actions = [
        action_id for action_id in checkpoint.expected_action_ids if action_id not in projection.action_support
    ]
    if missing_actions:
        reason = action_alignment_failure_reason(projection.action_alignment_rows)
        aligned_action_ids = {
            row.expected_action_id
            for row in projection.action_alignment_rows
            if row.verdict == "aligned"
        }
        buckets.append(
            "production_retrieval_missing_expected_action"
            if set(missing_actions) <= aligned_action_ids
            else f"production_semantic_graph_{reason or 'missing_expected_action'}"
        )
        if not projection.execution_state.active_continuation_branch:
            buckets.append("production_retrieval_execution_state_missing")
        if projection.execution_state.ambiguous_action_count:
            buckets.append("production_retrieval_execution_state_ambiguous")
    if expected_event_ids and not set(expected_event_ids) & set(output.supporting_citation_event_ids):
        buckets.append("production_semantic_graph_provenance_missing")
        if checkpoint.horizon_distance >= 10:
            buckets.append("production_semantic_graph_long_horizon_provenance_break")
    for claim_id in set(checkpoint.expected_excluded_claim_ids) - set(output.rejected_claim_ids):
        rejected_rows = [
            row
            for row in projection.channel_alignment_rows
            if row.channel == "rejected" and row.oracle_id == claim_id
        ]
        if any(row.verdict == "partial" for row in rejected_rows):
            buckets.append("production_semantic_graph_partial_expected_rejection")
        else:
            buckets.append(
                _missing_expected_bucket(
                    projection=projection,
                    item_type="claim",
                    oracle_id=claim_id,
                    suffix="expected_rejection",
                )
            )
    return sorted(set(buckets))


def runtime_ingestion_failure_buckets(
    recorded_runs: Sequence[RecordedExtractionRun],
) -> list[str]:
    """Classify commit-path failures before retrieval and oracle comparison."""

    buckets: list[str] = []
    for run in recorded_runs:
        if run.extraction_status.value in {"failed", "partial"}:
            failure_code = run.failure_code.value if run.failure_code is not None else "unknown"
            buckets.append(
                f"production_ingestion_extraction_{run.extraction_status.value}_{failure_code}"
            )
        if run.fallback_outcome.value != "not_used":
            buckets.append(
                f"production_ingestion_fallback_{run.fallback_outcome.value}"
            )
        if run.operation_failure_code is not None:
            buckets.append(
                f"production_ingestion_operation_{run.operation_failure_code.value}"
            )
    return sorted(set(buckets))


def _missing_expected_bucket(
    *,
    projection: RuntimeProjection,
    item_type: str,
    oracle_id: str,
    suffix: str | None = None,
) -> str:
    verdicts = {
        alignment.verdict
        for alignment in projection.alignments
        if alignment.item_type == item_type and alignment.oracle_item_id == oracle_id
    }
    label = suffix or f"expected_{item_type}"
    if RuntimeGraphAlignmentVerdict.ALIGNED in verdicts:
        aligned_runtime_ids = {
            alignment.runtime_item_id
            for alignment in projection.alignments
            if alignment.item_type == item_type
            and alignment.oracle_item_id == oracle_id
            and alignment.verdict == RuntimeGraphAlignmentVerdict.ALIGNED
            and alignment.runtime_item_id is not None
        }
        aligned_items = [
            item for item in projection.graph_items if item.runtime_item_id in aligned_runtime_ids
        ]
        if suffix == "expected_rejection" and any(
            item.lifecycle_state.value == "active" for item in aligned_items
        ):
            return "production_lifecycle_active_expected_rejection"
        if suffix is None and any(
            item.lifecycle_state.value != "active" for item in aligned_items
        ):
            return f"production_lifecycle_inactive_expected_{item_type}"
        return f"production_retrieval_missing_{label}"
    if RuntimeGraphAlignmentVerdict.PARTIAL in verdicts:
        return f"production_semantic_graph_partial_{label}"
    return f"production_semantic_graph_missing_{label}"


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
