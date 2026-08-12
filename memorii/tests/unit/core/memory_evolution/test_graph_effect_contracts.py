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
from tests.unit.core.semantic_ingestion.clean_room_request_test_support import build_prepared_source_authority

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
