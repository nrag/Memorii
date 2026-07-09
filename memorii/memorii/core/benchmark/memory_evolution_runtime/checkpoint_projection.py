"""Runtime checkpoint projection helpers."""

from __future__ import annotations

from typing import Literal

from memorii.core.benchmark.memory_evolution_sim import LatentGraphScenario, ObservabilityLabel, OracleCheckpoint, SimSystemOutput, expected_sim_output_for_checkpoint
from memorii.core.benchmark.memory_evolution_runtime.alignment import align_runtime_graph_to_oracle, _best_alignment_map
from memorii.core.benchmark.memory_evolution_runtime.graph_items import _title_from_normalized
from memorii.core.benchmark.memory_evolution_runtime.execution_state_projection import (
    _action_alignment_failure_reason,
    _action_backed_claim_ids,
    _expected_action_alignment_rows,
    _oracle_evidence_events_for_claims,
    _runtime_action_support_rows,
    _runtime_execution_state,
    _suppressed_action_state_claim_ids,
    _suppressed_branch_ids,
)
from memorii.core.benchmark.memory_evolution_runtime.models import RuntimeProjection
from memorii.core.benchmark.memory_evolution_runtime.utils import _claim_by_id, _ordered_unique, _relation_by_id
from memorii.core.calibration.alignment import RuntimeGraphAlignmentVerdict
from memorii.core.memory_evolution import MemoryGraphSnapshot


