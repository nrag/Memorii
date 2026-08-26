"""Coordinator retry proof using the real direct-provider recovery reload."""

from __future__ import annotations

from datetime import timedelta
from hashlib import sha256
from pathlib import Path

import memorii.core.semantic_ingestion.contracts as semantic_contracts
import pytest
from memorii.core.memory_evolution.atomic_store import (
    BootstrapWriterHandoffMarkerV3,
    PreplanningStoreError,
)
from memorii.core.memory_evolution.writer_admission import SemanticWriterAdmissionError
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import JsonlMemoryPlaneStore, _PersistedBatch
from memorii.core.provider.models import ProviderOperation
from memorii.core.provider.service import ProviderMemoryService
from memorii.core.semantic_ingestion.bootstrap_graph_coordinator import (
    BootstrapGraphDependentCoordinatorV3,
)
from memorii.core.semantic_ingestion.bootstrap_graph_host import BootstrapGraphHostBundleBuilder
from memorii.core.semantic_ingestion.bootstrap_graph_repository import (
    AtomicStoreBootstrapGraphControlEpochRepositoryV3,
    AtomicStoreBootstrapGraphGroupCommitRepositoryV3,
    AtomicStoreBootstrapGraphPlanRepositoryV3,
    AtomicStoreBootstrapGraphTerminalPersistencePortV3,
)
from memorii.core.semantic_ingestion.bootstrap_graph_terminal_preparation import (
    DeterministicBootstrapGraphTerminalPreparationV3,
)
from memorii.core.semantic_ingestion.contracts import (
    BootstrapGraphDependentCoordinatorRequestV3,
    BootstrapGraphSnapshotAuthorityV3,
    BootstrapGraphTerminalReloadV3,
    ProviderEntityObject,
    ProviderFact,
    ProviderMention,
    ProviderSemanticProposal,
    decode_semantic_contract,
)
from tests.fixtures.semantic_ingestion.bootstrap_graph_v3_fixture import (
    DeterministicBootstrapGraphAuthorityProviderV3,
    DeterministicBootstrapGraphPlanCompilerV3,
    DeterministicBootstrapGraphPlanningAuthorizerV3,
    build_bootstrap_graph_terminal_host_authority_v3,
    build_empty_capability_registry,
    build_empty_graph_snapshot_bundle,
    build_graph_coordinator_request,
    build_graph_epoch_transition_request,
    build_graph_policy_reference,
    build_minimal_bootstrap_graph_plan_compilation_v3,
    build_persisted_bootstrap_graph_replay_fixture,
)
from tests.unit.core.semantic_ingestion.test_semantic_provider_composition import (
    TEST_NOW,
    DeterministicTestHostBootstrapMaterialVerifier,
    _built_in_local_capability,
    _host_ingress,
    _v3_normalization_host_builder,
)
from tests.unit.core.test_provider_service import _build_production_scoped_provider_service


