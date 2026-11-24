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
import os
import stat
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
    restore.add_argument("--recovery-key-hex", help=argparse.SUPPRESS)
    stage = backup_sub.add_parser("restore-stage", help="Verify and stage a reviewed restore without activating it")
    stage.add_argument("--plan-file", type=Path, required=True)
    stage.add_argument("--staging-root", type=Path, required=True)
    stage.add_argument("--recovery-key-file", type=Path, required=True, help="Owner-only file with the 32-byte raw key")
    verify_stage = backup_sub.add_parser("restore-verify-stage", help="Reverify an inert restore stage against the reviewed plan")
    verify_stage.add_argument("--plan-file", type=Path, required=True)
    verify_stage.add_argument("--staging-root", type=Path, required=True)
    preview_stage = backup_sub.add_parser(
        "restore-preview-stage", help="Compare signed command and delivery inventories before restore",
    )
    preview_stage.add_argument("--plan-file", type=Path, required=True)
    preview_stage.add_argument("--staging-root", type=Path, required=True)
    activate_current = backup_sub.add_parser(
        "restore-activate-current", help="Select a verified staged backup at the exact live watermark",
    )
    activate_current.add_argument("--plan-file", type=Path, required=True)
    activate_current.add_argument("--staging-root", type=Path, required=True)

    forget = commands.add_parser("forget", help="Logical forget planning and apply")
    forget_sub = forget.add_subparsers(dest="forget_command", required=True)
    forget_plan = forget_sub.add_parser("plan", help="Resolve typed selectors into a closure")
    forget_plan.add_argument("--scope-note", required=True)
    forget_plan.add_argument(
        "--entity", action="append", default=[],
        help="opaque logical entity id (repeatable)",
    )
    forget_plan.add_argument(
        "--claim", action="append", default=[],
        help="opaque claim assertion id (repeatable)",
    )
    forget_plan.add_argument(
        "--source", action="append", default=[],
        help="opaque source id (repeatable)",
    )
    forget_plan.add_argument(
        "--record", action="append", default=[],
        help="opaque record coordinate kind=id (repeatable)",
    )
    forget_apply = forget_sub.add_parser("apply", help="Apply a reviewed plan")
    forget_apply.add_argument("--plan-json", required=True)
    forget_sub.add_parser(
        "enforce",
        help="Drain pending forget enforcements (directive + tombstones)",
    )

    erasure = commands.add_parser("erasure", help="Whole-partition erasure planning")
    erasure.add_argument("--offline-copies", default="")

    retention = commands.add_parser("retention", help="Retention planning")
    retention.add_argument("--older-than-days", type=int, required=True)

    grant = commands.add_parser("runtime-grant", help="Provision finite host command and writeback authority")
    grant_sub = grant.add_subparsers(dest="grant_command", required=True)
    grant_issue = grant_sub.add_parser("issue", help="Issue one finite host command grant")
    grant_issue.add_argument("--grant-id", required=True)
    grant_issue.add_argument("--credential-id", required=True)
    grant_issue.add_argument("--principal", required=True)
    grant_issue.add_argument("--client-namespace", required=True)
    grant_issue.add_argument("--kind", action="append", default=[])
    grant_issue.add_argument("--task-id", action="append", default=[])
    grant_issue.add_argument("--operation-id", action="append", default=[])
    grant_issue.add_argument(
        "--writeback-scope", action="append", default=[],
        help="closed writeback target scope JSON with kind, partition_id, and task_id (repeatable)",
    )
    grant_issue.add_argument("--expires-at", required=True, help="ISO-8601 timestamp with offset")
    grant_revoke = grant_sub.add_parser("revoke", help="Revoke one host command grant")
    grant_revoke.add_argument("--grant-id", required=True)

    source_grant = commands.add_parser("runtime-source-grant", help="Manage durable provider source release")
    source_grant_sub = source_grant.add_subparsers(dest="source_grant_command", required=True)
    source_grant_revoke = source_grant_sub.add_parser("revoke", help="Revoke one exact task/source release grant")
    source_grant_revoke.add_argument("--grant-id", required=True)

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
                RestorePlan,
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
            if arguments.backup_command in {
                "restore-verify-stage", "restore-preview-stage", "restore-activate-current",
            }:
                from pydantic import ValidationError

                owner = require_capability()
                try:
                    plan = RestorePlan.model_validate_json(arguments.plan_file.read_bytes())
                except (ValidationError, OSError) as exc:
                    raise OperatorError("invalid_request: restore plan could not be read") from exc
                if arguments.backup_command == "restore-preview-stage":
                    preview = backups.preview_staged_restore(
                        capability=owner, plan=plan, staging_root=arguments.staging_root,
                    )
                    print(preview.model_dump_json())
                    return 0
                if arguments.backup_command == "restore-activate-current":
                    try:
                        selector = backups.activate_exact_current_restore(
                            capability=owner, plan=plan, staging_root=arguments.staging_root,
                        )
                    except OSError as exc:
                        raise OperatorError("unavailable: exact-current restore selection could not be published") from exc
                    print(json.dumps({
                        "status": "selected", "generation_id": selector.generation_id, "reopen_required": True,
                    }, sort_keys=True))
                    return 0
                attestation = backups.verify_staged_restore(
                    capability=owner, plan=plan, staging_root=arguments.staging_root,
                )
                print(attestation.model_dump_json())
                return 0
            if arguments.backup_command == "restore-stage":
                from cryptography.exceptions import InvalidTag
                from pydantic import ValidationError

                owner = require_capability()
                try:
                    plan = RestorePlan.model_validate_json(arguments.plan_file.read_bytes())
                    with os.fdopen(
                        os.open(arguments.recovery_key_file, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK),
                        "rb",
                    ) as key_file:
                        file_state = os.fstat(key_file.fileno())
                        if (
                            not stat.S_ISREG(file_state.st_mode)
                            or file_state.st_uid != os.geteuid()
                            or file_state.st_mode & 0o077
                        ):
                            raise OperatorError("denied: recovery key must be a regular owner-only file")
                        recovery_key = key_file.read(33)
                except (ValidationError, OSError) as exc:
                    raise OperatorError("invalid_request: restore plan or recovery key could not be read") from exc
                try:
                    staged = backups.apply_restore(
                        capability=owner, plan=plan, staging_root=arguments.staging_root,
                        recovery_key=recovery_key,
                    )
                except InvalidTag as exc:
                    raise OperatorError("denied: recovery key did not authenticate the archive") from exc
                except OSError as exc:
                    raise OperatorError("unavailable: restore staging could not be published") from exc
                print(json.dumps({"status": "staged", "path": str(staged)}, sort_keys=True))
                return 0
            plan = backups.plan_restore(
                capability=require_capability(),
                archive_root=arguments.archive_root,
                data_loss_acknowledged=arguments.data_loss_acknowledged,
            )
            print(plan.model_dump_json())
            return 0
        if arguments.command == "runtime-source-grant":
            from memorii.core.persistence.runtime_repository import RuntimeStateError
            from memorii.core.provider.runtime_source_authority import RuntimeSourceAuthorityError
            from memorii.core.provider.runtime_source_release import RuntimeSourceReleaseAuthority
            from memorii.core.storage_administration.service import StorageAdministrationError

            try:
                release = RuntimeSourceReleaseAuthority(administration).revoke(
                    capability=require_capability(), grant_id=arguments.grant_id,
                )
            except (RuntimeSourceAuthorityError, RuntimeStateError, StorageAdministrationError) as exc:
                raise OperatorError(str(exc)) from exc
            print(json.dumps({"grant_id": release.grant_id, "status": release.status}, sort_keys=True))
            return 0
        if arguments.command == "runtime-grant":
            from datetime import datetime

            from pydantic import TypeAdapter, ValidationError

            from memorii.core.harness_state.write_authority import (
                HostCommandAuthorityError,
                HostCommandGrantRequest,
                ManagedHostCommandAuthority,
            )
            from memorii.core.persistence.writeback_decisions import CandidateScope

            authority = ManagedHostCommandAuthority(administration)
            if arguments.grant_command == "revoke":
                try:
                    epoch = authority.revoke(
                        arguments.grant_id, capability=require_capability()
                    )
                except HostCommandAuthorityError as exc:
                    raise OperatorError(str(exc)) from exc
                print(
                    json.dumps(
                        {"grant_id": arguments.grant_id, "epoch": epoch},
                        sort_keys=True,
                    )
                )
                return 0
            try:
                expires_at = datetime.fromisoformat(arguments.expires_at)
            except ValueError as exc:
                raise OperatorError(
                    "invalid_request: --expires-at must be ISO-8601"
                ) from exc
            scope_parser = TypeAdapter[CandidateScope](CandidateScope)
            try:
                grant_request = HostCommandGrantRequest(
                    grant_id=arguments.grant_id,
                    credential_id=arguments.credential_id,
                    principal=arguments.principal,
                    client_namespace=arguments.client_namespace,
                    allowed_kinds=tuple(arguments.kind),
                    allowed_task_ids=tuple(arguments.task_id),
                    allowed_operation_ids=tuple(arguments.operation_id),
                    allowed_writeback_scopes=tuple(
                        scope_parser.validate_json(raw) for raw in arguments.writeback_scope
                    ),
                    expires_at=expires_at,
                )
            except ValidationError as exc:
                raise OperatorError("invalid_request: runtime grant scope is invalid") from exc
            try:
                issued = authority.issue(grant_request, capability=require_capability())
            except HostCommandAuthorityError as exc:
                raise OperatorError(str(exc)) from exc
            print(issued.model_dump_json())
            return 0
        if arguments.command == "forget":
            from memorii.core.storage_administration.operator_governance import (
                ForgetPlan,
                ForgetTargetSelector,
                GovernanceOperator,
            )

            governance = GovernanceOperator(operator)
            if arguments.forget_command == "plan":
                selectors: list[ForgetTargetSelector] = [
                    *(ForgetTargetSelector(selector_kind="entity", selector_id=item)
                      for item in arguments.entity),
                    *(ForgetTargetSelector(selector_kind="claim", selector_id=item)
                      for item in arguments.claim),
                    *(ForgetTargetSelector(selector_kind="source", selector_id=item)
                      for item in arguments.source),
                    *(
                        ForgetTargetSelector(
                            selector_kind="record",
                            selector_id=item.split("=", 1)[1],
                            record_kind=item.split("=", 1)[0] or None,
                        )
                        for item in arguments.record
                        if "=" in item
                    ),
                ]
                plan = governance.plan_forget(
                    capability=require_capability(),
                    selectors=tuple(selectors),
                    scope_note=arguments.scope_note,
                )
                print(plan.model_dump_json())
                return 0
            if arguments.forget_command != "apply":
                raise ValueError(
                    f"unsupported forget command: {arguments.forget_command}"
                )
            plan = ForgetPlan.model_validate(json.loads(arguments.plan_json))
            receipt = governance.apply_forget(
                capability=require_capability(), plan=plan
            )
            print(receipt.model_dump_json())
            return 0
        if arguments.command == "forget" and arguments.forget_command == "enforce":
            # Drains every journal entry that lacks its directive through
            # the governance publication entry (same path the mode-resume
            # drain uses when a composed runtime is live).
            from memorii.core.memory_evolution.atomic_store import (
                SemanticIngestionAtomicStore,
            )
            from memorii.core.memory_evolution.graph_records import (
                canonical_graph_codec_manifest,
            )
            from memorii.core.memory_evolution.writer_admission import (
                SemanticWriterAdmissionStore,
                bounded_preplanning_ownership_manifest,
            )
            from memorii.core.memory_plane.service import MemoryPlaneService
            from memorii.core.memory_plane.sqlite_store import SqliteMemoryPlaneStore
            from memorii.core.persistence.factory import PublishedMemoryPlaneStore
            from memorii.core.storage_administration.operator_governance import (
                GovernanceOperator,
            )

            governance = GovernanceOperator(operator)
            plane = MemoryPlaneService(
                record_store=PublishedMemoryPlaneStore(
                    administration, SqliteMemoryPlaneStore(administration.partition())
                )
            )
            fingerprint = canonical_graph_codec_manifest().manifest_fingerprint
            writers = SemanticWriterAdmissionStore(
                plane, bounded_preplanning_ownership_manifest()
            )
            from memorii.core.memory_evolution.writer_admission import (
                writer_admission_memory_id,
            )

            if plane.get_record(writer_admission_memory_id()) is None:
                writers.create_initial_evidence_only(
                    admission_id="runtime-operator-enforce",
                    writer_implementation_fingerprint=fingerprint,
                    graph_schema_fingerprint=fingerprint,
                )
            store = SemanticIngestionAtomicStore(plane, writers)
            enforced = governance.enforce_forget(store=store)
            remaining = administration.drain_pending_forget_enforcement()
            print(
                json.dumps(
                    {"enforced": list(enforced), "pending": remaining}
                )
            )
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
