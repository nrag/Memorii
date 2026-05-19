from __future__ import annotations

from pathlib import Path

import pytest

from memorii.core.env_config import load_memorii_environment
from memorii.core.llm_config import LLMLiveTestConfig, LLMRuntimeConfig
from memorii.core.llm_provider.factory import LLMClientFactory
from memorii.core.llm_provider.runner import PromptLLMRunner
from memorii.core.prompts.registry import PromptRegistry

PROMPT_ROOT = Path(__file__).resolve().parents[3] / "prompts"


@pytest.mark.integration
def test_openai_live_structured_prompt_contract() -> None:
    env_snapshot = load_memorii_environment()
    runtime_config = LLMRuntimeConfig.from_env(env_snapshot.env)
    live_config = LLMLiveTestConfig.from_env(env_snapshot.env)
    if not live_config.should_run_live_llm_tests(runtime_config):
        pytest.skip("live LLM tests are disabled unless gate flag and API key are present")

    contract = PromptRegistry(prompt_root=PROMPT_ROOT).load("promotion_decision:v1")
    client = LLMClientFactory.from_config(runtime_config)
    runner = PromptLLMRunner(client=client, config=runtime_config)
    result = runner.run(contract=contract, variables={"context_json": {}, "candidate_summary": "short summary"}, request_id="live-r1")
    assert result.response.provider == "openai"
