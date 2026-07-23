from __future__ import annotations

from memorii.core.benchmark.memory_evolution_sim import (
    LatentGraphScenario,
    MemoryEvolutionSimReconstructionContext,
    expected_sim_semantic_decision_for_checkpoint,
    fake_llm_result_for_memory_evolution_sim,
)
from memorii.core.llm_provider.models import LLMDecisionResult, LLMStructuredRequest
from memorii.core.prompts.models import PromptModelDefaults
from memorii.core.prompts.registry import PromptRegistry, default_prompt_root
from memorii.tools.benchmark_suites import memory_evolution_sim as sim_suite
from memorii.tools.benchmark_suites.memory_evolution_artifacts import _llm_call_count
from memorii.tools.benchmark_suites.runtime_dependencies import BenchmarkRuntimeDependencies
from tests.unit.core.benchmark.memory_evolution_test_helpers import generate_scenario_by_family


class _RepairingFakeAdapter:
    provider_name = "fake"

    def __init__(
        self,
        *,
        scenarios: list[LatentGraphScenario],
        registry: PromptRegistry,
    ) -> None:
        self._registry = registry
        self._expected = {
            (scenario.scenario_id, checkpoint.checkpoint_id): expected_sim_semantic_decision_for_checkpoint(checkpoint)
            for scenario in scenarios
            for checkpoint in scenario.checkpoints
        }

    def decide(
        self,
        context: MemoryEvolutionSimReconstructionContext,
        *,
        request_id: str,
        metadata: dict[str, object] | None = None,
    ) -> LLMDecisionResult:
        expected = self._expected[(context.scenario_id, context.checkpoint.checkpoint_id)]
        decision = (
            expected
            if context.repair_request is not None
            else expected.model_copy(
                update={
                    "selected_claim_ids": ["not-visible"],
                    "considered_claim_ids": ["not-visible"],
                }
            )
        )
        request = LLMStructuredRequest(
            request_id=request_id,
            prompt_ref="memory_evolution_sim_reconstruction:v1",
            prompt_hash="offline-test",
            system="",
            user="",
            output_schema={},
            model_defaults=PromptModelDefaults(model="test-model"),
            metadata=metadata or {},
        )
        return fake_llm_result_for_memory_evolution_sim(
            request=request,
            decision=decision,
            provider_name=self.provider_name,
        )


def test_sim_runner_repairs_once_and_accounts_for_both_provider_calls(
    monkeypatch,
) -> None:
    scenario = generate_scenario_by_family(
        profile="adversarial",
        family="current_vs_historical_truth",
        seed=7,
        noise_rate=0.35,
    )
    monkeypatch.setattr(
        sim_suite,
        "ExpectedMemoryEvolutionSimFakeAdapter",
        _RepairingFakeAdapter,
    )

    _scenario_rows, checkpoint_rows, _judge_rows, llm_rows = sim_suite._run_memory_evolution_sim_transitions(
        scenarios=[scenario],
        mode="llm",
        dry_run=True,
        allow_live=False,
        prompt_root=default_prompt_root(),
        dependencies=BenchmarkRuntimeDependencies(),
    )

    assert all(row.success for row in checkpoint_rows)
    assert len(llm_rows) == len(scenario.checkpoints)
    assert _llm_call_count(llm_rows) == 2 * len(scenario.checkpoints)
    for row in llm_rows:
        assert len(row.provider_attempts) == 2
        assert row.provider_attempts[0].accepted is False
        assert row.provider_attempts[0].validation_issues == ["invalid_claim_id"]
        assert row.provider_attempts[1].accepted is True
        assert row.final_output_accepted is True
        assert row.fallback_outcome.value == "not_used"
