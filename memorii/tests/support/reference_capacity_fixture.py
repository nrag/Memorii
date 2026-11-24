"""Untimed preparation and verification of the signed reference storage fixture.

Run the engineering module from a driver directory containing tests/support
and an interpreter with the candidate wheel installed. The driver directory
must not also expose the source checkout's memorii package.
Transcript bodies go through the native source owner and signed managed
observation. Full fixture preparation also seals the approved checkpoint
and tail. Timed qualification requires both named runner profiles.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import asdict, dataclass
from datetime import timedelta
from importlib.metadata import distribution as installed_distribution
from itertools import groupby, islice
from pathlib import Path
from typing import TypeVar
from zipfile import ZipFile

import memorii
from memorii.core.memory_evolution.admission import source_admission_source_digest
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.store import record_digest
from memorii.core.persistence.contracts import BatchPosition, RuntimePublicationState, canonical_json_digest
from memorii.core.persistence.runtime_api import RuntimeOperationAttempt, operation_origin_namespace
from memorii.core.persistence.runtime_contracts import (
    HypothesisContent,
    NodeEvidenceReference,
    ObservationContent,
    OverlayJustificationBinding,
    RuntimeCommandReceipt,
    RuntimeOverlayVersion,
    SolverRunRecord,
    TaskRecord,
)
from memorii.core.persistence.runtime_journal import verify_runtime_history
from memorii.core.persistence.runtime_repository import RuntimeStateRepository, publish_runtime_change
from memorii.core.storage_administration.service import StorageAdministrationService
from memorii.domain.common import SolverEdgeMetadata, SolverNodeMetadata
from memorii.domain.enums import (
    CommitStatus,
    ConfidenceClass,
    ExecutionEdgeType,
    ExecutionNodeStatus,
    ExecutionNodeType,
    MemoryDomain,
    MemoryRecordVisibility,
    SolverCreatedBy,
    SolverEdgeType,
)
from memorii.domain.execution_graph.edges import ExecutionEdge
from memorii.domain.execution_graph.nodes import ExecutionNode
from memorii.domain.solver_graph.edges import SolverEdge
from memorii.stores.sqlite.partition import RuntimeMaterializedRow

from tests.support.reference_capacity import (
    CHECKPOINT_TAIL_COUNT,
    EVENT_COUNT,
    FIXTURE_START,
    Distribution,
    EventFillInput,
    TaskAllocation,
    event_fill_inputs,
    task_allocations,
    workload_manifest,
)
from tests.support.reference_capacity_sources import (
    REFERENCE_NAMESPACE,
    REFERENCE_PRINCIPAL,
    ReferenceSourceCapture,
    reference_delivery,
)

_GRAPH_CHUNK = 512
_SOURCE_RUNTIME_CATALOGS = frozenset({"runtime_command_receipts", "runtime_operation_attempts"})
_QUALIFICATION_BLOCKERS = ("timed_reference_workload_not_measured",)
_T = TypeVar("_T")
_Mutation = Callable[[sqlite3.Connection, RuntimeStateRepository], None]


class ReferenceFixtureError(RuntimeError):
    """The signed fixture failed its setup or closure requirements."""


@dataclass(frozen=True)
class ReferenceStorageAudit:
    distribution: Distribution
    workload_digest: str
    generator_digest: str
    loader_digest: str
    source_driver_digest: str
    partition_tuple_digest: str
    graph_digest: str
    sources_digest: str
    source_receipts_digest: str
    event_inventory_digest: str
    graph_row_counts: dict[str, int]
    source_count: int
    source_receipt_count: int
    source_body_bytes: int
    runtime_event_count: int
    runtime_event_batch_count: int
    runtime_operation_counts: dict[str, int]
    checkpoint_digest: str | None
    checkpoint_tail_count: int
    qualification_blockers: tuple[str, ...] = _QUALIFICATION_BLOCKERS


def _chunks(values: Iterable[_T], size: int) -> Iterator[tuple[_T, ...]]:
    iterator = iter(values)
    while block := tuple(islice(iterator, size)):
        yield block


def _canonical(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode("ascii")


def _root_node(task: TaskAllocation, *, execution_ordinal: int = 0) -> ExecutionNode:
    moment = FIXTURE_START + timedelta(seconds=execution_ordinal)
    return ExecutionNode(
        id=f"{task.task_id}:execution:0", type=ExecutionNodeType.MISSION,
        title=f"Mission {task.index}", description="Reference execution root",
        status=ExecutionNodeStatus.READY, created_at=moment, updated_at=moment,
    )


def _execution_changes(allocations: Sequence[TaskAllocation]) -> Iterator[_Mutation]:
    execution_ordinal = 0
    for task in allocations:
        root = _root_node(task, execution_ordinal=execution_ordinal)
        yield lambda connection, repo, task=task, root=root: repo.apply_task(connection, TaskRecord(
            task_id=task.task_id, principal=REFERENCE_PRINCIPAL, goal=root.title, created_at=root.created_at,
            root_execution_node_id=root.id, active_solver_by_execution_node={root.id: task.solver_id},
        ))
        for index in range(task.execution_nodes):
            moment = FIXTURE_START + timedelta(seconds=execution_ordinal)
            execution_ordinal += 1
            node = ExecutionNode(
                id=f"{task.task_id}:execution:{index}",
                type=ExecutionNodeType.MISSION if index == 0 else ExecutionNodeType.WORK_ITEM,
                title=root.title if index == 0 else f"Work item {index}",
                description=root.description if index == 0 else "Reference execution member",
                status=ExecutionNodeStatus.READY, created_at=moment, updated_at=moment,
            )
            yield lambda connection, repo, node=node, task=task: repo.apply_execution_node(
                connection, task_id=task.task_id, node_id=node.id, node_json=node.model_dump_json(),
            )
        for index, (source, target) in enumerate(task.execution_edges()):
            moment = FIXTURE_START + timedelta(seconds=execution_ordinal - task.execution_nodes + index + 1)
            edge = ExecutionEdge(
                id=f"{task.task_id}:execution-edge:{index}", src=source, dst=target,
                type=ExecutionEdgeType.DECOMPOSES_INTO, created_at=moment, updated_at=moment,
            )
            yield lambda connection, repo, edge=edge, task=task: repo.apply_execution_edge(
                connection, task_id=task.task_id, edge_id=edge.id, edge_json=edge.model_dump_json(),
            )


def _solver_changes(
    allocations: Sequence[TaskAllocation], refs: dict[str, NodeEvidenceReference],
) -> Iterator[_Mutation]:
    for task in allocations:
        root = _root_node(task)
        initial_overlay = f"{task.solver_id}:overlay:initial"
        yield lambda connection, repo, root=root, task=task, initial_overlay=initial_overlay: repo.apply_solver_run(
            connection, SolverRunRecord(
                solver_id=task.solver_id, task_id=task.task_id, parent_execution_node_id=root.id,
                category="diagnostic", created_by=REFERENCE_PRINCIPAL, selected_overlay_id=initial_overlay,
            ),
        )
        observations = dict(task.observation_inputs())
        for index in range(task.solver_nodes):
            node_id = f"{task.solver_id}:node:{index}"
            source_input = observations.get(node_id)
            content: ObservationContent | HypothesisContent = (
                HypothesisContent(statement=f"Reference hypothesis {index}", strength=0.5)
                if source_input is None else ObservationContent(
                    summary=f"Reference observation {source_input.coordinate}", source_refs=(refs[source_input.coordinate],),
                )
            )
            metadata = SolverNodeMetadata(
                created_at=FIXTURE_START + timedelta(seconds=task.first_solver_node + index),
                created_by=SolverCreatedBy.SYSTEM,
                candidate_state=CommitStatus.CANDIDATE if source_input is None else CommitStatus.COMMITTED,
                source_refs=[] if source_input is None else [refs[source_input.coordinate].source_id],
            )
            yield lambda connection, repo, task=task, node_id=node_id, content=content, metadata=metadata: (
                repo.apply_solver_node(
                    connection, solver_id=task.solver_id, node_id=node_id, content=content,
                    metadata_json=metadata.model_dump_json(),
                )
            )
        for index, (source, target) in enumerate(task.solver_edges()):
            edge = SolverEdge(
                id=f"{task.solver_id}:edge:{index}", src=source, dst=target, type=SolverEdgeType.SUPPORTS,
                metadata=SolverEdgeMetadata(
                    created_at=FIXTURE_START + timedelta(seconds=task.first_solver_node + index),
                    created_by=SolverCreatedBy.SYSTEM, candidate_state=CommitStatus.CANDIDATE,
                    confidence_class=ConfidenceClass.INFERRED,
                ),
            )
            yield lambda connection, repo, task=task, edge=edge: repo.apply_solver_edge(
                connection, solver_id=task.solver_id, edge=edge,
            )
        overlay = RuntimeOverlayVersion(
            version_id=initial_overlay, solver_id=task.solver_id,
            node_bindings=(OverlayJustificationBinding(node_id=f"{task.solver_id}:node:0", frontier=True),),
            created_at=FIXTURE_START, committed=True,
        )
        yield lambda connection, repo, overlay=overlay: repo.apply_overlay(connection, overlay)


def _publish_changes(
    service: StorageAdministrationService, changes: Iterable[_Mutation], *, batch_size: int = _GRAPH_CHUNK,
    checkpoint_at_end: bool = False,
) -> None:
    def publish(block: tuple[_Mutation, ...], *, checkpoint: bool = False) -> None:
        def write(connection: sqlite3.Connection, repository: RuntimeStateRepository) -> None:
            for change in block:
                change(connection, repository)

        publish_runtime_change(service, write, checkpoint_requested=checkpoint)

    blocks = _chunks(changes, batch_size)
    if checkpoint_at_end:
        previous = next(blocks, None)
        if previous is None:
            raise ReferenceFixtureError("reference fixture checkpoint requires an ordinary boundary batch")
        for block in blocks:
            publish(previous)
            previous = block
        publish(previous, checkpoint=True)
    else:
        for block in blocks:
            publish(block)


def _fill_changes(allocations: Sequence[TaskAllocation], steps: Iterable[EventFillInput]) -> Iterator[_Mutation]:
    tasks = {task.task_id: task for task in allocations}
    parent_overlay = {task.solver_id: f"{task.solver_id}:overlay:initial" for task in allocations}
    roots: dict[str, ExecutionNode] = {}
    execution_ordinal = 0
    for task in allocations:
        roots[task.task_id] = _root_node(task, execution_ordinal=execution_ordinal)
        execution_ordinal += task.execution_nodes
    for step in steps:
        task = tasks[step.task_id]
        if step.kind == "status_update":
            node = roots[step.task_id].model_copy(
                update={"updated_at": step.timestamp, "status": ExecutionNodeStatus.WAITING},
            )
            yield lambda connection, repo, task=task, node=node: repo.apply_execution_node(
                connection, task_id=task.task_id, node_id=node.id, node_json=node.model_dump_json(),
            )
        else:
            version_id = f"{task.solver_id}:overlay:{step.ordinal}"
            overlay = RuntimeOverlayVersion(
                version_id=version_id, solver_id=task.solver_id, parent_version_id=parent_overlay[task.solver_id],
                node_bindings=(OverlayJustificationBinding(node_id=f"{task.solver_id}:node:0", frontier=True),),
                created_at=step.timestamp,
            )
            parent_overlay[task.solver_id] = version_id
            yield lambda connection, repo, overlay=overlay: repo.apply_overlay(connection, overlay)


def _event_inventory(connection: sqlite3.Connection) -> tuple[int, int, Counter[str], str]:
    operations: Counter[str] = Counter()
    evidence = hashlib.sha256()
    rows = connection.execute("SELECT record_json FROM runtime_event_batches ORDER BY sequence")
    event_count = batch_count = 0
    for row in rows:
        batch_count += 1
        for event in json.loads(row["record_json"])["batch"]["events"]:
            event_count += 1
            entity = event["entity"]
            operations["/".join((entity["catalog"], event["graph_type"], event["entity_type"], event["operation"]))] += 1
            evidence.update(_canonical((event["operation"], entity)) + b"\n")
    return event_count, batch_count, operations, evidence.hexdigest()


def _verify_graph(
    observed: Sequence[RuntimeMaterializedRow],
    allocations: Sequence[TaskAllocation],
    source_refs: dict[str, NodeEvidenceReference],
) -> None:
    tasks = {task.task_id: task for task in allocations}
    runs = {task.solver_id: task for task in allocations}
    execution_edges = {
        (task.task_id, f"{task.task_id}:execution-edge:{index}"): (source, target)
        for task in allocations for index, (source, target) in enumerate(task.execution_edges())
    }
    solver_edges = {
        (task.solver_id, f"{task.solver_id}:edge:{index}"): (source, target)
        for task in allocations for index, (source, target) in enumerate(task.solver_edges())
    }
    execution_nodes = {
        (task.task_id, f"{task.task_id}:execution:{index}")
        for task in allocations for index in range(task.execution_nodes)
    }
    solver_nodes = {
        (task.solver_id, f"{task.solver_id}:node:{index}")
        for task in allocations for index in range(task.solver_nodes)
    }
    observations = {
        (task.solver_id, node_id): source.coordinate
        for task in allocations for node_id, source in task.observation_inputs()
    }
    overlays = {
        row.key[0]: RuntimeOverlayVersion.model_validate_json(row.record_json)
        for row in observed if row.catalog == "runtime_overlay_versions"
    }
    for row in observed:
        if row.catalog == "runtime_tasks":
            record = TaskRecord.model_validate_json(row.record_json)
            task = tasks.pop(record.task_id, None)
            if (
                task is None or row.key != (task.task_id,) or record.principal != REFERENCE_PRINCIPAL
                or record.root_execution_node_id != _root_node(task).id
                or record.active_solver_by_execution_node != {_root_node(task).id: task.solver_id}
            ):
                raise ReferenceFixtureError("task root or selected solver does not match its fixture")
        elif row.catalog == "runtime_solver_runs":
            run = SolverRunRecord.model_validate_json(row.record_json)
            task = runs.pop(run.solver_id, None)
            selected = None if run.selected_overlay_id is None else overlays.get(run.selected_overlay_id)
            if (
                task is None or row.key != (task.solver_id,) or row.indexed != (task.task_id,)
                or run.task_id != task.task_id or run.parent_execution_node_id != _root_node(task).id
                or selected is None or selected.solver_id != task.solver_id or not selected.committed
            ):
                raise ReferenceFixtureError("solver run parent or overlay selection is invalid")
        elif row.catalog == "runtime_execution_nodes":
            coordinate = (str(row.key[0]), str(row.key[1]))
            node = ExecutionNode.model_validate_json(row.record_json)
            if coordinate not in execution_nodes or node.id != coordinate[1]:
                raise ReferenceFixtureError("execution node coordinate does not match the fixture")
            execution_nodes.remove(coordinate)
        elif row.catalog == "runtime_solver_nodes":
            coordinate = (str(row.key[0]), str(row.key[1]))
            if coordinate not in solver_nodes:
                raise ReferenceFixtureError("solver node coordinate does not match the fixture")
            solver_nodes.remove(coordinate)
            content = json.loads(row.record_json)["content"]
            source_id = observations.pop(coordinate, None)
            if source_id is None:
                HypothesisContent.model_validate(content)
            elif ObservationContent.model_validate(content).source_refs != (source_refs[source_id],):
                raise ReferenceFixtureError("observation source closure is incomplete")
        elif row.catalog == "runtime_execution_edges":
            edge = ExecutionEdge.model_validate_json(row.record_json)
            if row.key[1] != edge.id or execution_edges.pop((str(row.key[0]), edge.id), None) != (edge.src, edge.dst):
                raise ReferenceFixtureError("execution edge does not match its fixture endpoints")
        elif row.catalog == "runtime_solver_edges":
            stored = SolverEdge.model_validate_json(row.record_json)
            if row.key[1] != stored.id or solver_edges.pop((str(row.key[0]), stored.id), None) != (
                stored.src, stored.dst,
            ):
                raise ReferenceFixtureError("solver edge does not match its fixture endpoints")
        elif row.catalog == "runtime_overlay_versions":
            overlay = overlays[row.key[0]]
            parent = None if overlay.parent_version_id is None else overlays.get(overlay.parent_version_id)
            if (
                row.indexed != (overlay.solver_id,)
                or (overlay.parent_version_id is not None and (parent is None or parent.solver_id != overlay.solver_id))
                or overlay.node_bindings != (OverlayJustificationBinding(
                    node_id=f"{overlay.solver_id}:node:0", frontier=True,
                ),)
            ):
                raise ReferenceFixtureError("overlay references do not match the fixture")
        else:
            raise ReferenceFixtureError("unexpected runtime catalog in fixture")
    if any((tasks, runs, execution_nodes, solver_nodes, execution_edges, solver_edges, observations)):
        raise ReferenceFixtureError("materialized graph is missing allocated records")


def _audit(
    service: StorageAdministrationService,
    distribution: Distribution,
    allocations: Sequence[TaskAllocation],
    *,
    expected_events: int,
    expected_tail: int,
) -> ReferenceStorageAudit:
    graph_digest = hashlib.sha256()
    counts: Counter[str] = Counter()
    partition = service.partition()
    with service.verified_operation_context() as (_state, finalized):
        with partition.transaction(write=False) as connection:
            expected_refs, source_bytes, source_digest, receipt_digest = _audit_native_sources(
                connection, finalized, allocations,
            )
            observed = sorted(
                (row for row in partition.runtime_materialized_rows(connection) if row.catalog not in _SOURCE_RUNTIME_CATALOGS),
                key=lambda row: (row.catalog, row.key),
            )
            _verify_graph(observed, allocations, expected_refs)
            for row in observed:
                counts[row.catalog] += 1
                graph_digest.update(_canonical((row.catalog, row.key, row.indexed, row.record_json)) + b"\n")
            events, batches, operations, event_digest = _event_inventory(connection)
            if events != expected_events or any(len(index) != events for index in partition.runtime_replay_bindings(
                connection,
            )):
                raise ReferenceFixtureError(f"expected {expected_events} verified runtime events, got {events}")
            checkpoint_digest = finalized.checkpoint_digest
            if expected_tail:
                _verify_checkpoint_tail(service, connection, finalized, expected_tail)
            elif checkpoint_digest is not None:
                raise ReferenceFixtureError("unexpected checkpoint in the diagnostic fixture")
        return ReferenceStorageAudit(
            distribution=distribution, workload_digest=hashlib.sha256(workload_manifest(distribution)).hexdigest(),
            generator_digest=hashlib.sha256(Path(workload_manifest.__code__.co_filename).read_bytes()).hexdigest(),
            loader_digest=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            source_driver_digest=hashlib.sha256(Path(ReferenceSourceCapture.capture.__code__.co_filename).read_bytes()).hexdigest(),
            partition_tuple_digest=finalized.payload_digest(), graph_digest=graph_digest.hexdigest(),
            sources_digest=source_digest, source_receipts_digest=receipt_digest, event_inventory_digest=event_digest,
            graph_row_counts=dict(counts), source_count=len(expected_refs), source_receipt_count=len(expected_refs),
            source_body_bytes=source_bytes,
            runtime_event_count=events, runtime_event_batch_count=batches, runtime_operation_counts=dict(operations),
            checkpoint_digest=checkpoint_digest, checkpoint_tail_count=expected_tail,
        )


def _verify_checkpoint_tail(
    service: StorageAdministrationService, connection: sqlite3.Connection,
    finalized: RuntimePublicationState, expected_tail: int,
) -> None:
    digest = finalized.checkpoint_digest
    head = finalized.vector.runtime_position
    if digest is None or not isinstance(head, BatchPosition):
        raise ReferenceFixtureError("reference fixture has no signed checkpoint and tail")
    boundary = connection.execute(
        "SELECT json_extract(record_json, '$.manifest.through_position.sequence') "
        "FROM runtime_replay_checkpoints WHERE checkpoint_digest = ?", (digest,),
    ).fetchone()
    if boundary is None or type(boundary[0]) is not int or head.sequence - boundary[0] != expected_tail:
        raise ReferenceFixtureError("signed checkpoint boundary does not have the exact reference tail")
    rows = connection.execute(
        "SELECT record_json FROM runtime_event_batches WHERE sequence > ? ORDER BY sequence", (boundary[0],),
    )
    for (raw,) in rows:
        events = json.loads(raw)["batch"]["events"]
        if (
            len(events) != 1 or events[0]["operation"] != "update"
            or events[0]["entity"]["catalog"] != "runtime_execution_nodes"
        ):
            raise ReferenceFixtureError("checkpoint tail must contain one execution status update per batch")
    # The released snapshot above verifies checkpoint-plus-tail. Verify the
    # identical head independently through genesis before timing starts.
    verify_runtime_history(
        connection, finalized=finalized,
        verify=lambda purpose, value, signature: service._verify_journal_signature(
            service._signer_key_id, purpose, value, signature,
        ),
        use_checkpoint=False,
    )


def _audit_native_sources(
    connection: sqlite3.Connection, finalized: RuntimePublicationState, allocations: Sequence[TaskAllocation],
) -> tuple[dict[str, NodeEvidenceReference], int, str, str]:
    sources = {}
    for task in allocations:
        for source in task.source_inputs():
            session, _, identity = reference_delivery(source)
            source_id = f"semantic_ingestion:source:{identity.delivery_key_digest}"
            sources[source_id] = (source, session, identity)
    pending = dict(sources)
    references: dict[str, NodeEvidenceReference] = {}
    provider_digests: dict[str, str] = {}
    source_bytes = 0
    source_digest = hashlib.sha256()
    for row in connection.execute(
        "SELECT memory_id, record_json FROM memory_current_records WHERE domain = ? ORDER BY memory_id",
        (MemoryDomain.TRANSCRIPT.value,),
    ):
        record = CanonicalMemoryRecord.model_validate_json(row["record_json"])
        if not record.is_raw_event:
            continue
        descriptor = pending.pop(record.memory_id, None)
        if descriptor is None:
            raise ReferenceFixtureError("unexpected or duplicate retained fixture source")
        source, session, _ = descriptor
        body = record.text.encode("ascii")
        if (
            row["memory_id"] != record.memory_id or record.task_id != source.task_id or record.session_id != session
            or record.timestamp != source.timestamp or body != source.body()
            or record.domain != MemoryDomain.TRANSCRIPT or record.source_kind != "semantic_ingestion_source"
            or record.status != CommitStatus.COMMITTED or record.visibility != MemoryRecordVisibility.INTERNAL_CONTROL
            or record.user_id != REFERENCE_PRINCIPAL
        ):
            raise ReferenceFixtureError("retained source differs from the fixture")
        ref = NodeEvidenceReference(source_id=record.memory_id, source_digest=record_digest(record))
        provider_digests[record.memory_id] = source_admission_source_digest(record)
        references[source.coordinate] = ref
        source_bytes += len(body)
        source_digest.update(_canonical((source.coordinate, ref.source_id, ref.source_digest)) + b"\n")
    if pending:
        raise ReferenceFixtureError("retained fixture sources are missing")

    receipt_digest = hashlib.sha256()
    attempts = {}
    for row in connection.execute(
        "SELECT client_namespace, operation_id, record_json FROM runtime_command_receipts ORDER BY operation_id",
    ):
        receipt = RuntimeCommandReceipt.model_validate_json(row["record_json"])
        origin, admission = receipt.operation_origin, receipt.source_admission
        if origin is None or admission is None or receipt.status != "committed":
            raise ReferenceFixtureError("fixture command receipt lacks native source admission")
        descriptor = sources.pop(admission.source_id, None)
        if descriptor is None:
            raise ReferenceFixtureError("unexpected or duplicate native source receipt")
        source, _, identity = descriptor
        if (
            row["client_namespace"] != operation_origin_namespace(origin) or row["operation_id"] != receipt.operation_id
            or receipt.operation_id != f"{source.coordinate}:observe" or receipt.client_namespace != REFERENCE_NAMESPACE
            or origin.principal != REFERENCE_PRINCIPAL or origin.installation_id != finalized.installation_id
            or origin.repository_id != finalized.repository_id or origin.generation_id != finalized.data_generation_id
            or admission.source_record_digest != references[source.coordinate].source_digest
            or admission.provider_source_digest != provider_digests[admission.source_id]
            or admission.delivery_key_digest != identity.delivery_key_digest
            or admission.task_id != source.task_id or admission.retained_at != source.timestamp
            or admission.source_write_revision > finalized.vector.memory_write_revision
        ):
            raise ReferenceFixtureError("signed observation receipt does not match the exact retained source")
        receipt_digest.update(_canonical((receipt.operation_id, admission.model_dump(mode="json"))) + b"\n")
        receipt_id = canonical_json_digest({"namespace": row["client_namespace"], "operation_id": receipt.operation_id})
        attempts[receipt_id] = (receipt.request_digest, receipt.current_revision)
    if sources:
        raise ReferenceFixtureError("native source receipt closure is incomplete")
    for row in connection.execute(
        "SELECT receipt_id, attempt_ordinal, record_json FROM runtime_operation_attempts ORDER BY receipt_id, attempt_ordinal",
    ):
        attempt = RuntimeOperationAttempt.model_validate_json(row["record_json"])
        if (
            attempt.receipt_id != row["receipt_id"] or row["attempt_ordinal"] != 1 or attempt.attempt_ordinal != 1
            or attempt.stage != "committed" or attempt.model_binding != "no-model" or attempt.invocation_count != 0
            or attempts.pop(attempt.receipt_id, None) != (attempt.request_digest, attempt.base_task_revision)
        ):
            raise ReferenceFixtureError("unexpected or mismatched managed observation attempt")
    if attempts:
        raise ReferenceFixtureError("native source operation attempt closure is incomplete")
    return references, source_bytes, source_digest.hexdigest(), receipt_digest.hexdigest()


def _prepare(
    root: Path,
    distribution: Distribution,
    allocations: Sequence[TaskAllocation],
    *,
    fill: Callable[[int], Iterable[EventFillInput]] | None = None,
) -> ReferenceStorageAudit:
    if root.exists():
        raise ReferenceFixtureError("fixture root already exists; supply a fresh path")
    with StorageAdministrationService(root) as service:
        installation = service.initialize()
        _publish_changes(service, _execution_changes(allocations))
        capture = ReferenceSourceCapture(service, installation, tuple(task.task_id for task in allocations))
        refs = {source.coordinate: capture.capture(source) for task in allocations for source in task.source_inputs()}
        _publish_changes(service, _solver_changes(allocations, refs))
        with service.partition().transaction(write=False) as connection:
            mandatory_events = _event_inventory(connection)[0]
        if fill is None:
            expected_events = mandatory_events
            expected_tail = 0
        else:
            steps = iter(groupby(fill(mandatory_events), key=lambda step: step.checkpoint_tail))
            before = next(steps, None)
            if before is None or before[0]:
                raise ReferenceFixtureError("checkpoint must follow the non-tail reference updates")
            # The generator cycles tasks, so no root repeats within this batch.
            _publish_changes(
                service, _fill_changes(allocations, before[1]), batch_size=len(allocations), checkpoint_at_end=True,
            )
            tail = next(steps, None)
            if tail is None or not tail[0]:
                raise ReferenceFixtureError("reference fixture is missing its checkpoint tail")
            _publish_changes(service, _fill_changes(allocations, tail[1]), batch_size=1)
            if next(steps, None) is not None:
                raise ReferenceFixtureError("non-tail reference event follows the checkpoint tail")
            expected_events, expected_tail = EVENT_COUNT, CHECKPOINT_TAIL_COUNT
    # The fresh process-compatible handle verifies signatures, replay, and
    # projections from bytes on disk rather than trusting our writer cache.
    with StorageAdministrationService(root) as service:
        return _audit(service, distribution, allocations, expected_events=expected_events, expected_tail=expected_tail)


def _installed_wheel_digest(wheel: Path) -> str:
    package_file = Path(memorii.__file__ or "").resolve()
    distribution = installed_distribution("memorii")
    expected_root = Path(str(distribution.locate_file("memorii/__init__.py"))).resolve()
    if package_file != expected_root or not package_file.is_file():
        raise ReferenceFixtureError("fixture driver must import Memorii from the installed wheel")
    with ZipFile(wheel) as artifact:
        package_files = {
            info.filename for info in artifact.infolist()
            if info.filename.startswith("memorii/") and not info.is_dir()
        }
        if "memorii/__init__.py" not in package_files:
            raise ReferenceFixtureError("candidate wheel does not contain the Memorii package")
        installed_files = {
            str(entry) for entry in distribution.files or ()
            if str(entry).startswith("memorii/") and entry.suffix != ".pyc"
        }
        if installed_files != package_files:
            raise ReferenceFixtureError("candidate wheel and installed package inventories differ")
        for name in package_files:
            if Path(str(distribution.locate_file(name))).read_bytes() != artifact.read(name):
                raise ReferenceFixtureError(f"installed package differs from wheel at {name}")
    with wheel.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation-root", required=True, type=Path)
    parser.add_argument("--distribution", required=True, choices=("balanced", "concentrated"))
    parser.add_argument("--candidate-wheel", type=Path)
    parser.add_argument("--require-qualified", action="store_true")
    args = parser.parse_args(argv)
    if args.require_qualified:
        print(json.dumps({"status": "unavailable", "blockers": _QUALIFICATION_BLOCKERS}), file=sys.stderr)
        return 2
    if args.candidate_wheel is None:
        parser.error("diagnostic preparation requires --candidate-wheel")
    wheel_digest = _installed_wheel_digest(args.candidate_wheel)
    distribution: Distribution = args.distribution
    audit = _prepare(
        args.installation_root, distribution, task_allocations(distribution),
        fill=lambda count: event_fill_inputs(distribution, verified_mandatory_events=count),
    )
    print(json.dumps({"status": "diagnostic_only", "candidate_wheel_digest": wheel_digest, **asdict(audit)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
