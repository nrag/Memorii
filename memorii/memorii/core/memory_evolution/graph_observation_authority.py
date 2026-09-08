"""Protected context, policy, and grant-backed observation authorization."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_evolution.graph_observation_contracts import (
    AuthenticatedGraphObservationContext,
    GraphObservationAuthorizationDecision,
    GraphObservationAuthorizationDecisionPreimage,
    GraphObservationCohortSelector,
    GraphObservationFailure,
    GraphObservationPagePolicySnapshot,
    GraphObservationPurpose,
)
from memorii.core.memory_evolution.ingestion_contracts import AuthenticatedHostIngress
from memorii.core.memory_evolution.models import MemoryScope


class GraphObservationContextResolver(Protocol):
    """Trusted host boundary; it alone may turn opaque ingress into context."""
    def resolve(self, host_ingress: AuthenticatedHostIngress, server_time: datetime) -> AuthenticatedGraphObservationContext: ...


class GraphObservationCurrentPolicyProvider(Protocol):
    """Returns the current protected policy, never a caller-selected policy."""
    def current_policy(self, *, context: AuthenticatedGraphObservationContext,
                       purpose: GraphObservationPurpose, scope_constraint: MemoryScope,
                       selector: GraphObservationCohortSelector,
                       server_time: datetime) -> GraphObservationPagePolicySnapshot | None: ...


class GraphObservationAccessGrant(BaseModel):
    principal_subject_id: str = Field(min_length=1)
    tenant_partition_id: str = Field(min_length=1)
    context_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    authorized_scopes: tuple[MemoryScope, ...]
    issued_at: datetime
    expires_at: datetime
    revoked: bool = False

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def _validate_grant(self) -> GraphObservationAccessGrant:
        scope_ids = tuple(scope.model_dump_json() for scope in self.authorized_scopes)
        if (not self.authorized_scopes or len(set(scope_ids)) != len(scope_ids)
                or self.authorized_scopes != tuple(sorted(self.authorized_scopes, key=lambda scope: scope.model_dump_json().encode("utf-8")))):
            raise ValueError("graph observation grant scopes must be ordered and unique")
        for value in (self.issued_at, self.expires_at):
            if value.tzinfo is None or value.utcoffset() is None or value.utcoffset() != UTC.utcoffset(value):
                raise ValueError("graph observation grant times must be UTC")
        if self.expires_at <= self.issued_at:
            raise ValueError("graph observation grant interval is invalid")
        return self


class GrantBackedGraphObservationAuthorizer:
    """Authorizes before a cohort owner can inspect a seed or storage index."""

    def __init__(self, *, grant_provider: Callable[[str], GraphObservationAccessGrant | None],
                 policy_provider: GraphObservationCurrentPolicyProvider,
                 correlation_token_factory: Callable[[], str] | None = None) -> None:
        self._grant_provider = grant_provider
        self._policy_provider = policy_provider
        self._correlation_token_factory = correlation_token_factory or (lambda: uuid4().hex)

    def _denied(self) -> GraphObservationFailure:
        return GraphObservationFailure(reason="denied", request_correlation_token=self._correlation_token_factory())

    def authorize(self, *, context: AuthenticatedGraphObservationContext, purpose: GraphObservationPurpose,
                  scope_constraint: MemoryScope, selector: GraphObservationCohortSelector,
                  server_time: datetime) -> GraphObservationAuthorizationDecision | GraphObservationFailure:
        if server_time.tzinfo is None or server_time.utcoffset() is None:
            return self._denied()
        now = server_time.astimezone(UTC)
        grant = self._grant_provider(context.context_digest)
        if (grant is None or grant.revoked or grant.context_digest != context.context_digest
                or grant.principal_subject_id != context.principal_subject_id
                or grant.tenant_partition_id != context.tenant_partition_id
                or now < grant.issued_at or now >= grant.expires_at):
            return self._denied()
        matching = tuple(scope for scope in grant.authorized_scopes if scope.can_read(scope_constraint))
        # More than one retained scope makes the authority identity ambiguous.
        if len(matching) != 1:
            return self._denied()
        policy = self._policy_provider.current_policy(
            context=context, purpose=purpose, scope_constraint=scope_constraint,
            selector=selector, server_time=now,
        )
        if policy is None:
            return self._denied()
        return GraphObservationAuthorizationDecision.create(
            preimage=GraphObservationAuthorizationDecisionPreimage(
                context=context, purpose=purpose, scope_constraint=scope_constraint,
                selector=selector, authorized_scope=matching[0], policy=policy,
                expires_at=grant.expires_at,
            )
        )
