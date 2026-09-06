"""Pure assembly of sealed bootstrap V3 graph artifacts.

The coordinator supplies already-produced graph effects; this owner only joins
their immutable coordinates and derives the content-addressed carriers.
"""

from __future__ import annotations

from hashlib import sha256

from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
from memorii.core.semantic_ingestion.contracts import (
    BootstrapFinalGroupResultReferenceV3,
    BootstrapGraphAtomicMemberReferenceV3,
    BootstrapGraphAttemptConstructionInputsV3,
    BootstrapGraphAttemptPublishedProgressV3,
    BootstrapGraphDependentAttemptV3,
    BootstrapGraphDurableRetryProgressV3,
    BootstrapGraphFinalStageEvidenceV3,
    BootstrapGraphGroupCasRequestV3,
    BootstrapGraphGroupCommitReloadV3,
    BootstrapGraphObservedCountersV3,
    BootstrapGraphPlanAtomicWriteRequestV3,
    BootstrapGraphPlanAuthorizationSetV3,
    BootstrapGraphPlanCompilationV3,
    BootstrapGraphPlannedProgressV3,
    BootstrapGraphPlanPublishedProgressV3,
    BootstrapGraphPreExecutionManifestCoreV3,
    BootstrapGraphPreExecutionManifestIdentityClosureV3,
    BootstrapGraphPreExecutionManifestIdentityV3,
    BootstrapGraphReplanClosureReferenceV3,
    BootstrapGraphReplanPartitionV3,
    BootstrapGraphReplayBundleV3,
    BootstrapGraphTerminalHandoffCoreV3,
    BootstrapGraphTerminalPersistenceHandoffV3,
    BootstrapGraphTerminalPublicationIntentV3,
    BootstrapGraphTerminalPublicationRequestV3,
    BootstrapGraphV3ProducerUnavailable,
    BootstrapGroupPlanningAuthorizationV3,
    BootstrapInitialAttemptAuthorityV3,
    BootstrapNativeGroupCommitTerminalConstructionV3,
    BootstrapReplacementGroupAuthorityV3,
    BootstrapReusedCommittedGroupAuthorityV3,
    BootstrapReusedFinalGroupAuthorityV3,
    BootstrapReusedUnfinishedGroupAuthorityV3,
    BootstrapSourcePlanLineageEntryReferenceV3,
    BootstrapSourcePlanLineageEntryV3,
    BootstrapSourcePlanLineageV3,
    BootstrapSuccessorAttemptAuthorityV3,
    BootstrapTransactionGroupPlanMemberV3,
    BootstrapTransactionGroupPlanV3,
    contract_digest,
    encode_bootstrap_graph_atomic_member_payload_v3,
)


