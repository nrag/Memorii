"""Pure native target selection used by Bootstrap graph planning V3.

This module deliberately has no store, clock, provider, or fixture dependency.
Pending planning records are authoritative over an identically keyed snapshot
record; callers must use the returned discriminated authority rather than
reconstructing a target later in the reducer.
"""

from __future__ import annotations

from memorii.core.memory_evolution.graph_planning import (
    AbsentPlanningPrecondition,
    DurablePlanningStateRecord,
    GraphPlanningDelta,
    GraphPlanningState,
    PendingPlanningStateRecord,
    PlanningGraphRecordMutation,
    PlanningSnapshotGraphRecord,
    canonical_planning_payload_from_record,
)
from memorii.core.memory_evolution.graph_records import (
    CitationRecord,
    ClaimProjection,
    EntityRevision,
    GraphReadSet,
    GraphReadSetExtension,
    GraphRecordKind,
    GraphWriteIntent,
    PlannedEntityIdentity,
    PlannedIdentityReservation,
    ProvenanceRecord,
    RelationRevision,
    graph_record_id,
)
from memorii.core.memory_evolution.semantic_state import (
    AcceptedClaimIdentity,
    ImmutableAssertionEntityRef,
    LineageEvidenceReference,
    SemanticAssertionKey,
    SemanticClaimSlotKey,
    SemanticClaimValueKey,
)
from memorii.core.memory_evolution.transaction_coordinator import SealedGraphStateSnapshot
from memorii.core.semantic_ingestion.contracts import (
    BootstrapAbsentCanonicalIdentityDecisionV3,
    BootstrapCanonicalClusterReferenceOccurrenceV3,
    BootstrapCanonicalFirstUseConsumerV3,
    BootstrapCanonicalFirstUseDependencyV3,
    BootstrapCanonicalIdentityBindingAllocationAuthorityV3,
    BootstrapCanonicalIdentityBindingAllocationReloadV3,
    BootstrapCanonicalIdentityClusterDecisionV3,
    BootstrapCanonicalIdentityDecisionProofV3,
    BootstrapCanonicalPlanningPrefixProofV3,
    BootstrapGraphTargetMaterializationPlanV3,
    BootstrapGraphTargetReferenceV3,
    BootstrapNativeEntitySeedV3,
    BootstrapNativeEvidenceProjectionV3,
    BootstrapNativeFactPlanningSeedV3,
    BootstrapNativeMentionTargetCandidateV3,
    BootstrapNativeOperationReductionInputV3,
    BootstrapNativePlanningConstructionAuthorityV3,
    BootstrapNativePlanningRecordV3,
    BootstrapNativePlanningUnavailableV3,
    BootstrapNativeTargetAuthorityV3,
    BootstrapNativeTargetBindingV3,
    BootstrapNativeTargetPlanningRequestV3,
    BootstrapNativeTargetResolutionAuthorityV3,
    BootstrapNativeTemporalTerminalBindingV3,
    BootstrapNewCanonicalIdentityAllocationV3,
    BootstrapNewFirstUseTargetAuthorityV3,
    BootstrapPendingTargetAuthorityV3,
    BootstrapProposalOperationMemberV3,
    BootstrapSnapshotTargetAuthorityV3,
    BootstrapSourceLocalIdentityResolutionV3,
    BootstrapSourceOperationMembershipV3,
    ClaimAssertion,
    contract_digest,
)


def resolve_pending_precedence_target_v3(
    *,
    record_kind: GraphRecordKind,
    record_id: str,
    planning_state: GraphPlanningState,
    sealed_snapshot_digest: str,
    effective_read_set_digest: str,
    source_local_cluster_id: str | None = None,
    source_coordinate_digest: str | None = None,
    producer_operation_execution_id: str | None = None,
    producer_membership_digest: str | None = None,
    canonical_prefix_proof: BootstrapCanonicalPlanningPrefixProofV3 | None = None,
) -> BootstrapNativeTargetAuthorityV3 | None:
    """Return the single current authority, preferring same-key pending state."""

    matches = [
        item
        for item in planning_state.records
        if (
            (item.record.payload.record_kind, item.record.record_id)
            if isinstance(item, PendingPlanningStateRecord)
            else (item.record.payload_record_kind, item.record.record_id)
        )
        == (record_kind, record_id)
    ]
    if len(matches) > 1:
        raise ValueError("native target planning state has duplicate target keys")
    if not matches:
        return None
    state_record = matches[0]
    if isinstance(state_record, PendingPlanningStateRecord):
        if None in (
            source_local_cluster_id,
            source_coordinate_digest,
            producer_operation_execution_id,
            producer_membership_digest,
            canonical_prefix_proof,
        ):
            raise ValueError("pending target requires complete first-use authority")
        target = BootstrapGraphTargetReferenceV3.create(
            record_kind=record_kind,
            record_id=record_id,
            record_digest=state_record.record.planning_record_digest,
        )
        return BootstrapPendingTargetAuthorityV3.create(
            kind="pending",
            target=target,
            source_local_cluster_id=source_local_cluster_id,
            source_coordinate_digest=source_coordinate_digest,
            producing_transaction_group_id=state_record.producing_transaction_group_id,
            producer_operation_execution_id=producer_operation_execution_id,
            producer_membership_digest=producer_membership_digest,
            canonical_prefix_proof=canonical_prefix_proof,
            planning_record_digest=state_record.record.planning_record_digest,
        )
    assert isinstance(state_record, DurablePlanningStateRecord)
    target = BootstrapGraphTargetReferenceV3.create(
        record_kind=record_kind,
        record_id=record_id,
        record_digest=state_record.record.record_digest,
    )
    return BootstrapSnapshotTargetAuthorityV3.create(
        kind="snapshot",
        target=target,
        sealed_snapshot_digest=sealed_snapshot_digest,
        effective_read_set_digest=effective_read_set_digest,
        snapshot_record_digest=state_record.record.record_digest,
    )


