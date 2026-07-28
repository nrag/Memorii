from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from memorii.tools.semantic_ingestion_traceability_checker import (
    TraceabilityCoverageError,
    rebuild_structural_manifest_bytes,
    verify_structural_manifest,
)
from memorii.tools.semantic_ingestion_traceability_manifest import build_structural_manifest
from memorii.tools.semantic_ingestion_traceability_registry import load_registry


def test_sia_t03_structural_manifest_is_deterministic_and_registry_expanded() -> None:
    root = Path(__file__).parents[4]
    design = (root / "docs" / "design" / "semantic_ingestion_architecture.md").read_bytes()
    registry = load_registry(root / "docs" / "design" / "semantic_ingestion" / "traceability_registry" / "registry-v1.json")
    first = build_structural_manifest(design_bytes=design, registry=registry)
    second = build_structural_manifest(design_bytes=design, registry=registry)
    assert first.structural_manifest_digest == second.structural_manifest_digest
    assert len(first.units) == len(second.units)
    assert first.mappings
    assert first.canonical_bytes == rebuild_structural_manifest_bytes(design_bytes=design, registry=registry)
    verify_structural_manifest(design_bytes=design, registry=registry, published_manifest=first)


def test_sia_t03_independent_manifest_rejects_published_byte_mutation() -> None:
    root = Path(__file__).parents[4]
    design = (root / "docs" / "design" / "semantic_ingestion_architecture.md").read_bytes()
    registry = load_registry(root / "docs" / "design" / "semantic_ingestion" / "traceability_registry" / "registry-v1.json")
    manifest = build_structural_manifest(design_bytes=design, registry=registry)
    with pytest.raises(TraceabilityCoverageError):
        verify_structural_manifest(design_bytes=design, registry=registry, published_manifest=replace(manifest, canonical_bytes=b"{}"))
