"""Registry-expanded immutable structural manifest construction."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from hashlib import sha256

from memorii.tools.semantic_ingestion_traceability import NormativeUnit, extract_normative_units
from memorii.tools.semantic_ingestion_traceability_registry import TraceabilityRegistry, canonical_json


class StructuralManifestError(ValueError):
    """Raised when frozen design structure cannot be expanded by the registry."""


_NUMBERED_HEADING = re.compile(r"^(#{2,6})\s+(\d+(?:\.\d+)*)[.\s]")


@dataclass(frozen=True)
class StructuralMapping:
    invariant_id: str
    content_key: str
    requirement_id: str
    assertion_template_id: str
    assertion_version: int
    test_evidence_group: str
    mapping_sources: tuple[str, ...]


@dataclass(frozen=True)
class StructuralManifest:
    design_document_digest: str
    registry_source_identity: str
    grammar_revision: str
    registry_root_digests: tuple[tuple[str, str], ...]
    units: tuple[NormativeUnit, ...]
    mappings: tuple[StructuralMapping, ...]
    canonical_bytes: bytes
    structural_manifest_digest: str


def _heading_paths(document: bytes) -> list[tuple[int, str]]:
    try:
        lines = document.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    except UnicodeDecodeError as exc:
        raise StructuralManifestError("design is not UTF-8") from exc
    paths = [
        (index + 1, match.group(2)) for index, line in enumerate(lines) if (match := _NUMBERED_HEADING.match(line))
    ]
    if not paths:
        raise StructuralManifestError("design contains no numeric headings")
    return paths


def build_structural_manifest(*, design_bytes: bytes, registry: TraceabilityRegistry) -> StructuralManifest:
    """Expand only author-provided defaults and structural ledger self-maps."""
    units = extract_normative_units(design_bytes)
    numbered = _heading_paths(design_bytes)
    defaults = {item["heading_path"]: tuple(item["requirements"]) for item in registry.source["heading_defaults"]}
    bindings = {item["requirement_id"]: item for item in registry.source["requirement_bindings"]}
    mappings: list[StructuralMapping] = []
    rules = registry.source["structural_rules"]
    overrides = {item["invariant_id"]: item for item in registry.source["overrides"]}
    anchors = registry.source["anchor_bindings"]
    rendered = design_bytes.decode("utf-8", "strict")
    for anchor in anchors:
        if rendered.count(f"[{anchor['anchor']}]") != 1:
            raise StructuralManifestError(f"anchor {anchor['anchor']} is dangling or duplicated")
    for unit in units:
        candidates = [path for line, path in numbered if line <= unit.source_start_line]
        if not candidates:
            raise StructuralManifestError("unit has no numeric heading")
        path = candidates[-1]
        requirements = set(defaults.get(path, ()))
        if not requirements:
            raise StructuralManifestError(f"registry has no default for heading {path}")
        sources = [f"heading-default:{path}"]
        for rule in rules:
            if rule["heading_path"] != path:
                continue
            if rule["selector_kind"] == "named_table_rows" and unit.unit_kind == "table_row":
                row = next(
                    (
                        line
                        for line in rendered.splitlines()[unit.source_start_line - 1 : unit.source_end_line]
                        if line.lstrip().startswith("|")
                    ),
                    "",
                )
                values = [cell.strip() for cell in row.strip().strip("|").split("|")]
                for value in rule["selector_values"]:
                    if value in values:
                        requirements.add(value)
                        sources.append(f"rule:{rule['rule_id']}:{value}")
        override = overrides.get(unit.invariant_id)
        if override:
            requirements.update(override["added_requirements"])
            sources.append(f"override:{unit.invariant_id}")
        for requirement in sorted(requirements, key=lambda item: int(item.rsplit("R", 1)[1])):
            binding = bindings[requirement]
            mappings.append(
                StructuralMapping(
                    unit.invariant_id,
                    unit.content_key,
                    requirement,
                    binding["assertion_template_id"],
                    binding["assertion_version"],
                    binding["test_evidence_group"],
                    tuple(sources),
                )
            )
    body = {
        "design_document_digest": sha256(design_bytes).hexdigest(),
        "registry_source_identity": registry.source_identity,
        "grammar_revision": registry.source["grammar_revision"],
        "registry_root_digests": [list(item) for item in sorted(registry.root_digests.items())],
        "units": [asdict(unit) for unit in units],
        "mappings": [{**asdict(mapping), "mapping_sources": list(mapping.mapping_sources)} for mapping in mappings],
    }
    canonical_bytes = canonical_json(body)
    digest = sha256(b"memorii:sia-traceability-structural-manifest:v1\0" + canonical_bytes).hexdigest()
    return StructuralManifest(
        body["design_document_digest"],
        registry.source_identity,
        registry.source["grammar_revision"],
        tuple(sorted(registry.root_digests.items())),
        units,
        tuple(mappings),
        canonical_bytes,
        digest,
    )
