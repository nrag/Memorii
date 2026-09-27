"""Focused proof for retained planner-selected observation mention authority."""

from __future__ import annotations

import pytest
from memorii.core.memory_evolution.atomic_store import PreplanningStoreError
from memorii.core.memory_evolution.bootstrap_graph_planning import (
    BootstrapCanonicalIdentityBindingAllocationProjectorV3,
    BootstrapNativeTargetResolutionProjectorV3,
    BuiltInBootstrapGraphTargetMaterializationPlannerV3,
)
from memorii.core.memory_evolution.graph_planning import (
    GraphPlanningState,
)
from memorii.core.memory_plane import MemoryPlaneService
from memorii.core.provider.models import ProviderOperation
from memorii.core.provider.service import ProviderMemoryService
from memorii.core.semantic_ingestion.bootstrap_native_reducer import _accepted_effect
from memorii.core.semantic_ingestion.contracts import (
    BootstrapGraphTargetMaterializationPlanV3,
    BootstrapNativeCorrectionEffectV3,
    BootstrapNativeFactEffectV3,
    BootstrapNativeObservationMentionBindingV3,
    BootstrapNativePlanningUnavailableV3,
    BootstrapNativeRetractionEffectV3,
    BootstrapNativeTemporalConstructionV3,
    BootstrapProposalCorrectionV3,
    BootstrapProposalEntityObjectV3,
    BootstrapProposalFactV3,
    BootstrapProposalRetractionV3,
    MessageAdmissionIdentity,
    OperationTemporalAttachmentBinding,
    OperationTemporalDecisionBinding,
    SegmentGovernanceBinding,
    decode_semantic_contract,
    encode_semantic_contract,
)
from tests.unit.core.semantic_ingestion.bootstrap_graph_production_roots_support import (
    graph_fact_proposal,
)
from tests.unit.core.semantic_ingestion.test_semantic_provider_composition import (
    TEST_NOW,
    DeterministicTestHostBootstrapMaterialVerifier,
    _built_in_local_capability,
    _host_ingress,
    _v3_normalization_host_builder,
)


def _capture_builtin_fact_planning(
    monkeypatch: pytest.MonkeyPatch,
    memory_plane: MemoryPlaneService | None = None,
    *,
    fail_group_commit: bool = True,
):
    planning_calls = []
    group_requests = []
    original_plan = BuiltInBootstrapGraphTargetMaterializationPlannerV3.plan

    def capture_plan(self, *, request):
        planned = original_plan(self, request=request)
        planning_calls.append((request, planned))
        return planned

    normalization, _calls = _v3_normalization_host_builder(proposal=graph_fact_proposal())
    from tests.integration.test_observation_ledger_activation import (
        _signed_monitoring_authority,
    )

    service = ProviderMemoryService(
        memory_plane=memory_plane,
        now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=_built_in_local_capability(),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        source_normalization_host_bundle_builder=normalization,
        verified_capability_monitoring_authorities=(_signed_monitoring_authority(),),
    )
    commit = service._semantic_atomic_store.commit_or_reload_bootstrap_graph_group_v3

    def capture_group_request(*, request):
        group_requests.append(request)
        if fail_group_commit:
            raise PreplanningStoreError("captured graph transaction authority")
        return commit(request=request)

    monkeypatch.setattr(BuiltInBootstrapGraphTargetMaterializationPlannerV3, "plan", capture_plan)
    monkeypatch.setattr(service._semantic_atomic_store, "commit_or_reload_bootstrap_graph_group_v3", capture_group_request)
    result = service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="retained-observation-mention-authority",
        task_id="task:retention",
        user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    expected_reason = "graph_transaction_authority_unavailable" if fail_group_commit else "source_only"
    assert result.blocked_reasons["semantic_ingestion"] == expected_reason
    assert len(group_requests) == 1
    effect = group_requests[0].ordered_operation_inputs[0].reduction.effect_materialization.accepted_effect
    assert isinstance(effect, BootstrapNativeFactEffectV3)
    matching = [
        (request, plan) for request, plan in planning_calls
        if isinstance(plan, BootstrapGraphTargetMaterializationPlanV3)
        and plan.target_bindings == effect.target_bindings
        and plan.planning_records == effect.planning_records
    ]
    assert matching
    # Planning may run again for deterministic verification. Every matching
    # construction must carry the authority retained by the committed effect.
    for request, plan in matching:
        assert plan.observation_mention_bindings == effect.observation_mention_bindings
        candidates = {item.mention_digest: item for item in request.target_resolution_authority.mention_candidates}
        for binding in effect.observation_mention_bindings:
            assert binding.target_candidate == candidates[binding.mention_digest]
    request, plan = matching[0]
    return request, plan, group_requests[0]


