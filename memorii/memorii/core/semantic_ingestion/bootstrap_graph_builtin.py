"""Built-in local composition for the native V3 bootstrap graph transaction.

This is deliberately a small fail-closed compiler.  It consumes only the
persisted normalization/replay authority and the atomic store's own snapshot,
read-set and reference-ledger authority.  Until a target planner is installed,
ordinary proposals become durable unresolved graph results; it never invents a
graph target or an accepted effect.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from memorii.core.memory_evolution.bootstrap_graph_planning import (
    BootstrapCanonicalIdentityBindingAllocationProjectorV3,
    BootstrapNativeTargetResolutionProjectorV3,
    BuiltInBootstrapGraphTargetMaterializationPlannerV3,
)
from memorii.core.memory_evolution.graph_planning import GraphPlanningState
from memorii.core.memory_evolution.transaction_coordinator import GraphReadSetToken, SealedGraphStateSnapshot
from memorii.core.semantic_ingestion.bootstrap_graph_coordinator import BootstrapGraphDependentCoordinatorV3
from memorii.core.semantic_ingestion.bootstrap_graph_host import (
    BootstrapGraphAuthorityRequestV3,
    BootstrapGraphExecutionV3,
)
from memorii.core.semantic_ingestion.bootstrap_graph_repository import (
    AtomicStoreBootstrapCanonicalIdentityAuthorityRepositoryV3,
    AtomicStoreBootstrapGraphControlEpochRepositoryV3,
    AtomicStoreBootstrapGraphGroupCommitRepositoryV3,
    AtomicStoreBootstrapGraphPlanRepositoryV3,
    AtomicStoreBootstrapGraphTerminalPersistencePortV3,
    AtomicStoreBootstrapGraphTransactionAuthorityRepositoryV3,
)
from memorii.core.semantic_ingestion.bootstrap_graph_terminal_preparation import (
    DeterministicBootstrapGraphTerminalPreparationV3,
)
from memorii.core.semantic_ingestion.bootstrap_native_reducer import BootstrapNativeSemanticReducerV3
from memorii.core.semantic_ingestion.contracts import (
    CANONICAL_INGESTION_EXECUTION_GRAPH,
    BootstrapCanonicalIdentityAuthorityWriteRequestV3,
    BootstrapGraphAttemptConstructionInputsV3,
    BootstrapGraphControlEpochTransitionRequestV3,
    BootstrapGraphControlEpochUnavailableV3,
    BootstrapGraphDependentCoordinatorRequestV3,
    BootstrapGraphExecutionManifestGroupInputV3,
    BootstrapGraphOperationReductionV3,
    BootstrapGraphPlanAuthorizationSetV3,
    BootstrapGraphPlanCompilationV3,
    BootstrapGraphPreExecutionGroupEvidenceV3,
    BootstrapGraphPreparedSourceTerminalAuthorityV3,
    BootstrapGraphSnapshotAuthorityV3,
    BootstrapGraphTerminalHostAuthorityV3,
    BootstrapGraphTransactionAuthorityProjectionV3,
    BootstrapGraphTransactionAuthorityWriteRequestV3,
    BootstrapGroupPlanningAuthorizationV3,
    BootstrapNativeOperationArtifactClosureV3,
    BootstrapNativeOperationCompilationV3,
    BootstrapNativeOperationEffectMaterializationV3,
    BootstrapNativeOperationTerminalV3,
    BootstrapNativeTargetPlanningRequestV3,
    BootstrapNoReservationUseV3,
    BootstrapTransactionGroupOperationPlanV3,
    BootstrapTransactionGroupPlanMemberV3,
    BootstrapTransactionGroupPlanV3,
    GraphDependentExecutionPolicyReferenceV3,
    GraphSemanticSnapshotBundleV3,
    contract_digest,
    decode_bootstrap_graph_atomic_member_payload_v3,
)


def _digest(value: object) -> str:
    return sha256(repr(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class _BuiltInCompilation:
    native: BootstrapGraphPlanCompilationV3

    @property
    def plan(self) -> BootstrapTransactionGroupPlanV3:
        return self.native.transaction_group_plan

    @property
    def manifest_group_inputs(self) -> tuple[BootstrapGraphExecutionManifestGroupInputV3, ...]:
        reductions: dict[str, list[BootstrapGraphOperationReductionV3]] = {}
        for reduction in self.native.operation_reductions:
            reductions.setdefault(reduction.transaction_group_id, []).append(reduction)
        values = []
        for member in self.plan.group_members:
            group_reductions = tuple(sorted(reductions[member.transaction_group_id], key=lambda item: item.operation_id))
            values.append(BootstrapGraphExecutionManifestGroupInputV3.create(
                transaction_group_id=member.transaction_group_id,
                group_plan_member=member,
                compilation_request_digest=self.native.request_digest,
                compilation_artifact_digest=contract_digest(
                    b"memorii.bootstrap-graph.builtin.compilation-artifact.v3",
                    tuple(item.native_compilation.compilation_digest for item in group_reductions),
                ),
                independence_certificate_digest=contract_digest(
                    b"memorii.bootstrap-graph.builtin.independence-certificate.v3",
                    tuple(item.native_artifact_closure.closure_digest for item in group_reductions),
                ),
                ordered_operation_ids=member.operation_ids,
                proposed_delta_digest=contract_digest(
                    b"memorii.bootstrap-graph.builtin.proposed-delta.v3",
                    tuple(item.effect_materialization.materialization_digest for item in group_reductions),
                ),
                event_batch_digest=contract_digest(
                    b"memorii.bootstrap-graph.builtin.event-batch.v3",
                    tuple(item.native_terminal.terminal_digest for item in group_reductions),
                ),
            ))
        return tuple(values)

    def __getattr__(self, name: str) -> object:
        return getattr(self.native, name)


def _compile(
    *, request: object, epoch: object, operation_inputs: tuple[object, ...],
    sealed_snapshot: SealedGraphStateSnapshot, canonical_identity_authority: object | None,
) -> _BuiltInCompilation:
    snapshot = GraphSemanticSnapshotBundleV3.create(
        graph_snapshot=sealed_snapshot.canonical_graph,
        base_read_set=sealed_snapshot.canonical_graph.read_set,
    )
    policy = request.graph_authority.execution_policy
    groups = request.source_dependency_groups
    expected_ids = tuple(operation_id for group in groups for operation_id in group.operation_ids)
    if not groups:
        raise ValueError("retained bootstrap graph reduction authority is incomplete")
    relevant_operations = tuple(
        sorted(
            (
                item
                for item in operation_inputs
                if item.operation_id in set(expected_ids)
            ),
            key=lambda item: item.operation_id,
        )
    )
    required_ids = tuple(sorted(expected_ids))
    if tuple(item.operation_id for item in relevant_operations) != required_ids:
        raise ValueError("retained bootstrap graph reduction authority is incomplete")
    by_operation = {item.operation_id: item for item in relevant_operations}
    state = GraphPlanningState.create(
        base_snapshot_digest=sealed_snapshot.snapshot_digest, records=(),
        codec_manifest_fingerprint=snapshot.graph_snapshot.codec_manifest_fingerprint,
        applied_planned_delta_digests=(),
    )
    replay_state = _digest((request.normalization_replay.replay_digest, "replay"))
    reference_ledger = _digest((request.normalization_replay.replay_digest, "ledger"))
    # The token is a group-local proof; reductions and the atomic request retain
    # the canonical GraphReadSet digest from the store snapshot.
    read_token = GraphReadSetToken.create(
        graph_revision=snapshot.graph_snapshot.graph_revision,
        replay_state_digest=replay_state, reference_ledger_digest=reference_ledger,
    )
    reductions: list[BootstrapGraphOperationReductionV3] = []
    members = []
    for group in groups:
        plans = []
        for operation_id in group.operation_ids:
            operation = by_operation[operation_id]
            plans.append(BootstrapTransactionGroupOperationPlanV3.create(
                operation_id=operation.operation_id, operation_execution_id=operation.operation_execution_id,
                proposal_digest=operation.normalized_proposal.proposal_digest,
                member_digests=(operation.operation_subject.member_digest,),
                segment_ids=(operation.operation_subject.segment_id,),
                dependency_group_ids=(group.group_id,), planning_result=None,
            ))
            if canonical_identity_authority is None:
                compilation = BootstrapNativeOperationCompilationV3.create(
                    transaction_group_id=group.group_id, operation_input=operation,
                    operation_id=operation.operation_id,
                    operation_execution_id=operation.operation_execution_id,
                    operation_member=operation.operation_member,
                    resolved_graph_targets=(), sealed_operations=(),
                    accepted_carriers=(), terminal_binding_sets=(),
                    terminal_status="unresolved", reason_codes=("graph_target_missing",),
                )
                materialization = BootstrapNativeOperationEffectMaterializationV3.create(
                    operation_execution_id=operation.operation_execution_id,
                    operation_id=operation.operation_id, terminal_status="unresolved",
                    accepted_effect=None, record_intents=(),
                    observation_disposition="unresolved",
                    observation_reason_codes=("graph_target_missing",),
                )
                terminal = BootstrapNativeOperationTerminalV3.create(
                    operation_execution_id=operation.operation_execution_id,
                    operation_id=operation.operation_id,
                    proposal_digest=operation.normalized_proposal.proposal_digest,
                    operation_kind=operation.operation_member.kind,
                    sealed_snapshot_digest=sealed_snapshot.snapshot_digest,
                    effective_read_set_digest=snapshot.base_read_set.read_set_digest,
                    native_compilation_digest=compilation.compilation_digest,
                    status="unresolved", reason_codes=("graph_target_missing",),
                    coverage_binding_digests=tuple(item.binding_digest for item in operation.coverage_bindings),
                    accepted_effect_digest=None, record_intent_digests=(),
                )
                closure = BootstrapNativeOperationArtifactClosureV3.create(
                    operation_execution_id=operation.operation_execution_id,
                    operation_id=operation.operation_id, terminal_digest=terminal.terminal_digest,
                    native_compilation_digest=compilation.compilation_digest,
                    accepted_effect_digest=None, record_intent_digests=(),
                    coverage_binding_digests=terminal.coverage_binding_digests,
                    graph_target_digests=(), planning_result_digest=None,
                )
                reductions.append(BootstrapGraphOperationReductionV3.create(
                    transaction_group_id=group.group_id, operation_id=operation.operation_id,
                    proposal_digest=operation.normalized_proposal.proposal_digest,
                    operation_execution_id=operation.operation_execution_id,
                    sealed_snapshot_digest=sealed_snapshot.snapshot_digest,
                    effective_read_set_digest=snapshot.base_read_set.read_set_digest,
                    native_compilation=compilation, native_terminal=terminal,
                    native_artifact_closure=closure,
                    effect_materialization=materialization,
                ))
                continue
            target_authority = BootstrapNativeTargetResolutionProjectorV3().project(
                operation_input=operation, transaction_group_id=group.group_id,
                sealed_snapshot=sealed_snapshot, effective_read_set=snapshot.base_read_set,
                current_planning_state=state, canonical_identity_authority=canonical_identity_authority,
            )
            target_request = BootstrapNativeTargetPlanningRequestV3.create(
                transaction_group_id=group.group_id, operation_input=operation,
                sealed_snapshot=sealed_snapshot, effective_read_set=snapshot.base_read_set,
                current_planning_state=state, target_resolution_authority=target_authority,
            )
            planned = BuiltInBootstrapGraphTargetMaterializationPlannerV3().plan(request=target_request)
            reduction = BootstrapNativeSemanticReducerV3().reduce(
                request=target_request, planning=planned,
            )
            reductions.append(reduction)
            if hasattr(planned, "planning_state_after"):
                state = planned.planning_state_after
        members.append(BootstrapTransactionGroupPlanMemberV3.create(
            transaction_group_id=group.group_id, source_dependency_group_digest=group.group_id,
            sealed_graph_snapshot_digest=sealed_snapshot.snapshot_digest, graph_read_set=read_token,
            reference_integrity_ledger_digest=read_token.reference_ledger_digest,
            planning_state_before=state, operation_plans=tuple(plans), planning_state_after=state,
            required_reservation_digests=(),
        ))
    members = tuple(members)
    evidence = tuple(BootstrapGraphPreExecutionGroupEvidenceV3.create(
        request_digest=request.request_digest, normalization_replay_digest=request.normalization_replay.replay_digest,
        transaction_group_id=group.group_id, group_plan_member_digest=member.member_digest,
        graph_snapshot_digest=sealed_snapshot.snapshot_digest, sealed_read_set_digest=snapshot.base_read_set.read_set_digest,
        reconciliation_digest=_digest((request.request_digest, "reconciliation")),
        reference_closure_digest=_digest((request.request_digest, "reference")), graph_validation_attempts=(),
        causal_blockers=(), terminal_before_planning_proof_digests=(), control_epoch_digest=epoch.epoch_digest,
    ) for group, member in zip(groups, members, strict=True))
    inputs = BootstrapGraphAttemptConstructionInputsV3.create(
        request_digest=request.request_digest, normalization_replay_digest=request.normalization_replay.replay_digest,
        normalization_result_digest=request.normalization_replay.source_normalization_result.result_digest,
        source_alignment_digest=request.source_alignment.alignment_digest, graph_snapshot_digest=sealed_snapshot.snapshot_digest,
        sealed_read_set_digest=snapshot.base_read_set.read_set_digest,
        reconciliation_digest=evidence[0].reconciliation_digest, reference_closure_digest=evidence[0].reference_closure_digest,
        execution_policy_reference_digest=policy.artifact_digest, control_epoch_digest=epoch.epoch_digest,
        ordered_pre_execution_evidence_digests=tuple(item.evidence_digest for item in evidence),
    )
    plan = BootstrapTransactionGroupPlanV3.create(
        request_digest=request.request_digest, normalization_replay_digest=request.normalization_replay.replay_digest,
        source_alignment_digest=request.source_alignment.alignment_digest, graph_snapshot_digest=sealed_snapshot.snapshot_digest,
        sealed_read_set_digest=snapshot.base_read_set.read_set_digest, fixed_point_rounds=1, group_members=members,
        canonical_group_order=tuple(item.transaction_group_id for item in members),
        execution_policy_reference_digest=policy.artifact_digest,
        operation_lease_binding_digest=epoch.operation_lease_binding.binding_digest,
        operation_fence_binding_digest=epoch.operation_fence_binding.binding_digest,
        writer_commit_binding_digest=epoch.writer_commit_binding.binding_digest, control_epoch_digest=epoch.epoch_digest,
    )
    reductions_by_group: dict[str, list[BootstrapGraphOperationReductionV3]] = {}
    for reduction in reductions:
        reductions_by_group.setdefault(reduction.transaction_group_id, []).append(reduction)
    manifest_group_inputs = tuple(
        BootstrapGraphExecutionManifestGroupInputV3.create(
            transaction_group_id=member.transaction_group_id,
            group_plan_member=member,
            compilation_request_digest=request.request_digest,
            compilation_artifact_digest=contract_digest(
                b"memorii.bootstrap-graph.builtin.compilation-artifact.v3",
                tuple(item.native_compilation.compilation_digest for item in sorted(
                    reductions_by_group[member.transaction_group_id],
                    key=lambda item: item.operation_id,
                )),
            ),
            independence_certificate_digest=contract_digest(
                b"memorii.bootstrap-graph.builtin.independence-certificate.v3",
                tuple(item.native_artifact_closure.closure_digest for item in sorted(
                    reductions_by_group[member.transaction_group_id],
                    key=lambda item: item.operation_id,
                )),
            ),
            ordered_operation_ids=member.operation_ids,
            proposed_delta_digest=contract_digest(
                b"memorii.bootstrap-graph.builtin.proposed-delta.v3",
                tuple(item.effect_materialization.materialization_digest for item in sorted(
                    reductions_by_group[member.transaction_group_id],
                    key=lambda item: item.operation_id,
                )),
            ),
            event_batch_digest=contract_digest(
                b"memorii.bootstrap-graph.builtin.event-batch.v3",
                tuple(item.native_terminal.terminal_digest for item in sorted(
                    reductions_by_group[member.transaction_group_id],
                    key=lambda item: item.operation_id,
                )),
            ),
        )
        for member in plan.group_members
    )
    return _BuiltInCompilation(BootstrapGraphPlanCompilationV3.create(
        request_digest=request.request_digest, normalization_replay_digest=request.normalization_replay.replay_digest,
        control_epoch_digest=epoch.epoch_digest, transaction_group_plan=plan,
        operation_reductions=tuple(reductions), manifest_group_inputs=manifest_group_inputs,
        attempt_construction_inputs=inputs, pre_execution_evidence=evidence,
    ))


@dataclass(frozen=True)
class _Compiler:
    operation_inputs: tuple[object, ...]
    sealed_snapshot: SealedGraphStateSnapshot
    canonical_identity_authority: object | None

    def compile(self, *, request: object, control_epoch: object) -> _BuiltInCompilation:
        return _compile(
            request=request, epoch=control_epoch, operation_inputs=self.operation_inputs,
            sealed_snapshot=self.sealed_snapshot,
            canonical_identity_authority=self.canonical_identity_authority,
        )


@dataclass(frozen=True)
class _Authorizer:
    compilation: _BuiltInCompilation

    def authorize(self, *, request: object, control_epoch: object, reloaded_plan: object) -> BootstrapGraphPlanAuthorizationSetV3:
        core = reloaded_plan.core
        raw_plan = next(item for item in core.members if item.kind == "bootstrap_transaction_group_plan")
        plan = BootstrapTransactionGroupPlanV3.model_validate(decode_bootstrap_graph_atomic_member_payload_v3(kind=raw_plan.kind, raw=raw_plan.canonical_payload))
        if core.control_epoch_digest != control_epoch.epoch_digest or plan.plan_digest != self.compilation.plan.plan_digest:
            raise ValueError("bootstrap graph plan authorization authority is substituted")
        authorizations = tuple(BootstrapGroupPlanningAuthorizationV3.create(
            request_digest=request.request_digest, transaction_group_id=member.transaction_group_id,
            group_plan_member_digest=member.member_digest, operation_ids=member.operation_ids,
            operation_plan_digests=tuple(item.operation_plan_digest for item in member.operation_plans),
            admission_authority_digest=contract_digest(
                b"memorii.bootstrap-graph.builtin.admission-authority.v3",
                {"request_digest": request.request_digest, "transaction_group_id": member.transaction_group_id,
                 "plan_digest": plan.plan_digest},
            ), capability_binding_digests=(),
            reservation_use_authority=BootstrapNoReservationUseV3.create(
                kind="none", transaction_group_id=member.transaction_group_id,
                planned_identity_reservation_digests=(),
            ), graph_read_set_digest=member.graph_read_set.read_set_digest,
            operation_lease_binding_digest=control_epoch.operation_lease_binding.binding_digest,
            operation_fence_binding_digest=control_epoch.operation_fence_binding.binding_digest,
            writer_commit_binding_digest=control_epoch.writer_commit_binding.binding_digest,
            control_epoch_digest=control_epoch.epoch_digest,
        ) for member in plan.group_members)
        return BootstrapGraphPlanAuthorizationSetV3.create(
            request_digest=request.request_digest, plan_digest=plan.plan_digest,
            control_epoch_digest=control_epoch.epoch_digest, authorizations=authorizations,
        )


class _BuiltInBootstrapGraphExecutionBuilderV3:
    def build(
        self, *, request: BootstrapGraphAuthorityRequestV3, atomic_store: object,
    ) -> BootstrapGraphExecutionV3 | None:
        """Build the concrete local graph execution without injection."""
        reduction_reload = atomic_store.reload_bootstrap_semantic_reduction_authority_v3(
            normalization_replay=request.normalization_replay
        )
        normalization_authority = atomic_store.reload_bootstrap_graph_normalization_authority_v3(
            normalization_replay=request.normalization_replay
        )
        if reduction_reload is None or normalization_authority is None:
            return None
        authority_repository = AtomicStoreBootstrapGraphTransactionAuthorityRepositoryV3(
            atomic_store=atomic_store
        )
        authority_reload = authority_repository.reload_for_recovery(
            recovery_key_digest=request.normalization_replay.recovery_key_digest,
            delivery_principal_binding_digest=request.operation_fence_binding.delivery_principal_binding_digest,
            required_outcome_scopes=request.required_outcome_scopes,
            operation_fence_binding=request.operation_fence_binding,
        )
        if authority_reload is None:
            graph_snapshot = atomic_store.graph_state_snapshot()
            snapshot = GraphSemanticSnapshotBundleV3.create(
                graph_snapshot=graph_snapshot, base_read_set=graph_snapshot.read_set,
            )
            policy_member = normalization_authority.authority_member
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
            capabilities = normalization_authority.authority_member.capability_registry
            authority = BootstrapGraphSnapshotAuthorityV3.create(
                source_id=request.prepared_source.source_id, source_digest=request.prepared_source.source_digest,
                preparation_fingerprint=request.prepared_source.preparation_fingerprint,
                normalization_replay_digest=request.normalization_replay.replay_digest,
                normalization_result_digest=request.normalization_replay.source_normalization_result.result_digest,
                source_alignment_digest=request.normalization_replay.source_normalization_request.source_alignment.alignment_digest,
                snapshot=snapshot, base_read_set_digest=snapshot.base_read_set.read_set_digest,
                required_scope_set_digest=request.required_outcome_scopes.required_scope_set_digest,
                delivery_principal_binding_digest=request.operation_fence_binding.delivery_principal_binding_digest,
                execution_policy=policy, capability_registry_snapshot=capabilities,
                operation_lease_binding=request.operation_lease_binding,
                operation_fence_binding=request.operation_fence_binding, writer_commit_binding=request.writer_commit_binding,
            )
            prepared_terminal = BootstrapGraphPreparedSourceTerminalAuthorityV3.create(
                prepared_source=request.prepared_source,
                execution_graph=CANONICAL_INGESTION_EXECUTION_GRAPH,
            )
            authority_projection = BootstrapGraphTransactionAuthorityProjectionV3.create(
                normalization_authority=normalization_authority,
                graph_authority=authority,
                prepared_source_terminal=prepared_terminal,
            )
            authority_reload = authority_repository.publish_or_reload(
                request=BootstrapGraphTransactionAuthorityWriteRequestV3.create(
                    authority_projection=authority_projection,
                    delivery_principal_binding_digest=request.operation_fence_binding.delivery_principal_binding_digest,
                    required_outcome_scopes=request.required_outcome_scopes,
                    operation_fence_binding=request.operation_fence_binding,
                    operation_lease_binding=request.operation_lease_binding,
                    writer_commit_binding=request.writer_commit_binding,
                    expected_normalization_operation_generation=(
                        normalization_authority.normalization_operation_generation
                    ),
                    expected_normalization_artifact_generation=(
                        normalization_authority.normalization_artifact_generation
                    ),
                )
            )
        authority = authority_reload.publication_core.authority_projection.graph_authority
        core = {"schema_version": 3, "normalization_replay": request.normalization_replay,
                "source_alignment": request.normalization_replay.source_normalization_request.source_alignment,
                "source_dependency_groups": request.normalization_replay.source_normalization_request.source_alignment.source_dependency_groups,
                "graph_authority": authority, "delivery_principal_binding_digest": (
                    request.operation_fence_binding.delivery_principal_binding_digest
                ),
                "required_outcome_scopes": request.required_outcome_scopes}
        request_core_digest = contract_digest(b"memorii.semantic-ingestion.bootstrap-graph-request-core.v3", core)
        epochs = AtomicStoreBootstrapGraphControlEpochRepositoryV3(atomic_store=atomic_store)
        source_alignment = request.normalization_replay.source_normalization_request.source_alignment
        groups = source_alignment.source_dependency_groups
        transition = None
        current_epoch = epochs.load_current(request_core_digest=request_core_digest)
        if current_epoch is None:
            transition = BootstrapGraphControlEpochTransitionRequestV3.create(
                request_core_digest=request_core_digest, expected_epoch_digest=None, transition="initial",
                normalization_replay=request.normalization_replay, graph_authority=authority,
                delivery_principal_binding_digest=request.operation_fence_binding.delivery_principal_binding_digest, required_outcome_scopes=request.required_outcome_scopes,
                operation_fence=authority.operation_fence_binding,
                operation_lease=authority.operation_lease_binding,
                writer_commit=authority.writer_commit_binding,
            )
            epoch = epochs.transition_or_find(request=transition).epoch
        else:
            coordinator_request = BootstrapGraphDependentCoordinatorRequestV3.create(
                normalization_replay=request.normalization_replay,
                source_alignment=source_alignment, source_dependency_groups=groups,
                delivery_principal_binding_digest=request.operation_fence_binding.delivery_principal_binding_digest,
                required_outcome_scopes=request.required_outcome_scopes,
                graph_authority=authority, request_core_digest=request_core_digest,
                initial_control_epoch=current_epoch,
            )
            refreshed = epochs.refresh_current(
                request=coordinator_request, current_epoch=current_epoch
            )
            if isinstance(refreshed, BootstrapGraphControlEpochUnavailableV3):
                return None
            epoch = refreshed.epoch
        coordinator_request = BootstrapGraphDependentCoordinatorRequestV3.create(
            normalization_replay=request.normalization_replay,
            source_alignment=source_alignment, source_dependency_groups=groups,
            delivery_principal_binding_digest=request.operation_fence_binding.delivery_principal_binding_digest, required_outcome_scopes=request.required_outcome_scopes,
            graph_authority=authority, request_core_digest=request_core_digest, initial_control_epoch=epoch,
        )
        graph_state = atomic_store.semantic_replay_state()
        reference_integrity = atomic_store.reference_integrity_snapshot()
        graph_snapshot = atomic_store.graph_state_snapshot()
        confirmed_graph_state = atomic_store.semantic_replay_state()
        partition_versions = {
            item.partition_id: item.version
            for item in graph_snapshot.read_set.partition_versions
        }
        if (
            graph_state != confirmed_graph_state
            or partition_versions.get("canonical_graph") != graph_state.state_digest
            or partition_versions.get("reference_ledger")
            != reference_integrity.ledger_digest
        ):
            return None
        sealed_snapshot = SealedGraphStateSnapshot.create(
            graph_state=graph_state, canonical_graph=graph_snapshot,
            reference_integrity=reference_integrity,
            read_set=GraphReadSetToken.create(
                graph_revision=graph_state.graph_revision,
                replay_state_digest=graph_state.state_digest,
                reference_ledger_digest=reference_integrity.ledger_digest,
            ), system_as_of=graph_snapshot.system_as_of,
        )
        operation_inputs = reduction_reload.authority_member.operation_inputs
        initial_state = GraphPlanningState.create(base_snapshot_digest=sealed_snapshot.snapshot_digest, records=(), codec_manifest_fingerprint=authority.snapshot.graph_snapshot.codec_manifest_fingerprint, applied_planned_delta_digests=())
        canonical_candidate = BootstrapCanonicalIdentityBindingAllocationProjectorV3().project(operation_inputs=operation_inputs, recovery_key_digest=request.normalization_replay.recovery_key_digest, sealed_snapshot=sealed_snapshot, effective_read_set=graph_snapshot.read_set, current_planning_state=initial_state, required_scope_set_digest=request.required_outcome_scopes.required_scope_set_digest, authorized_scope_identity=request.operation_fence_binding.delivery_principal_binding_digest, allocation_namespace_id=request.operation_fence_binding.allocation_namespace_id, allocation_policy_fingerprint=authority.execution_policy.policy_digest, allow_new_allocation=True, source_plan_checkpoint_digest=request_core_digest, publication_generation_digest=epoch.epoch_digest)
        canonical_reload = AtomicStoreBootstrapCanonicalIdentityAuthorityRepositoryV3(atomic_store=atomic_store).publish_or_reload(request=BootstrapCanonicalIdentityAuthorityWriteRequestV3.create(authority_reload=canonical_candidate, operation_fence_binding=request.operation_fence_binding, operation_lease_binding=request.operation_lease_binding, writer_commit_binding=request.writer_commit_binding, delivery_principal_binding_digest=request.operation_fence_binding.delivery_principal_binding_digest, required_outcome_scopes=request.required_outcome_scopes))
        compilation = _compile(
            request=coordinator_request, epoch=epoch, operation_inputs=operation_inputs,
            sealed_snapshot=sealed_snapshot, canonical_identity_authority=canonical_reload,
        )
        source = request.prepared_source
        artifact = source.governance_carrier_artifact
        host = BootstrapGraphTerminalHostAuthorityV3.create(
            source_id=source.source_id, source_digest=source.source_digest,
            preparation_fingerprint=source.preparation_fingerprint,
            delivery_principal_binding_digest=request.operation_fence_binding.delivery_principal_binding_digest,
            delivery_key_digest=request.operation_fence_binding.delivery_key_digest,
            execution_graph_fingerprint=CANONICAL_INGESTION_EXECUTION_GRAPH.graph_fingerprint,
            segment_language_routes=source.segment_language_routes,
            segment_governance_carriers=source.segment_governance_carriers,
            message_admission_carriers=source.message_admission_carriers,
            governance_carrier_artifact=artifact, capability_bindings=(),
            required_outcome_scopes=artifact.required_outcome_scopes,
            operation_fence_binding=request.operation_fence_binding,
        )
        coordinator = BootstrapGraphDependentCoordinatorV3(
            epoch_repository=epochs, plan_repository=AtomicStoreBootstrapGraphPlanRepositoryV3(atomic_store=atomic_store),
            terminal_port=AtomicStoreBootstrapGraphTerminalPersistencePortV3(atomic_store=atomic_store),
            compiler=_Compiler(operation_inputs, sealed_snapshot, canonical_reload), authorizer=_Authorizer(compilation),
            group_commit_repository=AtomicStoreBootstrapGraphGroupCommitRepositoryV3(atomic_store=atomic_store),
            terminal_preparer=DeterministicBootstrapGraphTerminalPreparationV3(), terminal_host_authority=host,
        )
        return BootstrapGraphExecutionV3(coordinator=coordinator, request=coordinator_request, transition=transition)


def build_builtin_bootstrap_graph_execution_v3(
    *, request: BootstrapGraphAuthorityRequestV3, atomic_store: object,
) -> BootstrapGraphExecutionV3 | None:
    return _BuiltInBootstrapGraphExecutionBuilderV3().build(request=request, atomic_store=atomic_store)


class BuiltInBootstrapGraphAuthorityProviderV3:
    """Historical fixture adapter; normal roots call the concrete function."""

    def acquire(
        self, *, request: BootstrapGraphAuthorityRequestV3, atomic_store: object,
    ) -> BootstrapGraphExecutionV3 | None:
        return build_builtin_bootstrap_graph_execution_v3(
            request=request, atomic_store=atomic_store,
        )


__all__ = [
    "BuiltInBootstrapGraphAuthorityProviderV3",
    "build_builtin_bootstrap_graph_execution_v3",
]
