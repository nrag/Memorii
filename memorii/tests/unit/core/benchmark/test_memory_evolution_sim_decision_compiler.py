from __future__ import annotations

from memorii.core.benchmark.memory_evolution_sim import (
    JudgeVerdict,
    SimClaimAssessment,
    SimClaimSemanticRole,
    SimDecisionContractViolationCode,
    compile_sim_semantic_decision,
    generate_memory_evolution_sim_scenarios,
    judge_sim_checkpoint,
    remap_scenario_ids,
    render_sim_answer,
    sim_reconstruction_context_for_checkpoint,
    validate_sim_decision_contract,
)
from memorii.core.benchmark.memory_evolution_sim.visible_output_validation import (
    validate_visible_sim_output,
)
from tests.unit.core.benchmark.memory_evolution_test_helpers import (
    checkpoint_by_type,
    generate_scenario_by_family,
    oracle_shaped_sim_semantic_decision,
)


def test_compiled_oracle_semantics_pass_adversarial_and_long_horizon_checkpoints() -> None:
    for profile in ("adversarial", "long_horizon"):
        scenarios = generate_memory_evolution_sim_scenarios(
            profile=profile,
            scenario_count=10,
            seed=7,
            noise_rate=0.35,
        )
        for scenario in scenarios:
            for checkpoint in scenario.checkpoints:
                context = sim_reconstruction_context_for_checkpoint(
                    scenario=scenario,
                    checkpoint=checkpoint,
                )
                semantic = oracle_shaped_sim_semantic_decision(
                    context=context,
                    checkpoint=checkpoint,
                )
                output = compile_sim_semantic_decision(context=context, semantic=semantic)
                aggregate = judge_sim_checkpoint(
                    scenario=scenario,
                    checkpoint=checkpoint,
                    output=output,
                )

                assert aggregate.verdict == JudgeVerdict.PASS, (
                    profile,
                    scenario.family,
                    checkpoint.checkpoint_type,
                    aggregate.critical_failure_buckets,
                )
                assert aggregate.review_required is False


def test_execution_rejects_ownership_and_inactive_action_claims() -> None:
    scenario = generate_scenario_by_family(
        profile="long_horizon",
        family="abandoned_then_resumed_work",
        seed=7,
        noise_rate=0.35,
    )
    checkpoint = checkpoint_by_type(scenario, "execution_continuation")
    context = sim_reconstruction_context_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    )
    semantic = oracle_shaped_sim_semantic_decision(
        context=context,
        checkpoint=checkpoint,
    )
    ownership = next(
        claim
        for claim in context.visible_claims
        if claim.predicate_id not in {"action_state", "status", "progress"} and "action" not in claim.predicate_id
    )
    blocked = next(claim for claim in context.visible_claims if claim.object_value.casefold() == "blocked")

    ownership_assessments = [
        assessment.model_copy(
            update={
                "role": (
                    SimClaimSemanticRole.PRIMARY
                    if assessment.claim_id == ownership.claim_id
                    else SimClaimSemanticRole.IRRELEVANT
                )
            }
        )
        for assessment in semantic.claim_assessments
    ]
    blocked_assessments = [
        assessment.model_copy(
            update={
                "role": (
                    SimClaimSemanticRole.PRIMARY
                    if assessment.claim_id == blocked.claim_id
                    else SimClaimSemanticRole.IRRELEVANT
                )
            }
        )
        for assessment in semantic.claim_assessments
    ]
    ownership_validation = validate_sim_decision_contract(
        context=context,
        semantic=semantic.model_copy(update={"claim_assessments": ownership_assessments}),
    )
    blocked_validation = validate_sim_decision_contract(
        context=context,
        semantic=semantic.model_copy(update={"claim_assessments": blocked_assessments}),
    )

    assert SimDecisionContractViolationCode.NON_ACTION_SELECTED_FOR_EXECUTION in {
        issue.code for issue in ownership_validation.issues
    }
    assert SimDecisionContractViolationCode.INACTIVE_ACTION_SELECTED_FOR_EXECUTION in {
        issue.code for issue in blocked_validation.issues
    }


def test_sim_compilation_is_invariant_to_candidate_order_and_irrelevant_insertion() -> None:
    scenario = generate_scenario_by_family(
        profile="adversarial",
        family="entity_split",
        seed=7,
        noise_rate=0.35,
    )
    checkpoint = checkpoint_by_type(scenario, "entity_split_repair")
    context = sim_reconstruction_context_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    )
    semantic = oracle_shaped_sim_semantic_decision(
        context=context,
        checkpoint=checkpoint,
    )
    expected = compile_sim_semantic_decision(context=context, semantic=semantic)
    irrelevant = context.visible_claims[0].model_copy(
        update={
            "claim_id": "irrelevant-visible-claim",
            "subject_entity_id": "irrelevant-visible-entity",
            "predicate_id": "unrelated_test_predicate",
            "object_entity_id": None,
            "object_entity_type": None,
        }
    )
    changed = context.model_copy(
        update={
            "visible_claim_ids": [
                "irrelevant-visible-claim",
                *reversed(context.visible_claim_ids),
            ],
            "visible_claims": [irrelevant, *reversed(context.visible_claims)],
            "visible_relations": list(reversed(context.visible_relations)),
            "visible_entities": list(reversed(context.visible_entities)),
            "visible_events": list(reversed(context.visible_events)),
        }
    )

    changed_semantic = semantic.model_copy(
        update={
            "claim_assessments": [
                *semantic.claim_assessments,
                SimClaimAssessment(
                    claim_id="irrelevant-visible-claim",
                    role=SimClaimSemanticRole.IRRELEVANT,
                    belief_rank=None,
                ),
            ]
        }
    )
    actual = compile_sim_semantic_decision(
        context=changed,
        semantic=changed_semantic,
    )

    assert actual == expected
    assert "irrelevant-visible" not in str(actual.model_dump(mode="json"))


