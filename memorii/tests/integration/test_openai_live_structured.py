from __future__ import annotations

import pytest
from memorii.core.env_config import load_memorii_environment
from memorii.core.llm_config import LLMLiveTestConfig, LLMRuntimeConfig
from memorii.core.llm_decision.adapters import LLMPromotionAssessmentAdapter
from memorii.core.llm_provider.factory import LLMClientFactory
from memorii.core.llm_provider.runner import PromptLLMRunner
from memorii.core.promotion.assessment import PromotionAssessment, PromotionAssessmentContext, PromotionCandidateType
from memorii.core.prompts.registry import PromptRegistry, default_prompt_root

PROMPT_ROOT = default_prompt_root()


@pytest.mark.integration
def test_openai_live_structured_prompt_contract() -> None:
    env_snapshot = load_memorii_environment()
    runtime_config = LLMRuntimeConfig.from_env(env_snapshot.env)
    live_config = LLMLiveTestConfig.from_env(env_snapshot.env)
    if not live_config.should_run_live_llm_tests(runtime_config):
        pytest.skip("live LLM tests are disabled unless gate flag and API key are present")

    registry = PromptRegistry(prompt_root=PROMPT_ROOT)
    runner = PromptLLMRunner(client=LLMClientFactory.from_config(runtime_config), config=runtime_config)
    adapter = LLMPromotionAssessmentAdapter(runner=runner, registry=registry)
    context = PromotionAssessmentContext(
        candidate_id="candidate:live-structured",
        candidate_type=PromotionCandidateType.EPISODIC,
        content="Completed the live structured provider contract check",
        source_ids=["event:live-structured"],
        created_from="task_outcome",
    )
    result = adapter.decide(context, request_id="live-r1")
    assert result.success is True
    assert result.response.provider == "openai"
    assert result.output is not None
    PromotionAssessment.model_validate(result.output)