class BuiltInBootstrapGraphTargetMaterializationPlannerV3:
    """Pure fact-only native target/materialization owner.

    The planner consumes the sealed source construction and target authority;
    it has no store or host-policy access.  Every unsupported or incomplete
    arm remains the established zero-effect unresolved result.
    """

    def plan(
        self, *, request: BootstrapNativeTargetPlanningRequestV3
    ) -> BootstrapGraphTargetMaterializationPlanV3 | BootstrapNativePlanningUnavailableV3:
        operation = request.operation_input
        if (
            operation.operation_member.kind == "fact"
            and operation.operation_member.object.kind == "entity"
            and operation.planning_construction_authority is not None
        ):
            return self._plan_entity_fact(request=request)
        return BootstrapNativePlanningUnavailableV3.create(
            request_digest=request.request_digest,
            transaction_group_id=request.transaction_group_id,
            operation_execution_id=operation.operation_execution_id,
            operation_id=operation.operation_id,
            proposal_digest=operation.normalized_proposal.proposal_digest,
            status="unresolved",
            reason_codes=("graph_target_missing",),
            sealed_snapshot_digest=request.sealed_snapshot.snapshot_digest,
            effective_read_set_digest=request.effective_read_set.read_set_digest,
            planning_state_before_digest=request.current_planning_state.state_digest,
        )

    def _plan_entity_fact(
        self, *, request: BootstrapNativeTargetPlanningRequestV3,
    ) -> BootstrapGraphTargetMaterializationPlanV3 | BootstrapNativePlanningUnavailableV3:
        operation = request.operation_input
        fact = operation.operation_member
        assert fact.kind == "fact" and fact.object.kind == "entity"
        authority = operation.planning_construction_authority
        assert authority is not None
        candidates = {item.mention_digest: item for item in request.target_resolution_authority.mention_candidates}
        subject_candidate = candidates.get(fact.subject_mention_digest)
        object_candidate = candidates.get(fact.object.mention_digest)
        if subject_candidate is None or object_candidate is None:
            return self._unavailable(request=request, reason="graph_target_missing")
        if len(candidates) != len(request.target_resolution_authority.mention_candidates):
            return self._unavailable(request=request, reason="graph_target_ambiguous")
        subject = BootstrapNativeTargetBindingV3.create(
            role="fact_subject", source_coordinate_digest=_mention_coordinate(
                operation=operation, path="fact.subject", mention=fact.subject_mention_digest
            ), authority=subject_candidate.target_authority,
        )
        object_target = BootstrapNativeTargetBindingV3.create(
            role="fact_object", source_coordinate_digest=_mention_coordinate(
                operation=operation, path="fact.object", mention=fact.object.mention_digest
            ), authority=object_candidate.target_authority,
        )
        temporal = _one_assertion_temporal(authority)
        records: list[BootstrapNativePlanningRecordV3] = []
        created: list[BootstrapNativeEntitySeedV3] = []
        for candidate in (subject_candidate, object_candidate):
            if candidate.target_authority.kind != "new_first_use":
                continue
            decision = next(
                item for item in request.target_resolution_authority.canonical_identity_authority.authority.cluster_decisions
                if item.decision_digest == candidate.canonical_identity_decision_digest
            )
            if decision.kind != "new":
                return self._unavailable(request=request, reason="reference_closure_incomplete")
            entity = EntityRevision.create(
                operation_id=operation.operation_id,
                record_version=1,
                codec_fingerprint=_codec(authority, "entity_revision"),
                entity_revision_id=candidate.entity_revision_id,
                logical_entity_id=candidate.logical_entity_id,
                lifecycle="active",
                source_evidence=tuple(
                    LineageEvidenceReference(
                        source_id=item.source_span.source_id,
                        start=item.source_span.projection_span.start,
                        end=item.source_span.projection_span.end,
                        evidence_digest=item.evidence_digest,
                    )
                    for item in authority.evidence_constructions
                    if item.evidence_item_digest in decision.proof.alias_proof_digests
                ),
            )
            entity_record = _planning_record(
                operation=operation, group_id=request.transaction_group_id, record=entity,
            )
            records.append(entity_record)
            created.append(BootstrapNativeEntitySeedV3.create(
                kind="entity", source_local_cluster_id=candidate.source_local_cluster_id,
                mention_digests=decision.proof.mention_digests,
                canonical_identity_decision_digest=decision.decision_digest,
                canonical_identity_proof_digest=decision.proof.proof_digest,
                seed_producer_operation_execution_id=decision.seed_producer_operation_execution_id,
                seed_producer_source_coordinate_digest=decision.seed_producer_source_coordinate_digest,
                logical_entity_id=candidate.logical_entity_id,
                entity_revision_id=candidate.entity_revision_id,
                entity_revision=entity_record.planning_payload,
                aliases=(), type_evidence=(),
                alias_type_proof_digest=contract_digest(
                    b"memorii.bootstrap-graph.native-entity-alias-type-proof.v3",
                    decision.decision_digest,
                ),
            ))
        claim_id = contract_digest(
            b"memorii.bootstrap-graph.native-fact-claim.v3",
            (operation.operation_execution_id, fact.fact_digest),
        )
        claim = _claim_assertion(
            operation=operation, fact=fact, claim_id=claim_id, authority=authority,
            temporal=temporal, subject=subject_candidate, object_target=object_candidate,
            target_resolution_authority=request.target_resolution_authority,
        )
        claim_record = _planning_record(operation=operation, group_id=request.transaction_group_id, record=claim)
        projection = ClaimProjection.create(
            operation_id=operation.operation_id, codec_fingerprint=_codec(authority, "claim_projection"),
            claim_projection_id=contract_digest(b"memorii.bootstrap-graph.native-fact-projection.v3", claim_id),
            claim_assertion_id=claim_id,
            subject_entity_revision_id=subject_candidate.entity_revision_id,
            subject_logical_entity_id=subject_candidate.logical_entity_id,
            object_entity_revision_id=object_candidate.entity_revision_id,
            object_logical_entity_id=object_candidate.logical_entity_id,
        )
        projection_record = _planning_record(operation=operation, group_id=request.transaction_group_id, record=projection)
        relation = RelationRevision.create(
            operation_id=operation.operation_id, codec_fingerprint=_codec(authority, "relation_revision"),
            relation_revision_id=contract_digest(b"memorii.bootstrap-graph.native-fact-relation.v3", claim_id),
            subject_entity_revision_id=subject_candidate.entity_revision_id,
            subject_logical_entity_id=subject_candidate.logical_entity_id,
            object_entity_revision_id=object_candidate.entity_revision_id,
            object_logical_entity_id=object_candidate.logical_entity_id,
            predicate_id=fact.predicate_id,
        )
        relation_record = _planning_record(operation=operation, group_id=request.transaction_group_id, record=relation)
        records.extend((claim_record, projection_record, relation_record))
        citations = []
        provenances = []
        evidence_projections = []
        for evidence in authority.evidence_constructions:
            citation = CitationRecord.create(
                operation_id=operation.operation_id, codec_fingerprint=_codec(authority, "citation"),
                citation_id=evidence.citation_id, cited_record_id=claim_id,
            )
            provenance = ProvenanceRecord.create(
                operation_id=operation.operation_id, codec_fingerprint=_codec(authority, "provenance"),
                provenance_id=evidence.provenance_id, source_id=operation.source_id,
            )
            citation_record = _planning_record(operation=operation, group_id=request.transaction_group_id, record=citation)
            provenance_record = _planning_record(operation=operation, group_id=request.transaction_group_id, record=provenance)
            records.extend((citation_record, provenance_record))
            citations.append(citation_record.planning_payload)
            provenances.append(provenance_record.planning_payload)
            evidence_projections.append(BootstrapNativeEvidenceProjectionV3.create(
                operation_execution_id=operation.operation_execution_id,
                evidence_item_digest=evidence.evidence_item_digest,
                citation_record=citation_record, provenance_record=provenance_record,
            ))
        terminal = BootstrapNativeTemporalTerminalBindingV3.create(
            operation_execution_id=operation.operation_execution_id, operation_id=operation.operation_id,
            temporal_role="assertion", temporal_consensus_digest=temporal.temporal_consensus_digest,
            planning_record_digest=claim_record.record_digest,
        )
        records = sorted(records, key=lambda item: (item.record_kind, item.record_id, item.record_digest))
        after = _fold_state(
            state=request.current_planning_state, group_id=request.transaction_group_id,
            records=tuple(records), authority=authority,
        )
        seed = BootstrapNativeFactPlanningSeedV3.create(
            kind="fact", fact=fact, subject_target=subject, object_target=object_target,
            created_entities=tuple(sorted(created, key=lambda item: item.entity_revision_id)),
            claim_assertion=claim_record.planning_payload,
            claim_projection=projection_record.planning_payload,
            relation_revision=relation_record.planning_payload,
            citations=tuple(citations), provenances=tuple(provenances), terminal_bindings=(terminal,),
        )
        return BootstrapGraphTargetMaterializationPlanV3.create(
            request_digest=request.request_digest, transaction_group_id=request.transaction_group_id,
            operation_execution_id=operation.operation_execution_id, operation_id=operation.operation_id,
            proposal_digest=operation.normalized_proposal.proposal_digest, operation_kind="fact",
            sealed_snapshot_digest=request.sealed_snapshot.snapshot_digest,
            effective_read_set_digest=request.effective_read_set.read_set_digest,
            planning_state_before_digest=request.current_planning_state.state_digest,
            target_bindings=(subject, object_target), operation_seed=seed,
            planning_records=tuple(records), terminal_bindings=(terminal,),
            evidence_projections=tuple(evidence_projections), identity_materialization=None,
            planning_state_after=after,
        )

    @staticmethod
    def _unavailable(*, request: BootstrapNativeTargetPlanningRequestV3, reason: str) -> BootstrapNativePlanningUnavailableV3:
        operation = request.operation_input
        return BootstrapNativePlanningUnavailableV3.create(
            request_digest=request.request_digest, transaction_group_id=request.transaction_group_id,
            operation_execution_id=operation.operation_execution_id, operation_id=operation.operation_id,
            proposal_digest=operation.normalized_proposal.proposal_digest, status="unresolved",
            reason_codes=(reason,), sealed_snapshot_digest=request.sealed_snapshot.snapshot_digest,
            effective_read_set_digest=request.effective_read_set.read_set_digest,
            planning_state_before_digest=request.current_planning_state.state_digest,
        )


