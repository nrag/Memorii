"""Complete canonical graph-record fixtures for replay and codec tests."""

from datetime import UTC, datetime
from hashlib import sha256

from memorii.core.memory_evolution.graph_records import (
    AliasRevision,
    CanonicalEntityRevisionRef,
    CitationRecord,
    ClaimProjection,
    EntityRevision,
    ProvenanceRecord,
    ReferenceDispositionRecord,
    RelationRevision,
    SourceAuthority,
    TypeEvidence,
    canonical_graph_codec_manifest,
)
from memorii.core.memory_evolution.identity_lineage import (
    identity_lineage_genesis_digest,
)
from memorii.core.memory_evolution.semantic_state import (
    CompiledIdentityLineageTransition,
    LineageEvidenceReference,
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
from pydantic import BaseModel
from semantic_terminal_test_support import accepted_terminal

NOW = datetime(2026, 8, 3, tzinfo=UTC)


def all_canonical_graph_records(
    *, repository_id: str = "semantic_ingestion"
) -> tuple[BaseModel, ...]:
    """Return one valid version-one record for every closed graph kind."""

    manifest = {
        item.record_kind: item for item in canonical_graph_codec_manifest().entries
    }
    claim = accepted_terminal(
        operation_id="complete-graph-records:claim"
    ).accepted_carriers[0]
    evidence = LineageEvidenceReference(
        source_id="source:test",
        start=0,
        end=1,
        evidence_digest=sha256(b"complete-graph-records").hexdigest(),
    )
    transition = CompiledIdentityLineageTransition.create(
        operation_id="complete-graph-records:identity",
        operation="alias",
        predecessors=(),
        successors=(),
        graph_revision_before="genesis",
        recorded_at=NOW,
        lineage_snapshot_before_digest=identity_lineage_genesis_digest(
            repository_id
        ),
        source_evidence=(evidence,),
        reverse_reference_closure=(),
        reference_dispositions=(),
    )
    source_attachment = claim.temporal_decision_binding.temporal_attachment
    attachment = OperationTemporalAttachmentBinding.create(
        operation_id=transition.operation_id,
        temporal_role="transition",
        stable_attachment_consensus_digest=(
            source_attachment.stable_attachment_consensus_digest
        ),
        candidate_ids=source_attachment.candidate_ids,
        candidate_spans=source_attachment.candidate_spans,
    )
    binding = OperationTemporalDecisionBinding.create(
        operation_id=transition.operation_id,
        temporal_role="transition",
        scope_assessment_digest=(
            claim.temporal_decision_binding.scope_assessment_digest
        ),
        semantic_assessment_digest=(
            claim.temporal_decision_binding.semantic_assessment_digest
        ),
        temporal_attachment=attachment,
        decision_closure=claim.temporal_decision_binding.decision_closure,
    )

    def temporal_record(record_type, *, record_kind: str, **extra):
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
        return record_type.model_validate(
            body
            | {
                "record_digest": contract_digest(
                    b"memorii.semantic-ingestion.temporal-carrier.v1", body
                )
            }
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
        | {
            "record_digest": contract_digest(
                b"memorii.semantic-ingestion.temporal-carrier.v1", identity_body
            )
        }
    )
    return (
        EntityRevision.create(
            operation_id="complete-graph-records",
            entity_revision_id="entity:alice:v1",
            logical_entity_id="entity:alice",
            lifecycle="active",
            source_evidence=(),
            record_version=1,
            codec_fingerprint=manifest["entity_revision"].codec_fingerprint,
        ),
        AliasRevision.create(
            operation_id="complete-graph-records",
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
            operation_id="complete-graph-records",
            evidence_id="type:v1",
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
            codec_fingerprint=manifest["type_evidence"].codec_fingerprint,
        ),
        claim,
        ClaimProjection.create(
            operation_id="complete-graph-records",
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
            operation_id="complete-graph-records",
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
            ActionRevision,
            record_kind="action_revision",
            action_revision_id="action:v1",
            statement_digest="2" * 64,
        ),
        CitationRecord.create(
            operation_id="complete-graph-records",
            citation_id="citation:v1",
            cited_record_id=claim.claim_assertion_id,
            entity_revision_id=None,
            logical_entity_id=None,
            record_version=1,
            codec_fingerprint=manifest["citation"].codec_fingerprint,
        ),
        ProvenanceRecord.create(
            operation_id="complete-graph-records",
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
            operation_id="complete-graph-records",
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
            codec_fingerprint=manifest[
                "reference_disposition"
            ].codec_fingerprint,
        ),
    )


def next_canonical_graph_record_versions(
    records: tuple[BaseModel, ...],
    *,
    graph_revision_before: str,
) -> tuple[BaseModel, ...]:
    """Advance every fixture record without changing its stable identity."""

    temporal_kinds = {
        "claim_assertion",
        "action_revision",
        "identity_lineage",
        "temporal_transition",
    }
    advanced = []
    for record in records:
        values = record.model_dump(mode="python", exclude={"record_digest"})
        values["record_version"] = record.record_version + 1
        if isinstance(record, IdentityLineageRecord):
            transition_values = record.transition.model_dump(
                mode="python", exclude={"transition_digest"}
            )
            transition_values["graph_revision_before"] = graph_revision_before
            transition_values["lineage_snapshot_before_digest"] = (
                record.transition.lineage_snapshot_after_digest
            )
            transition = CompiledIdentityLineageTransition.create(**transition_values)
            values["transition"] = transition
            values["identity_lineage_id"] = transition.transition_digest
            values["statement_digest"] = transition.transition_digest
            # Lineage transitions are immutable revisions: advancing the graph
            # creates a new stable record rather than versioning the old one.
            values["record_version"] = 1
        if record.record_kind in temporal_kinds:
            advanced.append(
                type(record).model_validate(
                    values
                    | {
                        "record_digest": contract_digest(
                            b"memorii.semantic-ingestion.temporal-carrier.v1",
                            values,
                        )
                    }
                )
            )
        else:
            values.pop("record_kind", None)
            advanced.append(type(record).create(**values))
    return tuple(advanced)
