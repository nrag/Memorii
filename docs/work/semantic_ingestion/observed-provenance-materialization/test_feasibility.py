"""Real native planning fields establish recipe feasibility, not certification.

The production capture currently supplies a validated fact arm. The helper's
typed dispatch covers all five accepted-effect classes; accepted sibling-arm
captures remain a runtime-readiness requirement, not evidence claimed here.
"""
from datetime import timedelta

import pytest
from feasibility import _effect_authority, _policy_context, retained_context

from memorii.core.memory_evolution.graph_planning import (
    AbsentPlanningPrecondition,
    PlanningCommitValues,
    canonical_planning_payload_from_record,
    materialize_canonical_planning_payload,
)
from memorii.core.semantic_ingestion.contracts import (
    BootstrapNativeActionStateEffectV3,
    BootstrapNativeCorrectionEffectV3,
    BootstrapNativeFactEffectV3,
    BootstrapNativeIdentityConstructionAuthorityV3,
    BootstrapNativeIdentityEffectV3,
    BootstrapNativeIdentityMaterializationV3,
    BootstrapNativePlanningRecordV3,
    BootstrapNativeRetractionEffectV3,
    BootstrapProposalActionRoleBindingV3,
    BootstrapProposalActionRoleParticipantV3,
    BootstrapProposalActionStateV3,
    BootstrapProposalCorrectionV3,
    BootstrapProposalRetractionV3,
    TemporalTransitionRecord,
    contract_digest,
)
from tests.fixtures.semantic_ingestion.semantic_terminal_fixture import accepted_terminal
from tests.unit.core.semantic_ingestion.test_bootstrap_graph_observation_retention import _capture_builtin_fact_planning
from tests.unit.core.semantic_ingestion.test_semantic_provider_composition import TEST_NOW


@pytest.fixture(scope="module")
def captured_fact():
    patch = pytest.MonkeyPatch()
    try:
        return _capture_builtin_fact_planning(patch)
    finally:
        patch.undo()


def _commit_values(group_request):
    return PlanningCommitValues(
        transaction_group_id=group_request.transaction_group_id,
        graph_revision_before="feasibility-before",
        graph_revision_after="feasibility-after",
        committed_at=TEST_NOW,
    )


def _retained_inventory(effect, group_request):
    commit_values = _commit_values(group_request)
    projections, owned_records, _ = _effect_authority(effect)
    native_records = list(owned_records)
    for item in projections:
        native_records.extend((item.citation_record, item.provenance_record))
    unique = {
        (item.record_kind, item.record_id): item
        for item in native_records
    }
    return tuple(
        materialize_canonical_planning_payload(
            item.planning_payload,
            commit_values=commit_values,
            authorizing_transaction_group_id=group_request.transaction_group_id,
        )
        for item in unique.values()
    )


def _retained_context(
    compilation, effect, projection, group_request, *, retained_records=None,
):
    commit_values = _commit_values(group_request)
    if retained_records is None:
        retained_records = _retained_inventory(effect, group_request)
    return retained_context(
        compilation,
        effect,
        projection,
        commit_values=commit_values,
        authorizing_transaction_group_id=group_request.transaction_group_id,
        retained_records=retained_records,
    )


