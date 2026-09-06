from __future__ import annotations

from hashlib import sha256

import pytest
from memorii.core.memory_evolution.graph_records import GraphReadSet
from memorii.core.memory_evolution.models import MemoryScope
from memorii.core.semantic_ingestion.contracts import (
    GovernanceCarrierArtifact,
    GroupIndependenceCertificate,
    MessageAdmissionCarrierSet,
    MessageAdmissionIdentity,
    OperationCarrierMembership,
    PlannedTransactionGroupExecution,
    PlanningArtifactReference,
    RequiredOutcomeScopeSet,
    SegmentGovernanceBinding,
    SegmentGovernanceCarrierSet,
    SourceDependencyGroup,
    TransactionSemanticGroup,
    TransactionSemanticGroupPlan,
    decode_semantic_contract,
    encode_semantic_contract,
)
from memorii.domain.enums import SourceModality
from pydantic import ValidationError


def _digest(label: str) -> str:
    return sha256(label.encode()).hexdigest()


def _artifact() -> GovernanceCarrierArtifact:
    binding = SegmentGovernanceBinding.create(
        source_id="source-1",
        segment_id="segment-1",
        message_semantic_context_digest=_digest("context"),
        effective_scope_digest=_digest("scope"),
        authority_digest=_digest("authority"),
        data_classification="internal",
        modality=SourceModality.ASSERTION,
        provider_egress_decision_digest=_digest("egress"),
        egress_disposition="allow_verbatim",
    )
    governance = SegmentGovernanceCarrierSet.create(source_id="source-1", bindings=(binding,))
    admission = MessageAdmissionIdentity.create(
        delivery_principal_binding_digest=_digest("principal"),
        authenticated_source_reference="source-ref-1",
        authenticated_source_reference_key_digest=_digest("source-ref"),
        message_bytes_digest=_digest("message"),
        segment_governance_binding_digest=binding.binding_digest,
    )
    admissions = MessageAdmissionCarrierSet.create(source_id="source-1", identities=(admission,))
    scopes = RequiredOutcomeScopeSet.create(tenant_partition_id="tenant-1", scopes=(MemoryScope(user_id="user-1"),))
    return GovernanceCarrierArtifact.create(
        artifact_id="artifact-1",
        atomic_generation=1,
        segment_governance=governance,
        message_admissions=admissions,
        required_outcome_scopes=scopes,
    )


def _operation_memberships(
    artifact: GovernanceCarrierArtifact, operation_ids: tuple[str, ...]
) -> tuple[OperationCarrierMembership, ...]:
    return tuple(
        OperationCarrierMembership(
            operation_id=operation_id,
            segment_governance_binding_digests=(artifact.segment_governance.bindings[0].binding_digest,),
            message_admission_key_digests=(artifact.message_admissions.identities[0].message_admission_key_digest,),
        )
        for operation_id in operation_ids
    )


def _plan() -> TransactionSemanticGroupPlan:
    artifact = _artifact()
    source_group = SourceDependencyGroup.create(
        operation_ids=("operation-1", "operation-2"),
        segment_ids=("segment-1",),
        kind="correction",
        source_dependency_kinds=("correction_replacement",),
        atomic=True,
        status="complete",
        reason_codes=(),
    )
    group = TransactionSemanticGroup.create(
        transaction_group_id="transaction-group-1",
        source_dependency_group_ids=(source_group.group_id,),
        operation_ids=source_group.operation_ids,
        segment_governance_bindings=artifact.segment_governance.bindings,
        message_admission_identities=artifact.message_admissions.identities,
        operation_carrier_memberships=_operation_memberships(artifact, source_group.operation_ids),
        governance_carrier_artifact=artifact,
        member_decisions=(("operation-1", "accepted"), ("operation-2", "accepted")),
        graph_dependency_record_keys=("record-1",),
        dependency_kinds=("correction_target",),
        atomic=True,
        status="commit_eligible",
    )
    planning_artifact = PlanningArtifactReference(
        artifact_id="planning-artifact-1",
        artifact_digest=_digest("planning-artifact"),
        repository_id="repository-1",
        repository_contract_fingerprint=_digest("repository-contract"),
    )
    execution = PlannedTransactionGroupExecution.create(
        transaction_group_id=group.transaction_group_id,
        planning_snapshot_digest=_digest("snapshot"),
        prefix_state_digest_before=_digest("before"),
        planning_artifact=planning_artifact,
        semantic_effect_digest=_digest("effect"),
        prefix_state_digest_after=_digest("after"),
        dependency_closure_digest=_digest("closure"),
    )
    certificate = GroupIndependenceCertificate.create(
        transaction_group_id=group.transaction_group_id,
        preceding_group_ids=(),
        preceding_execution_digests=(),
        baseline_artifact=planning_artifact,
        after_prefix_artifact=planning_artifact,
        prefix_state_digest=_digest("prefix"),
    )
    return TransactionSemanticGroupPlan.create(
        plan_id="plan-1",
        source_id="source-1",
        snapshot_token="snapshot-token-1",
        segment_governance_carriers=artifact.segment_governance,
        message_admission_carriers=artifact.message_admissions,
        governance_carrier_artifact=artifact,
        groups=(group,),
        planned_executions=(execution,),
        independence_certificates=(certificate,),
        effective_read_set=GraphReadSet.create(record_keys=(), partition_versions=(), manifest_fingerprints=()),
    )


