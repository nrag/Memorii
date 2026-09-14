from datetime import UTC, datetime
from hashlib import sha256

import pytest
from memorii.core.memory_evolution.graph_observation_contracts import (
    GraphObservationCursorPayload as LegacyCursorPayload,
)
from memorii.core.memory_evolution.graph_observation_snapshot_contracts import (
    GraphObservationCohortPreimage,
    GraphObservationCursorPayload,
    GraphObservationRecordKey,
    ResolvedGraphObservationCohort,
)
from pydantic import ValidationError


def _digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _cohort_body() -> dict[str, object]:
    return {
        "seed_source_ids": ("source",), "seed_operation_ids": (), "source_ids": ("source",),
        "operation_ids": (), "operation_fence_ids": (),
        "include_referenced_boundary_entities": True,
        "authorized_scope_identity": "scope", "authorization_policy_revision": "policy",
        "authorization_decision_digest": _digest("decision"),
        "graph_revision_delta_ids": (), "graph_revision_delta_digests": (),
        "ingestion_observation_delta_ids": (), "ingestion_observation_delta_digests": (),
        "reference_schema_manifest_fingerprint": _digest("reference-schema"),
        "reference_ledger_high_watermark": "watermark", "reference_ledger_digest": _digest("ledger"),
        "reference_audit_certificate_digest": _digest("audit"), "complete": True,
        "graph_revision": "graph", "observation_revision": "observation",
        "memory_plane_write_revision": 0,
        "temporal_projection_generation_digest": None,
        "temporal_projection_pointer_digest": None,
        "trust_projection_generation_digest": None,
        "trust_projection_pointer_digest": None,
        "observation_schema_fingerprint": _digest("observation-schema"),
        "changed_record_keys": (
            GraphObservationRecordKey(record_kind="entity_revision", primary_key="entity"),
        ),
        "boundary_record_keys": (),
    }


def test_preimage_has_no_self_digest_and_resolved_cohort_adds_only_digest() -> None:
    body = _cohort_body()
    preimage = GraphObservationCohortPreimage.model_validate(body)
    resolved = ResolvedGraphObservationCohort.model_validate({
        **body, "cohort_digest": _digest("cohort"),
    })

    assert "cohort_digest" not in GraphObservationCohortPreimage.model_fields
    assert tuple(ResolvedGraphObservationCohort.model_fields) == (
        *GraphObservationCohortPreimage.model_fields, "cohort_digest",
    )
    assert preimage.changed_record_keys == resolved.changed_record_keys


def test_cohort_rejects_projection_pair_and_changed_boundary_coordinate_errors() -> None:
    body = _cohort_body()
    with pytest.raises(ValidationError, match="coordinates are invalid"):
        GraphObservationCohortPreimage.model_validate({
            **body, "temporal_projection_generation_digest": _digest("temporal-generation"),
        })
    with pytest.raises(ValidationError, match="coordinates are invalid"):
        GraphObservationCohortPreimage.model_validate({
            **body,
            "boundary_record_keys": (
                GraphObservationRecordKey(record_kind="entity_revision", primary_key="entity"),
            ),
        })


def test_profile_three_cursor_binds_write_revision_and_leaves_legacy_import_unchanged() -> None:
    cursor = GraphObservationCursorPayload(
        schema_version=1, stream_position=0, preceding_record_kind=None,
        preceding_primary_key=None, preceding_record_digest=None, requested_total_page_size=1,
        page_policy_revision="policy", page_policy_digest=_digest("page-policy"),
        caller_context_digest=_digest("context"), authorization_decision_digest=_digest("decision"),
        authorization_expires_at=datetime(2026, 9, 7, tzinfo=UTC), cohort_digest=_digest("cohort"),
        snapshot_token="snapshot", snapshot_write_revision=0, graph_revision="graph",
        observation_revision="observation", view="current", valid_at=None,
        system_as_of=datetime(2026, 9, 7, tzinfo=UTC), signature="a" * 128,
    )

    assert cursor.snapshot_write_revision == 0
    assert "snapshot_write_revision" not in LegacyCursorPayload.model_fields
    with pytest.raises(ValidationError):
        GraphObservationCursorPayload.model_validate({
            **cursor.model_dump(mode="python"), "snapshot_write_revision": -1,
        })
    with pytest.raises(ValidationError, match="schema version must be an integer literal"):
        GraphObservationCursorPayload.model_validate({
            **cursor.model_dump(mode="python"), "schema_version": True,
        })
    with pytest.raises(ValidationError, match="predecessor"):
        GraphObservationCursorPayload.model_validate({
            **cursor.model_dump(mode="python"), "stream_position": 1,
        })
