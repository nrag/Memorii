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
from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.consolidation.runtime_outputs import ArchivePackageRef, SourceReferences
from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
from memorii.core.persistence.runtime_contracts import (
    AssumptionContent,
    RuntimeOverlayVersion,
    SolverJustificationRecord,
    SolverRunRecord,
    TaskRecord,
    canonical_runtime_digest,
)
from memorii.core.persistence.runtime_repository import RuntimeStateRepository
from memorii.core.storage_administration.revoked_identity_view import (
    RevokedIdentityServingGate,
)
from memorii.domain.execution_graph.nodes import ExecutionNode

_HEX_64 = r"^[0-9a-f]{64}$"
CHECKPOINT_SIGNATURE_PURPOSE = "memorii.runtime-checkpoint.v1"


class RuntimeCheckpointError(RuntimeError):
    """Checkpoint creation or verification refused."""


class TaskLifecycleCheckpoint(BaseModel):
    """Full pre-transition snapshot for a managed root and its source closure."""

    kind: Literal["task_lifecycle_checkpoint"] = "task_lifecycle_checkpoint"
    installation_id: str = Field(min_length=1)
    partition_id: str = Field(min_length=1)
    generation_id: str = Field(min_length=1)
    publication_digest: str = Field(pattern=_HEX_64)
    runtime_revision: int = Field(ge=1)
    task: TaskRecord
    root_node: ExecutionNode
    source_closure: SourceReferences = ()

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def root_matches_task(self) -> TaskLifecycleCheckpoint:
        if self.root_node.id != self.task.root_execution_node_id or self.root_node.owner != self.task.principal:
            raise ValueError("checkpoint root must belong to its task")
        return self

    def digest(self) -> str:
        return sha256(encode_typed_value(self.model_dump(mode="python"))).hexdigest()


class TaskLifecycleArchiveManifest(BaseModel):
    """Owner-prepared immutable archive closure for one signed checkpoint."""

    checkpoint_id: str = Field(min_length=1)
    checkpoint_digest: str = Field(pattern=_HEX_64)
    origin_revision: int = Field(ge=1)
    source_closure: SourceReferences = ()

    model_config = ConfigDict(extra="forbid", frozen=True)

    def digest(self) -> str:
        return sha256(encode_typed_value(self.model_dump(mode="python"))).hexdigest()


class TaskLifecycleArchive(BaseModel):
    """Manifest-covered checkpoint bytes, signer and retention reference."""

    checkpoint_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    checkpoint_digest: str = Field(pattern=_HEX_64)
    checkpoint: TaskLifecycleCheckpoint
    signer_key_id: str = Field(min_length=1)
    signature: str = Field(pattern=r"^[0-9a-f]{128}$")
    manifest: TaskLifecycleArchiveManifest

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def verify_closure(self) -> TaskLifecycleArchive:
        if (
            self.task_id != self.checkpoint.task.task_id
            or self.checkpoint_digest != self.checkpoint.digest()
            or self.checkpoint_id != f"checkpoint:{self.checkpoint_digest}"
            or self.manifest.checkpoint_id != self.checkpoint_id
            or self.manifest.checkpoint_digest != self.checkpoint_digest
            or self.manifest.origin_revision != self.checkpoint.runtime_revision + 1
            or self.manifest.source_closure != self.checkpoint.source_closure
        ):
            raise ValueError("task archive does not bind its exact checkpoint and origin")
        return self

    def reference(self) -> ArchivePackageRef:
        manifest_digest = self.manifest.digest()
        return ArchivePackageRef(
            installation_id=self.checkpoint.installation_id,
            partition_id=self.checkpoint.partition_id,
            task_id=self.task_id,
            origin_revision=self.manifest.origin_revision,
            checkpoint_id=self.checkpoint_id,
            checkpoint_digest=self.checkpoint_digest,
            manifest_id=f"archive:{manifest_digest}",
            manifest_digest=manifest_digest,
        )

    def verify_signature(self, verify: Callable[[str, str, str, str], bool]) -> None:
        digest = self.checkpoint.digest()
        if digest != self.checkpoint_digest or not verify(
            self.signer_key_id, CHECKPOINT_SIGNATURE_PURPOSE, digest, self.signature,
        ):
            raise RuntimeCheckpointError("integrity_error: task checkpoint signature verification failed")


