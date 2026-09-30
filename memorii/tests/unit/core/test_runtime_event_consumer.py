"""Local durable spool: idempotent intake, dead letters, no-fault-ack."""

from __future__ import annotations

from pathlib import Path

import pytest
from memorii.core.harness_state.consumer import (
    ConsumerDeliveryError,
    HostEventDelivery,
    LocalDurableSpool,
    command_digest,
)
from memorii.core.persistence.runtime_contracts import RuntimeCommandRequest


def _delivery(
    operation_id: str = "op:one",
    *,
    producer: str = "producer:trusted",
    goal: str = "Consume durably",
) -> HostEventDelivery:
    return HostEventDelivery(
        transport_message_id="msg:" + operation_id,
        producer_binding=producer,
        command=RuntimeCommandRequest(
            kind="start_task", operation_id=operation_id, goal=goal
        ),
    )


def test_intake_is_durable_and_idempotent(tmp_path: Path) -> None:
    spool = LocalDurableSpool(tmp_path / "spool")
    first = spool.admit(_delivery(), allowlisted_producers=("producer:trusted",))
    assert first.state == "pending"
    repeat = spool.admit(_delivery(), allowlisted_producers=("producer:trusted",))
    assert repeat == first
    assert len(spool.records()) == 1


def test_untrusted_producer_denies_without_intake(tmp_path: Path) -> None:
    spool = LocalDurableSpool(tmp_path / "spool")
    with pytest.raises(ConsumerDeliveryError, match="not allowlisted"):
        spool.admit(
            _delivery(producer="producer:stranger"),
            allowlisted_producers=("producer:trusted",),
        )
    assert spool.records() == ()


def test_divergent_duplicate_dead_letters(tmp_path: Path) -> None:
    spool = LocalDurableSpool(tmp_path / "spool")
    spool.admit(_delivery(), allowlisted_producers=("producer:trusted",))
    with pytest.raises(ConsumerDeliveryError, match="dead-lettered"):
        spool.admit(
            _delivery(goal="Different intent"),
            allowlisted_producers=("producer:trusted",),
        )
    states = {record.operation_id: record.state for record in spool.records()}
    assert states["op:one"] == "dead_letter"


def test_transient_storage_failure_never_writes(tmp_path: Path) -> None:
    spool = LocalDurableSpool(tmp_path / "spool")

    def unavailable() -> None:
        raise OSError("spool disk unavailable")

    with pytest.raises(OSError):
        spool.admit(
            _delivery(),
            allowlisted_producers=("producer:trusted",),
            storage_unavailable=unavailable,
        )
    assert spool.records() == ()


def test_command_digest_binds_full_intent() -> None:
    first = command_digest(_delivery().command)
    same = command_digest(_delivery().command)
    changed = command_digest(_delivery(goal="other").command)
    assert first == same and first != changed
