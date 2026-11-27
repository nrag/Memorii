from __future__ import annotations

import errno
import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event
from unittest.mock import Mock

import pytest
from memorii.core.memory_evolution.atomic_store import SemanticIngestionAtomicStore
from memorii.core.memory_evolution.ingestion_contracts import (
    AuthenticatedIngressContext,
    DeliveryPrincipalBinding,
    RequiredOutcomeScopeSet,
)
from memorii.core.memory_evolution.writer_admission import (
    SemanticWriterAdmissionStore,
    bounded_preplanning_ownership_manifest,
)
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.persistence.factory import open_managed_partition
from memorii.core.provider.catalog_read_workflow import CatalogReadHostRequest, read_catalog_workflow
from memorii.core.scoped_context.authority import InProcessScopedReadAuthority, ScopedNamespaceGrantRow
from memorii.core.semantic_ingestion.catalog_authority import (
    AuthenticatedPrincipalAgent,
    CatalogAuthorityScope,
    CatalogOwnerVisibilityGrant,
    FactScopeGrant,
    ResolvedStructuredSubmissionAuthority,
    SelectedCatalogAuthorityRepository,
    SourceScopeGrant,
    StructuredFactReadAuthority,
    catalog_version_memory_id,
)
from memorii.core.semantic_ingestion.catalog_capture_pin import PackageIndexedCatalogBundleLocator
from memorii.core.storage_administration.revoked_identity_view import empty_revoked_view
from memorii.core.storage_administration.service import InstallationIntegrityError, StorageAdministrationService
from memorii.domain.enums import MemoryDomain


@pytest.fixture(params=("memory", "managed"))
def catalog_planes(request, tmp_path):
    if request.param == "memory":
        plane = MemoryPlaneService()
        yield plane, plane, None, None
        return
    with StorageAdministrationService(tmp_path) as owner:
        owner.initialize()
    read_owner, read_plane = open_managed_partition(tmp_path)
    write_owner, write_plane = open_managed_partition(tmp_path)
    try:
        database_path = write_owner.partition().database_path
        yield read_plane, write_plane, database_path.with_name(database_path.name + ".lock"), read_owner
    finally:
        write_owner.close()
        read_owner.close()


