from __future__ import annotations

from memorii.core.belief.models import BeliefUpdateContext
from memorii.core.grounding.models import (
    AnswerVerificationContext,
    EvidenceSelectionContext,
    GroundedAnswerContext,
)
from memorii.core.llm_judge.models import JudgeDimension, JudgeRubric
from memorii.core.llm_provider.models import LLMDecisionResult
from memorii.core.llm_provider.runner import PromptLLMRunner
from memorii.core.prompts.registry import PromptRegistry
from memorii.core.promotion.models import PromotionContext

_DEFAULT_JUDGE_PROMPTS: dict[JudgeDimension, str] = {
    JudgeDimension.PROMOTION_PRECISION: "judges/promotion_precision:v1",
    JudgeDimension.TEMPORAL_VALIDITY: "judges/temporal_validity:v1",
    JudgeDimension.ATTRIBUTION: "judges/attribution:v1",
    JudgeDimension.BELIEF_DIRECTION: "judges/belief_direction:v1",
    JudgeDimension.MEMORY_PLANE: "judges/memory_plane:v1",
}


class LLMPromotionDecisionAdapter:
    def __init__(
        self,
        *,
        runner: PromptLLMRunner,
        registry: PromptRegistry,
        prompt_ref: str = "promotion_decision:v1",
    ) -> None:
        self._runner = runner
        self._registry = registry
        self._prompt_ref = prompt_ref

    def decide(
        self,
        context: PromotionContext,
        *,
        request_id: str,
        metadata: dict[str, object] | None = None,
    ) -> LLMDecisionResult:
        contract = self._registry.load(self._prompt_ref)
        variables = {"context_json": context.model_dump(mode="json"), "candidate_summary": context.content}
        return self._runner.run(contract=contract, variables=variables, request_id=request_id, metadata=metadata)


class LLMBeliefUpdateAdapter:
    def __init__(
        self,
        *,
        runner: PromptLLMRunner,
        registry: PromptRegistry,
        prompt_ref: str = "belief_update:v1",
    ) -> None:
        self._runner = runner
        self._registry = registry
        self._prompt_ref = prompt_ref

    def update(
        self,
        context: BeliefUpdateContext,
        *,
        request_id: str,
        metadata: dict[str, object] | None = None,
    ) -> LLMDecisionResult:
        contract = self._registry.load(self._prompt_ref)
        variables = {"context_json": context.model_dump(mode="json"), "prior_belief": context.prior_belief}
        return self._runner.run(contract=contract, variables=variables, request_id=request_id, metadata=metadata)


class LLMLifecycleDecisionAdapter:
    def __init__(
        self,
        *,
        runner: PromptLLMRunner,
        registry: PromptRegistry,
        prompt_ref: str = "lifecycle_decision:v1",
    ) -> None:
        self._runner = runner
        self._registry = registry
        self._prompt_ref = prompt_ref

    def decide(
        self,
        context: object,
        *,
        request_id: str,
        metadata: dict[str, object] | None = None,
    ) -> LLMDecisionResult:
        contract = self._registry.load(self._prompt_ref)
        context_json = context.model_dump(mode="json")  # type: ignore[attr-defined]
        variables = {"context_json": context_json, "query": str(context_json.get("query", ""))}
        return self._runner.run(contract=contract, variables=variables, request_id=request_id, metadata=metadata)


class LLMExecutionGraphDecisionAdapter:
    def __init__(
        self,
        *,
        runner: PromptLLMRunner,
        registry: PromptRegistry,
        prompt_ref: str = "execution_graph_decision:v1",
    ) -> None:
        self._runner = runner
        self._registry = registry
        self._prompt_ref = prompt_ref

    def decide(
        self,
        context: object,
        *,
        request_id: str,
        metadata: dict[str, object] | None = None,
    ) -> LLMDecisionResult:
        contract = self._registry.load(self._prompt_ref)
        context_json = context.model_dump(mode="json")  # type: ignore[attr-defined]
        variables = {
            "context_json": context_json,
            "task": str(context_json.get("task", "")),
        }
        return self._runner.run(contract=contract, variables=variables, request_id=request_id, metadata=metadata)


class LLMMemoryEvolutionDecisionAdapter:
    def __init__(
        self,
        *,
        runner: PromptLLMRunner,
        registry: PromptRegistry,
        prompt_ref: str = "memory_evolution_decision:v1",
    ) -> None:
        self._runner = runner
        self._registry = registry
        self._prompt_ref = prompt_ref

    def decide(
        self,
        context: object,
        *,
        request_id: str,
        metadata: dict[str, object] | None = None,
    ) -> LLMDecisionResult:
        contract = self._registry.load(self._prompt_ref)
        context_json = context.model_dump(mode="json")  # type: ignore[attr-defined]
        checkpoint = context_json.get("checkpoint", {})
        query = str(checkpoint.get("query_or_task", "")) if isinstance(checkpoint, dict) else ""
        variables = {
            "context_json": context_json,
            "query": query,
        }
        return self._runner.run(contract=contract, variables=variables, request_id=request_id, metadata=metadata)


