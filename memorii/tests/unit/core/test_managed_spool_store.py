"""Managed intake parity, selection, limits, and offline recovery evidence."""

from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from uuid import uuid4

import pytest
from memorii.core.harness_state import managed_spool_store
from memorii.core.harness_state.consumer import (
    ConsumerDeliveryError,
    HostEventDelivery,
    ManagedRuntimeSpool,
    ManagedSpoolEntry,
    operation_key,
)
from memorii.core.harness_state.managed_spool_store import verify_managed_spool_snapshot
from memorii.core.persistence.runtime_contracts import (
    OperationOrigin,
    OperationOriginCoordinate,
    RuntimeCommandReceipt,
    RuntimeCommandRequest,
)
from memorii.core.storage_administration.managed_spool_selection import (
    managed_spool_lease,
    open_managed_spool,
    register_managed_spool,
)
from memorii.core.storage_administration.operator import (
    ModeChangeRequest,
    StorageAdministrationOperator,
    mint_owner_capability,
)
from memorii.core.storage_administration.service import StorageAdministrationService


def _entry(operation_id: str, *, namespace: str = "host:pi", generation: str = "live") -> ManagedSpoolEntry:
    command = RuntimeCommandRequest(
        kind="resume_task", operation_id=operation_id, task_id="task:continue", expected_revision=1,
    )
    coordinate = OperationOriginCoordinate(
        installation_id="installation", repository_id="partition", generation_id=generation,
        principal="principal", client_namespace=namespace, operation_id=operation_id,
        request_digest=command.managed_intent_digest(),
    )
    return ManagedSpoolEntry(
        delivery=HostEventDelivery(
            transport_message_id=f"transport:{operation_id}", producer_binding=namespace, command=command,
        ),
        operation_origin=OperationOrigin(coordinate=coordinate, signature="a" * 128),
    )


def _admit(spool: ManagedRuntimeSpool, entry: ManagedSpoolEntry) -> ManagedSpoolEntry:
    return spool.admit(entry.delivery, operation_origin=entry.operation_origin, validate=lambda command, proof: None)


def _receipt(entry: ManagedSpoolEntry) -> RuntimeCommandReceipt:
    origin = entry.operation_origin
    return RuntimeCommandReceipt(
        operation_id=origin.coordinate.operation_id, client_namespace=origin.coordinate.client_namespace,
        request_digest=origin.coordinate.request_digest, status="committed", base_revision=1,
        current_revision=2, operation_origin=origin.coordinate, origin_proof_digest=origin.proof_digest(),
    )


def _selected(root: Path) -> tuple[ManagedRuntimeSpool, Path]:
    store_id = uuid4().hex
    path = ManagedRuntimeSpool.stage_sqlite(root, store_id=store_id)
    return ManagedRuntimeSpool(root, expected_store_id=store_id), path


def test_owner_stages_exact_legacy_bytes_and_requires_registered_store(tmp_path: Path) -> None:
    root = tmp_path / "managed"
    legacy = ManagedRuntimeSpool(root)
    pending, committed = _entry("pending"), _entry("committed")
    _admit(legacy, pending)
    _admit(legacy, committed)
    legacy.mark_committed(committed)
    physical = root / f"{operation_key(pending.operation_origin.coordinate)}.json"
    formatted = (json.dumps(pending.model_dump(mode="json"), indent=4) + "\n").encode()
    physical.write_bytes(formatted)

    selected, path = _selected(root)
    assert legacy.pending() == selected.pending() == (pending,)
    assert selected.find(committed.operation_origin.coordinate) == committed.model_copy(update={"state": "committed"})
    assert physical.read_bytes() == formatted
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute(
            "SELECT original_payload FROM intake WHERE operation_key = ?",
            (operation_key(pending.operation_origin.coordinate),),
        ).fetchone() == (formatted,)

    store_id = path.stem.removeprefix("store-")
    with pytest.raises(ConsumerDeliveryError, match="cannot be opened"):
        ManagedRuntimeSpool(root, expected_store_id=uuid4().hex)
    path.unlink()
    with pytest.raises(ConsumerDeliveryError, match="cannot be opened"):
        ManagedRuntimeSpool(root, expected_store_id=store_id)
    assert legacy.pending() == (pending,)


