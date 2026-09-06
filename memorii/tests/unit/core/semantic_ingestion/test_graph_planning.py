from datetime import UTC, datetime
from hashlib import sha256

import pytest
from memorii.core.memory_evolution.graph_planning import (
    AbsentPlanningPrecondition,
    DurablePlanningPrecondition,
    DurablePlanningStateRecord,
    GraphPlanningDelta,
    GraphPlanningState,
    PendingPlanningPrecondition,
    PlanningCommitValues,
    PlanningEntityRevision,
    PlanningGraphRecordMutation,
    PlanningSnapshotGraphRecord,
    _reproject_identity_closure,
)
from memorii.core.memory_evolution.graph_records import (
    AliasRevision,
    CanonicalEntityRevisionRef,
    CitationRecord,
    ClaimProjection,
    EntityRevision,
    ProvenanceRecord,
    ReferenceDispositionRecord,
    RelationRevision,
    SnapshotGraphRecord,
    SourceAuthority,
    TypeEvidence,
    canonical_graph_codec_manifest,
    graph_record_id,
)
from memorii.core.memory_evolution.identity_lineage import identity_lineage_genesis_digest
from memorii.core.memory_evolution.semantic_state import (
    CompiledIdentityLineageTransition,
    LineageEntityIdentity,
    LineageEvidenceReference,
    LineageReferenceDisposition,
    LineageReverseReference,
)
from memorii.core.memory_evolution.time_contracts import TimeInterval
from memorii.core.semantic_ingestion.contracts import (
    ActionRevision,
    IdentityLineageRecord,
    OperationTemporalAttachmentBinding,
    OperationTemporalDecisionBinding,
    TemporalTransitionRecord,
    contract_digest,
)
from planning_serialized_oracle import apply_serialized, materialize_serialized
from tests.fixtures.semantic_ingestion.semantic_terminal_fixture import accepted_terminal

NOW = datetime(2026, 8, 3, tzinfo=UTC)


def _semantic_record(*, version: int, lifecycle: str, operation_id: str) -> EntityRevision:
    codec = {item.record_kind: item for item in canonical_graph_codec_manifest().entries}["entity_revision"]
    return EntityRevision.create(
        operation_id=operation_id,
        record_version=version,
        codec_fingerprint=codec.codec_fingerprint,
        entity_revision_id="entity:alice:v1",
        logical_entity_id="entity:alice",
        lifecycle=lifecycle,
        source_evidence=(),
    )


def _durable(record: EntityRevision) -> SnapshotGraphRecord:
    codec = {item.record_kind: item for item in canonical_graph_codec_manifest().entries}["entity_revision"]
    return SnapshotGraphRecord(
        record_id=record.entity_revision_id,
        record_version=record.record_version,
        payload=record,
        codec_fingerprint=codec.codec_fingerprint,
        persistence_schema_fingerprint=codec.payload_schema_fingerprint,
        record_digest=record.record_digest,
    )


def _planned(record: EntityRevision, group_id: str) -> PlanningSnapshotGraphRecord:
    codec = {item.record_kind: item for item in canonical_graph_codec_manifest().entries}["entity_revision"]
    payload = PlanningEntityRevision(
        planning_record=record.model_dump(
            mode="python", exclude={"record_digest"}
        ),
    )
    return PlanningSnapshotGraphRecord.create(
        record_id=record.entity_revision_id,
        record_version=record.record_version,
        payload=payload,
        planning_projection_codec_fingerprint=codec.planning_projection_codec_fingerprint,
        planning_projection_schema_fingerprint=codec.planning_projection_schema_fingerprint,
    )


def _empty_state() -> GraphPlanningState:
    return GraphPlanningState.create(
        base_snapshot_digest="0" * 64,
        records=(),
        codec_manifest_fingerprint=canonical_graph_codec_manifest().manifest_fingerprint,
        applied_planned_delta_digests=(),
    )


def _commit_values(group_id: str) -> PlanningCommitValues:
    return PlanningCommitValues(
        transaction_group_id=group_id,
        graph_revision_before="revision:before",
        graph_revision_after="revision:after",
        committed_at=NOW,
    )


