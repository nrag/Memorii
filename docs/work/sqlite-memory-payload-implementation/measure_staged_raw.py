"""Measure owner-staged SQLite raw payload acquisition and backup on inert fixtures."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic_ns

from memorii.core.storage_administration.operator import (
    ModeChangeRequest,
    StorageAdministrationOperator,
    mint_owner_capability,
)
from memorii.core.storage_administration.operator_backup import BackupRestoreOperator
from memorii.stores.sqlite.partition import (
    PARTITION_SCHEMA_VERSION,
    RAW_MEMORY_PAYLOAD_SCHEMA_VERSION,
)
from tests.support.reference_capacity_fixture import (
    REFERENCE_PRINCIPAL,
    _installed_wheel_digest,
)
from tests.support.reference_capacity_measure import _BackupTimer, _fresh_copy


def emit(**fields: object) -> None:
    print(json.dumps(fields, sort_keys=True), flush=True)


def snapshot(root: Path, archive: Path | None) -> None:
    service = _BackupTimer(root)
    with service:
        started = monotonic_ns()
        verified = service.acquire_verified_snapshot()
        acquired_ns = monotonic_ns() - started
        partition = service.partition()
        with partition.transaction(write=False) as connection:
            version = partition.read_schema_version(connection)
            locator = connection.execute(
                "SELECT memory_id FROM memory_current_records WHERE source_kind = 'semantic_ingestion_source'"
                " ORDER BY memory_id LIMIT 1"
            ).fetchone()
        if version != RAW_MEMORY_PAYLOAD_SCHEMA_VERSION:
            raise RuntimeError("fresh acquisition did not use the staged raw format")
        if archive is None:
            if locator is None:
                raise RuntimeError("fixture is missing its native source sample")
            store = service.memory_plane_store()
            started = monotonic_ns()
            record = store.get_record(locator[0])
            first_read_ns = monotonic_ns() - started
            if record is None or record.memory_id != locator[0]:
                raise RuntimeError("released record does not match the fixture")
            emit(
                type="acquisition", elapsed_ns=acquired_ns, first_read_ns=first_read_ns,
                tuple_digest=verified.tuple_digest, schema_version=version,
                checkpoint_selected=_has_selected_checkpoint(service),
            )
            return

        operator = StorageAdministrationOperator(service)
        owner = mint_owner_capability(service, REFERENCE_PRINCIPAL)
        service.recording = True
        result = BackupRestoreOperator(operator).create_backup(
            capability=owner, archive_root=archive, reason="raw payload capacity diagnostic",
            recovery_key=os.urandom(32),
        )
        if service.backup_pause_ns is None or result.publication_digest != verified.tuple_digest:
            raise RuntimeError("the actual backup did not capture the verified publication")
        emit(
            type="backup", pause_ns=service.backup_pause_ns, tuple_digest=verified.tuple_digest,
            archive_digest=result.manifest_digest, schema_version=version,
        )


def _has_selected_checkpoint(service: _BackupTimer) -> bool:
    with service.verified_operation_context() as (_, state):
        return state.checkpoint_digest is not None


def stage(root: Path, expected_tuple: str) -> None:
    service = _BackupTimer(root)
    with TemporaryDirectory(prefix="raw-upgrade-source-", dir=root.parent) as scratch, service:
        original = service.acquire_verified_snapshot()
        if original.tuple_digest != expected_tuple:
            raise RuntimeError("the input fixture tuple changed")
        original_path = service.partition_path()
        source_size = original_path.stat().st_size
        partition = service.partition()
        with partition.transaction(write=False) as connection:
            if partition.read_schema_version(connection) != PARTITION_SCHEMA_VERSION:
                raise RuntimeError("the input fixture is not v7")
        owner = mint_owner_capability(service, REFERENCE_PRINCIPAL)
        operator = StorageAdministrationOperator(service)
        operator.change_mode(
            ModeChangeRequest(
                target_mode="read_only", expected_control_revision=operator.status().control_revision,
                reason="raw payload capacity diagnostic",
            ),
            capability=owner,
        )
        service.acquire_verified_snapshot()
        backups = BackupRestoreOperator(operator)
        recovery_key = os.urandom(32)
        archive = Path(scratch) / "archive"
        staging = Path(scratch) / "stage"
        service.recording = True
        backups.create_backup(
            capability=owner, archive_root=archive, reason="raw payload upgrade source",
            recovery_key=recovery_key,
        )
        service.recording = False
        if service.backup_pause_ns is None:
            raise RuntimeError("the source backup did not return a publication barrier measurement")
        emit(type="v7_backup", pause_ns=service.backup_pause_ns, database_bytes=source_size)
        plan = backups.plan_restore(capability=owner, archive_root=archive, data_loss_acknowledged=False)
        backups.apply_restore(capability=owner, plan=plan, staging_root=staging, recovery_key=recovery_key)
        preview = backups.preview_staged_restore(
            capability=owner, plan=plan, staging_root=staging, raw_payloads=True,
        )
        started = monotonic_ns()
        intent = backups.upgrade_current_runtime(
            capability=owner, plan=plan, staging_root=staging, preview_digest=preview.digest(), raw_payloads=True,
        )
        if intent.phase != "finalized" or not original_path.is_file():
            raise RuntimeError("the owner-authorized upgrade did not finalize with rollback data")
        emit(
            type="selected", elapsed_ns=monotonic_ns() - started,
            before_tuple=original.tuple_digest, preview_digest=preview.digest(),
            after_tuple=intent.candidate_publication.payload_digest(),
            database_bytes=service.partition_path().stat().st_size,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--work", type=Path)
    parser.add_argument("--tuple")
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--sample", choices=("acquisition", "backup"))
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    if args.sample:
        if args.sample == "backup" and args.archive is None:
            parser.error("backup sampling needs an archive destination")
        snapshot(args.base, args.archive)
        return
    if args.work is None or args.tuple is None or args.wheel is None or args.samples < 1:
        parser.error("provide --work, --tuple, --wheel and a positive sample count")
    emit(
        type="identity", candidate_wheel_digest=_installed_wheel_digest(args.wheel),
        runner_digest=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    )
    with _fresh_copy(args.base, args.work) as root:
        stage(root, args.tuple)
        for operation in ("acquisition", "backup"):
            for sample in range(args.samples):
                with TemporaryDirectory(prefix="raw-sample-", dir=root.parent) as scratch:
                    command = [sys.executable, __file__, "--base", str(root), "--sample", operation]
                    if operation == "backup":
                        command.extend(("--archive", str(Path(scratch) / "archive")))
                    try:
                        subprocess.run(command, check=True)
                    except subprocess.CalledProcessError:
                        emit(type="failed", operation=operation, sample=sample)
                        raise


if __name__ == "__main__":
    main()
