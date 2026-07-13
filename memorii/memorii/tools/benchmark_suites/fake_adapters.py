from __future__ import annotations

from memorii.core.benchmark.execution_graph_decision import (
    ExecutionGraphDecisionContext,
    ExecutionGraphScenario,
    expected_execution_graph_decision_for_scenario,
    fake_llm_result_for_execution_graph,
)
from memorii.core.benchmark.fixtures import normalize_fixtures
from memorii.core.benchmark.hotpotqa import HotpotQAExample
from memorii.core.benchmark.hotpotqa_official import expected_hotpotqa_grounding_decisions
from memorii.core.benchmark.lifecycle_decision import (
    LifecycleDecisionContext,
    expected_lifecycle_decision_for_fixture,
    fake_llm_result_for_lifecycle,
    lifecycle_family_requires_decision,
)
from memorii.core.benchmark.memory_evolution_decision import (
    MemoryEvolutionDecisionContext,
    MemoryEvolutionScenario,
    expected_memory_evolution_decision_for_checkpoint,
    fake_llm_result_for_memory_evolution,
)
from memorii.core.benchmark.memory_evolution_sim import (
    LatentGraphScenario,
    MemoryEvolutionSimReconstructionContext,
    expected_sim_output_for_checkpoint,
    fake_llm_result_for_memory_evolution_sim,
)
from memorii.core.benchmark.models import BenchmarkScenarioFixture
from memorii.core.benchmark.retrieval_relevance_decision import (
    RetrievalRelevanceContext,
    expected_retrieval_relevance_decision_for_fixture,
    fake_llm_result_for_retrieval_relevance,
)
from memorii.core.grounding.models import (
    AnswerVerificationContext,
    EvidenceSelectionContext,
    GroundedAnswerContext,
)
from memorii.core.grounding.pipeline import (
    fake_llm_result_for_answer_verification,
    fake_llm_result_for_evidence_selection,
    fake_llm_result_for_grounded_answer,
)
from memorii.core.llm_provider.models import LLMDecisionResult, LLMStructuredRequest
from memorii.core.prompts.registry import PromptRegistry


class _ExpectedLifecycleFakeAdapter:
    provider_name = "fake"

    def __init__(self, *, fixtures: list[BenchmarkScenarioFixture], registry: PromptRegistry) -> None:
        self._registry = registry
        self._expected_by_scenario = {
            fixture.scenario_id: expected_lifecycle_decision_for_fixture(fixture)
            for fixture in fixtures
            if fixture.lifecycle is not None
            and lifecycle_family_requires_decision(fixture.lifecycle.family)
        }

    def decide(
        self,
        context: object,
        *,
        request_id: str,
        metadata: dict[str, object] | None = None,
    ) -> LLMDecisionResult:
        lifecycle_context = LifecycleDecisionContext.model_validate(context)
        contract = self._registry.load("lifecycle_decision:v1")
        request = LLMStructuredRequest(
            request_id=request_id,
            prompt_ref="lifecycle_decision:v1",
            prompt_hash="dry-run",
            system="",
            user="",
            output_schema=contract.output_schema,
            model_defaults=contract.model_defaults,
            metadata=metadata or {},
        )
        decision = self._expected_by_scenario[lifecycle_context.scenario_id]
        return fake_llm_result_for_lifecycle(request=request, decision=decision, provider_name=self.provider_name)


class _ExpectedExecutionGraphFakeAdapter:
    provider_name = "fake"

    def __init__(self, *, scenarios: list[ExecutionGraphScenario], registry: PromptRegistry) -> None:
        self._registry = registry
        self._expected_by_scenario = {
            scenario.scenario_id: expected_execution_graph_decision_for_scenario(scenario)
            for scenario in scenarios
        }

    def decide(
        self,
        context: object,
        *,
        request_id: str,
        metadata: dict[str, object] | None = None,
    ) -> LLMDecisionResult:
        graph_context = ExecutionGraphDecisionContext.model_validate(context)
        contract = self._registry.load("execution_graph_decision:v1")
        request = LLMStructuredRequest(
            request_id=request_id,
            prompt_ref="execution_graph_decision:v1",
            prompt_hash="dry-run",
            system="",
            user="",
            output_schema=contract.output_schema,
            model_defaults=contract.model_defaults,
            metadata=metadata or {},
        )
        decision = self._expected_by_scenario[graph_context.scenario_id]
        return fake_llm_result_for_execution_graph(
            request=request,
            decision=decision,
            provider_name=self.provider_name,
        )


class _ExpectedMemoryEvolutionFakeAdapter:
    provider_name = "fake"

    def __init__(self, *, scenarios: list[MemoryEvolutionScenario], registry: PromptRegistry) -> None:
        self._registry = registry
        self._expected_by_key = {
            (scenario.scenario_id, checkpoint.checkpoint_id): expected_memory_evolution_decision_for_checkpoint(
                scenario=scenario,
                checkpoint=checkpoint,
            )
            for scenario in scenarios
            for checkpoint in scenario.checkpoints
        }

    def decide(
        self,
        context: object,
        *,
        request_id: str,
        metadata: dict[str, object] | None = None,
    ) -> LLMDecisionResult:
        evolution_context = MemoryEvolutionDecisionContext.model_validate(context)
        contract = self._registry.load("memory_evolution_decision:v1")
        request = LLMStructuredRequest(
            request_id=request_id,
            prompt_ref="memory_evolution_decision:v1",
            prompt_hash="dry-run",
            system="",
            user="",
            output_schema=contract.output_schema,
            model_defaults=contract.model_defaults,
            metadata=metadata or {},
        )
        decision = self._expected_by_key[
            (evolution_context.scenario_id, evolution_context.checkpoint.checkpoint_id)
        ]
        return fake_llm_result_for_memory_evolution(
            request=request,
            decision=decision,
            provider_name=self.provider_name,
        )


