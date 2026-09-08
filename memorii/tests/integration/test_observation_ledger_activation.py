"""Durable activation reaches the canonical atomic-store owner."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest
from memorii.core.memory_evolution.atomic_store import PreplanningStoreError, SemanticIngestionAtomicStore
from memorii.core.memory_evolution.observation_activation_configuration import (
    resolve_verified_observation_activation_target,
)
from memorii.core.memory_evolution.typed_value_decoder_sources import DecoderSourceSelection
from memorii.core.memory_evolution.typed_value_publication import (
    DecoderSourceSnapshotPin,
    ProtectedTypedValuePublicationPins,
    parse_typed_value_publication_manifest,
)
from memorii.core.memory_evolution.typed_value_publication_authoring import author_typed_value_publication_package
from memorii.core.memory_evolution.typed_value_registry_configuration import (
    ProtectedTypedValueRegistryConfiguration,
    ProtectedTypedValueRegistryPublicationConfiguration,
    verify_configured_typed_value_registry_history,
)
from memorii.core.memory_evolution.writer_admission import (
    SemanticWriterAdmissionError,
    SemanticWriterAdmissionStore,
    bounded_preplanning_ownership_manifest,
    observation_ledger_head_memory_id,
    writer_admission_memory_id,
)
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import InMemoryMemoryPlaneStore, JsonlMemoryPlaneStore
from memorii.core.provider.service import ProviderMemoryService
from memorii.domain.enums import CommitStatus, MemoryDomain
from tests.fixtures.semantic_ingestion.host_bootstrap_authority import DeterministicTestHostBootstrapMaterialVerifier
from tests.unit.core.memory_evolution.test_observation_activation_configuration import _signed_package
from tests.unit.core.memory_evolution.test_typed_value_artifact_integrity import (
    _PUBLICATION_LIMITS,
    _ROOT,
    _publication,
)
from tests.unit.core.semantic_ingestion.test_semantic_atomic_store import _handoff
from tests.unit.core.semantic_ingestion.test_semantic_provider_composition import TEST_NOW, _built_in_local_capability


def _registry_configuration(tmp_path: Path):
    schemas = ("ObservationLedgerActivation", "ObservationLedgerHead")
    roles = [(_ROOT / "grammar.json").read_bytes()]
    for schema in schemas:
        roles.extend((_ROOT / role / schema / "1.json").read_bytes()
                     for role in ("schema", "enum", "optional", "numeric", "digest-signature", "upcast"))
    decoder = tmp_path / "native_decoder_snapshot.py"
    decoder.write_bytes(b"# isolated integration decoder snapshot\n")
    package = author_typed_value_publication_package(
        roles, tuple(DecoderSourceSelection(
            f"memorii.semantic_ingestion.observation.{schema}.v1", "feature-test", decoder.name,
        ) for schema in schemas), source_package_root=tmp_path, limits=_PUBLICATION_LIMITS,
    )
    vectors = b'{"integration":"activation"}'
    registry = ProtectedTypedValueRegistryConfiguration((ProtectedTypedValueRegistryPublicationConfiguration(
        package.raw_role_sources, package.raw_decoder_source_manifest, package.raw_publication_manifest,
        vectors, tmp_path, _PUBLICATION_LIMITS,
        ProtectedTypedValuePublicationPins(
            parse_typed_value_publication_manifest(package.raw_publication_manifest, maximum_bytes=60_000).publication_digest,
            package.compiled_registry.registry_digest,
            tuple(DecoderSourceSnapshotPin(item.decoder_id, item.source_snapshot_digest)
                  for item in package.verified_decoder_sources.snapshots), sha256(vectors).hexdigest(),
        ),
    ),))
    return registry


def _provider_factory(tmp_path, monkeypatch, *, normalization=False):
    registry = _registry_configuration(tmp_path)
    target, _, _ = _signed_package(tmp_path, monkeypatch, verify_configured_typed_value_registry_history(registry))
    clock = [TEST_NOW]
    def build(plane):
        normalization_builder = None
        if normalization:
            from tests.unit.core.semantic_ingestion.bootstrap_graph_production_roots_support import graph_fact_proposal
            from tests.unit.core.semantic_ingestion.test_semantic_provider_composition import (
                _v3_normalization_host_builder,
            )
            normalization_builder, _ = _v3_normalization_host_builder(proposal=graph_fact_proposal())
        return ProviderMemoryService(
            memory_plane=plane, now_provider=lambda: clock[0],
            source_normalization_host_bundle_builder=normalization_builder,
            host_bootstrap_capability=replace(_built_in_local_capability(),
                typed_value_registry_configuration=registry,
                observation_activation_target_configuration=target),
            host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        )
    return build, target, clock


def _seed_provider(service):
    runtime = service._composed_semantic_runtime
    assert runtime is not None and runtime.writer_admission is not None
    return runtime.writer_admission.commit_binding(runtime.writer_admission.create_initial_evidence_only(
        admission_id="provider-activation", writer_implementation_fingerprint="legacy",
        graph_schema_fingerprint="graph",
    ))


def test_provider_activation_is_explicit_and_revalidates_configured_authority(tmp_path, monkeypatch) -> None:
    build, target, _ = _provider_factory(tmp_path, monkeypatch)
    plane = MemoryPlaneService()
    service = build(plane)
    assert _ledger_records(plane) == ()
    _seed_provider(service)
    assert _ledger_records(plane) == ()
    activated = service.activate_observation_ledger()
    assert activated.activation_digest is not None
    before = plane.read_write_snapshot()
    assert service.activate_observation_ledger() == activated
    assert plane.read_write_snapshot() == before
    (target.deployment_configuration.installation_root / "memorii/empty.py").write_bytes(b"changed")
    from memorii.core.memory_evolution.observation_activation_configuration import (
        ObservationActivationTargetConfigurationError,
    )
    with pytest.raises(ObservationActivationTargetConfigurationError):
        service.activate_observation_ledger()
    assert plane.read_write_snapshot() == before


def _runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, max_rescans: int = 3):
    history = _publication(tmp_path, schemas=("ObservationLedgerActivation", "ObservationLedgerHead"))
    configuration, _, _ = _signed_package(tmp_path, monkeypatch, history)
    target = resolve_verified_observation_activation_target(configuration, history)
    backing = InMemoryMemoryPlaneStore()
    plane = MemoryPlaneService(record_store=backing)
    admission, _ = _handoff(plane)
    clock = [datetime(2026, 1, 1, tzinfo=UTC)]
    writers = SemanticWriterAdmissionStore(
        plane, bounded_preplanning_ownership_manifest(), now_provider=lambda: clock[0],
        typed_value_registry_history=history, observation_activation_target=target,
    )
    binding = writers.commit_binding(writers.create_initial_evidence_only(
        admission_id="activation", writer_implementation_fingerprint="legacy", graph_schema_fingerprint="graph",
    ))
    store = SemanticIngestionAtomicStore(
        plane, writers, now_provider=lambda: clock[0], max_lease_recoveries=0,
        activation_max_rescans=max_rescans,
        typed_value_registry_history=history, observation_activation_target=target,
    )
    return backing, plane, writers, store, binding, clock, admission


def _ledger_records(plane: MemoryPlaneService):
    return tuple(record for record in plane.list_records()
                 if record.source_kind.startswith("semantic_ingestion_observation_ledger_"))


def test_activation_waits_for_leased_operation_without_forcing_completion(tmp_path, monkeypatch) -> None:
    _, plane, writers, store, binding, clock, admission = _runtime(tmp_path, monkeypatch)
    fence = admission.operation_fence_binding
    store._publish_preplanning(admission=admission, writer_binding=binding)
    leased = store.acquire_lease(
        operation_fence=fence, writer_binding=binding,
        execution_token="active-worker", duration=timedelta(minutes=1),
    )
    with pytest.raises(PreplanningStoreError, match="not drained"):
        store.activate_observation_ledger(writer_binding=binding)
    assert store.get_operation(fence) == leased
    assert writers.current().activation_digest is None
    assert _ledger_records(plane) == ()
    admission_record = plane.get_record(writer_admission_memory_id())
    assert admission_record is not None and admission_record.content["draining"] is True

    clock[0] += timedelta(minutes=2)
    exhausted = store.acquire_lease(
        operation_fence=fence, writer_binding=binding,
        execution_token="recovery-worker", duration=timedelta(minutes=1),
    )
    assert exhausted.state == "lease_recovery_exhausted" and exhausted.lease is None
    activated = store.activate_observation_ledger(writer_binding=binding)
    assert activated.activation_digest is not None
    assert store.activate_observation_ledger(writer_binding=activated) == activated


@pytest.mark.parametrize("intervening_writes", (1, 3))
def test_activation_rescans_after_real_root_write_and_bounds_contention(tmp_path, monkeypatch, intervening_writes) -> None:
    backing, plane, writers, store, binding, _, _ = _runtime(tmp_path, monkeypatch)
    apply_batch = backing.apply_batch
    attempts = []

    def with_intervening_write(records, **kwargs):
        if any(record.source_kind == "semantic_ingestion_observation_ledger_activation" for record in records):
            attempts.append(kwargs["expected_write_revision"])
            assert _ledger_records(plane) == ()
            if len(attempts) <= intervening_writes:
                apply_batch((CanonicalMemoryRecord(
                    memory_id=f"unrelated:{len(attempts)}", domain=MemoryDomain.TRANSCRIPT,
                    text="unrelated root write", content={}, status=CommitStatus.COMMITTED,
                    source_kind="test_transcript", timestamp=datetime(2026, 1, 1, tzinfo=UTC),
                ),), expected_revision=None)
        return apply_batch(records, **kwargs)

    monkeypatch.setattr(backing, "apply_batch", with_intervening_write)
    if intervening_writes == 3:
        with pytest.raises(PreplanningStoreError, match="did not stabilize"):
            store.activate_observation_ledger(writer_binding=binding)
        assert _ledger_records(plane) == ()
        assert writers.current().activation_digest is None
        assert len(attempts) == 3
    else:
        activated = store.activate_observation_ledger(writer_binding=binding)
        assert activated.activation_digest is not None
        assert len(attempts) == 2 and len(_ledger_records(plane)) == 2
    assert attempts == sorted(set(attempts))


@pytest.mark.parametrize("route", ("ordinary", "conditional", "unit_of_work", "atomic"))
def test_activated_writer_rejects_legacy_mutation_routes(tmp_path, monkeypatch, route) -> None:
    _, plane, _, store, binding, _, admission = _runtime(tmp_path, monkeypatch)
    activated = store.activate_observation_ledger(writer_binding=binding)
    before = plane.read_write_snapshot()
    persisted = plane.get_record(writer_admission_memory_id())
    assert persisted is not None
    with pytest.raises(SemanticWriterAdmissionError):
        if route == "ordinary":
            plane.write_records((persisted,))
        elif route == "conditional":
            from memorii.core.memory_plane.store import RecordDigestPrecondition, record_digest
            plane.conditionally_write_records((persisted,), preconditions=(RecordDigestPrecondition(
                memory_id=persisted.memory_id, expected_digest=record_digest(persisted),
            ),))
        elif route == "unit_of_work":
            with plane.unit_of_work() as unit:
                plane.write_records((persisted,))
                unit.commit()
        else:
            store._publish_preplanning(admission=admission, writer_binding=activated)
    assert plane.read_write_snapshot() == before


@pytest.mark.parametrize("damage", ("missing_head", "head_shape", "activation_shape", "inventory", "forged_binding"))
def test_activation_reload_rejects_incomplete_or_substituted_state(tmp_path, monkeypatch, damage) -> None:
    backing, plane, _, store, binding, _, _ = _runtime(tmp_path, monkeypatch)
    activated = store.activate_observation_ledger(writer_binding=binding)
    head_id = observation_ledger_head_memory_id("semantic_ingestion")
    if damage == "missing_head":
        del backing._records[head_id]
    elif damage in {"head_shape", "activation_shape"}:
        record_id = head_id if damage == "head_shape" else "semantic_ingestion:observation-ledger:activation:" + activated.activation_digest
        record = backing._records[record_id]
        backing._records[record_id] = record.model_copy(update={"text": "substituted"})
    elif damage == "inventory":
        backing._records["semantic_ingestion:operation:corrupt"] = CanonicalMemoryRecord(
            memory_id="semantic_ingestion:operation:corrupt", domain=MemoryDomain.EXECUTION,
            text="", content={"control": {}}, status=CommitStatus.COMMITTED,
            source_kind="semantic_ingestion_preplanning_control", timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        )
    else:
        binding = binding.model_copy(update={"expected_writer_epoch": binding.expected_writer_epoch + 10})
    before = plane.read_write_snapshot()
    with pytest.raises((PreplanningStoreError, SemanticWriterAdmissionError)):
        store.activate_observation_ledger(writer_binding=binding)
    assert plane.read_write_snapshot() == before


def test_atomic_activation_persists_registered_trio_and_replays_lost_ack(tmp_path, monkeypatch) -> None:
    history = _publication(tmp_path, schemas=("ObservationLedgerActivation", "ObservationLedgerHead"))
    configuration, _, _ = _signed_package(tmp_path, monkeypatch, history)
    target = resolve_verified_observation_activation_target(configuration, history)
    plane = MemoryPlaneService(record_store=InMemoryMemoryPlaneStore())
    writers = SemanticWriterAdmissionStore(
        plane, bounded_preplanning_ownership_manifest(),
        now_provider=lambda: datetime(2026, 1, 1, tzinfo=UTC),
        typed_value_registry_history=history, observation_activation_target=target,
    )
    binding = writers.commit_binding(writers.create_initial_evidence_only(
        admission_id="activation", writer_implementation_fingerprint="legacy", graph_schema_fingerprint="graph",
    ))
    store = SemanticIngestionAtomicStore(
        plane, writers, now_provider=lambda: datetime(2026, 1, 1, tzinfo=UTC),
        typed_value_registry_history=history, observation_activation_target=target,
    )

    successor = store.activate_observation_ledger(writer_binding=binding)
    replay = store.activate_observation_ledger(writer_binding=binding)
    current_replay = store.activate_observation_ledger(writer_binding=successor)

    assert replay == successor == current_replay
    assert successor.activation_digest is not None
    assert plane.get_record("semantic_ingestion:observation-ledger:activation:" + successor.activation_digest) is not None
    assert plane.get_record(observation_ledger_head_memory_id("semantic_ingestion")) is not None


def test_jsonl_activation_reopens_complete_registered_trio(tmp_path, monkeypatch) -> None:
    history = _publication(tmp_path, schemas=("ObservationLedgerActivation", "ObservationLedgerHead"))
    configuration, _, _ = _signed_package(tmp_path, monkeypatch, history)
    target = resolve_verified_observation_activation_target(configuration, history)
    path = tmp_path / "ledger-store"
    plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
    writers = SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest(), typed_value_registry_history=history, observation_activation_target=target)
    binding = writers.commit_binding(writers.create_initial_evidence_only(admission_id="activation", writer_implementation_fingerprint="legacy", graph_schema_fingerprint="graph"))
    successor = SemanticIngestionAtomicStore(plane, writers, typed_value_registry_history=history, observation_activation_target=target).activate_observation_ledger(writer_binding=binding)
    reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
    reopened_writers = SemanticWriterAdmissionStore(reopened_plane, bounded_preplanning_ownership_manifest(), typed_value_registry_history=history, observation_activation_target=target)
    reopened = SemanticIngestionAtomicStore(reopened_plane, reopened_writers, typed_value_registry_history=history, observation_activation_target=target)
    assert reopened.activate_observation_ledger(writer_binding=successor) == successor


@pytest.mark.parametrize("remove_member", (False, True))
def test_activation_validates_retained_native_terminal_closure(tmp_path, monkeypatch, remove_member) -> None:
    from tests.unit.core.semantic_ingestion.test_historical_terminal_persisted_reload import (
        _rehydrated_historical_plane,
    )

    historical = _rehydrated_historical_plane(tmp_path)
    backing = InMemoryMemoryPlaneStore()
    records = historical.read_write_snapshot()[1]
    # Rehydrate captured storage bytes, without authorizing a new semantic write.
    backing._records = {record.memory_id: record for record in records}
    plane = MemoryPlaneService(record_store=backing)
    history = _publication(tmp_path, schemas=("ObservationLedgerActivation", "ObservationLedgerHead"))
    configuration, _, _ = _signed_package(tmp_path, monkeypatch, history)
    target = resolve_verified_observation_activation_target(configuration, history)
    writers = SemanticWriterAdmissionStore(
        plane, bounded_preplanning_ownership_manifest(),
        typed_value_registry_history=history, observation_activation_target=target,
    )
    atomic = SemanticIngestionAtomicStore(
        plane, writers, typed_value_registry_history=history, observation_activation_target=target,
    )
    binding = writers.commit_binding(writers.current())
    if remove_member:
        member = next(record for record in records if record.source_kind == "semantic_ingestion_bootstrap_graph_v3_member"
                      and record.content.get("member", {}).get("kind") == "bootstrap_graph_canonical_source_result")
        del backing._records[member.memory_id]
        with pytest.raises(PreplanningStoreError, match="member closure is incomplete"):
            atomic.activate_observation_ledger(writer_binding=binding)
        assert _ledger_records(plane) == ()
    else:
        activated = atomic.activate_observation_ledger(writer_binding=binding)
        before = plane.read_write_snapshot()
        assert atomic.activate_observation_ledger(writer_binding=activated) == activated
        assert plane.read_write_snapshot() == before


@pytest.mark.parametrize("seam", ("_begin_observation_ledger_drain", "_activate_observation_ledger"))
def test_public_concurrent_activation_recovers_winning_jsonl_cutover(tmp_path, monkeypatch, seam) -> None:
    build, _, _ = _provider_factory(tmp_path, monkeypatch)
    path = tmp_path / "concurrent-store"
    plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
    service = build(plane)
    old_binding = _seed_provider(service)
    runtime = service._composed_semantic_runtime
    assert runtime is not None and runtime.writer_admission is not None and runtime.atomic_store is not None
    original = getattr(runtime.writer_admission, seam)
    winner = []
    interleaved = False

    def winner_before_loser(*args, **kwargs):
        nonlocal interleaved
        if not interleaved:
            interleaved = True
            winner.append(service.activate_observation_ledger())
        return original(*args, **kwargs)

    monkeypatch.setattr(runtime.writer_admission, seam, winner_before_loser)
    loser = service.activate_observation_ledger()
    assert winner == [loser]
    assert loser.expected_writer_epoch == old_binding.expected_writer_epoch + 1
    assert runtime.atomic_store.activate_observation_ledger(writer_binding=old_binding) == loser
    assert service.activate_observation_ledger() == loser
    assert len(_ledger_records(plane)) == 2
    reopened = build(MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path)))
    assert reopened.activate_observation_ledger() == loser
    _assert_fresh_process_trio(tmp_path, path, loser.activation_digest)


@pytest.mark.parametrize("after_commit", (False, True))
def test_public_activation_recovers_jsonl_failure_before_or_after_commit(tmp_path, monkeypatch, after_commit) -> None:
    build, _, _ = _provider_factory(tmp_path, monkeypatch)
    path = tmp_path / "interrupted-store"
    backing = JsonlMemoryPlaneStore(path)
    plane = MemoryPlaneService(record_store=backing)
    service = build(plane)
    old = _seed_provider(service)
    apply_batch = backing.apply_batch

    def interrupted(records, **kwargs):
        if any(record.source_kind == "semantic_ingestion_observation_ledger_activation" for record in records):
            if after_commit:
                apply_batch(records, **kwargs)
            raise OSError("injected activation interruption")
        return apply_batch(records, **kwargs)

    monkeypatch.setattr(backing, "apply_batch", interrupted)
    with pytest.raises(OSError, match="injected activation interruption"):
        service.activate_observation_ledger()
    reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
    reopened = build(reopened_plane)
    runtime = reopened._composed_semantic_runtime
    assert runtime is not None and runtime.writer_admission is not None
    before = reopened_plane.read_write_snapshot()
    persisted = runtime.writer_admission.current()
    assert persisted.writer_epoch == old.expected_writer_epoch + int(after_commit)
    assert len(_ledger_records(reopened_plane)) == (2 if after_commit else 0)
    result = reopened.activate_observation_ledger()
    assert result.expected_writer_epoch == old.expected_writer_epoch + 1
    if after_commit:
        assert reopened_plane.read_write_snapshot() == before
    assert len(_ledger_records(reopened_plane)) == 2
    _assert_fresh_process_trio(tmp_path, path, result.activation_digest)


def _assert_fresh_process_trio(root: Path, path: Path, activation_digest: str) -> None:
    import subprocess
    import sys

    code = """
