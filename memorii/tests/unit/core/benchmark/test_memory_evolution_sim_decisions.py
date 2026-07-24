from __future__ import annotations

import pytest
from memorii.core.benchmark.memory_evolution_sim import (
    SimSystemOutput,
    memory_evolution_sim_engine_result_from_llm,
    rule_sim_output_for_checkpoint,
    sim_reconstruction_context_for_checkpoint,
)
from memorii.core.llm_decision.models import LLMDecisionMode
from memorii.core.llm_provider.models import LLMStructuredRequest
from memorii.core.prompts.models import PromptModelDefaults
from pydantic import ValidationError
from tests.unit.core.benchmark.memory_evolution_test_helpers import (
    checkpoint_by_type,
    generate_scenario_by_family,
    oracle_shaped_sim_semantic_decision,
    provider_result_for_sim_semantic,
)


def _request() -> LLMStructuredRequest:
    return LLMStructuredRequest(
        request_id="test-memory-evolution-sim-decision",
        prompt_ref="memory_evolution_sim_reconstruction:v1",
        prompt_hash="test",
        system="system",
        user="user",
        output_schema={},
        model_defaults=PromptModelDefaults(model="test-model"),
    )


def test_rule_baseline_is_invariant_to_oracle_annotations() -> None:
    scenario = generate_scenario_by_family(
        profile="long_horizon",
        family="abandoned_then_resumed_work",
        seed=7,
    )
    checkpoint = checkpoint_by_type(scenario, "execution_continuation")

    decision = rule_sim_output_for_checkpoint(scenario=scenario, checkpoint=checkpoint)
    changed_oracle = checkpoint.model_copy(
        update={
            "checkpoint_type": "current_truth",
            "expected_next_action": None,
            "expected_claim_ids": [],
            "expected_execution_claim_ids": [],
        }
    )

    assert rule_sim_output_for_checkpoint(
        scenario=scenario,
        checkpoint=changed_oracle,
    ) == decision


def test_sim_output_rejects_removed_flat_channels() -> None:
    with pytest.raises(ValidationError):
        SimSystemOutput.model_validate(
            {
                "operation": "answer",
                "claim_ids": ["legacy-claim"],
                "rationale": "flat channels are not part of the contract",
            }
        )


def test_llm_engine_rejects_unknown_uncertain_id_and_uses_rule_fallback() -> None:
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
    ).model_copy(update={"uncertain_ids": ["fabricated-composite-id"]})
    rule_output = rule_sim_output_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    ).model_dump(mode="json")

    output, trace, success, failure = memory_evolution_sim_engine_result_from_llm(
        result=provider_result_for_sim_semantic(
            request=_request(),
            decision=semantic,
        ),
        mode=LLMDecisionMode.LLM,
        context=context,
        rule_output=rule_output,
    )

    assert success is False
    assert failure == "llm_semantic_validation_failed"
    assert output == rule_output
    assert [issue.code for issue in trace.validation_issues] == [
        "invalid_uncertain_id"
    ]
    assert trace.fallback_used is True


def test_llm_engine_compiles_support_and_citations_from_semantic_assessments() -> None:
    scenario = generate_scenario_by_family(
        profile="long_horizon",
        family="current_vs_historical_truth",
        seed=7,
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

    output, trace, success, failure = memory_evolution_sim_engine_result_from_llm(
        result=provider_result_for_sim_semantic(
            request=_request(),
            decision=semantic,
        ),
        mode=LLMDecisionMode.LLM,
        context=context,
        rule_output=rule_sim_output_for_checkpoint(
            scenario=scenario,
            checkpoint=checkpoint,
        ).model_dump(mode="json"),
    )

    assert success is True
    assert failure is None
    assert output["supporting_claim_ids"] == output["selected_claim_ids"]
    assert output["supporting_citation_event_ids"]
    assert trace.final_output == output


def test_llm_engine_rejects_invalid_claim_assessment_without_sanitizing_to_success() -> None:
    scenario = generate_scenario_by_family(
        profile="long_horizon",
        family="current_vs_historical_truth",
        seed=7,
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
    invalid_assessments = [
        assessment.model_copy(
            update={"claim_id": "claim:not-visible"}
        )
        if index == 0
        else assessment
        for index, assessment in enumerate(semantic.claim_assessments)
    ]
    invalid = semantic.model_copy(
        update={"claim_assessments": invalid_assessments}
    )
    rule_output = rule_sim_output_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    ).model_dump(mode="json")

    output, trace, success, failure = memory_evolution_sim_engine_result_from_llm(
        result=provider_result_for_sim_semantic(
            request=_request(),
            decision=invalid,
        ),
        mode=LLMDecisionMode.LLM,
        context=context,
        rule_output=rule_output,
    )

    assert success is False
    assert failure == "llm_semantic_validation_failed"
    assert output == rule_output
    assert {"invalid_claim_id", "missing_claim_assessment"}.issubset(
        {issue.code for issue in trace.validation_issues}
    )
    assert trace.fallback_used is True
