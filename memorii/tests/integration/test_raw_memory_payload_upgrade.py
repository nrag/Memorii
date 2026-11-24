"""Exercise the raw payload format through verified installation owners."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import pytest
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.store import PersistedBatch
from memorii.core.persistence.factory import open_managed_partition
from memorii.core.storage_administration import operator_backup
from memorii.core.storage_administration.generation_selection import PARTITION_GENERATION_SELECTOR
from memorii.core.storage_administration.operator import (
    ModeChangeRequest,
    OperatorError,
    OwnerCapability,
    StorageAdministrationOperator,
    mint_owner_capability,
)
from memorii.core.storage_administration.operator_backup import BackupRestoreOperator, RestorePlan
from memorii.core.storage_administration.service import InstallationIntegrityError, StorageAdministrationService
from memorii.domain.enums import CommitStatus, MemoryDomain
from memorii.stores.sqlite.raw_memory_payloads import payload_digest
from memorii.tools.runtime_operator import main as operator_main

_RECOVERY_KEY = b"x" * 32


def _record(memory_id: str, text: str) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=memory_id,
        domain=MemoryDomain.TRANSCRIPT,
        text=text,
        content={"evidence": "retained", "coordinates": [1, 2]},
        status=CommitStatus.COMMITTED,
        source_kind="raw_fixture",
        task_id="task:retained",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _stage_current(
    service: StorageAdministrationService, workspace: Path,
) -> tuple[BackupRestoreOperator, OwnerCapability, RestorePlan, Path]:
    workspace.mkdir()
    owner = mint_owner_capability(service, "owner:payload-test")
    operator = StorageAdministrationOperator(service)
    operator.change_mode(
        ModeChangeRequest(
            target_mode="read_only", expected_control_revision=operator.status().control_revision,
            reason="review an exact current restore",
        ),
        capability=owner,
    )
    archive, staging = workspace / "archive", workspace / "stage"
    backups = BackupRestoreOperator(operator)
    backups.create_backup(capability=owner, archive_root=archive, reason="verify format", recovery_key=_RECOVERY_KEY)
    plan = backups.plan_restore(capability=owner, archive_root=archive, data_loss_acknowledged=False)
    backups.apply_restore(capability=owner, plan=plan, staging_root=staging, recovery_key=_RECOVERY_KEY)
    return backups, owner, plan, staging


def _activate_raw(service: StorageAdministrationService, workspace: Path) -> None:
    backups, owner, plan, staging = _stage_current(service, workspace)
    preview = backups.preview_staged_restore(capability=owner, plan=plan, staging_root=staging, raw_payloads=True)
    assert backups.upgrade_current_runtime(
        capability=owner, plan=plan, staging_root=staging, preview_digest=preview.digest(), raw_payloads=True,
    ).phase == "finalized"


def test_owner_upgrades_exact_reviewed_v7_and_reopens_raw_partition(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "installation"
    original = _record("memory:first", "first \u00e9vidence")
    second = _record("memory:second", "other evidence")
    updated = original.model_copy(update={"text": "changed \u00e9vidence"})
    with StorageAdministrationService(root) as service:
        service.initialize()
        original_path = service.partition_path()
        with service.partition().transaction(write=False) as connection:
            assert service.partition().read_schema_version(connection) == 7
        service.publish_memory_plane_batch((original, second))
        service.publish_memory_plane_batch((original,))
        service.publish_memory_plane_batch((updated,))
        service.publish_memory_plane_batch(())
        with service.partition().transaction(write=False) as connection:
            original_batches = [tuple(row) for row in service.partition().iter_batch_rows(connection)]
        initial = service.acquire_verified_snapshot()
        assert (initial.vector.memory_write_revision, initial.vector.memory_data_revision) == (4, 3)
        backups, owner, plan, staging = _stage_current(service, tmp_path / "upgrade")
        ordinary = backups.preview_staged_restore(capability=owner, plan=plan, staging_root=staging)
        candidate = backups.preview_staged_restore(capability=owner, plan=plan, staging_root=staging, raw_payloads=True)
        assert candidate.digest() != ordinary.digest()
        with pytest.raises(OperatorError, match="exact reviewed"):
            backups.upgrade_current_runtime(
                capability=owner, plan=plan, staging_root=staging, preview_digest=ordinary.digest(), raw_payloads=True,
            )
        with pytest.raises(OperatorError, match="exact reviewed"):
            backups.upgrade_current_runtime(
                capability=owner, plan=plan, staging_root=staging, preview_digest=candidate.digest(),
            )
        assert service.partition_path() == original_path

        plan_file = tmp_path / "restore-plan.json"
        plan_file.write_text(plan.model_dump_json(), encoding="utf-8")
        operator_args = [
            "--installation-root", str(root), "--owner-principal", owner.owner_principal,
            "--capability-digest", owner.capability_digest, "backup",
        ]
        stage_args = ["--plan-file", str(plan_file), "--staging-root", str(staging)]
        assert operator_main([*operator_args, "restore-preview-stage", *stage_args, "--raw-payloads"]) == 0
        preview_output = json.loads(capsys.readouterr().out)
        assert preview_output["preview_digest"] == candidate.digest()
        assert preview_output["raw_payload_upgrade"]["source_schema_version"] == 7
        assert preview_output["raw_payload_upgrade"]["target_schema_version"] == 8
        assert operator_main([
            *operator_args, "upgrade-runtime", *stage_args, "--raw-payloads", "--preview-digest", candidate.digest(),
        ]) == 0
        assert json.loads(capsys.readouterr().out)["status"] == "selected"

    administration, memory = open_managed_partition(root)
    with administration:
        assert administration.partition_path() != original_path
        checked = administration.acquire_verified_snapshot()
        assert (checked.vector.memory_write_revision, checked.vector.memory_data_revision) == (4, 3)
        partition = administration.partition()
        with partition.transaction(write=False) as connection:
            assert partition.read_schema_version(connection) == 8
            assert [tuple(row) for row in partition.iter_batch_rows(connection)] == original_batches
            assert connection.execute("SELECT count(*) FROM memory_payloads").fetchone()[0] == 3
            assert connection.execute("SELECT count(*) FROM memory_batch_members").fetchone()[0] == 4
        assert memory.get_record(original.memory_id) == updated
        assert memory.list_records(source_kind="raw_fixture") == [updated, second]
        operator = StorageAdministrationOperator(administration)
        retry = BackupRestoreOperator(operator).upgrade_current_runtime(
            capability=owner, plan=plan, staging_root=staging, preview_digest=candidate.digest(), raw_payloads=True,
        )
        assert retry.phase == "finalized"
        assert administration.acquire_verified_snapshot() == checked
        with pytest.raises(OperatorError):
            BackupRestoreOperator(operator).upgrade_current_runtime(
                capability=owner, plan=plan, staging_root=staging, preview_digest=candidate.digest(),
            )
        operator.change_mode(
            ModeChangeRequest(
                target_mode="active", expected_control_revision=operator.status().control_revision,
                reason="resume verified publications",
            ),
            capability=owner,
        )
        final = _record("memory:third", "written on the new format")
        administration.publish_memory_plane_batch((final,))
        administration.publish_memory_plane_batch((final,))
        completed = administration.acquire_verified_snapshot()
        assert (completed.vector.memory_write_revision, completed.vector.memory_data_revision) == (6, 5)

    with StorageAdministrationService(root) as reopened:
        assert reopened.acquire_verified_snapshot() == completed
        with reopened.partition().transaction(write=False) as connection:
            assert connection.execute("SELECT count(*) FROM memory_payloads").fetchone()[0] == 4
            assert connection.execute("SELECT count(*) FROM memory_batch_members").fetchone()[0] == 6
        assert reopened.memory_plane_store().list_records(source_kind="raw_fixture") == [updated, second, final]
        backups, owner, plan, staging = _stage_current(reopened, tmp_path / "round-trip")
        backups.verify_staged_restore(capability=owner, plan=plan, staging_root=staging)
        published = reopened.acquire_verified_snapshot()
        backups.activate_exact_current_restore(capability=owner, plan=plan, staging_root=staging)
        assert reopened.acquire_verified_snapshot() == published


@pytest.mark.parametrize("write_selector", [False, True], ids=["before-selector", "after-selector"])
def test_interrupted_raw_cutover_recovers_the_selected_signed_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, write_selector: bool,
) -> None:
    root = tmp_path / "installation"
    record = _record("memory:existing", "retained on failed upgrade")
    with StorageAdministrationService(root) as service:
        service.initialize()
        service.publish_memory_plane_batch((record,))
        backups, owner, plan, staging = _stage_current(service, tmp_path / "upgrade")
        original = service.acquire_verified_snapshot()
        original_path = service.partition_path()
        preview = backups.preview_staged_restore(capability=owner, plan=plan, staging_root=staging, raw_payloads=True)
        atomic_write = operator_backup._atomic_write
        selector_write_attempted = False

        def fail_selection(path: Path, value: bytes) -> None:
            nonlocal selector_write_attempted
            if path.name == PARTITION_GENERATION_SELECTOR:
                selector_write_attempted = True
                if write_selector:
                    atomic_write(path, value)
                raise OSError("interrupted raw generation selection")
            atomic_write(path, value)

        with monkeypatch.context() as crash:
            crash.setattr(operator_backup, "_atomic_write", fail_selection)
            with pytest.raises(OperatorError, match="could not be prepared or published"):
                backups.upgrade_current_runtime(
                    capability=owner, plan=plan, staging_root=staging, preview_digest=preview.digest(), raw_payloads=True,
                )
        assert selector_write_attempted

    with StorageAdministrationService(root) as reopened:
        recovered = reopened.acquire_verified_snapshot()
        selected_v7 = not write_selector
        assert (reopened.partition_path() == original_path) is selected_v7
        assert (recovered == original) is selected_v7
        assert recovered.vector.memory_write_revision == original.vector.memory_write_revision
        assert recovered.vector.memory_data_revision == original.vector.memory_data_revision
        with reopened.partition().transaction(write=False) as connection:
            assert reopened.partition().read_schema_version(connection) == (7 if selected_v7 else 8)
        assert reopened.memory_plane_store().get_record(record.memory_id) == record


def _mutate_rootpage(db: Path, schema_name: str, replacements: tuple[tuple[bytes, bytes], ...]) -> None:
    with closing(sqlite3.connect(db)) as connection:
        rootpage = connection.execute("SELECT rootpage FROM sqlite_schema WHERE name=?", (schema_name,)).fetchone()[0]
        page_size = connection.execute("PRAGMA page_size").fetchone()[0]
    offset = (rootpage - 1) * page_size
    with db.open("r+b") as handle:
        handle.seek(offset)
        page = handle.read(page_size)
        for original, replacement in replacements:
            assert page.count(original) == 1 and len(replacement) == len(original)
            page = page.replace(original, replacement, 1)
        handle.seek(offset)
        handle.write(page)


@pytest.mark.parametrize("page", ["body", "table", "index", "selector_index"])
def test_preserved_head_raw_mutation_fails_fresh_acquisition(tmp_path: Path, page: str) -> None:
    root = tmp_path / "installation"
    with StorageAdministrationService(root) as service:
        service.initialize()
        service.publish_memory_plane_batch((_record("memory:existing", "signed payload"),))
        _activate_raw(service, tmp_path / "upgrade")
    with StorageAdministrationService(root) as converted:
        converted.acquire_verified_snapshot()
        db = converted.partition_path()
    if page == "body":
        with closing(sqlite3.connect(db)) as connection, connection:
            connection.execute("UPDATE memory_payloads SET body=zeroblob(length(body))")
    elif page == "selector_index":
        _mutate_rootpage(db, "memory_current_records_task_id", ((b"task:retained", b"task:forged__"),))
    else:
        # Keep all other pages and the signed head unchanged. A covering
        # index could otherwise report the old digest for a changed body.
        schema_name = "memory_payloads" if page == "table" else "memory_payloads_digest"
        with closing(sqlite3.connect(db)) as connection:
            original_digest, body = connection.execute("SELECT payload_digest,body FROM memory_payloads").fetchone()
        alternate = body.replace(b"signed payload", b"forged payload", 1)
        assert body != alternate and len(body) == len(alternate)
        replacements = ((original_digest, payload_digest(alternate)),)
        if page == "table":
            replacements += ((body, alternate),)
        _mutate_rootpage(db, schema_name, replacements)
    with StorageAdministrationService(root) as reopened, pytest.raises(InstallationIntegrityError):
        reopened.acquire_verified_snapshot()


def test_older_restore_keeps_the_attested_raw_format(tmp_path: Path) -> None:
    root = tmp_path / "installation"
    record = _record("memory:retained", "on the archived generation")
    newer = _record("memory:discarded", "published after the backup")
    with StorageAdministrationService(root) as service:
        service.initialize()
        service.publish_memory_plane_batch((record,))
        _activate_raw(service, tmp_path / "upgrade")

    with StorageAdministrationService(root) as converted:
        archive = tmp_path / "raw-archive"
        staging = tmp_path / "raw-stage"
        owner = mint_owner_capability(converted, "owner:payload-test")
        backups = BackupRestoreOperator(StorageAdministrationOperator(converted))
        backups.create_backup(capability=owner, archive_root=archive, reason="older raw restore", recovery_key=_RECOVERY_KEY)
        converted.publish_memory_plane_batch((newer,), operation_binding="migrate")
        plan = backups.plan_restore(capability=owner, archive_root=archive, data_loss_acknowledged=True)
        backups.apply_restore(capability=owner, plan=plan, staging_root=staging, recovery_key=_RECOVERY_KEY)
        preview = backups.preview_staged_restore(capability=owner, plan=plan, staging_root=staging)
        restored = backups.activate_older_restore(
            capability=owner, plan=plan, staging_root=staging, preview_digest=preview.digest(),
        )
        assert restored.phase == "finalized"

    with StorageAdministrationService(root) as reopened:
        assert reopened.acquire_verified_snapshot().tuple_digest == restored.candidate_publication.payload_digest()
        with reopened.partition().transaction(write=False) as connection:
            assert reopened.partition().read_schema_version(connection) == 8
        assert reopened.memory_plane_store().list_records() == [record]


def test_signed_noncanonical_batch_framing_refuses_upgrade_preview(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _record("memory:existing", "private framing fixture")
    original_encoder = PersistedBatch.model_dump_json

    def alternate_framing(batch: PersistedBatch) -> str:
        return original_encoder(batch).replace('{"revision":', '{ "revision":', 1)

    with StorageAdministrationService(tmp_path / "installation") as service:
        service.initialize()
        with monkeypatch.context() as historic:
            historic.setattr(PersistedBatch, "model_dump_json", alternate_framing)
            service.publish_memory_plane_batch((record,))
        backups, owner, plan, staging = _stage_current(service, tmp_path / "upgrade")
        before = service.acquire_verified_snapshot()
        ordinary = backups.preview_staged_restore(capability=owner, plan=plan, staging_root=staging)
        assert ordinary.staged_publication_digest == before.tuple_digest
        with pytest.raises(OperatorError, match="unsupported_configuration: .*framing") as refused:
            backups.preview_staged_restore(capability=owner, plan=plan, staging_root=staging, raw_payloads=True)
        assert record.text not in str(refused.value)
        assert service.acquire_verified_snapshot() == before
        assert service.memory_plane_store().get_record(record.memory_id) == record