def test_create_applies_exact_prefix_and_materializes_only_authorizing_group() -> None:
    state = _empty_state()
    record = _semantic_record(version=1, lifecycle="active", operation_id="group:create")
    mutation = PlanningGraphRecordMutation.create(
        mutation_kind="create",
        record_kind="entity_revision",
        record_id=record.entity_revision_id,
        before=AbsentPlanningPrecondition(),
        after_planning_record=_planned(record, "group:create"),
    )
    delta = GraphPlanningDelta.create(
        sequence=1,
        base_state_digest=state.state_digest,
        producing_transaction_group_id="group:create",
        mutations=(mutation,),
    )

    pending = state.apply(delta)
    oracle_pending = apply_serialized(
        state.model_dump(mode="python"), delta.model_dump(mode="python")
    )
    assert oracle_pending == pending.model_dump(mode="python")
    materialized = pending.materialize(
        authorizing_transaction_group_id="group:create",
        commit_values=_commit_values("group:create"),
        durable_records=(_durable(record),),
    )
    assert materialize_serialized(
        oracle_pending,
        authorizing_group="group:create",
        commit_values=_commit_values("group:create").model_dump(mode="python"),
        durable_records=(_durable(record).model_dump(mode="python"),),
    ) == materialized.model_dump(mode="python")

    assert isinstance(materialized.records[0], DurablePlanningStateRecord)
    assert "transaction_coordinates" not in mutation.after_planning_record.payload.model_dump(
        mode="python"
    )
    with pytest.raises(ValueError, match="prebound_record_digest"):
        PlanningEntityRevision(
            planning_record=record.model_dump(mode="python")
        )
    with pytest.raises(ValueError, match="reapplied|wrong_prefix"):
        pending.apply(delta)
    with pytest.raises(ValueError, match="reapplied|wrong_prefix"):
        apply_serialized(oracle_pending, delta.model_dump(mode="python"))
    with pytest.raises(ValueError, match="group_scope"):
        pending.materialize(
            authorizing_transaction_group_id="group:foreign",
            commit_values=_commit_values("group:foreign"),
            durable_records=(_durable(record),),
        )


def test_update_can_retire_entity_and_rejects_skipped_prefix() -> None:
    active = _semantic_record(version=1, lifecycle="active", operation_id="group:create")
    state = GraphPlanningState.create(
        base_snapshot_digest="1" * 64,
        records=(DurablePlanningStateRecord(record=_durable(active)),),
        codec_manifest_fingerprint=canonical_graph_codec_manifest().manifest_fingerprint,
        applied_planned_delta_digests=(),
    )
    retired = _semantic_record(version=2, lifecycle="retired", operation_id="group:retire")
    mutation = PlanningGraphRecordMutation.create(
        mutation_kind="update",
        record_kind="entity_revision",
        record_id=active.entity_revision_id,
        before=DurablePlanningPrecondition(
            record_version=active.record_version,
            record_digest=active.record_digest,
        ),
        after_planning_record=_planned(retired, "group:retire"),
    )
    skipped = GraphPlanningDelta.create(
        sequence=2,
        base_state_digest=state.state_digest,
        producing_transaction_group_id="group:retire",
        mutations=(mutation,),
    )

    with pytest.raises(ValueError, match="prefix_skipped"):
        state.apply(skipped)

    delta = GraphPlanningDelta.create(
        sequence=1,
        base_state_digest=state.state_digest,
        producing_transaction_group_id="group:retire",
        mutations=(mutation,),
    )
    result = state.apply(delta).materialize(
        authorizing_transaction_group_id="group:retire",
        commit_values=_commit_values("group:retire"),
        durable_records=(_durable(retired),),
    )
    durable = result.records[0]
    assert isinstance(durable, DurablePlanningStateRecord)
    assert durable.record.payload.lifecycle == "retired"


def test_pending_prefix_and_producer_match_independent_serialized_applicator() -> None:
    state = _empty_state()
    first_record = _semantic_record(
        version=1, lifecycle="active", operation_id="group:first"
    )
    first_mutation = PlanningGraphRecordMutation.create(
        mutation_kind="create",
        record_kind="entity_revision",
        record_id=first_record.entity_revision_id,
        before=AbsentPlanningPrecondition(),
        after_planning_record=_planned(first_record, "group:first"),
    )
    first_delta = GraphPlanningDelta.create(
        sequence=1,
        base_state_digest=state.state_digest,
        producing_transaction_group_id="group:first",
        mutations=(first_mutation,),
    )
    pending = state.apply(first_delta)
    second_record = _semantic_record(
        version=2, lifecycle="retired", operation_id="group:second"
    )
    second_mutation = PlanningGraphRecordMutation.create(
        mutation_kind="update",
        record_kind="entity_revision",
        record_id=second_record.entity_revision_id,
        before=PendingPlanningPrecondition(
            producing_transaction_group_id="group:first",
            record_version=first_mutation.after_planning_record.record_version,
            planning_record_digest=first_mutation.after_planning_record.planning_record_digest,
        ),
        after_planning_record=_planned(second_record, "group:second"),
    )
    second_delta = GraphPlanningDelta.create(
        sequence=2,
        base_state_digest=pending.state_digest,
        producing_transaction_group_id="group:second",
        mutations=(second_mutation,),
    )

    production = pending.apply(second_delta)
    oracle = apply_serialized(
        pending.model_dump(mode="python"), second_delta.model_dump(mode="python")
    )
    assert oracle == production.model_dump(mode="python")

    wrong_before = second_mutation.model_copy(
        update={
            "before": second_mutation.before.model_copy(
                update={"producing_transaction_group_id": "group:foreign"}
            )
        }
    )
    wrong_delta = second_delta.model_copy(update={"mutations": (wrong_before,)})
    with pytest.raises(ValueError, match="precondition"):
        pending.apply(wrong_delta)
    with pytest.raises(ValueError, match="precondition"):
        apply_serialized(
            pending.model_dump(mode="python"), wrong_delta.model_dump(mode="python")
        )


