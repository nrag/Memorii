"""Visible benchmark context and evidence-effect projection."""

from __future__ import annotations

import re
from datetime import datetime
from typing import TypedDict

from memorii.core.benchmark.memory_evolution_decision.contracts import (
    MemoryEvolutionCheckpoint,
    MemoryEvolutionEntityResolutionCard,
    MemoryEvolutionEntityStateClaimCard,
    MemoryEvolutionEvent,
    MemoryEvolutionEventRole,
    MemoryEvolutionEvidenceEffectCard,
    MemoryEvolutionMemoryKind,
    MemoryEvolutionRecordLifecycleState,
    MemoryEvolutionScenario,
    MemoryEvolutionSourceType,
    MemoryEvolutionTemporalAnchorCard,
    MemoryEvolutionVisibleMemoryCard,
)
from memorii.core.benchmark.memory_evolution_decision.utils import dedupe_string_ids, normalize_decision_text


class _TemporalAnchorAccumulator(TypedDict):
    aliases: list[str]
    valid_from: datetime | None
    valid_to: datetime | None
    source_memory_ids: list[str]


def visible_events_for_checkpoint(
    *,
    scenario: MemoryEvolutionScenario,
    checkpoint: MemoryEvolutionCheckpoint,
) -> list[MemoryEvolutionEvent]:
    return [event for event in scenario.events if event.timestamp <= checkpoint.timestamp]


def visible_memory_cards_for_events(events: list[MemoryEvolutionEvent]) -> list[MemoryEvolutionVisibleMemoryCard]:
    return [
        MemoryEvolutionVisibleMemoryCard(
            memory_id=event.event_id,
            memory_kind=_memory_kind_for_event(event),
            statement=event.content,
            timestamp=event.timestamp,
            source_type=event.source_type,
            trust_level=event.trust_level,
            entity_ids=list(event.entity_ids),
            task_id=event.task_id,
            scope=event.scope,
            event_role=event.event_role,
            language=event.language,
            script=event.script,
        )
        for event in events
    ]


def entity_resolution_cards_for_events(events: list[MemoryEvolutionEvent]) -> list[MemoryEvolutionEntityResolutionCard]:
    evidence_by_entity: dict[str, list[str]] = {}
    for event in events:
        for entity_id in event.entity_ids:
            evidence_by_entity.setdefault(entity_id, []).append(event.event_id)
    return [
        MemoryEvolutionEntityResolutionCard(
            entity_id=entity_id,
            canonical_name=_canonical_name_from_id(entity_id),
            evidence_memory_ids=dedupe_string_ids(evidence_ids),
        )
        for entity_id, evidence_ids in sorted(evidence_by_entity.items())
    ]


def temporal_anchor_cards_for_events(events: list[MemoryEvolutionEvent]) -> list[MemoryEvolutionTemporalAnchorCard]:
    anchors: dict[str, _TemporalAnchorAccumulator] = {}
    for event in events:
        for anchor_id in event.temporal_anchor_ids:
            anchor = anchors.setdefault(
                anchor_id,
                {
                    "aliases": [],
                    "valid_from": event.valid_from,
                    "valid_to": event.valid_to,
                    "source_memory_ids": [],
                },
            )
            anchor["aliases"].extend(event.temporal_anchor_aliases)
            anchor["source_memory_ids"].append(event.event_id)
            if event.valid_from is not None:
                current = anchor["valid_from"]
                anchor["valid_from"] = event.valid_from if current is None else min(current, event.valid_from)
            if event.valid_to is not None:
                current = anchor["valid_to"]
                anchor["valid_to"] = event.valid_to if current is None else max(current, event.valid_to)
    return [
        MemoryEvolutionTemporalAnchorCard(
            anchor_id=anchor_id,
            aliases=dedupe_string_ids(values["aliases"]),
            valid_from=values["valid_from"],
            valid_to=values["valid_to"],
            source_memory_ids=dedupe_string_ids(values["source_memory_ids"]),
        )
        for anchor_id, values in sorted(anchors.items())
    ]


def entity_state_cards_for_events(
    *,
    events: list[MemoryEvolutionEvent],
    checkpoint: MemoryEvolutionCheckpoint,
) -> list[MemoryEvolutionEntityStateClaimCard]:
    state_events = [
        event
        for event in events
        if event.subject_entity_id is not None and event.predicate is not None and event.object_value is not None
    ]
    return [
        MemoryEvolutionEntityStateClaimCard(
            memory_id=event.event_id,
            entity_id=event.subject_entity_id or "",
            predicate=event.predicate or "",
            value=event.object_value or "",
            valid_from=event.valid_from,
            valid_to=event.valid_to,
            observed_at=event.timestamp,
            temporal_anchor_ids=list(event.temporal_anchor_ids),
            record_lifecycle=_record_lifecycle_for_event(event=event, checkpoint=checkpoint, state_events=state_events),
            source_memory_ids=[event.event_id],
        )
        for event in state_events
    ]


