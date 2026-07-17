"""Evaluate a multi-seed live memory-evolution benchmark gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from memorii.core.calibration.gates import evaluate_live_gate, load_live_reports


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--suite", required=True)
    parser.add_argument("--mode", default="hybrid")
    parser.add_argument("--profile", default="long_horizon")
    parser.add_argument("--minimum-seed-count", type=int, default=10)
    parser.add_argument("--minimum-scenarios-per-seed", type=int, default=25)
    parser.add_argument("--minimum-pass-rate-lower-bound", type=float, default=0.90)
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
            minimum_scenarios_per_seed=args.minimum_scenarios_per_seed,
            minimum_pass_rate_lower_bound=args.minimum_pass_rate_lower_bound,
            maximum_provider_failure_rate=args.maximum_provider_failure_rate,
            maximum_fallback_rate=args.maximum_fallback_rate,
            baseline_reports=baseline_reports,
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