def test_snapshot_graph_record_closed_union_round_trips_all_twelve_kinds() -> None:
    manifest = {item.record_kind: item for item in canonical_graph_codec_manifest().entries}
    claim = accepted_terminal(operation_id="closed-union:claim").accepted_carriers[0]
    evidence = LineageEvidenceReference(
        source_id="source:test", start=0, end=1, evidence_digest=sha256(b"e").hexdigest()
    )
    transition = CompiledIdentityLineageTransition.create(
        operation_id="closed-union:identity",
        operation="alias",
        predecessors=(),
        successors=(),
        graph_revision_before="genesis",
        recorded_at=NOW,
        lineage_snapshot_before_digest=identity_lineage_genesis_digest("semantic_ingestion"),
        source_evidence=(evidence,),
        reverse_reference_closure=(),
        reference_dispositions=(),
    )
    attachment = OperationTemporalAttachmentBinding.create(
        operation_id=transition.operation_id,
        temporal_role="transition",
        stable_attachment_consensus_digest=claim.temporal_decision_binding.temporal_attachment.stable_attachment_consensus_digest,
        candidate_ids=claim.temporal_decision_binding.temporal_attachment.candidate_ids,
        candidate_spans=claim.temporal_decision_binding.temporal_attachment.candidate_spans,
    )
    binding = OperationTemporalDecisionBinding.create(
        operation_id=transition.operation_id,
        temporal_role="transition",
        scope_assessment_digest=claim.temporal_decision_binding.scope_assessment_digest,
        semantic_assessment_digest=claim.temporal_decision_binding.semantic_assessment_digest,
        temporal_attachment=attachment,
        decision_closure=claim.temporal_decision_binding.decision_closure,
    )

    def temporal_record(cls, *, record_kind: str, **extra):
        body = {
            "record_kind": record_kind,
            "operation_id": claim.operation_id,
            "valid_interval": claim.valid_interval,
            "temporal_evidence": claim.temporal_evidence,
            "temporal_decision_binding": claim.temporal_decision_binding,
            "record_version": 1,
            "codec_fingerprint": manifest[record_kind].codec_fingerprint,
            **extra,
        }
        return cls.model_validate(
            body | {"record_digest": contract_digest(b"memorii.semantic-ingestion.temporal-carrier.v1", body)}
        )

    identity_body = {
        "record_kind": "identity_lineage",
        "operation_id": transition.operation_id,
        "valid_interval": claim.valid_interval,
        "temporal_evidence": claim.temporal_evidence,
        "temporal_decision_binding": binding,
        "record_version": 1,
        "codec_fingerprint": manifest["identity_lineage"].codec_fingerprint,
        "identity_lineage_id": transition.transition_digest,
        "statement_digest": transition.transition_digest,
        "transition": transition,
    }
    identity = IdentityLineageRecord.model_validate(
        identity_body
        | {"record_digest": contract_digest(b"memorii.semantic-ingestion.temporal-carrier.v1", identity_body)}
    )
    records = (
        _semantic_record(version=1, lifecycle="active", operation_id="closed-union"),
        AliasRevision.create(
            operation_id="closed-union",
            alias_revision_id="alias:v1",
            entity_revision_id="entity:alice:v1",
            logical_entity_id="entity:alice",
            alias_namespace="people",
            normalized_alias_key="alice",
            source_evidence=(evidence,),
            record_version=1,
            codec_fingerprint=manifest["alias_revision"].codec_fingerprint,
        ),
        TypeEvidence.create(
            operation_id="closed-union",
            evidence_id="type:v1",
            entity_reference=CanonicalEntityRevisionRef(
                entity_revision_id="entity:alice:v1", logical_entity_id="entity:alice"
            ),
            asserted_type="person",
            origin="verified_graph_type_assertion",
            source_evidence=(),
            registry_record_id=None,
            authority=SourceAuthority(
                authority_class="official", authenticated_provenance_class="host", policy_revision="r1"
            ),
            valid_interval=None,
            recorded_at=NOW,
            proof_ancestry_ids=(),
            proof_policy_fingerprint="1" * 64,
            record_version=1,
            codec_fingerprint=manifest["type_evidence"].codec_fingerprint,
        ),
        claim,
        ClaimProjection.create(
            operation_id="closed-union",
            claim_projection_id="projection:v1",
            claim_assertion_id=claim.claim_assertion_id,
            subject_entity_revision_id="entity:alice:v1",
            subject_logical_entity_id="entity:alice",
            object_entity_revision_id=None,
            object_logical_entity_id=None,
            record_version=1,
            codec_fingerprint=manifest["claim_projection"].codec_fingerprint,
        ),
        RelationRevision.create(
            operation_id="closed-union",
            relation_revision_id="relation:v1",
            subject_entity_revision_id="entity:alice:v1",
            subject_logical_entity_id="entity:alice",
            object_entity_revision_id="entity:globex:v1",
            object_logical_entity_id="entity:globex",
            predicate_id="works_for",
            record_version=1,
            codec_fingerprint=manifest["relation_revision"].codec_fingerprint,
        ),
        temporal_record(
            ActionRevision, record_kind="action_revision", action_revision_id="action:v1", statement_digest="2" * 64
        ),
        CitationRecord.create(
            operation_id="closed-union",
            citation_id="citation:v1",
            cited_record_id=claim.claim_assertion_id,
            entity_revision_id=None,
            logical_entity_id=None,
            record_version=1,
            codec_fingerprint=manifest["citation"].codec_fingerprint,
        ),
        ProvenanceRecord.create(
            operation_id="closed-union",
            provenance_id="provenance:v1",
            source_id="source:test",
            entity_revision_id=None,
            logical_entity_id=None,
            record_version=1,
            codec_fingerprint=manifest["provenance"].codec_fingerprint,
        ),
        temporal_record(
            TemporalTransitionRecord,
            record_kind="temporal_transition",
            transition_kind="correction",
            transition_id="transition:v1",
            statement_digest="3" * 64,
            system_interval=TimeInterval(start=NOW),
        ),
        identity,
        ReferenceDispositionRecord.create(
            operation_id="closed-union",
            reference_disposition_id="disposition:v1",
            target_record_kind="claim_assertion",
            target_record_id=claim.claim_assertion_id,
            target_reference_path="subject",
            predecessor_entity_revision_id="entity:alice:v1",
            predecessor_logical_entity_id="entity:alice",
            successor_entity_revision_ids=(),
            successor_logical_entity_ids=(),
            disposition="unresolved",
            basis="insufficient_evidence",
            source_evidence=(),
            record_version=1,
            codec_fingerprint=manifest["reference_disposition"].codec_fingerprint,
        ),
    )

    envelopes = tuple(
        SnapshotGraphRecord(
            record_id=graph_record_id(record),
            record_version=record.record_version,
            payload=record,
            codec_fingerprint=manifest[record.record_kind].codec_fingerprint,
            persistence_schema_fingerprint=manifest[record.record_kind].payload_schema_fingerprint,
            record_digest=record.record_digest,
        )
        for record in records
    )
    assert tuple(item.payload_record_kind for item in envelopes) == tuple(item.record_kind for item in records)
    assert tuple(SnapshotGraphRecord.model_validate(item.model_dump(mode="python")) for item in envelopes) == envelopes
    for envelope in envelopes:
        for field, invalid in (
            ("record_id", "substituted"),
            ("record_version", envelope.record_version + 1),
            ("record_digest", "0" * 64),
            ("codec_fingerprint", "0" * 64),
            ("persistence_schema_fingerprint", "0" * 64),
        ):
            corrupted = envelope.model_dump(mode="python")
            corrupted[field] = invalid
            with pytest.raises(ValueError):
                SnapshotGraphRecord.model_validate(corrupted)
    unknown = envelopes[0].model_dump(mode="python")
    unknown["payload"]["record_kind"] = "unknown"
    with pytest.raises(ValueError):
        SnapshotGraphRecord.model_validate(unknown)


