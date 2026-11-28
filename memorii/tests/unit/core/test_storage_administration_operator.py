"""Operator controls: owner capability, modes, status, export."""

from __future__ import annotations

import json
import os
import sqlite3
import stat
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
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
from memorii.core.storage_administration.service import StorageAdministrationError, StorageAdministrationService
from tests.support.operator_files import write_owner_file

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _operator(tmp_path: Path) -> tuple[StorageAdministrationOperator, StorageAdministrationService]:
    service = StorageAdministrationService(tmp_path / "installation")
    service.initialize()
    return StorageAdministrationOperator(service), service


def _capability(service: StorageAdministrationService) -> OwnerCapability:
    from memorii.core.storage_administration.operator import mint_owner_capability

    return mint_owner_capability(service, "owner:one")


def test_cli_stages_a_reviewed_restore_with_an_owner_only_key(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    from memorii.core.harness_state.grant_registry import GrantEpochRegistry
    from memorii.core.harness_state.service import RuntimeReadGrant
    from memorii.core.harness_state.sidecar import RuntimeSidecar
    from memorii.core.persistence.runtime_repository import RuntimeStateRepository
    from memorii.core.storage_administration import operator_backup
    from memorii.core.storage_administration.generation_selection import PARTITION_GENERATION_SELECTOR
    from memorii.core.storage_administration.operator_backup import BackupRestoreOperator
    from memorii.tools.runtime_operator import main

    operator, service, capability = _fenced_operator(tmp_path)
    try:
        publish_runtime_change(
            service,
            lambda connection, repository: repository.apply_task(connection, TaskRecord(
                task_id="task:restore", principal="owner:one", goal="Verify a restored read",
                created_at=_NOW, root_execution_node_id="exec:restore",
            )),
            operation_binding="migrate",
        )
        read_grant = RuntimeReadGrant(
            grant_id="read:restore", principal="owner:one", allowed_task_ids=("task:restore",),
            epoch=1, expires_at=datetime(2099, 1, 1, tzinfo=UTC),
        )
        def read_status(reader: RuntimeSidecar) -> int:
            return reader.handle_state_request(
                bearer_token="reader", origin=None, body=b'{"task_id":"task:restore"}',
            )[0]

        sidecar = RuntimeSidecar(
            RuntimeStateRepository(service.partition()), credentials={"reader": "owner:one"},
            grant_factory=lambda _: read_grant,
        )
        assert read_status(sidecar) == 200
        backups = BackupRestoreOperator(operator)
        archive = tmp_path / "archive"
        recovery_key = b"k" * 32
        backups.create_backup(
            capability=capability, archive_root=archive, reason="verify installed restore", recovery_key=recovery_key,
        )
        cli = [
            "--installation-root", str(service.installation_root),
            "--owner-principal", capability.owner_principal, "--capability-file", write_owner_file(tmp_path / "owner.capability", capability.capability_digest),
            "backup",
        ]
        assert main([*cli, "restore-plan", "--archive-root", str(archive)]) == 0
        plan = tmp_path / "plan.json"
        plan.write_text(capsys.readouterr().out, encoding="utf-8")
        key = tmp_path / "recovery.key"
        key.write_bytes(recovery_key)
        key.chmod(0o644)
        staging = tmp_path / "stage"
        stage = [
            *cli, "restore-stage", "--plan-file", str(plan), "--staging-root", str(staging),
            "--recovery-key-file", str(key),
        ]
        assert main(stage) == 3
        assert "owner-only" in caplog.text
        assert not staging.exists()
        key.chmod(0o600)
        before = service.acquire_verified_snapshot()
        assert main(stage) == 0
        assert json.loads(capsys.readouterr().out) == {"status": "staged", "path": str(staging)}
        assert (staging / "partition.sqlite3").is_file()
        assert main([*cli, "restore-verify-stage", "--plan-file", str(plan), "--staging-root", str(staging)]) == 0
        attestation = json.loads(capsys.readouterr().out)
        assert attestation["plan_digest"] == json.loads(plan.read_bytes())["plan_digest"]
        preview_cli = [*cli, "restore-preview-stage", "--plan-file", str(plan), "--staging-root", str(staging)]
        assert main(preview_cli) == 0
        preview = json.loads(capsys.readouterr().out)
        assert preview["live_publication_digest"] == preview["staged_publication_digest"]
        assert preview["plan_digest"] == attestation["plan_digest"]
        assert preview["target_receipts"] == {"identical": 0, "live_only": 0, "staged_only": 0, "changed": 0}
        denied = [*preview_cli]
        denied[denied.index("--capability-file") + 1] = write_owner_file(tmp_path / "invalid.capability", "0" * 64)
        assert main(denied) == 3
        assert "denied" in caplog.text
        assert service.acquire_verified_snapshot() == before
        retained = service.partition()
        activate = [*cli, "restore-activate-current", "--plan-file", str(plan), "--staging-root", str(staging)]
        original_write = operator_backup._atomic_write

        def fail_before_selector(path: Path, contents: bytes) -> None:
            if path.name == PARTITION_GENERATION_SELECTOR:
                raise OSError("selector publication interrupted")
            original_write(path, contents)

        with monkeypatch.context() as cut:
            cut.setattr(operator_backup, "_atomic_write", fail_before_selector)
            assert main(activate) == 3
        assert "selection could not be published" in caplog.text
        assert service.acquire_verified_snapshot() == before
        assert main(activate) == 0
        activation = json.loads(capsys.readouterr().out)
        assert activation == {
            "status": "selected",
            "generation_id": attestation["source_publication"]["data_generation_id"],
            "reopen_required": True,
        }
        with pytest.raises(StorageAdministrationError, match="partition selection changed"), retained.transaction(
            write=False,
        ):
            pytest.fail("retained physical handles must be fenced after selection")
        assert read_status(sidecar) == 503
        with StorageAdministrationService(service.installation_root) as reopened:
            assert reopened.acquire_verified_snapshot() == before
            assert reopened.partition_path().parent.name == activation["generation_id"]
            reader = RuntimeSidecar(
                RuntimeStateRepository(reopened.partition()), credentials={"reader": "owner:one"},
                grant_factory=lambda _: read_grant,
            )
            assert read_status(reader) == 200
            GrantEpochRegistry(reopened.installation_root / "control" / "grants").revoke(
                read_grant.grant_id, reason="verify stable grant root",
            )
            assert read_status(reader) == 403
    finally:
        service.close()


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

        def write_task(connection, repository) -> None:
            repository.apply_task(connection, TaskRecord(
                task_id="task:maintenance", principal="owner:one", goal="Resume writes",
                created_at=_NOW, root_execution_node_id="exec:maintenance",
            ))

        with pytest.raises(InstallationQuarantinedError, match="read_only"):
            publish_runtime_change(service, write_task)
        resumed = operator.change_mode(
            ModeChangeRequest(
                target_mode="active",
                expected_control_revision=service._control_state().control_revision,
                reason="maintenance complete",
            ),
            capability=capability,
        )
        assert resumed.mode == "active"
        assert publish_runtime_change(service, write_task) == 1
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
                recovery_key=b"k" * 32,
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
        recovery_key = b"journey-recovery-key-32-bytes-xxxxx"[:32]
        manifest = backups.create_backup(
            capability=capability,
            archive_root=tmp_path / "backup",
            reason="round trip",
            recovery_key=recovery_key,
        )
        assert {p.participant_id for p in manifest.participants} == {
            "control",
            "partition",
        }
        assert (tmp_path / "backup" / "control-recovery-bundle.json").is_file()
        assert (tmp_path / "backup" / "recovery-anchor.json").is_file()
        verified = backups.verify_backup(archive_root=tmp_path / "backup")
        assert verified.manifest_digest == manifest.manifest_digest

        # Tamper with one participant snapshot: verify refuses.
        (tmp_path / "backup" / "partition.sqlite3.enc").write_bytes(b"tampered")
        with pytest.raises(OperatorError, match="size mismatch|digest mismatch"):
            backups.verify_backup(archive_root=tmp_path / "backup")

        # A tampered manifest with a recomputed digest still fails: the
        # signature is verified against the installation signing key.
        import json as _json

        marker = tmp_path / "backup" / "backup-complete.json"
        body = _json.loads(marker.read_text())
        body["participants"] = [
            p for p in body["participants"] if p["participant_id"] == "control"
        ]
        import hashlib as _hashlib

        stripped = {k: v for k, v in body.items() if k not in ("manifest_digest", "manifest_signature")}
        body["manifest_digest"] = _hashlib.sha256(
            _json.dumps(stripped, sort_keys=True).encode()
        ).hexdigest()
        marker.write_text(_json.dumps(body))
        with pytest.raises(OperatorError, match="signature"):
            backups.verify_backup(archive_root=tmp_path / "backup")

        # Path traversal / duplicate ids / unknown participants are refused
        # outright by the validator (defense-in-depth beneath the signature,
        # which already catches any manifest tampering as proven above).
        from memorii.core.storage_administration.operator_backup import (
            BackupParticipant as _Participant,
        )
        from memorii.core.storage_administration.operator_backup import (
            validate_backup_participant as _validate,
        )

        hostile = _Participant(
            participant_id="control",
            filename="../../control/control.sqlite3",
            sha256="0" * 64,
            size_bytes=1,
            nonce="AAAAAAAAAAAAAAAA",
        )
        with pytest.raises(OperatorError, match="plain basename"):
            _validate(hostile)
        absolute = hostile.model_copy(update={"filename": "/etc/passwd"})
        with pytest.raises(OperatorError, match="plain basename"):
            _validate(absolute)

        # Clean backup; restore to staging with the recovery key.
        backups.create_backup(
            capability=capability,
            archive_root=tmp_path / "backup2",
            reason="second",
            recovery_key=recovery_key,
        )
        plan = backups.plan_restore(
            capability=capability,
            archive_root=tmp_path / "backup2",
            data_loss_acknowledged=False,
        )
        assert plan.participant_count == 2
        staging = backups.apply_restore(
            capability=capability,
            plan=plan,
            staging_root=tmp_path / "staged",
            recovery_key=recovery_key,
        )
        assert (staging / "control.sqlite3").is_file()
        assert (staging / "partition.sqlite3").is_file()
        # A wrong recovery key cannot decrypt: restore refuses fail-closed.
        from cryptography.exceptions import InvalidTag

        with pytest.raises(InvalidTag):
            backups.apply_restore(
                capability=capability,
                plan=plan,
                staging_root=tmp_path / "staged2",
                recovery_key=b"wrong-recovery-key-32-bytes-xxxxxx"[:32],
            )
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
            recovery_key=b"k" * 32,
        )
        (tmp_path / "backup" / "backup-complete.json").unlink()
        with pytest.raises(OperatorError, match="no complete marker"):
            backups.verify_backup(archive_root=tmp_path / "backup")
    finally:
        service.close()


