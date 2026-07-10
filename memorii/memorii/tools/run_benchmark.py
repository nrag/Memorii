from __future__ import annotations

import argparse
from pathlib import Path

from memorii.tools.benchmark_suites import runtime_dependencies
from memorii.tools.benchmark_suites.registry import build_benchmark_suite_registry

EvalFakeClient = runtime_dependencies.EvalFakeClient
LLMClientFactory = runtime_dependencies.LLMClientFactory
_DEFAULT_EVAL_FAKE_CLIENT = runtime_dependencies._DEFAULT_EVAL_FAKE_CLIENT
_DEFAULT_HOTPOTQA_DATASET = runtime_dependencies._DEFAULT_HOTPOTQA_DATASET

def _benchmark_runtime_dependencies() -> runtime_dependencies.BenchmarkRuntimeDependencies:
    return runtime_dependencies.BenchmarkRuntimeDependencies(
        eval_fake_client_cls=EvalFakeClient,
        llm_client_factory=LLMClientFactory,
        default_eval_fake_client_cls=_DEFAULT_EVAL_FAKE_CLIENT,
    )


def _build_benchmark_suite_registry():
    return build_benchmark_suite_registry(dependencies=_benchmark_runtime_dependencies())


def benchmark_suite_names() -> list[str]:
    return _build_benchmark_suite_registry().suite_names()


def _run_parsed_args(args: argparse.Namespace, *, suite_registry) -> int:
    prompt_root = Path(args.prompt_root) if args.prompt_root else Path(__file__).resolve().parents[2] / "prompts"
    runner = suite_registry.get(args.suite)
    if not runner.supports_mode(args.mode):
        raise SystemExit(runner.unsupported_mode_message(args.mode))
    return runner.run(args, prompt_root=prompt_root)


def main(argv: list[str] | None = None) -> int:
    suite_registry = _build_benchmark_suite_registry()
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--suite",
        choices=suite_registry.suite_names(),
        default="memory_lifecycle_v1",
    )
    parser.add_argument("--mode", choices=["auto", "rule", "llm", "hybrid", "all"], default="auto")
    parser.add_argument("--systems", choices=["memorii", "all"], default="memorii")
    parser.add_argument("--storage-root", default=".memorii")
    parser.add_argument("--prompt-root", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-live", action="store_true")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--run-label", default=None)
    parser.add_argument("--hotpotqa-dataset", default=None)
    parser.add_argument("--hotpotqa-split", default="validation")
    parser.add_argument("--hotpotqa-subset-size", type=int, default=3)
    parser.add_argument("--hotpotqa-question-type", choices=["bridge", "comparison"], default=None)
    parser.add_argument("--hotpotqa-diagnostics", choices=["none", "oracle"], default="none")
    parser.add_argument("--sim-profile", choices=["smoke", "adversarial", "long_horizon"], default="smoke")
    parser.add_argument("--sim-scenario-count", type=int, default=10)
    parser.add_argument("--sim-min-events", type=int, default=None)
    parser.add_argument("--sim-max-events", type=int, default=None)
    parser.add_argument("--sim-noise-rate", type=float, default=None)
    parser.add_argument("--sim-fixture-path", default=None)
    parser.add_argument("--sim-freeze-output", action="store_true")
    parser.add_argument("--sim-export-review-set", default=None)
    args = parser.parse_args(argv)

    if args.hotpotqa_dataset is None and args.suite in {"hotpotqa_v1", "hotpotqa_official_v1"}:
        with runtime_dependencies.hotpotqa_default_dataset_path() as dataset_path:
            args.hotpotqa_dataset = str(dataset_path)
            return _run_parsed_args(args, suite_registry=suite_registry)
    return _run_parsed_args(args, suite_registry=suite_registry)


if __name__ == "__main__":
    raise SystemExit(main())
