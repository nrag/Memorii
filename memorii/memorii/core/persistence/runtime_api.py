"""Persistent runtime API: durable commands, attempts, outbox dispatch.

The dispatch owner implements the transaction protocol of the design at
the command level: duplicate commands with the same digest return the
prior receipt; divergent reuse fails; attempts carry lease, fence and
budget (no timestamp is a fencing token); takeover by a higher ordinal
moves the displaced attempt to terminal needs_reconciliation with cause
superseded_by_fence while keeping its staged bytes; external actions
reserve one dispatch per recommendation identity independent of the
caller's action id; the outbox requires a target receipt before
delivered and never reinterprets an unknown target result.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

if TYPE_CHECKING:
    from memorii.core.harness_state.write_authority import ResolvedHostCommandAuthority

from memorii.core.consolidation.consolidator import Consolidator
from memorii.core.consolidation.runtime_outputs import (
    MAX_CONSOLIDATION_SOURCE_REFERENCES,
    ArchivePackage,
    ConsolidationOmission,
    ConsolidationOrigin,
    ConsolidationResult,
    SourceReferences,
    UnresolvedFollowUpSummary,
    build_consolidation_result,
)
from memorii.core.persistence.contracts import (
    InstallationControlState,
    RuntimePublicationState,
    canonical_json_digest,
)
from memorii.core.persistence.managed_delivery import DeliveryTransitionError
from memorii.core.persistence.runtime_checkpoint import (
    RuntimeCheckpointError,
    TaskLifecycleArchive,
    read_bounded_task_root,
    stage_task_lifecycle_archive,
)
from memorii.core.persistence.runtime_contracts import (
    ActionAttemptRecord,
    BeliefUpdateProposal,
    NodeMergeProposal,
    NodeReopenProposal,
    OperationOrigin,
    OperationOriginCoordinate,
    RuntimeCommandReceipt,
    RuntimeCommandRequest,
    RuntimeSourceAdmissionReceipt,
    SolverRunRecord,
    StatusUpdateProposal,
    TaskRecord,
)
from memorii.core.persistence.runtime_repository import (
    RuntimeStateRepository,
    publish_runtime_change,
)
from memorii.core.storage_administration.revoked_identity_view import RefreshingRevokedIdentityView
from memorii.core.storage_administration.service import (
    StorageAdministrationService,
)
from memorii.domain.enums import ExecutionNodeStatus, ExecutionNodeType, SolverNodeStatus
from memorii.domain.execution_graph.nodes import ExecutionNode

_HEX_64 = r"^[0-9a-f]{64}$"
_MANAGED_NAMESPACE_PREFIX = "origin:"
AttemptStage = Literal[
    "prepared",
    "awaiting_model",
    "candidate_persisted",
    "validated",
    "committed",
    "rejected",
    "needs_reconciliation",
]
OutboxStatus = Literal[
    "pending", "delivering", "delivered", "rejected", "needs_reconciliation"
]
_OutboxKind = Literal["work_projection", "writeback_candidate"]


class RuntimeCommandError(RuntimeError):
    """Command dispatch refused; the detail carries the reason."""


class RuntimeOperationAttempt(BaseModel):
    """Recovery owner of one command receipt (durable, versioned)."""

    receipt_id: str = Field(min_length=1)
    attempt_ordinal: int = Field(ge=1)
    request_digest: str = Field(pattern=_HEX_64)
    base_task_revision: int = Field(ge=0)
    model_binding: str
    policy_digest: str = Field(pattern=_HEX_64)
    stage: AttemptStage = "prepared"
    lease_owner: str | None = None
    fence_token: int = Field(ge=1)
    lease_expires_at: datetime | None = None
    invocation_count: int = Field(default=0, ge=0)
    spend_reserved: float = Field(default=0.0, ge=0.0)
    staged_candidate_digest: str | None = Field(default=None, pattern=_HEX_64)
    terminal_error: str | None = None
    terminal_cause: Literal[None, "superseded_by_fence", "budget_exhausted", "stale_base", "cancelled"] = None
    version: int = Field(default=1, ge=1)

    model_config = ConfigDict(extra="forbid", frozen=True)


class RuntimeOutboxDelivery(BaseModel):
    """One durable cross-domain delivery with target idempotency."""

    delivery_id: str = Field(min_length=1)
    origin_operation_id: str = Field(min_length=1)
    kind: _OutboxKind
    target_protocol: str = Field(min_length=1)
    payload_digest: str = Field(pattern=_HEX_64)
    required_source_scopes: tuple[str, ...] = ()
    status: OutboxStatus = "pending"
    lease_owner: str | None = None
    fence_token: int = Field(ge=1)
    lease_expires_at: datetime | None = None
    attempt_count: int = Field(default=0, ge=0)
    next_retry_at: datetime | None = None
    target_result: str | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def delivered_requires_result(self) -> RuntimeOutboxDelivery:
        if self.status == "delivered" and not self.target_result:
            raise ValueError("delivered requires a target receipt reference")
        return self


class LegacyUnresolvedDelivery(BaseModel):
    """Quarantine a digest-only delivery while retaining its exact historical bytes."""

    record_type: Literal["legacy_unresolved_delivery"] = "legacy_unresolved_delivery"
    delivery_id: str = Field(min_length=1)
    status: Literal["needs_reconciliation"] = "needs_reconciliation"
    original_record_json: str
    original_record_digest: str = Field(pattern=_HEX_64)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def original_matches_delivery(self) -> LegacyUnresolvedDelivery:
        original = RuntimeOutboxDelivery.model_validate_json(self.original_record_json)
        if (
            original.delivery_id != self.delivery_id
            or hashlib.sha256(self.original_record_json.encode("utf-8")).hexdigest() != self.original_record_digest
        ):
            raise ValueError("quarantined legacy delivery differs from its retained record")
        return self


def convert_legacy_outbox_record(delivery_id: str, record_json: str) -> LegacyUnresolvedDelivery | None:
    """Convert one digest-only record, leaving the known managed formats to their owners."""
    payload = json.loads(record_json)
    if not isinstance(payload, dict):
        raise ValueError("outbox row must contain an object")
    record_type = payload.get("record_type")
    if record_type in ("managed_work_projection", "managed_writeback_candidate"):
        return None
    if record_type == "legacy_unresolved_delivery":
        legacy = LegacyUnresolvedDelivery.model_validate(payload)
    else:
        legacy = LegacyUnresolvedDelivery(
            delivery_id=delivery_id,
            original_record_json=record_json,
            original_record_digest=hashlib.sha256(record_json.encode("utf-8")).hexdigest(),
        )
    if legacy.delivery_id != delivery_id:
        raise ValueError("legacy outbox row disagrees with its storage key")
    return legacy


def require_no_legacy_delivery(delivery_id: str, record_json: str) -> None:
    """Give managed target owners a closed diagnostic for a selected legacy row."""
    try:
        legacy = convert_legacy_outbox_record(delivery_id, record_json)
    except ValueError as exc:
        raise DeliveryTransitionError("integrity_error: invalid outbox delivery record") from exc
    if legacy is not None:
        raise DeliveryTransitionError("needs_reconciliation: legacy digest-only delivery requires owner review")


def command_request_digest(request: RuntimeCommandRequest) -> str:
    import json

    payload = json.dumps(
        request.model_dump(mode="json", exclude={"expected_revision"}),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class RuntimeCommandService:
    """Durable dispatch of versioned runtime commands over one partition."""

    def __init__(
        self,
        administration: StorageAdministrationService,
        *,
        client_namespace: str = "default-client",
        max_model_invocations: int = 3,
    ) -> None:
        if client_namespace.startswith(_MANAGED_NAMESPACE_PREFIX):
            raise RuntimeCommandError("denied: client namespace is reserved for managed receipts")
        self._administration = administration
        self._client_namespace = client_namespace
        self._max_model_invocations = max_model_invocations
        self._repository = RuntimeStateRepository(administration.partition())

    @property
    def repository(self) -> RuntimeStateRepository:
        return self._repository

    def dispatch(self, request: RuntimeCommandRequest) -> RuntimeCommandReceipt:
        """Idempotent command dispatch with durable receipt and attempt."""
        digest = command_request_digest(request)
        existing = self._repository.get_command_receipt(
            self._client_namespace, request.operation_id
        )
        if existing is not None:
            if existing.request_digest != digest:
                raise RuntimeCommandError(
                    "conflict: operation id reused with a divergent request"
                )
            return existing
        publish_runtime_change(
            self._administration,
            lambda connection, repository: self._apply_command(
                connection, repository, request, digest
            ),
            operation_binding=f"runtime_command:{request.kind}",
            checkpoint_requested=request.kind == "checkpoint_task",
        )
        receipt = self._repository.get_command_receipt(
            self._client_namespace, request.operation_id
        )
        assert receipt is not None
        return receipt

    def _apply_command(
        self,
        connection: object,
        repository: RuntimeStateRepository,
        request: RuntimeCommandRequest,
        digest: str,
        *,
        operation_origin: OperationOrigin | None = None,
        source_admission: RuntimeSourceAdmissionReceipt | None = None,
    ) -> None:
        assert isinstance(connection, sqlite3.Connection)
        lookup_namespace = (
            self._client_namespace
            if operation_origin is None
            else operation_origin_namespace(operation_origin.coordinate)
        )
        # Idempotency re-check under the publication fence: a racing duplicate
        # dispatch must not re-apply the effect.
        existing = repository.get_command_receipt_in(
            connection, lookup_namespace, request.operation_id
        )
        if existing is not None:
            if existing.request_digest != digest:
                raise RuntimeCommandError(
                    "conflict: operation id reused with a divergent request"
                )
            return
        revision = repository.read_runtime_revision_in(connection)
        result = None
        if operation_origin is not None and request.kind in {"pause_task", "complete_task"}:
            result = self._apply_managed_lifecycle(connection, repository, request, operation_origin.coordinate)
        elif operation_origin is not None and request.kind == "resume_task":
            self._apply_managed_resume(connection, repository, request, operation_origin.coordinate)
        elif operation_origin is not None and request.kind == "record_observation":
            task = repository.get_task_in(connection, request.task_id or "")
            if (
                source_admission is None or task is None or source_admission.task_id != task.task_id
                or task.principal != operation_origin.coordinate.principal
                or source_admission.provider_source_digest != request.source_digest
            ):
                raise RuntimeCommandError("denied: verified provider admission is unavailable")
            if task.lifecycle != "active" or task.version != request.expected_revision:
                raise RuntimeCommandError("conflict: observation task or revision is no longer active")
            observed = repository.task_observation_source_keys_in(connection, task.task_id)
            key = source_admission.source_id, source_admission.source_record_digest
            if key not in observed and len(observed) >= MAX_CONSOLIDATION_SOURCE_REFERENCES:
                raise RuntimeCommandError("resource_exhausted: task observation source limit reached")
            repository.apply_task(connection, task.model_copy(update={"version": task.version + 1}))
        else:
            self._apply_command_effect(connection, repository, request, operation_origin=operation_origin)
        receipt = RuntimeCommandReceipt(
            operation_id=request.operation_id,
            client_namespace=self._client_namespace,
            request_digest=digest,
            status="committed",
            base_revision=revision - 1,
            current_revision=revision,
            consolidation_result_id=None if result is None else result.result_id,
            result_digest=(
                source_admission.digest() if source_admission is not None
                else None if result is None else hashlib.sha256(result.canonical_bytes()).hexdigest()
            ),
            operation_origin=(
                None if operation_origin is None else operation_origin.coordinate
            ),
            origin_proof_digest=(
                None if operation_origin is None else operation_origin_proof_digest(operation_origin)
            ),
            source_admission=source_admission,
        )
        repository.apply_command_receipt(connection, receipt, lookup_namespace=lookup_namespace)
        attempt = RuntimeOperationAttempt(
            receipt_id=(
                request.operation_id
                if operation_origin is None
                else canonical_json_digest(
                    {"namespace": lookup_namespace, "operation_id": request.operation_id}
                )
            ),
            attempt_ordinal=1,
            request_digest=digest,
            base_task_revision=revision,
            model_binding="no-model",
            policy_digest=hashlib.sha256(b"runtime-command-default-policy").hexdigest(),
            stage="committed",
            lease_owner=self._client_namespace,
            fence_token=revision,
            lease_expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
        self._administration.partition().upsert_runtime_row(
            connection,
            table="runtime_operation_attempts",
            keys=("receipt_id", "attempt_ordinal"),
            values=(attempt.receipt_id, attempt.attempt_ordinal),
            record_json=attempt.model_dump_json(),
        )

    def _apply_managed_lifecycle(
        self,
        connection: sqlite3.Connection,
        repository: RuntimeStateRepository,
        request: RuntimeCommandRequest,
        coordinate: OperationOriginCoordinate,
    ) -> ConsolidationResult:
        task = repository.get_task_in(connection, request.task_id or "")
        revoked = RefreshingRevokedIdentityView(self._administration.installation_root / "control")
        if task is None or task.principal != coordinate.principal or revoked.is_revoked_task(task.task_id):
            raise RuntimeCommandError("denied: task lifecycle authority is unavailable")
        if request.expected_revision != task.version:
            raise RuntimeCommandError("conflict: task state moved past the expected revision")
        if task.lifecycle != "active":
            raise RuntimeCommandError("conflict: managed lifecycle transition requires an active task")
        if request.kind == "complete_task":
            evidence = request.completion_evidence
            assert evidence is not None
            if (
                evidence.acceptance_results or evidence.required_artifact_refs
                or evidence.unresolved_blocker_acknowledged or task.acceptance_criteria
            ):
                raise RuntimeCommandError("unsupported_configuration: completion requires an evidence owner")
        try:
            source_closure = self._lifecycle_sources(connection, repository, task, revoked)
            archive, root = stage_task_lifecycle_archive(
                repository, connection, task=task,
                installation_id=coordinate.installation_id,
                partition_id=coordinate.repository_id,
                generation_id=coordinate.generation_id,
                signer_key_id=self._administration._signer_key_id,
                sign=lambda purpose, message: self._administration._signing.sign(
                    self._administration._signer_key_id, purpose, message,
                ),
                source_closure=source_closure,
            )
            if request.kind == "complete_task" and (
                root.acceptance_criteria
                or root.status in {ExecutionNodeStatus.BLOCKED, ExecutionNodeStatus.FAILED}
            ):
                raise RuntimeCommandError("unsupported_configuration: root completion is not validated")
            episode = Consolidator().from_task_lifecycle(
                completed=request.kind == "complete_task", execution_node_id=root.id, source_refs=source_closure,
            )
            result = build_consolidation_result(
                ConsolidationOrigin(
                    installation_id=coordinate.installation_id,
                    partition_id=coordinate.repository_id,
                    operation_generation=coordinate.generation_id,
                    task_id=task.task_id,
                    client_namespace=coordinate.client_namespace,
                    operation_id=coordinate.operation_id,
                    request_digest=coordinate.request_digest,
                ),
                origin_revision=archive.manifest.origin_revision,
                outputs=(
                    *((episode,) if episode is not None else ()),
                    UnresolvedFollowUpSummary(), ArchivePackage(reference=archive.reference()),
                ),
                omissions=(
                    *((ConsolidationOmission(kind="episodic_summary", reason="insufficient_evidence"),)
                      if episode is None else ()),
                    ConsolidationOmission(kind="skill_candidate", reason="insufficient_evidence"),
                    ConsolidationOmission(kind="semantic_candidate", reason="insufficient_evidence"),
                    ConsolidationOmission(kind="user_candidate", reason="insufficient_evidence"),
                ),
            )
        except (RuntimeCheckpointError, ValidationError) as exc:
            raise RuntimeCommandError(str(exc)) from exc
        completed = request.kind == "complete_task"
        repository.apply_task(connection, task.model_copy(update={
            "lifecycle": "completed" if completed else "paused", "version": task.version + 1,
        }))
        repository.apply_execution_node(
            connection,
            task_id=task.task_id,
            node_id=root.id,
            node_json=root.model_copy(update={
                "status": ExecutionNodeStatus.DONE if completed else ExecutionNodeStatus.WAITING,
                "updated_at": datetime.now(UTC),
            }).model_dump_json(),
        )
        repository.apply_consolidation_result(connection, result)
        return result

    @staticmethod
    def _lifecycle_sources(
        connection: sqlite3.Connection, repository: RuntimeStateRepository, task: TaskRecord,
        revoked: RefreshingRevokedIdentityView,
    ) -> SourceReferences:
        from memorii.core.provider.runtime_source_release import list_runtime_released_sources

        current = list_runtime_released_sources(
            connection, repository, task_id=task.task_id, principal=task.principal,
            now=datetime.now(UTC), revoked=revoked,
        )
        required = repository.task_observation_source_keys_in(connection, task.task_id)
        eligible = {(ref.source_id, ref.source_digest) for ref in current}
        if not required.issubset(eligible):
            raise RuntimeCheckpointError("denied: admitted source archive closure is unavailable")
        return tuple(ref for ref in current if (ref.source_id, ref.source_digest) in required)

    def _apply_managed_resume(
        self,
        connection: sqlite3.Connection,
        repository: RuntimeStateRepository,
        request: RuntimeCommandRequest,
        coordinate: OperationOriginCoordinate,
    ) -> None:
        task = repository.get_task_in(connection, request.task_id or "")
        revoked = RefreshingRevokedIdentityView(self._administration.installation_root / "control")
        if task is None or task.principal != coordinate.principal or revoked.is_revoked_task(task.task_id):
            raise RuntimeCommandError("denied: task resume authority is unavailable")
        if task.version != request.expected_revision:
            raise RuntimeCommandError("conflict: task state moved past the expected revision")
        if task.lifecycle == "active":
            return
        if task.lifecycle != "paused":
            raise RuntimeCommandError("conflict: task cannot be resumed")
        partition = repository.partition
        try:
            current_sources = self._lifecycle_sources(connection, repository, task, revoked)
            root = read_bounded_task_root(repository, connection, task, verified_sources=current_sources)
            validated_archives: list[TaskLifecycleArchive] = []
            for result in repository.list_consolidation_results_in(connection):
                origin = result.origin
                if (
                    origin.installation_id != coordinate.installation_id
                    or origin.partition_id != coordinate.repository_id
                    or origin.operation_generation != coordinate.generation_id
                    or origin.task_id != task.task_id
                ):
                    continue
                for output in result.outputs:
                    if not isinstance(output.payload, ArchivePackage):
                        continue
                    ref = output.payload.reference
                    row = partition.read_runtime_row(
                        connection, table="runtime_checkpoints", match=(("checkpoint_id", ref.checkpoint_id),),
                    )
                    if row is None:
                        raise RuntimeCheckpointError("integrity_error: recorded task archive is missing")
                    archive = TaskLifecycleArchive.model_validate_json(row["record_json"])
                    if archive.checkpoint.task.version + 1 != task.version:
                        continue
                    if any(ref not in current_sources for ref in archive.checkpoint.source_closure):
                        raise RuntimeCheckpointError("denied: archived source authority is unavailable")
                    if (
                        ref != archive.reference()
                        or archive.checkpoint.generation_id != coordinate.generation_id
                        or archive.checkpoint.task.lifecycle != "active"
                        or archive.checkpoint.task.model_copy(
                            update={"lifecycle": "paused", "version": task.version},
                        ) != task
                        or archive.checkpoint.root_node.model_copy(
                            update={"status": ExecutionNodeStatus.WAITING, "updated_at": root.updated_at},
                        ) != root
                    ):
                        raise RuntimeCheckpointError("integrity_error: task archive differs from the paused state")
                    archive.verify_signature(self._administration._signing.verify)
                    origin_namespace = managed_receipt_namespace(
                        installation_id=coordinate.installation_id, repository_id=coordinate.repository_id,
                        generation_id=coordinate.generation_id, principal=coordinate.principal,
                        client_namespace=origin.client_namespace,
                    )
                    receipt = repository.get_command_receipt_in(connection, origin_namespace, origin.operation_id)
                    expected_origin = coordinate.model_copy(update={
                        "client_namespace": origin.client_namespace,
                        "operation_id": origin.operation_id,
                        "request_digest": origin.request_digest,
                    })
                    if (
                        receipt is None or receipt.status != "committed"
                        or receipt.operation_origin != expected_origin
                        or receipt.consolidation_result_id != result.result_id
                        or receipt.request_digest != origin.request_digest
                        or receipt.current_revision != result.origin_revision
                        or receipt.result_digest != hashlib.sha256(result.canonical_bytes()).hexdigest()
                    ):
                        raise RuntimeCheckpointError("integrity_error: task archive lacks its exact pause receipt")
                    validated_archives.append(archive)
            if len(validated_archives) != 1:
                raise RuntimeCheckpointError("needs_reconciliation: paused task requires one verified archive")
        except (RuntimeCheckpointError, ValidationError) as exc:
            raise RuntimeCommandError(str(exc)) from exc
        archive_root = validated_archives[0].checkpoint.root_node
        repository.apply_task(connection, task.model_copy(update={"lifecycle": "active", "version": task.version + 1}))
        repository.apply_execution_node(
            connection, task_id=task.task_id, node_id=root.id,
            node_json=archive_root.model_copy(update={"updated_at": datetime.now(UTC)}).model_dump_json(),
        )

    def _apply_command_effect(
        self,
        connection: object,
        repository: RuntimeStateRepository,
        request: RuntimeCommandRequest,
        *,
        operation_origin: OperationOrigin | None = None,
    ) -> None:
        import sqlite3 as _sqlite3

        assert isinstance(connection, _sqlite3.Connection)
        if request.kind == "start_task":
            assert request.goal is not None
            task_id = "task:" + uuid.uuid5(
                uuid.NAMESPACE_URL,
                (
                    f"{self._client_namespace}:{request.operation_id}"
                    if operation_origin is None
                    else canonical_json_digest(operation_origin.coordinate.model_dump(mode="json"))
                ),
            ).hex[:12]
            created_at = datetime.now(UTC)
            principal = self._client_namespace if operation_origin is None else operation_origin.coordinate.principal
            root_node_id = "exec:" + task_id
            repository.apply_task(
                connection,
                TaskRecord(
                    task_id=task_id,
                    principal=principal,
                    goal=request.goal,
                    created_at=created_at,
                    root_execution_node_id=root_node_id,
                ),
            )
            if operation_origin is not None:
                root = ExecutionNode(
                    id=root_node_id,
                    type=ExecutionNodeType.MISSION,
                    title=request.goal,
                    description=request.goal,
                    status=ExecutionNodeStatus.READY,
                    owner=principal,
                    created_at=created_at,
                    updated_at=created_at,
                )
                repository.apply_execution_node(
                    connection, task_id=task_id, node_id=root.id, node_json=root.model_dump_json(),
                )
            return
        task = repository.get_task_in(connection, request.task_id or "")
        if task is None:
            raise RuntimeCommandError(
                f"not_found: task {request.task_id} does not exist"
            )
        if task.lifecycle in ("completed", "aborted") and request.kind not in (
            "resume_task",
            "checkpoint_task",
        ):
            raise RuntimeCommandError(
                f"conflict: task is {task.lifecycle}; mutation commands are closed"
            )
        if (
            request.kind in ("complete_task", "pause_task", "abort_task")
            and request.expected_revision is not None
            and task.version > int(request.expected_revision)
        ):
            raise RuntimeCommandError(
                "conflict: task state moved past the expected revision"
            )
        if request.kind == "complete_task":
            assert request.completion_evidence is not None
            if not request.completion_evidence.unresolved_blocker_acknowledged:
                for attempt in repository.list_action_attempts_in(
                    connection, task.task_id
                ):
                    if attempt.status in ("dispatched", "outcome_unknown"):
                        raise RuntimeCommandError(
                            "conflict: unresolved dispatched actions block completion"
                        )
            repository.apply_task(
                connection,
                task.model_copy(
                    update={"lifecycle": "completed", "version": task.version + 1}
                ),
            )
        elif request.kind == "pause_task":
            repository.apply_task(
                connection,
                task.model_copy(
                    update={"lifecycle": "paused", "version": task.version + 1}
                ),
            )
        elif request.kind == "abort_task":
            repository.apply_task(
                connection,
                task.model_copy(
                    update={"lifecycle": "aborted", "version": task.version + 1}
                ),
            )
        elif request.kind == "resume_task":
            if task.lifecycle == "paused":
                repository.apply_task(
                    connection,
                    task.model_copy(
                        update={"lifecycle": "active", "version": task.version + 1}
                    ),
                )
            # Resuming an active task is an idempotent continuation: the
            # receipt is the durable effect.
        elif request.kind == "record_action_dispatch":
            # Durable event journal + the outbox carrier: every dispatch
            # creates a pending delivery bound to its operation, so the
            # target transport can consume it with retry and idempotency.
            digest = command_request_digest(request)
            repository.apply_outbox_row(
                connection,
                RuntimeOutboxDelivery(
                    delivery_id="outbox:" + request.operation_id,
                    origin_operation_id=request.operation_id,
                    kind="work_projection",
                    target_protocol="memorii.runtime-intake/v1",
                    payload_digest=digest,
                    fence_token=1,
                ),
            )
        elif request.kind == "record_action_result":
            # Durable event journal: the result's receipt is its effect.
            # Target delivery is the outbox worker's concern (the classic
            # transactional-outbox relay), never an inline side effect.
            pass
        elif request.kind == "record_observation":
            # Durable event journal: the atomic receipt records that the host
            # event command executed. The observation's content effects live
            # with the memory-plane semantic wiring, not the runtime tables.
            pass
        elif request.kind == "propose_state_change":
            assert request.proposal is not None
            _apply_proposal(repository, connection, request.proposal, managed=operation_origin is not None)
        elif request.kind == "checkpoint_task":
            from datetime import UTC as _UTC
            from datetime import datetime as _datetime

            from memorii.core.persistence.runtime_checkpoint import (
                create_runtime_checkpoint as _checkpoint,
            )

            checkpoint = _checkpoint(
                repository,
                signer_key_id=self._administration._signer_key_id,
                sign=lambda purpose, message: self._administration._signing.sign(
                    self._administration._signer_key_id, purpose, message
                ),
                now=_datetime.now(_UTC),
                connection=connection,
            )
            repository.apply_checkpoint_receipt(
                connection,
                task_id=task.task_id,
                checkpoint_id=checkpoint.checkpoint_id,
                checkpoint_digest=checkpoint.signature,
            )
        elif request.kind == "replan_task":
            import uuid as _uuid

            replan_run = SolverRunRecord(
                solver_id="solver:replan:" + _uuid.uuid4().hex[:12],
                task_id=task.task_id,
                parent_execution_node_id=task.root_execution_node_id,
                category="replan",
                lifecycle="active",
                created_by=self._client_namespace,
            )
            repository.apply_solver_run(connection, replan_run)
        else:
            # Fail closed: kinds whose durable effects are not implemented at
            # this slice never commit a receipt claiming success.
            raise RuntimeCommandError(
                f"unsupported_configuration: command kind {request.kind} has no"
                " implemented durable effect at this slice"
            )



@dataclass(frozen=True)
class ResolvedRuntimeCommandAuthority:
    """Identity of a current, request-scoped authorization from the host owner."""

    principal: str
    client_namespace: str
    projection_grant: ResolvedHostCommandAuthority | None = None


CommandAuthorityPurpose = Literal["prepare", "dispatch", "release", "historical_release"]
RuntimeCommandAuthorizer = Callable[
    [
        RuntimeCommandRequest,
        CommandAuthorityPurpose,
        OperationOriginCoordinate | None,
        InstallationControlState,
        RuntimePublicationState,
    ],
    ResolvedRuntimeCommandAuthority | None,
]
RuntimeObservationSource = Callable[
    [sqlite3.Connection, RuntimeStateRepository, RuntimeCommandRequest, OperationOriginCoordinate, RuntimePublicationState],
    RuntimeSourceAdmissionReceipt,
]


def operation_origin_namespace(coordinate: OperationOriginCoordinate) -> str:
    """Generation-scope the existing receipt index without rewriting legacy receipts."""
    return managed_receipt_namespace(
        installation_id=coordinate.installation_id,
        repository_id=coordinate.repository_id,
        generation_id=coordinate.generation_id,
        principal=coordinate.principal,
        client_namespace=coordinate.client_namespace,
    )


def managed_receipt_namespace(
    *, installation_id: str, repository_id: str, generation_id: str, principal: str, client_namespace: str
) -> str:
    """Derive the receipt index for a caller whose scope is already resolved."""
    return _MANAGED_NAMESPACE_PREFIX + canonical_json_digest(
        {
            "installation_id": installation_id,
            "repository_id": repository_id,
            "generation_id": generation_id,
            "principal": principal,
            "client_namespace": client_namespace,
        },
    )


def operation_origin_proof_digest(proof: OperationOrigin) -> str:
    return proof.proof_digest()


class _ManagedReceiptAppeared(RuntimeError):
    """A duplicate arrived between the preliminary read and publication."""


class ManagedRuntimeCommandService:
    """Embedded command boundary for a host-owned current-authority resolver.

    The installed owner injects a local resolver bound to the authenticated
    caller. The verified state and finalized tuple are supplied under the
    installation barrier. Resolve the credential and grant in that context
    without reacquiring the fence. Historical release also requires restore
    reconciliation. The origin proof does not replace that check.
    """

    def __init__(
        self,
        administration: StorageAdministrationService,
        *,
        authorize: RuntimeCommandAuthorizer,
        observation_source: RuntimeObservationSource | None = None,
    ) -> None:
        self._administration = administration
        self._authorize = authorize
        self._observation_source = observation_source

    def prepare(self, request: RuntimeCommandRequest) -> OperationOrigin:
        """Authenticate new intent explicitly, without publishing any effect."""
        self._require_supported(request)
        with self._administration.verified_operation_context() as (state, finalized):
            authority = self._require_authority(request, "prepare", None, state, finalized)
            self._require_active(state)
            self._require_managed_schema()
            coordinate = OperationOriginCoordinate(
                installation_id=finalized.installation_id,
                repository_id=finalized.repository_id,
                generation_id=finalized.data_generation_id,
                principal=authority.principal,
                client_namespace=authority.client_namespace,
                operation_id=request.operation_id,
                request_digest=request.managed_intent_digest(),
            )
            if request.kind in ("record_observation", "propose_state_change"):
                repository = RuntimeStateRepository(self._administration.partition())
                with repository.partition.transaction(write=False) as connection:
                    if request.kind == "record_observation":
                        self._resolve_observation(connection, repository, request, coordinate, finalized)
                    else:
                        self._validate_status_proposal(connection, repository, request, coordinate.principal)
            return self._administration.sign_operation_origin(coordinate)

    def dispatch(
        self, request: RuntimeCommandRequest, *, operation_origin: OperationOrigin
    ) -> RuntimeCommandReceipt:
        """Apply an authenticated prepared intent or release its verified receipt."""
        existing = self._read_receipt(request, operation_origin)
        if existing is not None:
            return existing
        self._require_supported(request)
        coordinate = operation_origin.coordinate
        service = RuntimeCommandService(
            self._administration, client_namespace=coordinate.client_namespace
        )
        projection_grant: ResolvedHostCommandAuthority | None = None
        authorized_publication: RuntimePublicationState | None = None

        def validate(state: InstallationControlState, finalized: RuntimePublicationState) -> None:
            nonlocal projection_grant, authorized_publication
            self._require_active(state)
            authority = self._require_authority(request, "dispatch", coordinate, state, finalized)
            self._validate_proof(request, operation_origin, authority, finalized)
            self._require_managed_schema()
            if coordinate.generation_id != finalized.data_generation_id:
                raise RuntimeCommandError("needs_reconciliation: operation generation changed")
            if service.repository.get_command_receipt(
                operation_origin_namespace(coordinate), coordinate.operation_id
            ) is not None:
                raise _ManagedReceiptAppeared
            projection_grant = authority.projection_grant
            authorized_publication = finalized

        def apply(connection: sqlite3.Connection, repository: RuntimeStateRepository) -> None:
            source = None
            if request.kind == "record_observation":
                assert authorized_publication is not None
                source = self._resolve_observation(connection, repository, request, coordinate, authorized_publication)
            elif request.kind == "propose_state_change":
                self._validate_status_proposal(connection, repository, request, coordinate.principal)
            service._apply_command(
                connection, repository, request, coordinate.request_digest,
                operation_origin=operation_origin, source_admission=source,
            )
            if projection_grant is not None:
                from memorii.core.work_state.runtime_projection import stage_work_projection

                stage_work_projection(
                    connection, repository, command=request, origin=operation_origin,
                    grant=projection_grant, runtime_revision=repository.read_runtime_revision_in(connection),
                )

        # If a duplicate raced with publication, release its receipt through
        # the same checks as an ordinary retry.
        with suppress(_ManagedReceiptAppeared):
            publish_runtime_change(
                self._administration,
                apply,
                operation_binding=f"runtime_command:{request.kind}",
                validate_authority=validate,
                checkpoint_requested=request.kind == "checkpoint_task",
            )
        receipt = self._read_receipt(request, operation_origin)
        if receipt is None:
            raise RuntimeCommandError("integrity_error: committed operation receipt is missing")
        return receipt

    def validate_intake(
        self, request: RuntimeCommandRequest, *, operation_origin: OperationOrigin
    ) -> RuntimeCommandReceipt | None:
        """Check a prepared intent for intake without executing a runtime command."""
        return self._read_receipt(request, operation_origin, for_intake=True)

    def _read_receipt(
        self,
        request: RuntimeCommandRequest,
        proof: OperationOrigin,
        *,
        for_intake: bool = False,
    ) -> RuntimeCommandReceipt | None:
        if not isinstance(proof, OperationOrigin):
            raise RuntimeCommandError("denied: authenticated operation origin is required")
        coordinate = proof.coordinate
        with self._administration.verified_operation_context() as (state, finalized):
            if state.mode == "bypass":
                raise RuntimeCommandError("unavailable: installation is in bypass mode")
            historical = coordinate.generation_id != finalized.data_generation_id
            authority = self._require_authority(request, "release", coordinate, state, finalized)
            self._validate_proof(request, proof, authority, finalized)
            self._require_managed_schema()
            repository = RuntimeStateRepository(self._administration.partition())
            receipt = repository.get_command_receipt(
                operation_origin_namespace(coordinate), coordinate.operation_id
            )
            if receipt is not None and (
                receipt.operation_origin != coordinate
                or receipt.origin_proof_digest != operation_origin_proof_digest(proof)
            ):
                raise RuntimeCommandError("conflict: operation id reused with divergent intent")
            if historical:
                if receipt is None:
                    raise RuntimeCommandError("needs_reconciliation: historical receipt is absent")
                released = self._authorize(request, "historical_release", coordinate, state, finalized)
                if released != authority:
                    raise RuntimeCommandError("needs_reconciliation: historical receipt is held")
            if request.kind == "record_observation":
                with repository.partition.transaction(write=False) as connection:
                    source = self._resolve_observation(connection, repository, request, coordinate, finalized)
                if receipt is not None and source != receipt.source_admission:
                    raise RuntimeCommandError("integrity_error: observation receipt does not match its provider admission")
            if receipt is not None and request.task_id is not None:
                revoked = RefreshingRevokedIdentityView(self._administration.installation_root / "control")
                task = repository.get_task(request.task_id)
                if task is None or task.principal != authority.principal or revoked.is_revoked_task(task.task_id):
                    raise RuntimeCommandError("denied: task lifecycle authority is unavailable")
                if receipt.consolidation_result_id is not None:
                    result = repository.get_consolidation_result(receipt.consolidation_result_id)
                    if (
                        result is None
                        or result.origin.task_id != task.task_id
                        or result.origin_revision != receipt.current_revision
                        or result.origin.operation_generation != coordinate.generation_id
                        or result.origin.operation_id != coordinate.operation_id
                        or result.origin.request_digest != coordinate.request_digest
                        or hashlib.sha256(result.canonical_bytes()).hexdigest() != receipt.result_digest
                    ):
                        raise RuntimeCommandError("integrity_error: consolidation receipt does not bind its sealed result")
                    self._verify_lifecycle_archive_release(repository, result, task, revoked)
            if for_intake and receipt is None:
                self._require_supported(request)
                self._require_active(state)
                if self._require_authority(request, "dispatch", coordinate, state, finalized) != authority:
                    raise RuntimeCommandError("denied: mismatched intake authority")
                if request.kind == "propose_state_change":
                    with repository.partition.transaction(write=False) as connection:
                        self._validate_status_proposal(connection, repository, request, coordinate.principal)
            return receipt

    def _validate_status_proposal(
        self,
        connection: sqlite3.Connection,
        repository: RuntimeStateRepository,
        request: RuntimeCommandRequest,
        principal: str,
    ) -> None:
        proposal = request.proposal
        assert isinstance(proposal, StatusUpdateProposal)
        task = repository.get_task_in(connection, request.task_id or "")
        revoked = RefreshingRevokedIdentityView(self._administration.installation_root / "control")
        if task is None or task.principal != principal or revoked.is_revoked_task(task.task_id):
            raise RuntimeCommandError("denied: solver status authority is unavailable")
        if task.lifecycle != "active" or task.version != request.expected_revision:
            raise RuntimeCommandError("conflict: solver status requires an active task at the expected revision")
        partition = repository.partition
        row = partition.read_runtime_row(
            connection, table="runtime_solver_runs", match=(("solver_id", proposal.solver_id),),
        )
        if row is None:
            raise RuntimeCommandError("denied: solver status authority is unavailable")
        run = SolverRunRecord.model_validate_json(row["record_json"])
        if (
            run.solver_id != proposal.solver_id or run.task_id != task.task_id or run.lifecycle != "active"
            or task.active_solver_by_execution_node.get(run.parent_execution_node_id) != run.solver_id
            or partition.read_runtime_row(
                connection, table="runtime_solver_nodes",
                match=(("solver_id", run.solver_id), ("node_id", proposal.node_id)),
            ) is None
        ):
            raise RuntimeCommandError("denied: solver status authority is unavailable")

    @staticmethod
    def _verify_lifecycle_archive_release(
        repository: RuntimeStateRepository, result: ConsolidationResult, task: TaskRecord,
        revoked: RefreshingRevokedIdentityView,
    ) -> None:
        from memorii.core.provider.runtime_source_release import get_current_source_release

        partition = repository.partition
        with partition.transaction(write=False) as connection:
            for output in result.outputs:
                if not isinstance(output.payload, ArchivePackage):
                    continue
                reference = output.payload.reference
                row = partition.read_runtime_row(
                    connection, table="runtime_checkpoints", match=(("checkpoint_id", reference.checkpoint_id),),
                )
                if row is None:
                    raise RuntimeCommandError("integrity_error: sealed archive is missing")
                try:
                    archive = TaskLifecycleArchive.model_validate_json(row["record_json"])
                except ValidationError as exc:
                    raise RuntimeCommandError("integrity_error: sealed archive is malformed") from exc
                if archive.reference() != reference:
                    raise RuntimeCommandError("integrity_error: sealed archive does not match the result")
                now = datetime.now(UTC)
                if any(get_current_source_release(
                    connection, repository, task_id=task.task_id, principal=task.principal,
                    source_ref=source, now=now, revoked=revoked,
                ) is None for source in archive.checkpoint.source_closure):
                    raise RuntimeCommandError("denied: archived source authority is unavailable")

    def _resolve_observation(
        self, connection: sqlite3.Connection, repository: RuntimeStateRepository,
        request: RuntimeCommandRequest, coordinate: OperationOriginCoordinate, finalized: RuntimePublicationState,
    ) -> RuntimeSourceAdmissionReceipt:
        resolver = self._observation_source
        if resolver is None:
            raise RuntimeCommandError("unsupported_configuration: managed provider source owner is unavailable")
        if not repository.partition.supports_runtime_history(connection):
            raise RuntimeCommandError("unsupported_configuration: source-backed observations require signed runtime history")
        task = repository.get_task_in(connection, request.task_id or "")
        revoked = RefreshingRevokedIdentityView(self._administration.installation_root / "control")
        if task is None or task.principal != coordinate.principal or revoked.is_revoked_task(task.task_id):
            raise RuntimeCommandError("denied: observation task authority is unavailable")
        source = resolver(connection, repository, request, coordinate, finalized)
        if (
            source.task_id != task.task_id or source.provider_source_digest != request.source_digest
            or source.source_write_revision > finalized.vector.memory_write_revision
            or revoked.is_revoked_source(source.source_id) or revoked.is_revoked_record(source.source_id)
        ):
            raise RuntimeCommandError("denied: verified provider admission is unavailable")
        return source

    def _require_managed_schema(self) -> None:
        partition = self._administration.partition()
        with partition.transaction(write=False) as connection:
            if not partition.supports_managed_runtime(connection):
                raise RuntimeCommandError("unsupported_configuration: managed runtime catalog upgrade required")

    def _require_authority(
        self,
        request: RuntimeCommandRequest,
        purpose: CommandAuthorityPurpose,
        coordinate: OperationOriginCoordinate | None,
        state: InstallationControlState,
        finalized: RuntimePublicationState,
    ) -> ResolvedRuntimeCommandAuthority:
        authority = self._authorize(request, purpose, coordinate, state, finalized)
        if (
            not isinstance(authority, ResolvedRuntimeCommandAuthority)
            or not 1 <= len(authority.principal) <= 512
            or not 1 <= len(authority.client_namespace) <= 512
            or authority.client_namespace.startswith(_MANAGED_NAMESPACE_PREFIX)
        ):
            raise RuntimeCommandError("denied: current command authority is required")
        return authority

    def _validate_proof(
        self,
        request: RuntimeCommandRequest,
        proof: OperationOrigin,
        authority: ResolvedRuntimeCommandAuthority,
        finalized: RuntimePublicationState,
    ) -> None:
        coordinate = proof.coordinate
        if (
            coordinate.installation_id != finalized.installation_id
            or coordinate.repository_id != finalized.repository_id
            or coordinate.principal != authority.principal
            or coordinate.client_namespace != authority.client_namespace
            or coordinate.operation_id != request.operation_id
            or coordinate.request_digest != request.managed_intent_digest()
            or not self._administration.verify_operation_origin(proof)
        ):
            raise RuntimeCommandError("denied: operation origin does not authenticate this intent")

    @staticmethod
    def _require_active(state: InstallationControlState) -> None:
        if state.mode != "active":
            raise RuntimeCommandError("unavailable: installation is not active")

    def _require_supported(self, request: RuntimeCommandRequest) -> None:
        if len(request.operation_id) > 512 or "\0" in request.operation_id:
            raise RuntimeCommandError("invalid_request: operation identity is invalid")
        if request.kind == "record_observation" and self._observation_source is not None:
            return
        if request.kind == "propose_state_change":
            proposal = request.proposal
            if not isinstance(proposal, StatusUpdateProposal) or proposal.evidence:
                raise RuntimeCommandError("unsupported_configuration: managed status proposals require source-free input")
            if not proposal.reason.strip():
                raise RuntimeCommandError("invalid_request: a solver status proposal requires a reason")
            try:
                SolverNodeStatus(proposal.status)
            except ValueError as exc:
                raise RuntimeCommandError("invalid_request: unknown solver node status") from exc
            return
        if request.kind not in {"start_task", "resume_task", "pause_task", "complete_task", "checkpoint_task"}:
            raise RuntimeCommandError(
                "unsupported_configuration: managed result and mutation owners are not configured"
            )


def _apply_proposal(
    repository: RuntimeStateRepository,
    connection: sqlite3.Connection,
    proposal: BeliefUpdateProposal
    | StatusUpdateProposal
    | NodeReopenProposal
    | NodeMergeProposal,
    *,
    managed: bool = False,
) -> None:
    """Apply one typed solver proposal as durable overlay state.

    Every member lands the same closed shape: a justification recording the
    change (bound to its evidence or reason), and a new overlay version
    whose bindings express the state transition. Candidate state stays
    distinct from committed state: the overlay is written uncommitted;
    commitment is a separate owner action.
    """
    import hashlib as _hashlib
    import uuid as _uuid
    from datetime import UTC as _UTC
    from datetime import datetime as _datetime

    from memorii.core.persistence.runtime_contracts import (
        OverlayJustificationBinding,
        RuntimeOverlayVersion,
        SolverJustificationRecord,
    )

    kind = proposal.kind
    solver_id = proposal.solver_id
    moment = _datetime.now(_UTC)
    stamp = _uuid.uuid4().hex[:12]

    if isinstance(proposal, BeliefUpdateProposal):
        node_id = proposal.node_id
        justification = SolverJustificationRecord(
            justification_id=proposal.justification_id,
            solver_id=solver_id,
            conclusion=f"belief_update:{proposal.epistemic_status}",
            strength=proposal.strength,
            active=True,
        )
        binding = OverlayJustificationBinding(
            node_id=node_id, active_justification_ids=(proposal.justification_id,)
        )
    elif isinstance(proposal, StatusUpdateProposal):
        node_id = proposal.node_id
        justification = SolverJustificationRecord(
            justification_id=f"justification:status:{stamp}",
            solver_id=solver_id,
            conclusion=f"status_update:{proposal.status}:{proposal.reason}",
            source_refs=proposal.evidence,
            strength=1.0,
        )
        binding = OverlayJustificationBinding(
            node_id=node_id, active_justification_ids=(justification.justification_id,) if managed else (),
        )
    elif isinstance(proposal, NodeReopenProposal):
        node_id = proposal.node_id
        justification = SolverJustificationRecord(
            justification_id=f"justification:reopen:{stamp}",
            solver_id=solver_id,
            conclusion="node_reopen",
            strength=1.0,
        )
        binding = OverlayJustificationBinding(node_id=node_id, reopenable=True)
    elif isinstance(proposal, NodeMergeProposal):
        node_id = proposal.target_node_id
        justification = SolverJustificationRecord(
            justification_id=f"justification:merge:{stamp}",
            solver_id=solver_id,
            conclusion=f"node_merge:{proposal.source_node_id}->{proposal.target_node_id}",
            strength=1.0,
        )
        binding = OverlayJustificationBinding(node_id=node_id, frontier=True)
    else:
        raise RuntimeCommandError(
            f"unsupported_configuration: unknown proposal kind {kind}"
        )

    repository.apply_justification(connection, justification)
    version_id = "overlay:" + _hashlib.sha256(
        f"{solver_id}:{kind}:{stamp}".encode()
    ).hexdigest()[:16]
    repository.apply_overlay(
        connection,
        RuntimeOverlayVersion(
            version_id=version_id,
            solver_id=solver_id,
            node_bindings=(binding,),
            created_at=moment,
            committed=False,
        ),
    )


def apply_outbox_delivery(
    connection: sqlite3.Connection,
    repository: RuntimeStateRepository,
    delivery: RuntimeOutboxDelivery,
) -> None:
    """Persist one outbox delivery row (the manifest-covered catalog)."""
    repository.apply_outbox_row(connection, delivery)


def pending_outbox_deliveries(
    repository: RuntimeStateRepository,
    connection: sqlite3.Connection,
) -> tuple[RuntimeOutboxDelivery, ...]:
    """Drainable pending deliveries in primary-key order."""
    return repository.list_outbox_deliveries(connection)


def deliver_outbox(
    repository: RuntimeStateRepository,
    deliver: Callable[[RuntimeOutboxDelivery], str],
) -> tuple[RuntimeOutboxDelivery, ...]:
    """Deliver pending entries through the explicit legacy-v1 transport.

    ``deliver`` returns the target receipt reference; a raise aborts the
    batch with nothing marked delivered (fail-closed, retry-safe — the
    entries stay pending). Delivery is at-least-once per entry and
    idempotent by delivery_id at the row level.
    """
    delivered: list[RuntimeOutboxDelivery] = []
    with repository._partition.manual_write_transaction() as handle:
        connection = handle.connection
        if (
            repository.partition.read_publication_row(connection) is not None
            or repository.partition.supports_managed_runtime(connection)
        ):
            raise RuntimeCommandError("needs_reconciliation: legacy digest-only deliveries require owner review")
        for entry in repository.list_outbox_deliveries(connection):
            receipt = deliver(entry)
            updated = entry.model_copy(
                update={
                    "status": "delivered",
                    "target_result": receipt,
                    "attempt_count": entry.attempt_count + 1,
                }
            )
            repository.apply_outbox_row(connection, updated)
            delivered.append(updated)
        # A raising transport exits the block without this commit: the
        # transaction rolls back and every entry stays pending.
        handle.commit()
    return tuple(delivered)


def fence_takeover(
    displaced: RuntimeOperationAttempt, replacement_ordinal: int
) -> RuntimeOperationAttempt:
    """Terminal disposition for a lease-expired attempt overtaken by fence."""
    if replacement_ordinal <= displaced.attempt_ordinal:
        raise RuntimeCommandError(
            "takeover requires a strictly higher attempt ordinal"
        )
    return displaced.model_copy(
        update={
            "stage": "needs_reconciliation",
            "terminal_cause": "superseded_by_fence",
            "terminal_error": "displaced by fenced takeover",
            "lease_owner": None,
        }
    )


def reserve_dispatch(
    repository: RuntimeStateRepository,
    administration: StorageAdministrationService,
    *,
    task_id: str,
    recommendation_id: str,
    recommendation_revision: int,
    executor_binding: str,
) -> ActionAttemptRecord:
    """Validate-and-record one dispatch reservation for a recommendation.

    Two hosts using different action ids cannot double-execute one
    recommendation: the check runs inside the publication transaction under
    the fence, and the unique reservation is the (task, recommendation,
    revision) tuple.
    """
    from memorii.core.persistence.runtime_repository import (
        publish_runtime_change as _publish,
    )

    resolved: dict[str, ActionAttemptRecord] = {}

    def apply(connection: object, repo: RuntimeStateRepository) -> None:
        import sqlite3 as _sqlite3

        assert isinstance(connection, _sqlite3.Connection)
        for attempt in repo.list_action_attempts_in(connection, task_id):
            if (
                attempt.recommendation_id == recommendation_id
                and attempt.recommendation_revision == recommendation_revision
            ):
                if attempt.executor_binding != executor_binding:
                    raise RuntimeCommandError(
                        "conflict: recommendation dispatch already reserved"
                    )
                resolved["action"] = attempt
                return
        action = ActionAttemptRecord(
            action_id="action:" + uuid.uuid4().hex[:16],
            task_id=task_id,
            recommendation_id=recommendation_id,
            recommendation_revision=recommendation_revision,
            executor_binding=executor_binding,
            status="dispatched",
        )
        repo.apply_action_attempt(connection, action)
        resolved["action"] = action

    _publish(
        administration,
        apply,
        operation_binding="runtime_command:record_action_dispatch",
    )
    return resolved["action"]


__all__ = [
    "LegacyUnresolvedDelivery",
    "ManagedRuntimeCommandService",
    "ResolvedRuntimeCommandAuthority",
    "RuntimeCommandAuthorizer",
    "RuntimeCommandError",
    "RuntimeCommandService",
    "RuntimeOperationAttempt",
    "RuntimeOutboxDelivery",
    "command_request_digest",
    "convert_legacy_outbox_record",
    "fence_takeover",
    "reserve_dispatch",
]
