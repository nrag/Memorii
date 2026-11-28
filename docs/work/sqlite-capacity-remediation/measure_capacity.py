"""Rerun installed v8 acquisition and backup on a retained signed fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic_ns
from unittest.mock import patch

from memorii.core.storage_administration import operator_backup
from memorii.core.storage_administration.operator import (
    StorageAdministrationOperator,
    mint_owner_capability,
)
from tests.support.reference_capacity_fixture import (
    REFERENCE_PRINCIPAL,
    _installed_wheel_digest,
)
from tests.support.reference_capacity_measure import _BackupTimer


def emit(**values: object) -> None:
    print(json.dumps(values, sort_keys=True), flush=True)


def backup_sample(root: Path, expected_tuple: str, archive: Path) -> None:
    service = _BackupTimer(root)
    copies: dict[str, tuple[int, int]] = {}
    original_copy = operator_backup._sqlite_backup

    def profile_copy(source: sqlite3.Connection, destination: Path) -> None:
        if service.inside_backup_fence or destination.stem in copies:
            raise RuntimeError("unexpected online copy inside publication fence or duplicate copy")
        started = monotonic_ns()
        original_copy(source, destination)
        copies[destination.stem] = monotonic_ns() - started, destination.stat().st_size

    with service:
        signed = service.acquire_verified_snapshot()
        if signed.tuple_digest != expected_tuple:
            raise RuntimeError("backup sample does not bind the retained signed fixture")
        operator = StorageAdministrationOperator(service)
        if operator.status().mode != "read_only":
            raise RuntimeError("backup sample requires read-only authorization mode")
        owner = mint_owner_capability(service, REFERENCE_PRINCIPAL)
        backups = operator_backup.BackupRestoreOperator(operator)
        with patch.object(operator_backup, "_sqlite_backup", profile_copy):
            service.recording = True
            started = monotonic_ns()
            try:
                manifest = backups.create_backup(
                    capability=owner, archive_root=archive, reason="short backup fence capacity diagnostic",
                    recovery_key=os.urandom(32),
                )
            finally:
                service.recording = False
            wall = monotonic_ns() - started
        holds = service.backup_holds_ns
        if set(copies) != {"control", "partition"} or len(holds) != 2:
            raise RuntimeError("expected two SQLite copies and two short publication fences")
        if manifest.publication_digest != expected_tuple or backups.verify_backup(archive_root=archive) != manifest:
            raise RuntimeError("installed archive failed signed watermark verification")
        emit(
            type="backup", tuple_digest=expected_tuple, archive_digest=manifest.manifest_digest, total_wall_ns=wall,
            fence_holds_ns=holds, pause_ns=sum(holds), longest_hold_ns=max(holds),
            control_copy_ns=copies["control"][0], control_bytes=copies["control"][1],
            partition_copy_ns=copies["partition"][0], partition_bytes=copies["partition"][1],
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--expected-tuple", required=True)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--samples", type=int, default=3)
    args = parser.parse_args()
    if args.archive is not None:
        backup_sample(args.root, args.expected_tuple, args.archive)
        return
    if args.wheel is None or args.samples < 1:
        parser.error("provide the installed wheel and a positive sample count")
    script = Path(__file__)
    acquire_script = script.with_name("checkpoint_capacity.py")
    emit(
        type="identity", wheel_digest=_installed_wheel_digest(args.wheel), sqlite_version=sqlite3.sqlite_version,
        runner_digest=hashlib.sha256(script.read_bytes()).hexdigest(),
        acquisition_runner_digest=hashlib.sha256(acquire_script.read_bytes()).hexdigest(),
    )
    shared = ["--root", str(args.root), "--expected-tuple", args.expected_tuple]
    for _ in range(args.samples):
        subprocess.run([sys.executable, str(acquire_script), *shared, "--sample", "--checkpoint"], check=True)
    for _ in range(args.samples):
        with TemporaryDirectory(prefix="v8-short-fence-", dir=args.root.parent) as scratch:
            subprocess.run(
                [sys.executable, str(script), *shared, "--archive", str(Path(scratch) / "archive")], check=True,
            )


if __name__ == "__main__":
    main()
