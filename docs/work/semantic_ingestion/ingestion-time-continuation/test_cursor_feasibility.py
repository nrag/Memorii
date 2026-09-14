from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from cursor_feasibility import (
    IngestionTimeAttestationCursorPayload,
    RetentionReservations,
    RetainedContinuation,
    continue_verified_cursor,
    cursor_schema,
    failure_dispatch,
)
from pydantic import ValidationError

from memorii.core.memory_evolution.graph_ingestion_time_contracts import (
    SourceRetentionTimeAttestation,
    TransactionGroupCommitTimeAttestation,
)
from memorii.core.memory_evolution.graph_observation_contracts import GraphObservationCohortSelector
from memorii.core.memory_evolution.graph_observation_public_contracts import IngestionTimeAttestationRequestCoordinates
from memorii.core.memory_evolution.models import MemoryScope

NOW = datetime(2026, 9, 8, tzinfo=UTC)


def fixture():
    request = IngestionTimeAttestationRequestCoordinates(
        scope_constraint=MemoryScope(user_id="alice"),
        cohort_selector=GraphObservationCohortSelector(seed_source_ids=("source",),
            seed_operation_ids=(), include_referenced_boundary_entities=True),
        expected_graph_revision="graph", expected_observation_revision="observation", total_page_size=1,
    )
    source = SourceRetentionTimeAttestation(kind="source_retention", attestation_id="source-time",
        source_id="source", operation_fence_id="fence", retained_at=NOW,
        graph_revision="graph", clock_identity="clock", source_record_digest="a" * 64,
        attestation_digest="b" * 64)
    group = TransactionGroupCommitTimeAttestation(kind="transaction_group_commit",
        attestation_id="group-time", source_id="source", operation_fence_id="fence",
        transaction_group_id="group", operation_ids=("operation",), transaction_started_at=NOW,
        transaction_committed_at=NOW, graph_revision_before="before", graph_revision_after="graph",
        applied_graph_delta_digest="c" * 64, clock_identity="clock", committed_batch_digest="d" * 64,
        attestation_digest="e" * 64)
    cursor = IngestionTimeAttestationCursorPayload(schema_version=1, stream_position=1,
        preceding_attestation_kind=source.kind, preceding_attestation_id=source.attestation_id,
        preceding_attestation_digest=source.attestation_digest, request=request,
        page_policy_revision="policy", page_policy_digest="f" * 64,
        caller_context_digest="1" * 64, authorization_decision_digest="2" * 64,
        authorization_expires_at=NOW + timedelta(minutes=10), cohort_digest="3" * 64,
        snapshot_token="token", snapshot_write_revision=7, signature="0" * 128)
    state = RetainedContinuation(cursor, (source, group), NOW + timedelta(minutes=5))
    inputs = dict(retained=state, request=request, current_write_revision=7, now=NOW,
        context_digest=cursor.caller_context_digest, decision_digest=cursor.authorization_decision_digest,
        decision_expires_at=cursor.authorization_expires_at, policy_revision=cursor.page_policy_revision,
        policy_digest=cursor.page_policy_digest)
    return cursor, state, inputs


def test_complete_request_and_both_attestation_variants():
    cursor, state, inputs = fixture()
    assert continue_verified_cursor(cursor.model_dump(), **inputs) == (state.stream[1],)
    assert "view" not in type(cursor).model_fields and "system_as_of" not in type(cursor).model_fields
    payload = cursor.model_dump()
    payload.update(preceding_attestation_kind="transaction_group_commit",
                   preceding_attestation_id="group-time", preceding_attestation_digest="e" * 64)
    assert IngestionTimeAttestationCursorPayload.model_validate(payload).preceding_attestation_kind == "transaction_group_commit"
    payload["stream_position"] = 2
    next_cursor = IngestionTimeAttestationCursorPayload.model_validate(payload)
    third = state.stream[1].model_copy(update={"attestation_id": "later-group-time"})
    retained = replace(state, issued=next_cursor, stream=(*state.stream, third))
    assert continue_verified_cursor(payload, **{**inputs, "retained": retained}) == (third,)


@pytest.mark.parametrize("field,value", [
    ("schema_version", True), ("stream_position", True), ("snapshot_write_revision", True),
    ("stream_position", -1), ("preceding_attestation_kind", "entity_revision"),
    ("preceding_attestation_id", None), ("preceding_attestation_digest", None),
    ("view", "current"), ("signature", "ab"), ("authorization_expires_at", datetime(2026, 9, 8)),
])
def test_closed_shape_rejects_invalid_coordinates(field, value):
    cursor, _, _ = fixture()
    payload = {**cursor.model_dump(), field: value}
    with pytest.raises(ValidationError):
        IngestionTimeAttestationCursorPayload.model_validate(payload)


