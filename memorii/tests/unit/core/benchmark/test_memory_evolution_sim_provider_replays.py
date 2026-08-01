from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator
from memorii.core.benchmark.llm_adapters import (
    LLMMemoryEvolutionSimReconstructionAdapter,
)
from memorii.core.benchmark.memory_evolution_sim import (
    JudgeVerdict,
    SimSemanticDecision,
    SimSystemOutput,
    generate_memory_evolution_sim_scenarios,
    judge_sim_checkpoint,
    memory_evolution_sim_engine_result_from_llm,
    rule_sim_output_for_checkpoint,
    sim_reconstruction_context_for_checkpoint,
    validate_sim_decision_contract,
)
from memorii.core.benchmark.memory_evolution_sim.closed_world_schema import (
    constrain_sim_semantic_contract,
)
from memorii.core.llm_decision.models import LLMDecisionMode
from memorii.core.llm_provider.models import LLMStructuredRequest
from memorii.core.prompts.models import PromptModelDefaults
from memorii.core.prompts.registry import PromptRegistry, default_prompt_root
from memorii.core.prompts.runtime_manifest import PromptOwner
from tests.unit.core.benchmark.memory_evolution_test_helpers import (
    provider_result_for_sim_semantic,
)

_FIXTURE_PATH = (
    Path(__file__).parents[3]
    / "fixtures"
    / "memory_evolution_sim"
    / "captured_provider_semantic_decisions.json"
)


def _captured_rows() -> list[dict[str, object]]:
    payload = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, list)
    return payload


def _contract():
    return PromptRegistry(prompt_root=default_prompt_root()).load(
        "memory_evolution_sim_reconstruction:v1",
        owner=PromptOwner.LLM_MEMORY_EVOLUTION_SIM_RECONSTRUCTION_ADAPTER,
        output_model=LLMMemoryEvolutionSimReconstructionAdapter.output_model,
    )


def _request(row: dict[str, object]) -> LLMStructuredRequest:
    return LLMStructuredRequest(
        request_id=f"captured:{row['mode']}:{row['checkpoint_id']}",
        prompt_ref="memory_evolution_sim_reconstruction:v1",
        prompt_hash="captured-provider-replay",
        system="",
        user="",
        output_schema={},
        model_defaults=PromptModelDefaults(model="captured-provider-model"),
    )


def test_captured_provider_decisions_replay_without_oracle_substitution() -> None:
    scenarios = generate_memory_evolution_sim_scenarios(
        profile="adversarial",
        scenario_count=10,
        seed=7,
        noise_rate=0.35,
    )
    scenarios_by_id = {scenario.scenario_id: scenario for scenario in scenarios}
    rows = _captured_rows()

    assert len(rows) == 24
    assert {str(row["mode"]) for row in rows} == {"llm", "hybrid"}
    assert all(
        str(row["source_run"]).startswith(("bench-edb0", "bench-fbde"))
        for row in rows
    )
    assert all(
        row["recorded_fallback_outcome"] == "not_used"
        for row in rows
        if bool(row["recorded_final_output_accepted"])
    )
    assert all(
        row["recorded_fallback_outcome"] == "succeeded"
        for row in rows
        if not bool(row["recorded_final_output_accepted"])
    )

    for row in rows:
        scenario = scenarios_by_id[str(row["scenario_id"])]
        checkpoint = next(
            checkpoint
            for checkpoint in scenario.checkpoints
            if checkpoint.checkpoint_id == row["checkpoint_id"]
        )
        context = sim_reconstruction_context_for_checkpoint(
            scenario=scenario,
            checkpoint=checkpoint,
        )
        semantic = SimSemanticDecision.model_validate(row["semantic_decision"])
        validation = validate_sim_decision_contract(
            context=context,
            semantic=semantic,
        )
        key = (row["mode"], row["scenario_id"], row["checkpoint_id"])

        if not bool(row["recorded_final_output_accepted"]):
            assert not validation.valid, key
            constrained = constrain_sim_semantic_contract(
                contract=_contract(),
                context=context,
            )
            assert list(
                Draft202012Validator(constrained.output_schema).iter_errors(
                    semantic.model_dump(mode="json")
                )
            ), key
            continue

        assert validation.valid, (key, validation.issues)
        result = provider_result_for_sim_semantic(
            request=_request(row),
            decision=semantic,
            provider_name="captured-provider-replay",
        )
        output_payload, trace, success, failure_mode = (
            memory_evolution_sim_engine_result_from_llm(
                result=result,
                mode=LLMDecisionMode(str(row["mode"])),
                context=context,
                rule_output=rule_sim_output_for_checkpoint(
                    scenario=scenario,
                    checkpoint=checkpoint,
                ).model_dump(mode="json"),
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
        assert trace.fallback_used is False, key
        assert aggregate.verdict == JudgeVerdict.PASS, (
            key,
            aggregate.critical_failure_buckets,
        )
        assert aggregate.review_required is False, key