def test_retained_fact_context_has_complete_deterministic_recipe(captured_fact):
    _, _, group_request = captured_fact
    reduction = group_request.ordered_operation_inputs[0].reduction
    compilation = reduction.native_compilation
    effect = reduction.effect_materialization.accepted_effect
    assert isinstance(effect, BootstrapNativeFactEffectV3)
    authority = compilation.operation_input.planning_construction_authority
    assert authority is not None
    for projection in effect.evidence_projections:
        context = _retained_context(compilation, effect, projection, group_request)
        construction = next(item for item in authority.evidence_constructions
                            if item.evidence_item_digest == projection.evidence_item_digest)
        citation = projection.citation_record.planning_payload.planning_record
        assert context.target_id == citation["cited_record_id"]
        # The native fact planner deliberately cites the claim, not the relation
        # revision emitted from the same fact.
        assert context.target_kind == "claim_assertion"
        assert context.proof_ancestry_ids == tuple(sorted(set((
            compilation.compilation_digest, authority.authority_digest,
            authority.source_authority_evidence.evidence_digest,
            authority.source_authority_evidence.provenance_digest,
            construction.evidence_digest, projection.projection_digest, effect.effect_digest,
        ))))
        expected = [authority.predicate_registry_fingerprint,
                    authority.predicate_state_rule.policy_fingerprint, authority.action_policy_fingerprint]
        expected.extend(item.temporal_policy_fingerprint for item in authority.temporal_constructions)
        bundle = authority.arbitration_policy_bundle
        if bundle is not None:
            expected.extend((bundle.trust_policy.fingerprint, bundle.temporal_policy.fingerprint))
        if authority.identity_construction is not None:
            expected.append(authority.identity_construction.identity_policy_fingerprint)
        assert context.policy_fingerprints == tuple(sorted(set(expected)))
        bad = projection.model_copy(update={"operation_execution_id": "0" * 64})
        with pytest.raises(ValueError):
            _retained_context(compilation, effect, bad, group_request)
        bad = projection.model_copy(update={"citation_record": projection.provenance_record})
        with pytest.raises(ValueError):
            _retained_context(compilation, effect.model_copy(update={"evidence_projections": (bad,)}), bad, group_request)


def test_retained_fact_context_denies_substituted_and_ambiguous_targets(captured_fact):
    _, _, group_request = captured_fact
    reduction = group_request.ordered_operation_inputs[0].reduction
    compilation = reduction.native_compilation
    effect = reduction.effect_materialization.accepted_effect
    assert isinstance(effect, BootstrapNativeFactEffectV3)
    projection = effect.evidence_projections[0]

    citation_payload = dict(projection.citation_record.planning_payload.planning_record)
    citation_payload["cited_record_id"] = "not-a-retained-target"
    citation = projection.citation_record.model_copy(
        update={"planning_payload": projection.citation_record.planning_payload.model_copy(
            update={"planning_record": citation_payload}
        )}
    )
    changed = projection.model_copy(update={"citation_record": citation})
    changed_effect = effect.model_copy(update={"evidence_projections": (changed,)})
    with pytest.raises(ValueError, match="missing cited native target"):
        _retained_context(compilation, changed_effect, changed, group_request,
                          retained_records=_retained_inventory(effect, group_request))

    cited_record_id = projection.citation_record.planning_payload.planning_record["cited_record_id"]
    target = next(record for record in effect.planning_records if record.record_id == cited_record_id)
    duplicate_effect = effect.model_copy(update={"planning_records": (*effect.planning_records, target)})
    with pytest.raises(ValueError, match="nonunique or missing cited native target"):
        _retained_context(compilation, duplicate_effect, projection, group_request)


def test_retained_fact_context_denies_duplicate_evidence_construction(captured_fact):
    _, _, group_request = captured_fact
    reduction = group_request.ordered_operation_inputs[0].reduction
    compilation = reduction.native_compilation
    effect = reduction.effect_materialization.accepted_effect
    assert isinstance(effect, BootstrapNativeFactEffectV3)
    authority = compilation.operation_input.planning_construction_authority
    assert authority is not None
    duplicated = authority.model_copy(
        update={"evidence_constructions": (
            *authority.evidence_constructions,
            authority.evidence_constructions[0],
        )}
    )
    foreign = compilation.model_copy(
        update={"operation_input": compilation.operation_input.model_copy(
            update={"planning_construction_authority": duplicated}
        )}
    )
    with pytest.raises(ValueError, match="nonunique retained evidence"):
        _retained_context(foreign, effect, effect.evidence_projections[0], group_request)


