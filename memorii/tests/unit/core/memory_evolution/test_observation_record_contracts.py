from hashlib import sha256

import pytest
from memorii.core.memory_evolution.graph_effect_contracts import (
    CanonicalIngestionObservationDelta,
    CanonicalIngestionObservationRecord,
    CanonicalOperationIntroductionRecord,
    CanonicalOperationTerminalOutcomeRecord,
    CanonicalSourceIntroductionRecord,
    CanonicalSourceTerminalOutcomeCore,
    CanonicalSourceTerminalOutcomeRecord,
    GraphEffectCodec,
    IngestionObservationDelta,
    IngestionObservationRecordMutation,
    SourceFinalizationObservationDelta,
)
from memorii.core.memory_evolution.models import MemoryScope
from memorii.core.semantic_ingestion.contracts import (
    RequiredOutcomeScopeSet,
    rebuild_bootstrap_graph_effect_contracts,
)
from pydantic import TypeAdapter
from tests.fixtures.semantic_ingestion.clean_room_request_fixture import (
    build_clean_room_proposal_catalogs,
)

rebuild_bootstrap_graph_effect_contracts()


def _digest(label: str) -> str:
    return sha256(label.encode("ascii")).hexdigest()


def _source_material():
    return build_clean_room_proposal_catalogs(
        source_id="source:observation-record",
        source_digest=_digest("source:observation-record"),
        source_text="Ada works.",
        require_text_digest=False,
    )


def _source_terminal(material) -> CanonicalSourceTerminalOutcomeRecord:
    core = CanonicalSourceTerminalOutcomeCore.create(
        ingestion_record_kind="source_terminal_outcome",
        source_id=material.source_id,
        source_digest=material.source_digest,
        delivery_principal_binding_digest=_digest("principal"),
        delivery_key_digest=_digest("delivery"),
        segment_governance_carriers=material.governance_carrier_artifact.segment_governance,
        message_admission_carriers=material.governance_carrier_artifact.message_admissions,
        governance_carrier_artifact=material.governance_carrier_artifact,
        required_outcome_scopes=material.governance_carrier_artifact.required_outcome_scopes,
        operation_fence_id="fence:observation-record",
        operation_ids=("operation:observation-record",),
        final_status="evidence_only",
        group_result_digests=(),
    )
    return CanonicalSourceTerminalOutcomeRecord.create(
        core=core,
        preparation_fingerprint=material.preparation_fingerprint,
    )


def _records(material):
    common = {
        "source_id": material.source_id,
        "source_digest": material.source_digest,
        "delivery_principal_binding_digest": _digest("principal"),
        "delivery_key_digest": _digest("delivery"),
        "governance_carrier_artifact": material.governance_carrier_artifact,
        "operation_fence_id": "fence:observation-record",
    }
    source_introduction = CanonicalSourceIntroductionRecord.create(
        ingestion_record_kind="source_introduction",
        introduction_id="introduction:source",
        segment_governance=material.segment_governance,
        message_admission_identity=material.message_admission_identity,
        mention_span=material.owned_text,
        entity_revision_id="entity-revision:ada",
        logical_entity_id="entity:ada",
        independently_asserted_type_evidence_ids=("evidence:type:ada",),
        operation_id="operation:observation-record",
        **common,
    )
    operation_introduction = CanonicalOperationIntroductionRecord.create(
        ingestion_record_kind="operation_introduction",
        introduction_id="introduction:operation",
        operation_id="operation:observation-record",
        segment_governance_bindings=(material.segment_governance,),
        message_admission_identities=(material.message_admission_identity,),
        transaction_group_id="group:observation-record",
        operation_kind="claim",
        predicate_id="employs",
        owned_source_spans=(material.owned_text,),
        **common,
    )
    operation_terminal = CanonicalOperationTerminalOutcomeRecord.create(
        ingestion_record_kind="operation_terminal_outcome",
        outcome_id="outcome:operation",
        operation_id="operation:observation-record",
        segment_governance_bindings=(material.segment_governance,),
        message_admission_identities=(material.message_admission_identity,),
        transaction_group_id="group:observation-record",
        final_status="evidence_only",
        retry_disposition="terminal",
        graph_revision_delta_digest=None,
        temporal_decision_bindings=(),
        authorizing_plan_lineage_entry_digest=_digest("lineage"),
        execution_manifest_digest=_digest("manifest"),
        reason_codes=("insufficient_evidence",),
        **common,
    )
    return source_introduction, operation_introduction, operation_terminal


