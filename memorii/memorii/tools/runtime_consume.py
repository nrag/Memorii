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
        required=True,
        help="authenticated producer binding (must be allowlisted)",
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
    arguments = parser.parse_args(argv)

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
    spool_directory = arguments.spool_directory or (
        Path(arguments.installation_root) / "spool"
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