def test_identity_closure_reprojects_mutable_relation_as_one_versioned_after_record() -> None:
    codec = {
        item.record_kind: item for item in canonical_graph_codec_manifest().entries
    }["relation_revision"]
    relation = RelationRevision.create(
        operation_id="original",
        relation_revision_id="relation:alice-employer",
        subject_entity_revision_id="entity:alice:v1",
        subject_logical_entity_id="entity:alice",
        object_entity_revision_id="entity:globex:v1",
        object_logical_entity_id="entity:globex",
        predicate_id="works_for",
        record_version=1,
        codec_fingerprint=codec.codec_fingerprint,
    )
    predecessor = LineageEntityIdentity(
        entity_revision_id="entity:alice:v1", logical_entity_id="entity:alice"
    )
    successor = LineageEntityIdentity(
        entity_revision_id="entity:alice:v2", logical_entity_id="entity:alice"
    )
    references = tuple(
        LineageReverseReference.create(
            record_kind="relation_revision",
            record_id=relation.relation_revision_id,
            reference_path=path,
            predecessor=predecessor,
            lifecycle="current",
            base_record_digest=relation.record_digest,
            referenced_value_digest=sha256(path.encode()).hexdigest(),
        )
        for path in ("subject_entity_revision_id", "subject_logical_entity_id")
    )
    dispositions = tuple(
        LineageReferenceDisposition.create(
            reference_digest=reference.reference_digest,
            record_kind=reference.record_kind,
            record_id=reference.record_id,
            reference_path=reference.reference_path,
            predecessor=predecessor,
            disposition="redirect_current",
            successors=(successor,),
            source_evidence=(),
            basis="operation_defined_rekey_redirect",
        )
        for reference in references
    )
    transition = CompiledIdentityLineageTransition.create(
        operation_id="rekey:alice:v2",
        operation="rekey",
        predecessors=(predecessor,),
        successors=(successor,),
        graph_revision_before="graph:1",
        recorded_at=NOW,
        lineage_snapshot_before_digest=identity_lineage_genesis_digest(
            "semantic_ingestion"
        ),
        source_evidence=(
            LineageEvidenceReference(
                source_id="source:rekey",
                start=0,
                end=1,
                evidence_digest=sha256(b"rekey").hexdigest(),
            ),
        ),
        reverse_reference_closure=tuple(
            sorted(references, key=lambda item: item.reference_digest)
        ),
        reference_dispositions=tuple(
            sorted(dispositions, key=lambda item: item.reference_digest)
        ),
    )
    materialized = type(
        "Materialized",
        (),
        {
            "record_kind": relation.record_kind,
            "record_id": relation.relation_revision_id,
            "record_digest": relation.record_digest,
            "record": relation,
        },
    )()
    snapshot = type(
        "Snapshot",
        (),
        {
            "graph_state": type(
                "GraphState", (), {"materialized_records": (materialized,)}
            )()
        },
    )()

    outputs = _reproject_identity_closure(
        graph_snapshot=snapshot,
        compiled_transition=transition,
        operation_id=transition.operation_id,
    )

    assert len(outputs) == 1
    after = outputs[0]
    assert isinstance(after, RelationRevision)
    assert after.record_version == 2
    assert after.operation_id == transition.operation_id
    assert after.subject_entity_revision_id == successor.entity_revision_id
    assert after.subject_logical_entity_id == successor.logical_entity_id
    assert after.object_entity_revision_id == relation.object_entity_revision_id

    entity = EntityRevision.create(
        operation_id="original",
        entity_revision_id=predecessor.entity_revision_id,
        logical_entity_id=predecessor.logical_entity_id,
        lifecycle="active",
        source_evidence=(),
        record_version=1,
        codec_fingerprint={
            item.record_kind: item
            for item in canonical_graph_codec_manifest().entries
        }["entity_revision"].codec_fingerprint,
    )
    logical_reference = LineageReverseReference.create(
        record_kind="entity_revision",
        record_id=entity.entity_revision_id,
        reference_path="logical_entity_id",
        predecessor=predecessor,
        lifecycle="current",
        base_record_digest=entity.record_digest,
        referenced_value_digest=sha256(b"logical_entity_id").hexdigest(),
    )
    logical_disposition = LineageReferenceDisposition.create(
        reference_digest=logical_reference.reference_digest,
        record_kind=logical_reference.record_kind,
        record_id=logical_reference.record_id,
        reference_path=logical_reference.reference_path,
        predecessor=predecessor,
        disposition="redirect_current",
        successors=(successor,),
        source_evidence=(),
        basis="operation_defined_rekey_redirect",
    )
    no_op_transition = CompiledIdentityLineageTransition.create(
        operation_id=transition.operation_id,
        operation=transition.operation,
        predecessors=transition.predecessors,
        successors=transition.successors,
        graph_revision_before=transition.graph_revision_before,
        recorded_at=transition.recorded_at,
        lineage_snapshot_before_digest=transition.lineage_snapshot_before_digest,
        source_evidence=transition.source_evidence,
        reverse_reference_closure=(logical_reference,),
        reference_dispositions=(logical_disposition,),
    )
    entity_snapshot = type(
        "Snapshot",
        (),
        {
            "graph_state": type(
                "GraphState",
                (),
                {
                    "materialized_records": (
                        type(
                            "Materialized",
                            (),
                            {
                                "record_kind": entity.record_kind,
                                "record_id": entity.entity_revision_id,
                                "record_digest": entity.record_digest,
                                "record": entity,
                            },
                        )(),
                    )
                },
            )()
        },
    )()

    assert _reproject_identity_closure(
        graph_snapshot=entity_snapshot,
        compiled_transition=no_op_transition,
        operation_id=transition.operation_id,
    ) == ()