@pytest.mark.parametrize(
    "outcome_kind",
    (
        "retry", "success", "related_conflict", "exhausted_conflict",
        "lease_renewed", "lease_reclaimed", "writer_changed", "writer_unavailable",
    ),
)
def test_coordinator_persists_retry_or_terminal_once(monkeypatch, outcome_kind: str) -> None:
    builder, _calls = _v3_normalization_host_builder(
        proposal=ProviderSemanticProposal(
            mentions=(ProviderMention(local_id="atlas", mention_quote="Atlas", mention_context_quote="Atlas owner is Bob."), ProviderMention(local_id="bob", mention_quote="Bob", mention_context_quote="Atlas owner is Bob.")),
            facts=(ProviderFact(local_id="owner", predicate_id="owner_is", subject_entity_ref="atlas", object=ProviderEntityObject(entity_ref="bob"), assertion_quote="Atlas owner is Bob.", predicate_anchor_quote="owner", polarity="positive", commitment="asserted"),),
            abstained=False,
        )
    )
    plane = MemoryPlaneService()
    class UnavailableGraphAuthorityProvider:
        def acquire(self, **_kwargs):
            return None

    clock = [TEST_NOW]
    service = ProviderMemoryService._from_scenario_test_host(
        memory_plane=plane,
        now_provider=lambda: clock[0],
        host_bootstrap_capability=_built_in_local_capability(scenario_test=True),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        source_normalization_host_bundle_builder=builder,
        bootstrap_graph_host_bundle_builder=BootstrapGraphHostBundleBuilder(
            authority_provider=UnavailableGraphAuthorityProvider()
        ),
    )
    def stop_before_generic_terminal(*_args: object, **_kwargs: object) -> None:
        """Keep the real V3 normalization publication's control lease live."""

    monkeypatch.setattr(
        service._provider_ingestion,
        "_persist_semantic_terminal",
        stop_before_generic_terminal,
    )
    trace: list[str] = []
    bundle = service._provider_ingestion._semantic_runtime.source_normalization_host_bundle
    assert bundle is not None
    owner = bundle.execution_owner
    proposal_producer = owner._bootstrap_v3_proposal_producer
    evidence_producer = owner._bootstrap_v3_evidence_producer
    interpreter = owner._bootstrap_v3_interpreter
    stage = owner._bootstrap_v3_stage
    assert proposal_producer is not None and evidence_producer is not None and interpreter is not None

    def wrap(name, target):
        def call(*args, **kwargs):
            try:
                value = target(*args, **kwargs)
            except ValueError as exc:
                trace.append(f"{name}:ValueError:{exc}")
                raise
            trace.append(f"{name}:{type(value).__name__}")
            return value
        return call

    monkeypatch.setattr(proposal_producer, "produce", wrap("proposal", proposal_producer.produce))
    monkeypatch.setattr(evidence_producer, "produce", wrap("evidence", evidence_producer.produce))
    monkeypatch.setattr(interpreter, "interpret", wrap("interpreter", interpreter.interpret))
    monkeypatch.setattr(stage, "normalize", wrap("stage", stage.normalize))
    original_renew = bundle.recovery_repository.renew_or_abort
    monkeypatch.setattr(
        bundle.recovery_repository,
        "renew_or_abort",
        wrap("renew", original_renew),
    )
    result = service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="coordinator-retry",
        task_id="task:one",
        user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    assert result.blocked_reasons["semantic_ingestion"] == "graph_transaction_authority_unavailable", " | ".join(trace)
    marker = BootstrapWriterHandoffMarkerV3.model_validate(
        plane.list_records(source_kind="semantic_ingestion_bootstrap_handoff_marker")[0]
        .content["marker"]
    )
    atomic = service._semantic_atomic_store
    control = atomic.get_operation(marker.operation_fence_binding)
    lease = atomic.lease_binding(control)
    ingress = service._resolve_ingress(_host_ingress())
    assert ingress is not None
    source = atomic.load_prepared_source(
        source_id=marker.source_id,
        source_digest=marker.source_digest,
    )
    assert source is not None
    recovery_key = plane.list_records(
        source_kind="semantic_ingestion_bootstrap_v3_recovery_index"
    )[0].content["recovery_key_digest"]
    fixture = build_persisted_bootstrap_graph_replay_fixture(
        recovery_repository=atomic,
        recovery_key_digest=recovery_key,
        authenticated_ingress=ingress,
        required_outcome_scopes=source.governance_carrier_artifact.required_outcome_scopes,
        operation_fence_binding=marker.operation_fence_binding,
        operation_lease_binding=lease,
        writer_commit_binding=control.writer_binding,
        control_epoch=ingress,
    )
    snapshot = build_empty_graph_snapshot_bundle()
    policy = build_graph_policy_reference()
    capabilities = build_empty_capability_registry()
    authority = BootstrapGraphSnapshotAuthorityV3.create(
        source_id=source.source_id,
        source_digest=source.source_digest,
        preparation_fingerprint=source.preparation_fingerprint,
        normalization_replay_digest=fixture.replay.replay_digest,
        normalization_result_digest=(
            fixture.replay.source_normalization_result.result_digest
        ),
        source_alignment_digest=(
            fixture.replay.source_normalization_request.source_alignment.alignment_digest
        ),
        snapshot=snapshot,
        base_read_set_digest=snapshot.base_read_set.read_set_digest,
        required_scope_set_digest=(
            source.governance_carrier_artifact.required_outcome_scopes.required_scope_set_digest
        ),
        delivery_principal_binding_digest=(
            ingress.delivery_principal_binding.binding_digest
        ),
        execution_policy=policy,
        capability_registry_snapshot=capabilities,
        operation_lease_binding=lease,
        operation_fence_binding=marker.operation_fence_binding,
        writer_commit_binding=control.writer_binding,
    )
    transition = build_graph_epoch_transition_request(
        fixture=fixture,
        graph_authority=authority,
        source_alignment=fixture.replay.source_normalization_request.source_alignment,
    )
    epoch_result = AtomicStoreBootstrapGraphControlEpochRepositoryV3(
        atomic_store=atomic
    ).transition_or_find(request=transition)
    epoch = epoch_result.epoch
    request = build_graph_coordinator_request(
        fixture=fixture,
        graph_authority=authority,
        source_alignment=fixture.replay.source_normalization_request.source_alignment,
        initial_control_epoch=epoch,
    )
    if outcome_kind in {"lease_renewed", "writer_changed", "writer_unavailable"}:
        assert control.lease is not None
        atomic.renew_lease(
            operation_fence=marker.operation_fence_binding,
            writer_binding=control.writer_binding,
            lease=control.lease,
            duration=timedelta(minutes=10),
        )
        if outcome_kind == "lease_renewed":
            refreshed = AtomicStoreBootstrapGraphControlEpochRepositoryV3(
                atomic_store=atomic
            ).refresh_current(request=request, current_epoch=epoch)
            epoch = refreshed.epoch
    elif outcome_kind == "lease_reclaimed":
        assert control.lease is not None
        clock[0] = control.lease.expires_at + timedelta(seconds=1)
        atomic.acquire_lease(
            operation_fence=marker.operation_fence_binding,
            writer_binding=control.writer_binding,
            execution_token="graph-reclaimed-execution",
            owner_id="graph-reclaimed-owner",
            duration=timedelta(minutes=10),
        )
        refreshed = AtomicStoreBootstrapGraphControlEpochRepositoryV3(
            atomic_store=atomic
        ).refresh_current(request=request, current_epoch=epoch)
        epoch = refreshed.epoch
    reduction_reload = atomic.reload_bootstrap_semantic_reduction_authority_v3(
        normalization_replay=fixture.replay
    )
    assert reduction_reload is not None
    operation_inputs = reduction_reload.authority_member.operation_inputs
    compilation = build_minimal_bootstrap_graph_plan_compilation_v3(
        request=request,
        snapshot=snapshot,
        policy=policy,
        capability_registry=capabilities,
        operation_inputs=operation_inputs,
        control_epoch=epoch,
        accepted_materialization=outcome_kind == "success",
    )
    commit_calls: list[tuple[str, str]] = []
    host_authority = build_bootstrap_graph_terminal_host_authority_v3(
        source=source,
        operation_fence_binding=marker.operation_fence_binding,
    )

    original_commit_or_reload = atomic.commit_or_reload_bootstrap_graph_group_v3

    def flaky_group_commit(*, request):
        commit_calls.append((request.transaction_group_id, request.request_ctv_digest))
        if outcome_kind == "related_conflict" and len(commit_calls) == 1:
            raise PreplanningStoreError("bootstrap graph group commit CAS conflicted")
        return original_commit_or_reload(request=request)

    monkeypatch.setattr(
        atomic,
        "commit_or_reload_bootstrap_graph_group_v3",
        flaky_group_commit,
    )
    coordinator = BootstrapGraphDependentCoordinatorV3(
        epoch_repository=AtomicStoreBootstrapGraphControlEpochRepositoryV3(
            atomic_store=atomic
        ),
        plan_repository=AtomicStoreBootstrapGraphPlanRepositoryV3(atomic_store=atomic),
        terminal_port=AtomicStoreBootstrapGraphTerminalPersistencePortV3(
            atomic_store=atomic
        ),
        compiler=DeterministicBootstrapGraphPlanCompilerV3(
            snapshot=snapshot,
            policy=policy,
            capability_registry=capabilities,
            operation_inputs=operation_inputs,
            accepted_materialization=outcome_kind == "success",
        ),
        authorizer=DeterministicBootstrapGraphPlanningAuthorizerV3(
            compilation=compilation
        ),
        group_commit_repository=AtomicStoreBootstrapGraphGroupCommitRepositoryV3(
            atomic_store=atomic
        ),
        terminal_preparer=DeterministicBootstrapGraphTerminalPreparationV3(),
        terminal_host_authority=host_authority,
    )

    if outcome_kind == "writer_changed":
        current_binding = control.writer_binding
        changed_binding = current_binding.model_copy(
            update={"admission_digest": "f" * 64}
        )
        monkeypatch.setattr(
            atomic._writers,
            "commit_binding",
            lambda _record: changed_binding,
        )
    elif outcome_kind == "writer_unavailable":
        def reject_current_writer(_binding):
            raise SemanticWriterAdmissionError("writer authority is unavailable")

        monkeypatch.setattr(atomic._writers, "require_current", reject_current_writer)

    result = coordinator.coordinate(request=request, transition=transition)

    if outcome_kind in {"writer_changed", "writer_unavailable"}:
        assert result.kind == "pre_graph_noncommit"
        assert result.reason == "authority_unavailable"
        assert commit_calls == []
        return
    if outcome_kind == "retry":
        assert result.kind == "durable_retry"
        repeat = coordinator.coordinate(request=request, transition=transition)
        assert repeat == result
        assert commit_calls == []
        return
    if outcome_kind == "related_conflict":
        assert len(commit_calls) == 2
        assert result.kind == "succeeded"
    else:
        assert result.kind == "succeeded"
    if outcome_kind == "success":
        snapshot_after_commit = atomic.graph_state_snapshot()
        assert tuple(
            item.payload_record_kind for item in snapshot_after_commit.records
        ) == ("provenance",)
        assert snapshot_after_commit.graph_revision != "genesis"
    repeat = coordinator.coordinate(request=request, transition=transition)
    assert repeat == result
    if outcome_kind == "success":
        assert len(commit_calls) == 1
    if outcome_kind == "related_conflict":
        assert len(commit_calls) == 2


