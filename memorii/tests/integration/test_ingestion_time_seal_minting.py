"""Real-backend ingestion-time seal proofs (M2: ingestion-time persistence).

One activated provider on a JSONL store mints both seal kinds under real CAS
conditions: the group CAS writes a schema-3 core with its
TransactionGroupCommitTimeAttestation member, the terminal binds back to the
admission seal through the schema-2 outcome, redelivery and JSONL reopen
reuse the winner's bytes, noncommitting groups carry the explicit null, and
a reload with a missing member fails closed instead of re-minting.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime, timedelta
from threading import Event, Thread

import pytest
from memorii.core.memory_evolution.atomic_store import PreplanningStoreError
from memorii.core.memory_evolution.graph_effect_contracts import (
    SourceFinalizationObservationDelta,
)
from memorii.core.memory_evolution.graph_ingestion_time_contracts import (
    TransactionGroupCommitTimeAttestation,
)
from memorii.core.memory_evolution.ingestion_time_clock import (
    PRODUCTION_INGESTION_TIME_CLOCK_IDENTITY,
)
from memorii.core.memory_evolution.observation_activation_runtime import (
    validate_registered_artifact,
)
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import JsonlMemoryPlaneStore, _PersistedBatch
from memorii.core.provider.models import ProviderOperation
from memorii.core.scoped_context.authority import (
    InProcessScopedReadAuthority,
    ScopedNamespaceGrantRow,
)
from memorii.core.scoped_context.contracts import (
    ScopedContextBudget,
    ScopedContextRequest,
    ScopedContextStatus,
    ScopedRecordReference,
)
from memorii.core.semantic_ingestion.catalog_authority import (
    AuthenticatedPrincipalAgent,
    CatalogOwnerVisibilityGrant,
    FactScopeGrant,
    ResolvedStructuredSubmissionAuthority,
    SourceScopeGrant,
    StructuredFactReadAuthority,
    ThreePredicateSeedCatalogAuthorityRepository,
)
from memorii.core.semantic_ingestion.contracts import (
    BootstrapGraphGroupCommitReloadV3,
    BootstrapGraphGroupCommitRequestV3,
    ProviderSemanticProposal,
    decode_semantic_contract,
)
from memorii.core.semantic_ingestion.event_replay import (
    decode_semantic_memory_event_batch,
)
from memorii.domain.enums import MemoryDomain
from tests.integration.test_observation_ledger_activation import (
    _provider_factory,
    _seed_provider,
)
from tests.unit.core.semantic_ingestion.bootstrap_graph_production_roots_support import (
    graph_fact_proposal,
)
from tests.unit.core.semantic_ingestion.test_semantic_provider_composition import (
    TEST_NOW,
    _execute_retained_structured_submission,
    _host_ingress,
    _retained_structured_submission,
    _StructuredSubmissionAuthorityResolver,
)


def _sync(provider, operation_id: str, *, content: str = "Atlas owner is Bob."):
    return provider.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content=content,
        operation_id=operation_id,
        task_id="task:one",
        user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )


def _runtime_of(provider):
    runtime = provider._composed_semantic_runtime
    assert runtime is not None and runtime.atomic_store is not None
    assert runtime.typed_value_registry_history is not None
    return runtime


def _group_primary(plane: MemoryPlaneService):
    primaries = plane.list_records(
        source_kind="semantic_ingestion_bootstrap_graph_v3_group_commit_primary"
    )
    assert len(primaries) == 1
    return primaries[0]


def _group_reload(primary) -> BootstrapGraphGroupCommitReloadV3:
    return decode_semantic_contract(
        bytes.fromhex(primary.content["reload_hex"]),
        BootstrapGraphGroupCommitReloadV3,
    )


def _group_request(primary) -> BootstrapGraphGroupCommitRequestV3:
    return decode_semantic_contract(
        bytes.fromhex(primary.content["request_hex"]),
        BootstrapGraphGroupCommitRequestV3,
    )


def _group_seal_member(plane: MemoryPlaneService, primary):
    return plane.get_record(primary.memory_id + ":group_commit_attestation")


def _admission_seal(plane: MemoryPlaneService, source_id: str):
    delivery_key_digest = source_id.rsplit(":", 1)[-1]
    member = plane.get_record(
        f"semantic_ingestion:admission:{delivery_key_digest}:retention_attestation"
    )
    assert member is not None
    return member


def _activated_provider(
    tmp_path, monkeypatch: pytest.MonkeyPatch, *, without_ingestion_time_seals: bool = False,
    structured_fact_enabled: bool = False,
    normalization_proposal_ref: list[ProviderSemanticProposal] | None = None,
):
    build, _, _ = _provider_factory(
        tmp_path, monkeypatch, normalization=True, complete_registry=True,
        without_ingestion_time_seals=without_ingestion_time_seals,
        agent_bound=structured_fact_enabled,
        structured_submission_authority_resolver=(
            _StructuredSubmissionAuthorityResolver() if structured_fact_enabled else None
        ),
        normalization_proposal_ref=normalization_proposal_ref,
    )
    path = tmp_path / "ledger-store"
    plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
    provider = build(plane)
    _seed_provider(provider)
    if structured_fact_enabled:
        provider.provision_structured_submission_authority(
            authority=_mixed_authority()
        )
    provider.activate_observation_ledger()
    return build, path, plane, provider


def _mixed_authority() -> ResolvedStructuredSubmissionAuthority:
    authenticated = AuthenticatedPrincipalAgent(
        principal_id="principal:alice", agent_id="agent:alice",
    )
    catalog = ThreePredicateSeedCatalogAuthorityRepository().resolve_base()
    return ResolvedStructuredSubmissionAuthority(
        authenticated=authenticated,
        source_grant=SourceScopeGrant(
            grant_id="source-grant:mixed-history", grant_version=1,
            source_scope="task:task:one", authenticated=authenticated,
        ),
        fact_grant=FactScopeGrant(
            grant_id="fact-grant:mixed-history", grant_version=1,
            fact_scope="user:user:alice", authenticated=authenticated,
        ),
        catalog_visibility_grant=CatalogOwnerVisibilityGrant(
            grant_id="catalog-grant:mixed-history", grant_version=1,
            catalog_scope=catalog.catalog_scope, authenticated=authenticated,
            purpose="visibility_status",
        ),
        catalog=catalog,
    )


def _submit_catalog_bound_fact(provider, *, source_id: str):
    authority = _mixed_authority()
    accepted, submission, ingress = _retained_structured_submission(
        provider, authority=authority, activate_authority=False,
        source_id=source_id,
    )
    outcome = _execute_retained_structured_submission(
        provider, accepted=accepted, submission=submission, ingress=ingress,
    )
    assert outcome is not None
    assert "bootstrap_graph_terminal_persisted" in outcome.reason_codes
    return authority


@pytest.mark.parametrize("without_ingestion_time_seals", (False, True))
def test_projection_era_claim_and_new_catalog_claim_share_protected_scope_after_reopen(
    tmp_path, monkeypatch: pytest.MonkeyPatch,
    without_ingestion_time_seals: bool,
) -> None:
    proposal_ref = [graph_fact_proposal()]
    build, path, plane, provider = _activated_provider(
        tmp_path, monkeypatch,
        without_ingestion_time_seals=without_ingestion_time_seals,
        structured_fact_enabled=True,
        normalization_proposal_ref=proposal_ref,
    )
    _sync(provider, "mixed-history-original")
    primary = _group_primary(plane)
    reload = _group_reload(primary)
    assert reload.group_result_schema_version == (
        2 if without_ingestion_time_seals else 3
    )
    old_claim = next(
        record for record in plane.list_records()
        if record.content.get("runtime_context_projection_kind")
        == "bootstrap_v3_claim_assertion"
    )
    assert old_claim.agent_id == "agent:alice"
    old_bytes = old_claim.model_dump(mode="json")
    old_source_ids = {
        record.memory_id for record in plane.list_records(
            source_kind="semantic_ingestion_source"
        )
    }
    proposal_ref[0] = ProviderSemanticProposal(abstained=True)
    _sync(provider, "mixed-history-new-source")
    new_sources = tuple(
        record for record in plane.list_records(
            source_kind="semantic_ingestion_source"
        ) if record.memory_id not in old_source_ids
    )
    assert len(new_sources) == 1
    authority = _submit_catalog_bound_fact(
        provider, source_id=new_sources[0].memory_id,
    )
    bindings = plane.list_records(
        source_kind="semantic_ingestion_structured_claim_catalog_binding"
    )
    assert len(bindings) == 1
    new_claim = next(
        record for record in plane.list_records()
        if record.content.get("runtime_context_projection_kind")
        == "bootstrap_v3_claim_assertion"
        and record.content.get("claim_assertion_id")
        == bindings[0].content["binding"]["claim_assertion_id"]
    )
    assert new_claim.memory_id != old_claim.memory_id
    before_reopen = {
        record.memory_id: record.model_dump(mode="json")
        for record in plane.list_records()
    }

    def protected_response(service, *, read_authority=None, on_handle=None):
        scoped_authority = read_authority or InProcessScopedReadAuthority(
            now_provider=lambda: TEST_NOW
        )
        service._scoped_read_authority = scoped_authority
        handle = scoped_authority.provision(
            host_task_id="task:one", host_state_id="state:one",
            rows=(ScopedNamespaceGrantRow(
                domain=MemoryDomain.SEMANTIC, task_id="task:one",
                user_id="user:alice", agent_id="agent:alice",
            ),),
            expires_at=TEST_NOW + timedelta(minutes=1),
            structured_fact_read_authorities=(StructuredFactReadAuthority(
                authenticated=authority.authenticated,
                fact_grant=authority.fact_grant,
                catalog_visibility_grant=authority.catalog_visibility_grant,
            ),),
        )
        if on_handle is not None:
            on_handle(handle)
        response = service.retrieve_context(
            ScopedContextRequest(
                host_task_id="task:one", host_state_id="state:one",
                declared_complete_mandatory_set=True,
                mandatory_record_references=(
                    ScopedRecordReference(record_id=old_claim.memory_id, purpose="state"),
                    ScopedRecordReference(record_id=new_claim.memory_id, purpose="state"),
                ),
                optional_query=None, optional_domains=(),
                budget=ScopedContextBudget(
                    max_mandatory_items=2, max_optional_items=1,
                    max_optional_omission_ids=1, max_rendered_utf8_bytes=4096,
                ),
                reference_time=datetime(2026, 1, 15, tzinfo=UTC),
            ),
            opaque_host_ingress=handle,
        )
        return response

    expected_ids = (old_claim.memory_id, new_claim.memory_id)
    assert tuple(item.record_id for item in protected_response(provider).mandatory_items) == expected_ids
    reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
    reopened = build(reopened_plane)
    assert tuple(item.record_id for item in protected_response(reopened).mandatory_items) == expected_ids
    entered, proceed = Event(), Event()

    class ReleaseBarrierAuthority(InProcessScopedReadAuthority):
        def authorize_release(self, grant):
            entered.set()
            assert proceed.wait(120)
            return super().authorize_release(grant)

    race_authority = ReleaseBarrierAuthority(now_provider=lambda: TEST_NOW)
    handles = []
    outcomes = []
    worker = Thread(target=lambda: outcomes.append(protected_response(
        reopened, read_authority=race_authority, on_handle=handles.append,
    )))
    worker.start()
    try:
        assert entered.wait(900)
        assert len(handles) == 1
        race_authority.revoke(handles[0])
    finally:
        proceed.set()
        worker.join(120)
    assert not worker.is_alive()
    assert len(outcomes) == 1
    revoked = outcomes[0]
    assert revoked.status is ScopedContextStatus.DENIED
    assert revoked.mandatory_items == revoked.optional_items == ()
    assert revoked.structured_outcome is revoked.authority_binding_receipt is None
    if not without_ingestion_time_seals:
        seal_id = primary.memory_id + ":group_commit_attestation"
        assert reopened_plane.get_record(seal_id) is not None
        foreign_seal = next(
            record for record in reopened_plane.list_records(
                source_kind="semantic_ingestion_transaction_group_commit_attestation"
            ) if record.memory_id != seal_id
        )
        for variant in ("missing", "substituted"):
            variant_path = tmp_path / f"{variant}-old-group-seal"
            shutil.copytree(path, variant_path)
            log = variant_path / "memory_records.jsonl"
            batches = [
                _PersistedBatch.model_validate_json(line)
                for line in log.read_text(encoding="utf-8").splitlines()
            ]
            assert sum(record.memory_id == seal_id for batch in batches for record in batch.records) == 1
            changed_batches = [
                _PersistedBatch.create(
                    revision=batch.revision,
                    data_revision=batch.data_revision,
                    records=tuple(
                        foreign_seal.model_copy(update={"memory_id": seal_id})
                        if record.memory_id == seal_id and variant == "substituted"
                        else record
                        for record in batch.records if variant != "missing" or record.memory_id != seal_id
                    ),
                )
                for batch in batches
            ]
            log.write_text(
                "".join(batch.model_dump_json() + "\n" for batch in changed_batches),
                encoding="utf-8",
            )
            changed = build(MemoryPlaneService(record_store=JsonlMemoryPlaneStore(variant_path)))
            denied = protected_response(changed)
            assert denied.status is ScopedContextStatus.UNAVAILABLE
            assert denied.mandatory_items == denied.optional_items == ()
            assert denied.structured_outcome is denied.authority_binding_receipt is None
    else:
        assert reopened_plane.get_record(primary.memory_id + ":group_commit_attestation") is None
    after_reopen = {
        record.memory_id: record.model_dump(mode="json")
        for record in reopened_plane.list_records()
    }
    assert before_reopen == after_reopen
    assert after_reopen[old_claim.memory_id] == old_bytes
    assert len(reopened_plane.list_records(
        source_kind="semantic_ingestion_structured_claim_catalog_binding"
    )) == 1


def test_schema2_unsealed_native_projection_reads_through_protected_root(
    tmp_path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real activated pre-seal writer retains a readable schema-2 claim."""
    _build, _path, plane, provider = _activated_provider(
        tmp_path, monkeypatch, without_ingestion_time_seals=True,
    )
    _sync(provider, "unsealed-legacy-protected-read")
    primary = _group_primary(plane)
    reload = _group_reload(primary)
    assert reload.group_result_schema_version == 2
    assert reload.native_projection_publication_receipt is not None
    assert plane.get_record(primary.memory_id + ":group_commit_attestation") is None
    projection = next(
        record for record in plane.list_records()
        if record.content.get("runtime_context_projection_kind")
        == "bootstrap_v3_claim_assertion"
    )
    assert (projection.task_id, projection.user_id, projection.agent_id) == (
        "task:one", "user:alice", None,
    )
    assert not plane.list_records(
        source_kind="semantic_ingestion_structured_claim_catalog_binding"
    )
    authority = InProcessScopedReadAuthority(now_provider=lambda: TEST_NOW)
    provider._scoped_read_authority = authority
    handle = authority.provision(
        host_task_id="task:one", host_state_id="state:one",
        rows=(ScopedNamespaceGrantRow(
            domain=MemoryDomain.SEMANTIC, task_id="task:one", user_id="user:alice",
        ),),
        expires_at=TEST_NOW + timedelta(minutes=1),
    )
    response = provider.retrieve_context(
        ScopedContextRequest(
            host_task_id="task:one", host_state_id="state:one",
            declared_complete_mandatory_set=True,
            mandatory_record_references=(ScopedRecordReference(
                record_id=projection.memory_id, purpose="state",
            ),),
            optional_query=None,
            optional_domains=(),
            budget=ScopedContextBudget(
                max_mandatory_items=1, max_optional_items=1,
                max_optional_omission_ids=1, max_rendered_utf8_bytes=4096,
            ),
            reference_time=datetime(2026, 1, 15, tzinfo=UTC),
        ),
        opaque_host_ingress=handle,
    )
    assert tuple(item.record_id for item in response.mandatory_items) == (
        projection.memory_id,
    ), response.status


