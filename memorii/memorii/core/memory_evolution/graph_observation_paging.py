"""Authenticated, snapshot-contiguous paging for registered profile-3 observations.

This module deliberately owns no graph projection.  A host composes a cohort
provider which derives a complete stream from the one detached memory-plane
snapshot passed to it.  The owner here enforces the public read order,
authorization, retention, cursor continuity, and registered artifact boundary.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from secrets import token_urlsafe
from threading import RLock
from typing import Protocol, TypeVar

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import BaseModel

from memorii.core.memory_evolution.graph_ingestion_time_contracts import ProductionIngestionTimeAttestation
from memorii.core.memory_evolution.graph_observation_contracts import (
    GraphObservationCohortSelector,
    GraphObservationFailure,
    GraphObservationFailureReason,
    GraphObservationPurpose,
)
from memorii.core.memory_evolution.graph_observation_public_contracts import (
    AuthenticatedGraphObservationContext,
    GraphObservationAuthorizationDecision,
    GraphObservationPage,
    GraphObservationPagePolicySnapshot,
    GraphObservationRequest,
    GraphObservationRequestCoordinates,
    GraphObservationResponse,
    GraphRecordObservationSnapshot,
    IngestionTimeAttestationCursorPayload,
    IngestionTimeAttestationPage,
    IngestionTimeAttestationRequest,
    IngestionTimeAttestationRequestCoordinates,
    IngestionTimeAttestationResponse,
    IngestionTimeObservationSnapshot,
    _attestation_order_key,
)
from memorii.core.memory_evolution.graph_observation_snapshot_contracts import (
    GraphObservationCohortPreimage,
    GraphObservationCursorPayload,
    ResolvedGraphObservationCohort,
)
from memorii.core.memory_evolution.graph_observation_streams import GraphObservationStreamRecord
from memorii.core.memory_evolution.ingestion_contracts import AuthenticatedIngressResolutionError
from memorii.core.memory_evolution.models import MemoryScope
from memorii.core.memory_evolution.observation_activation_runtime import (
    ObservationActivationRuntimeError,
    RegisteredObservationArtifact,
    decode_registered_ingestion_time_attestation_cursor,
    decode_registered_observation_cursor,
    emit_registered_observation_artifact,
    issue_registered_ingestion_time_attestation_cursor,
    issue_registered_observation_cursor,
)
from memorii.core.memory_evolution.typed_value_artifact_integrity import TrustedTypedValueArtifactVerificationKey
from memorii.core.memory_evolution.typed_value_artifact_reader import ProtectedTypedValueArtifactReaderLimits
from memorii.core.memory_evolution.typed_value_model_codec import TypedValueModelCodecCapacityError
from memorii.core.memory_evolution.typed_value_publication import VerifiedTypedValuePublication
from memorii.core.memory_evolution.typed_value_registry_history import ProtectedTypedValueRegistryHistory
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService

_RegisteredModel = TypeVar("_RegisteredModel", bound=BaseModel)


class GraphObservationPagingError(ValueError):
    """Raised for a malformed trusted collaborator result or unavailable schema."""


class ObservationAuthorizationUnavailableError(ValueError):
    """The host could not authenticate ingress or resolve current grants."""


class ObservationCohortUnavailableError(ValueError):
    """A complete authorized cohort cannot be proved from the detached inventory."""


class ObservationSnapshotCapacityError(ObservationCohortUnavailableError):
    """The cohort exceeds a protected snapshot or retention ceiling."""


class ProtectedObservationClock(Protocol):
    def now(self) -> datetime: ...


class GraphObservationContextResolver(Protocol):
    def resolve(self, *, host_ingress: object, server_time: datetime) -> AuthenticatedGraphObservationContext | None: ...


@dataclass(frozen=True)
class VerifiedGraphObservationAuthorization:
    """Private authorization result; the concrete scope never crosses the wire."""

    decision: GraphObservationAuthorizationDecision
    page_policy: GraphObservationPagePolicySnapshot
    authorized_scope: MemoryScope


class GrantBackedGraphObservationAuthorizer(Protocol):
    def authorize(
        self,
        *,
        context: AuthenticatedGraphObservationContext,
        scope_constraint: MemoryScope,
        cohort_selector: GraphObservationCohortSelector,
        purpose: GraphObservationPurpose,
        server_time: datetime,
    ) -> VerifiedGraphObservationAuthorization | None: ...


@dataclass(frozen=True)
class DetachedGraphObservationRecords:
    """The sole inventory a cohort provider may use for one observation."""

    memory_plane_write_revision: int
    records: tuple[CanonicalMemoryRecord, ...]


@dataclass(frozen=True)
class GraphObservationCohortInput:
    cohort_preimage: GraphObservationCohortPreimage
    stream: tuple[GraphObservationStreamRecord, ...]


@dataclass(frozen=True)
class IngestionTimeObservationCohortInput:
    cohort_preimage: GraphObservationCohortPreimage
    stream: tuple[ProductionIngestionTimeAttestation, ...]


class DetachedGraphObservationCohortProvider(Protocol):
    """Produces complete typed cohorts solely from ``snapshot.records``.

    Implementations must not use live graph, ledger, reference, or projection
    accessors.  This protocol intentionally has no default implementation.
    """

    def graph_observation_input(
        self,
        *,
        snapshot: DetachedGraphObservationRecords,
        context: AuthenticatedGraphObservationContext,
        decision: GraphObservationAuthorizationDecision,
        authorized_scope: MemoryScope,
        request: GraphObservationRequestCoordinates,
        maximum_stream_records: int,
        maximum_snapshot_bytes: int,
    ) -> GraphObservationCohortInput: ...

    def ingestion_time_input(
        self,
        *,
        snapshot: DetachedGraphObservationRecords,
        context: AuthenticatedGraphObservationContext,
        decision: GraphObservationAuthorizationDecision,
        authorized_scope: MemoryScope,
        request: IngestionTimeAttestationRequestCoordinates,
        maximum_stream_records: int,
        maximum_snapshot_bytes: int,
    ) -> IngestionTimeObservationCohortInput: ...


@dataclass(frozen=True)
class _RetainedGraphSnapshot:
    snapshot: GraphRecordObservationSnapshot
    expires_at: datetime


@dataclass(frozen=True)
class _RetainedIngestionSnapshot:
    snapshot: IngestionTimeObservationSnapshot
    expires_at: datetime


@dataclass(frozen=True)
class ObservationRetentionBudget:
    maximum_stream_records: int
    maximum_snapshot_bytes: int
    maximum_retained_snapshots: int
    maximum_retained_bytes: int
    maximum_tenant_snapshots: int
    maximum_tenant_bytes: int

    def __post_init__(self) -> None:
        for name, value in self.__dict__.items():
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer literal")


class AuthenticatedGraphObservationPagingRuntime:
    """Canonical owner for profile-3 observation page issuance and continuation."""

    def __init__(
        self,
        *,
        memory_plane: MemoryPlaneService,
        context_resolver: GraphObservationContextResolver,
        authorizer: GrantBackedGraphObservationAuthorizer,
        cohort_provider: DetachedGraphObservationCohortProvider,
        protected_clock: ProtectedObservationClock,
        registry_history: ProtectedTypedValueRegistryHistory,
        registry_publication: VerifiedTypedValuePublication,
        cursor_signing_key: Ed25519PrivateKey,
        cursor_verification_key: TrustedTypedValueArtifactVerificationKey,
        reader_limits: ProtectedTypedValueArtifactReaderLimits,
        correlation_token_factory: Callable[[], str],
        retention_budget: ObservationRetentionBudget,
    ) -> None:
        self._memory_plane = memory_plane
        self._context_resolver = context_resolver
        self._authorizer = authorizer
        self._cohort_provider = cohort_provider
        self._clock = protected_clock
        self._history = registry_history
        self._publication = registry_publication
        self._signing_key = cursor_signing_key
        self._verification_key = cursor_verification_key
        self._limits = reader_limits
        self._correlation_token_factory = correlation_token_factory
        self._retention_budget = retention_budget
        self._retention_lock = RLock()
        self._graph_snapshots: dict[str, _RetainedGraphSnapshot] = {}
        self._ingestion_snapshots: dict[str, _RetainedIngestionSnapshot] = {}
        self._retained_tenants: dict[str, str] = {}
        self._retained_bytes: dict[str, int] = {}
        self._reservations: dict[str, str] = {}

    def observe_graph(
        self, *, host_ingress: object, request: GraphObservationRequest
    ) -> GraphObservationResponse:
        """Return one graph-record page after trusted reauthorization."""
        context, policy, decision, authorized_scope, now = self._authorize(
            host_ingress=host_ingress, scope_constraint=request.scope_constraint,
            cohort_selector=request.cohort_selector, purpose="graph_observation",
        )
        if decision is None:
            return self._failure("revoked_access" if request.cursor is not None else "denied")
        if context is None or policy is None or authorized_scope is None:
            raise GraphObservationPagingError("authorized graph request lacks private authority")
        if request.total_page_size < policy.minimum_total_page_size or request.total_page_size > policy.maximum_total_page_size:
            return self._failure("denied")
        coordinates = GraphObservationRequestCoordinates(**request.model_dump(exclude={"cursor"}))
        if request.cursor is None:
            token = self._reserve_token(context, now)
            if token is None:
                return self._failure("denied")
            completed = False
            try:
                write_revision, records = self._memory_plane.read_write_snapshot()
                cohort_input = self._cohort_provider.graph_observation_input(
                    snapshot=DetachedGraphObservationRecords(write_revision, records), context=context,
                    decision=decision, authorized_scope=authorized_scope, request=coordinates,
                    maximum_stream_records=self._retention_budget.maximum_stream_records,
                    maximum_snapshot_bytes=self._retention_budget.maximum_snapshot_bytes,
                )
                if decision.expires_at <= _utc(self._clock.now(), "protected observation clock"):
                    self._release_token(token)
                    return self._failure("denied")
                retained = self._retain_graph_snapshot(
                    context=context, decision=decision, policy=policy, request=coordinates,
                    cohort_input=cohort_input, memory_plane_write_revision=write_revision, created_at=now, token=token,
                )
                page = self._graph_page(
                    retained.snapshot, start=0, policy=policy, context=context, decision=decision, now=now
                )
                completed = True
                return page
            except (ObservationCohortUnavailableError, TypedValueModelCodecCapacityError):
                return self._failure("denied")
            finally:
                if not completed:
                    self._release_token(token)
        cursor = self._decode_cursor(request.cursor)
        if cursor is None:
            return self._failure("invalid_cursor")
        now = _utc(self._clock.now(), "protected observation clock")
        if decision.expires_at <= now:
            self._release_cursor_snapshot(cursor, context)
            return self._failure("revoked_access")
        if (cursor.page_policy_revision != policy.policy_revision
                or cursor.page_policy_digest != policy.policy_digest):
            self._release_cursor_snapshot(cursor, context)
            return self._failure("stale_cursor")
        retained = self._load_graph_continuation(
            cursor=cursor, context=context, decision=decision, policy=policy, request=coordinates, now=now
        )
        if isinstance(retained, str):
            return self._failure(retained)
        return self._graph_page(
            retained.snapshot, start=cursor.stream_position, policy=policy, context=context,
            decision=decision, now=now,
        )

    def observe_ingestion_time_attestations(
        self, *, host_ingress: object, request: IngestionTimeAttestationRequest
    ) -> IngestionTimeAttestationResponse:
        """Return a page from the separately signed ingestion-time stream."""
        context, policy, decision, authorized_scope, now = self._authorize(
            host_ingress=host_ingress, scope_constraint=request.scope_constraint,
            cohort_selector=request.cohort_selector, purpose="ingestion_time_attestation",
        )
        if decision is None:
            return self._failure("revoked_access" if request.cursor is not None else "denied")
        if context is None or policy is None or authorized_scope is None:
            raise GraphObservationPagingError("authorized ingestion-time request lacks private authority")
        if request.total_page_size < policy.minimum_total_page_size or request.total_page_size > policy.maximum_total_page_size:
            return self._failure("denied")
        coordinates = IngestionTimeAttestationRequestCoordinates(**request.model_dump(exclude={"cursor"}))
        if request.cursor is None:
            token = self._reserve_token(context, now)
            if token is None:
                return self._failure("denied")
            completed = False
            try:
                write_revision, records = self._memory_plane.read_write_snapshot()
                cohort_input = self._cohort_provider.ingestion_time_input(
                    snapshot=DetachedGraphObservationRecords(write_revision, records), context=context,
                    decision=decision, authorized_scope=authorized_scope, request=coordinates,
                    maximum_stream_records=self._retention_budget.maximum_stream_records,
                    maximum_snapshot_bytes=self._retention_budget.maximum_snapshot_bytes,
                )
                if decision.expires_at <= _utc(self._clock.now(), "protected observation clock"):
                    self._release_token(token)
                    return self._failure("denied")
                retained = self._retain_ingestion_snapshot(
                    context=context, decision=decision, policy=policy, request=coordinates,
                    cohort_input=cohort_input, memory_plane_write_revision=write_revision, created_at=now, token=token,
                )
                page = self._ingestion_page(retained.snapshot, 0, policy, context, decision)
                completed = True
                return page
            except (ObservationCohortUnavailableError, TypedValueModelCodecCapacityError):
                return self._failure("denied")
            finally:
                if not completed:
                    self._release_token(token)
        cursor = self._decode_ingestion_cursor(request.cursor)
        if cursor is None:
            return self._failure("invalid_cursor")
        now = _utc(self._clock.now(), "protected observation clock")
        if decision.expires_at <= now:
            self._release_cursor_snapshot(cursor, context)
            return self._failure("revoked_access")
        if (cursor.page_policy_revision != policy.policy_revision
                or cursor.page_policy_digest != policy.policy_digest):
            self._release_cursor_snapshot(cursor, context)
            return self._failure("stale_cursor")
        retained = self._load_ingestion_continuation(
            cursor=cursor, context=context, decision=decision, request=coordinates, now=now,
        )
        if isinstance(retained, str):
            return self._failure(retained)
        if decision.expires_at <= _utc(self._clock.now(), "protected observation clock"):
            return self._failure("revoked_access")
        return self._ingestion_page(retained.snapshot, cursor.stream_position, policy, context, decision)

    def _authorize(self, *, host_ingress: object, scope_constraint: MemoryScope,
                   cohort_selector: GraphObservationCohortSelector, purpose: GraphObservationPurpose) -> tuple[AuthenticatedGraphObservationContext | None, GraphObservationPagePolicySnapshot | None, GraphObservationAuthorizationDecision | None, MemoryScope | None, datetime]:
        now = _utc(self._clock.now(), "protected observation clock")
        try:
            context = self._context_resolver.resolve(host_ingress=host_ingress, server_time=now)
            if context is None:
                return None, None, None, None, now
            context = self._registered_exact(context, "AuthenticatedGraphObservationContext")
            authorization = self._authorizer.authorize(
                context=context, scope_constraint=scope_constraint, cohort_selector=cohort_selector,
                purpose=purpose, server_time=now,
            )
        except (AuthenticatedIngressResolutionError, ObservationAuthorizationUnavailableError, OSError):
            return None, None, None, None, now
        if authorization is None:
            # A denied authorization supplies no policy or concrete scope.
            return context, None, None, None, now
        policy = self._registered_exact(authorization.page_policy, "GraphObservationPagePolicySnapshot")
        decision = self._registered_exact(authorization.decision, "GraphObservationAuthorizationDecision")
        if (decision.page_policy_revision != policy.policy_revision
                or decision.page_policy_digest != policy.policy_digest
                or not authorization.authorized_scope.can_read(scope_constraint)):
            raise GraphObservationPagingError("authorization result is substituted")
        if decision.expires_at <= now:
            return context, policy, None, None, now
        return context, policy, decision, authorization.authorized_scope, now

    def _retain_graph_snapshot(self, *, context: AuthenticatedGraphObservationContext, decision: GraphObservationAuthorizationDecision, policy: GraphObservationPagePolicySnapshot, request: GraphObservationRequestCoordinates, cohort_input: GraphObservationCohortInput, memory_plane_write_revision: int, created_at: datetime, token: str) -> _RetainedGraphSnapshot:
        preimage = cohort_input.cohort_preimage
        if (
            preimage.memory_plane_write_revision != memory_plane_write_revision
            or preimage.graph_revision != request.expected_graph_revision
            or preimage.observation_revision != request.expected_observation_revision
            or preimage.authorization_decision_digest != decision.decision_digest
            or preimage.authorized_scope_identity != decision.authorized_scope_identity
            or preimage.authorization_policy_revision != decision.policy_revision
        ):
            raise GraphObservationPagingError("cohort input coordinates are substituted")
        if len(cohort_input.stream) > self._retention_budget.maximum_stream_records:
            raise ObservationSnapshotCapacityError("graph cohort stream exceeds protected capacity")
        cohort = self._emit_cohort(cohort_input.cohort_preimage)
        snapshot = GraphRecordObservationSnapshot(
            schema_version=1, snapshot_token=token, created_at=created_at,
            memory_plane_write_revision=cohort.memory_plane_write_revision,
            authenticated_context_digest=context.context_digest, purpose="graph_observation",
            authorization_decision=decision, request=request, cohort_preimage=cohort_input.cohort_preimage,
            resolved_cohort=cohort, stream=cohort_input.stream,
        )
        artifact = self._artifact(snapshot, "GraphRecordObservationSnapshot")
        snapshot = self._exact(artifact, GraphRecordObservationSnapshot)
        retained = _RetainedGraphSnapshot(snapshot, _retention_deadline(created_at, decision, policy))
        self._retain_token(token, context.tenant_partition_id, len(artifact.raw), retained, ingestion=False, now=_utc(self._clock.now(), "protected observation clock"))
        return retained

    def _retain_ingestion_snapshot(self, *, context: AuthenticatedGraphObservationContext,
                                   decision: GraphObservationAuthorizationDecision,
                                   policy: GraphObservationPagePolicySnapshot,
                                   request: IngestionTimeAttestationRequestCoordinates,
                                   cohort_input: IngestionTimeObservationCohortInput,
                                   memory_plane_write_revision: int,
                                   created_at: datetime, token: str) -> _RetainedIngestionSnapshot:
        preimage = cohort_input.cohort_preimage
        if (
            preimage.memory_plane_write_revision != memory_plane_write_revision
            or preimage.graph_revision != request.expected_graph_revision
            or preimage.observation_revision != request.expected_observation_revision
            or preimage.authorization_decision_digest != decision.decision_digest
            or preimage.authorized_scope_identity != decision.authorized_scope_identity
            or preimage.authorization_policy_revision != decision.policy_revision
        ):
            raise GraphObservationPagingError("ingestion cohort input coordinates are substituted")
        order = tuple(_attestation_order_key(item) for item in cohort_input.stream)
        if len(cohort_input.stream) > self._retention_budget.maximum_stream_records:
            raise ObservationSnapshotCapacityError("ingestion cohort stream exceeds protected capacity")
        if order != tuple(sorted(set(order))):
            raise GraphObservationPagingError("ingestion cohort stream order is invalid")
        cohort = self._emit_cohort(preimage)
        snapshot = IngestionTimeObservationSnapshot(
            schema_version=1, snapshot_token=token, created_at=created_at,
            memory_plane_write_revision=cohort.memory_plane_write_revision,
            authenticated_context_digest=context.context_digest, purpose="ingestion_time_attestation",
            authorization_decision=decision, request=request, cohort_preimage=preimage,
            resolved_cohort=cohort, stream=cohort_input.stream,
        )
        artifact = self._artifact(snapshot, "IngestionTimeObservationSnapshot")
        snapshot = self._exact(artifact, IngestionTimeObservationSnapshot)
        retained = _RetainedIngestionSnapshot(snapshot, _retention_deadline(created_at, decision, policy))
        self._retain_token(token, context.tenant_partition_id, len(artifact.raw), retained, ingestion=True, now=_utc(self._clock.now(), "protected observation clock"))
        return retained

    def _graph_page(self, snapshot: GraphRecordObservationSnapshot, start: int, policy: GraphObservationPagePolicySnapshot, context: AuthenticatedGraphObservationContext, decision: GraphObservationAuthorizationDecision, now: datetime) -> GraphObservationResponse:
        end = min(start + snapshot.request.total_page_size, len(snapshot.stream))
        next_cursor = self._next_cursor(snapshot, start, end, policy, context, decision) if end < len(snapshot.stream) else None
        page = GraphObservationPage(
            kind="page", graph_revision=snapshot.resolved_cohort.graph_revision,
            observation_revision=snapshot.resolved_cohort.observation_revision, snapshot_token=snapshot.snapshot_token,
            memory_plane_write_revision=snapshot.memory_plane_write_revision, cohort=snapshot.resolved_cohort,
            page_policy_revision=policy.policy_revision, page_policy_digest=policy.policy_digest,
            view=snapshot.request.view, valid_at=snapshot.request.valid_at, system_as_of=snapshot.request.system_as_of,
            total_page_size=snapshot.request.total_page_size, stream_start_position=start,
            stream_end_position=end, records=snapshot.stream[start:end],
            observation_schema_fingerprint=snapshot.resolved_cohort.observation_schema_fingerprint,
            next_cursor=next_cursor, page_digest="0" * 64,
        )
        emitted = self._emit(page, "GraphObservationPage")
        if type(emitted) is not GraphObservationPage:
            raise GraphObservationPagingError("registered graph page is substituted")
        failure = self._page_fence(snapshot.snapshot_token, snapshot.memory_plane_write_revision, decision, start, _retention_deadline(snapshot.created_at, decision, policy))
        if failure is not None:
            return self._failure(failure)
        if next_cursor is None:
            self._release_token(snapshot.snapshot_token)
        return emitted

    def _ingestion_page(self, snapshot: IngestionTimeObservationSnapshot, start: int,
                        policy: GraphObservationPagePolicySnapshot,
                        context: AuthenticatedGraphObservationContext,
                        decision: GraphObservationAuthorizationDecision) -> IngestionTimeAttestationResponse:
        end = min(start + snapshot.request.total_page_size, len(snapshot.stream))
        next_cursor = self._next_ingestion_cursor(snapshot, end, policy, context, decision) if end < len(snapshot.stream) else None
        page = IngestionTimeAttestationPage(
            kind="page", graph_revision=snapshot.resolved_cohort.graph_revision,
            observation_revision=snapshot.resolved_cohort.observation_revision,
            snapshot_token=snapshot.snapshot_token, memory_plane_write_revision=snapshot.memory_plane_write_revision,
            cohort=snapshot.resolved_cohort, page_policy_revision=policy.policy_revision,
            page_policy_digest=policy.policy_digest, total_page_size=snapshot.request.total_page_size,
            stream_start_position=start, stream_end_position=end, attestations=snapshot.stream[start:end],
            next_cursor=next_cursor, page_digest="0" * 64,
        )
        emitted = self._emit(page, "IngestionTimeAttestationPage")
        if type(emitted) is not IngestionTimeAttestationPage:
            raise GraphObservationPagingError("registered ingestion-time page is substituted")
        failure = self._page_fence(snapshot.snapshot_token, snapshot.memory_plane_write_revision, decision, start, _retention_deadline(snapshot.created_at, decision, policy))
        if failure is not None:
            return self._failure(failure)
        if next_cursor is None:
            self._release_token(snapshot.snapshot_token)
        return emitted

    def _page_fence(self, token: str, write_revision: int, decision: GraphObservationAuthorizationDecision, start: int, retention_deadline: datetime) -> GraphObservationFailureReason | None:
        now = _utc(self._clock.now(), "protected observation clock")
        if decision.expires_at <= now:
            self._release_token(token)
            return "denied" if start == 0 else "revoked_access"
        if retention_deadline <= now:
            self._release_token(token)
            return "denied" if start == 0 else "stale_cursor"
        current_revision, _ = self._memory_plane.read_write_snapshot()
        if current_revision != write_revision:
            self._release_token(token)
            return "denied" if start == 0 else "stale_cursor"
        return None

    def _next_cursor(self, snapshot: GraphRecordObservationSnapshot, start: int, end: int, policy: GraphObservationPagePolicySnapshot, context: AuthenticatedGraphObservationContext, decision: GraphObservationAuthorizationDecision) -> str:
        if end <= start:
            raise GraphObservationPagingError("nonempty continuation has no predecessor")
        predecessor = snapshot.stream[end - 1]
        kind, key, digest = predecessor.record_kind, predecessor.primary_key, predecessor.record_digest
        view, valid_at, system_as_of = snapshot.request.view, snapshot.request.valid_at, snapshot.request.system_as_of
        payload = GraphObservationCursorPayload(
            schema_version=1, stream_position=end, preceding_record_kind=kind,
            preceding_primary_key=key, preceding_record_digest=digest,
            requested_total_page_size=snapshot.request.total_page_size,
            page_policy_revision=policy.policy_revision, page_policy_digest=policy.policy_digest,
            caller_context_digest=context.context_digest, authorization_decision_digest=decision.decision_digest,
            authorization_expires_at=decision.expires_at, cohort_digest=snapshot.resolved_cohort.cohort_digest,
            snapshot_token=snapshot.snapshot_token, snapshot_write_revision=snapshot.memory_plane_write_revision,
            graph_revision=snapshot.resolved_cohort.graph_revision,
            observation_revision=snapshot.resolved_cohort.observation_revision,
            view=view, valid_at=valid_at, system_as_of=system_as_of, signature="0" * 128,
        )
        return issue_registered_observation_cursor(
            payload, history=self._history, publication=self._publication, signing_key=self._signing_key,
            verification_key=self._verification_key, limits=self._limits,
        )

    def _next_ingestion_cursor(self, snapshot: IngestionTimeObservationSnapshot, end: int,
                               policy: GraphObservationPagePolicySnapshot,
                               context: AuthenticatedGraphObservationContext,
                               decision: GraphObservationAuthorizationDecision) -> str:
        if end <= 0:
            raise GraphObservationPagingError("nonempty ingestion continuation has no predecessor")
        predecessor = snapshot.stream[end - 1]
        payload = IngestionTimeAttestationCursorPayload(
            schema_version=1, stream_position=end, preceding_attestation_kind=predecessor.kind,
            preceding_attestation_id=predecessor.attestation_id,
            preceding_attestation_digest=predecessor.attestation_digest, request=snapshot.request,
            page_policy_revision=policy.policy_revision, page_policy_digest=policy.policy_digest,
            caller_context_digest=context.context_digest, authorization_decision_digest=decision.decision_digest,
            authorization_expires_at=decision.expires_at, cohort_digest=snapshot.resolved_cohort.cohort_digest,
            snapshot_token=snapshot.snapshot_token, snapshot_write_revision=snapshot.memory_plane_write_revision,
            signature="0" * 128,
        )
        return issue_registered_ingestion_time_attestation_cursor(
            payload, history=self._history, publication=self._publication, signing_key=self._signing_key,
            verification_key=self._verification_key, limits=self._limits,
        )

    def _decode_cursor(self, value: str) -> GraphObservationCursorPayload | None:
        try:
            return decode_registered_observation_cursor(
                value, history=self._history, publication=self._publication,
                verification_key=self._verification_key, limits=self._limits,
            )
        except (ObservationActivationRuntimeError, ValueError):
            return None

    def _decode_ingestion_cursor(self, value: str) -> IngestionTimeAttestationCursorPayload | None:
        try:
            return decode_registered_ingestion_time_attestation_cursor(
                value, history=self._history, publication=self._publication,
                verification_key=self._verification_key, limits=self._limits,
            )
        except (ObservationActivationRuntimeError, ValueError):
            return None

    def _load_graph_continuation(self, *, cursor: GraphObservationCursorPayload, context: AuthenticatedGraphObservationContext, decision: GraphObservationAuthorizationDecision, policy: GraphObservationPagePolicySnapshot, request: GraphObservationRequestCoordinates, now: datetime) -> _RetainedGraphSnapshot | GraphObservationFailureReason:
        with self._retention_lock:
            self._purge(now)
            retained = self._graph_snapshots.get(cursor.snapshot_token)
        if retained is None:
            return "stale_cursor"
        write_revision, _records = self._memory_plane.read_write_snapshot()
        if write_revision != retained.snapshot.memory_plane_write_revision or retained.expires_at <= now:
            self._release_token(cursor.snapshot_token)
            return "stale_cursor"
        if not _cursor_matches(cursor, context, decision, policy, request, now) or not _cursor_snapshot_matches(cursor, retained.snapshot, request, context, decision):
            return "invalid_cursor"
        return retained

    def _load_ingestion_continuation(self, *, cursor: IngestionTimeAttestationCursorPayload,
                                     context: AuthenticatedGraphObservationContext,
                                     decision: GraphObservationAuthorizationDecision,
                                     request: IngestionTimeAttestationRequestCoordinates,
                                     now: datetime) -> _RetainedIngestionSnapshot | GraphObservationFailureReason:
        with self._retention_lock:
            self._purge(now)
            retained = self._ingestion_snapshots.get(cursor.snapshot_token)
        if retained is None:
            return "stale_cursor"
        write_revision, _records = self._memory_plane.read_write_snapshot()
        if write_revision != retained.snapshot.memory_plane_write_revision or retained.expires_at <= now:
            self._release_token(cursor.snapshot_token)
            return "stale_cursor"
        if not _ingestion_cursor_matches(cursor, context, decision, request, now) or not _ingestion_snapshot_matches(cursor, retained.snapshot, request, context, decision):
            return "invalid_cursor"
        return retained

    def _emit_cohort(self, preimage: GraphObservationCohortPreimage) -> ResolvedGraphObservationCohort:
        candidate = ResolvedGraphObservationCohort(**preimage.model_dump(mode="python"), cohort_digest="0" * 64)
        emitted = self._emit(candidate, "ResolvedGraphObservationCohort")
        if type(emitted) is not ResolvedGraphObservationCohort:
            raise GraphObservationPagingError("registered observation cohort is substituted")
        return emitted

    def _registered_exact(self, value: _RegisteredModel, schema_id: str) -> _RegisteredModel:
        emitted = self._emit(value, schema_id)
        if type(emitted) is not type(value) or emitted != value:
            raise GraphObservationPagingError("registered observation authority is substituted")
        return value

    def _emit(self, value: BaseModel, schema_id: str) -> BaseModel:
        return self._artifact(value, schema_id).value

    def _artifact(self, value: BaseModel, schema_id: str) -> RegisteredObservationArtifact:
        limits = self._limits
        if isinstance(value, (GraphRecordObservationSnapshot, IngestionTimeObservationSnapshot)):
            ceiling = self._retention_budget.maximum_snapshot_bytes
            limits = replace(
                limits, maximum_envelope_bytes=min(limits.maximum_envelope_bytes, ceiling),
                body_limits=replace(limits.body_limits, maximum_bytes=min(limits.body_limits.maximum_bytes, ceiling)),
            )
        return emit_registered_observation_artifact(
            value, schema_id=schema_id, history=self._history, publication=self._publication, limits=limits
        )

    @staticmethod
    def _exact(artifact: RegisteredObservationArtifact, expected: type[_RegisteredModel]) -> _RegisteredModel:
        if type(artifact.value) is not expected:
            raise GraphObservationPagingError("registered observation artifact is substituted")
        return artifact.value

    def _reserve_token(self, context: AuthenticatedGraphObservationContext, now: datetime) -> str | None:
        token = _new_token()
        with self._retention_lock:
            self._purge(now)
            tenant = context.tenant_partition_id
            count = len(self._graph_snapshots) + len(self._ingestion_snapshots) + len(self._reservations)
            total_bytes = sum(self._retained_bytes.values()) + len(self._reservations) * self._retention_budget.maximum_snapshot_bytes
            tenant_reservations = sum(value == tenant for value in self._reservations.values())
            tenant_tokens = [key for key, value in self._retained_tenants.items() if value == tenant]
            tenant_bytes = sum(self._retained_bytes[key] for key in tenant_tokens) + tenant_reservations * self._retention_budget.maximum_snapshot_bytes
            if (count >= self._retention_budget.maximum_retained_snapshots
                    or total_bytes + self._retention_budget.maximum_snapshot_bytes > self._retention_budget.maximum_retained_bytes
                    or len(tenant_tokens) + tenant_reservations >= self._retention_budget.maximum_tenant_snapshots
                    or tenant_bytes + self._retention_budget.maximum_snapshot_bytes > self._retention_budget.maximum_tenant_bytes):
                return None
            self._reservations[token] = tenant
        return token

    def _retain_token(self, token: str, tenant: str, byte_charge: int,
                      retained: _RetainedGraphSnapshot | _RetainedIngestionSnapshot,
                      *, ingestion: bool, now: datetime) -> None:
        if retained.expires_at <= now:
            raise ObservationCohortUnavailableError("snapshot expired during construction")
        if byte_charge > self._retention_budget.maximum_snapshot_bytes:
            raise ObservationSnapshotCapacityError("observation snapshot exceeds protected byte capacity")
        with self._retention_lock:
            self._purge(now)
            if self._reservations.get(token) != tenant:
                raise GraphObservationPagingError("observation snapshot reservation is unavailable")
            count = len(self._graph_snapshots) + len(self._ingestion_snapshots) + len(self._reservations) - 1
            total_bytes = sum(self._retained_bytes.values()) + (len(self._reservations) - 1) * self._retention_budget.maximum_snapshot_bytes
            tenant_tokens = [key for key, value in self._retained_tenants.items() if value == tenant]
            tenant_reservations = sum(value == tenant for value in self._reservations.values()) - 1
            tenant_bytes = sum(self._retained_bytes[key] for key in tenant_tokens) + tenant_reservations * self._retention_budget.maximum_snapshot_bytes
            if (count >= self._retention_budget.maximum_retained_snapshots
                    or total_bytes + byte_charge > self._retention_budget.maximum_retained_bytes
                    or len(tenant_tokens) + tenant_reservations >= self._retention_budget.maximum_tenant_snapshots
                    or tenant_bytes + byte_charge > self._retention_budget.maximum_tenant_bytes):
                raise ObservationSnapshotCapacityError("observation retained capacity is exhausted")
            if ingestion and isinstance(retained, _RetainedIngestionSnapshot):
                self._ingestion_snapshots[token] = retained
            elif not ingestion and isinstance(retained, _RetainedGraphSnapshot):
                self._graph_snapshots[token] = retained
            else:
                raise GraphObservationPagingError("retained snapshot purpose is invalid")
            self._retained_tenants[token] = tenant
            self._retained_bytes[token] = byte_charge
            self._reservations.pop(token)

    def _release_cursor_snapshot(
        self, cursor: GraphObservationCursorPayload | IngestionTimeAttestationCursorPayload,
        context: AuthenticatedGraphObservationContext,
    ) -> None:
        # A valid cursor is not authority to evict another caller's retained state.
        if cursor.caller_context_digest != context.context_digest:
            return
        with self._retention_lock:
            retained = self._graph_snapshots.get(cursor.snapshot_token) or self._ingestion_snapshots.get(cursor.snapshot_token)
            if retained is not None and retained.snapshot.authenticated_context_digest == context.context_digest:
                self._release_token(cursor.snapshot_token)

    def _release_token(self, token: str) -> None:
        with self._retention_lock:
            self._reservations.pop(token, None)
            self._graph_snapshots.pop(token, None)
            self._ingestion_snapshots.pop(token, None)
            self._retained_tenants.pop(token, None)
            self._retained_bytes.pop(token, None)

    def _purge(self, now: datetime) -> None:
        expired = {
            token for token, item in self._graph_snapshots.items() if item.expires_at <= now
        } | {
            token for token, item in self._ingestion_snapshots.items() if item.expires_at <= now
        }
        for token in expired:
            self._graph_snapshots.pop(token, None)
            self._ingestion_snapshots.pop(token, None)
            self._retained_tenants.pop(token, None)
            self._retained_bytes.pop(token, None)

    def _failure(self, reason: GraphObservationFailureReason) -> GraphObservationFailure:
        return GraphObservationFailure(reason=reason, request_correlation_token=self._correlation_token_factory())


def _utc(value: datetime, label: str) -> datetime:
    offset = value.utcoffset()
    if value.tzinfo is None or offset is None or offset.total_seconds() != 0:
        raise GraphObservationPagingError(f"{label} must return timezone-aware UTC")
    return value.astimezone(UTC)


def _new_token() -> str:
    return token_urlsafe(32)


def _retention_deadline(created_at: datetime, decision: GraphObservationAuthorizationDecision, policy: GraphObservationPagePolicySnapshot) -> datetime:
    return min(decision.expires_at, created_at + policy.snapshot_maximum_age)


def _cursor_matches(cursor: GraphObservationCursorPayload, context: AuthenticatedGraphObservationContext, decision: GraphObservationAuthorizationDecision, policy: GraphObservationPagePolicySnapshot, request: GraphObservationRequestCoordinates, now: datetime) -> bool:
    return (
        cursor.authorization_expires_at > now and cursor.caller_context_digest == context.context_digest
        and cursor.authorization_decision_digest == decision.decision_digest
        and cursor.page_policy_revision == policy.policy_revision and cursor.page_policy_digest == policy.policy_digest
        and cursor.requested_total_page_size == request.total_page_size
        and cursor.graph_revision == request.expected_graph_revision
        and cursor.observation_revision == request.expected_observation_revision
        and cursor.view == request.view and cursor.valid_at == request.valid_at
        and cursor.system_as_of == request.system_as_of
    )


def _cursor_snapshot_matches(
    cursor: GraphObservationCursorPayload,
    snapshot: GraphRecordObservationSnapshot,
    request: GraphObservationRequestCoordinates,
    context: AuthenticatedGraphObservationContext,
    decision: GraphObservationAuthorizationDecision,
) -> bool:
    if (
        cursor.stream_position <= 0
        or cursor.stream_position >= len(snapshot.stream)
        or cursor.cohort_digest != snapshot.resolved_cohort.cohort_digest
        or cursor.snapshot_write_revision != snapshot.memory_plane_write_revision
        or snapshot.request != request
        or snapshot.authenticated_context_digest != context.context_digest
        or snapshot.authorization_decision != decision
        or cursor.authorization_expires_at != decision.expires_at
    ):
        return False
    preceding = snapshot.stream[cursor.stream_position - 1]
    key = (preceding.record_kind, preceding.primary_key, preceding.record_digest)
    return key == (cursor.preceding_record_kind, cursor.preceding_primary_key, cursor.preceding_record_digest)


def _ingestion_cursor_matches(
    cursor: IngestionTimeAttestationCursorPayload,
    context: AuthenticatedGraphObservationContext,
    decision: GraphObservationAuthorizationDecision,
    request: IngestionTimeAttestationRequestCoordinates,
    now: datetime,
) -> bool:
    return (
        cursor.authorization_expires_at > now
        and cursor.caller_context_digest == context.context_digest
        and cursor.authorization_decision_digest == decision.decision_digest
        and cursor.request == request
    )


def _ingestion_snapshot_matches(
    cursor: IngestionTimeAttestationCursorPayload,
    snapshot: IngestionTimeObservationSnapshot,
    request: IngestionTimeAttestationRequestCoordinates,
    context: AuthenticatedGraphObservationContext,
    decision: GraphObservationAuthorizationDecision,
) -> bool:
    if (
        cursor.stream_position <= 0
        or cursor.stream_position >= len(snapshot.stream)
        or cursor.cohort_digest != snapshot.resolved_cohort.cohort_digest
        or cursor.snapshot_write_revision != snapshot.memory_plane_write_revision
        or snapshot.request != request
        or snapshot.authenticated_context_digest != context.context_digest
        or snapshot.authorization_decision != decision
        or cursor.authorization_expires_at != decision.expires_at
    ):
        return False
    predecessor = snapshot.stream[cursor.stream_position - 1]
    return (
        predecessor.kind,
        predecessor.attestation_id,
        predecessor.attestation_digest,
    ) == (
        cursor.preceding_attestation_kind,
        cursor.preceding_attestation_id,
        cursor.preceding_attestation_digest,
    )


__all__ = [
    "AuthenticatedGraphObservationPagingRuntime", "DetachedGraphObservationCohortProvider",
    "DetachedGraphObservationRecords", "GraphObservationCohortInput",
    "IngestionTimeObservationCohortInput", "GraphObservationContextResolver",
    "GrantBackedGraphObservationAuthorizer", "VerifiedGraphObservationAuthorization",
    "GraphObservationPagingError", "ObservationRetentionBudget", "ProtectedObservationClock",
]
