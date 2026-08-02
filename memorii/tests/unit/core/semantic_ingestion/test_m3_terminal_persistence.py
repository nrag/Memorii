from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest
from m3_test_support import accepted_terminal, handoff
from memorii.core.memory_evolution.atomic_store import (
    PreplanningStoreError,
    SemanticAuthorizationAuthorityRecord,
    SemanticIngestionAtomicStore,
    _control_from_record,
)
from memorii.core.memory_evolution.delivery_coordinate_migration import (
    DeliveryCoordinateMigrationCheckpoint,
    activate_migration,
    build_migration_plan,
    certify_migration,
)
from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
from memorii.core.memory_evolution.writer_admission import (
    SemanticWriterAdmissionStore,
    bounded_preplanning_ownership_manifest,
)
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import (
    JsonlMemoryPlaneStore,
    MemoryPlaneRevisionConflictError,
    MemoryPlaneStore,
    _PersistedBatch,
)
from memorii.core.semantic_ingestion.authorization import (
    M3AuthorizationAuthorityRepository,
    M3VerifiedAuthorizationTransition,
    VerifiedM3AuthorizationControlPlane,
)
from memorii.core.semantic_ingestion.contracts import SemanticTerminalOutcome
from memorii.core.semantic_ingestion.persistence import M3TerminalPersistenceService

NOW = datetime(2026, 1, 1, tzinfo=UTC)


class _CurrentAuthorization:
    def verify_current(self, read_set, *, use_point: str) -> bool:
        return use_point == "pre_commit"


AUTHORIZATION = _CurrentAuthorization()


class _StaleAuthorization:
    def verify_current(self, read_set, *, use_point: str) -> bool:
        return False


class _RotateInsideStoreAuthorization:
    def __init__(self) -> None:
        self.reads = 0

    def verify_current(self, read_set, *, use_point: str) -> bool:
        self.reads += 1
        return use_point == "pre_commit" and self.reads < 3


def _setup(
    *,
    verified: bool,
    backend: MemoryPlaneStore | None = None,
    now_provider=lambda: NOW,
):
    plane = MemoryPlaneService(record_store=backend) if backend is not None else MemoryPlaneService()
    admission, fence = handoff(plane)
    writers = SemanticWriterAdmissionStore(
        plane, bounded_preplanning_ownership_manifest(), now_provider=now_provider
    )
    binding = writers.commit_binding(writers.create_initial_evidence_only(
        admission_id="m3", writer_implementation_fingerprint="writer", graph_schema_fingerprint="schema"
    ))
    if verified:
        plan = build_migration_plan(
            migration_plan_id="m3:verified", source_writer_epoch=1,
            legacy_snapshot_token=sha256(encode_typed_value(())).hexdigest(), entries=(),
        )
        checkpoint_values = {
            "migration_plan_id": plan.migration_plan_id,
            "plan_digest": plan.plan_digest,
            "completed_entry_digests": (),
            "target_generation": 1,
        }
        checkpoint = DeliveryCoordinateMigrationCheckpoint(
            **checkpoint_values,
            checkpoint_digest=sha256(encode_typed_value(checkpoint_values)).hexdigest(),
        )
        certificate = certify_migration(plan, checkpoint, independent_verifier_fingerprint="m3-verifier")
        activation = activate_migration(plan, certificate)
        binding = writers.commit_binding(writers.transition(
            expected=binding, admission_id="m3:verified", runtime_mode="verified_semantic",
            writer_implementation_fingerprint="writer:verified", graph_schema_fingerprint="schema",
            migration_activation=activation, migration_plan=plan, migration_checkpoint=checkpoint,
            migration_certificate=certificate, target_records=(),
        ))
    store = SemanticIngestionAtomicStore(plane, writers, now_provider=now_provider)
    store._publish_preplanning(admission=admission, writer_binding=binding)
    repository = M3AuthorizationAuthorityRepository(
        atomic_store=store,
        writer_binding_provider=lambda: binding,
        now_provider=now_provider,
    )
    service = M3TerminalPersistenceService(
        atomic_store=store,
        writer_binding_provider=lambda: binding,
        authorization_repository=repository,
    )
    return plane, writers, store, binding, fence, service, repository