def test_committed_group_mints_the_schema3_seal_atomically(
    tmp_path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[BootstrapGraphGroupCommitRequestV3] = []
    from memorii.core.memory_evolution.atomic_store import (
        SemanticIngestionAtomicStore,
    )

    original = SemanticIngestionAtomicStore.commit_or_reload_bootstrap_graph_group_v3

    def capture(self, *, request):
        requests.append(request)
        return original(self, request=request)

    monkeypatch.setattr(
        SemanticIngestionAtomicStore,
        "commit_or_reload_bootstrap_graph_group_v3",
        capture,
    )
    _build, _path, plane, provider = _activated_provider(tmp_path, monkeypatch)
    result = _sync(provider, "seal-committed")
    assert result is not None and result.blocked_reasons["semantic_ingestion"] in {
        "source_only",
        "retryable_outage",
    }
    assert len(requests) == 1
    request = requests[0]
    primary = _group_primary(plane)
    reload = _group_reload(primary)
    core = reload.persisted_result.core
    assert reload.group_result_schema_version == 3
    assert core.group_result_schema_version == 3
    assert core.disposition == "committed"

    member = _group_seal_member(plane, primary)
    assert member is not None
    runtime = _runtime_of(provider)
    attestation = validate_registered_artifact(
        member.content["artifact"].encode("utf-8"),
        schema_id="TransactionGroupCommitTimeAttestation",
        history=runtime.typed_value_registry_history,
    )
    assert isinstance(attestation, TransactionGroupCommitTimeAttestation)
    # The digest fields bind exactly: the core's non-null digest is the
    # member's registered self-digest, never an unregistered companion.
    assert core.transaction_group_commit_attestation_digest == (
        attestation.attestation_digest
    )
    assert attestation.attestation_id == member.memory_id
    assert attestation.source_id == request.operation_fence_binding.source_id
    assert attestation.operation_fence_id == (
        request.operation_fence_binding.operation_fence_id
    )
    assert attestation.transaction_group_id == request.transaction_group_id
    assert attestation.operation_ids == request.operation_ids
    assert attestation.graph_revision_before == core.graph_revision_before
    assert attestation.graph_revision_after == core.graph_revision_after
    assert attestation.clock_identity == PRODUCTION_INGESTION_TIME_CLOCK_IDENTITY
    # Both protected instants are sampled inside the winning CAS; the frozen
    # composed clock pins them to the exact same instant.
    assert attestation.transaction_started_at == TEST_NOW
    assert attestation.transaction_committed_at == TEST_NOW
    # committed_batch_digest is acyclic: it equals the persisted canonical
    # event batch's source digest read back from the same JSONL store, and
    # the attestation preimage cannot contain the core that digests it.
    batches = plane.list_records(source_kind="semantic_ingestion_event_batch")
    assert len(batches) == 1
    persisted_batch = decode_semantic_memory_event_batch(
        bytes.fromhex(batches[0].content["canonical_hex"]),
        registry_history=runtime.atomic_store._event_schema_registry_history,
    )
    assert (
        attestation.committed_batch_digest
        == persisted_batch.source_event_batch_digest
    )
    assert attestation.applied_graph_delta_digest == (
        persisted_batch.graph_delta_digest
    )
    assert core.core_digest not in member.content["artifact"]

    # The outcome side binds back: the terminal source outcome is schema 2 and
    # carries the admission seal's registered attestation digest verbatim.
    entries = plane.list_records(
        source_kind="semantic_ingestion_observation_ledger_entry"
    )
    finalization = None
    for record in entries:
        entry = validate_registered_artifact(
            record.content["artifact"].encode("utf-8"),
            schema_id="ObservationLedgerEntry",
            history=runtime.typed_value_registry_history,
        )
        if isinstance(entry.delta, SourceFinalizationObservationDelta):
            finalization = entry.delta
    assert finalization is not None
    outcome = finalization.source_outcome
    admission_member = _admission_seal(plane, outcome.source_id)
    admission_attestation = validate_registered_artifact(
        admission_member.content["artifact"].encode("utf-8"),
        schema_id="SourceRetentionTimeAttestation",
        history=runtime.typed_value_registry_history,
    )
    assert outcome.core.source_result_schema_version == 2
    assert outcome.core.source_retention_attestation_digest == (
        admission_attestation.attestation_digest
    )
    assert outcome.source_retention_attestation_digest == (
        admission_attestation.attestation_digest
    )
    # The schema-2 fields serialize: the binding is explicit in the persisted
    # outcome bytes, never an implicit default.
    assert outcome.model_dump()["source_retention_attestation_digest"] == (
        admission_attestation.attestation_digest
    )


def test_schema3_legacy_projection_reads_through_protected_root_after_jsonl_reopen(
    tmp_path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The sealed projection-era group remains readable without a catalog binding."""
    build, path, plane, provider = _activated_provider(tmp_path, monkeypatch)
    _sync(provider, "sealed-legacy-protected-read")
    primary = _group_primary(plane)
    reload = _group_reload(primary)
    assert reload.group_result_schema_version == 3
    projection = next(
        record
        for record in plane.list_records()
        if record.content.get("runtime_context_projection_kind")
        == "bootstrap_v3_claim_assertion"
    )
    assert not plane.list_records(
        source_kind="semantic_ingestion_structured_claim_catalog_binding"
    )

    authority = InProcessScopedReadAuthority(now_provider=lambda: TEST_NOW)
    provider._scoped_read_authority = authority
    handle = authority.provision(
        host_task_id="task:one",
        host_state_id="state:one",
        rows=(ScopedNamespaceGrantRow(
            domain=MemoryDomain.SEMANTIC,
            task_id="task:one",
            user_id="user:alice",
        ),),
        expires_at=TEST_NOW + timedelta(minutes=1),
    )
    assert (
        projection.task_id,
        projection.user_id,
        projection.agent_id,
    ) == ("task:one", "user:alice", None)
    revision, snapshot = plane.read_snapshot()
    grant = authority.resolve(handle, task_id="task:one", state_id="state:one")
    assert grant is not None
    entry_record = plane.get_record(reload.ledger_entry_id)
    assert entry_record is not None
    from memorii.core.memory_evolution.atomic_store import _ledger_entry_from_record
    entry = _ledger_entry_from_record(
        entry_record,
        history=provider._semantic_atomic_store._typed_value_registry_history,
        limits=provider._semantic_atomic_store._observation_artifact_limits,
    )
    snapshot_by_id = {record.memory_id: record for record in snapshot}
    try:
        provider._semantic_atomic_store._verify_native_group_entry_snapshot(
            entry,
            snapshot_records=snapshot_by_id,
        )
    except PreplanningStoreError as exc:
        pytest.fail(f"schema3 native entry verifier: {exc}")
    try:
        provider._semantic_atomic_store._verify_group_commit_seal_snapshot(
            primary,
            reload,
            _group_request(primary),
            snapshot_records=snapshot_by_id,
        )
    except PreplanningStoreError as exc:
        pytest.fail(f"schema3 seal verifier: {exc}")
    verification = provider._semantic_atomic_store.verify_legacy_bootstrap_v3_runtime_projection(
        projection,
        revision=revision,
        records=snapshot,
        grant=grant,
    )
    assert verification == "verified"
    request = ScopedContextRequest(
        host_task_id="task:one",
        host_state_id="state:one",
        declared_complete_mandatory_set=True,
        mandatory_record_references=(ScopedRecordReference(
            record_id=projection.memory_id,
            purpose="state",
        ),),
        optional_query="Atlas owner",
        optional_domains=(MemoryDomain.SEMANTIC,),
        budget=ScopedContextBudget(
            max_mandatory_items=2,
            max_optional_items=2,
            max_optional_omission_ids=2,
            max_rendered_utf8_bytes=4096,
        ),
        reference_time=datetime(2026, 1, 15, tzinfo=UTC),
    )
    first = provider.retrieve_context(request, opaque_host_ingress=handle)
    assert tuple(item.record_id for item in first.mandatory_items) == (
        projection.memory_id,
    )

    before_reopen = {
        record.memory_id: record.model_dump(mode="json")
        for record in plane.list_records()
    }
    reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
    reopened = build(reopened_plane)
    assert reopened.activate_observation_ledger() == provider.activate_observation_ledger()
    reopened_authority = InProcessScopedReadAuthority(now_provider=lambda: TEST_NOW)
    reopened._scoped_read_authority = reopened_authority
    reopened_handle = reopened_authority.provision(
        host_task_id="task:one",
        host_state_id="state:one",
        rows=(ScopedNamespaceGrantRow(
            domain=MemoryDomain.SEMANTIC,
            task_id="task:one",
            user_id="user:alice",
        ),),
        expires_at=TEST_NOW + timedelta(minutes=1),
    )
    reopened_revision, reopened_snapshot = reopened_plane.read_snapshot()
    reopened_grant = reopened_authority.resolve(
        reopened_handle, task_id="task:one", state_id="state:one",
    )
    assert reopened_grant is not None
    reopened_projection = next(
        record for record in reopened_snapshot
        if record.memory_id == projection.memory_id
    )
    reopened_verification = reopened._semantic_atomic_store.verify_legacy_bootstrap_v3_runtime_projection(
        reopened_projection,
        revision=reopened_revision,
        records=reopened_snapshot,
        grant=reopened_grant,
    )
    assert reopened_verification == "verified"
    second = reopened.retrieve_context(request, opaque_host_ingress=reopened_handle)
    assert tuple(item.record_id for item in second.mandatory_items) == (
        projection.memory_id,
    )
    assert {
        record.memory_id: record.model_dump(mode="json")
        for record in reopened_plane.list_records()
    } == before_reopen


def test_reload_returns_original_and_never_remints(
    tmp_path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from memorii.core.memory_evolution.atomic_store import (
        SemanticIngestionAtomicStore,
    )

    requests: list[BootstrapGraphGroupCommitRequestV3] = []
    reloaded: list[BootstrapGraphGroupCommitReloadV3] = []
    original = SemanticIngestionAtomicStore.commit_or_reload_bootstrap_graph_group_v3

    def capture(self, *, request):
        requests.append(request)
        result = original(self, request=request)
        # Lost acknowledgement: re-commit the identical request while the
        # operation lease is still live. The store must return the original
        # reload from the persisted primary and write nothing.
        reloaded.append(original(self, request=request))
        return result

    monkeypatch.setattr(
        SemanticIngestionAtomicStore,
        "commit_or_reload_bootstrap_graph_group_v3",
        capture,
    )
    _build, _path, plane, provider = _activated_provider(tmp_path, monkeypatch)
    _sync(provider, "seal-reload")
    assert requests
    request = requests[0]
    primary = _group_primary(plane)
    member = _group_seal_member(plane, primary)
    assert member is not None
    records_after_commit = plane.list_records()
    assert reloaded == [_group_reload(primary)]
    assert plane.list_records() == records_after_commit
    assert plane.get_record(member.memory_id) == member

    runtime = _runtime_of(provider)
    # Guard proof: a reload whose image lost the member record fails closed
    # with the typed reload error instead of re-minting or returning quietly.
    revision, snapshot = plane.read_write_snapshot()

    def snapshot_without_member():
        return (
            revision,
            tuple(record for record in snapshot if record.memory_id != member.memory_id),
        )

    monkeypatch.setattr(plane, "read_write_snapshot", snapshot_without_member)
    with pytest.raises(PreplanningStoreError, match="attestation member is absent"):
        runtime.atomic_store._reload_bootstrap_graph_group_receipt(primary, request)
    monkeypatch.undo()
    assert plane.read_write_snapshot() == (revision, snapshot)


def test_redelivery_and_jsonl_reopen_reuse_winner_seal_bytes(
    tmp_path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    build, path, plane, provider = _activated_provider(tmp_path, monkeypatch)
    first = _sync(provider, "seal-reopen")
    assert first is not None
    primary = _group_primary(plane)
    group_member = _group_seal_member(plane, primary)
    assert group_member is not None
    admission_members = plane.list_records(
        source_kind="semantic_ingestion_source_retention_attestation"
    )
    assert len(admission_members) == 1
    retained_source = plane.get_record(
        "semantic_ingestion:source:" + admission_members[0].memory_id.split(":")[2]
    )
    assert retained_source is not None

    def _winner_seal_bytes(active_plane):
        # The winner's seal bytes are the immutable reuse contract: exactly one
        # admission seal and one group seal, byte-for-byte unchanged. Recovery
        # bookkeeping records beyond the seals may legitimately accompany a
        # full-flow redelivery; the seals themselves never move.
        return (
            active_plane.get_record(group_member.memory_id),
            active_plane.list_records(
                source_kind="semantic_ingestion_source_retention_attestation"
            ),
            active_plane.list_records(
                source_kind="semantic_ingestion_transaction_group_commit_attestation"
            ),
            active_plane.list_records(
                source_kind="semantic_ingestion_event_batch"
            ),
        )

    winner_state = _winner_seal_bytes(plane)
    assert winner_state[0] is not None
    assert len(winner_state[2]) == 1 and len(winner_state[3]) == 1

    redelivered = _sync(provider, "seal-reopen")
    assert redelivered == first
    assert _winner_seal_bytes(plane) == winner_state
    assert plane.get_record(retained_source.memory_id) == retained_source

    reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
    reopened = build(reopened_plane)
    activated = provider.activate_observation_ledger()
    assert reopened.activate_observation_ledger() == activated
    repeated = _sync(reopened, "seal-reopen")
    assert repeated == first
    assert _winner_seal_bytes(reopened_plane) == winner_state
    assert reopened_plane.get_record(retained_source.memory_id) == retained_source
