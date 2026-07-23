"""Temporal-frame and record-lifecycle diagnostics for benchmark decisions."""

from __future__ import annotations

import re

from memorii.core.benchmark.memory_evolution_decision.contracts import (
    MemoryEvolutionAnswerTemporalMode,
    MemoryEvolutionCheckpoint,
    MemoryEvolutionCheckpointContract,
    MemoryEvolutionEvent,
    MemoryEvolutionScenario,
    MemoryEvolutionScopeKeyPolicy,
    MemoryEvolutionScopeKind,
    MemoryEvolutionScopeMatchPolicy,
    MemoryEvolutionTemporalFrame,
    MemoryEvolutionTemporalIntervalPolicy,
    MemoryEvolutionTemporalKind,
)
from memorii.core.benchmark.memory_evolution_decision.utils import normalize_decision_text


def expected_temporal_frame(
    *,
    checkpoint: MemoryEvolutionCheckpoint,
    contract: MemoryEvolutionCheckpointContract,
) -> MemoryEvolutionTemporalFrame:
    if checkpoint.expected_temporal_frame is not None:
        return checkpoint.expected_temporal_frame
    mode_by_answer_mode = {
        MemoryEvolutionAnswerTemporalMode.CURRENT: MemoryEvolutionTemporalKind.CURRENT,
        MemoryEvolutionAnswerTemporalMode.HISTORICAL: MemoryEvolutionTemporalKind.HISTORICAL,
        MemoryEvolutionAnswerTemporalMode.EXECUTION: MemoryEvolutionTemporalKind.EXECUTION,
        MemoryEvolutionAnswerTemporalMode.BELIEF: MemoryEvolutionTemporalKind.BELIEF,
    }
    return MemoryEvolutionTemporalFrame(
        temporal_kind=mode_by_answer_mode[contract.answer_temporal_mode],
        scope_kind=MemoryEvolutionScopeKind.NONE,
        scope_key=None,
        anchor_id=None,
        valid_from=None,
        valid_to=None,
        confidence=1.0,
        rationale="Derived from the authored checkpoint contract.",
    )


def temporal_frame_diagnostics(
    *,
    expected: MemoryEvolutionTemporalFrame,
    actual: MemoryEvolutionTemporalFrame,
    contract: MemoryEvolutionCheckpointContract,
    scenario: MemoryEvolutionScenario,
    checkpoint: MemoryEvolutionCheckpoint,
) -> dict[str, bool]:
    kind_mismatch = actual.temporal_kind != expected.temporal_kind
    scope_kind_mismatch, scope_key_mismatch = _temporal_scope_mismatches(
        expected=expected,
        actual=actual,
        contract=contract,
        scenario=scenario,
        checkpoint=checkpoint,
    )
    anchor_mismatch = expected.anchor_id is not None and actual.anchor_id != expected.anchor_id
    extra_anchor = (
        expected.anchor_id is None
        and actual.anchor_id is not None
        and not contract.allow_extra_temporal_anchor
    )
    expected_has_interval = expected.valid_from is not None or expected.valid_to is not None
    actual_has_interval = actual.valid_from is not None or actual.valid_to is not None
    interval_mismatch = (
        (expected.valid_from is not None and actual.valid_from != expected.valid_from)
        or (expected.valid_to is not None and actual.valid_to != expected.valid_to)
    )
    extra_interval = (
        actual_has_interval
        and not expected_has_interval
        and not _extra_interval_is_allowed(contract=contract)
    )
    under_specified = expected_has_interval and not actual_has_interval
    if contract.temporal_interval_policy == MemoryEvolutionTemporalIntervalPolicy.REQUIRE_START_AND_END:
        under_specified = expected.valid_from is not None and actual.valid_from is None
        under_specified = under_specified or (expected.valid_to is not None and actual.valid_to is None)
    temporal_frame_warning = (
        (actual_has_interval and not expected_has_interval and _extra_interval_is_allowed(contract=contract))
        or (
            expected.anchor_id is None
            and actual.anchor_id is not None
            and contract.allow_extra_temporal_anchor
        )
    )
    return {
        "temporal_kind_mismatch": kind_mismatch,
        "temporal_scope_mismatch": scope_kind_mismatch,
        "temporal_anchor_mismatch": anchor_mismatch,
        "temporal_interval_mismatch": interval_mismatch,
        "temporal_frame_under_specified": under_specified,
        "temporal_scope_key_mismatch": scope_key_mismatch,
        "temporal_extra_anchor": extra_anchor,
        "temporal_extra_interval": extra_interval,
        "temporal_frame_warning": temporal_frame_warning,
    }


