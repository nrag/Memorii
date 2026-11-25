"""Indexed source admission through the managed provider and SQLite owners."""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event, get_ident
from typing import BinaryIO
from unittest.mock import patch

import pytest
from memorii.core.memory_plane import file_lock
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.store import (
    IndexedGovernedWritePolicy,
    MemoryPlaneRevisionConflictError,
    MemoryPlaneWriteAuthorization,
    RecordDigestPrecondition,
    record_digest,
)
from memorii.core.persistence.contracts import (
    InstallationControlJournalEntry,
    RuntimePublicationIntent,
    RuntimePublicationState,
)
from memorii.core.persistence.runtime_contracts import RuntimeCommandReceipt
from memorii.core.persistence.runtime_repository import RuntimeStateRepository, publish_runtime_change
from memorii.core.storage_administration.service import StorageAdministrationService
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility
from tests.support.reference_capacity import FIXTURE_START, SourceInput, TaskAllocation
from tests.support.reference_capacity_fixture import _execution_changes, _prepare, _publish_changes
from tests.support.reference_capacity_sources import ReferenceSourceCapture

_TASK = TaskAllocation(
    distribution="balanced", index=0, execution_nodes=2, solver_nodes=4,
    first_solver_node=0, first_source=0, sources=2,
)


@pytest.mark.parametrize("writer_kind", ["runtime", "memory_plane"])
@pytest.mark.parametrize("publication_cut", ["prepared", "data_committed", "control_committed"])
def test_managed_source_read_waits_for_live_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, writer_kind: str, publication_cut: str,
) -> None:
    fcntl = pytest.importorskip("fcntl")
    root = tmp_path / "installation"
    _prepare(root, "balanced", (_TASK,), raw_payloads=True)
    source = SourceInput(coordinate="concurrent-capture", task_id=_TASK.task_id, timestamp=FIXTURE_START)
    paused, attempted, release = Event(), Event(), Event()
    reader_thread = None
    entered_while_pending = False
    with StorageAdministrationService(root) as writer, StorageAdministrationService(root) as reader:
        capture = ReferenceSourceCapture(reader)
        repository = RuntimeStateRepository(writer.partition())
        task = repository.get_task(_TASK.task_id)
        assert task is not None
        updated = task.model_copy(update={"version": task.version + 1})
        path = writer.partition_path()
        lock_path = path.with_name(f"{path.name}.lock")
        original_intent = writer._control.write_intent
        original_finalize = writer._finalize_publication
        original_acquire = file_lock._acquire

        def pause() -> None:
            paused.set()
            assert release.wait(timeout=10)

        def write_intent(intent: RuntimePublicationIntent, entry: InstallationControlJournalEntry) -> None:
            if publication_cut == "control_committed" and intent.phase == "finalized":
                pause()
            original_intent(intent, entry)
            if publication_cut == "prepared" and intent.phase == "prepared":
                pause()

        def finalize(candidate: RuntimePublicationState) -> None:
            if publication_cut == "data_committed":
                pause()
            original_finalize(candidate)

        def acquire(handle: BinaryIO, *, exclusive: bool) -> None:
            nonlocal entered_while_pending
            if get_ident() == reader_thread and handle.name == str(lock_path) and not attempted.is_set():
                assert not exclusive
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
                except BlockingIOError:
                    attempted.set()
                else:
                    entered_while_pending = True
                    attempted.set()
                    return
            original_acquire(handle, exclusive=exclusive)

        def publish() -> None:
            if writer_kind == "runtime":
                publish_runtime_change(writer, lambda connection, repo: repo.apply_task(connection, updated))
            else:
                writer.publish_memory_plane_batch((CanonicalMemoryRecord(
                    memory_id="background-source", domain=MemoryDomain.TRANSCRIPT, text="background",
                    source_kind="fixture", status=CommitStatus.COMMITTED,
                ),))

        def retain_source() -> CanonicalMemoryRecord:
            nonlocal reader_thread
            reader_thread = get_ident()
            return capture.retain(source, "foreground source")

        monkeypatch.setattr(writer._control, "write_intent", write_intent)
        monkeypatch.setattr(writer, "_finalize_publication", finalize)
        monkeypatch.setattr(file_lock, "_acquire", acquire)
        with ThreadPoolExecutor(max_workers=2) as executor:
            publish_future = executor.submit(publish)
            try:
                assert paused.wait(timeout=10)
                read_future = executor.submit(retain_source)
                assert attempted.wait(timeout=10)
                if entered_while_pending:
                    read_future.result(timeout=5)
                    pytest.fail("managed capture entered the partition during a live publication")
            finally:
                release.set()
            publish_future.result(timeout=10)
            retained = read_future.result(timeout=10)
        assert retained.text == "foreground source"
        snapshot = reader.acquire_verified_snapshot()

    with StorageAdministrationService(root) as reopened:
        assert reopened.acquire_verified_snapshot() == snapshot
        assert reopened.memory_plane_store().get_record(retained.memory_id) == retained