@pytest.mark.parametrize("revoked_kind", ("fact", "catalog_visibility"))
def test_catalog_installation_version_change_precedes_membership_and_fact_reads(
    monkeypatch, catalog_planes, revoked_kind: str,
) -> None:
    now = datetime(2026, 11, 27, tzinfo=UTC)
    plane, writer_plane, partition_lock, read_owner = catalog_planes
    scope = CatalogAuthorityScope(schema_version=1, kind="base")
    authenticated = AuthenticatedPrincipalAgent(principal_id="alice", agent_id="assistant")
    fact = FactScopeGrant(
        grant_id="fact:alice", grant_version=1, fact_scope="user:alice", authenticated=authenticated,
    )
    catalog = CatalogOwnerVisibilityGrant(
        grant_id="catalog:base:alice", grant_version=1, catalog_scope=scope,
        authenticated=authenticated, purpose="visibility_status",
    )
    read_authority = StructuredFactReadAuthority(
        authenticated=authenticated, fact_grant=fact, catalog_visibility_grant=catalog,
    )
    writers = SemanticWriterAdmissionStore(writer_plane, bounded_preplanning_ownership_manifest())
    writer_binding = writers.commit_binding(writers.create_initial_evidence_only(
        admission_id="writer:test",
        writer_implementation_fingerprint="local-writer",
        graph_schema_fingerprint="local-graph",
    ))
    selected = SelectedCatalogAuthorityRepository(writer_plane, writers)
    selection = selected.ensure_seed_genesis()
    seed = selected.resolve_selected_bundle()
    store = SemanticIngestionAtomicStore(writer_plane, writers)
    store.provision_structured_submission_grant_states(
        authority=ResolvedStructuredSubmissionAuthority(
            authenticated=authenticated,
            source_grant=SourceScopeGrant(
                grant_id="source:alice", grant_version=1, source_scope="task:one",
                authenticated=authenticated,
            ),
            fact_grant=fact,
            catalog_visibility_grant=catalog,
            catalog=selection,
        ),
        writer_binding=writer_binding,
    )
    partition = "local:installation"
    session = "current-session"
    scopes = RequiredOutcomeScopeSet.create(
        tenant_partition_id=partition, scopes={fact.fact_scope, f"session:{session}"},
    )
    ingress = AuthenticatedIngressContext(
        delivery_principal_binding=DeliveryPrincipalBinding.create(
            principal_subject_id=authenticated.principal_id, tenant_partition_id=partition,
            provider_identity="installed-host",
        ),
        required_outcome_scopes=scopes,
        current_authorized_scopes=scopes,
        authenticated_agent_id=authenticated.agent_id,
    )
    host = InProcessScopedReadAuthority(now_provider=lambda: now)
    handle = host.provision(
        host_task_id="catalog-lookup", host_state_id=session, expires_at=now + timedelta(minutes=1),
        rows=(ScopedNamespaceGrantRow(domain=MemoryDomain.SEMANTIC, user_id="alice", agent_id="assistant"),),
        structured_fact_read_authorities=(read_authority,),
    )
    host_request = CatalogReadHostRequest(
        handle=handle, task_id="catalog-lookup", state_id=session, installation_partition_id=partition,
        session_id=session, authenticated=authenticated, fact_scope=fact.fact_scope,
        binding_is_current=lambda: True,
    )
    read_facts = Mock(side_effect=AssertionError("an early diagnosis reached the fact reader"))
    monkeypatch.setattr("memorii.core.provider.catalog_read_workflow.read_current_catalog_bound_facts", read_facts)
    locator = PackageIndexedCatalogBundleLocator()

    def inspect() -> str:
        result = read_catalog_workflow(
            {"kind": "name", "name": "project owner"}, operation="inspect", ingress=ingress,
            host_request=host_request, host_authority=host, memory_plane=plane, locator=locator,
            now_provider=lambda: now, legacy_verifier=Mock(), suppression_view=lambda _: empty_revoked_view(),
        )
        assert result.catalog_version_digest is not None
        return result.catalog_version_digest

    def diagnose(request: dict[str, str]) -> str:
        return read_catalog_workflow(
            request, operation="diagnose", ingress=ingress, host_request=host_request,
            host_authority=host, memory_plane=plane, locator=locator, now_provider=lambda: now,
            legacy_verifier=Mock(), suppression_view=lambda _: empty_revoked_view(),
        ).status

    def read_before_mutation(read: Callable[[], str], mutate: Callable[[], object]) -> str:
        if partition_lock is None:
            result = read()
            mutate()
            return result

        awaiting_release = Event()
        allow_release = Event()
        release_authorized = Event()
        write_requested = Event()
        authorize_release = host.authorize_release
        write = writer_plane.conditionally_write_records

        def hold_release(grant):
            awaiting_release.set()
            assert allow_release.wait(timeout=10)
            result = authorize_release(grant)
            release_authorized.set()
            return result

        def check_partition_fence(records, *, transaction_precondition=None, **kwargs):
            def inside_write_transaction() -> None:
                assert release_authorized.is_set()
                if transaction_precondition is not None:
                    transaction_precondition()

            write_requested.set()
            return write(records, **kwargs, transaction_precondition=inside_write_transaction)

        with monkeypatch.context() as scoped, ThreadPoolExecutor(max_workers=2) as pool:
            scoped.setattr(host, "authorize_release", hold_release)
            scoped.setattr(writer_plane, "conditionally_write_records", check_partition_fence)
            pending_read = pool.submit(read)
            try:
                assert awaiting_release.wait(timeout=10)
                with partition_lock.open("r+b") as probe:
                    if os.name == "nt":
                        import msvcrt

                        with pytest.raises(OSError) as blocked:
                            msvcrt.locking(probe.fileno(), msvcrt.LK_NBLCK, 1)
                        assert blocked.value.errno == errno.EACCES
                    else:
                        import fcntl

                        with pytest.raises(BlockingIOError):
                            fcntl.flock(probe.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                pending_mutation = pool.submit(mutate)
                assert write_requested.wait(timeout=10)
            finally:
                allow_release.set()
            result = pending_read.result(timeout=10)
            pending_mutation.result(timeout=10)
            return result

    expected = read_before_mutation(inspect, selected.install_default_catalog_release)
    assert expected == seed.version.version_digest
    default = selected.resolve_selected_bundle()
    assert default.catalog.catalog_digest == seed.catalog.catalog_digest
    assert default.version.version_digest != expected
    assert inspect() == default.version.version_digest
    for predicate in ("project_owner", "unknown_relation"):
        assert diagnose({
            "kind": "exact", "predicate_id": predicate, "subject_entity_id": "opaque-subject",
            "expected_catalog_version_digest": expected,
        }) == "catalog_changed"
    assert diagnose({
        "kind": "exact", "predicate_id": "unknown_relation", "subject_entity_id": "opaque-subject",
        "expected_catalog_version_digest": default.version.version_digest,
    }) == "unsupported_predicate"

    snapshot = plane.read_snapshot_linearized
    selected_version_id = catalog_version_memory_id(default.version)

    def snapshot_without_selected_version(callback):
        return snapshot(lambda revision, records: callback(revision, tuple(
            record for record in records if record.memory_id != selected_version_id
        )))

    with monkeypatch.context() as scoped:
        scoped.setattr(plane, "read_snapshot_linearized", snapshot_without_selected_version)
        assert diagnose({
            "kind": "exact", "predicate_id": "project_owner", "subject_entity_id": "opaque-subject",
            "expected_catalog_version_digest": expected,
        }) == "unavailable"
        response = read_catalog_workflow(
            {"kind": "name", "name": "project owner"}, operation="inspect", ingress=ingress,
            host_request=host_request, host_authority=host, memory_plane=plane, locator=locator,
            now_provider=lambda: now, legacy_verifier=Mock(), suppression_view=lambda _: empty_revoked_view(),
        )
        assert response.model_dump(mode="json") == {"status": "unavailable"}

    selection = Mock(side_effect=AssertionError("no selected catalog should be probed"))
    monkeypatch.setattr(locator, "locate_selected", selection)
    assert diagnose({"kind": "unresolved", "reference": "subject"}) == "needs_clarification"
    assert diagnose({"kind": "exact"}) == "invalid_request"
    selection.assert_not_called()
    read_facts.assert_not_called()
    # The managed guard can refuse a snapshot before dispatch ever enters the
    # callback. Both public shapes are safe and disjoint from read denial.
    with monkeypatch.context() as scoped:
        if read_owner is None:
            scoped.setattr(plane, "read_snapshot_linearized", Mock(side_effect=InstallationIntegrityError(
                "private partition state",
            )))
        else:
            path, publication = read_owner._active_partition_selection()
            scoped.setattr(
                read_owner, "_active_partition_selection",
                lambda: (path.with_name("new-generation.sqlite3"), publication),
            )
        assert diagnose({"kind": "unresolved", "reference": "subject"}) == "unavailable"
        response = read_catalog_workflow(
            {"kind": "name", "name": "project owner"}, operation="inspect", ingress=ingress,
            host_request=host_request, host_authority=host, memory_plane=plane, locator=locator,
            now_provider=lambda: now, legacy_verifier=Mock(), suppression_view=lambda _: empty_revoked_view(),
        )
        assert response.model_dump(mode="json") == {"status": "unavailable"}
    def revoke_grant() -> None:
        store.revoke_structured_submission_grant(
            grant_kind=revoked_kind,
            grant=fact if revoked_kind == "fact" else catalog,
            writer_binding=writer_binding,
        )

    assert read_before_mutation(
        lambda: diagnose({"kind": "unresolved", "reference": "subject"}), revoke_grant,
    ) == "needs_clarification"

    # The next read observes the persisted revocation before parsing or lookup.
    assert diagnose({
        "kind": "exact", "predicate_id": "project_owner", "subject_entity_id": "opaque-subject",
    }) == "denied"
    host.revoke(handle)
    assert diagnose({"kind": "exact"}) == "denied"
    selection.assert_not_called()
