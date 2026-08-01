"""Typed LLM adapters owned by benchmark decision contracts."""

from __future__ import annotations

from collections.abc import Callable
from typing import ClassVar

from pydantic import BaseModel

from memorii.core.benchmark.execution_graph_decision import (
    ExecutionGraphDecisionContext,
    ExecutionGraphDecisionOutput,
)
from memorii.core.benchmark.hotpotqa_official import HotpotQAAnswerContext, HotpotQAAnswerOutput
from memorii.core.benchmark.lifecycle_decision import LifecycleDecisionContext, LifecycleDecisionOutput
from memorii.core.benchmark.memory_evolution_decision.closed_world_schema import (
    constrain_memory_evolution_semantic_contract,
)
from memorii.core.benchmark.memory_evolution_decision.contracts import (
    MemoryEvolutionDecisionContext,
    MemoryEvolutionSemanticDecision,
    MemoryEvolutionSemanticDecisionOutput,
)
from memorii.core.benchmark.memory_evolution_sim.closed_world_schema import (
    constrain_sim_semantic_contract,
)
from memorii.core.benchmark.memory_evolution_sim.schemas import (
    MemoryEvolutionSimReconstructionContext,
    SimSemanticDecision,
    SimSemanticDecisionOutput,
)
from memorii.core.benchmark.retrieval_relevance_decision import (
    RetrievalRelevanceContext,
    RetrievalRelevanceOutput,
)
from memorii.core.llm_provider.models import LLMDecisionResult
from memorii.core.llm_provider.runner import PromptLLMRunner
from memorii.core.prompts.registry import PromptRegistry, RegisteredPromptContract
from memorii.core.prompts.runtime_manifest import PromptOwner


class _BenchmarkPromptAdapter:
    prompt_ref: ClassVar[str]
    owner: ClassVar[PromptOwner]
    output_model: ClassVar[type[BaseModel]]
    semantic_model: ClassVar[type[BaseModel] | None] = None

    def __init__(
        self,
        *,
        runner: PromptLLMRunner,
        registry: PromptRegistry,
    ) -> None:
        self._runner = runner
        self._registry = registry

    def _run(
        self,
        *,
        context: BaseModel,
        query_variable: str,
        query: str,
        request_id: str,
        metadata: dict[str, object] | None,
        contract_transform: Callable[
            [RegisteredPromptContract], RegisteredPromptContract
        ]
        | None = None,
    ) -> LLMDecisionResult:
        contract = self._registry.load(
            self.prompt_ref,
            owner=self.owner,
            output_model=self.output_model,
        )
        if contract_transform is not None:
            contract = contract_transform(contract)
        return self._runner.run(
            contract=contract,
            variables={
                "context_json": context.model_dump(mode="json"),
                query_variable: query,
            },
            request_id=request_id,
            metadata=metadata,
            output_model=self.output_model,
            semantic_model=self.semantic_model,
        )


class LLMLifecycleDecisionAdapter(_BenchmarkPromptAdapter):
    prompt_ref = "lifecycle_decision:v1"
    owner = PromptOwner.LLM_LIFECYCLE_DECISION_ADAPTER
    output_model = LifecycleDecisionOutput

    def decide(
        self,
        context: LifecycleDecisionContext,
        *,
        request_id: str,
        metadata: dict[str, object] | None = None,
    ) -> LLMDecisionResult:
        context = LifecycleDecisionContext.model_validate(context)
        return self._run(
            context=context,
            query_variable="query",
            query=context.query,
            request_id=request_id,
            metadata=metadata,
        )


class LLMExecutionGraphDecisionAdapter(_BenchmarkPromptAdapter):
    prompt_ref = "execution_graph_decision:v1"
    owner = PromptOwner.LLM_EXECUTION_GRAPH_DECISION_ADAPTER
    output_model = ExecutionGraphDecisionOutput

    def decide(
        self,
        context: ExecutionGraphDecisionContext,
        *,
        request_id: str,
        metadata: dict[str, object] | None = None,
    ) -> LLMDecisionResult:
        context = ExecutionGraphDecisionContext.model_validate(context)
        return self._run(
            context=context,
            query_variable="task",
            query=context.task,
            request_id=request_id,
            metadata=metadata,
        )


class LLMMemoryEvolutionDecisionAdapter(_BenchmarkPromptAdapter):
    prompt_ref = "memory_evolution_decision:v1"
    owner = PromptOwner.LLM_MEMORY_EVOLUTION_DECISION_ADAPTER
    output_model = MemoryEvolutionSemanticDecisionOutput
    semantic_model = MemoryEvolutionSemanticDecision

    def decide(
        self,
        context: MemoryEvolutionDecisionContext,
        *,
        request_id: str,
        metadata: dict[str, object] | None = None,
    ) -> LLMDecisionResult:
        context = MemoryEvolutionDecisionContext.model_validate(context)
        return self._run(
            context=context,
            query_variable="query",
            query=context.checkpoint.query_or_task,
            request_id=request_id,
            metadata=metadata,
            contract_transform=lambda contract: constrain_memory_evolution_semantic_contract(
                contract=contract,
                context=context,
            ),
        )


class LLMMemoryEvolutionSimReconstructionAdapter(_BenchmarkPromptAdapter):
    prompt_ref = "memory_evolution_sim_reconstruction:v1"
    owner = PromptOwner.LLM_MEMORY_EVOLUTION_SIM_RECONSTRUCTION_ADAPTER
    output_model = SimSemanticDecisionOutput
    semantic_model = SimSemanticDecision

    def decide(
        self,
        context: MemoryEvolutionSimReconstructionContext,
        *,
        request_id: str,
        metadata: dict[str, object] | None = None,
    ) -> LLMDecisionResult:
        context = MemoryEvolutionSimReconstructionContext.model_validate(context)
        return self._run(
            context=context,
            query_variable="query",
            query=context.checkpoint.query_or_task,
            request_id=request_id,
            metadata=metadata,
            contract_transform=lambda contract: constrain_sim_semantic_contract(
                contract=contract,
                context=context,
            ),
        )


class LLMRetrievalRelevanceDecisionAdapter(_BenchmarkPromptAdapter):
    prompt_ref = "retrieval_relevance:v1"
    owner = PromptOwner.LLM_RETRIEVAL_RELEVANCE_DECISION_ADAPTER
    output_model = RetrievalRelevanceOutput

    def decide(
        self,
        context: RetrievalRelevanceContext,
        *,
        request_id: str,
        metadata: dict[str, object] | None = None,
    ) -> LLMDecisionResult:
        context = RetrievalRelevanceContext.model_validate(context)
        return self._run(
            context=context,
            query_variable="query",
            query=context.query,
            request_id=request_id,
            metadata=metadata,
        )


class LLMHotpotQAAnswerAdapter(_BenchmarkPromptAdapter):
    prompt_ref = "hotpotqa_answer:v1"
    owner = PromptOwner.LLM_HOTPOTQA_ANSWER_ADAPTER
    output_model = HotpotQAAnswerOutput

    def decide(
        self,
        context: HotpotQAAnswerContext,
        *,
        request_id: str,
        metadata: dict[str, object] | None = None,
    ) -> LLMDecisionResult:
        context = HotpotQAAnswerContext.model_validate(context)
        return self._run(
            context=context,
            query_variable="question",
            query=context.question,
            request_id=request_id,
            metadata=metadata,
        )
