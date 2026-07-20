from __future__ import annotations

from memorii.core.belief.models import BeliefUpdateContext, BeliefUpdateOutput
from memorii.core.grounding.models import (
    AnswerVerificationContext,
    AnswerVerificationOutput,
    EvidenceSelectionContext,
    EvidenceSelectionOutput,
    GroundedAnswerContext,
    GroundedAnswerOutput,
)
from memorii.core.llm_judge.models import JudgeDecisionOutput, JudgeDimension, JudgeRubric
from memorii.core.llm_provider.models import LLMDecisionResult
from memorii.core.llm_provider.runner import PromptLLMRunner
from memorii.core.promotion.assessment import PromotionAssessmentContext, PromotionAssessmentOutput
from memorii.core.prompts.registry import PromptRegistry
from memorii.core.prompts.runtime_manifest import PromptOwner

_DEFAULT_JUDGE_PROMPTS: dict[JudgeDimension, str] = {
    JudgeDimension.PROMOTION_PRECISION: "judges/promotion_precision:v1",
    JudgeDimension.TEMPORAL_VALIDITY: "judges/temporal_validity:v1",
    JudgeDimension.ATTRIBUTION: "judges/attribution:v1",
    JudgeDimension.BELIEF_DIRECTION: "judges/belief_direction:v1",
    JudgeDimension.MEMORY_PLANE: "judges/memory_plane:v1",
}


def default_judge_prompt_refs() -> dict[JudgeDimension, str]:
    return dict(_DEFAULT_JUDGE_PROMPTS)


class LLMPromotionAssessmentAdapter:
    output_model = PromotionAssessmentOutput

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
        context: PromotionAssessmentContext,
        *,
        request_id: str,
        metadata: dict[str, object] | None = None,
    ) -> LLMDecisionResult:
        contract = self._registry.load(
            self._prompt_ref,
            owner=PromptOwner.LLM_PROMOTION_DECISION_ADAPTER,
            output_model=self.output_model,
        )
        variables = {"context_json": context.prompt_payload(), "candidate_summary": context.content}
        return self._runner.run(
            contract=contract,
            variables=variables,
            request_id=request_id,
            metadata=metadata,
            output_model=self.output_model,
        )


class LLMBeliefUpdateAdapter:
    output_model = BeliefUpdateOutput

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
        contract = self._registry.load(
            self._prompt_ref,
            owner=PromptOwner.LLM_BELIEF_UPDATE_ADAPTER,
            output_model=self.output_model,
        )
        variables: dict[str, object] = {"context_json": context.prompt_payload()}
        return self._runner.run(
            contract=contract,
            variables=variables,
            request_id=request_id,
            metadata=metadata,
            output_model=self.output_model,
        )


class LLMEvidenceSelectionAdapter:
    output_model = EvidenceSelectionOutput

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
        contract = self._registry.load(
            self._prompt_ref,
            owner=PromptOwner.LLM_EVIDENCE_SELECTION_ADAPTER,
            output_model=self.output_model,
        )
        variables = {
            "context_json": context.model_dump(mode="json"),
            "query": context.query,
        }
        return self._runner.run(
            contract=contract,
            variables=variables,
            request_id=request_id,
            metadata=metadata,
            output_model=self.output_model,
        )


class LLMGroundedAnswerAdapter:
    output_model = GroundedAnswerOutput

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
        contract = self._registry.load(
            self._prompt_ref,
            owner=PromptOwner.LLM_GROUNDED_ANSWER_ADAPTER,
            output_model=self.output_model,
        )
        variables = {
            "context_json": context.model_dump(mode="json"),
            "query": context.query,
        }
        return self._runner.run(
            contract=contract,
            variables=variables,
            request_id=request_id,
            metadata=metadata,
            output_model=self.output_model,
        )


class LLMAnswerVerificationAdapter:
    output_model = AnswerVerificationOutput

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
        contract = self._registry.load(
            self._prompt_ref,
            owner=PromptOwner.LLM_ANSWER_VERIFICATION_ADAPTER,
            output_model=self.output_model,
        )
        variables = {
            "context_json": context.model_dump(mode="json"),
            "query": context.query,
        }
        return self._runner.run(
            contract=contract,
            variables=variables,
            request_id=request_id,
            metadata=metadata,
            output_model=self.output_model,
        )


class LLMJudgeDecisionAdapter:
    output_model = JudgeDecisionOutput

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
        contract = self._registry.load(
            prompt_ref,
            owner=PromptOwner.LLM_JUDGE_DECISION_ADAPTER,
            output_model=self.output_model,
        )
        variables = {"rubric_json": rubric.model_dump(mode="json"), "input_payload": input_payload}
        return self._runner.run(
            contract=contract,
            variables=variables,
            request_id=request_id,
            metadata=metadata,
            output_model=self.output_model,
        )
