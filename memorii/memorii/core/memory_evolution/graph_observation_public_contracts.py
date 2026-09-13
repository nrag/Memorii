"""Closed profile-3 public observation body contracts, without runtime behavior."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_evolution.graph_ingestion_time_contracts import (
    ProductionIngestionTimeAttestation,
    SourceRetentionTimeAttestation,
    TransactionGroupCommitTimeAttestation,
)
from memorii.core.memory_evolution.graph_observation_contracts import (
    GraphObservationCohortSelector,
    GraphObservationFailure,
)
from memorii.core.memory_evolution.graph_observation_records import Digest, Identifier
from memorii.core.memory_evolution.graph_observation_snapshot_contracts import (
    GraphObservationCohortPreimage,
    GraphObservationView,
    ResolvedGraphObservationCohort,
)
from memorii.core.memory_evolution.graph_observation_streams import GraphObservationStreamRecord
from memorii.core.memory_evolution.models import MemoryScope


def _utc(value: datetime, *, label: str) -> datetime:
    offset = value.utcoffset()
    if value.tzinfo is None or offset is None or offset.total_seconds() != 0:
        raise ValueError(f"{label} must be timezone-aware UTC")
    return value.astimezone(UTC)


class _ClosedPublicContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="before")
    @classmethod
    def _reject_boolean_schema_version(cls, value: object) -> object:
        if (
            isinstance(value, Mapping)
            and any(
                isinstance(value.get(field), bool)
                for field in ("schema_version", "cursor_schema_version")
                if field in cls.model_fields
            )
        ):
            raise ValueError("schema version must be an integer literal")
        return value


class AuthenticatedGraphObservationContext(_ClosedPublicContract):
    principal_subject_id: Identifier
    tenant_partition_id: Identifier
    authorized_scope_set_digest: Digest
    authentication_session_id: Identifier
    context_digest: Digest


class GraphObservationAuthorizationDecision(_ClosedPublicContract):
    kind: Literal["authorized"]
    authorized_scope_identity: Identifier
    policy_revision: Identifier
    page_policy_revision: Identifier
    page_policy_digest: Digest
    expires_at: datetime
    decision_digest: Digest

    @model_validator(mode="after")
    def _validate_time(self) -> GraphObservationAuthorizationDecision:
        _utc(self.expires_at, label="authorization expiry")
        return self


class GraphObservationPagePolicySnapshot(_ClosedPublicContract):
    policy_revision: Identifier
    minimum_total_page_size: int = Field(gt=0)
    maximum_total_page_size: int = Field(gt=0)
    cursor_schema_version: Literal[1]
    snapshot_maximum_age: timedelta
    policy_digest: Digest

    @model_validator(mode="after")
    def _validate_bounds(self) -> GraphObservationPagePolicySnapshot:
        if self.minimum_total_page_size > self.maximum_total_page_size or self.snapshot_maximum_age <= timedelta(0):
            raise ValueError("graph observation page policy bounds are invalid")
        return self


class GraphObservationRequestCoordinates(_ClosedPublicContract):
    scope_constraint: MemoryScope
    cohort_selector: GraphObservationCohortSelector
    view: GraphObservationView
    expected_graph_revision: Identifier
    expected_observation_revision: Identifier
    valid_at: datetime | None
    system_as_of: datetime
    total_page_size: int = Field(gt=0)

    @model_validator(mode="after")
    def _validate_times(self) -> GraphObservationRequestCoordinates:
        _utc(self.system_as_of, label="graph observation system_as_of")
        if self.valid_at is not None:
            _utc(self.valid_at, label="graph observation valid_at")
        return self


class IngestionTimeAttestationRequestCoordinates(_ClosedPublicContract):
    scope_constraint: MemoryScope
    cohort_selector: GraphObservationCohortSelector
    expected_graph_revision: Identifier
    expected_observation_revision: Identifier
    total_page_size: int = Field(gt=0)


class GraphObservationRequest(GraphObservationRequestCoordinates):
    cursor: str | None


class IngestionTimeAttestationRequest(IngestionTimeAttestationRequestCoordinates):
    cursor: str | None


class IngestionTimeAttestationCursorPayload(_ClosedPublicContract):
    """Signed continuation coordinates for the ingestion-time endpoint only."""

    schema_version: Literal[1]
    stream_position: int = Field(ge=0)
    preceding_attestation_kind: Literal[
        "source_retention", "transaction_group_commit"
    ] | None
    preceding_attestation_id: Identifier | None
    preceding_attestation_digest: Digest | None
    request: IngestionTimeAttestationRequestCoordinates
    page_policy_revision: Identifier
    page_policy_digest: Digest
    caller_context_digest: Digest
    authorization_decision_digest: Digest
    authorization_expires_at: datetime
    cohort_digest: Digest
    snapshot_token: Identifier
    snapshot_write_revision: int = Field(ge=0)
    signature: Annotated[str, Field(pattern=r"^[0-9a-f]{128}$")]

    @model_validator(mode="before")
    @classmethod
    def _reject_boolean_integers(cls, value: object) -> object:
        if isinstance(value, Mapping) and any(
            isinstance(value.get(field), bool)
            for field in ("schema_version", "stream_position", "snapshot_write_revision")
        ):
            raise ValueError("ingestion-time cursor integer must be an integer literal")
        return value

    @model_validator(mode="after")
    def _validate_predecessor(self) -> IngestionTimeAttestationCursorPayload:
        _utc(self.authorization_expires_at, label="ingestion-time cursor authorization expiry")
        predecessor = (
            self.preceding_attestation_kind,
            self.preceding_attestation_id,
            self.preceding_attestation_digest,
        )
        if self.stream_position == 0 and any(value is not None for value in predecessor):
            raise ValueError("position-zero ingestion-time cursor has a predecessor")
        if self.stream_position > 0 and any(value is None for value in predecessor):
            raise ValueError("positive ingestion-time cursor lacks a predecessor")
        return self


def _validate_snapshot_coordinates(
    *,
    authorization_decision: GraphObservationAuthorizationDecision,
    cohort_preimage: GraphObservationCohortPreimage,
    resolved_cohort: ResolvedGraphObservationCohort,
    cohort_selector: GraphObservationCohortSelector,
    expected_graph_revision: str,
    expected_observation_revision: str,
) -> None:
    if (
        cohort_preimage.model_dump(mode="python")
        != resolved_cohort.model_dump(mode="python", exclude={"cohort_digest"})
        or authorization_decision.decision_digest != resolved_cohort.authorization_decision_digest
        or authorization_decision.authorized_scope_identity != resolved_cohort.authorized_scope_identity
        or authorization_decision.policy_revision != resolved_cohort.authorization_policy_revision
        or cohort_selector.seed_source_ids != resolved_cohort.seed_source_ids
        or cohort_selector.seed_operation_ids != resolved_cohort.seed_operation_ids
        or (
            cohort_selector.include_referenced_boundary_entities
            != resolved_cohort.include_referenced_boundary_entities
        )
        or expected_graph_revision != resolved_cohort.graph_revision
        or expected_observation_revision != resolved_cohort.observation_revision
    ):
        raise ValueError("graph observation snapshot coordinates are invalid")


class GraphRecordObservationSnapshot(_ClosedPublicContract):
    schema_version: Literal[1]
    snapshot_token: Identifier
    created_at: datetime
    memory_plane_write_revision: int = Field(ge=0)
    authenticated_context_digest: Digest
    purpose: Literal["graph_observation"]
    authorization_decision: GraphObservationAuthorizationDecision
    request: GraphObservationRequestCoordinates
    cohort_preimage: GraphObservationCohortPreimage
    resolved_cohort: ResolvedGraphObservationCohort
    stream: tuple[GraphObservationStreamRecord, ...]

    @model_validator(mode="after")
    def _validate_coordinates(self) -> GraphRecordObservationSnapshot:
        _utc(self.created_at, label="graph observation snapshot creation time")
        _validate_snapshot_coordinates(
            authorization_decision=self.authorization_decision, cohort_preimage=self.cohort_preimage,
            resolved_cohort=self.resolved_cohort,
            cohort_selector=self.request.cohort_selector,
            expected_graph_revision=self.request.expected_graph_revision,
            expected_observation_revision=self.request.expected_observation_revision,
        )
        if self.memory_plane_write_revision != self.resolved_cohort.memory_plane_write_revision:
            raise ValueError("graph observation snapshot write revision is invalid")
        stream_keys = tuple((record.record_kind, record.primary_key) for record in self.stream)
        cohort_keys = {
            (key.record_kind, key.primary_key) for key in self.resolved_cohort.changed_record_keys
        } | {
            (key.record_kind, key.primary_key) for key in self.resolved_cohort.boundary_record_keys
        }
        if stream_keys != tuple(sorted(set(stream_keys))) or set(stream_keys) != cohort_keys:
            raise ValueError("graph observation snapshot stream is invalid")
        return self


class IngestionTimeObservationSnapshot(_ClosedPublicContract):
    schema_version: Literal[1]
    snapshot_token: Identifier
    created_at: datetime
    memory_plane_write_revision: int = Field(ge=0)
    authenticated_context_digest: Digest
    purpose: Literal["ingestion_time_attestation"]
    authorization_decision: GraphObservationAuthorizationDecision
    request: IngestionTimeAttestationRequestCoordinates
    cohort_preimage: GraphObservationCohortPreimage
    resolved_cohort: ResolvedGraphObservationCohort
    stream: tuple[ProductionIngestionTimeAttestation, ...]

    @model_validator(mode="after")
    def _validate_coordinates(self) -> IngestionTimeObservationSnapshot:
        _utc(self.created_at, label="ingestion-time snapshot creation time")
        _validate_snapshot_coordinates(
            authorization_decision=self.authorization_decision, cohort_preimage=self.cohort_preimage,
            resolved_cohort=self.resolved_cohort,
            cohort_selector=self.request.cohort_selector,
            expected_graph_revision=self.request.expected_graph_revision,
            expected_observation_revision=self.request.expected_observation_revision,
        )
        if self.memory_plane_write_revision != self.resolved_cohort.memory_plane_write_revision:
            raise ValueError("ingestion-time snapshot write revision is invalid")
        attestation_keys = tuple(attestation_order_key(value) for value in self.stream)
        if attestation_keys != tuple(sorted(set(attestation_keys))):
            raise ValueError("ingestion-time snapshot stream is invalid")
        return self


GraphObservationSnapshot: TypeAlias = Annotated[
    GraphRecordObservationSnapshot | IngestionTimeObservationSnapshot,
    Field(discriminator="purpose"),
]


def _validate_page_positions(*, start: int, end: int, count: int) -> None:
    if end < start or end - start != count:
        raise ValueError("graph observation page positions are invalid")


def attestation_order_key(
    value: ProductionIngestionTimeAttestation,
) -> tuple[str, str, str, str, str]:
    if isinstance(value, SourceRetentionTimeAttestation):
        return (value.kind, value.source_id, value.operation_fence_id, "", value.attestation_id)
    if isinstance(value, TransactionGroupCommitTimeAttestation):
        return (
            value.kind, value.source_id, value.operation_fence_id,
            value.transaction_group_id, value.attestation_id,
        )
    raise ValueError("unknown ingestion-time attestation kind")


class GraphObservationPage(_ClosedPublicContract):
    kind: Literal["page"]
    graph_revision: Identifier
    observation_revision: Identifier
    snapshot_token: Identifier
    memory_plane_write_revision: int = Field(ge=0)
    cohort: ResolvedGraphObservationCohort
    page_policy_revision: Identifier
    page_policy_digest: Digest
    view: GraphObservationView
    valid_at: datetime | None
    system_as_of: datetime
    total_page_size: int = Field(gt=0)
    stream_start_position: int = Field(ge=0)
    stream_end_position: int = Field(ge=0)
    records: tuple[GraphObservationStreamRecord, ...]
    observation_schema_fingerprint: Digest
    next_cursor: str | None
    page_digest: Digest

    @model_validator(mode="after")
    def _validate_coordinates(self) -> GraphObservationPage:
        _utc(self.system_as_of, label="graph observation page system_as_of")
        if self.valid_at is not None:
            _utc(self.valid_at, label="graph observation page valid_at")
        _validate_page_positions(start=self.stream_start_position, end=self.stream_end_position, count=len(self.records))
        record_keys = tuple((record.record_kind, record.primary_key) for record in self.records)
        if (
            len(self.records) > self.total_page_size
            or record_keys != tuple(sorted(set(record_keys)))
            or (
                not self.records
                and (
                    self.stream_start_position != 0
                    or self.stream_end_position != 0
                    or self.next_cursor is not None
                )
            )
            or self.graph_revision != self.cohort.graph_revision
            or self.observation_revision != self.cohort.observation_revision
            or self.memory_plane_write_revision != self.cohort.memory_plane_write_revision
            or self.observation_schema_fingerprint != self.cohort.observation_schema_fingerprint
        ):
            raise ValueError("graph observation page cohort coordinates are invalid")
        return self


class IngestionTimeAttestationPage(_ClosedPublicContract):
    kind: Literal["page"]
    graph_revision: Identifier
    observation_revision: Identifier
    snapshot_token: Identifier
    memory_plane_write_revision: int = Field(ge=0)
    cohort: ResolvedGraphObservationCohort
    page_policy_revision: Identifier
    page_policy_digest: Digest
    total_page_size: int = Field(gt=0)
    stream_start_position: int = Field(ge=0)
    stream_end_position: int = Field(ge=0)
    attestations: tuple[ProductionIngestionTimeAttestation, ...]
    next_cursor: str | None
    page_digest: Digest

    @model_validator(mode="after")
    def _validate_coordinates(self) -> IngestionTimeAttestationPage:
        _validate_page_positions(start=self.stream_start_position, end=self.stream_end_position, count=len(self.attestations))
        attestation_keys = tuple(attestation_order_key(value) for value in self.attestations)
        if (
            len(self.attestations) > self.total_page_size
            or attestation_keys != tuple(sorted(set(attestation_keys)))
            or (
                not self.attestations
                and (
                    self.stream_start_position != 0
                    or self.stream_end_position != 0
                    or self.next_cursor is not None
                )
            )
            or self.graph_revision != self.cohort.graph_revision
            or self.observation_revision != self.cohort.observation_revision
            or self.memory_plane_write_revision != self.cohort.memory_plane_write_revision
        ):
            raise ValueError("ingestion-time page cohort coordinates are invalid")
        return self


GraphObservationResponse: TypeAlias = Annotated[
    GraphObservationPage | GraphObservationFailure,
    Field(discriminator="kind"),
]
IngestionTimeAttestationResponse: TypeAlias = Annotated[
    IngestionTimeAttestationPage | GraphObservationFailure,
    Field(discriminator="kind"),
]


__all__ = [
    "AuthenticatedGraphObservationContext", "GraphObservationAuthorizationDecision",
    "GraphObservationPagePolicySnapshot", "GraphObservationRequestCoordinates",
    "IngestionTimeAttestationRequestCoordinates", "GraphObservationRequest",
    "IngestionTimeAttestationRequest", "IngestionTimeAttestationCursorPayload",
    "GraphRecordObservationSnapshot",
    "IngestionTimeObservationSnapshot", "GraphObservationSnapshot", "GraphObservationPage",
    "IngestionTimeAttestationPage", "GraphObservationResponse", "IngestionTimeAttestationResponse",
]