def test_direct_provider_root_reaches_bootstrap_graph_terminal() -> None:
    normalization_builder, _calls = _v3_normalization_host_builder(
        proposal=ProviderSemanticProposal(
            mentions=(
                ProviderMention(
                    local_id="atlas", mention_quote="Atlas",
                    mention_context_quote="Atlas owner is Bob.",
                ),
                ProviderMention(
                    local_id="bob", mention_quote="Bob",
                    mention_context_quote="Atlas owner is Bob.",
                ),
            ),
            facts=(ProviderFact(
                local_id="owner", predicate_id="owner_is",
                subject_entity_ref="atlas", object=ProviderEntityObject(entity_ref="bob"),
                assertion_quote="Atlas owner is Bob.", predicate_anchor_quote="owner",
                polarity="positive", commitment="asserted",
            ),),
            abstained=False,
        )
    )
    graph_calls: list[str] = []
    plane = MemoryPlaneService()
    service = ProviderMemoryService._from_scenario_test_host(
        memory_plane=plane,
        now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=_built_in_local_capability(scenario_test=True),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        source_normalization_host_bundle_builder=normalization_builder,
        bootstrap_graph_host_bundle_builder=BootstrapGraphHostBundleBuilder(
            authority_provider=DeterministicBootstrapGraphAuthorityProviderV3(
                successful_calls=graph_calls
            )
        ),
    )

    result = service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.", operation_id="graph-root-success",
        task_id="task:one", user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )

    assert result.blocked_reasons
    assert len(graph_calls) == 1
    assert len(plane.list_records(
        source_kind="semantic_ingestion_bootstrap_graph_v3_terminal_locator"
    )) == 3
    repeat = service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.", operation_id="graph-root-success",
        task_id="task:one", user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    assert repeat == result
    assert len(graph_calls) == 1


