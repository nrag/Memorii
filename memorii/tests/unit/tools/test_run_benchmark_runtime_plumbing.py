from __future__ import annotations

import argparse
from pathlib import Path

import pytest
from memorii.core.benchmark.memory_evolution_runtime import RuntimeSuiteRows
from memorii.core.benchmark.memory_evolution_runtime.runner import build_runtime_extractor
from memorii.core.llm_config import LLMRuntimeConfig
from memorii.core.llm_provider.models import LLMStructuredRequest, LLMStructuredResponse
from memorii.tools.benchmark_suites import memory_evolution_runtime as runtime_suite
from memorii.tools.run_benchmark import main
from tests.unit.core.benchmark.memory_evolution_test_helpers import generate_scenario_by_family
from tests.unit.tools.run_benchmark_test_helpers import _clear_llm_env


def test_runtime_benchmark_report_write_failure_is_not_swallowed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    args = argparse.Namespace(
        mode="hybrid",
        dry_run=True,
        allow_live=False,
        storage_root=str(tmp_path),
        sim_profile="smoke",
    )
    def _fake_load(_args: argparse.Namespace):
        return [], "unit"

    def _fake_rows(**_kwargs: object) -> RuntimeSuiteRows:
        return RuntimeSuiteRows(scenario_rows=[], checkpoint_rows=[], judge_rows=[], llm_rows=[])

    def _raise_on_required_artifact_write(**_kwargs: object) -> Path:
        raise OSError("report write failed")

    monkeypatch.setattr(runtime_suite, "load_memory_evolution_scenarios", _fake_load)
    monkeypatch.setattr(runtime_suite, "run_runtime_scenarios", _fake_rows)
    monkeypatch.setattr(
        runtime_suite,
        "write_memory_evolution_artifacts",
        _raise_on_required_artifact_write,
    )
    monkeypatch.setattr(runtime_suite, "runtime_warning_policy", lambda: {})
    monkeypatch.setattr(runtime_suite, "print_memory_evolution_summary", lambda **_kwargs: None)

    with pytest.raises(OSError, match="report write failed"):
        runtime_suite._run_memory_evolution_runtime_suite(
            args,
            prompt_root=tmp_path,
            dependencies=runtime_suite.BenchmarkRuntimeDependencies(),
        )


def test_runtime_extractor_uses_injected_llm_client_factory(tmp_path: Path) -> None:
    calls: list[LLMRuntimeConfig] = []

    class StubClient:
        def complete_structured(
            self,
            request: LLMStructuredRequest,
            *,
            config: LLMRuntimeConfig | None = None,
        ) -> LLMStructuredResponse:
            raise AssertionError("extractor construction should not call the client")

    class StubFactory:
        @staticmethod
        def from_config(config: LLMRuntimeConfig) -> StubClient:
            calls.append(config)
            return StubClient()

    scenario = generate_scenario_by_family(
        profile="smoke",
        family="entity_definition_before_role_claims",
        scenario_count=10,
        seed=7,
    )

    extractor = build_runtime_extractor(
        scenario=scenario,
        effective_mode="llm",
        dry_run=False,
        runtime_config=LLMRuntimeConfig(provider="fake"),
        prompt_root=tmp_path,
        llm_client_factory=StubFactory,
    )

    assert calls == [LLMRuntimeConfig(provider="fake")]
    assert extractor is not None


def test_non_hotpotqa_suite_does_not_resolve_hotpotqa_default_dataset(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _clear_llm_env(monkeypatch)

    def _unexpected_hotpotqa_default():
        raise AssertionError("non-HotPotQA suites must not resolve HotPotQA package data")

    monkeypatch.setattr(
        "memorii.tools.benchmark_suites.runtime_dependencies.hotpotqa_default_dataset_path",
        _unexpected_hotpotqa_default,
    )

    assert main(["--suite", "memory_lifecycle_v1", "--storage-root", str(tmp_path)]) == 0
