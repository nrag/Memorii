from __future__ import annotations

import re
from pathlib import Path

import pytest

from memorii.core.llm_config import LLMLiveTestConfig, LLMRuntimeConfig

REPO_ROOT = Path(__file__).resolve().parents[4]


def test_runtime_config_from_env_does_not_read_live_test_gate() -> None:
    cfg = LLMRuntimeConfig.from_env({"MEMORII_ENABLE_LIVE_LLM_TESTS": "true"})
    assert cfg.provider == "none"


def test_live_test_config_reads_gate_flag() -> None:
    cfg = LLMLiveTestConfig.from_env({"MEMORII_ENABLE_LIVE_LLM_TESTS": "true"})
    assert cfg.enable_live_llm_tests is True


def test_provider_specific_keys_load() -> None:
    assert LLMRuntimeConfig.from_env({"MEMORII_LLM_PROVIDER": "openai", "OPENAI_API_KEY": "secret"}).has_api_key()
    assert LLMRuntimeConfig.from_env({"MEMORII_LLM_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "secret"}).has_api_key()


def test_live_permission_requires_flag_and_key() -> None:
    runtime_with_key = LLMRuntimeConfig.from_env({"MEMORII_LLM_PROVIDER": "openai", "OPENAI_API_KEY": "x"})
    runtime_no_key = LLMRuntimeConfig.from_env({"MEMORII_LLM_PROVIDER": "openai"})
    assert LLMLiveTestConfig(enable_live_llm_tests=False).should_run_live_llm_tests(runtime_with_key) is False
    assert LLMLiveTestConfig(enable_live_llm_tests=True).should_run_live_llm_tests(runtime_no_key) is False
    assert LLMLiveTestConfig(enable_live_llm_tests=True).should_run_live_llm_tests(runtime_with_key) is True


def test_live_permission_rejects_none_and_fake_even_with_key() -> None:
    runtime_none = LLMRuntimeConfig(provider="none", api_key="secret")
    runtime_fake = LLMRuntimeConfig(provider="fake", api_key="secret")
    live = LLMLiveTestConfig(enable_live_llm_tests=True)
    assert live.should_run_live_llm_tests(runtime_none) is False
    assert live.should_run_live_llm_tests(runtime_fake) is False


def test_redacted_no_secret_and_no_test_flag() -> None:
    cfg = LLMRuntimeConfig.from_env({"MEMORII_LLM_PROVIDER": "openai", "OPENAI_API_KEY": "super-secret-value"})
    data = cfg.redacted_dict()
    assert data["api_key"] == "present"
    assert "enable_live_llm_tests" not in data
    assert "super-secret-value" not in str(data)


@pytest.mark.parametrize("value", ["true", "1", "yes", "y", "on", "false", "0", "no", "n", "off", ""])
def test_boolean_variants(value: str) -> None:
    LLMLiveTestConfig.from_env({"MEMORII_ENABLE_LIVE_LLM_TESTS": value})


def test_invalid_boolean_raises() -> None:
    with pytest.raises(ValueError):
        LLMLiveTestConfig.from_env({"MEMORII_ENABLE_LIVE_LLM_TESTS": "maybe"})


def test_invalid_timeout_retry_raise() -> None:
    with pytest.raises(ValueError):
        LLMRuntimeConfig.from_env({"MEMORII_LLM_TIMEOUT_SECONDS": "0"})
    with pytest.raises(ValueError):
        LLMRuntimeConfig.from_env({"MEMORII_LLM_MAX_RETRIES": "-1"})


def test_gitignore_env_rules() -> None:
    gitignore = (REPO_ROOT / ".gitignore").read_text()
    assert ".env" in gitignore
    assert ".env.*" in gitignore
    assert "!.env.example" in gitignore


def test_env_example_placeholders_only() -> None:
    body = (REPO_ROOT / ".env.example").read_text()
    assert "OPENAI_API_KEY=" in body
    assert "ANTHROPIC_API_KEY=" in body
    assert not re.search(r"sk-[A-Za-z0-9]", body)
