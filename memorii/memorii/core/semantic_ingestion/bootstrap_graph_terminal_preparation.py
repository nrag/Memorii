"""Host-owned preparation boundary for sealed bootstrap graph terminals."""

from __future__ import annotations

from typing import Protocol

from memorii.core.memory_evolution.graph_effect_contracts import (
    CanonicalSourceTerminalOutcomeCore,
    CanonicalSourceTerminalOutcomeRecord,
)
from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
from memorii.core.semantic_ingestion.bootstrap_graph_artifact_assembler import (
    BootstrapGraphArtifactAssemblerV3,
)
from memorii.core.semantic_ingestion.contracts import (
    CANONICAL_INGESTION_EXECUTION_GRAPH,
    BootstrapGraphCanonicalSourceResultInputV3,
    BootstrapGraphCanonicalSourceResultV3,
    BootstrapGraphCurrentGenerationV3,
    BootstrapGraphDependentAttemptV3,
    BootstrapGraphDependentCoordinatorRequestV3,
    BootstrapGraphExecutionManifestConstructionV3,
    BootstrapGraphFinalStageEvidenceV3,
    BootstrapGraphPlanCompilationV3,
    BootstrapGraphPreExecutionManifestIdentityClosureV3,
    BootstrapGraphTerminalHandoffCoreV3,
    BootstrapGraphTerminalHostAuthorityV3,
    BootstrapGraphTerminalMemberIntentV3,
    BootstrapGraphTerminalPersistenceHandoffV3,
    BootstrapGraphTerminalPreparationV3,
    BootstrapGraphTerminalPublicationIntentV3,
    BootstrapNativeGroupCommitTerminalConstructionV3,
    BootstrapSourcePlanLineageV3,
    BootstrapTransactionGroupPlanV3,
    IngestionExecutionManifest,
    IngestionStageInstanceRef,
    IngestionStageOutcome,
    contract_digest,
)


def _canonical_outcomes(
    outcomes: tuple[IngestionStageOutcome, ...],
) -> tuple[IngestionStageOutcome, ...]:
    return tuple(
        sorted(
            outcomes,
            key=lambda outcome: encode_typed_value(outcome.model_dump(mode="python")),
        )
    )


def _canonical_stage_instances(
    values: tuple[IngestionStageInstanceRef, ...],
) -> tuple[IngestionStageInstanceRef, ...]:
    return tuple(
        sorted(
            set(values),
            key=lambda value: encode_typed_value(value.model_dump(mode="python")),
        )
    )