def _effect_create_values(effect: BootstrapNativeFactEffectV3, bindings) -> dict[str, object]:
    values = effect.model_dump(mode="python")
    values.pop("schema_version")
    values.pop("effect_digest")
    values["observation_mention_bindings"] = bindings
    return values


def test_builtin_fact_retention_is_authoritative_and_fail_closed(monkeypatch) -> None:
    """One public commit preserves exact planner authority and rejects substitutes."""
    request, plan, group_request = _capture_builtin_fact_planning(monkeypatch)
    effect = group_request.ordered_operation_inputs[0].reduction.effect_materialization.accepted_effect
    assert isinstance(effect, BootstrapNativeFactEffectV3)
    candidates = {item.mention_digest: item for item in request.target_resolution_authority.mention_candidates}
    governance = request.operation_input.planning_construction_authority.segment_governance
    assert len(governance.segment_governance_bindings) == 1
    assert effect.fact.object.kind == "entity"
    assert {item.mention_digest for item in effect.observation_mention_bindings} == {
        effect.fact.subject_mention_digest,
        effect.fact.object.mention_digest,
    }
    for binding in effect.observation_mention_bindings:
        assert binding.target_candidate == candidates[binding.mention_digest]
        assert binding.segment_governance == governance.segment_governance_bindings[0]
        assert binding.message_admission_identities == governance.message_admission_identities

    bindings = effect.observation_mention_bindings
    with pytest.raises(ValueError, match="observation authority"):
        BootstrapNativeFactEffectV3.create(**_effect_create_values(effect, bindings[:1]))
    with pytest.raises(ValueError, match="observation authority"):
        BootstrapNativeFactEffectV3.create(**_effect_create_values(effect, (bindings[0], bindings[0])))
    with pytest.raises(ValueError, match="observation mention binding"):
        BootstrapNativeObservationMentionBindingV3.create(
            operation_id=bindings[0].operation_id, operation_execution_id=bindings[0].operation_execution_id,
            mention_digest=bindings[0].mention_digest, mention_span=bindings[0].mention_span,
            target_candidate=bindings[1].target_candidate, segment_governance=bindings[0].segment_governance,
            message_admission_identities=bindings[0].message_admission_identities,
        )
    governance_values = bindings[0].segment_governance.model_dump(mode="python")
    governance_values.pop("binding_digest")
    governance_values.pop("authority_digest")
    substituted_governance = SegmentGovernanceBinding.create(
        **governance_values, authority_digest="0" * 64
    )
    with pytest.raises(ValueError, match="observation mention binding"):
        BootstrapNativeObservationMentionBindingV3.create(
            operation_id=bindings[0].operation_id, operation_execution_id=bindings[0].operation_execution_id,
            mention_digest=bindings[0].mention_digest, mention_span=bindings[0].mention_span,
            target_candidate=bindings[0].target_candidate, segment_governance=substituted_governance,
            message_admission_identities=bindings[0].message_admission_identities,
        )
    admission = bindings[0].message_admission_identities[0]
    admission_values = admission.model_dump(mode="python")
    admission_values.pop("message_admission_key_digest")
    admission_values.pop("segment_governance_binding_digest")
    substituted_admission = MessageAdmissionIdentity.create(
        **admission_values, segment_governance_binding_digest="0" * 64
    )
    for admissions in ((substituted_admission,), (admission, admission), ()):
        with pytest.raises(ValueError, match="observation mention binding"):
            BootstrapNativeObservationMentionBindingV3.create(
                operation_id=bindings[0].operation_id, operation_execution_id=bindings[0].operation_execution_id,
                mention_digest=bindings[0].mention_digest, mention_span=bindings[0].mention_span,
                target_candidate=bindings[0].target_candidate, segment_governance=bindings[0].segment_governance,
                message_admission_identities=admissions,
            )
    with pytest.raises(ValueError, match="observation authority is incomplete"):
        _accepted_effect(member=effect.fact, plan=plan.model_copy(update={"observation_mention_bindings": ()}))

    legacy_effect = BootstrapNativeFactEffectV3.create(**_effect_create_values(effect, ()))
    assert "observation_mention_bindings" not in legacy_effect.model_dump(mode="python")
    assert "observation_mention_bindings" not in legacy_effect.model_dump(mode="json")
    encoded_legacy = encode_semantic_contract(legacy_effect)
    assert b"observation_mention_bindings" not in encoded_legacy
    assert decode_semantic_contract(encoded_legacy, BootstrapNativeFactEffectV3) == legacy_effect


