"""Signed SQLite runtime history and replay of current catalog rows."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from hashlib import sha256
from typing import Annotated, Literal, Self, TypeVar

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from memorii.core.persistence.contracts import (
    RUNTIME_EVENT_BATCH_SIGNATURE_PURPOSE,
    BatchPosition,
    GenesisPosition,
    PublicationPosition,
    RuntimePublicationState,
)
from memorii.core.persistence.key_owner import RUNTIME_CHECKPOINT_SIGNATURE_PURPOSE
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
    "runtime_source_release_grants", "runtime_delivery_restore_holds",
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
    "runtime_source_release_grants": ("system", "routing"),
    "runtime_delivery_restore_holds": ("system", "routing"),
}
_OWNER_VERSIONED = frozenset({
    "runtime_tasks", "runtime_solver_runs", "runtime_justifications", "runtime_action_attempts",
    "runtime_source_release_grants",
})
_IMMUTABLE = frozenset({
    "runtime_overlay_versions", "runtime_checkpoints", "runtime_command_receipts", "consolidation_results",
    "writeback_decisions", "runtime_work_projections", "runtime_target_receipts", "runtime_skill_candidates",
    "runtime_delivery_restore_holds",
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


class _CheckpointMember(_Closed):
    catalog: _Catalog
    key: tuple[_KeyPart, ...] = Field(min_length=1)
    indexed: tuple[_KeyPart, ...]
    owner_record_json: str = Field(min_length=2)

    @property
    def record_json(self) -> str:
        return self.owner_record_json


class _CheckpointBinding(_Closed):
    coordinate: _Digest
    owner_binding_json: str = Field(min_length=2)


_ReplayRows = dict[tuple[str, tuple[_KeyPart, ...]], RuntimeMaterializedRow | _CheckpointMember]
_CheckpointEntry = TypeVar("_CheckpointEntry", _CheckpointMember, _CheckpointBinding)
_MEMBER_JSON = TypeAdapter(_CheckpointMember)
_BINDING_JSON = TypeAdapter(_CheckpointBinding)


class _CheckpointManifest(_Closed):
    version: Literal[1] = 1
    installation_id: str = Field(min_length=1)
    repository_id: str = Field(min_length=1)
    generation_id: str = Field(min_length=1)
    through_position: BatchPosition
    runtime_revision: int = Field(ge=1)
    partition_schema: int = Field(ge=1)
    trust_registry_digest: _Digest
    eligibility_epoch: int = Field(ge=1)
    ancestry_digest: _Digest
    signer_key_id: str = Field(min_length=1)
    signer_key_fingerprint: _Digest
    member_count: int = Field(ge=1)
    member_digest: _Digest
    event_binding_digest: _Digest
    dedupe_binding_digest: _Digest
    record_version_binding_digest: _Digest

    def digest(self) -> str:
        return canonical_runtime_digest((RUNTIME_CHECKPOINT_SIGNATURE_PURPOSE, self.model_dump(mode="json")))


class _ReplayCheckpoint(_Closed):
    manifest: _CheckpointManifest
    members: tuple[_CheckpointMember, ...]
    event_bindings: tuple[_CheckpointBinding, ...]
    dedupe_bindings: tuple[_CheckpointBinding, ...]
    record_version_bindings: tuple[_CheckpointBinding, ...]
    signature: str = Field(pattern=r"^[0-9a-f]{128}$")


def _member_digest(records: Sequence[_CheckpointEntry], adapter: TypeAdapter[_CheckpointEntry]) -> str:
    digest = sha256()
    encode = adapter.dump_json
    for item in records:
        payload = encode(item)
        digest.update(len(payload).to_bytes(8, byteorder="big"))
        digest.update(payload)
    return digest.hexdigest()


def _ancestry_digest(publication: RuntimePublicationState) -> str:
    return canonical_runtime_digest(tuple(
        interval.model_dump(mode="json") for interval in publication.runtime_history_ancestry
    ))


def persist_runtime_replay_checkpoint(
    connection: sqlite3.Connection,
    *,
    previous: RuntimePublicationState,
    through_position: BatchPosition,
    runtime_revision: int,
    eligibility_epoch: int,
    signer_key_id: str,
    signer_key_fingerprint: str,
    sign: Callable[[str, str], str],
) -> str:
    """Seal the transaction's new batch boundary before its publication commits."""
    members: list[_CheckpointMember] = []
    rows = PartitionDataRepository.runtime_materialized_rows(connection)
    for row in sorted(rows, key=lambda item: (item.catalog, item.key)):
        members.append(_CheckpointMember.model_validate({
            "catalog": row.catalog, "key": row.key, "indexed": row.indexed, "owner_record_json": row.record_json,
        }))
    stored_bindings = PartitionDataRepository.runtime_replay_bindings(connection)
    event, dedupe, versions = (
        tuple(
            _CheckpointBinding(coordinate=coordinate, owner_binding_json=payload)
            for coordinate, payload in sorted(index.items())
        )
        for index in stored_bindings
    )
    manifest = _CheckpointManifest(
        installation_id=previous.installation_id,
        repository_id=previous.repository_id,
        generation_id=previous.data_generation_id,
        through_position=through_position,
        runtime_revision=runtime_revision,
        partition_schema=PartitionDataRepository.read_schema_version(connection),
        trust_registry_digest=previous.trust_registry_digest,
        eligibility_epoch=eligibility_epoch,
        ancestry_digest=_ancestry_digest(previous),
        signer_key_id=signer_key_id,
        signer_key_fingerprint=signer_key_fingerprint,
        member_count=len(members),
        member_digest=_member_digest(members, _MEMBER_JSON),
        event_binding_digest=_member_digest(event, _BINDING_JSON),
        dedupe_binding_digest=_member_digest(dedupe, _BINDING_JSON),
        record_version_binding_digest=_member_digest(versions, _BINDING_JSON),
    )
    digest = manifest.digest()
    checkpoint = _ReplayCheckpoint(
        manifest=manifest, members=tuple(members), event_bindings=event, dedupe_bindings=dedupe,
        record_version_bindings=versions, signature=sign(RUNTIME_CHECKPOINT_SIGNATURE_PURPOSE, digest),
    )
    connection.execute(
        "INSERT INTO runtime_replay_checkpoints (checkpoint_digest, record_json) VALUES (?, ?)",
        (digest, checkpoint.model_dump_json()),
    )
    return digest


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