def build_bootstrap_graph_execution_stage_outcomes(
    *,
    request: BootstrapGraphDependentCoordinatorRequestV3,
    control_epoch: object,
    host_authority: BootstrapGraphTerminalHostAuthorityV3,
    final_attempt: BootstrapGraphDependentAttemptV3,
    complete_lineage: BootstrapSourcePlanLineageV3,
    group_constructions: tuple[BootstrapNativeGroupCommitTerminalConstructionV3, ...],
    finalized_failure_group_id: str | None = None,
) -> tuple[
    tuple[IngestionStageOutcome, ...],
    tuple[tuple[str, tuple[IngestionStageOutcome, ...]], ...],
    tuple[IngestionStageInstanceRef, ...],
]:
    """Materialize the terminal source/segment/group stage closure from sealed inputs.

    This deliberately has no store lookup: the terminal manifest is an exact projection
    of the retained replay authority, epoch, lineage, and CAS constructions.
    """
    if (
        final_attempt.request_digest != request.request_digest
        or final_attempt.normalization_replay_digest != request.normalization_replay.replay_digest
        or complete_lineage.request_digest != request.request_digest
        or complete_lineage.control_epoch_digest != control_epoch.epoch_digest
        or host_authority.execution_graph_fingerprint
        != CANONICAL_INGESTION_EXECUTION_GRAPH.graph_fingerprint
        or not complete_lineage.entries
        or (host_authority.source_id, host_authority.source_digest, host_authority.preparation_fingerprint)
        != (
            complete_lineage.entries[0].source_id,
            complete_lineage.entries[0].source_digest,
            complete_lineage.entries[0].preparation_fingerprint,
        )
    ):
        raise ValueError("bootstrap graph execution stage inputs are substituted")

    dispositions = {item.transaction_group_id: item.disposition for item in group_constructions}
    group_ids = tuple(
        group_id for group_id, _entry_digest in complete_lineage.latest_entry_by_group
    )
    if (
        not group_ids
        or len(dispositions) != len(group_constructions)
        or not set(dispositions).issubset(group_ids)
        or (
            finalized_failure_group_id is not None
            and finalized_failure_group_id not in group_ids
        )
    ):
        raise ValueError("bootstrap graph execution stage groups are invalid")

    routes = host_authority.segment_language_routes.routes
    stage_specs = {spec.stage: spec for spec in CANONICAL_INGESTION_EXECUTION_GRAPH.stages}
    successful = {"complete", "committed", "evidence_only"}
    target_status: dict[IngestionStageInstanceRef, str] = {}

    # All pre-graph source and segment work is retained by the recovered V3 replay.
    for spec in CANONICAL_INGESTION_EXECUTION_GRAPH.stages:
        if "source" in spec.allowed_scopes:
            target_status[IngestionStageInstanceRef(stage=spec.stage, scope="source")] = "complete"
        if "segment" in spec.allowed_scopes:
            for route in routes:
                target_status[IngestionStageInstanceRef(
                    stage=spec.stage,
                    scope="segment",
                    segment_id=route.segment_id,
                    segment_language_route_digest=route.route_digest,
                )] = "complete"

    # A failed group stops at its first terminal group stage; later stages and source
    # summary persistence remain explicitly blocked. Noncommitting groups are durable
    # evidence, while committed groups retain their persistence terminal.
    for group_id in group_ids:
        disposition = dispositions.get(group_id)
        for spec in CANONICAL_INGESTION_EXECUTION_GRAPH.stages:
            if "transaction_group" not in spec.allowed_scopes:
                continue
            instance = IngestionStageInstanceRef(
                stage=spec.stage, scope="transaction_group", transaction_group_id=group_id
            )
            if group_id == finalized_failure_group_id:
                target_status[instance] = "failed" if spec.stage == "graph_compilation" else "not_started"
            elif disposition is None:
                target_status[instance] = "not_started"
            elif disposition == "committed" and spec.stage == "transaction_group_persistence":
                target_status[instance] = "committed"
            elif disposition == "committed":
                target_status[instance] = "complete"
            else:
                target_status[instance] = "evidence_only"

    summary = IngestionStageInstanceRef(stage="source_summary_persistence", scope="source")
    if any(
        target_status[IngestionStageInstanceRef(
            stage="transaction_group_persistence", scope="transaction_group", transaction_group_id=group_id
        )] not in successful
        for group_id in group_ids
    ):
        target_status[summary] = "not_started"

    def dependencies(instance: IngestionStageInstanceRef) -> tuple[IngestionStageInstanceRef, ...]:
        values: list[IngestionStageInstanceRef] = []
        for dependency in stage_specs[instance.stage].dependencies:
            if dependency.mode != "required":
                continue
            allowed = stage_specs[dependency.stage].allowed_scopes
            if instance.scope == "segment":
                if "segment" in allowed:
                    values.append(IngestionStageInstanceRef(
                        stage=dependency.stage, scope="segment", segment_id=instance.segment_id,
                        segment_language_route_digest=instance.segment_language_route_digest,
                    ))
                elif "source" in allowed:
                    values.append(IngestionStageInstanceRef(stage=dependency.stage, scope="source"))
            elif instance.scope == "source":
                if "source" in allowed:
                    values.append(IngestionStageInstanceRef(stage=dependency.stage, scope="source"))
                elif "segment" in allowed:
                    values.extend(IngestionStageInstanceRef(
                        stage=dependency.stage, scope="segment", segment_id=route.segment_id,
                        segment_language_route_digest=route.route_digest,
                    ) for route in routes)
                elif "transaction_group" in allowed:
                    values.extend(IngestionStageInstanceRef(
                        stage=dependency.stage, scope="transaction_group", transaction_group_id=group_id,
                    ) for group_id in group_ids)
            elif instance.scope == "transaction_group" and "transaction_group" in allowed:
                values.append(IngestionStageInstanceRef(
                    stage=dependency.stage, scope="transaction_group", transaction_group_id=instance.transaction_group_id,
                ))
        return tuple(sorted(set(values), key=lambda value: encode_typed_value(value.model_dump(mode="python"))))

    def artifact_digest(instance: IngestionStageInstanceRef) -> str:
        return contract_digest(
            b"memorii.semantic-ingestion.bootstrap-graph-execution-stage-outcome.v3",
            {
                "request_digest": request.request_digest,
                "normalization_replay_digest": request.normalization_replay.replay_digest,
                "attempt_digest": final_attempt.attempt_digest,
                "source_plan_lineage_digest": complete_lineage.lineage_digest,
                "control_epoch_digest": control_epoch.epoch_digest,
                "instance": instance,
            },
        )

    outcomes: dict[IngestionStageInstanceRef, IngestionStageOutcome] = {}
    for instance, status in target_status.items():
        blockers = tuple(
            dependency for dependency in dependencies(instance)
            if target_status.get(dependency) not in successful
        )
        if status == "not_started":
            outcomes[instance] = IngestionStageOutcome(
                instance=instance, status="not_started", blocking_stages=blockers,
            )
        else:
            outcomes[instance] = IngestionStageOutcome(
                instance=instance, status=status, started_at=control_epoch.issued_server_time,
                completed_at=control_epoch.issued_server_time, artifact_digest=artifact_digest(instance),
                reason_codes=("group_execution_failed",) if status == "failed" else (),
            )

    source_outcomes = _canonical_outcomes(tuple(
        outcome for outcome in outcomes.values() if outcome.instance.scope in {"source", "segment"}
    ))
    transaction_group_outcomes = tuple(
        (group_id, _canonical_outcomes(tuple(
            outcome for outcome in outcomes.values()
            if outcome.instance.scope == "transaction_group"
            and outcome.instance.transaction_group_id == group_id
        )))
        for group_id in group_ids
    )
    causal_blockers = tuple(sorted({
        outcome.instance
        for outcome in outcomes.values()
        if outcome.status == "not_started" and outcome.blocking_stages
    }, key=lambda value: encode_typed_value(value.model_dump(mode="python"))))
    return source_outcomes, transaction_group_outcomes, causal_blockers


