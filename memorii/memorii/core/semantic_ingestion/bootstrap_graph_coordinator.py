"""Sequencing owner for the native bootstrap-V3 graph transaction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pydantic import TypeAdapter

from memorii.core.memory_evolution.atomic_store import (
    BootstrapGraphRelatedConflictError,
    PreplanningStoreError,
)
from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
from memorii.core.semantic_ingestion.bootstrap_graph_artifact_assembler import BootstrapGraphArtifactAssemblerV3
from memorii.core.semantic_ingestion.bootstrap_graph_repository import (
    AtomicStoreBootstrapGraphControlEpochRepositoryV3,
    AtomicStoreBootstrapGraphGroupCommitRepositoryV3,
    AtomicStoreBootstrapGraphPlanRepositoryV3,
    AtomicStoreBootstrapGraphTerminalPersistencePortV3,
)
from memorii.core.semantic_ingestion.bootstrap_graph_terminal_preparation import (
    BootstrapGraphTerminalPreparationPortV3,
    build_bootstrap_graph_execution_stage_outcomes,
)
from memorii.core.semantic_ingestion.contracts import (
    BootstrapGraphControlEpochAdvancedV3,
    BootstrapGraphControlEpochFoundV3,
    BootstrapGraphControlEpochTransitionRequestV3,
    BootstrapGraphControlEpochUnavailableV3,
    BootstrapGraphDependentCoordinatorRequestV3,
    BootstrapGraphDependentCoordinatorResultV3,
    BootstrapGraphDependentCoordinatorSucceededV3,
    BootstrapGraphDependentPreGraphNonCommitV3,
    BootstrapGraphDurableRetryProgressV3,
    BootstrapGraphFinalizedFailureV3,
    BootstrapGraphPlanAuthorizationSetV3,
    BootstrapGraphPlanCompilationV3,
    BootstrapGraphRelatedConflictRefreshRequiredV3,
    BootstrapGraphTerminalHostAuthorityV3,
    BootstrapGraphV3ProducerUnavailable,
    BootstrapNativeGroupCommitTerminalConstructionV3,
    contract_digest,
    decode_bootstrap_graph_atomic_member_payload_v3,
)


class BootstrapGraphPlanCompilerPortV3(Protocol):
    def compile(self, *, request: BootstrapGraphDependentCoordinatorRequestV3, control_epoch: object) -> BootstrapGraphPlanCompilationV3 | BootstrapGraphV3ProducerUnavailable: ...


class BootstrapGraphPlanningAuthorizerPortV3(Protocol):
    def authorize(self, *, request: BootstrapGraphDependentCoordinatorRequestV3, control_epoch: object, reloaded_plan: object) -> BootstrapGraphPlanAuthorizationSetV3 | BootstrapGraphV3ProducerUnavailable: ...


@dataclass(frozen=True)
class BootstrapGraphDependentCoordinatorV3:
    def __init__(self, *, epoch_repository: AtomicStoreBootstrapGraphControlEpochRepositoryV3,
                 plan_repository: AtomicStoreBootstrapGraphPlanRepositoryV3,
                 terminal_port: AtomicStoreBootstrapGraphTerminalPersistencePortV3,
                 compiler: BootstrapGraphPlanCompilerPortV3, authorizer: BootstrapGraphPlanningAuthorizerPortV3,
                 group_commit_repository: AtomicStoreBootstrapGraphGroupCommitRepositoryV3,
                 terminal_preparer: BootstrapGraphTerminalPreparationPortV3,
                 terminal_host_authority: BootstrapGraphTerminalHostAuthorityV3) -> None:
        object.__setattr__(self, "_epochs", epoch_repository)
        object.__setattr__(self, "_plans", plan_repository)
        object.__setattr__(self, "_terminal", terminal_port)
        object.__setattr__(self, "_compiler", compiler)
        object.__setattr__(self, "_authorizer", authorizer)
        object.__setattr__(self, "_group_commits", group_commit_repository)
        object.__setattr__(self, "_preparer", terminal_preparer)
        object.__setattr__(self, "_host", terminal_host_authority)

    def coordinate(self, *, request: BootstrapGraphDependentCoordinatorRequestV3,
                   transition: BootstrapGraphControlEpochTransitionRequestV3 | None) -> BootstrapGraphDependentCoordinatorResultV3:
        if transition is not None and transition.request_core_digest != request.request_core_digest:
            return self._unavailable(request, "authority_unavailable")
        terminal = self._terminal.reload_by_request(request=request)
        if terminal is not None:
            if terminal.canonical_source_result.canonical_source_result.final_status == "failed":
                return BootstrapGraphFinalizedFailureV3.create(
                    kind="finalized_failure",
                    terminal_reload=terminal,
                    control_epoch_digest=terminal.control_epoch_digest,
                    reason="related_conflict_exhausted",
                )
            return BootstrapGraphDependentCoordinatorSucceededV3.create(
                kind="succeeded",
                terminal_reload=terminal,
                control_epoch_digest=terminal.control_epoch_digest,
            )
        if transition is None:
            epoch = request.initial_control_epoch
            if (
                epoch.request_core_digest != request.request_core_digest
                or epoch.operation_fence_binding != request.initial_control_epoch.operation_fence_binding
                or epoch.writer_commit_binding != request.initial_control_epoch.writer_commit_binding
                or epoch.delivery_principal_binding_digest != request.initial_control_epoch.delivery_principal_binding_digest
                or epoch.required_scope_set_digest != request.initial_control_epoch.required_scope_set_digest
            ):
                return self._unavailable(request, "authority_unavailable")
            refreshed = self._epochs.refresh_current(
                request=request, current_epoch=epoch
            )
            if isinstance(refreshed, BootstrapGraphControlEpochUnavailableV3):
                return self._unavailable(request, "authority_unavailable")
            epoch = refreshed.epoch
        else:
            found = self._epochs.transition_or_find(request=transition)
            if not isinstance(found, (BootstrapGraphControlEpochFoundV3, BootstrapGraphControlEpochAdvancedV3)):
                return self._unavailable(request, "authority_unavailable")
            epoch = found.epoch
        if (
            epoch.request_core_digest != request.request_core_digest
            or epoch.operation_fence_binding
            != request.initial_control_epoch.operation_fence_binding
            or epoch.writer_commit_binding
            != request.initial_control_epoch.writer_commit_binding
            or epoch.delivery_principal_binding_digest
            != request.initial_control_epoch.delivery_principal_binding_digest
            or epoch.required_scope_set_digest
            != request.initial_control_epoch.required_scope_set_digest
        ):
            return self._unavailable(request, "authority_unavailable")
        if transition is not None:
            refreshed = self._epochs.refresh_current(
                request=request, current_epoch=epoch
            )
            if isinstance(refreshed, BootstrapGraphControlEpochUnavailableV3):
                return self._unavailable(request, "authority_unavailable")
            epoch = refreshed.epoch
        retry_reload = self._plans.reload_retry_by_request(
            request=request,
            delivery_principal_binding_digest=request.delivery_principal_binding_digest,
            required_outcome_scopes=request.required_outcome_scopes,
            control_epoch=epoch,
        )
        if retry_reload is not None:
            progress_member = next(
                (
                    member
                    for member in retry_reload.core.members
                    if member.kind == "bootstrap_graph_retry_progress"
                ),
                None,
            )
            if progress_member is None:
                raise ValueError("bootstrap graph retry progress is absent")
            return BootstrapGraphDurableRetryProgressV3.model_validate(
                decode_bootstrap_graph_atomic_member_payload_v3(
                    kind=progress_member.kind,
                    raw=progress_member.canonical_payload,
                ),
                strict=False,
            )
        try:
            checkpoint = self._plans.reload_checkpoint_for_resume(
                operation_fence_binding=epoch.operation_fence_binding,
                delivery_principal_binding_digest=request.delivery_principal_binding_digest,
                required_outcome_scopes=request.required_outcome_scopes,
                control_epoch=epoch,
                operation_lease_binding=epoch.operation_lease_binding,
                writer_commit_binding=epoch.writer_commit_binding,
            )
        except PreplanningStoreError:
            checkpoint = None
        if checkpoint is not None:
            from memorii.core.semantic_ingestion.contracts import (
                BootstrapGraphAttemptAuthorityV3,
                BootstrapGraphAttemptConstructionInputsV3,
                BootstrapGraphDependentAttemptV3,
                BootstrapGraphPlanCompilationV3,
                BootstrapGroupPlanningAuthorizationV3,
                BootstrapInitialAttemptAuthorityV3,
                BootstrapSourcePlanLineageV3,
                BootstrapTransactionGroupPlanV3,
            )

            by_id = {member.member_id: member for member in checkpoint.request.members}
            try:
                compilation = BootstrapGraphPlanCompilationV3.model_validate(
                    decode_bootstrap_graph_atomic_member_payload_v3(
                        kind=by_id["compilation"].kind,
                        raw=by_id["compilation"].canonical_payload,
                    ), strict=False
                )
                inputs = BootstrapGraphAttemptConstructionInputsV3.model_validate(
                    decode_bootstrap_graph_atomic_member_payload_v3(
                        kind=by_id["attempt-inputs"].kind,
                        raw=by_id["attempt-inputs"].canonical_payload,
                    ), strict=False
                )
                plan = BootstrapTransactionGroupPlanV3.model_validate(
                    decode_bootstrap_graph_atomic_member_payload_v3(
                        kind=by_id["plan"].kind,
                        raw=by_id["plan"].canonical_payload,
                    ), strict=False
                )
            except (KeyError, TypeError, ValueError):
                return self._unavailable(request, "authority_unavailable")
            if (
                compilation.attempt_construction_inputs != inputs
                or compilation.plan != plan
                or compilation.request_digest != request.request_digest
                or compilation.control_epoch_digest != epoch.epoch_digest
                or inputs.request_digest != request.request_digest
                or inputs.control_epoch_digest != epoch.epoch_digest
                or plan.operation_lease_binding_digest
                != epoch.operation_lease_binding.binding_digest
                or plan.operation_fence_binding_digest
                != epoch.operation_fence_binding.binding_digest
                or plan.writer_commit_binding_digest
                != epoch.writer_commit_binding.binding_digest
            ):
                return self._unavailable(request, "authority_unavailable")
            current_generation = self._plans.load_current_generation(
                request=request,
                control_epoch=epoch,
                delivery_principal_binding_digest=request.delivery_principal_binding_digest,
                required_outcome_scopes=request.required_outcome_scopes,
            )
            progress_kind = checkpoint.progress.artifact.kind
            if progress_kind == "plan_published":
                # The retained plan is the sole authorization input.  A recovery
                # never re-enters compilation or reconstructs a plan.
                if current_generation.operation_generation != checkpoint.progress.generation:
                    return self._unavailable(request, "authority_unavailable")
                try:
                    plan_reload = self._plans.reload(
                        request=checkpoint.request,
                        delivery_principal_binding_digest=request.delivery_principal_binding_digest,
                        required_outcome_scopes=request.required_outcome_scopes,
                        control_epoch=epoch,
                    )
                    authorizations = self._authorizer.authorize(
                        request=request, control_epoch=epoch, reloaded_plan=plan_reload
                    )
                except (PreplanningStoreError, ValueError):
                    return self._unavailable(request, "authority_unavailable")
                if isinstance(authorizations, BootstrapGraphV3ProducerUnavailable):
                    return self._unavailable(request, "authorization_unavailable")
                try:
                    authority = BootstrapGraphArtifactAssemblerV3.initial_attempt_authority(
                        authorizations=authorizations, plan=plan,
                        request_digest=request.request_digest, control_epoch_digest=epoch.epoch_digest,
                    )
                    counters = BootstrapGraphArtifactAssemblerV3._observed_counters(
                        inputs=inputs, operation_fence_binding=epoch.operation_fence_binding,
                        publication_generation=current_generation.operation_generation + 1,
                        plan=plan, attempts=1,
                        reservations=len(authorizations.authorizations), lineage_entries=0,
                    )
                    attempt = BootstrapGraphArtifactAssemblerV3.build_initial_attempt(
                        inputs=inputs, authority=authority, plan=plan,
                        source_dependency_group_digests=tuple(
                            item.group_id for item in request.source_dependency_groups
                        ),
                        capability_binding_digests=tuple(
                            item.binding_digest for item in self._host.capability_bindings
                        ),
                        reservation_use_authorization_digests=tuple(sorted({
                            item.reservation_use_authority.authority_digest
                            for item in authorizations.authorizations
                        })),
                        operation_lease_binding_digest=epoch.operation_lease_binding.binding_digest,
                        operation_fence_binding_digest=epoch.operation_fence_binding.binding_digest,
                        writer_commit_binding_digest=epoch.writer_commit_binding.binding_digest,
                        observed_counters_digest=counters.counters_digest,
                    )
                    attempt_reload = self._plans.publish_and_reload(
                        request=BootstrapGraphArtifactAssemblerV3.build_attempt_checkpoint(
                            attempt=attempt, inputs=inputs, compilation=compilation,
                            authority=authority, plan=plan, authorizations=authorizations,
                            operation_lease_binding=epoch.operation_lease_binding,
                            operation_fence_binding=epoch.operation_fence_binding,
                            writer_commit_binding=epoch.writer_commit_binding,
                            predecessor_generation=current_generation,
                            preparation_fingerprint=epoch.preparation_fingerprint,
                        ),
                        delivery_principal_binding_digest=request.delivery_principal_binding_digest,
                        required_outcome_scopes=request.required_outcome_scopes,
                        control_epoch=epoch,
                    )
                    lineage = BootstrapGraphArtifactAssemblerV3.build_initial_lineage(
                        attempt=attempt, plan=plan, authorizations=authorizations,
                        source_id=epoch.source_id, source_digest=epoch.source_digest,
                        preparation_fingerprint=epoch.preparation_fingerprint,
                    )
                    lineage_reload = self._plans.publish_and_reload(
                        request=BootstrapGraphArtifactAssemblerV3.build_authorized_lineage_checkpoint(
                            attempt=attempt, authorizations=authorizations,
                            lineage=lineage.entries, plan=plan, compilation=compilation,
                            inputs=inputs, preparation_fingerprint=epoch.preparation_fingerprint,
                            pre_execution_identity_closure=BootstrapGraphArtifactAssemblerV3.build_pre_execution_identity_closure(compilation=compilation, attempt=attempt, plan=plan, lineage=lineage, host_authority=self._host),
                            operation_lease_binding=epoch.operation_lease_binding,
                            operation_fence_binding=epoch.operation_fence_binding,
                            writer_commit_binding=epoch.writer_commit_binding,
                            predecessor_generation=attempt_reload.checkpoint_receipt.successor_generation,
                        ),
                        delivery_principal_binding_digest=request.delivery_principal_binding_digest,
                        required_outcome_scopes=request.required_outcome_scopes,
                        control_epoch=epoch,
                    )
                except (PreplanningStoreError, ValueError):
                    return self._unavailable(request, "authority_unavailable")
                return self._execute_attempt(
                    request=request, epoch=epoch, compilation=compilation,
                    authorizations=authorizations, attempt=attempt, lineage=lineage,
                    current_generation=lineage_reload.checkpoint_receipt.successor_generation,
                )
            try:
                authority = TypeAdapter(BootstrapGraphAttemptAuthorityV3).validate_python(
                    decode_bootstrap_graph_atomic_member_payload_v3(
                        kind=by_id["successor-authority"].kind,
                        raw=by_id["successor-authority"].canonical_payload,
                    ), strict=False
                )
                attempt = BootstrapGraphDependentAttemptV3.model_validate(
                    decode_bootstrap_graph_atomic_member_payload_v3(
                        kind=by_id["attempt"].kind,
                        raw=by_id["attempt"].canonical_payload,
                    ), strict=False
                )
                authorizations = BootstrapGraphPlanAuthorizationSetV3.create(
                    request_digest=attempt.request_digest,
                    plan_digest=plan.plan_digest,
                    control_epoch_digest=attempt.control_epoch_digest,
                    authorizations=tuple(
                        BootstrapGroupPlanningAuthorizationV3.model_validate(
                            decode_bootstrap_graph_atomic_member_payload_v3(
                                kind=member.kind, raw=member.canonical_payload,
                            ), strict=False
                        )
                        for member in checkpoint.request.members
                        if member.member_id.startswith("authorization:")
                    ),
                )
            except (KeyError, TypeError, ValueError):
                return self._unavailable(request, "authority_unavailable")
            if (
                attempt.attempt_authority != authority
                or attempt.request_digest != request.request_digest
                or attempt.control_epoch_digest != epoch.epoch_digest
            ):
                return self._unavailable(request, "authority_unavailable")
            if progress_kind == "attempt_published":
                if current_generation.operation_generation != checkpoint.progress.generation:
                    return self._unavailable(request, "authority_unavailable")
                try:
                    if isinstance(authority, BootstrapInitialAttemptAuthorityV3):
                        lineage = BootstrapGraphArtifactAssemblerV3.build_initial_lineage(
                            attempt=attempt, plan=plan, authorizations=authorizations,
                            source_id=epoch.source_id, source_digest=epoch.source_digest,
                            preparation_fingerprint=epoch.preparation_fingerprint,
                        )
                    else:
                        sealed = self._plans.reload_resume_closure_for_original_fence(
                            operation_fence_binding=epoch.operation_fence_binding,
                            delivery_principal_binding_digest=request.delivery_principal_binding_digest,
                            required_outcome_scopes=request.required_outcome_scopes,
                            control_epoch=epoch,
                            operation_lease_binding=epoch.operation_lease_binding,
                            writer_commit_binding=epoch.writer_commit_binding,
                        )
                        lineage = BootstrapGraphArtifactAssemblerV3.append_successor_lineage(
                            predecessor=sealed.lineage.artifact, attempt=attempt,
                            plan=plan, authorizations=authorizations,
                        )
                    lineage_reload = self._plans.publish_and_reload(
                        request=BootstrapGraphArtifactAssemblerV3.build_authorized_lineage_checkpoint(
                            attempt=attempt, authorizations=authorizations,
                            lineage=lineage.entries, plan=plan, compilation=compilation,
                            inputs=inputs, preparation_fingerprint=epoch.preparation_fingerprint,
                            pre_execution_identity_closure=BootstrapGraphArtifactAssemblerV3.build_pre_execution_identity_closure(compilation=compilation, attempt=attempt, plan=plan, lineage=lineage, host_authority=self._host),
                            operation_lease_binding=epoch.operation_lease_binding,
                            operation_fence_binding=epoch.operation_fence_binding,
                            writer_commit_binding=epoch.writer_commit_binding,
                            predecessor_generation=current_generation,
                        ),
                        delivery_principal_binding_digest=request.delivery_principal_binding_digest,
                        required_outcome_scopes=request.required_outcome_scopes,
                        control_epoch=epoch,
                    )
                except (PreplanningStoreError, ValueError):
                    return self._unavailable(request, "authority_unavailable")
                return self._execute_attempt(
                    request=request, epoch=epoch, compilation=compilation,
                    authorizations=authorizations, attempt=attempt, lineage=lineage,
                    current_generation=lineage_reload.checkpoint_receipt.successor_generation,
                )
            if progress_kind == "planned":
                try:
                    lineage = BootstrapSourcePlanLineageV3.model_validate(
                        decode_bootstrap_graph_atomic_member_payload_v3(
                            kind=by_id["lineage"].kind,
                            raw=by_id["lineage"].canonical_payload,
                        ), strict=False
                    )
                except (KeyError, TypeError, ValueError):
                    return self._unavailable(request, "authority_unavailable")
                return self._execute_attempt(
                    request=request, epoch=epoch, compilation=compilation,
                    authorizations=authorizations, attempt=attempt, lineage=lineage,
                    current_generation=current_generation,
                    preserved_constructions=tuple(
                        item.artifact for item in checkpoint.completed_group_results
                    ),
                )
            return self._unavailable(request, "authority_unavailable")
        generation = self._plans.load_current_generation(request=request, control_epoch=epoch, delivery_principal_binding_digest=request.delivery_principal_binding_digest, required_outcome_scopes=request.required_outcome_scopes)
        compilation = self._compiler.compile(request=request, control_epoch=epoch)
        if isinstance(compilation, BootstrapGraphV3ProducerUnavailable):
            return self._unavailable(request, "planning_unavailable")
        bindings = epoch.operation_lease_binding, epoch.operation_fence_binding, epoch.writer_commit_binding
        plan_reload = self._plans.publish_and_reload(request=BootstrapGraphArtifactAssemblerV3.build_plan_checkpoint(compilation=compilation, operation_lease_binding=bindings[0], operation_fence_binding=bindings[1], writer_commit_binding=bindings[2], predecessor_generation=generation, preparation_fingerprint=epoch.preparation_fingerprint), delivery_principal_binding_digest=request.delivery_principal_binding_digest, required_outcome_scopes=request.required_outcome_scopes, control_epoch=epoch)
        authorizations = self._authorizer.authorize(request=request, control_epoch=epoch, reloaded_plan=plan_reload)
        if isinstance(authorizations, BootstrapGraphV3ProducerUnavailable):
            return self._unavailable(request, "authorization_unavailable")
        authority = BootstrapGraphArtifactAssemblerV3.initial_attempt_authority(authorizations=authorizations, plan=compilation.plan, request_digest=request.request_digest, control_epoch_digest=epoch.epoch_digest)
        attempt_counters = BootstrapGraphArtifactAssemblerV3._observed_counters(inputs=compilation.attempt_construction_inputs, operation_fence_binding=bindings[1], publication_generation=plan_reload.checkpoint_receipt.successor_generation.operation_generation + 1, plan=compilation.plan, attempts=1, reservations=len(authorizations.authorizations), lineage_entries=0)
        attempt = BootstrapGraphArtifactAssemblerV3.build_initial_attempt(inputs=compilation.attempt_construction_inputs, authority=authority, plan=compilation.plan, source_dependency_group_digests=tuple(item.group_id for item in request.source_dependency_groups), capability_binding_digests=tuple(item.binding_digest for item in self._host.capability_bindings), reservation_use_authorization_digests=tuple(sorted({item.reservation_use_authority.authority_digest for item in authorizations.authorizations})), operation_lease_binding_digest=bindings[0].binding_digest, operation_fence_binding_digest=bindings[1].binding_digest, writer_commit_binding_digest=bindings[2].binding_digest, observed_counters_digest=attempt_counters.counters_digest)
        attempt_reload = self._plans.publish_and_reload(request=BootstrapGraphArtifactAssemblerV3.build_attempt_checkpoint(attempt=attempt, inputs=compilation.attempt_construction_inputs, compilation=compilation, authority=authority, plan=compilation.plan, authorizations=authorizations, operation_lease_binding=bindings[0], operation_fence_binding=bindings[1], writer_commit_binding=bindings[2], predecessor_generation=plan_reload.checkpoint_receipt.successor_generation, preparation_fingerprint=epoch.preparation_fingerprint), delivery_principal_binding_digest=request.delivery_principal_binding_digest, required_outcome_scopes=request.required_outcome_scopes, control_epoch=epoch)
        lineage = BootstrapGraphArtifactAssemblerV3.build_initial_lineage(attempt=attempt, plan=compilation.plan, authorizations=authorizations, source_id=epoch.source_id, source_digest=epoch.source_digest, preparation_fingerprint=epoch.preparation_fingerprint)
        lineage_reload = self._plans.publish_and_reload(request=BootstrapGraphArtifactAssemblerV3.build_authorized_lineage_checkpoint(attempt=attempt, authorizations=authorizations, lineage=lineage.entries, plan=compilation.plan, compilation=compilation, inputs=compilation.attempt_construction_inputs, preparation_fingerprint=epoch.preparation_fingerprint, pre_execution_identity_closure=BootstrapGraphArtifactAssemblerV3.build_pre_execution_identity_closure(compilation=compilation, attempt=attempt, plan=compilation.plan, lineage=lineage, host_authority=self._host), operation_lease_binding=bindings[0], operation_fence_binding=bindings[1], writer_commit_binding=bindings[2], predecessor_generation=attempt_reload.checkpoint_receipt.successor_generation), delivery_principal_binding_digest=request.delivery_principal_binding_digest, required_outcome_scopes=request.required_outcome_scopes, control_epoch=epoch)
        return self._execute_attempt(
            request=request,
            epoch=epoch,
            compilation=compilation,
            authorizations=authorizations,
            attempt=attempt,
            lineage=lineage,
            current_generation=lineage_reload.checkpoint_receipt.successor_generation,
        )

    def coordinate_related_conflict(
        self,
        *,
        request: BootstrapGraphDependentCoordinatorRequestV3,
        conflict: BootstrapGraphRelatedConflictRefreshRequiredV3,
    ) -> BootstrapGraphDependentCoordinatorResultV3:
        """Resume a stale group CAS under freshly acquired host authority."""
        if (
            conflict.operation_fence_binding_digest
            != request.initial_control_epoch.operation_fence_binding.binding_digest
        ):
            return self._unavailable(request, "authority_unavailable")
        refreshed = self._epochs.refresh_current(
            request=request, current_epoch=request.initial_control_epoch
        )
        if isinstance(refreshed, BootstrapGraphControlEpochUnavailableV3):
            return self._unavailable(request, "authority_unavailable")
        epoch = refreshed.epoch
        try:
            sealed = self._plans.reload_resume_closure_for_original_fence(
                operation_fence_binding=epoch.operation_fence_binding,
                delivery_principal_binding_digest=request.delivery_principal_binding_digest,
                required_outcome_scopes=request.required_outcome_scopes,
                control_epoch=epoch,
                operation_lease_binding=epoch.operation_lease_binding,
                writer_commit_binding=epoch.writer_commit_binding,
            )
            predecessor_authorizations = BootstrapGraphPlanAuthorizationSetV3.create(
                request_digest=sealed.attempt.artifact.request_digest,
                plan_digest=sealed.plan.artifact.plan_digest,
                control_epoch_digest=sealed.attempt.artifact.control_epoch_digest,
                authorizations=tuple(item.artifact for item in sealed.authorizations),
            )
            current_generation = self._plans.load_current_generation(
                request=request,
                control_epoch=epoch,
                delivery_principal_binding_digest=request.delivery_principal_binding_digest,
                required_outcome_scopes=request.required_outcome_scopes,
            )
        except (PreplanningStoreError, TypeError, ValueError, AttributeError):
            return self._unavailable(request, "authority_unavailable")
        return self._related_conflict_successor(
            request=request,
            epoch=epoch,
            predecessor_attempt=sealed.attempt.artifact,
            predecessor_lineage=sealed.lineage.artifact,
            predecessor_plan=sealed.plan.artifact,
            predecessor_authorizations=predecessor_authorizations,
            predecessor_pre_execution=sealed.pre_execution_identity_closure.artifact,
            completed_group_results=tuple(
                item.artifact for item in sealed.canonical_final_group_results
            ),
            current_generation=current_generation,
            conflicted_group_id=conflict.transaction_group_id,
            sealed_resume=sealed,
        )

    def _execute_attempt(
        self, *, request: object, epoch: object, compilation: object,
        authorizations: object, attempt: object, lineage: object,
        current_generation: object, preserved_constructions: tuple[object, ...] = (),
        preserved_pre_execution: object | None = None,
    ) -> BootstrapGraphDependentCoordinatorResultV3:
        bindings = (
            epoch.operation_lease_binding,
            epoch.operation_fence_binding,
            epoch.writer_commit_binding,
        )
        preserved_group_ids = {
            item.transaction_group_id for item in preserved_constructions
        }
        reused_group_ids = {
            item.transaction_group_id
            for item in getattr(
                attempt.attempt_authority, "group_member_authorities", ()
            )
            if item.kind != "replacement"
        }
        # Every reused arm retains its predecessor identity byte-for-byte.
        # Final arms are skipped below, while an unfinished reused arm may be
        # executed under that retained authority.
        identity_reuse_group_ids = reused_group_ids
        preserved_identities = None
        if identity_reuse_group_ids:
            if preserved_pre_execution is None:
                raise ValueError("bootstrap graph preserved pre-execution closure is absent")
            preserved_identities = {
                item.core.transaction_group_id: item
                for item in preserved_pre_execution.identities
                if item.core.transaction_group_id in identity_reuse_group_ids
            }
            if set(preserved_identities) != identity_reuse_group_ids:
                raise ValueError("bootstrap graph preserved pre-execution closure is incomplete")
        pre_execution = BootstrapGraphArtifactAssemblerV3.build_pre_execution_identity_closure(
            compilation=compilation,
            attempt=attempt,
            plan=compilation.plan,
            lineage=lineage,
            host_authority=self._host,
            preserved_identities=preserved_identities,
        )
        latest = dict(lineage.latest_entry_by_group)
        entries = {entry.entry_digest: entry for entry in lineage.entries}
        by_group = {group_id: entries[digest] for group_id, digest in latest.items()}
        by_auth = {
            item.transaction_group_id: item for item in authorizations.authorizations
        }
        identity_by_group = {
            item.core.transaction_group_id: item for item in pre_execution.identities
        }
        constructions: list[BootstrapNativeGroupCommitTerminalConstructionV3] = list(
            preserved_constructions
        )
        for member in compilation.plan.group_members:
            if member.transaction_group_id in preserved_group_ids:
                continue
            group_commit_request = BootstrapGraphArtifactAssemblerV3.group_commit_request(
                request=request, attempt=attempt, member=member,
                authorization=by_auth[member.transaction_group_id],
                lineage=by_group[member.transaction_group_id],
                pre_execution_manifest_identity=identity_by_group[member.transaction_group_id],
                control_epoch=epoch, current_generation=current_generation,
                operation_reductions=compilation.operation_reductions,
            )
            try:
                group_commit_reload = self._group_commits.commit_or_reload(
                    request=group_commit_request,
                )
            except BootstrapGraphRelatedConflictError as exc:
                return BootstrapGraphRelatedConflictRefreshRequiredV3.create(
                    kind="related_conflict_refresh_required",
                    request_digest=request.request_digest,
                    transaction_group_id=exc.transaction_group_id,
                    expected_graph_revision=exc.expected_graph_revision,
                    observed_graph_revision=exc.observed_graph_revision,
                    operation_fence_binding_digest=epoch.operation_fence_binding.binding_digest,
                )
            except (PreplanningStoreError, ValueError):
                reason = "storage_retry"
                return self._post_effect_retry(
                    request=request, epoch=epoch, attempt=attempt,
                    plan=compilation.plan, authorizations=authorizations, lineage=lineage,
                    constructions=constructions, groups=compilation.plan.canonical_group_order,
                    generation=current_generation, reason=reason,
                )
            construction = BootstrapGraphArtifactAssemblerV3.group_construction(
                request_digest=request.request_digest,
                normalization_replay_digest=request.normalization_replay.replay_digest,
                attempt=attempt,
                lineage=by_group[member.transaction_group_id],
                member=member,
                authorization=by_auth[member.transaction_group_id],
                group_commit_request=group_commit_request,
                group_commit_reload=group_commit_reload,
                operation_fence_binding=epoch.operation_fence_binding,
                control_epoch=epoch,
            )
            group_checkpoint_request = (
                BootstrapGraphArtifactAssemblerV3.build_group_result_checkpoint(
                    construction=construction,
                    attempt=attempt,
                    operation_lease_binding=bindings[0],
                    operation_fence_binding=bindings[1],
                    writer_commit_binding=bindings[2],
                    predecessor_generation=group_commit_reload.successor_generation,
                )
            )
            try:
                group_reload = self._plans.publish_and_reload(
                    request=group_checkpoint_request,
                    delivery_principal_binding_digest=request.delivery_principal_binding_digest,
                    required_outcome_scopes=request.required_outcome_scopes,
                    control_epoch=epoch,
                )
            except (PreplanningStoreError, ValueError):
                # The executor has already linearized the group CAS.  A
                # checkpoint acknowledgement failure publishes the durable
                # post-effect retry instead of re-issuing the same request
                # in-process: recovery reloads the retained construction
                # and cannot repeat an effect.
                constructions.append(construction)
                return self._post_effect_retry(
                    request=request,
                    epoch=epoch,
                    attempt=attempt,
                    plan=compilation.plan,
                    authorizations=authorizations,
                    lineage=lineage,
                    constructions=constructions,
                    groups=compilation.plan.canonical_group_order,
                    generation=group_commit_reload.successor_generation,
                )
            current_generation = group_reload.checkpoint_receipt.successor_generation
            constructions.append(construction)
        return self._finalize_attempt(
            request=request,
            epoch=epoch,
            compilation=compilation,
            authorizations=authorizations,
            attempt=attempt,
            lineage=lineage,
            pre_execution=pre_execution,
            constructions=tuple(constructions),
            current_generation=current_generation,
        )

    def _related_conflict_successor(
        self, *, request: object, epoch: object, predecessor_attempt: object,
        predecessor_lineage: object, predecessor_plan: object,
        predecessor_authorizations: object, predecessor_pre_execution: object,
        completed_group_results: tuple[object, ...], current_generation: object,
        conflicted_group_id: str,
        predecessor_progress_reference: object | None = None,
        replan_closure_reference: object | None = None,
        predecessor_observed_counters: object | None = None,
        sealed_resume: object | None = None,
    ) -> BootstrapGraphDependentCoordinatorResultV3:
        # A conflict reached from the normal group executor appends a persisted
        # bridge closure before its V3 successor is published.
        if replan_closure_reference is None:
            if sealed_resume is None:
                try:
                    sealed = self._plans.reload_resume_closure_for_original_fence(
                        operation_fence_binding=epoch.operation_fence_binding,
                        delivery_principal_binding_digest=request.delivery_principal_binding_digest,
                        required_outcome_scopes=request.required_outcome_scopes,
                        control_epoch=epoch,
                        operation_lease_binding=epoch.operation_lease_binding,
                        writer_commit_binding=epoch.writer_commit_binding,
                    )
                except (PreplanningStoreError, ValueError):
                    return self._unavailable(request, "authority_unavailable")
            else:
                sealed = sealed_resume
            if (
                sealed.attempt.artifact != predecessor_attempt
                or sealed.plan.artifact != predecessor_plan
                or sealed.lineage.artifact != predecessor_lineage
            ):
                return self._unavailable(request, "authority_unavailable")
            sealed_final_ids = {
                item.artifact.transaction_group_id
                for item in sealed.canonical_final_group_results
            }
            unfinished = tuple(
                group_id for group_id in predecessor_plan.canonical_group_order
                if group_id not in sealed_final_ids
            )
            if conflicted_group_id not in unfinished:
                return self._unavailable(request, "authority_unavailable")
            # Replan only the stale group and unfinished groups whose plans
            # actually depend on it.  Canonical order is not dependency
            # authority: replacing the entire later tuple would erase the
            # required reused-unfinished partition for independent groups.
            member_by_group = {
                item.transaction_group_id: item
                for item in predecessor_plan.group_members
            }
            affected = {conflicted_group_id}
            changed = True
            while changed:
                changed = False
                for group_id in unfinished:
                    if group_id in affected:
                        continue
                    dependencies = {
                        dependency_group_id
                        for operation in member_by_group[group_id].operation_plans
                        for dependency_group_id in operation.dependency_group_ids
                        if dependency_group_id != group_id
                    }
                    if dependencies & affected:
                        affected.add(group_id)
                        changed = True
            replanned_group_ids = tuple(
                group_id
                for group_id in predecessor_plan.canonical_group_order
                if group_id in affected
            )
            replan_closure_reference = (
                BootstrapGraphArtifactAssemblerV3.build_replan_closure_reference(
                    predecessor_progress_member=sealed.progress.member,
                    predecessor_progress=sealed.progress.artifact,
                    predecessor_lineage_member=sealed.lineage.member,
                    predecessor_lineage=sealed.lineage.artifact,
                    predecessor_generation=sealed.progress.generation,
                    final_result_members=tuple(
                        (item.generation, item.member, item.artifact)
                        for item in sealed.canonical_final_group_results
                    ),
                    unfinished_transaction_group_ids=unfinished,
                    replanned_transaction_group_ids=replanned_group_ids,
                )
            )
            predecessor_progress_reference = (
                replan_closure_reference.predecessor_planned_progress_reference
            )
            predecessor_observed_counters = sealed.observed_counters.artifact
        if (
            replan_closure_reference is not None
            and conflicted_group_id
            not in replan_closure_reference.replanned_transaction_group_ids
        ):
            return self._unavailable(request, "authority_unavailable")
        compilation = self._compiler.compile(request=request, control_epoch=epoch)
        if isinstance(compilation, BootstrapGraphV3ProducerUnavailable):
            return self._retry(
                request, epoch, predecessor_attempt, predecessor_plan,
                predecessor_authorizations, predecessor_lineage, [],
                tuple(item.group_id for item in request.source_dependency_groups),
                compilation, current_generation,
                reason="related_conflict",
            )
        compilation = BootstrapGraphArtifactAssemblerV3.successor_compilation(
            replacement=compilation,
            predecessor=sealed.compilation.artifact,
            replanned_group_ids=tuple(
                replan_closure_reference.replanned_transaction_group_ids
            ),
        )
        bindings = (
            epoch.operation_lease_binding,
            epoch.operation_fence_binding,
            epoch.writer_commit_binding,
        )
        successor_plan_counters = BootstrapGraphArtifactAssemblerV3._observed_counters(
            inputs=compilation.attempt_construction_inputs,
            operation_fence_binding=bindings[1],
            publication_generation=current_generation.operation_generation + 1,
            plan=compilation.plan,
            attempts=0,
            reservations=0,
            lineage_entries=0,
            predecessor=predecessor_observed_counters,
            related_conflict=True,
        )
        plan_reload = self._plans.publish_and_reload(
            request=BootstrapGraphArtifactAssemblerV3.build_plan_checkpoint(
                compilation=compilation,
                operation_lease_binding=bindings[0],
                operation_fence_binding=bindings[1],
                writer_commit_binding=bindings[2],
                predecessor_generation=current_generation,
                preparation_fingerprint=epoch.preparation_fingerprint,
                predecessor_progress_reference=predecessor_progress_reference,
                replan_closure_reference=replan_closure_reference,
                predecessor_observed_counters=predecessor_observed_counters,
            ),
            delivery_principal_binding_digest=request.delivery_principal_binding_digest,
            required_outcome_scopes=request.required_outcome_scopes,
            control_epoch=epoch,
        )
        authorizations = self._authorizer.authorize(
            request=request, control_epoch=epoch, reloaded_plan=plan_reload
        )
        if isinstance(authorizations, BootstrapGraphV3ProducerUnavailable):
            return self._retry(
                request, epoch, predecessor_attempt, predecessor_plan,
                predecessor_authorizations, predecessor_lineage, [],
                tuple(item.group_id for item in request.source_dependency_groups),
                authorizations,
                plan_reload.checkpoint_receipt.successor_generation,
                reason="related_conflict",
            )
        authority = BootstrapGraphArtifactAssemblerV3.replacement_successor_authority(
            predecessor_attempt=predecessor_attempt,
            predecessor_lineage=predecessor_lineage,
            predecessor_plan=predecessor_plan,
            predecessor_authorizations=predecessor_authorizations,
            replacement_plan=compilation.plan,
            replacement_authorizations=authorizations,
            completed_group_results=completed_group_results,
            replanned_group_ids=tuple(
                replan_closure_reference.replanned_transaction_group_ids
            ),
        )
        predecessor_auth_by_group = {
            item.transaction_group_id: item
            for item in predecessor_authorizations.authorizations
        }
        replacement_auth_by_group = {
            item.transaction_group_id: item for item in authorizations.authorizations
        }
        successor_authority_by_group = {
            item.transaction_group_id: item
            for item in authority.group_member_authorities
        }
        effective_authorizations = tuple(
            predecessor_auth_by_group[group_id]
            if successor_authority_by_group[group_id].kind != "replacement"
            else replacement_auth_by_group[group_id]
            for group_id in compilation.plan.canonical_group_order
        )
        authorizations = BootstrapGraphPlanAuthorizationSetV3.create(
            request_digest=request.request_digest,
            plan_digest=compilation.plan.plan_digest,
            control_epoch_digest=epoch.epoch_digest,
            authorizations=effective_authorizations,
        )
        successor_attempt_counters = BootstrapGraphArtifactAssemblerV3._observed_counters(
            inputs=compilation.attempt_construction_inputs,
            operation_fence_binding=bindings[1],
            publication_generation=plan_reload.checkpoint_receipt.successor_generation.operation_generation + 1,
            plan=compilation.plan, attempts=predecessor_attempt.attempt_index + 2,
            reservations=len(authorizations.authorizations), lineage_entries=0,
            predecessor=successor_plan_counters,
        )
        attempt = BootstrapGraphArtifactAssemblerV3.build_successor_attempt(
            predecessor_attempt=predecessor_attempt,
            inputs=compilation.attempt_construction_inputs,
            authority=authority,
            plan=compilation.plan,
            capability_binding_digests=tuple(
                item.binding_digest for item in self._host.capability_bindings
            ),
            reservation_use_authorization_digests=tuple(sorted({
                item.reservation_use_authority.authority_digest
                for item in authorizations.authorizations
            })),
            operation_lease_binding_digest=bindings[0].binding_digest,
            operation_fence_binding_digest=bindings[1].binding_digest,
            writer_commit_binding_digest=bindings[2].binding_digest,
            observed_counters_digest=successor_attempt_counters.counters_digest,
        )
        attempt_reload = self._plans.publish_and_reload(
            request=BootstrapGraphArtifactAssemblerV3.build_attempt_checkpoint(
                attempt=attempt,
                inputs=compilation.attempt_construction_inputs,
                compilation=compilation,
                authority=authority,
                plan=compilation.plan,
                authorizations=authorizations,
                operation_lease_binding=bindings[0],
                operation_fence_binding=bindings[1],
                writer_commit_binding=bindings[2],
                predecessor_generation=plan_reload.checkpoint_receipt.successor_generation,
                preparation_fingerprint=epoch.preparation_fingerprint,
                predecessor_progress_reference=predecessor_progress_reference,
                replan_closure_reference=replan_closure_reference,
                predecessor_observed_counters=successor_plan_counters,
            ),
            delivery_principal_binding_digest=request.delivery_principal_binding_digest,
            required_outcome_scopes=request.required_outcome_scopes,
            control_epoch=epoch,
        )
        lineage = BootstrapGraphArtifactAssemblerV3.append_successor_lineage(
            predecessor=predecessor_lineage,
            attempt=attempt,
            plan=compilation.plan,
            authorizations=authorizations,
        )
        successor_pre_execution = (
            BootstrapGraphArtifactAssemblerV3.build_pre_execution_identity_closure(
                compilation=compilation,
                attempt=attempt,
                plan=compilation.plan,
                lineage=lineage,
                host_authority=self._host,
                preserved_identities={
                    item.core.transaction_group_id: item
                    for item in predecessor_pre_execution.identities
                    if item.core.transaction_group_id
                    in {
                        value.transaction_group_id
                        for value in authority.group_member_authorities
                        if value.kind != "replacement"
                    }
                },
            )
        )
        lineage_reload = self._plans.publish_and_reload(
            request=BootstrapGraphArtifactAssemblerV3.build_authorized_lineage_checkpoint(
                attempt=attempt,
                authorizations=authorizations,
                lineage=lineage.entries,
                plan=compilation.plan,
                compilation=compilation,
                inputs=compilation.attempt_construction_inputs,
                preparation_fingerprint=epoch.preparation_fingerprint,
                pre_execution_identity_closure=successor_pre_execution,
                operation_lease_binding=bindings[0],
                operation_fence_binding=bindings[1],
                writer_commit_binding=bindings[2],
                predecessor_generation=attempt_reload.checkpoint_receipt.successor_generation,
                predecessor_progress_reference=predecessor_progress_reference,
                replan_closure_reference=replan_closure_reference,
                predecessor_observed_counters=successor_attempt_counters,
            ),
            delivery_principal_binding_digest=request.delivery_principal_binding_digest,
            required_outcome_scopes=request.required_outcome_scopes,
            control_epoch=epoch,
        )
        result = self._execute_attempt(
            request=request,
            epoch=epoch,
            compilation=compilation,
            authorizations=authorizations,
            attempt=attempt,
            lineage=lineage,
            current_generation=lineage_reload.checkpoint_receipt.successor_generation,
            preserved_constructions=completed_group_results,
            preserved_pre_execution=predecessor_pre_execution,
        )
        if isinstance(result, BootstrapGraphRelatedConflictRefreshRequiredV3):
            # The successor may have committed and checkpointed earlier groups
            # before a later group discovers that the refreshed snapshot is
            # stale again. Reload the sealed closure so final-stage evidence
            # includes those current-attempt results as well as predecessor
            # results retained by the replan authority.
            try:
                sealed_failure = (
                    self._plans.reload_resume_closure_for_original_fence(
                        operation_fence_binding=epoch.operation_fence_binding,
                        delivery_principal_binding_digest=(
                            request.delivery_principal_binding_digest
                        ),
                        required_outcome_scopes=request.required_outcome_scopes,
                        control_epoch=epoch,
                        operation_lease_binding=epoch.operation_lease_binding,
                        writer_commit_binding=epoch.writer_commit_binding,
                    )
                )
            except (PreplanningStoreError, TypeError, ValueError, AttributeError):
                return self._unavailable(request, "authority_unavailable")
            if (
                sealed_failure.attempt.artifact != attempt
                or sealed_failure.plan.artifact != compilation.plan
                or sealed_failure.lineage.artifact != lineage
            ):
                return self._unavailable(request, "authority_unavailable")
            return self._finalize_attempt(
                request=request,
                epoch=epoch,
                compilation=compilation,
                authorizations=authorizations,
                attempt=attempt,
                lineage=lineage,
                pre_execution=successor_pre_execution,
                constructions=tuple(
                    item.artifact
                    for item in sealed_failure.canonical_final_group_results
                ),
                current_generation=self._plans.load_current_generation(
                    request=request,
                    control_epoch=epoch,
                    delivery_principal_binding_digest=(
                        request.delivery_principal_binding_digest
                    ),
                    required_outcome_scopes=request.required_outcome_scopes,
                ),
                finalized_failure_group_id=result.transaction_group_id,
            )
        return result

    def _finalize_attempt(
        self, *, request: object, epoch: object, compilation: object,
        authorizations: object,
        attempt: object, lineage: object, pre_execution: object,
        constructions: tuple[object, ...], current_generation: object,
        finalized_failure_group_id: str | None = None,
    ) -> BootstrapGraphDependentCoordinatorResultV3:
        bindings = (
            epoch.operation_lease_binding,
            epoch.operation_fence_binding,
            epoch.writer_commit_binding,
        )
        source_outcomes, _, causal_blockers = build_bootstrap_graph_execution_stage_outcomes(
            request=request,
            control_epoch=epoch,
            host_authority=self._host,
            final_attempt=attempt,
            complete_lineage=lineage,
            group_constructions=constructions,
            finalized_failure_group_id=finalized_failure_group_id,
        )
        graph_validation_attempts = tuple(
            value
            for item in compilation.pre_execution_evidence
            for value in item.graph_validation_attempts
        )
        causal_blockers = tuple(sorted({
            *causal_blockers,
            *(
                blocker
                for validation_attempt in graph_validation_attempts
                for outcome in validation_attempt.stage_outcomes
                if outcome.status == "not_started"
                for blocker in outcome.blocking_stages
            ),
        }, key=lambda value: encode_typed_value(value.model_dump(mode="python"))))
        final_evidence = BootstrapGraphArtifactAssemblerV3.build_final_stage_evidence(
            request_digest=request.request_digest,
            normalization_replay_digest=request.normalization_replay.replay_digest,
            attempt=attempt,
            plan=compilation.plan,
            lineage=lineage,
            ordered_group_commit_reload_digests=tuple(
                item.group_commit_reload.reload_digest for item in constructions
            ),
            source_outcomes=source_outcomes,
            graph_validation_attempts=graph_validation_attempts,
            causal_blockers=causal_blockers,
            proof_digests=tuple(
                value
                for item in compilation.pre_execution_evidence
                for value in item.terminal_before_planning_proof_digests
            ),
            finalized_failure_group_id=finalized_failure_group_id,
        )
        retry_generation = current_generation
        try:
            final_evidence_reload = self._plans.publish_and_reload(
                request=BootstrapGraphArtifactAssemblerV3.build_final_stage_evidence_checkpoint(
                    evidence=final_evidence,
                    operation_lease_binding=bindings[0],
                    operation_fence_binding=bindings[1],
                    writer_commit_binding=bindings[2],
                    predecessor_generation=current_generation,
                ),
                delivery_principal_binding_digest=request.delivery_principal_binding_digest,
                required_outcome_scopes=request.required_outcome_scopes,
                control_epoch=epoch,
            )
            retry_generation = (
                final_evidence_reload.checkpoint_receipt.successor_generation
            )
            preparation = self._preparer.prepare(
                request=request,
                control_epoch=epoch,
                current_generation=final_evidence_reload.checkpoint_receipt.successor_generation,
                final_attempt=attempt,
                final_compilation=compilation,
                pre_execution_manifests=pre_execution,
                final_stage_evidence=final_evidence,
                complete_lineage=lineage,
                group_constructions=constructions,
                host_authority=self._host,
                finalized_failure_group_id=finalized_failure_group_id,
            )
        except (PreplanningStoreError, ValueError):
            return self._post_effect_retry(
                request=request, epoch=epoch, attempt=attempt,
                plan=compilation.plan, authorizations=authorizations, lineage=lineage,
                constructions=list(constructions),
                groups=compilation.plan.canonical_group_order,
                generation=retry_generation,
            )
        try:
            reload = self._terminal.persist_and_reload(
                request=preparation.publication_request
            )
        except (PreplanningStoreError, ValueError):
            # A terminal CAS can commit before transport/acknowledgement fails.
            # Found-first reload is the only authoritative recovery path.
            try:
                reload = self._terminal.reload_by_request(request=request)
            except (PreplanningStoreError, ValueError):
                reload = None
            if reload is None:
                return self._post_effect_retry(
                    request=request, epoch=epoch, attempt=attempt,
                    plan=compilation.plan, authorizations=authorizations, lineage=lineage,
                    constructions=list(constructions),
                    groups=compilation.plan.canonical_group_order,
                    generation=final_evidence_reload.checkpoint_receipt.successor_generation,
                )
        if finalized_failure_group_id is not None or (
            attempt.attempt_index > 0
            and any(item.disposition == "failed" for item in constructions)
        ):
            return BootstrapGraphFinalizedFailureV3.create(
                kind="finalized_failure",
                terminal_reload=reload,
                control_epoch_digest=epoch.epoch_digest,
                reason="related_conflict_exhausted",
            )
        return BootstrapGraphDependentCoordinatorSucceededV3.create(
            kind="succeeded",
            terminal_reload=reload,
            control_epoch_digest=epoch.epoch_digest,
        )

    def _post_effect_retry(
        self, *, request: object, epoch: object, attempt: object, plan: object,
        authorizations: object, lineage: object, constructions: list[object],
        groups: tuple[str, ...], generation: object, reason: str = "storage_retry",
    ) -> BootstrapGraphDurableRetryProgressV3:
        unavailable = BootstrapGraphV3ProducerUnavailable.create(
            phase="group_execute",
            reason="storage_unavailable",
            request_digest=attempt.request_digest,
            control_epoch_digest=epoch.epoch_digest,
        )
        return self._retry(
            request, epoch, attempt, plan, authorizations, lineage, constructions,
            groups, unavailable, generation, reason=reason,
        )

    def _retry(
        self, request: object, epoch: object, attempt: object, plan: object,
        authorizations: object, lineage: object, constructions: list[object],
        groups: tuple[str, ...], unavailable: object, generation: object,
        *, reason: str = "storage_retry",
    ):
        progress = BootstrapGraphArtifactAssemblerV3.durable_retry(
            unavailable=unavailable,
            attempt=attempt,
            source_plan_lineage_digest=lineage.lineage_digest,
            completed_group_result_digests=tuple(item.result_digest for item in constructions),
            retry_group_ids=tuple(
                item for item in groups if item not in {
                    value.transaction_group_id for value in constructions
                }
            ),
            reason=reason,
        )
        reload = self._plans.publish_and_reload(request=BootstrapGraphArtifactAssemblerV3.build_retry_checkpoint(progress=progress, attempt=attempt, plan=plan, authorizations=authorizations, lineage=lineage, completed_group_results=tuple(constructions), operation_lease_binding=epoch.operation_lease_binding, operation_fence_binding=epoch.operation_fence_binding, writer_commit_binding=epoch.writer_commit_binding, predecessor_generation=generation), delivery_principal_binding_digest=request.delivery_principal_binding_digest, required_outcome_scopes=request.required_outcome_scopes, control_epoch=epoch)
        progress_member = next(
            (
                member for member in reload.core.members
                if member.kind == "bootstrap_graph_retry_progress"
            ),
            None,
        )
        if progress_member is None:
            raise PreplanningStoreError("bootstrap graph retry checkpoint is absent")
        return BootstrapGraphDurableRetryProgressV3.model_validate(
            decode_bootstrap_graph_atomic_member_payload_v3(
                kind=progress_member.kind,
                raw=progress_member.canonical_payload,
            ), strict=False
        )

    @staticmethod
    def _unavailable(request: BootstrapGraphDependentCoordinatorRequestV3, reason: str) -> BootstrapGraphDependentPreGraphNonCommitV3:
        return BootstrapGraphDependentPreGraphNonCommitV3.create(kind="pre_graph_noncommit", request_digest=request.request_digest, reason=reason, reason_digest=contract_digest(b"memorii.semantic-ingestion.bootstrap-graph-dependent-coordinator-pre-graph-noncommit-reason.v3", {"reason": reason}))


__all__ = [
    "BootstrapGraphDependentCoordinatorV3",
    "BootstrapGraphPlanCompilerPortV3",
    "BootstrapGraphPlanningAuthorizerPortV3",
]
