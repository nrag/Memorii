"""Closed contracts for authenticated structural graph observation.

These models intentionally stop before record projection and storage access.  A
future repository owner supplies the resolved cohort and page records; callers
can neither supply an authorization decision nor weaken the cohort selector.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_evolution.models import MemoryScope
from memorii.core.semantic_ingestion.contracts import contract_digest

GraphObservationRecordKind = Literal[
    "entity_revision", "alias_revision", "type_evidence", "claim_assertion",
    "claim_projection", "relation", "action_revision", "citation", "provenance",
    "temporal_transition", "identity_transition", "reference_disposition",
    "source_introduction", "operation_introduction", "operation_terminal_outcome",
    "source_terminal_outcome",
]
GraphObservationPurpose = Literal["graph_observation", "ingestion_time_attestation"]
GraphObservationView = Literal["current", "historical", "lineage"]
GraphObservationFailureReason = Literal["denied", "invalid_cursor", "stale_cursor", "revoked_access"]

_CONTEXT_DOMAIN = b"memorii.graph-observation.context.v1"
_POLICY_DOMAIN = b"memorii.graph-observation.page-policy.v1"
_DECISION_DOMAIN = b"memorii.graph-observation.authorization-decision.v1"
_COHORT_DOMAIN = b"memorii.graph-observation.resolved-cohort.v1"
_SCOPE_IDENTITY_DOMAIN = b"memorii.graph-observation.authorized-scope-identity.v1"


def _utc(value: datetime, *, label: str) -> datetime:
    offset = value.utcoffset()
    if value.tzinfo is None or offset is None or offset.total_seconds() != 0:
        raise ValueError(f"{label} must be timezone-aware UTC")
    return value.astimezone(UTC)


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class AuthenticatedGraphObservationContext(_ClosedModel):
    principal_subject_id: str = Field(min_length=1)
    tenant_partition_id: str = Field(min_length=1)
    authorized_scope_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    authentication_session_id: str = Field(min_length=1)
    context_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _validate_digest(self) -> AuthenticatedGraphObservationContext:
        body = self.model_dump(mode="python", exclude={"context_digest"})
        if self.context_digest != contract_digest(_CONTEXT_DOMAIN, body):
            raise ValueError("graph observation context digest mismatch")
        return self

    @classmethod
    def create(cls, *, principal_subject_id: str, tenant_partition_id: str,
               authorized_scope_set_digest: str, authentication_session_id: str) -> AuthenticatedGraphObservationContext:
        body = {"principal_subject_id": principal_subject_id, "tenant_partition_id": tenant_partition_id,
                "authorized_scope_set_digest": authorized_scope_set_digest,
                "authentication_session_id": authentication_session_id}
        return cls(**body, context_digest=contract_digest(_CONTEXT_DOMAIN, body))


class GraphObservationPagePolicySnapshot(_ClosedModel):
    policy_revision: str = Field(min_length=1)
    minimum_total_page_size: int = Field(gt=0)
    maximum_total_page_size: int = Field(gt=0)
    cursor_schema_version: Literal[1]
    snapshot_maximum_age: timedelta
    policy_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _validate_policy(self) -> GraphObservationPagePolicySnapshot:
        if self.minimum_total_page_size > self.maximum_total_page_size or self.snapshot_maximum_age <= timedelta(0):
            raise ValueError("graph observation page policy bounds are invalid")
        body = self.model_dump(mode="python", exclude={"policy_digest"})
        if self.policy_digest != contract_digest(_POLICY_DOMAIN, body):
            raise ValueError("graph observation page policy digest mismatch")
        return self

    @classmethod
    def create(cls, *, policy_revision: str, minimum_total_page_size: int,
               maximum_total_page_size: int, snapshot_maximum_age: timedelta) -> GraphObservationPagePolicySnapshot:
        body = {"policy_revision": policy_revision, "minimum_total_page_size": minimum_total_page_size,
                "maximum_total_page_size": maximum_total_page_size, "cursor_schema_version": 1,
                "snapshot_maximum_age": snapshot_maximum_age}
        return cls(**body, policy_digest=contract_digest(_POLICY_DOMAIN, body))


class GraphObservationAuthorizationDecision(_ClosedModel):
    kind: Literal["authorized"]
    authorized_scope_identity: str = Field(min_length=1)
    policy_revision: str = Field(min_length=1)
    page_policy_revision: str = Field(min_length=1)
    page_policy_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    expires_at: datetime
    decision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _validate_decision_shape(self) -> GraphObservationAuthorizationDecision:
        _utc(self.expires_at, label="authorization expiry")
        return self

    @classmethod
    def create(cls, *, preimage: GraphObservationAuthorizationDecisionPreimage) -> GraphObservationAuthorizationDecision:
        return cls(
            kind="authorized",
            authorized_scope_identity=authorized_scope_identity(preimage.authorized_scope),
            policy_revision=preimage.policy.policy_revision,
            page_policy_revision=preimage.policy.policy_revision,
            page_policy_digest=preimage.policy.policy_digest,
            expires_at=_utc(preimage.expires_at, label="authorization expiry"),
            decision_digest=contract_digest(_DECISION_DOMAIN, preimage.model_dump(mode="python")),
        )

    def validate_for_request(self, preimage: GraphObservationAuthorizationDecisionPreimage) -> None:
        if self != type(self).create(preimage=preimage):
            raise ValueError("graph observation authorization decision does not bind the request")


class GraphObservationAuthorizationDecisionPreimage(_ClosedModel):
    """Protected inputs bound before any seed, cohort, index, or store lookup."""

    context: AuthenticatedGraphObservationContext
    purpose: GraphObservationPurpose
    scope_constraint: MemoryScope
    selector: GraphObservationCohortSelector
    authorized_scope: MemoryScope
    policy: GraphObservationPagePolicySnapshot
    expires_at: datetime

    @model_validator(mode="after")
    def _validate_preimage(self) -> GraphObservationAuthorizationDecisionPreimage:
        _utc(self.expires_at, label="authorization expiry")
        if not self.authorized_scope.can_read(self.scope_constraint):
            raise ValueError("graph observation scope constraint exceeds authorized scope")
        return self

def authorized_scope_identity(scope: MemoryScope) -> str:
    """Hash the complete typed scope; display-oriented ``stable_id`` is unsafe."""
    return contract_digest(_SCOPE_IDENTITY_DOMAIN, scope.model_dump(mode="python"))


class GraphObservationFailure(_ClosedModel):
    kind: Literal["failure"] = "failure"
    reason: GraphObservationFailureReason
    request_correlation_token: str = Field(min_length=1)


class GraphObservationCohortSelector(_ClosedModel):
    seed_source_ids: tuple[str, ...]
    seed_operation_ids: tuple[str, ...]
    include_referenced_boundary_entities: Literal[True]

    @model_validator(mode="after")
    def _validate_selector(self) -> GraphObservationCohortSelector:
        if not self.seed_source_ids and not self.seed_operation_ids:
            raise ValueError("graph observation selector must include a seed")
        for values, label in ((self.seed_source_ids, "source"), (self.seed_operation_ids, "operation")):
            if any(not value for value in values) or values != tuple(sorted(set(values), key=lambda value: value.encode("utf-8"))):
                raise ValueError(f"graph observation {label} seeds must be ordered, unique, and nonempty")
        return self


class ResolvedGraphObservationCohort(_ClosedModel):
    seed_source_ids: tuple[str, ...]
    seed_operation_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    operation_ids: tuple[str, ...]
    operation_fence_ids: tuple[str, ...]
    include_referenced_boundary_entities: Literal[True]
    authorized_scope_identity: str = Field(min_length=1)
    authorization_policy_revision: str = Field(min_length=1)
    authorization_decision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    graph_revision_delta_ids: tuple[str, ...]
    graph_revision_delta_digests: tuple[str, ...]
    ingestion_observation_delta_ids: tuple[str, ...]
    ingestion_observation_delta_digests: tuple[str, ...]
    reference_schema_manifest_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reference_ledger_high_watermark: str = Field(min_length=1)
    reference_ledger_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    reference_audit_certificate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    complete: Literal[True]
    cohort_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _validate_cohort(self) -> ResolvedGraphObservationCohort:
        pairs = ((self.graph_revision_delta_ids, self.graph_revision_delta_digests),
                 (self.ingestion_observation_delta_ids, self.ingestion_observation_delta_digests))
        if any(len(ids) != len(digests) for ids, digests in pairs):
            raise ValueError("graph observation cohort delta coordinates are mismatched")
        body = self.model_dump(mode="python", exclude={"cohort_digest"})
        if self.cohort_digest != contract_digest(_COHORT_DOMAIN, body):
            raise ValueError("graph observation cohort digest mismatch")
        return self


class GraphObservationRequest(_ClosedModel):
    scope_constraint: MemoryScope
    cohort_selector: GraphObservationCohortSelector
    view: GraphObservationView
    expected_graph_revision: str = Field(min_length=1)
    expected_observation_revision: str = Field(min_length=1)
    valid_at: datetime | None
    system_as_of: datetime
    total_page_size: int = Field(gt=0)
    cursor: str | None

    @model_validator(mode="after")
    def _validate_times(self) -> GraphObservationRequest:
        _utc(self.system_as_of, label="system_as_of")
        if self.valid_at is not None:
            _utc(self.valid_at, label="valid_at")
        return self


class IngestionTimeAttestationRequest(_ClosedModel):
    scope_constraint: MemoryScope
    cohort_selector: GraphObservationCohortSelector
    expected_graph_revision: str = Field(min_length=1)
    expected_observation_revision: str = Field(min_length=1)
    total_page_size: int = Field(gt=0)
    cursor: str | None


class GraphObservationCursorPayload(_ClosedModel):
    schema_version: Literal[1]
    stream_position: int = Field(ge=0)
    preceding_record_kind: GraphObservationRecordKind | None
    preceding_primary_key: str | None
    preceding_record_digest: str | None
    requested_total_page_size: int = Field(gt=0)
    page_policy_revision: str = Field(min_length=1)
    page_policy_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    caller_context_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    authorization_decision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    authorization_expires_at: datetime
    cohort_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    snapshot_token: str = Field(min_length=1)
    graph_revision: str = Field(min_length=1)
    observation_revision: str = Field(min_length=1)
    view: GraphObservationView
    valid_at: datetime | None
    system_as_of: datetime
    signature: str = Field(pattern=r"^[0-9a-f]{128}$")

    @model_validator(mode="after")
    def _validate_cursor_shape(self) -> GraphObservationCursorPayload:
        triple = (self.preceding_record_kind, self.preceding_primary_key, self.preceding_record_digest)
        if (self.stream_position == 0 and triple != (None, None, None)) or (self.stream_position > 0 and any(value is None for value in triple)):
            raise ValueError("graph observation cursor predecessor is invalid")
        _utc(self.authorization_expires_at, label="cursor authorization expiry")
        _utc(self.system_as_of, label="cursor system_as_of")
        if self.valid_at is not None:
            _utc(self.valid_at, label="cursor valid_at")
        return self


class GraphObservationUnsignedCursorCoordinates(_ClosedModel):
    """Exact signed cursor coordinates before a configured signer adds bytes."""

    schema_version: Literal[1]
    stream_position: int = Field(ge=0)
    preceding_record_kind: GraphObservationRecordKind | None
    preceding_primary_key: str | None
    preceding_record_digest: str | None
    requested_total_page_size: int = Field(gt=0)
    page_policy_revision: str = Field(min_length=1)
    page_policy_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    caller_context_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    authorization_decision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    authorization_expires_at: datetime
    cohort_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    snapshot_token: str = Field(min_length=1)
    graph_revision: str = Field(min_length=1)
    observation_revision: str = Field(min_length=1)
    view: GraphObservationView
    valid_at: datetime | None
    system_as_of: datetime

    @model_validator(mode="after")
    def _validate_shape(self) -> GraphObservationUnsignedCursorCoordinates:
        GraphObservationCursorPayload.model_validate(
            self.model_dump(mode="python") | {"signature": "0" * 128}
        )
        return self

    def signed(self, signature: str) -> GraphObservationCursorPayload:
        return GraphObservationCursorPayload.model_validate(
            self.model_dump(mode="python") | {"signature": signature}
        )


class GraphObservationAuthorizer(Protocol):
    def authorize(self, *, context: AuthenticatedGraphObservationContext, purpose: GraphObservationPurpose,
                  scope_constraint: MemoryScope, selector: GraphObservationCohortSelector,
                  server_time: datetime) -> GraphObservationAuthorizationDecision | GraphObservationFailure: ...
