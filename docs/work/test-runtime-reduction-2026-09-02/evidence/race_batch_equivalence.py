"""L2 adoption gate: batched vs unbatched race-runner outputs.

Runs every race-family element (scenario x root x phase, 200 elements)
twice at the same revision — once through the legacy single-element CLI
(one interpreter per element) and once through `--batch` (one
interpreter for all elements) — then requires the 200 output files to be
byte-identical between the modes.  Writes a JSON verdict beside this
script.  Deterministic content only; no assertion is weakened.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path("/Users/nandaraghunathan/Code/Memorii/Memorii")
PYTHON = REPO_ROOT / ".venv/bin/python3.12"
RUNNER = "tests.fixtures.semantic_ingestion.bootstrap_graph_v3_process_runner"
EVIDENCE = REPO_ROOT / "docs/work/test-runtime-reduction-2026-09-02/evidence"

sys.path.insert(0, str(REPO_ROOT / "memorii"))
from tests.unit.core.semantic_ingestion.bootstrap_graph_production_roots_support import (  # noqa: E402
    GRAPH_SCENARIO_BEHAVIOR,
)

ROOTS = ("direct", "factory", "filesystem", "hermes")


def _elements(base: Path) -> list[dict[str, str]]:
    records = []
    for scenario in GRAPH_SCENARIO_BEHAVIOR:
        for root in ROOTS:
            storage = base / scenario / root
            for phase in ("first", "reopen"):
                records.append(
                    {
                        "storage_root": str(storage),
                        "root": root,
                        "scenario": scenario,
                        "phase": phase,
                        "output": str(base / "outputs" / f"{scenario}-{root}-{phase}.json"),
                    }
                )
    return records


def _env() -> dict[str, str]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = "memorii"
    return environment


def main() -> None:
    started = time.perf_counter()
    work = EVIDENCE / "race-batch-equivalence-work"
    singles = work / "singles"
    batch = work / "batch"
    singles.mkdir(parents=True, exist_ok=True)
    batch.mkdir(parents=True, exist_ok=True)
    elements_single = _elements(singles)
    elements_batch = _elements(batch)
    (singles / "outputs").mkdir(exist_ok=True)
    (batch / "outputs").mkdir(exist_ok=True)

    single_started = time.perf_counter()
    for element in elements_single:
        subprocess.run(
            (
                str(PYTHON),
                "-m",
                RUNNER,
                element["storage_root"],
                element["root"],
                element["scenario"],
                element["phase"],
                element["output"],
            ),
            cwd=REPO_ROOT,
            env=_env(),
            check=True,
            timeout=300,
        )
    single_seconds = time.perf_counter() - single_started

    batch_started = time.perf_counter()
    manifest = batch / "batch-manifest.json"
    manifest.write_text(json.dumps({"elements": elements_batch}), encoding="utf-8")
    subprocess.run(
        (str(PYTHON), "-m", RUNNER, "--batch", str(manifest)),
        cwd=REPO_ROOT,
        env=_env(),
        check=True,
        timeout=180 * len(elements_batch),
    )
    batch_seconds = time.perf_counter() - batch_started

    mismatches: list[dict[str, str]] = []
    for single_element, batch_element in zip(elements_single, elements_batch, strict=True):
        single_bytes = Path(single_element["output"]).read_bytes()
        batch_bytes = Path(batch_element["output"]).read_bytes()
        if single_bytes != batch_bytes:
            mismatches.append(
                {
                    "element": f"{single_element['scenario']}-{single_element['root']}-{single_element['phase']}",
                    "single_sha256": __import__("hashlib").sha256(single_bytes).hexdigest(),
                    "batch_sha256": __import__("hashlib").sha256(batch_bytes).hexdigest(),
                }
            )

    verdict = {
        "revision": subprocess.run(
            ("git", "rev-parse", "HEAD"), cwd=REPO_ROOT, capture_output=True, text=True, check=True
        ).stdout.strip(),
        "elements": len(elements_single),
        "byte_identical": not mismatches,
        "mismatches": mismatches,
        "single_element_mode_seconds": round(single_seconds, 1),
        "batch_mode_seconds": round(batch_seconds, 1),
        "spawn_savings_seconds": round(single_seconds - batch_seconds, 1),
        "total_elapsed_seconds": round(time.perf_counter() - started, 1),
    }
    output_path = EVIDENCE / "race-batch-equivalence-v1.json"
    output_path.write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(verdict, sort_keys=True))


if __name__ == "__main__":
    main()