def _lifecycle_request_from_fact_plan(
    request,
    plan,
    *,
    kind="correction",
    state=None,
    selector_fact=None,
    target_resolution_authority=None,
):
    fact = request.operation_input.operation_member
    assert fact.kind == "fact"
    selector_fact = selector_fact or fact
    assertion = request.operation_input.planning_construction_authority.temporal_constructions[0]
    original_attachment = assertion.temporal_decision_binding.temporal_attachment
    attachment = OperationTemporalAttachmentBinding.create(
        operation_id=original_attachment.operation_id,
        temporal_role="transition",
        stable_attachment_consensus_digest=original_attachment.stable_attachment_consensus_digest,
        candidate_ids=original_attachment.candidate_ids,
        candidate_spans=original_attachment.candidate_spans,
    )
    original_decision = assertion.temporal_decision_binding
    decision = OperationTemporalDecisionBinding.create(
        operation_id=original_decision.operation_id,
        temporal_role="transition",
        scope_assessment_digest=original_decision.scope_assessment_digest,
        semantic_assessment_digest=original_decision.semantic_assessment_digest,
        temporal_attachment=attachment,
        decision_closure=original_decision.decision_closure,
    )
    transition = BootstrapNativeTemporalConstructionV3.create(
        temporal_role="transition",
        temporal_consensus_digest=assertion.temporal_consensus_digest,
        effective_time=assertion.effective_time,
        accepted_temporal_evidence=assertion.accepted_temporal_evidence,
        temporal_decision_binding=decision,
        temporal_policy_fingerprint=assertion.temporal_policy_fingerprint,
    )
    authority = request.operation_input.planning_construction_authority.model_copy(
        update={
            "temporal_constructions": (assertion, transition),
            "operation_execution_id": "2" * 64,
        }
    )
    member = (
        BootstrapProposalCorrectionV3.create(
            kind="correction", corrected_fact=selector_fact, replacement_fact=fact,
            assertion=fact.assertion, correction_anchor=fact.predicate_anchor,
        )
        if kind == "correction"
        else BootstrapProposalRetractionV3.create(
            kind="retraction", retracted_fact=selector_fact,
            assertion=fact.assertion, retraction_anchor=fact.predicate_anchor,
        )
    )
    operation = request.operation_input.model_copy(update={
        "operation_member": member, "planning_construction_authority": authority,
        "operation_execution_id": "2" * 64,
    })
    return request.model_copy(update={
        "operation_input": operation,
        "target_resolution_authority": (
            request.target_resolution_authority
            if target_resolution_authority is None
            else target_resolution_authority
        ),
        "current_planning_state": (
            GraphPlanningState.create(
                base_snapshot_digest=plan.planning_state_after.base_snapshot_digest,
                records=(next(
                    item for item in plan.planning_state_after.records
                    if item.record.payload.record_kind == "claim_assertion"
                ),),
                codec_manifest_fingerprint=plan.planning_state_after.codec_manifest_fingerprint,
                applied_planned_delta_digests=(),
            )
            if state is None else state
        ),
    })


