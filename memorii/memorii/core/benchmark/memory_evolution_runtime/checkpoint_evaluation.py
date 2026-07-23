"""Runtime checkpoint answer projection and failure classification."""

from __future__ import annotations

from collections.abc import Mapping

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
from memorii.core.benchmark.memory_evolution_sim import JudgeAggregate, OracleCheckpoint, SimSystemOutput
from memorii.core.memory_evolution import MemoryGraphSnapshot


def runtime_failure_buckets(
    *,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
    aggregate: JudgeAggregate,
    projection: RuntimeProjection,
    graph_snapshot: MemoryGraphSnapshot,
) -> list[str]:
    buckets: list[str] = list(projection.stage_failure_buckets)
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
        buckets.append("runtime_graph_validation_error")
    selected = set(output.selected_claim_ids)
    missing_claims = [claim_id for claim_id in expected_claim_ids if claim_id not in selected]
    if missing_claims:
        buckets.append("runtime_missing_expected_claim")
        if checkpoint.horizon_distance >= 10:
            buckets.append("long_horizon_retrieval_miss")
    if any(entity_id not in output.selected_entity_ids for entity_id in expected_entity_ids):
        buckets.append("runtime_missing_expected_entity")
    if any(
        relation_id not in output.selected_relation_ids
        and relation_id not in output.context_relation_ids
        and relation_id not in output.supporting_relation_ids
        for relation_id in checkpoint.expected_relation_ids
    ):
        buckets.append("runtime_missing_expected_relation")
    missing_actions = [
        action_id for action_id in checkpoint.expected_action_ids if action_id not in projection.action_support
    ]
    if missing_actions:
        buckets.append("runtime_missing_expected_action")
        reason = action_alignment_failure_reason(projection.action_alignment_rows)
        if reason:
            buckets.append(reason)
        if not projection.execution_state.active_continuation_branch:
            buckets.append("runtime_execution_state_missing")
        if projection.execution_state.ambiguous_action_count:
            buckets.append("runtime_execution_state_ambiguous")
        buckets.append("branch_state_not_projected")
    if expected_event_ids and not set(expected_event_ids) & set(output.supporting_citation_event_ids):
        buckets.append("runtime_provenance_missing")
        if checkpoint.horizon_distance >= 10:
            buckets.append("provenance_chain_broken")
    critical = set(aggregate.critical_failure_buckets)
    if "modality_false_positive" in critical:
        buckets.extend(("runtime_modality_false_positive", "stale_fact_resurfaced", "modality_decay"))
    if "scope_leak" in critical:
        buckets.extend(("runtime_scope_leak", "scope_decay"))
    if {"hidden_fact_hallucinated", "hidden_fact_answer_leak"} & critical:
        buckets.extend(("runtime_extra_hidden_fact", "hidden_fact_leak"))
    if "source_trust_inversion" in critical:
        buckets.append("source_trust_decay")
    if {"claim_rekey_error", "entity_split_error"} & critical:
        buckets.append("entity_rekey_lost")
    if "abandoned_branch_selected" in critical:
        buckets.extend(("branch_state_decay", "blocked_branch_selected"))
    if {"stale_memory_selected", "supporting_noncurrent_claim_selected"} & critical:
        buckets.append("stale_fact_resurfaced")
    if "historical_truth_lost" in critical:
        buckets.append("historical_fact_lost")
    if "missing_rejected_id" in critical:
        buckets.append("runtime_missing_expected_rejection")
    if "overconfident_wrong_answer" in critical:
        buckets.append("calibration_drift")
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
