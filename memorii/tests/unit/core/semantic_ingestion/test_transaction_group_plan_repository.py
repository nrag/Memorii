from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

import pytest
from memorii.core.memory_evolution.atomic_store import (
    AtomicGenerationMember,
    SourceCheckpointAtomicWriteRequest,
    generation_request_digest,
)
from memorii.core.memory_evolution.graph_records import GraphReadSet
from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
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
    SemanticArtifactClosure,
    SourceDependencyGroup,
    TransactionSemanticGroup,
    TransactionSemanticGroupPlan,
    decode_semantic_contract,
)
from memorii.core.semantic_ingestion.persistence import SemanticTerminalPersistenceService
from memorii.core.semantic_ingestion.transaction_group_plan_repository import (
    TRANSACTION_SEMANTIC_GROUP_PLAN_REPOSITORY_CONTRACT_FINGERPRINT,
    AtomicStoreTransactionSemanticGroupPlanRepository,
)
from memorii.domain.enums import SourceModality
from test_semantic_generation_transactions import _setup, _terminal_for_operation
from test_source_group_plan_contracts import _plan
from tests.fixtures.semantic_ingestion.semantic_terminal_fixture import accepted_terminal


@dataclass(frozen=True)
class _Control:
    generation: int


class _AtomicPlanStore:
    def __init__(self, members: dict[int, tuple[AtomicGenerationMember, ...]]) -> None:
        self._members = members

    def get_operation(self, _fence: object) -> _Control:
        return _Control(generation=max(self._members))

    def generation_members(
        self, _fence: object, generation: int
    ) -> tuple[AtomicGenerationMember, ...]:
        return self._members[generation]


def test_repository_reads_only_the_exact_atomic_plan_member() -> None:
    plan = _plan()
    member = AtomicStoreTransactionSemanticGroupPlanRepository.checkpoint_member(plan)
    legacy_payload = encode_typed_value({"kind": "semantic_terminal_committed"})
    repository = AtomicStoreTransactionSemanticGroupPlanRepository(
        atomic_store=_AtomicPlanStore(
            {
                2: (
                    AtomicGenerationMember(
                        member_id="legacy-terminal-marker",
                        kind="plan",
                        canonical_payload=legacy_payload,
                        payload_digest=sha256(legacy_payload).hexdigest(),
                    ),
                ),
                3: (member,),
            }
        ),
        operation_fence=object(),
    )
    reference = repository.reference_for(plan)

    assert reference.repository_contract_fingerprint == (
        TRANSACTION_SEMANTIC_GROUP_PLAN_REPOSITORY_CONTRACT_FINGERPRINT
    )
    assert repository.get(reference) == plan
    assert decode_semantic_contract(
        member.canonical_payload, TransactionSemanticGroupPlan
    ) == plan


def test_repository_rejects_wrong_repository_or_ambiguous_plan_id() -> None:
    plan = _plan()
    member = AtomicStoreTransactionSemanticGroupPlanRepository.checkpoint_member(plan)
    repository = AtomicStoreTransactionSemanticGroupPlanRepository(
        atomic_store=_AtomicPlanStore({2: (member,), 3: (member,)}),
        operation_fence=object(),
    )
    reference = repository.reference_for(plan)

    with pytest.raises(ValueError, match="absent or ambiguous"):
        repository.get(reference)
    with pytest.raises(ValueError, match="another repository"):
        repository.get(reference.model_copy(update={"repository_id": "foreign"}))


def test_repository_loads_the_plan_published_with_the_planned_checkpoint() -> None:
    _, store, binding, control = _setup()
    plan = _plan_for_source(control.operation_fence.source_id)
    terminal = _terminal_for_operation(control.operation_fence)
    checkpoint = SourceCheckpointAtomicWriteRequest(
        operation_fence_binding=control.operation_fence,
        operation_lease_binding=store.lease_binding(control),
        writer_commit_binding=binding,
        expected_operation_generation=control.generation,
        expected_artifact_generation=control.generation,
        members=SemanticTerminalPersistenceService._checkpoint_members(
            terminal,
            SemanticArtifactClosure.create(terminal),
            binding,
            transaction_group_plan=plan,
        ),
        required_artifact_digests=(),
        request_digest="0" * 64,
        progress_state="planned",
    )
    checkpoint = checkpoint.model_copy(
        update={"request_digest": generation_request_digest(checkpoint)}
    )
    store.checkpoint_source_progress(checkpoint)

    repository = AtomicStoreTransactionSemanticGroupPlanRepository(
        atomic_store=store,
        operation_fence=control.operation_fence,
    )
    assert repository.get(repository.reference_for(plan)) == plan


