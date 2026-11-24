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
    from memorii.core.persistence.managed_delivery import RuntimeTargetReceipt
    from memorii.core.persistence.runtime_api import RuntimeOutboxDelivery
    from memorii.core.work_state.runtime_projection import ManagedWorkProjectionDelivery

import json as re
import sqlite3
from collections.abc import Callable
from typing import TypeVar

from pydantic import BaseModel, TypeAdapter

from memorii.core.consolidation.runtime_outputs import ConsolidationResult
from memorii.core.persistence.contracts import InstallationControlState, RuntimePublicationState
from memorii.core.persistence.runtime_contracts import (
    ActionAttemptRecord,
    RuntimeCommandReceipt,
    RuntimeOverlayVersion,
    SolverJustificationRecord,
    SolverNodeContent,
    SolverRunRecord,
    TaskRecord,
)
from memorii.core.persistence.runtime_journal import append_runtime_changes
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

    def apply_consolidation_result(
        self, connection: sqlite3.Connection, result: ConsolidationResult,
    ) -> None:
        """Insert a sealed result in its origin publication transaction."""
        result = ConsolidationResult.model_validate(result)
        prior = self.get_consolidation_result_in(connection, result.result_id)
        if prior is not None:
            if prior.canonical_bytes() != result.canonical_bytes():
                raise RuntimeStateError("conflict: divergent consolidation result for origin")
            return
        self._partition.insert_consolidation_row(
            connection, result_id=result.result_id, record_json=result.model_dump_json(),
        )

    @staticmethod
    def _decode_consolidation_result(row: sqlite3.Row) -> ConsolidationResult:
        result = ConsolidationResult.model_validate_json(row["record_json"])
        if result.result_id != row["result_id"]:
            raise RuntimeStateError("integrity_error: consolidation catalog key mismatch")
        return result

    def get_consolidation_result_in(
        self, connection: sqlite3.Connection, result_id: str,
    ) -> ConsolidationResult | None:
        rows = self._partition.read_consolidation_rows(connection, result_id=result_id)
        return self._decode_consolidation_result(rows[0]) if rows else None

    def list_consolidation_results_in(
        self, connection: sqlite3.Connection,
    ) -> tuple[ConsolidationResult, ...]:
        return tuple(
            self._decode_consolidation_result(row)
            for row in self._partition.read_consolidation_rows(connection)
        )

    def get_consolidation_result(self, result_id: str) -> ConsolidationResult | None:
        """Internal owner read. The public API must grant-check and verify its snapshot."""
        with self._partition.transaction(write=False) as connection:
            return self.get_consolidation_result_in(connection, result_id)

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
        if _managed_outbox_type(str(rows[0]["record_json"])) is not None:
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
            if _managed_outbox_type(str(row["record_json"])) is None
        )
        # Drainable surface: only pending rows, in primary-key order.
        return tuple(entry for entry in entries if entry.status == "pending")

    def get_managed_work_projection_delivery(
        self, connection: sqlite3.Connection, delivery_id: str,
    ) -> ManagedWorkProjectionDelivery | None:
        from memorii.core.work_state.runtime_projection import ManagedWorkProjectionDelivery

        self._partition.require_delivery_catalogs(connection)
        row = self._partition.read_runtime_row(
            connection, table="runtime_outbox_deliveries", match=(("delivery_id", delivery_id),),
        )
        if row is None:
            return None
        record = str(row["record_json"])
        if _managed_outbox_type(record) != "managed_work_projection":
            raise RuntimeStateError("needs_reconciliation: outbox row has no managed projection payload")
        entry = ManagedWorkProjectionDelivery.model_validate_json(record)
        if entry.delivery.request.delivery_id != delivery_id:
            raise RuntimeStateError("integrity_error: projection delivery key mismatch")
        return entry

    def apply_managed_work_projection_delivery(
        self, connection: sqlite3.Connection, entry: ManagedWorkProjectionDelivery,
    ) -> None:
        delivery_id = entry.delivery.request.delivery_id
        existing = self.get_managed_work_projection_delivery(connection, delivery_id)
        if existing == entry:
            return
        if existing is None and (entry.delivery.version != 1 or entry.delivery.progress.status != "pending"):
            raise RuntimeStateError("conflict: new projection delivery must be pending at version one")
        if existing is not None and (
            existing.delivery.request != entry.delivery.request
            or existing.origin != entry.origin
            or existing.command != entry.command
            or existing.projection != entry.projection
            or existing.delivery.generation_id != entry.delivery.generation_id
            or existing.delivery.version + 1 != entry.delivery.version
        ):
            raise RuntimeStateError("conflict: divergent projection payload or version")
        self._partition.upsert_runtime_row(
            connection, table="runtime_outbox_deliveries",
            keys=("delivery_id",), values=(delivery_id,), record_json=entry.model_dump_json(),
        )

    def insert_work_projection_effect(
        self, connection: sqlite3.Connection, entry: ManagedWorkProjectionDelivery,
        receipt: RuntimeTargetReceipt,
    ) -> None:
        """Type-owned target effect and receipt inside the same signed transaction."""
        delivery_id = entry.delivery.request.delivery_id
        self._partition.insert_delivery_record(
            connection, catalog="runtime_work_projections",
            record_id=delivery_id, record_json=entry.projection.model_dump_json(),
        )
        self._partition.insert_delivery_record(
            connection, catalog="runtime_target_receipts",
            record_id=delivery_id, record_json=receipt.model_dump_json(),
        )

    def verify_work_projection_effect(
        self, connection: sqlite3.Connection, entry: ManagedWorkProjectionDelivery,
        receipt: RuntimeTargetReceipt,
    ) -> None:
        from memorii.core.persistence.managed_delivery import RuntimeTargetReceipt
        from memorii.core.work_state.runtime_projection import ManagedWorkProjection

        delivery_id = entry.delivery.request.delivery_id
        projection = self._partition.read_delivery_record(
            connection, catalog="runtime_work_projections", record_id=delivery_id,
        )
        target = self._partition.read_delivery_record(
            connection, catalog="runtime_target_receipts", record_id=delivery_id,
        )
        if (
            projection is None or target is None
            or ManagedWorkProjection.model_validate_json(projection) != entry.projection
            or RuntimeTargetReceipt.model_validate_json(target) != receipt
            or receipt.effect.record_id != delivery_id
            or receipt.effect.record_digest != entry.projection.digest()
        ):
            raise RuntimeStateError("integrity_error: projection target effect or receipt is incomplete")

    def apply_command_receipt(
        self, connection: sqlite3.Connection, receipt: RuntimeCommandReceipt,
        *, lookup_namespace: str | None = None,
    ) -> None:
        self._partition.upsert_runtime_row(
            connection,
            table="runtime_command_receipts",
            keys=("client_namespace", "operation_id"),
            values=(lookup_namespace or receipt.client_namespace, receipt.operation_id),
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


def _managed_outbox_type(record_json: str) -> str | None:
    raw = re.loads(record_json)
    kind = raw.get("record_type") if isinstance(raw, dict) else None
    return kind if kind in ("managed_work_projection", "managed_writeback_candidate") else None


def publish_runtime_change(
    administration: StorageAdministrationService,
    apply: Callable[[sqlite3.Connection, RuntimeStateRepository], None],
    *,
    operation_binding: str = "runtime_change",
    validate_authority: Callable[[InstallationControlState, RuntimePublicationState], None] | None = None,
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
        PartitionRevisionVector,
        RuntimeMaterializationManifest,
        RuntimePublicationIntent,
        RuntimePublicationState,
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
        state = administration._require_operational()
        administration._verified_snapshot_locked()
        if validate_authority is not None:
            validate_authority(state, finalized)
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
            with partition.capture_runtime_rows(connection) as changes:
                apply(connection, repository)
            runtime_position = (
                append_runtime_changes(
                    connection,
                    changes=changes,
                    previous=finalized,
                    runtime_revision=runtime_revision,
                    sign=lambda purpose, digest: administration._signing.sign(
                        administration._signer_key_id, purpose, digest,
                    ),
                )
                if partition.supports_runtime_history(connection)
                else None
            )
            manifest_entries = partition.compute_materialization_manifest(connection)
            manifest = RuntimeMaterializationManifest(catalogs=manifest_entries)
            memory_write, memory_data = partition.read_revision_state(connection)
            prior_ordinal = int(pre_state["ordinal"])
            vector = PartitionRevisionVector(
                partition_ordinal=prior_ordinal + 1,
                runtime_position=runtime_position if runtime_position is not None else BatchPosition(
                    sequence=runtime_revision, digest=manifest.digest()
                ),
                memory_write_revision=memory_write,
                memory_data_revision=memory_data,
                semantic_position=finalized.vector.semantic_position,
                ontology_pointer_digest=finalized.vector.ontology_pointer_digest,
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
                eligibility_epoch=(
                    state.eligibility_epoch + state.pending_epoch_increments
                ),
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
                authority_epoch=(
                    state.eligibility_epoch + state.pending_epoch_increments
                ),
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
            data_version = partition.data_version(connection)
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
        administration._verified_tuples[candidate.payload_digest()] = data_version
        return runtime_revision
