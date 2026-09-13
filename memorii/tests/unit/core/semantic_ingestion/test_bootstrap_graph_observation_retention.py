"""Focused proof for retained planner-selected observation mention authority."""

from __future__ import annotations

import pytest
from memorii.core.memory_evolution.bootstrap_graph_planning import (
    BuiltInBootstrapGraphTargetMaterializationPlannerV3,
)
from memorii.core.memory_plane import MemoryPlaneService
from memorii.core.provider.models import ProviderOperation
from memorii.core.provider.service import ProviderMemoryService
from memorii.core.semantic_ingestion.bootstrap_native_reducer import _accepted_effect
from memorii.core.semantic_ingestion.contracts import (
    BootstrapGraphTargetMaterializationPlanV3,
    BootstrapNativeFactEffectV3,
    BootstrapNativeObservationMentionBindingV3,
    MessageAdmissionIdentity,
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
):
    planning_calls = []
    group_requests = []
    original_plan = BuiltInBootstrapGraphTargetMaterializationPlannerV3.plan

    def capture_plan(self, *, request):
        planned = original_plan(self, request=request)
        planning_calls.append((request, planned))
        return planned

    normalization, _calls = _v3_normalization_host_builder(proposal=graph_fact_proposal())
    service = ProviderMemoryService(
        memory_plane=memory_plane,
        now_provider=lambda: TEST_NOW,
        host_bootstrap_capability=_built_in_local_capability(),
        host_bootstrap_material_verifier=DeterministicTestHostBootstrapMaterialVerifier(),
        source_normalization_host_bundle_builder=normalization,
    )
    commit = service._semantic_atomic_store.commit_or_reload_bootstrap_graph_group_v3

    def capture_group_request(*, request):
        group_requests.append(request)
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
    assert result.blocked_reasons["semantic_ingestion"] == "source_only"
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
    substituted_governance = SegmentGovernanceBinding.create(**governance_values, authority_digest="0" * 64)
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
