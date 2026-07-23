from __future__ import annotations

from memorii.core.benchmark.fixture_sets.memory_evolution_v1 import load_memory_evolution_v1_fixture_set
from memorii.core.benchmark.memory_evolution_decision import (
    MemoryEvolutionSemanticViolationCode,
    compile_memory_evolution_decision,
    expected_memory_evolution_semantic_decision_for_checkpoint,
    memory_evolution_context_for_checkpoint,
    memory_evolution_decision_diagnostics,
    render_memory_evolution_answer,
    validate_memory_evolution_semantic_decision,
)


def _scenario(scenario_id: str):
    return next(scenario for scenario in load_memory_evolution_v1_fixture_set() if scenario.scenario_id == scenario_id)


def test_compiled_oracle_semantics_pass_every_curated_checkpoint() -> None:
    for scenario in load_memory_evolution_v1_fixture_set():
        for checkpoint in scenario.checkpoints:
            context = memory_evolution_context_for_checkpoint(
                scenario=scenario,
                checkpoint=checkpoint,
            )
            semantic = expected_memory_evolution_semantic_decision_for_checkpoint(
                scenario=scenario,
                checkpoint=checkpoint,
            )

            compiled = compile_memory_evolution_decision(context=context, semantic=semantic)
            diagnostics = memory_evolution_decision_diagnostics(
                scenario=scenario,
                checkpoint=checkpoint,
                decision=compiled.model_dump(mode="json"),
            )

            assert diagnostics.assertion_passed, (
                scenario.scenario_id,
                checkpoint.checkpoint_id,
                diagnostics.failure_buckets,
            )


def test_compilation_keeps_considered_direct_support_out_of_rejected_channel() -> None:
    for scenario in load_memory_evolution_v1_fixture_set():
        for checkpoint in scenario.checkpoints:
            context = memory_evolution_context_for_checkpoint(
                scenario=scenario,
                checkpoint=checkpoint,
            )
            semantic = expected_memory_evolution_semantic_decision_for_checkpoint(
                scenario=scenario,
                checkpoint=checkpoint,
            ).model_copy(
                update={
                    "considered_memory_ids": [
                        card.memory_id for card in context.visible_memory_cards
                    ]
                }
            )

            validation = validate_memory_evolution_semantic_decision(
                context=context,
                semantic=semantic,
            )
            assert validation.valid, (
                scenario.scenario_id,
                checkpoint.checkpoint_id,
                validation.violation_codes,
            )

            compiled = compile_memory_evolution_decision(
                context=context,
                semantic=semantic,
            )
            direct_support = {
                *compiled.answer_selection.selected_memory_ids,
                *compiled.answer_selection.supporting_memory_ids,
                *compiled.answer_selection.citation_memory_ids,
            }
            rejected = set(compiled.retrieval_context.rejected_memory_ids)

            assert not direct_support & rejected, (
                scenario.scenario_id,
                checkpoint.checkpoint_id,
                sorted(direct_support & rejected),
            )


def test_falsified_belief_cannot_become_direct_answer_support() -> None:
    scenario = _scenario("evolution_belief_dependency_degradation")
    checkpoint = scenario.checkpoints[0]
    context = memory_evolution_context_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    )
    semantic = expected_memory_evolution_semantic_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    )
    falsified_id = next(score.memory_id for score in semantic.belief_scores if score.belief_state.value == "falsified")
    invalid = semantic.model_copy(
        update={
            "selected_memory_ids": [falsified_id],
            "considered_memory_ids": [falsified_id],
        }
    )

    validation = validate_memory_evolution_semantic_decision(
        context=context,
        semantic=invalid,
    )

    assert MemoryEvolutionSemanticViolationCode.FALSIFIED_BELIEF_SELECTED in validation.violation_codes


def test_curated_compilation_is_invariant_to_candidate_order_and_irrelevant_insertion() -> None:
    scenario = _scenario("evolution_abandoned_then_resumed_work")
    checkpoint = scenario.checkpoints[0]
    context = memory_evolution_context_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    )
    semantic = expected_memory_evolution_semantic_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    )
    expected = compile_memory_evolution_decision(context=context, semantic=semantic)
    irrelevant = context.visible_memory_cards[0].model_copy(update={"memory_id": "irrelevant-visible-memory"})
    changed = context.model_copy(
        update={
            "visible_memory_cards": [
                irrelevant,
                *reversed(context.visible_memory_cards),
            ],
            "entity_state_cards": list(reversed(context.entity_state_cards)),
            "evidence_effect_cards": list(reversed(context.evidence_effect_cards)),
        }
    )

    actual = compile_memory_evolution_decision(context=changed, semantic=semantic)

    assert actual == expected
    assert "irrelevant-visible-memory" not in str(actual.model_dump(mode="json"))


def test_equivalent_query_wording_does_not_change_compiled_state() -> None:
    scenario = _scenario("evolution_current_vs_historical_truth")
    checkpoint = scenario.checkpoints[0]
    context = memory_evolution_context_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    )
    semantic = expected_memory_evolution_semantic_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    )
    rephrased = context.model_copy(
        update={
            "checkpoint": context.checkpoint.model_copy(update={"query_or_task": "State the presently valid owner."})
        }
    )

    assert compile_memory_evolution_decision(
        context=rephrased,
        semantic=semantic,
    ) == compile_memory_evolution_decision(
        context=context,
        semantic=semantic,
    )


def test_answer_rendering_cannot_mutate_compiled_channels() -> None:
    scenario = _scenario("evolution_current_vs_historical_truth")
    checkpoint = scenario.checkpoints[0]
    context = memory_evolution_context_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    )
    semantic = expected_memory_evolution_semantic_decision_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    )
    compiled = compile_memory_evolution_decision(context=context, semantic=semantic)
    rendered = render_memory_evolution_answer(
        decision=compiled,
        semantic=semantic.model_copy(update={"answer": "Equivalent rendered answer"}),
    )
    compiled_payload = compiled.model_dump(mode="json")
    rendered_payload = rendered.model_dump(mode="json")

    assert rendered_payload.pop("answer") == "Equivalent rendered answer"
    compiled_payload.pop("answer")
    assert rendered_payload == compiled_payload