def _activate(repository, fence, terminal, *, valid_until=None) -> None:
    assert terminal.authorization_read_set is not None
    repository.observe_verified(
        authority_scope_id=repository.scope_id(
            source_id=fence.source_id, source_digest=fence.source_digest
        ),
        read_set=terminal.authorization_read_set,
        valid_until=valid_until or datetime(2030, 1, 1, tzinfo=UTC),
    )


def _nonaccepted(operation_id: str) -> SemanticTerminalOutcome:
    return SemanticTerminalOutcome.create(
        operation_id=operation_id,
        status="unresolved",
        reason_codes=("consensus_unresolved",),
        candidates=(),
        temporal_closures=(),
        attempt_count=1,
    )


def test_store_commits_only_accepted_exact_effect_closure() -> None:
    _, _, store, _, fence, service, repository = _setup(verified=True)
    terminal = accepted_terminal(operation_id=fence.operation_id)
    _activate(repository, fence, terminal)
    service.persist(fence=fence, terminal=terminal, authorization_verifier=AUTHORIZATION)
    group = store.generation_members(fence, 3)
    assert {value.kind for value in group} == {
        "artifact_closure", "artifact_index", "event_batch", "graph_delta", "group_result", "observation_delta"
    }
    control = store.get_operation(fence)
    assert control.state == "terminal"
    assert control.graph_revision != "genesis" and control.observation_revision != "genesis"


def test_store_nonaccepted_terminal_has_no_graph_or_event_effect() -> None:
    _, _, store, _, fence, service, _ = _setup(verified=False)
    service.persist(fence=fence, terminal=_nonaccepted(fence.operation_id))
    group = store.generation_members(fence, 3)
    assert {value.kind for value in group} == {
        "artifact_closure", "artifact_index", "group_result", "observation_delta"
    }
    control = store.get_operation(fence)
    assert control.state == "terminal" and control.graph_revision == "genesis"


def test_accepted_terminal_rechecks_authorization_before_any_planned_generation() -> None:
    _, _, store, _, fence, service, repository = _setup(verified=True)
    terminal = accepted_terminal(operation_id=fence.operation_id)
    _activate(repository, fence, terminal)
    with pytest.raises(ValueError, match="authorization read set is stale"):
        service.persist(
            fence=fence,
            terminal=terminal,
            authorization_verifier=_StaleAuthorization(),
        )
    assert store.get_operation(fence).generation == 1


def test_same_store_authority_rotation_rejects_before_graph_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plane, _, store, binding, fence, service, repository = _setup(verified=True)
    terminal = accepted_terminal(operation_id=fence.operation_id)
    _activate(repository, fence, terminal)
    original = store.persist_terminal_group
    rotated = False

    def rotate_before_cas(request):
        nonlocal rotated
        if not rotated:
            rotated = True
            expected = request.authorization_precondition
            assert expected is not None
            record = plane.get_record(expected.authority_record_id)
            assert record is not None
            current = SemanticAuthorizationAuthorityRecord.model_validate(record.content["authority"])
            body = current.model_dump(mode="python", exclude={"coordinates_digest"})
            body.update({"authority_revision": 2, "state": "revoked"})
            replacement = SemanticAuthorizationAuthorityRecord(
                **body, coordinates_digest=sha256(encode_typed_value(body)).hexdigest()
            )
            store.replace_authorization_authority(
                writer_binding=binding, expected=expected, authority=replacement,
            )
        return original(request)

    monkeypatch.setattr(store, "persist_terminal_group", rotate_before_cas)
    with pytest.raises(MemoryPlaneRevisionConflictError, match="authorization"):
        service.persist(
            fence=fence,
            terminal=terminal,
            authorization_verifier=AUTHORIZATION,
        )
    control = store.get_operation(fence)
    assert control.generation == 2
    assert control.graph_revision == "genesis"
    assert control.group_result_digests == ()


