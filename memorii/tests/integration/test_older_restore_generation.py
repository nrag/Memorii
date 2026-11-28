"""Owner cutover and interruption recovery from an older authenticated backup."""

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import pytest
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.persistence.managed_delivery import DeliveryRestoreHold
from memorii.core.persistence.runtime_api import LegacyUnresolvedDelivery, RuntimeOutboxDelivery
from memorii.core.persistence.runtime_contracts import TaskRecord
from memorii.core.persistence.runtime_repository import RuntimeStateRepository, publish_runtime_change
from memorii.core.storage_administration import operator_backup
from memorii.core.storage_administration.generation_selection import PARTITION_GENERATION_SELECTOR
from memorii.core.storage_administration.operator import (
    ModeChangeRequest,
    OperatorError,
    StorageAdministrationOperator,
    mint_owner_capability,
)
from memorii.core.storage_administration.operator_backup import BackupRestoreOperator
from memorii.core.storage_administration.service import (
    InstallationPermissionsError,
    StorageAdministrationError,
    StorageAdministrationService,
)
from memorii.domain.enums import CommitStatus, MemoryDomain
from memorii.tools.runtime_operator import main as operator_main
from tests.support.operator_files import write_owner_file


def _task(task_id: str) -> TaskRecord:
    return TaskRecord(
        task_id=task_id, principal="owner:test", goal="Verify selected generation",
        created_at=datetime(2026, 1, 1, tzinfo=UTC), root_execution_node_id=f"exec:{task_id}",
    )


