"""Drive signed managed intents or verified legacy deliveries into runtime."""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path

from pydantic import ValidationError

from memorii.core.harness_state.consumer import (
    ConsumerDeliveryError,
    HostEventDelivery,
    LocalDurableSpool,
    ManagedRuntimeSpool,
    ManagedSpoolEntry,
)
from memorii.core.persistence.runtime_api import RuntimeCommandError, RuntimeCommandService
from memorii.core.persistence.runtime_contracts import RuntimeCommandRequest
from memorii.core.persistence.runtime_repository import RuntimeStateError
from memorii.core.storage_administration.service import StorageAdministrationError, StorageAdministrationService
from memorii.stores.sqlite.private_storage import read_private_file
from memorii.tools.cli_diagnostics import SafeArgumentParser, diagnostic_code

_LOGGER = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = SafeArgumentParser(
        prog="memorii-consume",
        description="Admit one host event delivery and dispatch it durably.",
    )
    parser.add_argument(
        "--installation-root",
        required=True,
        help="initialized installation root",
    )
    parser.add_argument(
        "--producer",
        default=None,
        help="legacy v1 producer binding (required for legacy intake)",
    )
    parser.add_argument(
        "--delivery",
        type=Path,
        help="JSON delivery file; omit to read stdin",
    )
    parser.add_argument(
        "--spool-directory",
        type=Path,
        default=None,
        help="durable spool directory (default: <root>/spool)",
    )
    parser.add_argument(
        "--drain",
        action="store_true",
        help="drain every allowlisted pending delivery: dispatch each through"
        " the runtime command service and mark it committed",
    )
    parser.add_argument(
        "--allowlisted-producers",
        default="",
        help="comma-separated producer bindings allowed to drain on legacy v1 only",
    )
    parser.add_argument("--managed", action="store_true", help="Require the installation's managed command authority")
    parser.add_argument("--prepare", action="store_true", help="Prepare one new managed command without executing it")
    parser.add_argument("--credential-file", type=Path, help="Owner-only file containing the host credential")
    arguments = parser.parse_args(argv)

    if arguments.managed or arguments.prepare:
        if arguments.producer or arguments.allowlisted_producers:
            parser.error("managed commands resolve producer authority from the installation")
        if arguments.prepare and arguments.drain:
            parser.error("--prepare and --drain cannot be combined")
        if not arguments.drain and arguments.credential_file is None:
            parser.error("managed preparation and intake require --credential-file")
        return _run_managed(arguments)
    if arguments.credential_file is not None:
        parser.error("--credential-file requires managed mode")

    return _run_verified_legacy(arguments)


def _run_verified_legacy(arguments: argparse.Namespace) -> int:
    root = Path(arguments.installation_root)
    try:
        administration = StorageAdministrationService(
            root, use_registered_writers=arguments.drain,
        )
    except (OSError, sqlite3.DatabaseError, StorageAdministrationError):
        _LOGGER.error("unavailable: installation could not be verified")
        return 3
    try:
        # Resolve and verify the signed publication before consulting its
        # format marker. Keep this partition handle for the legacy path.
        with administration.verified_operation_context() as (state, _finalized):
            partition = administration.partition()
            with partition.transaction(write=False) as connection:
                if partition.supports_managed_runtime(connection):
                    _LOGGER.error("denied: this installation requires --managed")
                    return 3
            if state.mode != "active":
                _LOGGER.error("unavailable: installation is not active")
                return 3
        return _run_legacy(arguments, administration)
    except (OSError, sqlite3.DatabaseError, StorageAdministrationError):
        _LOGGER.error("unavailable: installation could not accept the operation")
        return 3
    except ValidationError:
        _LOGGER.error("integrity_error: legacy spool could not be verified")
        return 3
    finally:
        administration.close()


