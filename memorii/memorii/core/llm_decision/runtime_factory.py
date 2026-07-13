from __future__ import annotations

from pathlib import Path

from memorii.core.belief.hybrid_provider import HybridBeliefUpdateProvider
from memorii.core.belief.llm_provider import LLMBeliefUpdateProvider
from memorii.core.belief.models import BeliefUpdateContext
from memorii.core.belief.provider import BeliefUpdateProvider
from memorii.core.belief.rule_provider import RuleBasedBeliefUpdateProvider
from memorii.core.env_config import load_memorii_environment
from memorii.core.llm_config import LLMDecisionRuntimeConfig, LLMRuntimeConfig
from memorii.core.llm_decision.adapters import LLMBeliefUpdateAdapter, LLMPromotionDecisionAdapter
from memorii.core.llm_decision.models import LLMDecisionMode, LLMDecisionPoint, LLMDecisionTrace
from memorii.core.llm_decision.provider import LLMDecisionProvider
from memorii.core.llm_provider.factory import LLMClientFactory
from memorii.core.llm_provider.runner import PromptLLMRunner
from memorii.core.llm_trace.builder import build_llm_decision_trace_from_result
from memorii.core.promotion.hybrid_provider import HybridPromotionDecisionProvider
from memorii.core.promotion.llm_provider import LLMPromotionDecisionProvider
from memorii.core.promotion.models import PromotionContext
from memorii.core.promotion.provider import PromotionDecisionProvider
from memorii.core.promotion.rule_provider import RuleBasedPromotionDecisionProvider
from memorii.core.prompts.registry import PromptRegistry


class PromptBackedLLMDecisionProvider:
    def __init__(
        self,
        *,
        runtime_config: LLMRuntimeConfig,
        prompt_root: Path | None = None,
    ) -> None:
        root = prompt_root or Path(__file__).resolve().parents[2] / "prompts"
        runner = PromptLLMRunner(
            client=LLMClientFactory.from_config(runtime_config),
            config=runtime_config,
        )
        registry = PromptRegistry(prompt_root=root)
        self._promotion_adapter = LLMPromotionDecisionAdapter(runner=runner, registry=registry)
        self._belief_adapter = LLMBeliefUpdateAdapter(runner=runner, registry=registry)

    def decide(
        self,
        *,
        decision_point: LLMDecisionPoint,
        input_payload: dict[str, object],
        prompt_version: str | None = None,
    ) -> LLMDecisionTrace:
        del prompt_version
        request_id = f"runtime:{decision_point.value}:{input_payload.get('candidate_id') or input_payload.get('node_id') or 'decision'}"
        if decision_point == LLMDecisionPoint.PROMOTION:
            result = self._promotion_adapter.decide(
                PromotionContext.model_validate(input_payload),
                request_id=request_id,
            )
        elif decision_point == LLMDecisionPoint.BELIEF_UPDATE:
            result = self._belief_adapter.update(
                BeliefUpdateContext.model_validate(input_payload),
                request_id=request_id,
            )
        else:
            raise ValueError(f"Unsupported runtime LLM decision point: {decision_point.value}")
        return build_llm_decision_trace_from_result(
            decision_point=decision_point,
            mode=LLMDecisionMode.LLM,
            result=result,
            final_output=result.output,
            fallback_used=False,
        )


def _resolve_runtime_config() -> tuple[LLMRuntimeConfig, str]:
    snapshot = load_memorii_environment()
    runtime_config = LLMRuntimeConfig.from_env(snapshot.env)
    decision_config = LLMDecisionRuntimeConfig.from_env(snapshot.env)
    return runtime_config, decision_config.resolve(runtime_config)


def _build_prompt_llm_provider(runtime_config: LLMRuntimeConfig) -> LLMDecisionProvider:
    if not runtime_config.has_live_provider():
        raise RuntimeError("LLM decision mode requires a configured provider and API key.")
    return PromptBackedLLMDecisionProvider(runtime_config=runtime_config)


def build_promotion_decision_provider_from_env() -> PromotionDecisionProvider:
    runtime_config, mode = _resolve_runtime_config()
    if mode == "rule":
        return RuleBasedPromotionDecisionProvider()
    llm_provider = LLMPromotionDecisionProvider(llm_provider=_build_prompt_llm_provider(runtime_config))
    if mode == "hybrid":
        return HybridPromotionDecisionProvider(llm_provider=llm_provider)
    if mode == "llm":
        return llm_provider
    raise ValueError(f"Unsupported decision mode: {mode}")


def build_belief_update_provider_from_env() -> BeliefUpdateProvider:
    runtime_config, mode = _resolve_runtime_config()
    if mode == "rule":
        return RuleBasedBeliefUpdateProvider()
    llm_provider = LLMBeliefUpdateProvider(llm_provider=_build_prompt_llm_provider(runtime_config))
    if mode == "hybrid":
        return HybridBeliefUpdateProvider(llm_provider=llm_provider)
    if mode == "llm":
        return llm_provider
    raise ValueError(f"Unsupported decision mode: {mode}")