def test_verified_revocation_rejects_policy_bearing_noncommit_before_any_effect() -> None:
    _, _, store, _, fence, service, repository = _setup(verified=True)
    accepted = accepted_terminal(operation_id=fence.operation_id)
    _activate(repository, fence, accepted)
    scope_id = repository.scope_id(
        source_id=fence.source_id, source_digest=fence.source_digest
    )

    class _Verifier:
        def verify(self, *, command_bytes: bytes, server_time: datetime):
            assert command_bytes == b"signed-revoke"
            assert server_time == NOW
            return M3VerifiedAuthorizationTransition.create(
                authority_scope_id=scope_id,
                action="revoke",
                expected_revision=1,
            )

    VerifiedM3AuthorizationControlPlane(
        verifier=_Verifier(), repository=repository, now_provider=lambda: NOW
    ).apply(b"signed-revoke")
    terminal = SemanticTerminalOutcome.create(
        operation_id=fence.operation_id,
        status="unresolved",
        reason_codes=("consensus_unresolved",),
        candidates=(),
        arbitration_policy_bundle=accepted.arbitration_policy_bundle,
        authorization_read_set=accepted.authorization_read_set,
        temporal_closures=(),
        attempt_count=1,
    )
    with pytest.raises(ValueError, match="authorization authority is stale"):
        service.persist(
            fence=fence, terminal=terminal, authorization_verifier=AUTHORIZATION
        )
    control = store.get_operation(fence)
    assert control.generation == 1
    assert control.group_result_digests == ()
    assert control.graph_revision == "genesis"


def test_same_store_authority_expiry_at_precommit_has_zero_effects() -> None:
    clock = [NOW]
    _, _, store, _, fence, service, repository = _setup(
        verified=True, now_provider=lambda: clock[0]
    )
    terminal = accepted_terminal(operation_id=fence.operation_id)
    _activate(repository, fence, terminal, valid_until=NOW + timedelta(minutes=1))
    clock[0] = NOW + timedelta(minutes=2)
    with pytest.raises(ValueError, match="authorization authority is stale"):
        service.persist(
            fence=fence, terminal=terminal, authorization_verifier=AUTHORIZATION
        )
    control = store.get_operation(fence)
    assert control.generation == 1
    assert control.group_result_digests == ()
    assert control.graph_revision == "genesis"


@pytest.mark.parametrize("method_name", ["checkpoint_source_progress", "persist_terminal_group", "finalize_source"])
def test_retry_and_lost_ack_are_byte_idempotent(
    monkeypatch: pytest.MonkeyPatch, method_name: str
) -> None:
    _, _, store, _, fence, service, repository = _setup(verified=True)
    terminal = accepted_terminal(operation_id=fence.operation_id)
    _activate(repository, fence, terminal)
    original = getattr(store, method_name)
    failed = False

    def lost_ack(request, **kwargs):
        nonlocal failed
        result = original(request, **kwargs)
        if not failed:
            failed = True
            raise OSError("simulated lost acknowledgement")
        return result

    monkeypatch.setattr(store, method_name, lost_ack)
    with pytest.raises(OSError, match="lost acknowledgement"):
        service.persist(fence=fence, terminal=terminal, authorization_verifier=AUTHORIZATION)
    assert failed is True
    service.persist(fence=fence, terminal=terminal, authorization_verifier=AUTHORIZATION)
    assert store.get_operation(fence).state == "terminal"
    with pytest.raises(ValueError, match="differs from retry terminal"):
        service.persist(fence=fence, terminal=_nonaccepted(fence.operation_id))


def test_filesystem_reopen_recovers_exact_terminal_without_duplicate_effects(tmp_path) -> None:
    backend = JsonlMemoryPlaneStore(tmp_path / "m3-store")
    _, _, store, _, fence, service, repository = _setup(verified=True, backend=backend)
    terminal = accepted_terminal(operation_id=fence.operation_id)
    _activate(repository, fence, terminal)
    service.persist(fence=fence, terminal=terminal, authorization_verifier=AUTHORIZATION)

    reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(tmp_path / "m3-store"))
    reopened_writers = SemanticWriterAdmissionStore(
        reopened_plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: NOW
    )
    reopened_binding = reopened_writers.commit_binding(reopened_writers.current())
    reopened_store = SemanticIngestionAtomicStore(reopened_plane, reopened_writers, now_provider=lambda: NOW)
    reopened = M3TerminalPersistenceService(
        atomic_store=reopened_store, writer_binding_provider=lambda: reopened_binding
    )
    reopened.persist(fence=fence, terminal=terminal, authorization_verifier=AUTHORIZATION)
    assert reopened_store.get_operation(fence).generation == 4