def test_verified_production_root_leases_prepared_bytes_into_writer_handoff(monkeypatch) -> None:
    builder, _calls = _v3_normalization_host_builder(
        proposal=ProviderSemanticProposal(mentions=(), facts=(), abstained=True)
    )
    service = _build_production_scoped_provider_service(
        source_normalization_host_bundle_builder=builder,
    )
    observed = []
    atomic = service._provider_ingestion._atomic_store
    original = atomic.bootstrap_writer_handoff
    encoded_prepared = []
    encode = semantic_contracts.encode_semantic_contract

    def observe_encode(value):
        if type(value).__name__ == "PreparedSource":
            encoded_prepared.append(value)
        return encode(value)

    def observe(request, *, canonical_evidence_lease=None):
        assert canonical_evidence_lease is not None
        assert canonical_evidence_lease.result.member_evidence
        assert canonical_evidence_lease.scope.tenant
        assert canonical_evidence_lease.scope.operation == request.operation_fence_binding.operation_id
        assert canonical_evidence_lease.scope.generation == request.prepared_generation
        assert canonical_evidence_lease.scope.fence == request.operation_fence_binding.operation_fence_id
        assert canonical_evidence_lease.scope.writer
        observed.append(canonical_evidence_lease)
        encoded_before_handoff = len(encoded_prepared)
        outcome = original(request, canonical_evidence_lease=canonical_evidence_lease)
        assert len(encoded_prepared) == encoded_before_handoff
        return outcome

    monkeypatch.setattr(atomic, "bootstrap_writer_handoff", observe)
    monkeypatch.setattr(semantic_contracts, "encode_semantic_contract", observe_encode)
    service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.", operation_id="production-lease-root",
        task_id="task:scenario-task", user_id="user:scenario-user",
        session_id="session:scenario-session",
        authenticated_host_ingress=_host_ingress().model_copy(
            update={"provider_identity": "scenario-test-host"}
        ),
    )
    assert len(observed) == 1
    assert observed[0]._released
    terminal = observed[0]._owner.terminal_snapshot
    assert terminal is not None
    assert terminal.hits == 1
    assert terminal.released
    snapshots = service._canonical_closure_dispatcher.snapshots
    assert len(snapshots) == 1
    assert snapshots[0] == terminal
    assert "Atlas owner is Bob." not in repr(snapshots[0])


def test_verified_production_root_redelivery_uses_a_fresh_sealed_lease(monkeypatch) -> None:
    builder, _calls = _v3_normalization_host_builder(
        proposal=ProviderSemanticProposal(mentions=(), facts=(), abstained=True)
    )
    service = _build_production_scoped_provider_service(
        source_normalization_host_bundle_builder=builder,
    )
    atomic = service._provider_ingestion._atomic_store
    original_handoff = atomic.bootstrap_writer_handoff
    observed = []
    issuers = []
    requests = []
    current_calls = []
    admission_calls = []
    admission_differences = []
    original_current = atomic._writers.current
    original_publish = atomic.publish_admitted_source

    def observe_current():
        current_calls.append(None)
        return original_current()

    def observe_handoff(request, *, canonical_evidence_lease=None):
        assert canonical_evidence_lease is not None
        requests.append(request)
        binding = canonical_evidence_lease._owner.capability
        assert binding is not None
        issuers.append(binding.issuer)
        observed.append((canonical_evidence_lease, original_handoff(
            request, canonical_evidence_lease=canonical_evidence_lease
        )))
        return observed[-1][1]

    def observe_publish(*, prepared, writer_binding):
        admission_calls.append(prepared)
        if len(admission_calls) == 2:
            differences = []
            for expected in prepared.records:
                existing = service._memory_plane.get_record(expected.memory_id)
                if existing is None:
                    differences.append((expected.memory_id, "missing"))
                    continue
                existing_body = existing.model_dump(mode="python")
                expected_body = expected.model_dump(mode="python")
                changed = {
                    key: (existing_body[key], expected_body[key])
                    for key in expected_body
                    if existing_body[key] != expected_body[key]
                }
                if changed:
                    differences.append((existing.source_kind, existing.memory_id, changed))
            if differences:
                admission_differences.extend(differences)
        try:
            return original_publish(prepared=prepared, writer_binding=writer_binding)
        except PreplanningStoreError as exc:
            if admission_differences:
                exc.add_note(f"redelivery admission differences: {admission_differences!r}")
            raise

    monkeypatch.setattr(atomic._writers, "current", observe_current)
    monkeypatch.setattr(atomic, "bootstrap_writer_handoff", observe_handoff)
    monkeypatch.setattr(atomic, "publish_admitted_source", observe_publish)
    ingress = _host_ingress().model_copy(update={"provider_identity": "scenario-test-host"})
    kwargs = {
        "operation": ProviderOperation.CHAT_USER_TURN,
        "content": "Atlas owner is Bob.",
        "operation_id": "production-lease-redelivery",
        "task_id": "task:scenario-task",
        "user_id": "user:scenario-user",
        "session_id": "session:scenario-session",
        "timestamp": TEST_NOW,
        "authenticated_host_ingress": ingress,
    }
    service.sync_event(**kwargs)
    records_before = tuple(service._memory_plane.list_records(
        source_kind="semantic_ingestion_prepared_source"
    ))
    handoffs_before = tuple(service._memory_plane.list_records(
        source_kind="semantic_ingestion_bootstrap_handoff_marker"
    ))
    service.sync_event(**kwargs)
    assert admission_differences == []
    assert len(observed) == 2
    first_lease, first = observed[0]
    second_lease, second = observed[1]
    assert first.kind == "started"
    assert second.kind == "already_started"
    assert first_lease._owner is not second_lease._owner
    assert issuers[0] is not issuers[1]
    assert first_lease._released and second_lease._released
    assert first_lease._owner.terminal_snapshot is not None
    assert second_lease._owner.terminal_snapshot is not None
    assert first_lease._owner.terminal_snapshot.released
    assert second_lease._owner.terminal_snapshot.released
    assert len(current_calls) >= 2
    assert original_handoff(
        requests[1], canonical_evidence_lease=first_lease
    ).kind == "conflict"
    assert tuple(service._memory_plane.list_records(
        source_kind="semantic_ingestion_prepared_source"
    )) == records_before
    assert tuple(service._memory_plane.list_records(
        source_kind="semantic_ingestion_bootstrap_handoff_marker"
    )) == handoffs_before