def _codec(authority: BootstrapNativePlanningConstructionAuthorityV3, kind: GraphRecordKind) -> str:
    entries = tuple(item for item in authority.planning_codec_entries if item.record_kind == kind)
    if len(entries) != 1:
        raise ValueError("native fact planning codec authority is incomplete")
    return entries[0].codec_fingerprint


def _planning_codec(authority: BootstrapNativePlanningConstructionAuthorityV3, kind: GraphRecordKind) -> str:
    entries = tuple(item for item in authority.planning_codec_entries if item.record_kind == kind)
    if len(entries) != 1:
        raise ValueError("native fact planning codec authority is incomplete")
    return entries[0].planning_projection_codec_fingerprint


def _planning_schema(authority: BootstrapNativePlanningConstructionAuthorityV3, kind: GraphRecordKind) -> str:
    entries = tuple(item for item in authority.planning_codec_entries if item.record_kind == kind)
    if len(entries) != 1:
        raise ValueError("native fact planning codec authority is incomplete")
    return entries[0].planning_projection_schema_fingerprint


def _mention_coordinate(*, operation: BootstrapNativeOperationReductionInputV3, path: str, mention: str) -> str:
    return contract_digest(
        b"memorii.bootstrap-graph.cluster-reference-coordinate.v3",
        {"operation_member_digest": operation.operation_subject.member_digest, "path": path, "mention_digest": mention},
    )


