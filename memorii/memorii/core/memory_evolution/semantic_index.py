"""Derived semantic index projection over the canonical graph snapshot.

The typed graph (entity revisions, claim assertions) is projected by the
atomic store's replay authority; this module materializes that projection
into typed index rows for the shared partition. Rows carry the canonical
record identity and digest of their source — they are rebuildable derived
state, never independent facts, and a governed claim never collapses into a
plain subject/predicate/object edge: claim rows keep their assertion
identity, entity-revision references, predicate rule and validity interval.
"""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.memory_evolution.graph_records import (
    EntityRevision,
    GraphStateSnapshot,
    SnapshotGraphRecord,
)
from memorii.core.semantic_ingestion.contracts import ClaimAssertion


class SemanticEntityIndexRow(BaseModel):
    logical_entity_id: str = Field(min_length=1)
    entity_revision_id: str = Field(min_length=1)
    lifecycle: str
    record_id: str = Field(min_length=1)
    record_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    codec_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)


class SemanticClaimIndexRow(BaseModel):
    claim_assertion_id: str = Field(min_length=1)
    subject_entity_id: str = Field(min_length=1)
    object_entity_id: str | None = None
    predicate_id: str | None = None
    record_id: str = Field(min_length=1)
    record_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    valid_from: str | None = None
    valid_to: str | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class SemanticEvidenceLinkIndexRow(BaseModel):
    claim_assertion_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)


class SemanticIndexProjection(BaseModel):
    """One full derived-index generation bound to its snapshot authority."""

    graph_revision: str = Field(min_length=1)
    snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    entities: tuple[SemanticEntityIndexRow, ...] = ()
    claims: tuple[SemanticClaimIndexRow, ...] = ()
    evidence_links: tuple[SemanticEvidenceLinkIndexRow, ...] = ()

    model_config = ConfigDict(extra="forbid", frozen=True)


def project_semantic_index(snapshot: GraphStateSnapshot) -> SemanticIndexProjection:
    """Project the public graph snapshot into derived index rows."""
    entities: list[SemanticEntityIndexRow] = []
    claims: list[SemanticClaimIndexRow] = []
    evidence_links: list[SemanticEvidenceLinkIndexRow] = []
    for record in snapshot.records:
        payload = record.payload
        if isinstance(payload, EntityRevision):
            entities.append(
                SemanticEntityIndexRow(
                    logical_entity_id=payload.logical_entity_id,
                    entity_revision_id=payload.entity_revision_id,
                    lifecycle=payload.lifecycle,
                    record_id=record.record_id,
                    record_digest=record.record_digest,
                    codec_fingerprint=record.codec_fingerprint,
                )
            )
        elif isinstance(payload, ClaimAssertion):
            claims.append(_claim_row(record, payload))
            evidence_links.extend(_evidence_rows(payload))
    return SemanticIndexProjection(
        graph_revision=snapshot.graph_revision,
        snapshot_digest=snapshot.snapshot_digest,
        entities=tuple(sorted(entities, key=lambda row: row.record_id)),
        claims=tuple(sorted(claims, key=lambda row: row.record_id)),
        evidence_links=tuple(
            sorted(
                evidence_links,
                key=lambda row: (row.claim_assertion_id, row.source_id),
            )
        ),
    )


def _claim_row(record: SnapshotGraphRecord, claim: ClaimAssertion) -> SemanticClaimIndexRow:
    identity = claim.claim_identity
    predicate_id: str | None = None
    if identity is not None:
        predicate_id = identity.predicate_state_rule.predicate_id
    valid_from: str | None = None
    valid_to: str | None = None
    if claim.valid_interval is not None:
        valid_from = claim.valid_interval.start.isoformat()
        valid_to = (
            claim.valid_interval.end.isoformat()
            if claim.valid_interval.end is not None
            else None
        )
    return SemanticClaimIndexRow(
        claim_assertion_id=claim.claim_assertion_id,
        subject_entity_id=(
            identity.subject_assertion_ref.logical_entity_id_at_assertion
            if identity is not None
            else ""
        ),
        object_entity_id=(
            identity.object_assertion_ref.logical_entity_id_at_assertion
            if identity is not None and identity.object_assertion_ref is not None
            else None
        ),
        predicate_id=predicate_id,
        record_id=record.record_id,
        record_digest=record.record_digest,
        valid_from=valid_from,
        valid_to=valid_to,
    )


def _evidence_rows(claim: ClaimAssertion) -> Iterable[SemanticEvidenceLinkIndexRow]:
    evidence = claim.source_authority_evidence
    if claim.claim_identity is None or evidence is None:
        return ()
    return (
        SemanticEvidenceLinkIndexRow(
            claim_assertion_id=claim.claim_assertion_id,
            source_id=evidence.source_id,
            source_digest=evidence.source_digest,
            evidence_digest=evidence.evidence_digest,
        ),
    )


__all__ = [
    "SemanticClaimIndexRow",
    "SemanticEntityIndexRow",
    "SemanticEvidenceLinkIndexRow",
    "SemanticIndexProjection",
    "project_semantic_index",
]