@pytest.mark.parametrize("cut", ["none", "before_selector", "after_selector", "invalid_selector", "permissions"])
def test_older_restore_recovers_exact_bytes_and_keeps_delivery_held(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], cut: str,
) -> None:
    root, archive, staging = tmp_path / "installed", tmp_path / "archive", tmp_path / "stage"
    key = b"k" * 32
    legacy = RuntimeOutboxDelivery(
        delivery_id="legacy:projection", origin_operation_id="task-start", kind="work_projection",
        payload_digest="a" * 64, target_protocol="local", fence_token=1,
    )
    with StorageAdministrationService(root) as service:
        service.initialize()
        operator = StorageAdministrationOperator(service)
        capability = mint_owner_capability(service, "owner:test")
        operator.change_mode(
            ModeChangeRequest(
                target_mode="read_only", expected_control_revision=operator.status().control_revision,
                reason="exercise owner restore",
            ),
            capability=capability,
        )
        publish_runtime_change(
            service, lambda connection, state: state.apply_task(connection, _task("task:retained")),
            operation_binding="migrate",
        )
        publish_runtime_change(
            service, lambda connection, state: state.apply_outbox_row(connection, legacy), operation_binding="migrate",
        )
        backups = BackupRestoreOperator(operator)
        backups.create_backup(capability=capability, archive_root=archive, reason="rollback checkpoint", recovery_key=key)

        publish_runtime_change(
            service, lambda connection, state: state.apply_task(connection, _task("task:postbackup")),
            operation_binding="migrate",
        )
        plan = backups.plan_restore(capability=capability, archive_root=archive, data_loss_acknowledged=True)
        backups.apply_restore(capability=capability, plan=plan, staging_root=staging, recovery_key=key)
        preview = backups.preview_staged_restore(capability=capability, plan=plan, staging_root=staging)
        repository_id = service._repository_id()
        old = service._control.read_publication_state(repository_id)
        assert old is not None
        with pytest.raises(OperatorError, match="exact reviewed"):
            backups.activate_older_restore(
                capability=capability, plan=plan, staging_root=staging, preview_digest="0" * 64,
            )
        if cut == "none":
            intent = backups.activate_older_restore(
                capability=capability, plan=plan, staging_root=staging, preview_digest=preview.digest(),
            )
            assert intent.phase == "finalized"
            with pytest.raises(StorageAdministrationError, match="reopen"), service.partition().transaction(write=False):
                pytest.fail("a retained physical store was used after generation selection")
        else:
            original = operator_backup._atomic_write

            def fail_selector(path: Path, value: bytes) -> None:
                if path.name != PARTITION_GENERATION_SELECTOR:
                    original(path, value)
                    return
                if cut in {"after_selector", "permissions"}:
                    original(path, value)
                elif cut == "invalid_selector":
                    original(path, b"invalid")
                raise OSError("interrupted selector publication")

            with monkeypatch.context() as crash:
                crash.setattr(operator_backup, "_atomic_write", fail_selector)
                with pytest.raises(OperatorError, match="could not be prepared or published"):
                    backups.activate_older_restore(
                        capability=capability, plan=plan, staging_root=staging, preview_digest=preview.digest(),
                    )
            pending = service._control.read_generation_change(repository_id)
            assert pending is not None and pending.phase == "prepared"
            with (
                pytest.raises(StorageAdministrationError, match="requires recovery"),
                service.partition().transaction(write=False),
            ):
                pytest.fail("a prepared generation change released partition data")

    if cut == "permissions":
        selected = root / "partition" / "generations"
        selected.chmod(0o755)
        with StorageAdministrationService(root) as unsafe:
            with pytest.raises(InstallationPermissionsError, match="repair-permissions"):
                unsafe.acquire_verified_snapshot()
            pending = unsafe._control.read_generation_change(repository_id)
            assert pending is not None and pending.phase == "prepared"
            assert unsafe._control_state().quarantined_reason is None
        assert operator_main(["--installation-root", str(root), "repair-permissions"]) == 0

    with StorageAdministrationService(root) as reopened:
        operator = StorageAdministrationOperator(reopened)
        if cut == "invalid_selector":
            with pytest.raises(StorageAdministrationError, match="quarantined"):
                reopened.acquire_verified_snapshot()
            quarantined = reopened._control.read_generation_change(repository_id)
            assert quarantined is not None and quarantined.phase == "quarantined"
            return
        status = operator.status()
        assert status.mode == "read_only"
        assert status.control_revision == plan.expected_control_revision + 2
        repository = RuntimeStateRepository(reopened.partition())
        intent = reopened._control.read_generation_change(repository_id)
        assert intent is not None
        if cut == "before_selector":
            assert intent.phase == "aborted"
            assert reopened.acquire_verified_snapshot().tuple_digest == old.payload_digest()
            assert repository.get_task("task:postbackup") is not None
            return

        assert intent.phase == "finalized"
        final = intent.candidate_publication
        assert final.data_generation_id != old.data_generation_id
        assert final.eligibility_epoch == old.eligibility_epoch
        assert final.runtime_history_ancestry[0].generation_id == old.data_generation_id
        assert repository.get_task("task:retained") is not None
        assert repository.get_task("task:postbackup") is None
        assert reopened.acquire_verified_snapshot().tuple_digest == final.payload_digest()
        partition = reopened.partition()
        with partition.transaction(write=False) as connection:
            row = connection.execute("SELECT record_json FROM runtime_delivery_restore_holds").fetchone()
            held = DeliveryRestoreHold.model_validate_json(row[0])
            assert held.restored_generation_id == final.data_generation_id
            assert held.source_publication_digest == preview.staged_publication_digest
            assert held.live_publication_digest == old.payload_digest()
            raw = connection.execute(
                "SELECT record_json FROM runtime_outbox_deliveries WHERE delivery_id = ?", (legacy.delivery_id,),
            ).fetchone()[0]
            converted = LegacyUnresolvedDelivery.model_validate_json(raw)
            assert converted.original_record_json == legacy.model_dump_json()
            assert converted.status == "needs_reconciliation"
        assert BackupRestoreOperator(operator).activate_older_restore(
            capability=capability, plan=plan, staging_root=staging, preview_digest=preview.digest(),
        ) == intent
        if cut == "none":
            cli = [
                "--installation-root", str(root), "--owner-principal", capability.owner_principal,
                "--capability-file", write_owner_file(tmp_path / "owner.capability", capability.capability_digest), "reconcile-delivery",
            ]
            assert operator_main([*cli, "plan-reject", "--delivery-id", legacy.delivery_id]) == 0
            review = json.loads(capsys.readouterr().out)
            assert review["plan"]["hold_id"] == held.hold_id
            reviewed_plan = tmp_path / "delivery-plan.json"
            reviewed_plan.write_text(json.dumps(review["plan"]), encoding="utf-8")
            reject = [*cli, "reject", "--plan-file", str(reviewed_plan), "--plan-digest"]
            assert operator_main([*reject, "0" * 64]) == 3
            capsys.readouterr()
            assert operator_main([*reject, review["plan_digest"]]) == 0
            rejection = json.loads(capsys.readouterr().out)
            assert rejection["status"] == "rejected"
            assert rejection["evidence_digest"] == review["plan"]["evidence_digest"]
            after_rejection = reopened.acquire_verified_snapshot()
            assert operator_main([*reject, review["plan_digest"]]) == 0
            assert json.loads(capsys.readouterr().out) == rejection
            assert reopened.acquire_verified_snapshot() == after_rejection
        publish_runtime_change(
            reopened, lambda connection, state: state.apply_task(connection, _task("task:new")),
            operation_binding="migrate",
        )
    with StorageAdministrationService(root) as reopened:
        reopened.acquire_verified_snapshot()
        assert RuntimeStateRepository(reopened.partition()).get_task("task:new") is not None


