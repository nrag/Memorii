from datetime import UTC, datetime

import pytest
from memorii.core.memory_evolution.identity_lineage import (
    AtomicStoreScopedIdentityLineageAuditReader,
    GrantBackedIdentityLineageAuditAuthorizer,
    IdentityLineageAuditGrant,
    IdentityLineageAuditScopeSnapshot,
    IdentityLineageAuditView,
)
from memorii.core.memory_evolution.ingestion_contracts import (
    AuthenticatedHostIngress,
    AuthenticatedIngressContext,
    DeliveryPrincipalBinding,
    RequiredOutcomeScopeSet,
)
from memorii.core.memory_evolution.models import MemoryScope
from memorii.core.memory_evolution.retrieval_contracts import (
    GraphAuditRequest,
    RetrievalPurpose,
)
from memorii.core.provider.service import ProviderMemoryService
from memorii.integrations.hermes_provider import HermesMemoryProvider


def _view() -> IdentityLineageAuditView:
    return IdentityLineageAuditView(
        repository_id="tenant-graph",
        graph_revision="graph:2",
        lineage_snapshot_digest="a" * 64,
        transition_digests=("b" * 64,),
        resolved_claims=(),
        view_digest="c" * 64,
    )


def test_hermes_forwards_typed_scoped_graph_audit_lineage_without_reinterpretation() -> None:
    class Reader:
        def __init__(self) -> None:
            self.calls = []
            self.view = _view()

        def read_identity_lineage(self, *, request, scope, system_time=None):
            self.calls.append((request, scope, system_time))
            return self.view

    reader = Reader()
    now = datetime(2026, 2, 1, tzinfo=UTC)
    scope = IdentityLineageAuditScopeSnapshot.create(
        tenant_partition_id="tenant",
        principal_binding_digest="d" * 64,
        authorized_scope_ids=("user:user:alice",),
        scope_mode="scoped",
        issued_at=now,
        expires_at=datetime(2026, 4, 1, tzinfo=UTC),
    )
    authorizer = type(
        "Authorizer",
        (),
        {"authorize_identity_lineage_audit": lambda self, **kwargs: scope},
    )()
    resolver = type(
        "Resolver",
        (),
        {"resolve": lambda self, host_ingress, server_time: object()},
    )()
    service = ProviderMemoryService(
        identity_lineage_audit_reader=reader,
        identity_lineage_audit_authorizer=authorizer,
        authenticated_ingress_resolver=resolver,
        now_provider=lambda: now,
    )
    hermes = HermesMemoryProvider(service=service)
    request = GraphAuditRequest(
        query="Alice identity lineage",
        purpose=RetrievalPurpose.GRAPH_AUDIT,
        scope=MemoryScope(user_id="user:alice"),
        scope_mode="scoped",
    )
    system_time = datetime(2026, 3, 1, tzinfo=UTC)

    ingress = AuthenticatedHostIngress(
        provider_identity="hermes",
        principal_handle=object(),
        session_handle=object(),
        received_at=now,
    )
    assert hermes.read_identity_lineage(
        request,
        authenticated_host_ingress=ingress,
        system_time=system_time,
    ) is reader.view
    assert reader.calls[0] == (request, scope, system_time)


def test_provider_denies_before_reader_when_lineage_authority_is_missing() -> None:
    now = datetime(2026, 2, 1, tzinfo=UTC)
    resolver = type(
        "Resolver",
        (),
        {"resolve": lambda self, host_ingress, server_time: object()},
    )()
    service = ProviderMemoryService(
        authenticated_ingress_resolver=resolver,
        now_provider=lambda: now,
    )

    audit_request = GraphAuditRequest(
        query="Alice",
        purpose=RetrievalPurpose.GRAPH_AUDIT,
    )
    ingress = AuthenticatedHostIngress(
        provider_identity="hermes",
        principal_handle=object(),
        session_handle=object(),
        received_at=now,
    )
    with pytest.raises(ValueError, match="identity_lineage_audit_denied"):
        service.read_identity_lineage(
            audit_request,
            authenticated_host_ingress=ingress,
        )


def test_scoped_reader_rejects_incomplete_atomic_store_at_construction() -> None:
    store = type("IncompleteStore", (), {"semantic_replay_state": lambda self: object()})()

    with pytest.raises(TypeError, match="requires canonical atomic store"):
        AtomicStoreScopedIdentityLineageAuditReader(
            store,
            tenant_partition_id="tenant",
            scope_revalidator=lambda scope, server_time: scope,
        )


