"""Regression gate for the non-operational scenario-first C2 harness."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
VECTORS = ROOT / "docs/design/semantic_ingestion/traceability_golden_vectors"
SCENARIO = VECTORS / "scenario-first-v1.json"
DESIGN = ROOT / "docs/design/semantic_ingestion_architecture.md"
REGISTRY = ROOT / "docs/design/semantic_ingestion/traceability_registry/registry-v1.json"


def invoke(*arguments: str) -> None:
    environment = {**os.environ, "PYTHONPATH": str(ROOT / "memorii")}
    subprocess.run([sys.executable, *arguments], cwd=ROOT, env=environment, check=True)


def test_scenario_first_c2_harness_is_deterministic(tmp_path: Path) -> None:
    first_run = tmp_path / "first-run.json"
    second_run = tmp_path / "second-run.json"
    for output in (first_run, second_run):
        invoke(str(VECTORS / "run_scenario_ingress.py"), str(SCENARIO), str(output), "--design", str(DESIGN), "--registry", str(REGISTRY))
    assert first_run.read_bytes() == second_run.read_bytes()

    outputs = []
    for name in ("a", "b"):
        output = tmp_path / f"{name}.json"
        invoke(str(VECTORS / f"elaborate_scenario_{name}.py"), str(SCENARIO), str(first_run), str(DESIGN), str(REGISTRY), str(output))
        outputs.append(output)
    assert outputs[0].read_bytes() == outputs[1].read_bytes()
    assert outputs[0].with_suffix(".structural.spool").read_bytes() == outputs[1].with_suffix(".structural.spool").read_bytes()
    invoke(str(VECTORS / "validate_scenario_manifest.py"), str(outputs[0]), str(outputs[0].with_suffix(".structural.spool")), "--self-test")