def test_scoped_pending_resume_and_disjoint_pages(tmp_path: Path) -> None:
    spool, path = _selected(tmp_path / "managed")
    first, second = _entry("first"), _entry("second")
    unrelated = _entry("unrelated", namespace="host:other")
    retired = _entry("retired", generation="prior")
    for item in (first, unrelated, second, retired):
        _admit(spool, item)
    page = spool.pending_page(limit=1)
    assert [item.entry for item in page] == [first]
    assert [item.entry for item in spool.pending_page(after_sequence=page[-1].sequence, limit=2)] == [unrelated, second]
    with pytest.raises(ConsumerDeliveryError, match="page bounds"):
        spool.pending_page(limit=101)

    # Malformed out-of-scope data would fail validation if the index path read it.
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("UPDATE intake SET payload_digest = 'broken' WHERE operation_id = 'unrelated'")
        connection.commit()
    assert spool.pending_resumes(
        installation_id="installation", repository_id="partition", generation_id="live",
        principal="principal", client_namespace="host:pi", task_id="task:continue",
    ) == (first, second)
    with pytest.raises(ConsumerDeliveryError, match="payload digest"):
        spool.pending()


def test_commit_and_exact_idempotent_retry_require_receipt(tmp_path: Path) -> None:
    spool, _ = _selected(tmp_path / "managed")
    entry = _entry("operation")
    assert _admit(spool, entry) == entry
    divergent = entry.model_copy(update={
        "operation_origin": entry.operation_origin.model_copy(update={"signature": "b" * 128}),
    })
    with pytest.raises(ConsumerDeliveryError, match="divergent managed intake"):
        _admit(spool, divergent)
    with pytest.raises(ConsumerDeliveryError, match="exact committed receipt"):
        spool.mark_committed(entry)
    with pytest.raises(ConsumerDeliveryError, match="exact committed receipt"):
        spool.mark_committed(entry, receipt=_receipt(divergent))
    receipt = _receipt(entry)
    spool.mark_committed(entry, receipt=receipt)
    spool.mark_committed(entry, receipt=receipt)
    assert spool.pending() == ()
    assert _admit(spool, entry) == entry.model_copy(update={"state": "committed"})


def test_pending_limit_is_atomic_across_concurrent_writers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(managed_spool_store, "MAX_PENDING_PER_TASK", 2)
    spool, _ = _selected(tmp_path / "managed")

    def try_admit(number: int) -> str:
        try:
            _admit(spool, _entry(f"operation-{number}"))
        except ConsumerDeliveryError as exc:
            assert str(exc) == "resource_exhausted: task pending managed intake limit"
            return "full"
        return "admitted"

    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = tuple(pool.map(try_admit, range(8)))
    assert outcomes.count("admitted") == 2
    assert len(spool.pending()) == 2


def test_prior_generation_entries_do_not_consume_live_capacity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(managed_spool_store, "MAX_PENDING_PER_TASK", 1)
    monkeypatch.setattr(managed_spool_store, "MAX_PENDING_PER_INSTALLATION", 1)
    spool, _ = _selected(tmp_path / "managed")
    original = _admit(spool, _entry("original", generation="prior"))
    current = _admit(spool, _entry("current"))

    assert tuple(spool.iter_generation_pending(
        installation_id="installation", repository_id="partition", generation_id="live",
    )) == (current,)
    assert spool.find(original.operation_origin.coordinate) == original
    with pytest.raises(ConsumerDeliveryError, match="installation pending managed intake limit"):
        _admit(spool, _entry("over-limit"))


