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
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.persistence.runtime_contracts import (
    ActionAttemptRecord,
    RuntimeCommandReceipt,
    RuntimeCommandRequest,
    TaskRecord,
)
from memorii.core.persistence.runtime_repository import (
    RuntimeStateRepository,
    publish_runtime_change,
)
from memorii.core.storage_administration.service import (
    StorageAdministrationService,
)

_HEX_64 = r"^[0-9a-f]{64}$"
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
        self._administration = administration
        self._client_namespace = client_namespace
        self._max_model_invocations = max_model_invocations
        self._repository = RuntimeStateRepository(administration.partition())

    @property
    def repository(self) -> RuntimeStateRepository:
        return self._repository

    def dispatch(self, request: RuntimeCommandRequest) -> object:
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
    ) -> None:
        import sqlite3 as _sqlite3

        assert isinstance(connection, _sqlite3.Connection)
        # Idempotency re-check under the publication fence: a racing duplicate
        # dispatch must not re-apply the effect.
        existing = repository.get_command_receipt_in(
            connection, self._client_namespace, request.operation_id
        )
        if existing is not None:
            if existing.request_digest != digest:
                raise RuntimeCommandError(
                    "conflict: operation id reused with a divergent request"
                )
            return
        revision = repository.read_runtime_revision_in(connection)
        receipt = RuntimeCommandReceipt(
            operation_id=request.operation_id,
            client_namespace=self._client_namespace,
            request_digest=digest,
            status="committed",
            base_revision=revision - 1,
            current_revision=revision,
        )
        repository.apply_command_receipt(connection, receipt)
        attempt = RuntimeOperationAttempt(
            receipt_id=request.operation_id,
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
        self._apply_command_effect(connection, repository, request)

    def _apply_command_effect(
        self,
        connection: object,
        repository: RuntimeStateRepository,
        request: RuntimeCommandRequest,
    ) -> None:
        import sqlite3 as _sqlite3

        assert isinstance(connection, _sqlite3.Connection)
        if request.kind == "start_task":
            assert request.goal is not None
            task_id = "task:" + uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"{self._client_namespace}:{request.operation_id}",
            ).hex[:12]
            repository.apply_task(
                connection,
                TaskRecord(
                    task_id=task_id,
                    principal=self._client_namespace,
                    goal=request.goal,
                    created_at=datetime.now(UTC),
                    root_execution_node_id="exec:" + task_id,
                ),
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
        else:
            # Fail closed: kinds whose durable effects are not implemented at
            # this slice never commit a receipt claiming success.
            raise RuntimeCommandError(
                f"unsupported_configuration: command kind {request.kind} has no"
                " implemented durable effect at this slice"
            )


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
    "RuntimeCommandError",
    "RuntimeCommandService",
    "RuntimeOperationAttempt",
    "RuntimeOutboxDelivery",
    "command_request_digest",
    "fence_takeover",
    "reserve_dispatch",
]
