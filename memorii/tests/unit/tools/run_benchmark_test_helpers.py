from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from memorii.core.llm_config import LLMRuntimeConfig
from memorii.core.llm_provider.base import LLMStructuredClient
from memorii.tools.benchmark_suites.runtime_dependencies import (
    BenchmarkRuntimeDependencies,
    DryRunDecisionStrategy,
    ExecutionBackend,
    LLMClientBinding,
)
from memorii.tools.run_benchmark import BenchmarkApplication


def _clear_llm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in [
        "MEMORII_LLM_PROVIDER",
        "MEMORII_LLM_MODEL",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "MEMORII_DECISION_MODE",
    ]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("MEMORII_LLM_PROVIDER", "none")


def _latest_run_dir(storage_root: Path, suite: str, mode: str = "auto") -> Path:
    return max(
        (storage_root / "benchmark_runs" / suite / mode).glob("bench-*"),
        key=lambda path: path.stat().st_mtime_ns,
    )


def _summary_fields(output: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for part in output.strip().split():
        if "=" not in part:
            continue
        key, value = part.split("=", maxsplit=1)
        fields[key] = value
    return fields


def _jsonl_count(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    return len(text.splitlines()) if text else 0


def _application_with_fake_client(
    client_factory: Callable[[], LLMStructuredClient],
) -> BenchmarkApplication:
    def factory() -> LLMClientBinding:
        client = client_factory()
        return LLMClientBinding(
            client=client,
            backend=ExecutionBackend.FAKE_ORACLE,
            provider_name=client.provider_name,
        )

    return BenchmarkApplication(
        dependencies=BenchmarkRuntimeDependencies(
            fake_client_binding_factory=factory,
            dry_run_decision_strategy=DryRunDecisionStrategy.CLIENT_ADAPTERS,
        )
    )


def _application_with_live_client(
    client_factory: Callable[[], LLMStructuredClient],
) -> BenchmarkApplication:
    def factory(_config: LLMRuntimeConfig) -> LLMClientBinding:
        client = client_factory()
        return LLMClientBinding(
            client=client,
            backend=ExecutionBackend.LIVE_PROVIDER,
            provider_name=client.provider_name,
        )

    return BenchmarkApplication(
        dependencies=BenchmarkRuntimeDependencies(live_client_binding_factory=factory)
    )
