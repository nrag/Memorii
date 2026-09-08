from datetime import UTC, datetime
from hashlib import sha256

import pytest
from memorii.core.memory_evolution.graph_observation_records import (
    ObservedEffectiveTimeCoordinate,
    ObservedEntityReference,
    ObservedRelation,
    ObservedSystemRecordedEffectiveTime,
    ObservedTemporalClaimProjection,
    ObservedTrustClaimProjection,
)
from memorii.core.memory_evolution.semantic_state import (
    ActiveTemporalProjectionPointer,
    ActiveTrustProjectionPointer,
    TemporalProjectionRecord,
    TrustProjectionRecord,
    projection_contract_digest,
)
from memorii.core.memory_evolution.time_contracts import TimeInterval
from pydantic import TypeAdapter, ValidationError


def _digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _temporal_projection_with_pointer() -> tuple[
    TemporalProjectionRecord, ActiveTemporalProjectionPointer
]:
    projection = TemporalProjectionRecord.create(
        projection_id="projection", repository_id="repository",
        source_record_kind="claim_assertion", source_record_id="claim",
        source_record_version=1, source_record_digest=_digest("source"),
        temporal_policy_fingerprint=_digest("temporal-policy"), valid_interval=None,
        outcome="unknown", evidence=(),
    )
    pointer_body = {
        "repository_id": "repository", "policy_fingerprint": _digest("temporal-policy"),
        "generation_digest": _digest("generation"), "publication_kind": "projection_commit",
        "publication_certificate_digest": _digest("certificate"), "writer_epoch": 1,
        "pointer_revision": 1, "published_at": datetime(2026, 9, 7, tzinfo=UTC),
        "publication_sequence": 1, "predecessor_pointer_digest": None,
    }
    return projection, ActiveTemporalProjectionPointer.model_validate({
        **pointer_body,
        "pointer_digest": projection_contract_digest("temporal_pointer", pointer_body),
    })


def test_observed_entity_reference_is_closed_strict_and_immutable() -> None:
    reference = ObservedEntityReference(
        entity_revision_id="entity-revision", logical_entity_id="entity",
        reference_path="subject",
    )

    assert reference.model_config.get("extra") == "forbid"
    assert reference.model_config.get("frozen") is True
    with pytest.raises(ValidationError):
        ObservedEntityReference.model_validate({
            "entity_revision_id": "entity-revision", "logical_entity_id": "entity",
            "reference_path": "subject", "unexpected": "value",
        })
    with pytest.raises(ValidationError):
        ObservedEntityReference.model_validate({
            "entity_revision_id": 1, "logical_entity_id": "entity", "reference_path": "subject",
        })
    with pytest.raises(ValidationError):
        reference.entity_revision_id = "other"


def test_effective_time_coordinate_kind_is_closed() -> None:
    coordinate = ObservedSystemRecordedEffectiveTime(
        kind="system_recorded_only", temporal_policy_fingerprint="policy",
    )

    assert coordinate.kind == "system_recorded_only"
    adapter = TypeAdapter(ObservedEffectiveTimeCoordinate)
    assert adapter.validate_python(coordinate) == coordinate
    with pytest.raises(ValidationError):
        adapter.validate_python({"kind": "unknown", "temporal_policy_fingerprint": "policy"})


def test_structural_payload_roots_match_approved_field_authority() -> None:
    from memorii.core.memory_evolution import graph_observation_records as records

    expected = {
        "ObservedEntityReference", "ObservedAssertionEntityReference", "ObservedEntityRevision",
        "ObservedAliasRevision", "ObservedTypeEvidence", "ObservedClaimAssertion",
        "ObservedTemporalClaimProjection", "ObservedTrustClaimProjection", "ObservedRelation",
        "ObservedActionRoleBinding", "ObservedActionRevision", "ObservedCitationRecord",
        "ObservedProvenanceRecord", "ObservedTemporalTransition",
        "ObservedCertifiedTextEffectiveTime", "ObservedAuthenticatedReferenceEffectiveTime",
        "ObservedSystemRecordedEffectiveTime", "ObservedIdentityTransition",
        "ObservedReferenceDisposition",
    }

    assert expected <= set(records.__all__)


def test_projection_payloads_use_complete_native_records_and_pointers() -> None:
    assert tuple(ObservedTemporalClaimProjection.model_fields) == (
        "observation_id", "projection", "generation_digest", "publication_pointer",
        "successor_publication_pointer", "boundary", "record_digest",
    )
    assert ObservedTemporalClaimProjection.model_fields["projection"].annotation is TemporalProjectionRecord
    assert (
        ObservedTemporalClaimProjection.model_fields["publication_pointer"].annotation
        is ActiveTemporalProjectionPointer
    )
    assert tuple(ObservedTrustClaimProjection.model_fields) == (
        "observation_id", "projection", "generation_digest", "publication_pointer",
        "successor_publication_pointer", "boundary", "record_digest",
    )
    assert ObservedTrustClaimProjection.model_fields["projection"].annotation is TrustProjectionRecord
    assert (
        ObservedTrustClaimProjection.model_fields["publication_pointer"].annotation
        is ActiveTrustProjectionPointer
    )


def test_temporal_projection_payload_validates_native_pointer_binding() -> None:
    projection, pointer = _temporal_projection_with_pointer()
    body = {
        "observation_id": "observation", "projection": projection,
        "generation_digest": pointer.generation_digest, "publication_pointer": pointer,
        "successor_publication_pointer": None, "boundary": False,
        "record_digest": _digest("record"),
    }

    assert ObservedTemporalClaimProjection.model_validate(body).projection == projection
    with pytest.raises(ValidationError, match="pointer binding mismatch"):
        ObservedTemporalClaimProjection.model_validate({
            **body, "generation_digest": _digest("different-generation"),
        })


def test_relation_object_kind_requires_its_matching_endpoint_shape() -> None:
    reference = ObservedEntityReference(
        entity_revision_id="entity-revision", logical_entity_id="entity", reference_path="subject",
    )
    body = {
        "relation_id": "relation", "predicate_id": "predicate", "subject": reference,
        "object_kind": "entity", "object_entity": None, "literal_value": None,
        "supporting_claim_assertion_ids": (), "lifecycle_state": "active",
        "valid_interval": None,
        "system_interval": TimeInterval(start=datetime(2026, 9, 7, tzinfo=UTC)),
        "source_ids": (), "provenance_ids": (), "boundary": False,
        "record_digest": _digest("record"),
    }

    with pytest.raises(ValidationError, match="object does not match"):
        ObservedRelation.model_validate(body)
