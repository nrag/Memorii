from __future__ import annotations

from collections import Counter

from memorii.core.benchmark.fixture_sets.memory_evolution_v1 import (
    load_memory_evolution_v1_fixture_set,
)
from memorii.core.benchmark.memory_evolution_decision import (
    expected_memory_evolution_semantic_decision_for_checkpoint,
    fake_llm_result_for_memory_evolution,
    memory_evolution_context_for_checkpoint,
    memory_evolution_decision_diagnostics,
    memory_evolution_engine_result_from_llm,
    rule_memory_evolution_decision_for_checkpoint,
)
from memorii.core.benchmark.memory_evolution_sim import (
    JudgeVerdict,
    SimSystemOutput,
    generate_memory_evolution_sim_scenarios,
    judge_sim_checkpoint,
    memory_evolution_sim_engine_result_from_llm,
    rule_sim_output_for_checkpoint,
    sim_reconstruction_context_for_checkpoint,
)
from memorii.core.benchmark.memory_evolution_sim.visible_output_validation import (
    validate_visible_sim_output,
)
from memorii.core.llm_decision.models import LLMDecisionMode
from memorii.core.llm_provider.models import LLMStructuredRequest
from memorii.core.prompts.models import PromptModelDefaults
from tests.unit.core.benchmark.memory_evolution_test_helpers import (
    oracle_shaped_sim_semantic_decision,
    provider_result_for_sim_semantic,
)

_CURATED_FAILURES = {
    (
        "curated_llm",
        "evolution_current_vs_historical_truth",
        "checkpoint:atlas-owner-january",
    ),
}

_SIM_FAILURES = {
    ("long_llm", "oid_33fcdc090f4d4008eaf3", "oid_2288e7a5ae26d5c5f24e"),
    ("long_llm", "oid_9ce86c7cb379cbcbe6d3", "oid_a14cb3682fd05ae8a18a"),
    ("long_hybrid", "oid_33fcdc090f4d4008eaf3", "oid_2288e7a5ae26d5c5f24e"),
    ("long_hybrid", "oid_9ce86c7cb379cbcbe6d3", "oid_a14cb3682fd05ae8a18a"),
    ("adversarial_llm", "oid_2d1db2a7b6866110d7be", "oid_f41bbeb17c14dc25cbda"),
    ("adversarial_llm", "oid_f92c667b9cc6e81fee74", "oid_6dad5521a38ef27d95a1"),
    ("adversarial_llm", "oid_150209408cb8c026a8cf", "oid_4166db9732fc3e453eaf"),
    ("adversarial_llm", "oid_150209408cb8c026a8cf", "oid_30acef56657ad5fafbd0"),
    ("adversarial_hybrid", "oid_2d1db2a7b6866110d7be", "oid_f41bbeb17c14dc25cbda"),
    ("adversarial_hybrid", "oid_f92c667b9cc6e81fee74", "oid_6dad5521a38ef27d95a1"),
    ("adversarial_hybrid", "oid_1aa1ad401446205a5fe9", "oid_1fbb6db0ed38322148a4"),
    ("adversarial_hybrid", "oid_150209408cb8c026a8cf", "oid_4166db9732fc3e453eaf"),
    ("adversarial_hybrid", "oid_150209408cb8c026a8cf", "oid_30acef56657ad5fafbd0"),
}


def _request(*, request_id: str, prompt_ref: str) -> LLMStructuredRequest:
    return LLMStructuredRequest(
        request_id=request_id,
        prompt_ref=prompt_ref,
        prompt_hash="artifact-replay",
        system="",
        user="",
        output_schema={},
        model_defaults=PromptModelDefaults(model="test-model"),
    )