def test_identity_closure_reprojects_each_current_projection_and_preserves_history() -> None:
    codecs = {
        item.record_kind: item for item in canonical_graph_codec_manifest().entries
    }
    evidence = LineageEvidenceReference(
        source_id="source:rekey",
        start=0,
        end=1,
        evidence_digest=sha256(b"rekey-complete").hexdigest(),
    )
    alias = AliasRevision.create(
        operation_id="original",
        alias_revision_id="alias:alice",
        entity_revision_id="entity:alice:v1",
        logical_entity_id="entity:alice",
        alias_namespace="people",
        normalized_alias_key="alice",
        source_evidence=(evidence,),
        record_version=1,
        codec_fingerprint=codecs["alias_revision"].codec_fingerprint,
    )
    projection = ClaimProjection.create(
        operation_id="original",
        claim_projection_id="projection:alice-employer",
        claim_assertion_id="claim:alice-employer",
        subject_entity_revision_id="entity:alice:v1",
        subject_logical_entity_id="entity:alice",
        object_entity_revision_id=None,
        object_logical_entity_id=None,
        record_version=4,
        codec_fingerprint=codecs["claim_projection"].codec_fingerprint,
    )
    type_evidence = TypeEvidence.create(
        operation_id="original",
        evidence_id="type:alice",
        entity_reference=CanonicalEntityRevisionRef(
            entity_revision_id="entity:alice:v1",
            logical_entity_id="entity:alice",
        ),
        asserted_type="person",
        origin="verified_graph_type_assertion",
        source_evidence=(),
        registry_record_id=None,
        authority=SourceAuthority(
            authority_class="official",
            authenticated_provenance_class="host",
            policy_revision="r1",
        ),
        valid_interval=None,
        recorded_at=NOW,
        proof_ancestry_ids=(),
        proof_policy_fingerprint="1" * 64,
        record_version=1,
        codec_fingerprint=codecs["type_evidence"].codec_fingerprint,
    )
    historical = CitationRecord.create(
        operation_id="original",
        citation_id="citation:alice",
        cited_record_id="claim:alice-employer",
        entity_revision_id="entity:alice:v1",
        logical_entity_id="entity:alice",
        record_version=1,
        codec_fingerprint=codecs["citation"].codec_fingerprint,
    )
    provenance = ProvenanceRecord.create(
        operation_id="original",
        provenance_id="provenance:alice",
        source_id="source:alice",
        entity_revision_id="entity:alice:v1",
        logical_entity_id="entity:alice",
        record_version=1,
        codec_fingerprint=codecs["provenance"].codec_fingerprint,
    )
    prior_disposition = ReferenceDispositionRecord.create(
        operation_id="original",
        reference_disposition_id="disposition:prior",
        target_record_kind="relation_revision",
        target_record_id="relation:prior",
        target_reference_path="subject_entity_revision_id",
        predecessor_entity_revision_id="entity:older:v1",
        predecessor_logical_entity_id="entity:older",
        successor_entity_revision_ids=("entity:alice:v1",),
        successor_logical_entity_ids=("entity:alice",),
        disposition="redirect_current",
        basis="operation_defined_rekey_redirect",
        source_evidence=(),
        record_version=1,
        codec_fingerprint=codecs["reference_disposition"].codec_fingerprint,
    )
    predecessor = LineageEntityIdentity(
        entity_revision_id="entity:alice:v1", logical_entity_id="entity:alice"
    )
    successor = LineageEntityIdentity(
        entity_revision_id="entity:people:v1", logical_entity_id="entity:people"
    )
    bob = LineageEntityIdentity(
        entity_revision_id="entity:bob:v1", logical_entity_id="entity:bob"
    )

    references: list[LineageReverseReference] = []
    dispositions: list[LineageReferenceDisposition] = []
    for record, paths in (
        (alias, (("entity_revision_id", "current"), ("logical_entity_id", "current"))),
        (
            projection,
            (
                ("subject_entity_revision_id", "current"),
                ("subject_logical_entity_id", "current"),
            ),
        ),
        (
            historical,
            (("entity_revision_id", "historical"), ("logical_entity_id", "current")),
        ),
        (
            provenance,
            (("entity_revision_id", "historical"), ("logical_entity_id", "current")),
        ),
        (
            type_evidence,
            (
                ("entity_reference.entity_revision_id", "historical"),
                ("entity_reference.logical_entity_id", "current"),
            ),
        ),
        (
            prior_disposition,
            (
                ("successor_entity_revision_ids[]", "current"),
                ("successor_logical_entity_ids[]", "current"),
            ),
        ),
    ):
        for path, lifecycle in paths:
            reference = LineageReverseReference.create(
                record_kind=record.record_kind,
                record_id=graph_record_id(record),
                reference_path=path,
                predecessor=predecessor,
                lifecycle=lifecycle,
                base_record_digest=record.record_digest,
                referenced_value_digest=sha256(
                    f"{record.record_kind}:{path}".encode()
                ).hexdigest(),
            )
            references.append(reference)
            dispositions.append(
                LineageReferenceDisposition.create(
                    reference_digest=reference.reference_digest,
                    record_kind=reference.record_kind,
                    record_id=reference.record_id,
                    reference_path=reference.reference_path,
                    predecessor=predecessor,
                    disposition=(
                        "redirect_current"
                        if lifecycle == "current"
                        else "preserve_historical"
                    ),
                    successors=(successor,) if lifecycle == "current" else (),
                    source_evidence=(),
                    basis=(
                        "operation_defined_merge_redirect"
                        if lifecycle == "current"
                        else "operation_defined_history_preservation"
                    ),
                )
            )
    transition = CompiledIdentityLineageTransition.create(
        operation_id="merge:people:v1",
        operation="merge",
        predecessors=tuple(
            sorted((predecessor, bob), key=lambda item: item.entity_revision_id)
        ),
        successors=(successor,),
        graph_revision_before="graph:1",
        recorded_at=NOW,
        lineage_snapshot_before_digest=identity_lineage_genesis_digest(
            "semantic_ingestion"
        ),
        source_evidence=(evidence,),
        reverse_reference_closure=tuple(
            sorted(references, key=lambda item: item.reference_digest)
        ),
        reference_dispositions=tuple(
            sorted(dispositions, key=lambda item: item.reference_digest)
        ),
    )

    def snapshot(*records):
        materialized = tuple(
            type(
                "Materialized",
                (),
                {
                    "record_kind": record.record_kind,
                    "record_id": graph_record_id(record),
                    "record_digest": record.record_digest,
                    "record": record,
                },
            )()
            for record in records
        )
        return type(
            "Snapshot",
            (),
            {
                "graph_state": type(
                    "GraphState", (), {"materialized_records": materialized}
                )()
            },
        )()

    outputs = _reproject_identity_closure(
        graph_snapshot=snapshot(
            alias,
            projection,
            historical,
            provenance,
            type_evidence,
            prior_disposition,
        ),
        compiled_transition=transition,
        operation_id=transition.operation_id,
    )

    assert tuple(type(item) for item in outputs) == (
        AliasRevision,
        CitationRecord,
        ClaimProjection,
        ProvenanceRecord,
        ReferenceDispositionRecord,
        TypeEvidence,
    )
    assert tuple(item.record_version for item in outputs) == (2, 2, 5, 2, 2, 2)
    assert all(item.operation_id == transition.operation_id for item in outputs)
    assert outputs[0].entity_revision_id == successor.entity_revision_id
    assert outputs[0].logical_entity_id == successor.logical_entity_id
    assert outputs[2].subject_entity_revision_id == successor.entity_revision_id
    assert outputs[2].subject_logical_entity_id == successor.logical_entity_id
    citation_after = outputs[1]
    assert citation_after.entity_revision_id == historical.entity_revision_id
    assert citation_after.logical_entity_id == successor.logical_entity_id
    provenance_after = outputs[3]
    assert provenance_after.entity_revision_id == provenance.entity_revision_id
    assert provenance_after.logical_entity_id == successor.logical_entity_id
    disposition_after = outputs[4]
    assert disposition_after.successor_entity_revision_ids == (
        successor.entity_revision_id,
    )
    assert disposition_after.successor_logical_entity_ids == (
        successor.logical_entity_id,
    )
    type_after = outputs[5]
    assert type_after.entity_reference.entity_revision_id == (
        type_evidence.entity_reference.entity_revision_id
    )
    assert type_after.entity_reference.logical_entity_id == successor.logical_entity_id

    stale_alias = alias.model_copy(update={"record_digest": "0" * 64})
    with pytest.raises(ValueError, match="closure_record_stale"):
        _reproject_identity_closure(
            graph_snapshot=snapshot(
                stale_alias,
                projection,
                historical,
                provenance,
                type_evidence,
                prior_disposition,
            ),
            compiled_transition=transition,
            operation_id=transition.operation_id,
        )