def _one_assertion_temporal(authority: BootstrapNativePlanningConstructionAuthorityV3):
    rows = tuple(item for item in authority.temporal_constructions if item.temporal_role == "assertion")
    if len(rows) != 1:
        raise ValueError("native fact planning temporal construction is incomplete")
    return rows[0]


def _claim_assertion(*, operation, fact, claim_id: str, authority, temporal, subject, object_target, target_resolution_authority):
    canonical = target_resolution_authority.canonical_identity_authority.authority
    decisions = tuple(
        item for item in canonical.cluster_decisions
        if item.decision_digest in {
            subject.canonical_identity_decision_digest,
            object_target.canonical_identity_decision_digest,
        }
    )
    if (
        len(decisions) != 2
        or any(
            item.proof.required_scope_set_digest != authority.required_scope_set_digest
            or item.proof.authorized_scope_identity != canonical.authorized_scope_identity
            or item.proof.sealed_snapshot_digest != canonical.sealed_snapshot_digest
            for item in decisions
        )
    ):
        raise ValueError("native fact claim identity authority is incomplete")
    claim_identity = AcceptedClaimIdentity(
        subject_assertion_ref=ImmutableAssertionEntityRef(
            entity_revision_id=subject.entity_revision_id,
            logical_entity_id_at_assertion=subject.logical_entity_id,
        ),
        object_assertion_ref=ImmutableAssertionEntityRef(
            entity_revision_id=object_target.entity_revision_id,
            logical_entity_id_at_assertion=object_target.logical_entity_id,
        ),
        assertion_key_at_recording=SemanticAssertionKey(
            slot=SemanticClaimSlotKey(
                subject_logical_entity_id=subject.logical_entity_id,
                predicate_id=fact.predicate_id,
                scope_identity=canonical.authorized_scope_identity,
                qualifier_partition=(),
            ),
            value=SemanticClaimValueKey(
                object_kind="entity",
                object_logical_entity_id=object_target.logical_entity_id,
                value_policy_fingerprint=authority.predicate_state_rule.policy_fingerprint,
            ),
        ),
        predicate_state_rule=authority.predicate_state_rule,
        identity_lineage_snapshot_digest=canonical.sealed_snapshot_digest,
    )
    body = {
        "record_kind": "claim_assertion", "operation_id": operation.operation_id,
        "record_version": 1,
        "codec_fingerprint": _codec(authority, "claim_assertion"), "claim_assertion_id": claim_id,
        "statement_digest": fact.fact_digest,
        "valid_interval": temporal.accepted_temporal_evidence.valid_interval,
        "temporal_evidence": temporal.accepted_temporal_evidence,
        "temporal_decision_binding": temporal.temporal_decision_binding,
        "claim_identity": claim_identity,
        "source_authority_evidence": authority.source_authority_evidence,
        "predicate_trust_rule": authority.predicate_trust_rule,
    }
    provisional = ClaimAssertion.model_construct(**body, record_digest="0" * 64)
    digest_body = provisional.model_dump(mode="python", exclude={"record_digest"})
    return ClaimAssertion.model_validate(body | {
        "record_digest": contract_digest(b"memorii.semantic-ingestion.temporal-carrier.v1", digest_body)
    })


def _planning_record(*, operation, group_id: str, record) -> BootstrapNativePlanningRecordV3:
    payload = canonical_planning_payload_from_record(record, transaction_group_id=group_id)
    return BootstrapNativePlanningRecordV3.create(
        operation_execution_id=operation.operation_execution_id, record_kind=record.record_kind,
        record_id=graph_record_id(record), precondition=AbsentPlanningPrecondition(), planning_payload=payload,
        source_member_digest=operation.operation_subject.member_digest,
    )


def _fold_state(*, state: GraphPlanningState, group_id: str, records: tuple[BootstrapNativePlanningRecordV3, ...], authority: BootstrapNativePlanningConstructionAuthorityV3) -> GraphPlanningState:
    mutations = tuple(sorted((
            PlanningGraphRecordMutation.create(
            mutation_kind="create", record_kind=record.record_kind, record_id=record.record_id,
            before=record.precondition,
            after_planning_record=PlanningSnapshotGraphRecord.create(
                record_id=record.record_id, record_version=record.planning_payload.planning_record["record_version"],
                payload=record.planning_payload,
                planning_projection_codec_fingerprint=_planning_codec(authority, record.record_kind),
                planning_projection_schema_fingerprint=_planning_schema(authority, record.record_kind),
            ),
        ) for record in records
    ), key=lambda item: (item.record_kind, item.record_id)))
    return state.apply(GraphPlanningDelta.create(
        sequence=len(state.applied_planned_delta_digests) + 1,
        base_state_digest=state.state_digest, producing_transaction_group_id=group_id,
        mutations=mutations,
    ))