def test_managed_source_admission_uses_indexed_reads_and_recovers_exact_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    first, second = _TASK.source_inputs()
    with StorageAdministrationService(tmp_path / "installation") as service:
        installed = service.initialize()
        _publish_changes(service, _execution_changes((_TASK,)))
        capture = ReferenceSourceCapture(service, installed, (_TASK.task_id,))
        capture.capture(first)
        partition = service.partition()
        before = service.acquire_verified_snapshot()

        def reject_full_scan(_connection: sqlite3.Connection, **_filters: object) -> None:
            pytest.fail("native source capture scanned the entire current-record table")

        monkeypatch.setattr(partition, "read_current_record_rows", reject_full_scan)
        reference = capture.capture(second)
        after = service.acquire_verified_snapshot()
        assert after.vector.memory_write_revision == before.vector.memory_write_revision + 1
        assert after.vector.runtime_position != before.vector.runtime_position

        retained = capture.retain(second, second.body().decode("ascii"))
        assert retained.memory_id == reference.source_id
        assert record_digest(retained) == reference.source_digest
        assert service.acquire_verified_snapshot() == after

    with StorageAdministrationService(tmp_path / "installation") as reopened:
        assert reopened.acquire_verified_snapshot() == after
        retained = reopened.memory_plane_store().get_record(reference.source_id)
        assert retained is not None
        assert retained.text.encode("ascii") == second.body()
        partition = reopened.partition()
        with partition.transaction(write=False) as connection:
            row = partition.read_runtime_row(
                connection, table="runtime_command_receipts", match=(("operation_id", f"{second.coordinate}:observe"),),
            )
        assert row is not None
        receipt = RuntimeCommandReceipt.model_validate_json(row["record_json"])
        assert receipt.status == "committed"
        assert receipt.source_admission is not None
        assert receipt.source_admission.source_record_digest == reference.source_digest


def test_indexed_admission_retains_revision_and_cas_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    first, second = _TASK.source_inputs()
    with StorageAdministrationService(tmp_path / "installation") as service:
        service.initialize()
        capture = ReferenceSourceCapture(service)
        capture.retain(first, first.body().decode("ascii"))
        before = service.acquire_verified_snapshot()
        partition = service.partition()

        def reject_full_scan(_connection: sqlite3.Connection, **_filters: object) -> None:
            pytest.fail("source admission CAS scanned the entire current-record table")

        monkeypatch.setattr(partition, "read_current_record_rows", reject_full_scan)
        original_publish = service.publish_memory_plane_batch

        def publish_after_stale_writer_check(
            records: tuple[CanonicalMemoryRecord, ...], **kwargs,
        ):
            current = kwargs["preconditions"]
            assert sum(isinstance(entry, RecordDigestPrecondition) for entry in current) == 1
            stale = tuple(
                entry.model_copy(update={"expected_digest": "0" * 64})
                if isinstance(entry, RecordDigestPrecondition) else entry
                for entry in current
            )
            with pytest.raises(MemoryPlaneRevisionConflictError, match="record_digest"):
                original_publish(records, **{**kwargs, "preconditions": stale})
            assert service.acquire_verified_snapshot() == before
            return original_publish(records, **kwargs)

        with patch.object(service, "publish_memory_plane_batch", side_effect=publish_after_stale_writer_check) as publish:
            capture.retain(second, second.body().decode("ascii"))
        publish.assert_called_once()
        assert publish.call_args is not None
        args, kwargs = publish.call_args
        records, = args
        policy = kwargs["store"]._governed_write_policy
        assert isinstance(policy, IndexedGovernedWritePolicy)
        assert policy.required_current_record_ids(records, kwargs["authorization"])
        base_records = tuple(
            record for record in records if record.source_kind != "semantic_ingestion_source_retention_attestation"
        )
        assert len(base_records) == 5
        extra = CanonicalMemoryRecord(
            memory_id="semantic_ingestion:shape-slack", domain=MemoryDomain.EXECUTION,
            source_kind="semantic_ingestion_authorization_authority", status=CommitStatus.COMMITTED,
            visibility=MemoryRecordVisibility.INTERNAL_CONTROL, text="",
        )
        assert policy.required_current_record_ids((*base_records, extra), kwargs["authorization"]) is None
        after = service.acquire_verified_snapshot()

        with pytest.raises(MemoryPlaneRevisionConflictError, match="memory-plane write revision changed"):
            service.publish_memory_plane_batch(
                *args, **{**kwargs, "expected_write_revision": before.vector.memory_write_revision},
            )
        with pytest.raises(MemoryPlaneRevisionConflictError, match="record_absent"):
            service.publish_memory_plane_batch(*args, **kwargs)
        assert service.acquire_verified_snapshot() == after


def test_other_governed_policies_keep_full_validation_context(tmp_path: Path) -> None:
    class FullContextPolicy:
        def validate(
            self,
            records: tuple[CanonicalMemoryRecord, ...],
            current: tuple[CanonicalMemoryRecord, ...],
            authorization: MemoryPlaneWriteAuthorization | None,
        ) -> None:
            assert records == (replacement,)
            assert current == (existing,)
            assert authorization is None

    existing = CanonicalMemoryRecord(
        memory_id="source:existing", domain=MemoryDomain.TRANSCRIPT, text="unrelated current record",
        status=CommitStatus.COMMITTED,
    )
    replacement = CanonicalMemoryRecord(
        memory_id="source:new", domain=MemoryDomain.TRANSCRIPT, text="next current record",
        status=CommitStatus.COMMITTED,
    )
    with StorageAdministrationService(tmp_path / "installation") as service:
        service.initialize()
        store = service.memory_plane_store()
        service.publish_memory_plane_batch((existing,), store=store)
        store.install_governed_write_policy(FullContextPolicy())
        service.publish_memory_plane_batch((replacement,), store=store)
        assert store.get_record(replacement.memory_id) == replacement
