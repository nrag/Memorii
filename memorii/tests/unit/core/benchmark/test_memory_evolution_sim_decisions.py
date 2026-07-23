from __future__ import annotations

import pytest
from memorii.core.benchmark.memory_evolution_sim import (
    SimSystemOutput,
    expected_sim_output_for_checkpoint,
    fake_llm_result_for_memory_evolution_sim,
    memory_evolution_sim_engine_result_from_llm,
    rule_sim_output_for_checkpoint,
)
from memorii.core.llm_decision.models import LLMDecisionMode
from memorii.core.llm_provider.models import LLMStructuredRequest
from memorii.core.prompts.models import PromptModelDefaults
from pydantic import ValidationError
from tests.unit.core.benchmark.memory_evolution_test_helpers import (
    checkpoint_by_type,
    generate_scenario_by_family,
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

    assert rule_sim_output_for_checkpoint(scenario=scenario, checkpoint=changed_oracle) == decision


def test_sim_output_rejects_removed_flat_channels() -> None:
    with pytest.raises(ValidationError):
        SimSystemOutput.model_validate(
            {
                "operation": "answer",
                "claim_ids": ["legacy-claim"],
                "rationale": "flat channels are not part of the contract",
            }
        )


def test_llm_engine_preserves_explicit_role_channels_without_evaluator_repair() -> None:
    scenario = generate_scenario_by_family(
        profile="long_horizon",
        family="current_vs_historical_truth",
        seed=7,
    )
    checkpoint = checkpoint_by_type(scenario, "current_truth")
    live_output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={"supporting_claim_ids": [], "supporting_citation_event_ids": []}
    )
    result = fake_llm_result_for_memory_evolution_sim(request=_request(), decision=live_output)

    output, _trace, success, failure = memory_evolution_sim_engine_result_from_llm(
        result=result,
        mode=LLMDecisionMode.LLM,
        scenario=scenario,
        rule_output=rule_sim_output_for_checkpoint(
            scenario=scenario,
            checkpoint=checkpoint,
        ).model_dump(mode="json"),
    )

    assert success is True
    assert failure is None
    assert output == live_output.model_dump(mode="json")


def test_llm_engine_reports_invalid_role_channel_ids_without_fallback_rewrite() -> None:
    scenario = generate_scenario_by_family(
        profile="long_horizon",
        family="current_vs_historical_truth",
        seed=7,
    )
    checkpoint = checkpoint_by_type(scenario, "current_truth")
    live_output = expected_sim_output_for_checkpoint(checkpoint).model_copy(
        update={"rejection_citation_event_ids": ["event:not-visible"]}
    )
    result = fake_llm_result_for_memory_evolution_sim(request=_request(), decision=live_output)

    output, trace, success, failure = memory_evolution_sim_engine_result_from_llm(
        result=result,
        mode=LLMDecisionMode.LLM,
        scenario=scenario,
        rule_output=rule_sim_output_for_checkpoint(
            scenario=scenario,
            checkpoint=checkpoint,
        ).model_dump(mode="json"),
    )

    assert success is False
    assert failure == "llm_output_referenced_invalid_ids"
    assert output == live_output.model_dump(mode="json")
    assert trace.validation_errors == ["invalid_rejection_citation_event_ids:event:not-visible"]