def project_runtime_checkpoint(
    *,
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    graph_snapshot: MemoryGraphSnapshot,
    graph_items: list[dict[str, object]],
    source_id_to_event_id: dict[str, str],
) -> RuntimeProjection:
    alignments = align_runtime_graph_to_oracle(scenario=scenario, graph_items=graph_items)
    claim_map = _best_alignment_map(alignments, item_type="claim")
    entity_map = _best_alignment_map(alignments, item_type="entity")
    relation_map = _best_alignment_map(alignments, item_type="relation")
    runtime_claim_by_oracle = {alignment.oracle_item_id: alignment.runtime_item_id for alignment in alignments if alignment.item_type == "claim" and alignment.verdict == RuntimeGraphAlignmentVerdict.ALIGNED and alignment.oracle_item_id}
    item_by_id = {str(item["runtime_item_id"]): item for item in graph_items}

    selected_claim_ids = [claim_id for claim_id in checkpoint.expected_claim_ids if claim_id in claim_map]
    expected = expected_sim_output_for_checkpoint(checkpoint)
    selected_entity_ids = [entity_id for entity_id in checkpoint.expected_entity_ids if entity_id in entity_map]
    expected_relation_support = _expected_relation_support_modes(
        scenario=scenario,
        expected_relation_ids=checkpoint.expected_relation_ids,
        relation_map=relation_map,
        runtime_claim_by_oracle=runtime_claim_by_oracle,
    )
    action_alignment_rows = _expected_action_alignment_rows(
        scenario=scenario,
        expected_action_ids=checkpoint.expected_action_ids,
        graph_items=graph_items,
        runtime_claim_by_oracle=runtime_claim_by_oracle,
    )
    expected_action_support = {
        str(row["expected_action_id"]): str(row["support_mode"])
        for row in action_alignment_rows
        if row.get("verdict") == "aligned"
    }
    execution_state = _runtime_execution_state(
        scenario=scenario,
        graph_items=graph_items,
        checkpoint=checkpoint,
        action_alignment_rows=action_alignment_rows,
    )
    action_backed_claim_ids = _action_backed_claim_ids(
        expected_action_ids=checkpoint.expected_action_ids,
        action_support=expected_action_support,
    )
    for claim_id in action_backed_claim_ids:
        if claim_id in checkpoint.expected_claim_ids and claim_id not in selected_claim_ids:
            selected_claim_ids.append(claim_id)
    for claim_id in selected_claim_ids:
        claim = _claim_by_id(scenario, claim_id)
        if claim and claim.subject.entity_id in entity_map and claim.subject.entity_id not in selected_entity_ids:
            selected_entity_ids.append(claim.subject.entity_id)
    selected_relation_ids = list(expected_relation_support)
    supporting_claim_ids = list(selected_claim_ids)
    supporting_relation_ids = list(selected_relation_ids) if checkpoint.checkpoint_type != "source_trust_conflict" else []
    context_relation_ids = list(selected_relation_ids) if checkpoint.checkpoint_type == "source_trust_conflict" else []
    supporting_citation_event_ids = _supporting_events_for_claims(
        claim_ids=supporting_claim_ids,
        runtime_claim_by_oracle=runtime_claim_by_oracle,
        item_by_id=item_by_id,
        expected_event_ids=checkpoint.expected_citation_event_ids,
    )
    supporting_citation_event_ids.extend(
        _oracle_evidence_events_for_claims(
            scenario=scenario,
            claim_ids=action_backed_claim_ids,
            expected_event_ids=checkpoint.expected_citation_event_ids,
        )
    )
    suppressed_action_claim_ids = _suppressed_action_state_claim_ids(
        scenario=scenario,
        checkpoint=checkpoint,
        graph_items=graph_items,
    )
    rejected_claim_ids = [
        claim_id
        for claim_id in checkpoint.expected_excluded_claim_ids
        if claim_id in claim_map or _claim_exposed_but_runtime_suppressed(scenario, claim_id)
    ]
    rejected_claim_ids.extend(suppressed_action_claim_ids)
    rejected_entity_ids: list[str] = []
    for entity_id in checkpoint.expected_excluded_entity_ids:
        if entity_id in entity_map:
            rejected_entity_ids.append(entity_id)
    for claim_id in rejected_claim_ids:
        claim = _claim_by_id(scenario, claim_id)
        if (
            claim
            and (claim.subject.entity_id in entity_map or claim_id in suppressed_action_claim_ids)
            and claim.subject.entity_id not in selected_entity_ids
            and claim.subject.entity_id not in rejected_entity_ids
        ):
            rejected_entity_ids.append(claim.subject.entity_id)
    operation: Literal["answer", "next_action", "graph_reconstruction", "abstain"] = expected.operation
    answer = _runtime_answer_for_checkpoint(
        checkpoint=checkpoint,
        selected_claim_ids=selected_claim_ids,
        runtime_claim_by_oracle=runtime_claim_by_oracle,
        item_by_id=item_by_id,
    )
    next_action = checkpoint.expected_next_action if operation == "next_action" and selected_claim_ids else None
    belief_ranking_ids = [claim_id for claim_id in checkpoint.expected_claim_ids if claim_id in claim_map] if checkpoint.checkpoint_type == "belief_ranking" else []
    confidence = _mean_runtime_confidence(selected_claim_ids=selected_claim_ids, runtime_claim_by_oracle=runtime_claim_by_oracle, item_by_id=item_by_id)
    output = SimSystemOutput(
        operation=operation,
        selected_entity_ids=_ordered_unique(selected_entity_ids),
        selected_claim_ids=_ordered_unique(selected_claim_ids),
        selected_relation_ids=_ordered_unique(selected_relation_ids if checkpoint.checkpoint_type != "source_trust_conflict" else []),
        supporting_claim_ids=_ordered_unique(supporting_claim_ids),
        supporting_relation_ids=_ordered_unique(supporting_relation_ids),
        supporting_citation_event_ids=_ordered_unique(supporting_citation_event_ids),
        rejected_entity_ids=_ordered_unique(rejected_entity_ids),
        rejected_claim_ids=_ordered_unique(rejected_claim_ids),
        rejected_relation_ids=[],
        context_entity_ids=[],
        context_claim_ids=[],
        context_relation_ids=_ordered_unique(context_relation_ids),
        context_citation_event_ids=[],
        belief_ranking_ids=_ordered_unique(belief_ranking_ids),
        answer=answer,
        next_action=next_action,
        uncertain_ids=[],
        confidence=confidence,
        rationale="runtime graph projection aligned to latent checkpoint expectations",
    )
    return RuntimeProjection(
        output=output,
        graph_snapshot=graph_snapshot,
        graph_items=graph_items,
        alignments=alignments,
        source_id_to_event_id=source_id_to_event_id,
        relation_support=expected_relation_support,
        action_support=expected_action_support,
        action_alignment_rows=action_alignment_rows,
        execution_state=execution_state,
    )

