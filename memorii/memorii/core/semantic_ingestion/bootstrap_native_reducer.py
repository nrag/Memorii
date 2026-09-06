"""Pure request-bound V3 native operation reduction."""

from __future__ import annotations

from memorii.core.semantic_ingestion.contracts import (
    BootstrapGraphOperationReductionV3,
    BootstrapGraphTargetMaterializationPlanV3,
    BootstrapNativeActionStateEffectV3,
    BootstrapNativeCorrectionEffectV3,
    BootstrapNativeFactEffectV3,
    BootstrapNativeIdentityEffectV3,
    BootstrapNativeOperationArtifactClosureV3,
    BootstrapNativeOperationCompilationV3,
    BootstrapNativeOperationEffectMaterializationV3,
    BootstrapNativeOperationTerminalV3,
    BootstrapNativePlanningUnavailableV3,
    BootstrapNativeRecordMaterializationIntentV3,
    BootstrapNativeRetractionEffectV3,
    BootstrapNativeTargetPlanningRequestV3,
)


class BootstrapNativeSemanticReducerV3:
    """Project exactly one planner result; never discovers graph state itself."""

    def reduce(
        self,
        *,
        request: BootstrapNativeTargetPlanningRequestV3,
        planning: BootstrapGraphTargetMaterializationPlanV3
        | BootstrapNativePlanningUnavailableV3,
    ) -> BootstrapGraphOperationReductionV3:
        _validate_planning_binding(request=request, planning=planning)
        if isinstance(planning, BootstrapNativePlanningUnavailableV3):
            return _reduce_unavailable(request=request, planning=planning)
        return _reduce_accepted(request=request, plan=planning)


def _validate_planning_binding(
    *,
    request: BootstrapNativeTargetPlanningRequestV3,
    planning: BootstrapGraphTargetMaterializationPlanV3 | BootstrapNativePlanningUnavailableV3,
) -> None:
    operation = request.operation_input
    expected = (
        request.request_digest,
        request.transaction_group_id,
        operation.operation_execution_id,
        operation.operation_id,
        operation.normalized_proposal.proposal_digest,
        request.sealed_snapshot.snapshot_digest,
        request.effective_read_set.read_set_digest,
        request.current_planning_state.state_digest,
    )
    actual = (
        planning.request_digest,
        planning.transaction_group_id,
        planning.operation_execution_id,
        planning.operation_id,
        planning.proposal_digest,
        planning.sealed_snapshot_digest,
        planning.effective_read_set_digest,
        planning.planning_state_before_digest,
    )
    if actual != expected:
        raise ValueError("native target planning result is cross-request")
    if isinstance(planning, BootstrapGraphTargetMaterializationPlanV3) and (
        planning.operation_kind != operation.operation_member.kind
    ):
        raise ValueError("native target plan operation kind is substituted")


