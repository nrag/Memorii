"""Safe runtime LLM config loaded from environment mappings."""

from __future__ import annotations

import os
from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, SecretStr


class LLMRuntimeConfig(BaseModel):
    provider: str
    model: str | None = None
    api_key: SecretStr | None = None
    timeout_seconds: int = 60
    max_retries: int = 2
    enable_live_llm_tests: bool = False

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "LLMRuntimeConfig":
        source = env if env is not None else os.environ
        provider = (source.get("MEMORII_LLM_PROVIDER") or "none").strip().lower()
        model = (source.get("MEMORII_LLM_MODEL") or "").strip() or None
        timeout = _parse_int(source.get("MEMORII_LLM_TIMEOUT_SECONDS"), default=60, minimum=1)
        retries = _parse_int(source.get("MEMORII_LLM_MAX_RETRIES"), default=2, minimum=0)
        enable_live = _parse_bool(source.get("MEMORII_ENABLE_LIVE_LLM_TESTS"), default=False)

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
            enable_live_llm_tests=enable_live,
        )

    def has_api_key(self) -> bool:
        return self.api_key is not None and bool(self.api_key.get_secret_value())

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
            "enable_live_llm_tests": self.enable_live_llm_tests,
            "api_key": "present" if self.has_api_key() else "missing",
        }

    def should_run_live_llm_tests(self) -> bool:
        return self.enable_live_llm_tests and self.has_api_key()


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
    if value is None or value.strip() == "":
        parsed = default
    else:
        parsed = int(value)
    if parsed < minimum:
        raise ValueError("Invalid integer environment value")
    return parsed
