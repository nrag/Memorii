"""Authored checkpoint policy shared by decision construction and judging."""

from __future__ import annotations

from typing import Literal

from memorii.core.benchmark.memory_evolution_decision.contracts import (
    DEGRADED_BELIEF_SCORE_MAX,
    MemoryEvolutionAnswerTemporalMode,
    MemoryEvolutionBeliefScorePolicy,
    MemoryEvolutionCheckpoint,
    MemoryEvolutionCheckpointContract,
    MemoryEvolutionCheckpointKind,
    MemoryEvolutionScenario,
)
from memorii.core.benchmark.memory_evolution_decision.utils import dedupe_string_ids


def checkpoint_contract(
    *,
    scenario: MemoryEvolutionScenario,
    checkpoint: MemoryEvolutionCheckpoint,
) -> MemoryEvolutionCheckpointContract:
    """Return the fixture-authored contract without inferring policy from query text."""

    del scenario
    return checkpoint.contract


def evidence_effect_policy(contract: MemoryEvolutionCheckpointContract) -> dict[str, str]:
    if contract.checkpoint_kind != MemoryEvolutionCheckpointKind.BELIEF_RANKING:
        return {}
    return {
        "source": "surface-derived evidence_effect_cards",
        "ranking_order": "supported > neutral > weakened > falsified",
        "neutral_rule": "A visible hypothesis with no support or weakening outranks an explicitly weakened hypothesis.",
    }


def temporal_grounding_policy() -> dict[str, str]:
    return {
        "query_temporal_frame": "Resolve the time/scope frame of the query before selecting memories.",
        "entity_state_cards": "Use valid_from/valid_to and record_lifecycle to distinguish query-applicable state from checkpoint-current memory record state.",
        "content_state_warning": "Words such as archived, closed, inactive, deprecated, or abandoned in a fact describe the subject state, not the memory record lifecycle.",
    }


def output_channel_contract(contract: MemoryEvolutionCheckpointContract) -> dict[str, str]:
    base = {
        "answer_projection_policy": f"Project answer text using {contract.answer_projection_policy.value}; do not infer projection from English query phrasing.",
        "query_temporal_frame": "Resolve query time and scope before selecting memories.",
        "answer_selection.selected_memory_ids": "Final answer or decision memories only.",
        "answer_selection.supporting_memory_ids": "Memories that directly support the selected answer or next action.",
        "answer_selection.citation_memory_ids": "Direct evidence/source memory ids only.",
        "answer_selection.temporal_mode": "Query temporal mode; scope belongs only in query_temporal_frame.",
        "lifecycle_snapshot.checkpoint_active_record_ids": "Memory records asserted by the graph at checkpoint time, independent of query relevance.",
        "lifecycle_snapshot.checkpoint_superseded_record_ids": "Memory records superseded, invalidated, blocked, lower-trust, or no longer current.",
        "lifecycle_snapshot.checkpoint_retained_record_ids": "Memory records retained for audit/history only.",
        "retrieval_context.query_relevant_memory_ids": "Memories useful for interpreting the query or answer.",
        "retrieval_context.query_historical_memory_ids": "Memories relevant to past state or supersession.",
        "retrieval_context.query_context_memory_ids": "Audit context that is neither final truth nor direct support.",
        "retrieval_context.rejected_memory_ids": "Stale, blocked, falsified, lower-trust, wrong-scope, or wrong-entity memories.",
        "excluded_memory_policy": (
            f"{contract.excluded_memory_policy.value}: expected excluded memories require an explicit rejection, "
            "context, or suppressed-branch signal."
        ),
        "lifecycle_expectation_scope": "Use full-graph expectations only when explicit expected_full_* fields exist.",
    }
    if contract.belief_score_policy != MemoryEvolutionBeliefScorePolicy.NONE:
        base["belief_scores"] = "Rank and evaluate belief ids; score order must agree with selection and answer text."
        base["evaluated_belief_ids"] = "Belief candidates under evaluation; this is not an answer-support channel."
    if contract.belief_score_policy == MemoryEvolutionBeliefScorePolicy.DEGRADED_THRESHOLD:
        base["belief_score_calibration"] = (
            f"Emit degraded scores in [0.0, {DEGRADED_BELIEF_SCORE_MAX:.2f}] and use belief_state for content state."
        )
    if contract.checkpoint_kind == MemoryEvolutionCheckpointKind.CURRENT_TRUTH:
        base["source_trust_conflict"] = "Select the highest-authority current claim and reject weaker contradictions."
    if contract.checkpoint_kind == MemoryEvolutionCheckpointKind.BELIEF_DEGRADATION:
        base["answer_selection.selected_memory_ids"] = "Select falsifying/current evidence when no belief remains confident."
    if contract.checkpoint_kind == MemoryEvolutionCheckpointKind.EXECUTION_CONTINUATION:
        base.update(
            {
                "execution_selection.selected_action_memory_ids": "Select the active continuation action.",
                "execution_selection.active_work_state_memory_ids": "Select the current active branch/work state.",
                "execution_selection.command_context_memory_ids": "Command events are context, not active state.",
                "execution_selection.suppressed_branch_memory_ids": "Blocked, abandoned, stale, or lower-priority branches.",
                "next_action": "Emit a non-empty action for the selected active branch.",
            }
        )
    return base


def lifecycle_expected_ids(
    *,
    checkpoint: MemoryEvolutionCheckpoint,
    lifecycle_kind: Literal["active", "superseded", "retained"],
) -> list[str]:
    full_ids = {
        "active": checkpoint.expected_full_checkpoint_active_record_ids,
        "superseded": checkpoint.expected_full_checkpoint_superseded_record_ids,
        "retained": checkpoint.expected_full_checkpoint_retained_record_ids,
    }[lifecycle_kind]
    if full_ids:
        return list(full_ids)
    return list(
        {
            "active": checkpoint.expected_checkpoint_active_record_ids,
            "superseded": checkpoint.expected_checkpoint_superseded_record_ids,
            "retained": checkpoint.expected_checkpoint_retained_record_ids,
        }[lifecycle_kind]
    )


def expected_belief_ids(checkpoint: MemoryEvolutionCheckpoint) -> list[str]:
    return dedupe_string_ids(
        [
            *checkpoint.expected_belief_ranking,
            *checkpoint.expected_belief_scores.keys(),
            *(expectation.memory_id for expectation in checkpoint.expected_belief_states),
        ]
    )


def expected_rejected_memory_ids(
    *,
    checkpoint: MemoryEvolutionCheckpoint,
    contract: MemoryEvolutionCheckpointContract,
) -> list[str]:
    candidates = [
        *checkpoint.expected_excluded_memory_ids,
        *checkpoint.expected_checkpoint_superseded_record_ids,
    ]
    if contract.answer_temporal_mode == MemoryEvolutionAnswerTemporalMode.HISTORICAL:
        historical_answer_ids = set(checkpoint.expected_retrieval_ids)
        candidates = [memory_id for memory_id in candidates if memory_id not in historical_answer_ids]
    return dedupe_string_ids(candidates)
