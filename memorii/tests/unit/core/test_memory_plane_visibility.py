from __future__ import annotations

from datetime import UTC, datetime

import pytest
from memorii.core.memory_plane.models import (
    CanonicalMemoryRecord,
    to_memory_object,
    to_provider_stored_record,
)
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.domain.enums import (
    CommitStatus,
    MemoryDomain,
    MemoryRecordVisibility,
    TemporalValidityStatus,
)
from memorii.domain.retrieval import (
    DomainRetrievalQuery,
    RetrievalIntent,
    RetrievalNamespace,
    RetrievalPlan,
    RetrievalScope,
)
from pydantic import ValidationError


def _record(memory_id: str, *, visibility: MemoryRecordVisibility) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=memory_id,
        domain=MemoryDomain.EXECUTION,
        text=memory_id,
        content={"kind": "coordinator_state"},
        status=CommitStatus.COMMITTED,
        validity_status=TemporalValidityStatus.ACTIVE,
        source_kind="control:test",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        visibility=visibility,
    )


def _query() -> DomainRetrievalQuery:
    return DomainRetrievalQuery(
        domain=MemoryDomain.EXECUTION,
        scope=RetrievalScope(),
        namespace=RetrievalNamespace(memory_domain=MemoryDomain.EXECUTION),
    )


def test_internal_control_records_never_enter_runtime_or_provider_context() -> None:
    plane = MemoryPlaneService()
    internal = _record("control:operation", visibility=MemoryRecordVisibility.INTERNAL_CONTROL)
    runtime = _record("execution:visible", visibility=MemoryRecordVisibility.RUNTIME_CONTEXT)
    plane.write_records((internal, runtime))

    assert [item.memory_id for item in plane.query_runtime_memory(_query())] == [runtime.memory_id]
    trace = plane.retrieve_runtime_context(
        plan=RetrievalPlan(intent=RetrievalIntent.CONTINUE_EXECUTION, queries=[_query()])
    )
    assert trace.retrieved_ids_deduped == [runtime.memory_id]
    provider_context = plane.prefetch_provider_context(
        "continue execution",
        session_id=None,
        task_id=None,
        user_id=None,
        top_k=10,
    )
    assert internal.memory_id not in provider_context
    assert plane.get_record(internal.memory_id) == internal
    assert internal in plane.list_records()


def test_internal_control_record_cannot_be_converted_to_runtime_memory() -> None:
    internal = _record("control:operation", visibility=MemoryRecordVisibility.INTERNAL_CONTROL)

    with pytest.raises(ValueError, match="cannot enter runtime context"):
        to_memory_object(internal)


def test_internal_control_record_cannot_be_converted_to_provider_memory() -> None:
    internal = _record("control:operation", visibility=MemoryRecordVisibility.INTERNAL_CONTROL)

    with pytest.raises(ValueError, match="cannot enter provider context"):
        to_provider_stored_record(internal)


def test_unknown_record_visibility_fails_closed() -> None:
    payload = _record(
        "control:operation",
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    ).model_dump(mode="python")
    payload["visibility"] = "maybe_internal"

    with pytest.raises(ValidationError):
        CanonicalMemoryRecord.model_validate(payload)
