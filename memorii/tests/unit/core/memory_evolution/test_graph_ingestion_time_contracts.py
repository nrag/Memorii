from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest
from memorii.core.memory_evolution.graph_ingestion_time_contracts import (
    ProductionIngestionTimeAttestation,
    SourceRetentionTimeAttestation,
    TransactionGroupCommitTimeAttestation,
)
from pydantic import TypeAdapter, ValidationError


def _digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def test_attestations_round_trip_through_the_closed_production_alias() -> None:
    retained_at = datetime(2026, 9, 7, tzinfo=UTC)
    source = SourceRetentionTimeAttestation(
        kind="source_retention", attestation_id="source-attestation", source_id="source",
        operation_fence_id="fence", retained_at=retained_at, graph_revision="graph",
        clock_identity="clock", source_record_digest=_digest("source-record"),
        attestation_digest=_digest("source-attestation"),
    )
    group = TransactionGroupCommitTimeAttestation(
        kind="transaction_group_commit", attestation_id="group-attestation", source_id="source",
        operation_fence_id="fence", transaction_group_id="group", operation_ids=("operation",),
        transaction_started_at=retained_at, transaction_committed_at=retained_at,
        graph_revision_before="graph-before", graph_revision_after="graph-after",
        applied_graph_delta_digest=_digest("delta"), clock_identity="clock",
        committed_batch_digest=_digest("batch"), attestation_digest=_digest("group-attestation"),
    )
    adapter = TypeAdapter(ProductionIngestionTimeAttestation)

    assert adapter.validate_python(source.model_dump(mode="python")) == source
    assert adapter.validate_python(group.model_dump(mode="python")) == group


def test_attestation_times_are_utc_and_commit_cannot_precede_start() -> None:
    body = {
        "kind": "transaction_group_commit", "attestation_id": "group-attestation",
        "source_id": "source", "operation_fence_id": "fence", "transaction_group_id": "group",
        "operation_ids": ("operation",), "transaction_started_at": datetime(2026, 9, 7, tzinfo=UTC),
        "transaction_committed_at": datetime(2026, 9, 7, tzinfo=UTC),
        "graph_revision_before": "graph-before", "graph_revision_after": "graph-after",
        "applied_graph_delta_digest": _digest("delta"), "clock_identity": "clock",
        "committed_batch_digest": _digest("batch"), "attestation_digest": _digest("attestation"),
    }

    with pytest.raises(ValidationError, match="precedes"):
        TransactionGroupCommitTimeAttestation.model_validate({
            **body, "transaction_committed_at": body["transaction_started_at"] - timedelta(seconds=1),
        })
    with pytest.raises(ValidationError, match="UTC"):
        SourceRetentionTimeAttestation.model_validate({
            "kind": "source_retention", "attestation_id": "source-attestation", "source_id": "source",
            "operation_fence_id": "fence", "retained_at": datetime(2026, 9, 7),
            "graph_revision": "graph", "clock_identity": "clock",
            "source_record_digest": _digest("record"), "attestation_digest": _digest("attestation"),
        })
