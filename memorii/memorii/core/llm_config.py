"""Safe runtime LLM config loaded from environment mappings."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, SecretStr


class LLMRuntimeConfig(BaseModel):
    provider: str = "none"
    model: str | None = None
    api_key: SecretStr | None = None
    timeout_seconds: int = 60
    max_retries: int = 2

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> LLMRuntimeConfig:
        source = env if env is not None else os.environ
        provider = (source.get("MEMORII_LLM_PROVIDER") or "none").strip().lower()
        model = (source.get("MEMORII_LLM_MODEL") or "").strip() or None
        timeout = _parse_int(source.get("MEMORII_LLM_TIMEOUT_SECONDS"), default=60, minimum=1)
        retries = _parse_int(source.get("MEMORII_LLM_MAX_RETRIES"), default=2, minimum=0)

        key: SecretStr | None = None
        if provider == "openai":
            raw = (source.get("OPENAI_API_KEY") or "").strip()
            key = SecretStr(raw) if raw else None
        elif provider == "anthropic":
            raw = (source.get("ANTHROPIC_API_KEY") or "").strip()
            key = SecretStr(raw) if raw else None

        return cls(
            provider=provider,
            model=model,
            api_key=key,
            timeout_seconds=timeout,
            max_retries=retries,
        )

    def has_api_key(self) -> bool:
        return self.api_key is not None and bool(self.api_key.get_secret_value())

    def has_live_provider(self) -> bool:
        return self.provider.strip().lower() not in {"none", "fake"} and self.has_api_key()

    def require_api_key(self) -> SecretStr:
        if not self.has_api_key():
            raise RuntimeError("LLM API key is required for configured provider but is missing.")
        return self.api_key  # type: ignore[return-value]

    def redacted_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "model": self.model,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "api_key": "present" if self.has_api_key() else "missing",
        }


class LLMLiveTestConfig(BaseModel):
    enable_live_llm_tests: bool = False

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> LLMLiveTestConfig:
        source = env if env is not None else os.environ
        return cls(enable_live_llm_tests=_parse_bool(source.get("MEMORII_ENABLE_LIVE_LLM_TESTS"), default=False))

    def should_run_live_llm_tests(self, runtime_config: LLMRuntimeConfig) -> bool:
        provider = runtime_config.provider.strip().lower()
        return self.enable_live_llm_tests and provider not in {"none", "fake"} and runtime_config.has_api_key()


DecisionModeName = Literal["auto", "rule", "llm", "hybrid"]
ResolvedDecisionModeName = Literal["rule", "llm", "hybrid"]


class LLMDecisionRuntimeConfig(BaseModel):
    mode: DecisionModeName = "auto"

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> LLMDecisionRuntimeConfig:
        source = env if env is not None else os.environ
        mode = (source.get("MEMORII_DECISION_MODE") or "auto").strip().lower()
        if mode not in {"auto", "rule", "llm", "hybrid"}:
            raise ValueError("Invalid MEMORII_DECISION_MODE value")
        return cls(mode=mode)  # type: ignore[arg-type]

    def resolve(self, runtime_config: LLMRuntimeConfig) -> ResolvedDecisionModeName:
        if self.mode == "auto":
            return "hybrid" if runtime_config.has_live_provider() else "rule"
        if self.mode == "hybrid" and not runtime_config.has_live_provider():
            return "rule"
        return self.mode  # type: ignore[return-value]


class ResolvedLLMDecisionConfig(BaseModel):
    """Validated LLM runtime and decision mode derived from one environment mapping."""

    runtime: LLMRuntimeConfig
    mode: ResolvedDecisionModeName

    model_config = ConfigDict(extra="forbid", frozen=True)

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> ResolvedLLMDecisionConfig:
        runtime = LLMRuntimeConfig.from_env(env)
        decision = LLMDecisionRuntimeConfig.from_env(env)
        return cls(runtime=runtime, mode=decision.resolve(runtime))


def _parse_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"", "false", "0", "no", "n", "off"}:
        return False
    if normalized in {"true", "1", "yes", "y", "on"}:
        return True
    raise ValueError("Invalid boolean environment value")


def _parse_int(value: str | None, *, default: int, minimum: int) -> int:
    parsed = default if value is None or value.strip() == "" else int(value)
    if parsed < minimum:
        raise ValueError("Invalid integer environment value")
    return parsed