def test_snapshot_cut_and_prior_generation_hold(tmp_path: Path) -> None:
    spool, _ = _selected(tmp_path / "managed")
    original, current, later = _entry("original", generation="prior"), _entry("current"), _entry("later")
    _admit(spool, original)
    _admit(spool, current)
    copy = tmp_path / "intake-snapshot.sqlite3"
    copy.touch(mode=0o600)
    with spool.pin_snapshot() as snapshot:
        assert snapshot.high_water_mark == 2
        _admit(spool, later)
        assert snapshot.connection.execute("SELECT MAX(sequence) FROM intake").fetchone()[0] == 2
        with closing(sqlite3.connect(copy)) as output:
            snapshot.connection.backup(output)
    verify_managed_spool_snapshot(
        copy, store_id=snapshot.store_id, high_water_mark=2, installation_id="installation", repository_id="partition",
        verify_origin=lambda proof: proof in (original.operation_origin, current.operation_origin),
    )
    with pytest.raises(ConsumerDeliveryError, match="unauthenticated origin"):
        verify_managed_spool_snapshot(
            copy, store_id=snapshot.store_id, high_water_mark=2, installation_id="installation", repository_id="partition",
            verify_origin=lambda proof: False,
        )
    assert tuple(spool.iter_generation_pending(
        installation_id="installation", repository_id="partition", generation_id="live",
    )) == (current, later)
    spool.hold_prior_generation(installation_id="installation", repository_id="partition", generation_id="live")
    assert spool.pending() == (current, later)
    with pytest.raises(ConsumerDeliveryError, match="held"):
        _admit(spool, original)
    with pytest.raises(ConsumerDeliveryError, match="held"):
        spool.find(original.operation_origin.coordinate)


def test_failed_stage_preserves_legacy_and_can_retry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "managed"
    spool = ManagedRuntimeSpool(root)
    entry = _entry("original")
    _admit(spool, entry)
    store_id = uuid4().hex

    def unavailable(*args: object) -> None:
        raise sqlite3.OperationalError("injected interruption")

    with monkeypatch.context() as fault:
        fault.setattr(managed_spool_store.SqliteManagedSpool, "_insert", staticmethod(unavailable))
        with pytest.raises(ConsumerDeliveryError, match="staging failed"):
            ManagedRuntimeSpool.stage_sqlite(root, store_id=store_id)
    assert not list(root.glob("*.sqlite3"))
    assert spool.pending() == (entry,)
    ManagedRuntimeSpool.stage_sqlite(root, store_id=store_id)
    assert ManagedRuntimeSpool(root, expected_store_id=store_id).pending() == (entry,)


def test_owner_selection_binds_current_control_and_refuses_missing_state(tmp_path: Path) -> None:
    root = tmp_path / "installation"
    with StorageAdministrationService(root) as service:
        service.initialize()
        owner = mint_owner_capability(service, "owner")
        operator = StorageAdministrationOperator(service)
        store_id = uuid4().hex
        with pytest.raises(ConsumerDeliveryError, match="read-only"):
            register_managed_spool(service, capability=owner, store_id=store_id)
        operator.change_mode(
            ModeChangeRequest(
                target_mode="read_only", expected_control_revision=operator.status().control_revision,
                reason="select managed intake while stopped",
            ),
            capability=owner,
        )
        with managed_spool_lease(service):
            open_managed_spool(service)
            with pytest.raises(ConsumerDeliveryError, match="selection or use is already in progress"):
                register_managed_spool(service, capability=owner, store_id=store_id)
        binding = register_managed_spool(service, capability=owner, store_id=store_id)
        assert register_managed_spool(service, capability=owner, store_id=store_id) == binding
        assert [item.operation for item in service._control.read_journal()].count("managed_spool_registered") == 1
        with pytest.raises(ConsumerDeliveryError, match="alternate directory"):
            open_managed_spool(service, directory=root / "replacement")
    with StorageAdministrationService(root) as reopened:
        with open_managed_spool(reopened).pin_snapshot() as snapshot:
            assert (snapshot.store_id, snapshot.high_water_mark) == (store_id, 0)
        with reopened._control.transaction(write=True) as connection:
            connection.execute("DELETE FROM managed_spool_binding")
        with pytest.raises(ConsumerDeliveryError, match="registered authority"):
            open_managed_spool(reopened)