def read_bounded_task_root(
    repository: RuntimeStateRepository, connection: sqlite3.Connection, task: TaskRecord,
    *, verified_sources: SourceReferences = (),
) -> ExecutionNode:
    """Validate the complete archive/resume graph supported by this owner."""
    from memorii.core.memory_plane.store import (
        RUNTIME_WRITEBACK_CANDIDATE_ID_PREFIX,
        RUNTIME_WRITEBACK_CANDIDATE_SOURCE_KIND,
    )

    partition = repository.partition
    rows = partition.read_runtime_rows(
        connection, table="runtime_execution_nodes", match=(("task_id", task.task_id),),
    )
    verified_ids = tuple(ref.source_id for ref in verified_sources)
    permitted = ", ".join("?" for _ in verified_ids)
    other_evidence = connection.execute(
        "SELECT 1 FROM memory_current_records WHERE json_extract(record_json, '$.task_id') = ?"
        " AND NOT (source_kind = ? AND memory_id GLOB ?)"
        + (f" AND memory_id NOT IN ({permitted})" if verified_ids else "")
        + " LIMIT 1",
        (task.task_id, RUNTIME_WRITEBACK_CANDIDATE_SOURCE_KIND, RUNTIME_WRITEBACK_CANDIDATE_ID_PREFIX + "*", *verified_ids),
    ).fetchone()
    if (
        len(rows) != 1
        or task.active_solver_by_execution_node
        or repository.list_solver_runs_in(connection, task.task_id)
        or repository.list_action_attempts_in(connection, task.task_id)
        or partition.read_runtime_rows(
            connection, table="runtime_execution_edges", match=(("task_id", task.task_id),),
        )
        or other_evidence is not None
    ):
        raise RuntimeCheckpointError("unsupported_configuration: full task archive closure is unavailable")
    root = ExecutionNode.model_validate_json(rows[0]["record_json"])
    if root.id != task.root_execution_node_id or root.owner != task.principal:
        raise RuntimeCheckpointError("integrity_error: execution root does not match the task")
    if root.linked_artifacts or root.linked_constraints:
        raise RuntimeCheckpointError("unsupported_configuration: linked archive artifacts require their owner")
    return root


def stage_task_lifecycle_archive(
    repository: RuntimeStateRepository,
    connection: sqlite3.Connection,
    *,
    task: TaskRecord,
    installation_id: str,
    partition_id: str,
    generation_id: str,
    signer_key_id: str,
    sign: Callable[[str, str], str],
    source_closure: SourceReferences = (),
) -> tuple[TaskLifecycleArchive, ExecutionNode]:
    """Archive verified task state before a managed lifecycle transition."""
    partition = repository.partition
    publication = partition.read_publication_row(connection)
    if publication is None or publication["generation_id"] != generation_id:
        raise RuntimeCheckpointError("integrity_error: task archive publication origin mismatch")
    root = read_bounded_task_root(repository, connection, task, verified_sources=source_closure)
    checkpoint = TaskLifecycleCheckpoint(
        installation_id=installation_id,
        partition_id=partition_id,
        generation_id=generation_id,
        publication_digest=publication["tuple_digest"],
        runtime_revision=repository.read_runtime_revision_in(connection) - 1,
        task=task,
        root_node=root,
        source_closure=source_closure,
    )
    checkpoint_digest = checkpoint.digest()
    checkpoint_id = f"checkpoint:{checkpoint_digest}"
    archive = TaskLifecycleArchive(
        checkpoint_id=checkpoint_id,
        task_id=task.task_id,
        checkpoint_digest=checkpoint_digest,
        checkpoint=checkpoint,
        signer_key_id=signer_key_id,
        signature=sign(CHECKPOINT_SIGNATURE_PURPOSE, checkpoint_digest),
        manifest=TaskLifecycleArchiveManifest(
            checkpoint_id=checkpoint_id,
            checkpoint_digest=checkpoint_digest,
            origin_revision=checkpoint.runtime_revision + 1,
            source_closure=source_closure,
        ),
    )
    prior = partition.read_runtime_row(
        connection, table="runtime_checkpoints", match=(("checkpoint_id", checkpoint_id),),
    )
    if prior is not None and prior["record_json"] != archive.model_dump_json():
        raise RuntimeCheckpointError("integrity_error: divergent task archive identity")
    if prior is None:
        partition.upsert_runtime_row(
            connection,
            table="runtime_checkpoints",
            keys=("checkpoint_id",),
            values=(checkpoint_id,),
            record_json=archive.model_dump_json(),
            index_columns=("task_id",),
            index_values=(task.task_id,),
        )
    return archive, root


class RuntimeCheckpointManifest(BaseModel):
    """Canonical manifest of one checkpoint's members."""

    format_version: Literal[1, 2] = 1
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
    if manifest.format_version == 2:
        return canonical_runtime_digest((CHECKPOINT_SIGNATURE_PURPOSE, manifest.model_dump(mode="json")))
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


