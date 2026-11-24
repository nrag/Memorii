"""``memorii consume``: drive the durable spool into the command service.

The CLI reads one delivery file (or admits stdin) through the local
durable spool with its allowlisted producer binding, then dispatches
the recorded command through the persistent runtime command service of
the selected installation. Intake is durable before acknowledgement;
committed effects print a receipt; refused deliveries exit nonzero with
the closed reason and never execute the command.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from memorii.core.harness_state.consumer import (
    ConsumerDeliveryError,
    HostEventDelivery,
    LocalDurableSpool,
    ManagedRuntimeSpool,
    ManagedSpoolEntry,
)
from memorii.core.persistence.runtime_api import RuntimeCommandError, RuntimeCommandService
from memorii.core.persistence.runtime_contracts import RuntimeCommandRequest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="memorii-consume",
        description="Admit one host event delivery and dispatch it durably.",
    )
    parser.add_argument(
        "--installation-root",
        required=True,
        help="initialized managed installation root",
    )
    parser.add_argument(
        "--producer",
        default=None,
        help="authenticated producer binding (required without --drain)",
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
        help="comma-separated producer bindings allowed to drain (required with --drain)",
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
            print("invalid_request: --drain requires --allowlisted-producers", file=sys.stderr)
            return 2
        from memorii.core.storage_administration.service import (
            StorageAdministrationService,
        )

        spool = LocalDurableSpool(spool_directory)
        from memorii.core.storage_administration.writer_enrollment import (
            WriterEnrollmentRegistry,
        )

        administration = StorageAdministrationService(
            arguments.installation_root,
            writer_enrollment=WriterEnrollmentRegistry(
                Path(arguments.installation_root) / "control" / "writers"
            ),
        )
        refused = 0
        try:
            pending = spool.pending_deliveries(allowlisted_producers=allowlisted)
            for record, delivery in pending:
                # One refused delivery never aborts the queue: it stays
                # pending for operator handling and its reason is reported.
                service = RuntimeCommandService(
                    administration, client_namespace=record.producer_binding
                )
                try:
                    receipt = service.dispatch(delivery.command)
                except RuntimeError as exc:
                    refused += 1
                    print(
                        json.dumps(
                            {
                                "operation_id": record.operation_id,
                                "status": "refused",
                                "reason": str(exc).split(":", 1)[-1].strip(),
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
                    except RuntimeError as mark_error:
                        # State transition races (dead-letter, unknown id)
                        # report and continue: the queue keeps draining, the
                        # record stays for operator handling.
                        refused += 1
                        print(
                            json.dumps(
                                {
                                    "operation_id": record.operation_id,
                                    "status": "mark_failed",
                                    "reason": str(mark_error).split(":", 1)[-1].strip(),
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
        finally:
            administration.close()
        return 1 if refused else 0

    if not arguments.producer:
        print("invalid_request: --producer is required without --drain", file=sys.stderr)
        return 2
    raw = (
        arguments.delivery.read_text(encoding="utf-8")
        if arguments.delivery is not None
        else sys.stdin.read()
    )
    try:
        payload = json.loads(raw)
        command = RuntimeCommandRequest.model_validate(payload.get("command", payload))
    except (ValueError, AttributeError) as exc:
        print(f"invalid_request: delivery is not a closed command: {exc}", file=sys.stderr)
        return 2
    delivery = HostEventDelivery(
        transport_message_id=str(payload.get("transport_message_id", "stdin")),
        producer_binding=arguments.producer,
        command=command,
    )
    spool = LocalDurableSpool(spool_directory)
    try:
        record = spool.admit(
            delivery, allowlisted_producers=(arguments.producer,)
        )
    except ConsumerDeliveryError as exc:
        print(f"denied: {exc}", file=sys.stderr)
        return 3

    from memorii.core.storage_administration.service import (
        StorageAdministrationService,
    )

    administration = StorageAdministrationService(arguments.installation_root)
    try:
        service = RuntimeCommandService(
            administration, client_namespace=arguments.producer
        )
        receipt = service.dispatch(command)
    finally:
        administration.close()
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
    from memorii.core.persistence.runtime_repository import RuntimeStateError
    from memorii.core.storage_administration.service import StorageAdministrationError, StorageAdministrationService
    from memorii.core.storage_administration.writer_enrollment import WriterEnrollmentRegistry

    root = Path(arguments.installation_root)
    administration = StorageAdministrationService(
        root, writer_enrollment=WriterEnrollmentRegistry(root / "control" / "writers"),
    )
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
                    print(_managed_error_code(exc), file=sys.stderr)
                    continue
                spool.mark_committed(entry)
                print(receipt.model_dump_json())
            return 3 if refused else 0

        credential_file: Path = arguments.credential_file
        if credential_file.stat().st_mode & 0o077:
            print("denied: credential file permissions must be owner-only", file=sys.stderr)
            return 3
        credentials = SidecarCredentialStore(root / "control" / "runtime-credentials")
        service = authenticated_host_commands(administration, credentials, credential_file.read_text().strip())
        incoming = (
            arguments.delivery.read_bytes() if arguments.delivery else sys.stdin.buffer.read((1 << 20) + 1)
        )
        if len(incoming) > (1 << 20):
            print("invalid_request: managed body exceeds limit", file=sys.stderr)
            return 2
        if arguments.prepare:
            command = RuntimeCommandRequest.model_validate_json(incoming)
            print(service.prepare(command).model_dump_json())
            return 0
        envelope = ManagedSpoolEntry.model_validate_json(incoming)
        if envelope.state != "pending":
            print("invalid_request: intake requires a pending intent", file=sys.stderr)
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
        print("invalid_request: managed body does not match the closed schema", file=sys.stderr)
        return 2
    except (RuntimeCommandError, ConsumerDeliveryError) as exc:
        print(_managed_error_code(exc), file=sys.stderr)
        return 3
    except (OSError, CredentialError, RuntimeStateError, StorageAdministrationError):
        print("unavailable: managed installation could not accept the operation", file=sys.stderr)
        return 3
    finally:
        administration.close()


def _managed_error_code(error: RuntimeError) -> str:
    code = str(error).partition(":")[0]
    return code if code in {"conflict", "denied", "needs_reconciliation", "unsupported_configuration"} else "unavailable"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
