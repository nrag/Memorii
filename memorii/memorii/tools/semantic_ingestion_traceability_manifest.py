"""Registry-expanded immutable structural manifest construction."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import asdict, dataclass
from time import monotonic
from typing import Any

from memorii.core.memory_evolution.ingestion_contracts import (
    CanonicalTypedValueProfileBinding,
    decode_artifact,
    encode_typed_value,
    serialize_artifact,
)
from memorii.tools.semantic_ingestion_structural_ledger import (
    StructuralLedgerError,
    digest_raw_bytes,
    digest_typed_value,
    load_checked_in_frozen_structural_manifest_ledger,
)
from memorii.tools.semantic_ingestion_traceability import NormativeUnit, extract_normative_units
from memorii.tools.semantic_ingestion_traceability_registry import TraceabilityRegistry


class StructuralManifestError(ValueError):
    """Raised when frozen design structure cannot be expanded by the registry."""


_MAX_RAW_AUTHORITY_BYTES = 8 * 1024 * 1024


def _validate_raw_design_bytes(document: bytes) -> None:
    """Bind the manifest to the supplied design artifact, without normalization."""
    if len(document) > _MAX_RAW_AUTHORITY_BYTES:
        raise StructuralManifestError("design exceeds the frozen 8 MiB bound")
    if not document:
        raise StructuralManifestError("design is empty")
    if document.startswith(b"\xef\xbb\xbf"):
        raise StructuralManifestError("design must not contain a UTF-8 BOM")
    if b"\x00" in document:
        raise StructuralManifestError("design must not contain NUL")
    if b"\r" in document:
        raise StructuralManifestError("design must use LF line endings")
    try:
        text = document.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise StructuralManifestError("design is not strict UTF-8") from exc
    if unicodedata.normalize("NFC", text) != text:
        raise StructuralManifestError("design must be NFC-normalized")
    if not document.endswith(b"\n") or document.endswith(b"\n\n"):
        raise StructuralManifestError("design must end in exactly one LF")


_NUMBERED_HEADING = re.compile(r"^(#{2,6})\s+(\d+(?:\.\d+)*)[.\s]")
_SECTION_HEADING = re.compile(r"^##\s+([1-5])\.\s")


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
    body: dict[str, Any]


def _heading_paths(document: bytes, *, check: Callable[[], None] | None = None) -> list[tuple[int, str]]:
    try:
        lines = document.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    except UnicodeDecodeError as exc:
        raise StructuralManifestError("design is not UTF-8") from exc
    paths = []
    for index, line in enumerate(lines):
        if check is not None:
            check()
        if match := _NUMBERED_HEADING.match(line):
            paths.append((index + 1, match.group(2)))
    if not paths:
        raise StructuralManifestError("design contains no numeric headings")
    return paths


def _section_one_to_five_heading_paths(
    document: bytes, *, check: Callable[[], None] | None = None
) -> set[str]:
    """Return only numeric headings physically contained in Sections 1-5."""
    try:
        lines = document.decode("utf-8", "strict").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    except UnicodeDecodeError as exc:
        raise StructuralManifestError("design is not UTF-8") from exc
    active = False
    paths: set[str] = set()
    for line in lines:
        if check is not None:
            check()
        section = _SECTION_HEADING.match(line)
        if section:
            active = True
        elif line.startswith("## "):
            active = False
        if active and (match := _NUMBERED_HEADING.match(line)):
            path = match.group(2)
            if path in paths:
                raise StructuralManifestError(f"design contains duplicate numeric Section 1-5 heading {path}")
            paths.add(path)
    if not paths:
        raise StructuralManifestError("design contains no numeric Section 1-5 headings")
    return paths


def build_structural_manifest(
    *,
    design_bytes: bytes,
    registry: TraceabilityRegistry,
    check: Callable[[], None] | None = None,
) -> StructuralManifest:
    """Derive the frozen 29-field structural body before any authorization.

    This is deliberately not a projection of ``registry.root_digests``: every
    collection and root is reconstructed in the ledger's declared domain and
    collection order.  The previous six-field JSON projection is retained only
    in historical diagnostics and must not be emitted here.
    """
    started = monotonic()
    parse_complete = False

    def effective_check() -> None:
        if check is not None:
            check()
        elapsed = monotonic() - started
        limit = 60 if parse_complete else 30
        if elapsed >= limit:
            raise StructuralManifestError("structural derivation deadline exceeded")

    _validate_raw_design_bytes(design_bytes)
    effective_check()
    if len(registry.canonical_bytes) > _MAX_RAW_AUTHORITY_BYTES:
        raise StructuralManifestError("registry exceeds the frozen 8 MiB bound")
    ledger = load_checked_in_frozen_structural_manifest_ledger()
    units = extract_normative_units(design_bytes, check=effective_check)
    effective_check()
    numbered = _heading_paths(design_bytes, check=effective_check)
    effective_check()
    expected_paths = _section_one_to_five_heading_paths(design_bytes, check=effective_check)
    effective_check()
    parse_complete = True
    registered_paths = {item["heading_path"] for item in registry.source["heading_defaults"]}
    if registered_paths != expected_paths:
        raise StructuralManifestError("registry heading defaults do not exactly cover numeric Sections 1-5 headings")
    defaults = {item["heading_path"]: tuple(item["requirements"]) for item in registry.source["heading_defaults"]}
    bindings = {item["requirement_id"]: item for item in registry.source["requirement_bindings"]}
    mappings: list[StructuralMapping] = []
    rules = registry.source["structural_rules"]
    overrides = {item["invariant_id"]: item for item in registry.source["overrides"]}
    anchors = registry.source["anchor_bindings"]
    rendered = design_bytes.decode("utf-8", "strict")
    for anchor in anchors:
        effective_check()
        if rendered.count(f"[{anchor['anchor']}]") != 1:
            raise StructuralManifestError(f"anchor {anchor['anchor']} is dangling or duplicated")
    for unit in units:
        effective_check()
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
    # Registry source arrays are normative.  Preserve their source order except
    # where the frozen ledger explicitly supplies a different order.
    source = registry.source
    requirement_bindings = sorted(
        source["requirement_bindings"], key=lambda item: int(item["requirement_id"].rsplit("R", 1)[1])
    )
    section_defaults = sorted(
        source["heading_defaults"],
        key=lambda item: next(index for index, (_, path) in enumerate(numbered) if path == item["heading_path"]),
    )
    explicit_anchors = [(item["anchor"], (item["heading_path"],)) for item in source["anchor_bindings"]]
    profile_binding = CanonicalTypedValueProfileBinding(
        "semantic_ingestion_typed_value", 2,
        "9dc8b3d01e3f78ed6a11c7668cbb576b09f48ddf107c5efe441bb8bad234fd7f",
        "NormativeTraceabilityStructuralManifestBody.v1", 1,
        "133ba5b492880d5b773eb75f5a81de0bdf0c09e85cce20d17d7aa076cee7b79b",
    )
    assertion_binding = CanonicalTypedValueProfileBinding(
        profile_binding.profile_id, profile_binding.profile_version, profile_binding.profile_digest,
        "TraceabilityRegistryRoot.assertion_templates.v1", 1,
        "bcec42cc6a2f198fd8a35461f612ee5ca373af14b6e74d023e98cc7cbe70acb6",
    )
    assertion_artifact = serialize_artifact(source["assertion_templates"], assertion_binding)
    body: dict[str, Any] = {
        "grammar_revision": ledger.grammar_revision,
        "design_document_digest": digest_raw_bytes(ledger, "raw_design", design_bytes),
        "registry_source_identity": digest_raw_bytes(ledger, "raw_registry", registry.canonical_bytes),
        "derivation_ledger_schema_id": ledger.schema_id,
        "derivation_ledger_schema_version": ledger.schema_version,
        "derivation_ledger_digest": ledger.digest,
        "derivation_ledger_coordinate": ledger.coordinate,
        "artifact_dag": source["artifact_dag"],
        "artifact_dag_digest": digest_typed_value(ledger, "artifact_dag_root", source["artifact_dag"]),
        "canonical_profile_binding": asdict(profile_binding),
        "requirement_binding_registry_digest": digest_typed_value(ledger, "requirement_binding_root", requirement_bindings),
        "section_defaults": section_defaults,
        "section_default_registry_digest": digest_typed_value(ledger, "section_default_root", section_defaults),
        "structural_mapping_rules": source["structural_rules"],
        "structural_mapping_rule_registry_digest": digest_typed_value(ledger, "structural_mapping_rule_root", source["structural_rules"]),
        "assertion_registry_artifact": assertion_artifact,
        "assertion_registry_digest": decode_artifact(assertion_artifact).artifact_digest,
        "test_evidence_groups": source["test_evidence_groups"],
        "test_evidence_group_registry_digest": digest_typed_value(ledger, "test_evidence_group_root", source["test_evidence_groups"]),
        "report_schemas": source["report_schemas"],
        "report_schema_registry_digest": digest_typed_value(ledger, "report_schema_root", source["report_schemas"]),
        "runner_environment_profiles": source["runner_environment_profiles"],
        "runner_environment_profile_registry_digest": digest_typed_value(ledger, "runner_environment_profile_root", source["runner_environment_profiles"]),
        "units": [asdict(unit) for unit in units],
        "entries": [{**asdict(mapping), "mapping_sources": list(mapping.mapping_sources)} for mapping in mappings],
        "overrides": source["overrides"],
        "override_registry_digest": digest_typed_value(ledger, "override_root", source["overrides"]),
        "explicit_anchor_bindings": explicit_anchors,
        "anchor_binding_registry_digest": digest_typed_value(ledger, "anchor_binding_root", explicit_anchors),
    }
    try:
        ledger.validate_body_shape(body)
    except StructuralLedgerError as exc:
        raise StructuralManifestError(str(exc)) from exc
    # ``canonical_bytes`` is CTV body bytes, not a JSON convenience projection.
    effective_check()
    canonical_bytes = encode_typed_value(body, check=effective_check)
    effective_check()
    digest = digest_typed_value(ledger, "structural_body", body)
    return StructuralManifest(
        body["design_document_digest"], body["registry_source_identity"], body["grammar_revision"],
        tuple(),
        units,
        tuple(mappings),
        canonical_bytes,
        digest,
        body,
    )