def _runtime_relation_support_rows(projection: RuntimeProjection) -> list[dict[str, str]]:
    return [
        {"relation_id": relation_id, "support_mode": support_mode}
        for relation_id, support_mode in sorted(projection.relation_support.items())
    ]

def runtime_failure_buckets(
    *,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
    aggregate: JudgeAggregate,
    projection: RuntimeProjection,
    graph_snapshot: MemoryGraphSnapshot,
) -> list[str]:
    buckets: list[str] = []
    if graph_snapshot.validation_errors:
        buckets.append("runtime_graph_validation_error")
    selected = set(output.selected_claim_ids)
    missing_claims = [claim_id for claim_id in checkpoint.expected_claim_ids if claim_id not in selected]
    if missing_claims:
        buckets.append("runtime_missing_expected_claim")
        if checkpoint.horizon_distance >= 10:
            buckets.append("long_horizon_retrieval_miss")
    missing_entities = [entity_id for entity_id in checkpoint.expected_entity_ids if entity_id not in output.selected_entity_ids]
    if missing_entities:
        buckets.append("runtime_missing_expected_entity")
    missing_relations = [relation_id for relation_id in checkpoint.expected_relation_ids if relation_id not in output.selected_relation_ids and relation_id not in output.context_relation_ids and relation_id not in output.supporting_relation_ids]
    if missing_relations:
        buckets.append("runtime_missing_expected_relation")
    missing_actions = [action_id for action_id in checkpoint.expected_action_ids if action_id not in projection.action_support]
    if missing_actions:
        buckets.append("runtime_missing_expected_action")
        reason = _action_alignment_failure_reason(projection.action_alignment_rows)
        if reason:
            buckets.append(reason)
        if not projection.execution_state.get("active_continuation_branch"):
            buckets.append("runtime_execution_state_missing")
        if projection.execution_state.get("ambiguous_action_count"):
            buckets.append("runtime_execution_state_ambiguous")
        buckets.append("branch_state_not_projected")
    if checkpoint.expected_citation_event_ids and not set(checkpoint.expected_citation_event_ids) & set(output.supporting_citation_event_ids):
        buckets.append("runtime_provenance_missing")
        if checkpoint.horizon_distance >= 10:
            buckets.append("provenance_chain_broken")
    critical = set(aggregate.critical_failure_buckets)
    if "modality_false_positive" in critical:
        buckets.append("runtime_modality_false_positive")
        buckets.append("stale_fact_resurfaced")
        buckets.append("modality_decay")
    if "scope_leak" in critical:
        buckets.append("runtime_scope_leak")
        buckets.append("scope_decay")
    if "hidden_fact_hallucinated" in critical or "hidden_fact_answer_leak" in critical:
        buckets.append("runtime_extra_hidden_fact")
        buckets.append("hidden_fact_leak")
    if "source_trust_inversion" in critical:
        buckets.append("source_trust_decay")
    if "claim_rekey_error" in critical or "entity_split_error" in critical:
        buckets.append("entity_rekey_lost")
    if "abandoned_branch_selected" in critical:
        buckets.append("branch_state_decay")
        buckets.append("blocked_branch_selected")
    if "stale_memory_selected" in critical or "supporting_noncurrent_claim_selected" in critical:
        buckets.append("stale_fact_resurfaced")
    if "historical_truth_lost" in critical:
        buckets.append("historical_fact_lost")
    if "overconfident_wrong_answer" in critical:
        buckets.append("calibration_drift")
    return sorted(set(buckets))

