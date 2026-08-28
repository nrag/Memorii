"""Dedicated construction home for sealed bootstrap graph terminal fixtures.

The terminal publication request must be assembled from the real coordinator,
attempt, plan, lineage, graph-effect, and event-batch producers.  This module
is intentionally reserved for that strict closure rather than using
``model_construct`` or an untyped test double.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Literal

from memorii.core.memory_evolution.atomic_store import PreplanningStoreError
from memorii.core.memory_evolution.graph_effect_contracts import (
    CanonicalSourceTerminalOutcomeCore,
    CanonicalSourceTerminalOutcomeRecord,
    IngestionObservationDelta,
    IngestionObservationRecordMutation,
)
from memorii.core.memory_evolution.graph_planning import (
    AbsentPlanningPrecondition,
    GraphPlanningState,
    canonical_planning_payload_from_record,
)
from memorii.core.memory_evolution.graph_records import (
    GraphReadSet,
    GraphRecordKind,
    GraphStateSnapshot,
    ProvenanceRecord,
    canonical_graph_codec_manifest,
    graph_digest,
)
from memorii.core.memory_evolution.transaction_coordinator import GraphReadSetToken
from memorii.core.semantic_ingestion.bootstrap_graph_host import (
    BootstrapGraphAuthorityRequestV3,
    BootstrapGraphExecutionV3,
)
from memorii.core.semantic_ingestion.contracts import (
    CANONICAL_INGESTION_EXECUTION_GRAPH,
    BootstrapGraphAttemptConstructionInputsV3,
    BootstrapGraphControlEpochTransitionRequestV3,
    BootstrapGraphDependentCoordinatorRequestV3,
    BootstrapGraphEffectNotApplicableV3,
    BootstrapGraphExecutionManifestGroupInputV3,
    BootstrapGraphGroupCasOutcomeV3,
    BootstrapGraphGroupEffectReceiptV3,
    BootstrapGraphGroupExecutionResultV3,
    BootstrapGraphNormalizationAuthorityMemberV3,
    BootstrapGraphObservationDeltaEffectV3,
    BootstrapGraphOperationReductionV3,
    BootstrapGraphPlanAuthorizationSetV3,
    BootstrapGraphPlanCompilationV3,
    BootstrapGraphPreExecutionGroupEvidenceV3,
    BootstrapGraphSnapshotAuthorityV3,
    BootstrapGraphTerminalHostAuthorityV3,
    BootstrapGraphV3ProducerUnavailable,
    BootstrapGroupPlanningAuthorizationV3,
    BootstrapNativeFactEffectV3,
    BootstrapNativeOperationArtifactClosureV3,
    BootstrapNativeOperationCompilationV3,
    BootstrapNativeOperationEffectMaterializationV3,
    BootstrapNativeOperationReductionInputV3,
    BootstrapNativeOperationTerminalV3,
    BootstrapNativePlanningRecordV3,
    BootstrapNativeRecordMaterializationIntentV3,
    BootstrapNoReservationUseV3,
    BootstrapNormalizationRequestCoreV3,
    BootstrapRecoveryReplayRecordV3,
    BootstrapSemanticReductionAuthorityMemberV3,
    BootstrapSemanticReductionAuthorityReloadV3,
    BootstrapSourceProposalAlignmentV3,
    BootstrapTransactionGroupOperationPlanV3,
    BootstrapTransactionGroupPlanMemberV3,
    BootstrapTransactionGroupPlanV3,
    GraphDependentExecutionPolicyReferenceV3,
    GraphSemanticSnapshotBundleV3,
    PreparedSource,
    contract_digest,
    decode_bootstrap_graph_atomic_member_payload_v3,
    decode_semantic_contract,
)
from memorii.core.semantic_ingestion.source_normalization_authority import (
    CapabilityRegistrySnapshot,
)
from memorii.core.semantic_ingestion.source_normalization_stage import _native_reduction_inputs


def digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def build_empty_graph_snapshot_bundle() -> GraphSemanticSnapshotBundleV3:
    """Smallest canonical graph authority; all values use public contracts."""
    read_set = GraphReadSet.create(
        record_keys=(), partition_versions=(), manifest_fingerprints=(),
    )
    snapshot_values = {
        "snapshot_token": "bootstrap-graph-v3-fixture",
        "graph_revision": "genesis",
        "system_as_of": datetime(2026, 1, 1, tzinfo=UTC),
        "records": (),
        "exact_record_counts_by_kind": tuple(
            (kind, 0) for kind in sorted(GraphRecordKind.__args__)
        ),
        "codec_manifest_fingerprint": canonical_graph_codec_manifest().manifest_fingerprint,
        "governance_policy_fingerprints": (),
        "read_set": read_set,
    }
    snapshot = GraphStateSnapshot(
        **snapshot_values,
        snapshot_digest=graph_digest(
            b"memorii.graph-state-snapshot.v1\0", snapshot_values,
        ),
    )
    return GraphSemanticSnapshotBundleV3.create(
        graph_snapshot=snapshot, base_read_set=read_set,
    )


def build_graph_policy_reference() -> GraphDependentExecutionPolicyReferenceV3:
    policy_digest = digest("bootstrap-graph-v3-policy")
    return GraphDependentExecutionPolicyReferenceV3.create(
        repository_id="tests.bootstrap-graph-v3",
        repository_contract_fingerprint=digest("repository-contract"),
        policy_digest=policy_digest, artifact_digest=digest("policy-artifact"),
    )


def build_empty_capability_registry() -> CapabilityRegistrySnapshot:
    values = {"registry_revision": "bootstrap-graph-v3", "capabilities": ()}
    return CapabilityRegistrySnapshot(
        **values,
        snapshot_digest=contract_digest(
            b"memorii.semantic-ingestion.capability-registry-snapshot.v2", values,
        ),
    )


@dataclass(frozen=True)
class _FixturePlanCompilationV3:
    """Expose the native compilation through the coordinator's legacy-shaped seam.

    The production coordinator still consumes ``plan`` and per-group execution
    inputs while the sealed V3 compilation persists ``transaction_group_plan``
    and operation reductions.  This fixture-only adapter derives the former
    deterministically from the latter; it never accepts the retired wire form.
    """

    native: BootstrapGraphPlanCompilationV3

    @property
    def plan(self) -> BootstrapTransactionGroupPlanV3:
        return self.native.transaction_group_plan

    @property
    def manifest_group_inputs(self) -> tuple[BootstrapGraphExecutionManifestGroupInputV3, ...]:
        reductions_by_group: dict[str, list[BootstrapGraphOperationReductionV3]] = {}
        for reduction in self.native.operation_reductions:
            reductions_by_group.setdefault(reduction.transaction_group_id, []).append(reduction)
        values = []
        for member in self.plan.group_members:
            reductions = tuple(sorted(
                reductions_by_group[member.transaction_group_id],
                key=lambda item: item.operation_id,
            ))
            if tuple(item.operation_id for item in reductions) != member.operation_ids:
                raise ValueError("bootstrap graph fixture reduction/group closure is invalid")
            values.append(BootstrapGraphExecutionManifestGroupInputV3.create(
                transaction_group_id=member.transaction_group_id,
                group_plan_member=member,
                compilation_request_digest=self.native.request_digest,
                compilation_artifact_digest=contract_digest(
                    b"memorii.tests.bootstrap-graph-v3.compilation-artifact",
                    tuple(item.native_compilation.compilation_digest for item in reductions),
                ),
                independence_certificate_digest=contract_digest(
                    b"memorii.tests.bootstrap-graph-v3.independence-certificate",
                    tuple(item.native_artifact_closure.closure_digest for item in reductions),
                ),
                ordered_operation_ids=member.operation_ids,
                proposed_delta_digest=contract_digest(
                    b"memorii.tests.bootstrap-graph-v3.proposed-delta",
                    tuple(item.effect_materialization.materialization_digest for item in reductions),
                ),
                event_batch_digest=contract_digest(
                    b"memorii.tests.bootstrap-graph-v3.event-batch",
                    tuple(item.native_terminal.terminal_digest for item in reductions),
                ),
            ))
        return tuple(values)

    def __getattr__(self, name: str) -> object:
        return getattr(self.native, name)


def build_minimal_bootstrap_graph_plan_compilation_v3(
    *,
    request: BootstrapGraphDependentCoordinatorRequestV3,
    snapshot: GraphSemanticSnapshotBundleV3,
    policy: GraphDependentExecutionPolicyReferenceV3,
    capability_registry: CapabilityRegistrySnapshot,
    operation_inputs: tuple[BootstrapNativeOperationReductionInputV3, ...],
    control_epoch: object | None = None,
    accepted_materialization: bool = False,
) -> _FixturePlanCompilationV3:
    """Build the smallest one-group retained V40 plan closure from V3 inputs."""
    authority = request.graph_authority
    if (
        authority.snapshot != snapshot
        or authority.execution_policy != policy
        or authority.capability_registry_snapshot != capability_registry
    ):
        raise ValueError("bootstrap graph plan fixture authority is substituted")
    if not request.source_dependency_groups:
        raise ValueError("bootstrap graph plan fixture requires a complete dependency group")
    groups = request.source_dependency_groups
    epoch = control_epoch or request.initial_control_epoch
    required_operation_ids = tuple(
        sorted(
            operation_id
            for group in groups
            for operation_id in group.operation_ids
        )
    )
    relevant_operations = tuple(
        sorted(
            (
                item
                for item in operation_inputs
                if item.operation_id in set(required_operation_ids)
            ),
            key=lambda item: item.operation_id,
        )
    )
    by_operation = {item.operation_id: item for item in relevant_operations}
    if tuple(by_operation) != required_operation_ids:
        raise ValueError("bootstrap graph fixture retained reduction authority is incomplete")
    planning_state = GraphPlanningState.create(
        base_snapshot_digest=snapshot.snapshot_digest,
        records=(),
        codec_manifest_fingerprint=canonical_graph_codec_manifest().manifest_fingerprint,
        applied_planned_delta_digests=(),
    )
    graph_read_set = GraphReadSetToken.create(
        graph_revision=snapshot.graph_snapshot.graph_revision,
        replay_state_digest=digest("fixture-empty-replay-state"),
        reference_ledger_digest=digest("fixture-empty-reference-ledger"),
    )
    reductions: list[BootstrapGraphOperationReductionV3] = []
    members = []
    for group in groups:
        operation_plans = []
        for operation_id in group.operation_ids:
            operation = by_operation[operation_id]
            operation_plans.append(BootstrapTransactionGroupOperationPlanV3.create(
                operation_id=operation.operation_id,
                operation_execution_id=operation.operation_execution_id,
                proposal_digest=operation.normalized_proposal.proposal_digest,
                member_digests=(operation.operation_subject.member_digest,),
                segment_ids=(operation.operation_subject.segment_id,),
                dependency_group_ids=(group.group_id,),
                planning_result=None,
            ))
            planning_records = ()
            accepted_effect = None
            record_intents = ()
            terminal_status = "unresolved"
            reason_codes = ("graph_target_missing",)
            if accepted_materialization:
                if operation.operation_member.kind != "fact":
                    raise ValueError("accepted fixture supports only native facts")
                codec = next(
                    item
                    for item in canonical_graph_codec_manifest().entries
                    if item.record_kind == "provenance"
                )
                provenance_body = {
                    "operation_id": operation.operation_id,
                    "record_version": 1,
                    "codec_fingerprint": codec.codec_fingerprint,
                    "record_kind": "provenance",
                    "provenance_id": f"provenance:{operation.operation_id}",
                    "source_id": operation.source_id,
                    "entity_revision_id": None,
                    "logical_entity_id": None,
                }
                provenance = ProvenanceRecord(
                    **provenance_body,
                    record_digest=graph_digest(
                        b"memorii.canonical-graph-record.v1\0", provenance_body
                    ),
                )
                planning_payload = canonical_planning_payload_from_record(
                    provenance, transaction_group_id=group.group_id,
                )
                planning_record = BootstrapNativePlanningRecordV3.create(
                    operation_execution_id=operation.operation_execution_id,
                    record_kind="provenance",
                    record_id=provenance.provenance_id,
                    precondition=AbsentPlanningPrecondition(),
                    planning_payload=planning_payload,
                    source_member_digest=operation.operation_subject.member_digest,
                )
                planning_records = (planning_record,)
                accepted_effect = BootstrapNativeFactEffectV3.create(
                    kind="fact", fact=operation.operation_member,
                    target_bindings=(), planning_records=planning_records,
                    terminal_bindings=(), evidence_projections=(),
                )
                record_intents = (
                    BootstrapNativeRecordMaterializationIntentV3.create(
                        operation_execution_id=operation.operation_execution_id,
                        record_kind="provenance", record_id=provenance.provenance_id,
                        mutation_kind="create", expected_prior_record_digest=None,
                        canonical_after_record=planning_payload,
                        source_member_digest=operation.operation_subject.member_digest,
                    ),
                )
                terminal_status = "accepted"
                reason_codes = ()
            native_compilation = BootstrapNativeOperationCompilationV3.create(
                transaction_group_id=group.group_id,
                operation_input=operation,
                operation_id=operation.operation_id,
                operation_execution_id=operation.operation_execution_id,
                operation_member=operation.operation_member,
                resolved_graph_targets=(),
                sealed_operations=(),
                accepted_carriers=(),
                terminal_binding_sets=(),
                terminal_status=terminal_status,
                reason_codes=reason_codes,
            )
            materialization = BootstrapNativeOperationEffectMaterializationV3.create(
                operation_execution_id=operation.operation_execution_id,
                operation_id=operation.operation_id,
                terminal_status=terminal_status,
                accepted_effect=accepted_effect,
                record_intents=record_intents,
                observation_disposition=(
                    "committed" if accepted_materialization else "unresolved"
                ),
                observation_reason_codes=reason_codes,
            )
            terminal = BootstrapNativeOperationTerminalV3.create(
                operation_execution_id=operation.operation_execution_id,
                operation_id=operation.operation_id,
                proposal_digest=operation.normalized_proposal.proposal_digest,
                operation_kind=operation.operation_member.kind,
                sealed_snapshot_digest=snapshot.snapshot_digest,
                effective_read_set_digest=snapshot.base_read_set.read_set_digest,
                native_compilation_digest=native_compilation.compilation_digest,
                status=terminal_status,
                reason_codes=reason_codes,
                coverage_binding_digests=tuple(
                    item.binding_digest for item in operation.coverage_bindings
                ),
                accepted_effect_digest=(
                    None if accepted_effect is None else accepted_effect.effect_digest
                ),
                record_intent_digests=tuple(
                    item.intent_digest for item in record_intents
                ),
            )
            closure = BootstrapNativeOperationArtifactClosureV3.create(
                operation_execution_id=operation.operation_execution_id,
                operation_id=operation.operation_id,
                terminal_digest=terminal.terminal_digest,
                native_compilation_digest=native_compilation.compilation_digest,
                accepted_effect_digest=terminal.accepted_effect_digest,
                record_intent_digests=terminal.record_intent_digests,
                coverage_binding_digests=terminal.coverage_binding_digests,
                graph_target_digests=(),
                planning_result_digest=None,
            )
            reductions.append(BootstrapGraphOperationReductionV3.create(
                transaction_group_id=group.group_id,
                operation_id=operation.operation_id,
                proposal_digest=operation.normalized_proposal.proposal_digest,
                operation_execution_id=operation.operation_execution_id,
                sealed_snapshot_digest=snapshot.snapshot_digest,
                effective_read_set_digest=snapshot.base_read_set.read_set_digest,
                native_compilation=native_compilation,
                native_terminal=terminal,
                native_artifact_closure=closure,
                effect_materialization=materialization,
            ))
        members.append(BootstrapTransactionGroupPlanMemberV3.create(
            transaction_group_id=group.group_id,
            source_dependency_group_digest=group.group_id,
            sealed_graph_snapshot_digest=snapshot.snapshot_digest,
            graph_read_set=graph_read_set,
            reference_integrity_ledger_digest=graph_read_set.reference_ledger_digest,
            planning_state_before=planning_state,
            operation_plans=tuple(operation_plans),
            planning_state_after=planning_state,
            required_reservation_digests=(),
        ))
    members = tuple(members)
    evidence = tuple(
        BootstrapGraphPreExecutionGroupEvidenceV3.create(
            request_digest=request.request_digest,
            normalization_replay_digest=request.normalization_replay.replay_digest,
            transaction_group_id=group.group_id,
            group_plan_member_digest=member.member_digest,
            graph_snapshot_digest=snapshot.snapshot_digest,
            sealed_read_set_digest=snapshot.base_read_set.read_set_digest,
            reconciliation_digest=digest("reconciliation"),
            reference_closure_digest=digest("reference"),
            graph_validation_attempts=(),
            causal_blockers=(),
            terminal_before_planning_proof_digests=(),
            control_epoch_digest=epoch.epoch_digest,
        )
        for group, member in zip(groups, members, strict=True)
    )
    inputs = BootstrapGraphAttemptConstructionInputsV3.create(
        request_digest=request.request_digest, normalization_replay_digest=request.normalization_replay.replay_digest,
        normalization_result_digest=request.normalization_replay.source_normalization_result.result_digest,
        source_alignment_digest=request.source_alignment.alignment_digest, graph_snapshot_digest=snapshot.snapshot_digest,
        sealed_read_set_digest=snapshot.base_read_set.read_set_digest, reconciliation_digest=digest("reconciliation"),
        reference_closure_digest=digest("reference"), execution_policy_reference_digest=policy.artifact_digest,
        control_epoch_digest=epoch.epoch_digest,
        ordered_pre_execution_evidence_digests=tuple(
            item.evidence_digest for item in evidence
        ),
    )
    plan = BootstrapTransactionGroupPlanV3.create(
        request_digest=request.request_digest, normalization_replay_digest=request.normalization_replay.replay_digest,
        source_alignment_digest=request.source_alignment.alignment_digest, graph_snapshot_digest=snapshot.snapshot_digest,
        sealed_read_set_digest=snapshot.base_read_set.read_set_digest,
        fixed_point_rounds=1,
        group_members=members,
        canonical_group_order=tuple(item.transaction_group_id for item in members),
        execution_policy_reference_digest=policy.artifact_digest,
        operation_lease_binding_digest=epoch.operation_lease_binding.binding_digest,
        operation_fence_binding_digest=epoch.operation_fence_binding.binding_digest,
        writer_commit_binding_digest=epoch.writer_commit_binding.binding_digest, control_epoch_digest=epoch.epoch_digest,
    )
    return _FixturePlanCompilationV3(native=BootstrapGraphPlanCompilationV3.create(
        request_digest=request.request_digest,
        normalization_replay_digest=request.normalization_replay.replay_digest,
        control_epoch_digest=epoch.epoch_digest,
        transaction_group_plan=plan,
        operation_reductions=tuple(reductions),
        attempt_construction_inputs=inputs,
        pre_execution_evidence=evidence,
    ))


@dataclass(frozen=True)
class DeterministicBootstrapGraphPlanCompilerV3:
    """Strict one-group compiler used only by the coordinator integration fixture."""

    snapshot: GraphSemanticSnapshotBundleV3
    policy: GraphDependentExecutionPolicyReferenceV3
    capability_registry: CapabilityRegistrySnapshot
    operation_inputs: tuple[BootstrapNativeOperationReductionInputV3, ...]
    accepted_materialization: bool = False

    def compile(
        self,
        *,
        request: BootstrapGraphDependentCoordinatorRequestV3,
        control_epoch: object,
    ) -> _FixturePlanCompilationV3:
        if (
            control_epoch.request_core_digest != request.request_core_digest
            or control_epoch.operation_fence_binding
            != request.initial_control_epoch.operation_fence_binding
        ):
            raise ValueError("bootstrap graph fixture compiler epoch is substituted")
        return build_minimal_bootstrap_graph_plan_compilation_v3(
            request=request,
            snapshot=self.snapshot,
            policy=self.policy,
            capability_registry=self.capability_registry,
            operation_inputs=self.operation_inputs,
            control_epoch=control_epoch,
            accepted_materialization=self.accepted_materialization,
        )


@dataclass(frozen=True)
class DeterministicBootstrapGraphPlanningAuthorizerV3:
    """Issues the exact plan-member authorization bijection for one fixture group."""

    compilation: _FixturePlanCompilationV3

    def authorize(
        self,
        *,
        request: BootstrapGraphDependentCoordinatorRequestV3,
        control_epoch: object,
        reloaded_plan: object,
    ) -> BootstrapGraphPlanAuthorizationSetV3:
        reload_core = reloaded_plan.core
        plan_member = next(
            item for item in reload_core.members
            if item.kind == "bootstrap_transaction_group_plan"
        )
        inputs_member = next(
            item for item in reload_core.members
            if item.kind == "bootstrap_graph_snapshot_authority"
        )
        plan_payload = decode_bootstrap_graph_atomic_member_payload_v3(
            kind=plan_member.kind,
            raw=plan_member.canonical_payload,
        )
        inputs_payload = decode_bootstrap_graph_atomic_member_payload_v3(
            kind=inputs_member.kind,
            raw=inputs_member.canonical_payload,
        )
        plan = BootstrapTransactionGroupPlanV3.model_validate(plan_payload)
        inputs = BootstrapGraphAttemptConstructionInputsV3.model_validate(inputs_payload)
        if (
            self.compilation.request_digest != request.request_digest
            or reload_core.control_epoch_digest != control_epoch.epoch_digest
            or reload_core.delivery_principal_binding_digest
            != request.delivery_principal_binding_digest
            or reload_core.required_scope_set_digest
            != request.required_outcome_scopes.required_scope_set_digest
        ):
            raise ValueError("bootstrap graph fixture authorization inputs are substituted")
        authorizations = tuple(
            BootstrapGroupPlanningAuthorizationV3.create(
                request_digest=request.request_digest,
                transaction_group_id=member.transaction_group_id,
                group_plan_member_digest=member.member_digest,
                operation_ids=member.operation_ids,
                operation_plan_digests=tuple(
                    item.operation_plan_digest for item in member.operation_plans
                ),
                admission_authority_digest=contract_digest(
                    b"memorii.tests.bootstrap-graph-v3.admission-authority",
                    {
                        "request_digest": request.request_digest,
                        "transaction_group_id": member.transaction_group_id,
                        "attempt_inputs_digest": inputs.inputs_digest,
                    },
                ),
                capability_binding_digests=(),
                reservation_use_authority=BootstrapNoReservationUseV3.create(
                    kind="none",
                    transaction_group_id=member.transaction_group_id,
                    planned_identity_reservation_digests=(),
                ),
                graph_read_set_digest=member.graph_read_set.read_set_digest,
                operation_lease_binding_digest=control_epoch.operation_lease_binding.binding_digest,
                operation_fence_binding_digest=control_epoch.operation_fence_binding.binding_digest,
                writer_commit_binding_digest=control_epoch.writer_commit_binding.binding_digest,
                control_epoch_digest=control_epoch.epoch_digest,
            )
            for member in plan.group_members
        )
        return BootstrapGraphPlanAuthorizationSetV3.create(
            request_digest=request.request_digest,
            plan_digest=plan.plan_digest,
            control_epoch_digest=control_epoch.epoch_digest,
            authorizations=authorizations,
        )


@dataclass(frozen=True)
class DeterministicBootstrapGraphUnavailableExecutorV3:
    """Strict executor failure used to prove the durable-retry checkpoint path."""

    reason: str = "storage_unavailable"
    calls: list[str] | None = None

    def execute_cas(
        self,
        *,
        request: object,
        control_epoch: object,
        delivery_principal_binding_digest: str,
        required_outcome_scopes: object,
    ) -> BootstrapGraphV3ProducerUnavailable:
        if (
            request.control_epoch_digest != control_epoch.epoch_digest
            or delivery_principal_binding_digest
            != control_epoch.delivery_principal_binding_digest
            or required_outcome_scopes.required_scope_set_digest
            != control_epoch.required_scope_set_digest
        ):
            raise ValueError("bootstrap graph fixture executor authority is substituted")
        if self.calls is not None:
            self.calls.append(request.transaction_group_id)
        return BootstrapGraphV3ProducerUnavailable.create(
            phase="group_execute",
            reason=self.reason,
            request_digest=request.request_digest,
            control_epoch_digest=control_epoch.epoch_digest,
        )


@dataclass(frozen=True)
class DeterministicBootstrapGraphSuccessfulExecutorV3:
    """Emit one closed evidence-only group result with all three effect proofs."""

    host_authority: BootstrapGraphTerminalHostAuthorityV3
    calls: list[str]
    disposition: Literal["noncommitting", "failed"] = "noncommitting"
    terminal_status: Literal["evidence_only", "failed"] = "evidence_only"
    final_status: Literal["evidence_only", "failed"] = "evidence_only"
    not_applicable_reason: Literal["noncommitting", "failed"] = "noncommitting"
    cas_attempts: list[str] | None = None
    before_compare_and_swap: Callable[[str], None] | None = None
    current_scope_digest: Callable[[], str] | None = None

    def execute_cas(self, *, request: object, control_epoch: object,
                    delivery_principal_binding_digest: str, required_outcome_scopes: object) -> BootstrapGraphGroupExecutionResultV3:
        if (request.control_epoch_digest != control_epoch.epoch_digest
                or delivery_principal_binding_digest
                != self.host_authority.delivery_principal_binding_digest
                or required_outcome_scopes != self.host_authority.required_outcome_scopes):
            raise ValueError("bootstrap graph successful executor authority is substituted")
        if self.cas_attempts is not None:
            self.cas_attempts.append(request.cas_digest)
        if self.before_compare_and_swap is not None:
            self.before_compare_and_swap(request.transaction_group_id)
        if (
            self.current_scope_digest is not None
            and self.current_scope_digest()
            != required_outcome_scopes.required_scope_set_digest
        ):
            return BootstrapGraphV3ProducerUnavailable.create(
                phase="group_execute",
                reason="scope_revoked",
                request_digest=request.request_digest,
                control_epoch_digest=control_epoch.epoch_digest,
            )
        core = CanonicalSourceTerminalOutcomeCore.create(
            ingestion_record_kind="source_terminal_outcome", source_id=self.host_authority.source_id,
            source_digest=self.host_authority.source_digest,
            delivery_principal_binding_digest=self.host_authority.delivery_principal_binding_digest,
            delivery_key_digest=self.host_authority.delivery_key_digest,
            segment_governance_carriers=self.host_authority.segment_governance_carriers,
            message_admission_carriers=self.host_authority.message_admission_carriers,
            governance_carrier_artifact=self.host_authority.governance_carrier_artifact,
            required_outcome_scopes=self.host_authority.required_outcome_scopes,
            operation_fence_id=self.host_authority.operation_fence_binding.operation_fence_id,
            operation_ids=(self.host_authority.operation_fence_binding.operation_id,),
            final_status=self.final_status, group_result_digests=(),
        )
        record = CanonicalSourceTerminalOutcomeRecord.create(
            core=core, preparation_fingerprint=self.host_authority.preparation_fingerprint
        )
        mutation = IngestionObservationRecordMutation.create(
            mutation_kind="create", ingestion_record_kind="source_terminal_outcome",
            record_id=record.outcome_id, record_version=1, record=record,
            record_digest=record.record_digest,
        )
        observation = IngestionObservationDelta.create(
            kind="terminal_group", observation_delta_id=f"observation:{request.transaction_group_id}",
            observation_revision_before="before", observation_revision_after="after",
            source_id=self.host_authority.source_id, source_digest=self.host_authority.source_digest,
            segment_governance_bindings=self.host_authority.segment_governance_carriers.bindings,
            message_admission_identities=self.host_authority.message_admission_carriers.identities,
            governance_carrier_artifact=self.host_authority.governance_carrier_artifact,
            operation_fence_id=self.host_authority.operation_fence_binding.operation_fence_id,
            transaction_group_id=request.transaction_group_id,
            operation_ids=(self.host_authority.operation_fence_binding.operation_id,),
            terminal_status=self.terminal_status, graph_revision_delta_digest=None,
            observation_schema_fingerprint=digest("observation-schema"), record_mutations=(mutation,),
        )
        coordinate = digest(f"coordinate:{request.cas_digest}")
        observation_carrier = BootstrapGraphObservationDeltaEffectV3.create(
            kind="observation_delta", transaction_group_id=request.transaction_group_id,
            commit_coordinate_digest=coordinate, payload=observation, payload_digest=observation.delta_digest,
        )
        graph_carrier = BootstrapGraphEffectNotApplicableV3.create(
            kind="not_applicable", effect_kind="graph_delta", transaction_group_id=request.transaction_group_id,
            commit_coordinate_digest=coordinate, reason=self.not_applicable_reason,
        )
        event_carrier = BootstrapGraphEffectNotApplicableV3.create(
            kind="not_applicable", effect_kind="event_batch", transaction_group_id=request.transaction_group_id,
            commit_coordinate_digest=coordinate, reason=self.not_applicable_reason,
        )
        carriers = tuple(sorted((observation_carrier, graph_carrier, event_carrier), key=lambda item: item.carrier_digest))
        outcome = BootstrapGraphGroupCasOutcomeV3.create(
            cas_request=request, transaction_group_id=request.transaction_group_id, disposition=self.disposition,
            terminal_observation_status=self.terminal_status, observed_graph_revision="graph-before",
            observed_event_revision="event-before", observed_observation_revision="observation-before",
            publication_graph_revision=None, publication_event_revision=None,
            publication_observation_revision="observation-after", effect_carriers=carriers,
        )
        receipts = tuple(BootstrapGraphGroupEffectReceiptV3.create(
            effect_kind=kind, effect_id=f"{kind}:{request.transaction_group_id}",
            effect_carrier_digest=next(item.carrier_digest for item in carriers if (kind == "observation_delta" and item.kind == kind) or (kind != "observation_delta" and item.kind == "not_applicable" and item.effect_kind == kind)),
            commit_coordinate_digest=coordinate, status="applied" if kind == "observation_delta" else "not_applicable",
        ) for kind in ("observation_delta", "graph_delta", "event_batch"))
        self.calls.append(request.cas_digest)
        return BootstrapGraphGroupExecutionResultV3.create(cas_request=request, cas_request_digest=request.cas_digest,
            control_epoch_digest=request.control_epoch_digest, transaction_group_id=request.transaction_group_id,
            attempt_digest=request.attempt_digest, cas_outcome=outcome, effect_carriers=carriers, effect_receipts=receipts)


@dataclass
class DeterministicBootstrapGraphConflictThenSuccessExecutorV3:
    """Emit one related conflict, then delegate the successor CAS."""

    delegate: DeterministicBootstrapGraphSuccessfulExecutorV3
    calls: list[str]

    def execute_cas(self, **kwargs: object):
        request = kwargs["request"]
        self.calls.append(request.cas_digest)
        if len(self.calls) == 1:
            return BootstrapGraphV3ProducerUnavailable.create(
                phase="group_execute",
                reason="read_conflict",
                request_digest=request.request_digest,
                control_epoch_digest=kwargs["control_epoch"].epoch_digest,
            )
        return self.delegate.execute_cas(**kwargs)


@dataclass
class DeterministicBootstrapGraphPartialConflictExecutorV3:
    """Commit the first group, conflict the second, then finish its replacement."""

    delegate: DeterministicBootstrapGraphSuccessfulExecutorV3
    calls: list[str]

    def execute_cas(self, **kwargs: object):
        request = kwargs["request"]
        self.calls.append(request.transaction_group_id)
        if len(self.calls) == 2:
            return BootstrapGraphV3ProducerUnavailable.create(
                phase="group_execute",
                reason="read_conflict",
                request_digest=request.request_digest,
                control_epoch_digest=kwargs["control_epoch"].epoch_digest,
            )
        return self.delegate.execute_cas(**kwargs)


def build_bootstrap_graph_terminal_host_authority_v3(
    *,
    source: PreparedSource,
    operation_fence_binding: object,
    capability_bindings: tuple[object, ...] = (),
) -> BootstrapGraphTerminalHostAuthorityV3:
    """Project host-owned prepared-source carriers into the terminal authority."""
    artifact = source.governance_carrier_artifact
    if (
        operation_fence_binding.source_id != source.source_id
        or operation_fence_binding.source_digest != source.source_digest
        or artifact.segment_governance != source.segment_governance_carriers
        or artifact.message_admissions != source.message_admission_carriers
    ):
        raise ValueError("bootstrap graph terminal host fixture inputs are substituted")
    return BootstrapGraphTerminalHostAuthorityV3.create(
        source_id=source.source_id,
        source_digest=source.source_digest,
        preparation_fingerprint=source.preparation_fingerprint,
        delivery_principal_binding_digest=(
            operation_fence_binding.delivery_principal_binding_digest
        ),
        delivery_key_digest=operation_fence_binding.delivery_key_digest,
        execution_graph_fingerprint=CANONICAL_INGESTION_EXECUTION_GRAPH.graph_fingerprint,
        segment_language_routes=source.segment_language_routes,
        segment_governance_carriers=source.segment_governance_carriers,
        message_admission_carriers=source.message_admission_carriers,
        governance_carrier_artifact=artifact,
        capability_bindings=capability_bindings,
        required_outcome_scopes=artifact.required_outcome_scopes,
        operation_fence_binding=operation_fence_binding,
    )


@dataclass(frozen=True)
class PersistedBootstrapGraphReplayFixture:
    """Exact replay and current authority supplied by the publication owner."""

    replay: BootstrapRecoveryReplayRecordV3
    delivery_principal_binding_digest: str
    required_outcome_scopes: object
    operation_fence_binding: object
    operation_lease_binding: object
    writer_commit_binding: object
    control_epoch: object


def build_persisted_bootstrap_graph_replay_fixture(
    *, recovery_repository: object, recovery_key_digest: str,
    delivery_principal_binding_digest: str, required_outcome_scopes: object,
    operation_fence_binding: object,
    operation_lease_binding: object, writer_commit_binding: object,
    control_epoch: object,
) -> PersistedBootstrapGraphReplayFixture:
    """Load only the exact persisted replay; authority is never ambiently found."""
    replay = recovery_repository.reload_bootstrap_recovery_replay_v3(
        recovery_key_digest=recovery_key_digest
    )
    if replay is None:
        raise ValueError("bootstrap graph fixture replay is absent or corrupt")
    return PersistedBootstrapGraphReplayFixture(
        replay=replay, delivery_principal_binding_digest=delivery_principal_binding_digest,
        required_outcome_scopes=required_outcome_scopes,
        operation_fence_binding=operation_fence_binding,
        operation_lease_binding=operation_lease_binding,
        writer_commit_binding=writer_commit_binding, control_epoch=control_epoch,
    )


def build_graph_epoch_transition_request(
    *, fixture: PersistedBootstrapGraphReplayFixture,
    graph_authority: BootstrapGraphSnapshotAuthorityV3,
    source_alignment: BootstrapSourceProposalAlignmentV3,
) -> BootstrapGraphControlEpochTransitionRequestV3:
    if (
        graph_authority.normalization_replay_digest != fixture.replay.replay_digest
        or graph_authority.operation_fence_binding != fixture.operation_fence_binding
        or graph_authority.operation_lease_binding != fixture.operation_lease_binding
        or graph_authority.writer_commit_binding != fixture.writer_commit_binding
        or graph_authority.required_scope_set_digest
        != fixture.required_outcome_scopes.required_scope_set_digest
        or fixture.delivery_principal_binding_digest
        != graph_authority.delivery_principal_binding_digest
    ):
        raise ValueError("bootstrap graph fixture authority is substituted")
    core = {
        "schema_version": 3,
        "normalization_replay": fixture.replay,
        "source_alignment": source_alignment,
        "source_dependency_groups": source_alignment.source_dependency_groups,
        "graph_authority": graph_authority,
        "delivery_principal_binding_digest": fixture.delivery_principal_binding_digest,
        "required_outcome_scopes": fixture.required_outcome_scopes,
    }
    request_core_digest = contract_digest(
        b"memorii.semantic-ingestion.bootstrap-graph-request-core.v3", core
    )
    return BootstrapGraphControlEpochTransitionRequestV3.create(
        request_core_digest=request_core_digest, expected_epoch_digest=None,
        transition="initial", normalization_replay=fixture.replay,
        graph_authority=graph_authority,
        delivery_principal_binding_digest=fixture.delivery_principal_binding_digest,
        required_outcome_scopes=fixture.required_outcome_scopes,
        operation_fence=fixture.operation_fence_binding,
        operation_lease=fixture.operation_lease_binding,
        writer_commit=fixture.writer_commit_binding,
    )


def build_graph_coordinator_request(
    *, fixture: PersistedBootstrapGraphReplayFixture,
    graph_authority: BootstrapGraphSnapshotAuthorityV3,
    source_alignment: BootstrapSourceProposalAlignmentV3,
    initial_control_epoch: object,
) -> BootstrapGraphDependentCoordinatorRequestV3:
    groups = source_alignment.source_dependency_groups
    core = {
        "schema_version": 3, "normalization_replay": fixture.replay,
        "source_alignment": source_alignment, "source_dependency_groups": groups,
        "delivery_principal_binding_digest": fixture.delivery_principal_binding_digest,
        "required_outcome_scopes": fixture.required_outcome_scopes,
        "graph_authority": graph_authority,
    }
    request_core_digest = contract_digest(
        b"memorii.semantic-ingestion.bootstrap-graph-request-core.v3", core
    )
    if (
        source_alignment != fixture.replay.source_normalization_request.source_alignment
        or graph_authority.normalization_replay_digest != fixture.replay.replay_digest
        or initial_control_epoch.request_core_digest != request_core_digest
    ):
        raise ValueError("bootstrap graph fixture coordinator inputs are substituted")
    return BootstrapGraphDependentCoordinatorRequestV3.create(
        normalization_replay=fixture.replay, source_alignment=source_alignment,
        source_dependency_groups=groups,
        delivery_principal_binding_digest=fixture.delivery_principal_binding_digest,
        required_outcome_scopes=fixture.required_outcome_scopes,
        graph_authority=graph_authority, request_core_digest=request_core_digest,
        initial_control_epoch=initial_control_epoch,
    )


def _reconstruct_bootstrap_semantic_reduction_reload_v3(
    *, atomic_store: object, request: BootstrapGraphAuthorityRequestV3,
) -> BootstrapSemanticReductionAuthorityReloadV3 | None:
    try:
        recovered = atomic_store.recover_bootstrap_v3_source_normalization(
            recovery_key_digest=request.normalization_replay.recovery_key_digest,
        )
        if recovered is None:
            raise ValueError("missing bootstrap v3 recovery record")
        generation, atomic_write_digest, _result_digest, members = recovered
        try:
            core_member = next(
                item for item in members
                if item.kind == "bootstrap_normalization_request_core"
            )
        except StopIteration as exc:
            raise ValueError("missing bootstrap normalization request core") from exc
        core = decode_semantic_contract(
            core_member.canonical_payload, BootstrapNormalizationRequestCoreV3,
        )
        for item in members:
            if item.kind != "bootstrap_semantic_reduction_authority":
                continue
            reduction_member = decode_semantic_contract(
                item.canonical_payload, BootstrapSemanticReductionAuthorityMemberV3,
            )
            if reduction_member.normalization_request_core != core:
                raise ValueError(
                    "bootstrap semantic reduction authority is for a different core"
                )
            return BootstrapSemanticReductionAuthorityReloadV3.create(
                normalization_replay=request.normalization_replay,
                normalization_atomic_write_digest=atomic_write_digest,
                normalization_operation_generation=generation,
                normalization_artifact_generation=generation,
                authority_member=reduction_member,
            )

        operation_inputs = _native_reduction_inputs(
            core=core, operation_fence_binding=request.operation_fence_binding,
        )
        graph_authority_member = next(
            (
                decode_semantic_contract(
                    member.canonical_payload,
                    BootstrapGraphNormalizationAuthorityMemberV3,
                )
                for member in members
                if member.kind == "bootstrap_graph_normalization_authority"
            ),
            None,
        )
        if graph_authority_member is None:
            raise ValueError("missing graph normalization authority")
        policy = (
            graph_authority_member.execution_policy
        )
        capability_registry = (
            graph_authority_member.capability_registry
        )
        authority = BootstrapSemanticReductionAuthorityMemberV3.create(
            normalization_request_core=core,
            normalization_request_core_canonical_bytes=core_member.canonical_payload,
            operation_inputs=operation_inputs,
            execution_policy=policy,
            execution_policy_canonical_bytes=graph_authority_member.execution_policy_canonical_bytes,
            capability_registry=capability_registry,
            capability_registry_canonical_bytes=graph_authority_member.capability_registry_canonical_bytes,
        )
        return BootstrapSemanticReductionAuthorityReloadV3.create(
            normalization_replay=request.normalization_replay,
            normalization_atomic_write_digest=atomic_write_digest,
            normalization_operation_generation=generation,
            normalization_artifact_generation=generation,
            authority_member=authority,
        )
    except (ValueError, TypeError, KeyError) as exc:
        raise RuntimeError(
            f"semantic reduction authority reconstruction failed: {exc}"
        ) from exc
    except Exception as exc:
        raise RuntimeError(
            f"semantic reduction authority reconstruction failed: {exc}"
        ) from exc
        return None


@dataclass
class DeterministicBootstrapGraphAuthorityProviderV3:
    """Strict test authority provider for the real shared provider root."""

    successful_calls: list[str]
    accepted_materialization: bool = False
    unavailable_calls: list[str] | None = None
    conflict_calls: list[str] | None = None
    partial_conflict_calls: list[str] | None = None
    exhausted_conflict_calls: list[str] | None = None
    cas_attempts: list[str] | None = None
    before_compare_and_swap: Callable[[str], None] | None = None
    current_scope_digest: Callable[[], str] | None = None
    before_epoch_created: Callable[[object], None] | None = None
    after_epoch_created: Callable[[object, object, object], object] | None = None
    acquire_errors: list[str] | None = None

    def acquire(
        self, *, request: BootstrapGraphAuthorityRequestV3, atomic_store: object,
    ) -> BootstrapGraphExecutionV3 | None:
        if self.acquire_errors is not None:
            self.acquire_errors.clear()
        from memorii.core.semantic_ingestion.bootstrap_graph_coordinator import (
            BootstrapGraphDependentCoordinatorV3,
        )
        from memorii.core.semantic_ingestion.bootstrap_graph_repository import (
            AtomicStoreBootstrapGraphControlEpochRepositoryV3,
            AtomicStoreBootstrapGraphGroupCommitRepositoryV3,
            AtomicStoreBootstrapGraphPlanRepositoryV3,
            AtomicStoreBootstrapGraphTerminalPersistencePortV3,
        )
        from memorii.core.semantic_ingestion.bootstrap_graph_terminal_preparation import (
            DeterministicBootstrapGraphTerminalPreparationV3,
        )
        from memorii.core.semantic_ingestion.contracts import (
            BootstrapGraphControlEpochAdvancedV3,
            BootstrapGraphControlEpochFoundV3,
            BootstrapGraphControlEpochUnavailableV3,
        )

        try:
            snapshot_record = atomic_store.graph_state_snapshot()
            fixture = PersistedBootstrapGraphReplayFixture(
                replay=request.normalization_replay,
                delivery_principal_binding_digest=request.operation_fence_binding.delivery_principal_binding_digest,
                required_outcome_scopes=request.required_outcome_scopes,
                operation_fence_binding=request.operation_fence_binding,
                operation_lease_binding=request.operation_lease_binding,
                writer_commit_binding=request.writer_commit_binding,
                control_epoch=request.operation_fence_binding.delivery_principal_binding_digest,
            )
            replay = request.normalization_replay
            normalization_authority = atomic_store.reload_bootstrap_graph_normalization_authority_v3(
                normalization_replay=replay
            )
            if normalization_authority is None:
                if self.acquire_errors is not None:
                    self.acquire_errors.append(
                        "missing bootstrap graph normalization authority"
                    )
                return None
            policy_member = normalization_authority.authority_member
            snapshot = GraphSemanticSnapshotBundleV3.create(
                graph_snapshot=snapshot_record,
                base_read_set=snapshot_record.read_set,
            )
            policy = GraphDependentExecutionPolicyReferenceV3.create(
                repository_id="memorii.bootstrap-graph-normalization-authority-v3",
                repository_contract_fingerprint=contract_digest(
                    b"memorii.bootstrap-graph.normalization-policy-repository.v3",
                    "BootstrapGraphNormalizationAuthorityMemberV3",
                ),
                policy_digest=policy_member.execution_policy.policy_digest,
                artifact_digest=contract_digest(
                    b"memorii.bootstrap-graph.normalization-policy-artifact.v3",
                    policy_member.execution_policy_canonical_bytes,
                ),
            )
            capabilities = policy_member.capability_registry
            reduction_reload = _reconstruct_bootstrap_semantic_reduction_reload_v3(
                atomic_store=atomic_store, request=request
            )
            if reduction_reload is None:
                if self.acquire_errors is not None:
                    self.acquire_errors.append(
                        "missing semantic reduction authority reload"
                    )
                return None
            operation_inputs = reduction_reload.authority_member.operation_inputs
            authority = BootstrapGraphSnapshotAuthorityV3.create(
                source_id=request.prepared_source.source_id,
                source_digest=request.prepared_source.source_digest,
                preparation_fingerprint=request.prepared_source.preparation_fingerprint,
                normalization_replay_digest=replay.replay_digest,
                normalization_result_digest=replay.source_normalization_result.result_digest,
                source_alignment_digest=replay.source_normalization_request.source_alignment.alignment_digest,
                snapshot=snapshot,
                base_read_set_digest=snapshot.base_read_set.read_set_digest,
                required_scope_set_digest=request.required_outcome_scopes.required_scope_set_digest,
                delivery_principal_binding_digest=(
                    request.operation_fence_binding.delivery_principal_binding_digest
                ),
                execution_policy=policy,
                capability_registry_snapshot=capabilities,
                operation_lease_binding=request.operation_lease_binding,
                operation_fence_binding=request.operation_fence_binding,
                writer_commit_binding=request.writer_commit_binding,
            )
            transition = build_graph_epoch_transition_request(
                fixture=fixture,
                graph_authority=authority,
                source_alignment=replay.source_normalization_request.source_alignment,
            )
            epoch_repository = AtomicStoreBootstrapGraphControlEpochRepositoryV3(
                atomic_store=atomic_store
            )
            if self.before_epoch_created is not None:
                self.before_epoch_created(atomic_store)
            transition_result = epoch_repository.transition_or_find(request=transition)
            if self.acquire_errors is not None and isinstance(
                transition_result, BootstrapGraphControlEpochUnavailableV3
            ):
                self.acquire_errors.append(
                    f"authority transition unavailable: {transition_result.reason}"
                )
            elif self.acquire_errors is not None and not isinstance(
                transition_result,
                (BootstrapGraphControlEpochFoundV3, BootstrapGraphControlEpochAdvancedV3),
            ):
                self.acquire_errors.append(
                    "authority transition returned unexpected: "
                    f"{type(transition_result).__name__}"
                )
                reason = getattr(transition_result, "reason", None)
                if reason is not None:
                    self.acquire_errors.append(
                        f"authority transition reason: {reason}"
                    )
                kind = getattr(transition_result, "kind", None)
                if kind is not None:
                    self.acquire_errors.append(f"authority transition kind: {kind}")
                try:
                    if hasattr(transition_result, "model_dump"):
                        self.acquire_errors.append(
                            f"authority transition payload: {transition_result.model_dump()}"
                        )
                except Exception as exc:
                    self.acquire_errors.append(
                        f"authority transition payload_dump_failed: {type(exc).__name__}"
                    )
            if not isinstance(
                transition_result, (BootstrapGraphControlEpochFoundV3, BootstrapGraphControlEpochAdvancedV3)
            ):
                return None
            epoch = transition_result.epoch
            coordinator_request = build_graph_coordinator_request(
                fixture=fixture,
                graph_authority=authority,
                source_alignment=replay.source_normalization_request.source_alignment,
                initial_control_epoch=epoch,
            )
            if self.after_epoch_created is not None:
                epoch = self.after_epoch_created(atomic_store, coordinator_request, epoch)
            materialized = self.accepted_materialization
            if callable(materialized):
                materialized = materialized(request.prepared_source)
            compilation = build_minimal_bootstrap_graph_plan_compilation_v3(
                request=coordinator_request,
                snapshot=snapshot,
                policy=policy,
                capability_registry=capabilities,
                operation_inputs=operation_inputs,
                accepted_materialization=materialized,
            )
            host_authority = build_bootstrap_graph_terminal_host_authority_v3(
                source=request.prepared_source,
                operation_fence_binding=request.operation_fence_binding,
            )
            group_commits = AtomicStoreBootstrapGraphGroupCommitRepositoryV3(
                atomic_store=atomic_store
            )
            if self.unavailable_calls is not None:
                class UnavailableGroupCommitRepository:
                    def commit_or_reload(inner_self, *, request):
                        if self.cas_attempts is not None:
                            self.cas_attempts.append(request.transaction_group_id)
                        self.unavailable_calls.append(request.transaction_group_id)
                        raise PreplanningStoreError("injected graph group commit unavailable")

                group_commits = UnavailableGroupCommitRepository()
            else:
                max_conflict_failures = (
                    2 if self.conflict_calls is not None
                    else 4 if self.partial_conflict_calls is not None
                    else 2 if self.exhausted_conflict_calls is not None
                    else 0
                )

                class RecordingGroupCommitRepository:
                    def __init__(self, repository: object):
                        self._repository = repository

                    @staticmethod
                    def _run_before_compare_and_swap(*, request) -> None:
                        if self.before_compare_and_swap is None:
                            return
                        self.before_compare_and_swap(request.transaction_group_id)

                    def commit_or_reload(inner_self, *, request):
                        type(inner_self)._run_before_compare_and_swap(
                            request=request
                        )
                        if self.cas_attempts is not None:
                            self.cas_attempts.append(request.transaction_group_id)
                        reload = inner_self._repository.commit_or_reload(request=request)
                        self.successful_calls.append(request.transaction_group_id)
                        return reload

                recording_group_commits = RecordingGroupCommitRepository(
                    repository=group_commits
                )

                class ConflictInjectingGroupCommitRepository:
                    failures = {"remaining": max_conflict_failures}

                    def _record_conflict(inner_self, *, request, conflict_calls: list[str]):
                        if self.cas_attempts is not None:
                            self.cas_attempts.append(request.transaction_group_id)
                        conflict_calls.append(request.transaction_group_id)
                        inner_self.failures["remaining"] -= 1
                        if inner_self.failures["remaining"] < 0:
                            inner_self.failures["remaining"] = 0

                    def commit_or_reload(inner_self, *, request):
                        if inner_self.failures["remaining"] > 0:
                            if self.conflict_calls is not None:
                                inner_self._record_conflict(
                                    request=request, conflict_calls=self.conflict_calls,
                                )
                                raise PreplanningStoreError(
                                    "injected graph group commit conflict"
                                )
                            if self.partial_conflict_calls is not None:
                                inner_self._record_conflict(
                                    request=request, conflict_calls=self.partial_conflict_calls,
                                )
                                raise PreplanningStoreError(
                                    "injected graph group commit partial conflict"
                                )
                            if self.exhausted_conflict_calls is not None:
                                inner_self._record_conflict(
                                    request=request,
                                    conflict_calls=self.exhausted_conflict_calls,
                                )
                                raise PreplanningStoreError(
                                    "injected graph group commit conflict"
                                )
                        if self.cas_attempts is not None:
                            self.cas_attempts.append(request.transaction_group_id)
                        self._run_before_compare_and_swap(request=request)
                        reload = recording_group_commits.commit_or_reload(request=request)
                        return reload

                if max_conflict_failures > 0:
                    group_commits = ConflictInjectingGroupCommitRepository()
                else:
                    group_commits = recording_group_commits

            coordinator = BootstrapGraphDependentCoordinatorV3(
                epoch_repository=epoch_repository,
                plan_repository=AtomicStoreBootstrapGraphPlanRepositoryV3(
                    atomic_store=atomic_store
                ),
                terminal_port=AtomicStoreBootstrapGraphTerminalPersistencePortV3(
                    atomic_store=atomic_store
                ),
                compiler=DeterministicBootstrapGraphPlanCompilerV3(
                    snapshot=snapshot, policy=policy, capability_registry=capabilities,
                    operation_inputs=operation_inputs,
                    accepted_materialization=materialized,
                ),
                authorizer=DeterministicBootstrapGraphPlanningAuthorizerV3(
                    compilation=compilation
                ),
                group_commit_repository=group_commits,
                terminal_preparer=DeterministicBootstrapGraphTerminalPreparationV3(),
                terminal_host_authority=host_authority,
            )
            return BootstrapGraphExecutionV3(
                coordinator=coordinator,
                request=coordinator_request,
                transition=transition,
            )
        except (ValueError, TypeError, AttributeError, RecursionError, RuntimeError) as exc:
            if self.acquire_errors is not None:
                self.acquire_errors.append(f"{type(exc).__name__}: {exc}")
            return None
        except Exception as exc:
            if self.acquire_errors is not None:
                self.acquire_errors.append(f"unexpected provider error: {type(exc).__name__}: {exc}")
            return None

__all__ = [
    "build_empty_capability_registry",
    "build_empty_graph_snapshot_bundle",
    "build_graph_policy_reference",
    "build_bootstrap_graph_terminal_host_authority_v3",
    "DeterministicBootstrapGraphPlanCompilerV3",
    "DeterministicBootstrapGraphPlanningAuthorizerV3",
    "DeterministicBootstrapGraphSuccessfulExecutorV3",
    "DeterministicBootstrapGraphConflictThenSuccessExecutorV3",
    "DeterministicBootstrapGraphPartialConflictExecutorV3",
    "DeterministicBootstrapGraphUnavailableExecutorV3",
    "DeterministicBootstrapGraphAuthorityProviderV3",
    "build_minimal_bootstrap_graph_plan_compilation_v3",
    "build_graph_epoch_transition_request",
    "build_graph_coordinator_request",
    "build_persisted_bootstrap_graph_replay_fixture",
    "digest",
    "PersistedBootstrapGraphReplayFixture",
]