def test_native_lifecycle_planner_selects_one_pending_claim_and_fails_closed(monkeypatch) -> None:
    """Correction plans one immutable transition and refuses missing/ambiguous claims."""
    request, plan, _group_request = _capture_builtin_fact_planning(monkeypatch)
    lifecycle_request = _lifecycle_request_from_fact_plan(request, plan)
    planned = BuiltInBootstrapGraphTargetMaterializationPlannerV3().plan(
        request=lifecycle_request
    )
    assert isinstance(planned, BootstrapGraphTargetMaterializationPlanV3)
    assert planned.operation_kind == "correction"
    assert len([item for item in planned.target_bindings if item.role == "corrected_target"]) == 1
    assert len([item for item in planned.planning_records if item.record_kind == "temporal_transition"]) == 1
    reduced = _accepted_effect(
        member=lifecycle_request.operation_input.operation_member, plan=planned,
    )
    assert isinstance(reduced, BootstrapNativeCorrectionEffectV3)
    assert reduced.transition_records

    retraction_request = _lifecycle_request_from_fact_plan(request, plan, kind="retraction")
    retraction_plan = BuiltInBootstrapGraphTargetMaterializationPlannerV3().plan(
        request=retraction_request
    )
    assert isinstance(retraction_plan, BootstrapGraphTargetMaterializationPlanV3)
    retracted = _accepted_effect(
        member=retraction_request.operation_input.operation_member, plan=retraction_plan,
    )
    assert isinstance(retracted, BootstrapNativeRetractionEffectV3)
    assert len(retracted.retracted_targets) == 1
    assert len(retracted.transition_records) == 1

    missing = _lifecycle_request_from_fact_plan(
        request, plan, state=request.current_planning_state,
    )
    unavailable = BuiltInBootstrapGraphTargetMaterializationPlannerV3().plan(request=missing)
    assert isinstance(unavailable, BootstrapNativePlanningUnavailableV3)
    assert unavailable.reason_codes == ("graph_target_missing",)

    base_state = lifecycle_request.current_planning_state
    first = base_state.records[0]
    duplicate = first.model_copy(update={
        "record": first.record.model_copy(update={"record_id": "duplicate:" + first.record.record_id})
    })
    ambiguous_state = base_state.model_copy(update={"records": (*base_state.records, duplicate)})
    ambiguous = BuiltInBootstrapGraphTargetMaterializationPlannerV3().plan(
        request=_lifecycle_request_from_fact_plan(request, plan, state=ambiguous_state)
    )
    assert isinstance(ambiguous, BootstrapNativePlanningUnavailableV3)
    assert ambiguous.reason_codes == ("graph_target_ambiguous",)