def test_certified_payload_corrupted_bindings_still_fail_inside_active_arena() -> None:
    from memorii.core.semantic_ingestion.canonical_evidence_arena import (
        CanonicalEvidenceArena,
    )

    manifest = {item.record_kind: item for item in canonical_graph_codec_manifest().entries}
    with CanonicalEvidenceArena(enabled=True) as arena:
        record = ReferenceDispositionRecord.create(
            operation_id="certified-binding",
            reference_disposition_id="disposition:v1",
            target_record_kind="claim_assertion",
            target_record_id="claim:target",
            target_reference_path="subject",
            predecessor_entity_revision_id="entity:alice:v1",
            predecessor_logical_entity_id="entity:alice",
            successor_entity_revision_ids=(),
            successor_logical_entity_ids=(),
            disposition="unresolved",
            basis="insufficient_evidence",
            source_evidence=(),
            record_version=1,
            codec_fingerprint=manifest["reference_disposition"].codec_fingerprint,
        )
        # Prove the certified path is the one under test: the construction
        # certified the record inside this operation.
        assert arena._digest_verification_scope.lookup_certified_instance(record) is not None
        envelope = SnapshotGraphRecord(
            record_id=graph_record_id(record),
            record_version=record.record_version,
            payload=record,
            codec_fingerprint=manifest[record.record_kind].codec_fingerprint,
            persistence_schema_fingerprint=manifest[record.record_kind].payload_schema_fingerprint,
            record_digest=record.record_digest,
        )
        assert envelope.payload is record
        for field, invalid in (
            ("record_id", "substituted"),
            ("record_version", envelope.record_version + 1),
            ("record_digest", "0" * 64),
            ("codec_fingerprint", "0" * 64),
            ("persistence_schema_fingerprint", "0" * 64),
        ):
            corrupted = envelope.model_dump(mode="python")
            corrupted[field] = invalid
            with pytest.raises(ValueError, match="snapshot_graph_record_binding_mismatch"):
                SnapshotGraphRecord.model_validate(corrupted)


