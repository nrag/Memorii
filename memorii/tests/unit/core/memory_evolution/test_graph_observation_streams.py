from datetime import UTC, datetime
from hashlib import sha256

import pytest
from memorii.core.memory_evolution.graph_observation_records import ObservedEntityRevision
from memorii.core.memory_evolution.graph_observation_streams import (
    EntityRevisionStreamRecord,
    GraphObservationStreamRecord,
)
from memorii.core.memory_evolution.time_contracts import TimeInterval
from pydantic import TypeAdapter, ValidationError


def _digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _entity_payload() -> ObservedEntityRevision:
    return ObservedEntityRevision(
        entity_revision_id="entity-revision", logical_entity_id="entity",
        canonical_type=None, lifecycle_state="active", valid_interval=None,
        system_interval=TimeInterval(start=datetime(2026, 9, 7, tzinfo=UTC)),
        source_ids=(), operation_ids=(), boundary=False, record_digest=_digest("record"),
    )


def test_entity_stream_record_binds_explicit_primary_key_and_digest() -> None:
    payload = _entity_payload()
    record = EntityRevisionStreamRecord(
        record_kind="entity_revision", primary_key=payload.entity_revision_id,
        record_digest=payload.record_digest, payload=payload,
    )

    adapter = TypeAdapter(GraphObservationStreamRecord)
    assert adapter.validate_python(record.model_dump(mode="python")) == record
    with pytest.raises(ValidationError, match="closure mismatch"):
        EntityRevisionStreamRecord(
            record_kind="entity_revision", primary_key="other", record_digest=payload.record_digest,
            payload=payload,
        )
    with pytest.raises(ValidationError):
        adapter.validate_python({**record.model_dump(mode="python"), "record_kind": "unknown"})


def test_stream_union_has_exact_profile_three_variants() -> None:
    from memorii.core.memory_evolution import graph_observation_streams as streams

    assert len(set(streams.__all__) - {"GraphObservationStreamRecord"}) == 17
