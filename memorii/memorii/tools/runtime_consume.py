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
)
from memorii.core.persistence.runtime_api import RuntimeCommandService
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
    arguments = parser.parse_args(argv)

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
        administration = StorageAdministrationService(arguments.installation_root)
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
                    spool.mark_committed(record.operation_id)
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


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
