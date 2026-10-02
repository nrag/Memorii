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


def _seed_delivery(operation_id: str = "op:one", goal: str = "first") -> HostEventDelivery:
    from memorii.core.persistence.runtime_contracts import RuntimeCommandRequest

    return HostEventDelivery(
        transport_message_id="t:1",
        producer_binding="producer:trusted",
        command=RuntimeCommandRequest(
            kind="start_task",
            operation_id=operation_id,
            goal=goal,
        ),
    )


def test_admit_retains_delivery_content_for_drain(tmp_path: Path) -> None:
    spool = LocalDurableSpool(tmp_path)
    spool.admit(_seed_delivery(), allowlisted_producers=("producer:trusted",))
    deliveries = tmp_path / "deliveries"
    content = deliveries / f"{command_digest(_seed_delivery().command)}.json"
    assert content.is_file()
    assert (content.stat().st_mode & 0o077) == 0
    pending = spool.pending_deliveries(allowlisted_producers=("producer:trusted",))
    assert len(pending) == 1
    record, delivery = pending[0]
    assert record.state == "pending"
    assert delivery.command.operation_id == "op:one"


def test_pending_deliveries_skips_untrusted_missing_and_mismatched(tmp_path: Path) -> None:
    spool = LocalDurableSpool(tmp_path)
    spool.admit(_seed_delivery(), allowlisted_producers=("producer:trusted",))
    # Untrusted producer filter.
    assert spool.pending_deliveries(allowlisted_producers=()) == ()
    # Missing retained content (deleted file) is never guessed into effect.
    digest = command_digest(_seed_delivery().command)
    (tmp_path / "deliveries" / f"{digest}.json").unlink()
    assert spool.pending_deliveries(allowlisted_producers=("producer:trusted",)) == ()
    # Tampered content whose recomputed digest no longer matches is skipped.
    spool.admit(
        _seed_delivery(operation_id="op:two"),
        allowlisted_producers=("producer:trusted",),
    )
    tampered = tmp_path / "deliveries" / f"{command_digest(_seed_delivery(operation_id='op:two').command)}.json"
    tampered.write_text(tampered.read_text().replace("op:two", "op:evil"))
    assert spool.pending_deliveries(allowlisted_producers=("producer:trusted",)) == ()


def test_mark_committed_transitions_and_refuses(tmp_path: Path) -> None:
    spool = LocalDurableSpool(tmp_path)
    spool.admit(_seed_delivery(), allowlisted_producers=("producer:trusted",))
    committed = spool.mark_committed("op:one")
    assert committed.state == "committed"
    # Idempotent re-commit returns the same record.
    assert spool.mark_committed("op:one") == committed
    with pytest.raises(ConsumerDeliveryError, match="unknown operation"):
        spool.mark_committed("op:missing")
    # Committed records are not drainable again.
    assert spool.pending_deliveries(allowlisted_producers=("producer:trusted",)) == ()
    # Dead-lettered operations can never commit.
    spool.admit(
        _seed_delivery(operation_id="op:dead"),
        allowlisted_producers=("producer:trusted",),
    )
    with pytest.raises(ConsumerDeliveryError, match="dead-lettered"):
        spool.admit(
            _seed_delivery(operation_id="op:dead", goal="divergent"),
            allowlisted_producers=("producer:trusted",),
        )
    with pytest.raises(ConsumerDeliveryError, match="dead-lettered"):
        spool.mark_committed("op:dead")
