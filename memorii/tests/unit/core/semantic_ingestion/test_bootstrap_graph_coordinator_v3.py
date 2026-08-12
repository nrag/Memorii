"""Coordinator retry proof using the real direct-provider recovery reload."""

from __future__ import annotations

from datetime import timedelta
from hashlib import sha256
from pathlib import Path

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
    BootstrapGraphV3ProducerUnavailable,
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
    DeterministicBootstrapGraphSuccessfulExecutorV3,
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
    successful_calls: list[str] = []
    unavailable_calls: list[str] = []
    host_authority = build_bootstrap_graph_terminal_host_authority_v3(
        source=source,
        operation_fence_binding=marker.operation_fence_binding,
    )
    successful_executor = DeterministicBootstrapGraphSuccessfulExecutorV3(
        host_authority=host_authority,
        calls=successful_calls,
    )

    class ConflictThenSuccessExecutor:
        def __init__(self, delegate) -> None:
            self.calls = 0
            self.delegate = delegate

        def execute_cas(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                cas_request = kwargs["request"]
                return BootstrapGraphV3ProducerUnavailable.create(
                    phase="group_execute",
                    reason="read_conflict",
                    request_digest=cas_request.request_digest,
                    control_epoch_digest=kwargs["control_epoch"].epoch_digest,
                )
            return self.delegate.execute_cas(**kwargs)

    conflict_executor = ConflictThenSuccessExecutor(successful_executor)
    exhausted_executor = ConflictThenSuccessExecutor(
        DeterministicBootstrapGraphSuccessfulExecutorV3(
            host_authority=host_authority,
            calls=successful_calls,
            disposition="failed",
            terminal_status="failed",
            final_status="failed",
            not_applicable_reason="failed",
        )
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
        assert successful_calls == []
        assert unavailable_calls == []
        return
    if outcome_kind == "retry":
        assert result.kind == "durable_retry"
        repeat = coordinator.coordinate(request=request, transition=transition)
        assert repeat == result
        assert len(unavailable_calls) == 1
        return
    assert result.kind == (
        "finalized_failure" if outcome_kind == "exhausted_conflict" else "succeeded"
    )
    assert len(successful_calls) == (0 if outcome_kind == "success" else 1)
    if outcome_kind == "success":
        snapshot_after_commit = atomic.graph_state_snapshot()
        assert tuple(
            item.payload_record_kind for item in snapshot_after_commit.records
        ) == ("provenance",)
        assert snapshot_after_commit.graph_revision != "genesis"
    if outcome_kind == "related_conflict":
        assert conflict_executor.calls == 2
    if outcome_kind == "exhausted_conflict":
        assert exhausted_executor.calls == 2
    repeat = coordinator.coordinate(request=request, transition=transition)
    assert repeat == result
    assert len(successful_calls) == (0 if outcome_kind == "success" else 1)


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

    assert result.blocked_reasons["semantic_ingestion"] == "source_only"
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
