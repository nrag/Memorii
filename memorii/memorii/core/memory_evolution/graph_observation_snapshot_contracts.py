"""Closed profile-3 graph-observation cohort and cursor body contracts.

Historical v1 cursor wire models remain in ``graph_observation_contracts``.
This module deliberately provides no signing, self-digest, token, or paging
behavior; the protected profile-3 decoder owns those operations.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_evolution.graph_observation_records import Digest, Identifier

GraphObservationRecordKindV3 = Literal[
    "entity_revision", "alias_revision", "type_evidence", "claim_assertion",
    "temporal_claim_projection", "trust_claim_projection", "relation", "action_revision",
    "citation", "provenance", "temporal_transition", "identity_transition",
    "reference_disposition", "source_introduction", "operation_introduction",
    "operation_terminal_outcome", "source_terminal_outcome",
]
GraphObservationView = Literal["current", "historical", "lineage"]


def _utc(value: datetime, *, label: str) -> datetime:
    offset = value.utcoffset()
    if value.tzinfo is None or offset is None or offset.total_seconds() != 0:
        raise ValueError(f"{label} must be timezone-aware UTC")
    return value.astimezone(UTC)


class _ClosedSnapshotContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="before")
    @classmethod
    def _reject_boolean_schema_version(cls, value: object) -> object:
        if (
            "schema_version" in cls.model_fields
            and isinstance(value, Mapping)
            and isinstance(value.get("schema_version"), bool)
        ):
            raise ValueError("schema version must be an integer literal")
        return value


class GraphObservationRecordKey(_ClosedSnapshotContract):
    record_kind: GraphObservationRecordKindV3
    primary_key: Identifier


class _GraphObservationCohortBody(_ClosedSnapshotContract):
    seed_source_ids: tuple[Identifier, ...]
    seed_operation_ids: tuple[Identifier, ...]
    source_ids: tuple[Identifier, ...]
    operation_ids: tuple[Identifier, ...]
    operation_fence_ids: tuple[Identifier, ...]
    include_referenced_boundary_entities: Literal[True]
    authorized_scope_identity: Identifier
    authorization_policy_revision: Identifier
    authorization_decision_digest: Digest
    graph_revision_delta_ids: tuple[Identifier, ...]
    graph_revision_delta_digests: tuple[Digest, ...]
    ingestion_observation_delta_ids: tuple[Identifier, ...]
    ingestion_observation_delta_digests: tuple[Digest, ...]
    reference_schema_manifest_fingerprint: Digest
    reference_ledger_high_watermark: Identifier
    reference_ledger_digest: Digest
    reference_audit_certificate_digest: Digest
    complete: Literal[True]
    graph_revision: Identifier
    observation_revision: Identifier
    memory_plane_write_revision: int = Field(ge=0)
    temporal_projection_generation_digest: Digest | None
    temporal_projection_pointer_digest: Digest | None
    trust_projection_generation_digest: Digest | None
    trust_projection_pointer_digest: Digest | None
    observation_schema_fingerprint: Digest
    changed_record_keys: tuple[GraphObservationRecordKey, ...]
    boundary_record_keys: tuple[GraphObservationRecordKey, ...]

    @model_validator(mode="after")
    def _validate_coordinates(self) -> _GraphObservationCohortBody:
        pairs = (
            (self.graph_revision_delta_ids, self.graph_revision_delta_digests),
            (self.ingestion_observation_delta_ids, self.ingestion_observation_delta_digests),
        )
        temporal_pair = (
            self.temporal_projection_generation_digest,
            self.temporal_projection_pointer_digest,
        )
        trust_pair = (
            self.trust_projection_generation_digest,
            self.trust_projection_pointer_digest,
        )
        changed = tuple((item.record_kind, item.primary_key) for item in self.changed_record_keys)
        boundary = tuple((item.record_kind, item.primary_key) for item in self.boundary_record_keys)
        if (
            any(len(ids) != len(digests) for ids, digests in pairs)
            or (temporal_pair[0] is None) != (temporal_pair[1] is None)
            or (trust_pair[0] is None) != (trust_pair[1] is None)
            or changed != tuple(sorted(set(changed)))
            or boundary != tuple(sorted(set(boundary)))
            or set(changed) & set(boundary)
        ):
            raise ValueError("graph observation cohort coordinates are invalid")
        return self


class GraphObservationCohortPreimage(_GraphObservationCohortBody):
    pass


class ResolvedGraphObservationCohort(_GraphObservationCohortBody):
    cohort_digest: Digest


class GraphObservationCursorPayload(_ClosedSnapshotContract):
    schema_version: Literal[1]
    stream_position: int = Field(ge=0)
    preceding_record_kind: GraphObservationRecordKindV3 | None
    preceding_primary_key: Identifier | None
    preceding_record_digest: Digest | None
    requested_total_page_size: int = Field(gt=0)
    page_policy_revision: Identifier
    page_policy_digest: Digest
    caller_context_digest: Digest
    authorization_decision_digest: Digest
    authorization_expires_at: datetime
    cohort_digest: Digest
    snapshot_token: Identifier
    snapshot_write_revision: int = Field(ge=0)
    graph_revision: Identifier
    observation_revision: Identifier
    view: GraphObservationView
    valid_at: datetime | None
    system_as_of: datetime
    signature: str = Field(pattern=r"^[0-9a-f]{128}$")

    @model_validator(mode="after")
    def _validate_coordinates(self) -> GraphObservationCursorPayload:
        predecessor = (
            self.preceding_record_kind,
            self.preceding_primary_key,
            self.preceding_record_digest,
        )
        if (self.stream_position == 0 and predecessor != (None, None, None)) or (
            self.stream_position > 0 and any(value is None for value in predecessor)
        ):
            raise ValueError("graph observation cursor predecessor is invalid")
        _utc(self.authorization_expires_at, label="cursor authorization expiry")
        _utc(self.system_as_of, label="cursor system_as_of")
        if self.valid_at is not None:
            _utc(self.valid_at, label="cursor valid_at")
        return self


__all__ = [
    "GraphObservationCohortPreimage", "GraphObservationCursorPayload",
    "GraphObservationRecordKey", "ResolvedGraphObservationCohort",
]