def test_six_live_artifact_cohorts_replay_through_repaired_engine_contracts() -> None:
    cohort_counts: Counter[str] = Counter()

    curated_scenarios = load_memory_evolution_v1_fixture_set()
    for label, mode in (
        ("curated_llm", LLMDecisionMode.LLM),
        ("curated_hybrid", LLMDecisionMode.HYBRID),
    ):
        for scenario in curated_scenarios:
            for checkpoint in scenario.checkpoints:
                key = (label, scenario.scenario_id, checkpoint.checkpoint_id)
                cohort_counts[
                    "failure" if key in _CURATED_FAILURES else "true_success"
                ] += 1
                context = memory_evolution_context_for_checkpoint(
                    scenario=scenario,
                    checkpoint=checkpoint,
                )
                rule_output = rule_memory_evolution_decision_for_checkpoint(
                    scenario=scenario,
                    checkpoint=checkpoint,
                ).model_dump(mode="json")
                semantic = expected_memory_evolution_semantic_decision_for_checkpoint(
                    scenario=scenario,
                    checkpoint=checkpoint,
                )
                result = fake_llm_result_for_memory_evolution(
                    request=_request(
                        request_id=":".join(key),
                        prompt_ref="memory_evolution_decision:v1",
                    ),
                    decision=semantic,
                    provider_name="artifact-replay",
                )

                output, _trace, success, failure_mode = (
                    memory_evolution_engine_result_from_llm(
                        result=result,
                        mode=mode,
                        context=context,
                        rule_output=rule_output,
                    )
                )
                diagnostics = memory_evolution_decision_diagnostics(
                    scenario=scenario,
                    checkpoint=checkpoint,
                    decision=output,
                )

                assert success is True, key
                assert failure_mode is None, key
                assert diagnostics.assertion_passed is True, key

    for profile, label_prefix in (
        ("long_horizon", "long"),
        ("adversarial", "adversarial"),
    ):
        scenarios = generate_memory_evolution_sim_scenarios(
            profile=profile,
            scenario_count=10,
            seed=7,
            noise_rate=0.35,
        )
        for mode_name, mode in (
            ("llm", LLMDecisionMode.LLM),
            ("hybrid", LLMDecisionMode.HYBRID),
        ):
            label = f"{label_prefix}_{mode_name}"
            for scenario in scenarios:
                for checkpoint in scenario.checkpoints:
                    key = (label, scenario.scenario_id, checkpoint.checkpoint_id)
                    if key in _SIM_FAILURES:
                        cohort = "failure"
                    elif (
                        checkpoint.task_contract.belief_ranking_policy
                        == "forbidden"
                    ):
                        cohort = "false_success"
                    else:
                        cohort = "true_success"
                    cohort_counts[cohort] += 1

                    context = sim_reconstruction_context_for_checkpoint(
                        scenario=scenario,
                        checkpoint=checkpoint,
                    )
                    semantic = oracle_shaped_sim_semantic_decision(
                        context=context,
                        checkpoint=checkpoint,
                    )
                    result = provider_result_for_sim_semantic(
                        request=_request(
                            request_id=":".join(key),
                            prompt_ref="memory_evolution_sim_reconstruction:v1",
                        ),
                        decision=semantic,
                        provider_name="artifact-replay",
                    )
                    rule_output = rule_sim_output_for_checkpoint(
                        scenario=scenario,
                        checkpoint=checkpoint,
                    ).model_dump(mode="json")

                    output_payload, _trace, success, failure_mode = (
                        memory_evolution_sim_engine_result_from_llm(
                            result=result,
                            mode=mode,
                            context=context,
                            rule_output=rule_output,
                        )
                    )
                    output = SimSystemOutput.model_validate(output_payload)
                    aggregate = judge_sim_checkpoint(
                        scenario=scenario,
                        checkpoint=checkpoint,
                        output=output,
                    )

                    assert success is True, key
                    assert failure_mode is None, key
                    assert aggregate.verdict == JudgeVerdict.PASS, key
                    assert aggregate.review_required is False, key

                    if cohort == "false_success":
                        historical_shape = output.model_copy(
                            update={
                                "belief_ranking_ids": [
                                    output.selected_claim_ids[0]
                                    if output.selected_claim_ids
                                    else context.visible_claim_ids[0]
                                ]
                            }
                        )
                        assert "belief_ranking_forbidden" in {
                            issue.code
                            for issue in validate_visible_sim_output(
                                context=context,
                                output=historical_shape,
                            )
                        }, key

    assert cohort_counts == {
        "failure": 14,
        "false_success": 31,
        "true_success": 29,
    }
    assert len(_CURATED_FAILURES | _SIM_FAILURES) == 14
