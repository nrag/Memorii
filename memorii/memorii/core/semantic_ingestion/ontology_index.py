"""Derived ontology index projection over canonical catalog records.

The learned-ontology owner (LearnedRelationRuntime) stores its proposals,
immutable catalog versions, selection pointers, activation attempts and
replay operations as internal-control records in the memory plane. This
module materializes those records into typed index rows for the shared
partition. Rows carry the canonical record identity and digest of their
source — rebuildable derived state, never independent facts, and catalog
selection never becomes a grant: the pointer rows are selection witnesses
only.
"""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.store import record_digest

KIND_PROPOSAL = "learned_ontology_change_proposal_v1"
KIND_VERSION = "learned_ontology_catalog_version_v1"
KIND_POINTER = "learned_ontology_catalog_pointer_v1"
KIND_ATTEMPT = "learned_ontology_activation_attempt_v1"
KIND_REPLAY = "learned_ontology_replay_operation_v1"

_ONTOLOGY_KINDS = frozenset(
    {KIND_PROPOSAL, KIND_VERSION, KIND_POINTER, KIND_ATTEMPT, KIND_REPLAY}
)


class OntologyCandidateIndexRow(BaseModel):
    proposal_id: str = Field(min_length=1)
    lifecycle: str
    record_id: str = Field(min_length=1)
    record_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)


class OntologyVersionIndexRow(BaseModel):
    version_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    record_id: str = Field(min_length=1)
    record_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)


class OntologySelectionIndexRow(BaseModel):
    scope_key: str = Field(min_length=1)
    selected_version_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    selected_attempt_id: str = Field(min_length=1)
    activation_sequence: int = Field(ge=1)
    record_id: str = Field(min_length=1)
    record_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)


class OntologyAttemptIndexRow(BaseModel):
    attempt_id: str = Field(min_length=1)
    status: str
    record_id: str = Field(min_length=1)
    record_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)


class OntologyReplayReceiptIndexRow(BaseModel):
    operation_id: str = Field(min_length=1)
    record_id: str = Field(min_length=1)
    record_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)


class OntologyIndexProjection(BaseModel):
    """One full derived ontology index generation."""

    candidates: tuple[OntologyCandidateIndexRow, ...] = ()
    versions: tuple[OntologyVersionIndexRow, ...] = ()
    selections: tuple[OntologySelectionIndexRow, ...] = ()
    attempts: tuple[OntologyAttemptIndexRow, ...] = ()
    replay_receipts: tuple[OntologyReplayReceiptIndexRow, ...] = ()

    model_config = ConfigDict(extra="forbid", frozen=True)


def project_ontology_index(
    records: Iterable[CanonicalMemoryRecord],
) -> OntologyIndexProjection:
    """Project canonical ontology records into derived index rows."""
    candidates: list[OntologyCandidateIndexRow] = []
    versions: list[OntologyVersionIndexRow] = []
    selections: list[OntologySelectionIndexRow] = []
    attempts: list[OntologyAttemptIndexRow] = []
    replay_receipts: list[OntologyReplayReceiptIndexRow] = []
    for record in records:
        kind = record.source_kind
        if kind not in _ONTOLOGY_KINDS:
            continue
        digest = record_digest(record)
        if kind == KIND_PROPOSAL:
            candidates.append(
                OntologyCandidateIndexRow(
                    proposal_id=record.memory_id,
                    lifecycle=record.text,
                    record_id=record.memory_id,
                    record_digest=digest,
                )
            )
        elif kind == KIND_VERSION:
            versions.append(
                OntologyVersionIndexRow(
                    version_digest=_version_digest_from_memory_id(record.memory_id),
                    record_id=record.memory_id,
                    record_digest=digest,
                )
            )
        elif kind == KIND_POINTER:
            pointer = record.content["pointer"]
            selections.append(
                OntologySelectionIndexRow(
                    scope_key=_scope_key_from_memory_id(record.memory_id),
                    selected_version_digest=pointer["selected_version_digest"],
                    selected_attempt_id=pointer["selected_attempt_id"],
                    activation_sequence=pointer["activation_sequence"],
                    record_id=record.memory_id,
                    record_digest=digest,
                )
            )
        elif kind == KIND_ATTEMPT:
            attempts.append(
                OntologyAttemptIndexRow(
                    attempt_id=record.memory_id,
                    status=record.text,
                    record_id=record.memory_id,
                    record_digest=digest,
                )
            )
        else:
            replay_receipts.append(
                OntologyReplayReceiptIndexRow(
                    operation_id=record.memory_id,
                    record_id=record.memory_id,
                    record_digest=digest,
                )
            )
    return OntologyIndexProjection(
        candidates=tuple(sorted(candidates, key=lambda row: row.proposal_id)),
        versions=tuple(sorted(versions, key=lambda row: row.version_digest)),
        selections=tuple(sorted(selections, key=lambda row: row.scope_key)),
        attempts=tuple(sorted(attempts, key=lambda row: row.attempt_id)),
        replay_receipts=tuple(
            sorted(replay_receipts, key=lambda row: row.operation_id)
        ),
    )


def _version_digest_from_memory_id(memory_id: str) -> str:
    prefix = "learned-catalog-version:"
    if not memory_id.startswith(prefix):
        raise ValueError("ontology version record id is not canonical")
    return memory_id[len(prefix) :]


def _scope_key_from_memory_id(memory_id: str) -> str:
    prefix = "learned-catalog-pointer:"
    if not memory_id.startswith(prefix):
        raise ValueError("ontology pointer record id is not canonical")
    return memory_id[len(prefix) :]


__all__ = [
    "KIND_ATTEMPT",
    "KIND_POINTER",
    "KIND_PROPOSAL",
    "KIND_REPLAY",
    "KIND_VERSION",
    "OntologyAttemptIndexRow",
    "OntologyCandidateIndexRow",
    "OntologyIndexProjection",
    "OntologyReplayReceiptIndexRow",
    "OntologySelectionIndexRow",
    "OntologyVersionIndexRow",
    "project_ontology_index",
]