def test_restore_planning_detects_data_only_watermark_change(tmp_path: Path) -> None:
    from memorii.core.storage_administration.operator_backup import BackupRestoreOperator

    operator, service, capability = _fenced_operator(tmp_path)
    try:
        backups = BackupRestoreOperator(operator)
        archive = tmp_path / "archive"
        recovery_key = b"k" * 32
        manifest = backups.create_backup(
            capability=capability, archive_root=archive, reason="data watermark", recovery_key=recovery_key,
        )
        plan = backups.plan_restore(capability=capability, archive_root=archive, data_loss_acknowledged=True)
        assert manifest.publication_digest == plan.expected_publication_digest
        assert manifest.control_tip_digest == plan.expected_control_tip_digest
        # Maintenance publication can move data under read_only without a mode or control revision change.
        publish_runtime_change(
            service,
            lambda connection, repository: repository.apply_task(connection, TaskRecord(
                task_id="task:new", root_execution_node_id="exec:new", goal="newer graph",
                principal="principal:one", created_at=_NOW,
            )),
            operation_binding="migrate",
        )
        assert operator.status().control_revision == manifest.control_revision
        with pytest.raises(OperatorError, match="data-loss acknowledgement"):
            backups.plan_restore(capability=capability, archive_root=archive, data_loss_acknowledged=False)
        staging = tmp_path / "staged"
        with pytest.raises(OperatorError, match="live restore watermark changed"):
            backups.apply_restore(capability=capability, plan=plan, staging_root=staging, recovery_key=recovery_key)
        assert not staging.exists()
        renewed = backups.plan_restore(capability=capability, archive_root=archive, data_loss_acknowledged=True)
        live = service.acquire_verified_snapshot()
        assert backups.apply_restore(
            capability=capability, plan=renewed, staging_root=staging, recovery_key=recovery_key,
        ) == staging
        with pytest.raises(OperatorError, match="older restore requires a new generation"):
            backups.activate_exact_current_restore(
                capability=capability, plan=renewed, staging_root=staging,
            )
        assert service.acquire_verified_snapshot() == live
    finally:
        service.close()