class BootstrapGraphArtifactAssemblerV3:
    """Build only closed artifacts; it neither reads nor writes repositories."""

    @staticmethod
    def _retained_compilation(
        compilation: object,
    ) -> BootstrapGraphPlanCompilationV3:
        """Strip the runtime compiler facade before persisting native bytes."""
        native = getattr(compilation, "native", compilation)
        if not isinstance(native, BootstrapGraphPlanCompilationV3):
            raise ValueError("bootstrap graph compilation is not a native artifact")
        return native

    @staticmethod
    def successor_compilation(
        *, replacement: object, predecessor: BootstrapGraphPlanCompilationV3,
        replanned_group_ids: tuple[str, ...],
    ) -> BootstrapGraphPlanCompilationV3:
        """Retain predecessor compiler bytes for every unreplanned group."""
        fresh = BootstrapGraphArtifactAssemblerV3._retained_compilation(replacement)
        replanned = set(replanned_group_ids)
        predecessor_members = {
            item.transaction_group_id: item
            for item in predecessor.transaction_group_plan.group_members
        }
        members = tuple(
            item
            if item.transaction_group_id in replanned
            else predecessor_members[item.transaction_group_id]
            for item in fresh.transaction_group_plan.group_members
        )
        plan = BootstrapTransactionGroupPlanV3.create(
            request_digest=fresh.transaction_group_plan.request_digest,
            normalization_replay_digest=(
                fresh.transaction_group_plan.normalization_replay_digest
            ),
            source_alignment_digest=fresh.transaction_group_plan.source_alignment_digest,
            graph_snapshot_digest=fresh.transaction_group_plan.graph_snapshot_digest,
            sealed_read_set_digest=fresh.transaction_group_plan.sealed_read_set_digest,
            fixed_point_rounds=fresh.transaction_group_plan.fixed_point_rounds,
            group_members=members,
            canonical_group_order=tuple(item.transaction_group_id for item in members),
            execution_policy_reference_digest=(
                fresh.transaction_group_plan.execution_policy_reference_digest
            ),
            operation_lease_binding_digest=(
                fresh.transaction_group_plan.operation_lease_binding_digest
            ),
            operation_fence_binding_digest=(
                fresh.transaction_group_plan.operation_fence_binding_digest
            ),
            writer_commit_binding_digest=(
                fresh.transaction_group_plan.writer_commit_binding_digest
            ),
            control_epoch_digest=fresh.transaction_group_plan.control_epoch_digest,
        )
        predecessor_reductions = {
            (item.transaction_group_id, item.operation_id): item
            for item in predecessor.operation_reductions
        }
        reductions = tuple(
            item
            if item.transaction_group_id in replanned
            else predecessor_reductions[(item.transaction_group_id, item.operation_id)]
            for item in fresh.operation_reductions
        )
        predecessor_inputs = {
            item.transaction_group_id: item
            for item in predecessor.manifest_group_inputs
        }
        manifest_inputs = tuple(
            item
            if item.transaction_group_id in replanned
            else predecessor_inputs[item.transaction_group_id]
            for item in fresh.manifest_group_inputs
        )
        predecessor_evidence = {
            item.transaction_group_id: item
            for item in predecessor.pre_execution_evidence
        }
        evidence = tuple(
            item
            if item.transaction_group_id in replanned
            else predecessor_evidence[item.transaction_group_id]
            for item in fresh.pre_execution_evidence
        )
        fresh_inputs = fresh.attempt_construction_inputs
        attempt_inputs = BootstrapGraphAttemptConstructionInputsV3.create(
            request_digest=fresh_inputs.request_digest,
            normalization_replay_digest=fresh_inputs.normalization_replay_digest,
            normalization_result_digest=fresh_inputs.normalization_result_digest,
            source_alignment_digest=fresh_inputs.source_alignment_digest,
            graph_snapshot_digest=fresh_inputs.graph_snapshot_digest,
            sealed_read_set_digest=fresh_inputs.sealed_read_set_digest,
            reconciliation_digest=fresh_inputs.reconciliation_digest,
            reference_closure_digest=fresh_inputs.reference_closure_digest,
            execution_policy_reference_digest=(
                fresh_inputs.execution_policy_reference_digest
            ),
            control_epoch_digest=fresh_inputs.control_epoch_digest,
            ordered_pre_execution_evidence_digests=tuple(
                item.evidence_digest for item in evidence
            ),
        )
        return BootstrapGraphPlanCompilationV3.create(
            request_digest=fresh.request_digest,
            normalization_replay_digest=fresh.normalization_replay_digest,
            control_epoch_digest=fresh.control_epoch_digest,
            transaction_group_plan=plan,
            operation_reductions=reductions,
            manifest_group_inputs=manifest_inputs,
            pre_execution_evidence=evidence,
            attempt_construction_inputs=attempt_inputs,
        )

    @staticmethod
    def _authorizations_match_plan(
        *,
        authorizations: BootstrapGraphPlanAuthorizationSetV3,
        plan: object,
        request_digest: str,
        control_epoch_digest: str,
    ) -> bool:
        """Verify the per-member authorization join before deriving an attempt.

        The authorization is intentionally bound to each immutable plan member,
        rather than carrying the retired aggregate plan-digest field.
        """
        members = tuple(plan.group_members)
        values = authorizations.authorizations
        if (
            authorizations.request_digest != request_digest
            or authorizations.plan_digest != plan.plan_digest
            or authorizations.control_epoch_digest != control_epoch_digest
            or tuple(item.transaction_group_id for item in values)
            != tuple(member.transaction_group_id for member in members)
        ):
            return False
        return all(
            authorization.request_digest == request_digest
            and authorization.group_plan_member_digest == member.member_digest
            and authorization.operation_ids == member.operation_ids
            and authorization.operation_plan_digests
            == tuple(item.operation_plan_digest for item in member.operation_plans)
            and authorization.graph_read_set_digest
            == member.graph_read_set.read_set_digest
            and authorization.control_epoch_digest == control_epoch_digest
            and authorization.operation_lease_binding_digest
            == plan.operation_lease_binding_digest
            and authorization.operation_fence_binding_digest
            == plan.operation_fence_binding_digest
            and authorization.writer_commit_binding_digest
            == plan.writer_commit_binding_digest
            for authorization, member in zip(values, members, strict=True)
        )

    @staticmethod
    def _successor_authorizations_match_plan(
        *, authorizations: BootstrapGraphPlanAuthorizationSetV3,
        plan: object, authority: BootstrapSuccessorAttemptAuthorityV3,
        request_digest: str, control_epoch_digest: str,
    ) -> bool:
        members = tuple(plan.group_members)
        values = authorizations.authorizations
        group_authorities = authority.group_member_authorities
        if (
            authorizations.request_digest != request_digest
            or authorizations.plan_digest != plan.plan_digest
            or authorizations.control_epoch_digest != control_epoch_digest
            or tuple(item.transaction_group_id for item in values)
            != tuple(member.transaction_group_id for member in members)
            or tuple(item.transaction_group_id for item in group_authorities)
            != tuple(member.transaction_group_id for member in members)
        ):
            return False
        for authorization, member, group_authority in zip(
            values, members, group_authorities, strict=True
        ):
            expected = (
                group_authority.replacement_planning_authorization
                if group_authority.kind == "replacement"
                else group_authority.planning_authorization
                if group_authority.kind == "reused_final"
                else group_authority.predecessor_planning_authorization
            )
            if (
                expected is None
                or authorization != expected
                or authorization.group_plan_member_digest != member.member_digest
                or authorization.operation_ids != member.operation_ids
                or authorization.operation_plan_digests
                != tuple(item.operation_plan_digest for item in member.operation_plans)
                or authorization.graph_read_set_digest
                != member.graph_read_set.read_set_digest
                or authorization.operation_lease_binding_digest
                != plan.operation_lease_binding_digest
                or authorization.operation_fence_binding_digest
                != plan.operation_fence_binding_digest
                or authorization.writer_commit_binding_digest
                != plan.writer_commit_binding_digest
                or (
                    group_authority.kind == "replacement"
                    and (
                        authorization.request_digest != request_digest
                        or authorization.control_epoch_digest != control_epoch_digest
                    )
                )
            ):
                return False
        return True

    @staticmethod
    def build_pre_execution_identity_closure(
        *, compilation: BootstrapGraphPlanCompilationV3,
        attempt: BootstrapGraphDependentAttemptV3, plan: object,
        lineage: BootstrapSourcePlanLineageV3,
        host_authority: object,
        preserved_identities: dict[str, BootstrapGraphPreExecutionManifestIdentityV3]
        | None = None,
    ) -> BootstrapGraphPreExecutionManifestIdentityClosureV3:
        """Seal the per-group pre-CAS identity closure from immutable inputs only."""
        members = tuple(plan.group_members)
        group_ids = tuple(item.transaction_group_id for item in members)
        inputs = tuple(compilation.manifest_group_inputs)
        evidence = tuple(compilation.pre_execution_evidence)
        input_by_group = {item.transaction_group_id: item for item in inputs}
        evidence_by_group = {item.transaction_group_id: item for item in evidence}
        entry_by_group = dict(lineage.latest_entry_by_group)
        entries_by_digest = {item.entry_digest: item for item in lineage.entries}
        if (
            compilation.plan != plan
            or compilation.request_digest != attempt.request_digest
            or compilation.normalization_replay_digest != attempt.normalization_replay_digest
            or compilation.control_epoch_digest != attempt.control_epoch_digest
            or plan.plan_digest != attempt.transaction_group_plan_digest
            or lineage.request_digest != attempt.request_digest
            or lineage.normalization_replay_digest != attempt.normalization_replay_digest
            or lineage.control_epoch_digest != attempt.control_epoch_digest
            or tuple(item.transaction_group_id for item in inputs) != group_ids
            or tuple(item.transaction_group_id for item in evidence) != group_ids
            or tuple(item.evidence_digest for item in evidence)
            != compilation.attempt_construction_inputs.ordered_pre_execution_evidence_digests
            or set(entry_by_group) != set(group_ids)
            or host_authority.operation_fence_binding.binding_digest
            != attempt.operation_fence_binding_digest
            or tuple(item.binding_digest for item in host_authority.capability_bindings)
            != attempt.capability_binding_digests
            or any(
                (entry.source_id, entry.source_digest, entry.preparation_fingerprint)
                != (host_authority.source_id, host_authority.source_digest,
                    host_authority.preparation_fingerprint)
                for entry in lineage.entries
            )
        ):
            raise ValueError("bootstrap graph pre-execution closure inputs are substituted")
        preserved_identities = preserved_identities or {}
        if not set(preserved_identities).issubset(group_ids):
            raise ValueError("bootstrap graph preserved pre-execution identity is foreign")
        identities = []
        for member in members:
            group_id = member.transaction_group_id
            preserved = preserved_identities.get(group_id)
            if preserved is not None:
                if (
                    preserved.core.transaction_group_id != group_id
                    or preserved.core.normalization_replay_digest
                    != attempt.normalization_replay_digest
                    or preserved.core.execution_graph_fingerprint
                    != host_authority.execution_graph_fingerprint
                ):
                    raise ValueError(
                        "bootstrap graph preserved pre-execution identity is substituted"
                    )
                identities.append(preserved)
                continue
            group_input = input_by_group[group_id]
            group_evidence = evidence_by_group[group_id]
            entry = entries_by_digest.get(entry_by_group[group_id])
            if (
                entry is None
                or entry.transaction_group_id != group_id
                or entry.attempt_digest != attempt.attempt_digest
                or entry.group_plan_member_digest != member.member_digest
                or group_input.group_plan_member != member
                or group_evidence.request_digest != attempt.request_digest
                or group_evidence.normalization_replay_digest
                != attempt.normalization_replay_digest
                or group_evidence.group_plan_member_digest != member.member_digest
                or group_evidence.graph_snapshot_digest
                != attempt.graph_snapshot_digest
                or group_evidence.sealed_read_set_digest
                != attempt.sealed_read_set_digest
                or group_evidence.reconciliation_digest
                != attempt.reconciliation_digest
                or group_evidence.reference_closure_digest
                != attempt.reference_closure_digest
                or group_evidence.control_epoch_digest
                != attempt.control_epoch_digest
            ):
                raise ValueError(
                    "bootstrap graph pre-execution group closure is substituted"
                )
            core = BootstrapGraphPreExecutionManifestCoreV3.create(
                request_digest=attempt.request_digest,
                normalization_replay_digest=attempt.normalization_replay_digest,
                transaction_group_id=group_id,
                producing_attempt_digest=attempt.attempt_digest,
                producing_transaction_group_plan_digest=plan.plan_digest,
                producing_lineage_entry_digest=entry.entry_digest,
                control_epoch_digest=attempt.control_epoch_digest,
                execution_graph_fingerprint=host_authority.execution_graph_fingerprint,
                segment_language_routes=host_authority.segment_language_routes,
                segment_governance_carriers=host_authority.segment_governance_carriers,
                message_admission_carriers=host_authority.message_admission_carriers,
                governance_carrier_artifact=host_authority.governance_carrier_artifact,
                capability_bindings=host_authority.capability_bindings,
                graph_validation_attempts=group_evidence.graph_validation_attempts,
                causal_blockers=group_evidence.causal_blockers,
                terminal_before_planning_proof_digests=group_evidence.terminal_before_planning_proof_digests,
                manifest_group_inputs=(group_input,),
            )
            identity_id = contract_digest(
                b"memorii.semantic-ingestion.bootstrap-graph-pre-execution-manifest-id.v3",
                {
                    "request_digest": attempt.request_digest,
                    "transaction_group_id": group_id,
                    "producing_attempt_digest": attempt.attempt_digest,
                    "producing_transaction_group_plan_digest": plan.plan_digest,
                    "producing_lineage_entry_digest": entry.entry_digest,
                    "core_digest": core.core_digest,
                },
            )
            identities.append(BootstrapGraphPreExecutionManifestIdentityV3.create(
                core=core, manifest_identity_id=identity_id,
            ))
        return BootstrapGraphPreExecutionManifestIdentityClosureV3.create(
            request_digest=attempt.request_digest,
            normalization_replay_digest=attempt.normalization_replay_digest,
            source_id=host_authority.source_id, source_digest=host_authority.source_digest,
            preparation_fingerprint=host_authority.preparation_fingerprint,
            identities=tuple(identities),
            identity_by_group=tuple((group_id, identity.identity_digest)
                                    for group_id, identity in zip(group_ids, identities, strict=True)),
            operation_fence_binding_digest=attempt.operation_fence_binding_digest,
            writer_commit_binding_digest=attempt.writer_commit_binding_digest,
        )

    @staticmethod
    def build_final_stage_evidence(*, request_digest: str, normalization_replay_digest: str,
                                   attempt: BootstrapGraphDependentAttemptV3, plan: object,
                                   lineage: BootstrapSourcePlanLineageV3,
                                   ordered_group_commit_reload_digests: tuple[str, ...],
                                   source_outcomes: tuple[object, ...], graph_validation_attempts: tuple[object, ...],
                                   causal_blockers: tuple[object, ...], proof_digests: tuple[str, ...],
                                   finalized_failure_group_id: str | None = None) -> BootstrapGraphFinalStageEvidenceV3:
        group_ids = tuple(member.transaction_group_id for member in plan.group_members)
        complete_reload_set = len(group_ids) == len(ordered_group_commit_reload_digests)
        failed_suffix = (
            finalized_failure_group_id in group_ids
            and len(ordered_group_commit_reload_digests)
            == group_ids.index(finalized_failure_group_id)
        ) if finalized_failure_group_id is not None else False
        request_matches = request_digest == attempt.request_digest
        normalization_matches = (
            normalization_replay_digest == attempt.normalization_replay_digest
        )
        plan_matches = plan.plan_digest == attempt.transaction_group_plan_digest
        lineage_is_complete = lineage.lineage_digest is not None
        if not (
            request_matches
            and normalization_matches
            and plan_matches
            and lineage_is_complete
            and (complete_reload_set or failed_suffix)
        ):
            raise ValueError(
                "bootstrap graph final stage evidence inputs are substituted: "
                f"request_matches={request_matches}, "
                f"normalization_matches={normalization_matches}, "
                f"plan_matches={plan_matches}, "
                f"lineage_is_complete={lineage_is_complete}, "
                f"group_count={len(group_ids)}, "
                f"reload_count={len(ordered_group_commit_reload_digests)}, "
                f"finalized_failure_group_id={finalized_failure_group_id!r}, "
                f"failure_index={group_ids.index(finalized_failure_group_id) if finalized_failure_group_id in group_ids else None}"
            )
        return BootstrapGraphFinalStageEvidenceV3.create(request_digest=request_digest, normalization_replay_digest=normalization_replay_digest, attempt_digest=attempt.attempt_digest, transaction_group_plan_digest=plan.plan_digest, source_plan_lineage_digest=lineage.lineage_digest, ordered_transaction_group_ids=group_ids, ordered_group_commit_reload_digests=ordered_group_commit_reload_digests, source_outcomes=source_outcomes, graph_validation_attempts=graph_validation_attempts, causal_blockers=causal_blockers, terminal_before_planning_proof_digests=proof_digests, control_epoch_digest=attempt.control_epoch_digest)

    @classmethod
    def build_final_stage_evidence_checkpoint(cls, *, evidence: BootstrapGraphFinalStageEvidenceV3,
                                               operation_lease_binding: object, operation_fence_binding: object,
                                               writer_commit_binding: object, predecessor_generation: object) -> BootstrapGraphPlanAtomicWriteRequestV3:
        member = cls.atomic_member(member_id="final-stage-evidence", kind="bootstrap_graph_final_stage_evidence", artifact=evidence)
        return BootstrapGraphPlanAtomicWriteRequestV3.create(kind="bootstrap_graph_final_stage_evidence_checkpoint", request_digest=evidence.request_digest, normalization_replay_digest=evidence.normalization_replay_digest, normalization_result_digest="0" * 64, predecessor_generation=predecessor_generation, operation_lease_binding=operation_lease_binding, operation_fence_binding=operation_fence_binding, writer_commit_binding=writer_commit_binding, control_epoch_digest=evidence.control_epoch_digest, members=(member,), required_member_digests=(member.member_digest,))

    @staticmethod
    def group_cas_request(
        *,
        request_digest: str,
        normalization_replay_digest: str,
        attempt: BootstrapGraphDependentAttemptV3,
        member: BootstrapTransactionGroupPlanMemberV3,
        authorization: BootstrapGroupPlanningAuthorizationV3,
        lineage: BootstrapSourcePlanLineageEntryV3,
        pre_execution_manifest_identity_digest: str,
    ) -> BootstrapGraphGroupCasRequestV3:
        if (
            attempt.request_digest != request_digest
            or attempt.normalization_replay_digest != normalization_replay_digest
            or authorization.transaction_group_id != member.transaction_group_id
            or authorization.group_plan_member_digest != member.member_digest
            or authorization.request_digest != attempt.request_digest
            or authorization.graph_read_set_digest != member.graph_read_set.read_set_digest
            or authorization.operation_ids != member.operation_ids
            or authorization.operation_plan_digests
            != tuple(item.operation_plan_digest for item in member.operation_plans)
            or authorization.control_epoch_digest != attempt.control_epoch_digest
            or authorization.operation_lease_binding_digest
            != attempt.operation_lease_binding_digest
            or authorization.operation_fence_binding_digest
            != attempt.operation_fence_binding_digest
            or authorization.writer_commit_binding_digest
            != attempt.writer_commit_binding_digest
            or lineage.transaction_group_id != member.transaction_group_id
            or lineage.attempt_digest != attempt.attempt_digest
            or lineage.group_plan_member_digest != member.member_digest
            or lineage.planning_authorization_digest != authorization.authorization_digest
            or lineage.control_epoch_digest != attempt.control_epoch_digest
        ):
            raise ValueError("bootstrap graph CAS assembly inputs are substituted")
        return BootstrapGraphGroupCasRequestV3.create(
            request_digest=request_digest,
            normalization_replay_digest=normalization_replay_digest,
            attempt_digest=attempt.attempt_digest,
            transaction_group_id=member.transaction_group_id,
            group_plan_member_digest=member.member_digest,
            planning_authorization_digest=authorization.authorization_digest,
            source_plan_lineage_entry_digest=lineage.entry_digest,
            pre_execution_manifest_identity_digest=pre_execution_manifest_identity_digest,
            sealed_read_set_digest=attempt.sealed_read_set_digest,
            proposed_delta_digest=member.proposed_delta_digest,
            event_batch_digest=member.event_batch_digest,
            control_epoch_digest=attempt.control_epoch_digest,
        )

    @staticmethod
    def atomic_member(*, member_id: str, kind: str, artifact: object):
        """Encode a single sealed V3 artifact for a checkpoint closure."""
        from memorii.core.semantic_ingestion.contracts import BootstrapGraphPlanAtomicMemberV3

        if not hasattr(artifact, "model_dump"):
            raise ValueError("bootstrap graph atomic member requires a typed native artifact")
        payload = encode_bootstrap_graph_atomic_member_payload_v3(
            kind=kind, artifact=artifact,
        )
        return BootstrapGraphPlanAtomicMemberV3.create(
            member_id=member_id, kind=kind, canonical_payload=payload,
            payload_digest=sha256(payload).hexdigest(),
        )

    @staticmethod
    def _member_reference(*, repository_id: str, member: object, artifact: object,
                          payload_type: str, generation: int) -> BootstrapGraphAtomicMemberReferenceV3:
        return BootstrapGraphAtomicMemberReferenceV3.create(
            repository_id=repository_id, artifact_digest=getattr(artifact, {
                "BootstrapTransactionGroupPlanV3": "plan_digest",
                "BootstrapGraphReplayBundleV3": "replay_bundle_digest",
                "BootstrapGraphObservedCountersV3": "counters_digest",
                "BootstrapGraphDependentAttemptV3": "attempt_digest",
                "BootstrapSourcePlanLineageV3": "lineage_digest",
                "BootstrapGraphPreExecutionManifestIdentityClosureV3": "closure_digest",
                "BootstrapNativeGroupCommitTerminalConstructionV3": "result_digest",
                "BootstrapGraphSourceProgressV3": "progress_digest",
            }.get(payload_type, "authority_digest")),
            generation=generation, member_id=member.member_id, member_kind=member.kind,
            member_payload_digest=member.payload_digest, payload_type=payload_type,
        )

    @classmethod
    def build_replan_closure_reference(
        cls,
        *,
        predecessor_progress_member: object,
        predecessor_progress: BootstrapGraphPlannedProgressV3,
        predecessor_lineage_member: object,
        predecessor_lineage: BootstrapSourcePlanLineageV3,
        predecessor_generation: int,
        final_result_members: tuple[
            tuple[int, object, BootstrapNativeGroupCommitTerminalConstructionV3], ...
        ],
        unfinished_transaction_group_ids: tuple[str, ...],
        replanned_transaction_group_ids: tuple[str, ...],
    ) -> BootstrapGraphReplanClosureReferenceV3:
        """Bind only already-sealed predecessor bytes for a related replan."""
        predecessor_progress_reference = cls._member_reference(
            repository_id="semantic_ingestion.bootstrap_graph_progress.v3",
            member=predecessor_progress_member, artifact=predecessor_progress,
            payload_type="BootstrapGraphSourceProgressV3", generation=predecessor_generation,
        )
        predecessor_lineage_reference = cls._member_reference(
            repository_id="semantic_ingestion.bootstrap_source_plan_lineage.v3",
            member=predecessor_lineage_member, artifact=predecessor_lineage,
            payload_type="BootstrapSourcePlanLineageV3", generation=predecessor_generation,
        )
        final_references = tuple(sorted((
            cls._member_reference(
                repository_id="semantic_ingestion.bootstrap_group_result.v3",
                member=member, artifact=result,
                payload_type="BootstrapNativeGroupCommitTerminalConstructionV3",
                generation=generation,
            )
            for generation, member, result in final_result_members
        ), key=lambda reference: reference.member_id))
        return BootstrapGraphReplanClosureReferenceV3.create(
            predecessor_planned_progress_reference=predecessor_progress_reference,
            predecessor_lineage_reference=predecessor_lineage_reference,
            canonical_final_result_references=final_references,
            unfinished_transaction_group_ids=unfinished_transaction_group_ids,
            replanned_transaction_group_ids=replanned_transaction_group_ids,
        )

    @staticmethod
    def _replay_bundle(inputs: BootstrapGraphAttemptConstructionInputsV3) -> BootstrapGraphReplayBundleV3:
        return BootstrapGraphReplayBundleV3.create(
            request_digest=inputs.request_digest,
            normalization_replay_digest=inputs.normalization_replay_digest,
            normalization_result_digest=inputs.normalization_result_digest,
            source_alignment_digest=inputs.source_alignment_digest,
        )

    @staticmethod
    def _observed_counters(*, inputs: BootstrapGraphAttemptConstructionInputsV3,
                           operation_fence_binding: object, publication_generation: int,
                           plan: object, attempts: int, reservations: int,
                           lineage_entries: int,
                           predecessor: BootstrapGraphObservedCountersV3 | None = None,
                           related_conflict: bool = False) -> BootstrapGraphObservedCountersV3:
        values = dict(
            request_digest=inputs.request_digest, control_epoch_digest=inputs.control_epoch_digest,
            operation_fence_binding_digest=operation_fence_binding.binding_digest,
            execution_policy_reference_digest=inputs.execution_policy_reference_digest,
            publication_generation=publication_generation,
            observed_operations=sum(len(item.operation_plans) for item in plan.group_members),
            observed_groups=len(plan.group_members), observed_fixed_point_rounds=0,
            observed_snapshot_records=0, observed_snapshot_partitions=0,
            observed_related_conflicts=1 if related_conflict else 0, observed_attempts=attempts,
            observed_read_set_extensions=0, observed_reservations=reservations,
            observed_lineage_entries=lineage_entries, observed_replay_artifacts=1,
            observed_replay_bundle_bytes=len(encode_typed_value({
                "request_digest": inputs.request_digest,
                "normalization_replay_digest": inputs.normalization_replay_digest,
                "normalization_result_digest": inputs.normalization_result_digest,
                "source_alignment_digest": inputs.source_alignment_digest,
            })), observed_decode_depth=0,
        )
        if predecessor is not None:
            if (
                predecessor.operation_fence_binding_digest
                != operation_fence_binding.binding_digest
                or (
                    not related_conflict
                    and (
                        predecessor.request_digest != inputs.request_digest
                        or predecessor.control_epoch_digest != inputs.control_epoch_digest
                        or predecessor.execution_policy_reference_digest
                        != inputs.execution_policy_reference_digest
                    )
                )
            ):
                raise ValueError("bootstrap graph predecessor counters are substituted")
            for name in BootstrapGraphObservedCountersV3.model_fields:
                if name.startswith("observed_"):
                    values[name] = max(values[name], getattr(predecessor, name))
            if related_conflict:
                values["observed_related_conflicts"] = predecessor.observed_related_conflicts + 1
        return BootstrapGraphObservedCountersV3.create(**values)

    @classmethod
    def _progress_member(cls, *, kind: str, source_id: str, source_digest: str,
                         preparation_fingerprint: str, operation_id: str,
                         inputs: BootstrapGraphAttemptConstructionInputsV3,
                         operation_lease_binding: object, operation_fence_binding: object,
                         writer_commit_binding: object, plan_reference: object,
                         replay_reference: object, counters_reference: object,
                         authority_reference: object | None = None,
                         attempt_reference: object | None = None,
                         lineage_reference: object | None = None,
                         pre_execution_identity_closure_reference: object | None = None,
                         predecessor_progress_reference: object | None = None,
                         replan_closure_reference: object | None = None) -> object:
        values = dict(
            source_id=source_id, source_digest=source_digest,
            preparation_fingerprint=preparation_fingerprint, operation_id=operation_id,
            request_digest=inputs.request_digest,
            normalization_replay_digest=inputs.normalization_replay_digest,
            normalization_result_digest=inputs.normalization_result_digest,
            control_epoch_digest=inputs.control_epoch_digest,
            operation_fence_binding_digest=operation_fence_binding.binding_digest,
            operation_lease_binding_digest=operation_lease_binding.binding_digest,
            writer_commit_binding_digest=writer_commit_binding.binding_digest,
            plan_reference=plan_reference, replay_bundle_reference=replay_reference,
            observed_counters_reference=counters_reference,
            predecessor_progress_reference=predecessor_progress_reference,
            replan_closure_reference=replan_closure_reference,
        )
        if kind == "plan_published":
            progress = BootstrapGraphPlanPublishedProgressV3.create(**values)
        elif kind == "attempt_published":
            progress = BootstrapGraphAttemptPublishedProgressV3.create(
                **values, authority_reference=authority_reference, attempt_reference=attempt_reference,
            )
        else:
            progress = BootstrapGraphPlannedProgressV3.create(
                **values, authority_reference=authority_reference, attempt_reference=attempt_reference,
                lineage_reference=lineage_reference,
                pre_execution_identity_closure_reference=(
                    pre_execution_identity_closure_reference
                ),
            )
        return cls.atomic_member(member_id="source-progress", kind="bootstrap_graph_source_progress", artifact=progress)

    @classmethod
    def build_initial_checkpoint(
        cls, *, compilation: BootstrapGraphPlanCompilationV3,
        attempt: BootstrapGraphDependentAttemptV3, operation_lease_binding: object,
        operation_fence_binding: object, writer_commit_binding: object,
        predecessor_generation: object,
    ) -> BootstrapGraphPlanAtomicWriteRequestV3:
        if (
            compilation.plan.plan_digest != attempt.transaction_group_plan_digest
            or compilation.control_epoch_digest != attempt.control_epoch_digest
            or compilation.request_digest != attempt.request_digest
        ):
            raise ValueError("bootstrap graph initial checkpoint inputs are substituted")
        members = tuple(sorted((
            cls.atomic_member(member_id="attempt", kind="bootstrap_graph_dependent_attempt", artifact=attempt),
            cls.atomic_member(member_id="plan", kind="bootstrap_transaction_group_plan", artifact=compilation.plan),
        ), key=lambda item: item.member_id))
        return BootstrapGraphPlanAtomicWriteRequestV3.create(
            kind="bootstrap_graph_attempt_checkpoint", request_digest=attempt.request_digest,
            normalization_replay_digest=attempt.normalization_replay_digest,
            normalization_result_digest=attempt.normalization_result_digest,
            predecessor_generation=predecessor_generation,
            operation_lease_binding=operation_lease_binding,
            operation_fence_binding=operation_fence_binding,
            writer_commit_binding=writer_commit_binding,
            control_epoch_digest=attempt.control_epoch_digest, members=members,
            required_member_digests=tuple(sorted(item.member_digest for item in members)),
        )

    @classmethod
    def build_plan_checkpoint(
        cls, *, compilation: BootstrapGraphPlanCompilationV3,
        operation_lease_binding: object, operation_fence_binding: object,
        writer_commit_binding: object, predecessor_generation: object,
        preparation_fingerprint: str,
        predecessor_progress_reference: object | None = None,
        replan_closure_reference: object | None = None,
        predecessor_observed_counters: BootstrapGraphObservedCountersV3 | None = None,
    ) -> BootstrapGraphPlanAtomicWriteRequestV3:
        """Publish only the plan and pre-attempt inputs before authorization."""
        retained_compilation = cls._retained_compilation(compilation)
        inputs = retained_compilation.attempt_construction_inputs
        if (
            inputs.request_digest != retained_compilation.request_digest
            or inputs.normalization_replay_digest != retained_compilation.normalization_replay_digest
            or inputs.control_epoch_digest != retained_compilation.control_epoch_digest
            or inputs.sealed_read_set_digest != retained_compilation.transaction_group_plan.sealed_read_set_digest
        ):
            raise ValueError("bootstrap graph plan checkpoint inputs are substituted")
        publication_generation = predecessor_generation.operation_generation + 1
        replay_bundle = cls._replay_bundle(inputs)
        counters = cls._observed_counters(
            inputs=inputs, operation_fence_binding=operation_fence_binding,
            publication_generation=publication_generation, plan=retained_compilation.transaction_group_plan,
            attempts=0, reservations=0, lineage_entries=0,
            predecessor=predecessor_observed_counters,
            related_conflict=replan_closure_reference is not None,
        )
        plan_member = cls.atomic_member(member_id="plan", kind="bootstrap_transaction_group_plan", artifact=retained_compilation.transaction_group_plan)
        replay_member = cls.atomic_member(member_id="replay-bundle", kind="bootstrap_graph_replay_bundle", artifact=replay_bundle)
        counters_member = cls.atomic_member(member_id="observed-counters", kind="bootstrap_graph_observed_counters", artifact=counters)
        progress_member = cls._progress_member(
            kind="plan_published", source_id=operation_fence_binding.source_id,
            source_digest=operation_fence_binding.source_digest,
            preparation_fingerprint=preparation_fingerprint,
            operation_id=operation_fence_binding.operation_id, inputs=inputs,
            operation_lease_binding=operation_lease_binding,
            operation_fence_binding=operation_fence_binding,
            writer_commit_binding=writer_commit_binding,
            plan_reference=cls._member_reference(repository_id="semantic_ingestion.bootstrap_graph_plan.v3", member=plan_member, artifact=retained_compilation.transaction_group_plan, payload_type="BootstrapTransactionGroupPlanV3", generation=publication_generation),
            replay_reference=cls._member_reference(repository_id="semantic_ingestion.bootstrap_graph_replay_bundle.v3", member=replay_member, artifact=replay_bundle, payload_type="BootstrapGraphReplayBundleV3", generation=publication_generation),
            counters_reference=cls._member_reference(repository_id="semantic_ingestion.bootstrap_graph_observed_counters.v3", member=counters_member, artifact=counters, payload_type="BootstrapGraphObservedCountersV3", generation=publication_generation),
            predecessor_progress_reference=predecessor_progress_reference,
            replan_closure_reference=replan_closure_reference,
        )
        members = tuple(sorted((
            cls.atomic_member(member_id="attempt-inputs", kind="bootstrap_graph_snapshot_authority", artifact=inputs),
            cls.atomic_member(member_id="compilation", kind="group_compilation_artifact", artifact=retained_compilation),
            *(cls.atomic_member(member_id=f"pre-execution-evidence:{item.transaction_group_id}", kind="bootstrap_graph_pre_execution_group_evidence", artifact=item) for item in retained_compilation.pre_execution_evidence),
            plan_member, replay_member, counters_member, progress_member,
        ), key=lambda item: item.member_id))
        return BootstrapGraphPlanAtomicWriteRequestV3.create(
            kind="bootstrap_graph_plan_checkpoint", request_digest=retained_compilation.request_digest,
            normalization_replay_digest=retained_compilation.normalization_replay_digest,
            normalization_result_digest=inputs.normalization_result_digest,
            predecessor_generation=predecessor_generation,
            operation_lease_binding=operation_lease_binding, operation_fence_binding=operation_fence_binding,
            writer_commit_binding=writer_commit_binding, control_epoch_digest=retained_compilation.control_epoch_digest,
            members=members, required_member_digests=tuple(sorted(item.member_digest for item in members)),
        )

    @staticmethod
    def initial_attempt_authority(
        *, authorizations: BootstrapGraphPlanAuthorizationSetV3,
        plan: object, request_digest: str, control_epoch_digest: str,
    ) -> BootstrapInitialAttemptAuthorityV3:
        if not BootstrapGraphArtifactAssemblerV3._authorizations_match_plan(
            authorizations=authorizations,
            plan=plan,
            request_digest=request_digest,
            control_epoch_digest=control_epoch_digest,
        ):
            raise ValueError("bootstrap graph initial authorization bijection is invalid")
        return BootstrapInitialAttemptAuthorityV3.create(
            kind="initial", planning_authorizations=authorizations.authorizations
        )

    @staticmethod
    def build_initial_attempt(
        *, inputs: BootstrapGraphAttemptConstructionInputsV3,
        authority: BootstrapInitialAttemptAuthorityV3, plan: object,
        source_dependency_group_digests: tuple[str, ...], capability_binding_digests: tuple[str, ...],
        reservation_use_authorization_digests: tuple[str, ...], operation_lease_binding_digest: str,
        operation_fence_binding_digest: str, writer_commit_binding_digest: str,
        observed_counters_digest: str,
    ) -> BootstrapGraphDependentAttemptV3:
        authorizations = authority.planning_authorizations
        if (
            not authorizations
            or tuple(item.transaction_group_id for item in authorizations)
            != tuple(member.transaction_group_id for member in plan.group_members)
            or any(
                item.request_digest != inputs.request_digest
                or item.group_plan_member_digest != member.member_digest
                or item.operation_ids != member.operation_ids
                or item.operation_plan_digests
                != tuple(operation.operation_plan_digest for operation in member.operation_plans)
                or item.graph_read_set_digest != member.graph_read_set.read_set_digest
                or item.control_epoch_digest != inputs.control_epoch_digest
                or item.operation_lease_binding_digest != operation_lease_binding_digest
                or item.operation_fence_binding_digest != operation_fence_binding_digest
                or item.writer_commit_binding_digest != writer_commit_binding_digest
                for item, member in zip(authorizations, plan.group_members, strict=True)
            )
        ):
            raise ValueError("bootstrap graph initial attempt authorization is substituted")
        return BootstrapGraphDependentAttemptV3.create(
            attempt_id=inputs.inputs_digest, attempt_index=0, trigger="initial_plan",
            attempt_context_digest=inputs.inputs_digest, request_digest=inputs.request_digest,
            normalization_replay_digest=inputs.normalization_replay_digest,
            normalization_result_digest=inputs.normalization_result_digest,
            source_alignment_digest=inputs.source_alignment_digest,
            source_dependency_group_digests=source_dependency_group_digests,
            graph_snapshot_digest=inputs.graph_snapshot_digest, sealed_read_set_digest=inputs.sealed_read_set_digest,
            read_set_extension_digests=(), reconciliation_digest=inputs.reconciliation_digest,
            reference_closure_digest=inputs.reference_closure_digest,
            capability_binding_digests=capability_binding_digests,
            reservation_use_authorization_digests=reservation_use_authorization_digests,
            transaction_group_plan_digest=plan.plan_digest, attempt_authority=authority,
            execution_policy_reference_digest=inputs.execution_policy_reference_digest,
            operation_lease_binding_digest=operation_lease_binding_digest,
            operation_fence_binding_digest=operation_fence_binding_digest,
            writer_commit_binding_digest=writer_commit_binding_digest,
            control_epoch_digest=inputs.control_epoch_digest,
            observed_counters_digest=observed_counters_digest, status="eligible",
        )

    @staticmethod
    def replacement_successor_authority(
        *,
        predecessor_attempt: BootstrapGraphDependentAttemptV3,
        predecessor_lineage: BootstrapSourcePlanLineageV3,
        predecessor_plan: object,
        predecessor_authorizations: BootstrapGraphPlanAuthorizationSetV3,
        replacement_plan: object,
        replacement_authorizations: BootstrapGraphPlanAuthorizationSetV3,
        completed_group_results: tuple[BootstrapNativeGroupCommitTerminalConstructionV3, ...] = (),
        replanned_group_ids: tuple[str, ...] | None = None,
    ) -> BootstrapSuccessorAttemptAuthorityV3:
        """Build the bounded first-conflict authority with an exact group partition."""
        latest = dict(predecessor_lineage.latest_entry_by_group)
        entries = {item.entry_digest: item for item in predecessor_lineage.entries}
        members = {item.transaction_group_id: item for item in replacement_plan.group_members}
        authorizations = {
            item.transaction_group_id: item
            for item in replacement_authorizations.authorizations
        }
        predecessor_members = {
            item.transaction_group_id: item for item in predecessor_plan.group_members
        }
        predecessor_auths = {
            item.transaction_group_id: item
            for item in predecessor_authorizations.authorizations
        }
        group_ids = tuple(replacement_plan.canonical_group_order)
        if (
            # The predecessor closure binds through lineage membership and
            # the exact group bijections below: successors chain at positive
            # indices (the design contract), so neither the attempt index
            # nor the initial trigger may gate the closure.
            predecessor_attempt.attempt_digest
            not in {item.attempt_digest for item in predecessor_lineage.entries}
            or set(group_ids) != set(latest)
            or set(group_ids) != set(members)
            or set(group_ids) != set(authorizations)
            or set(group_ids) != set(predecessor_members)
            or set(group_ids) != set(predecessor_auths)
        ):
            raise ValueError("bootstrap graph successor predecessor closure is invalid")
        completed = {item.transaction_group_id: item for item in completed_group_results}
        if not set(completed).issubset(group_ids):
            raise ValueError("bootstrap graph successor result partition is invalid")
        unfinished = tuple(group_id for group_id in group_ids if group_id not in completed)
        replanned = tuple(sorted(replanned_group_ids or unfinished))
        if not set(replanned).issubset(unfinished):
            raise ValueError("bootstrap graph replanned group partition is invalid")
        partition = BootstrapGraphReplanPartitionV3.create(
            predecessor_attempt_digest=predecessor_attempt.attempt_digest,
            predecessor_lineage_digest=predecessor_lineage.lineage_digest,
            final_group_ids=tuple(sorted(completed)),
            unfinished_group_ids=unfinished,
            replanned_group_ids=replanned,
        )
        repository_fingerprint = contract_digest(
            b"memorii.semantic-ingestion.bootstrap-source-plan-lineage-repository.v3",
            {"repository_id": "semantic_ingestion.bootstrap_source_plan_lineage.v3"},
        )
        lineage_refs = {
            group_id: BootstrapSourcePlanLineageEntryReferenceV3.create(
                    repository_id="semantic_ingestion.bootstrap_source_plan_lineage.v3",
                    entry_digest=latest[group_id],
                    artifact_digest=sha256(
                        encode_typed_value(entries[latest[group_id]].model_dump(mode="python"))
                    ).hexdigest(),
                    repository_contract_fingerprint=repository_fingerprint,
            )
            for group_id in group_ids
        }
        result_repository_fingerprint = contract_digest(
            b"memorii.semantic-ingestion.bootstrap-group-result-repository.v3",
            {"repository_id": "semantic_ingestion.bootstrap_group_result.v3"},
        )
        group_authorities = []
        for group_id in group_ids:
            if group_id in replanned:
                group_authorities.append(BootstrapReplacementGroupAuthorityV3.create(
                    kind="replacement",
                    transaction_group_id=group_id,
                    predecessor_lineage_entry=lineage_refs[group_id],
                    replacement_group_plan_member=members[group_id],
                    replacement_planning_authorization=authorizations[group_id],
                ))
                continue
            if group_id not in completed:
                group_authorities.append(BootstrapReusedUnfinishedGroupAuthorityV3.create(
                    kind="reused_unfinished",
                    transaction_group_id=group_id,
                    predecessor_lineage_entry=lineage_refs[group_id],
                    predecessor_group_plan_member=predecessor_members[group_id],
                    predecessor_planning_authorization=predecessor_auths[group_id],
                ))
                continue
            result = completed[group_id]
            result_reference = BootstrapFinalGroupResultReferenceV3.create(
                repository_id="semantic_ingestion.bootstrap_group_result.v3",
                transaction_group_id=group_id,
                result_digest=result.result_digest,
                artifact_digest=sha256(
                    encode_typed_value(result.model_dump(mode="python"))
                ).hexdigest(),
                repository_contract_fingerprint=result_repository_fingerprint,
            )
            if result.disposition == "committed":
                group_authorities.append(BootstrapReusedCommittedGroupAuthorityV3.create(
                    kind="reused_committed",
                    transaction_group_id=group_id,
                    predecessor_lineage_entry=lineage_refs[group_id],
                    predecessor_final_result=result_reference,
                    predecessor_group_plan_member=predecessor_members[group_id],
                    predecessor_planning_authorization=predecessor_auths[group_id],
                ))
            else:
                group_authorities.append(BootstrapReusedFinalGroupAuthorityV3.create(
                    kind="reused_final",
                    transaction_group_id=group_id,
                    predecessor_lineage_entry=lineage_refs[group_id],
                    predecessor_final_result=result_reference,
                    predecessor_group_plan_member=predecessor_members[group_id],
                    terminal_disposition=result.disposition,
                    planning_authorization=predecessor_auths[group_id],
                ))
        return BootstrapSuccessorAttemptAuthorityV3.create(
            kind="successor",
            predecessor_attempt_digest=predecessor_attempt.attempt_digest,
            predecessor_lineage_digest=predecessor_lineage.lineage_digest,
            replan_partition=partition,
            group_member_authorities=tuple(group_authorities),
        )

    @staticmethod
    def build_successor_attempt(
        *,
        predecessor_attempt: BootstrapGraphDependentAttemptV3,
        inputs: BootstrapGraphAttemptConstructionInputsV3,
        authority: BootstrapSuccessorAttemptAuthorityV3,
        plan: object,
        capability_binding_digests: tuple[str, ...],
        reservation_use_authorization_digests: tuple[str, ...],
        operation_lease_binding_digest: str,
        operation_fence_binding_digest: str,
        writer_commit_binding_digest: str,
        observed_counters_digest: str,
    ) -> BootstrapGraphDependentAttemptV3:
        if (
            authority.predecessor_attempt_digest != predecessor_attempt.attempt_digest
            or tuple(item.transaction_group_id for item in authority.group_member_authorities)
            != tuple(plan.canonical_group_order)
        ):
            raise ValueError("bootstrap graph successor attempt authority is substituted")
        return BootstrapGraphDependentAttemptV3.create(
            attempt_id=inputs.inputs_digest,
            attempt_index=predecessor_attempt.attempt_index + 1,
            trigger="related_version_conflict",
            attempt_context_digest=inputs.inputs_digest,
            request_digest=inputs.request_digest,
            normalization_replay_digest=inputs.normalization_replay_digest,
            normalization_result_digest=inputs.normalization_result_digest,
            source_alignment_digest=inputs.source_alignment_digest,
            source_dependency_group_digests=predecessor_attempt.source_dependency_group_digests,
            graph_snapshot_digest=inputs.graph_snapshot_digest,
            sealed_read_set_digest=inputs.sealed_read_set_digest,
            read_set_extension_digests=(),
            reconciliation_digest=inputs.reconciliation_digest,
            reference_closure_digest=inputs.reference_closure_digest,
            capability_binding_digests=capability_binding_digests,
            reservation_use_authorization_digests=reservation_use_authorization_digests,
            transaction_group_plan_digest=plan.plan_digest,
            attempt_authority=authority,
            execution_policy_reference_digest=inputs.execution_policy_reference_digest,
            operation_lease_binding_digest=operation_lease_binding_digest,
            operation_fence_binding_digest=operation_fence_binding_digest,
            writer_commit_binding_digest=writer_commit_binding_digest,
            control_epoch_digest=inputs.control_epoch_digest,
            observed_counters_digest=observed_counters_digest,
            status="eligible",
        )

    @classmethod
    def build_attempt_checkpoint(
        cls, *, attempt: BootstrapGraphDependentAttemptV3, inputs: BootstrapGraphAttemptConstructionInputsV3,
        compilation: BootstrapGraphPlanCompilationV3,
        authority: BootstrapInitialAttemptAuthorityV3, plan: object, authorizations: BootstrapGraphPlanAuthorizationSetV3,
        operation_lease_binding: object, operation_fence_binding: object, writer_commit_binding: object,
        predecessor_generation: object, preparation_fingerprint: str,
        predecessor_progress_reference: object | None = None,
        replan_closure_reference: object | None = None,
        predecessor_observed_counters: BootstrapGraphObservedCountersV3 | None = None,
    ) -> BootstrapGraphPlanAtomicWriteRequestV3:
        retained_compilation = cls._retained_compilation(compilation)
        if attempt.attempt_authority != authority:
            raise ValueError("bootstrap graph attempt checkpoint authority is substituted")
        if attempt.transaction_group_plan_digest != plan.plan_digest:
            raise ValueError("bootstrap graph attempt checkpoint plan is substituted")
        authorizations_match = (
            cls._successor_authorizations_match_plan(
                authorizations=authorizations,
                plan=plan,
                authority=authority,
                request_digest=attempt.request_digest,
                control_epoch_digest=attempt.control_epoch_digest,
            )
            if isinstance(authority, BootstrapSuccessorAttemptAuthorityV3)
            else cls._authorizations_match_plan(
                authorizations=authorizations,
                plan=plan,
                request_digest=attempt.request_digest,
                control_epoch_digest=attempt.control_epoch_digest,
            )
        )
        if not authorizations_match:
            raise ValueError("bootstrap graph attempt checkpoint authorizations are substituted")
        generation = predecessor_generation.operation_generation + 1
        replay = cls._replay_bundle(inputs)
        counters = cls._observed_counters(inputs=inputs, operation_fence_binding=operation_fence_binding, publication_generation=generation, plan=plan, attempts=attempt.attempt_index + 1, reservations=len(authorizations.authorizations), lineage_entries=0, predecessor=predecessor_observed_counters)
        authority_member = cls.atomic_member(member_id="successor-authority", kind="bootstrap_graph_successor_attempt_authority", artifact=authority)
        attempt_member = cls.atomic_member(member_id="attempt", kind="bootstrap_graph_dependent_attempt", artifact=attempt)
        plan_member = cls.atomic_member(member_id="plan", kind="bootstrap_transaction_group_plan", artifact=plan)
        replay_member = cls.atomic_member(member_id="replay-bundle", kind="bootstrap_graph_replay_bundle", artifact=replay)
        counters_member = cls.atomic_member(member_id="observed-counters", kind="bootstrap_graph_observed_counters", artifact=counters)
        progress_member = cls._progress_member(kind="attempt_published", source_id=operation_fence_binding.source_id, source_digest=operation_fence_binding.source_digest, preparation_fingerprint=preparation_fingerprint, operation_id=operation_fence_binding.operation_id, inputs=inputs, operation_lease_binding=operation_lease_binding, operation_fence_binding=operation_fence_binding, writer_commit_binding=writer_commit_binding, plan_reference=cls._member_reference(repository_id="semantic_ingestion.bootstrap_graph_plan.v3", member=plan_member, artifact=plan, payload_type="BootstrapTransactionGroupPlanV3", generation=generation), replay_reference=cls._member_reference(repository_id="semantic_ingestion.bootstrap_graph_replay_bundle.v3", member=replay_member, artifact=replay, payload_type="BootstrapGraphReplayBundleV3", generation=generation), counters_reference=cls._member_reference(repository_id="semantic_ingestion.bootstrap_graph_observed_counters.v3", member=counters_member, artifact=counters, payload_type="BootstrapGraphObservedCountersV3", generation=generation), authority_reference=cls._member_reference(repository_id="semantic_ingestion.bootstrap_graph_authority.v3", member=authority_member, artifact=authority, payload_type="BootstrapGraphAttemptAuthorityV3", generation=generation), attempt_reference=cls._member_reference(repository_id="semantic_ingestion.bootstrap_graph_attempt.v3", member=attempt_member, artifact=attempt, payload_type="BootstrapGraphDependentAttemptV3", generation=generation), predecessor_progress_reference=predecessor_progress_reference, replan_closure_reference=replan_closure_reference)
        if (
            retained_compilation.attempt_construction_inputs != inputs
            or retained_compilation.transaction_group_plan != plan
        ):
            raise ValueError("bootstrap graph retained compilation is substituted")
        artifacts = (
            ("attempt-inputs", "bootstrap_graph_snapshot_authority", inputs),
            ("compilation", "group_compilation_artifact", retained_compilation),
        )
        members = tuple(sorted((cls.atomic_member(member_id=item[0], kind=item[1], artifact=item[2]) for item in artifacts), key=lambda item: item.member_id))
        members = tuple(sorted((
            *members,
            *(cls.atomic_member(member_id=f"authorization:{item.transaction_group_id}", kind="bootstrap_group_planning_authorization", artifact=item) for item in authorizations.authorizations),
            authority_member, attempt_member, plan_member, replay_member,
            counters_member, progress_member,
        ), key=lambda item: item.member_id))
        return BootstrapGraphPlanAtomicWriteRequestV3.create(
            kind="bootstrap_graph_attempt_checkpoint", request_digest=attempt.request_digest, normalization_replay_digest=attempt.normalization_replay_digest,
            normalization_result_digest=attempt.normalization_result_digest, predecessor_generation=predecessor_generation,
            operation_lease_binding=operation_lease_binding,
            operation_fence_binding=operation_fence_binding, writer_commit_binding=writer_commit_binding,
            control_epoch_digest=attempt.control_epoch_digest, members=members,
            required_member_digests=tuple(sorted(item.member_digest for item in members)),
        )

    @staticmethod
    def build_initial_lineage(
        *, attempt: BootstrapGraphDependentAttemptV3, plan: object,
        authorizations: BootstrapGraphPlanAuthorizationSetV3, source_id: str,
        source_digest: str, preparation_fingerprint: str,
    ) -> BootstrapSourcePlanLineageV3:
        authorizations_by_group = {item.transaction_group_id: item for item in authorizations.authorizations}
        if authorizations.plan_digest != plan.plan_digest or len(authorizations_by_group) != len(plan.group_members):
            raise ValueError("bootstrap graph lineage authorization closure is invalid")
        entries = tuple(
            BootstrapSourcePlanLineageEntryV3.create(
                source_id=source_id, source_digest=source_digest, preparation_fingerprint=preparation_fingerprint,
                lineage_ordinal=index, attempt_digest=attempt.attempt_digest,
                predecessor_entry_digest=None,
                transaction_group_id=member.transaction_group_id,
                source_dependency_group_digest=member.source_dependency_group_digest,
                group_plan_member_digest=member.member_digest,
                planning_authorization_digest=authorizations_by_group[member.transaction_group_id].authorization_digest,
                predecessor_group_result_digest=None,
                disposition="planned", operation_lease_binding_digest=attempt.operation_lease_binding_digest,
                operation_fence_binding_digest=attempt.operation_fence_binding_digest,
                writer_commit_binding_digest=attempt.writer_commit_binding_digest,
                control_epoch_digest=attempt.control_epoch_digest,
            ) for index, member in enumerate(plan.group_members)
        )
        return BootstrapSourcePlanLineageV3.create(
            request_digest=attempt.request_digest, normalization_replay_digest=attempt.normalization_replay_digest,
            normalization_result_digest=attempt.normalization_result_digest,
            control_epoch_digest=attempt.control_epoch_digest, entries=entries,
            latest_entry_by_group=tuple((item.transaction_group_id, item.entry_digest) for item in entries),
        )

    @staticmethod
    def append_successor_lineage(
        *,
        predecessor: BootstrapSourcePlanLineageV3,
        attempt: BootstrapGraphDependentAttemptV3,
        plan: object,
        authorizations: BootstrapGraphPlanAuthorizationSetV3,
    ) -> BootstrapSourcePlanLineageV3:
        latest = dict(predecessor.latest_entry_by_group)
        authorization_by_group = {
            item.transaction_group_id: item for item in authorizations.authorizations
        }
        successor_execution_ids = {
            item.transaction_group_id
            for item in attempt.attempt_authority.group_member_authorities
            if item.kind == "replacement"
        }
        if (
            attempt.attempt_authority.kind != "successor"
            or attempt.attempt_authority.predecessor_lineage_digest
            != predecessor.lineage_digest
            or tuple(plan.canonical_group_order) != tuple(sorted(latest))
            or not successor_execution_ids
            or not successor_execution_ids.issubset(authorization_by_group)
        ):
            raise ValueError("bootstrap graph successor lineage inputs are substituted")
        appended = tuple(
            BootstrapSourcePlanLineageEntryV3.create(
                source_id=predecessor.entries[0].source_id,
                source_digest=predecessor.entries[0].source_digest,
                preparation_fingerprint=predecessor.entries[0].preparation_fingerprint,
                lineage_ordinal=len(predecessor.entries) + index,
                attempt_digest=attempt.attempt_digest,
                predecessor_entry_digest=latest[member.transaction_group_id],
                transaction_group_id=member.transaction_group_id,
                source_dependency_group_digest=member.source_dependency_group_digest,
                group_plan_member_digest=member.member_digest,
                planning_authorization_digest=authorization_by_group[
                    member.transaction_group_id
                ].authorization_digest,
                predecessor_group_result_digest=None,
                disposition="planned",
                operation_lease_binding_digest=attempt.operation_lease_binding_digest,
                operation_fence_binding_digest=attempt.operation_fence_binding_digest,
                writer_commit_binding_digest=attempt.writer_commit_binding_digest,
                control_epoch_digest=attempt.control_epoch_digest,
            )
            for index, member in enumerate(
                item for item in plan.group_members
                if item.transaction_group_id in successor_execution_ids
            )
        )
        entries = (*predecessor.entries, *appended)
        successor_latest = {**latest}
        successor_latest.update(
            {item.transaction_group_id: item.entry_digest for item in appended}
        )
        return BootstrapSourcePlanLineageV3.create(
            request_digest=attempt.request_digest,
            normalization_replay_digest=attempt.normalization_replay_digest,
            normalization_result_digest=attempt.normalization_result_digest,
            control_epoch_digest=attempt.control_epoch_digest,
            entries=entries,
            latest_entry_by_group=tuple(sorted(successor_latest.items())),
        )

    @classmethod
    def build_lineage_checkpoint(
        cls, *, attempt: BootstrapGraphDependentAttemptV3, lineage: BootstrapSourcePlanLineageV3,
        operation_lease_binding: object, operation_fence_binding: object,
        writer_commit_binding: object, predecessor_generation: object,
    ) -> BootstrapGraphPlanAtomicWriteRequestV3:
        if lineage.request_digest != attempt.request_digest or lineage.control_epoch_digest != attempt.control_epoch_digest:
            raise ValueError("bootstrap graph lineage checkpoint inputs are substituted")
        members = tuple(sorted((
            cls.atomic_member(member_id=f"lineage:{entry.lineage_ordinal:08d}:{entry.transaction_group_id}", kind="bootstrap_source_plan_lineage_entry", artifact=entry)
            for entry in lineage.entries
        ), key=lambda item: item.member_id))
        return BootstrapGraphPlanAtomicWriteRequestV3.create(
            kind="bootstrap_graph_lineage_checkpoint", request_digest=attempt.request_digest,
            normalization_replay_digest=attempt.normalization_replay_digest,
            normalization_result_digest=attempt.normalization_result_digest,
            predecessor_generation=predecessor_generation,
            operation_lease_binding=operation_lease_binding, operation_fence_binding=operation_fence_binding,
            writer_commit_binding=writer_commit_binding, control_epoch_digest=attempt.control_epoch_digest,
            members=members, required_member_digests=tuple(sorted(item.member_digest for item in members)),
        )

    @classmethod
    def build_authorized_lineage_checkpoint(
        cls, *, attempt: BootstrapGraphDependentAttemptV3,
        authorizations: BootstrapGraphPlanAuthorizationSetV3,
        lineage: tuple[BootstrapSourcePlanLineageEntryV3, ...], plan: object,
        compilation: BootstrapGraphPlanCompilationV3,
        inputs: BootstrapGraphAttemptConstructionInputsV3, preparation_fingerprint: str,
        pre_execution_identity_closure: BootstrapGraphPreExecutionManifestIdentityClosureV3,
        operation_lease_binding: object, operation_fence_binding: object,
        writer_commit_binding: object, predecessor_generation: object,
        predecessor_progress_reference: object | None = None,
        replan_closure_reference: object | None = None,
        predecessor_observed_counters: BootstrapGraphObservedCountersV3 | None = None,
    ) -> BootstrapGraphPlanAtomicWriteRequestV3:
        if authorizations.plan_digest != attempt.transaction_group_plan_digest or authorizations.control_epoch_digest != attempt.control_epoch_digest:
            raise ValueError("bootstrap graph authorization checkpoint inputs are substituted")
        generation = predecessor_generation.operation_generation + 1
        full_lineage = BootstrapSourcePlanLineageV3.create(request_digest=attempt.request_digest, normalization_replay_digest=attempt.normalization_replay_digest, normalization_result_digest=attempt.normalization_result_digest, control_epoch_digest=attempt.control_epoch_digest, entries=lineage, latest_entry_by_group=tuple(sorted({item.transaction_group_id: item.entry_digest for item in lineage}.items())))
        replay = cls._replay_bundle(inputs)
        counters = cls._observed_counters(inputs=inputs, operation_fence_binding=operation_fence_binding, publication_generation=generation, plan=plan, attempts=attempt.attempt_index + 1, reservations=len(authorizations.authorizations), lineage_entries=len(lineage), predecessor=predecessor_observed_counters)
        plan_member = cls.atomic_member(member_id="plan", kind="bootstrap_transaction_group_plan", artifact=plan)
        replay_member = cls.atomic_member(member_id="replay-bundle", kind="bootstrap_graph_replay_bundle", artifact=replay)
        counters_member = cls.atomic_member(member_id="observed-counters", kind="bootstrap_graph_observed_counters", artifact=counters)
        authority_member = cls.atomic_member(member_id="successor-authority", kind="bootstrap_graph_successor_attempt_authority", artifact=attempt.attempt_authority)
        attempt_member = cls.atomic_member(member_id="attempt", kind="bootstrap_graph_dependent_attempt", artifact=attempt)
        lineage_member = cls.atomic_member(member_id="lineage", kind="bootstrap_source_plan_lineage", artifact=full_lineage)
        retained_compilation = cls._retained_compilation(compilation)
        if (
            retained_compilation.attempt_construction_inputs != inputs
            or retained_compilation.transaction_group_plan != plan
            or pre_execution_identity_closure.request_digest != attempt.request_digest
            or pre_execution_identity_closure.normalization_replay_digest
            != attempt.normalization_replay_digest
            or tuple(item.core.transaction_group_id for item in pre_execution_identity_closure.identities)
            != plan.canonical_group_order
        ):
            raise ValueError("bootstrap graph retained compilation is substituted")
        inputs_member = cls.atomic_member(member_id="attempt-inputs", kind="bootstrap_graph_snapshot_authority", artifact=inputs)
        compilation_member = cls.atomic_member(member_id="compilation", kind="group_compilation_artifact", artifact=retained_compilation)
        pre_execution_member = cls.atomic_member(
            member_id="pre-execution-identity-closure",
            kind="bootstrap_graph_pre_execution_identity_closure",
            artifact=pre_execution_identity_closure,
        )
        progress_member = cls._progress_member(kind="planned", source_id=operation_fence_binding.source_id, source_digest=operation_fence_binding.source_digest, preparation_fingerprint=preparation_fingerprint, operation_id=operation_fence_binding.operation_id, inputs=inputs, operation_lease_binding=operation_lease_binding, operation_fence_binding=operation_fence_binding, writer_commit_binding=writer_commit_binding, plan_reference=cls._member_reference(repository_id="semantic_ingestion.bootstrap_graph_plan.v3", member=plan_member, artifact=plan, payload_type="BootstrapTransactionGroupPlanV3", generation=generation), replay_reference=cls._member_reference(repository_id="semantic_ingestion.bootstrap_graph_replay_bundle.v3", member=replay_member, artifact=replay, payload_type="BootstrapGraphReplayBundleV3", generation=generation), counters_reference=cls._member_reference(repository_id="semantic_ingestion.bootstrap_graph_observed_counters.v3", member=counters_member, artifact=counters, payload_type="BootstrapGraphObservedCountersV3", generation=generation), authority_reference=cls._member_reference(repository_id="semantic_ingestion.bootstrap_graph_authority.v3", member=authority_member, artifact=attempt.attempt_authority, payload_type="BootstrapGraphAttemptAuthorityV3", generation=generation), attempt_reference=cls._member_reference(repository_id="semantic_ingestion.bootstrap_graph_attempt.v3", member=attempt_member, artifact=attempt, payload_type="BootstrapGraphDependentAttemptV3", generation=generation), lineage_reference=cls._member_reference(repository_id="semantic_ingestion.bootstrap_source_plan_lineage.v3", member=lineage_member, artifact=full_lineage, payload_type="BootstrapSourcePlanLineageV3", generation=generation), pre_execution_identity_closure_reference=cls._member_reference(repository_id="semantic_ingestion.bootstrap_graph_pre_execution_identity_closure.v3", member=pre_execution_member, artifact=pre_execution_identity_closure, payload_type="BootstrapGraphPreExecutionManifestIdentityClosureV3", generation=generation), predecessor_progress_reference=predecessor_progress_reference, replan_closure_reference=replan_closure_reference)
        members = tuple(sorted((
            *(cls.atomic_member(member_id=f"authorization:{item.transaction_group_id}", kind="bootstrap_group_planning_authorization", artifact=item) for item in authorizations.authorizations),
            *(cls.atomic_member(member_id=f"lineage:{item.lineage_ordinal:08d}:{item.transaction_group_id}", kind="bootstrap_source_plan_lineage_entry", artifact=item) for item in lineage),
            inputs_member, compilation_member, pre_execution_member, plan_member, replay_member, counters_member, authority_member, attempt_member, lineage_member, progress_member,
        ), key=lambda item: item.member_id))
        return BootstrapGraphPlanAtomicWriteRequestV3.create(
            kind="bootstrap_graph_lineage_checkpoint", request_digest=attempt.request_digest,
            normalization_replay_digest=attempt.normalization_replay_digest,
            normalization_result_digest=attempt.normalization_result_digest,
            predecessor_generation=predecessor_generation,
            operation_lease_binding=operation_lease_binding, operation_fence_binding=operation_fence_binding,
            writer_commit_binding=writer_commit_binding, control_epoch_digest=attempt.control_epoch_digest,
            members=members, required_member_digests=tuple(sorted(item.member_digest for item in members)),
        )

    @staticmethod
    def build_terminal_publication_request(
        *, coordinator_request: object, control_epoch: object, final_attempt: BootstrapGraphDependentAttemptV3,
        final_plan: object, complete_lineage: object, execution_manifest: object,
        ordered_group_result_constructions: tuple[BootstrapNativeGroupCommitTerminalConstructionV3, ...],
        canonical_source_result_input: object, handoff_core: BootstrapGraphTerminalHandoffCoreV3,
        publication_intent: BootstrapGraphTerminalPublicationIntentV3,
        handoff: BootstrapGraphTerminalPersistenceHandoffV3, predecessor_generation: object,
        delivery_principal_binding_digest: str, required_outcome_scopes: object,
        operation_lease_binding: object, operation_fence_binding: object,
        writer_commit_binding: object,
    ) -> BootstrapGraphTerminalPublicationRequestV3:
        if (
            predecessor_generation.operation_generation
            != publication_intent.expected_operation_generation
            or predecessor_generation.artifact_generation
            != publication_intent.expected_artifact_generation
        ):
            raise ValueError("bootstrap graph terminal publication inputs are substituted")
        lineage_entries = {
            item.entry_digest: item for item in complete_lineage.entries
        }
        def construction_matches_lineage(
            item: BootstrapNativeGroupCommitTerminalConstructionV3,
        ) -> bool:
            entry = lineage_entries.get(item.source_plan_lineage_entry.entry_digest)
            if entry is None or entry != item.source_plan_lineage_entry:
                return False
            if entry.attempt_digest == item.attempt.attempt_digest:
                return True
            authority = next((
                value
                for value in getattr(
                    item.attempt.attempt_authority,
                    "group_member_authorities",
                    (),
                )
                if value.transaction_group_id == item.transaction_group_id
            ), None)
            return bool(
                authority is not None
                and authority.kind == "reused_unfinished"
                and authority.predecessor_lineage_entry.entry_digest
                == entry.entry_digest
                and authority.predecessor_group_plan_member
                == item.group_plan_member
                and authority.predecessor_planning_authorization
                == item.planning_authorization
            )

        constructions_match_lineage = all(
            construction_matches_lineage(item)
            for item in ordered_group_result_constructions
        )
        if (
            (
                not ordered_group_result_constructions
                and canonical_source_result_input.source_status != "failed"
            )
            or final_attempt.request_digest != handoff_core.request_digest
            or final_attempt.transaction_group_plan_digest != handoff_core.transaction_group_plan_digest
            or final_attempt.control_epoch_digest != handoff_core.control_epoch_digest
            or handoff.core != handoff_core
            or handoff.publication_intent != publication_intent
            or publication_intent.request_digest != handoff_core.request_digest
            or publication_intent.control_epoch_digest != handoff_core.control_epoch_digest
            or not constructions_match_lineage
        ):
            raise ValueError("bootstrap graph terminal publication inputs are substituted")
        return BootstrapGraphTerminalPublicationRequestV3.create(
            coordinator_request=coordinator_request, control_epoch=control_epoch,
            final_attempt=final_attempt, final_plan=final_plan, complete_lineage=complete_lineage,
            execution_manifest=execution_manifest,
            ordered_group_result_constructions=ordered_group_result_constructions,
            ordered_group_commit_reload_digests=tuple(
                item.group_commit_reload.reload_digest
                for item in ordered_group_result_constructions
            ),
            canonical_source_result_input=canonical_source_result_input,
            handoff_core=handoff_core, publication_intent=publication_intent, handoff=handoff,
            predecessor_generation=predecessor_generation,
            delivery_principal_binding_digest=delivery_principal_binding_digest, required_outcome_scopes=required_outcome_scopes,
            operation_lease_binding=operation_lease_binding, operation_fence_binding=operation_fence_binding,
            writer_commit_binding=writer_commit_binding,
        )

    @staticmethod
    def group_construction(
        *, request_digest: str, normalization_replay_digest: str,
        attempt: BootstrapGraphDependentAttemptV3,
        lineage: BootstrapSourcePlanLineageEntryV3,
        member: BootstrapTransactionGroupPlanMemberV3,
        authorization: BootstrapGroupPlanningAuthorizationV3,
        group_commit_request: object,
        group_commit_reload: BootstrapGraphGroupCommitReloadV3,
        operation_fence_binding: object,
        control_epoch: object,
    ) -> BootstrapNativeGroupCommitTerminalConstructionV3:
        from memorii.core.semantic_ingestion.contracts import (
            validate_bootstrap_native_group_commit_terminal_request_v3,
        )

        authority = next((
            item for item in getattr(
                attempt.attempt_authority, "group_member_authorities", ()
            )
            if item.transaction_group_id == member.transaction_group_id
        ), None)
        retained_unfinished = (
            authority is not None
            and authority.kind == "reused_unfinished"
            and authority.predecessor_group_plan_member == member
            and authority.predecessor_planning_authorization == authorization
            and authority.predecessor_lineage_entry.entry_digest == lineage.entry_digest
        )
        if (
            attempt.request_digest != request_digest
            or attempt.normalization_replay_digest != normalization_replay_digest
            or group_commit_reload.transaction_group_id != member.transaction_group_id
            or lineage.transaction_group_id != member.transaction_group_id
            or authorization.transaction_group_id != member.transaction_group_id
            or group_commit_reload.operation_ids != member.operation_ids
            or authorization.operation_ids != member.operation_ids
            or (
                lineage.attempt_digest != attempt.attempt_digest
                and not retained_unfinished
            )
            or group_commit_request.attempt != attempt
            or group_commit_request.group_plan_member != member
            or group_commit_request.planning_authorization != authorization
            or group_commit_request.source_plan_lineage_entry != lineage
            or group_commit_reload.request_ctv_digest
            != group_commit_request.request_ctv_digest
            or operation_fence_binding.binding_digest != attempt.operation_fence_binding_digest
            or control_epoch.epoch_digest != attempt.control_epoch_digest
        ):
            raise ValueError("bootstrap graph result construction inputs are substituted")
        construction = BootstrapNativeGroupCommitTerminalConstructionV3.create(
            request_digest=request_digest, normalization_replay_digest=normalization_replay_digest,
            attempt=attempt, source_plan_lineage_entry=lineage, group_plan_member=member,
            planning_authorization=authorization,
            group_commit_reload=group_commit_reload,
            operation_fence_binding=operation_fence_binding, control_epoch=control_epoch,
        )
        validate_bootstrap_native_group_commit_terminal_request_v3(
            construction, group_commit_request
        )
        return construction

    @staticmethod
    def group_commit_request(
        *, request: object, attempt: BootstrapGraphDependentAttemptV3,
        member: BootstrapTransactionGroupPlanMemberV3,
        authorization: BootstrapGroupPlanningAuthorizationV3,
        lineage: BootstrapSourcePlanLineageEntryV3,
        pre_execution_manifest_identity: object,
        control_epoch: object, current_generation: object,
        operation_reductions: tuple[object, ...],
    ) -> object:
        """Build the store request from already reloaded native authorities."""
        from memorii.core.semantic_ingestion.contracts import (
            BootstrapGraphGroupCommitRequestV3,
            BootstrapGraphOperationStoreMaterializationInputV3,
        )

        reductions = tuple(
            item for item in operation_reductions
            if item.transaction_group_id == member.transaction_group_id
        )
        if (
            tuple(item.operation_id for item in reductions) != member.operation_ids
            or authorization.operation_ids != member.operation_ids
            or lineage.transaction_group_id != member.transaction_group_id
            or pre_execution_manifest_identity.core.transaction_group_id
            != member.transaction_group_id
        ):
            raise ValueError("bootstrap native group commit inputs are substituted")
        plans = {item.operation_id: item for item in member.operation_plans}
        operation_inputs = tuple(
            BootstrapGraphOperationStoreMaterializationInputV3.create(
                transaction_group_id=member.transaction_group_id,
                operation_id=reduction.operation_id,
                operation_execution_id=reduction.operation_execution_id,
                operation_plan=plans[reduction.operation_id], reduction=reduction,
                planning_result=plans[reduction.operation_id].planning_result,
                reservation_use_authority=authorization.reservation_use_authority,
            )
            for reduction in reductions
        )
        return BootstrapGraphGroupCommitRequestV3.create(
            source_operation_id=control_epoch.operation_fence_binding.operation_id,
            transaction_group_id=member.transaction_group_id,
            operation_ids=member.operation_ids,
            request_digest=request.request_digest,
            normalization_replay_digest=request.normalization_replay.replay_digest,
            attempt=attempt, group_plan_member=member,
            planning_authorization=authorization,
            source_plan_lineage_entry=lineage,
            pre_execution_manifest_identity=pre_execution_manifest_identity,
            control_epoch=control_epoch,
            operation_fence_binding=control_epoch.operation_fence_binding,
            operation_lease_binding=control_epoch.operation_lease_binding,
            writer_commit_binding=control_epoch.writer_commit_binding,
            delivery_principal_binding_digest=request.delivery_principal_binding_digest,
            required_outcome_scopes=request.required_outcome_scopes,
            expected_generation=current_generation,
            ordered_operation_inputs=operation_inputs,
        )

    @classmethod
    def build_group_result_checkpoint(
        cls,
        *,
        construction: BootstrapNativeGroupCommitTerminalConstructionV3,
        attempt: BootstrapGraphDependentAttemptV3,
        operation_lease_binding: object,
        operation_fence_binding: object,
        writer_commit_binding: object,
        predecessor_generation: object,
    ) -> BootstrapGraphPlanAtomicWriteRequestV3:
        """Durably retain a completed group before another group may execute."""
        if (
            construction.request_digest != attempt.request_digest
            or construction.normalization_replay_digest
            != attempt.normalization_replay_digest
            or construction.attempt.attempt_digest != attempt.attempt_digest
            or construction.control_epoch.epoch_digest != attempt.control_epoch_digest
        ):
            raise ValueError("bootstrap graph group checkpoint inputs are substituted")
        member = cls.atomic_member(
            member_id=f"group-result:{construction.transaction_group_id}",
            kind="transaction_group_result",
            artifact=construction,
        )
        return BootstrapGraphPlanAtomicWriteRequestV3.create(
            kind="bootstrap_graph_group_result_checkpoint",
            request_digest=attempt.request_digest,
            normalization_replay_digest=attempt.normalization_replay_digest,
            normalization_result_digest=attempt.normalization_result_digest,
            predecessor_generation=predecessor_generation,
            operation_lease_binding=operation_lease_binding,
            operation_fence_binding=operation_fence_binding,
            writer_commit_binding=writer_commit_binding,
            control_epoch_digest=attempt.control_epoch_digest,
            members=(member,),
            required_member_digests=(member.member_digest,),
        )

    @staticmethod
    def durable_retry(
        *, unavailable: BootstrapGraphV3ProducerUnavailable,
        attempt: BootstrapGraphDependentAttemptV3,
        source_plan_lineage_digest: str,
        completed_group_result_digests: tuple[str, ...],
        retry_group_ids: tuple[str, ...],
        reason: str,
    ) -> BootstrapGraphDurableRetryProgressV3:
        if unavailable.request_digest != attempt.request_digest or unavailable.control_epoch_digest != attempt.control_epoch_digest:
            raise ValueError("bootstrap graph retry inputs are substituted")
        return BootstrapGraphDurableRetryProgressV3.create(
            kind="durable_retry", request_digest=attempt.request_digest,
            normalization_replay_digest=attempt.normalization_replay_digest,
            attempt_digest=attempt.attempt_digest, source_plan_lineage_digest=source_plan_lineage_digest,
            completed_group_result_digests=completed_group_result_digests,
            retry_group_ids=retry_group_ids, reason=reason,
            operation_fence_binding_digest=attempt.operation_fence_binding_digest,
            writer_commit_binding_digest=attempt.writer_commit_binding_digest,
            control_epoch_digest=attempt.control_epoch_digest,
            progress_digest=unavailable.unavailable_digest,
        )

    @classmethod
    def build_retry_checkpoint(
        cls, *, progress: BootstrapGraphDurableRetryProgressV3,
        attempt: BootstrapGraphDependentAttemptV3, operation_lease_binding: object,
        operation_fence_binding: object, writer_commit_binding: object,
        predecessor_generation: object, plan: object,
        authorizations: BootstrapGraphPlanAuthorizationSetV3,
        lineage: BootstrapSourcePlanLineageV3,
        completed_group_results: tuple[BootstrapNativeGroupCommitTerminalConstructionV3, ...],
    ) -> BootstrapGraphPlanAtomicWriteRequestV3:
        if (
            progress.attempt_digest != attempt.attempt_digest
            or plan.plan_digest != attempt.transaction_group_plan_digest
            or authorizations.plan_digest != plan.plan_digest
            or lineage.lineage_digest != progress.source_plan_lineage_digest
            or tuple(item.result_digest for item in completed_group_results)
            != progress.completed_group_result_digests
        ):
            raise ValueError("bootstrap graph retry checkpoint inputs are substituted")
        members = tuple(sorted((
            cls.atomic_member(member_id="attempt", kind="bootstrap_graph_dependent_attempt", artifact=attempt),
            cls.atomic_member(member_id="plan", kind="bootstrap_transaction_group_plan", artifact=plan),
            cls.atomic_member(member_id="retry-progress", kind="bootstrap_graph_retry_progress", artifact=progress),
            *(cls.atomic_member(member_id=f"authorization:{item.transaction_group_id}", kind="bootstrap_group_planning_authorization", artifact=item) for item in authorizations.authorizations),
            *(cls.atomic_member(member_id=f"lineage:{item.lineage_ordinal:08d}:{item.transaction_group_id}", kind="bootstrap_source_plan_lineage_entry", artifact=item) for item in lineage.entries),
            *(cls.atomic_member(member_id=f"group-result:{item.transaction_group_id}", kind="transaction_group_result", artifact=item) for item in completed_group_results),
        ), key=lambda item: item.member_id))
        return BootstrapGraphPlanAtomicWriteRequestV3.create(
            kind="bootstrap_graph_retry_checkpoint", request_digest=attempt.request_digest,
            normalization_replay_digest=attempt.normalization_replay_digest,
            normalization_result_digest=attempt.normalization_result_digest,
            predecessor_generation=predecessor_generation,
            operation_lease_binding=operation_lease_binding,
            operation_fence_binding=operation_fence_binding,
            writer_commit_binding=writer_commit_binding,
            control_epoch_digest=attempt.control_epoch_digest, members=members,
            required_member_digests=tuple(sorted(item.member_digest for item in members)),
        )


__all__ = ["BootstrapGraphArtifactAssemblerV3"]
