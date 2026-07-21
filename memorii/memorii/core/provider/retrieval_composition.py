"""Pure provider retrieval-channel arbitration and rendering."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from memorii.core.memory_evolution.models import ClaimState
from memorii.core.memory_evolution.retrieval_contracts import (
    ProductionRetrievalDecision,
    SemanticFrameStatus,
)
from memorii.core.provider.models import (
    RetrievalChannelAuthority,
    RetrievalChannelResult,
    RetrievalChannelStatus,
)


def build_evolution_channel_result(
    *,
    context: str,
    decision: ProductionRetrievalDecision | None,
) -> RetrievalChannelResult:
    if decision is None:
        return RetrievalChannelResult(
            channel="evolution",
            status=RetrievalChannelStatus.NO_MATCH,
            authority=RetrievalChannelAuthority.NONE,
            context="",
            reason="evolution_decision_unavailable",
        )
    if decision.abstained:
        return RetrievalChannelResult(
            channel="evolution",
            status=RetrievalChannelStatus.ABSTAIN,
            authority=(
                RetrievalChannelAuthority.AUTHORITATIVE
                if decision.semantic_frame_status == SemanticFrameStatus.MATCHED
                else RetrievalChannelAuthority.NONE
            ),
            context=context,
            reason=decision.abstention_reason or "evolution_abstained",
        )
    if not decision.selected_record_ids:
        return RetrievalChannelResult(
            channel="evolution",
            status=RetrievalChannelStatus.NO_MATCH,
            authority=RetrievalChannelAuthority.NONE,
            context=context,
            reason="no_evolution_records_matched",
        )
    if not context:
        return RetrievalChannelResult(
            channel="evolution",
            status=RetrievalChannelStatus.ERROR,
            authority=RetrievalChannelAuthority.NONE,
            context="",
            selected_record_ids=list(decision.selected_record_ids),
            reason="selected_evolution_records_could_not_be_rendered",
        )
    return RetrievalChannelResult(
        channel="evolution",
        status=RetrievalChannelStatus.ANSWER,
        authority=RetrievalChannelAuthority.AUTHORITATIVE,
        context=context,
        selected_record_ids=list(decision.selected_record_ids),
    )


def arbitrate_retrieval_channels(
    *,
    canonical: RetrievalChannelResult,
    evolution: RetrievalChannelResult,
) -> tuple[Literal["canonical", "evolution", "none"], str]:
    if (
        evolution.status == RetrievalChannelStatus.ANSWER
        and evolution.authority == RetrievalChannelAuthority.AUTHORITATIVE
    ):
        return "evolution", evolution.context
    if (
        canonical.status == RetrievalChannelStatus.ANSWER
        and canonical.authority == RetrievalChannelAuthority.AUTHORITATIVE
    ):
        return "canonical", canonical.context
    if (
        evolution.status == RetrievalChannelStatus.ABSTAIN
        and evolution.authority == RetrievalChannelAuthority.AUTHORITATIVE
    ):
        return "evolution", evolution.context
    if canonical.status == RetrievalChannelStatus.ANSWER:
        return "canonical", canonical.context
    if evolution.context:
        return "evolution", evolution.context
    return "none", canonical.context


def format_evolution_claim_decision(
    decision: ProductionRetrievalDecision,
    *,
    states: Mapping[str, ClaimState],
    top_k: int,
) -> str:
    lines = ["Evolution memory (production retrieval):"]
    for item in decision.context_items[:top_k]:
        state = states.get(item.claim_id)
        if state is None:
            continue
        evidence_ids = [
            evidence.source_id for evidence in decision.evidence if evidence.claim_id == item.claim_id
        ]
        citations = f"; citations={','.join(evidence_ids)}" if evidence_ids else ""
        lines.append(
            f"- [{item.channel}] {state.claim_key.subject_entity_id} "
            f"{state.claim_key.predicate_id} = {state.object_value}{citations}"
        )
    return "\n".join(lines) if len(lines) > 1 else ""


def format_evolution_execution_decision(decision: ProductionRetrievalDecision) -> str:
    lines = ["Evolution execution (production retrieval):"]
    candidate_branch_ids = (
        set(decision.execution_state.continuation.candidate_branch_ids) if decision.execution_state else set()
    )
    active_states = (
        [
            state
            for state in decision.execution_state.work_state.states
            if state.active and state.branch_id in candidate_branch_ids
        ]
        if decision.execution_state
        else []
    )
    for state in active_states:
        lines.append(
            f"- Active branch {state.branch_id}: {state.status.value} "
            f"(last event {state.last_event_id})"
        )
    if decision.selected_record_ids:
        lines.append(f"- Selected continuation events: {', '.join(decision.selected_record_ids)}")
    return "\n".join(lines)