def _validate_catalog_transition(
    row: RuntimeMaterializedRow,
    previous_json: str | None,
    *,
    installation_id: str,
    repository_id: str,
    generation_id: str,
) -> None:
    match row.catalog:
        case "runtime_source_release_grants":
            from memorii.core.provider.runtime_source_release import validate_runtime_source_release_event

            if len(row.key) != 1 or row.indexed:
                raise RuntimeJournalError("integrity_error: invalid source release grant catalog key")
            try:
                validate_runtime_source_release_event(row.record_json, grant_id=row.key[0], previous_json=previous_json)
            except ValueError as exc:
                raise RuntimeJournalError("integrity_error: invalid source release grant transition") from exc
        case "runtime_delivery_restore_holds":
            from memorii.core.persistence.managed_delivery import DeliveryRestoreHold, DeliveryRestoreRejection

            payload = json.loads(row.record_json)
            record: DeliveryRestoreHold | DeliveryRestoreRejection
            if isinstance(payload, dict) and payload.get("status") == "rejected":
                record = DeliveryRestoreRejection.model_validate(payload)
                expected_key = record.record_id
            else:
                record = DeliveryRestoreHold.model_validate(payload)
                expected_key = record.hold_id
                if record.source_generation_id == generation_id:
                    raise RuntimeJournalError("integrity_error: delivery hold cannot inherit its own generation")
            if (
                row.key != (expected_key,) or row.indexed or previous_json is not None
                or record.installation_id != installation_id or record.partition_id != repository_id
                or record.restored_generation_id != generation_id
            ):
                raise RuntimeJournalError("integrity_error: delivery hold does not match its signed generation")
        case "runtime_outbox_deliveries":
            from memorii.core.persistence.runtime_api import LegacyUnresolvedDelivery

            current = json.loads(row.record_json)
            prior = None if previous_json is None else json.loads(previous_json)
            if isinstance(prior, dict) and prior.get("record_type") == "legacy_unresolved_delivery":
                raise RuntimeJournalError("integrity_error: unresolved legacy history is immutable")
            if isinstance(current, dict) and current.get("record_type") == "legacy_unresolved_delivery":
                legacy = LegacyUnresolvedDelivery.model_validate_json(row.record_json)
                if row.key != (legacy.delivery_id,) or row.indexed or legacy.original_record_json != previous_json:
                    raise RuntimeJournalError("integrity_error: unresolved legacy delivery differs from signed history")


