from __future__ import annotations

import json
from pathlib import Path

import pytest

from memorii.core.llm_config import LLMRuntimeConfig
from memorii.core.llm_provider.fake import FakeLLMStructuredClient
from memorii.core.llm_provider.runner import PromptLLMRunner
from memorii.core.prompts.registry import PromptRegistry

PROMPT_ROOT = Path(__file__).resolve().parents[3] / "prompts"


def _contract():
    return PromptRegistry(prompt_root=PROMPT_ROOT).load("promotion_decision:v1")


def _runner(response_text: str, raise_on_request: bool = False) -> tuple[PromptLLMRunner, FakeLLMStructuredClient]:
    client = FakeLLMStructuredClient(default_response=response_text, raise_on_request=raise_on_request)
    config = LLMRuntimeConfig(provider="none")
    return PromptLLMRunner(client=client, config=config), client


def test_fake_provider_returns_default_structured_json() -> None:
    runner, _ = _runner('{"promote": false, "target_plane": null, "rationale": "x", "confidence": 0.5, "failure_mode": null, "requires_judge_review": false}')
    result = runner.run(contract=_contract(), variables={"context_json": {}, "candidate_summary": "s"}, request_id="r1")
    assert result.success is True


def test_invalid_json_returns_failure() -> None:
    runner, _ = _runner("not-json")
    result = runner.run(contract=_contract(), variables={"context_json": {}, "candidate_summary": "s"}, request_id="r1")
    assert result.success is False
    assert result.failure_mode == "invalid_json"


def test_schema_missing_required_field_returns_failure() -> None:
    runner, _ = _runner('{"promote": false, "target_plane": null, "rationale": "x", "confidence": 0.5, "requires_judge_review": false}')
    result = runner.run(contract=_contract(), variables={"context_json": {}, "candidate_summary": "s"}, request_id="r1")
    assert result.success is False
    assert result.failure_mode == "schema_validation"


def test_schema_type_enum_and_additional_properties_are_enforced() -> None:
    bad_cases = [
        '{"promote": "no", "target_plane": null, "rationale": "x", "confidence": 0.5, "failure_mode": null, "requires_judge_review": false}',
        '{"promote": true, "target_plane": "bad", "rationale": "x", "confidence": 0.5, "failure_mode": null, "requires_judge_review": false}',
        '{"promote": true, "target_plane": "semantic", "rationale": "x", "confidence": 0.5, "failure_mode": null, "requires_judge_review": false, "extra": 1}',
    ]
    for payload in bad_cases:
        runner, _ = _runner(payload)
        result = runner.run(contract=_contract(), variables={"context_json": {}, "candidate_summary": "s"}, request_id="r1")
        assert result.success is False
        assert result.failure_mode == "schema_validation"


def test_provider_exception_returns_failure_safely() -> None:
    runner, _ = _runner("{}", raise_on_request=True)
    result = runner.run(contract=_contract(), variables={"context_json": {}, "candidate_summary": "s"}, request_id="r1")
    assert result.success is False
    assert result.failure_mode == "provider_error"
    assert "Provider request failed" in (result.response.error or "")


def test_request_includes_prompt_ref_hash_and_redaction_and_serializable() -> None:
    runner, client = _runner('{"promote": false, "target_plane": null, "rationale": "x", "confidence": 0.5, "failure_mode": null, "requires_judge_review": false}')
    result = runner.run(
        contract=_contract(),
        variables={"context_json": {}, "candidate_summary": "s", "api_key": "secret-123"},
        request_id="r1",
        metadata={"k": "v"},
    )
    assert client.last_request is not None
    assert client.last_request.prompt_ref == "promotion_decision:v1"
    assert client.last_request.prompt_hash
    assert "secret-123" not in client.last_request.system
    assert "secret-123" not in client.last_request.user
    assert client.last_request.metadata["provider"] == "fake"
    dumped = result.model_dump(mode="json")
    assert isinstance(dumped, dict)
    json.dumps(dumped)


def test_no_api_key_required_and_provider_none_works_with_fake() -> None:
    config = LLMRuntimeConfig.from_env({"MEMORII_LLM_PROVIDER": "none"})
    assert config.has_api_key() is False
    runner = PromptLLMRunner(client=FakeLLMStructuredClient(default_response='{"promote": false, "target_plane": null, "rationale": "x", "confidence": 0.5, "failure_mode": null, "requires_judge_review": false}'), config=config)
    result = runner.run(contract=_contract(), variables={"context_json": {}, "candidate_summary": "s"}, request_id="r1")
    assert result.success is True


def test_optional_live_llm_tests_are_gated() -> None:
    env = {"MEMORII_ENABLE_LIVE_LLM_TESTS": "true", "MEMORII_LLM_PROVIDER": "openai"}
    config = LLMRuntimeConfig.from_env(env)
    if not config.should_run_live_llm_tests():
        pytest.skip("live LLM tests are disabled unless key + flag are present")
    pytest.fail("live network test intentionally not implemented in unit tests")
