"""Operator controls: owner capability, modes, status, export."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from memorii.core.persistence.contracts import canonical_json_digest
from memorii.core.persistence.runtime_contracts import TaskRecord
from memorii.core.persistence.runtime_repository import (
    publish_runtime_change,
)
from memorii.core.storage_administration.operator import (
    ModeChangeRequest,
    OperatorError,
    OwnerCapability,
    StorageAdministrationOperator,
)
from memorii.core.storage_administration.service import StorageAdministrationService

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _operator(tmp_path: Path) -> tuple[StorageAdministrationOperator, StorageAdministrationService]:
    service = StorageAdministrationService(tmp_path / "installation")
    service.initialize()
    return StorageAdministrationOperator(service), service


def _capability(service: StorageAdministrationService) -> OwnerCapability:
    return OwnerCapability(
        owner_principal="owner:one",
        capability_digest=canonical_json_digest(
            {
                "installation_id": service._control_state().installation_id,
                "owner_principal": "owner:one",
            }
        ),
    )


def test_status_reports_content_free_state(tmp_path: Path) -> None:
    operator, service = _operator(tmp_path)
    try:
        status = operator.status()
        assert status.mode == "active"
        assert status.quarantined is False
        assert status.runtime_revision == 0
        assert status.memory_write_revision == 0
    finally:
        service.close()


def test_mode_change_fences_and_round_trips(tmp_path: Path) -> None:
    operator, service = _operator(tmp_path)
    try:
        capability = _capability(service)
        paused = operator.change_mode(
            ModeChangeRequest(
                target_mode="read_only",
                expected_control_revision=service._control_state().control_revision,
                reason="maintenance window",
            ),
            capability=capability,
        )
        assert paused.mode == "read_only"
        # Data publication is fenced in read_only.
        from memorii.core.storage_administration.service import (
            InstallationQuarantinedError,
        )

        with pytest.raises(InstallationQuarantinedError, match="read_only"):
            publish_runtime_change(
                service, lambda connection, repository: None
            )
        resumed = operator.change_mode(
            ModeChangeRequest(
                target_mode="active",
                expected_control_revision=service._control_state().control_revision,
                reason="maintenance complete",
            ),
            capability=capability,
        )
        assert resumed.mode == "active"
        revision = publish_runtime_change(
            service, lambda connection, repository: None
        )
        assert revision >= 1
    finally:
        service.close()


def test_stale_control_revision_conflicts(tmp_path: Path) -> None:
    operator, service = _operator(tmp_path)
    try:
        with pytest.raises(OperatorError, match="control revision changed"):
            operator.change_mode(
                ModeChangeRequest(
                    target_mode="read_only",
                    expected_control_revision=99,
                    reason="stale",
                ),
                capability=_capability(service),
            )
    finally:
        service.close()


def test_foreign_capability_denies_before_state_change(tmp_path: Path) -> None:
    operator, service = _operator(tmp_path)
    try:
        forged = OwnerCapability(
            owner_principal="owner:other",
            capability_digest="0" * 64,
        )
        with pytest.raises(OperatorError, match="does not match"):
            operator.change_mode(
                ModeChangeRequest(
                    target_mode="read_only",
                    expected_control_revision=service._control_state().control_revision,
                    reason="forged",
                ),
                capability=forged,
            )
        assert service._control_state().mode == "active"
    finally:
        service.close()


def test_bypass_returns_to_active_only(tmp_path: Path) -> None:
    operator, service = _operator(tmp_path)
    try:
        capability = _capability(service)
        bypassed = operator.change_mode(
            ModeChangeRequest(
                target_mode="bypass",
                expected_control_revision=service._control_state().control_revision,
                reason="host stop calling data paths",
            ),
            capability=capability,
        )
        assert bypassed.mode == "bypass"
        with pytest.raises(OperatorError, match="bypass returns to active only"):
            operator.change_mode(
                ModeChangeRequest(
                    target_mode="read_only",
                    expected_control_revision=service._control_state().control_revision,
                    reason="invalid transition",
                ),
                capability=capability,
            )
        returned = operator.change_mode(
            ModeChangeRequest(
                target_mode="active",
                expected_control_revision=service._control_state().control_revision,
                reason="return to active",
            ),
            capability=capability,
        )
        assert returned.mode == "active"
    finally:
        service.close()


def test_export_is_scoped_deterministic_and_authorized(tmp_path: Path) -> None:
    operator, service = _operator(tmp_path)
    try:
        publish_runtime_change(
            service,
            lambda connection, repository: repository.apply_task(
                connection,
                TaskRecord(
                    task_id="task:export",
                    principal="principal:a",
                    goal="Export journey",
                    created_at=_NOW,
                    root_execution_node_id="exec:root",
                ),
            ),
        )
        export = operator.read_export(capability=_capability(service))
        assert export["tasks"][0]["task_id"] == "task:export"
        assert export["memory_data_revision"] == 0
        forged = OwnerCapability(
            owner_principal="owner:other", capability_digest="1" * 64
        )
        with pytest.raises(OperatorError, match="does not match"):
            operator.read_export(capability=forged)
    finally:
        service.close()


# --- Backup / restore / forget / erasure / retention / doctor ---------------


def _fenced_operator(
    tmp_path: Path,
) -> tuple[StorageAdministrationOperator, StorageAdministrationService, OwnerCapability]:
    from memorii.core.storage_administration.operator import ModeChangeRequest

    operator, service = _operator(tmp_path)
    capability = _capability(service)
    status = operator.status()
    operator.change_mode(
        ModeChangeRequest(
            target_mode="read_only",
            expected_control_revision=status.control_revision,
            reason="backup journey",
        ),
        capability=capability,
    )
    return operator, service, capability


def test_backup_requires_the_exclusive_barrier(tmp_path: Path) -> None:
    from memorii.core.storage_administration.operator_backup import BackupRestoreOperator

    operator, service = _operator(tmp_path)
    try:
        backups = BackupRestoreOperator(operator)
        with pytest.raises(OperatorError, match="exclusive barrier"):
            backups.create_backup(
                capability=_capability(service),
                archive_root=tmp_path / "backup",
                reason="barrier test",
            )
    finally:
        service.close()


def test_backup_create_verify_and_restore_round_trip(tmp_path: Path) -> None:
    from memorii.core.storage_administration.operator_backup import (
        BackupRestoreOperator,
    )

    operator, service, capability = _fenced_operator(tmp_path)
    try:
        backups = BackupRestoreOperator(operator)
        manifest = backups.create_backup(
            capability=capability,
            archive_root=tmp_path / "backup",
            reason="round trip",
        )
        assert {p.participant_id for p in manifest.participants} == {
            "control",
            "partition",
        }
        verified = backups.verify_backup(archive_root=tmp_path / "backup")
        assert verified.manifest_digest == manifest.manifest_digest

        # Tamper with one participant snapshot: verify refuses.
        (tmp_path / "backup" / "partition.sqlite3").write_bytes(b"tampered")
        with pytest.raises(OperatorError, match="size mismatch|digest mismatch"):
            backups.verify_backup(archive_root=tmp_path / "backup")

        # Recreate a clean backup; restore to staging.
        manifest = backups.create_backup(
            capability=capability,
            archive_root=tmp_path / "backup2",
            reason="second",
        )
        del manifest
        plan = backups.plan_restore(
            capability=capability,
            archive_root=tmp_path / "backup2",
            data_loss_acknowledged=False,
        )
        assert plan.participant_count == 2
        staging = backups.apply_restore(
            capability=capability, plan=plan, staging_root=tmp_path / "staged"
        )
        assert (staging / "control.sqlite3").is_file()
        assert (staging / "partition.sqlite3").is_file()
    finally:
        service.close()


def test_backup_foreign_installation_and_missing_marker_refuse(tmp_path: Path) -> None:
    from memorii.core.storage_administration.operator_backup import (
        BackupRestoreOperator,
    )

    operator, service, capability = _fenced_operator(tmp_path)
    try:
        backups = BackupRestoreOperator(operator)
        with pytest.raises(OperatorError, match="no complete marker"):
            backups.verify_backup(archive_root=tmp_path / "empty")
        backups.create_backup(
            capability=capability,
            archive_root=tmp_path / "backup",
            reason="marker",
        )
        (tmp_path / "backup" / "backup-complete.json").unlink()
        with pytest.raises(OperatorError, match="no complete marker"):
            backups.verify_backup(archive_root=tmp_path / "backup")
    finally:
        service.close()


def test_forget_plan_apply_and_retention_cycle(tmp_path: Path) -> None:
    from memorii.core.storage_administration.operator import ModeChangeRequest
    from memorii.core.storage_administration.operator_governance import (
        GovernanceOperator,
    )

    operator, service = _operator(tmp_path)
    capability = _capability(service)
    try:
        governance = GovernanceOperator(operator)
        with pytest.raises(OperatorError, match="matched no records"):
            governance.plan_forget(capability=capability, scope_note="empty")

        from memorii.core.persistence.runtime_contracts import TaskRecord
        from memorii.core.persistence.runtime_repository import publish_runtime_change

        def seed(connection, repo) -> None:
            repo.apply_task(
                connection,
                TaskRecord(
                    task_id="task:forget",
                    principal="principal:a",
                    goal="Forget journey",
                    created_at=_NOW,
                    root_execution_node_id="exec:root",
                ),
            )

        publish_runtime_change(service, seed, operation_binding="forget_seed")
        plan = governance.plan_forget(capability=capability, scope_note="scope")
        assert plan.matched_record_ids == ("task:forget",)
        assert plan.retention_disclosed is True
        receipt = governance.apply_forget(capability=capability, plan=plan)
        assert receipt.suppressed_count == 1
        assert receipt.historical_bytes_retained is True

        # Retention sees the fresh journal as ineligible; nothing prunes.
        retention = governance.plan_retention(
            capability=capability, older_than_days=30
        )
        assert retention.eligible_suppression_journals == ()
        assert (
            governance.apply_retention(capability=capability, plan=retention) == 0
        )

        operator.change_mode(
            ModeChangeRequest(
                target_mode="read_only",
                expected_control_revision=operator.status().control_revision,
                reason="doctor read",
            ),
            capability=capability,
        )
    finally:
        service.close()


def test_erasure_requires_acknowledgement_and_reports_incomplete(tmp_path: Path) -> None:
    from memorii.core.storage_administration.operator_governance import (
        GovernanceOperator,
    )

    operator, service = _operator(tmp_path)
    capability = _capability(service)
    try:
        governance = GovernanceOperator(operator)
        plan = governance.plan_erasure(capability=capability)
        assert plan.installation_id == service._control_state().installation_id
        with pytest.raises(OperatorError, match="acknowledged plan"):
            governance.apply_erasure(capability=capability, plan=plan)
        dry = governance.apply_erasure(
            capability=capability,
            plan=plan.model_copy(update={"acknowledged": True}),
        )
        assert dry.incomplete is True  # offline copies unaccounted
        receipts = list(
            (service.installation_root / "control" / "erasure-receipts").glob(
                "erasure-*.json"
            )
        )
        assert receipts, "content-free erasure receipt recorded"
    finally:
        service.close()


def test_doctor_reports_and_never_repairs(tmp_path: Path) -> None:
    from memorii.core.storage_administration.operator_governance import (
        GovernanceOperator,
    )

    operator, service = _operator(tmp_path)
    try:
        governance = GovernanceOperator(operator)
        findings = governance.doctor()
        checks = {finding.check: finding.status for finding in findings}
        assert checks["control_state"] == "ok"
        assert checks["partition_verification"] == "ok"
        # Doctor ran read-only: the partition and control files remain.
        assert service.control_path().exists()
        assert service.partition_path().exists()
    finally:
        service.close()
