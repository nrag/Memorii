"""Runtime state repository: typed durable views over the shared partition.

Every write goes through the publication transaction supplied by the
administration owner — the repository never mutates durable state on its
own. Reads take one partition snapshot. Solver node content crosses the
persistence boundary only through the closed content union; generic
dictionaries are rejected.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from memorii.core.persistence.runtime_api import RuntimeOutboxDelivery

import json as re
import sqlite3
from collections.abc import Callable
from typing import TypeVar

from pydantic import BaseModel, TypeAdapter

from memorii.core.persistence.runtime_contracts import (
    ActionAttemptRecord,
    RuntimeCommandReceipt,
    RuntimeOverlayVersion,
    SolverJustificationRecord,
    SolverNodeContent,
    SolverRunRecord,
    TaskRecord,
)
from memorii.core.storage_administration.service import (
    StorageAdministrationService,
)
from memorii.stores.sqlite.partition import PartitionDataRepository

_T = TypeVar("_T", bound=BaseModel)
_content_adapter: TypeAdapter[SolverNodeContent] = TypeAdapter(SolverNodeContent)


class RuntimeStateError(RuntimeError):
    """Runtime state operation refused; the detail carries the reason."""


class RuntimeStateRepository:
    """Runtime-owned durable view of one application-data partition."""

    def __init__(self, partition: PartitionDataRepository) -> None:
        self._partition = partition

    @property
    def partition(self) -> PartitionDataRepository:
        return self._partition

    # --- reads ---------------------------------------------------------

    def runtime_revision(self) -> int:
        with self._partition.transaction(write=False) as connection:
            return self._partition.read_runtime_revision(connection)

    def get_task(self, task_id: str) -> TaskRecord | None:
        with self._partition.transaction(write=False) as connection:
            row = self._partition.read_runtime_row(
                connection,
                table="runtime_tasks",
                match=(("task_id", task_id),),
            )
        return None if row is None else TaskRecord.model_validate_json(row["record_json"])

    def list_tasks(self) -> tuple[TaskRecord, ...]:
        return self._list("runtime_tasks", TaskRecord)

    def get_solver_run(self, solver_id: str) -> SolverRunRecord | None:
        with self._partition.transaction(write=False) as connection:
            row = self._partition.read_runtime_row(
                connection,
                table="runtime_solver_runs",
                match=(("solver_id", solver_id),),
            )
        return (
            None if row is None else SolverRunRecord.model_validate_json(row["record_json"])
        )

    def list_solver_runs(self, task_id: str) -> tuple[SolverRunRecord, ...]:
        return self._list(
            "runtime_solver_runs", SolverRunRecord, match=(("task_id", task_id),)
        )

    def get_justification(self, justification_id: str) -> SolverJustificationRecord | None:
        with self._partition.transaction(write=False) as connection:
            row = self._partition.read_runtime_row(
                connection,
                table="runtime_justifications",
                match=(("justification_id", justification_id),),
            )
        return (
            None
            if row is None
            else SolverJustificationRecord.model_validate_json(row["record_json"])
        )

    def list_justifications(self, solver_id: str) -> tuple[SolverJustificationRecord, ...]:
        return self._list(
            "runtime_justifications",
            SolverJustificationRecord,
            match=(("solver_id", solver_id),),
        )

    def get_overlay(self, version_id: str) -> RuntimeOverlayVersion | None:
        with self._partition.transaction(write=False) as connection:
            row = self._partition.read_runtime_row(
                connection,
                table="runtime_overlay_versions",
                match=(("version_id", version_id),),
            )
        return (
            None if row is None else RuntimeOverlayVersion.model_validate_json(row["record_json"])
        )

    def list_overlays(self, solver_id: str) -> tuple[RuntimeOverlayVersion, ...]:
        return self._list(
            "runtime_overlay_versions",
            RuntimeOverlayVersion,
            match=(("solver_id", solver_id),),
        )

    def get_action_attempt(self, action_id: str) -> ActionAttemptRecord | None:
        with self._partition.transaction(write=False) as connection:
            row = self._partition.read_runtime_row(
                connection,
                table="runtime_action_attempts",
                match=(("action_id", action_id),),
            )
        return (
            None
            if row is None
            else ActionAttemptRecord.model_validate_json(row["record_json"])
        )

    def list_action_attempts(self, task_id: str) -> tuple[ActionAttemptRecord, ...]:
        return self._list(
            "runtime_action_attempts",
            ActionAttemptRecord,
            match=(("task_id", task_id),),
        )

    def get_command_receipt(
        self, client_namespace: str, operation_id: str
    ) -> RuntimeCommandReceipt | None:
        with self._partition.transaction(write=False) as connection:
            row = self._partition.read_runtime_row(
                connection,
                table="runtime_command_receipts",
                match=(
                    ("client_namespace", client_namespace),
                    ("operation_id", operation_id),
                ),
            )
        return (
            None
            if row is None
            else RuntimeCommandReceipt.model_validate_json(row["record_json"])
        )

    def list_solver_nodes_in(
        self, connection: sqlite3.Connection, solver_id: str
    ) -> tuple[tuple[str, str, object], ...]:
        """(solver_id, node_id, validated content) for one solver run."""
        import json as _json

        rows = connection.execute(
            "SELECT solver_id, node_id, record_json FROM runtime_solver_nodes"
            " WHERE solver_id = ?",
            (solver_id,),
        ).fetchall()
        result = []
        for row in rows:
            payload = _json.loads(row[2])
            result.append(
                (
                    str(row[0]),
                    str(row[1]),
                    _content_adapter.validate_python(payload["content"]),
                )
            )
        return tuple(result)

    def read_solver_node_content(self, solver_id: str, node_id: str) -> object | None:
        with self._partition.transaction(write=False) as connection:
            row = self._partition.read_runtime_row(
                connection,
                table="runtime_solver_nodes",
                match=(("solver_id", solver_id), ("node_id", node_id)),
            )
        if row is None:
            return None
        import json

        payload = json.loads(row["record_json"])
        return _content_adapter.validate_python(payload["content"])

    def get_task_in(self, connection: sqlite3.Connection, task_id: str) -> TaskRecord | None:
        row = self._partition.read_runtime_row(
            connection, table="runtime_tasks", match=(("task_id", task_id),)
        )
        return None if row is None else TaskRecord.model_validate_json(row["record_json"])

    def get_command_receipt_in(
        self,
        connection: sqlite3.Connection,
        client_namespace: str,
        operation_id: str,
    ) -> RuntimeCommandReceipt | None:
        row = self._partition.read_runtime_row(
            connection,
            table="runtime_command_receipts",
            match=(
                ("client_namespace", client_namespace),
                ("operation_id", operation_id),
            ),
        )
        return (
            None
            if row is None
            else RuntimeCommandReceipt.model_validate_json(row["record_json"])
        )

    def list_solver_runs_in(
        self, connection: sqlite3.Connection, task_id: str
    ) -> tuple[SolverRunRecord, ...]:
        rows = self._partition.read_runtime_rows(
            connection, table="runtime_solver_runs", match=(("task_id", task_id),)
        )
        return tuple(
            SolverRunRecord.model_validate_json(row["record_json"]) for row in rows
        )

    def list_overlays_in(
        self, connection: sqlite3.Connection, solver_id: str
    ) -> tuple[RuntimeOverlayVersion, ...]:
        rows = self._partition.read_runtime_rows(
            connection, table="runtime_overlay_versions", match=(("solver_id", solver_id),)
        )
        return tuple(
            RuntimeOverlayVersion.model_validate_json(row["record_json"]) for row in rows
        )

    def list_justifications_in(
        self, connection: sqlite3.Connection, solver_id: str
    ) -> tuple[SolverJustificationRecord, ...]:
        rows = self._partition.read_runtime_rows(
            connection,
            table="runtime_justifications",
            match=(("solver_id", solver_id),),
        )
        return tuple(
            SolverJustificationRecord.model_validate_json(row["record_json"])
            for row in rows
        )

    def list_action_attempts_in(
        self, connection: sqlite3.Connection, task_id: str
    ) -> tuple[ActionAttemptRecord, ...]:
        rows = self._partition.read_runtime_rows(
            connection,
            table="runtime_action_attempts",
            match=(("task_id", task_id),),
        )
        return tuple(
            ActionAttemptRecord.model_validate_json(row["record_json"]) for row in rows
        )

    def read_runtime_revision_in(self, connection: sqlite3.Connection) -> int:
        return self._partition.read_runtime_revision(connection)

    # --- writes (inside a coordinator-owned publication transaction) ----

    def apply_task(
        self, connection: sqlite3.Connection, task: TaskRecord
    ) -> None:
        self._partition.upsert_runtime_row(
            connection,
            table="runtime_tasks",
            keys=("task_id",),
            values=(task.task_id,),
            record_json=task.model_dump_json(),
        )

    def apply_solver_run(
        self, connection: sqlite3.Connection, run: SolverRunRecord
    ) -> None:
        self._partition.upsert_runtime_row(
            connection,
            table="runtime_solver_runs",
            keys=("solver_id",),
            values=(run.solver_id,),
            record_json=run.model_dump_json(),
            index_columns=("task_id",),
            index_values=(run.task_id,),
        )

    def apply_solver_node(
        self,
        connection: sqlite3.Connection,
        *,
        solver_id: str,
        node_id: str,
        content: object,
        metadata_json: str,
    ) -> None:
        import json

        # Validate at the boundary: generic dictionaries never cross into
        # durable state, and unknown kinds fail closed here.
        validated = _content_adapter.validate_python(content)
        encoded = _content_adapter.dump_python(validated, mode="json")
        record = json.dumps({"content": encoded, "metadata": json.loads(metadata_json)})
        self._partition.upsert_runtime_row(
            connection,
            table="runtime_solver_nodes",
            keys=("solver_id", "node_id"),
            values=(solver_id, node_id),
            record_json=record,
        )

    def apply_execution_node(
        self,
        connection: sqlite3.Connection,
        *,
        task_id: str,
        node_id: str,
        node_json: str,
    ) -> None:
        self._partition.upsert_runtime_row(
            connection,
            table="runtime_execution_nodes",
            keys=("task_id", "node_id"),
            values=(task_id, node_id),
            record_json=node_json,
        )

    def apply_execution_edge(
        self,
        connection: sqlite3.Connection,
        *,
        task_id: str,
        edge_id: str,
        edge_json: str,
    ) -> None:
        self._partition.upsert_runtime_row(
            connection,
            table="runtime_execution_edges",
            keys=("task_id", "edge_id"),
            values=(task_id, edge_id),
            record_json=edge_json,
        )

    def apply_justification(
        self, connection: sqlite3.Connection, justification: SolverJustificationRecord
    ) -> None:
        self._partition.upsert_runtime_row(
            connection,
            table="runtime_justifications",
            keys=("justification_id",),
            values=(justification.justification_id,),
            record_json=justification.model_dump_json(),
            index_columns=("solver_id",),
            index_values=(justification.solver_id,),
        )

    def apply_overlay(
        self, connection: sqlite3.Connection, overlay: RuntimeOverlayVersion
    ) -> None:
        self._partition.upsert_runtime_row(
            connection,
            table="runtime_overlay_versions",
            keys=("version_id",),
            values=(overlay.version_id,),
            record_json=overlay.model_dump_json(),
            index_columns=("solver_id",),
            index_values=(overlay.solver_id,),
        )

    def apply_action_attempt(
        self, connection: sqlite3.Connection, attempt: ActionAttemptRecord
    ) -> None:
        self._partition.upsert_runtime_row(
            connection,
            table="runtime_action_attempts",
            keys=("action_id",),
            values=(attempt.action_id,),
            record_json=attempt.model_dump_json(),
            index_columns=("task_id", "recommendation_id", "recommendation_revision"),
            index_values=(
                attempt.task_id,
                attempt.recommendation_id,
                attempt.recommendation_revision,
            ),
        )

    def apply_checkpoint_receipt(
        self,
        connection: sqlite3.Connection,
        *,
        task_id: str,
        checkpoint_id: str,
        checkpoint_digest: str,
    ) -> None:
        self._partition.upsert_runtime_row(
            connection,
            table="runtime_checkpoints",
            keys=("checkpoint_id",),
            values=(checkpoint_id,),
            record_json=re.dumps(
                {
                    "checkpoint_id": checkpoint_id,
                    "task_id": task_id,
                    "checkpoint_digest": checkpoint_digest,
                },
                sort_keys=True,
            ),
            index_columns=("task_id",),
            index_values=(task_id,),
        )

    def apply_outbox_row(
        self,
        connection: sqlite3.Connection,
        delivery: RuntimeOutboxDelivery,
    ) -> None:
        self._partition.upsert_runtime_row(
            connection,
            table="runtime_outbox_deliveries",
            keys=("delivery_id",),
            values=(delivery.delivery_id,),
            record_json=delivery.model_dump_json(),
        )

    def get_outbox_delivery(
        self, connection: sqlite3.Connection, delivery_id: str
    ) -> RuntimeOutboxDelivery | None:
        from memorii.core.persistence.runtime_api import RuntimeOutboxDelivery

        rows = self._partition.read_runtime_rows(
            connection, table="runtime_outbox_deliveries",
            match=(("delivery_id", delivery_id),),
        )
        if not rows:
            return None
        return RuntimeOutboxDelivery.model_validate_json(str(rows[0]["record_json"]))

    def list_outbox_deliveries(
        self, connection: sqlite3.Connection
    ) -> tuple[RuntimeOutboxDelivery, ...]:
        from memorii.core.persistence.runtime_api import RuntimeOutboxDelivery

        rows = self._partition.read_runtime_rows(
            connection, table="runtime_outbox_deliveries"
        )
        entries = tuple(
            RuntimeOutboxDelivery.model_validate_json(str(row["record_json"]))
            for row in rows
        )
        # Drainable surface: only pending rows, in primary-key order.
        return tuple(entry for entry in entries if entry.status == "pending")

    def apply_command_receipt(
        self, connection: sqlite3.Connection, receipt: RuntimeCommandReceipt
    ) -> None:
        self._partition.upsert_runtime_row(
            connection,
            table="runtime_command_receipts",
            keys=("client_namespace", "operation_id"),
            values=(receipt.client_namespace, receipt.operation_id),
            record_json=receipt.model_dump_json(),
        )

    def _list(
        self,
        table: str,
        model: type[_T],
        match: tuple[tuple[str, object], ...] = (),
    ) -> tuple[_T, ...]:
        with self._partition.transaction(write=False) as connection:
            rows = self._partition.read_runtime_rows(
                connection, table=table, match=match
            )
        return tuple(model.model_validate_json(row["record_json"]) for row in rows)


def publish_runtime_change(
    administration: StorageAdministrationService,
    apply: Callable[[sqlite3.Connection, RuntimeStateRepository], None],
    *,
    operation_binding: str = "runtime_change",
) -> int:
    """Apply one runtime change and publish it atomically.

    ``apply`` receives the open publication transaction and the repository
    view and performs the typed runtime writes. The publisher bumps the
    durable runtime revision, and the signed vector's runtime position
    advances as a batch position; memory-plane heads are carried unchanged.
    """
    import uuid

    from memorii.core.persistence.contracts import (
        BatchPosition,
        GenesisPosition,
        PartitionRevisionVector,
        RuntimeMaterializationManifest,
        RuntimePublicationIntent,
        RuntimePublicationState,
        empty_pointer_set_digest,
    )
    from memorii.core.storage_administration.service import (
        InstallationIntegrityError,
        InstallationQuarantinedError,
        StorageAdministrationError,
    )

    try:
        state = administration._require_operational()
    except StorageAdministrationError as exc:
        raise RuntimeStateError(str(exc)) from exc
    if administration._writer_enrollment is not None:
        administration._writer_enrollment.require_enrolled(operation_binding)
    if state.mode == "read_only" and operation_binding != "migrate":
        raise InstallationQuarantinedError(
            "installation is read_only; runtime publication is denied"
        )
    repository = RuntimeStateRepository(administration.partition())
    with administration._publication_fence():
        # Mode re-checked under the fence: a writer that passed the entry
        # check before an owner flipped read_only cannot commit across the
        # barrier (mirrors publish_memory_plane_batch).
        fenced_state = administration._require_operational()
        if fenced_state.mode == "read_only" and operation_binding != "migrate":
            raise InstallationQuarantinedError(
                "installation is read_only; data publication is denied"
            )
        resolution = administration.resolve_pending_publication()
        if resolution.disposition == "quarantined":
            raise InstallationQuarantinedError("pending publication quarantined")
        finalized = administration._control.read_publication_state(
            administration._repository_id()
        )
        if finalized is None:
            raise RuntimeStateError("installation is not initialized")
        administration._verified_snapshot_locked(state)
        partition = administration.partition()
        with partition.manual_write_transaction() as handle:
            connection = handle.connection
            pre_state = partition.read_publication_row(connection)
            if pre_state is None or str(pre_state["tuple_digest"]) != (
                finalized.payload_digest()
            ):
                raise InstallationIntegrityError(
                    "partition pre-state does not match the finalized control tuple"
                )
            runtime_revision = partition.bump_runtime_revision(connection)
            apply(connection, repository)
            manifest_entries = partition.compute_materialization_manifest(connection)
            manifest = RuntimeMaterializationManifest(catalogs=manifest_entries)
            memory_write, memory_data = partition.read_revision_state(connection)
            prior_ordinal = int(pre_state["ordinal"])
            vector = PartitionRevisionVector(
                partition_ordinal=prior_ordinal + 1,
                runtime_position=BatchPosition(
                    sequence=runtime_revision, digest=manifest.digest()
                ),
                memory_write_revision=memory_write,
                memory_data_revision=memory_data,
                semantic_position=GenesisPosition(),
                ontology_pointer_digest=empty_pointer_set_digest(),
            )
            unsigned = RuntimePublicationState(
                installation_id=state.installation_id,
                repository_id=administration._repository_id(),
                data_generation_id=finalized.data_generation_id,
                position=BatchPosition(
                    sequence=prior_ordinal + 1, digest=manifest.digest()
                ),
                manifest_digest=manifest.digest(),
                trust_registry_digest=finalized.trust_registry_digest,
                eligibility_epoch=state.eligibility_epoch,
                vector=vector,
                signature="0" * 64,
            )
            candidate = administration._sign_state(unsigned)
            partition.write_publication_row(
                connection,
                ordinal=prior_ordinal + 1,
                position_kind="batch",
                position_sequence=prior_ordinal + 1,
                position_digest=manifest.digest(),
                tuple_digest=candidate.payload_digest(),
                generation_id=finalized.data_generation_id,
                vector_json=candidate.vector.model_dump_json(),
                manifest_digest=candidate.manifest_digest,
            )
            intent = RuntimePublicationIntent(
                intent_id=uuid.uuid4().hex,
                repository_id=administration._repository_id(),
                expected_old_discriminator=finalized.payload_digest(),
                candidate_state=candidate,
                operation_binding=operation_binding,
                authority_epoch=state.eligibility_epoch,
                fence_token=prior_ordinal + 1,
            )
            administration._control.write_intent(
                intent,
                administration._journal_entry(
                    operation="publication_prepared",
                    before_digest=finalized.payload_digest(),
                    after_digest=candidate.payload_digest(),
                ),
            )
            handle.commit()
        administration._finalize_publication(candidate)
        administration._control.write_intent(
            intent.model_copy(update={"phase": "finalized"}),
            administration._journal_entry(
                operation="publication_finalized",
                before_digest=finalized.payload_digest(),
                after_digest=candidate.payload_digest(),
            ),
        )
        administration._verified_tuples[candidate.payload_digest()] = True
        return runtime_revision