def test_filesystem_reopen_rejects_malformed_terminal_artifact_batch(tmp_path) -> None:
    backend = JsonlMemoryPlaneStore(tmp_path / "m3-malformed-terminal")
    _, _, _, _, fence, service, repository = _setup(verified=True, backend=backend)
    terminal = accepted_terminal(operation_id=fence.operation_id)
    _activate(repository, fence, terminal)
    service.persist(fence=fence, terminal=terminal, authorization_verifier=AUTHORIZATION)

    batches = backend._read_batches_unlocked()
    rewritten = []
    changed = False
    for batch in batches:
        records = []
        for record in batch.records:
            member = record.content.get("member")
            if isinstance(member, dict) and member.get("kind") == "terminal_artifact":
                malformed = dict(member)
                malformed["canonical_payload"] = b"{malformed-terminal"
                malformed["payload_digest"] = sha256(
                    malformed["canonical_payload"]
                ).hexdigest()
                content = dict(record.content)
                content["member"] = malformed
                record = record.model_copy(update={"content": content})
                changed = True
            records.append(record)
        rewritten.append(
            _PersistedBatch.create(
                revision=batch.revision,
                data_revision=batch.data_revision,
                records=tuple(records),
            )
        )
    assert changed is True
    backend._replace_batches(rewritten)

    reopened_plane = MemoryPlaneService(
        record_store=JsonlMemoryPlaneStore(tmp_path / "m3-malformed-terminal")
    )
    reopened_writers = SemanticWriterAdmissionStore(
        reopened_plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: NOW
    )
    reopened_store = SemanticIngestionAtomicStore(
        reopened_plane, reopened_writers, now_provider=lambda: NOW
    )
    reopened = M3TerminalPersistenceService(
        atomic_store=reopened_store,
        writer_binding_provider=lambda: reopened_writers.commit_binding(
            reopened_writers.current()
        ),
    )
    with pytest.raises((PreplanningStoreError, ValueError)):
        reopened.recover_terminal_artifact(fence=fence)


def test_durable_retry_checkpoint_resumes_after_group_lost_ack_without_learned_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, store, _, fence, service, repository = _setup(verified=True)
    terminal = accepted_terminal(operation_id=fence.operation_id)
    _activate(repository, fence, terminal)
    original = store.persist_terminal_group
    failed = False

    def lost_ack(request, **kwargs):
        nonlocal failed
        result = original(request, **kwargs)
        if not failed:
            failed = True
            raise OSError("simulated group lost acknowledgement")
        return result

    monkeypatch.setattr(store, "persist_terminal_group", lost_ack)
    with pytest.raises(OSError, match="lost acknowledgement"):
        service.persist(
            fence=fence, terminal=terminal, authorization_verifier=AUTHORIZATION
        )
    session = service.open_lease_session(fence=fence)
    session.checkpoint_retryable(
        stage="finalization", failure_kind="store_outage", terminal=terminal
    )
    monkeypatch.setattr(store, "persist_terminal_group", original)
    service.persist(
        fence=fence, terminal=terminal, authorization_verifier=AUTHORIZATION
    )
    assert store.get_operation(fence).state == "terminal"


def test_cross_operation_terminal_swap_fails_before_generation_write() -> None:
    _, _, store, _, fence, service, _ = _setup(verified=True)
    with pytest.raises(ValueError, match="does not bind"):
        service.persist(
            fence=fence, terminal=accepted_terminal(operation_id="other-operation")
        )
    assert store.get_operation(fence).generation == 1


def test_legacy_retry_exhausted_control_requires_explicit_terminal_migration() -> None:
    plane, _, _, _, fence, _, _ = _setup(verified=True)
    record = plane.get_record(
        f"semantic_ingestion:operation:{fence.operation_fence_id}"
    )
    assert record is not None
    content = dict(record.content)
    control = dict(content["control"])
    control["state"] = "retry_exhausted"
    content["control"] = control
    legacy = record.model_copy(update={"content": content})
    with pytest.raises(
        PreplanningStoreError,
        match="legacy retry_exhausted control requires explicit terminal migration",
    ):
        _control_from_record(legacy)