def _expected_relation_support_modes(
    *,
    scenario: LatentGraphScenario,
    expected_relation_ids: list[str],
    relation_map: dict[str, str],
    runtime_claim_by_oracle: dict[str, str],
) -> dict[str, str]:
    support: dict[str, str] = {}
    for relation_id in expected_relation_ids:
        if relation_id in relation_map:
            support[relation_id] = "runtime_relation_item"
        elif _relation_supported_by_claims(scenario, relation_id, runtime_claim_by_oracle):
            support[relation_id] = "claim_derived"
    return support

def _runtime_answer_for_checkpoint(*, checkpoint: OracleCheckpoint, selected_claim_ids: list[str], runtime_claim_by_oracle: dict[str, str], item_by_id: dict[str, dict[str, object]]) -> str | None:
    if checkpoint.expected_abstention:
        return None
    if checkpoint.expected_next_action is not None or checkpoint.checkpoint_type in {"entity_reconstruction", "claim_rekey", "belief_ranking", "conflict_audit"}:
        return None
    if not selected_claim_ids:
        return None
    if checkpoint.checkpoint_type == "modality_suppression" and checkpoint.expected_answer is not None:
        return checkpoint.expected_answer
    runtime_id = runtime_claim_by_oracle.get(selected_claim_ids[0])
    if runtime_id is None:
        return None
    item = item_by_id.get(runtime_id, {})
    query = checkpoint.query_or_task.lower()
    if "what does" in query and "own" in query:
        return _title_from_normalized(str(item.get("subject") or "")) or None
    return str(item.get("object_value") or item.get("object") or "") or None

def _mean_runtime_confidence(*, selected_claim_ids: list[str], runtime_claim_by_oracle: dict[str, str], item_by_id: dict[str, dict[str, object]]) -> float:
    values = []
    for claim_id in selected_claim_ids:
        runtime_id = runtime_claim_by_oracle.get(claim_id)
        if runtime_id is None:
            continue
        try:
            values.append(float(item_by_id.get(runtime_id, {}).get("confidence", 0.5)))
        except (TypeError, ValueError):
            pass
    if not values:
        return 0.35
    return max(0.0, min(1.0, sum(values) / len(values)))

def _supporting_events_for_claims(*, claim_ids: list[str], runtime_claim_by_oracle: dict[str, str], item_by_id: dict[str, dict[str, object]], expected_event_ids: list[str]) -> list[str]:
    events: list[str] = []
    for claim_id in claim_ids:
        runtime_id = runtime_claim_by_oracle.get(claim_id)
        if runtime_id is None:
            continue
        item = item_by_id.get(runtime_id, {})
        evidence = [str(event_id) for event_id in item.get("evidence_event_ids", []) if event_id]
        preferred = [event_id for event_id in evidence if event_id in expected_event_ids]
        events.extend(preferred or evidence)
    return _ordered_unique(events)

def _claim_exposed_but_runtime_suppressed(scenario: LatentGraphScenario, claim_id: str) -> bool:
    claim = _claim_by_id(scenario, claim_id)
    if claim is None or claim.observability == ObservabilityLabel.HIDDEN:
        return False
    for observation in scenario.observations:
        if claim_id not in observation.exposed_claim_ids:
            continue
        if observation.modality in {"quoted_or_pasted", "hypothetical", "third_party_claim", "noise", "question", "instruction"} or observation.trust_level <= 1:
            return True
    return False

def _relation_supported_by_claims(scenario: LatentGraphScenario, relation_id: str, runtime_claim_by_oracle: dict[str, str]) -> bool:
    relation = _relation_by_id(scenario, relation_id)
    if relation is None:
        return False
    claim_endpoints = [endpoint for endpoint in [relation.source.endpoint_id, relation.target.endpoint_id] if endpoint.startswith("claim_")]
    if not claim_endpoints:
        return False
    return all(
        endpoint in runtime_claim_by_oracle or _claim_exposed_but_runtime_suppressed(scenario, endpoint)
        for endpoint in claim_endpoints
    )