def _reduce_unavailable(
    *,
    request: BootstrapNativeTargetPlanningRequestV3,
    planning: BootstrapNativePlanningUnavailableV3,
) -> BootstrapGraphOperationReductionV3:
    operation = request.operation_input
    compilation = BootstrapNativeOperationCompilationV3.create(
        transaction_group_id=request.transaction_group_id,
        operation_input=operation,
        operation_id=operation.operation_id,
        operation_execution_id=operation.operation_execution_id,
        operation_member=operation.operation_member,
        resolved_graph_targets=(),
        sealed_operations=(),
        accepted_carriers=(),
        terminal_binding_sets=(),
        terminal_status=planning.status,
        reason_codes=planning.reason_codes,
    )
    materialization = BootstrapNativeOperationEffectMaterializationV3.create(
        operation_execution_id=operation.operation_execution_id,
        operation_id=operation.operation_id,
        terminal_status=planning.status,
        accepted_effect=None,
        record_intents=(),
        observation_disposition=planning.status,
        observation_reason_codes=planning.reason_codes,
    )
    terminal = BootstrapNativeOperationTerminalV3.create(
        operation_execution_id=operation.operation_execution_id,
        operation_id=operation.operation_id,
        proposal_digest=operation.normalized_proposal.proposal_digest,
        operation_kind=operation.operation_member.kind,
        sealed_snapshot_digest=request.sealed_snapshot.snapshot_digest,
        effective_read_set_digest=request.effective_read_set.read_set_digest,
        native_compilation_digest=compilation.compilation_digest,
        status=planning.status,
        reason_codes=planning.reason_codes,
        coverage_binding_digests=tuple(item.binding_digest for item in operation.coverage_bindings),
        accepted_effect_digest=None,
        record_intent_digests=(),
    )
    closure = BootstrapNativeOperationArtifactClosureV3.create(
        operation_execution_id=operation.operation_execution_id,
        operation_id=operation.operation_id,
        terminal_digest=terminal.terminal_digest,
        native_compilation_digest=compilation.compilation_digest,
        accepted_effect_digest=None,
        record_intent_digests=(),
        coverage_binding_digests=terminal.coverage_binding_digests,
        graph_target_digests=(),
        planning_result_digest=None,
    )
    return BootstrapGraphOperationReductionV3.create(
        transaction_group_id=request.transaction_group_id,
        operation_id=operation.operation_id,
        proposal_digest=operation.normalized_proposal.proposal_digest,
        operation_execution_id=operation.operation_execution_id,
        sealed_snapshot_digest=request.sealed_snapshot.snapshot_digest,
        effective_read_set_digest=request.effective_read_set.read_set_digest,
        native_compilation=compilation,
        native_terminal=terminal,
        native_artifact_closure=closure,
        effect_materialization=materialization,
    )


def _reduce_accepted(
    *, request: BootstrapNativeTargetPlanningRequestV3,
    plan: BootstrapGraphTargetMaterializationPlanV3,
) -> BootstrapGraphOperationReductionV3:
    operation = request.operation_input
    member = operation.operation_member
    effect = _accepted_effect(member=member, plan=plan)
    intents = tuple(
        BootstrapNativeRecordMaterializationIntentV3.create(
            operation_execution_id=operation.operation_execution_id,
            record_kind=record.record_kind,
            record_id=record.record_id,
            mutation_kind="create" if record.precondition.kind == "absent" else "update",
            expected_prior_record_digest=(
                None
                if record.precondition.kind == "absent"
                else record.precondition.record_digest
                if record.precondition.kind == "durable"
                else record.precondition.planning_record_digest
            ),
            canonical_after_record=record.planning_payload,
            source_member_digest=record.source_member_digest,
        )
        for record in plan.planning_records
    )
    if not intents:
        raise ValueError("native accepted plan has no materialization records")
    targets = tuple(item.authority.target for item in plan.target_bindings)
    compilation = BootstrapNativeOperationCompilationV3.create(
        transaction_group_id=request.transaction_group_id,
        operation_input=operation,
        operation_id=operation.operation_id,
        operation_execution_id=operation.operation_execution_id,
        operation_member=member,
        resolved_graph_targets=targets,
        sealed_operations=(),
        accepted_carriers=(),
        terminal_binding_sets=(),
        terminal_status="accepted",
        reason_codes=(),
    )
    materialization = BootstrapNativeOperationEffectMaterializationV3.create(
        operation_execution_id=operation.operation_execution_id,
        operation_id=operation.operation_id,
        terminal_status="accepted",
        accepted_effect=effect,
        record_intents=intents,
        observation_disposition="committed",
        observation_reason_codes=(),
    )
    terminal = BootstrapNativeOperationTerminalV3.create(
        operation_execution_id=operation.operation_execution_id,
        operation_id=operation.operation_id,
        proposal_digest=operation.normalized_proposal.proposal_digest,
        operation_kind=member.kind,
        sealed_snapshot_digest=request.sealed_snapshot.snapshot_digest,
        effective_read_set_digest=request.effective_read_set.read_set_digest,
        native_compilation_digest=compilation.compilation_digest,
        status="accepted",
        reason_codes=(),
        coverage_binding_digests=tuple(item.binding_digest for item in operation.coverage_bindings),
        accepted_effect_digest=effect.effect_digest,
        record_intent_digests=tuple(item.intent_digest for item in intents),
    )
    closure = BootstrapNativeOperationArtifactClosureV3.create(
        operation_execution_id=operation.operation_execution_id,
        operation_id=operation.operation_id,
        terminal_digest=terminal.terminal_digest,
        native_compilation_digest=compilation.compilation_digest,
        accepted_effect_digest=effect.effect_digest,
        record_intent_digests=terminal.record_intent_digests,
        coverage_binding_digests=terminal.coverage_binding_digests,
        graph_target_digests=tuple(item.binding_digest for item in plan.target_bindings),
        planning_result_digest=(
            plan.identity_materialization.fresh_planning_result.result_digest
            if plan.identity_materialization is not None else None
        ),
    )
    return BootstrapGraphOperationReductionV3.create(
        transaction_group_id=request.transaction_group_id,
        operation_id=operation.operation_id,
        proposal_digest=operation.normalized_proposal.proposal_digest,
        operation_execution_id=operation.operation_execution_id,
        sealed_snapshot_digest=request.sealed_snapshot.snapshot_digest,
        effective_read_set_digest=request.effective_read_set.read_set_digest,
        native_compilation=compilation,
        native_terminal=terminal,
        native_artifact_closure=closure,
        effect_materialization=materialization,
    )


