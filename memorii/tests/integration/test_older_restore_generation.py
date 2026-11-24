"""Owner cutover and interruption recovery from an older authenticated backup."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
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
from memorii.core.storage_administration.service import StorageAdministrationError, StorageAdministrationService
from memorii.tools.runtime_operator import main as operator_main


def _task(task_id: str) -> TaskRecord:
    return TaskRecord(
        task_id=task_id, principal="owner:test", goal="Verify selected generation",
        created_at=datetime(2026, 1, 1, tzinfo=UTC), root_execution_node_id=f"exec:{task_id}",
    )


@pytest.mark.parametrize("cut", ["none", "before_selector", "after_selector", "invalid_selector"])
def test_older_restore_recovers_exact_bytes_and_keeps_delivery_held(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cut: str,
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
                if cut == "after_selector":
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
        publish_runtime_change(
            reopened, lambda connection, state: state.apply_task(connection, _task("task:new")),
            operation_binding="migrate",
        )
    with StorageAdministrationService(root) as reopened:
        reopened.acquire_verified_snapshot()
        assert RuntimeStateRepository(reopened.partition()).get_task("task:new") is not None


def test_owner_upgrades_signed_v4_runtime_without_rewriting_old_batches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    root, archive, staging = tmp_path / "installed", tmp_path / "archive", tmp_path / "stage"
    with StorageAdministrationService(root) as service:
        with monkeypatch.context() as previous:
            previous.setattr("memorii.stores.sqlite.partition.PARTITION_SCHEMA_VERSION", 4)
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
        partition = service.partition()
        with partition.transaction(write=False) as connection:
            assert partition.read_schema_version(connection) == 4
            original = tuple(partition.runtime_event_batch_rows(connection))
        backups = BackupRestoreOperator(operator)
        key = b"x" * 32
        backups.create_backup(capability=owner, archive_root=archive, reason="upgrade backup", recovery_key=key)
        plan = backups.plan_restore(capability=owner, archive_root=archive, data_loss_acknowledged=False)
        backups.apply_restore(capability=owner, plan=plan, staging_root=staging, recovery_key=key)
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(plan.model_dump_json(), encoding="utf-8")
        cli = [
            "--installation-root", str(root), "--owner-principal", owner.owner_principal,
            "--capability-digest", owner.capability_digest, "backup",
        ]
        stage_args = ["--plan-file", str(plan_file), "--staging-root", str(staging)]
        preview = backups.preview_staged_restore(capability=owner, plan=plan, staging_root=staging)
        assert operator_main([*cli, "upgrade-runtime", *stage_args, "--preview-digest", preview.digest()]) == 0
        assert "needs_reconciliation" in capsys.readouterr().out

    with StorageAdministrationService(root) as reopened:
        reopened.acquire_verified_snapshot()
        partition = reopened.partition()
        with partition.transaction(write=False) as connection:
            assert partition.supports_runtime_source_release(connection)
            assert partition.supports_runtime_replay_checkpoints(connection)
            assert tuple(partition.runtime_event_batch_rows(connection))[:-1] == original
        assert RuntimeStateRepository(partition).get_task("task:upgrade") is not None