def _extra_interval_is_allowed(*, contract: MemoryEvolutionCheckpointContract) -> bool:
    return contract.allow_extra_temporal_bounds or contract.temporal_interval_policy in {
        MemoryEvolutionTemporalIntervalPolicy.ALLOW_CHECKPOINT_BOUNDS,
        MemoryEvolutionTemporalIntervalPolicy.ALLOW_EXTRA_BOUNDS,
    }


def _temporal_scope_mismatches(
    *,
    expected: MemoryEvolutionTemporalFrame,
    actual: MemoryEvolutionTemporalFrame,
    contract: MemoryEvolutionCheckpointContract,
    scenario: MemoryEvolutionScenario,
    checkpoint: MemoryEvolutionCheckpoint,
) -> tuple[bool, bool]:
    if contract.scope_match_policy == MemoryEvolutionScopeMatchPolicy.KIND_ONLY:
        return actual.scope_kind != expected.scope_kind, False
    if contract.scope_match_policy == MemoryEvolutionScopeMatchPolicy.NONE_OR_GLOBAL:
        return actual.scope_kind not in {
            MemoryEvolutionScopeKind.NONE,
            MemoryEvolutionScopeKind.GLOBAL,
        }, False
    if contract.scope_match_policy == MemoryEvolutionScopeMatchPolicy.NONE_OR_ENTITY:
        scope_kind_mismatch = actual.scope_kind not in {
            MemoryEvolutionScopeKind.NONE,
            MemoryEvolutionScopeKind.ENTITY,
        }
        scope_key_mismatch = (
            actual.scope_kind == MemoryEvolutionScopeKind.ENTITY
            and expected.scope_key is not None
            and not _scope_keys_equivalent(
                expected_key=expected.scope_key,
                actual_key=actual.scope_key,
                kind=MemoryEvolutionScopeKind.ENTITY,
                scenario=scenario,
                checkpoint=checkpoint,
                contract=contract,
            )
        )
        return scope_kind_mismatch, scope_key_mismatch
    if contract.scope_match_policy == MemoryEvolutionScopeMatchPolicy.NONE_OR_TASK:
        scope_kind_mismatch = actual.scope_kind not in {
            MemoryEvolutionScopeKind.NONE,
            MemoryEvolutionScopeKind.TASK,
        }
        scope_key_mismatch = (
            actual.scope_kind == MemoryEvolutionScopeKind.TASK
            and expected.scope_key is not None
            and not _scope_keys_equivalent(
                expected_key=expected.scope_key,
                actual_key=actual.scope_key,
                kind=MemoryEvolutionScopeKind.TASK,
                scenario=scenario,
                checkpoint=checkpoint,
                contract=contract,
            )
        )
        return scope_kind_mismatch, scope_key_mismatch
    if contract.scope_match_policy == MemoryEvolutionScopeMatchPolicy.NONE_GLOBAL_OR_ENTITY:
        scope_kind_mismatch = actual.scope_kind not in {
            MemoryEvolutionScopeKind.NONE,
            MemoryEvolutionScopeKind.GLOBAL,
            MemoryEvolutionScopeKind.ENTITY,
        }
        scope_key_mismatch = (
            actual.scope_kind == MemoryEvolutionScopeKind.ENTITY
            and expected.scope_key is not None
            and not _scope_keys_equivalent(
                expected_key=expected.scope_key,
                actual_key=actual.scope_key,
                kind=MemoryEvolutionScopeKind.ENTITY,
                scenario=scenario,
                checkpoint=checkpoint,
                contract=contract,
            )
        )
        return scope_kind_mismatch, scope_key_mismatch
    return (
        actual.scope_kind != expected.scope_kind,
        expected.scope_key is not None
        and not _scope_keys_equivalent(
            expected_key=expected.scope_key,
            actual_key=actual.scope_key,
            kind=actual.scope_kind,
            scenario=scenario,
            checkpoint=checkpoint,
            contract=contract,
        ),
    )


