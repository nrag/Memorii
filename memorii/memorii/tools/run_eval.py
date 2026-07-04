from __future__ import annotations

import argparse

from memorii.core.env_config import load_memorii_environment
from memorii.core.llm_config import LLMDecisionRuntimeConfig, LLMRuntimeConfig
from memorii.tools import run_benchmark, run_live_llm_eval


DECISION_SUITES = {
    "promotion_belief_v1": "all",
    "promotion_v1": "promotion",
    "belief_v1": "belief",
}

BENCHMARK_SUITES = {
    "memory_lifecycle_v1",
    "execution_graph_v1",
    "memory_evolution_v1",
    "memory_evolution_sim_v1",
    "retrieval_corruption_v1",
    "hotpotqa_v1",
    "hotpotqa_official_v1",
}

AGGREGATE_SUITES = {"all"}


def _add_bool_flag(argv: list[str], *, enabled: bool, flag: str) -> None:
    if enabled:
        argv.append(flag)


def _run_decision_suite(args: argparse.Namespace) -> int:
    golden_set = DECISION_SUITES[args.suite]
    mode = args.mode
    if mode in {"auto", "hybrid"}:
        env_snapshot = load_memorii_environment()
        runtime_config = LLMRuntimeConfig.from_env(env_snapshot.env)
        decision_config = (
            LLMDecisionRuntimeConfig.from_env(env_snapshot.env)
            if mode == "auto"
            else LLMDecisionRuntimeConfig(mode="hybrid")
        )
        mode = decision_config.resolve(runtime_config)
    argv = [
        "--golden-set",
        golden_set,
        "--mode",
        mode,
        "--storage-root",
        args.storage_root,
    ]
    if args.prompt_root is not None:
        argv.extend(["--prompt-root", args.prompt_root])
    if args.min_judge_score_to_keep is not None:
        argv.extend(["--min-judge-score-to-keep", str(args.min_judge_score_to_keep)])
    _add_bool_flag(argv, enabled=args.dry_run, flag="--dry-run")
    _add_bool_flag(argv, enabled=args.allow_live, flag="--allow-live")
    _add_bool_flag(argv, enabled=args.trace_successes, flag="--trace-successes")
    _add_bool_flag(argv, enabled=args.no_trace_failures, flag="--no-trace-failures")
    _add_bool_flag(argv, enabled=args.no_trace_fallbacks, flag="--no-trace-fallbacks")
    _add_bool_flag(argv, enabled=args.no_trace_disagreements, flag="--no-trace-disagreements")
    _add_bool_flag(argv, enabled=args.no_trace_human_review, flag="--no-trace-human-review")
    return run_live_llm_eval.main(argv)


def _run_benchmark_suite(args: argparse.Namespace) -> int:
    argv = [
        "--suite",
        args.suite,
        "--mode",
        args.mode,
        "--systems",
        args.systems,
        "--storage-root",
        args.storage_root,
        "--seed",
        str(args.seed),
    ]
    if args.prompt_root is not None:
        argv.extend(["--prompt-root", args.prompt_root])
    if args.run_label is not None:
        argv.extend(["--run-label", args.run_label])
    if args.suite in {"hotpotqa_v1", "hotpotqa_official_v1"}:
        argv.extend(
            [
                "--hotpotqa-dataset",
                args.hotpotqa_dataset,
                "--hotpotqa-split",
                args.hotpotqa_split,
                "--hotpotqa-subset-size",
                str(args.hotpotqa_subset_size),
            ]
        )
        if args.hotpotqa_question_type is not None:
            argv.extend(["--hotpotqa-question-type", args.hotpotqa_question_type])
        if args.suite == "hotpotqa_official_v1":
            argv.extend(["--hotpotqa-diagnostics", args.hotpotqa_diagnostics])
    if args.suite == "memory_evolution_sim_v1":
        argv.extend(
            [
                "--sim-profile",
                args.sim_profile,
                "--sim-scenario-count",
                str(args.sim_scenario_count),
            ]
        )
        if args.sim_min_events is not None:
            argv.extend(["--sim-min-events", str(args.sim_min_events)])
        if args.sim_max_events is not None:
            argv.extend(["--sim-max-events", str(args.sim_max_events)])
        if args.sim_noise_rate is not None:
            argv.extend(["--sim-noise-rate", str(args.sim_noise_rate)])
        if args.sim_fixture_path is not None:
            argv.extend(["--sim-fixture-path", args.sim_fixture_path])
        if args.sim_export_review_set is not None:
            argv.extend(["--sim-export-review-set", args.sim_export_review_set])
        _add_bool_flag(argv, enabled=args.sim_freeze_output, flag="--sim-freeze-output")
    _add_bool_flag(argv, enabled=args.dry_run, flag="--dry-run")
    _add_bool_flag(argv, enabled=args.allow_live, flag="--allow-live")
    return run_benchmark.main(argv)