def test_retained_fact_context_denies_foreign_source_and_duplicate_provenance(captured_fact):
    _, _, group_request = captured_fact
    reduction = group_request.ordered_operation_inputs[0].reduction
    compilation = reduction.native_compilation
    effect = reduction.effect_materialization.accepted_effect
    assert isinstance(effect, BootstrapNativeFactEffectV3)
    authority = compilation.operation_input.planning_construction_authority
    assert authority is not None
    foreign_authority = authority.model_copy(update={"source_id": "other-source"})
    foreign_compilation = compilation.model_copy(
        update={"operation_input": compilation.operation_input.model_copy(
            update={"planning_construction_authority": foreign_authority}
        )}
    )
    with pytest.raises(ValueError, match="foreign retained operation authority"):
        _retained_context(foreign_compilation, effect, effect.evidence_projections[0], group_request)
    duplicate_effect = effect.model_copy(
        update={"evidence_projections": (*effect.evidence_projections, effect.evidence_projections[0])}
    )
    with pytest.raises(ValueError, match="nonunique retained provenance projection"):
        _retained_context(compilation, duplicate_effect, effect.evidence_projections[0], group_request)


@pytest.mark.parametrize("record_role", ("citation", "provenance", "target"))
def test_retained_fact_context_requires_exact_supplied_graph_inventory(
    captured_fact, record_role,
):
    _, _, group_request = captured_fact
    reduction = group_request.ordered_operation_inputs[0].reduction
    compilation = reduction.native_compilation
    effect = reduction.effect_materialization.accepted_effect
    assert isinstance(effect, BootstrapNativeFactEffectV3)
    projection = effect.evidence_projections[0]
    inventory = _retained_inventory(effect, group_request)
    if record_role == "citation":
        record_id = projection.citation_record.record_id
        record_kind = "citation"
    elif record_role == "provenance":
        record_id = projection.provenance_record.record_id
        record_kind = "provenance"
    else:
        record_id = projection.citation_record.planning_payload.planning_record["cited_record_id"]
        record_kind = "claim_assertion"
    selected = next(
        item for item in inventory
        if item.record_kind == record_kind and getattr(item, f"{record_kind}_id", None) == record_id
    )
    missing = tuple(item for item in inventory if item != selected)
    with pytest.raises(ValueError, match="retained graph inventory"):
        _retained_context(
            compilation, effect, projection, group_request, retained_records=missing,
        )
    duplicated = (*inventory, selected)
    with pytest.raises(ValueError, match="retained graph inventory"):
        _retained_context(
            compilation, effect, projection, group_request, retained_records=duplicated,
        )
    replacement = selected.model_copy(update={"record_digest": "0" * 64})
    replaced = tuple(replacement if item == selected else item for item in inventory)
    with pytest.raises(ValueError, match="retained graph inventory"):
        _retained_context(
            compilation, effect, projection, group_request, retained_records=replaced,
        )