def _to_event(change: RuntimeRowChange, previous: RuntimePublicationState, revision: int) -> RuntimeEventEnvelope:
    row = change.row
    _validate_catalog_transition(
        row, change.prior_record_json, installation_id=previous.installation_id,
        repository_id=previous.repository_id, generation_id=previous.data_generation_id,
    )
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


@dataclass(frozen=True)
class _ReplayStart:
    position: PublicationPosition
    revision: int
    rows: _ReplayRows
    bindings: _Bindings


def _checkpoint_start(
    connection: sqlite3.Connection,
    *,
    finalized: RuntimePublicationState,
    verify: Callable[[str, str, str], bool],
    signer_key_id: str | None,
    signer_fingerprint: str | None,
) -> _ReplayStart:
    digest = finalized.checkpoint_digest
    position = finalized.vector.runtime_position
    if (
        digest is None
        or not PartitionDataRepository.supports_runtime_replay_checkpoints(connection)
        or not isinstance(position, BatchPosition)
        or signer_key_id is None
        or signer_fingerprint is None
    ):
        raise RuntimeJournalError("integrity_error: selected runtime checkpoint has no verified owner")
    stored = connection.execute(
        "SELECT record_json FROM runtime_replay_checkpoints WHERE checkpoint_digest = ?", (digest,),
    ).fetchone()
    if stored is None:
        raise RuntimeJournalError("integrity_error: selected runtime checkpoint is missing")
    checkpoint = _ReplayCheckpoint.model_validate_json(stored[0])
    manifest = checkpoint.manifest
    ancestry = finalized.runtime_history_ancestry
    if (
        manifest.digest() != digest
        or manifest.installation_id != finalized.installation_id
        or manifest.repository_id != finalized.repository_id
        or manifest.generation_id != finalized.data_generation_id
        or manifest.partition_schema != PartitionDataRepository.read_schema_version(connection)
        or manifest.ancestry_digest != _ancestry_digest(finalized)
        or manifest.trust_registry_digest != finalized.trust_registry_digest
        or manifest.eligibility_epoch > finalized.eligibility_epoch
        or manifest.signer_key_id != signer_key_id
        or manifest.signer_key_fingerprint != signer_fingerprint
        or manifest.through_position.sequence > position.sequence
        or (ancestry and manifest.through_position.sequence <= ancestry[-1].through_position.sequence)
        or not verify(RUNTIME_CHECKPOINT_SIGNATURE_PURPOSE, digest, checkpoint.signature)
    ):
        raise RuntimeJournalError("integrity_error: runtime checkpoint is outside the signed publication")
    sequence = manifest.through_position.sequence
    prefix = connection.execute(
        "SELECT count(*) FROM runtime_event_batches WHERE sequence BETWEEN 1 AND ?", (sequence,),
    ).fetchone()
    anchor = connection.execute(
        "SELECT record_json FROM runtime_event_batches WHERE sequence = ?", (sequence,),
    ).fetchone()
    if prefix[0] != sequence or anchor is None:
        raise RuntimeJournalError("integrity_error: runtime checkpoint batch prefix is unavailable")
    boundary = _SignedBatch.model_validate_json(anchor[0])
    if (
        boundary.position() != manifest.through_position
        or boundary.runtime_revision != manifest.runtime_revision
        or boundary.installation_id != finalized.installation_id
        or boundary.batch.repository_id != finalized.repository_id
        or boundary.generation_id != finalized.data_generation_id
        or not verify(RUNTIME_EVENT_BATCH_SIGNATURE_PURPOSE, boundary.digest(), boundary.signature)
    ):
        raise RuntimeJournalError("integrity_error: runtime checkpoint batch boundary is invalid")
    event, dedupe, versions = (
        checkpoint.event_bindings, checkpoint.dedupe_bindings, checkpoint.record_version_bindings,
    )
    if (
        manifest.member_count != len(checkpoint.members)
        or manifest.member_digest != _member_digest(checkpoint.members, _MEMBER_JSON)
        or manifest.event_binding_digest != _member_digest(event, _BINDING_JSON)
        or manifest.dedupe_binding_digest != _member_digest(dedupe, _BINDING_JSON)
        or manifest.record_version_binding_digest != _member_digest(versions, _BINDING_JSON)
    ):
        raise RuntimeJournalError("integrity_error: runtime checkpoint members or indexes differ from its manifest")
    rows: _ReplayRows = {(member.catalog, member.key): member for member in checkpoint.members}
    bindings = (
        {entry.coordinate: entry.owner_binding_json for entry in event},
        {entry.coordinate: entry.owner_binding_json for entry in dedupe},
        {entry.coordinate: entry.owner_binding_json for entry in versions},
    )
    if len(rows) != len(checkpoint.members) or any(
        len(index) != len(entries) for index, entries in zip(bindings, (event, dedupe, versions), strict=True)
    ):
        raise RuntimeJournalError("integrity_error: runtime checkpoint contains duplicate identities")
    return _ReplayStart(manifest.through_position, manifest.runtime_revision, rows, bindings)


