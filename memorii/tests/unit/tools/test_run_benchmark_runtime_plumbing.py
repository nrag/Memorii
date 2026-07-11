from __future__ import annotations

import argparse
import json
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
    run_dir = tmp_path / "runtime-artifacts"

    def _fake_load(_args: argparse.Namespace):
        return [], "unit"

    def _fake_rows(**_kwargs: object) -> RuntimeSuiteRows:
        return RuntimeSuiteRows(scenario_rows=[], checkpoint_rows=[], judge_rows=[], llm_rows=[])

    def _fake_artifacts(**_kwargs: object) -> Path:
        run_dir.mkdir(parents=True)
        with (run_dir / "report.json").open("w", encoding="utf-8") as handle:
            json.dump(
                {
                    "suite": "memory_evolution_runtime_v1",
                    "mode": "hybrid",
                    "profile": "smoke",
                    "seed": 0,
                    "scenario_count": 0,
                    "event_count": 0,
                    "checkpoint_count": 0,
                    "passed": 0,
                    "failed": 0,
                    "llm_calls": 0,
                    "provider_successes": 0,
                    "provider_failures": 0,
                    "fallbacks": 0,
                    "final_output_source_counts": {},
                    "metrics": {},
                    "calibration": {
                        "event_count": 0,
                        "labeled_event_count": 0,
                        "overall_accuracy": None,
                        "ece": None,
                        "brier_score": None,
                        "overconfident_wrong_count": 0,
                        "low_confidence_correct_count": 0,
                        "hidden_hallucination_rate": 0.0,
                        "ambiguous_overcommit_rate": 0.0,
                        "worst_slices": [],
                        "rolling_windows": {},
                        "response_recommendations": {},
                        "label_source_counts": {},
                        "hierarchy_layer_counts": {},
                    },
                    "decision_quality": {
                        "decision_cost_total": 0.0,
                        "decision_cost_mean": 0.0,
                        "cost_by_failure_bucket": {},
                        "cost_by_checkpoint_type": {},
                        "cost_by_source_modality": {},
                        "cost_by_decision_action": {},
                        "regret_total": 0.0,
                        "regret_mean": 0.0,
                    },
                },
                handle,
            )
        return run_dir

    def _raise_on_report_write(self: Path, *_args: object, **_kwargs: object) -> int:
        if self == run_dir / "report.json":
            raise OSError("report write failed")
        return original_write_text(self, *_args, **_kwargs)

    original_write_text = Path.write_text
    monkeypatch.setattr(runtime_suite, "_load_memory_evolution_sim_suite", _fake_load)
    monkeypatch.setattr(runtime_suite, "run_runtime_scenarios", _fake_rows)
    monkeypatch.setattr(runtime_suite, "_write_memory_evolution_sim_artifacts", _fake_artifacts)
    monkeypatch.setattr(runtime_suite, "write_runtime_artifacts", lambda **_kwargs: None)
    monkeypatch.setattr(runtime_suite, "runtime_summary_metrics", lambda _rows: {})
    monkeypatch.setattr(runtime_suite, "runtime_warning_policy", lambda: {})
    monkeypatch.setattr(runtime_suite, "_print_memory_evolution_sim_summary", lambda **_kwargs: None)
    monkeypatch.setattr(Path, "write_text", _raise_on_report_write)

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
