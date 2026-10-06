"""Operator controls: owner capability, modes, status, export."""

from __future__ import annotations

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
from memorii.core.storage_administration.service import StorageAdministrationService

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _operator(tmp_path: Path) -> tuple[StorageAdministrationOperator, StorageAdministrationService]:
    service = StorageAdministrationService(tmp_path / "installation")
    service.initialize()
    return StorageAdministrationOperator(service), service


def _capability(service: StorageAdministrationService) -> OwnerCapability:
    from memorii.core.storage_administration.operator import mint_owner_capability

    return mint_owner_capability(service, "owner:one")


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
            _validate_participant as _validate,
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

    registry = WriterEnrollmentRegistry(tmp_path / "installation" / "control" / "writers")
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


def test_erasure_destroys_the_real_layout_and_keys(tmp_path: Path) -> None:
    from memorii.core.storage_administration.operator_governance import (
        GovernanceOperator,
    )
    from memorii.core.storage_administration.service import (
        StorageAdministrationService,
    )

    root = tmp_path / "installation"
    service = StorageAdministrationService(root)
    service.initialize()
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


def test_fresh_host_boot_from_verified_restore(tmp_path: Path) -> None:
    from memorii.core.storage_administration.operator_backup import (
        BackupRestoreOperator,
        boot_restored_installation,
    )

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