def _scope_keys_equivalent(
    *,
    expected_key: str | None,
    actual_key: str | None,
    kind: MemoryEvolutionScopeKind,
    scenario: MemoryEvolutionScenario,
    checkpoint: MemoryEvolutionCheckpoint,
    contract: MemoryEvolutionCheckpointContract,
) -> bool:
    if contract.scope_key_policy == MemoryEvolutionScopeKeyPolicy.KIND_ONLY:
        return True
    if expected_key == actual_key:
        return True
    if actual_key is None:
        return contract.scope_key_policy == MemoryEvolutionScopeKeyPolicy.NONE_ALLOWED
    if contract.scope_key_policy != MemoryEvolutionScopeKeyPolicy.CANONICAL_ALIAS:
        return False
    expected_canonical = _canonical_scope_key(
        raw_key=expected_key,
        kind=kind,
        scenario=scenario,
        checkpoint=checkpoint,
    )
    actual_canonical = _canonical_scope_key(
        raw_key=actual_key,
        kind=kind,
        scenario=scenario,
        checkpoint=checkpoint,
    )
    return expected_canonical is not None and expected_canonical == actual_canonical


def _canonical_scope_key(
    *,
    raw_key: str | None,
    kind: MemoryEvolutionScopeKind,
    scenario: MemoryEvolutionScenario,
    checkpoint: MemoryEvolutionCheckpoint,
) -> str | None:
    if raw_key is None:
        return None
    normalized = _normalize_scope_key(raw_key)
    aliases = _scope_aliases_by_canonical_key(
        kind=kind,
        scenario=scenario,
        checkpoint=checkpoint,
    )
    for canonical, values in aliases.items():
        if normalized in values:
            return canonical
    return normalized


def _scope_aliases_by_canonical_key(
    *,
    kind: MemoryEvolutionScopeKind,
    scenario: MemoryEvolutionScenario,
    checkpoint: MemoryEvolutionCheckpoint,
) -> dict[str, set[str]]:
    aliases: dict[str, set[str]] = {}
    relevant_ids = {
        *checkpoint.expected_retrieval_ids,
        *checkpoint.expected_citation_ids,
        *checkpoint.expected_context_citation_ids,
        *checkpoint.expected_excluded_memory_ids,
        *checkpoint.expected_checkpoint_active_record_ids,
        *checkpoint.expected_checkpoint_superseded_record_ids,
        *checkpoint.expected_checkpoint_retained_record_ids,
        *checkpoint.expected_belief_ranking,
        *checkpoint.expected_belief_scores.keys(),
    }
    for event in scenario.events:
        if relevant_ids and event.event_id not in relevant_ids:
            continue
        if kind == MemoryEvolutionScopeKind.TASK and event.task_id:
            canonical = _normalize_scope_key(event.task_id)
            aliases.setdefault(canonical, set()).update(
                _scope_key_aliases(event.task_id)
            )
        if kind == MemoryEvolutionScopeKind.ENTITY:
            for entity_id in event.entity_ids:
                canonical = _normalize_scope_key(entity_id)
                aliases.setdefault(canonical, set()).update(
                    _scope_key_aliases(entity_id)
                )
    return aliases


def _scope_key_aliases(value: str) -> set[str]:
    normalized = _normalize_scope_key(value)
    aliases = {normalized}
    if ":" in normalized:
        aliases.add(normalized.split(":", 1)[1])
    aliases.add(normalized.replace("-", " "))
    aliases.add(normalized.replace("_", " "))
    return aliases


def _normalize_scope_key(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower()).replace("_", "-")


def record_lifecycle_content_state_conflation_ids(
    *,
    scenario: MemoryEvolutionScenario,
    missing_checkpoint_active_ids: list[str],
    checkpoint_superseded: set[str],
    checkpoint_retained: set[str],
) -> list[str]:
    misplaced = set(missing_checkpoint_active_ids) & (checkpoint_superseded | checkpoint_retained)
    if not misplaced:
        return []
    event_by_id = {event.event_id: event for event in scenario.events}
    return [
        memory_id
        for memory_id in missing_checkpoint_active_ids
        if memory_id in misplaced and _content_uses_domain_lifecycle_word(event_by_id.get(memory_id))
    ]


def _content_uses_domain_lifecycle_word(event: MemoryEvolutionEvent | None) -> bool:
    if event is None:
        return False
    lifecycle_like_terms = {
        "abandoned",
        "archived",
        "closed",
        "deprecated",
        "done",
        "expired",
        "inactive",
        "retired",
    }
    return bool(set(normalize_decision_text(event.content).split()) & lifecycle_like_terms)