def _run_legacy(arguments: argparse.Namespace, administration: StorageAdministrationService) -> int:
    spool_directory = arguments.spool_directory or (
        Path(arguments.installation_root) / "spool"
    )

    if arguments.drain:
        allowlisted = tuple(
            producer.strip()
            for producer in arguments.allowlisted_producers.split(",")
            if producer.strip()
        )
        if not allowlisted:
            _LOGGER.error("invalid_request: --drain requires --allowlisted-producers")
            return 2
        spool = LocalDurableSpool(spool_directory)
        refused = 0
        pending = spool.pending_deliveries(allowlisted_producers=allowlisted)
        for record, delivery in pending:
            # One refused delivery never aborts the queue: it stays
            # pending for operator handling and its reason is reported.
            service = RuntimeCommandService(
                administration, client_namespace=record.producer_binding
            )
            try:
                receipt = service.dispatch(delivery.command)
            except (RuntimeCommandError, RuntimeStateError, StorageAdministrationError) as exc:
                refused += 1
                print(
                    json.dumps(
                        {
                            "operation_id": record.operation_id,
                            "status": "refused",
                            "reason": diagnostic_code(exc),
                            "intake_state": "pending",
                        },
                        sort_keys=True,
                    )
                )
                continue
            committed = receipt.status in ("committed", "duplicate")
            if committed:
                try:
                    spool.mark_committed(record.operation_id)
                except ConsumerDeliveryError as mark_error:
                    # State transition races (dead-letter, unknown id)
                    # report and continue: the queue keeps draining, the
                    # record stays for operator handling.
                    refused += 1
                    print(
                        json.dumps(
                            {
                                "operation_id": record.operation_id,
                                "status": "mark_failed",
                                "reason": diagnostic_code(mark_error),
                                "intake_state": "pending",
                            },
                            sort_keys=True,
                        )
                    )
                    continue
            print(
                json.dumps(
                    {
                        "operation_id": receipt.operation_id,
                        "status": receipt.status,
                        "base_revision": receipt.base_revision,
                        "current_revision": receipt.current_revision,
                        "intake_state": "committed" if committed else "pending",
                    },
                    sort_keys=True,
                )
            )
        return 1 if refused else 0

    if not arguments.producer:
        _LOGGER.error("invalid_request: --producer is required without --drain")
        return 2
    try:
        raw = (
            arguments.delivery.read_text(encoding="utf-8")
            if arguments.delivery is not None
            else sys.stdin.read()
        )
        payload = json.loads(raw)
        command = RuntimeCommandRequest.model_validate(payload.get("command", payload))
        delivery = HostEventDelivery(
            transport_message_id=str(payload.get("transport_message_id", "stdin")),
            producer_binding=arguments.producer,
            command=command,
        )
    except (ValueError, AttributeError):
        _LOGGER.error("invalid_request: delivery is not a closed command")
        return 2
    spool = LocalDurableSpool(spool_directory)
    try:
        record = spool.admit(
            delivery, allowlisted_producers=(arguments.producer,)
        )
    except ConsumerDeliveryError:
        _LOGGER.error("denied: delivery was refused by the durable spool")
        return 3

    service = RuntimeCommandService(administration, client_namespace=arguments.producer)
    try:
        receipt = service.dispatch(command)
    except (RuntimeCommandError, RuntimeStateError) as exc:
        _LOGGER.error("%s: delivery could not be dispatched", diagnostic_code(exc))
        return 3
    print(
        json.dumps(
            {
                "operation_id": receipt.operation_id,
                "status": receipt.status,
                "base_revision": receipt.base_revision,
                "current_revision": receipt.current_revision,
                "intake_state": record.state,
            },
            sort_keys=True,
        )
    )
    return 0


def _run_managed(arguments: argparse.Namespace) -> int:
    from memorii.core.harness_state.credentials import CredentialError, SidecarCredentialStore
    from memorii.core.harness_state.managed_ingress import authenticated_host_commands, spooled_host_commands
    root = Path(arguments.installation_root)
    try:
        administration = StorageAdministrationService(root, use_registered_writers=True)
    except (OSError, sqlite3.DatabaseError, StorageAdministrationError):
        _LOGGER.error("unavailable: managed installation could not be opened")
        return 3
    try:
        spool = ManagedRuntimeSpool(arguments.spool_directory or root / "spool" / "managed")
        if arguments.drain:
            refused = 0
            for entry in spool.pending():
                service = spooled_host_commands(administration, entry.operation_origin)
                try:
                    receipt = service.dispatch(entry.delivery.command, operation_origin=entry.operation_origin)
                except RuntimeCommandError as exc:
                    refused += 1
                    _LOGGER.error("%s", diagnostic_code(exc))
                    continue
                spool.mark_committed(entry)
                print(receipt.model_dump_json())
            return 3 if refused else 0

        credential_file: Path = arguments.credential_file
        try:
            credential = read_private_file(credential_file, limit=4097)
        except OSError:
            _LOGGER.error("denied: credential must be a readable, regular owner-only file")
            return 3
        if len(credential) > 4096:
            _LOGGER.error("invalid_request: credential file exceeds limit")
            return 2
        credentials = SidecarCredentialStore(root / "control" / "runtime-credentials")
        service = authenticated_host_commands(administration, credentials, credential.decode("utf-8").strip())
        incoming = (
            arguments.delivery.read_bytes() if arguments.delivery else sys.stdin.buffer.read((1 << 20) + 1)
        )
        if len(incoming) > (1 << 20):
            _LOGGER.error("invalid_request: managed body exceeds limit")
            return 2
        if arguments.prepare:
            command = RuntimeCommandRequest.model_validate_json(incoming)
            print(service.prepare(command).model_dump_json())
            return 0
        envelope = ManagedSpoolEntry.model_validate_json(incoming)
        if envelope.state != "pending":
            _LOGGER.error("invalid_request: intake requires a pending intent")
            return 2
        entry = spool.admit(
            envelope.delivery,
            operation_origin=envelope.operation_origin,
            validate=lambda command, proof: service.validate_intake(command, operation_origin=proof),
        )
        receipt = service.dispatch(entry.delivery.command, operation_origin=entry.operation_origin)
        spool.mark_committed(entry)
        print(receipt.model_dump_json())
        return 0
    except ValueError:
        _LOGGER.error("invalid_request: managed body does not match the closed schema")
        return 2
    except (RuntimeCommandError, ConsumerDeliveryError) as exc:
        _LOGGER.error("%s", diagnostic_code(exc))
        return 3
    except (OSError, sqlite3.DatabaseError, CredentialError, RuntimeStateError, StorageAdministrationError):
        _LOGGER.error("unavailable: managed installation could not accept the operation")
        return 3
    finally:
        administration.close()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
