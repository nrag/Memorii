"""Validate persisted benchmark reports against the current artifact contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from memorii.core.benchmark.artifact_validation import (
    ArtifactValidationError,
    validate_curated_memory_evolution_run,
    validate_memory_evolution_run,
)

_SUITES = {"memory_evolution_v1", "memory_evolution_sim_v1", "memory_evolution_runtime_v1"}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--suite", choices=sorted(_SUITES))
    return parser


def validate_reports(root: Path, *, suite: str | None = None) -> list[str]:
    suites = [suite] if suite else sorted(_SUITES)
    reports = [
        (path.parent, name)
        for name in suites
        for path in sorted(root.glob(f"{name}/**/report.json"))
    ]
    errors: list[str] = []
    for run_dir, suite_name in reports:
        try:
            if suite_name == "memory_evolution_v1":
                validate_curated_memory_evolution_run(run_dir)
            else:
                validate_memory_evolution_run(run_dir, suite=suite_name)
        except (OSError, json.JSONDecodeError, ArtifactValidationError, ValueError) as exc:
            errors.append(f"{run_dir}: {exc}")
    if not reports:
        errors.append(f"no benchmark reports found under {root}")
    return errors


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    errors = validate_reports(args.root, suite=args.suite)
    if errors:
        for error in errors:
            print(error)
        return 1
    print(f"validated benchmark reports under {args.root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