def test_scoped_reader_revalidates_revocation_before_any_store_disclosure() -> None:
    now = datetime(2026, 2, 1, tzinfo=UTC)
    scope = IdentityLineageAuditScopeSnapshot.create(
        tenant_partition_id="tenant",
        principal_binding_digest="d" * 64,
        authorized_scope_ids=("user:alice",),
        scope_mode="scoped",
        issued_at=now,
        expires_at=datetime(2026, 3, 1, tzinfo=UTC),
    )

    class Store:
        def __init__(self) -> None:
            self.reads = 0

        def lineage_audit_scope_event_ids(self, **kwargs):
            del kwargs
            self.reads += 1
            return frozenset()

        def semantic_replay_state(self):
            self.reads += 1
            return object()

    store = Store()
    reader = AtomicStoreScopedIdentityLineageAuditReader(
        store,
        tenant_partition_id="tenant",
        scope_revalidator=lambda authorized, server_time: None,
        now_provider=lambda: now,
    )
    request = GraphAuditRequest(
        query="Alice",
        purpose=RetrievalPurpose.GRAPH_AUDIT,
        scope=MemoryScope(user_id="user:alice"),
        scope_mode="scoped",
    )

    with pytest.raises(ValueError, match="identity_lineage_audit_denied"):
        reader.read_identity_lineage(request=request, scope=scope)
    assert store.reads == 0


@pytest.mark.parametrize(
    ("revoked", "expired", "scope_mode", "allow_full", "permitted"),
    (
        (False, False, "scoped", False, True),
        (True, False, "scoped", False, False),
        (False, True, "scoped", False, False),
        (False, False, "full", False, False),
        (False, False, "full", True, True),
    ),
)
def test_lineage_audit_grants_enforce_revocation_expiry_and_distinct_full_scope(
    revoked: bool,
    expired: bool,
    scope_mode: str,
    allow_full: bool,
    permitted: bool,
) -> None:
    now = datetime(2026, 2, 1, tzinfo=UTC)
    principal = DeliveryPrincipalBinding.create(
        principal_subject_id="principal",
        tenant_partition_id="tenant",
        provider_identity="hermes",
    )
    scopes = RequiredOutcomeScopeSet.create(
        tenant_partition_id="tenant", scopes={"user:alice"}
    )
    ingress = AuthenticatedIngressContext(
        delivery_principal_binding=principal,
        required_outcome_scopes=scopes,
        current_authorized_scopes=scopes,
    )
    grant = IdentityLineageAuditGrant(
        tenant_partition_id="tenant",
        principal_binding_digest=principal.binding_digest,
        authorized_scope_ids=("user:alice",),
        allow_full_scope=allow_full,
        issued_at=datetime(2026, 1, 1, tzinfo=UTC),
        expires_at=(
            datetime(2026, 1, 31, tzinfo=UTC)
            if expired
            else datetime(2026, 3, 1, tzinfo=UTC)
        ),
        revoked=revoked,
    )
    authorizer = GrantBackedIdentityLineageAuditAuthorizer(lambda _: grant)
    request = GraphAuditRequest(
        query="Alice",
        purpose=RetrievalPurpose.GRAPH_AUDIT,
        scope=MemoryScope(user_id="user:alice"),
        scope_mode=scope_mode,
    )
    result = authorizer.authorize_identity_lineage_audit(
        ingress=ingress, request=request, server_time=now
    )
    assert (result is not None) is permitted


@pytest.mark.parametrize(
    "fault",
    ("tenant", "principal", "grant_scope", "current_scope", "future_issued"),
)
def test_lineage_audit_grants_fail_closed_for_binding_and_scope_mismatch(
    fault: str,
) -> None:
    now = datetime(2026, 2, 1, tzinfo=UTC)
    principal = DeliveryPrincipalBinding.create(
        principal_subject_id="principal",
        tenant_partition_id="tenant",
        provider_identity="hermes",
    )
    requested = RequiredOutcomeScopeSet.create(
        tenant_partition_id="tenant", scopes={"user:alice"}
    )
    current = RequiredOutcomeScopeSet.create(
        tenant_partition_id="tenant",
        scopes={"user:bob"} if fault == "current_scope" else {"user:alice"},
    )
    ingress = AuthenticatedIngressContext(
        delivery_principal_binding=principal,
        required_outcome_scopes=requested,
        current_authorized_scopes=current,
    )
    grant = IdentityLineageAuditGrant(
        tenant_partition_id="other" if fault == "tenant" else "tenant",
        principal_binding_digest=(
            "f" * 64 if fault == "principal" else principal.binding_digest
        ),
        authorized_scope_ids=(
            ("user:bob",) if fault == "grant_scope" else ("user:alice",)
        ),
        allow_full_scope=False,
        issued_at=(
            datetime(2026, 2, 2, tzinfo=UTC)
            if fault == "future_issued"
            else datetime(2026, 1, 1, tzinfo=UTC)
        ),
        expires_at=datetime(2026, 3, 1, tzinfo=UTC),
        revoked=False,
    )
    request = GraphAuditRequest(
        query="Alice",
        purpose=RetrievalPurpose.GRAPH_AUDIT,
        scope=MemoryScope(user_id="user:alice"),
        scope_mode="scoped",
    )

    assert GrantBackedIdentityLineageAuditAuthorizer(
        lambda _: grant
    ).authorize_identity_lineage_audit(
        ingress=ingress, request=request, server_time=now
    ) is None
