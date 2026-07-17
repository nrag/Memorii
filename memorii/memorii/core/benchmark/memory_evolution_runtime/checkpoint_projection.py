"""Runtime checkpoint projection helpers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import suppress
from typing import Literal

from memorii.core.benchmark.artifact_rows import RuntimeActionAlignmentRow, RuntimeExecutionStateSection
from memorii.core.benchmark.memory_evolution_runtime.alignment import _best_alignment_map, align_runtime_graph_to_oracle
from memorii.core.benchmark.memory_evolution_runtime.execution_state_projection import (
    _action_alignment_failure_reason,
    _expected_action_alignment_rows,
    _suppressed_action_state_claim_ids,
)
from memorii.core.benchmark.memory_evolution_runtime.graph_items import _title_from_normalized
from memorii.core.benchmark.memory_evolution_runtime.models import RuntimeProjection
from memorii.core.benchmark.memory_evolution_runtime.utils import _claim_by_id, _ordered_unique, _relation_by_id
from memorii.core.benchmark.memory_evolution_sim import (
    JudgeAggregate,
    LatentGraphScenario,
    ObservabilityLabel,
    OracleCheckpoint,
    SimSystemOutput,
)
from memorii.core.calibration.alignment import RuntimeGraphAlignmentVerdict
from memorii.core.memory_evolution import MemoryGraphSnapshot, ProductionRetrievalDecision, WorkStateSnapshot


def project_runtime_checkpoint(
    *,
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    graph_snapshot: MemoryGraphSnapshot,
    graph_items: list[dict[str, object]],
    source_id_to_event_id: dict[str, str],
    work_state: WorkStateSnapshot | None = None,
    retrieval_decision: ProductionRetrievalDecision | None = None,
) -> RuntimeProjection:
    alignments = align_runtime_graph_to_oracle(scenario=scenario, graph_items=graph_items)
    entity_map = _best_alignment_map(alignments, item_type="entity")
    runtime_claim_by_oracle = {alignment.oracle_item_id: alignment.runtime_item_id for alignment in alignments if alignment.item_type == "claim" and alignment.verdict == RuntimeGraphAlignmentVerdict.ALIGNED and alignment.oracle_item_id}
    item_by_id = {str(item["runtime_item_id"]): item for item in graph_items}

    action_alignment_rows = _expected_action_alignment_rows(
        scenario=scenario,
        expected_action_ids=checkpoint.expected_action_ids,
        graph_items=graph_items,
        runtime_claim_by_oracle=runtime_claim_by_oracle,
    )
    selected_runtime_claims = _runtime_claims_for_decision(
        decision=retrieval_decision,
        graph_items=graph_items,
    )
    selected_runtime_actions = _runtime_actions_for_decision(
        decision=retrieval_decision,
        graph_items=graph_items,
    )
    selected_runtime_decision_ids = {
        value
        for item in [*selected_runtime_claims, *selected_runtime_actions]
        for value in (str(item.get("action_id", "")), str(item.get("runtime_item_id", "")))
        if value
    }
    selected_action_alignment_rows = [
        row
        for row in action_alignment_rows
        if row.get("verdict") == "aligned"
        and (
            str(row.get("runtime_action_id", "")) in selected_runtime_decision_ids
            or str(row.get("runtime_item_id", "")) in selected_runtime_decision_ids
        )
    ]
    selected_claim_ids = _oracle_ids_for_runtime_items(
        runtime_items=selected_runtime_claims,
        alignments=alignments,
        item_type="claim",
    )
    selected_claim_ids.extend(
        _oracle_claim_ids_for_selected_actions(
            selected_runtime_actions=selected_runtime_actions,
            action_alignment_rows=action_alignment_rows,
        )
    )
    selected_entity_ids = _oracle_subject_ids_for_runtime_claims(
        runtime_items=selected_runtime_claims,
        alignments=alignments,
        scenario=scenario,
    )
    selected_runtime_relations = _runtime_relations_for_claims(
        graph_items=graph_items,
        selected_runtime_claims=selected_runtime_claims,
    )
    selected_relation_ids = _oracle_ids_for_runtime_items(
        runtime_items=selected_runtime_relations,
        alignments=alignments,
        item_type="relation",
    )
    relation_support = {relation_id: "runtime_relation_item" for relation_id in selected_relation_ids}
    expected_action_support = {
        str(row["expected_action_id"]): str(row["support_mode"])
        for row in selected_action_alignment_rows
    }
    execution_state = _production_execution_state(retrieval_decision)
    for claim_id in selected_claim_ids:
        claim = _claim_by_id(scenario, claim_id)
        if claim and claim.subject.entity_id not in selected_entity_ids:
            selected_entity_ids.append(claim.subject.entity_id)
    supporting_claim_ids = list(selected_claim_ids)
    supporting_relation_ids = list(selected_relation_ids) if checkpoint.checkpoint_type != "source_trust_conflict" else []
    context_relation_ids = list(selected_relation_ids) if checkpoint.checkpoint_type == "source_trust_conflict" else []
    supporting_citation_event_ids = _supporting_events_for_claims(
        claim_ids=supporting_claim_ids,
        runtime_claim_by_oracle=runtime_claim_by_oracle,
        item_by_id=item_by_id,
        expected_event_ids=[],
    )
    supporting_citation_event_ids.extend(
        _runtime_action_evidence_events(
            action_alignment_rows=selected_action_alignment_rows,
            item_by_id=item_by_id,
        )
    )
    suppressed_action_claim_ids = _suppressed_action_state_claim_ids(
        scenario=scenario,
        checkpoint=checkpoint,
        graph_items=graph_items,
    )
    rejected_claim_items = [
        item
        for item in graph_items
        if item.get("item_type") == "claim"
        and str(item.get("claim_id", "")) in set(retrieval_decision.rejected_record_ids if retrieval_decision else [])
        and str(item.get("claim_id", "")) not in set(selected_claim_ids)
    ]
    rejected_claim_ids = _oracle_ids_for_runtime_items(
        runtime_items=rejected_claim_items,
        alignments=alignments,
        item_type="claim",
    )
    rejected_claim_ids.extend(suppressed_action_claim_ids)
    context_claim_ids = _oracle_ids_for_runtime_claim_ids(
        claim_ids=retrieval_decision.context_record_ids if retrieval_decision else [],
        alignments=alignments,
    )
    rejected_entity_ids: list[str] = []
    context_entity_ids = _oracle_subject_ids_for_oracle_claim_ids(
        claim_ids=context_claim_ids,
        scenario=scenario,
    )
    rejected_entity_ids.extend(
        _oracle_subject_ids_for_runtime_claims(
            runtime_items=rejected_claim_items,
            alignments=alignments,
            scenario=scenario,
        )
    )
    rejected_entity_ids = [
        entity_id for entity_id in rejected_entity_ids if entity_id not in set(selected_entity_ids)
    ]
    for claim_id in rejected_claim_ids:
        claim = _claim_by_id(scenario, claim_id)
        if (
            claim
            and (claim.subject.entity_id in entity_map or claim_id in suppressed_action_claim_ids)
            and claim.subject.entity_id not in selected_entity_ids
            and claim.subject.entity_id not in rejected_entity_ids
        ):
            rejected_entity_ids.append(claim.subject.entity_id)
    operation: Literal["answer", "next_action", "graph_reconstruction", "abstain"] = _operation_for_checkpoint(
        checkpoint=checkpoint,
        has_selection=bool(selected_claim_ids or selected_relation_ids),
    )
    answer = _runtime_answer_for_checkpoint(
        checkpoint=checkpoint,
        selected_claim_ids=selected_claim_ids,
        runtime_claim_by_oracle=runtime_claim_by_oracle,
        item_by_id=item_by_id,
    )
    next_action = _next_action_from_runtime_state(execution_state) if operation == "next_action" else None
    belief_ranking_ids = list(selected_claim_ids) if checkpoint.checkpoint_type == "belief_ranking" else []
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
        context_entity_ids=_ordered_unique(context_entity_ids),
        context_claim_ids=_ordered_unique(context_claim_ids),
        context_relation_ids=_ordered_unique(context_relation_ids),
        context_citation_event_ids=[],
        belief_ranking_ids=_ordered_unique(belief_ranking_ids),
        answer=answer,
        next_action=next_action,
        uncertain_ids=[],
        confidence=confidence,
        rationale="runtime graph candidates selected from query and production state; oracle IDs added only at comparison boundary",
    )
    return RuntimeProjection(
        output=output,
        graph_snapshot=graph_snapshot,
        graph_items=graph_items,
        alignments=alignments,
        source_id_to_event_id=source_id_to_event_id,
        relation_support=relation_support,
        action_support=expected_action_support,
        action_alignment_rows=[
            RuntimeActionAlignmentRow.from_runtime_alignment(row)
            for row in action_alignment_rows
        ],
        execution_state=RuntimeExecutionStateSection.model_validate(execution_state),
        work_state=work_state,
        retrieval_decision=retrieval_decision,
    )


def _runtime_claims_for_decision(
    *,
    decision: ProductionRetrievalDecision | None,
    graph_items: list[dict[str, object]],
) -> list[dict[str, object]]:
    if decision is None:
        return []
    selected_ids = set(decision.selected_record_ids)
    return [
        item
        for item in graph_items
        if item.get("item_type") == "claim" and str(item.get("claim_id", "")) in selected_ids
    ]


def _runtime_actions_for_decision(
    *,
    decision: ProductionRetrievalDecision | None,
    graph_items: list[dict[str, object]],
) -> list[dict[str, object]]:
    if decision is None:
        return []
    selected_ids = set(decision.selected_record_ids)
    return [
        item
        for item in graph_items
        if item.get("item_type") == "action"
        and (
            str(item.get("action_id", "")) in selected_ids
            or str(item.get("action_id", "")).removeprefix("action:") in selected_ids
            or str(item.get("runtime_item_id", "")) in selected_ids
        )
    ]


def _oracle_claim_ids_for_selected_actions(
    *,
    selected_runtime_actions: list[dict[str, object]],
    action_alignment_rows: list[dict[str, object]],
) -> list[str]:
    selected_runtime_ids = {
        value
        for item in selected_runtime_actions
        for value in (str(item.get("action_id", "")), str(item.get("runtime_item_id", "")))
        if value
    }
    claim_ids: list[str] = []
    for row in action_alignment_rows:
        if row.get("verdict") != "aligned":
            continue
        if str(row.get("runtime_action_id", "")) not in selected_runtime_ids and str(row.get("runtime_item_id", "")) not in selected_runtime_ids:
            continue
        action_id = str(row.get("expected_action_id", ""))
        if action_id.startswith("action:"):
            claim_ids.append(action_id.removeprefix("action:"))
    return _ordered_unique(claim_ids)


def _production_execution_state(decision: ProductionRetrievalDecision | None) -> dict[str, object]:
    if decision is None:
        return {
            "status": "unavailable",
            "reason": "production_retrieval_decision_required",
            "active_continuation_branch": None,
            "suppressed_branch_ids": [],
            "ambiguous_action_count": 0,
        }
    if decision.execution_state is None:
        state: dict[str, object] = {}
        continuation: Mapping[str, object] = {}
        work_state: Mapping[str, object] = {}
    else:
        continuation = decision.execution_state.continuation.model_dump(mode="json")
        work_state = decision.execution_state.work_state.model_dump(mode="json")
        state = {
            "states": work_state.get("states", []),
            "active_branch_ids": work_state.get("active_branch_ids", []),
            "suppressed_branch_ids": work_state.get("suppressed_branch_ids", []),
            "ambiguous_branch_ids": work_state.get("ambiguous_branch_ids", []),
            "continuation_decision": continuation,
            "production_work_state": work_state,
        }
        state["active_continuation_branch"] = continuation.get("branch_id")
        candidate_ids = continuation.get("candidate_branch_ids", [])
        state["ambiguous_action_count"] = (
            len(candidate_ids)
            if continuation.get("status") == "ambiguous" and isinstance(candidate_ids, Sequence)
            else 0
        )
    state.setdefault("active_continuation_branch", None)
    state.setdefault("suppressed_branch_ids", [])
    state.setdefault("ambiguous_action_count", 0)
    state["decision_status"] = decision.resolution_status
    state["decision_abstained"] = decision.abstained
    return state


def _runtime_relations_for_claims(
    *,
    graph_items: list[dict[str, object]],
    selected_runtime_claims: list[dict[str, object]],
) -> list[dict[str, object]]:
    selected_runtime_ids = {str(item.get("runtime_item_id", "")) for item in selected_runtime_claims}
    selected_claim_ids = {str(item.get("claim_id", "")) for item in selected_runtime_claims}
    return [
        item
        for item in graph_items
        if item.get("item_type") == "relation"
        and (
            str(item.get("source", "")) in selected_runtime_ids
            or str(item.get("target", "")) in selected_runtime_ids
            or str(item.get("source", "")) in selected_claim_ids
            or str(item.get("target", "")) in selected_claim_ids
        )
    ]


def _oracle_ids_for_runtime_items(*, runtime_items: list[dict[str, object]], alignments: Sequence[object], item_type: str) -> list[str]:
    runtime_ids = {str(item.get("runtime_item_id", "")) for item in runtime_items}
    return _ordered_unique(
        [
            str(getattr(alignment, "oracle_item_id", ""))
            for alignment in alignments
            if getattr(alignment, "item_type", "") == item_type
            and str(getattr(alignment, "runtime_item_id", "")) in runtime_ids
            and getattr(alignment, "verdict", None) == RuntimeGraphAlignmentVerdict.ALIGNED
            and getattr(alignment, "oracle_item_id", None)
        ]
    )


def _oracle_ids_for_runtime_claim_ids(*, claim_ids: Sequence[str], alignments: Sequence[object]) -> list[str]:
    wanted = set(str(claim_id) for claim_id in claim_ids)
    return _ordered_unique([
        str(getattr(alignment, "oracle_item_id", ""))
        for alignment in alignments
        if getattr(alignment, "item_type", "") == "claim"
        and getattr(alignment, "verdict", None) == RuntimeGraphAlignmentVerdict.ALIGNED
        and str(getattr(alignment, "oracle_item_id", "")) in wanted
    ])


def _oracle_subject_ids_for_oracle_claim_ids(*, claim_ids: Sequence[str], scenario: LatentGraphScenario) -> list[str]:
    wanted = set(claim_ids)
    return _ordered_unique([
        claim.subject.entity_id
        for claim in scenario.claims
        if claim.claim_id in wanted
    ])


def _oracle_subject_ids_for_runtime_claims(*, runtime_items: list[dict[str, object]], alignments: Sequence[object], scenario: LatentGraphScenario) -> list[str]:
    oracle_claim_ids = _oracle_ids_for_runtime_items(runtime_items=runtime_items, alignments=alignments, item_type="claim")
    return _ordered_unique(
        [
            claim.subject.entity_id
            for claim in scenario.claims
            if claim.claim_id in oracle_claim_ids
        ]
    )


def _runtime_action_evidence_events(
    *,
    action_alignment_rows: list[dict[str, object]],
    item_by_id: Mapping[str, dict[str, object]],
) -> list[str]:
    events: list[str] = []
    for row in action_alignment_rows:
        if row.get("verdict") != "aligned":
            continue
        item = item_by_id.get(str(row.get("runtime_item_id", "")))
        if item is None:
            continue
        events.extend(str(value) for value in _sequence(item.get("evidence_event_ids")))
    return _ordered_unique(events)


def _operation_for_checkpoint(*, checkpoint: OracleCheckpoint, has_selection: bool) -> Literal["answer", "next_action", "graph_reconstruction", "abstain"]:
    if not has_selection:
        return "abstain"
    if checkpoint.checkpoint_type == "execution_continuation":
        return "next_action"
    if checkpoint.checkpoint_type in {"entity_reconstruction", "entity_split_repair", "claim_rekey", "conflict_audit"}:
        return "graph_reconstruction"
    return "answer"


def _next_action_from_runtime_state(execution_state: Mapping[str, object]) -> str | None:
    branch = str(execution_state.get("active_continuation_branch", "")).strip()
    return f"Continue {branch}" if branch else None


def _sequence(value: object) -> Sequence[object]:
    return value if isinstance(value, Sequence) and not isinstance(value, str) else ()


def _runtime_relation_support_rows(projection: RuntimeProjection) -> list[dict[str, str]]:
    return [
        {"relation_id": relation_id, "support_mode": support_mode}
        for relation_id, support_mode in sorted(projection.relation_support.items())
    ]


def _expected_claim_ids_for_projection(checkpoint: OracleCheckpoint) -> list[str]:
    if checkpoint.checkpoint_type == "execution_continuation":
        return list(checkpoint.expected_execution_claim_ids)
    return list(checkpoint.expected_claim_ids)


def _expected_entity_ids_for_projection(checkpoint: OracleCheckpoint) -> list[str]:
    if checkpoint.checkpoint_type == "execution_continuation":
        return list(checkpoint.expected_execution_entity_ids)
    return list(checkpoint.expected_entity_ids)


def _expected_event_ids_for_projection(checkpoint: OracleCheckpoint) -> list[str]:
    if checkpoint.checkpoint_type == "execution_continuation":
        return list(checkpoint.expected_execution_citation_event_ids)
    return list(checkpoint.expected_citation_event_ids)


def runtime_failure_buckets(
    *,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
    aggregate: JudgeAggregate,
    projection: RuntimeProjection,
    graph_snapshot: MemoryGraphSnapshot,
) -> list[str]:
    buckets: list[str] = []
    expected_claim_ids = _expected_claim_ids_for_projection(checkpoint)
    expected_entity_ids = _expected_entity_ids_for_projection(checkpoint)
    expected_event_ids = _expected_event_ids_for_projection(checkpoint)
    if graph_snapshot.validation_errors:
        buckets.append("runtime_graph_validation_error")
    selected = set(output.selected_claim_ids)
    missing_claims = [claim_id for claim_id in expected_claim_ids if claim_id not in selected]
    if missing_claims:
        buckets.append("runtime_missing_expected_claim")
        if checkpoint.horizon_distance >= 10:
            buckets.append("long_horizon_retrieval_miss")
    missing_entities = [entity_id for entity_id in expected_entity_ids if entity_id not in output.selected_entity_ids]
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
    if expected_event_ids and not set(expected_event_ids) & set(output.supporting_citation_event_ids):
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
    relation_map: Mapping[str, object],
    runtime_claim_by_oracle: Mapping[str, str | None],
) -> dict[str, str]:
    support: dict[str, str] = {}
    for relation_id in expected_relation_ids:
        if relation_id in relation_map:
            support[relation_id] = "runtime_relation_item"
        elif _relation_supported_by_claims(scenario, relation_id, runtime_claim_by_oracle):
            support[relation_id] = "claim_derived"
    return support

def _runtime_answer_for_checkpoint(
    *,
    checkpoint: OracleCheckpoint,
    selected_claim_ids: list[str],
    runtime_claim_by_oracle: Mapping[str, str | None],
    item_by_id: Mapping[str, Mapping[str, object]],
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
    item = item_by_id.get(runtime_id, {})
    if checkpoint.answer_projection_policy == "claim_subject":
        return _title_from_normalized(str(item.get("subject") or "")) or None
    return str(item.get("object_value") or item.get("object") or "") or None

def _mean_runtime_confidence(
    *,
    selected_claim_ids: list[str],
    runtime_claim_by_oracle: Mapping[str, str | None],
    item_by_id: Mapping[str, Mapping[str, object]],
) -> float:
    values = []
    for claim_id in selected_claim_ids:
        runtime_id = runtime_claim_by_oracle.get(claim_id)
        if runtime_id is None:
            continue
        raw_confidence = item_by_id.get(runtime_id, {}).get("confidence", 0.5)
        if not isinstance(raw_confidence, (int, float, str)):
            continue
        with suppress(TypeError, ValueError):
            values.append(float(raw_confidence))
    if not values:
        return 0.35
    return max(0.0, min(1.0, sum(values) / len(values)))

def _supporting_events_for_claims(
    *,
    claim_ids: list[str],
    runtime_claim_by_oracle: Mapping[str, str | None],
    item_by_id: Mapping[str, Mapping[str, object]],
    expected_event_ids: list[str],
) -> list[str]:
    events: list[str] = []
    for claim_id in claim_ids:
        runtime_id = runtime_claim_by_oracle.get(claim_id)
        if runtime_id is None:
            continue
        item = item_by_id.get(runtime_id, {})
        evidence_value = item.get("evidence_event_ids", [])
        evidence_items: Sequence[object] = evidence_value if isinstance(evidence_value, Sequence) and not isinstance(evidence_value, str) else ()
        evidence = [str(event_id) for event_id in evidence_items if event_id]
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

def _relation_supported_by_claims(scenario: LatentGraphScenario, relation_id: str, runtime_claim_by_oracle: Mapping[str, str | None]) -> bool:
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