def _terminal_group_delta(material) -> IngestionObservationDelta:
    _, introduction, outcome = _records(material)
    mutations = tuple(
        IngestionObservationRecordMutation.create(
            mutation_kind="create",
            ingestion_record_kind=record.ingestion_record_kind,
            record_id=record.introduction_id
            if isinstance(record, CanonicalOperationIntroductionRecord)
            else record.outcome_id,
            record_version=1,
            record=record,
            record_digest=record.record_digest,
        )
        for record in (introduction, outcome)
    )
    return IngestionObservationDelta.create(
        kind="terminal_group",
        observation_delta_id="observation:terminal-group",
        observation_revision_before="observation:0",
        observation_revision_after="observation:1",
        source_id=material.source_id,
        source_digest=material.source_digest,
        segment_governance_bindings=(material.segment_governance,),
        message_admission_identities=(material.message_admission_identity,),
        governance_carrier_artifact=material.governance_carrier_artifact,
        operation_fence_id="fence:observation-record",
        transaction_group_id="group:observation-record",
        operation_ids=("operation:observation-record",),
        terminal_status="evidence_only",
        graph_revision_delta_digest=None,
        observation_schema_fingerprint=_digest("observation-schema"),
        record_mutations=mutations,
    )


def test_all_observation_record_variants_round_trip_through_discriminated_contract() -> None:
    material = _source_material()
    adapter = TypeAdapter(CanonicalIngestionObservationRecord)
    records = (*_records(material), _source_terminal(material))

    for record in records:
        restored = adapter.validate_python(record.model_dump(mode="python"))
        assert type(restored) is type(record)
        assert restored.record_digest == record.record_digest
        assert type(GraphEffectCodec.validate_python(record.model_dump(mode="python"))) is type(record)


def test_source_terminal_fixture_remains_compatible_with_expanded_record_union() -> None:
    record = _source_terminal(_source_material())
    restored = TypeAdapter(CanonicalIngestionObservationRecord).validate_python(
        record.model_dump(mode="python")
    )

    assert isinstance(restored, CanonicalSourceTerminalOutcomeRecord)
    assert restored.model_dump(mode="python") == record.model_dump(mode="python")


def test_mutation_rejects_kind_and_digest_substitution() -> None:
    source_introduction, _, _ = _records(_source_material())
    mutation = IngestionObservationRecordMutation.create(
        mutation_kind="create",
        ingestion_record_kind="source_introduction",
        record_id=source_introduction.introduction_id,
        record_version=1,
        record=source_introduction,
        record_digest=source_introduction.record_digest,
    )
    body = mutation.model_dump(mode="python", exclude={"mutation_digest"})

    with pytest.raises(ValueError, match="closure"):
        IngestionObservationRecordMutation.create(
            **{**body, "ingestion_record_kind": "operation_introduction"}
        )
    with pytest.raises(ValueError, match="closure"):
        IngestionObservationRecordMutation.create(
            **{**body, "record_digest": _digest("substituted-record")}
        )
    with pytest.raises(ValueError):
        IngestionObservationRecordMutation.create(**{**body, "record_version": "1"})


def test_records_reject_cross_source_span_and_unknown_kind() -> None:
    material = _source_material()
    other_material = build_clean_room_proposal_catalogs(
        source_id="source:other",
        source_digest=_digest("source:other"),
        source_text="Grace works.",
        require_text_digest=False,
    )
    source_introduction, _, _ = _records(material)
    body = source_introduction.model_dump(mode="python", exclude={"record_digest"})

    with pytest.raises(ValueError, match="closure"):
        CanonicalSourceIntroductionRecord.create(**{**body, "mention_span": other_material.owned_text})
    with pytest.raises(ValueError, match="closure"):
        CanonicalSourceIntroductionRecord.create(
            **{**body, "segment_governance": other_material.segment_governance}
        )
    with pytest.raises(ValueError):
        TypeAdapter(CanonicalIngestionObservationRecord).validate_python(
            {**source_introduction.model_dump(mode="python"), "ingestion_record_kind": "unknown"}
        )


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("source_id", "source:substituted"),
        ("source_digest", _digest("source:substituted")),
        ("operation_fence_id", "fence:substituted"),
        ("transaction_group_id", "group:substituted"),
        ("operation_ids", ("operation:substituted",)),
    ),
)
def test_terminal_group_rejects_new_record_container_coordinate_substitution(
    field: str, replacement: object
) -> None:
    delta = _terminal_group_delta(_source_material())
    body = delta.model_dump(mode="python", exclude={"delta_digest"})

    with pytest.raises(ValueError, match="closure"):
        IngestionObservationDelta.create(**{**body, field: replacement})


