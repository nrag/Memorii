"""Registered observation identity and current host-grant adaptation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, TypeVar

from pydantic import BaseModel

from memorii.core.memory_evolution.graph_observation_contracts import (
    GraphObservationCohortSelector,
    GraphObservationPurpose,
    authorized_scope_identity,
)
from memorii.core.memory_evolution.graph_observation_paging import VerifiedGraphObservationAuthorization
from memorii.core.memory_evolution.graph_observation_public_contracts import (
    AuthenticatedGraphObservationContext,
    GraphObservationAuthorizationDecision,
    GraphObservationPagePolicySnapshot,
)
from memorii.core.memory_evolution.ingestion_contracts import AuthenticatedHostIngress, RequiredOutcomeScopeSet
from memorii.core.memory_evolution.models import MemoryScope
from memorii.core.memory_evolution.observation_activation_runtime import emit_registered_observation_artifact
from memorii.core.memory_evolution.typed_value_artifact_reader import ProtectedTypedValueArtifactReaderLimits
from memorii.core.memory_evolution.typed_value_publication import VerifiedTypedValuePublication
from memorii.core.memory_evolution.typed_value_registry_history import ProtectedTypedValueRegistryHistory


@dataclass(frozen=True)
class ProtectedObservationSession:
    principal_subject_id: str
    authentication_session_id: str
    authorized_scopes: RequiredOutcomeScopeSet
    issued_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class ProtectedObservationGrant:
    """A current grant supplied by the host's policy authority for this query."""

    context: AuthenticatedGraphObservationContext
    session: ProtectedObservationSession
    purpose: GraphObservationPurpose
    scope_constraint: MemoryScope
    cohort_selector: GraphObservationCohortSelector
    authorized_scope: MemoryScope
    authorized_scope_identity: str
    authorization_policy_revision: str
    page_policy: GraphObservationPagePolicySnapshot
    issued_at: datetime
    expires_at: datetime


class CurrentObservationGrantProvider(Protocol):
    def resolve(
        self, *, context: AuthenticatedGraphObservationContext,
        purpose: GraphObservationPurpose, scope_constraint: MemoryScope,
        cohort_selector: GraphObservationCohortSelector, server_time: datetime,
    ) -> ProtectedObservationGrant | None: ...


_Model = TypeVar("_Model", bound=BaseModel)


class RegisteredGraphObservationAccess:
    """Adapt authenticated host sessions and exact current grants to wire roots.

    No identity is inferred from request fields or from the opaque handle's
    string representation. The host must resolve it and check current policy.
    """

    def __init__(
        self, *,
        session_provider: Callable[[AuthenticatedHostIngress, datetime], ProtectedObservationSession | None],
        grant_provider: CurrentObservationGrantProvider,
        registry_history: ProtectedTypedValueRegistryHistory,
        registry_publication: VerifiedTypedValuePublication,
        reader_limits: ProtectedTypedValueArtifactReaderLimits,
    ) -> None:
        self._sessions = session_provider
        self._grants = grant_provider
        self._history = registry_history
        self._publication = registry_publication
        self._limits = reader_limits

    def resolve(self, *, host_ingress: object, server_time: datetime) -> AuthenticatedGraphObservationContext | None:
        if not isinstance(host_ingress, AuthenticatedHostIngress):
            return None
        session = self._sessions(host_ingress, server_time)
        if session is None or not _current(session.issued_at, session.expires_at, server_time):
            return None
        return self._context(session)

    def _context(self, session: ProtectedObservationSession) -> AuthenticatedGraphObservationContext:
        return self._emit(AuthenticatedGraphObservationContext(
            principal_subject_id=session.principal_subject_id,
            tenant_partition_id=session.authorized_scopes.tenant_partition_id,
            authorized_scope_set_digest=session.authorized_scopes.required_scope_set_digest,
            authentication_session_id=session.authentication_session_id,
            context_digest="0" * 64,
        ))

    def authorize(
        self, *, context: AuthenticatedGraphObservationContext,
        purpose: GraphObservationPurpose, scope_constraint: MemoryScope,
        cohort_selector: GraphObservationCohortSelector, server_time: datetime,
    ) -> VerifiedGraphObservationAuthorization | None:
        grant = self._grants.resolve(
            context=context, purpose=purpose, scope_constraint=scope_constraint,
            cohort_selector=cohort_selector, server_time=server_time,
        )
        if grant is None or (
            grant.context != context or grant.purpose != purpose
            or grant.scope_constraint != scope_constraint or grant.cohort_selector != cohort_selector
            or not grant.authorized_scope.can_read(scope_constraint)
            or grant.authorized_scope_identity != authorized_scope_identity(grant.authorized_scope)
            or not _current(grant.issued_at, grant.expires_at, server_time)
            or not _current(grant.session.issued_at, grant.session.expires_at, server_time)
            or grant.expires_at > grant.session.expires_at
            or self._context(grant.session) != context
        ):
            return None
        policy = self._emit(grant.page_policy)
        if policy != grant.page_policy:
            return None
        decision = self._emit(GraphObservationAuthorizationDecision(
            kind="authorized", authorized_scope_identity=grant.authorized_scope_identity,
            policy_revision=grant.authorization_policy_revision,
            page_policy_revision=policy.policy_revision, page_policy_digest=policy.policy_digest,
            expires_at=grant.expires_at, decision_digest="0" * 64,
        ))
        return VerifiedGraphObservationAuthorization(decision, policy, grant.authorized_scope)

    def _emit(self, value: _Model) -> _Model:
        emitted = emit_registered_observation_artifact(
            value, schema_id=type(value).__name__, history=self._history,
            publication=self._publication, limits=self._limits,
        ).value
        if not isinstance(emitted, type(value)):
            raise ValueError("registered observation access schema differs")
        return emitted


def _current(issued_at: datetime, expires_at: datetime, now: datetime) -> bool:
    return all(value.tzinfo is not None and value.utcoffset() == UTC.utcoffset(value)
               for value in (issued_at, expires_at, now)) and issued_at <= now < expires_at
