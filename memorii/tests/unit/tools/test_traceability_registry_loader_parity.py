"""Parity checks for the production and independent traceability registry loaders."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from memorii.tools.semantic_ingestion_traceability_checker import (
    TraceabilityCoverageError,
    load_independent_registry_bytes,
    rebuild_structural_manifest_bytes,
)
from memorii.tools.semantic_ingestion_traceability_manifest import build_structural_manifest
from memorii.tools.semantic_ingestion_traceability_registry import (
    RegistryValidationError,
    canonical_document,
    load_registry,
    load_registry_bytes,
)

ROOT = Path(__file__).parents[4]
DESIGN = ROOT / "docs/design/semantic_ingestion_architecture.md"
REGISTRY = ROOT / "docs/design/semantic_ingestion/traceability_registry/registry-v1.json"


def test_registry_loaders_and_structural_rebuild_agree_on_canonical_bytes() -> None:
    raw = REGISTRY.read_bytes()
    registry = load_registry(REGISTRY)
    independent = load_independent_registry_bytes(raw)
    assert independent == registry.source
    manifest = build_structural_manifest(design_bytes=DESIGN.read_bytes(), registry=registry)
    assert rebuild_structural_manifest_bytes(
        design_bytes=DESIGN.read_bytes(), registry=registry, registry_bytes=raw
    ) == manifest.canonical_bytes


@pytest.mark.parametrize(
    "mutation",
    ("trailing_space", "unknown_member", "missing_heading_default", "parser_depth"),
)
def test_registry_loaders_and_structural_rebuild_reject_the_same_invalid_families(
    mutation: str,
) -> None:
    raw = REGISTRY.read_bytes()
    if mutation == "trailing_space":
        mutated = raw + b" "
    elif mutation == "parser_depth":
        mutated = b"[" * 1100 + b"0" + b"]" * 1100 + b"\n"
    else:
        source = json.loads(raw)
        if mutation == "unknown_member":
            source["assertion_templates"][0]["unknown_v1_member"] = "forbidden"
        else:
            source["heading_defaults"].pop()
        mutated = canonical_document(source)
    with pytest.raises(RegistryValidationError):
        load_registry_bytes(mutated)
    with pytest.raises(TraceabilityCoverageError):
        load_independent_registry_bytes(mutated)
    with pytest.raises(TraceabilityCoverageError):
        rebuild_structural_manifest_bytes(
            design_bytes=DESIGN.read_bytes(),
            registry=load_registry(REGISTRY),
            registry_bytes=mutated,
        )
