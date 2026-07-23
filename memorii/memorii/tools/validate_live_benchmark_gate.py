"""Evaluate a multi-seed live memory-evolution benchmark gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from memorii.core.benchmark.calibration.gates import (
    evaluate_live_gate_with_policy,
    load_live_reports,
)
from memorii.core.benchmark.calibration.policy import DEFAULT_LIVE_CERTIFICATION_POLICY


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--baseline-root", type=Path)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    policy = DEFAULT_LIVE_CERTIFICATION_POLICY
    try:
        reports = load_live_reports(
            args.root,
            suite=policy.suite,
            mode=policy.mode,
            profile=policy.profile,
        )
        baseline_reports = (
            load_live_reports(
                args.baseline_root,
                suite=policy.suite,
                mode=policy.mode,
                profile=policy.profile,
            )
            if args.baseline_root is not None
            else []
        )
        summary = evaluate_live_gate_with_policy(
            reports,
            policy=policy,
            baseline_reports=baseline_reports,
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
