"""Legacy digest-only deliveries remain inert in signed installations."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from memorii.core.persistence.managed_delivery import DeliveryTransitionError
from memorii.core.persistence.runtime_api import (
    LegacyUnresolvedDelivery,
    RuntimeCommandError,
    RuntimeOutboxDelivery,
    convert_legacy_outbox_record,
    deliver_outbox,
)
from memorii.core.persistence.runtime_repository import (
    RuntimeStateError,
    RuntimeStateRepository,
    publish_runtime_change,
)
from memorii.core.provider.runtime_candidate_delivery import ManagedCandidateDeliveryWorker
from memorii.core.storage_administration.service import StorageAdministrationService
from memorii.core.storage_administration.writer_enrollment import WriterEnrollmentRegistry
from memorii.core.work_state.runtime_projection import ManagedWorkProjectionWorker
from pydantic import ValidationError


def _outbox_delivery() -> RuntimeOutboxDelivery:
    return RuntimeOutboxDelivery(
        delivery_id="legacy-delivery",
        origin_operation_id="legacy-operation",
        kind="work_projection",
        target_protocol="memorii.runtime-intake/v1",
        payload_digest="a" * 64,
        fence_token=1,
    )


def test_conversion_retains_exact_bytes_and_identity() -> None:
    entry = _outbox_delivery()
    raw = json.dumps(entry.model_dump(mode="json"), indent=2) + "\n"
    held = convert_legacy_outbox_record(entry.delivery_id, raw)
    assert held is not None
    assert held.status == "needs_reconciliation"
    assert held.original_record_json == raw
    assert convert_legacy_outbox_record(entry.delivery_id, held.model_dump_json()) == held

    with pytest.raises(ValueError, match="storage key"):
        convert_legacy_outbox_record("different-delivery", held.model_dump_json())
    with pytest.raises(ValidationError, match="differs from its retained record"):
        LegacyUnresolvedDelivery.model_validate(held.model_dump() | {"original_record_digest": "1" * 64})
    with pytest.raises(ValidationError, match="Extra inputs"):
        convert_legacy_outbox_record(
            entry.delivery_id,
            json.dumps(entry.model_dump(mode="json") | {"record_type": "unsupported-outbox-format"}),
        )


def test_signed_v1_cannot_invoke_legacy_callback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("memorii.stores.sqlite.partition.PARTITION_SCHEMA_VERSION", 1)
    with StorageAdministrationService(tmp_path / "installation") as service:
        service.initialize()
        entry = _outbox_delivery()
        publish_runtime_change(service, lambda connection, repository: repository.apply_outbox_row(connection, entry))
        before = service.acquire_verified_snapshot()

        def forbidden_target(_entry: RuntimeOutboxDelivery) -> str:
            pytest.fail("a signed legacy row cannot call a target")

        with pytest.raises(RuntimeCommandError, match="needs_reconciliation"):
            deliver_outbox(RuntimeStateRepository(service.partition()), forbidden_target)
        assert service.acquire_verified_snapshot() == before


@pytest.mark.parametrize("converted", [False, True])
def test_managed_workers_refuse_legacy_rows_without_effect(tmp_path: Path, converted: bool) -> None:
    with StorageAdministrationService(tmp_path / "installation") as service:
        service.initialize()
        entry = _outbox_delivery()
        raw = entry.model_dump_json()
        publish_runtime_change(service, lambda connection, repository: repository.apply_outbox_row(connection, entry))
        if converted:
            held = convert_legacy_outbox_record(entry.delivery_id, raw)
            assert held is not None

            def convert(connection: sqlite3.Connection, repository: RuntimeStateRepository) -> None:
                repository.partition.upsert_runtime_row(
                    connection, table="runtime_outbox_deliveries",
                    keys=("delivery_id",), values=(held.delivery_id,), record_json=held.model_dump_json(),
                )

            publish_runtime_change(service, convert)
        before = service.acquire_verified_snapshot()
        writers = WriterEnrollmentRegistry(service.installation_root / "control" / "writers")
        writers.enroll("candidate-worker", kind="managed_writeback_candidate")
        writers.enroll("projection-worker", kind="managed_work_projection")
        candidate = ManagedCandidateDeliveryWorker(service, worker_id="candidate-worker")
        projection = ManagedWorkProjectionWorker(service, worker_id="projection-worker")
        with pytest.raises(DeliveryTransitionError, match="needs_reconciliation"):
            candidate.claim(entry.delivery_id)
        with pytest.raises(RuntimeStateError, match="needs_reconciliation"):
            projection.claim(entry.delivery_id)
        assert service.acquire_verified_snapshot() == before