def test_validated_sibling_effect_envelopes_expose_their_closed_digest_paths(captured_fact):
    """Sibling arm constructors need no provider run to establish field paths."""
    _, _, group_request = captured_fact
    fact = group_request.ordered_operation_inputs[0].reduction.effect_materialization.accepted_effect
    assert isinstance(fact, BootstrapNativeFactEffectV3)
    correction = BootstrapProposalCorrectionV3.create(
        corrected_fact=fact.fact,
        replacement_fact=fact.fact,
        assertion=fact.fact.assertion,
        correction_anchor=fact.fact.predicate_anchor,
    )
    correction_effect = BootstrapNativeCorrectionEffectV3.create(
        kind="correction",
        correction=correction,
        corrected_targets=(),
        replacement_effect=BootstrapNativeFactEffectV3.create(
            kind="fact",
            fact=fact.fact,
            target_bindings=fact.target_bindings,
            planning_records=fact.planning_records,
            terminal_bindings=fact.terminal_bindings,
            evidence_projections=fact.evidence_projections,
        ),
        transition_records=(),
    )
    retraction = BootstrapProposalRetractionV3.create(
        retracted_fact=fact.fact,
        assertion=fact.fact.assertion,
        retraction_anchor=fact.fact.predicate_anchor,
    )
    retraction_effect = BootstrapNativeRetractionEffectV3.create(
        kind="retraction",
        retraction=retraction,
        retracted_targets=(),
        transition_records=(),
        evidence_projections=fact.evidence_projections,
    )
    participant = BootstrapProposalActionRoleParticipantV3.create(
        mention_digest=fact.fact.subject_mention_digest,
        grounding=(fact.fact.assertion,),
    )
    binding = BootstrapProposalActionRoleBindingV3.create(
        role_id="actor", endpoint_kind="actor", participants=(participant,),
    )
    action = BootstrapProposalActionStateV3.create(
        action_anchor=fact.fact.predicate_anchor,
        logical_action_digest=contract_digest(
            b"memorii.semantic-ingestion.bootstrap-proposal-logical-action.v3",
            {"action_anchor": fact.fact.predicate_anchor, "role_bindings": (binding,)},
        ),
        role_bindings=(binding,),
        state_id="observed",
        state_anchor=fact.fact.assertion,
        execution_branch=None,
        execution_branch_digest=None,
        assertion=fact.fact.assertion,
        temporal_qualifiers=(),
    )
    action_effect = BootstrapNativeActionStateEffectV3.create(
        kind="action_state",
        action_state=action,
        resolved_participants=(),
        planning_records=fact.planning_records,
        terminal_bindings=fact.terminal_bindings,
        evidence_projections=fact.evidence_projections,
    )
    expected = (
        (correction_effect, (correction_effect.effect_digest, correction_effect.replacement_effect.effect_digest)),
        (retraction_effect, (retraction_effect.effect_digest,)),
        (action_effect, (action_effect.effect_digest,)),
    )
    for effect, digests in expected:
        projections, records, effect_digests = _effect_authority(effect)
        assert projections == fact.evidence_projections
        assert effect_digests == digests
        assert records == (() if effect.kind == "retraction" else fact.planning_records)
        if effect.kind == "action_state":
            compilation = group_request.ordered_operation_inputs[0].reduction.native_compilation
            inventory = _retained_inventory(effect, group_request)
            context = _retained_context(compilation, effect, projections[0], group_request,
                                        retained_records=inventory)
            assert context.target_kind == "claim_assertion"
            with pytest.raises(ValueError, match="missing cited native target"):
                _retained_context(compilation, effect.model_copy(update={"planning_records": ()}),
                                  projections[0], group_request, retained_records=inventory)


def test_identity_policy_context_is_a_validated_optional_construction_field(captured_fact):
    _, _, group_request = captured_fact
    compilation = group_request.ordered_operation_inputs[0].reduction.native_compilation
    authority = compilation.operation_input.planning_construction_authority
    assert authority is not None
    identity = BootstrapNativeIdentityConstructionAuthorityV3.create(
        graph_free_identity_input_digest="1" * 64,
        authority_record_id="identity-authority:feasibility",
        authority_record_digest="2" * 64,
        verifier_id="feasibility-verifier",
        semantic_authorization_read_set_digest="3" * 64,
        identity_policy_fingerprint="4" * 64,
        operation_fence_id="identity-fence:feasibility",
        operation_fence_binding_digest="5" * 64,
    )
    values = {name: getattr(authority, name) for name in type(authority).model_fields
              if name not in {"schema_version", "authority_digest"}}
    values["identity_construction"] = identity
    with_identity = authority.__class__.create(**values)
    updated = compilation.model_copy(update={"operation_input": compilation.operation_input.model_copy(
        update={"planning_construction_authority": with_identity}
    )})
    assert identity.identity_policy_fingerprint in _policy_context(updated)
    # No validated identity materialization producer exists yet. The native
    # schema nevertheless fixes the only retained record owner this recipe may
    # inspect; it must not silently fall back to fact planning records.
    fields = BootstrapNativeIdentityEffectV3.model_fields
    assert fields["materialization"].annotation is BootstrapNativeIdentityMaterializationV3
    owned = BootstrapNativeIdentityMaterializationV3.model_fields
    assert owned["lineage_record"].annotation is BootstrapNativePlanningRecordV3
    assert owned["revision_and_alias_records"].annotation == tuple[BootstrapNativePlanningRecordV3, ...]
    assert owned["reference_disposition_records"].annotation == tuple[BootstrapNativePlanningRecordV3, ...]
    assert _policy_context(updated) == tuple(sorted(set(_policy_context(compilation)) | {identity.identity_policy_fingerprint}))

    # A repeated retained fingerprint appears once, regardless of its owner.
    duplicate_identity = BootstrapNativeIdentityConstructionAuthorityV3.create(**{
        **{name: getattr(identity, name) for name in type(identity).model_fields
           if name not in {"schema_version", "construction_digest"}},
        "identity_policy_fingerprint": authority.action_policy_fingerprint,
    })
    duplicate_authority = type(authority).create(**{**values, "identity_construction": duplicate_identity})
    duplicate_compilation = compilation.model_copy(update={"operation_input": compilation.operation_input.model_copy(
        update={"planning_construction_authority": duplicate_authority}
    )})
    assert _policy_context(duplicate_compilation) == _policy_context(compilation)