def test_uncertified_items_keep_the_adapter_path_inside_active_arena() -> None:
    from memorii.core.memory_evolution.graph_records import (
        canonical_graph_record_adapter,
    )
    from memorii.core.semantic_ingestion.canonical_evidence_arena import (
        CanonicalEvidenceArena,
    )

    manifest = {item.record_kind: item for item in canonical_graph_codec_manifest().entries}
    original_validate = canonical_graph_record_adapter().validate_python
    calls = {"n": 0}

    def counting(values):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        return original_validate(values)

    with CanonicalEvidenceArena(enabled=True):
        # Bypass-constructed (uncertified) record: every conversion keeps
        # the adapter path; nothing is shared.
        uncertified = ReferenceDispositionRecord.model_construct(
            **ReferenceDispositionRecord.create(
                operation_id="uncertified-path",
                reference_disposition_id="disposition:v2",
                target_record_kind="claim_assertion",
                target_record_id="claim:target",
                target_reference_path="subject",
                predecessor_entity_revision_id="entity:alice:v1",
                predecessor_logical_entity_id="entity:alice",
                successor_entity_revision_ids=(),
                successor_logical_entity_ids=(),
                disposition="unresolved",
                basis="insufficient_evidence",
                source_evidence=(),
                record_version=1,
                codec_fingerprint=manifest["reference_disposition"].codec_fingerprint,
            ).model_dump(mode="python")
        )
        canonical_graph_record_adapter().validate_python = counting
        try:
            from memorii.core.memory_evolution.graph_planning import _snapshot_record

            _snapshot_record(uncertified, manifest["reference_disposition"])
        finally:
            canonical_graph_record_adapter().validate_python = original_validate
        assert calls["n"] >= 1
