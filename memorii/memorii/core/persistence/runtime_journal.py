"""Signed SQLite runtime history and replay of current catalog rows."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Sequence
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.persistence.contracts import (
    RUNTIME_EVENT_BATCH_SIGNATURE_PURPOSE,
    BatchPosition,
    GenesisPosition,
    PublicationPosition,
    RuntimePublicationState,
)
from memorii.core.persistence.runtime_contracts import SolverNodeContent, canonical_runtime_digest
from memorii.core.persistence.runtime_events import (
    RuntimeEventBatch,
    RuntimeEventEnvelope,
    create_runtime_batch,
    create_runtime_event,
)
from memorii.domain.execution_graph.edges import ExecutionEdge
from memorii.domain.execution_graph.nodes import ExecutionNode
from memorii.domain.solver_graph.edges import SolverEdge
from memorii.stores.sqlite.partition import PartitionDataRepository, RuntimeMaterializedRow, RuntimeRowChange

_HEX = r"^[0-9a-f]{64}$"
_MAX_BATCH_BYTES = 10 * 1024 * 1024
_Digest = Annotated[str, Field(pattern=_HEX)]
_KeyPart = str | int
_Bindings = tuple[dict[str, str], dict[str, str], dict[str, str]]
_Catalog = Literal[
    "runtime_tasks", "runtime_execution_nodes", "runtime_execution_edges",
    "runtime_solver_runs", "runtime_solver_nodes", "runtime_solver_edges",
    "runtime_overlay_versions", "runtime_justifications", "runtime_action_attempts",
    "runtime_command_receipts", "runtime_operation_attempts", "runtime_outbox_deliveries",
    "runtime_checkpoints", "consolidation_results", "writeback_decisions",
    "runtime_work_projections", "runtime_target_receipts", "runtime_skill_candidates",
]
_GRAPH_ENTITY = {
    "runtime_execution_nodes": ("execution", "node"),
    "runtime_execution_edges": ("execution", "edge"),
    "runtime_solver_nodes": ("solver", "node"),
    "runtime_solver_edges": ("solver", "edge"),
    "runtime_overlay_versions": ("solver", "overlay"),
    "runtime_checkpoints": ("system", "checkpoint"),
    "runtime_outbox_deliveries": ("system", "routing"),
    "consolidation_results": ("system", "routing"),
    "writeback_decisions": ("system", "routing"),
    "runtime_work_projections": ("system", "routing"),
    "runtime_target_receipts": ("system", "routing"),
    "runtime_skill_candidates": ("system", "routing"),
}
_OWNER_VERSIONED = frozenset({
    "runtime_tasks", "runtime_solver_runs", "runtime_justifications", "runtime_action_attempts",
})
_IMMUTABLE = frozenset({
    "runtime_overlay_versions", "runtime_checkpoints", "runtime_command_receipts", "consolidation_results",
    "writeback_decisions", "runtime_work_projections", "runtime_target_receipts", "runtime_skill_candidates",
})


class RuntimeJournalError(RuntimeError):
    """The durable runtime journal or its materialization is inconsistent."""


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class _StoredSolverNode(_Closed):
    content: SolverNodeContent
    metadata: dict[str, object]


class _FullCatalogState(_Closed):
    catalog: _Catalog
    key: tuple[_KeyPart, ...] = Field(min_length=1)
    indexed: tuple[_KeyPart, ...]
    version: int = Field(ge=1)
    owner_record_json: str = Field(min_length=2)

    @model_validator(mode="after")
    def valid_record_object(self) -> Self:
        if not isinstance(json.loads(self.owner_record_json), dict):
            raise ValueError("runtime catalog event requires a full owner record")
        match self.catalog:
            case "runtime_execution_nodes":
                identity = ExecutionNode.model_validate_json(self.owner_record_json).id
            case "runtime_execution_edges":
                identity = ExecutionEdge.model_validate_json(self.owner_record_json).id
            case "runtime_solver_edges":
                identity = SolverEdge.model_validate_json(self.owner_record_json).id
            case "runtime_solver_nodes":
                _StoredSolverNode.model_validate_json(self.owner_record_json)
                return self
            case _:
                return self
        if len(self.key) != 2 or identity != self.key[1]:
            raise ValueError("runtime graph event identity differs from its catalog key")
        return self

    def row(self) -> RuntimeMaterializedRow:
        return RuntimeMaterializedRow(self.catalog, self.key, self.indexed, self.owner_record_json)


class _SignedBatch(_Closed):
    installation_id: str
    generation_id: str
    previous_position: PublicationPosition
    runtime_revision: int = Field(ge=1)
    batch: RuntimeEventBatch
    signature: str = Field(pattern=r"^[0-9a-f]{128}$")

    def digest(self) -> str:
        return canonical_runtime_digest((
            RUNTIME_EVENT_BATCH_SIGNATURE_PURPOSE,
            self.installation_id,
            self.generation_id,
            self.previous_position.model_dump(mode="json"),
            self.runtime_revision,
            self.batch.repository_id,
            self.batch.sequence,
            self.batch.event_batch_digest,
        ))

    def position(self) -> BatchPosition:
        return BatchPosition(sequence=self.batch.sequence, digest=self.digest())


class _Binding(_Closed):
    event_id: _Digest
    event_digest: _Digest
    batch_sequence: int = Field(ge=1)


def _record_id(row: RuntimeMaterializedRow) -> str:
    return canonical_runtime_digest((row.catalog, row.key))


def _version_id(record_id: str, revision: int) -> str:
    return canonical_runtime_digest((record_id, revision))


def _state_version(catalog: str, record_json: str, revision: int) -> int:
    record = json.loads(record_json)
    if not isinstance(record, dict):
        raise RuntimeJournalError("integrity_error: runtime event state must be an owner record object")
    if catalog in _IMMUTABLE:
        return 1
    if catalog in _OWNER_VERSIONED:
        version = record.get("version")
    elif (
        catalog == "runtime_outbox_deliveries"
        and record.get("record_type") in ("managed_work_projection", "managed_writeback_candidate")
    ):
        delivery = record.get("delivery")
        version = delivery.get("version") if isinstance(delivery, dict) else None
    else:
        return revision
    if type(version) is not int or version < 1:
        raise RuntimeJournalError("integrity_error: runtime event record version is invalid")
    return version


def _to_event(change: RuntimeRowChange, previous: RuntimePublicationState, revision: int) -> RuntimeEventEnvelope:
    row = change.row
    version = _state_version(row.catalog, row.record_json, revision)
    if change.prior_record_json is not None and version <= _state_version(
        row.catalog, change.prior_record_json, revision - 1,
    ):
        raise RuntimeJournalError("memory_integrity_conflict: divergent runtime record version")
    payload = _FullCatalogState.model_validate({
        "catalog": row.catalog, "key": row.key, "indexed": row.indexed, "owner_record_json": row.record_json,
        "version": version,
    })
    record_id = _record_id(row)
    graph_type, entity_type = _GRAPH_ENTITY.get(row.catalog, ("system", "directory"))
    record = json.loads(row.record_json)
    task_id = (
        str(row.key[0])
        if row.catalog in ("runtime_tasks", "runtime_execution_nodes", "runtime_execution_edges")
        else record.get("task_id") or "partition"
    )
    solver_id = (
        str(row.key[0])
        if row.catalog in ("runtime_solver_nodes", "runtime_solver_edges", "runtime_solver_runs")
        else record.get("solver_id")
    )
    content = record.get("content")
    is_candidate = (
        (row.catalog == "runtime_solver_nodes" and isinstance(content, dict)
         and content.get("epistemic_status") == "candidate")
        or (row.catalog == "runtime_overlay_versions" and record.get("committed") is False)
    )
    operation = "version" if entity_type == "overlay" else change.operation
    return create_runtime_event(
        event_id=canonical_runtime_digest(("runtime_event", previous.data_generation_id, record_id, revision)),
        dedupe_key=canonical_runtime_digest(("runtime_record", previous.repository_id, record_id, revision)),
        graph_type=graph_type, entity_type=entity_type, operation=operation,
        entity_id=record_id, entity=payload.model_dump(mode="json"), metadata_version=revision,
        task_id=task_id, solver_run_id=solver_id, is_candidate=is_candidate,
    )


def _bind_events(signed: _SignedBatch, bindings: _Bindings) -> None:
    for event in signed.batch.events:
        full_state = _FullCatalogState.model_validate_json(json.dumps(event.entity))
        binding = _Binding(
            event_id=event.event_id,
            event_digest=event.event_digest,
            batch_sequence=signed.batch.sequence,
        ).model_dump_json()
        for index, coordinate in zip(bindings, (
            event.event_id, event.dedupe_key, _version_id(event.record_id, full_state.version),
        ), strict=True):
            if coordinate in index:
                raise RuntimeJournalError("memory_integrity_conflict: duplicate runtime history binding")
            index[coordinate] = binding


def append_runtime_changes(
    connection: sqlite3.Connection,
    *,
    changes: Sequence[RuntimeRowChange],
    previous: RuntimePublicationState,
    runtime_revision: int,
    sign: Callable[[str, str], str],
) -> PublicationPosition:
    """Append a complete change group and all uniqueness indexes before commit."""
    previous_position = previous.vector.runtime_position
    if not changes:
        return previous_position
    sequence = previous_position.sequence + 1 if isinstance(previous_position, BatchPosition) else 1
    batch = create_runtime_batch(
        repository_id=previous.repository_id,
        sequence=sequence,
        events=tuple(_to_event(change, previous, runtime_revision) for change in changes),
    )
    unsigned = _SignedBatch(
        installation_id=previous.installation_id,
        generation_id=previous.data_generation_id,
        previous_position=previous_position,
        runtime_revision=runtime_revision,
        batch=batch,
        signature="0" * 128,
    )
    signed = unsigned.model_copy(update={"signature": sign(RUNTIME_EVENT_BATCH_SIGNATURE_PURPOSE, unsigned.digest())})
    record_json = signed.model_dump_json()
    if len(record_json.encode("utf-8")) > _MAX_BATCH_BYTES:
        raise RuntimeJournalError("runtime event batch exceeds the durable size limit")
    bindings: _Bindings = ({}, {}, {})
    _bind_events(signed, bindings)
    try:
        PartitionDataRepository.insert_runtime_event_batch(
            connection, sequence=sequence, record_json=record_json, bindings=bindings,
        )
    except sqlite3.IntegrityError as exc:
        raise RuntimeJournalError("memory_integrity_conflict: runtime event or record version already bound") from exc
    return signed.position()


def verify_runtime_history(
    connection: sqlite3.Connection,
    *,
    finalized: RuntimePublicationState,
    verify: Callable[[str, str, str], bool],
) -> None:
    """Replay the complete history and verify its exact signed head and projections."""
    if not PartitionDataRepository.supports_runtime_history(connection):
        return
    position: PublicationPosition = GenesisPosition()
    replayed: dict[tuple[str, tuple[_KeyPart, ...]], RuntimeMaterializedRow] = {}
    bindings: _Bindings = ({}, {}, {})
    revision = 0
    for expected_sequence, (sequence, payload) in enumerate(
        PartitionDataRepository.runtime_event_batch_rows(connection), 1,
    ):
        signed = _SignedBatch.model_validate_json(payload)
        if (
            sequence != expected_sequence or sequence != signed.batch.sequence
            or signed.installation_id != finalized.installation_id
            or signed.batch.repository_id != finalized.repository_id
            or signed.generation_id != finalized.data_generation_id
            or signed.previous_position != position
            or signed.runtime_revision <= revision
            or not verify(RUNTIME_EVENT_BATCH_SIGNATURE_PURPOSE, signed.digest(), signed.signature)
        ):
            raise RuntimeJournalError("integrity_error: runtime event batch is outside the signed history")
        _bind_events(signed, bindings)
        for event in signed.batch.events:
            full_state = _FullCatalogState.model_validate_json(json.dumps(event.entity))
            row = full_state.row()
            identity = (row.catalog, row.key)
            prior = replayed.get(identity)
            graph_type, entity_type = _GRAPH_ENTITY.get(row.catalog, ("system", "directory"))
            if (
                event.record_id != _record_id(row)
                or event.metadata_version != signed.runtime_revision
                or full_state.version != _state_version(row.catalog, row.record_json, revision=signed.runtime_revision)
                or (event.graph_type, event.entity_type) != (graph_type, entity_type)
                or (event.operation in ("create", "version") and prior is not None)
                or (event.operation == "update" and prior is None)
                or (prior is not None and full_state.version <= _state_version(
                    prior.catalog, prior.record_json, signed.runtime_revision - 1,
                ))
                or event.operation == "delete"
            ):
                raise RuntimeJournalError("integrity_error: runtime event does not match its catalog state")
            replayed[identity] = row
        position = signed.position()
        revision = signed.runtime_revision
    if position != finalized.vector.runtime_position:
        raise RuntimeJournalError("integrity_error: runtime history does not match the signed head")
    if revision != PartitionDataRepository.read_runtime_revision(connection):
        raise RuntimeJournalError("integrity_error: runtime revision does not match the signed history")
    if PartitionDataRepository.runtime_replay_bindings(connection) != bindings:
        raise RuntimeJournalError("integrity_error: runtime replay indexes do not match the event history")
    actual = {
        (row.catalog, row.key): row for row in PartitionDataRepository.runtime_materialized_rows(connection)
    }
    if actual != replayed:
        raise RuntimeJournalError("integrity_error: runtime materializations do not match replay")
