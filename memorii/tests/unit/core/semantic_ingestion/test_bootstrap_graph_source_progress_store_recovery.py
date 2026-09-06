"""Real-store recovery proof for the native Bootstrap V3 progress member."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from hashlib import sha256
from pathlib import Path

import pytest
from memorii.core.memory_evolution.atomic_store import (
    BootstrapGraphSourceProgressRecoveryUnavailableError,
    BootstrapWriterHandoffMarkerV3,
    PreplanningStoreError,
    SemanticIngestionAtomicStore,
)
from memorii.core.memory_evolution.writer_admission import (
    SemanticWriterAdmissionStore,
    bounded_preplanning_ownership_manifest,
)
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import JsonlMemoryPlaneStore
from memorii.core.provider.models import ProviderOperation
from memorii.core.provider.service import ProviderMemoryService
from memorii.core.semantic_ingestion.bootstrap_graph_host import (
    BootstrapGraphAuthorityRequestV3,
    BootstrapGraphHostBundleBuilder,
)
from memorii.core.semantic_ingestion.bootstrap_graph_repository import (
    AtomicStoreBootstrapGraphControlEpochRepositoryV3,
    AtomicStoreBootstrapGraphPlanRepositoryV3,
)
from memorii.core.semantic_ingestion.contracts import (
    BootstrapGraphAtomicMemberReferenceV3,
    BootstrapGraphControlEpochV3,
    BootstrapGraphCurrentGenerationV3,
    BootstrapGraphObservedCountersV3,
    BootstrapGraphPlanAtomicMemberV3,
    BootstrapGraphPlanAtomicWriteRequestV3,
    BootstrapGraphPlannedProgressV3,
    ProviderEntityObject,
    ProviderFact,
    ProviderMention,
    ProviderSemanticProposal,
    decode_bootstrap_graph_atomic_member_payload_v3,
    encode_bootstrap_graph_atomic_member_payload_v3,
)
from tests.fixtures.semantic_ingestion.bootstrap_graph_v3_fixture import (
    DeterministicBootstrapGraphAuthorityProviderV3,
    build_persisted_bootstrap_graph_replay_fixture,
)
from tests.unit.core.semantic_ingestion.test_semantic_provider_composition import (
    TEST_NOW,
    DeterministicTestHostBootstrapMaterialVerifier,
    _built_in_local_capability,
    _host_ingress,
    _v3_normalization_host_builder,
)


def _publish_live_progress(*, path: Path | None = None, coordinate: bool = True):
    """Publish plan/attempt/lineage through the real coordinator and stop at retry.

    The injected group-store failure happens only after the lineage checkpoint; it
    keeps the original lease current while avoiding a terminal publication.
    """
    builder, _ = _v3_normalization_host_builder(
        proposal=ProviderSemanticProposal(
            mentions=(
                ProviderMention(local_id="atlas", mention_quote="Atlas", mention_context_quote="Atlas owner is Bob."),
                ProviderMention(local_id="bob", mention_quote="Bob", mention_context_quote="Atlas owner is Bob."),
            ),
            facts=(
                ProviderFact(
                    local_id="owner", predicate_id="owner_is",
                    subject_entity_ref="atlas", object=ProviderEntityObject(entity_ref="bob"),
                    assertion_quote="Atlas owner is Bob.", predicate_anchor_quote="owner",
                    polarity="positive", commitment="asserted",
                ),
            ),
            abstained=False,
        )
    )
    plane = MemoryPlaneService(
        record_store=None if path is None else JsonlMemoryPlaneStore(path)
    )
    class UnavailableAuthority:
        def acquire(self, **_kwargs):
            return None

    service = ProviderMemoryService._from_scenario_test_host(
        memory_plane=plane,
        now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=_built_in_local_capability(scenario_test=True),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        source_normalization_host_bundle_builder=builder,
        bootstrap_graph_host_bundle_builder=BootstrapGraphHostBundleBuilder(
            authority_provider=UnavailableAuthority()
        ),
    )
    atomic = service._semantic_atomic_store

    def stop_after_lineage(*, request):
        raise PreplanningStoreError("bootstrap graph group commit storage unavailable")

    # First publish source-normalization authority only.  The direct V3
    # coordinator below is the real persistence owner and avoids provider
    # recovery retries obscuring this storage-level proof.
    service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.", operation_id="source-progress-store-proof",
        task_id="task:source-progress", user_id="user:source-progress",
        authenticated_host_ingress=_host_ingress(),
    )
    marker_record = plane.list_records(
        source_kind="semantic_ingestion_bootstrap_handoff_marker"
    )[0]
    marker = BootstrapWriterHandoffMarkerV3.model_validate(marker_record.content["marker"])
    control = atomic.get_operation(marker.operation_fence_binding)
    lease = atomic.lease_binding(control)
    ingress = service._resolve_ingress(_host_ingress())
    assert ingress is not None
    source = atomic.load_prepared_source(source_id=marker.source_id, source_digest=marker.source_digest)
    assert source is not None
    recovery_key = plane.list_records(
        source_kind="semantic_ingestion_bootstrap_v3_recovery_index"
    )[0].content["recovery_key_digest"]
    fixture = build_persisted_bootstrap_graph_replay_fixture(
        recovery_repository=atomic, recovery_key_digest=recovery_key,
        delivery_principal_binding_digest=ingress.delivery_principal_binding.binding_digest,
        required_outcome_scopes=source.governance_carrier_artifact.required_outcome_scopes,
        operation_fence_binding=marker.operation_fence_binding,
        operation_lease_binding=lease, writer_commit_binding=control.writer_binding,
        control_epoch=ingress,
    )
    atomic.commit_or_reload_bootstrap_graph_group_v3 = stop_after_lineage  # type: ignore[method-assign]
    execution = DeterministicBootstrapGraphAuthorityProviderV3(successful_calls=[]).acquire(
        request=BootstrapGraphAuthorityRequestV3(
            normalization_replay=fixture.replay, prepared_source=source,
            required_outcome_scopes=source.governance_carrier_artifact.required_outcome_scopes,
            operation_fence_binding=marker.operation_fence_binding,
            operation_lease_binding=lease, writer_commit_binding=control.writer_binding,
        ),
        atomic_store=atomic,
    )
    assert execution is not None
    if coordinate:
        execution.coordinator.coordinate(
            request=execution.request, transition=execution.transition
        )
    epoch_record = plane.list_records(
        source_kind="semantic_ingestion_bootstrap_graph_v3_epoch"
    )[-1]
    epoch = BootstrapGraphControlEpochV3.model_validate_json(
        json.dumps(epoch_record.content["epoch"])
    )
    return service, plane, atomic, marker, epoch, execution.request


def _reload(atomic, marker, epoch, request):
    return AtomicStoreBootstrapGraphPlanRepositoryV3(atomic_store=atomic).reload_progress_for_original_fence(
        operation_fence_binding=epoch.operation_fence_binding,
        delivery_principal_binding_digest=epoch.delivery_principal_binding_digest,
        required_outcome_scopes=request.required_outcome_scopes,
        control_epoch=epoch,
        operation_lease_binding=epoch.operation_lease_binding,
        writer_commit_binding=epoch.writer_commit_binding,
    )


def _reload_closure(atomic, epoch, request):
    return AtomicStoreBootstrapGraphPlanRepositoryV3(atomic_store=atomic).reload_resume_closure_for_original_fence(
        operation_fence_binding=epoch.operation_fence_binding,
        delivery_principal_binding_digest=epoch.delivery_principal_binding_digest,
        required_outcome_scopes=request.required_outcome_scopes,
        control_epoch=epoch,
        operation_lease_binding=epoch.operation_lease_binding,
        writer_commit_binding=epoch.writer_commit_binding,
    )


def _latest_lineage_request(plane) -> BootstrapGraphPlanAtomicWriteRequestV3:
    manifests = plane.list_records(source_kind="semantic_ingestion_bootstrap_graph_v3_manifest")
    for record in reversed(manifests):
        request = BootstrapGraphPlanAtomicWriteRequestV3.model_validate_json(
            json.dumps(record.content["request"])
        )
        if request.kind == "bootstrap_graph_lineage_checkpoint":
            return request
    raise AssertionError("lineage checkpoint was not published")


def _request_with_member_payload(
    request: BootstrapGraphPlanAtomicWriteRequestV3, *, member_id: str, payload: bytes,
) -> BootstrapGraphPlanAtomicWriteRequestV3:
    old = next(item for item in request.members if item.member_id == member_id)
    replacement = BootstrapGraphPlanAtomicMemberV3.create(
        member_id=old.member_id, kind=old.kind, canonical_payload=payload,
        payload_digest=sha256(payload).hexdigest(),
    )
    members = tuple(sorted(
        (replacement if item.member_id == member_id else item for item in request.members),
        key=lambda item: item.member_id,
    ))
    values = request.model_dump(mode="python")
    values.pop("schema_version")
    values.pop("write_digest")
    return BootstrapGraphPlanAtomicWriteRequestV3.create(
        **(values | {
            "members": members,
            "required_member_digests": tuple(sorted(item.member_digest for item in members)),
        })
    )


def _request_with_member_payloads(request, payloads: dict[str, bytes]):
    updated = request
    for member_id, payload in payloads.items():
        updated = _request_with_member_payload(updated, member_id=member_id, payload=payload)
    return updated


@pytest.fixture(scope="module")
def live_progress():
    """Amortize the real plan/attempt/lineage publication across memory cases."""
    return _publish_live_progress()


def test_memory_found_first_and_lost_ack_reload_exact_committed_progress_bytes(live_progress) -> None:
    _service, plane, atomic, marker, epoch, _request = live_progress
    request = _latest_lineage_request(plane)
    member = next(item for item in request.members if item.member_id == "source-progress")
    expected = decode_bootstrap_graph_atomic_member_payload_v3(
        kind=member.kind, raw=member.canonical_payload
    )
    first = _reload(atomic, marker, epoch, _request)
    second = _reload(atomic, marker, epoch, _request)
    assert first.model_dump(mode="json") == expected
    assert second.model_dump(mode="json") == expected
    assert first is not second


def test_jsonl_reopen_returns_exact_progress_bytes(tmp_path: Path) -> None:
    path = tmp_path / "progress-jsonl"
    _service, plane, atomic, marker, epoch, _request = _publish_live_progress(path=path)
    expected = _reload(atomic, marker, epoch, _request).model_dump(mode="json")
    reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
    reopened_atomic = SemanticIngestionAtomicStore(
        reopened_plane,
        SemanticWriterAdmissionStore(
            reopened_plane, bounded_preplanning_ownership_manifest(),
            now_provider=lambda: TEST_NOW,
        ),
        now_provider=lambda: TEST_NOW,
    )
    assert _reload(reopened_atomic, marker, epoch, _request).model_dump(mode="json") == expected


def test_resume_closure_returns_exact_persisted_members(live_progress) -> None:
    _service, plane, atomic, _marker, epoch, request = live_progress
    closure = _reload_closure(atomic, epoch, request)
    latest = _latest_lineage_request(plane)
    by_id = {member.member_id: member for member in latest.members}
    assert closure.progress.raw == by_id["source-progress"].canonical_payload
    assert closure.plan.raw == by_id["plan"].canonical_payload
    assert closure.replay_bundle.raw == by_id["replay-bundle"].canonical_payload
    assert closure.observed_counters.raw == by_id["observed-counters"].canonical_payload
    assert closure.attempt_inputs.raw == by_id["attempt-inputs"].canonical_payload
    assert closure.authority.raw == by_id["successor-authority"].canonical_payload
    assert closure.attempt.raw == by_id["attempt"].canonical_payload
    assert closure.lineage.raw == by_id["lineage"].canonical_payload
    assert tuple(item.member.member_id for item in closure.authorizations) == tuple(
        member.member_id for member in latest.members if member.member_id.startswith("authorization:")
    )
    assert closure.pre_execution_evidence
    assert all(item.generation < closure.progress.generation for item in closure.pre_execution_evidence)


def test_resume_closure_rejects_missing_member_record(live_progress) -> None:
    _service, plane, atomic, _marker, epoch, request = live_progress
    store = plane._records  # type: ignore[attr-defined]
    closure = _reload_closure(atomic, epoch, request)
    record = next(
        item for item in plane.list_records(source_kind="semantic_ingestion_bootstrap_graph_v3_member")
        if (
            item.content["member"]["member_id"] == "lineage"
            and f":{closure.lineage.generation}:" in item.memory_id
        )
    )
    # This is an adversarial persistence mutation, not an API operation. Hold
    # the in-memory store's normal lock and restore the exact mapping so the
    # module-scoped real-store fixture cannot leak corruption to later tests.
    with store._lock:  # type: ignore[attr-defined]
        before = dict(store._records)  # type: ignore[attr-defined]
        store._records.pop(record.memory_id)  # type: ignore[attr-defined]
    try:
        with pytest.raises(PreplanningStoreError, match="member record is substituted"):
            _reload_closure(atomic, epoch, request)
    finally:
        with store._lock:  # type: ignore[attr-defined]
            store._records = before  # type: ignore[attr-defined]
    with store._lock:  # type: ignore[attr-defined]
        assert store._records == before  # type: ignore[attr-defined]


def test_identical_requests_converge_and_stale_predecessor_conflicts(live_progress) -> None:
    _service, plane, atomic, marker, epoch, _request = live_progress
    request = _latest_lineage_request(plane)
    repository = AtomicStoreBootstrapGraphPlanRepositoryV3(atomic_store=atomic)
    with ThreadPoolExecutor(max_workers=2) as pool:
        reloads = tuple(pool.map(
            lambda _: repository.publish_and_reload(
                request=request,
                delivery_principal_binding_digest=epoch.delivery_principal_binding_digest,
                required_outcome_scopes=_request.required_outcome_scopes,
                control_epoch=epoch,
            ),
            range(2),
        ))
    assert reloads[0].core == reloads[1].core
    # A byte-identical payload with a new write identity cannot claim an old
    # predecessor once the lineage generation has been sealed.
    conflicting_values = request.model_dump(mode="python")
    conflicting_values.pop("schema_version")
    conflicting_values.pop("write_digest")
    predecessor_values = conflicting_values["predecessor_generation"] | {
        "store_identity_digest": "e" * 64
    }
    predecessor_values.pop("schema_version")
    predecessor_values.pop("snapshot_digest")
    predecessor = BootstrapGraphCurrentGenerationV3.create(**predecessor_values)
    conflicting = BootstrapGraphPlanAtomicWriteRequestV3.create(
        **(conflicting_values | {"predecessor_generation": predecessor})
    )
    with pytest.raises(PreplanningStoreError, match="generation is stale"):
        repository.publish_and_reload(
            request=conflicting,
            delivery_principal_binding_digest=epoch.delivery_principal_binding_digest,
            required_outcome_scopes=_request.required_outcome_scopes,
            control_epoch=epoch,
        )


def test_store_rejects_duplicate_progress_member_before_visibility(live_progress) -> None:
    _service, plane, atomic, _marker, epoch, _request = live_progress
    request = _latest_lineage_request(plane)
    duplicate_values = request.model_dump(mode="python")
    duplicate_values.pop("schema_version")
    duplicate_values.pop("write_digest")
    before = tuple(plane.list_records())
    with pytest.raises(ValueError, match="atomic write closure is invalid"):
        BootstrapGraphPlanAtomicWriteRequestV3.create(**(duplicate_values | {
            "members": (*request.members, request.members[0]),
            "required_member_digests": tuple(sorted(
                (*request.required_member_digests, request.members[0].member_digest)
            )),
        }))
    assert tuple(plane.list_records()) == before


def test_reclaimed_lease_reloads_the_sealed_predecessor() -> None:
    _service, _plane, atomic, marker, epoch, request = _publish_live_progress()
    control = atomic.get_operation(marker.operation_fence_binding)
    assert control.lease is not None
    # The store owns its clock boundary; advance only that deterministic test
    # clock, then use the normal lease-acquire and epoch-refresh APIs.
    atomic._now = lambda: control.lease.expires_at + timedelta(seconds=1)  # type: ignore[method-assign]
    atomic.acquire_lease(
        operation_fence=marker.operation_fence_binding,
        writer_binding=control.writer_binding,
        execution_token="source-progress-reclaimed-execution",
        owner_id="source-progress-reclaimed-owner",
        duration=timedelta(minutes=10),
    )
    refreshed = AtomicStoreBootstrapGraphControlEpochRepositoryV3(
        atomic_store=atomic
    ).refresh_current(request=request, current_epoch=epoch)
    assert _reload(atomic, marker, refreshed.epoch, request).kind == "planned"


def test_prebridge_generation_is_typed_unavailable_without_writes() -> None:
    _service, plane, atomic, marker, epoch, _request = _publish_live_progress(
        coordinate=False
    )
    before = tuple(plane.list_records())
    with pytest.raises(BootstrapGraphSourceProgressRecoveryUnavailableError):
        _reload(atomic, marker, epoch, _request)
    assert tuple(plane.list_records()) == before


@pytest.mark.parametrize(
    "interrupted_kind",
    ("bootstrap_graph_plan_checkpoint", "bootstrap_graph_attempt_checkpoint"),
)
def test_exact_checkpoint_resume_advances_only_the_next_native_transition(
    interrupted_kind: str,
) -> None:
    """A retained checkpoint resumes without recompiling or republishing it."""
    _service, plane, _atomic, _marker, _epoch, request = _publish_live_progress(
        coordinate=False
    )
    execution = DeterministicBootstrapGraphAuthorityProviderV3(
        successful_calls=[]
    )
    # The helper deliberately constructs the real coordinator but does not
    # expose it. Reacquire the retained execution bundle through the actual
    # source/authority boundary rather than fabricating a checkpoint request.
    del execution
    # `_publish_live_progress` has already acquired this real V3 bundle; the
    # plan manifests are still empty until we invoke the production coordinator.
    # Rebuild only its authority bundle from the persisted source, as a process
    # restart would do.
    source = _atomic.load_prepared_source(
        source_id=request.initial_control_epoch.source_id,
        source_digest=request.initial_control_epoch.source_digest,
    )
    assert source is not None
    fixture = build_persisted_bootstrap_graph_replay_fixture(
        recovery_repository=_atomic,
        recovery_key_digest=plane.list_records(
            source_kind="semantic_ingestion_bootstrap_v3_recovery_index"
        )[0].content["recovery_key_digest"],
        delivery_principal_binding_digest=request.delivery_principal_binding_digest,
        required_outcome_scopes=request.required_outcome_scopes,
        operation_fence_binding=request.initial_control_epoch.operation_fence_binding,
        operation_lease_binding=request.initial_control_epoch.operation_lease_binding,
        writer_commit_binding=request.initial_control_epoch.writer_commit_binding,
        control_epoch=request.initial_control_epoch,
    )
    bundle = DeterministicBootstrapGraphAuthorityProviderV3(successful_calls=[]).acquire(
        request=BootstrapGraphAuthorityRequestV3(
            normalization_replay=fixture.replay,
            prepared_source=source,
            required_outcome_scopes=request.required_outcome_scopes,
            operation_fence_binding=request.initial_control_epoch.operation_fence_binding,
            operation_lease_binding=request.initial_control_epoch.operation_lease_binding,
            writer_commit_binding=request.initial_control_epoch.writer_commit_binding,
        ),
        atomic_store=_atomic,
    )
    assert bundle is not None
    coordinator = bundle.coordinator
    original_publish = coordinator._plans.publish_and_reload  # type: ignore[attr-defined]
    interrupted = False

    def interrupt_after_persist(*, request, **kwargs):
        nonlocal interrupted
        reload = original_publish(request=request, **kwargs)
        if request.kind == interrupted_kind and not interrupted:
            interrupted = True
            raise PreplanningStoreError("injected native checkpoint interruption")
        return reload

    coordinator._plans.publish_and_reload = interrupt_after_persist  # type: ignore[method-assign]
    with pytest.raises(PreplanningStoreError, match="native checkpoint interruption"):
        coordinator.coordinate(request=bundle.request, transition=bundle.transition)
    coordinator._plans.publish_and_reload = original_publish  # type: ignore[method-assign]

    current_epoch = BootstrapGraphControlEpochV3.model_validate_json(json.dumps(
        plane.list_records(source_kind="semantic_ingestion_bootstrap_graph_v3_epoch")[-1]
        .content["epoch"]
    ))
    checkpoint = coordinator._plans.reload_checkpoint_for_resume(
        operation_fence_binding=current_epoch.operation_fence_binding,
        delivery_principal_binding_digest=bundle.request.delivery_principal_binding_digest,
        required_outcome_scopes=bundle.request.required_outcome_scopes,
        control_epoch=current_epoch,
        operation_lease_binding=current_epoch.operation_lease_binding,
        writer_commit_binding=current_epoch.writer_commit_binding,
    )
    assert checkpoint.progress.artifact.kind == {
        "bootstrap_graph_plan_checkpoint": "plan_published",
        "bootstrap_graph_attempt_checkpoint": "attempt_published",
    }[interrupted_kind]
    coordinator.coordinate(request=bundle.request, transition=bundle.transition)
    manifests = tuple(
        BootstrapGraphPlanAtomicWriteRequestV3.model_validate_json(
            json.dumps(record.content["request"])
        )
        for record in plane.list_records(
            source_kind="semantic_ingestion_bootstrap_graph_v3_manifest"
        )
    )
    kinds = tuple(item.kind for item in manifests)
    assert kinds.count("bootstrap_graph_plan_checkpoint") == 1
    assert kinds.count("bootstrap_graph_attempt_checkpoint") == 1
    assert kinds.count("bootstrap_graph_lineage_checkpoint") == 1


@pytest.mark.parametrize("mutation", ("substituted", "future"))
def test_store_rejects_progress_reference_substitution_before_visibility(
    live_progress, mutation: str,
) -> None:
    _service, plane, atomic, _marker, epoch, _request = live_progress
    request = _latest_lineage_request(plane)
    member = next(item for item in request.members if item.member_id == "source-progress")
    payload = decode_bootstrap_graph_atomic_member_payload_v3(kind=member.kind, raw=member.canonical_payload)
    reference = payload["plan_reference"]
    reference_values = reference | {
        "artifact_digest": "f" * 64
        if mutation == "substituted" else reference["artifact_digest"],
        "generation": request.publication_operation_generation + 1
        if mutation == "future" else reference["generation"],
    }
    reference_values.pop("schema_version")
    reference_values.pop("reference_digest")
    payload["plan_reference"] = BootstrapGraphAtomicMemberReferenceV3.create(
        **reference_values
    ).model_dump(mode="json")
    payload.pop("schema_version")
    payload.pop("progress_digest")
    progress = BootstrapGraphPlannedProgressV3.create(**payload)
    bad = _request_with_member_payload(
        request, member_id="source-progress",
        payload=encode_bootstrap_graph_atomic_member_payload_v3(
            kind="bootstrap_graph_source_progress", artifact=progress,
        ),
    )
    with pytest.raises(PreplanningStoreError, match="artifact digest is substituted|reference is substituted"):
        AtomicStoreBootstrapGraphPlanRepositoryV3(atomic_store=atomic).publish_and_reload(
            request=bad,
            delivery_principal_binding_digest=epoch.delivery_principal_binding_digest,
            required_outcome_scopes=_request.required_outcome_scopes,
            control_epoch=epoch,
        )


def test_store_rejects_recomputed_counter_decrease_before_visibility(live_progress) -> None:
    _service, plane, atomic, _marker, epoch, _request = live_progress
    request = _latest_lineage_request(plane)
    member = next(item for item in request.members if item.member_id == "observed-counters")
    payload = decode_bootstrap_graph_atomic_member_payload_v3(kind=member.kind, raw=member.canonical_payload)
    payload.pop("schema_version")
    payload.pop("counters_digest")
    payload["observed_attempts"] = 0
    counters = BootstrapGraphObservedCountersV3.create(**payload)
    counter_raw = encode_bootstrap_graph_atomic_member_payload_v3(
        kind="bootstrap_graph_observed_counters", artifact=counters,
    )
    counter_member = BootstrapGraphPlanAtomicMemberV3.create(
        member_id="observed-counters", kind="bootstrap_graph_observed_counters",
        canonical_payload=counter_raw, payload_digest=sha256(counter_raw).hexdigest(),
    )
    progress_member = next(item for item in request.members if item.member_id == "source-progress")
    progress_values = decode_bootstrap_graph_atomic_member_payload_v3(
        kind=progress_member.kind, raw=progress_member.canonical_payload,
    )
    reference_values = progress_values["observed_counters_reference"]
    reference_values.pop("schema_version")
    reference_values.pop("reference_digest")
    progress_values["observed_counters_reference"] = BootstrapGraphAtomicMemberReferenceV3.create(
        **(reference_values | {
            "artifact_digest": counters.counters_digest,
            "member_payload_digest": counter_member.payload_digest,
        })
    ).model_dump(mode="json")
    progress_values.pop("schema_version")
    progress_values.pop("progress_digest")
    progress = BootstrapGraphPlannedProgressV3.create(**progress_values)
    bad = _request_with_member_payloads(request, {
        "observed-counters": counter_raw,
        "source-progress": encode_bootstrap_graph_atomic_member_payload_v3(
            kind="bootstrap_graph_source_progress", artifact=progress,
        ),
    })
    before = tuple(plane.list_records())
    with pytest.raises(PreplanningStoreError, match="counters stage is invalid"):
        AtomicStoreBootstrapGraphPlanRepositoryV3(atomic_store=atomic).publish_and_reload(
            request=bad,
            delivery_principal_binding_digest=epoch.delivery_principal_binding_digest,
            required_outcome_scopes=_request.required_outcome_scopes,
            control_epoch=epoch,
        )
    assert tuple(plane.list_records()) == before
