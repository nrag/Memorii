from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest
from memorii.tools.semantic_ingestion_traceability_checker import (
    TraceabilityCoverageError,
    rebuild_structural_manifest_bytes,
    verify_structural_manifest,
)
from memorii.tools.semantic_ingestion_traceability_manifest import StructuralManifestError, build_structural_manifest
from memorii.tools.semantic_ingestion_traceability_registry import canonical_document, load_registry


def test_structural_manifest_is_deterministic_and_registry_expanded() -> None:
    root = Path(__file__).parents[4]
    design = (root / "docs" / "design" / "semantic_ingestion_architecture.md").read_bytes()
    registry = load_registry(root / "docs" / "design" / "semantic_ingestion" / "traceability_registry" / "registry-v1.json")
    first = build_structural_manifest(design_bytes=design, registry=registry)
    second = build_structural_manifest(design_bytes=design, registry=registry)
    assert first.structural_manifest_digest == second.structural_manifest_digest
    assert len(first.units) == len(second.units)
    assert first.mappings
    # This oracle deliberately does not call either production digest helper.
    assert first.design_document_digest == sha256(
        b"semantic-ingestion-traceability\0" + design
    ).hexdigest()
    assert first.canonical_bytes == rebuild_structural_manifest_bytes(
        design_bytes=design, registry=registry, registry_bytes=(root / "docs" / "design" / "semantic_ingestion" / "traceability_registry" / "registry-v1.json").read_bytes()
    )
    verify_structural_manifest(design_bytes=design, registry=registry, published_manifest=first)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: b"\xef\xbb\xbf" + value,
        lambda value: value[:1] + b"\x00" + value[1:],
        lambda value: value.replace(b"\n", b"\r\n", 1),
        lambda value: b"\xff" + value[1:],
        lambda value: value[:-1],
        lambda value: value + b"\n",
    ],
    ids=("bom", "nul", "cr", "invalid_utf8", "missing_final_lf", "double_final_lf"),
)
def test_both_structural_paths_reject_noncanonical_raw_design_bytes(
    mutation: object,
) -> None:
    root = Path(__file__).parents[4]
    design = (root / "docs" / "design" / "semantic_ingestion_architecture.md").read_bytes()
    registry_path = root / "docs" / "design" / "semantic_ingestion" / "traceability_registry" / "registry-v1.json"
    registry = load_registry(registry_path)
    assert callable(mutation)
    invalid = mutation(design)
    assert isinstance(invalid, bytes)
    with pytest.raises(StructuralManifestError):
        build_structural_manifest(design_bytes=invalid, registry=registry)
    with pytest.raises(TraceabilityCoverageError):
        rebuild_structural_manifest_bytes(
            design_bytes=invalid, registry=registry, registry_bytes=registry_path.read_bytes()
        )


def test_independent_manifest_rejects_published_byte_mutation() -> None:
    root = Path(__file__).parents[4]
    design = (root / "docs" / "design" / "semantic_ingestion_architecture.md").read_bytes()
    registry = load_registry(root / "docs" / "design" / "semantic_ingestion" / "traceability_registry" / "registry-v1.json")
    manifest = build_structural_manifest(design_bytes=design, registry=registry)
    with pytest.raises(TraceabilityCoverageError):
        verify_structural_manifest(design_bytes=design, registry=registry, published_manifest=replace(manifest, canonical_bytes=b"{}"))


@pytest.mark.parametrize("mutation", ["missing", "extra", "parent_fallback"])
def test_both_structural_paths_require_exact_section_heading_paths(tmp_path: Path, mutation: str) -> None:
    root = Path(__file__).parents[4]
    design = (root / "docs" / "design" / "semantic_ingestion_architecture.md").read_bytes()
    registry_path = root / "docs" / "design" / "semantic_ingestion" / "traceability_registry" / "registry-v1.json"
    source = __import__("json").loads(registry_path.read_text())
    heading = b"#### 3.23.4.2.1 scenario-first closure-only canonical typed-value profile v2"
    replacements = {
        "missing": b"#### Appendix scenario-first closure-only canonical typed-value profile v2",
        "extra": b"#### 3.23.4.2.2 scenario-first closure-only canonical typed-value profile v2",
        "parent_fallback": b"#### 3.23.4 scenario-first closure-only canonical typed-value profile v2",
    }
    assert design.count(heading) == 1
    design = design.replace(heading, replacements[mutation], 1)
    mutated = tmp_path / "registry.json"
    mutated.write_bytes(canonical_document(source))
    # Both manifest paths reject rather than inferring a parent default.
    registry = load_registry(mutated)
    expected = "duplicate" if mutation == "parent_fallback" else "exactly cover"
    with pytest.raises(StructuralManifestError, match=expected):
        build_structural_manifest(design_bytes=design, registry=registry)
    with pytest.raises(TraceabilityCoverageError, match=expected):
        rebuild_structural_manifest_bytes(design_bytes=design, registry=registry, registry_bytes=mutated.read_bytes())


def test_both_structural_paths_reject_duplicate_numbered_heading() -> None:
    root = Path(__file__).parents[4]
    design = (root / "docs/design/semantic_ingestion_architecture.md").read_bytes()
    registry_path = root / "docs/design/semantic_ingestion/traceability_registry/registry-v1.json"
    registry = load_registry(registry_path)
    duplicated = design.replace(
        b"## 1. ", b"## 1. \n### 1.1. Duplicate heading\n\n", 1
    )
    with pytest.raises(StructuralManifestError, match="duplicate"):
        build_structural_manifest(design_bytes=duplicated, registry=registry)
    with pytest.raises(TraceabilityCoverageError, match="duplicate"):
        rebuild_structural_manifest_bytes(
            design_bytes=duplicated,
            registry=registry,
            registry_bytes=registry_path.read_bytes(),
        )
