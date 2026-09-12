from hashlib import sha256

import pytest
from memorii.core.memory_evolution.graph_effect_contracts import (
    CanonicalSourceTerminalOutcomeCore,
    CanonicalSourceTerminalOutcomeRecord,
    IngestionObservationDelta,
    IngestionObservationRecordMutation,
)
from memorii.core.semantic_ingestion.contracts import (
    contract_digest,
    rebuild_bootstrap_graph_effect_contracts,
)
from memorii.core.semantic_ingestion.event_replay import SemanticMemoryEventBatch
from tests.fixtures.semantic_ingestion.clean_room_request_fixture import build_prepared_source_authority

rebuild_bootstrap_graph_effect_contracts()


def _digest(label: str) -> str:
    return sha256(label.encode()).hexdigest()


def _source_record() -> CanonicalSourceTerminalOutcomeRecord:
    source = build_prepared_source_authority(
        source_id="source:graph-effect", source_digest=_digest("source"), source_text="Ada works."
    )
    core_body = {
        "ingestion_record_kind": "source_terminal_outcome",
        "source_id": source.source_id,
        "source_digest": source.source_digest,
        "delivery_principal_binding_digest": _digest("principal"),
        "delivery_key_digest": _digest("delivery"),
        "segment_governance_carriers": source.segment_governance_carriers,
        "message_admission_carriers": source.message_admission_carriers,
        "governance_carrier_artifact": source.governance_carrier_artifact,
        "required_outcome_scopes": source.governance_carrier_artifact.required_outcome_scopes,
        "operation_fence_id": "fence:graph-effect",
        "operation_ids": ("operation:graph-effect",),
        "final_status": "evidence_only",
        "group_result_digests": (),
    }
    core = CanonicalSourceTerminalOutcomeCore(
        **core_body,
        core_digest=contract_digest(
            b"memorii.semantic-ingestion.canonical-source-terminal-outcome-core.v1", core_body
        ),
    )
    body = {
        "core": core,
        **core_body,
        "outcome_id": "outcome:graph-effect",
        "source_result_digest": _digest("source-result"),
    }
    return CanonicalSourceTerminalOutcomeRecord(
        **body,
        record_digest=contract_digest(
            b"memorii.semantic-ingestion.canonical-source-terminal-outcome-record.v1", body
        ),
    )


def test_source_terminal_outcome_is_closed_and_content_addressed() -> None:
    record = _source_record()
    assert record.record_digest
    body = record.model_dump(mode="python", exclude={"record_digest"})
    body["operation_ids"] = ("operation:other",)
    with pytest.raises(ValueError, match="closure"):
        CanonicalSourceTerminalOutcomeRecord(**body, record_digest=record.record_digest)


def test_source_terminal_outcome_create_derives_the_completed_record() -> None:
    source = build_prepared_source_authority(
        source_id="source:derived", source_digest=_digest("derived"), source_text="Ada works."
    )
    core = CanonicalSourceTerminalOutcomeCore.create(
        ingestion_record_kind="source_terminal_outcome",
        source_id=source.source_id,
        source_digest=source.source_digest,
        delivery_principal_binding_digest=_digest("principal:derived"),
        delivery_key_digest=_digest("delivery:derived"),
        segment_governance_carriers=source.segment_governance_carriers,
        message_admission_carriers=source.message_admission_carriers,
        governance_carrier_artifact=source.governance_carrier_artifact,
        required_outcome_scopes=source.governance_carrier_artifact.required_outcome_scopes,
        operation_fence_id="fence:derived",
        operation_ids=("operation:derived",),
        final_status="fully_committed",
        group_result_digests=(_digest("group:derived"),),
    )

    record = CanonicalSourceTerminalOutcomeRecord.create(
        core=core, preparation_fingerprint=_digest("preparation:derived"),
    )

    assert record.core == core
    assert record.outcome_id
    assert record.source_result_digest
    assert record.record_digest


def test_observation_delta_rejects_committed_without_graph_delta() -> None:
    record = _source_record()
    mutation_body = {
        "mutation_kind": "create",
        "ingestion_record_kind": "source_terminal_outcome",
        "record_id": record.outcome_id,
        "record_version": 1,
        "record": record,
        "record_digest": record.record_digest,
    }
    mutation = IngestionObservationRecordMutation(
        **mutation_body,
        mutation_digest=contract_digest(
            b"memorii.semantic-ingestion.ingestion-observation-record-mutation.v1", mutation_body
        ),
    )
    source = record.governance_carrier_artifact
    body = {
        "kind": "terminal_group",
        "observation_delta_id": "observation:graph-effect",
        "observation_revision_before": "observation:0",
        "observation_revision_after": "observation:1",
        "source_id": record.source_id,
        "source_digest": record.source_digest,
        "segment_governance_bindings": source.segment_governance.bindings,
        "message_admission_identities": source.message_admissions.identities,
        "governance_carrier_artifact": source,
        "operation_fence_id": record.operation_fence_id,
        "transaction_group_id": "group:graph-effect",
        "operation_ids": record.operation_ids,
        "terminal_status": "committed",
        "graph_revision_delta_digest": None,
        "observation_schema_fingerprint": _digest("observation-schema"),
        "record_mutations": (mutation,),
    }
    with pytest.raises(ValueError, match="closure"):
        IngestionObservationDelta(
            **body,
            delta_digest=contract_digest(
                b"memorii.semantic-ingestion.ingestion-observation-delta.v1", body
            ),
        )


def test_terminal_effect_rebuild_resolves_canonical_event_owner() -> None:
    from memorii.core.semantic_ingestion import contracts

    contracts.rebuild_bootstrap_graph_effect_contracts()
    assert (
        contracts.BootstrapGraphEventBatchEffectV3.model_fields["payload"].annotation
        is SemanticMemoryEventBatch
    )


