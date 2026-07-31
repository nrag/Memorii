"""End-to-end regression coverage for the bounded scenario-first M1 package."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[4]
VECTORS = ROOT / "docs" / "design" / "semantic_ingestion" / "traceability_golden_vectors"
SCENARIO = VECTORS / "scenario-first-v1.json"
DESIGN = ROOT / "docs" / "design" / "semantic_ingestion_architecture.md"
REGISTRY = ROOT / "docs" / "design" / "semantic_ingestion" / "traceability_registry" / "registry-v1.json"


def _run(*args: str) -> None:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT / "memorii")
    subprocess.run([sys.executable, *args], cwd=ROOT, env=environment, check=True)


def test_scenario_first_milestone1_is_repeatable_and_registered(tmp_path: Path) -> None:
    first, second, a, b = (tmp_path / name for name in ("first.json", "second.json", "a.json", "b.json"))
    runner = str(VECTORS / "run_scenario_ingress.py")
    for output in (first, second):
        _run(runner, str(SCENARIO), str(output), "--design", str(DESIGN), "--registry", str(REGISTRY))
    assert first.read_bytes() == second.read_bytes()
    for script, output in (("elaborate_scenario_a.py", a), ("elaborate_scenario_b.py", b)):
        _run(str(VECTORS / script), str(SCENARIO), str(first), str(DESIGN), str(REGISTRY), str(output))
    assert a.read_bytes() == b.read_bytes()
    assert a.with_suffix(".structural.spool").read_bytes() == b.with_suffix(".structural.spool").read_bytes()
    assert a.with_suffix(".structural.spool").read_bytes()
    _run(str(VECTORS / "validate_scenario_manifest.py"), str(a), str(a.with_suffix(".structural.spool")), "--self-test")