def _recreate(value, **changes):
    return type(value).create(**{
        **{name: getattr(value, name) for name in type(value).model_fields
           if name not in {"schema_version", value._digest_field}},
        **changes,
    })


@pytest.mark.parametrize("coordinate", ("authorizing_group", "commit_group"))
def test_commit_authority_substitution_cannot_reinterpret_retained_inventory(captured_fact, coordinate):
    _, _, request = captured_fact
    reduction = request.ordered_operation_inputs[0].reduction
    effect = reduction.effect_materialization.accepted_effect
    commit = _commit_values(request)
    authorizing_group = request.transaction_group_id
    if coordinate == "authorizing_group":
        authorizing_group = "foreign-group"
    else:
        commit = commit.model_copy(update={"transaction_group_id": "foreign-group"})
    with pytest.raises(ValueError):
        retained_context(
            reduction.native_compilation, effect, effect.evidence_projections[0],
            commit_values=commit, authorizing_transaction_group_id=authorizing_group,
            retained_records=_retained_inventory(effect, request),
        )


def test_target_metadata_cannot_replace_canonical_payload_identity(captured_fact):
    _, _, request = captured_fact
    reduction = request.ordered_operation_inputs[0].reduction
    effect = reduction.effect_materialization.accepted_effect
    projection = effect.evidence_projections[0]
    target_id = projection.citation_record.planning_payload.planning_record["cited_record_id"]
    target = next(item for item in effect.planning_records if item.record_id == target_id)
    changed_target = _recreate(target, record_id="metadata-only-substitution")
    citation_payload = dict(projection.citation_record.planning_payload.planning_record)
    citation_payload["cited_record_id"] = changed_target.record_id
    citation = _recreate(projection.citation_record, planning_payload=type(projection.citation_record.planning_payload)(
        planning_record=citation_payload,
    ))
    changed_projection = _recreate(projection, citation_record=citation)
    changed_effect = _recreate(effect, planning_records=tuple(
        changed_target if item == target else item for item in effect.planning_records
    ), evidence_projections=(changed_projection,))
    inventory = tuple(
        materialize_canonical_planning_payload(citation.planning_payload,
            commit_values=_commit_values(request), authorizing_transaction_group_id=request.transaction_group_id)
        if item.record_kind == "citation" and item.citation_id == citation.record_id else item
        for item in _retained_inventory(effect, request)
    )
    with pytest.raises(ValueError, match="canonical materialized identity"):
        _retained_context(reduction.native_compilation, changed_effect, changed_projection, request,
                          retained_records=inventory)


