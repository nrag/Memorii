"""Runtime checkpoints and resume: signed snapshots, consistent restore."""

from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from memorii.core.persistence.runtime_api import (
    RuntimeCommandService,
    reserve_dispatch,
)
from memorii.core.persistence.runtime_checkpoint import (
    CHECKPOINT_SIGNATURE_PURPOSE,
    RuntimeCheckpoint,
    RuntimeCheckpointError,
    build_resume_envelope,
    create_runtime_checkpoint,
    verify_runtime_checkpoint,
)
from memorii.core.persistence.runtime_contracts import (
    RuntimeCommandRequest,
)
from memorii.core.storage_administration.service import StorageAdministrationService

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _command_service(tmp_path: Path) -> RuntimeCommandService:
    administration = StorageAdministrationService(tmp_path / "installation")
    administration.initialize()
    return RuntimeCommandService(administration)


def _sign(purpose: str, digest: str) -> str:
    # Deterministic stand-in for the key owner in unit-scope tests; the
    # signature plumbing is exercised via verify below.
    import hashlib

    return hashlib.sha256(f"{purpose}:{digest}".encode()).hexdigest()


def _verify(key_id: str, purpose: str, digest: str, signature: str) -> bool:
    return signature == _sign(purpose, digest)


def _seeded_service_with_task(tmp_path: Path) -> tuple[RuntimeCommandService, str]:
    service = _command_service(tmp_path)
    service.dispatch(
        RuntimeCommandRequest(
            kind="start_task", operation_id="op:start", goal="Diagnose latency"
        )
    )
    task_id = service.repository.list_tasks()[0].task_id
    return service, task_id


def test_checkpoint_is_signed_counted_and_verified(tmp_path: Path) -> None:
    service, task_id = _seeded_service_with_task(tmp_path)
    try:
        checkpoint = create_runtime_checkpoint(
            service.repository,
            signer_key_id="installation-control",
            sign=_sign,
            now=_NOW,
        )
        assert checkpoint.manifest.task_count == 1
        assert checkpoint.manifest.runtime_revision >= 1
        verify_runtime_checkpoint(checkpoint, verify=_verify)

        forged = checkpoint.model_copy(
            update={"signature": _sign(CHECKPOINT_SIGNATURE_PURPOSE, "f" * 64)}
        )
        with pytest.raises(RuntimeCheckpointError, match="signature"):
            verify_runtime_checkpoint(forged, verify=_verify)

        with pytest.raises(ValueError, match="count mismatch"):
            # model_copy bypasses validation by design; parse is the boundary
            RuntimeCheckpoint.model_validate(
                checkpoint.model_dump(mode="json")
                | {
                    "manifest": checkpoint.manifest.model_dump(mode="json")
                    | {"task_count": 2}
                }
            )
    finally:
        service._administration.close()


def test_checkpoint_requires_a_committed_revision(tmp_path: Path) -> None:
    service = _command_service(tmp_path)
    try:
        with pytest.raises(RuntimeCheckpointError, match="committed runtime revision"):
            create_runtime_checkpoint(
                service.repository,
                signer_key_id="installation-control",
                sign=_sign,
            )
    finally:
        service._administration.close()


def test_resume_envelope_reconciles_pending_actions_without_rerunning(
    tmp_path: Path,
) -> None:
    service, task_id = _seeded_service_with_task(tmp_path)
    try:
        reserve_dispatch(
            service.repository,
            service._administration,
            task_id=task_id,
            recommendation_id="rec:1",
            recommendation_revision=1,
            executor_binding="host-a",
        )
        checkpoint = create_runtime_checkpoint(
            service.repository,
            signer_key_id="installation-control",
            sign=_sign,
            now=_NOW,
        )
        envelope = build_resume_envelope(
            service.repository, task_id=task_id, checkpoint=checkpoint
        )
        assert envelope.status == "reconcile_required"
        assert envelope.pending_actions  # dispatched action survives; never rerun
        assert envelope.task.task_id == task_id
        assert envelope.runtime_revision == service.repository.runtime_revision()
    finally:
        service._administration.close()


def test_resume_envelope_ready_and_not_found(tmp_path: Path) -> None:
    service, task_id = _seeded_service_with_task(tmp_path)
    try:
        envelope = build_resume_envelope(service.repository, task_id=task_id)
        assert envelope.status == "ready"
        assert envelope.pending_actions == ()
        with pytest.raises(RuntimeCheckpointError, match="not_found"):
            build_resume_envelope(service.repository, task_id="task:missing")
    finally:
        service._administration.close()


def test_checkpoint_from_future_revision_refuses(tmp_path: Path) -> None:
    service, task_id = _seeded_service_with_task(tmp_path)
    try:
        checkpoint = create_runtime_checkpoint(
            service.repository,
            signer_key_id="installation-control",
            sign=_sign,
            now=_NOW,
        )
        ahead = checkpoint.model_copy(
            update={
                "manifest": checkpoint.manifest.model_copy(
                    update={"runtime_revision": checkpoint.manifest.runtime_revision + 5}
                )
            }
        )
        with pytest.raises(RuntimeCheckpointError, match="exceeds current state"):
            build_resume_envelope(
                service.repository, task_id=task_id, checkpoint=ahead
            )
    finally:
        service._administration.close()


_RESUME_PROGRAM = '''
import sys
from datetime import UTC, datetime
from pathlib import Path

from memorii.core.persistence.runtime_api import RuntimeCommandService
from memorii.core.persistence.runtime_checkpoint import build_resume_envelope
from memorii.core.persistence.runtime_contracts import RuntimeCommandRequest

root = Path(sys.argv[1])
administration_service = __import__(
    "memorii.core.storage_administration.service", fromlist=["x"]
).StorageAdministrationService(root)
service = RuntimeCommandService(administration_service, client_namespace="author")
try:
    service.dispatch(RuntimeCommandRequest(
        kind="start_task", operation_id="op:start", goal="Cross process resume"))
    task_id = service.repository.list_tasks()[0].task_id
    service.dispatch(RuntimeCommandRequest(
        kind="pause_task", operation_id="op:pause", task_id=task_id,
        expected_revision=1, pause_reason="user stop"))
    print(task_id)
finally:
    administration_service.close()
'''

_RESUME_READER = '''
import sys
from pathlib import Path

from memorii.core.persistence.runtime_api import RuntimeCommandService
from memorii.core.persistence.runtime_checkpoint import build_resume_envelope

root = Path(sys.argv[1])
administration_service = __import__(
    "memorii.core.storage_administration.service", fromlist=["x"]
).StorageAdministrationService(root)
service = RuntimeCommandService(administration_service, client_namespace="reader")
try:
    envelope = build_resume_envelope(service.repository, task_id=sys.argv[2])
    print(envelope.status, envelope.task.lifecycle, envelope.runtime_revision >= 2)
finally:
    administration_service.close()
'''


def test_resume_across_processes_restores_paused_state(tmp_path: Path) -> None:
    root = tmp_path / "installation"
    administration = StorageAdministrationService(root)
    administration.initialize()
    administration.close()
    author = subprocess.run(
        [sys.executable, "-c", _RESUME_PROGRAM, str(root)],
        capture_output=True,
        text=True,
        check=True,
        cwd=Path(__file__).resolve().parents[2],
    )
    task_id = author.stdout.strip()
    reader = subprocess.run(
        [sys.executable, "-c", _RESUME_READER, str(root), task_id],
        capture_output=True,
        text=True,
        check=True,
        cwd=Path(__file__).resolve().parents[2],
    )
    assert reader.stdout.strip() == "ready paused True"