def test_older_restore_preview_compares_exact_signed_receipt_and_outbox_rows(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture,
) -> None:
    from memorii.core.persistence.runtime_api import RuntimeOutboxDelivery
    from memorii.core.persistence.runtime_contracts import RuntimeCommandReceipt
    from memorii.core.persistence.runtime_repository import RuntimeStateRepository
    from memorii.core.storage_administration.operator_backup import BackupRestoreOperator, RestoreInventoryDelta
    from memorii.tools.runtime_operator import main

    operator, service, capability = _fenced_operator(tmp_path)
    try:
        backups = BackupRestoreOperator(operator)
        initial = RuntimeCommandReceipt(
            operation_id="old-operation", client_namespace="harness", request_digest="a" * 64,
            base_revision=0, current_revision=1, status="committed", result_digest="a" * 64,
        )
        accepted = RuntimeCommandReceipt(
            operation_id="new-operation", client_namespace="harness", request_digest="b" * 64,
            base_revision=1, current_revision=2, status="committed", result_digest="c" * 64,
        )
        delivery = RuntimeOutboxDelivery(
            delivery_id="old-delivery", origin_operation_id=initial.operation_id, kind="work_projection",
            target_protocol="local", payload_digest="d" * 64, fence_token=1,
        )

        def publish(rows: tuple[RuntimeCommandReceipt, ...], queued: RuntimeOutboxDelivery) -> None:
            def apply(connection: sqlite3.Connection, repository: RuntimeStateRepository) -> None:
                for receipt in rows:
                    repository.apply_command_receipt(connection, receipt)
                repository.apply_outbox_row(connection, queued)

            publish_runtime_change(service, apply, operation_binding="migrate")

        publish((initial,), delivery)
        archive, stage = tmp_path / "archive", tmp_path / "stage"
        key = b"k" * 32
        manifest = backups.create_backup(
            capability=capability, archive_root=archive, reason="compare signed receipts", recovery_key=key,
        )
        publish((accepted,), delivery.model_copy(update={"fence_token": 2}))
        plan = backups.plan_restore(capability=capability, archive_root=archive, data_loss_acknowledged=True)
        backups.apply_restore(capability=capability, plan=plan, staging_root=stage, recovery_key=key)
        before = service.acquire_verified_snapshot()
        before_stage = {entry.name: entry.read_bytes() for entry in stage.iterdir() if entry.is_file()}
        preview = backups.preview_staged_restore(capability=capability, plan=plan, staging_root=stage)
        assert preview.plan_digest == plan.plan_digest
        assert preview.live_publication_digest == before.tuple_digest
        assert preview.staged_publication_digest == manifest.publication_digest
        assert preview.command_receipts == RestoreInventoryDelta(identical=1, live_only=1, staged_only=0, changed=0)
        assert preview.outbox_deliveries == RestoreInventoryDelta(identical=0, live_only=0, staged_only=0, changed=1)
        assert service.acquire_verified_snapshot() == before
        assert {entry.name: entry.read_bytes() for entry in stage.iterdir() if entry.is_file()} == before_stage
        publish((), delivery.model_copy(update={"fence_token": 3}))
        with pytest.raises(OperatorError, match="live restore watermark changed"):
            backups.preview_staged_restore(capability=capability, plan=plan, staging_root=stage)
        service._quarantine_state("partition rows do not match the signed materialization manifest")
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(plan.model_dump_json())
        assert main([
            "--installation-root", str(service.installation_root),
            "--owner-principal", capability.owner_principal, "--capability-file", write_owner_file(tmp_path / "owner.capability", capability.capability_digest),
            "backup", "restore-preview-stage", "--plan-file", str(plan_file), "--staging-root", str(stage),
        ]) == 3
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "unavailable: operator request failed" in caplog.text
    finally:
        service.close()


def test_restore_plan_rejects_archive_substitution(tmp_path: Path) -> None:
    from memorii.core.storage_administration.operator_backup import BackupRestoreOperator

    operator, service, capability = _fenced_operator(tmp_path)
    try:
        backups = BackupRestoreOperator(operator)
        archive = tmp_path / "archive"
        recovery_key = b"k" * 32
        backups.create_backup(
            capability=capability, archive_root=archive, reason="reviewed", recovery_key=recovery_key,
        )
        plan = backups.plan_restore(capability=capability, archive_root=archive, data_loss_acknowledged=False)
        archive.rename(tmp_path / "reviewed-archive")
        backups.create_backup(
            capability=capability, archive_root=archive, reason="replacement", recovery_key=recovery_key,
        )
        staging = tmp_path / "staged"
        with pytest.raises(OperatorError, match="plan and archive disagree"):
            backups.apply_restore(capability=capability, plan=plan, staging_root=staging, recovery_key=recovery_key)
        assert not staging.exists()
    finally:
        service.close()