def test_checkpoint_member_uses_the_typed_plan_payload_when_supplied() -> None:
    plan = _plan()
    terminal = accepted_terminal(operation_id="plan-member-operation")
    members = SemanticTerminalPersistenceService._checkpoint_members(
        terminal=terminal,
        closure=SemanticArtifactClosure.create(terminal),
        writer=type("Writer", (), {"admission_digest": "0" * 64})(),
        transaction_group_plan=plan,
    )
    plan_members = tuple(member for member in members if member.kind == "plan")

    assert len(plan_members) == 1
    assert decode_semantic_contract(
        plan_members[0].canonical_payload, TransactionSemanticGroupPlan
    ) == plan


def _plan_for_source(source_id: str) -> TransactionSemanticGroupPlan:
    def digest(value: str) -> str:
        return sha256(value.encode()).hexdigest()

    binding = SegmentGovernanceBinding.create(
        source_id=source_id,
        segment_id="segment-1",
        message_semantic_context_digest=digest("context"),
        effective_scope_digest=digest("scope"),
        authority_digest=digest("authority"),
        data_classification="internal",
        modality=SourceModality.ASSERTION,
        provider_egress_decision_digest=digest("egress"),
        egress_disposition="allow_verbatim",
    )
    governance = SegmentGovernanceCarrierSet.create(source_id=source_id, bindings=(binding,))
    admission = MessageAdmissionIdentity.create(
        delivery_principal_binding_digest=digest("principal"),
        authenticated_source_reference="source-ref-1",
        authenticated_source_reference_key_digest=digest("source-ref"),
        message_bytes_digest=digest("message"),
        segment_governance_binding_digest=binding.binding_digest,
    )
    admissions = MessageAdmissionCarrierSet.create(source_id=source_id, identities=(admission,))
    artifact = GovernanceCarrierArtifact.create(
        artifact_id="artifact-1",
        atomic_generation=1,
        segment_governance=governance,
        message_admissions=admissions,
        required_outcome_scopes=RequiredOutcomeScopeSet.create(
            tenant_partition_id="tenant-1", scopes=(MemoryScope(user_id="user-1"),)
        ),
    )
    source_group = SourceDependencyGroup.create(
        operation_ids=("operation-1",),
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
        segment_governance_bindings=governance.bindings,
        message_admission_identities=admissions.identities,
        operation_carrier_memberships=(
            OperationCarrierMembership(
                operation_id="operation-1",
                segment_governance_binding_digests=(binding.binding_digest,),
                message_admission_key_digests=(admission.message_admission_key_digest,),
            ),
        ),
        governance_carrier_artifact=artifact,
        member_decisions=(("operation-1", "accepted"),),
        graph_dependency_record_keys=(),
        dependency_kinds=(),
        atomic=True,
        status="commit_eligible",
    )
    planning_artifact = PlanningArtifactReference(
        artifact_id="planning-artifact-1",
        artifact_digest=digest("planning-artifact"),
        repository_id="repository-1",
        repository_contract_fingerprint=digest("repository-contract"),
    )
    execution = PlannedTransactionGroupExecution.create(
        transaction_group_id=group.transaction_group_id,
        planning_snapshot_digest=digest("snapshot"),
        prefix_state_digest_before=digest("before"),
        planning_artifact=planning_artifact,
        semantic_effect_digest=digest("effect"),
        prefix_state_digest_after=digest("after"),
        dependency_closure_digest=digest("closure"),
    )
    certificate = GroupIndependenceCertificate.create(
        transaction_group_id=group.transaction_group_id,
        preceding_group_ids=(),
        preceding_execution_digests=(),
        baseline_artifact=planning_artifact,
        after_prefix_artifact=planning_artifact,
        prefix_state_digest=digest("prefix"),
    )
    return TransactionSemanticGroupPlan.create(
        plan_id="plan-for-atomic-store",
        source_id=source_id,
        snapshot_token="snapshot-token-1",
        segment_governance_carriers=governance,
        message_admission_carriers=admissions,
        governance_carrier_artifact=artifact,
        groups=(group,),
        planned_executions=(execution,),
        independence_certificates=(certificate,),
        effective_read_set=GraphReadSet.create(
            record_keys=(), partition_versions=(), manifest_fingerprints=()
        ),
    )
