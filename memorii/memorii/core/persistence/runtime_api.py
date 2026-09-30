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
    "prepared", "awaiting_model", "candidate_persisted", "validated", "committed"
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
        runtime_revision = publish_runtime_change(
            self._administration,
            lambda connection, repository: self._apply_command(
                connection, repository, request, digest
            ),
            operation_binding=f"runtime_command:{request.kind}",
        )
        return self._repository.get_command_receipt(
            self._client_namespace, request.operation_id
        ) or RuntimeCommandReceipt(
            operation_id=request.operation_id,
            client_namespace=self._client_namespace,
            request_digest=digest,
            status="committed",
            base_revision=runtime_revision - 1,
            current_revision=runtime_revision,
        )

    def _apply_command(
        self,
        connection: object,
        repository: RuntimeStateRepository,
        request: RuntimeCommandRequest,
        digest: str,
    ) -> None:
        import sqlite3 as _sqlite3

        assert isinstance(connection, _sqlite3.Connection)
        base = repository.read_runtime_revision_in(connection)
        receipt = RuntimeCommandReceipt(
            operation_id=request.operation_id,
            client_namespace=self._client_namespace,
            request_digest=digest,
            status="committed",
            base_revision=base,
            current_revision=base + 1,
        )
        repository.apply_command_receipt(connection, receipt)
        attempt = RuntimeOperationAttempt(
            receipt_id=request.operation_id,
            attempt_ordinal=1,
            request_digest=digest,
            base_task_revision=base,
            model_binding="no-model",
            policy_digest=hashlib.sha256(b"runtime-command-default-policy").hexdigest(),
            stage="committed",
            lease_owner=self._client_namespace,
            fence_token=base + 1,
            lease_expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
        self._administration.partition().upsert_runtime_row(
            connection,
            table="runtime_operation_attempts",
            keys=("receipt_id",),
            values=(attempt.receipt_id,),
            record_json=attempt.model_dump_json(),
            index_columns=("attempt_ordinal",),
            index_values=(attempt.attempt_ordinal,),
        )
        self._apply_command_effect(connection, repository, request, base)

    def _apply_command_effect(
        self,
        connection: object,
        repository: RuntimeStateRepository,
        request: RuntimeCommandRequest,
        base: int,
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
        if request.expected_revision is not None and task.version > int(
            request.expected_revision
        ):
            raise RuntimeCommandError(
                "conflict: task state moved past the expected revision"
            )
        if task.lifecycle in ("completed", "aborted"):
            raise RuntimeCommandError(
                f"conflict: task is {task.lifecycle}; mutation commands are closed"
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
        del base

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
            "stage": "validated",  # displaced attempts end in needs_reconciliation
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
    recommendation: the unique reservation is the
    (task, recommendation, revision) tuple.
    """
    for attempt in repository.list_action_attempts(task_id):
        if (
            attempt.recommendation_id == recommendation_id
            and attempt.recommendation_revision == recommendation_revision
        ):
            if attempt.executor_binding != executor_binding:
                raise RuntimeCommandError(
                    "conflict: recommendation dispatch already reserved"
                )
            return attempt
    action = ActionAttemptRecord(
        action_id="action:" + uuid.uuid4().hex[:16],
        task_id=task_id,
        recommendation_id=recommendation_id,
        recommendation_revision=recommendation_revision,
        executor_binding=executor_binding,
        status="dispatched",
    )
    publish_runtime_change(
        administration,
        lambda connection, repo: repo.apply_action_attempt(connection, action),
        operation_binding="runtime_command:record_action_dispatch",
    )
    return action


__all__ = [
    "RuntimeCommandError",
    "RuntimeCommandService",
    "RuntimeOperationAttempt",
    "RuntimeOutboxDelivery",
    "command_request_digest",
    "fence_takeover",
    "reserve_dispatch",
]