@pytest.mark.parametrize(
    ("change", "refusal"),
    [
        ("owner", "owner capability"),
        ("plan", "reviewed restore plan"),
        ("attestation", "attestation signature is invalid"),
        ("database", "bytes differ from the attestation"),
        ("sidecar", "contains a live sidecar"),
        ("staged_suppression", "bytes differ from the attestation"),
        ("live_suppression", "suppression watermark changed"),
        ("control", "live restore watermark changed"),
    ],
)
def test_staged_restore_revalidation_after_reopen(
    tmp_path: Path, change: str, refusal: str,
) -> None:
    from memorii.core.storage_administration.operator_backup import BackupRestoreOperator
    from memorii.core.storage_administration.suppression_journal import (
        SuppressionCoordinate,
        SuppressionRecord,
        write_suppression_record,
    )

    def record_suppression(control_root: Path, identifier: str) -> None:
        write_suppression_record(
            control_root,
            SuppressionRecord(
                suppression_id=identifier * 64,
                plan_digest="a" * 64,
                closure_digest="b" * 64,
                scope_note="restore staging test",
                suppressed=(SuppressionCoordinate(coordinate_kind="task", coordinate_id=f"task:{identifier}"),),
                applied_at_unix=1,
            ),
        )

    operator, service, capability = _fenced_operator(tmp_path)
    root = service.installation_root
    archive = tmp_path / "archive"
    staging = tmp_path / "staged"
    recovery_key = b"k" * 32
    with service:
        record_suppression(root / "control", "c")
        backups = BackupRestoreOperator(operator)
        manifest = backups.create_backup(
            capability=capability, archive_root=archive, reason="restore staging", recovery_key=recovery_key,
        )
        plan = backups.plan_restore(capability=capability, archive_root=archive, data_loss_acknowledged=False)
        before = service.acquire_verified_snapshot()
        backups.apply_restore(capability=capability, plan=plan, staging_root=staging, recovery_key=recovery_key)

    with StorageAdministrationService(root) as reopened:
        backups = BackupRestoreOperator(StorageAdministrationOperator(reopened))
        attestation = backups.verify_staged_restore(capability=capability, plan=plan, staging_root=staging)
        assert attestation.source_publication.payload_digest() == manifest.publication_digest
        assert attestation.source_control_tip_digest == manifest.control_tip_digest
        assert attestation.archive_manifest_digest == manifest.manifest_digest
        assert reopened.acquire_verified_snapshot() == before

        if change == "owner":
            capability = capability.model_copy(update={"capability_digest": "0" * 64})
        elif change == "plan":
            plan = plan.model_copy(update={"data_loss_acknowledged": True})
            plan = plan.model_copy(update={"plan_digest": plan.unsigned_digest()})
        elif change == "attestation":
            altered = attestation.model_copy(update={"data_loss_acknowledged": True})
            (staging / "restore-staging-attestation.json").write_text(altered.model_dump_json())
        elif change == "database":
            with (staging / "partition.sqlite3").open("ab") as handle:
                handle.write(b"changed")
        elif change == "sidecar":
            (staging / "partition.sqlite3-wal").write_bytes(b"changed")
        elif change == "staged_suppression":
            record_suppression(staging, "d")
        elif change == "live_suppression":
            record_suppression(root / "control", "d")
        elif change == "control":
            StorageAdministrationOperator(reopened).change_mode(
                ModeChangeRequest(
                    target_mode="active", expected_control_revision=plan.expected_control_revision,
                    reason="changed after staging",
                ),
                capability=capability,
            )
        with pytest.raises(OperatorError, match=refusal):
            backups.verify_staged_restore(capability=capability, plan=plan, staging_root=staging)


def test_restore_staging_refuses_decrypted_history_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sqlite3
    from contextlib import closing

    from memorii.core.storage_administration import operator_backup

    operator, service = _operator(tmp_path)
    try:
        publish_runtime_change(
            service,
            lambda connection, repository: repository.apply_task(connection, TaskRecord(
                task_id="task:source", root_execution_node_id="exec:source", goal="verified graph",
                principal="principal:one", created_at=_NOW,
            )),
        )
        capability = _capability(service)
        operator.change_mode(
            ModeChangeRequest(
                target_mode="read_only", expected_control_revision=operator.status().control_revision,
                reason="prepare backup verification",
            ),
            capability=capability,
        )
        backups = operator_backup.BackupRestoreOperator(operator)
        archive = tmp_path / "archive"
        recovery_key = b"k" * 32
        backups.create_backup(capability=capability, archive_root=archive, reason="valid", recovery_key=recovery_key)
        plan = backups.plan_restore(capability=capability, archive_root=archive, data_loss_acknowledged=False)
        original = operator_backup.decrypt_backup_participant

        def remove_history(
            source: Path, path: Path, *, key: bytes, nonce: bytes, expected_digest: str, expected_size: int,
        ) -> None:
            original(source, path, key=key, nonce=nonce, expected_digest=expected_digest, expected_size=expected_size)
            if path.name == "partition.sqlite3":
                with closing(sqlite3.connect(path)) as connection:
                    connection.execute("DELETE FROM runtime_event_batches")
                    connection.commit()

        monkeypatch.setattr(operator_backup, "decrypt_backup_participant", remove_history)
        staging = tmp_path / "staged"
        with pytest.raises(OperatorError, match="staged backup verification failed"):
            backups.apply_restore(capability=capability, plan=plan, staging_root=staging, recovery_key=recovery_key)
        assert not staging.exists()
        assert service.acquire_verified_snapshot().tuple_digest == plan.expected_publication_digest
    finally:
        service.close()