def _graph_terminal_service(*, storage: Path | None = None) -> tuple[ProviderMemoryService, MemoryPlaneService]:
    normalization_builder, _calls = _v3_normalization_host_builder(
        proposal=ProviderSemanticProposal(
            mentions=(
                ProviderMention(local_id="atlas", mention_quote="Atlas", mention_context_quote="Atlas owner is Bob."),
                ProviderMention(local_id="bob", mention_quote="Bob", mention_context_quote="Atlas owner is Bob."),
            ),
            facts=(ProviderFact(local_id="owner", predicate_id="owner_is", subject_entity_ref="atlas", object=ProviderEntityObject(entity_ref="bob"), assertion_quote="Atlas owner is Bob.", predicate_anchor_quote="owner", polarity="positive", commitment="asserted"),),
            abstained=False,
        )
    )
    plane = MemoryPlaneService(
        record_store=None if storage is None else JsonlMemoryPlaneStore(storage)
    )
    service = ProviderMemoryService._from_scenario_test_host(
        memory_plane=plane,
        now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=_built_in_local_capability(scenario_test=True),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        source_normalization_host_bundle_builder=normalization_builder,
        bootstrap_graph_host_bundle_builder=BootstrapGraphHostBundleBuilder(
            authority_provider=DeterministicBootstrapGraphAuthorityProviderV3(
                successful_calls=[]
            )
        ),
    )
    return service, plane


def _sync_graph_terminal(service: ProviderMemoryService) -> None:
    result = service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.", operation_id="graph-terminal-reload",
        task_id="task:one", user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    assert result.blocked_reasons["semantic_ingestion"] == "source_only"


def _terminal_reload_material(plane: MemoryPlaneService):
    locator = next(
        record for record in plane.list_records(
            source_kind="semantic_ingestion_bootstrap_graph_v3_terminal_locator"
        )
        if "handoff_digest" in record.content
    )
    reload = BootstrapGraphTerminalReloadV3.model_validate(
        locator.content["reload"], strict=False
    )
    manifest = plane.get_record(reload.final_write_identity.member_manifest_id)
    assert manifest is not None
    coordinator_member = next(
        item for item in manifest.content["members"]
        if item["kind"] == "bootstrap_graph_coordinator_request"
    )
    payload = coordinator_member["canonical_payload"]
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    request = decode_semantic_contract(
        payload, BootstrapGraphDependentCoordinatorRequestV3
    )
    return locator, manifest, reload, request


def _corrupt_terminal_record(
    record, *, variant: str, locator_id: str, member_id: str, substitute_member: object,
):
    if variant == "removed_member" and record.memory_id == member_id:
        return None
    if variant == "substituted_member" and record.memory_id == member_id:
        return record.model_copy(update={
            "content": record.content | {"member": substitute_member},
        })
    if variant == "locator" and record.memory_id == locator_id:
        return record.model_copy(update={
            "content": record.content | {"locator_digest": "0" * 64},
        })
    return record


def _reload_terminal_by_recovery(service: ProviderMemoryService, plane: MemoryPlaneService):
    atomic = service._semantic_atomic_store
    recovery_index = plane.list_records(
        source_kind="semantic_ingestion_bootstrap_v3_recovery_index"
    )[0].content
    replay = atomic.reload_bootstrap_recovery_replay_v3(
        recovery_key_digest=recovery_index["recovery_key_digest"]
    )
    assert replay is not None
    marker = BootstrapWriterHandoffMarkerV3.model_validate(
        plane.list_records(source_kind="semantic_ingestion_bootstrap_handoff_marker")[0]
        .content["marker"]
    )
    ingress = service._resolve_ingress(_host_ingress())
    source = atomic.load_prepared_source(
        source_id=marker.source_id, source_digest=marker.source_digest,
    )
    assert ingress is not None and source is not None
    return atomic.reload_bootstrap_graph_terminal_by_recovery_v3(
        normalization_replay=replay,
        authenticated_ingress=ingress,
        required_outcome_scopes=source.governance_carrier_artifact.required_outcome_scopes,
        operation_fence_binding=marker.operation_fence_binding,
    )