def _checkpoint_member_digest(
    tasks: tuple[TaskRecord, ...],
    runs: tuple[SolverRunRecord, ...],
    overlays: tuple[RuntimeOverlayVersion, ...],
    justifications: tuple[SolverJustificationRecord, ...],
) -> str:
    return canonical_runtime_digest((
        "memorii.runtime-checkpoint-members.v2",
        tuple(tuple(record.model_dump_json().encode("utf-8") for record in records)
              for records in (tasks, runs, overlays, justifications)),
    ))


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
    import uuid

    if connection is None:
        with repository.partition.transaction(write=False) as snapshot:
            return create_runtime_checkpoint(
                repository, signer_key_id=signer_key_id, sign=sign, checkpoint_id=checkpoint_id,
                now=now, connection=snapshot,
            )
    rows = connection.execute("SELECT record_json FROM runtime_tasks ORDER BY task_id").fetchall()
    tasks = tuple(TaskRecord.model_validate_json(row[0]) for row in rows)
    solver_runs = tuple(sorted(
        (run for task in tasks for run in repository.list_solver_runs_in(connection, task.task_id)),
        key=lambda run: run.solver_id,
    ))
    overlays = tuple(sorted(
        (overlay for run in solver_runs for overlay in repository.list_overlays_in(connection, run.solver_id)),
        key=lambda overlay: overlay.version_id,
    ))
    justifications = tuple(sorted(
        (item for run in solver_runs for item in repository.list_justifications_in(connection, run.solver_id)),
        key=lambda item: item.justification_id,
    ))
    revision = repository.read_runtime_revision_in(connection)
    if revision < 1:
        raise RuntimeCheckpointError(
            "a checkpoint requires at least one committed runtime revision"
        )
    manifest = RuntimeCheckpointManifest(
        format_version=2,
        repository_id="default",
        runtime_revision=revision,
        task_count=len(tasks),
        solver_run_count=len(solver_runs),
        overlay_count=len(overlays),
        justification_count=len(justifications),
        member_digest=_checkpoint_member_digest(tasks, solver_runs, overlays, justifications),
    )
    digest = compute_checkpoint_manifest_digest(manifest)
    signature = sign(CHECKPOINT_SIGNATURE_PURPOSE, digest)  # type: ignore[call-arg]
    return RuntimeCheckpoint(
        checkpoint_id=checkpoint_id or ("checkpoint:" + uuid.uuid4().hex[:16]),
        manifest=manifest,
        created_at=now or datetime.now(UTC),
        signer_key_id=signer_key_id,
        signature=signature,
        tasks=tasks, solver_runs=solver_runs, overlays=overlays, justifications=justifications,
    )


def verify_runtime_checkpoint(
    checkpoint: RuntimeCheckpoint,
    *,
    verify: object,
) -> None:
    """Fail closed on signature, purpose or manifest mismatch."""
    if checkpoint.manifest.format_version != 2:
        raise RuntimeCheckpointError("integrity_error: checkpoint has no authenticated member content")
    if checkpoint.manifest.member_digest != _checkpoint_member_digest(
        checkpoint.tasks, checkpoint.solver_runs, checkpoint.overlays, checkpoint.justifications,
    ):
        raise RuntimeCheckpointError("integrity_error: checkpoint member content differs from manifest")
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
    revoked_view: RevokedIdentityServingGate | None = None,
) -> HarnessResumeEnvelope:
    """Restore one consistent view; never rerun or auto-complete actions."""
    moment = now or datetime.now(UTC)
    with repository.partition.transaction(write=False) as connection:
        task = repository.get_task_in(connection, task_id)
        if task is None:
            raise RuntimeCheckpointError(f"not_found: task {task_id} does not exist")
        revision = repository.read_runtime_revision_in(connection)
        runs = repository.list_solver_runs_in(connection, task_id)
        overlays = tuple(
            overlay for run in runs for overlay in repository.list_overlays_in(connection, run.solver_id)
        )
        justifications = tuple(
            item for run in runs for item in repository.list_justifications_in(connection, run.solver_id)
        )
        pending_actions = tuple(
            attempt.action_id for attempt in repository.list_action_attempts_in(connection, task_id)
            if attempt.status in ("dispatched", "outcome_unknown")
        )
        revalidation: list[str] = []
        for run in runs:
            for _, node_id, content in repository.list_solver_nodes_in(connection, run.solver_id):
                if not isinstance(content, AssumptionContent):
                    continue
                expired = content.valid_to is not None and content.valid_to < moment
                premature = content.valid_from is not None and content.valid_from > moment
                if expired or premature:
                    revalidation.append(f"{node_id}:{'expired' if expired else 'not_yet_valid'}")
    # Revocation revalidation: a justification whose evidence was revoked
    # can no longer sponsor a served conclusion; it lists for revalidation
    # exactly like an expired assumption.
    if revoked_view is not None:
        for justification in justifications:
            if revoked_view.is_revoked_justification(justification.justification_id):
                revalidation.append(
                    f"{justification.justification_id}:revoked_evidence"
                )
    if checkpoint is not None and checkpoint.manifest.runtime_revision > revision:
        raise RuntimeCheckpointError(
            "integrity_error: checkpoint revision exceeds current state"
        )
    status: Literal["ready", "revalidation_required", "reconcile_required"] = "ready"
    if pending_actions:
        status = "reconcile_required"
    if revalidation:
        status = "revalidation_required"
    return HarnessResumeEnvelope(
        task_id=task_id,
        runtime_revision=revision,
        checkpoint_id=None if checkpoint is None else checkpoint.checkpoint_id,
        status=status,
        task=task,
        solver_runs=runs,
        overlays=overlays,
        justifications=justifications,
        pending_actions=pending_actions,
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
