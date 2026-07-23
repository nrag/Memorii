"""Expose and execute the repository-owned live certification policy."""

from __future__ import annotations

import argparse
import json

from memorii.core.benchmark.calibration.design_audit import (
    audit_live_certification_design,
)
from memorii.core.benchmark.calibration.policy import DEFAULT_LIVE_CERTIFICATION_POLICY
from memorii.tools import run_eval


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("describe")
    subparsers.add_parser("github-matrix")
    subparsers.add_parser("preflight")
    run_parser = subparsers.add_parser("run-replicate")
    run_parser.add_argument("--storage-root", required=True)
    run_parser.add_argument("--seed", type=int, required=True)
    run_parser.add_argument("--replicate", type=int, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    policy = DEFAULT_LIVE_CERTIFICATION_POLICY
    if args.command == "describe":
        print(
            json.dumps(
                {
                    "digest": policy.digest(),
                    "policy": policy.model_dump(mode="json"),
                },
                sort_keys=True,
            )
        )
        return 0
    if args.command == "github-matrix":
        print(json.dumps(policy.github_matrix(), separators=(",", ":"), sort_keys=True))
        return 0
    if args.command == "preflight":
        audit = audit_live_certification_design(policy)
        print(json.dumps(audit.model_dump(mode="json"), sort_keys=True))
        return 0 if audit.passed else 1
    if args.seed not in policy.seeds:
        raise ValueError(f"seed {args.seed} is not part of the live certification policy")
    if args.replicate not in policy.replicates:
        raise ValueError(f"replicate {args.replicate} is not part of the live certification policy")
    return run_eval.main(
        [
            "--suite",
            policy.suite,
            "--mode",
            policy.mode,
            "--allow-live",
            "--defer-live-gate",
            "--storage-root",
            args.storage_root,
            "--sim-profile",
            policy.profile,
            "--sim-scenario-count",
            str(policy.scenarios_per_replicate),
            "--sim-min-events",
            str(policy.minimum_events),
            "--sim-max-events",
            str(policy.maximum_events),
            "--sim-noise-rate",
            str(policy.noise_rate),
            "--seed",
            str(args.seed),
            "--inference-replicate",
            str(args.replicate),
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
