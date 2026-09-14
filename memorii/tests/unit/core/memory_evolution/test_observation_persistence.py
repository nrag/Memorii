from hashlib import sha256
from types import SimpleNamespace

import pytest
from memorii.core.memory_evolution.graph_effect_contracts import (
    CanonicalOperationIntroductionRecord,
    CanonicalOperationTerminalOutcomeRecord,
    CanonicalSourceTerminalOutcomeCore,
    CanonicalSourceTerminalOutcomeRecord,
)
from memorii.core.memory_evolution.observation_persistence import (
    ObservationPersistenceError,
    build_source_finalization_observation_delta,
    build_terminal_group_observation_delta,
)
from memorii.core.semantic_ingestion.contracts import (
    BootstrapGraphGroupCommitRequestV3,
    rebuild_bootstrap_graph_effect_contracts,
)
from tests.fixtures.semantic_ingestion.clean_room_request_fixture import (
    build_clean_room_proposal_catalogs,
)

rebuild_bootstrap_graph_effect_contracts()


def _digest(label: str) -> str:
    return sha256(label.encode("ascii")).hexdigest()


def _request() -> BootstrapGraphGroupCommitRequestV3:
    """A typed group carrier with only the coordinates this pure builder reads."""
    return BootstrapGraphGroupCommitRequestV3.model_construct(
        transaction_group_id="group:observation-persistence",
        operation_ids=("operation:observation-persistence",),
        group_plan_member=SimpleNamespace(transaction_group_id="group:observation-persistence"),
        source_plan_lineage_entry=SimpleNamespace(
            source_id="source:observation-persistence",
            source_digest=_digest("source:observation-persistence"),
        ),
        operation_fence_binding=SimpleNamespace(
            operation_fence_id="fence:observation-persistence",
            delivery_principal_binding_digest=_digest("principal"),
            delivery_key_digest=_digest("delivery"),
        ),
    )


def _records():
    material = build_clean_room_proposal_catalogs(
        source_id="source:observation-persistence",
        source_digest=_digest("source:observation-persistence"),
        source_text="Ada works.",
        require_text_digest=False,
    )
    common = {
        "source_id": material.source_id,
        "source_digest": material.source_digest,
        "delivery_principal_binding_digest": _digest("principal"),
        "delivery_key_digest": _digest("delivery"),
        "governance_carrier_artifact": material.governance_carrier_artifact,
        "operation_fence_id": "fence:observation-persistence",
        "operation_id": "operation:observation-persistence",
        "segment_governance_bindings": (material.segment_governance,),
        "message_admission_identities": (material.message_admission_identity,),
        "transaction_group_id": "group:observation-persistence",
    }
    introduction = CanonicalOperationIntroductionRecord.create(
        ingestion_record_kind="operation_introduction",
        introduction_id="introduction:operation",
        operation_kind="fact",
        predicate_id="employs",
        owned_source_spans=(material.owned_text,),
        **common,
    )
    outcome = CanonicalOperationTerminalOutcomeRecord.create(
        ingestion_record_kind="operation_terminal_outcome",
        outcome_id="outcome:operation",
        final_status="evidence_only",
        retry_disposition="terminal",
        graph_revision_delta_digest=None,
        temporal_decision_bindings=(),
        authorizing_plan_lineage_entry_digest=_digest("lineage"),
        execution_manifest_digest=_digest("manifest"),
        reason_codes=("insufficient_evidence",),
        **common,
    )
    return material, introduction, outcome


def test_builder_persists_native_terminal_records_without_relabeling_summary() -> None:
    material, introduction, outcome = _records()

    delta = build_terminal_group_observation_delta(
        request=_request(),
        materialized_graph_records=(),
        source_introductions=(),
        operation_introductions=(introduction,),
        operation_terminal_outcomes=(outcome,),
        graph_revision_delta=None,
        observation_delta_id="observation:terminal-group",
        observation_revision_before="observation:0",
        observation_revision_after="observation:1",
        observation_schema_fingerprint=_digest("observation-schema"),
        segment_governance_bindings=(material.segment_governance,),
        message_admission_identities=(material.message_admission_identity,),
        governance_carrier_artifact=material.governance_carrier_artifact,
        terminal_status="evidence_only",
    )

    assert delta.kind == "terminal_group"
    assert tuple(item.record.ingestion_record_kind for item in delta.record_mutations) == (
        "operation_introduction",
        "operation_terminal_outcome",
    )
    assert delta.graph_revision_delta_digest is None


