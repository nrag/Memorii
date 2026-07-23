from __future__ import annotations

from memorii.core.benchmark.memory_evolution_sim import (
    JudgeVerdict,
    SimSemanticViolationCode,
    compile_sim_semantic_decision,
    expected_sim_semantic_decision_for_checkpoint,
    generate_memory_evolution_sim_scenarios,
    judge_sim_checkpoint,
    remap_scenario_ids,
    render_sim_answer,
    sim_reconstruction_context_for_checkpoint,
    validate_sim_semantic_decision,
)
from tests.unit.core.benchmark.memory_evolution_test_helpers import (
    checkpoint_by_type,
    generate_scenario_by_family,
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
                semantic = expected_sim_semantic_decision_for_checkpoint(checkpoint)
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
    semantic = expected_sim_semantic_decision_for_checkpoint(checkpoint)
    ownership = next(
        claim
        for claim in context.visible_claims
        if claim.predicate_id not in {"action_state", "status", "progress"} and "action" not in claim.predicate_id
    )
    blocked = next(claim for claim in context.visible_claims if claim.object_value.casefold() == "blocked")

    ownership_validation = validate_sim_semantic_decision(
        context=context,
        semantic=semantic.model_copy(
            update={
                "selected_claim_ids": [ownership.claim_id],
                "considered_claim_ids": [ownership.claim_id],
            }
        ),
    )
    blocked_validation = validate_sim_semantic_decision(
        context=context,
        semantic=semantic.model_copy(
            update={
                "selected_claim_ids": [blocked.claim_id],
                "considered_claim_ids": [blocked.claim_id],
            }
        ),
    )

    assert SimSemanticViolationCode.NON_ACTION_SELECTED_FOR_EXECUTION in ownership_validation.violation_codes
    assert SimSemanticViolationCode.INACTIVE_ACTION_SELECTED_FOR_EXECUTION in blocked_validation.violation_codes


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
    semantic = expected_sim_semantic_decision_for_checkpoint(checkpoint)
    expected = compile_sim_semantic_decision(context=context, semantic=semantic)
    irrelevant = context.visible_claims[0].model_copy(
        update={
            "claim_id": "irrelevant-visible-claim",
            "subject_entity_id": "irrelevant-visible-entity",
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

    actual = compile_sim_semantic_decision(context=changed, semantic=semantic)

    assert actual == expected
    assert "irrelevant-visible" not in str(actual.model_dump(mode="json"))


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
            semantic=expected_sim_semantic_decision_for_checkpoint(checkpoint),
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
    semantic = expected_sim_semantic_decision_for_checkpoint(checkpoint)
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
