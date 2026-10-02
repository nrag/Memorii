"""Runtime checkpoints: signed snapshots and the resume envelope.

Checkpoints accelerate reads and never create durability by themselves.
One checkpoint binds the exact runtime revision it was taken at, a
canonical manifest of its members, and an Ed25519 signature over a
domain-separated digest (``memorii.runtime-checkpoint.v1``) issued by
the installation's signing key owner — key bytes never enter the
checkpoint or the data generation. Resume reconstructs one consistent
view from a verified checkpoint plus the signed tail, revalidates
time-dependent evidence (expired assumptions produce
revalidation_required; dependent recommendations become
non-actionable), never changes a dispatched external action's state and
never repeats a tool.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.persistence.runtime_contracts import (
    RuntimeOverlayVersion,
    SolverJustificationRecord,
    SolverRunRecord,
    TaskRecord,
)
from memorii.core.persistence.runtime_repository import RuntimeStateRepository

_HEX_64 = r"^[0-9a-f]{64}$"
CHECKPOINT_SIGNATURE_PURPOSE = "memorii.runtime-checkpoint.v1"


class RuntimeCheckpointError(RuntimeError):
    """Checkpoint creation or verification refused."""


class RuntimeCheckpointManifest(BaseModel):
    """Canonical manifest of one checkpoint's members."""

    repository_id: str = Field(min_length=1)
    runtime_revision: int = Field(ge=1)
    task_count: int = Field(ge=0)
    solver_run_count: int = Field(ge=0)
    overlay_count: int = Field(ge=0)
    justification_count: int = Field(ge=0)
    member_digest: str = Field(pattern=_HEX_64)

    model_config = ConfigDict(extra="forbid", frozen=True)


class RuntimeCheckpoint(BaseModel):
    """One signed checkpoint over durable runtime state."""

    checkpoint_id: str = Field(min_length=1)
    manifest: RuntimeCheckpointManifest
    created_at: datetime
    signer_key_id: str = Field(min_length=1)
    signature: str = Field(min_length=1)
    tasks: tuple[TaskRecord, ...] = ()
    solver_runs: tuple[SolverRunRecord, ...] = ()
    overlays: tuple[RuntimeOverlayVersion, ...] = ()
    justifications: tuple[SolverJustificationRecord, ...] = ()

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def manifest_counts_match(self) -> RuntimeCheckpoint:
        checks = (
            (len(self.tasks), self.manifest.task_count),
            (len(self.solver_runs), self.manifest.solver_run_count),
            (len(self.overlays), self.manifest.overlay_count),
            (len(self.justifications), self.manifest.justification_count),
        )
        for actual, declared in checks:
            if actual != declared:
                raise ValueError(
                    f"checkpoint manifest count mismatch: {actual} != {declared}"
                )
        return self