class BootstrapCanonicalIdentityBindingAllocationProjectorV3:
    """Pure v69-v74 source-wide canonical allocation authority projector.

    All authority inputs are explicit.  A caller persists the returned object
    through its dedicated repository before any per-operation target plan may
    use it; this class performs no lookup and cannot allocate from a clock.
    """

    def project(
        self,
        *,
        operation_inputs: tuple[BootstrapNativeOperationReductionInputV3, ...],
        recovery_key_digest: str,
        sealed_snapshot: SealedGraphStateSnapshot,
        effective_read_set: GraphReadSet,
        current_planning_state: GraphPlanningState,
        required_scope_set_digest: str,
        authorized_scope_identity: str,
        allocation_namespace_id: str,
        allocation_policy_fingerprint: str,
        allow_new_allocation: bool,
        source_plan_checkpoint_digest: str,
        publication_generation_digest: str,
    ) -> BootstrapCanonicalIdentityBindingAllocationReloadV3:
        if not operation_inputs:
            raise ValueError("canonical identity authority requires source operations")
        first = operation_inputs[0]
        if (
            any(
                (item.source_id, item.source_digest, item.preparation_fingerprint)
                != (first.source_id, first.source_digest, first.preparation_fingerprint)
                for item in operation_inputs
            )
            or effective_read_set.read_set_digest != sealed_snapshot.canonical_graph.read_set.read_set_digest
            or current_planning_state.base_snapshot_digest != sealed_snapshot.snapshot_digest
        ):
            raise ValueError("canonical identity authority source/state is substituted")
        referenced = _referenced_clusters(first.source_local_identity, operation_inputs)
        proofs = {
            cluster.cluster_id: BootstrapCanonicalIdentityDecisionProofV3.create(
                source_id=first.source_id,
                source_digest=first.source_digest,
                preparation_fingerprint=first.preparation_fingerprint,
                source_local_cluster_id=cluster.cluster_id,
                mention_digests=cluster.mention_digests,
                required_scope_set_digest=required_scope_set_digest,
                authorized_scope_identity=authorized_scope_identity,
                sealed_snapshot_digest=sealed_snapshot.snapshot_digest,
                effective_read_set_digest=effective_read_set.read_set_digest,
                authority_base_planning_state_digest=current_planning_state.state_digest,
                identity_partition_evidence_digest=first.identity_partition_evidence.evidence_digest,
                source_local_resolution_digest=first.source_local_identity.resolution_digest,
                alias_proof_digests=tuple(item.item_digest for item in cluster.source_evidence),
                type_proof_digests=(),
            )
            for cluster in referenced
        }
        memberships, dependencies = derive_source_memberships_and_dependencies_v3(
            operation_inputs=operation_inputs,
            proof_digest_by_cluster={key: value.proof_digest for key, value in proofs.items()},
        )
        dependency_by_cluster = {item.source_local_cluster_id: item for item in dependencies}
        decisions = []
        for cluster in referenced:
            proof = proofs[cluster.cluster_id]
            dependency = dependency_by_cluster[cluster.cluster_id]
            if cluster.decision == "unresolved" or not allow_new_allocation:
                decisions.append(BootstrapAbsentCanonicalIdentityDecisionV3.create(
                    kind="absent", proof=proof,
                    reason="no_binding_proof" if cluster.decision == "unresolved" else "allocation_forbidden",
                ))
                continue
            producer = dependency.producer_membership
            producer_coordinate = dependency.producer_occurrences[0].source_coordinate_digest
            alias_proofs = (
                cluster.source_evidence
                if cluster.proof_kind in {"explicit_alias", "explicit_apposition", "authenticated_external_id"}
                else ()
            )
            allocation_key = contract_digest(
                b"memorii.bootstrap-graph.canonical-cluster-allocation.v3",
                {
                    "source_id": first.source_id,
                    "source_digest": first.source_digest,
                    "preparation_fingerprint": first.preparation_fingerprint,
                    "recovery_key_digest": recovery_key_digest,
                    "allocation_namespace_id": allocation_namespace_id,
                    "authorized_scope_identity": authorized_scope_identity,
                    "cluster_id": cluster.cluster_id,
                    "mention_digests": cluster.mention_digests,
                    "alias_proof_digests": tuple(item.item_digest for item in alias_proofs),
                    "type_proof_digests": (),
                },
            )
            logical_id = contract_digest(b"memorii.bootstrap-graph.canonical-logical-entity.v3", allocation_key)
            entity_id = contract_digest(b"memorii.bootstrap-graph.canonical-entity-revision.v3", allocation_key)
            identity = PlannedEntityIdentity(
                allocation_key=allocation_key,
                entity_revision_id=entity_id,
                logical_entity_id=logical_id,
                allocation_namespace_id=allocation_namespace_id,
                allocation_policy_fingerprint=allocation_policy_fingerprint,
            )
            record_keys = tuple(sorted((f"entity_revision:{entity_id}", f"logical_entity:{logical_id}")))
            extension = GraphReadSetExtension.create(
                snapshot_token=sealed_snapshot.canonical_graph.snapshot_token,
                graph_revision=sealed_snapshot.graph_state.graph_revision,
                segment_governance_binding_digests=tuple(sorted({
                    binding.binding_digest
                    for operation in operation_inputs
                    if operation.planning_construction_authority is not None
                    for binding in operation.planning_construction_authority.segment_governance.segment_governance_bindings
                })),
                operation_fence_id=first.graph_free_identity_input.operation_fence_binding_digest if first.graph_free_identity_input else first.operation_execution_id,
                issuer_repository_id=sealed_snapshot.graph_state.repository_id,
                issuer_contract_fingerprint=allocation_policy_fingerprint,
                dependency_kind="identity_allocation",
                record_keys=record_keys,
                partition_versions=sealed_snapshot.canonical_graph.read_set.partition_versions,
                manifest_fingerprints=(allocation_policy_fingerprint,),
            )
            reservation = PlannedIdentityReservation.create(
                planned_identity=identity,
                collision_read_set_extension=extension,
                expected_absent_write_intents=tuple(GraphWriteIntent(record_key=key) for key in record_keys),
            )
            decisions.append(BootstrapNewCanonicalIdentityAllocationV3.create(
                kind="new", proof=proof, allocation_namespace_id=allocation_namespace_id,
                allocation_policy_fingerprint=allocation_policy_fingerprint,
                allocation_key=allocation_key, logical_entity_id=logical_id,
                entity_revision_id=entity_id, alias_proofs=alias_proofs, type_proofs=(),
                planned_identity_reservation=reservation,
                seed_producer_operation_execution_id=producer.operation_execution_id,
                seed_producer_source_coordinate_digest=producer_coordinate,
                allocation_proof_digest=contract_digest(
                    b"memorii.bootstrap-graph.canonical-allocation-proof.v3", proof
                ),
            ))
        authority = BootstrapCanonicalIdentityBindingAllocationAuthorityV3.create(
            source_id=first.source_id, source_digest=first.source_digest,
            preparation_fingerprint=first.preparation_fingerprint,
            recovery_key_digest=recovery_key_digest,
            sealed_snapshot_digest=sealed_snapshot.snapshot_digest,
            effective_read_set_digest=effective_read_set.read_set_digest,
            authority_base_planning_state_digest=current_planning_state.state_digest,
            required_scope_set_digest=required_scope_set_digest,
            authorized_scope_identity=authorized_scope_identity,
            allocation_namespace_id=allocation_namespace_id,
            source_operation_memberships=memberships,
            referenced_cluster_ids=tuple(cluster.cluster_id for cluster in referenced),
            cluster_decisions=tuple(decisions),
            first_use_dependencies=dependencies,
        )
        return BootstrapCanonicalIdentityBindingAllocationReloadV3.create(
            authority=authority,
            source_plan_checkpoint_digest=source_plan_checkpoint_digest,
            publication_generation_digest=publication_generation_digest,
        )