def _run_all_suites(args: argparse.Namespace) -> int:
    print("suite=promotion_belief_v1 status=starting")
    decision_args = argparse.Namespace(**vars(args))
    decision_args.suite = "promotion_belief_v1"
    decision_status = _run_decision_suite(decision_args)
    print(f"suite=promotion_belief_v1 status=finished exit_code={decision_status}")

    print("suite=memory_lifecycle_v1 status=starting")
    benchmark_args = argparse.Namespace(**vars(args))
    benchmark_args.suite = "memory_lifecycle_v1"
    benchmark_status = _run_benchmark_suite(benchmark_args)
    print(f"suite=memory_lifecycle_v1 status=finished exit_code={benchmark_status}")

    print("suite=retrieval_corruption_v1 status=starting")
    retrieval_args = argparse.Namespace(**vars(args))
    retrieval_args.suite = "retrieval_corruption_v1"
    retrieval_status = _run_benchmark_suite(retrieval_args)
    print(f"suite=retrieval_corruption_v1 status=finished exit_code={retrieval_status}")

    print("suite=execution_graph_v1 status=starting")
    execution_args = argparse.Namespace(**vars(args))
    execution_args.suite = "execution_graph_v1"
    execution_status = _run_benchmark_suite(execution_args)
    print(f"suite=execution_graph_v1 status=finished exit_code={execution_status}")
    return decision_status or benchmark_status or execution_status or retrieval_status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--suite",
        choices=[*AGGREGATE_SUITES, *DECISION_SUITES.keys(), *BENCHMARK_SUITES],
        default="all",
    )
    parser.add_argument("--storage-root", default=".memorii")

    parser.add_argument("--mode", choices=["auto", "rule", "llm", "hybrid", "all"], default="auto")
    parser.add_argument("--prompt-root", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-live", action="store_true")
    parser.add_argument("--trace-successes", action="store_true")
    parser.add_argument("--no-trace-failures", action="store_true")
    parser.add_argument("--no-trace-fallbacks", action="store_true")
    parser.add_argument("--no-trace-disagreements", action="store_true")
    parser.add_argument("--no-trace-human-review", action="store_true")
    parser.add_argument("--min-judge-score-to-keep", type=float, default=None)

    parser.add_argument("--systems", choices=["memorii", "all"], default="memorii")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--run-label", default=None)
    parser.add_argument("--hotpotqa-dataset", default=str(run_benchmark._DEFAULT_HOTPOTQA_DATASET))
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

    if args.suite in AGGREGATE_SUITES:
        if args.systems != "memorii":
            raise SystemExit("suite all does not support --systems")
        return _run_all_suites(args)
    if args.suite in DECISION_SUITES:
        if args.systems != "memorii":
            raise SystemExit(f"{args.suite} does not support --systems")
        return _run_decision_suite(args)
    return _run_benchmark_suite(args)


if __name__ == "__main__":
    raise SystemExit(main())