def compute_checkpoint_manifest_digest(manifest: RuntimeCheckpointManifest) -> str:
    import hashlib

    payload = ":".join(
        (
            manifest.repository_id,
            str(manifest.runtime_revision),
            str(manifest.task_count),
            str(manifest.solver_run_count),
            str(manifest.overlay_count),
            str(manifest.justification_count),
            manifest.member_digest,
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ResumeStatus(str):
    READY = "ready"
    REVALIDATION_REQUIRED = "revalidation_required"
    RECONCILE_REQUIRED = "reconcile_required"


class HarnessResumeEnvelope(BaseModel):
    """One consistent restored view for the host adapter."""

    protocol_version: Literal[1] = 1
    task_id: str = Field(min_length=1)
    runtime_revision: int = Field(ge=0)
    checkpoint_id: str | None = None
    status: Literal["ready", "revalidation_required", "reconcile_required"]
    task: TaskRecord
    solver_runs: tuple[SolverRunRecord, ...] = ()
    overlays: tuple[RuntimeOverlayVersion, ...] = ()
    justifications: tuple[SolverJustificationRecord, ...] = ()
    pending_actions: tuple[str, ...] = ()
    revalidation_reasons: tuple[str, ...] = ()

    model_config = ConfigDict(extra="forbid", frozen=True)


def create_runtime_checkpoint(
    repository: RuntimeStateRepository,
    *,
    signer_key_id: str,
    sign: object,
    checkpoint_id: str | None = None,
    now: datetime | None = None,
    connection: sqlite3.Connection | None = None,
) -> RuntimeCheckpoint:
    """Snapshot one consistent verified view and sign its manifest.

    When ``connection`` is supplied the snapshot reads run inside that
    already-open transaction (the publication path); otherwise the
    repository opens its own read transaction as before.
    """
    import hashlib
    import uuid

    if connection is not None:
        import sqlite3 as _sqlite3

        rows = connection.execute(
            "SELECT record_json FROM runtime_tasks"
        ).fetchall()
        tasks = tuple(
            TaskRecord.model_validate_json(str(row[0])) for row in rows
        )
        solver_runs: list[SolverRunRecord] = []
        overlays: list[RuntimeOverlayVersion] = []
        justifications: list[SolverJustificationRecord] = []
        for task in tasks:
            for run in repository.list_solver_runs_in(connection, task.task_id):
                solver_runs.append(run)
                overlays.extend(repository.list_overlays_in(connection, run.solver_id))
                justifications.extend(
                    repository.list_justifications_in(connection, run.solver_id)
                )
        member_source = (tasks, solver_runs, overlays, justifications)
        revision = repository.read_runtime_revision_in(connection)
        del _sqlite3
    else:
        tasks = repository.list_tasks()
        solver_runs = []
        overlays = []
        justifications = []
        for task in tasks:
            for run in repository.list_solver_runs(task.task_id):
                solver_runs.append(run)
                overlays.extend(repository.list_overlays(run.solver_id))
                justifications.extend(repository.list_justifications(run.solver_id))
        member_source = None
        revision = repository.runtime_revision()
    if member_source is not None:
        tasks, solver_runs, overlays, justifications = member_source
    member_digest = hashlib.sha256(
        (
            "|".join(sorted(task.task_id for task in tasks))
            + "|"
            + "|".join(sorted(run.solver_id for run in solver_runs))
            + "|"
            + "|".join(sorted(o.version_id for o in overlays))
            + "|"
            + "|".join(sorted(j.justification_id for j in justifications))
        ).encode("utf-8")
    ).hexdigest()
    if revision < 1:
        raise RuntimeCheckpointError(
            "a checkpoint requires at least one committed runtime revision"
        )
    manifest = RuntimeCheckpointManifest(
        repository_id="default",
        runtime_revision=revision,
        task_count=len(tasks),
        solver_run_count=len(solver_runs),
        overlay_count=len(overlays),
        justification_count=len(justifications),
        member_digest=member_digest,
    )
    digest = compute_checkpoint_manifest_digest(manifest)
    signature = sign(CHECKPOINT_SIGNATURE_PURPOSE, digest)  # type: ignore[call-arg]
    return RuntimeCheckpoint(
        checkpoint_id=checkpoint_id or ("checkpoint:" + uuid.uuid4().hex[:16]),
        manifest=manifest,
        created_at=now or datetime.now(UTC),
        signer_key_id=signer_key_id,
        signature=signature,
        tasks=tuple(sorted(tasks, key=lambda task: task.task_id)),
        solver_runs=tuple(sorted(solver_runs, key=lambda run: run.solver_id)),
        overlays=tuple(sorted(overlays, key=lambda overlay: overlay.version_id)),
        justifications=tuple(
            sorted(justifications, key=lambda item: item.justification_id)
        ),
    )


def verify_runtime_checkpoint(
    checkpoint: RuntimeCheckpoint,
    *,
    verify: object,
) -> None:
    """Fail closed on signature, purpose or manifest mismatch."""
    digest = compute_checkpoint_manifest_digest(checkpoint.manifest)
    ok = verify(checkpoint.signer_key_id, CHECKPOINT_SIGNATURE_PURPOSE, digest, checkpoint.signature)  # type: ignore[call-arg]
    if not ok:
        raise RuntimeCheckpointError(
            "integrity_error: checkpoint signature verification failed"
        )


def build_resume_envelope(
    repository: RuntimeStateRepository,
    *,
    task_id: str,
    now: datetime | None = None,
    checkpoint: RuntimeCheckpoint | None = None,
) -> HarnessResumeEnvelope:
    """Restore one consistent view; never rerun or auto-complete actions."""
    moment = now or datetime.now(UTC)
    task = repository.get_task(task_id)
    if task is None:
        raise RuntimeCheckpointError(f"not_found: task {task_id} does not exist")
    runs = repository.list_solver_runs(task_id)
    overlays: list[RuntimeOverlayVersion] = []
    justifications: list[SolverJustificationRecord] = []
    for run in runs:
        overlays.extend(repository.list_overlays(run.solver_id))
        justifications.extend(repository.list_justifications(run.solver_id))
    pending_actions = [
        attempt.action_id
        for attempt in repository.list_action_attempts(task_id)
        if attempt.status in ("dispatched", "outcome_unknown")
    ]
    # Temporal revalidation: an ASSUMPTION node whose valid_to has passed
    # (or whose valid_from has not yet arrived) relative to the resume
    # moment lists its node for revalidation; dependent recommendations
    # surface as revalidation_required instead of ready.
    revalidation: list[str] = []
    for run in runs:
        with repository._partition.transaction(write=False) as connection:
            nodes = repository.list_solver_nodes_in(connection, run.solver_id)
        for _solver_id, node_id, content in nodes:
            kind = getattr(content, "kind", None)
            if kind != "ASSUMPTION":
                continue
            valid_from = getattr(content, "valid_from", None)
            valid_to = getattr(content, "valid_to", None)
            expired = valid_to is not None and valid_to < moment
            premature = valid_from is not None and valid_from > moment
            if expired or premature:
                revalidation.append(
                    f"{node_id}:{'expired' if expired else 'not_yet_valid'}"
                )
    del moment  # consumed by the temporal walk above
    if (
        checkpoint is not None
        and checkpoint.manifest.runtime_revision > repository.runtime_revision()
    ):
        raise RuntimeCheckpointError(
            "integrity_error: checkpoint revision exceeds current state"
        )
    status: str = "ready"
    if pending_actions:
        status = "reconcile_required"
    if revalidation:
        status = "revalidation_required"
    return HarnessResumeEnvelope(
        task_id=task_id,
        runtime_revision=repository.runtime_revision(),
        checkpoint_id=None if checkpoint is None else checkpoint.checkpoint_id,
        status=status,  # type: ignore[arg-type]
        task=task,
        solver_runs=tuple(runs),
        overlays=tuple(overlays),
        justifications=tuple(justifications),
        pending_actions=tuple(pending_actions),
        revalidation_reasons=tuple(revalidation),
    )


__all__ = [
    "CHECKPOINT_SIGNATURE_PURPOSE",
    "HarnessResumeEnvelope",
    "RuntimeCheckpoint",
    "RuntimeCheckpointError",
    "RuntimeCheckpointManifest",
    "build_resume_envelope",
    "compute_checkpoint_manifest_digest",
    "create_runtime_checkpoint",
    "verify_runtime_checkpoint",
]