def test_terminal_request_reload_rejects_in_memory_corrupt_closure(monkeypatch) -> None:
    service, plane = _graph_terminal_service()
    _sync_graph_terminal(service)
    locator, manifest, reload, request = _terminal_reload_material(plane)
    member = manifest.content["members"][0]
    substitute = manifest.content["members"][-1]
    member_id = (
        "semantic_ingestion:bootstrap-graph-v3:member:"
        f"{service._semantic_atomic_store.get_operation(request.initial_control_epoch.operation_fence_binding).persistence_namespace_id}:"
        f"{reload.final_write_identity.publication_operation_generation}:"
        f"{sha256(member['member_id'].encode('utf-8')).hexdigest()}"
    )
    original_get = plane.get_record
    for variant in ("removed_member", "substituted_member", "locator"):
        def corrupted_get(memory_id, *, _variant=variant):
            record = original_get(memory_id)
            return None if record is None else _corrupt_terminal_record(
                record,
                variant=_variant,
                locator_id=locator.memory_id,
                member_id=member_id,
                substitute_member=substitute,
            )

        monkeypatch.setattr(
            plane,
            "get_record",
            corrupted_get,
        )
        with pytest.raises(PreplanningStoreError, match="bootstrap graph terminal"):
            service._semantic_atomic_store.reload_bootstrap_graph_terminal_by_request_v3(
                request=request
            )
        with pytest.raises(PreplanningStoreError, match="bootstrap graph terminal"):
            _reload_terminal_by_recovery(service, plane)
    monkeypatch.setattr(plane, "get_record", original_get)


