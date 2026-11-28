"""``memorii-operator``: owner CLI over the operator control surface.

Commands bind the implemented operator owners: status, mode, export,
backup create/verify, restore plan, forget plan, erasure plan, retention
plan, doctor. Every destructive command requires the owner capability
(principal + digest) and prints its plan for review before apply flags
are accepted. Machine JSON and readable output carry the same status.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from argparse import Namespace
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import TypeAdapter, ValidationError

from memorii.stores.sqlite.private_storage import (
    finish_private_handoff,
    read_private_file,
    repair_installation_permissions,
    require_private_directory,
    write_private_file,
)
from memorii.tools.cli_diagnostics import SafeArgumentParser, diagnostic_code

if TYPE_CHECKING:
    from memorii.core.storage_administration.operator import OwnerCapability, StorageAdministrationOperator
    from memorii.core.storage_administration.service import StorageAdministrationService

_LOGGER = logging.getLogger(__name__)


class _CliError(RuntimeError):
    """Static, operator-facing diagnostic from this adapter."""

    def __init__(self, message: str, *, exit_status: int = 3) -> None:
        super().__init__(message)
        self.exit_status = exit_status


def _read_secret(path: Path, *, size: int, label: str) -> bytes:
    try:
        value = read_private_file(path, limit=size + 1)
    except OSError as exc:
        raise _CliError(f"denied: {label} must be a readable, regular owner-only file") from exc
    if len(value) != size:
        raise _CliError(f"invalid_request: {label} has an invalid length")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = SafeArgumentParser(
        prog="memorii-operator",
        description="Owner-only operator controls over one installation.",
        allow_abbrev=False,
    )
    parser.add_argument("--installation-root", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)

    status = commands.add_parser("status", help="Content-free installation status")
    status.add_argument("--backup-archive", type=Path, help="Verify the selected backup and report its age")
    commands.add_parser("doctor", help="Read-only health checks")
    commands.add_parser("repair-permissions", help="Restrict an offline installation to its filesystem owner")
    init = commands.add_parser("init", help="Initialize private managed storage")
    init.add_argument("--capability-output", type=Path, required=True, help="New private owner capability file")
    serve = commands.add_parser("serve", help="Serve verified native host requests on loopback")
    serve.add_argument("--port", type=int, default=8762)

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
        "--recovery-key-file",
        type=Path,
        required=True,
        help="Owner-only file with the 32-byte raw recovery key",
    )
    verify = backup_sub.add_parser("verify", help="Verify an archive")
    verify.add_argument("--archive-root", type=Path, required=True)
    restore = backup_sub.add_parser("restore-plan", help="Plan a restore")
    restore.add_argument("--archive-root", type=Path, required=True)
    restore.add_argument("--data-loss-acknowledged", action="store_true")
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
    preview_stage.add_argument(
        "--raw-payloads", action="store_true", help="Review a raw payload upgrade or v8 read selector backfill",
    )
    activate_current = backup_sub.add_parser(
        "restore-activate-current", help="Select a verified staged backup at the exact live watermark",
    )
    activate_current.add_argument("--plan-file", type=Path, required=True)
    activate_current.add_argument("--staging-root", type=Path, required=True)
    activate_older = backup_sub.add_parser(
        "restore-activate-older", help="Select a reviewed older backup with a durable delivery hold",
    )
    activate_older.add_argument("--plan-file", type=Path, required=True)
    activate_older.add_argument("--staging-root", type=Path, required=True)
    activate_older.add_argument("--preview-digest", required=True)
    upgrade = backup_sub.add_parser(
        "upgrade-runtime", help="Upgrade an exact-current staged runtime and hold prior-generation deliveries",
    )
    upgrade.add_argument("--plan-file", type=Path, required=True)
    upgrade.add_argument("--staging-root", type=Path, required=True)
    upgrade.add_argument("--preview-digest", required=True)
    upgrade.add_argument(
        "--raw-payloads", action="store_true", help="Apply a reviewed raw payload upgrade or v8 read selector backfill",
    )
    reconcile = commands.add_parser("reconcile-delivery", help="Review a held delivery from a restored generation")
    reconcile_sub = reconcile.add_subparsers(dest="reconcile_command", required=True)
    reject_plan = reconcile_sub.add_parser("plan-reject", help="Plan to permanently decline a held delivery")
    reject_plan.add_argument("--delivery-id", required=True)
    reject = reconcile_sub.add_parser("reject", help="Record the reviewed decision without resending the delivery")
    reject.add_argument("--plan-file", type=Path, required=True)
    reject.add_argument("--plan-digest", required=True)

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
    grant_issue.add_argument(
        "--native-source", help="Exact dedicated native source as JSON with kind and session_id",
    )
    grant_revoke = grant_sub.add_parser("revoke", help="Revoke one host command grant")
    grant_revoke.add_argument("--grant-id", required=True)
    enroll = grant_sub.add_parser("enroll-native", help="Provision an exact native host binding")
    enroll.add_argument("--operation-id", required=True)
    enroll.add_argument("--principal", required=True)
    enroll.add_argument("--native-source", required=True, help="Exact native scope JSON with kind and session_id")
    enroll.add_argument("--expires-at", required=True, help="ISO-8601 timestamp with offset")
    enroll.add_argument("--credential-output", type=Path, required=True, help="New owner-only host credential file")
    enroll.add_argument("--replaces-grant-id", help="Rotate the prior exact binding to a fresh credential")
    task = enroll.add_mutually_exclusive_group(required=True)
    task.add_argument("--task-id")
    task.add_argument("--goal")

    spool = commands.add_parser("runtime-spool", help="Inspect or select the private managed intake store")
    spool_sub = spool.add_subparsers(dest="spool_command", required=True)
    spool_sub.add_parser("register", help="Select a verified SQLite spool for a stopped read-only installation")
    export_entry = spool_sub.add_parser("export-entry", help="Write one exact committed original signed entry")
    export_entry.add_argument("--coordinate-file", type=Path, required=True)
    export_entry.add_argument("--output-file", type=Path, required=True)

    source_grant = commands.add_parser("runtime-source-grant", help="Manage durable provider source release")
    source_grant_sub = source_grant.add_subparsers(dest="source_grant_command", required=True)
    source_grant_issue = source_grant_sub.add_parser(
        "issue-native", help="Release one committed native observation for runtime lifecycle use",
    )
    source_grant_issue.add_argument("--entry-file", type=Path, required=True, help="Original committed managed spool entry")
    source_grant_revoke = source_grant_sub.add_parser("revoke", help="Revoke one exact task/source release grant")
    source_grant_revoke.add_argument("--grant-id", required=True)

    common = parser.add_argument_group("owner capability")
    common.add_argument("--owner-principal", default="")
    common.add_argument("--capability-file", type=Path, help="Owner-only file with the 64-character hex digest")

    arguments = parser.parse_args(argv)

    from memorii.core.storage_administration.operator import (
        ModeChangeRequest,
        OperatorError,
        OwnerCapability,
        StorageAdministrationOperator,
    )
    from memorii.core.storage_administration.service import (
        InstallationPermissionsError,
        StorageAdministrationError,
        StorageAdministrationService,
    )

    if arguments.command == "repair-permissions":
        try:
            repair_installation_permissions(arguments.installation_root)
        except OSError:
            _LOGGER.error("denied: could not restrict all managed storage; check its ownership and file types")
            return 3
        print(json.dumps({"status": "permissions_repaired"}))
        return 0
    try:
        administration = StorageAdministrationService(
            arguments.installation_root, use_registered_writers=True,
        )
    except InstallationPermissionsError:
        _LOGGER.error("denied: unsafe installation permissions; run memorii-operator repair-permissions")
        return 3
    except (OSError, sqlite3.DatabaseError, StorageAdministrationError):
        _LOGGER.error("unavailable: installation could not be opened")
        return 3
    operator = StorageAdministrationOperator(administration)

    def require_capability() -> OwnerCapability:
        if not arguments.owner_principal or arguments.capability_file is None:
            raise _CliError(
                "invalid_request: --owner-principal and --capability-file are required",
                exit_status=2,
            )
        digest = _read_secret(arguments.capability_file, size=64, label="owner capability")
        try:
            return OwnerCapability(owner_principal=arguments.owner_principal, capability_digest=digest.decode("ascii"))
        except (UnicodeError, ValidationError) as exc:
            raise _CliError("invalid_request: owner capability is malformed") from exc

    try:
        if arguments.command == "runtime-spool":
            return _run_spool_operator(arguments, administration, require_capability())
        if arguments.command in {"init", "serve"} or (
            arguments.command == "runtime-grant" and arguments.grant_command == "enroll-native"
        ):
            return _run_native_operator(arguments, administration, require_capability)
        if arguments.command == "status":
            print(operator.status(backup_archive=arguments.backup_archive).model_dump_json())
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
            return _run_backup(arguments, operator, require_capability)
        if arguments.command == "reconcile-delivery":
            from memorii.core.persistence.runtime_repository import RuntimeStateError
            from memorii.core.storage_administration.delivery_reconciliation import (
                DeliveryReconciliationOperator,
                DeliveryRejectionPlan,
            )
            from memorii.core.storage_administration.service import StorageAdministrationError
            from memorii.stores.sqlite.control import ControlStateError

            owner = require_capability()
            reconciliation = DeliveryReconciliationOperator(administration)
            try:
                if arguments.reconcile_command == "plan-reject":
                    plan = reconciliation.plan_rejection(capability=owner, delivery_id=arguments.delivery_id)
                    print(json.dumps({"plan": plan.model_dump(mode="json"), "plan_digest": plan.digest()}))
                    return 0
                plan = DeliveryRejectionPlan.model_validate_json(arguments.plan_file.read_bytes())
                decision = reconciliation.reject(capability=owner, plan=plan, plan_digest=arguments.plan_digest)
            except (RuntimeStateError, StorageAdministrationError, ControlStateError) as exc:
                raise _CliError("unavailable: held delivery could not be reconciled") from exc
            except (OSError, ValidationError) as exc:
                raise _CliError("invalid_request: delivery rejection plan could not be read") from exc
            print(decision.model_dump_json())
            return 0
        if arguments.command == "runtime-source-grant":
            from memorii.core.persistence.runtime_api import RuntimeCommandError
            from memorii.core.persistence.runtime_repository import RuntimeStateError
            from memorii.core.provider.runtime_source_authority import RuntimeSourceAuthorityError
            from memorii.core.provider.runtime_source_release import RuntimeSourceReleaseAuthority
            from memorii.core.storage_administration.service import StorageAdministrationError

            try:
                owner = require_capability()
                if arguments.source_grant_command == "issue-native":
                    from memorii.core.harness_state.consumer import ManagedSpoolEntry
                    from memorii.core.harness_state.native_source_release import issue_native_source_release

                    try:
                        entry = ManagedSpoolEntry.model_validate_json(arguments.entry_file.read_bytes())
                    except (OSError, ValidationError) as exc:
                        raise _CliError("invalid_request: committed native observation entry could not be read") from exc
                    release = issue_native_source_release(administration, capability=owner, entry=entry)
                else:
                    release = RuntimeSourceReleaseAuthority(administration).revoke(
                        capability=owner, grant_id=arguments.grant_id,
                    )
            except (RuntimeCommandError, RuntimeSourceAuthorityError, RuntimeStateError, StorageAdministrationError) as exc:
                raise _CliError(f"{diagnostic_code(exc)}: native source grant request failed") from exc
            print(json.dumps({"grant_id": release.grant_id, "status": release.status}, sort_keys=True))
            return 0
        if arguments.command == "runtime-grant":
            from datetime import datetime

            from memorii.core.harness_state.write_authority import (
                HostCommandAuthorityError,
                HostCommandGrantRequest,
                ManagedHostCommandAuthority,
                NativeSourceScope,
            )
            from memorii.core.persistence.writeback_decisions import CandidateScope

            authority = ManagedHostCommandAuthority(administration)
            if arguments.grant_command == "revoke":
                try:
                    epoch = authority.revoke(
                        arguments.grant_id, capability=require_capability()
                    )
                except HostCommandAuthorityError as exc:
                    raise _CliError(f"{diagnostic_code(exc)}: runtime grant revocation failed") from exc
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
                raise _CliError(
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
                    native_source=(
                        None if arguments.native_source is None
                        else NativeSourceScope.model_validate_json(arguments.native_source)
                    ),
                    expires_at=expires_at,
                )
            except ValidationError as exc:
                raise _CliError("invalid_request: runtime grant scope is invalid") from exc
            try:
                if grant_request.native_source is None:
                    issued = authority.issue(grant_request, capability=require_capability())
                else:
                    from memorii.core.harness_state.native_sources import enroll_native_source

                    issued = enroll_native_source(administration, grant_request, capability=require_capability())
            except HostCommandAuthorityError as exc:
                raise _CliError(f"{diagnostic_code(exc)}: runtime grant issuance failed") from exc
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
    except _CliError as error:
        _LOGGER.error("%s", error)
        return error.exit_status
    except OperatorError as error:
        _LOGGER.error("%s: operator request failed", diagnostic_code(error))
        return 3
    except ValueError:
        _LOGGER.error("invalid_request: operator input is invalid")
        return 2
    except InstallationPermissionsError:
        _LOGGER.error("denied: unsafe installation permissions; run memorii-operator repair-permissions")
        return 3
    except (OSError, sqlite3.DatabaseError, StorageAdministrationError):
        _LOGGER.error("unavailable: installation could not complete the operation")
        return 3
    finally:
        administration.close()


def _run_spool_operator(
    arguments: Namespace, administration: StorageAdministrationService, capability: OwnerCapability,
) -> int:
    from memorii.core.harness_state.consumer import ConsumerDeliveryError
    from memorii.core.persistence.runtime_contracts import OperationOriginCoordinate
    from memorii.core.storage_administration.managed_spool_selection import open_managed_spool, register_managed_spool
    from memorii.core.storage_administration.operator import require_owner_capability

    require_owner_capability(administration, capability)
    try:
        if arguments.spool_command == "register":
            binding = register_managed_spool(administration, capability=capability)
            print(binding.model_dump_json())
            return 0

        coordinate = OperationOriginCoordinate.model_validate_json(
            read_private_file(arguments.coordinate_file, limit=64 * 1024),
        )
        with administration.verified_operation_context() as (_, publication):
            if (
                coordinate.installation_id != publication.installation_id
                or coordinate.repository_id != publication.repository_id
                or coordinate.generation_id != publication.data_generation_id
            ):
                raise _CliError("denied: managed spool coordinate belongs to a different generation")
            entry = open_managed_spool(administration).find(coordinate)
            if entry is None or entry.state != "committed":
                raise _CliError("denied: no matching committed managed spool entry")
        write_private_file(arguments.output_file, entry.model_dump_json().encode(), exclusive=True)
        print(json.dumps({"status": "exported"}))
        return 0
    except ConsumerDeliveryError as exc:
        raise _CliError(f"{diagnostic_code(exc)}: managed intake store is unavailable") from exc


def _run_native_operator(
    arguments: Namespace, administration: StorageAdministrationService,
    require_capability: Callable[[], OwnerCapability],
) -> int:
    import threading
    from dataclasses import asdict
    from datetime import datetime

    from memorii.core.harness_state.consumer import ConsumerDeliveryError
    from memorii.core.harness_state.credentials import CredentialError
    from memorii.core.harness_state.managed_enrollment import (
        HostEnrollmentError,
        HostEnrollmentRequest,
        ManagedHostEnrollment,
    )
    from memorii.core.harness_state.sidecar import RuntimeSidecar, serve_loopback
    from memorii.core.harness_state.write_authority import HostCommandAuthorityError, NativeSourceScope
    from memorii.core.persistence.runtime_api import RuntimeCommandError
    from memorii.core.storage_administration.managed_spool_selection import (
        managed_spool_lease,
        open_managed_spool,
        register_managed_spool,
    )
    from memorii.core.storage_administration.operator import mint_owner_capability, require_owner_capability

    if arguments.command == "init":
        if not arguments.owner_principal or arguments.capability_file is not None:
            raise _CliError("invalid_request: --owner-principal is required for initialization", exit_status=2)
        output = arguments.capability_output
        require_private_directory(output.parent)
        finish_private_handoff(output)
        receipt = administration.initialize()
        capability = mint_owner_capability(administration, arguments.owner_principal)
        try:
            register_managed_spool(administration, capability=capability, initializing=True)
        except ConsumerDeliveryError as exc:
            raise _CliError(f"{diagnostic_code(exc)}: managed intake registration failed") from exc
        contents = capability.capability_digest.encode("ascii")
        try:
            prior = read_private_file(output, limit=65)
        except FileNotFoundError:
            write_private_file(output, contents, exclusive=True)
        else:
            if prior != contents:
                raise _CliError("conflict: capability destination already exists")
        print(json.dumps(asdict(receipt)))
        return 0
    capability = require_capability()
    require_owner_capability(administration, capability)
    if arguments.command == "serve":
        if not 0 <= arguments.port < 65_536:
            raise _CliError("invalid_request: sidecar port is invalid", exit_status=2)
        with administration.verified_operation_context() as (state, finalized):
            if state.mode == "bypass":
                raise _CliError("unavailable: installation is in bypass mode")
            partition = administration.partition()
            with partition.transaction(write=False) as connection:
                if not partition.uses_raw_memory_payloads(connection) or partition.needs_verified_read_selectors(connection):
                    raise _CliError("unavailable: managed native service requires verified v8 read selectors")
            publication_digest = finalized.payload_digest()
        enrollment = ManagedHostEnrollment(administration)
        try:
            with managed_spool_lease(administration):
                spool = open_managed_spool(administration)
                sidecar = RuntimeSidecar.for_managed_installation(
                    administration, credentials=enrollment.credentials, enrollment=enrollment, spool=spool,
                )
                url, server = serve_loopback(sidecar, port=arguments.port)
                try:
                    print(json.dumps({
                        "status": "ready", "url": url, "publication_digest": publication_digest,
                    }), flush=True)
                    threading.Event().wait()
                except KeyboardInterrupt:
                    return 0
                finally:
                    server.shutdown()
                    server.server_close()
        except ConsumerDeliveryError as exc:
            raise _CliError(f"{diagnostic_code(exc)}: managed intake store is unavailable") from exc
    try:
        request = HostEnrollmentRequest(
            operation_id=arguments.operation_id, principal=arguments.principal,
            source=NativeSourceScope.model_validate_json(arguments.native_source),
            expires_at=datetime.fromisoformat(arguments.expires_at), task_id=arguments.task_id, goal=arguments.goal,
            replaces_grant_id=arguments.replaces_grant_id,
        )
        receipt = ManagedHostEnrollment(administration).enroll(
            request, capability=capability, credential_file=arguments.credential_output,
        )
    except ValidationError as exc:
        raise _CliError("invalid_request: native enrollment scope is invalid", exit_status=2) from exc
    except (CredentialError, HostCommandAuthorityError, HostEnrollmentError, RuntimeCommandError) as exc:
        raise _CliError(f"{diagnostic_code(exc)}: native enrollment failed") from exc
    print(receipt.model_dump_json())
    return 0


def _run_backup(
    arguments: Namespace,
    operator: StorageAdministrationOperator,
    require_capability: Callable[[], OwnerCapability],
) -> int:
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
            recovery_key=_read_secret(arguments.recovery_key_file, size=32, label="recovery key"),
        )
        print(manifest.model_dump_json())
        return 0
    if arguments.backup_command == "verify":
        manifest = backups.verify_backup(archive_root=arguments.archive_root)
        print(manifest.model_dump_json())
        return 0
    if arguments.backup_command in {
        "restore-verify-stage", "restore-preview-stage", "restore-activate-current", "restore-activate-older",
        "upgrade-runtime",
    }:
        owner = require_capability()
        try:
            plan = RestorePlan.model_validate_json(arguments.plan_file.read_bytes())
        except (ValidationError, OSError) as exc:
            raise _CliError("invalid_request: restore plan could not be read") from exc
        if arguments.backup_command == "restore-preview-stage":
            preview = backups.preview_staged_restore(
                capability=owner, plan=plan, staging_root=arguments.staging_root,
                raw_payloads=arguments.raw_payloads,
            )
            print(json.dumps({**preview.model_dump(mode="json"), "preview_digest": preview.digest()}))
            return 0
        if arguments.backup_command in {"restore-activate-older", "upgrade-runtime"}:
            from memorii.core.storage_administration.service import StorageAdministrationError
            from memorii.stores.sqlite.control import ControlStateError
            from memorii.stores.sqlite.partition import RAW_MEMORY_PAYLOAD_SCHEMA_VERSION

            try:
                if arguments.backup_command == "upgrade-runtime":
                    intent = backups.upgrade_current_runtime(
                        capability=owner, plan=plan, staging_root=arguments.staging_root,
                        preview_digest=arguments.preview_digest, raw_payloads=arguments.raw_payloads,
                    )
                else:
                    intent = backups.activate_older_restore(
                        capability=owner, plan=plan, staging_root=arguments.staging_root,
                        preview_digest=arguments.preview_digest,
                    )
            except (StorageAdministrationError, ControlStateError) as exc:
                raise _CliError("unavailable: generation change could not be published") from exc
            result: dict[str, str | int | bool] = {
                "status": "selected", "generation_id": intent.candidate_publication.data_generation_id,
                "delivery_status": "needs_reconciliation", "reopen_required": True,
            }
            if arguments.backup_command == "upgrade-runtime" and arguments.raw_payloads:
                result["previous_generation_id"] = intent.old_publication.data_generation_id
                result["storage_schema_version"] = RAW_MEMORY_PAYLOAD_SCHEMA_VERSION
            print(json.dumps(result, sort_keys=True))
            return 0
        if arguments.backup_command == "restore-activate-current":
            try:
                selector = backups.activate_exact_current_restore(
                    capability=owner, plan=plan, staging_root=arguments.staging_root,
                )
            except OSError as exc:
                raise _CliError("unavailable: exact-current restore selection could not be published") from exc
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
        owner = require_capability()
        try:
            plan = RestorePlan.model_validate_json(arguments.plan_file.read_bytes())
        except (ValidationError, OSError) as exc:
            raise _CliError("invalid_request: restore plan could not be read") from exc
        recovery_key = _read_secret(arguments.recovery_key_file, size=32, label="recovery key")
        try:
            staged = backups.apply_restore(
                capability=owner, plan=plan, staging_root=arguments.staging_root,
                recovery_key=recovery_key,
            )
        except InvalidTag as exc:
            raise _CliError("denied: recovery key did not authenticate the archive") from exc
        except OSError as exc:
            raise _CliError("unavailable: restore staging could not be published") from exc
        print(json.dumps({"status": "staged", "path": str(staged)}, sort_keys=True))
        return 0
    plan = backups.plan_restore(
        capability=require_capability(),
        archive_root=arguments.archive_root,
        data_loss_acknowledged=arguments.data_loss_acknowledged,
    )
    print(plan.model_dump_json())
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
