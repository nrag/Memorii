"""Installed command for configured acceptance evaluation.

The command accepts only candidate resource paths.  Authority construction is
provided by exactly one installed host runtime entry point, so command-line
arguments cannot replace keys, lifecycle history, numeric context, or limits.
"""

from __future__ import annotations

import argparse
from importlib.metadata import entry_points
from pathlib import Path
from typing import Protocol, runtime_checkable

from acceptance.evaluator import AcceptanceEvaluator


@runtime_checkable
class ConfiguredAcceptanceRuntime(Protocol):
    def evaluator(self) -> AcceptanceEvaluator: ...


def _configured_evaluator() -> AcceptanceEvaluator:
    candidates = tuple(entry_points(group="memorii.acceptance_evaluator_runtime"))
    if len(candidates) != 1:
        raise ValueError("acceptance_runtime_configuration")
    runtime = candidates[0].load()()
    if not isinstance(runtime, ConfiguredAcceptanceRuntime):
        raise ValueError("acceptance_runtime_configuration")
    evaluator = runtime.evaluator()
    if type(evaluator) is not AcceptanceEvaluator:
        raise ValueError("acceptance_runtime_configuration")
    return evaluator


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", required=True)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--certificate", required=True)
    parser.add_argument("--deployment-manifest-digest", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        # Discover the one configured authority before opening any candidate
        # resource. Command arguments are paths only and cannot alter it.
        selected = _configured_evaluator()
        receipt = selected.evaluate_and_publish(
            release_bytes=Path(args.release).read_bytes(), baseline_bytes=Path(args.baseline).read_bytes(),
            policy_bytes=Path(args.policy).read_bytes(), evidence_bytes=Path(args.evidence).read_bytes(),
            certificate_bytes=Path(args.certificate).read_bytes(),
            deployment_manifest_digest=args.deployment_manifest_digest,
        )
    except (OSError, ValueError) as exc:
        _parser().error(str(exc))
    print(receipt.receipt_digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
