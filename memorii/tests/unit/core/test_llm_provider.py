from __future__ import annotations

import json
from pathlib import Path

import pytest

from memorii.core.llm_config import LLMRuntimeConfig
from memorii.core.llm_provider.fake import FakeLLMStructuredClient
from memorii.core.llm_provider.models import LLMStructuredResponse
from memorii.core.llm_provider.runner import PromptLLMRunner
from memorii.core.prompts.registry import PromptRegistry

PROMPT_ROOT = Path(__file__).resolve().parents[3] / "prompts"
_VALID = '{"promote": false, "target_plane": null, "rationale": "x", "confidence": 0.5, "failure_mode": null, "requires_judge_review": false}'


def _contract():
    return PromptRegistry(prompt_root=PROMPT_ROOT).load("promotion_decision:v1")


def _runner(response_text: str, raise_on_request: bool = False) -> tuple[PromptLLMRunner, FakeLLMStructuredClient]:
    client = FakeLLMStructuredClient(default_response=response_text, raise_on_request=raise_on_request)
    config = LLMRuntimeConfig(provider="none")
    return PromptLLMRunner(client=client, config=config), client


def test_fake_provider_returns_default_structured_json() -> None:
    runner, _ = _runner(_VALID)
    result = runner.run(contract=_contract(), variables={"context_json": {}, "candidate_summary": "s"}, request_id="r1")
    assert result.success is True


def test_invalid_json_returns_failure() -> None:
    runner, _ = _runner("not-json")
    result = runner.run(contract=_contract(), variables={"context_json": {}, "candidate_summary": "s"}, request_id="r1")
    assert result.success is False
    assert result.failure_mode == "invalid_json"


def test_non_object_json_returns_failure() -> None:
    runner, _ = _runner('[{"promote": false}]')
    result = runner.run(contract=_contract(), variables={"context_json": {}, "candidate_summary": "s"}, request_id="r1")
    assert result.success is False
    assert result.failure_mode == "invalid_json"


def test_schema_missing_required_field_returns_failure() -> None:
    runner, _ = _runner('{"promote": false, "target_plane": null, "rationale": "x", "confidence": 0.5, "requires_judge_review": false}')
    result = runner.run(contract=_contract(), variables={"context_json": {}, "candidate_summary": "s"}, request_id="r1")
    assert result.success is False
    assert result.failure_mode == "schema_validation"


def test_schema_type_enum_additional_properties_and_bounds_are_enforced() -> None:
    bad_cases = [
        '{"promote": "no", "target_plane": null, "rationale": "x", "confidence": 0.5, "failure_mode": null, "requires_judge_review": false}',
        '{"promote": true, "target_plane": "bad", "rationale": "x", "confidence": 0.5, "failure_mode": null, "requires_judge_review": false}',
        '{"promote": true, "target_plane": "semantic", "rationale": "x", "confidence": 1.5, "failure_mode": null, "requires_judge_review": false}',
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


def test_mismatched_provider_request_id_fails_safely() -> None:
    class _MismatchClient(FakeLLMStructuredClient):
        def complete_structured(self, request, *, config):
            response = super().complete_structured(request, config=config)
            return response.model_copy(update={"request_id": "different"})

    runner = PromptLLMRunner(client=_MismatchClient(default_response=_VALID), config=LLMRuntimeConfig(provider="none"))
    result = runner.run(contract=_contract(), variables={"context_json": {}, "candidate_summary": "s"}, request_id="r1")
    assert result.success is False
    assert result.failure_mode == "provider_error"


def test_request_metadata_redacts_secrets_and_result_is_serializable() -> None:
    runner, client = _runner(_VALID)
    result = runner.run(
        contract=_contract(),
        variables={"context_json": {}, "candidate_summary": "s", "api_key": "secret-123"},
        request_id="r1",
        metadata={"k": "v", "api_key": "should-not-store", "token": "hide-me"},
    )
    assert client.last_request is not None
    assert client.last_request.prompt_ref == "promotion_decision:v1"
    assert client.last_request.prompt_hash
    assert client.last_request.metadata["api_key"] == "[REDACTED]"
    assert client.last_request.metadata["token"] == "[REDACTED]"
    assert "secret-123" not in client.last_request.system
    assert "secret-123" not in client.last_request.user
    dumped = result.model_dump(mode="json")
    assert isinstance(dumped, dict)
    json.dumps(dumped)


def test_request_metadata_redaction_is_recursive_and_non_mutating() -> None:
    runner, client = _runner(_VALID)
    metadata = {"token": "top", "nested": {"password": "pw"}, "items": [{"authorization": "a1"}]}
    original = {"token": "top", "nested": {"password": "pw"}, "items": [{"authorization": "a1"}]}
    result = runner.run(
        contract=_contract(),
        variables={"context_json": {}, "candidate_summary": "s"},
        request_id="r-nested",
        metadata=metadata,
    )
    assert client.last_request is not None
    assert client.last_request.metadata["token"] == "[REDACTED]"
    assert client.last_request.metadata["nested"]["password"] == "[REDACTED]"
    assert client.last_request.metadata["items"][0]["authorization"] == "[REDACTED]"
    assert metadata == original
    dumped = json.dumps(result.model_dump(mode="json"))
    assert "top" not in dumped
    assert "\"pw\"" not in dumped
    assert "\"a1\"" not in dumped


def test_schema_error_message_is_safe_and_does_not_echo_values() -> None:
    secret = "TOP_SECRET_SHOULD_NOT_APPEAR"
    bad_payload = f'{{"promote": true, "target_plane": "semantic", "rationale": "{secret}", "confidence": 5, "failure_mode": null, "requires_judge_review": false}}'
    runner, _ = _runner(bad_payload)
    result = runner.run(contract=_contract(), variables={"context_json": {}, "candidate_summary": "s"}, request_id="r1")
    assert result.success is False
    assert result.response.error == "Response failed schema validation."
    assert secret not in (result.response.error or "")


def test_no_api_key_required_and_provider_none_works_with_fake() -> None:
    config = LLMRuntimeConfig.from_env({"MEMORII_LLM_PROVIDER": "none"})
    assert config.has_api_key() is False
    runner = PromptLLMRunner(client=FakeLLMStructuredClient(default_response=_VALID), config=config)
    result = runner.run(contract=_contract(), variables={"context_json": {}, "candidate_summary": "s"}, request_id="r1")
    assert result.success is True


def test_optional_live_llm_tests_are_gated() -> None:
    env = {"MEMORII_ENABLE_LIVE_LLM_TESTS": "true", "MEMORII_LLM_PROVIDER": "openai"}
    config = LLMRuntimeConfig.from_env(env)
    if not config.should_run_live_llm_tests():
        pytest.skip("live LLM tests are disabled unless key + flag are present")
    pytest.fail("live network test intentionally not implemented in unit tests")
