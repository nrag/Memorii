"""Focused proof of neutral MemoryPlane conditional-batch mechanics.

These records intentionally use no semantic-ingestion identifiers or kinds.
Passing tests establish backend transaction feasibility only; they do not claim
semantic ledger admission, writer-policy integration, or a production caller.
"""

from __future__ import annotations

import pytest

from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import JsonlMemoryPlaneStore, record_digest

from backend_feasibility import (
    MemoryPlaneRevisionConflictError,
    NeutralAppendRequest,
    NeutralConditionalBatchProbe,
)


def _request(source_id: str, request_id: str, payload: str) -> NeutralAppendRequest:
    return NeutralAppendRequest(source_id=source_id, request_id=request_id, payload=payload)


@pytest.mark.parametrize("existing_head", [False, True])
def test_stale_head_batch_writes_no_head_entry_or_result_and_retry_succeeds(tmp_path, existing_head) -> None:
    plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(tmp_path / "mechanics"))
    probe = NeutralConditionalBatchProbe(plane)
    source_a = _request("source-a", "request-a", "a")
    source_b = _request("source-b", "request-b", "b")
    if existing_head:
        probe.append(probe.prepare(_request("seed", "seed", "seed")))
    stale_b = probe.prepare(source_b)

    committed_a = probe.append(probe.prepare(source_a))
    before_failed_batch = plane.read_snapshot()
    with pytest.raises(MemoryPlaneRevisionConflictError, match="record_digest" if existing_head else "record_absent"):
        probe.append(stale_b)

    assert plane.read_snapshot() == before_failed_batch
    assert plane.get_record("backend-feasibility:entry:source-b:request-b") is None
    assert plane.get_record("backend-feasibility:result:source-b:request-b") is None

    committed_b = probe.append(probe.prepare(source_b))
    assert committed_b.entry.content["generation"] == (3 if existing_head else 2)
    assert committed_b.entry.content["expected_head_digest"] == record_digest(committed_a.head)


def test_two_sources_interleave_exact_reload_and_survive_durable_restart(tmp_path) -> None:
    store_path = tmp_path / "mechanics"
    first_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(store_path))
    first_probe = NeutralConditionalBatchProbe(first_plane)
    source_a = _request("source-a", "request-a", "payload-a")
    source_b = _request("source-b", "request-b", "payload-b")
    source_a_second = _request("source-a", "request-a-second", "payload-a-second")

    committed_a = first_probe.append(first_probe.prepare(source_a))
    committed_b = first_probe.append(first_probe.prepare(source_b))
    committed_a_second = first_probe.append(first_probe.prepare(source_a_second))
    assert [
        committed_a.entry.content["generation"],
        committed_b.entry.content["generation"],
        committed_a_second.entry.content["generation"],
    ] == [1, 2, 3]

    reopened_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(store_path))
    reopened_probe = NeutralConditionalBatchProbe(reopened_plane)
    reloaded_a = reopened_probe.append(first_probe.prepare(source_a))
    reloaded_b = reopened_probe.append(reopened_probe.prepare(source_b))
    reloaded_a_second = reopened_probe.append(reopened_probe.prepare(source_a_second))
    assert reloaded_a.entry == committed_a.entry
    assert reloaded_a.result == committed_a.result
    assert reloaded_b.entry == committed_b.entry
    assert reloaded_b.result == committed_b.result
    assert reloaded_a_second.entry == committed_a_second.entry
    assert reloaded_a_second.result == committed_a_second.result

    with pytest.raises(ValueError, match="changed immutable content"):
        reopened_probe.append(reopened_probe.prepare(_request("source-a", "request-a", "changed")))


def test_immutable_result_collision_does_not_publish_head_or_entry(tmp_path) -> None:
    from backend_feasibility import _result_record

    plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(tmp_path / "mechanics"))
    probe = NeutralConditionalBatchProbe(plane)
    request = _request("a", "a", "payload")
    result = _result_record(request)
    plane.conditionally_write_records((result,), preconditions=())
    before = plane.read_snapshot()
    with pytest.raises(MemoryPlaneRevisionConflictError, match="record_absent.*result"):
        probe.append(probe.prepare(request))
    assert plane.read_snapshot() == before
    assert plane.get_record("backend-feasibility:neutral-head") is None
    assert plane.get_record("backend-feasibility:entry:a:a") is None
