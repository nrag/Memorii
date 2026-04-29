from __future__ import annotations

import re
from pathlib import Path

import pytest

from memorii.core.llm_config import LLMRuntimeConfig


def test_default_from_env_empty() -> None:
    cfg = LLMRuntimeConfig.from_env({})
    assert cfg.provider == "none"
    assert not cfg.has_api_key()


def test_openai_loads_key() -> None:
    cfg = LLMRuntimeConfig.from_env({"MEMORII_LLM_PROVIDER": "openai", "OPENAI_API_KEY": "secret"})
    assert cfg.has_api_key()


def test_anthropic_loads_key() -> None:
    cfg = LLMRuntimeConfig.from_env({"MEMORII_LLM_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "secret"})
    assert cfg.has_api_key()


def test_provider_none_no_key_required() -> None:
    cfg = LLMRuntimeConfig.from_env({"MEMORII_LLM_PROVIDER": "none"})
    assert not cfg.has_api_key()


def test_require_api_key_raises_safe() -> None:
    cfg = LLMRuntimeConfig.from_env({"MEMORII_LLM_PROVIDER": "openai"})
    with pytest.raises(RuntimeError, match="required"):
        cfg.require_api_key()


def test_redacted_no_secret() -> None:
    cfg = LLMRuntimeConfig.from_env({"MEMORII_LLM_PROVIDER": "openai", "OPENAI_API_KEY": "super-secret-value"})
    data = cfg.redacted_dict()
    assert data["api_key"] == "present"
    assert "super-secret-value" not in str(data)


def test_should_run_live_llm_tests_paths() -> None:
    assert not LLMRuntimeConfig.from_env({"MEMORII_ENABLE_LIVE_LLM_TESTS": "false", "MEMORII_LLM_PROVIDER": "openai", "OPENAI_API_KEY": "x"}).should_run_live_llm_tests()
    assert not LLMRuntimeConfig.from_env({"MEMORII_ENABLE_LIVE_LLM_TESTS": "true", "MEMORII_LLM_PROVIDER": "openai"}).should_run_live_llm_tests()
    assert LLMRuntimeConfig.from_env({"MEMORII_ENABLE_LIVE_LLM_TESTS": "true", "MEMORII_LLM_PROVIDER": "openai", "OPENAI_API_KEY": "x"}).should_run_live_llm_tests()


@pytest.mark.parametrize("value", ["true", "1", "yes", "y", "on", "false", "0", "no", "n", "off", ""])
def test_boolean_variants(value: str) -> None:
    LLMRuntimeConfig.from_env({"MEMORII_ENABLE_LIVE_LLM_TESTS": value})


def test_invalid_boolean_raises() -> None:
    with pytest.raises(ValueError):
        LLMRuntimeConfig.from_env({"MEMORII_ENABLE_LIVE_LLM_TESTS": "maybe"})


def test_invalid_timeout_retry_raise() -> None:
    with pytest.raises(ValueError):
        LLMRuntimeConfig.from_env({"MEMORII_LLM_TIMEOUT_SECONDS": "0"})
    with pytest.raises(ValueError):
        LLMRuntimeConfig.from_env({"MEMORII_LLM_MAX_RETRIES": "-1"})


def test_gitignore_env_rules() -> None:
    gitignore = Path(".gitignore").read_text()
    assert ".env" in gitignore
    assert ".env.*" in gitignore
    assert "!.env.example" in gitignore


def test_env_example_placeholders_only() -> None:
    body = Path(".env.example").read_text()
    assert "OPENAI_API_KEY=" in body
    assert "ANTHROPIC_API_KEY=" in body
    assert not re.search(r"sk-[A-Za-z0-9]", body)
