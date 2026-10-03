"""Content-free tombstone versions for revoked evolution-plane records.

Logical forgetting rewrites each affected derived record as a new version
(revision, not deletion): the tombstone keeps identity coordinates and
lifecycle state only. The prior bytes remain in the record's version
history and in the append-only semantic event batches; serving exclusion
comes from the revoked lifecycle plus the reader gates, never from
deleting history.
"""

from __future__ import annotations

from datetime import UTC, datetime

from memorii.core.memory_evolution.models import (
    ClaimLifecycleState,
    ClaimState,
    EntityLinkLifecycleState,
    EntityLinkState,
)
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.domain.enums import TemporalValidityStatus

_REVOKED_MARKER_PREFIX = "revoked"


def _marker(suppression_id: str) -> str:
    """A deterministic, content-free replacement for any servable text."""

    return f"{_REVOKED_MARKER_PREFIX}:{suppression_id}"


def revoked_claim_state(
    state: ClaimState, *, suppression_id: str, applied_at: datetime
) -> ClaimState:
    """Return the tombstone version of one claim state.

    Identity coordinates (claim id, key, link ids, derivation ids) survive
    so audit and closure reasoning stay coherent; every servable payload
    field is replaced by content-free markers.
    """

    return ClaimState(
        claim_id=state.claim_id,
        claim_key=state.claim_key,
        object_value=_marker(suppression_id),
        lifecycle_state=ClaimLifecycleState.REVOKED,
        source_claim_id=state.source_claim_id,
        confidence=state.confidence,
        source_modality=state.source_modality,
        semantic_context=state.semantic_context,
        validation_results=[],
        evidence_spans=[],
        supersedes_claim_ids=state.supersedes_claim_ids,
        superseded_by_claim_id=state.superseded_by_claim_id,
        conflict_with_claim_ids=state.conflict_with_claim_ids,
        confidence_history=state.confidence_history,
        subject_link_id=state.subject_link_id,
        object_link_id=state.object_link_id,
        valid_from=state.valid_from,
        valid_to=state.valid_to,
        created_at=state.created_at,
        updated_at=applied_at,
    )


def revoked_entity_link(
    link: EntityLinkState, *, suppression_id: str, applied_at: datetime
) -> EntityLinkState:
    """Return the tombstone version of one entity link.

    The link's names and aliases are the servable surface; the tombstone
    keeps only the opaque identifiers and the revoked lifecycle.
    """

    return EntityLinkState(
        link_id=link.link_id,
        mention_text=_marker(suppression_id),
        canonical_entity_id=link.canonical_entity_id,
        normalized_name=_marker(suppression_id),
        entity_type=link.entity_type,
        aliases=[],
        observed_names=[],
        evidence_spans=[],
        confidence=link.confidence,
        scope=link.scope,
        lifecycle_state=EntityLinkLifecycleState.REVOKED,
        superseded_by_entity_id=link.superseded_by_entity_id,
        lineage_parent_entity_id=link.lineage_parent_entity_id,
        valid_from=link.valid_from,
        valid_to=link.valid_to,
        created_at=link.created_at,
        updated_at=applied_at,
    )


def _tombstone_record(
    record: CanonicalMemoryRecord,
    *,
    payload_key: str,
    tombstone_payload: dict[str, object],
    suppression_id: str,
    applied_at: datetime,
) -> CanonicalMemoryRecord:
    return record.model_copy(
        update={
            "text": _marker(suppression_id),
            "validity_status": TemporalValidityStatus.INVALIDATED,
            "timestamp": applied_at,
            "content": {
                "memory_evolution_kind": record.content["memory_evolution_kind"],
                payload_key: tombstone_payload,
            },
        }
    )


def claim_state_tombstone_record(
    record: CanonicalMemoryRecord, *, suppression_id: str, applied_at: datetime
) -> CanonicalMemoryRecord:
    """Rewrite one persisted claim_state record as its tombstone version."""

    state = ClaimState.model_validate(record.content["claim_state"])
    tombstone = revoked_claim_state(
        state, suppression_id=suppression_id, applied_at=applied_at
    )
    return _tombstone_record(
        record,
        payload_key="claim_state",
        tombstone_payload=tombstone.model_dump(mode="python"),
        suppression_id=suppression_id,
        applied_at=applied_at,
    )


def entity_link_tombstone_record(
    record: CanonicalMemoryRecord, *, suppression_id: str, applied_at: datetime
) -> CanonicalMemoryRecord:
    """Rewrite one persisted entity_link record as its tombstone version."""

    link = EntityLinkState.model_validate(record.content["entity_link"])
    tombstone = revoked_entity_link(
        link, suppression_id=suppression_id, applied_at=applied_at
    )
    return _tombstone_record(
        record,
        payload_key="entity_link",
        tombstone_payload=tombstone.model_dump(mode="python"),
        suppression_id=suppression_id,
        applied_at=applied_at,
    )


def tombstone_records_for(
    records: tuple[CanonicalMemoryRecord, ...],
    *,
    suppression_id: str,
    applied_at: datetime | None = None,
) -> tuple[CanonicalMemoryRecord, ...]:
    """Return tombstone versions for every revocable evolution record given.

    Records of other kinds pass through untouched; the caller (the
    governance enforcement publication) owns preconditions and the CAS.
    """

    moment = applied_at or datetime.now(UTC)
    rewritten: list[CanonicalMemoryRecord] = []
    for record in records:
        kind = record.content.get("memory_evolution_kind")
        if kind == "claim_state":
            rewritten.append(
                claim_state_tombstone_record(
                    record, suppression_id=suppression_id, applied_at=moment
                )
            )
        elif kind == "entity_link":
            rewritten.append(
                entity_link_tombstone_record(
                    record, suppression_id=suppression_id, applied_at=moment
                )
            )
        else:
            rewritten.append(record)
    return tuple(rewritten)


__all__ = [
    "claim_state_tombstone_record",
    "entity_link_tombstone_record",
    "revoked_claim_state",
    "revoked_entity_link",
    "tombstone_records_for",
]