def test_source_group_and_transaction_plan_round_trip() -> None:
    plan = _plan()

    assert decode_semantic_contract(encode_semantic_contract(plan), TransactionSemanticGroupPlan) == plan
    assert plan.groups[0].source_dependency_group_ids == (
        SourceDependencyGroup.create(
            operation_ids=("operation-1", "operation-2"),
            segment_ids=("segment-1",),
            kind="correction",
            source_dependency_kinds=("correction_replacement",),
            atomic=True,
            status="complete",
            reason_codes=(),
        ).group_id,
    )
    assert plan.groups[0].operation_ids == ("operation-1", "operation-2")


def test_carrier_sets_reject_noncanonical_or_mismatched_members() -> None:
    artifact = _artifact()
    binding = artifact.segment_governance.bindings[0]
    second = SegmentGovernanceBinding.create(
        source_id="source-1",
        segment_id="segment-2",
        message_semantic_context_digest=_digest("context-2"),
        effective_scope_digest=_digest("scope-2"),
        authority_digest=_digest("authority-2"),
        data_classification="internal",
        modality=SourceModality.ASSERTION,
        provider_egress_decision_digest=_digest("egress-2"),
        egress_disposition="allow_verbatim",
    )

    with pytest.raises(ValidationError, match="canonical"):
        SegmentGovernanceCarrierSet.create(source_id="source-1", bindings=(binding, second))
    with pytest.raises(ValidationError, match="admission bindings mismatch"):
        GovernanceCarrierArtifact.create(
            artifact_id="artifact-2",
            atomic_generation=1,
            segment_governance=SegmentGovernanceCarrierSet.create(source_id="source-1", bindings=(second,)),
            message_admissions=artifact.message_admissions,
            required_outcome_scopes=artifact.required_outcome_scopes,
        )


def test_groups_reject_split_or_noncommitting_status_mismatch() -> None:
    artifact = _artifact()
    with pytest.raises(ValidationError, match="member decisions"):
        TransactionSemanticGroup.create(
            transaction_group_id="transaction-group-1",
            source_dependency_group_ids=("source-group-1",),
            operation_ids=("operation-1", "operation-2"),
            segment_governance_bindings=artifact.segment_governance.bindings,
            message_admission_identities=artifact.message_admissions.identities,
            operation_carrier_memberships=_operation_memberships(artifact, ("operation-1", "operation-2")),
            governance_carrier_artifact=artifact,
            member_decisions=(("operation-1", "accepted"),),
            graph_dependency_record_keys=("record-1",),
            dependency_kinds=("correction_target",),
            atomic=True,
            status="commit_eligible",
        )

    with pytest.raises(ValidationError, match="status does not match"):
        TransactionSemanticGroup.create(
            transaction_group_id="transaction-group-1",
            source_dependency_group_ids=("source-group-1",),
            operation_ids=("operation-1",),
            segment_governance_bindings=artifact.segment_governance.bindings,
            message_admission_identities=artifact.message_admissions.identities,
            operation_carrier_memberships=_operation_memberships(artifact, ("operation-1",)),
            governance_carrier_artifact=artifact,
            member_decisions=(("operation-1", "unresolved"),),
            graph_dependency_record_keys=("record-1",),
            dependency_kinds=("correction_target",),
            atomic=True,
            status="commit_eligible",
        )


def test_governance_contracts_reject_coercion_and_mismatched_plan_carriers() -> None:
    binding = _artifact().segment_governance.bindings[0]
    payload = binding.model_dump(mode="python")
    payload["modality"] = "assertion"
    with pytest.raises(ValidationError):
        SegmentGovernanceBinding.model_validate(payload)

    plan = _plan()
    mismatch = plan.model_dump(mode="python")
    mismatch["message_admission_carriers"] = MessageAdmissionCarrierSet.create(
        source_id="source-2", identities=plan.message_admission_carriers.identities
    )
    with pytest.raises(ValidationError, match="carrier source mismatch"):
        TransactionSemanticGroupPlan.model_validate(mismatch)