def _record_lifecycle_for_event(
    *,
    event: MemoryEvolutionEvent,
    checkpoint: MemoryEvolutionCheckpoint,
    state_events: list[MemoryEvolutionEvent],
) -> MemoryEvolutionRecordLifecycleState:
    if event.event_role == MemoryEvolutionEventRole.ARCHIVED_STATE:
        return MemoryEvolutionRecordLifecycleState.CHECKPOINT_RETAINED
    if event.valid_to is not None and event.valid_to <= checkpoint.timestamp:
        return MemoryEvolutionRecordLifecycleState.CHECKPOINT_SUPERSEDED
    newer_same_slot = [
        candidate
        for candidate in state_events
        if candidate.event_id != event.event_id
        and candidate.subject_entity_id == event.subject_entity_id
        and candidate.predicate == event.predicate
        and candidate.timestamp <= checkpoint.timestamp
        and candidate.timestamp > event.timestamp
    ]
    if newer_same_slot:
        return MemoryEvolutionRecordLifecycleState.CHECKPOINT_SUPERSEDED
    return MemoryEvolutionRecordLifecycleState.CHECKPOINT_ACTIVE


def _canonical_name_from_id(entity_id: str) -> str:
    return entity_id.replace("-", " ").replace("_", " ").strip().title()


def _memory_kind_for_event(event: MemoryEvolutionEvent) -> MemoryEvolutionMemoryKind:
    if event.event_id.startswith("belief:"):
        return MemoryEvolutionMemoryKind.BELIEF
    if event.event_id.startswith("evidence:"):
        return MemoryEvolutionMemoryKind.EVIDENCE
    if event.event_id.startswith("exec:"):
        return MemoryEvolutionMemoryKind.ACTION
    if event.event_id.startswith("mem:"):
        return MemoryEvolutionMemoryKind.FACT
    return MemoryEvolutionMemoryKind.UNKNOWN


def evidence_effect_cards_for_events(events: list[MemoryEvolutionEvent]) -> list[MemoryEvolutionEvidenceEffectCard]:
    label_to_memory_id = _belief_label_map(events)
    cards: list[MemoryEvolutionEvidenceEffectCard] = []
    for event in events:
        supports = _effect_ids_for_verbs(
            event.content,
            label_to_memory_id,
            ["supports", "support", "confirms", "backs", "strengthens"],
        )
        supports.extend(
            _effect_ids_for_label_predicates(
                event.content,
                label_to_memory_id,
                ["supported", "confirmed", "backed", "strengthened"],
            )
        )
        weakens = _effect_ids_for_verbs(
            event.content,
            label_to_memory_id,
            ["weakens", "weaken", "downgrades", "degrades", "undermines", "leaves", "makes", "renders"],
        )
        weakens.extend(
            _effect_ids_for_label_predicates(
                event.content,
                label_to_memory_id,
                ["weakened", "downgraded", "degraded", "less likely", "weaker", "unsupported"],
            )
        )
        falsifies = _effect_ids_for_verbs(
            event.content,
            label_to_memory_id,
            ["falsifies", "falsify", "refutes", "disproves", "invalidates"],
        )
        falsifies.extend(
            _effect_ids_for_label_predicates(
                event.content,
                label_to_memory_id,
                ["falsified", "refuted", "disproved", "invalidated", "ruled out"],
            )
        )
        dependencies = _dependency_ids_for_text(event.content, label_to_memory_id)
        supports = dedupe_string_ids(supports)
        weakens = dedupe_string_ids(weakens)
        falsifies = dedupe_string_ids(falsifies)
        if not (supports or weakens or falsifies or dependencies):
            continue
        cards.append(
            MemoryEvolutionEvidenceEffectCard(
                evidence_memory_id=event.event_id,
                supports_memory_ids=supports,
                weakens_memory_ids=weakens,
                falsifies_memory_ids=falsifies,
                dependency_memory_ids=dependencies,
            )
        )
    return cards


def _belief_label_map(events: list[MemoryEvolutionEvent]) -> dict[str, str]:
    label_to_memory_id: dict[str, str] = {}
    for event in events:
        if not event.event_id.startswith("belief:"):
            continue
        for match in re.finditer(r"\b(?:hypothesis|belief)\s+([a-z])\b", event.content, flags=re.IGNORECASE):
            label_to_memory_id.setdefault(match.group(1).upper(), event.event_id)
        event_id_match = re.match(r"belief:([a-z])-", event.event_id, flags=re.IGNORECASE)
        if event_id_match is not None:
            label_to_memory_id.setdefault(event_id_match.group(1).upper(), event.event_id)
    return label_to_memory_id


def _effect_ids_for_verbs(content: str, label_to_memory_id: dict[str, str], verbs: list[str]) -> list[str]:
    ids: list[str] = []
    for verb in verbs:
        for match in re.finditer(rf"\b{re.escape(verb)}\s+([a-z])\b", content, flags=re.IGNORECASE):
            memory_id = label_to_memory_id.get(match.group(1).upper())
            if memory_id is not None:
                ids.append(memory_id)
    return dedupe_string_ids(ids)