def test_compiler_places_context_only_definitions_outside_selected_truth() -> None:
    scenario = generate_scenario_by_family(
        profile="adversarial",
        family="current_vs_historical_truth",
        seed=7,
        noise_rate=0.35,
    )
    checkpoint = checkpoint_by_type(scenario, "current_truth")
    context = sim_reconstruction_context_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    )
    semantic = oracle_shaped_sim_semantic_decision(
        context=context,
        checkpoint=checkpoint,
    )
    output = compile_sim_semantic_decision(context=context, semantic=semantic)
    selected_subjects = {
        claim.subject_entity_id
        for claim in context.visible_claims
        if claim.claim_id in output.selected_claim_ids
        and claim.predicate_id != "entity_type"
    }
    definitions = {
        claim.claim_id
        for claim in context.visible_claims
        if claim.predicate_id == "entity_type"
        and claim.lifecycle_state == "active"
        and claim.subject_entity_id in selected_subjects
    }

    assert definitions
    assert definitions.isdisjoint(output.selected_claim_ids)
    assert definitions <= set(output.context_claim_ids)
    assert validate_visible_sim_output(context=context, output=output) == ()


def test_id_permutation_preserves_compiler_judgment() -> None:
    scenario = generate_scenario_by_family(
        profile="long_horizon",
        family="current_vs_historical_truth",
        seed=7,
        noise_rate=0.35,
    )
    permuted = remap_scenario_ids(
        scenario,
        permutation_seed="semantic-compiler-metamorphic",
    )

    for candidate in (scenario, permuted):
        checkpoint = checkpoint_by_type(candidate, "current_truth")
        context = sim_reconstruction_context_for_checkpoint(
            scenario=candidate,
            checkpoint=checkpoint,
        )
        output = compile_sim_semantic_decision(
            context=context,
            semantic=oracle_shaped_sim_semantic_decision(
                context=context,
                checkpoint=checkpoint,
            ),
        )
        aggregate = judge_sim_checkpoint(
            scenario=candidate,
            checkpoint=checkpoint,
            output=output,
        )

        assert aggregate.verdict == JudgeVerdict.PASS
        assert aggregate.review_required is False


def test_sim_answer_rendering_cannot_mutate_graph_channels() -> None:
    scenario = generate_scenario_by_family(
        profile="adversarial",
        family="current_vs_historical_truth",
        seed=7,
        noise_rate=0.35,
    )
    checkpoint = checkpoint_by_type(scenario, "current_truth")
    context = sim_reconstruction_context_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    )
    semantic = oracle_shaped_sim_semantic_decision(
        context=context,
        checkpoint=checkpoint,
    )
    compiled = compile_sim_semantic_decision(context=context, semantic=semantic)
    rendered = render_sim_answer(
        output=compiled,
        semantic=semantic.model_copy(update={"answer": "Equivalent rendered answer"}),
    )
    compiled_payload = compiled.model_dump(mode="json")
    rendered_payload = rendered.model_dump(mode="json")

    assert rendered_payload.pop("answer") == "Equivalent rendered answer"
    compiled_payload.pop("answer")
    assert rendered_payload == compiled_payload


def test_hidden_expectation_mutation_cannot_change_compilation_but_changes_judgment() -> None:
    scenario = generate_scenario_by_family(
        profile="adversarial",
        family="current_vs_historical_truth",
        seed=7,
        noise_rate=0.35,
    )
    checkpoint = checkpoint_by_type(scenario, "current_truth")
    context = sim_reconstruction_context_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    )
    semantic = oracle_shaped_sim_semantic_decision(
        context=context,
        checkpoint=checkpoint,
    )
    compiled = compile_sim_semantic_decision(context=context, semantic=semantic)
    mutated_checkpoint = checkpoint.model_copy(
        update={
            "expected_entity_ids": ["hidden:wrong-entity"],
            "expected_claim_ids": ["hidden:wrong-claim"],
            "expected_citation_event_ids": ["hidden:wrong-event"],
            "expected_answer": "hidden wrong answer",
        }
    )
    mutated_context = sim_reconstruction_context_for_checkpoint(
        scenario=scenario,
        checkpoint=mutated_checkpoint,
    )
    compiled_with_mutated_oracle = compile_sim_semantic_decision(
        context=mutated_context,
        semantic=semantic,
    )

    assert mutated_context == context
    assert compiled_with_mutated_oracle == compiled
    assert judge_sim_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
        output=compiled,
    ).verdict == JudgeVerdict.PASS
    assert judge_sim_checkpoint(
        scenario=scenario,
        checkpoint=mutated_checkpoint,
        output=compiled,
    ).verdict == JudgeVerdict.FAIL


def test_audit_graph_entity_policy_is_consistent_across_compiler_and_validator() -> None:
    scenario = generate_scenario_by_family(
        profile="adversarial",
        family="entity_split",
        seed=7,
        noise_rate=0.35,
    )
    checkpoint = checkpoint_by_type(scenario, "entity_split_repair")
    checkpoint = checkpoint.model_copy(
        update={
            "task_contract": checkpoint.task_contract.model_copy(
                update={"selected_entity_role_policy": "audit_graph_entities"}
            )
        }
    )
    context = sim_reconstruction_context_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    )
    semantic = oracle_shaped_sim_semantic_decision(
        context=context,
        checkpoint=checkpoint,
    )

    output = compile_sim_semantic_decision(context=context, semantic=semantic)
    issue_codes = {issue.code for issue in validate_visible_sim_output(context=context, output=output)}

    assert output.selected_entity_ids == []
    assert "selected_entity_role_mismatch" not in issue_codes