class _ExpectedMemoryEvolutionSimFakeAdapter:
    provider_name = "fake"

    def __init__(self, *, scenarios: list[LatentGraphScenario], registry: PromptRegistry) -> None:
        self._registry = registry
        self._expected_by_key = {
            (scenario.scenario_id, checkpoint.checkpoint_id): expected_sim_output_for_checkpoint(checkpoint)
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
        contract = self._registry.load("memory_evolution_sim_reconstruction:v1")
        request = LLMStructuredRequest(
            request_id=request_id,
            prompt_ref="memory_evolution_sim_reconstruction:v1",
            prompt_hash="dry-run",
            system="",
            user="",
            output_schema=contract.output_schema,
            model_defaults=contract.model_defaults,
            metadata=metadata or {},
        )
        decision = self._expected_by_key[(context.scenario_id, context.checkpoint.checkpoint_id)]
        return fake_llm_result_for_memory_evolution_sim(
            request=request,
            decision=decision,
            provider_name=self.provider_name,
        )


class _ExpectedRetrievalRelevanceFakeAdapter:
    provider_name = "fake"

    def __init__(self, *, fixtures: list[BenchmarkScenarioFixture], registry: PromptRegistry) -> None:
        self._registry = registry
        self._expected_by_scenario = {
            fixture.scenario_id: expected_retrieval_relevance_decision_for_fixture(fixture)
            for fixture in normalize_fixtures(fixtures)
            if fixture.retrieval is not None
        }

    def decide(
        self,
        context: object,
        *,
        request_id: str,
        metadata: dict[str, object] | None = None,
    ) -> LLMDecisionResult:
        relevance_context = RetrievalRelevanceContext.model_validate(context)
        contract = self._registry.load("retrieval_relevance:v1")
        request = LLMStructuredRequest(
            request_id=request_id,
            prompt_ref="retrieval_relevance:v1",
            prompt_hash="dry-run",
            system="",
            user="",
            output_schema=contract.output_schema,
            model_defaults=contract.model_defaults,
            metadata=metadata or {},
        )
        decision = self._expected_by_scenario[relevance_context.scenario_id]
        return fake_llm_result_for_retrieval_relevance(
            request=request,
            decision=decision,
            provider_name=self.provider_name,
        )


class _ExpectedHotpotQAEvidenceSelectionFakeAdapter:
    provider_name = "fake"

    def __init__(self, *, examples: list[HotpotQAExample], registry: PromptRegistry) -> None:
        self._registry = registry
        self._expected_by_example = {
            example.example_id: expected_hotpotqa_grounding_decisions(example)[0]
            for example in examples
        }

    def decide(
        self,
        context: object,
        *,
        request_id: str,
        metadata: dict[str, object] | None = None,
    ) -> LLMDecisionResult:
        evidence_context = EvidenceSelectionContext.model_validate(context)
        contract = self._registry.load("evidence_selection:v1")
        request = LLMStructuredRequest(
            request_id=request_id,
            prompt_ref="evidence_selection:v1",
            prompt_hash="dry-run",
            system="",
            user="",
            output_schema=contract.output_schema,
            model_defaults=contract.model_defaults,
            metadata=metadata or {},
        )
        decision = self._expected_by_example[str(evidence_context.metadata["example_id"])]
        return fake_llm_result_for_evidence_selection(
            request=request,
            decision=decision,
            provider_name=self.provider_name,
        )


class _ExpectedHotpotQAGroundedAnswerFakeAdapter:
    provider_name = "fake"

    def __init__(self, *, examples: list[HotpotQAExample], registry: PromptRegistry) -> None:
        self._registry = registry
        self._expected_by_example = {
            example.example_id: expected_hotpotqa_grounding_decisions(example)[1]
            for example in examples
        }

    def decide(
        self,
        context: object,
        *,
        request_id: str,
        metadata: dict[str, object] | None = None,
    ) -> LLMDecisionResult:
        answer_context = GroundedAnswerContext.model_validate(context)
        contract = self._registry.load("grounded_answer:v1")
        request = LLMStructuredRequest(
            request_id=request_id,
            prompt_ref="grounded_answer:v1",
            prompt_hash="dry-run",
            system="",
            user="",
            output_schema=contract.output_schema,
            model_defaults=contract.model_defaults,
            metadata=metadata or {},
        )
        decision = self._expected_by_example[str(answer_context.metadata["example_id"])]
        return fake_llm_result_for_grounded_answer(
            request=request,
            decision=decision,
            provider_name=self.provider_name,
        )


class _ExpectedHotpotQAAnswerVerificationFakeAdapter:
    provider_name = "fake"

    def __init__(self, *, examples: list[HotpotQAExample], registry: PromptRegistry) -> None:
        self._registry = registry
        self._expected_by_example = {
            example.example_id: expected_hotpotqa_grounding_decisions(example)[2]
            for example in examples
        }

    def decide(
        self,
        context: object,
        *,
        request_id: str,
        metadata: dict[str, object] | None = None,
    ) -> LLMDecisionResult:
        verification_context = AnswerVerificationContext.model_validate(context)
        contract = self._registry.load("answer_verification:v1")
        request = LLMStructuredRequest(
            request_id=request_id,
            prompt_ref="answer_verification:v1",
            prompt_hash="dry-run",
            system="",
            user="",
            output_schema=contract.output_schema,
            model_defaults=contract.model_defaults,
            metadata=metadata or {},
        )
        decision = self._expected_by_example[str(verification_context.metadata["example_id"])]
        return fake_llm_result_for_answer_verification(
            request=request,
            decision=decision,
            provider_name=self.provider_name,
        )