def verify_runtime_history(
    connection: sqlite3.Connection,
    *,
    finalized: RuntimePublicationState,
    verify: Callable[[str, str, str], bool],
    checkpoint_signer_key_id: str | None = None,
    checkpoint_signer_fingerprint: str | None = None,
    use_checkpoint: bool = True,
) -> None:
    """Replay from the signed checkpoint or genesis and verify the exact head and projections."""
    if not PartitionDataRepository.supports_runtime_history(connection):
        if finalized.runtime_history_ancestry or finalized.checkpoint_digest is not None:
            raise RuntimeJournalError("integrity_error: signed runtime history is unavailable")
        return
    start = (
        _checkpoint_start(
            connection,
            finalized=finalized,
            verify=verify,
            signer_key_id=checkpoint_signer_key_id,
            signer_fingerprint=checkpoint_signer_fingerprint,
        )
        if use_checkpoint and finalized.checkpoint_digest is not None
        else _ReplayStart(GenesisPosition(), 0, {}, ({}, {}, {}))
    )
    position = start.position
    replayed, bindings, revision = start.rows, start.bindings, start.revision
    through_sequence = position.sequence if isinstance(position, BatchPosition) else 0
    remaining_ancestry = iter(
        interval for interval in finalized.runtime_history_ancestry
        if interval.through_position.sequence > through_sequence
    )
    interval = next(remaining_ancestry, None)
    tail = connection.execute(
        "SELECT sequence, record_json FROM runtime_event_batches WHERE sequence > ? ORDER BY sequence",
        (through_sequence,),
    )
    for expected_sequence, (sequence, payload) in enumerate(tail, through_sequence + 1):
        signed = _SignedBatch.model_validate_json(payload)
        batch_position = signed.position()
        generation_id = finalized.data_generation_id if interval is None else interval.generation_id
        if (
            sequence != expected_sequence or sequence != signed.batch.sequence
            or signed.installation_id != finalized.installation_id
            or signed.batch.repository_id != finalized.repository_id
            or signed.generation_id != generation_id
            or signed.previous_position != position
            or signed.runtime_revision <= revision
            or not verify(RUNTIME_EVENT_BATCH_SIGNATURE_PURPOSE, batch_position.digest, signed.signature)
        ):
            raise RuntimeJournalError("integrity_error: runtime event batch is outside the signed history")
        if interval is not None and sequence == interval.through_position.sequence:
            if batch_position != interval.through_position:
                raise RuntimeJournalError("integrity_error: runtime event batch differs from its signed ancestor")
            interval = next(remaining_ancestry, None)
        _bind_events(signed, bindings)
        for event in signed.batch.events:
            full_state = _FullCatalogState.model_validate_json(json.dumps(event.entity))
            row = full_state.row()
            identity = (row.catalog, row.key)
            prior = replayed.get(identity)
            _validate_catalog_transition(
                row, None if prior is None else prior.record_json,
                installation_id=signed.installation_id, repository_id=signed.batch.repository_id,
                generation_id=signed.generation_id,
            )
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
        position = batch_position
        revision = signed.runtime_revision
    if interval is not None or position != finalized.vector.runtime_position:
        raise RuntimeJournalError("integrity_error: runtime history does not match the signed head")
    if revision != PartitionDataRepository.read_runtime_revision(connection):
        raise RuntimeJournalError("integrity_error: runtime revision does not match the signed history")
    if PartitionDataRepository.runtime_replay_bindings(connection) != bindings:
        raise RuntimeJournalError("integrity_error: runtime replay indexes do not match the event history")
    # Compare exact rows while consuming the replayed identities. Checkpoint
    # members can remain typed owner records and the live rows need no second map.
    for row in PartitionDataRepository.runtime_materialized_rows(connection):
        expected = replayed.pop((row.catalog, row.key), None)
        if expected is None or row.indexed != expected.indexed or row.record_json != expected.record_json:
            raise RuntimeJournalError("integrity_error: runtime materializations do not match replay")
    if replayed:
        raise RuntimeJournalError("integrity_error: runtime materializations do not match replay")
