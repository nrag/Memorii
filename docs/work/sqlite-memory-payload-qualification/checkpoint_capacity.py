"""Measure complete acquisition before and after a generation-local replay checkpoint."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import subprocess
import sys
from collections.abc import Callable
from datetime import timedelta
from itertools import cycle, islice
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic_ns
from typing import ParamSpec, TypeVar
from unittest.mock import patch

from memorii.core.persistence.runtime_contracts import TaskRecord
from memorii.core.persistence.runtime_repository import (
    RuntimeStateRepository,
    publish_runtime_change,
)
from memorii.core.storage_administration import service as storage_service
from memorii.core.storage_administration.operator import (
    InstallationMode,
    ModeChangeRequest,
    StorageAdministrationOperator,
    mint_owner_capability,
)
from memorii.core.storage_administration.service import StorageAdministrationService
from memorii.domain.execution_graph.nodes import ExecutionNode
from memorii.stores.sqlite import materialization_sql
from memorii.stores.sqlite.partition import (
    RAW_MEMORY_PAYLOAD_SCHEMA_VERSION,
    PartitionDataRepository,
)
from tests.support.reference_capacity_fixture import (
    REFERENCE_PRINCIPAL,
    _installed_wheel_digest,
    _verify_checkpoint_tail,
)

_Params = ParamSpec("_Params")
_Result = TypeVar("_Result")


def emit(**values: object) -> None:
    print(json.dumps(values, sort_keys=True), flush=True)


def timed(
    samples: dict[str, int], name: str, operation: Callable[_Params, _Result],
) -> Callable[_Params, _Result]:
    def profile(*args: _Params.args, **kwargs: _Params.kwargs) -> _Result:
        if name in samples:
            raise RuntimeError(f"expected one acquisition pass for {name}")
        started = monotonic_ns()
        result = operation(*args, **kwargs)
        samples[name] = monotonic_ns() - started
        return result

    return profile


def sample(root: Path, expected_tuple: str, checkpoint: bool) -> None:
    components: dict[str, int] = {}
    with StorageAdministrationService(root) as service:
        rebuild = PartitionDataRepository.rebuild_manifest_accumulator
        history = storage_service.verify_runtime_history
        payloads = materialization_sql.verify_raw_payloads
        with (
            patch.object(PartitionDataRepository, "rebuild_manifest_accumulator", timed(components, "manifest_ns", rebuild)),
            patch.object(storage_service, "verify_runtime_history", timed(components, "replay_ns", history)),
            patch.object(materialization_sql, "verify_raw_payloads", timed(components, "raw_payload_verification_ns", payloads)),
        ):
            started = monotonic_ns()
            snapshot = service.acquire_verified_snapshot()
            elapsed = monotonic_ns() - started
        if snapshot.tuple_digest != expected_tuple or len(components) != 3:
            raise RuntimeError("fresh acquisition did not verify the expected staged fixture")
        with service.verified_operation_context() as (_, current):
            if (current.checkpoint_digest is not None) != checkpoint:
                raise RuntimeError("fresh acquisition used an unexpected replay mode")
        emit(type="acquisition", checkpoint_selected=checkpoint, tuple_digest=snapshot.tuple_digest, elapsed_ns=elapsed, **components)


def change_mode(service: StorageAdministrationService, mode: InstallationMode) -> None:
    operator = StorageAdministrationOperator(service)
    owner = mint_owner_capability(service, REFERENCE_PRINCIPAL)
    operator.change_mode(
        ModeChangeRequest(
            target_mode=mode, expected_control_revision=operator.status().control_revision,
            reason="isolated generation-local checkpoint capacity check",
        ),
        capability=owner,
    )


def append_root_update(service: StorageAdministrationService, task: TaskRecord, *, checkpoint: bool = False) -> None:
    def apply(connection: sqlite3.Connection, repository: RuntimeStateRepository) -> None:
        row = repository.partition.read_runtime_row(
            connection, table="runtime_execution_nodes",
            match=(("task_id", task.task_id), ("node_id", task.root_execution_node_id)),
        )
        if row is None:
            raise RuntimeError("fixture has a missing execution root")
        node = ExecutionNode.model_validate_json(row["record_json"])
        updated = node.model_copy(update={"updated_at": node.updated_at + timedelta(microseconds=1)})
        repository.apply_execution_node(
            connection, task_id=task.task_id, node_id=updated.id, node_json=updated.model_dump_json(),
        )

    publish_runtime_change(service, apply, checkpoint_requested=checkpoint)


def seal_checkpoint(root: Path, expected_tuple: str, tail: int) -> str:
    with StorageAdministrationService(root) as service:
        partition = service.partition()
        with service.verified_operation_context() as (state, before), partition.transaction(write=False) as connection:
            if (
                before.payload_digest() != expected_tuple or before.checkpoint_digest is not None
                or state.mode != "read_only" or partition.read_schema_version(connection) != RAW_MEMORY_PAYLOAD_SCHEMA_VERSION
            ):
                raise RuntimeError("checkpoint seeding requires the reviewed read-only raw upgrade")
            tasks = tuple(TaskRecord.model_validate_json(row[0]) for row in connection.execute(
                "SELECT record_json FROM runtime_tasks ORDER BY task_id"
            ))
        if not tasks:
            raise RuntimeError("fixture has no execution roots")
        change_mode(service, "active")
        append_root_update(service, tasks[0], checkpoint=True)
        for task in islice(cycle(tasks), tail):
            append_root_update(service, task)
        change_mode(service, "read_only")

    with StorageAdministrationService(root) as service:
        with service.verified_operation_context() as (_state, after), service.partition().transaction(write=False) as connection:
            if (
                before.data_generation_id != after.data_generation_id
                or before.vector.memory_write_revision != after.vector.memory_write_revision
                or before.vector.memory_data_revision != after.vector.memory_data_revision
                or before.vector.semantic_position != after.vector.semantic_position
                or before.vector.ontology_pointer_digest != after.vector.ontology_pointer_digest
            ):
                raise RuntimeError("checkpoint publication changed protected fixture state")
            _verify_checkpoint_tail(service, connection, after, expected_tail=tail)
            boundary = connection.execute(
                "SELECT json_extract(record_json, '$.manifest.partition_schema'),"
                " json_extract(record_json, '$.manifest.generation_id')"
                " FROM runtime_replay_checkpoints WHERE checkpoint_digest=?",
                (after.checkpoint_digest,),
            ).fetchone()
            if boundary is None or tuple(boundary) != (RAW_MEMORY_PAYLOAD_SCHEMA_VERSION, after.data_generation_id):
                raise RuntimeError("checkpoint is outside the upgraded generation")
        digest = after.payload_digest()
        emit(
            type="checkpoint", input_tuple=expected_tuple, tuple_digest=digest, digest=after.checkpoint_digest,
            generation_id=after.data_generation_id, tail_events=tail,
            memory_write_revision=after.vector.memory_write_revision, independent_genesis_replay=True,
        )
        return digest


def run_trials(root: Path, expected_tuple: str, wheel: Path, tail: int, samples: int) -> None:
    script = Path(__file__)
    profiler = script.with_name("profile_backup.py")
    emit(
        type="identity", wheel_digest=_installed_wheel_digest(wheel),
        runner_digest=hashlib.sha256(script.read_bytes()).hexdigest(),
        profiler_digest=hashlib.sha256(profiler.read_bytes()).hexdigest(),
        sqlite_version=sqlite3.sqlite_version,
    )
    args = [sys.executable, str(script), "--root", str(root), "--sample", "--expected-tuple"]
    for _ in range(samples):
        subprocess.run([*args, expected_tuple], check=True)
    checkpointed = seal_checkpoint(root, expected_tuple, tail)
    for _ in range(samples):
        subprocess.run([*args, checkpointed, "--checkpoint"], check=True)
    for _ in range(samples):
        with TemporaryDirectory(prefix="raw-backup-profile-", dir=root.parent) as scratch:
            subprocess.run(
                [
                    sys.executable, str(profiler), "--root", str(root), "--archive", str(Path(scratch) / "archive"),
                    "--expected-tuple", checkpointed,
                ],
                check=True,
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--expected-tuple", required=True)
    parser.add_argument("--sample", action="store_true")
    parser.add_argument("--checkpoint", action="store_true")
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--tail", type=int, default=1_000)
    args = parser.parse_args()
    if args.sample:
        sample(args.root, args.expected_tuple, args.checkpoint)
    elif args.wheel is not None and args.samples >= 1 and args.tail >= 1:
        run_trials(args.root, args.expected_tuple, args.wheel, args.tail, args.samples)
    else:
        parser.error("provide --wheel and positive sample and tail counts")


if __name__ == "__main__":
    main()