@pytest.mark.parametrize("field,value", [
    ("context_digest", "4" * 64), ("decision_digest", "5" * 64),
    ("policy_revision", "new"), ("policy_digest", "6" * 64),
    ("decision_expires_at", NOW + timedelta(minutes=11)), ("current_write_revision", 8),
    ("now", NOW + timedelta(minutes=5)),
])
def test_changed_authority_or_snapshot_rejects(field, value):
    cursor, _, inputs = fixture()
    with pytest.raises(ValueError, match="stale cursor"):
        continue_verified_cursor(cursor.model_dump(), **{**inputs, field: value})


def test_scope_and_predecessor_and_order_cannot_change():
    cursor, state, inputs = fixture()
    other = cursor.request.model_copy(update={"scope_constraint": MemoryScope(user_id="bob")})
    with pytest.raises(ValueError, match="stale cursor"):
        continue_verified_cursor(cursor.model_dump(), **{**inputs, "request": other})
    with pytest.raises(ValueError, match="invalid ordered stream"):
        continue_verified_cursor(cursor.model_dump(), **{**inputs, "retained": replace(state, stream=state.stream[::-1])})
    with pytest.raises(ValueError, match="invalid ordered stream"):
        continue_verified_cursor(cursor.model_dump(), **{**inputs, "retained": replace(state, stream=(state.stream[0], state.stream[0]))})
    bad = cursor.model_copy(update={"preceding_attestation_digest": "7" * 64})
    with pytest.raises(ValueError, match="invalid retained predecessor"):
        continue_verified_cursor(bad.model_dump(), **{**inputs, "retained": replace(state, issued=bad)})


def test_zero_predecessors_only_at_zero_and_no_empty_continuation():
    cursor, state, inputs = fixture()
    payload = {**cursor.model_dump(), "stream_position": 0,
               "preceding_attestation_kind": None, "preceding_attestation_id": None,
               "preceding_attestation_digest": None}
    zero = IngestionTimeAttestationCursorPayload.model_validate(payload)
    with pytest.raises(ValueError, match="invalid continuation position"):
        continue_verified_cursor(payload, **{**inputs, "retained": replace(state, issued=zero)})


@pytest.mark.parametrize("continuation,changes,expected", [
    (False, {"authorized": False}, "denied"),
    (True, {"authorized": False, "cursor_valid": False}, "revoked_access"),
    (True, {"size_allowed": False}, "denied"),
    (True, {"cursor_valid": False}, "invalid_cursor"),
    (True, {"revisions_current": False, "request_matches": False}, "stale_cursor"),
    (True, {"request_matches": False}, "invalid_cursor"),
    (True, {"retained": False}, "stale_cursor"),
    (False, {"revisions_current": False}, "denied"),
    (True, {}, None), (False, {}, None),
])
def test_endpoint_and_failure_dispatch(continuation, changes, expected):
    assert cursor_schema("graph_observation") == "GraphObservationCursorPayload"
    assert cursor_schema("ingestion_time_attestation") == "IngestionTimeAttestationCursorPayload"
    assert failure_dispatch(continuation=continuation, **changes) == expected


def test_tenant_and_global_count_and_byte_capacity():
    budget = RetentionReservations(total_tokens=3, tenant_tokens=2, total_bytes=10, tenant_bytes=6)
    assert budget.reserve("a", "tenant-a", 3)
    assert budget.reserve("b", "tenant-a", 3)
    assert not budget.reserve("c", "tenant-a", 1)
    assert budget.reserve("d", "tenant-b", 4)
    assert not budget.reserve("e", "tenant-c", 1)
    budget.release("d")
    assert not budget.reserve("e", "tenant-b", 5)
    assert not budget.reserve("e", "tenant-b", 7)
    budget.release("a")
    assert budget.reserve("e", "tenant-b", 5)


def test_concurrent_reservation_cannot_overbook():
    from concurrent.futures import ThreadPoolExecutor

    budget = RetentionReservations(total_tokens=1, tenant_tokens=1, total_bytes=5, tenant_bytes=5)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(lambda token: budget.reserve(token, "tenant", 5), ("a", "b")))
    assert sum(results) == 1 and len(budget.entries) == 1
