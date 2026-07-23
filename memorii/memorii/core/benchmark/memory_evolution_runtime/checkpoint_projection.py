"""Runtime checkpoint projection helpers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal

from memorii.core.benchmark.artifact_rows import (
    RuntimeActionAlignmentRow,
    RuntimeExecutionStateSection,
    RuntimeRelationSupportRow,
)
from memorii.core.benchmark.calibration.alignment import RuntimeGraphAlignment, RuntimeGraphAlignmentVerdict
from memorii.core.benchmark.memory_evolution_runtime.alignment import align_runtime_graph_to_oracle, best_alignment_map
from memorii.core.benchmark.memory_evolution_runtime.checkpoint_evaluation import (
    mean_runtime_confidence,
    runtime_answer_for_checkpoint,
    supporting_events_for_claims,
)
from memorii.core.benchmark.memory_evolution_runtime.execution_state_projection import (
    expected_action_alignment_rows,
    suppressed_action_state_claim_ids,
)
from memorii.core.benchmark.memory_evolution_runtime.models import (
    RuntimeActionGraphItemRow,
    RuntimeClaimGraphItemRow,
    RuntimeGraphItem,
    RuntimeProjection,
    RuntimeRelationGraphItemRow,
)
from memorii.core.benchmark.memory_evolution_runtime.utils import claim_by_id, ordered_unique
from memorii.core.benchmark.memory_evolution_sim import (
    LatentGraphScenario,
    OracleCheckpoint,
    SimSystemOutput,
)
from memorii.core.memory_evolution import MemoryGraphSnapshot, ProductionRetrievalDecision, WorkStateSnapshot


def project_runtime_checkpoint(
    *,
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    graph_snapshot: MemoryGraphSnapshot,
    graph_items: list[RuntimeGraphItem],
    source_id_to_event_id: dict[str, str],
    work_state: WorkStateSnapshot | None = None,
    retrieval_decision: ProductionRetrievalDecision | None = None,
) -> RuntimeProjection:
    alignments = align_runtime_graph_to_oracle(
        scenario=scenario,
        graph_items=graph_items,
    )
    entity_map = best_alignment_map(alignments, item_type="entity")
    runtime_claim_by_oracle = {
        alignment.oracle_item_id: alignment.runtime_item_id
        for alignment in alignments
        if alignment.item_type == "claim"
        and alignment.verdict == RuntimeGraphAlignmentVerdict.ALIGNED
        and alignment.oracle_item_id
    }
    item_by_id = {item.runtime_item_id: item for item in graph_items}

    action_alignment_rows = expected_action_alignment_rows(
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
        item.runtime_item_id for item in [*selected_runtime_claims, *selected_runtime_actions]
    }
    selected_runtime_decision_ids.update(item.action_id for item in selected_runtime_actions)
    selected_action_alignment_rows = [
        row
        for row in action_alignment_rows
        if row.verdict == "aligned"
        and (
            row.runtime_action_id in selected_runtime_decision_ids
            or row.runtime_item_id in selected_runtime_decision_ids
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
    expected_action_support = {row.expected_action_id: row.support_mode for row in selected_action_alignment_rows}
    execution_state = _production_execution_state(retrieval_decision)
    for claim_id in selected_claim_ids:
        claim = claim_by_id(scenario, claim_id)
        if claim and claim.subject.entity_id not in selected_entity_ids:
            selected_entity_ids.append(claim.subject.entity_id)
    supporting_claim_ids = list(selected_claim_ids)
    supporting_relation_ids = (
        list(selected_relation_ids) if checkpoint.checkpoint_type != "source_trust_conflict" else []
    )
    context_relation_ids = list(selected_relation_ids) if checkpoint.checkpoint_type == "source_trust_conflict" else []
    supporting_citation_event_ids = supporting_events_for_claims(
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
    suppressed_action_claim_ids = suppressed_action_state_claim_ids(
        scenario=scenario,
        checkpoint=checkpoint,
        graph_items=graph_items,
    )
    rejected_claim_items = [
        item
        for item in graph_items
        if item.item_type == "claim"
        and item.claim_id in set(retrieval_decision.rejected_record_ids if retrieval_decision else [])
        and item.claim_id not in set(selected_claim_ids)
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
    rejected_entity_ids = [entity_id for entity_id in rejected_entity_ids if entity_id not in set(selected_entity_ids)]
    for claim_id in rejected_claim_ids:
        claim = claim_by_id(scenario, claim_id)
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
    answer = runtime_answer_for_checkpoint(
        checkpoint=checkpoint,
        selected_claim_ids=selected_claim_ids,
        runtime_claim_by_oracle=runtime_claim_by_oracle,
        item_by_id=item_by_id,
    )
    next_action = _next_action_from_runtime_state(execution_state) if operation == "next_action" else None
    belief_ranking_ids = list(selected_claim_ids) if checkpoint.checkpoint_type == "belief_ranking" else []
    confidence = mean_runtime_confidence(
        selected_claim_ids=selected_claim_ids, runtime_claim_by_oracle=runtime_claim_by_oracle, item_by_id=item_by_id
    )
    output = SimSystemOutput(
        operation=operation,
        selected_entity_ids=ordered_unique(selected_entity_ids),
        selected_claim_ids=ordered_unique(selected_claim_ids),
        selected_relation_ids=ordered_unique(
            selected_relation_ids if checkpoint.checkpoint_type != "source_trust_conflict" else []
        ),
        supporting_claim_ids=ordered_unique(supporting_claim_ids),
        supporting_relation_ids=ordered_unique(supporting_relation_ids),
        supporting_citation_event_ids=ordered_unique(supporting_citation_event_ids),
        rejected_entity_ids=ordered_unique(rejected_entity_ids),
        rejected_claim_ids=ordered_unique(rejected_claim_ids),
        rejected_relation_ids=[],
        context_entity_ids=ordered_unique(context_entity_ids),
        context_claim_ids=ordered_unique(context_claim_ids),
        context_relation_ids=ordered_unique(context_relation_ids),
        context_citation_event_ids=[],
        belief_ranking_ids=ordered_unique(belief_ranking_ids),
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
        action_alignment_rows=action_alignment_rows,
        execution_state=execution_state,
        work_state=work_state,
        retrieval_decision=retrieval_decision,
    )


def _runtime_claims_for_decision(
    *,
    decision: ProductionRetrievalDecision | None,
    graph_items: list[RuntimeGraphItem],
) -> list[RuntimeClaimGraphItemRow]:
    if decision is None:
        return []
    selected_ids = set(decision.selected_record_ids)
    return [item for item in graph_items if item.item_type == "claim" and item.claim_id in selected_ids]


def _runtime_actions_for_decision(
    *,
    decision: ProductionRetrievalDecision | None,
    graph_items: list[RuntimeGraphItem],
) -> list[RuntimeActionGraphItemRow]:
    if decision is None:
        return []
    selected_ids = set(decision.selected_record_ids)
    return [
        item
        for item in graph_items
        if item.item_type == "action"
        and (
            item.action_id in selected_ids
            or item.action_id.removeprefix("action:") in selected_ids
            or item.runtime_item_id in selected_ids
        )
    ]


def _oracle_claim_ids_for_selected_actions(
    *,
    selected_runtime_actions: list[RuntimeActionGraphItemRow],
    action_alignment_rows: list[RuntimeActionAlignmentRow],
) -> list[str]:
    selected_runtime_ids = {
        value for item in selected_runtime_actions for value in (item.action_id, item.runtime_item_id) if value
    }
    claim_ids: list[str] = []
    for row in action_alignment_rows:
        if row.verdict != "aligned":
            continue
        if row.runtime_action_id not in selected_runtime_ids and row.runtime_item_id not in selected_runtime_ids:
            continue
        action_id = row.expected_action_id
        if action_id.startswith("action:"):
            claim_ids.append(action_id.removeprefix("action:"))
    return ordered_unique(claim_ids)


def _production_execution_state(
    decision: ProductionRetrievalDecision | None,
) -> RuntimeExecutionStateSection:
    if decision is None:
        return RuntimeExecutionStateSection(
            status="unavailable",
            reason="production_retrieval_decision_required",
        )
    if decision.execution_state is None:
        return RuntimeExecutionStateSection(
            decision_status=decision.resolution_status,
            decision_abstained=decision.abstained,
        )
    execution_state = decision.execution_state
    work_state = execution_state.work_state
    continuation = execution_state.continuation
    return RuntimeExecutionStateSection(
        active_continuation_branch=continuation.branch_id,
        suppressed_branch_ids=list(work_state.suppressed_branch_ids),
        ambiguous_action_count=(len(continuation.candidate_branch_ids) if continuation.status == "ambiguous" else 0),
        decision_status=decision.resolution_status,
        decision_abstained=decision.abstained,
        active_branch_ids=list(work_state.active_branch_ids),
        states=list(work_state.states),
        ambiguous_branch_ids=list(work_state.ambiguous_branch_ids),
        continuation_decision=continuation,
        production_work_state=work_state,
    )


def _runtime_relations_for_claims(
    *,
    graph_items: list[RuntimeGraphItem],
    selected_runtime_claims: list[RuntimeClaimGraphItemRow],
) -> list[RuntimeRelationGraphItemRow]:
    selected_runtime_ids = {item.runtime_item_id for item in selected_runtime_claims}
    selected_claim_ids = {item.claim_id for item in selected_runtime_claims}
    selected_entity_ids = {
        entity_id
        for item in selected_runtime_claims
        for entity_id in (item.subject_entity_id, item.object_entity_id)
        if entity_id
    }
    return [
        item
        for item in graph_items
        if item.item_type == "relation"
        and (
            item.source in selected_runtime_ids
            or item.target in selected_runtime_ids
            or item.source in selected_claim_ids
            or item.target in selected_claim_ids
            or item.source in selected_entity_ids
            or item.target in selected_entity_ids
        )
    ]


def _oracle_ids_for_runtime_items(
    *, runtime_items: Sequence[RuntimeGraphItem], alignments: Sequence[RuntimeGraphAlignment], item_type: str
) -> list[str]:
    runtime_ids = {item.runtime_item_id for item in runtime_items}
    return ordered_unique(
        [
            str(alignment.oracle_item_id or "")
            for alignment in alignments
            if alignment.item_type == item_type
            and str(alignment.runtime_item_id or "") in runtime_ids
            and alignment.verdict == RuntimeGraphAlignmentVerdict.ALIGNED
            and alignment.oracle_item_id
        ]
    )


def _oracle_ids_for_runtime_claim_ids(
    *, claim_ids: Sequence[str], alignments: Sequence[RuntimeGraphAlignment]
) -> list[str]:
    wanted = set(str(claim_id) for claim_id in claim_ids)
    return ordered_unique(
        [
            str(alignment.oracle_item_id or "")
            for alignment in alignments
            if alignment.item_type == "claim"
            and alignment.verdict == RuntimeGraphAlignmentVerdict.ALIGNED
            and str(alignment.oracle_item_id or "") in wanted
        ]
    )


def _oracle_subject_ids_for_oracle_claim_ids(*, claim_ids: Sequence[str], scenario: LatentGraphScenario) -> list[str]:
    wanted = set(claim_ids)
    return ordered_unique([claim.subject.entity_id for claim in scenario.claims if claim.claim_id in wanted])


def _oracle_subject_ids_for_runtime_claims(
    *,
    runtime_items: Sequence[RuntimeClaimGraphItemRow],
    alignments: Sequence[RuntimeGraphAlignment],
    scenario: LatentGraphScenario,
) -> list[str]:
    oracle_claim_ids = _oracle_ids_for_runtime_items(
        runtime_items=runtime_items, alignments=alignments, item_type="claim"
    )
    return ordered_unique([claim.subject.entity_id for claim in scenario.claims if claim.claim_id in oracle_claim_ids])


def _runtime_action_evidence_events(
    *,
    action_alignment_rows: list[RuntimeActionAlignmentRow],
    item_by_id: Mapping[str, RuntimeGraphItem],
) -> list[str]:
    events: list[str] = []
    for row in action_alignment_rows:
        if row.verdict != "aligned":
            continue
        item = item_by_id.get(row.runtime_item_id)
        if item is None:
            continue
        events.extend(item.evidence_event_ids)
    return ordered_unique(events)


def _operation_for_checkpoint(
    *, checkpoint: OracleCheckpoint, has_selection: bool
) -> Literal["answer", "next_action", "graph_reconstruction", "abstain"]:
    if not has_selection:
        return "abstain"
    if checkpoint.checkpoint_type == "execution_continuation":
        return "next_action"
    if checkpoint.checkpoint_type in {"entity_reconstruction", "entity_split_repair", "claim_rekey", "conflict_audit"}:
        return "graph_reconstruction"
    return "answer"


def _next_action_from_runtime_state(execution_state: RuntimeExecutionStateSection) -> str | None:
    branch = (execution_state.active_continuation_branch or "").strip()
    return f"Continue {branch}" if branch else None


def _sequence(value: object) -> Sequence[object]:
    return value if isinstance(value, Sequence) and not isinstance(value, str) else ()


def runtime_relation_support_rows(projection: RuntimeProjection) -> list[RuntimeRelationSupportRow]:
    return [
        RuntimeRelationSupportRow(relation_id=relation_id, support_mode=support_mode)
        for relation_id, support_mode in sorted(projection.relation_support.items())
    ]
