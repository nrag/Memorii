from hashlib import sha256

import pytest
from memorii.core.memory_evolution.graph_effect_contracts import CanonicalSourceIntroductionRecord
from memorii.core.memory_evolution.graph_ingestion_observation_records import (
    ObservedOperationIntroduction,
    ObservedSourceIntroduction,
    ObservedSourceOutcomeConsistencyAssessment,
)
from memorii.core.memory_evolution.graph_observation_records import ObservedEntityReference
from memorii.core.semantic_ingestion.contracts import rebuild_bootstrap_graph_effect_contracts
from pydantic import ValidationError
from tests.fixtures.semantic_ingestion.clean_room_request_fixture import (
    build_clean_room_proposal_catalogs,
)


def _digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _material():
    return build_clean_room_proposal_catalogs(
        source_id="source:observation", source_digest=_digest("source"),
        source_text="Ada works.", require_text_digest=False,
    )


def test_consistency_assessment_requires_complete_sha256_coordinates() -> None:
    body = {
        "source_id": "source", "delivery_principal_binding_digest": _digest("principal"),
        "delivery_key_digest": _digest("key"),
        "governance_carrier_artifact_digest": _digest("artifact"),
        "required_outcome_scope_set_digest": _digest("scope"),
        "source_outcome_record_digest": _digest("outcome"),
        "source_result_digest": _digest("result"), "operation_set_digest": _digest("operations"),
        "group_result_set_digest": _digest("groups"),
        "operation_fence_partition_digest": _digest("fence"),
        "observation_delta_set_digest": _digest("delta"), "status": "consistent",
        "reason_codes": (), "assessment_digest": _digest("assessment"),
    }

    assert ObservedSourceOutcomeConsistencyAssessment.model_validate(body).status == "consistent"
    with pytest.raises(ValidationError):
        ObservedSourceOutcomeConsistencyAssessment.model_validate({
            **body, "source_result_digest": "not-a-digest",
        })


def test_admissible_native_source_introduction_allows_distinct_delivery_and_reference_keys() -> None:
    rebuild_bootstrap_graph_effect_contracts()
    material = _material()
    delivery_key_digest = _digest("delivery-key")
    assert delivery_key_digest != material.message_admission_identity.authenticated_source_reference_key_digest
    native = CanonicalSourceIntroductionRecord.create(
        ingestion_record_kind="source_introduction", introduction_id="introduction",
        source_id=material.source_id, source_digest=material.source_digest,
        delivery_principal_binding_digest=material.message_admission_identity.delivery_principal_binding_digest,
        delivery_key_digest=delivery_key_digest, segment_governance=material.segment_governance,
        message_admission_identity=material.message_admission_identity,
        governance_carrier_artifact=material.governance_carrier_artifact,
        mention_span=material.owned_text, entity_revision_id="entity-revision",
        logical_entity_id="entity", independently_asserted_type_evidence_ids=("evidence",),
        operation_id="operation", operation_fence_id="fence",
    )

    observed = ObservedSourceIntroduction(
        introduction_id=native.introduction_id, source_id=native.source_id,
        source_digest=native.source_digest,
        delivery_principal_binding_digest=native.delivery_principal_binding_digest,
        delivery_key_digest=native.delivery_key_digest, segment_governance=native.segment_governance,
        message_admission_identity=native.message_admission_identity,
        governance_carrier_artifact=native.governance_carrier_artifact,
        mention_span=native.mention_span,
        entity=ObservedEntityReference(
            entity_revision_id=native.entity_revision_id,
            logical_entity_id=native.logical_entity_id, reference_path="subject",
        ),
        independently_asserted_type_evidence_ids=native.independently_asserted_type_evidence_ids,
        operation_id=native.operation_id, operation_fence_id=native.operation_fence_id,
        boundary=False, record_digest=native.record_digest,
    )

    assert observed.delivery_key_digest == delivery_key_digest


def test_operation_admission_must_bind_one_of_the_selected_governance_entries() -> None:
    material = _material()
    body = {
        "introduction_id": "introduction", "operation_id": "operation",
        "source_id": material.source_id, "source_digest": material.source_digest,
        "delivery_principal_binding_digest": _digest("principal"),
        "delivery_key_digest": _digest("delivery"),
        "segment_governance_binding_digests": (material.segment_governance.binding_digest,),
        "message_admission_key_digests": (
            material.message_admission_identity.message_admission_key_digest,
        ),
        "governance_carrier_artifact": material.governance_carrier_artifact,
        "operation_fence_id": "fence", "transaction_group_id": "group",
        "operation_kind": "claim", "predicate_id": None,
        "owned_source_spans": (material.owned_text,), "boundary": False,
        "record_digest": _digest("record"),
    }

    assert ObservedOperationIntroduction.model_validate(body).operation_id == "operation"
    with pytest.raises(ValidationError, match="governance coordinates mismatch"):
        ObservedOperationIntroduction.model_validate({
            **body, "segment_governance_binding_digests": (),
        })