class LLMMemoryEvolutionSimReconstructionAdapter:
    def __init__(
        self,
        *,
        runner: PromptLLMRunner,
        registry: PromptRegistry,
        prompt_ref: str = "memory_evolution_sim_reconstruction:v1",
    ) -> None:
        self._runner = runner
        self._registry = registry
        self._prompt_ref = prompt_ref

    def decide(
        self,
        context: object,
        *,
        request_id: str,
        metadata: dict[str, object] | None = None,
    ) -> LLMDecisionResult:
        contract = self._registry.load(self._prompt_ref)
        context_json = context.model_dump(mode="json")  # type: ignore[attr-defined]
        checkpoint = context_json.get("checkpoint", {})
        query = str(checkpoint.get("query_or_task", "")) if isinstance(checkpoint, dict) else ""
        variables = {
            "context_json": context_json,
            "query": query,
        }
        return self._runner.run(contract=contract, variables=variables, request_id=request_id, metadata=metadata)


class LLMRetrievalRelevanceDecisionAdapter:
    def __init__(
        self,
        *,
        runner: PromptLLMRunner,
        registry: PromptRegistry,
        prompt_ref: str = "retrieval_relevance:v1",
    ) -> None:
        self._runner = runner
        self._registry = registry
        self._prompt_ref = prompt_ref

    def decide(
        self,
        context: object,
        *,
        request_id: str,
        metadata: dict[str, object] | None = None,
    ) -> LLMDecisionResult:
        contract = self._registry.load(self._prompt_ref)
        context_json = context.model_dump(mode="json")  # type: ignore[attr-defined]
        variables = {
            "context_json": context_json,
            "query": str(context_json.get("query", "")),
        }
        return self._runner.run(contract=contract, variables=variables, request_id=request_id, metadata=metadata)


class LLMEvidenceSelectionAdapter:
    def __init__(
        self,
        *,
        runner: PromptLLMRunner,
        registry: PromptRegistry,
        prompt_ref: str = "evidence_selection:v1",
    ) -> None:
        self._runner = runner
        self._registry = registry
        self._prompt_ref = prompt_ref

    def decide(
        self,
        context: EvidenceSelectionContext,
        *,
        request_id: str,
        metadata: dict[str, object] | None = None,
    ) -> LLMDecisionResult:
        contract = self._registry.load(self._prompt_ref)
        variables = {
            "context_json": context.model_dump(mode="json"),
            "query": context.query,
        }
        return self._runner.run(contract=contract, variables=variables, request_id=request_id, metadata=metadata)


class LLMGroundedAnswerAdapter:
    def __init__(
        self,
        *,
        runner: PromptLLMRunner,
        registry: PromptRegistry,
        prompt_ref: str = "grounded_answer:v1",
    ) -> None:
        self._runner = runner
        self._registry = registry
        self._prompt_ref = prompt_ref

    def decide(
        self,
        context: GroundedAnswerContext,
        *,
        request_id: str,
        metadata: dict[str, object] | None = None,
    ) -> LLMDecisionResult:
        contract = self._registry.load(self._prompt_ref)
        variables = {
            "context_json": context.model_dump(mode="json"),
            "query": context.query,
        }
        return self._runner.run(contract=contract, variables=variables, request_id=request_id, metadata=metadata)


class LLMAnswerVerificationAdapter:
    def __init__(
        self,
        *,
        runner: PromptLLMRunner,
        registry: PromptRegistry,
        prompt_ref: str = "answer_verification:v1",
    ) -> None:
        self._runner = runner
        self._registry = registry
        self._prompt_ref = prompt_ref

    def decide(
        self,
        context: AnswerVerificationContext,
        *,
        request_id: str,
        metadata: dict[str, object] | None = None,
    ) -> LLMDecisionResult:
        contract = self._registry.load(self._prompt_ref)
        variables = {
            "context_json": context.model_dump(mode="json"),
            "query": context.query,
        }
        return self._runner.run(contract=contract, variables=variables, request_id=request_id, metadata=metadata)


class LLMHotpotQAAnswerAdapter:
    def __init__(
        self,
        *,
        runner: PromptLLMRunner,
        registry: PromptRegistry,
        prompt_ref: str = "hotpotqa_answer:v1",
    ) -> None:
        self._runner = runner
        self._registry = registry
        self._prompt_ref = prompt_ref

    def decide(
        self,
        context: object,
        *,
        request_id: str,
        metadata: dict[str, object] | None = None,
    ) -> LLMDecisionResult:
        contract = self._registry.load(self._prompt_ref)
        context_json = context.model_dump(mode="json")  # type: ignore[attr-defined]
        variables = {
            "context_json": context_json,
            "question": str(context_json.get("question", "")),
        }
        return self._runner.run(contract=contract, variables=variables, request_id=request_id, metadata=metadata)


class LLMJudgeDecisionAdapter:
    def __init__(
        self,
        *,
        runner: PromptLLMRunner,
        registry: PromptRegistry,
        prompt_ref_by_dimension: dict[JudgeDimension, str] | None = None,
    ) -> None:
        self._runner = runner
        self._registry = registry
        self._prompt_ref_by_dimension = dict(prompt_ref_by_dimension or _DEFAULT_JUDGE_PROMPTS)

    def judge(
        self,
        *,
        rubric: JudgeRubric,
        input_payload: dict[str, object],
        request_id: str,
        metadata: dict[str, object] | None = None,
    ) -> LLMDecisionResult:
        prompt_ref = self._prompt_ref_by_dimension.get(rubric.dimension)
        if prompt_ref is None:
            raise ValueError(f"Unsupported judge dimension mapping: {rubric.dimension.value}")
        contract = self._registry.load(prompt_ref)
        variables = {"rubric_json": rubric.model_dump(mode="json"), "input_payload": input_payload}
        return self._runner.run(contract=contract, variables=variables, request_id=request_id, metadata=metadata)