@pytest.mark.parametrize(("prior_format", "selector_drift"), [(4, False), (5, False), (6, False), (6, True)])
def test_owner_upgrades_signed_runtime_without_rewriting_old_batches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    prior_format: int, selector_drift: bool,
) -> None:
    root, archive, staging = tmp_path / "installed", tmp_path / "archive", tmp_path / "stage"
    with StorageAdministrationService(root) as service:
        with monkeypatch.context() as previous:
            previous.setattr("memorii.stores.sqlite.partition.PARTITION_SCHEMA_VERSION", prior_format)
            service.initialize()
        owner = mint_owner_capability(service, "owner:test")
        operator = StorageAdministrationOperator(service)
        operator.change_mode(
            ModeChangeRequest(
                target_mode="read_only", expected_control_revision=operator.status().control_revision,
                reason="upgrade a signed runtime",
            ),
            capability=owner,
        )
        publish_runtime_change(
            service, lambda connection, state: state.apply_task(connection, _task("task:upgrade")),
            operation_binding="migrate",
        )
        service.publish_memory_plane_batch((CanonicalMemoryRecord(
            memory_id="source:upgrade", domain=MemoryDomain.TRANSCRIPT, source_kind="raw",
            text="Retained during migration", status=CommitStatus.COMMITTED,
        ),), operation_binding="migrate")
        partition = service.partition()
        with partition.transaction(write=False) as connection:
            assert partition.read_schema_version(connection) == prior_format
            original = tuple(partition.runtime_event_batch_rows(connection))
        before = service.acquire_verified_snapshot()
        if selector_drift:
            with closing(sqlite3.connect(partition.database_path)) as external:
                external.execute("UPDATE memory_current_records SET source_kind = 'foreign'")
                external.commit()
        backups = BackupRestoreOperator(operator)
        key = b"x" * 32
        backups.create_backup(capability=owner, archive_root=archive, reason="upgrade backup", recovery_key=key)
        plan = backups.plan_restore(capability=owner, archive_root=archive, data_loss_acknowledged=False)
        backups.apply_restore(capability=owner, plan=plan, staging_root=staging, recovery_key=key)
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(plan.model_dump_json(), encoding="utf-8")
        cli = [
            "--installation-root", str(root), "--owner-principal", owner.owner_principal,
            "--capability-file", write_owner_file(tmp_path / "owner.capability", owner.capability_digest), "backup",
        ]
        stage_args = ["--plan-file", str(plan_file), "--staging-root", str(staging)]
        preview = backups.preview_staged_restore(capability=owner, plan=plan, staging_root=staging)
        if selector_drift:
            with pytest.raises(OperatorError, match="candidate could not be prepared") as caught:
                backups.upgrade_current_runtime(
                    capability=owner, plan=plan, staging_root=staging, preview_digest=preview.digest(),
                )
            assert "legacy current selectors differ" in str(caught.value.__cause__)
            assert service.acquire_verified_snapshot() == before
            return
        assert operator_main([*cli, "upgrade-runtime", *stage_args, "--preview-digest", preview.digest()]) == 0
        assert "needs_reconciliation" in capsys.readouterr().out

    with StorageAdministrationService(root) as reopened:
        reopened.acquire_verified_snapshot()
        partition = reopened.partition()
        with partition.transaction(write=False) as connection:
            assert partition.read_schema_version(connection) == 7
            assert partition.supports_runtime_source_release(connection)
            assert partition.supports_runtime_replay_checkpoints(connection)
            assert tuple(partition.runtime_event_batch_rows(connection))[:-1] == original
        assert RuntimeStateRepository(partition).get_task("task:upgrade") is not None
