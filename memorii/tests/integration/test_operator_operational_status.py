"""Content-free status through recovered, inert, and admitted installation states."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import NoReturn

import pytest
from memorii.core.harness_state.consumer import HostEventDelivery
from memorii.core.harness_state.managed_spool_store import SqliteManagedSpool
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.persistence.contracts import (
    InstallationControlJournalEntry,
    RuntimePublicationIntent,
    canonical_json_digest,
)
from memorii.core.persistence.runtime_api import (
    ManagedRuntimeCommandService,
    OutboxStatus,
    ResolvedRuntimeCommandAuthority,
    RuntimeOutboxDelivery,
    apply_outbox_delivery,
)
from memorii.core.persistence.runtime_contracts import RuntimeCommandRequest
from memorii.core.persistence.runtime_repository import RuntimeStateRepository, publish_runtime_change
from memorii.core.storage_administration import operator as operator_owner
from memorii.core.storage_administration.managed_spool_selection import (
    open_managed_spool,
    register_managed_spool,
)
from memorii.core.storage_administration.operator import (
    ModeChangeRequest,
    StorageAdministrationOperator,
    mint_owner_capability,
)
from memorii.core.storage_administration.operator_backup import BackupRestoreOperator
from memorii.core.storage_administration.service import REPLACEMENT_RECOVERY_QUARANTINE, StorageAdministrationService
from memorii.domain.enums import CommitStatus, MemoryDomain
from memorii.tools.runtime_operator import main


def test_status_reports_signed_scopes_and_selected_archive_without_content(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "installation"
    archive = tmp_path / "semantic-private-marker"
    with StorageAdministrationService(root) as service:
        operator = StorageAdministrationOperator(service)
        assert operator.status().readiness == "uninitialized"
        installed = service.initialize()
        capability = mint_owner_capability(service, "owner")
        binding = register_managed_spool(service, capability=capability, initializing=True)
        assert operator.status().intake_queue is not None

        def stage(connection: sqlite3.Connection, repository: RuntimeStateRepository) -> None:
            outcomes: tuple[tuple[str, OutboxStatus], ...] = (("pending", "pending"), ("held", "needs_reconciliation"))
            for identity, outcome in outcomes:
                apply_outbox_delivery(connection, repository, RuntimeOutboxDelivery(
                    delivery_id=f"secret-{identity}", origin_operation_id="secret-runtime-coordinate",
                    kind="work_projection", target_protocol="test-owner", payload_digest="0" * 64,
                    status=outcome, fence_token=1,
                ))

        publish_runtime_change(service, stage, operation_binding="migrate")
        owner_commands = ManagedRuntimeCommandService(
            service, authorize=lambda *_: ResolvedRuntimeCommandAuthority("private-principal", "private-origin"),
        )
        command = RuntimeCommandRequest(kind="start_task", operation_id="private-start", goal="private task goal")
        proof = owner_commands.prepare(command)
        spool = open_managed_spool(service)
        spool.admit(
            HostEventDelivery(
                transport_message_id="private-message", producer_binding="private-origin", command=command,
            ),
            operation_origin=proof,
            validate=lambda request, origin: owner_commands.validate_intake(request, operation_origin=origin),
        )

        outbox_counts = operator_owner.delivery_queue_status
        intake_counts = SqliteManagedSpool.backlog_counts

        def count_outbox(*args):
            with service._publication_fence(blocking=False):
                pass
            return outbox_counts(*args)

        def count_intake(*args, **kwargs):
            with service._publication_fence(blocking=False):
                pass
            return intake_counts(*args, **kwargs)

        monkeypatch.setattr(operator_owner, "delivery_queue_status", count_outbox)
        monkeypatch.setattr(SqliteManagedSpool, "backlog_counts", staticmethod(count_intake))
        active = operator.status()
        assert active.verified_generation_id == installed.data_generation_id
        assert active.verified_publication_digest == service.acquire_verified_snapshot().tuple_digest
        assert active.storage_schema_version == 8
        assert active.readiness == "ready" and active.effective_mode == "active"
        assert active.custody_state == "unknown" and active.backup_state == "unknown"
        assert active.artifact.distribution == "memorii"
        assert active.delivery_queue is not None and active.intake_queue is not None
        assert (active.delivery_queue.pending_count, active.delivery_queue.held_count) == (1, 1)
        assert (active.intake_queue.pending_count, active.intake_queue.held_count) == (1, 0)
        assert active.intake_queue.oldest_pending_age_seconds is None
        assert active.control_revision is not None
        operator.change_mode(ModeChangeRequest(
            target_mode="read_only", expected_control_revision=active.control_revision, reason="status smoke",
        ), capability=capability)
        BackupRestoreOperator(operator).create_backup(
            capability=capability, archive_root=archive, reason="status smoke", recovery_key=b"e" * 32,
        )

    cli = ["--installation-root", str(root), "status", "--backup-archive", str(archive)]
    assert main(cli) == 0
    output = capsys.readouterr().out
    assert all(marker not in output for marker in ("semantic-private-marker", "private task goal", "private-origin"))
    report = json.loads(output)
    assert report["backup_state"] == "verified"
    assert report["verified_backup_age_seconds"] >= 0
    assert report["effective_mode"] == "read_only"
    assert main(["--installation-root", str(root), "status", "--backup-archive", str(archive / "missing")]) == 0
    assert json.loads(capsys.readouterr().out)["backup_state"] == "unavailable"
    selected = root / "spool" / "managed" / f"store-{binding.store_id}.sqlite3"
    selected.rename(tmp_path / "detached")
    assert main(["--installation-root", str(root), "status"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["readiness"] == "unavailable" and report["effective_mode"] == "offline"
    assert report["intake_queue"] is None and not selected.exists()


def test_status_refuses_to_open_inert_replacement_even_for_operator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    with StorageAdministrationService(tmp_path / "installation") as service:
        service.initialize()
        with service._publication_fence():
            state = service._control_state()
            candidate = state.model_copy(update={
                "mode": "read_only", "control_revision": state.control_revision + 1,
                "quarantined_reason": REPLACEMENT_RECOVERY_QUARANTINE,
            })
            service._control.write_control_state(candidate, service._journal_entry(
                operation="mode_changed", before_digest=canonical_json_digest(state.model_dump()),
                after_digest=canonical_json_digest(candidate.model_dump()),
            ))

        def unavailable() -> NoReturn:
            raise AssertionError("status opened inert replacement data")

        monkeypatch.setattr(service, "partition", unavailable)
        report = StorageAdministrationOperator(service).status()
        assert report.readiness == "pending_recovery"
        assert report.custody_state == "pending"
        assert report.effective_mode == "offline"
        assert report.verified_generation_id is None
        assert report.intake_queue is None and report.delivery_queue is None


def test_status_does_not_resolve_prepared_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    with StorageAdministrationService(tmp_path / "installation") as service:
        service.initialize()
        write_intent = service._control.write_intent

        def interrupt(intent: RuntimePublicationIntent, journal_entry: InstallationControlJournalEntry) -> NoReturn:
            write_intent(intent, journal_entry)
            raise OSError("simulated interruption after prepared publication")

        monkeypatch.setattr(service._control, "write_intent", interrupt)
        with pytest.raises(OSError, match="simulated interruption"):
            service.publish_memory_plane_batch((CanonicalMemoryRecord(
                memory_id="hidden-pending", domain=MemoryDomain.USER,
                text="pending private text", status=CommitStatus.COMMITTED,
            ),))
        before = service._control.read_pending_intent(service._repository_id())
        assert before is not None
        report = StorageAdministrationOperator(service).status()
        assert report.readiness == "pending_recovery"
        assert report.verified_generation_id is None and report.effective_mode == "offline"
        assert service._control.read_pending_intent(service._repository_id()) == before