def test_correction_and_retraction_resolve_their_single_owned_transition(captured_fact):
    _, _, request = captured_fact
    reduction = request.ordered_operation_inputs[0].reduction
    fact = reduction.effect_materialization.accepted_effect
    compilation = reduction.native_compilation
    carrier = next(item for item in accepted_terminal(
        operation_id=compilation.operation_id, operation_kind="correction",
    ).accepted_carriers if isinstance(item, TemporalTransitionRecord))
    # The generic terminal fixture derives its own operation identity. Rebind
    # its typed transition authority to this native operation through owners.
    original_binding = carrier.temporal_decision_binding
    attachment = type(original_binding.temporal_attachment).create(**{
        **{name: getattr(original_binding.temporal_attachment, name)
           for name in type(original_binding.temporal_attachment).model_fields if name != "binding_digest"},
        "operation_id": compilation.operation_id,
    })
    binding = type(original_binding).create(**{
        **{name: getattr(original_binding, name) for name in type(original_binding).model_fields
           if name != "binding_digest"},
        "operation_id": compilation.operation_id, "temporal_attachment": attachment,
    })
    body = {**carrier.model_dump(mode="python", exclude={"record_digest"}),
            "operation_id": compilation.operation_id,
            "temporal_decision_binding": binding.model_dump(mode="python")}
    carrier = TemporalTransitionRecord.model_validate({
        **body, "record_digest": contract_digest(b"memorii.semantic-ingestion.temporal-carrier.v1", body),
    })
    transition = BootstrapNativePlanningRecordV3.create(
        operation_execution_id=compilation.operation_execution_id,
        record_kind="temporal_transition", record_id=carrier.transition_id,
        precondition=AbsentPlanningPrecondition(),
        planning_payload=canonical_planning_payload_from_record(carrier,
            transaction_group_id=request.transaction_group_id),
        source_member_digest=fact.fact.fact_digest,
    )
    original = fact.evidence_projections[0]
    payload = dict(original.citation_record.planning_payload.planning_record)
    payload["cited_record_id"] = transition.record_id
    citation = _recreate(original.citation_record, planning_payload=type(original.citation_record.planning_payload)(
        planning_record=payload,
    ))
    projection = _recreate(original, citation_record=citation)
    # The actual reducer stores transitions both in replacement.planning_records
    # and as an exact subset view on the correction envelope.
    replacement = _recreate(fact, planning_records=(transition,), evidence_projections=(projection,))
    correction = BootstrapNativeCorrectionEffectV3.create(
        kind="correction", correction=BootstrapProposalCorrectionV3.create(
            corrected_fact=fact.fact, replacement_fact=fact.fact, assertion=fact.fact.assertion,
            correction_anchor=fact.fact.predicate_anchor),
        corrected_targets=(), replacement_effect=replacement, transition_records=(transition,),
    )
    retraction = BootstrapNativeRetractionEffectV3.create(
        kind="retraction", retraction=BootstrapProposalRetractionV3.create(
            retracted_fact=fact.fact, assertion=fact.fact.assertion, retraction_anchor=fact.fact.predicate_anchor),
        retracted_targets=(), transition_records=(transition,), evidence_projections=(projection,),
    )
    for effect in (correction, retraction):
        inventory = _retained_inventory(effect, request)
        context = _retained_context(compilation, effect, projection, request, retained_records=inventory)
        assert (context.target_kind, context.target_id) == ("temporal_transition", transition.record_id)
        assert _effect_authority(effect)[1] == (transition,)
        commit = _commit_values(request)
        with pytest.raises(ValueError, match="retained graph inventory"):
            retained_context(compilation, effect, projection,
                commit_values=commit.model_copy(update={"committed_at": commit.committed_at + timedelta(seconds=1)}),
                authorizing_transaction_group_id=request.transaction_group_id, retained_records=inventory)
        if effect.kind == "correction":
            assert set((effect.effect_digest, replacement.effect_digest)).issubset(context.proof_ancestry_ids)
            broken = effect.model_copy(update={"replacement_effect": replacement.model_copy(
                update={"planning_records": ()})})
        else:
            broken = effect.model_copy(update={"transition_records": ()})
        with pytest.raises(ValueError):
            _retained_context(compilation, broken, projection, request, retained_records=inventory)