def test_source_finalization_binds_exact_source_terminal_coordinates() -> None:
    material = _source_material()
    outcome = _source_terminal(material)
    delta = SourceFinalizationObservationDelta.create(
        kind="source_finalization",
        observation_delta_id="observation:source-finalization",
        observation_revision_before="observation:0",
        observation_revision_after="observation:1",
        source_id=outcome.source_id,
        source_digest=outcome.source_digest,
        delivery_principal_binding_digest=outcome.delivery_principal_binding_digest,
        delivery_key_digest=outcome.delivery_key_digest,
        segment_governance_carriers=outcome.segment_governance_carriers,
        message_admission_carriers=outcome.message_admission_carriers,
        governance_carrier_artifact=outcome.governance_carrier_artifact,
        required_outcome_scopes=outcome.required_outcome_scopes,
        operation_fence_id=outcome.operation_fence_id,
        operation_ids=outcome.operation_ids,
        source_outcome=outcome,
        observation_schema_fingerprint=_digest("observation-schema"),
    )
    body = delta.model_dump(mode="python", exclude={"delta_digest"})

    assert TypeAdapter(CanonicalIngestionObservationDelta).validate_python(
        delta.model_dump(mode="python")
    ) == delta
    assert GraphEffectCodec.validate_python(delta.model_dump(mode="python")) == delta
    with pytest.raises(ValueError, match="closure"):
        SourceFinalizationObservationDelta.create(**{**body, "source_digest": _digest("substituted-source")})
    with pytest.raises(ValueError, match="closure"):
        SourceFinalizationObservationDelta.create(
            **{
                **body,
                "required_outcome_scopes": RequiredOutcomeScopeSet.create(
                    tenant_partition_id="tenant:substituted",
                    scopes=(MemoryScope(user_id="user:substituted"),),
                ),
            }
        )


def test_terminal_group_binds_committed_operation_to_group_graph_delta() -> None:
    delta = _terminal_group_delta(_source_material())
    original = delta.record_mutations[-1].record
    assert isinstance(original, CanonicalOperationTerminalOutcomeRecord)
    graph_digest = _digest("committed-graph")
    outcome = CanonicalOperationTerminalOutcomeRecord.create(**{
        **original.model_dump(mode="python", exclude={"record_digest"}),
        "final_status": "committed", "graph_revision_delta_digest": graph_digest,
    })
    mutation = IngestionObservationRecordMutation.create(
        mutation_kind="create", ingestion_record_kind="operation_terminal_outcome",
        record_id=outcome.outcome_id, record_version=1, record=outcome,
        record_digest=outcome.record_digest,
    )
    body = {
        **delta.model_dump(mode="python", exclude={"delta_digest"}),
        "terminal_status": "committed", "graph_revision_delta_digest": graph_digest,
        "record_mutations": (delta.record_mutations[0], mutation),
    }
    assert IngestionObservationDelta.create(**body).terminal_status == "committed"
    with pytest.raises(ValueError, match="closure"):
        IngestionObservationDelta.create(**{**body, "graph_revision_delta_digest": _digest("foreign-graph")})
    with pytest.raises(ValueError, match="closure"):
        IngestionObservationDelta.create(**{
            **body, "terminal_status": "evidence_only", "graph_revision_delta_digest": None,
        })


def test_source_terminal_only_delta_still_requires_source_container_binding() -> None:
    material = _source_material()
    record = _source_terminal(material)
    mutation = IngestionObservationRecordMutation.create(
        mutation_kind="create", ingestion_record_kind="source_terminal_outcome",
        record_id=record.outcome_id, record_version=1, record=record,
        record_digest=record.record_digest,
    )
    body = {
        **_terminal_group_delta(material).model_dump(mode="python", exclude={"delta_digest"}),
        "record_mutations": (mutation,),
    }
    assert IngestionObservationDelta.create(**body).source_id == record.source_id
    with pytest.raises(ValueError, match="closure"):
        IngestionObservationDelta.create(**{**body, "source_id": "foreign-source"})