import sys
from pathlib import Path
from memorii.core.memory_evolution.observation_activation_runtime import validate_registered_artifact
from memorii.core.memory_evolution.typed_value_registry_configuration import verify_configured_typed_value_registry_history
from memorii.core.memory_evolution.writer_admission import SemanticWriterAdmissionStore, bounded_preplanning_ownership_manifest
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import JsonlMemoryPlaneStore
from tests.integration.test_observation_ledger_activation import _registry_configuration
history = verify_configured_typed_value_registry_history(_registry_configuration(Path(sys.argv[1])))
plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(Path(sys.argv[2])))
writers = SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest(), typed_value_registry_history=history)
assert writers.current().activation_digest == sys.argv[3]
for kind, schema in (("activation", "ObservationLedgerActivation"), ("head", "ObservationLedgerHead")):
    rows = plane.list_records(source_kind="semantic_ingestion_observation_ledger_" + kind)
    assert len(rows) == 1
    value = validate_registered_artifact(rows[0].content["artifact"].encode(), schema_id=schema, history=history)
    assert value.activation_digest == sys.argv[3]
"""
    completed = subprocess.run(
        [sys.executable, "-W", "error", "-c", code, str(root), str(path), activation_digest],
        cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, timeout=60,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr



def test_public_drain_preserves_live_operation_and_rejects_new_old_epoch_work(tmp_path, monkeypatch) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
    from memorii.core.memory_evolution.observation_activation_runtime import validate_registered_artifact
    from memorii.core.memory_plane.store import record_digest
    from memorii.core.provider.models import ProviderOperation
    from tests.unit.core.semantic_ingestion.test_semantic_provider_composition import _host_ingress

    build, _, _ = _provider_factory(tmp_path, monkeypatch, normalization=True)
    path = tmp_path / "draining-store"
    plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
    service = build(plane)
    runtime = service._composed_semantic_runtime
    assert runtime is not None and runtime.atomic_store is not None
    atomic = runtime.atomic_store

    def ingest(operation):
        return service.sync_event(
            operation=ProviderOperation.CHAT_USER_TURN, content="Atlas owner is Bob.",
            operation_id=operation, task_id="task:one", user_id="user:alice",
            authenticated_host_ingress=_host_ingress(),
        )

    ingest("completed-before-drain")
    acquire = atomic.acquire_lease
    ready, release = Event(), Event()
    held = []

    def hold_after_lease(**kwargs):
        control = acquire(**kwargs)
        held.append(control)
        ready.set()
        assert release.wait(timeout=120), "test did not release the held operation"
        return control

    monkeypatch.setattr(atomic, "acquire_lease", hold_after_lease)
    with ThreadPoolExecutor(max_workers=1) as executor:
        running = executor.submit(ingest, "held-operation")
        try:
            assert ready.wait(timeout=30), "public ingestion did not acquire a lease"
            assert held[0].lease is not None
            with pytest.raises(PreplanningStoreError, match="not drained"):
                service.activate_observation_ledger()
            assert atomic.get_operation(held[0].operation_fence) == held[0]
            before_controls = plane.list_records(source_kind="semantic_ingestion_preplanning_control")
            with pytest.raises(ValueError, match="draining and source admission is frozen"):
                ingest("new-operation-during-drain")
            assert plane.list_records(source_kind="semantic_ingestion_preplanning_control") == before_controls
        finally:
            release.set()
        running.result(timeout=120)
    terminal = atomic.get_operation(held[0].operation_fence)
    assert terminal.state == "terminal" and terminal.lease is None
    snapshot = plane.read_write_snapshot()[1]
    controls = tuple(record for record in snapshot if record.source_kind == "semantic_ingestion_preplanning_control")
    assert len(controls) == 2
    roots = tuple(record for record in snapshot
                  if record.memory_id.startswith("semantic_ingestion:bootstrap-graph-v3:terminal-locator:"))
    terminals = tuple(record for record in snapshot
                      if record.source_kind == "semantic_ingestion_bootstrap_graph_v3_terminal_control")
    assert len(roots) == len(terminals) == 2
    expected_inventory = sha256(encode_typed_value(tuple(sorted(
        (record.memory_id, record_digest(record)) for record in (*controls, *roots, *terminals)
    )))).hexdigest()
    activated = service.activate_observation_ledger()
    artifact = plane.get_record("semantic_ingestion:observation-ledger:activation:" + activated.activation_digest)
    assert artifact is not None and runtime.typed_value_registry_history is not None
    decoded = validate_registered_artifact(artifact.content["artifact"].encode(), schema_id="ObservationLedgerActivation",
                                           history=runtime.typed_value_registry_history)
    assert decoded.legacy_terminal_inventory_digest == expected_inventory
    reopened = build(MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path)))
    assert reopened.activate_observation_ledger() == activated


def test_public_activation_preserves_captured_jsonl_history_bytes(tmp_path, monkeypatch) -> None:
    from memorii.core.semantic_ingestion.contracts import BootstrapGraphTerminalReloadV3, decode_semantic_contract
    from tests.unit.core.semantic_ingestion.test_historical_terminal_persisted_reload import (
        _fixture_bytes,
        _rehydrated_historical_plane,
    )

    plane = _rehydrated_historical_plane(tmp_path)
    path = tmp_path / "historical-terminal"
    original_bytes = (path / "memory_records.jsonl").read_bytes()
    old_records = {record.memory_id: record for record in plane.read_write_snapshot()[1]
                   if record.memory_id != writer_admission_memory_id()}
    build, _, _ = _provider_factory(tmp_path, monkeypatch)
    service = build(plane)
    activated = service.activate_observation_ledger()
    assert (path / "memory_records.jsonl").read_bytes().startswith(original_bytes)
    reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(path))
    reopened = build(reopened_plane)
    assert reopened.activate_observation_ledger() == activated
    assert all(reopened_plane.get_record(key) == value for key, value in old_records.items())
    expected = decode_semantic_contract(_fixture_bytes("terminal-reload.ctv"), BootstrapGraphTerminalReloadV3)
    root = next(record for record in reopened_plane.list_records()
                if record.memory_id.startswith("semantic_ingestion:bootstrap-graph-v3:terminal-locator:"))
    assert BootstrapGraphTerminalReloadV3.model_validate(root.content["reload"], strict=False) == expected



def test_public_activation_retries_competing_jsonl_drain_fence(tmp_path, monkeypatch) -> None:
    build, _, _ = _provider_factory(tmp_path, monkeypatch)
    backing = JsonlMemoryPlaneStore(tmp_path / "competing-drain-store")
    plane = MemoryPlaneService(record_store=backing)
    service = build(plane)
    old = _seed_provider(service)
    apply_batch = backing.apply_batch
    raced = False

    def competing_drain(records, **kwargs):
        nonlocal raced
        if not raced and len(records) == 1 and records[0].memory_id == writer_admission_memory_id() and records[0].content.get("draining") is True:
            raced = True
            apply_batch(records, **kwargs)
        return apply_batch(records, **kwargs)

    monkeypatch.setattr(backing, "apply_batch", competing_drain)
    result = service.activate_observation_ledger()
    assert raced and result.expected_writer_epoch == old.expected_writer_epoch + 1
    assert service.activate_observation_ledger() == result
    assert len(_ledger_records(plane)) == 2
