"""L1b equivalence protocol: serial vs xdist loadfile/load suite runs.

Runs the complete unit suite at one revision in four configurations —

1. serial
2. `-n 8 --dist loadfile`
3. `-n 8 --dist load`
4. `-n 4 --dist load` (varied worker count repetition)

— each with CI flag parity (`-W error`, `-p no:cacheprovider`, cwd
`memorii/`), parses per-node outcomes from each run's junitxml, and
requires node-granular equality (outcome + count) across all runs.
Contention policy: no retries — any failure/timeout is recorded as the
result it is.  Writes a JSON verdict beside this script.
"""

from __future__ import annotations

import json
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path("/Users/nandaraghunathan/Code/Memorii/Memorii")
PYTHON = REPO_ROOT / ".venv/bin/python3.12"
EVIDENCE = REPO_ROOT / "docs/work/test-runtime-reduction-2026-09-02/evidence"

CONFIGS = (
    ("serial", ()),
    ("loadfile-n8", ("-n", "8", "--dist", "loadfile")),
    ("load-n8", ("-n", "8", "--dist", "load")),
    ("load-n4", ("-n", "4", "--dist", "load")),
)


def _outcomes(junit_path: Path) -> dict[str, str]:
    root = ET.parse(junit_path).getroot()
    results: dict[str, str] = {}
    for case in root.iter("testcase"):
        nodeid = f"{case.get('file')}::{case.get('name')}"
        children = list(case)
        kinds = {child.tag for child in children}
        if "failure" in kinds or "error" in kinds:
            outcome = "failed"
        elif "skipped" in kinds:
            outcome = "skipped"
        else:
            outcome = "passed"
        results[nodeid] = outcome
    return results


def main() -> None:
    verdict: dict[str, object] = {
        "revision": subprocess.run(
            ("git", "rev-parse", "HEAD"), cwd=REPO_ROOT, capture_output=True, text=True, check=True
        ).stdout.strip(),
        "runs": {},
    }
    outcomes_by_config: dict[str, dict[str, str]] = {}
    for name, extra_args in CONFIGS:
        junit = EVIDENCE / f"xdist-equivalence-{name}.xml"
        command = [
            str(PYTHON),
            "-m",
            "pytest",
            "tests/unit",
            "-W",
            "error",
            "-p",
            "no:cacheprovider",
            "-q",
            f"--junitxml={junit}",
            *extra_args,
        ]
        started = time.perf_counter()
        completed = subprocess.run(command, cwd=REPO_ROOT / "memorii", check=False)
        elapsed = time.perf_counter() - started
        outcomes = _outcomes(junit)
        outcomes_by_config[name] = outcomes
        verdict["runs"][name] = {
            "exit_status": completed.returncode,
            "seconds": round(elapsed, 1),
            "nodes": len(outcomes),
            "passed": sum(1 for value in outcomes.values() if value == "passed"),
            "failed": sum(1 for value in outcomes.values() if value == "failed"),
            "skipped": sum(1 for value in outcomes.values() if value == "skipped"),
        }
        print(json.dumps(verdict["runs"][name], sort_keys=True), flush=True)

    serial = outcomes_by_config["serial"]
    comparisons: dict[str, object] = {}
    for name in ("loadfile-n8", "load-n8", "load-n4"):
        other = outcomes_by_config[name]
        only_serial = sorted(set(serial) - set(other))
        only_other = sorted(set(other) - set(serial))
        outcome_diffs = sorted(
            f"{nodeid}: {serial[nodeid]} vs {other[nodeid]}"
            for nodeid in set(serial) & set(other)
            if serial[nodeid] != other[nodeid]
        )
        comparisons[name] = {
            "node_sets_equal": not only_serial and not only_other,
            "outcomes_equal": not outcome_diffs,
            "only_serial_count": len(only_serial),
            "only_other_count": len(only_other),
            "outcome_differences": outcome_diffs[:20],
        }
    verdict["comparisons"] = comparisons
    verdict["equivalent"] = all(
        entry["node_sets_equal"] and entry["outcomes_equal"]
        for entry in comparisons.values()
    )
    output_path = EVIDENCE / "xdist-equivalence-v1.json"
    output_path.write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"equivalent": verdict["equivalent"]}, sort_keys=True))


if __name__ == "__main__":
    main()