def _frozen_legacy_outcome_core() -> CanonicalSourceTerminalOutcomeCore:
    source = build_prepared_source_authority(
        source_id="source:m1-freeze", source_digest=_digest("m1-freeze-source"),
        source_text="Ada works.",
    )
    return CanonicalSourceTerminalOutcomeCore.create(
        ingestion_record_kind="source_terminal_outcome",
        source_id=source.source_id,
        source_digest=source.source_digest,
        delivery_principal_binding_digest=_digest("m1-principal"),
        delivery_key_digest=_digest("m1-delivery"),
        segment_governance_carriers=source.segment_governance_carriers,
        message_admission_carriers=source.message_admission_carriers,
        governance_carrier_artifact=source.governance_carrier_artifact,
        required_outcome_scopes=source.governance_carrier_artifact.required_outcome_scopes,
        operation_fence_id="fence:m1-freeze",
        operation_ids=("operation:m1-freeze",),
        final_status="evidence_only",
        group_result_digests=(),
    )


def test_schema_1_terminal_outcome_bytes_are_frozen() -> None:
    """Schema-1 core -> outcome -> source-result -> record bytes are legacy-exact.

    The frozen literals were captured from the pre-extension contracts, so the
    new schema-2 fields must stay excluded from every preimage and from
    serialization while the declared schema version is 1.
    """
    core = _frozen_legacy_outcome_core()
    record = CanonicalSourceTerminalOutcomeRecord.create(
        core=core, preparation_fingerprint=_digest("m1-preparation"),
    )

    assert core.core_digest == (
        "f75a240f69b1c2b204417204bb7632a9792370fe2ebfe905ad21c228aca888f3"
    )
    assert record.outcome_id == (
        "a332bc813870c7cdacd5b221f94ca34028dd215a8e73ae634118df5626338c28"
    )
    assert record.source_result_digest == (
        "a351ba1bdd3ef497169359badcd3aa7839db060e5b2bd1f9c86d7302160decbc"
    )
    assert record.record_digest == (
        "f7d5dcf1c4bca01d34fb4f508857cc64444697324445288c0813a95ca17739c7"
    )
    core_dump = core.model_dump(mode="python")
    record_dump = record.model_dump(mode="python")
    assert "source_result_schema_version" not in core_dump
    assert "source_retention_attestation_digest" not in core_dump
    assert "source_result_schema_version" not in record_dump
    assert "source_retention_attestation_digest" not in record_dump
    assert sorted(core._canonical_contract_field_names()) == sorted(
        name for name in type(core).model_fields
        if name not in {
            "source_result_schema_version", "source_retention_attestation_digest",
        }
    )


def test_schema_2_terminal_outcome_requires_and_binds_the_attestation_digest() -> None:
    core = _frozen_legacy_outcome_core()
    attestation_digest = _digest("m1-admission-seal")
    schema_2_core = CanonicalSourceTerminalOutcomeCore.create(
        **{
            **core.model_dump(mode="python", exclude={"core_digest"}),
            "source_result_schema_version": 2,
            "source_retention_attestation_digest": attestation_digest,
        },
    )
    record = CanonicalSourceTerminalOutcomeRecord.create(
        core=schema_2_core, preparation_fingerprint=_digest("m1-preparation"),
    )

    assert schema_2_core.source_result_schema_version == 2
    assert record.source_result_schema_version == 2
    assert record.source_retention_attestation_digest == attestation_digest
    # Schema 2 includes both fields in every preimage: the digests must differ
    # from their schema-1 counterparts over otherwise identical material.
    schema_1_record = CanonicalSourceTerminalOutcomeRecord.create(
        core=core, preparation_fingerprint=_digest("m1-preparation"),
    )
    assert schema_2_core.core_digest != core.core_digest
    assert record.source_result_digest != schema_1_record.source_result_digest
    assert record.record_digest != schema_1_record.record_digest
    # The outcome_id formula itself is unchanged: it still digests only
    # source, fence, preparation, and core-digest fields, so the schema-2 id
    # differs only through the schema-2 core_digest it already contains.
    assert record.outcome_id != schema_1_record.outcome_id
    dump = record.model_dump(mode="python")
    assert dump["source_result_schema_version"] == 2
    assert dump["source_retention_attestation_digest"] == attestation_digest

    with pytest.raises(ValueError, match="canonical source terminal outcome core is invalid"):
        CanonicalSourceTerminalOutcomeCore.create(
            **{
                **core.model_dump(mode="python", exclude={"core_digest"}),
                "source_result_schema_version": 2,
            },
        )
    with pytest.raises(ValueError, match="canonical source terminal outcome closure is invalid"):
        CanonicalSourceTerminalOutcomeRecord(
            **{
                **record.model_dump(mode="python", exclude={"record_digest"}),
                "source_retention_attestation_digest": _digest("substituted-seal"),
            },
            record_digest=record.record_digest,
        )


def test_addressed_versioned_exclusion_hooks_default_to_no_exclusion() -> None:
    """Every other _Addressed contract keeps unfiltered fields and bytes."""
    from memorii.core.memory_evolution.graph_effect_contracts import (
        CanonicalOperationIntroductionRecord,
        GraphRecordMutation,
        _Addressed,
    )

    empty = {name: None for name in GraphRecordMutation.model_fields}
    assert _Addressed._versioned_digest_excluded_fields({}) == frozenset()
    assert GraphRecordMutation._versioned_digest_excluded_fields(empty) == frozenset()
    assert CanonicalOperationIntroductionRecord._versioned_digest_excluded_fields(
        {name: None for name in CanonicalOperationIntroductionRecord.model_fields}
    ) == frozenset()
