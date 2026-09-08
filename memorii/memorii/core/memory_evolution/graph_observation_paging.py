"""Authenticated, snapshot-contiguous paging for registered profile-3 observations.

This module deliberately owns no graph projection.  A host composes a cohort
provider which derives a complete stream from the one detached memory-plane
snapshot passed to it.  The owner here enforces the public read order,
authorization, retention, cursor continuity, and registered artifact boundary.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from secrets import token_urlsafe
from threading import RLock
from typing import Protocol, TypeVar

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import BaseModel

from memorii.core.memory_evolution.graph_ingestion_time_contracts import ProductionIngestionTimeAttestation
from memorii.core.memory_evolution.graph_observation_contracts import (
    GraphObservationFailure,
    GraphObservationFailureReason,
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
    IngestionTimeAttestationRequestCoordinates,
)
from memorii.core.memory_evolution.graph_observation_snapshot_contracts import (
    GraphObservationCohortPreimage,
    GraphObservationCursorPayload,
    ResolvedGraphObservationCohort,
)
from memorii.core.memory_evolution.graph_observation_streams import GraphObservationStreamRecord
from memorii.core.memory_evolution.observation_activation_runtime import (
    ObservationActivationRuntimeError,
    decode_registered_observation_cursor,
    emit_registered_observation_artifact,
    issue_registered_observation_cursor,
)
from memorii.core.memory_evolution.typed_value_artifact_integrity import TrustedTypedValueArtifactVerificationKey
from memorii.core.memory_evolution.typed_value_artifact_reader import ProtectedTypedValueArtifactReaderLimits
from memorii.core.memory_evolution.typed_value_publication import VerifiedTypedValuePublication
from memorii.core.memory_evolution.typed_value_registry_history import ProtectedTypedValueRegistryHistory
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService

_RegisteredModel = TypeVar("_RegisteredModel", bound=BaseModel)


class GraphObservationPagingError(ValueError):
    """Raised for a malformed trusted collaborator result or unavailable schema."""


class ProtectedObservationClock(Protocol):
    def now(self) -> datetime: ...


class GraphObservationContextResolver(Protocol):
    def resolve(self, *, host_ingress: object, server_time: datetime) -> AuthenticatedGraphObservationContext: ...


class GraphObservationCurrentPolicyProvider(Protocol):
    def current_policy(
        self, *, context: AuthenticatedGraphObservationContext, server_time: datetime
    ) -> GraphObservationPagePolicySnapshot: ...


class GrantBackedGraphObservationAuthorizer(Protocol):
    def authorize(
        self,
        *,
        context: AuthenticatedGraphObservationContext,
        scope_constraint: object,
        page_policy: GraphObservationPagePolicySnapshot,
        server_time: datetime,
    ) -> GraphObservationAuthorizationDecision | None: ...


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
        request: GraphObservationRequestCoordinates,
    ) -> GraphObservationCohortInput: ...

    def ingestion_time_input(
        self,
        *,
        snapshot: DetachedGraphObservationRecords,
        context: AuthenticatedGraphObservationContext,
        decision: GraphObservationAuthorizationDecision,
        request: IngestionTimeAttestationRequestCoordinates,
    ) -> IngestionTimeObservationCohortInput: ...


@dataclass(frozen=True)
class _RetainedGraphSnapshot:
    snapshot: GraphRecordObservationSnapshot
    expires_at: datetime


class AuthenticatedGraphObservationPagingRuntime:
    """Canonical owner for profile-3 observation page issuance and continuation."""

    def __init__(
        self,
        *,
        memory_plane: MemoryPlaneService,
        context_resolver: GraphObservationContextResolver,
        current_policy_provider: GraphObservationCurrentPolicyProvider,
        authorizer: GrantBackedGraphObservationAuthorizer,
        cohort_provider: DetachedGraphObservationCohortProvider,
        protected_clock: ProtectedObservationClock,
        registry_history: ProtectedTypedValueRegistryHistory,
        registry_publication: VerifiedTypedValuePublication,
        cursor_signing_key: Ed25519PrivateKey,
        cursor_verification_key: TrustedTypedValueArtifactVerificationKey,
        reader_limits: ProtectedTypedValueArtifactReaderLimits,
        correlation_token_factory: Callable[[], str],
    ) -> None:
        self._memory_plane = memory_plane
        self._context_resolver = context_resolver
        self._current_policy_provider = current_policy_provider
        self._authorizer = authorizer
        self._cohort_provider = cohort_provider
        self._clock = protected_clock
        self._history = registry_history
        self._publication = registry_publication
        self._signing_key = cursor_signing_key
        self._verification_key = cursor_verification_key
        self._limits = reader_limits
        self._correlation_token_factory = correlation_token_factory
        self._retention_lock = RLock()
        self._graph_snapshots: dict[str, _RetainedGraphSnapshot] = {}

    def observe_graph(
        self, *, host_ingress: object, request: GraphObservationRequest
    ) -> GraphObservationResponse:
        """Return one graph-record page after trusted reauthorization."""
        context, policy, decision, now = self._authorize(
            host_ingress=host_ingress, scope_constraint=request.scope_constraint
        )
        if decision is None:
            return self._failure("denied")
        if request.total_page_size < policy.minimum_total_page_size or request.total_page_size > policy.maximum_total_page_size:
            return self._failure("denied")
        coordinates = GraphObservationRequestCoordinates(**request.model_dump(exclude={"cursor"}))
        if request.cursor is None:
            write_revision, records = self._memory_plane.read_write_snapshot()
            cohort_input = self._cohort_provider.graph_observation_input(
                snapshot=DetachedGraphObservationRecords(write_revision, records), context=context,
                decision=decision, request=coordinates,
            )
            retained = self._retain_graph_snapshot(
                context=context, decision=decision, policy=policy, request=coordinates,
                cohort_input=cohort_input, memory_plane_write_revision=write_revision, created_at=now,
            )
            return self._graph_page(
                retained.snapshot, start=0, policy=policy, context=context, decision=decision, now=now
            )
        cursor = self._decode_cursor(request.cursor)
        if cursor is None:
            return self._failure("invalid_cursor")
        retained = self._load_graph_continuation(
            cursor=cursor, context=context, decision=decision, policy=policy, request=coordinates, now=now
        )
        if retained is None:
            return self._failure("stale_cursor")
        return self._graph_page(
            retained.snapshot, start=cursor.stream_position, policy=policy, context=context,
            decision=decision, now=now,
        )

    def _authorize(self, *, host_ingress: object, scope_constraint: object) -> tuple[AuthenticatedGraphObservationContext, GraphObservationPagePolicySnapshot, GraphObservationAuthorizationDecision | None, datetime]:
        now = _utc(self._clock.now(), "protected observation clock")
        context = self._context_resolver.resolve(host_ingress=host_ingress, server_time=now)
        context = self._registered_exact(context, "AuthenticatedGraphObservationContext")
        policy = self._current_policy_provider.current_policy(context=context, server_time=now)
        policy = self._registered_exact(policy, "GraphObservationPagePolicySnapshot")
        decision = self._authorizer.authorize(
            context=context, scope_constraint=scope_constraint, page_policy=policy, server_time=now
        )
        if decision is not None:
            decision = self._registered_exact(decision, "GraphObservationAuthorizationDecision")
            if (
                decision.page_policy_revision != policy.policy_revision
                or decision.page_policy_digest != policy.policy_digest
            ):
                raise GraphObservationPagingError("authorization decision page policy is substituted")
        if decision is not None and decision.expires_at <= now:
            return context, policy, None, now
        return context, policy, decision, now

    def _retain_graph_snapshot(self, *, context: AuthenticatedGraphObservationContext, decision: GraphObservationAuthorizationDecision, policy: GraphObservationPagePolicySnapshot, request: GraphObservationRequestCoordinates, cohort_input: GraphObservationCohortInput, memory_plane_write_revision: int, created_at: datetime) -> _RetainedGraphSnapshot:
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
        cohort = self._emit_cohort(cohort_input.cohort_preimage)
        token = _new_token()
        snapshot = GraphRecordObservationSnapshot(
            schema_version=1, snapshot_token=token, created_at=created_at,
            memory_plane_write_revision=cohort.memory_plane_write_revision,
            authenticated_context_digest=context.context_digest, purpose="graph_observation",
            authorization_decision=decision, request=request, cohort_preimage=cohort_input.cohort_preimage,
            resolved_cohort=cohort, stream=cohort_input.stream,
        )
        snapshot = self._emit(snapshot, "GraphRecordObservationSnapshot")
        if type(snapshot) is not GraphRecordObservationSnapshot:
            raise GraphObservationPagingError("registered graph snapshot is substituted")
        retained = _RetainedGraphSnapshot(snapshot, _retention_deadline(created_at, decision, policy))
        with self._retention_lock:
            self._purge(created_at)
            self._graph_snapshots[token] = retained
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
        return emitted

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

    def _decode_cursor(self, value: str) -> GraphObservationCursorPayload | None:
        try:
            return decode_registered_observation_cursor(
                value, history=self._history, publication=self._publication,
                verification_key=self._verification_key, limits=self._limits,
            )
        except (ObservationActivationRuntimeError, ValueError):
            return None

    def _load_graph_continuation(self, *, cursor: GraphObservationCursorPayload, context: AuthenticatedGraphObservationContext, decision: GraphObservationAuthorizationDecision, policy: GraphObservationPagePolicySnapshot, request: GraphObservationRequestCoordinates, now: datetime) -> _RetainedGraphSnapshot | None:
        if not _cursor_matches(cursor, context, decision, policy, request, now):
            return None
        with self._retention_lock:
            self._purge(now)
            retained = self._graph_snapshots.get(cursor.snapshot_token)
        if retained is None or not _cursor_snapshot_matches(
            cursor, retained.snapshot, request, context, decision
        ):
            return None
        write_revision, _records = self._memory_plane.read_write_snapshot()
        if write_revision != cursor.snapshot_write_revision or retained.expires_at <= now:
            return None
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
        return emit_registered_observation_artifact(
            value, schema_id=schema_id, history=self._history, publication=self._publication, limits=self._limits
        ).value

    def _purge(self, now: datetime) -> None:
        self._graph_snapshots = {token: item for token, item in self._graph_snapshots.items() if item.expires_at > now}

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
        cursor.stream_position > len(snapshot.stream)
        or cursor.cohort_digest != snapshot.resolved_cohort.cohort_digest
        or cursor.snapshot_write_revision != snapshot.memory_plane_write_revision
        or snapshot.request != request
        or snapshot.authenticated_context_digest != context.context_digest
        or snapshot.authorization_decision != decision
        or cursor.authorization_expires_at != decision.expires_at
    ):
        return False
    if cursor.stream_position == 0:
        return True
    preceding = snapshot.stream[cursor.stream_position - 1]
    key = (preceding.record_kind, preceding.primary_key, preceding.record_digest)
    return key == (cursor.preceding_record_kind, cursor.preceding_primary_key, cursor.preceding_record_digest)


__all__ = [
    "AuthenticatedGraphObservationPagingRuntime", "DetachedGraphObservationCohortProvider",
    "DetachedGraphObservationRecords", "GraphObservationCohortInput",
    "IngestionTimeObservationCohortInput", "GraphObservationContextResolver",
    "GraphObservationCurrentPolicyProvider", "GrantBackedGraphObservationAuthorizer",
    "GraphObservationPagingError", "ProtectedObservationClock",
]