class BootstrapNativeTargetResolutionProjectorV3:
    """Project one operation's mention targets from the sealed canonical reload."""

    def project(
        self,
        *,
        operation_input: BootstrapNativeOperationReductionInputV3,
        transaction_group_id: str,
        sealed_snapshot: SealedGraphStateSnapshot,
        effective_read_set: GraphReadSet,
        current_planning_state: GraphPlanningState,
        canonical_identity_authority: BootstrapCanonicalIdentityBindingAllocationReloadV3,
    ) -> BootstrapNativeTargetResolutionAuthorityV3:
        authority = canonical_identity_authority.authority
        membership = next(
            (
                item for item in authority.source_operation_memberships
                if item.operation_execution_id == operation_input.operation_execution_id
            ),
            None,
        )
        if membership is None or membership.transaction_group_id != transaction_group_id:
            raise ValueError("target projection operation membership is absent")
        prefix = BootstrapCanonicalPlanningPrefixProofV3.create(
            authority_base_planning_state_digest=authority.authority_base_planning_state_digest,
            membership=membership,
            preceding_memberships=tuple(
                item for item in authority.source_operation_memberships
                if item.operation_ordinal < membership.operation_ordinal
            ),
            prefix_planning_state_digest=current_planning_state.state_digest,
            required_producer_record_digests=(),
        )
        cluster_by_mention = {
            mention: cluster.cluster_id
            for cluster in operation_input.source_local_identity.clusters
            for mention in cluster.mention_digests
        }
        decision_by_cluster = {
            item.proof.source_local_cluster_id: item
            for item in authority.cluster_decisions
        }
        dependency_by_cluster = {
            item.source_local_cluster_id: item for item in authority.first_use_dependencies
        }
        candidates = []
        for path, mention in _operation_mention_occurrences(operation_input.operation_member):
            cluster_id = cluster_by_mention.get(mention)
            if cluster_id is None:
                continue
            decision = decision_by_cluster.get(cluster_id)
            dependency = dependency_by_cluster.get(cluster_id)
            if decision is None or dependency is None:
                raise ValueError("target projection canonical decision is absent")
            coordinate = contract_digest(
                b"memorii.bootstrap-graph.cluster-reference-coordinate.v3",
                {"operation_member_digest": membership.operation_member_digest, "path": path, "mention_digest": mention},
            )
            target_authority, logical_id, entity_id = self._target_for_decision(
                decision=decision, dependency=dependency, membership=membership,
                coordinate=coordinate, prefix=prefix, planning_state=current_planning_state,
                sealed_snapshot_digest=sealed_snapshot.snapshot_digest,
                effective_read_set_digest=effective_read_set.read_set_digest,
            )
            candidates.append(BootstrapNativeMentionTargetCandidateV3.create(
                mention_digest=mention, source_local_cluster_id=cluster_id,
                canonical_identity_decision_digest=decision.decision_digest,
                canonical_identity_proof_digest=decision.proof.proof_digest,
                target_authority=target_authority, logical_entity_id=logical_id,
                entity_revision_id=entity_id, alias_record_ids=(), type_evidence_record_ids=(),
            ))
        return BootstrapNativeTargetResolutionAuthorityV3.create(
            source_id=operation_input.source_id, source_digest=operation_input.source_digest,
            preparation_fingerprint=operation_input.preparation_fingerprint,
            operation_execution_id=operation_input.operation_execution_id,
            sealed_snapshot_digest=sealed_snapshot.snapshot_digest,
            effective_read_set_digest=effective_read_set.read_set_digest,
            canonical_prefix_proof=prefix,
            canonical_identity_authority=canonical_identity_authority,
            mention_candidates=tuple(sorted(candidates, key=lambda item: (item.mention_digest, item.candidate_digest))),
            selector_targets=(),
        )

    @staticmethod
    def _target_for_decision(
        *,
        decision: BootstrapCanonicalIdentityClusterDecisionV3,
        dependency: BootstrapCanonicalFirstUseDependencyV3,
        membership: BootstrapSourceOperationMembershipV3,
        coordinate: str,
        prefix: BootstrapCanonicalPlanningPrefixProofV3, planning_state: GraphPlanningState,
        sealed_snapshot_digest: str, effective_read_set_digest: str,
    ) -> tuple[BootstrapNativeTargetAuthorityV3, str, str]:
        if decision.kind == "absent":
            raise ValueError("canonical identity decision is absent")
        if decision.kind == "existing":
            return decision.snapshot_or_pending_authority, decision.target.record_id, decision.target.record_id
        assert decision.kind == "new"
        target = BootstrapGraphTargetReferenceV3.create(
            record_kind="entity_revision", record_id=decision.entity_revision_id,
            record_digest=decision.decision_digest,
        )
        if membership.operation_execution_id == decision.seed_producer_operation_execution_id:
            return (
                BootstrapNewFirstUseTargetAuthorityV3.create(
                    kind="new_first_use", target=target,
                    source_local_cluster_id=decision.proof.source_local_cluster_id,
                    source_coordinate_digest=coordinate,
                    canonical_identity_decision_digest=decision.decision_digest,
                    planned_identity_reservation_digest=decision.planned_identity_reservation.reservation_digest,
                    seed_producer_operation_execution_id=decision.seed_producer_operation_execution_id,
                    seed_producer_source_coordinate_digest=decision.seed_producer_source_coordinate_digest,
                    seed_producer_transaction_group_id=membership.transaction_group_id,
                    seed_producer_membership_digest=membership.membership_digest,
                    canonical_prefix_proof=prefix,
                ), decision.logical_entity_id, decision.entity_revision_id,
            )
        # Consumers must find the producer's pending entity record in the
        # caller-supplied planning state; there is no synthetic pending arm.
        pending = resolve_pending_precedence_target_v3(
            record_kind="entity_revision", record_id=decision.entity_revision_id,
            planning_state=planning_state, sealed_snapshot_digest=sealed_snapshot_digest,
            effective_read_set_digest=effective_read_set_digest,
            source_local_cluster_id=decision.proof.source_local_cluster_id,
            source_coordinate_digest=coordinate,
            producer_operation_execution_id=decision.seed_producer_operation_execution_id,
            producer_membership_digest=dependency.producer_membership.membership_digest,
            canonical_prefix_proof=prefix,
        )
        if not isinstance(pending, BootstrapPendingTargetAuthorityV3):
            raise ValueError("new identity consumer has no pending producer target")
        return pending, decision.logical_entity_id, decision.entity_revision_id