def _accepted_effect(*, member: object, plan: BootstrapGraphTargetMaterializationPlanV3):
    if member.kind == "fact":
        return BootstrapNativeFactEffectV3.create(
            kind="fact", fact=member, target_bindings=plan.target_bindings,
            planning_records=plan.planning_records, terminal_bindings=plan.terminal_bindings,
            evidence_projections=plan.evidence_projections,
        )
    if member.kind == "correction":
        replacement = BootstrapNativeFactEffectV3.create(
            kind="fact", fact=member.replacement_fact, target_bindings=plan.target_bindings,
            planning_records=plan.planning_records, terminal_bindings=plan.terminal_bindings,
            evidence_projections=plan.evidence_projections,
        )
        return BootstrapNativeCorrectionEffectV3.create(
            kind="correction", correction=member,
            corrected_targets=tuple(item for item in plan.target_bindings if item.role == "corrected_target"),
            replacement_effect=replacement,
            transition_records=tuple(item for item in plan.planning_records if item.record_kind == "temporal_transition"),
        )
    if member.kind == "retraction":
        return BootstrapNativeRetractionEffectV3.create(
            kind="retraction", retraction=member,
            retracted_targets=tuple(item for item in plan.target_bindings if item.role == "retracted_target"),
            transition_records=tuple(item for item in plan.planning_records if item.record_kind == "temporal_transition"),
            evidence_projections=plan.evidence_projections,
        )
    if member.kind == "action_state":
        return BootstrapNativeActionStateEffectV3.create(
            kind="action_state", action_state=member,
            resolved_participants=tuple(item for item in plan.target_bindings if item.role == "action_participant"),
            planning_records=plan.planning_records, terminal_bindings=plan.terminal_bindings,
            evidence_projections=plan.evidence_projections,
        )
    if member.kind == "identity" and plan.identity_materialization is not None:
        return BootstrapNativeIdentityEffectV3.create(
            kind="identity", identity_operation=member,
            materialization=plan.identity_materialization,
            target_bindings=plan.target_bindings, terminal_bindings=plan.terminal_bindings,
            evidence_projections=plan.evidence_projections,
        )
    raise ValueError("native accepted plan/member arm is incomplete")


__all__ = ["BootstrapNativeSemanticReducerV3"]
