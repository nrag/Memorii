from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from memorii.tools.benchmark_registry import BenchmarkSuiteRegistry, FunctionBenchmarkSuiteRunner
from memorii.tools.run_benchmark import BenchmarkApplication, benchmark_suite_names, main


def test_run_benchmark_rejects_unknown_suite() -> None:
    with pytest.raises(SystemExit):
        main(["--suite", "unknown"])


def test_benchmark_suite_registry_contains_cli_suites() -> None:
    assert benchmark_suite_names() == [
        "memory_lifecycle_v1",
        "execution_graph_v1",
        "memory_evolution_v1",
        "memory_evolution_sim_v1",
        "memory_evolution_runtime_v1",
        "retrieval_corruption_v1",
        "hotpotqa_v1",
        "hotpotqa_official_v1",
        "minimal",
    ]
    registry = BenchmarkApplication().suite_registry()
    assert registry.get("memory_evolution_runtime_v1").supports_mode("hybrid")
    assert registry.get("hotpotqa_v1").supports_mode("rule")
    assert not registry.get("hotpotqa_v1").supports_mode("llm")
    assert not registry.get("hotpotqa_v1").supports_mode("hybrid")


def test_benchmark_suite_registry_rejects_duplicate_names() -> None:
    def _noop(_args, _prompt_root):
        return 0

    with pytest.raises(ValueError, match="Duplicate benchmark suite runner"):
        BenchmarkSuiteRegistry([
            FunctionBenchmarkSuiteRunner("duplicate", _noop, frozenset({"rule"})),
            FunctionBenchmarkSuiteRunner("duplicate", _noop, frozenset({"rule"})),
        ])


def test_run_benchmark_dispatches_to_registered_runner(tmp_path: Path) -> None:
    calls: list[tuple[str, str, Path]] = []

    class RecordingRunner:
        suite_name = "custom_v1"

        def supports_mode(self, mode: str) -> bool:
            return mode == "rule"

        def unsupported_mode_message(self, mode: str) -> str:
            return f"custom_v1 rejects {mode}"

        def run(self, args, *, prompt_root: Path) -> int:
            calls.append((args.suite, args.mode, prompt_root))
            return 7

    application = BenchmarkApplication(registry=BenchmarkSuiteRegistry([RecordingRunner()]))
    assert application.run(
        ["--suite", "custom_v1", "--mode", "rule", "--prompt-root", str(tmp_path)]
    ) == 7
    assert calls == [("custom_v1", "rule", tmp_path)]


def test_run_benchmark_uses_runner_unsupported_mode_message() -> None:
    class RuleOnlyRunner:
        suite_name = "custom_v1"

        def supports_mode(self, mode: str) -> bool:
            return mode == "rule"

        def unsupported_mode_message(self, mode: str) -> str:
            return f"custom_v1 rejects {mode}"

        def run(self, args, *, prompt_root: Path) -> int:
            raise AssertionError("unsupported mode should not dispatch")

    application = BenchmarkApplication(registry=BenchmarkSuiteRegistry([RuleOnlyRunner()]))
    with pytest.raises(SystemExit, match="custom_v1 rejects llm"):
        application.run(["--suite", "custom_v1", "--mode", "llm"])


def test_benchmark_suite_runner_modules_import() -> None:
    modules = [
        "memorii.tools.benchmark_suites.execution_graph",
        "memorii.tools.benchmark_suites.fixture_harness",
        "memorii.tools.benchmark_suites.fixture_loaders",
        "memorii.tools.benchmark_suites.hotpotqa_v1",
        "memorii.tools.benchmark_suites.hotpotqa_official",
        "memorii.tools.benchmark_suites.memory_evolution",
        "memorii.tools.benchmark_suites.memory_evolution_runtime",
        "memorii.tools.benchmark_suites.memory_evolution_sim",
        "memorii.tools.benchmark_suites.memory_lifecycle_fixture",
        "memorii.tools.benchmark_suites.minimal",
        "memorii.tools.benchmark_suites.registry",
        "memorii.tools.benchmark_suites.retrieval_corruption",
    ]

    for module_name in modules:
        assert importlib.import_module(module_name)


def test_benchmark_suite_modules_use_direct_ownership() -> None:
    suite_root = Path(__file__).resolve().parents[3] / "memorii" / "tools" / "benchmark_suites"

    assert not (suite_root / "_implementation.py").exists()
    assert not (suite_root / "shared.py").exists()
    assert not (suite_root / "fixture_backed.py").exists()