def _unavailable_reason(operation: BootstrapNativeOperationReductionInputV3) -> str:
    # Keep the check intentionally structural: a later planner must not infer
    # missing coverage or consensus through a provider call.
    coverage = operation.coverage_bindings
    if not coverage or any(item.disposition.kind == "unresolved" for item in coverage):
        return "coverage_unresolved"
    if operation.parser_consensus.status != "stable":
        return "parser_disagreement"
    if operation.scope_consensus.status != "stable":
        return "scope_disagreement"
    if not operation.temporal_consensus_set.role_consensus_digests:
        return "temporal_disagreement"
    return "graph_target_missing"


__all__ = [
    "BuiltInBootstrapGraphTargetMaterializationPlannerV3",
    "BootstrapCanonicalIdentityBindingAllocationProjectorV3",
    "BootstrapNativeTargetResolutionProjectorV3",
    "derive_source_memberships_and_dependencies_v3",
    "resolve_pending_precedence_target_v3",
]


def derive_source_memberships_and_dependencies_v3(
    *,
    operation_inputs: tuple[BootstrapNativeOperationReductionInputV3, ...],
    proof_digest_by_cluster: dict[str, str] | None = None,
) -> tuple[
    tuple[BootstrapSourceOperationMembershipV3, ...],
    tuple[BootstrapCanonicalFirstUseDependencyV3, ...],
]:
    """Derive the v72-v74 source order and first-use graph from retained bytes.

    No graph target, allocation, or plan artifact participates in this pass.
    That keeps the first-use order acyclic and makes repeated occurrences of a
    mention visible before canonical identity decisions are made.
    """

    if not operation_inputs:
        raise ValueError("source membership derivation requires native operations")
    ordered = tuple(
        sorted(
            operation_inputs,
            key=lambda item: (
                item.dependency_group.group_id,
                item.operation_id,
            ),
        )
    )
    if ordered != operation_inputs:
        raise ValueError("native operation inputs are not in canonical source order")
    group_ordinals = {
        group_id: ordinal
        for ordinal, group_id in enumerate(
            sorted({item.dependency_group.group_id for item in ordered})
        )
    }
    memberships = tuple(
        BootstrapSourceOperationMembershipV3.create(
            source_id=item.source_id,
            source_digest=item.source_digest,
            preparation_fingerprint=item.preparation_fingerprint,
            source_dependency_group_id=item.dependency_group.group_id,
            dependency_group_ordinal=group_ordinals[item.dependency_group.group_id],
            transaction_group_id=item.dependency_group.group_id,
            operation_id=item.operation_id,
            operation_execution_id=item.operation_execution_id,
            operation_ordinal=index,
            operation_member_digest=item.operation_subject.member_digest,
        )
        for index, item in enumerate(ordered)
    )
    cluster_by_mention = {
        mention: cluster.cluster_id
        for cluster in ordered[0].source_local_identity.clusters
        for mention in cluster.mention_digests
        if cluster.decision != "unresolved"
    }
    occurrences: dict[str, list[BootstrapCanonicalClusterReferenceOccurrenceV3]] = {}
    for item, membership in zip(ordered, memberships, strict=True):
        for path, mention_digest in _operation_mention_occurrences(item.operation_member):
            cluster_id = cluster_by_mention.get(mention_digest)
            if cluster_id is None:
                continue
            coordinate = contract_digest(
                b"memorii.bootstrap-graph.cluster-reference-coordinate.v3",
                {
                    "operation_member_digest": membership.operation_member_digest,
                    "path": path,
                    "mention_digest": mention_digest,
                },
            )
            occurrences.setdefault(cluster_id, []).append(
                BootstrapCanonicalClusterReferenceOccurrenceV3.create(
                    membership=membership,
                    source_local_cluster_id=cluster_id,
                    source_coordinate_digest=coordinate,
                )
            )
    dependencies: list[BootstrapCanonicalFirstUseDependencyV3] = []
    for cluster_id, rows in sorted(occurrences.items()):
        canonical_rows = tuple(
            sorted(rows, key=lambda item: (item.membership.operation_ordinal, item.source_coordinate_digest))
        )
        producer_ordinal = canonical_rows[0].membership.operation_ordinal
        producer = tuple(
            item for item in canonical_rows if item.membership.operation_ordinal == producer_ordinal
        )
        consumers = tuple(
            BootstrapCanonicalFirstUseConsumerV3.create(occurrence=item)
            for item in canonical_rows
            if item.membership.operation_ordinal > producer_ordinal
        )
        proof_digest = (proof_digest_by_cluster or {}).get(cluster_id) or contract_digest(
            b"memorii.bootstrap-graph.canonical-identity-cluster-proof-projection.v3",
            {
                "cluster_id": cluster_id,
                "source_local_resolution_digest": ordered[0].source_local_identity.resolution_digest,
                "identity_partition_evidence_digest": ordered[0].identity_partition_evidence.evidence_digest,
            },
        )
        dependencies.append(BootstrapCanonicalFirstUseDependencyV3.create(
            source_local_cluster_id=cluster_id,
            canonical_identity_proof_digest=proof_digest,
            producer_membership=producer[0].membership,
            producer_occurrences=tuple(sorted(producer, key=lambda item: item.source_coordinate_digest)),
            consumers=consumers,
        ))
    return memberships, tuple(dependencies)


