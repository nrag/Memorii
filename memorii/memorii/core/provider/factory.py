"""Application composition for provider memory services."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from memorii.core.decision_state.service import DecisionStateService
from memorii.core.memory_evolution.atomic_store import SemanticIngestionAtomicStore
from memorii.core.memory_evolution.conflict_integrity import (
    PrivilegedSemanticIntegrityLifecycle,
)
from memorii.core.memory_evolution.identity_lineage import (
    AtomicStoreScopedIdentityLineageAuditReader,
    GrantBackedIdentityLineageAuditAuthorizer,
    IdentityLineageAuditGrant,
)
from memorii.core.memory_evolution.ingestion_contracts import (
    AuthenticatedIngressContextResolver,
)
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.provider.service import ProviderMemoryService
from memorii.core.work_state.service import WorkStateService

_DEFAULT_DECISION_STATE_SERVICE = object()


def build_provider_memory_service_from_env(
    *,
    memory_plane: MemoryPlaneService | None = None,
    work_state_service: WorkStateService | None = None,
    decision_state_service: DecisionStateService | None | object = _DEFAULT_DECISION_STATE_SERVICE,
    semantic_integrity_lifecycle: PrivilegedSemanticIntegrityLifecycle
    | None = None,
    semantic_integrity_root: Path | None = None,
    identity_lineage_atomic_store: SemanticIngestionAtomicStore | None = None,
    identity_lineage_tenant_partition_id: str | None = None,
    identity_lineage_grant_provider: (
        Callable[[str], IdentityLineageAuditGrant | None] | None
    ) = None,
    authenticated_ingress_resolver: AuthenticatedIngressContextResolver | None = None,
    now_provider: Callable[[], datetime] | None = None,
) -> ProviderMemoryService:
    """Build the source-only governed-source admission provider composition without ambient model dependencies."""

    audit_values = (
        identity_lineage_atomic_store,
        identity_lineage_tenant_partition_id,
        identity_lineage_grant_provider,
        authenticated_ingress_resolver,
    )
    if any(value is not None for value in audit_values) and not all(
        value is not None for value in audit_values
    ):
        raise ValueError("identity lineage audit composition is incomplete")
    audit_reader = None
    audit_authorizer = None
    if identity_lineage_atomic_store is not None:
        assert identity_lineage_tenant_partition_id is not None
        assert identity_lineage_grant_provider is not None
        audit_authorizer = GrantBackedIdentityLineageAuditAuthorizer(
            identity_lineage_grant_provider
        )
        audit_reader = AtomicStoreScopedIdentityLineageAuditReader(
            identity_lineage_atomic_store,
            tenant_partition_id=identity_lineage_tenant_partition_id,
            scope_revalidator=lambda scope, server_time: (
                audit_authorizer.revalidate_identity_lineage_audit_scope(
                    scope, server_time=server_time
                )
            ),
            now_provider=now_provider or (lambda: datetime.now(UTC)),
        )
    return ProviderMemoryService(
        memory_plane=memory_plane,
        work_state_service=work_state_service,
        decision_state_service=None if decision_state_service is _DEFAULT_DECISION_STATE_SERVICE else decision_state_service,
        semantic_integrity_lifecycle=semantic_integrity_lifecycle,
        semantic_integrity_root=semantic_integrity_root,
        authenticated_ingress_resolver=authenticated_ingress_resolver,
        identity_lineage_audit_reader=audit_reader,
        identity_lineage_audit_authorizer=audit_authorizer,
        now_provider=now_provider,
    )


__all__ = ["build_provider_memory_service_from_env"]