def test_backup_refuses_a_captured_partition_outside_the_fenced_tuple(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sqlite3
    from contextlib import closing

    from memorii.core.storage_administration import operator_backup

    operator, service, capability = _fenced_operator(tmp_path)
    try:
        original = operator_backup.copy_sqlite_backup

        def corrupt_copy(source: Path, destination: Path) -> None:
            original(source, destination)
            if destination.name == "partition.sqlite3":
                with closing(sqlite3.connect(destination)) as connection:
                    connection.execute("UPDATE runtime_revision_state SET runtime_revision = 7")
                    connection.commit()

        monkeypatch.setattr(operator_backup, "copy_sqlite_backup", corrupt_copy)
        backups = operator_backup.BackupRestoreOperator(operator)
        archive = tmp_path / "archive"
        live = service.acquire_verified_snapshot()
        with pytest.raises(OperatorError, match="staged partition does not match the backup watermark"):
            backups.create_backup(capability=capability, archive_root=archive, reason="broken copy", recovery_key=b"k" * 32)
        assert not archive.exists()
        assert service.acquire_verified_snapshot() == live
    finally:
        service.close()


def test_forget_plan_apply_and_retention_cycle(tmp_path: Path) -> None:
    from memorii.core.storage_administration.operator import ModeChangeRequest
    from memorii.core.storage_administration.operator_governance import (
        ForgetTargetSelector,
        GovernanceOperator,
    )

    operator, service = _operator(tmp_path)
    capability = _capability(service)
    try:
        governance = GovernanceOperator(operator)
        empty_selector = (ForgetTargetSelector(selector_kind="entity", selector_id="entity:nobody"),)
        with pytest.raises(OperatorError, match="matched no records"):
            governance.plan_forget(
                capability=capability, selectors=empty_selector, scope_note="empty"
            )

        from memorii.core.memory_plane.models import CanonicalMemoryRecord
        from memorii.core.persistence.runtime_contracts import (
            NodeEvidenceReference,
            SolverJustificationRecord,
            SolverRunRecord,
            TaskRecord,
        )
        from memorii.core.persistence.runtime_repository import publish_runtime_change
        from memorii.domain.enums import CommitStatus, MemoryDomain

        claim_payload = {
            "claim_id": "claim:ada-owns",
            "claim_key": {
                "subject_entity_id": "entity:ada",
                "predicate_id": "owns",
                "scope": {},
                "qualifier_key": "default",
                "assertion_mode": "world_assertion",
                "epistemic_status": "asserted",
                "polarity": "positive",
                "modality": "assertion",
                "belief_holder_entity_id": None,
            },
            "object_value": "revocation fixture",
            "lifecycle_state": "active",
            "source_claim_id": "source:ada",
            "confidence": {
                "extraction": 0.9, "evidence": 0.8, "source_trust": 0.7,
                "agreement": 0.0, "contradiction": 0.0, "calibrated": 0.9,
            },
            "semantic_context": {
                "assertion_mode": "world_assertion",
                "epistemic_status": "asserted",
                "polarity": "positive",
                "modality": "assertion",
                "attribution_source_id": "source:ada",
            },
            "validation_results": [],
            "evidence_spans": [
                {"source_id": "source:ada", "start": 0, "end": 8,
                 "evidence_digest": "1" * 64}
            ],
            "subject_link_id": "link:ada",
            "object_link_id": None,
        }
        link_payload = {
            "link_id": "link:ada",
            "mention_text": "fixture entity",
            "canonical_entity_id": "entity:ada",
            "normalized_name": "fixture entity",
            "entity_type": "unknown",
            "aliases": [],
            "observed_names": [],
            "evidence_spans": [],
            "confidence": 0.9,
            "scope": {},
            "lifecycle_state": "active",
        }
        semantic_records = (
            CanonicalMemoryRecord(
                memory_id="mem:evolution:claim:claim:ada-owns",
                domain=MemoryDomain.SEMANTIC,
                text="revocation fixture",
                content={"memory_evolution_kind": "claim_state", "claim_state": claim_payload},
                status=CommitStatus.COMMITTED,
                source_kind="memory_evolution",
            ),
            CanonicalMemoryRecord(
                memory_id="mem:evolution:link:link:ada",
                domain=MemoryDomain.SEMANTIC,
                text="fixture entity",
                content={"memory_evolution_kind": "entity_link", "entity_link": link_payload},
                status=CommitStatus.COMMITTED,
                source_kind="memory_evolution",
            ),
        )

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
            repo.apply_solver_run(
                connection,
                SolverRunRecord(
                    solver_id="solver:forget",
                    task_id="task:forget",
                    parent_execution_node_id="exec:root",
                    category="reasoning",
                    created_by="principal:a",
                ),
            )
            repo.apply_justification(
                connection,
                SolverJustificationRecord(
                    justification_id="justification:forget",
                    solver_id="solver:forget",
                    conclusion="fixture conclusion",
                    supporting_ids=(),
                    contradicting_ids=(),
                    assumption_ids=(),
                    strength=0.9,
                    active=True,
                    source_refs=(NodeEvidenceReference(source_id="source:ada"),),
                ),
            )

        service.publish_memory_plane_batch(
            semantic_records, operation_binding="forget_seed"
        )
        publish_runtime_change(service, seed, operation_binding="forget_seed")

        selectors = (ForgetTargetSelector(selector_kind="entity", selector_id="entity:ada"),)
        plan = governance.plan_forget(
            capability=capability, selectors=selectors, scope_note="scope"
        )
        assert "entity|entity:ada" in plan.closure
        assert "claim|claim:ada-owns" in plan.closure
        assert "source|source:ada" in plan.closure
        assert "record|mem:evolution:claim:claim:ada-owns|claim_state" in plan.closure
        assert "record|mem:evolution:link:link:ada|entity_link" in plan.closure
        assert "justification|justification:forget" in plan.closure
        assert "task|task:forget" in plan.closure
        assert plan.retention_disclosed is True
        assert len(plan.plan_digest) == 64 and len(plan.closure_digest) == 64

        # Forget apply requires the barrier and is refused without it.
        with pytest.raises(OperatorError, match="exclusive"):
            governance.apply_forget(capability=capability, plan=plan)
        operator.change_mode(
            ModeChangeRequest(
                target_mode="read_only",
                expected_control_revision=operator.status().control_revision,
                reason="forget barrier",
            ),
            capability=capability,
        )
        before = operator.status()
        receipt = governance.apply_forget(capability=capability, plan=plan)
        assert receipt.newly_revoked_count == len(plan.closure)
        assert receipt.historical_bytes_retained is True
        assert receipt.enforcement_publication_pending is True
        after = operator.status()
        # The control revision advanced (journalled) and a PENDING epoch
        # increment was recorded; the base epoch is untouched so verified
        # reads keep passing.
        assert after.control_revision == before.control_revision + 1
        assert after.pending_epoch_increments == 1
        assert after.eligibility_epoch == before.eligibility_epoch
        export = operator.read_export(capability=capability)
        assert export["tasks"] == []

        # Retrying the same plan is idempotent: no second journal entry,
        # no second pending increment.
        retried = governance.apply_forget(capability=capability, plan=plan)
        assert retried.newly_revoked_count == 0
        assert retried.suppression_id == receipt.suppression_id
        assert operator.status().pending_epoch_increments == 1

        # Retention sees the fresh journal as ineligible; nothing archives.
        retention = governance.plan_retention(
            capability=capability, older_than_days=30
        )
        assert retention.eligible_suppression_journals == ()
        assert (
            governance.apply_retention(capability=capability, plan=retention) == 0
        )

        # Aged journals ARCHIVE (bytes retained), never delete, and the
        # suppression stays enforceable from the archive-free live set.
        import os as _os
        import time as _time

        journals = list(
            (service.installation_root / "control" / "suppressions").glob(
                "forget-*.json"
            )
        )
        aged = _time.time() - 40 * 86400
        for journal in journals:
            _os.utime(journal, (aged, aged))
        aged_plan = governance.plan_retention(
            capability=capability, older_than_days=30
        )
        assert len(aged_plan.eligible_suppression_journals) == 1
        assert (
            governance.apply_retention(capability=capability, plan=aged_plan) == 1
        )
        archive = (
            service.installation_root / "control" / "suppressions-archive"
        )
        assert list(archive.glob("forget-*.json")), "bytes retained in archive"
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


def test_writer_enrollment_barriers_unknown_writers(tmp_path: Path) -> None:
    from memorii.core.storage_administration.writer_enrollment import (
        WriterEnrollmentError,
        WriterEnrollmentRegistry,
    )

    registry = WriterEnrollmentRegistry(tmp_path / "control" / "writers")
    with pytest.raises(WriterEnrollmentError, match="not enrolled"):
        registry.require_enrolled("writer:unknown")

    record = registry.enroll("writer:runtime", kind="runtime-sqlite")
    assert registry.require_enrolled("writer:runtime") == record
    # Idempotent re-enrollment; kind drift refuses.
    assert registry.enroll("writer:runtime", kind="runtime-sqlite") == record
    with pytest.raises(WriterEnrollmentError, match="kind drift"):
        registry.enroll("writer:runtime", kind="memory-plane")

    registry.enroll("writer:memory-plane", kind="memory-plane-sqlite")
    assert len(registry.writers()) == 2

    # Durable across restart; owner-only permissions held.
    reopened = WriterEnrollmentRegistry(tmp_path / "control" / "writers")
    assert {w.writer_id for w in reopened.writers()} == {
        "writer:runtime",
        "writer:memory-plane",
    }


def test_writer_enrollment_gates_publication(tmp_path: Path) -> None:
    from memorii.core.persistence.runtime_contracts import TaskRecord
    from memorii.core.persistence.runtime_repository import publish_runtime_change
    from memorii.core.storage_administration.service import (
        StorageAdministrationService,
    )
    from memorii.core.storage_administration.writer_enrollment import (
        WriterEnrollmentRegistry,
    )

    root = tmp_path / "installation"
    root.mkdir(mode=0o700)
    (root / "control").mkdir(mode=0o700)
    registry = WriterEnrollmentRegistry(root / "control" / "writers")
    service = StorageAdministrationService(
        tmp_path / "installation", writer_enrollment=registry
    )
    try:
        service.initialize()

        def seed(connection, repo) -> None:
            repo.apply_task(
                connection,
                TaskRecord(
                    task_id="task:enroll",
                    principal="principal:a",
                    goal="Enrollment gate",
                    created_at=_NOW,
                    root_execution_node_id="exec:root",
                ),
            )

        # An unregistered writer fails closed with the closed reason.
        with pytest.raises(RuntimeError, match="unsupported_configuration.*not enrolled"):
            publish_runtime_change(service, seed, operation_binding="stranger")

        registry.enroll("runtime-writer", kind="runtime-sqlite")
        # Enrolling a DIFFERENT id does not unlock the stranger binding.
        with pytest.raises(RuntimeError, match="not enrolled"):
            publish_runtime_change(service, seed, operation_binding="stranger")
    finally:
        service.close()


@pytest.mark.parametrize("named_generation", [False, True])
def test_erasure_destroys_the_real_layout_and_keys(tmp_path: Path, named_generation: bool) -> None:
    from memorii.core.storage_administration.generation_selection import PARTITION_GENERATION_SELECTOR
    from memorii.core.storage_administration.operator_backup import BackupRestoreOperator
    from memorii.core.storage_administration.operator_governance import (
        GovernanceOperator,
    )
    from memorii.core.storage_administration.service import (
        StorageAdministrationService,
    )

    root = tmp_path / "installation"
    service = StorageAdministrationService(root)
    service.initialize()
    if named_generation:
        operator = StorageAdministrationOperator(service)
        capability = _capability(service)
        operator.change_mode(
            ModeChangeRequest(
                target_mode="read_only", expected_control_revision=operator.status().control_revision,
                reason="test erasure of named generation",
            ),
            capability=capability,
        )
        backups = BackupRestoreOperator(operator)
        archive, staging = tmp_path / "archive", tmp_path / "staging"
        recovery_key = b"k" * 32
        backups.create_backup(
            capability=capability, archive_root=archive, reason="test backup", recovery_key=recovery_key,
        )
        restore_plan = backups.plan_restore(
            capability=capability, archive_root=archive, data_loss_acknowledged=False,
        )
        backups.apply_restore(
            capability=capability, plan=restore_plan, staging_root=staging, recovery_key=recovery_key,
        )
        backups.activate_exact_current_restore(capability=capability, plan=restore_plan, staging_root=staging)
    service.close()

    service = StorageAdministrationService(root)
    operator = StorageAdministrationOperator(service)
    capability = _capability(service)
    try:
        governance = GovernanceOperator(operator)
        plan = governance.plan_erasure(capability=capability)
        acknowledged = plan.model_copy(update={"acknowledged": True})
        receipt = governance.apply_erasure(
            capability=capability, plan=acknowledged, erase=True
        )
        assert receipt.incomplete is True  # offline copies unaccounted
        # The partition database and signing keys are GONE; control remains
        # as the independent authority holding the content-free receipt.
        assert not service.partition_path().exists()
        assert not (root / "control" / "keys").exists()
        assert not (root / "control" / PARTITION_GENERATION_SELECTOR).exists()
        assert service.control_path().exists()
        receipts = list(
            (root / "control" / "erasure-receipts").glob("erasure-*.json")
        )
        assert receipts
    finally:
        service.close()


def test_doctor_flags_permission_drift(tmp_path: Path) -> None:
    import os as _os

    from memorii.core.storage_administration.operator_governance import (
        GovernanceOperator,
    )

    operator, service = _operator(tmp_path)
    try:
        governance = GovernanceOperator(operator)
        _os.chmod(service.partition_path(), 0o600)
        before = {f.check: f.status for f in governance.doctor()}
        assert before["partition_database_permissions"] == "ok"
        _os.chmod(service.partition_path(), 0o644)
        after = {f.check: f.status for f in governance.doctor()}
        assert after["partition_database_permissions"] == "error"
    finally:
        service.close()


def test_existing_storage_is_refused_until_owner_repairs_permissions(tmp_path: Path) -> None:
    from memorii.core.storage_administration.service import InstallationPermissionsError
    from memorii.tools.runtime_operator import main

    _, service = _operator(tmp_path)
    root = service.installation_root
    partition = service.partition_path()
    with service:
        snapshot = service.acquire_verified_snapshot()
        for directory in (root, root / "control", partition.parent):
            assert stat.S_IMODE(directory.stat().st_mode) == 0o700
        for database in (service.control_path(), partition):
            for suffix in ("", "-wal", "-shm"):
                assert stat.S_IMODE(database.with_name(database.name + suffix).stat().st_mode) == 0o600
        for name in (".init.lock", ".publication.lock"):
            assert stat.S_IMODE((root / name).stat().st_mode) == 0o600

    root.chmod(0o755)
    partition.parent.chmod(0o755)
    partition.chmod(0o644)
    with pytest.raises(InstallationPermissionsError):
        StorageAdministrationService(root)
    assert main(["--installation-root", str(root), "repair-permissions"]) == 0
    with StorageAdministrationService(root) as reopened:
        assert reopened.acquire_verified_snapshot() == snapshot
    assert stat.S_IMODE(partition.stat().st_mode) == 0o600
    assert stat.S_IMODE(partition.parent.stat().st_mode) == 0o700


def test_permission_repair_leaves_unrelated_directories_and_link_targets_alone(tmp_path: Path) -> None:
    from memorii.tools.runtime_operator import main

    unrelated = tmp_path / "unrelated"
    unrelated.mkdir(mode=0o755)
    unrelated.chmod(0o755)
    assert main(["--installation-root", str(unrelated), "repair-permissions"]) == 3
    assert stat.S_IMODE(unrelated.stat().st_mode) == 0o755
    (unrelated / "control" / "keys").mkdir(parents=True)
    (unrelated / "control" / "control.sqlite3").write_bytes(b"not a control database")
    assert main(["--installation-root", str(unrelated), "repair-permissions"]) == 3
    assert stat.S_IMODE(unrelated.stat().st_mode) == 0o755

    _, service = _operator(tmp_path)
    root = service.installation_root
    with service:
        partition = service.partition_path()
    outside = tmp_path / "outside.txt"
    outside.write_text("unchanged")
    outside.chmod(0o644)
    for make_link in (os.link, os.symlink):
        linked = partition.parent / "linked"
        make_link(outside, linked)
        assert main(["--installation-root", str(root), "repair-permissions"]) == 3
        assert outside.read_text() == "unchanged"
        assert stat.S_IMODE(outside.stat().st_mode) == 0o644
        linked.unlink()
    lock = root / ".publication.lock"
    lock.unlink(missing_ok=True)
    lock.symlink_to(outside)
    with pytest.raises(StorageAdministrationError, match="repair-permissions"):
        StorageAdministrationService(root)
    assert main(["--installation-root", str(root), "repair-permissions"]) == 3
    assert stat.S_IMODE(outside.stat().st_mode) == 0o644
    lock.unlink()
    assert main(["--installation-root", str(root), "repair-permissions"]) == 0


def test_operator_reports_closed_diagnostics_for_rejected_secrets_and_payloads(tmp_path: Path) -> None:
    from memorii.core.harness_state.grant_registry import GrantEpochRegistry

    _, service = _operator(tmp_path)
    marker = "synthetic-private-marker"
    private_bad = write_owner_file(tmp_path / "malformed", marker.ljust(64, "!"))
    valid_owner = write_owner_file(tmp_path / "owner", _capability(service).capability_digest)
    with service:
        grants = service.installation_root / "control" / "grants"
        GrantEpochRegistry(grants)
        (grants / "grant-revocations.jsonl").write_text(
            json.dumps({"grant_id": "test", "epoch": marker}) + "\n"
        )
    cli = [
        sys.executable, "-m", "memorii.tools.runtime_operator",
        "--installation-root", str(service.installation_root), "--owner-principal", "owner:one",
    ]
    for arguments, status, diagnostic in (
        (["--capability-digest", marker, "status"], 2, "invalid arguments"),
        (["--capability-file", private_bad, "forget", "plan", "--scope-note", "review"], 3, "malformed"),
        (
            ["--capability-file", valid_owner, "forget", "plan", "--scope-note", "review", "--record", f"{marker}="],
            2, "invalid_request",
        ),
        (["backup", "restore-plan", "--archive-root", str(tmp_path), f"--recovery-key-hex={marker}"], 2, "invalid arguments"),
    ):
        result = subprocess.run([*cli, *arguments], capture_output=True, text=True, timeout=30)
        assert result.returncode == status
        assert result.stdout == ""
        assert diagnostic in result.stderr and marker not in result.stderr
        assert "Traceback" not in result.stderr

    report = subprocess.run([*cli, "doctor"], capture_output=True, text=True, timeout=30, check=True)
    assert marker not in report.stdout and marker not in report.stderr
    findings = {entry["check"]: entry for entry in json.loads(report.stdout)}
    assert findings["grant_registry"]["detail"] == "grant registry could not be verified"


def test_cli_status_doctor_and_capability_refusal(tmp_path: Path) -> None:
    import json as _json
    import subprocess as _subprocess
    import sys as _sys

    service = StorageAdministrationService(tmp_path / "installation")
    service.initialize()
    service.close()

    cli = [
        _sys.executable,
        "-m",
        "memorii.tools.runtime_operator",
        "--installation-root",
        str(tmp_path / "installation"),
    ]
    status = _subprocess.run(cli + ["status"], capture_output=True, text=True)
    assert status.returncode == 0
    assert _json.loads(status.stdout)["mode"] == "active"
    doctor = _subprocess.run(cli + ["doctor"], capture_output=True, text=True)
    assert doctor.returncode == 0
    checks = {row["check"]: row["status"] for row in _json.loads(doctor.stdout)}
    assert checks["control_state"] == "ok"
    refusal = _subprocess.run(
        cli + ["mode", "--target", "read_only", "--expected-revision", "1", "--reason", "x"],
        capture_output=True,
        text=True,
    )
    assert refusal.returncode == 2
    assert "--owner-principal" in refusal.stderr


def test_fresh_host_boot_from_verified_legacy_restore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from memorii.core.storage_administration.operator_backup import (
        BackupRestoreOperator,
        boot_restored_installation,
    )

    monkeypatch.setattr("memorii.stores.sqlite.partition.PARTITION_SCHEMA_VERSION", 1)
    operator, service, capability = _fenced_operator(tmp_path)
    try:
        backups = BackupRestoreOperator(operator)
        recovery_key = b"k" * 32
        backups.create_backup(
            capability=capability,
            archive_root=tmp_path / "archive",
            reason="fresh host",
            recovery_key=recovery_key,
        )
        import json as _json

        anchor = _json.loads(
            (tmp_path / "archive" / "recovery-anchor.json").read_text()
        )
        plan = backups.plan_restore(
            capability=capability,
            archive_root=tmp_path / "archive",
            data_loss_acknowledged=False,
        )
        staging = backups.apply_restore(
            capability=capability,
            plan=plan,
            staging_root=tmp_path / "staged",
            recovery_key=recovery_key,
        )
        fresh_root = tmp_path / "fresh-host"
        identity = boot_restored_installation(
            capability=capability,
            staging_root=staging,
            anchor=anchor,
            installation_root=fresh_root,
            signing_keys_directory=tmp_path / "installation" / "control" / "keys",
        )
        assert identity == anchor["installation_id"]
        assert (fresh_root / "control" / "control.sqlite3").is_file()
        assert (fresh_root / "partition" / "partition.sqlite3").is_file()
        assert stat.S_IMODE(fresh_root.stat().st_mode) == 0o700
        assert stat.S_IMODE((fresh_root / "partition" / "partition.sqlite3").stat().st_mode) == 0o600
        rejected_root = tmp_path / "rejected-boot"
        keys = tmp_path / "installation" / "control" / "keys"
        staged_partition = staging / "partition.sqlite3"
        retained_key = next(keys.glob("*.key"))
        for source in (staged_partition, retained_key):
            source.chmod(0o644)
            with pytest.raises(OperatorError, match="restore media and destination must be private"):
                boot_restored_installation(
                    capability=capability, staging_root=staging, anchor=anchor,
                    installation_root=rejected_root, signing_keys_directory=keys,
                )
            assert not rejected_root.exists()
            source.chmod(0o600)
            original = source.with_suffix(".original")
            source.rename(original)
            source.symlink_to(original)
            with pytest.raises(OperatorError, match="restore media and destination must be private"):
                boot_restored_installation(
                    capability=capability, staging_root=staging, anchor=anchor,
                    installation_root=rejected_root, signing_keys_directory=keys,
                )
            assert not rejected_root.exists()
            source.unlink()
            original.rename(source)
        # A non-empty root refuses; a mismatched anchor refuses.
        with pytest.raises(OperatorError, match="empty installation root"):
            boot_restored_installation(
                capability=capability,
                staging_root=staging,
                anchor=anchor,
                installation_root=fresh_root,
                signing_keys_directory=tmp_path / "installation" / "control" / "keys",
            )
        empty_root = tmp_path / "fresh-two"
        empty_root.mkdir()
        bad_anchor = {**anchor, "installation_id": "ffffffff" * 8}
        with pytest.raises(OperatorError, match="does not match the anchor"):
            boot_restored_installation(
                capability=capability,
                staging_root=staging,
                anchor=bad_anchor,
                installation_root=empty_root,
                signing_keys_directory=tmp_path / "installation" / "control" / "keys",
            )
    finally:
        service.close()


def test_forget_pending_epoch_rides_the_next_publication(tmp_path: Path) -> None:
    from memorii.core.memory_plane.models import CanonicalMemoryRecord
    from memorii.core.storage_administration.operator import ModeChangeRequest
    from memorii.core.storage_administration.operator_governance import (
        ForgetTargetSelector,
        GovernanceOperator,
    )
    from memorii.domain.enums import CommitStatus, MemoryDomain

    operator, service = _operator(tmp_path)
    capability = _capability(service)
    try:
        governance = GovernanceOperator(operator)
        link_payload = {
            "link_id": "link:epoch",
            "mention_text": "fixture",
            "canonical_entity_id": "entity:epoch",
            "normalized_name": "fixture",
            "entity_type": "unknown",
            "aliases": [],
            "observed_names": [],
            "evidence_spans": [],
            "confidence": 0.9,
            "scope": {},
            "lifecycle_state": "active",
        }
        seed_record = CanonicalMemoryRecord(
            memory_id="mem:evolution:link:link:epoch",
            domain=MemoryDomain.SEMANTIC,
            text="fixture",
            content={"memory_evolution_kind": "entity_link", "entity_link": link_payload},
            status=CommitStatus.COMMITTED,
            source_kind="memory_evolution",
        )
        service.publish_memory_plane_batch(
            (seed_record,), operation_binding="epoch_seed"
        )
        plan = governance.plan_forget(
            capability=capability,
            selectors=(ForgetTargetSelector(selector_kind="entity", selector_id="entity:epoch"),),
            scope_note="epoch ride",
        )
        operator.change_mode(
            ModeChangeRequest(
                target_mode="read_only",
                expected_control_revision=operator.status().control_revision,
                reason="forget barrier",
            ),
            capability=capability,
        )
        base_epoch = operator.status().eligibility_epoch
        governance.apply_forget(capability=capability, plan=plan)

        # In the window: Tier A still passes (verified reads succeed), the
        # base epoch is untouched, and one increment is pending.
        window = operator.status()
        assert window.eligibility_epoch == base_epoch
        assert window.pending_epoch_increments == 1
        assert operator.read_export(capability=capability)["tasks"] == []

        operator.change_mode(
            ModeChangeRequest(
                target_mode="active",
                expected_control_revision=window.control_revision,
                reason="resume",
            ),
            capability=capability,
        )

        # The next publication embeds the effective epoch and finalize
        # advances the base epoch atomically with the tuple.
        follow_up = seed_record.model_copy(update={"text": "follow-up"})
        service.publish_memory_plane_batch((follow_up,), operation_binding="epoch_follow_up")
        after = operator.status()
        assert after.eligibility_epoch == base_epoch + 1
        assert after.pending_epoch_increments == 0
        assert operator.read_export(capability=capability)["publication_ordinal"] > 0
    finally:
        service.close()
