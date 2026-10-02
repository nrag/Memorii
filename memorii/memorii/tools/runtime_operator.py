"""``memorii-operator``: owner CLI over the operator control surface.

Commands bind the implemented operator owners: status, mode, export,
backup create/verify, restore plan, forget plan, erasure plan, retention
plan, doctor. Every destructive command requires the owner capability
(principal + digest) and prints its plan for review before apply flags
are accepted. Machine JSON and readable output carry the same status.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="memorii-operator",
        description="Owner-only operator controls over one installation.",
    )
    parser.add_argument("--installation-root", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("status", help="Content-free installation status")
    commands.add_parser("doctor", help="Read-only health checks")

    mode = commands.add_parser("mode", help="Change the installation mode")
    mode.add_argument("--target", choices=("active", "read_only", "bypass"), required=True)
    mode.add_argument("--expected-revision", type=int, required=True)
    mode.add_argument("--reason", required=True)

    backup = commands.add_parser("backup", help="Backup operations")
    backup_sub = backup.add_subparsers(dest="backup_command", required=True)
    create = backup_sub.add_parser("create", help="Create a backup archive")
    create.add_argument("--archive-root", type=Path, required=True)
    create.add_argument("--reason", required=True)
    create.add_argument(
        "--recovery-key-hex",
        required=True,
        help="64 hex chars; the 32-byte operator recovery key wrapping the archive content key",
    )
    verify = backup_sub.add_parser("verify", help="Verify an archive")
    verify.add_argument("--archive-root", type=Path, required=True)
    restore = backup_sub.add_parser("restore-plan", help="Plan a restore")
    restore.add_argument("--archive-root", type=Path, required=True)
    restore.add_argument("--data-loss-acknowledged", action="store_true")
    restore.add_argument("--recovery-key-hex", required=True)

    forget = commands.add_parser("forget", help="Logical forget planning")
    forget.add_argument("--scope-note", required=True)

    erasure = commands.add_parser("erasure", help="Whole-partition erasure planning")
    erasure.add_argument("--offline-copies", default="")

    retention = commands.add_parser("retention", help="Retention planning")
    retention.add_argument("--older-than-days", type=int, required=True)

    common = parser.add_argument_group("owner capability")
    common.add_argument("--owner-principal", default="")
    common.add_argument("--capability-digest", default="")

    arguments = parser.parse_args(argv)

    from memorii.core.storage_administration.operator import (
        ModeChangeRequest,
        OperatorError,
        OwnerCapability,
        StorageAdministrationOperator,
    )
    from memorii.core.storage_administration.service import (
        StorageAdministrationService,
    )
    from memorii.core.storage_administration.writer_enrollment import (
        WriterEnrollmentRegistry,
    )

    administration = StorageAdministrationService(
        arguments.installation_root,
        writer_enrollment=WriterEnrollmentRegistry(
            arguments.installation_root / "control" / "writers"
        ),
    )
    operator = StorageAdministrationOperator(administration)
    capability = (
        OwnerCapability(
            owner_principal=arguments.owner_principal,
            capability_digest=arguments.capability_digest,
        )
        if arguments.owner_principal and arguments.capability_digest
        else None
    )

    def require_capability() -> OwnerCapability:
        if capability is None:
            print(
                "invalid_request: --owner-principal and --capability-digest are required",
                file=sys.stderr,
            )
            sys.exit(2)
        return capability

    try:
        if arguments.command == "status":
            print(operator.status().model_dump_json())
            return 0
        if arguments.command == "doctor":
            from memorii.core.storage_administration.operator_governance import (
                GovernanceOperator,
            )

            findings = GovernanceOperator(operator).doctor()
            print(json.dumps([f.model_dump() for f in findings], sort_keys=True))
            return 0
        if arguments.command == "mode":
            status = operator.change_mode(
                ModeChangeRequest(
                    target_mode=arguments.target,
                    expected_control_revision=arguments.expected_revision,
                    reason=arguments.reason,
                ),
                capability=require_capability(),
            )
            print(status.model_dump_json())
            return 0
        if arguments.command == "backup":
            from memorii.core.storage_administration.operator_backup import (
                BackupRestoreOperator,
            )

            backups = BackupRestoreOperator(operator)
            if arguments.backup_command == "create":
                manifest = backups.create_backup(
                    capability=require_capability(),
                    archive_root=arguments.archive_root,
                    reason=arguments.reason,
                    recovery_key=bytes.fromhex(arguments.recovery_key_hex),
                )
                print(manifest.model_dump_json())
                return 0
            if arguments.backup_command == "verify":
                manifest = backups.verify_backup(archive_root=arguments.archive_root)
                print(manifest.model_dump_json())
                return 0
            bytes.fromhex(arguments.recovery_key_hex)  # shape-validated now
            plan = backups.plan_restore(
                capability=require_capability(),
                archive_root=arguments.archive_root,
                data_loss_acknowledged=arguments.data_loss_acknowledged,
            )
            print(plan.model_dump_json())
            return 0
        if arguments.command == "forget":
            from memorii.core.storage_administration.operator_governance import (
                GovernanceOperator,
            )

            plan = GovernanceOperator(operator).plan_forget(
                capability=require_capability(), scope_note=arguments.scope_note
            )
            print(plan.model_dump_json())
            return 0
        if arguments.command == "erasure":
            from memorii.core.storage_administration.operator_governance import (
                GovernanceOperator,
            )

            plan = GovernanceOperator(operator).plan_erasure(
                capability=require_capability(),
                offline_copies_accounted=tuple(
                    item.strip()
                    for item in arguments.offline_copies.split(",")
                    if item.strip()
                ),
            )
            print(plan.model_dump_json())
            return 0
        if arguments.command == "retention":
            from memorii.core.storage_administration.operator_governance import (
                GovernanceOperator,
            )

            plan = GovernanceOperator(operator).plan_retention(
                capability=require_capability(),
                older_than_days=arguments.older_than_days,
            )
            print(plan.model_dump_json())
            return 0
        parser.error(f"unknown command {arguments.command}")
        return 2
    except OperatorError as error:
        print(str(error), file=sys.stderr)
        return 3
    finally:
        administration.close()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
