from __future__ import annotations

from memorii.core.benchmark.fixture_sets.memory_evolution_v1 import (
    load_memory_evolution_v1_fixture_set,
)
from memorii.core.benchmark.memory_evolution_decision import (
    MemoryEvolutionBeliefState,
    MemoryEvolutionDecisionContext,
    MemoryEvolutionMemoryKind,
    MemoryEvolutionScenario,
    MemoryEvolutionSemanticBeliefScore,
    expected_memory_evolution_semantic_decision_for_checkpoint,
    fake_llm_result_for_memory_evolution,
)
from memorii.core.benchmark.memory_evolution_sim import (
    LatentGraphScenario,
    MemoryEvolutionSimReconstructionContext,
)
from memorii.core.llm_provider.models import LLMDecisionResult, LLMStructuredRequest
from memorii.core.prompts.models import PromptModelDefaults
from memorii.core.prompts.registry import PromptRegistry, default_prompt_root
from memorii.tools.benchmark_suites import memory_evolution as curated_suite
from memorii.tools.benchmark_suites import memory_evolution_sim as sim_suite
from memorii.tools.benchmark_suites.memory_evolution_artifacts import _llm_call_count
from memorii.tools.benchmark_suites.runtime_dependencies import (
    BenchmarkRuntimeDependencies,
    DryRunDecisionStrategy,
)
from tests.unit.core.benchmark.memory_evolution_test_helpers import (
    generate_scenario_by_family,
    oracle_shaped_sim_semantic_decision,
    provider_result_for_sim_semantic,
)


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
            (scenario.scenario_id, checkpoint.checkpoint_id): (
                oracle_shaped_sim_semantic_decision(
                    context=sim_suite.sim_reconstruction_context_for_checkpoint(
                        scenario=scenario,
                        checkpoint=checkpoint,
                    ),
                    checkpoint=checkpoint,
                )
            )
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
                    "claim_assessments": [
                        assessment.model_copy(
                            update={"claim_id": "not-visible"}
                        )
                        if index == 0
                        else assessment
                        for index, assessment in enumerate(
                            expected.claim_assessments
                        )
                    ],
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
        return provider_result_for_sim_semantic(
            request=request,
            decision=decision,
            provider_name=self.provider_name,
        )


class _RepairingCuratedFakeAdapter:
    provider_name = "fake"

    def __init__(
        self,
        *,
        scenarios: list[MemoryEvolutionScenario],
        registry: PromptRegistry,
    ) -> None:
        self._registry = registry
        self._expected = {
            (scenario.scenario_id, checkpoint.checkpoint_id): (
                expected_memory_evolution_semantic_decision_for_checkpoint(
                    scenario=scenario,
                    checkpoint=checkpoint,
                )
            )
            for scenario in scenarios
            for checkpoint in scenario.checkpoints
        }

    def decide(
        self,
        context: MemoryEvolutionDecisionContext,
        *,
        request_id: str,
        metadata: dict[str, object] | None = None,
    ) -> LLMDecisionResult:
        expected = self._expected[(context.scenario_id, context.checkpoint.checkpoint_id)]
        if context.repair_request is not None:
            decision = expected
        else:
            non_belief = next(
                card
                for card in context.visible_memory_cards
                if card.memory_kind != MemoryEvolutionMemoryKind.BELIEF
            )
            decision = expected.model_copy(
                update={
                    "considered_memory_ids": [
                        *expected.considered_memory_ids,
                        non_belief.memory_id,
                    ],
                    "belief_scores": [
                        *expected.belief_scores,
                        MemoryEvolutionSemanticBeliefScore(
                            memory_id=non_belief.memory_id,
                            belief=0.5,
                            belief_state=MemoryEvolutionBeliefState.UNKNOWN,
                        ),
                    ],
                }
            )
        request = LLMStructuredRequest(
            request_id=request_id,
            prompt_ref="memory_evolution_decision:v1",
            prompt_hash="offline-test",
            system="",
            user="",
            output_schema={},
            model_defaults=PromptModelDefaults(model="test-model"),
            metadata=metadata or {},
        )
        return fake_llm_result_for_memory_evolution(
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
        "LLMMemoryEvolutionSimReconstructionAdapter",
        lambda *, runner, registry: _RepairingFakeAdapter(
            scenarios=[scenario],
            registry=registry,
        ),
    )

    _scenario_rows, checkpoint_rows, _judge_rows, llm_rows = sim_suite._run_memory_evolution_sim_transitions(
        scenarios=[scenario],
        mode="llm",
        dry_run=True,
        allow_live=False,
        prompt_root=default_prompt_root(),
        dependencies=BenchmarkRuntimeDependencies(
            dry_run_decision_strategy=DryRunDecisionStrategy.CLIENT_ADAPTERS,
        ),
    )

    assert all(row.success for row in checkpoint_rows)
    assert len(llm_rows) == len(scenario.checkpoints)
    assert _llm_call_count(llm_rows) == 2 * len(scenario.checkpoints)
    for row in llm_rows:
        assert len(row.provider_attempts) == 2
        assert row.provider_attempts[0].accepted is False
        assert set(row.provider_attempts[0].validation_issues) == {
            "invalid_claim_id",
            "missing_claim_assessment",
        }
        assert row.provider_attempts[1].accepted is True
        assert row.provider_attempts[1].repair_request is not None
        assert row.provider_attempts[1].previous_decision_digest is not None
        assert row.provider_attempts[1].compiled_output == row.output.model_dump(
            mode="json"
        )
        assert row.final_output_accepted is True
        assert row.fallback_outcome.value == "not_used"


def test_curated_runner_records_schema_valid_semantic_rejection_before_repair(
    monkeypatch,
) -> None:
    scenario = load_memory_evolution_v1_fixture_set()[0]
    monkeypatch.setattr(
        curated_suite,
        "ExpectedMemoryEvolutionFakeAdapter",
        _RepairingCuratedFakeAdapter,
    )

    _scenario_rows, checkpoint_rows, llm_rows = curated_suite._run_memory_evolution_transitions(
        scenarios=[scenario],
        mode="llm",
        dry_run=True,
        allow_live=False,
        prompt_root=default_prompt_root(),
        dependencies=BenchmarkRuntimeDependencies(),
    )

    assert all(row["success"] is True for row in checkpoint_rows)
    assert len(llm_rows) == len(scenario.checkpoints)
    for row in llm_rows:
        assert len(row.provider_attempts) == 2
        assert row.provider_attempts[0].provider_attempt_status.value == "succeeded"
        assert row.provider_attempts[0].semantic_validation_status == "failed"
        assert row.provider_attempts[0].accepted is False
        assert set(row.provider_attempts[0].validation_issues) == {
            "belief_scores_forbidden",
            "invalid_belief_id",
        }
        assert row.provider_attempts[1].semantic_validation_status == "passed"
        assert row.provider_attempts[1].accepted is True
        assert row.provider_attempts[1].repair_request is not None
        assert row.provider_attempts[1].previous_decision_digest is not None
        assert row.provider_attempts[1].compiled_output == row.output.model_dump(
            mode="json"
        )
        assert row.semantic_validation_status == "passed"
        assert row.final_output_accepted is True
