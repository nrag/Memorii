"""Exercise the owner backup path across its two short publication fences."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
from pathlib import Path
from threading import Event

import pytest
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.storage_administration import operator_backup
from memorii.core.storage_administration.operator import (
    InstallationMode,
    ModeChangeRequest,
    OperatorError,
    OwnerCapability,
    StorageAdministrationOperator,
    mint_owner_capability,
)
from memorii.core.storage_administration.operator_backup import BackupRestoreOperator, RestorePlan
from memorii.core.storage_administration.operator_governance import ForgetTargetSelector, GovernanceOperator
from memorii.core.storage_administration.service import StorageAdministrationService
from memorii.domain.enums import CommitStatus, MemoryDomain

_RECOVERY_KEY = b"k" * 32
_OWNER = "owner:backup-test"
_TIMEOUT = 10


def _record(identity: str) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=identity, domain=MemoryDomain.TRANSCRIPT, source_kind="backup_fixture",
        text=identity, status=CommitStatus.COMMITTED,
    )


def _set_mode(operator: StorageAdministrationOperator, owner: OwnerCapability, mode: InstallationMode) -> None:
    operator.change_mode(
        ModeChangeRequest(
            target_mode=mode, expected_control_revision=operator.status().control_revision,
            reason="backup concurrency fixture",
        ),
        capability=owner,
    )


@pytest.fixture
def installation(tmp_path: Path) -> Path:
    root = tmp_path / "installation"
    with StorageAdministrationService(root) as service:
        service.initialize()
        service.publish_memory_plane_batch((_record("memory:before"),))
        _set_mode(StorageAdministrationOperator(service), mint_owner_capability(service, _OWNER), "read_only")
    return root


def _stage_raw(
    backups: BackupRestoreOperator, owner: OwnerCapability, tmp_path: Path,
) -> tuple[RestorePlan, Path, str]:
    archive, staging = tmp_path / "source", tmp_path / "stage"
    backups.create_backup(capability=owner, archive_root=archive, reason="prepare staged upgrade", recovery_key=_RECOVERY_KEY)
    plan = backups.plan_restore(capability=owner, archive_root=archive, data_loss_acknowledged=False)
    backups.apply_restore(capability=owner, plan=plan, staging_root=staging, recovery_key=_RECOVERY_KEY)
    preview = backups.preview_staged_restore(capability=owner, plan=plan, staging_root=staging, raw_payloads=True)
    return plan, staging, preview.digest()


@pytest.mark.parametrize("raw", [False, True])
def test_backup_copies_the_pinned_pair_while_a_signed_writer_advances(
    installation: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, raw: bool,
) -> None:
    if raw:
        with StorageAdministrationService(installation) as service:
            backups = BackupRestoreOperator(StorageAdministrationOperator(service))
            owner = mint_owner_capability(service, _OWNER)
            plan, staging, preview_digest = _stage_raw(backups, owner, tmp_path)
            assert backups.upgrade_current_runtime(
                capability=owner, plan=plan, staging_root=staging, preview_digest=preview_digest, raw_payloads=True,
            ).phase == "finalized"

    def publish() -> str:
        with StorageAdministrationService(installation) as writer:
            operator = StorageAdministrationOperator(writer)
            owner = mint_owner_capability(writer, _OWNER)
            _set_mode(operator, owner, "active")
            writer.publish_memory_plane_batch((_record("memory:queued"),))
            _set_mode(operator, owner, "read_only")
            return writer.acquire_verified_snapshot().tuple_digest

    original_copy = operator_backup._sqlite_backup
    advanced: list[str] = []
    archive = tmp_path / "archive"
    with ThreadPoolExecutor(max_workers=1) as executor, StorageAdministrationService(installation) as service:
        expected = service.acquire_verified_snapshot().tuple_digest

        def copy_after_publication(source: sqlite3.Connection, destination: Path) -> None:
            if destination.name == "control.sqlite3":
                # A writer completes before either copy starts. Holding the
                # publication fence during this callback makes the test time out.
                advanced.append(executor.submit(publish).result(timeout=_TIMEOUT))
            original_copy(source, destination)

        monkeypatch.setattr(operator_backup, "_sqlite_backup", copy_after_publication)
        backups = BackupRestoreOperator(StorageAdministrationOperator(service))
        owner = mint_owner_capability(service, _OWNER)
        manifest = backups.create_backup(
            capability=owner, archive_root=archive, reason="verify paired snapshots", recovery_key=_RECOVERY_KEY,
        )
        assert len(advanced) == 1 and advanced[0] != expected
        assert service.acquire_verified_snapshot().tuple_digest == advanced[0]
        assert manifest.publication_digest == expected
        assert backups.verify_backup(archive_root=archive) == manifest

        plan = backups.plan_restore(capability=owner, archive_root=archive, data_loss_acknowledged=True)
        staged = tmp_path / "archived"
        backups.apply_restore(capability=owner, plan=plan, staging_root=staged, recovery_key=_RECOVERY_KEY)
        with closing(sqlite3.connect(staged / "partition.sqlite3")) as connection:
            assert connection.execute("SELECT memory_id FROM memory_current_records").fetchall() == [("memory:before",)]
            assert connection.execute("SELECT tuple_digest FROM partition_publication WHERE id=1").fetchone() == (expected,)


@pytest.mark.parametrize("failed_copy", ["control.sqlite3", "partition.sqlite3"])
def test_copy_failure_closes_both_pins_and_leaves_the_archive_path_retryable(
    installation: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failed_copy: str,
) -> None:
    original_copy = operator_backup._sqlite_backup
    original_open = operator_backup._open_backup_snapshot
    sources: list[sqlite3.Connection] = []
    archive = tmp_path / "archive"

    @contextmanager
    def observed_pin(path: Path) -> Iterator[sqlite3.Connection]:
        with original_open(path) as connection:
            sources.append(connection)
            yield connection

    def interrupted_copy(source: sqlite3.Connection, destination: Path) -> None:
        if destination.name == failed_copy:
            destination.write_bytes(b"partial SQLite copy")
            raise OSError("injected copy failure")
        original_copy(source, destination)

    with StorageAdministrationService(installation) as service:
        expected = service.acquire_verified_snapshot().tuple_digest
        backups = BackupRestoreOperator(StorageAdministrationOperator(service))
        owner = mint_owner_capability(service, _OWNER)
        with monkeypatch.context() as broken:
            broken.setattr(operator_backup, "_open_backup_snapshot", observed_pin)
            broken.setattr(operator_backup, "_sqlite_backup", interrupted_copy)
            with pytest.raises(OperatorError, match="could not capture pinned backup snapshots"):
                backups.create_backup(
                    capability=owner, archive_root=archive, reason="inject copy failure", recovery_key=_RECOVERY_KEY,
                )
        assert len(sources) == 2
        for connection in sources:
            with pytest.raises(sqlite3.ProgrammingError, match="closed"):
                connection.execute("SELECT 1")
        assert not archive.exists()
        assert not list(tmp_path.glob(".backup-*"))
        assert not list((installation / "partition").glob(".backup-plaintext-*"))

        recovered = backups.create_backup(
            capability=owner, archive_root=archive, reason="retry copy failure", recovery_key=_RECOVERY_KEY,
        )
        assert recovered.publication_digest == expected


def test_backup_refuses_a_generation_switch_after_both_snapshots_are_pinned(
    installation: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    with StorageAdministrationService(installation) as service:
        owner = mint_owner_capability(service, _OWNER)
        backups = BackupRestoreOperator(StorageAdministrationOperator(service))
        plan, staging, preview_digest = _stage_raw(backups, owner, tmp_path)

    def upgrade() -> str:
        with StorageAdministrationService(installation) as service:
            operator = StorageAdministrationOperator(service)
            intent = BackupRestoreOperator(operator).upgrade_current_runtime(
                capability=mint_owner_capability(service, _OWNER), plan=plan, staging_root=staging,
                preview_digest=preview_digest, raw_payloads=True,
            )
            return intent.candidate_publication.payload_digest()

    original_copy = operator_backup._sqlite_backup
    upgrades: list[str] = []
    archive = tmp_path / "archive"
    with ThreadPoolExecutor(max_workers=1) as executor, StorageAdministrationService(installation) as service:
        expected = service.acquire_verified_snapshot().tuple_digest

        def copy_after_upgrade(source: sqlite3.Connection, destination: Path) -> None:
            if destination.name == "control.sqlite3":
                upgrades.append(executor.submit(upgrade).result(timeout=_TIMEOUT))
            original_copy(source, destination)

        monkeypatch.setattr(operator_backup, "_sqlite_backup", copy_after_upgrade)
        backups = BackupRestoreOperator(StorageAdministrationOperator(service))
        owner = mint_owner_capability(service, _OWNER)
        with pytest.raises(OperatorError, match="backup authority changed before archive publication"):
            backups.create_backup(
                capability=owner, archive_root=archive, reason="fail closed after cutover", recovery_key=_RECOVERY_KEY,
            )
    assert len(upgrades) == 1 and upgrades[0] != expected
    assert not archive.exists()
    assert not list(tmp_path.glob(".backup-*"))
    with StorageAdministrationService(installation) as reopened:
        assert reopened.acquire_verified_snapshot().tuple_digest == upgrades[0]


def test_second_pin_failure_closes_the_first_without_copying(
    installation: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_open = operator_backup._open_backup_snapshot
    sources: list[sqlite3.Connection] = []
    archive = tmp_path / "archive"

    @contextmanager
    def interrupt_partition_pin(path: Path) -> Iterator[sqlite3.Connection]:
        if path.name == "partition.sqlite3":
            raise sqlite3.OperationalError("injected snapshot pin failure")
        with original_open(path) as connection:
            sources.append(connection)
            yield connection

    def unexpected_copy(_source: sqlite3.Connection, _destination: Path) -> None:
        pytest.fail("SQLite copy started with only one participant pinned")

    monkeypatch.setattr(operator_backup, "_open_backup_snapshot", interrupt_partition_pin)
    monkeypatch.setattr(operator_backup, "_sqlite_backup", unexpected_copy)
    with StorageAdministrationService(installation) as service:
        owner = mint_owner_capability(service, _OWNER)
        backups = BackupRestoreOperator(StorageAdministrationOperator(service))
        with pytest.raises(OperatorError, match="could not capture pinned backup snapshots"):
            backups.create_backup(
                capability=owner, archive_root=archive, reason="inject pin failure", recovery_key=_RECOVERY_KEY,
            )
    assert len(sources) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        sources[0].execute("SELECT 1")
    assert not archive.exists()
    assert not list(tmp_path.glob(".backup-*"))


def test_pin_checks_the_partition_watermark_before_any_copy(
    installation: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_open = operator_backup._open_backup_snapshot
    archive = tmp_path / "archive"

    @contextmanager
    def pin_after_publication_tamper(path: Path) -> Iterator[sqlite3.Connection]:
        if path.name == "partition.sqlite3":
            with closing(sqlite3.connect(path)) as writer:
                writer.execute("UPDATE partition_publication SET tuple_digest = ? WHERE id = 1", ("0" * 64,))
                writer.commit()
        with original_open(path) as connection:
            yield connection

    def unexpected_copy(_source: sqlite3.Connection, _destination: Path) -> None:
        pytest.fail("copy started with a participant outside the selected watermark")

    monkeypatch.setattr(operator_backup, "_open_backup_snapshot", pin_after_publication_tamper)
    monkeypatch.setattr(operator_backup, "_sqlite_backup", unexpected_copy)
    with StorageAdministrationService(installation) as service:
        owner = mint_owner_capability(service, _OWNER)
        backups = BackupRestoreOperator(StorageAdministrationOperator(service))
        with pytest.raises(OperatorError, match="pinned backup snapshots differ from the selected watermark"):
            backups.create_backup(
                capability=owner, archive_root=archive, reason="inject pin drift", recovery_key=_RECOVERY_KEY,
            )
    assert not archive.exists()
    assert not list(tmp_path.glob(".backup-*"))


def test_copy_deadline_refuses_the_archive_and_allows_retry(
    installation: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = tmp_path / "archive"
    with StorageAdministrationService(installation) as service:
        expected = service.acquire_verified_snapshot().tuple_digest
        owner = mint_owner_capability(service, _OWNER)
        backups = BackupRestoreOperator(StorageAdministrationOperator(service))
        with monkeypatch.context() as expired:
            expired.setattr(operator_backup, "_SQLITE_BACKUP_TIMEOUT_SECONDS", 0)
            with pytest.raises(OperatorError, match="pinned SQLite backup copy deadline exceeded"):
                backups.create_backup(
                    capability=owner, archive_root=archive, reason="expire snapshot copy", recovery_key=_RECOVERY_KEY,
                )
        assert not archive.exists()
        assert not list(tmp_path.glob(".backup-*"))
        recovered = backups.create_backup(
            capability=owner, archive_root=archive, reason="retry expired snapshot copy", recovery_key=_RECOVERY_KEY,
        )
        assert recovered.publication_digest == expected


def test_backup_refuses_a_suppression_committed_during_copy(
    installation: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forget() -> str:
        with StorageAdministrationService(installation) as service:
            owner = mint_owner_capability(service, _OWNER)
            governance = GovernanceOperator(StorageAdministrationOperator(service))
            plan = governance.plan_forget(
                capability=owner, scope_note="request arrives during copy",
                selectors=(ForgetTargetSelector(selector_kind="record", selector_id="memory:before"),),
            )
            return governance.apply_forget(capability=owner, plan=plan).suppression_id

    original_copy = operator_backup._sqlite_backup
    suppressed: list[str] = []
    archive = tmp_path / "archive"
    with ThreadPoolExecutor(max_workers=1) as executor, StorageAdministrationService(installation) as service:
        def copy_after_forget(source: sqlite3.Connection, destination: Path) -> None:
            if destination.name == "control.sqlite3":
                suppressed.append(executor.submit(forget).result(timeout=_TIMEOUT))
            original_copy(source, destination)

        monkeypatch.setattr(operator_backup, "_sqlite_backup", copy_after_forget)
        owner = mint_owner_capability(service, _OWNER)
        backups = BackupRestoreOperator(StorageAdministrationOperator(service))
        with pytest.raises(OperatorError, match="backup authority changed before archive publication"):
            backups.create_backup(
                capability=owner, archive_root=archive, reason="fail closed after forget", recovery_key=_RECOVERY_KEY,
            )
    assert len(suppressed) == 1
    assert not archive.exists()
    assert not list(tmp_path.glob(".backup-*"))


def test_erasure_waits_for_backup_plaintext_cleanup(
    installation: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = tmp_path / "archive"
    copy_started = Event()
    erasure_waiting = Event()
    partition = installation / "partition"
    original_copy = operator_backup._sqlite_backup
    original_guard = operator_backup._backup_lifetime_guard

    @contextmanager
    def observed_guard(service: StorageAdministrationService, *, exclusive: bool) -> Iterator[None]:
        if exclusive:
            erasure_waiting.set()
        with original_guard(service, exclusive=exclusive):
            if exclusive:
                assert archive.is_dir()
                assert not list(tmp_path.glob(".backup-*"))
                assert not list(partition.glob(".backup-plaintext-*"))
            yield

    def copy_during_erasure_request(source: sqlite3.Connection, destination: Path) -> None:
        if destination.name == "control.sqlite3":
            assert destination.is_relative_to(partition)
            assert list(partition.glob(".backup-plaintext-*"))
            copy_started.set()
            assert erasure_waiting.wait(timeout=_TIMEOUT)
        original_copy(source, destination)

    def make_backup() -> str:
        with StorageAdministrationService(installation) as service:
            owner = mint_owner_capability(service, _OWNER)
            backups = BackupRestoreOperator(StorageAdministrationOperator(service))
            return backups.create_backup(
                capability=owner, archive_root=archive, reason="verify erasure ordering", recovery_key=_RECOVERY_KEY,
            ).manifest_digest

    def erase() -> bool:
        with StorageAdministrationService(installation) as service:
            owner = mint_owner_capability(service, _OWNER)
            governance = GovernanceOperator(StorageAdministrationOperator(service))
            reviewed = governance.plan_erasure(capability=owner).model_copy(update={"acknowledged": True})
            return governance.apply_erasure(capability=owner, plan=reviewed, erase=True).incomplete

    monkeypatch.setattr(operator_backup, "_backup_lifetime_guard", observed_guard)
    monkeypatch.setattr(operator_backup, "_sqlite_backup", copy_during_erasure_request)
    with ThreadPoolExecutor(max_workers=2) as executor:
        backup = executor.submit(make_backup)
        assert copy_started.wait(timeout=_TIMEOUT)
        erasure = executor.submit(erase)
        assert backup.result(timeout=_TIMEOUT)
        assert erasure.result(timeout=_TIMEOUT)  # The external archive is unaccounted for.
    assert not (installation / "partition").exists()


def test_whole_partition_erasure_removes_plaintext_from_an_interrupted_backup(
    installation: Path,
) -> None:
    orphan = installation / "partition" / ".backup-plaintext-interrupted"
    orphan.mkdir(mode=0o700)
    plaintext = orphan / "partition.sqlite3"
    plaintext.write_bytes(b"unfinished plaintext snapshot")

    with StorageAdministrationService(installation) as service:
        owner = mint_owner_capability(service, _OWNER)
        governance = GovernanceOperator(StorageAdministrationOperator(service))
        reviewed = governance.plan_erasure(capability=owner).model_copy(update={"acknowledged": True})
        assert governance.apply_erasure(capability=owner, plan=reviewed, erase=True).incomplete

    assert not plaintext.exists()
    assert not orphan.exists()
    assert not (installation / "partition").exists()
