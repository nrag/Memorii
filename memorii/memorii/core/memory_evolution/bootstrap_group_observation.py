"""Construct the native observation audit for one materialized V3 group.

The atomic-store owner supplies the live snapshot and the two reference-ledger
snapshots from its successful CAS construction.  This leaf deliberately does
not read storage, allocate a ledger entry, or assign observation revisions.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from hashlib import sha256
from typing import TYPE_CHECKING, Literal, TypeVar

from memorii.core.memory_evolution.graph_effect_contracts import (
    CanonicalOperationIntroductionRecord,
    CanonicalOperationTerminalOutcomeRecord,
    CanonicalSourceIntroductionRecord,
    GraphRecordMutation,
    GraphRevisionDelta,
    IngestionObservationDelta,
)
from memorii.core.memory_evolution.graph_records import (
    GraphStateSnapshot,
    SnapshotGraphRecord,
    graph_digest,
    graph_record_id,
    graph_record_union_member,
)
from memorii.core.memory_evolution.reference_integrity import (
    ReferenceEdgeLedgerEntry,
    ReferenceEdgeLedgerSnapshot,
)
from memorii.core.semantic_ingestion.contracts import (
    BootstrapGraphGroupCommitRequestV3,
    BootstrapNativeFactEffectV3,
    contract_digest,
)

if TYPE_CHECKING:
    from memorii.core.memory_evolution.graph_planning import PlanningCommitValues
    from memorii.core.memory_evolution.graph_records import CanonicalGraphRecord
    from memorii.core.semantic_ingestion.contracts import (
        BootstrapGraphOperationStoreMaterializationInputV3,
        BootstrapNativeOperationReductionInputV3,
        BootstrapNativePlanningConstructionAuthorityV3,
        BootstrapProposalEvidenceItemV3,
        BootstrapProposalFactV3,
        BootstrapProposalOperationMemberV3,
        GovernanceCarrierArtifact,
        MessageAdmissionIdentity,
        SegmentGovernanceBinding,
        SourceSpanReference,
    )


_T = TypeVar("_T")


class BootstrapGroupObservationAuditError(ValueError):
    """The committed group inputs cannot establish a complete native audit."""


@dataclass(frozen=True)
class BootstrapGroupObservationAudit:
    """Canonical records assembled before the group observation delta is sealed."""

    graph_revision_delta: GraphRevisionDelta | None
    source_introductions: tuple[CanonicalSourceIntroductionRecord, ...]
    operation_introductions: tuple[CanonicalOperationIntroductionRecord, ...]
    operation_terminal_outcomes: tuple[CanonicalOperationTerminalOutcomeRecord, ...]


def build_native_group_observation_delta(
    *, request: BootstrapGraphGroupCommitRequestV3,
    audit: BootstrapGroupObservationAudit,
    materialized_graph_records: tuple[CanonicalGraphRecord, ...],
    observation_revision_before: str, observation_revision_after: str,
    observation_schema_fingerprint: str,
) -> IngestionObservationDelta:
    """Seal the audited group using the existing native delta constructor."""
    from memorii.core.memory_evolution.observation_persistence import build_terminal_group_observation_delta

    introductions = audit.operation_introductions
    segments = _sorted_unique(
        (binding for item in introductions for binding in item.segment_governance_bindings),
        key=lambda item: item.binding_digest, error="group segment governance is not canonical",
    )
    admissions = _sorted_unique(
        (identity for item in introductions for identity in item.message_admission_identities),
        key=lambda item: item.message_admission_key_digest, error="group message admissions are not canonical",
    )
    statuses = tuple(item.reduction.native_terminal.status for item in request.ordered_operation_inputs)
    status: Literal["committed", "rejected", "unresolved", "evidence_only"] = (
        "committed" if audit.graph_revision_delta is not None else
        "rejected" if statuses and all(item == "rejected" for item in statuses) else
        "unresolved" if "unresolved" in statuses else "evidence_only"
    )
    return build_terminal_group_observation_delta(
        request=request, materialized_graph_records=materialized_graph_records,
        source_introductions=audit.source_introductions,
        operation_introductions=introductions,
        operation_terminal_outcomes=audit.operation_terminal_outcomes,
        graph_revision_delta=audit.graph_revision_delta,
        observation_delta_id=_coordinate_id(
            b"memorii.semantic-ingestion.group-observation-delta-id.v1\0", request,
            request.transaction_group_id,
        ),
        observation_revision_before=observation_revision_before,
        observation_revision_after=observation_revision_after,
        observation_schema_fingerprint=observation_schema_fingerprint,
        segment_governance_bindings=segments, message_admission_identities=admissions,
        governance_carrier_artifact=request.pre_execution_manifest_identity.core.governance_carrier_artifact,
        terminal_status=status,
    )


def build_bootstrap_group_observation_audit(
    *,
    request: BootstrapGraphGroupCommitRequestV3,
    current_graph_snapshot: GraphStateSnapshot,
    materialized_graph_records: tuple[CanonicalGraphRecord, ...],
    commit_values: PlanningCommitValues,
    prior_reference_integrity: ReferenceEdgeLedgerSnapshot,
    next_reference_integrity: ReferenceEdgeLedgerSnapshot,
) -> BootstrapGroupObservationAudit:
    """Build exactly the audit facts supported by one live group materialization.

    The request carries sealed planner authority.  The live graph snapshot and
    reference-ledger pair establish the actual before/after mutation surface.
    A caller must still put this result into its same-CAS group closure.
    """
    if not isinstance(request, BootstrapGraphGroupCommitRequestV3):
        raise BootstrapGroupObservationAuditError("group request type is invalid")
    if not isinstance(current_graph_snapshot, GraphStateSnapshot):
        raise BootstrapGroupObservationAuditError("current graph snapshot type is invalid")
    if not isinstance(prior_reference_integrity, ReferenceEdgeLedgerSnapshot) or not isinstance(
        next_reference_integrity, ReferenceEdgeLedgerSnapshot
    ):
        raise BootstrapGroupObservationAuditError("reference integrity snapshot type is invalid")

    inputs = request.ordered_operation_inputs
    if tuple(item.operation_id for item in inputs) != request.operation_ids:
        raise BootstrapGroupObservationAuditError("operation inputs do not close group request")
    # The native reduction retains the sealed read authority.  A later owned
    # group may legitimately see a successor current snapshot in the same CAS
    # attempt, so this audit binds that actual snapshot without equating it to
    # every retained sealed-read coordinate.
    partition_versions = {
        item.partition_id: item.version
        for item in current_graph_snapshot.read_set.partition_versions
    }
    if partition_versions.get("reference_ledger") != prior_reference_integrity.ledger_digest:
        raise BootstrapGroupObservationAuditError("current graph reference ledger is substituted")

    accepted = tuple(
        item for item in inputs if item.reduction.native_terminal.status == "accepted"
    )
    if bool(accepted) != bool(materialized_graph_records):
        raise BootstrapGroupObservationAuditError("accepted materialization closure is incomplete")
    if any(not graph_record_union_member(record) for record in materialized_graph_records):
        raise BootstrapGroupObservationAuditError("materialized graph record type is invalid")
    if accepted:
        _validate_materialized_records(
            request=request,
            current_graph_snapshot=current_graph_snapshot,
            materialized_graph_records=materialized_graph_records,
            commit_values=commit_values,
            accepted=accepted,
        )

    authorities = tuple(_planning_authority(item) for item in inputs)
    artifact = request.pre_execution_manifest_identity.core.governance_carrier_artifact
    segment_bindings = _sorted_unique(
        (
            binding
            for authority in authorities
            for binding in authority.segment_governance.segment_governance_bindings
        ),
        key=lambda item: item.binding_digest,
        error="group segment governance is not canonical",
    )
    admission_identities = _sorted_unique(
        (identity for authority in authorities for identity in authority.message_admission_identities),
        key=lambda item: item.message_admission_key_digest,
        error="group message admissions are not canonical",
    )
    if (
        not segment_bindings
        or not admission_identities
        or any(
            authority.segment_governance.governance_carrier_artifact != artifact
            for authority in authorities
        )
        or any(binding not in artifact.segment_governance.bindings for binding in segment_bindings)
        or any(identity not in artifact.message_admissions.identities for identity in admission_identities)
    ):
        raise BootstrapGroupObservationAuditError("group governance authority is substituted")

    graph_delta = None
    if accepted:
        graph_delta = _build_graph_revision_delta(
            request=request,
            current_graph_snapshot=current_graph_snapshot,
            materialized_graph_records=materialized_graph_records,
            prior_reference_integrity=prior_reference_integrity,
            next_reference_integrity=next_reference_integrity,
            segment_bindings=segment_bindings,
            admission_identities=admission_identities,
        )
    elif _reference_suffix(prior_reference_integrity, next_reference_integrity):
        raise BootstrapGroupObservationAuditError("noncommitting group advanced reference integrity")

    return build_native_group_observation_records(request=request, graph_revision_delta=graph_delta)


def build_native_group_observation_records(
    *, request: BootstrapGraphGroupCommitRequestV3, graph_revision_delta: GraphRevisionDelta | None,
) -> BootstrapGroupObservationAudit:
    """Regenerate audit records from retained request authority and a verified delta."""
    if not isinstance(request, BootstrapGraphGroupCommitRequestV3):
        raise BootstrapGroupObservationAuditError("group request type is invalid")
    inputs = request.ordered_operation_inputs
    if tuple(item.operation_id for item in inputs) != request.operation_ids:
        raise BootstrapGroupObservationAuditError("operation inputs do not close group request")
    authorities = tuple(_planning_authority(item) for item in inputs)
    artifact = request.pre_execution_manifest_identity.core.governance_carrier_artifact
    segment_bindings = _sorted_unique((b for a in authorities for b in a.segment_governance.segment_governance_bindings), key=lambda item: item.binding_digest, error="group segment governance is not canonical")
    admission_identities = _sorted_unique((i for a in authorities for i in a.message_admission_identities), key=lambda item: item.message_admission_key_digest, error="group message admissions are not canonical")
    accepted = tuple(item for item in inputs if item.reduction.native_terminal.status == "accepted")
    if ((graph_revision_delta is None) != (not accepted) or not segment_bindings or not admission_identities
            or any(a.segment_governance.governance_carrier_artifact != artifact for a in authorities)
            or any(b not in artifact.segment_governance.bindings for b in segment_bindings)
            or any(i not in artifact.message_admissions.identities for i in admission_identities)):
        raise BootstrapGroupObservationAuditError("group governance or disposition is substituted")
    if graph_revision_delta is not None and (graph_revision_delta.transaction_group_id != request.transaction_group_id or graph_revision_delta.operation_ids != request.operation_ids or graph_revision_delta.source_ids != (request.source_plan_lineage_entry.source_id,) or graph_revision_delta.segment_governance_bindings != segment_bindings or graph_revision_delta.message_admission_identities != admission_identities or graph_revision_delta.governance_carrier_artifact != artifact):
        raise BootstrapGroupObservationAuditError("group graph delta authority is substituted")
    operation_introductions = tuple(
        _operation_introduction(request=request, item=item, authority=authority, artifact=artifact)
        for item, authority in zip(inputs, authorities, strict=True)
    )
    operation_outcomes = tuple(
        _operation_outcome(
            request=request,
            item=item,
            authority=authority,
            artifact=artifact,
            graph_delta=graph_revision_delta,
        )
        for item, authority in zip(inputs, authorities, strict=True)
    )
    source_introductions = () if graph_revision_delta is None else tuple(
        source
        for item in accepted
        for source in _source_introductions(request=request, item=item, artifact=artifact)
    )
    return BootstrapGroupObservationAudit(
        graph_revision_delta=graph_revision_delta,
        source_introductions=source_introductions,
        operation_introductions=operation_introductions,
        operation_terminal_outcomes=operation_outcomes,
    )


def _build_graph_revision_delta(
    *,
    request: BootstrapGraphGroupCommitRequestV3,
    current_graph_snapshot: GraphStateSnapshot,
    materialized_graph_records: tuple[CanonicalGraphRecord, ...],
    prior_reference_integrity: ReferenceEdgeLedgerSnapshot,
    next_reference_integrity: ReferenceEdgeLedgerSnapshot,
    segment_bindings: tuple[SegmentGovernanceBinding, ...],
    admission_identities: tuple[MessageAdmissionIdentity, ...],
) -> GraphRevisionDelta:
    before_by_key = {
        (record.payload_record_kind, record.record_id): record
        for record in current_graph_snapshot.records
    }
    after_records = _snapshot_after_records(materialized_graph_records)
    after_by_key = {
        (record.payload_record_kind, record.record_id): record
        for record in after_records
    }
    if len(after_by_key) != len(after_records):
        raise BootstrapGroupObservationAuditError("materialized graph records are duplicated")
    suffix = _reference_suffix(prior_reference_integrity, next_reference_integrity)
    changes = []
    for key, after in after_by_key.items():
        before = before_by_key.get(key)
        if before is not None and before.record_digest == after.record_digest:
            raise BootstrapGroupObservationAuditError("materialized graph record did not change")
        additions = _edges_for(suffix, key, "add")
        removals = _edges_for(suffix, key, "remove")
        changes.append(GraphRecordMutation.create(
            mutation_kind="create" if before is None else "update",
            record_kind=after.payload_record_kind,
            record_id=after.record_id,
            before_record_version=None if before is None else before.record_version,
            before_digest=None if before is None else before.record_digest,
            after_record_version=after.record_version,
            after_digest=after.record_digest,
            # _Addressed.create hashes the passed value, while GraphRecordMutation
            # validates its parsed canonical model dump. SnapshotGraphRecord's
            # payload serializer makes the typed instances observably distinct.
            after_record=after.model_dump(mode="python"),
            reference_edges_added=tuple(edge.model_dump(mode="python") for edge in additions),
            reference_edges_removed=tuple(edge.model_dump(mode="python") for edge in removals),
        ))
    changes = tuple(sorted(changes, key=lambda item: (item.record_kind, item.record_id, item.mutation_digest)))
    changed_keys = {(change.record_kind, change.record_id) for change in changes}
    if any((edge.record_kind, edge.record_id) not in changed_keys for edge in suffix):
        raise BootstrapGroupObservationAuditError("reference suffix is outside actual graph changes")
    graph_revision_after = sha256(
        b"memorii.semantic-ingestion.bootstrap-graph-group-revision.v3\0"
        + current_graph_snapshot.graph_revision.encode()
        + request.request_ctv_digest.encode()
    ).hexdigest()
    if any(
        edge.graph_revision != graph_revision_after
        or edge.operation_id != request.transaction_group_id
        for edge in suffix
    ):
        raise BootstrapGroupObservationAuditError("reference suffix is outside group authority")
    delta_id = contract_digest(
        b"memorii.semantic-ingestion.graph-revision-delta-id.v1\0",
        {
            "transaction_group_id": request.transaction_group_id,
            "graph_revision_before": current_graph_snapshot.graph_revision,
            "graph_revision_after": graph_revision_after,
            "request_ctv_digest": request.request_ctv_digest,
        },
    )
    return GraphRevisionDelta.create(
        graph_revision_delta_id=delta_id,
        graph_revision_before=current_graph_snapshot.graph_revision,
        graph_revision_after=graph_revision_after,
        source_ids=(request.source_plan_lineage_entry.source_id,),
        operation_ids=request.operation_ids,
        transaction_group_id=request.transaction_group_id,
        segment_governance_bindings=segment_bindings,
        message_admission_identities=admission_identities,
        governance_carrier_artifact=request.pre_execution_manifest_identity.core.governance_carrier_artifact,
        record_changes=tuple(change.model_dump(mode="python") for change in changes),
        read_set_digest=current_graph_snapshot.read_set.read_set_digest,
        write_set_digest=graph_digest(
            b"memorii.semantic-ingestion.graph-revision-write-set.v1\0",
            tuple(change.model_dump(mode="python") for change in changes),
        ),
    )


def _snapshot_after_records(
    records: tuple[CanonicalGraphRecord, ...],
) -> tuple[SnapshotGraphRecord, ...]:
    from memorii.core.memory_evolution.graph_planning import snapshot_record
    from memorii.core.memory_evolution.graph_records import canonical_graph_codec_manifest

    manifest = {entry.record_kind: entry for entry in canonical_graph_codec_manifest().entries}
    return tuple(
        snapshot_record(record, manifest[record.record_kind])
        for record in records
    )


def _reference_suffix(
    prior: ReferenceEdgeLedgerSnapshot, next_snapshot: ReferenceEdgeLedgerSnapshot,
) -> tuple[ReferenceEdgeLedgerEntry, ...]:
    prior_entries = prior.entries
    if next_snapshot.entries[:len(prior_entries)] != prior_entries:
        raise BootstrapGroupObservationAuditError("reference integrity history is not an exact prefix")
    return next_snapshot.entries[len(prior_entries):]


def _edges_for(
    suffix: tuple[ReferenceEdgeLedgerEntry, ...],
    key: tuple[str, str],
    change: Literal["add", "remove"],
) -> tuple[ReferenceEdgeLedgerEntry, ...]:
    return tuple(sorted(
        (edge for edge in suffix if (edge.record_kind, edge.record_id) == key and edge.change == change),
        key=lambda edge: edge.ledger_entry_digest,
    ))


def _planning_authority(
    item: BootstrapGraphOperationStoreMaterializationInputV3,
) -> BootstrapNativePlanningConstructionAuthorityV3:
    authority = item.reduction.native_compilation.operation_input.planning_construction_authority
    if authority is None:
        raise BootstrapGroupObservationAuditError("planning construction authority is absent")
    return authority


def _operation_introduction(
    *,
    request: BootstrapGraphGroupCommitRequestV3,
    item: BootstrapGraphOperationStoreMaterializationInputV3,
    authority: BootstrapNativePlanningConstructionAuthorityV3,
    artifact: GovernanceCarrierArtifact,
) -> CanonicalOperationIntroductionRecord:
    operation_input = item.reduction.native_compilation.operation_input
    member = operation_input.operation_member
    predicate_id = _predicate_id(member)
    spans = _owned_source_spans(operation_input)
    return CanonicalOperationIntroductionRecord.create(
        ingestion_record_kind="operation_introduction",
        introduction_id=_coordinate_id(
            b"memorii.semantic-ingestion.operation-introduction-id.v1\0",
            request,
            item.operation_id,
        ),
        operation_id=item.operation_id,
        source_id=request.source_plan_lineage_entry.source_id,
        source_digest=request.source_plan_lineage_entry.source_digest,
        delivery_principal_binding_digest=request.operation_fence_binding.delivery_principal_binding_digest,
        delivery_key_digest=request.operation_fence_binding.delivery_key_digest,
        segment_governance_bindings=authority.segment_governance.segment_governance_bindings,
        message_admission_identities=authority.message_admission_identities,
        governance_carrier_artifact=artifact,
        operation_fence_id=request.operation_fence_binding.operation_fence_id,
        transaction_group_id=request.transaction_group_id,
        operation_kind=item.reduction.native_terminal.operation_kind,
        predicate_id=predicate_id,
        owned_source_spans=spans,
    )


def _operation_outcome(
    *,
    request: BootstrapGraphGroupCommitRequestV3,
    item: BootstrapGraphOperationStoreMaterializationInputV3,
    authority: BootstrapNativePlanningConstructionAuthorityV3,
    artifact: GovernanceCarrierArtifact,
    graph_delta: GraphRevisionDelta | None,
) -> CanonicalOperationTerminalOutcomeRecord:
    status = item.reduction.effect_materialization.observation_disposition
    temporal = tuple(construction.temporal_decision_binding for construction in authority.temporal_constructions)
    if status == "committed" and graph_delta is None:
        raise BootstrapGroupObservationAuditError("committed operation lacks group graph delta")
    return CanonicalOperationTerminalOutcomeRecord.create(
        ingestion_record_kind="operation_terminal_outcome",
        outcome_id=_coordinate_id(
            b"memorii.semantic-ingestion.operation-terminal-outcome-id.v1\0",
            request,
            item.operation_id,
        ),
        operation_id=item.operation_id,
        source_id=request.source_plan_lineage_entry.source_id,
        source_digest=request.source_plan_lineage_entry.source_digest,
        delivery_principal_binding_digest=request.operation_fence_binding.delivery_principal_binding_digest,
        delivery_key_digest=request.operation_fence_binding.delivery_key_digest,
        segment_governance_bindings=authority.segment_governance.segment_governance_bindings,
        message_admission_identities=authority.message_admission_identities,
        governance_carrier_artifact=artifact,
        operation_fence_id=request.operation_fence_binding.operation_fence_id,
        transaction_group_id=request.transaction_group_id,
        final_status=status,
        retry_disposition="terminal",
        graph_revision_delta_digest=(
            graph_delta.delta_digest if status == "committed" and graph_delta is not None else None
        ),
        temporal_decision_bindings=temporal,
        authorizing_plan_lineage_entry_digest=request.source_plan_lineage_entry.entry_digest,
        execution_manifest_digest=request.pre_execution_manifest_identity.identity_digest,
        reason_codes=item.reduction.effect_materialization.observation_reason_codes,
    )


def _source_introductions(
    *,
    request: BootstrapGraphGroupCommitRequestV3,
    item: BootstrapGraphOperationStoreMaterializationInputV3,
    artifact: GovernanceCarrierArtifact,
) -> tuple[CanonicalSourceIntroductionRecord, ...]:
    effect = item.reduction.effect_materialization.accepted_effect
    if not isinstance(effect, BootstrapNativeFactEffectV3):
        return ()
    introductions = []
    for binding in effect.observation_mention_bindings:
        if (
            binding.operation_id != item.operation_id
            or binding.operation_execution_id != item.operation_execution_id
            or len(binding.message_admission_identities) != 1
        ):
            raise BootstrapGroupObservationAuditError("source mention admission is not singular")
        candidate = binding.target_candidate
        if candidate.type_evidence_record_ids != tuple(sorted(set(candidate.type_evidence_record_ids))):
            raise BootstrapGroupObservationAuditError("source mention type evidence is not canonical")
        introductions.append(CanonicalSourceIntroductionRecord.create(
            ingestion_record_kind="source_introduction",
            introduction_id=_coordinate_id(
                b"memorii.semantic-ingestion.source-introduction-id.v1\0",
                request,
                item.operation_id,
                binding.binding_digest,
            ),
            source_id=request.source_plan_lineage_entry.source_id,
            source_digest=request.source_plan_lineage_entry.source_digest,
            delivery_principal_binding_digest=request.operation_fence_binding.delivery_principal_binding_digest,
            delivery_key_digest=request.operation_fence_binding.delivery_key_digest,
            segment_governance=binding.segment_governance,
            message_admission_identity=binding.message_admission_identities[0],
            governance_carrier_artifact=artifact,
            mention_span=binding.mention_span,
            entity_revision_id=candidate.entity_revision_id,
            logical_entity_id=candidate.logical_entity_id,
            independently_asserted_type_evidence_ids=candidate.type_evidence_record_ids,
            operation_id=item.operation_id,
            operation_fence_id=request.operation_fence_binding.operation_fence_id,
        ))
    return tuple(sorted(introductions, key=lambda record: record.introduction_id))


def _coordinate_id(
    domain: bytes,
    request: BootstrapGraphGroupCommitRequestV3,
    operation_id: str,
    binding_digest: str | None = None,
) -> str:
    values: dict[str, str] = {
        "transaction_group_id": request.transaction_group_id,
        "request_ctv_digest": request.request_ctv_digest,
        "operation_id": operation_id,
        "operation_fence_id": request.operation_fence_binding.operation_fence_id,
    }
    if binding_digest is not None:
        values["binding_digest"] = binding_digest
    return contract_digest(domain, values)


def _predicate_id(member: BootstrapProposalOperationMemberV3) -> str | None:
    if member.kind == "fact":
        return member.predicate_id
    if member.kind == "correction":
        return member.replacement_fact.predicate_id
    if member.kind == "retraction":
        return member.retracted_fact.predicate_id
    return None


def _validate_materialized_records(
    *,
    request: BootstrapGraphGroupCommitRequestV3,
    current_graph_snapshot: GraphStateSnapshot,
    materialized_graph_records: tuple[CanonicalGraphRecord, ...],
    commit_values: PlanningCommitValues,
    accepted: tuple[BootstrapGraphOperationStoreMaterializationInputV3, ...],
) -> None:
    """Prove the supplied after-records are the exact accepted intent outputs."""
    from memorii.core.memory_evolution.graph_planning import (
        materialize_canonical_planning_payload,
    )

    expected_graph_revision_after = sha256(
        b"memorii.semantic-ingestion.bootstrap-graph-group-revision.v3\0"
        + current_graph_snapshot.graph_revision.encode()
        + request.request_ctv_digest.encode()
    ).hexdigest()
    if (
        commit_values.transaction_group_id != request.transaction_group_id
        or commit_values.graph_revision_before != current_graph_snapshot.graph_revision
        or commit_values.graph_revision_after != expected_graph_revision_after
    ):
        raise BootstrapGroupObservationAuditError("materialization commit coordinates are substituted")
    expected = tuple(
        materialize_canonical_planning_payload(
            intent.canonical_after_record,
            commit_values=commit_values,
            authorizing_transaction_group_id=request.transaction_group_id,
        )
        for item in accepted
        for intent in item.reduction.effect_materialization.record_intents
    )
    actual_by_key = {
        (record.record_kind, graph_record_id(record)): record
        for record in materialized_graph_records
    }
    expected_by_key = {
        (record.record_kind, graph_record_id(record)): record
        for record in expected
    }
    if len(actual_by_key) != len(materialized_graph_records) or len(expected_by_key) != len(expected):
        raise BootstrapGroupObservationAuditError("accepted materialization records are duplicated")
    if tuple(sorted(actual_by_key)) != tuple(sorted(expected_by_key)) or any(
        actual_by_key[key].record_digest != expected_by_key[key].record_digest
        for key in expected_by_key
    ):
        raise BootstrapGroupObservationAuditError("materialized graph records differ from accepted intents")
    before_by_key = {
        (record.payload_record_kind, record.record_id): record
        for record in current_graph_snapshot.records
    }
    for item in accepted:
        for intent in item.reduction.effect_materialization.record_intents:
            key = (intent.record_kind, intent.record_id)
            before = before_by_key.get(key)
            if (
                (intent.mutation_kind == "create") != (before is None)
                or intent.expected_prior_record_digest
                != (None if before is None else before.record_digest)
            ):
                raise BootstrapGroupObservationAuditError("accepted materialization prior is substituted")


def _owned_source_spans(
    operation_input: BootstrapNativeOperationReductionInputV3,
) -> tuple[SourceSpanReference, ...]:
    member = operation_input.operation_member
    mentions = {
        mention.mention_digest: mention.mention_span
        for mention in operation_input.normalized_proposal.mentions
    }
    spans: list[SourceSpanReference] = []

    def add_evidence(*evidence: BootstrapProposalEvidenceItemV3 | None) -> None:
        spans.extend(item.span for item in evidence if item is not None)

    def add_fact(fact: BootstrapProposalFactV3) -> None:
        add_evidence(fact.assertion, fact.predicate_anchor, *fact.temporal_qualifiers)
        mention_ids = [fact.subject_mention_digest]
        if fact.object.kind == "entity":
            mention_ids.append(fact.object.mention_digest)
        if fact.attributed_to_mention_digest is not None:
            mention_ids.append(fact.attributed_to_mention_digest)
        try:
            spans.extend(mentions[mention_id] for mention_id in mention_ids)
        except KeyError as error:
            raise BootstrapGroupObservationAuditError("operation mention authority is absent") from error

    if member.kind == "fact":
        add_fact(member)
    elif member.kind == "correction":
        add_fact(member.corrected_fact)
        add_fact(member.replacement_fact)
        add_evidence(member.assertion, member.correction_anchor)
    elif member.kind == "retraction":
        add_fact(member.retracted_fact)
        add_evidence(member.assertion, member.retraction_anchor)
    elif member.kind == "action_state":
        add_evidence(
            member.action_anchor,
            member.state_anchor,
            member.execution_branch,
            member.assertion,
            *member.temporal_qualifiers,
        )
        for role in member.role_bindings:
            for participant in role.participants:
                add_evidence(*participant.grounding)
    else:
        add_evidence(member.assertion, member.identity_anchor)
        for assignment in member.reference_assignments:
            add_evidence(assignment.assertion)
            selector = assignment.record_selector
            if selector.kind == "action":
                add_evidence(selector.action_anchor)
            elif selector.kind == "alias":
                add_evidence(selector.alias_anchor)
        mention_ids = (*member.predecessor_mention_digests, *member.successor_mention_digests)
        try:
            spans.extend(mentions[mention_id] for mention_id in mention_ids)
        except KeyError as error:
            raise BootstrapGroupObservationAuditError("operation mention authority is absent") from error
    return tuple(sorted({span.reference_digest: span for span in spans}.values(), key=lambda span: span.reference_digest))


def _sorted_unique(
    items: Iterable[_T],
    *,
    key: Callable[[_T], str],
    error: str,
) -> tuple[_T, ...]:
    materialized = tuple(sorted(items, key=key))
    deduplicated: dict[str, _T] = {}
    for item in materialized:
        item_key = key(item)
        prior = deduplicated.get(item_key)
        if prior is not None and prior != item:
            raise BootstrapGroupObservationAuditError(error)
        deduplicated[item_key] = item
    return tuple(deduplicated.values())


__all__ = [
    "BootstrapGroupObservationAudit",
    "BootstrapGroupObservationAuditError",
    "build_bootstrap_group_observation_audit",
    "build_native_group_observation_records",
]