def _operation_mention_occurrences(
    member: BootstrapProposalOperationMemberV3,
) -> tuple[tuple[str, str], ...]:
    """Return retained mention sites without collapsing equal mentions."""

    if member.kind == "fact":
        rows = [("fact.subject", member.subject_mention_digest)]
        if member.object.kind == "entity":
            rows.append(("fact.object", member.object.mention_digest))
        if member.attributed_to_mention_digest is not None:
            rows.append(("fact.attribution", member.attributed_to_mention_digest))
        return tuple(rows)
    if member.kind == "correction" or member.kind == "retraction":
        if member.kind == "correction":
            facts = (member.corrected_fact, member.replacement_fact)
        else:
            facts = (member.retracted_fact,)
        rows: list[tuple[str, str]] = []
        for index, fact in enumerate(facts):
            prefix = "correction" if member.kind == "correction" else "retraction"
            rows.append((f"{prefix}.{index}.subject", fact.subject_mention_digest))
            if fact.object.kind == "entity":
                rows.append((f"{prefix}.{index}.object", fact.object.mention_digest))
        return tuple(rows)
    if member.kind == "action_state":
        return tuple(
            (f"action.{binding.role_id}.{index}", participant.mention_digest)
            for binding in member.role_bindings
            for index, participant in enumerate(binding.participants)
        )
    if member.kind == "identity":
        return tuple(
            [("identity.predecessor", item) for item in member.predecessor_mention_digests]
            + [("identity.successor", item) for item in member.successor_mention_digests]
        )
    raise ValueError("unknown native operation member")


def _referenced_clusters(
    resolution: BootstrapSourceLocalIdentityResolutionV3,
    operation_inputs: tuple[BootstrapNativeOperationReductionInputV3, ...],
):
    mentions = {
        mention_digest
        for item in operation_inputs
        for _, mention_digest in _operation_mention_occurrences(item.operation_member)
    }
    clusters = tuple(
        sorted(
            (item for item in resolution.clusters if set(item.mention_digests) & mentions),
            key=lambda item: item.cluster_id,
        )
    )
    if not clusters:
        raise ValueError("canonical identity authority has no referenced clusters")
    return clusters