def test_builder_rejects_records_outside_the_retained_group() -> None:
    material, introduction, outcome = _records()
    substituted = outcome.model_copy(update={"operation_id": "operation:other"})

    with pytest.raises(ObservationPersistenceError, match="close the group"):
        build_terminal_group_observation_delta(
            request=_request(),
            materialized_graph_records=(),
            source_introductions=(),
            operation_introductions=(introduction,),
            operation_terminal_outcomes=(substituted,),
            graph_revision_delta=None,
            observation_delta_id="observation:terminal-group",
            observation_revision_before="observation:0",
            observation_revision_after="observation:1",
            observation_schema_fingerprint=_digest("observation-schema"),
            segment_governance_bindings=(material.segment_governance,),
            message_admission_identities=(material.message_admission_identity,),
            governance_carrier_artifact=material.governance_carrier_artifact,
            terminal_status="evidence_only",
        )


@pytest.mark.parametrize("record_kind", ["introduction", "outcome"])
@pytest.mark.parametrize("field", ["delivery_principal_binding_digest", "delivery_key_digest"])
def test_builder_rejects_rehashed_delivery_authority_substitution(record_kind: str, field: str) -> None:
    material, introduction, outcome = _records()
    record = introduction if record_kind == "introduction" else outcome
    values = record.model_dump(mode="python", exclude={"record_digest"})
    values[field] = _digest("other-delivery-authority")
    if record_kind == "introduction":
        introduction = CanonicalOperationIntroductionRecord.create(**values)
    else:
        outcome = CanonicalOperationTerminalOutcomeRecord.create(**values)
    with pytest.raises(ObservationPersistenceError, match="authority is substituted"):
        build_terminal_group_observation_delta(
            request=_request(),
            materialized_graph_records=(),
            source_introductions=(),
            operation_introductions=(introduction,),
            operation_terminal_outcomes=(outcome,),
            graph_revision_delta=None,
            observation_delta_id="observation:terminal-group",
            observation_revision_before="observation:0",
            observation_revision_after="observation:1",
            observation_schema_fingerprint=_digest("observation-schema"),
            segment_governance_bindings=(material.segment_governance,),
            message_admission_identities=(material.message_admission_identity,),
            governance_carrier_artifact=material.governance_carrier_artifact,
            terminal_status="evidence_only",
        )


def test_source_finalization_builder_uses_only_the_canonical_source_outcome() -> None:
    material, _, _ = _records()
    outcome = CanonicalSourceTerminalOutcomeRecord.create(
        core=CanonicalSourceTerminalOutcomeCore.create(
            ingestion_record_kind="source_terminal_outcome",
            source_id=material.source_id,
            source_digest=material.source_digest,
            delivery_principal_binding_digest=_digest("principal"),
            delivery_key_digest=_digest("delivery"),
            segment_governance_carriers=material.governance_carrier_artifact.segment_governance,
            message_admission_carriers=material.governance_carrier_artifact.message_admissions,
            governance_carrier_artifact=material.governance_carrier_artifact,
            required_outcome_scopes=material.governance_carrier_artifact.required_outcome_scopes,
            operation_fence_id="fence:observation-persistence",
            operation_ids=("operation:observation-persistence",),
            final_status="evidence_only",
            group_result_digests=(),
        ),
        preparation_fingerprint=material.preparation_fingerprint,
    )

    delta = build_source_finalization_observation_delta(
        source_outcome=outcome,
        observation_delta_id="observation:source-finalization",
        observation_revision_before="observation:1",
        observation_revision_after="observation:2",
        observation_schema_fingerprint=_digest("observation-schema"),
    )

    assert delta.kind == "source_finalization"
    assert delta.source_outcome == outcome
