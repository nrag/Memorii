"""Create a disposable owner-upgraded v8 fixture for installed capacity checks."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic_ns

from memorii.core.storage_administration.operator import (
    ModeChangeRequest,
    StorageAdministrationOperator,
    mint_owner_capability,
)
from memorii.core.storage_administration.operator_backup import BackupRestoreOperator
from memorii.core.storage_administration.service import StorageAdministrationService


def stage(base: Path, root: Path, expected_tuple: str) -> None:
    root.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(base, root)
    print(json.dumps({"type": "cloned", "root": str(root)}), flush=True)
    with TemporaryDirectory(prefix="v8-source-", dir=root.parent) as scratch_dir, StorageAdministrationService(root) as service:
        source = service.acquire_verified_snapshot()
        if source.tuple_digest != expected_tuple:
            raise RuntimeError("frozen source does not match the audited tuple")
        owner = mint_owner_capability(service, "owner:capacity")
        operator = StorageAdministrationOperator(service)
        operator.change_mode(
            ModeChangeRequest(
                target_mode="read_only", expected_control_revision=operator.status().control_revision,
                reason="staged raw checkpoint and backup capacity check",
            ),
            capability=owner,
        )
        backups = BackupRestoreOperator(operator)
        archive = Path(scratch_dir) / "archive"
        staging = Path(scratch_dir) / "stage"
        recovery_key = os.urandom(32)
        backups.create_backup(
            capability=owner, archive_root=archive, reason="synthetic upgrade source", recovery_key=recovery_key,
        )
        plan = backups.plan_restore(capability=owner, archive_root=archive, data_loss_acknowledged=False)
        backups.apply_restore(capability=owner, plan=plan, staging_root=staging, recovery_key=recovery_key)
        # Subsequent operations bind the independently attested plaintext stage.
        shutil.rmtree(archive)
        print(json.dumps({"type": "attested", "source_tuple": source.tuple_digest}), flush=True)

        preview = backups.preview_staged_restore(capability=owner, plan=plan, staging_root=staging, raw_payloads=True)
        started = monotonic_ns()
        intent = backups.upgrade_current_runtime(
            capability=owner, plan=plan, staging_root=staging, preview_digest=preview.digest(), raw_payloads=True,
        )
        if intent.phase != "finalized":
            raise RuntimeError("raw fixture upgrade did not select the staged generation")
        print(json.dumps({
            "type": "selected", "tuple_digest": intent.candidate_publication.payload_digest(),
            "generation_id": intent.candidate_publication.data_generation_id,
            "elapsed_ns": monotonic_ns() - started, "database_bytes": service.partition_path().stat().st_size,
        }), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--expected-tuple", required=True)
    args = parser.parse_args()
    stage(args.base, args.root, args.expected_tuple)


if __name__ == "__main__":
    main()
