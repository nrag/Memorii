"""Evaluate a multi-seed live memory-evolution benchmark gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from memorii.core.benchmark.calibration.gates import evaluate_live_gate, load_live_reports
from memorii.core.benchmark.memory_evolution_sim import MEMORY_EVOLUTION_SCENARIO_FAMILIES


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--suite", required=True)
    parser.add_argument("--mode", default="hybrid")
    parser.add_argument("--profile", default="long_horizon")
    parser.add_argument("--minimum-seed-count", type=int, default=10)
    parser.add_argument("--minimum-scenarios-per-replicate", type=int, default=25)
    parser.add_argument("--minimum-replicates-per-seed", type=int, default=2)
    parser.add_argument("--minimum-pass-rate-lower-bound", type=float, default=0.90)
    parser.add_argument("--minimum-family-pass-rate-lower-bound", type=float, default=0.75)
    parser.add_argument("--minimum-family-scenarios-per-seed", type=int, default=2)
    parser.add_argument("--minimum-seed-pass-rate", type=float, default=0.80)
    parser.add_argument("--confidence-level", type=float, default=0.95)
    parser.add_argument("--design-target-scenario-reliability", type=float, default=0.98)
    parser.add_argument("--minimum-design-power", type=float, default=0.80)
    parser.add_argument("--maximum-null-acceptance-probability", type=float, default=0.05)
    parser.add_argument("--minimum-interval-coverage", type=float, default=0.90)
    parser.add_argument("--design-trials", type=int, default=500)
    parser.add_argument("--intraseed-correlation", type=float, default=0.05)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--maximum-provider-failure-rate", type=float, default=0.05)
    parser.add_argument("--maximum-fallback-rate", type=float, default=0.05)
    parser.add_argument("--baseline-root", type=Path)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        reports = load_live_reports(
            args.root,
            suite=args.suite,
            mode=args.mode,
            profile=args.profile,
        )
        baseline_reports = (
            load_live_reports(
                args.baseline_root,
                suite=args.suite,
                mode=args.mode,
                profile=args.profile,
            )
            if args.baseline_root is not None
            else []
        )
        summary = evaluate_live_gate(
            reports,
            suite=args.suite,
            mode=args.mode,
            profile=args.profile,
            minimum_seed_count=args.minimum_seed_count,
            minimum_scenarios_per_replicate=args.minimum_scenarios_per_replicate,
            minimum_replicates_per_seed=args.minimum_replicates_per_seed,
            minimum_pass_rate_lower_bound=args.minimum_pass_rate_lower_bound,
            minimum_family_pass_rate_lower_bound=args.minimum_family_pass_rate_lower_bound,
            minimum_family_scenarios_per_seed=args.minimum_family_scenarios_per_seed,
            minimum_seed_pass_rate=args.minimum_seed_pass_rate,
            confidence_level=args.confidence_level,
            design_target_scenario_reliability=args.design_target_scenario_reliability,
            minimum_design_power=args.minimum_design_power,
            maximum_null_acceptance_probability=args.maximum_null_acceptance_probability,
            minimum_interval_coverage=args.minimum_interval_coverage,
            design_trials=args.design_trials,
            intraseed_correlation=args.intraseed_correlation,
            maximum_provider_failure_rate=args.maximum_provider_failure_rate,
            maximum_fallback_rate=args.maximum_fallback_rate,
            baseline_reports=baseline_reports,
            required_families=(
                MEMORY_EVOLUTION_SCENARIO_FAMILIES
                if args.suite in {"memory_evolution_sim_v1", "memory_evolution_runtime_v1"}
                else ()
            ),
            source_revision=args.source_revision,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"live benchmark gate error: {exc}")
        return 1
    payload = summary.model_dump(mode="json")
    if args.output:
        args.output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))
    return 0 if summary.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
