"""Import-boundary and full-member-output checks for clean-room scenario B."""

from __future__ import annotations

import ast
import base64
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
B = ROOT / "docs/design/semantic_ingestion/traceability_golden_vectors/elaborate_scenario_b.py"


def test_cleanroom_b_has_no_production_or_reference_a_imports() -> None:
    tree = ast.parse(B.read_text(encoding="utf-8"))
    imports = [
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    ] + [
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    ]
    assert all(not name.startswith("memorii") for name in imports)
    assert "elaborate_scenario_a" not in imports


def test_cleanroom_b_registered_closure_exports_18_member_body_and_envelope_bytes() -> None:
    spec = importlib.util.spec_from_file_location("cleanroom_b_test", B)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module.__name__] = module
    spec.loader.exec_module(module)
    build = module._build_registered_closure
    assert callable(build)
    vectors = B.parent
    result = build(
        (ROOT / "docs/design/semantic_ingestion_architecture.md").read_bytes(),
        (ROOT / "docs/design/semantic_ingestion/traceability_registry/registry-v1.json").read_bytes(),
        (vectors / "ctv-binding-authority-v2.json").read_bytes(),
        (vectors / "structural_manifest_derivation_ledger-v1.json").read_bytes(),
    )
    assert isinstance(result, tuple) and len(result) == 2
    generation, closure = result
    assert isinstance(generation, bytes)
    assert isinstance(closure, list)
    assert len(closure) == 19  # 18 members plus the generation envelope.
    members = [item for item in closure[:-1] if isinstance(item, dict)]
    assert len(members) == 18
    assert any("/structural_manifest_derivation_ledger/" in item["coordinate"] for item in members)
    for item in members:
        artifact_bytes = base64.b64decode(item["bytes_base64"], validate=True)
        assert artifact_bytes
        assert item["digest"]
