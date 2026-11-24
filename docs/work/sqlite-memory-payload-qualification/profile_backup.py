"""Attribute the production backup fence on a selected read-only v8 fixture."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from time import monotonic_ns
from unittest.mock import patch

from memorii.core.storage_administration import operator_backup
from memorii.core.storage_administration.operator import (
    StorageAdministrationOperator,
    mint_owner_capability,
)
from memorii.stores.sqlite.partition import RAW_MEMORY_PAYLOAD_SCHEMA_VERSION
from tests.support.reference_capacity_fixture import REFERENCE_PRINCIPAL
from tests.support.reference_capacity_measure import _BackupTimer


def measure_backup(root: Path, archive: Path, *, expected_tuple: str | None = None) -> dict[str, object]:
    """Measure each unchanged online SQLite copy inside the actual operator call."""
    copies: dict[str, dict[str, int]] = {}
    original_copy = operator_backup._sqlite_backup

    def profiled_copy(source: Path, destination: Path) -> None:
        participant = destination.stem
        if participant not in {"control", "partition"} or participant in copies:
            raise RuntimeError(f"unexpected backup copy participant {participant!r}")
        started = monotonic_ns()
        original_copy(source, destination)
        elapsed = monotonic_ns() - started
        copies[participant] = {"elapsed_ns": elapsed, "snapshot_bytes": destination.stat().st_size}

    service = _BackupTimer(root)
    with service:
        verified = service.acquire_verified_snapshot()
        if expected_tuple is not None and verified.tuple_digest != expected_tuple:
            raise RuntimeError("backup fixture tuple differs from the selected signed publication")
        partition = service.partition()
        with partition.transaction(write=False) as connection:
            version = partition.read_schema_version(connection)
        operator = StorageAdministrationOperator(service)
        if version != RAW_MEMORY_PAYLOAD_SCHEMA_VERSION or operator.status().mode != "read_only":
            raise RuntimeError("backup profiling requires an already selected read-only v8 generation")
        capability = mint_owner_capability(service, REFERENCE_PRINCIPAL)
        backups = operator_backup.BackupRestoreOperator(operator)
        key = os.urandom(32)
        with patch.object(operator_backup, "_sqlite_backup", profiled_copy):
            service.recording = True
            started = monotonic_ns()
            try:
                manifest = backups.create_backup(
                    capability=capability,
                    archive_root=archive,
                    reason="raw payload backup fence attribution",
                    recovery_key=key,
                )
                wall = monotonic_ns() - started
            finally:
                service.recording = False

        fence = service.backup_pause_ns
        if fence is None or copies.keys() != {"control", "partition"}:
            raise RuntimeError("backup did not capture the expected publication fence and both participants")
        residual = fence - sum(copy["elapsed_ns"] for copy in copies.values())
        if residual < 0 or fence > wall:
            raise RuntimeError("timed SQLite copies did not fit inside the measured publication fence")
        if manifest.publication_digest != verified.tuple_digest:
            raise RuntimeError("archive did not capture the expected publication")
        checking = monotonic_ns()
        if backups.verify_backup(archive_root=archive) != manifest:
            raise RuntimeError("verified archive manifest differs from the returned manifest")
        archive_check = monotonic_ns() - checking

    return {
        "type": "backup_profile",
        "schema_version": version,
        "tuple_digest": verified.tuple_digest,
        "archive_digest": manifest.manifest_digest,
        "pause_ns": fence,
        "control_copy_ns": copies["control"]["elapsed_ns"],
        "control_snapshot_bytes": copies["control"]["snapshot_bytes"],
        "partition_copy_ns": copies["partition"]["elapsed_ns"],
        "partition_snapshot_bytes": copies["partition"]["snapshot_bytes"],
        "fence_residual_ns": residual,
        "create_backup_wall_ns": wall,
        "archive_check_ns": archive_check,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--expected-tuple")
    args = parser.parse_args()
    result = measure_backup(args.root, args.archive, expected_tuple=args.expected_tuple)
    print(json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