def test_native_lifecycle_planner_selects_by_canonical_assertion_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lifecycle selectors ignore source-local mention IDs after target resolution."""
    request, plan, _group_request = _capture_builtin_fact_planning(monkeypatch)
    fact = request.operation_input.operation_member
    assert fact.kind == "fact"
    original_candidates = {
        item.mention_digest: item
        for item in request.target_resolution_authority.mention_candidates
    }
    replacement_subject_mention = "3" * 64
    replacement_subject = original_candidates[fact.subject_mention_digest].model_copy(
        update={"mention_digest": replacement_subject_mention}
    )
    selector_fact = BootstrapProposalFactV3.create(
        predicate_id=fact.predicate_id,
        subject_mention_digest=replacement_subject_mention,
        object=fact.object,
        assertion=fact.assertion,
        predicate_anchor=fact.predicate_anchor,
        polarity=fact.polarity,
        commitment=fact.commitment,
        attributed_to_mention_digest=fact.attributed_to_mention_digest,
        temporal_qualifiers=fact.temporal_qualifiers,
    )
    assert selector_fact.fact_digest != fact.fact_digest
    authority = request.target_resolution_authority.model_copy(update={
        "mention_candidates": (
            *request.target_resolution_authority.mention_candidates,
            replacement_subject,
        )
    })
    planned = BuiltInBootstrapGraphTargetMaterializationPlannerV3().plan(
        request=_lifecycle_request_from_fact_plan(
            request,
            plan,
            selector_fact=selector_fact,
            target_resolution_authority=authority,
        )
    )
    assert isinstance(planned, BootstrapGraphTargetMaterializationPlanV3)

    changed_object_mention = "4" * 64
    changed_object = BootstrapProposalEntityObjectV3.create(
        mention_digest=changed_object_mention
    )
    changed_fact = BootstrapProposalFactV3.create(
        predicate_id=fact.predicate_id,
        subject_mention_digest=replacement_subject_mention,
        object=changed_object,
        assertion=fact.assertion,
        predicate_anchor=fact.predicate_anchor,
        polarity=fact.polarity,
        commitment=fact.commitment,
        attributed_to_mention_digest=fact.attributed_to_mention_digest,
        temporal_qualifiers=fact.temporal_qualifiers,
    )
    original_object = original_candidates[fact.object.mention_digest]
    changed_object_target = original_object.model_copy(update={
        "mention_digest": changed_object_mention,
        "logical_entity_id": "logical:changed-object",
    })
    changed_authority = authority.model_copy(update={
        "mention_candidates": (*authority.mention_candidates, changed_object_target)
    })
    unavailable = BuiltInBootstrapGraphTargetMaterializationPlannerV3().plan(
        request=_lifecycle_request_from_fact_plan(
            request,
            plan,
            selector_fact=changed_fact,
            target_resolution_authority=changed_authority,
        )
    )
    assert isinstance(unavailable, BootstrapNativePlanningUnavailableV3)
    assert unavailable.reason_codes == ("graph_target_missing",)


def test_lifecycle_identity_allocator_reuses_only_one_scoped_prior_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A correction reuses immutable refs, while a changed replacement stays new."""
    request, plan, _group_request = _capture_builtin_fact_planning(monkeypatch)
    fact = request.operation_input.operation_member
    assert fact.kind == "fact"
    subject_mention = "3" * 64
    changed_object_mention = "4" * 64
    mentions = {item.mention_digest: item for item in request.operation_input.normalized_proposal.mentions}
    subject = mentions[fact.subject_mention_digest].model_copy(update={"mention_digest": subject_mention})
    changed_object = mentions[fact.object.mention_digest].model_copy(update={"mention_digest": changed_object_mention})
    selector_fact = BootstrapProposalFactV3.create(
        predicate_id=fact.predicate_id,
        subject_mention_digest=subject_mention,
        object=fact.object,
        assertion=fact.assertion,
        predicate_anchor=fact.predicate_anchor,
        polarity=fact.polarity,
        commitment=fact.commitment,
        attributed_to_mention_digest=fact.attributed_to_mention_digest,
        temporal_qualifiers=fact.temporal_qualifiers,
    )
    replacement_fact = BootstrapProposalFactV3.create(
        predicate_id=fact.predicate_id,
        subject_mention_digest=fact.subject_mention_digest,
        object=BootstrapProposalEntityObjectV3.create(mention_digest=changed_object_mention),
        assertion=fact.assertion,
        predicate_anchor=fact.predicate_anchor,
        polarity=fact.polarity,
        commitment=fact.commitment,
        attributed_to_mention_digest=fact.attributed_to_mention_digest,
        temporal_qualifiers=fact.temporal_qualifiers,
    )
    member = BootstrapProposalCorrectionV3.create(
        corrected_fact=selector_fact,
        replacement_fact=replacement_fact,
        assertion=fact.assertion,
        correction_anchor=fact.predicate_anchor,
    )
    original_cluster = next(
        item
        for item in request.operation_input.source_local_identity.clusters
        if fact.subject_mention_digest in item.mention_digests
    )
    shared_cluster = original_cluster.model_copy(update={
        "mention_digests": tuple(sorted((*original_cluster.mention_digests, subject_mention)))
    })
    original_object_cluster = next(
        item
        for item in request.operation_input.source_local_identity.clusters
        if fact.object.mention_digest in item.mention_digests
    )
    changed_object_cluster = original_object_cluster.model_copy(update={
        "cluster_id": "b" * 64,
        "mention_digests": (changed_object_mention,),
    })
    identity = request.operation_input.source_local_identity.model_copy(update={
        "clusters": tuple(
            shared_cluster if item.cluster_id == original_cluster.cluster_id else item
            for item in request.operation_input.source_local_identity.clusters
        ) + (changed_object_cluster,)
    })
    proposal = request.operation_input.normalized_proposal.model_copy(update={
        "mentions": (*request.operation_input.normalized_proposal.mentions, subject, changed_object)
    })
    operation = request.operation_input.model_copy(update={
        "source_id": "source:cross-correction",
        "source_digest": "5" * 64,
        "preparation_fingerprint": "6" * 64,
        "operation_member": member,
        "normalized_proposal": proposal.model_copy(update={
            "source_id": "source:cross-correction", "source_digest": "5" * 64,
            "preparation_fingerprint": "6" * 64,
        }),
        "source_local_identity": identity.model_copy(update={
            "source_id": "source:cross-correction", "source_digest": "5" * 64,
            "preparation_fingerprint": "6" * 64,
        }),
    })
    prior_authority = request.target_resolution_authority.canonical_identity_authority.authority
    reload = BootstrapCanonicalIdentityBindingAllocationProjectorV3().project(
        operation_inputs=(operation,),
        recovery_key_digest="7" * 64,
        sealed_snapshot=request.sealed_snapshot,
        effective_read_set=request.effective_read_set,
        current_planning_state=plan.planning_state_after,
        required_scope_set_digest=prior_authority.required_scope_set_digest,
        authorized_scope_identity=prior_authority.authorized_scope_identity,
        allocation_namespace_id=prior_authority.allocation_namespace_id,
        allocation_policy_fingerprint="8" * 64,
        allow_new_allocation=True,
        source_plan_checkpoint_digest="9" * 64,
        publication_generation_digest="a" * 64,
    )
    shared = next(
        item for item in reload.authority.cluster_decisions
        if item.proof.source_local_cluster_id == original_cluster.cluster_id
    )
    assert shared.kind == "existing"
    targets = BootstrapNativeTargetResolutionProjectorV3().project(
        operation_input=operation,
        transaction_group_id=operation.dependency_group.group_id,
        sealed_snapshot=request.sealed_snapshot,
        effective_read_set=request.effective_read_set,
        current_planning_state=plan.planning_state_after,
        canonical_identity_authority=reload,
    )
    by_mention = {item.mention_digest: item for item in targets.mention_candidates}
    assert by_mention[subject_mention].logical_entity_id == by_mention[fact.subject_mention_digest].logical_entity_id
    assert by_mention[changed_object_mention].logical_entity_id != by_mention[fact.object.mention_digest].logical_entity_id

    def decision_for(*, state, scope):
        result = BootstrapCanonicalIdentityBindingAllocationProjectorV3().project(
            operation_inputs=(operation,),
            recovery_key_digest="7" * 64,
            sealed_snapshot=request.sealed_snapshot,
            effective_read_set=request.effective_read_set,
            current_planning_state=state,
            required_scope_set_digest=prior_authority.required_scope_set_digest,
            authorized_scope_identity=scope,
            allocation_namespace_id=prior_authority.allocation_namespace_id,
            allocation_policy_fingerprint="8" * 64,
            allow_new_allocation=True,
            source_plan_checkpoint_digest="9" * 64,
            publication_generation_digest="a" * 64,
        )
        return next(
            item for item in result.authority.cluster_decisions
            if item.proof.source_local_cluster_id == original_cluster.cluster_id
        )

    assert decision_for(state=request.current_planning_state, scope=prior_authority.authorized_scope_identity).kind == "absent"
    claim = next(
        item for item in plan.planning_state_after.records
        if item.record.payload.record_kind == "claim_assertion"
    )
    duplicate_state = plan.planning_state_after.model_copy(update={
        "records": (*plan.planning_state_after.records, claim.model_copy(update={
            "record": claim.record.model_copy(update={"record_id": "duplicate:" + claim.record.record_id})
        }))
    })
    assert decision_for(state=duplicate_state, scope=prior_authority.authorized_scope_identity).kind == "absent"
    assert decision_for(state=plan.planning_state_after, scope="scope:foreign").kind == "absent"