def test_terminal_request_reload_rejects_corrupt_jsonl_closure_after_reopen(tmp_path) -> None:
    for variant in ("removed_member", "substituted_member", "locator"):
        storage = tmp_path / variant
        service, plane = _graph_terminal_service(storage=storage)
        _sync_graph_terminal(service)
        locator, manifest, reload, request = _terminal_reload_material(plane)
        member = manifest.content["members"][0]
        substitute = manifest.content["members"][-1]
        namespace = service._semantic_atomic_store.get_operation(
            request.initial_control_epoch.operation_fence_binding
        ).persistence_namespace_id
        member_id = (
            "semantic_ingestion:bootstrap-graph-v3:member:"
            f"{namespace}:{reload.final_write_identity.publication_operation_generation}:"
            f"{sha256(member['member_id'].encode('utf-8')).hexdigest()}"
        )
        batches = [
            _PersistedBatch.model_validate_json(line)
            for line in (storage / "memory_records.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        rewritten = []
        for batch in batches:
            records = tuple(
                changed
                for record in batch.records
                if (changed := _corrupt_terminal_record(
                    record,
                    variant=variant,
                    locator_id=locator.memory_id,
                    member_id=member_id,
                    substitute_member=substitute,
                )) is not None
            )
            rewritten.append(_PersistedBatch.create(
                revision=batch.revision,
                data_revision=batch.data_revision,
                records=records,
            ))
        (storage / "memory_records.jsonl").write_text(
            "".join(batch.model_dump_json() + "\n" for batch in rewritten),
            encoding="utf-8",
        )
        reopened, _ = _graph_terminal_service(storage=storage)
        with pytest.raises(PreplanningStoreError, match="bootstrap graph terminal"):
            reopened._semantic_atomic_store.reload_bootstrap_graph_terminal_by_request_v3(
                request=request
            )




def _recovery_proposal() -> ProviderSemanticProposal:
    return ProviderSemanticProposal(
        mentions=(
            ProviderMention(
                local_id="atlas", mention_quote="Atlas",
                mention_context_quote="Atlas owner is Bob.",
            ),
            ProviderMention(
                local_id="bob", mention_quote="Bob",
                mention_context_quote="Atlas owner is Bob.",
            ),
        ),
        facts=(ProviderFact(
            local_id="owner", predicate_id="owner_is",
            subject_entity_ref="atlas", object=ProviderEntityObject(entity_ref="bob"),
            assertion_quote="Atlas owner is Bob.", predicate_anchor_quote="owner",
            polarity="positive", commitment="asserted",
        ),),
        abstained=False,
    )


def _delivery(service: ProviderMemoryService, operation_id: str):
    return service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.", operation_id=operation_id,
        task_id="task:one", user_id="user:alice",
        authenticated_host_ingress=_host_ingress().model_copy(
            update={"provider_identity": "scenario-test-host"}
        ),
    )


def _crash_once_after_handoff(monkeypatch, service: ProviderMemoryService) -> None:
    """Simulate a transport outage after the handoff marker and found index exist."""
    atomic = service._provider_ingestion._atomic_store
    original = atomic.reload_bootstrap_recovery_replay_v3
    state = {"crashed": False}

    def crash_once(**kwargs):
        if not state["crashed"]:
            state["crashed"] = True
            raise OSError("injected durable crash after handoff")
        return original(**kwargs)

    monkeypatch.setattr(atomic, "reload_bootstrap_recovery_replay_v3", crash_once)


def _interrupt_after_handoff(
    monkeypatch, service: ProviderMemoryService, operation_id: str,
) -> None:
    _crash_once_after_handoff(monkeypatch, service)
    first = _delivery(service, operation_id)
    monkeypatch.undo()
    # The injected outage must leave recoverable retained state rather than
    # any terminal outcome: handoff marker, found recovery index, and a
    # non-terminal preplanning control.
    assert (
        first.blocked_reasons["semantic_ingestion"]
        == "source_alignment_authority_unavailable"
    )
    controls = service._memory_plane.list_records(
        source_kind="semantic_ingestion_preplanning_control"
    )
    assert [c.content["control"]["state"] for c in controls] == ["preplanning"]
    assert service._memory_plane.list_records(
        source_kind="semantic_ingestion_bootstrap_handoff_marker"
    )
    index = service._memory_plane.list_records(
        source_kind="semantic_ingestion_bootstrap_v3_recovery_index"
    )[0]
    assert index.content["state"] == "found"


def _production_recovery_service(*, plane=None):
    builder, _calls = _v3_normalization_host_builder(proposal=_recovery_proposal())
    service = _build_production_scoped_provider_service(
        source_normalization_host_bundle_builder=builder,
        memory_plane=plane,
        now_provider=lambda: TEST_NOW,
    )
    return service


def _scenario_recovery_service(*, plane):
    builder, _calls = _v3_normalization_host_builder(proposal=_recovery_proposal())
    service = ProviderMemoryService._from_scenario_test_host(
        memory_plane=plane,
        now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=_built_in_local_capability(scenario_test=True),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        source_normalization_host_bundle_builder=builder,
    )
    return service


def test_redelivery_recovery_uses_fresh_owner_and_leases_exact_prepared_bytes(
    monkeypatch,
) -> None:
    service = _production_recovery_service()
    plane = service._memory_plane
    _interrupt_after_handoff(monkeypatch, service, "recovery-fresh-owner")

    from memorii.core.semantic_ingestion.canonical_evidence_arena import (
        CanonicalEvidenceArena,
    )

    constructed: list[CanonicalEvidenceArena] = []
    original_init = CanonicalEvidenceArena.__init__

    def observe_init(self, *args, **kwargs):
        constructed.append(self)
        return original_init(self, *args, **kwargs)

    monkeypatch.setattr(CanonicalEvidenceArena, "__init__", observe_init)

    atomic = service._provider_ingestion._atomic_store
    reload_captures: list[tuple[object, object, object]] = []
    original_reload = atomic.reload_bootstrap_recovery_replay_v3

    def observe_reload(*, recovery_key_digest, canonical_evidence_lease=None,
                       handoff_marker=None, authenticated_ingress=None):
        reload_captures.append(
            (canonical_evidence_lease, handoff_marker, authenticated_ingress)
        )
        encodes_at_lease.append(len(prepared_encodes))
        return original_reload(
            recovery_key_digest=recovery_key_digest,
            canonical_evidence_lease=canonical_evidence_lease,
            handoff_marker=handoff_marker,
            authenticated_ingress=authenticated_ingress,
        )

    monkeypatch.setattr(
        atomic, "reload_bootstrap_recovery_replay_v3", observe_reload
    )

    prepared_encodes: list[object] = []
    encodes_at_lease: list[int] = []
    encode = semantic_contracts.encode_semantic_contract

    def observe_encode(value):
        if type(value).__name__ == "PreparedSource":
            prepared_encodes.append(value)
        return encode(value)

    monkeypatch.setattr(semantic_contracts, "encode_semantic_contract", observe_encode)

    snapshots_before = len(service._canonical_closure_dispatcher.snapshots)
    recovered = _delivery(service, "recovery-fresh-owner")

    assert recovered.blocked_reasons["semantic_ingestion"] == "source_only"
    assert len(constructed) == 1
    assert len(reload_captures) == 1
    lease, marker, ingress = reload_captures[0]
    assert lease is not None and marker is not None and ingress is not None
    assert lease.result.member_evidence
    assert lease.scope.operation == marker.operation_fence_binding.operation_id
    assert lease.scope.generation == marker.prepared_generation
    assert lease.scope.fence == marker.operation_fence_binding.operation_fence_id
    assert (
        lease.scope.tenant
        == ingress.delivery_principal_binding.tenant_partition_id
    )
    current = service._provider_ingestion._writer_admission.current()
    assert lease.scope.writer == f"{current.admission_digest}:{current.writer_epoch}"
    assert lease._released
    terminal = lease._owner.terminal_snapshot
    assert terminal is not None
    assert terminal.mode == "enabled"
    assert terminal.released
    assert "Atlas owner is Bob." not in repr(terminal)
    snapshots = service._canonical_closure_dispatcher.snapshots
    assert len(snapshots) == snapshots_before + 1
    assert snapshots[-1] == terminal
    # The leased bytes carry all downstream reconstruction: no plain-path
    # re-encode of the prepared source happens after the sealed lease
    # reaches the replay reload consumer.
    assert len(prepared_encodes) == encodes_at_lease[0]
    assert plane.list_records(
        source_kind="semantic_ingestion_preplanning_control"
    )[0].content["control"]["state"] == "terminal"

    # A third exact delivery is a completed lost-ack idempotent replay: it
    # must not reconstruct any new graph effect or duplicate the terminal.
    third = _delivery(service, "recovery-fresh-owner")
    assert third == recovered
    assert len(constructed) == 2
    assert plane.list_records(
        source_kind="semantic_ingestion_bootstrap_graph_v3_terminal_locator"
    ).__len__() == 3


def test_redelivery_recovery_rejects_mutated_lease_coordinates(monkeypatch) -> None:
    service = _production_recovery_service()
    plane = service._memory_plane
    _interrupt_after_handoff(monkeypatch, service, "recovery-coordinate-mutations")

    atomic = service._provider_ingestion._atomic_store
    probe_results: dict[str, object] = {}
    drained: list[tuple[object, object, object]] = []
    original_reload = atomic.reload_bootstrap_recovery_replay_v3

    def probe(recovery_key_digest, lease, marker, ingress):
        return original_reload(
            recovery_key_digest=recovery_key_digest,
            canonical_evidence_lease=lease,
            handoff_marker=marker,
            authenticated_ingress=ingress,
        )

    def observe_reload(*, recovery_key_digest, canonical_evidence_lease=None,
                       handoff_marker=None, authenticated_ingress=None):
        # Every foreign-coordinate probe must fail closed before any replay
        # reconstruction; these probes run while the lease is still held.
        marker = handoff_marker
        ingress = authenticated_ingress
        fence = marker.operation_fence_binding
        probes = {
            "foreign_generation": (
                marker.model_copy(
                    update={"prepared_generation": marker.prepared_generation + 1}
                ),
                ingress,
            ),
            "foreign_fence": (
                marker.model_copy(update={
                    "operation_fence_binding": fence.model_copy(
                        update={"operation_fence_id": fence.operation_fence_id + ":foreign"}
                    )
                }),
                ingress,
            ),
            "foreign_operation": (
                marker.model_copy(update={
                    "operation_fence_binding": fence.model_copy(
                        update={"operation_id": fence.operation_id + ":foreign"}
                    )
                }),
                ingress,
            ),
            "foreign_writer": (
                marker.model_copy(update={
                    "writer_commit_binding": marker.writer_commit_binding.model_copy(
                        update={"admission_digest": "0" * 64}
                    )
                }),
                ingress,
            ),
            "foreign_tenant": (
                marker,
                ingress.model_copy(update={
                    "delivery_principal_binding": (
                        ingress.delivery_principal_binding.model_copy(
                            update={"tenant_partition_id": "foreign-tenant"}
                        )
                    )
                }),
            ),
        }
        for name, (marker_override, ingress_override) in probes.items():
            probe_results[name] = probe(
                recovery_key_digest, canonical_evidence_lease,
                marker_override, ingress_override,
            )
        drained.append((canonical_evidence_lease, handoff_marker, authenticated_ingress))
        return original_reload(
            recovery_key_digest=recovery_key_digest,
            canonical_evidence_lease=canonical_evidence_lease,
            handoff_marker=handoff_marker,
            authenticated_ingress=authenticated_ingress,
        )

    monkeypatch.setattr(
        atomic, "reload_bootstrap_recovery_replay_v3", observe_reload
    )
    recovered = _delivery(service, "recovery-coordinate-mutations")
    assert recovered.blocked_reasons["semantic_ingestion"] == "source_only"

    assert probe_results and all(
        result is None for result in probe_results.values()
    ), probe_results
    lease, marker, ingress = drained[0]
    assert lease._released

    # The drained lease itself can no longer authorize a replay reload.
    recovery_index = plane.list_records(
        source_kind="semantic_ingestion_bootstrap_v3_recovery_index"
    )[0].content
    assert original_reload(
        recovery_key_digest=recovery_index["recovery_key_digest"],
        canonical_evidence_lease=lease,
        handoff_marker=marker,
        authenticated_ingress=ingress,
    ) is None


def test_redelivery_recovery_outcomes_are_identical_across_enabled_and_disabled_modes(
    monkeypatch, tmp_path,
) -> None:
    enabled_plane = MemoryPlaneService(
        record_store=JsonlMemoryPlaneStore(tmp_path / "enabled")
    )
    disabled_plane = MemoryPlaneService(
        record_store=JsonlMemoryPlaneStore(tmp_path / "disabled")
    )
    enabled_service = _production_recovery_service(plane=enabled_plane)
    disabled_service = _scenario_recovery_service(plane=disabled_plane)
    _interrupt_after_handoff(monkeypatch, enabled_service, "recovery-mode-parity")
    _interrupt_after_handoff(monkeypatch, disabled_service, "recovery-mode-parity")

    enabled_recovered = _delivery(enabled_service, "recovery-mode-parity")
    disabled_recovered = _delivery(disabled_service, "recovery-mode-parity")
    assert (
        enabled_recovered.blocked_reasons["semantic_ingestion"]
        == disabled_recovered.blocked_reasons["semantic_ingestion"]
        == "source_only"
    )
    enabled_again = _delivery(enabled_service, "recovery-mode-parity")
    disabled_again = _delivery(disabled_service, "recovery-mode-parity")
    assert enabled_again == enabled_recovered
    assert disabled_again == disabled_recovered

    def durable_projection(plane: MemoryPlaneService):
        projection: dict[str, object] = {}
        for record in plane.list_records():
            projection.setdefault(record.source_kind, 0)
            projection[record.source_kind] += 1
        return projection

    enabled_projection = durable_projection(enabled_plane)
    disabled_projection = durable_projection(disabled_plane)
    assert enabled_projection == disabled_projection
    # Record bytes embed material-derived identities (source ids, preparation
    # fingerprints), so cross-material byte equality is not a well-formed
    # claim; structural, outcome, and idempotence parity above carry the
    # mode-equivalence projection, and byte-level substitution equality is
    # proven inside the lease consumers of the sibling recovery proofs.
    enabled_index = enabled_plane.list_records(
        source_kind="semantic_ingestion_bootstrap_v3_recovery_index"
    )[0].content
    disabled_index = disabled_plane.list_records(
        source_kind="semantic_ingestion_bootstrap_v3_recovery_index"
    )[0].content
    assert enabled_index["state"] == disabled_index["state"] == "found"