class BootstrapGraphTerminalPreparationPortV3(Protocol):
    def prepare(
        self, *, request: BootstrapGraphDependentCoordinatorRequestV3, control_epoch: object,
        current_generation: BootstrapGraphCurrentGenerationV3, final_attempt: BootstrapGraphDependentAttemptV3,
        final_compilation: BootstrapGraphPlanCompilationV3,
        pre_execution_manifests: BootstrapGraphPreExecutionManifestIdentityClosureV3,
        final_stage_evidence: BootstrapGraphFinalStageEvidenceV3,
        complete_lineage: BootstrapSourcePlanLineageV3,
        group_constructions: tuple[BootstrapNativeGroupCommitTerminalConstructionV3, ...],
        host_authority: BootstrapGraphTerminalHostAuthorityV3,
        finalized_failure_group_id: str | None = None,
    ) -> BootstrapGraphTerminalPreparationV3: ...


class DeterministicBootstrapGraphTerminalPreparationV3:
    """Validates host authority before emitting the sealed preparation carrier."""

    def execution_manifest(self, *, construction: BootstrapGraphExecutionManifestConstructionV3) -> IngestionExecutionManifest:
        if construction.pre_execution_manifest_identity_closure_digest != construction.pre_execution_manifests.closure_digest:
            raise ValueError("bootstrap graph execution manifest construction is substituted")
        return IngestionExecutionManifest.create(
            pre_execution_manifests=construction.pre_execution_manifests,
            pre_execution_manifest_identity_closure_digest=construction.pre_execution_manifest_identity_closure_digest,
            execution_graph_fingerprint=construction.execution_graph_fingerprint,
            segment_language_routes=construction.segment_language_routes,
            segment_governance_carriers=construction.segment_governance_carriers,
            message_admission_carriers=construction.message_admission_carriers,
            governance_carrier_artifact=construction.governance_carrier_artifact,
            capability_bindings=construction.capability_bindings, source_outcomes=construction.source_outcomes,
            graph_validation_attempts=construction.graph_validation_attempts,
            transaction_group_outcomes=construction.transaction_group_outcomes,
            causal_blockers=construction.causal_blockers,
            terminal_before_planning_proof_digests=construction.terminal_before_planning_proof_digests,
        )

    @staticmethod
    def validate_host_authority(
        *, request: object, complete_lineage: object, manifest: object,
        host_authority: object,
    ) -> None:
        if (
            (host_authority.source_id, host_authority.source_digest, host_authority.preparation_fingerprint)
            != (
                complete_lineage.entries[0].source_id,
                complete_lineage.entries[0].source_digest,
                complete_lineage.entries[0].preparation_fingerprint,
            )
            or host_authority.segment_governance_carriers != manifest.segment_governance_carriers
            or host_authority.message_admission_carriers != manifest.message_admission_carriers
            or host_authority.governance_carrier_artifact != manifest.governance_carrier_artifact
            or host_authority.required_outcome_scopes != request.required_outcome_scopes
            or host_authority.delivery_principal_binding_digest
            != request.delivery_principal_binding_digest
            or host_authority.operation_fence_binding != request.initial_control_epoch.operation_fence_binding
        ):
            raise ValueError("bootstrap graph terminal host authority is substituted")

    def prepare(
        self, *, request: BootstrapGraphDependentCoordinatorRequestV3, control_epoch: object,
        current_generation: BootstrapGraphCurrentGenerationV3, final_attempt: BootstrapGraphDependentAttemptV3,
        final_compilation: BootstrapGraphPlanCompilationV3,
        pre_execution_manifests: BootstrapGraphPreExecutionManifestIdentityClosureV3,
        final_stage_evidence: BootstrapGraphFinalStageEvidenceV3,
        complete_lineage: BootstrapSourcePlanLineageV3,
        group_constructions: tuple[BootstrapNativeGroupCommitTerminalConstructionV3, ...],
        host_authority: BootstrapGraphTerminalHostAuthorityV3,
        finalized_failure_group_id: str | None = None,
    ) -> BootstrapGraphTerminalPreparationV3:
        final_plan = final_compilation.plan
        source_outcomes, transaction_group_outcomes, causal_blockers = (
            build_bootstrap_graph_execution_stage_outcomes(
                request=request,
                control_epoch=control_epoch,
                host_authority=host_authority,
                final_attempt=final_attempt,
                complete_lineage=complete_lineage,
                group_constructions=group_constructions,
                finalized_failure_group_id=finalized_failure_group_id,
            )
        )
        causal_blockers = _canonical_stage_instances(
            causal_blockers + tuple(
                blocker
                for attempt in final_stage_evidence.graph_validation_attempts
                for outcome in attempt.stage_outcomes
                if outcome.status == "not_started"
                for blocker in outcome.blocking_stages
            )
        )
        if (
            final_stage_evidence.source_outcomes != source_outcomes
            or final_stage_evidence.causal_blockers != causal_blockers
        ):
            raise ValueError("bootstrap graph final stage evidence is substituted")
        manifest_construction = BootstrapGraphExecutionManifestConstructionV3.create(
            request_digest=request.request_digest,
            normalization_replay_digest=request.normalization_replay.replay_digest,
            attempt_digest=final_attempt.attempt_digest,
            transaction_group_plan_digest=final_plan.plan_digest,
            source_plan_lineage_digest=complete_lineage.lineage_digest,
            control_epoch_digest=control_epoch.epoch_digest,
            pre_execution_manifests=pre_execution_manifests,
            pre_execution_manifest_identity_closure_digest=pre_execution_manifests.closure_digest,
            execution_graph_fingerprint=host_authority.execution_graph_fingerprint,
            segment_language_routes=host_authority.segment_language_routes,
            segment_governance_carriers=host_authority.segment_governance_carriers,
            message_admission_carriers=host_authority.message_admission_carriers,
            governance_carrier_artifact=host_authority.governance_carrier_artifact,
            capability_bindings=host_authority.capability_bindings,
            source_outcomes=source_outcomes,
            graph_validation_attempts=final_stage_evidence.graph_validation_attempts,
            transaction_group_outcomes=transaction_group_outcomes, causal_blockers=causal_blockers,
            terminal_before_planning_proof_digests=final_stage_evidence.terminal_before_planning_proof_digests,
            manifest_group_inputs=final_compilation.manifest_group_inputs,
            ordered_group_commit_reload_digests=final_stage_evidence.ordered_group_commit_reload_digests,
        )
        if (
            request.request_digest != manifest_construction.request_digest
            or final_attempt.attempt_digest != manifest_construction.attempt_digest
            or final_plan.plan_digest != manifest_construction.transaction_group_plan_digest
            or complete_lineage.lineage_digest != manifest_construction.source_plan_lineage_digest
            or control_epoch.epoch_digest != manifest_construction.control_epoch_digest
            or current_generation.request_digest != request.request_digest
            or current_generation.control_epoch_digest != control_epoch.epoch_digest
            or final_attempt.request_digest != request.request_digest
            or final_attempt.transaction_group_plan_digest != final_plan.plan_digest
            or complete_lineage.request_digest != request.request_digest
            or final_stage_evidence.evidence_digest == ""
        ):
            raise ValueError("bootstrap graph terminal preparation closure is substituted")
        manifest = self.execution_manifest(construction=manifest_construction)
        self.validate_host_authority(
            request=request, complete_lineage=complete_lineage, manifest=manifest,
            host_authority=host_authority,
        )
        constructions = self._ordered_constructions(
            plan=final_plan, construction=manifest_construction,
            group_constructions=group_constructions,
            finalized_failure_group_id=finalized_failure_group_id,
        )
        status = (
            "failed"
            if finalized_failure_group_id is not None
            else self._source_status(constructions)
        )
        operation_ids = tuple(sorted({
            operation_id
            for member in final_plan.group_members
            for operation_id in member.operation_ids
        }))
        outcome_core = CanonicalSourceTerminalOutcomeCore.create(
            ingestion_record_kind="source_terminal_outcome",
            source_id=host_authority.source_id,
            source_digest=host_authority.source_digest,
            delivery_principal_binding_digest=host_authority.delivery_principal_binding_digest,
            delivery_key_digest=host_authority.delivery_key_digest,
            segment_governance_carriers=host_authority.segment_governance_carriers,
            message_admission_carriers=host_authority.message_admission_carriers,
            governance_carrier_artifact=host_authority.governance_carrier_artifact,
            required_outcome_scopes=host_authority.required_outcome_scopes,
            operation_fence_id=host_authority.operation_fence_binding.operation_fence_id,
            operation_ids=operation_ids,
            final_status=status,
            group_result_digests=tuple(
                item.result_digest for item in constructions
            ),
        )
        outcome_record = CanonicalSourceTerminalOutcomeRecord.create(
            core=outcome_core,
            preparation_fingerprint=host_authority.preparation_fingerprint,
        )
        canonical_input = BootstrapGraphCanonicalSourceResultInputV3.create(
            request_digest=request.request_digest,
            normalization_replay_digest=request.normalization_replay.replay_digest,
            source_plan_lineage_digest=complete_lineage.lineage_digest,
            ordered_group_result_constructions=constructions,
            ordered_group_commit_reload_digests=tuple(
                item.group_commit_reload.reload_digest for item in constructions
            ),
            source_status=status,
            canonical_outcome_core=outcome_core,
            completed_canonical_source_result=outcome_record,
            control_epoch_digest=control_epoch.epoch_digest,
        )
        canonical_result = BootstrapGraphCanonicalSourceResultV3.create(
            request_digest=request.request_digest,
            normalization_replay_digest=request.normalization_replay.replay_digest,
            source_plan_lineage_digest=complete_lineage.lineage_digest,
            ordered_group_result_digests=tuple(
                item.result_digest for item in constructions
            ),
            canonical_source_result=outcome_record,
            control_epoch_digest=control_epoch.epoch_digest,
        )
        handoff_core = BootstrapGraphTerminalHandoffCoreV3.create(
            request_digest=request.request_digest,
            normalization_replay_digest=request.normalization_replay.replay_digest,
            normalization_result_digest=final_attempt.normalization_result_digest,
            attempt_digest=final_attempt.attempt_digest,
            transaction_group_plan_digest=final_plan.plan_digest,
            source_plan_lineage_digest=complete_lineage.lineage_digest,
            execution_manifest_digest=manifest.manifest_digest,
            ordered_group_result_digests=tuple(item.result_digest for item in constructions),
            final_source_result_digest=canonical_result.result_digest,
            operation_lease_binding=control_epoch.operation_lease_binding,
            operation_fence_binding=control_epoch.operation_fence_binding,
            writer_commit_binding=control_epoch.writer_commit_binding,
            control_epoch_digest=control_epoch.epoch_digest,
        )
        intents = self._member_intents(
            request=request, control_epoch=control_epoch, attempt=final_attempt, plan=final_plan,
            lineage=complete_lineage, manifest=manifest, results=constructions,
            handoff_core=handoff_core, canonical_result=canonical_result,
        )
        publication_intent = BootstrapGraphTerminalPublicationIntentV3.create(
            source_id=host_authority.source_id, source_digest=host_authority.source_digest,
            preparation_fingerprint=host_authority.preparation_fingerprint,
            operation_id=control_epoch.operation_fence_binding.operation_id,
            request_digest=request.request_digest,
            normalization_replay_digest=request.normalization_replay.replay_digest,
            transaction_group_plan_digest=final_plan.plan_digest,
            source_plan_lineage_digest=complete_lineage.lineage_digest,
            control_epoch_digest=control_epoch.epoch_digest,
            delivery_principal_binding_digest=host_authority.delivery_principal_binding_digest,
            required_scope_set_digest=(
                host_authority.required_outcome_scopes.required_scope_set_digest
            ),
            operation_fence_binding_digest=control_epoch.operation_fence_binding.binding_digest,
            operation_lease_binding_digest=control_epoch.operation_lease_binding.binding_digest,
            writer_commit_binding_digest=control_epoch.writer_commit_binding.binding_digest,
            expected_operation_generation=current_generation.operation_generation,
            expected_artifact_generation=current_generation.artifact_generation,
            canonical_source_result_input_digest=canonical_input.input_digest,
            member_intents=intents,
        )
        handoff = BootstrapGraphTerminalPersistenceHandoffV3.create(
            core=handoff_core, publication_intent=publication_intent,
        )
        publication = BootstrapGraphArtifactAssemblerV3.build_terminal_publication_request(
            coordinator_request=request, control_epoch=control_epoch, final_attempt=final_attempt,
            final_plan=final_plan, complete_lineage=complete_lineage, execution_manifest=manifest,
            ordered_group_result_constructions=constructions,
            canonical_source_result_input=canonical_input, handoff_core=handoff_core,
            publication_intent=publication_intent, handoff=handoff,
            predecessor_generation=current_generation,
            delivery_principal_binding_digest=request.delivery_principal_binding_digest,
            required_outcome_scopes=request.required_outcome_scopes,
            operation_lease_binding=control_epoch.operation_lease_binding,
            operation_fence_binding=control_epoch.operation_fence_binding,
            writer_commit_binding=control_epoch.writer_commit_binding,
        )
        return BootstrapGraphTerminalPreparationV3.create(
            request_digest=request.request_digest, control_epoch_digest=control_epoch.epoch_digest,
            host_authority_digest=host_authority.authority_digest,
            predecessor_generation_digest=current_generation.snapshot_digest,
            publication_request=publication,
        )

    @staticmethod
    def _ordered_constructions(
        *, plan: BootstrapTransactionGroupPlanV3,
        construction: BootstrapGraphExecutionManifestConstructionV3,
        group_constructions: tuple[BootstrapNativeGroupCommitTerminalConstructionV3, ...],
        finalized_failure_group_id: str | None = None,
    ) -> tuple[BootstrapNativeGroupCommitTerminalConstructionV3, ...]:
        result_group_ids = tuple(
            item.transaction_group_id for item in group_constructions
        )
        expected_group_ids = (
            plan.canonical_group_order
            if finalized_failure_group_id is None
            else plan.canonical_group_order[
                : plan.canonical_group_order.index(finalized_failure_group_id)
            ]
        )
        if (
            finalized_failure_group_id is not None
            and finalized_failure_group_id not in plan.canonical_group_order
        ) or (
            result_group_ids != expected_group_ids
            or tuple(item.group_commit_reload.reload_digest for item in group_constructions)
            != construction.ordered_group_commit_reload_digests
        ):
            raise ValueError("bootstrap graph terminal group construction is substituted")
        return group_constructions

    @staticmethod
    def _source_status(
        constructions: tuple[BootstrapNativeGroupCommitTerminalConstructionV3, ...],
    ) -> str:
        dispositions = tuple(item.disposition for item in constructions)
        observations = tuple(item.terminal_observation_status for item in constructions)
        if "failed" in dispositions:
            return "failed"
        if all(item == "committed" for item in dispositions):
            return "fully_committed"
        if "committed" in dispositions:
            return "partially_committed"
        if all(item == "rejected" for item in observations):
            return "rejected"
        if "unresolved" in observations:
            return "unresolved"
        return "evidence_only"

    @staticmethod
    def _member_intents(
        *, request: BootstrapGraphDependentCoordinatorRequestV3, control_epoch: object,
        attempt: BootstrapGraphDependentAttemptV3, plan: BootstrapTransactionGroupPlanV3,
        lineage: BootstrapSourcePlanLineageV3, manifest: IngestionExecutionManifest,
        results: tuple[BootstrapNativeGroupCommitTerminalConstructionV3, ...],
        handoff_core: BootstrapGraphTerminalHandoffCoreV3,
        canonical_result: BootstrapGraphCanonicalSourceResultV3,
    ) -> tuple[BootstrapGraphTerminalMemberIntentV3, ...]:
        rows = [
            ("bootstrap_graph_coordinator_request", "coordinator-request", request.request_digest),
            ("bootstrap_graph_control_epoch", "control-epoch", control_epoch.epoch_digest),
            ("bootstrap_graph_dependent_attempt", "attempt", attempt.attempt_digest),
            ("bootstrap_transaction_group_plan", "plan", plan.plan_digest),
            *(
                ("bootstrap_source_plan_lineage_entry", f"lineage:{entry.lineage_ordinal:08d}:{entry.transaction_group_id}", entry.entry_digest)
                for entry in lineage.entries
            ),
            ("ingestion_execution_manifest", "execution-manifest", manifest.manifest_digest),
            *( 
                ("transaction_group_result", f"result:{result.transaction_group_id}", result.result_digest)
                for result in results
            ),
            ("bootstrap_graph_terminal_handoff", "terminal-handoff", handoff_core.core_digest),
            ("bootstrap_graph_canonical_source_result", "canonical-source-result", canonical_result.result_digest),
        ]
        return tuple(
            BootstrapGraphTerminalMemberIntentV3.create(
                kind=kind, member_id=member_id, construction_input_digest=digest,
            )
            for kind, member_id, digest in rows
        )


__all__ = [
    "BootstrapGraphTerminalPreparationPortV3",
    "DeterministicBootstrapGraphTerminalPreparationV3",
    "build_bootstrap_graph_execution_stage_outcomes",
]