def _effect_ids_for_label_predicates(
    content: str,
    label_to_memory_id: dict[str, str],
    predicates: list[str],
) -> list[str]:
    ids: list[str] = []
    predicate_pattern = "|".join(re.escape(predicate) for predicate in predicates)
    for match in re.finditer(
        rf"\b([a-z])\b\s+(?:is|was|looks|seems|becomes|became)?\s*(?:now\s+)?(?:more\s+)?(?:{predicate_pattern})\b",
        content,
        flags=re.IGNORECASE,
    ):
        memory_id = label_to_memory_id.get(match.group(1).upper())
        if memory_id is not None:
            ids.append(memory_id)
    return dedupe_string_ids(ids)


def _dependency_ids_for_text(content: str, label_to_memory_id: dict[str, str]) -> list[str]:
    ids: list[str] = []
    for match in re.finditer(r"\bdepends\s+on\s+([a-z])\b", content, flags=re.IGNORECASE):
        memory_id = label_to_memory_id.get(match.group(1).upper())
        if memory_id is not None:
            ids.append(memory_id)
    return dedupe_string_ids(ids)


def belief_effect_order_errors(
    *,
    scenario: MemoryEvolutionScenario,
    checkpoint: MemoryEvolutionCheckpoint,
    ranking: list[str],
) -> list[str]:
    if not checkpoint.expected_belief_ranking:
        return []
    visible_events = visible_events_for_checkpoint(scenario=scenario, checkpoint=checkpoint)
    effect_cards = evidence_effect_cards_for_events(visible_events)
    supported: set[str] = set()
    weakened: set[str] = set()
    falsified: set[str] = set()
    for card in effect_cards:
        supported.update(card.supports_memory_ids)
        weakened.update(card.weakens_memory_ids)
        falsified.update(card.falsifies_memory_ids)
    candidates = list(checkpoint.expected_belief_ranking)
    ranked_candidates = [memory_id for memory_id in ranking if memory_id in set(candidates)]
    rank_by_id = {memory_id: index for index, memory_id in enumerate(ranked_candidates)}
    neutral = [memory_id for memory_id in candidates if memory_id not in supported | weakened | falsified]
    errors: list[str] = []
    for weakened_id in sorted(weakened & set(candidates)):
        if weakened_id not in rank_by_id:
            continue
        for neutral_id in neutral:
            if neutral_id not in rank_by_id:
                continue
            if rank_by_id[weakened_id] < rank_by_id[neutral_id]:
                errors.append(f"{weakened_id}>{neutral_id}")
    return errors


def belief_score_order_errors(*, ranking: list[str], score_by_id: dict[str, float]) -> list[str]:
    errors: list[str] = []
    for earlier_index, earlier_id in enumerate(ranking):
        earlier_score = score_by_id.get(earlier_id)
        if earlier_score is None:
            continue
        for later_id in ranking[earlier_index + 1 :]:
            later_score = score_by_id.get(later_id)
            if later_score is None:
                continue
            if earlier_score < later_score:
                errors.append(f"{later_id}>{earlier_id}")
    return errors


def belief_ids_from_order_errors(errors: list[str]) -> list[str]:
    ids: list[str] = []
    for error in errors:
        ids.extend(part for part in error.split(">") if part)
    return dedupe_string_ids(ids)


def source_trust_losers_marked_active(
    *,
    scenario: MemoryEvolutionScenario,
    checkpoint: MemoryEvolutionCheckpoint,
    checkpoint_active: set[str],
    selected: set[str],
) -> list[str]:
    excluded_superseded = (
        set(checkpoint.expected_excluded_memory_ids)
        & set(checkpoint.expected_checkpoint_superseded_record_ids)
        & checkpoint_active
    )
    if not excluded_superseded:
        return []
    event_by_id = {event.event_id: event for event in scenario.events}
    selected_trust = [
        event_by_id[memory_id].trust_level
        for memory_id in selected
        if memory_id in event_by_id
    ]
    if not selected_trust:
        return []
    winning_trust = max(selected_trust)
    return [
        memory_id
        for memory_id in sorted(excluded_superseded)
        if (event := event_by_id.get(memory_id)) is not None
        and event.trust_level < winning_trust
    ]


def command_context_ids(*, scenario: MemoryEvolutionScenario, checkpoint: MemoryEvolutionCheckpoint) -> list[str]:
    return [
        event.event_id
        for event in scenario.events
        if event.timestamp <= checkpoint.timestamp
        and event.source_type == MemoryEvolutionSourceType.USER
        and event.event_role == MemoryEvolutionEventRole.COMMAND_CONTEXT
    ]


def rank_events_by_shallow_overlap(
    *,
    scenario: MemoryEvolutionScenario,
    checkpoint: MemoryEvolutionCheckpoint,
) -> list[MemoryEvolutionEvent]:
    query_tokens = set(normalize_decision_text(checkpoint.query_or_task).split())
    eligible = [event for event in scenario.events if event.timestamp <= checkpoint.timestamp]
    return sorted(
        eligible,
        key=lambda event: (
            -len(query_tokens & set(normalize_decision_text(event.content).split())),
            -event.timestamp.timestamp(),
            event.event_id,
        ),
    )
