"""Strict loader for the revision-3 semantic-ingestion traceability registry."""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

CANONICAL_PROFILE = "memorii-sia-canonical-json-v1"
_ROOTS = (
    "anchor_bindings", "artifact_dag", "assertion_templates", "design_path", "format", "grammar_revision",
    "heading_defaults", "overrides", "registry_id", "report_schemas", "requirement_bindings",
    "runner_environment_profiles", "structural_rules", "test_evidence_groups",
)
_ARRAY_ROOTS = frozenset(_ROOTS) - {"design_path", "format", "grammar_revision", "registry_id"}
_SPECIAL_ROOTS = frozenset({"report_schemas", "runner_environment_profiles"})


class RegistryValidationError(ValueError):
    """Raised when a registry source package is not the exact frozen artifact."""


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise RegistryValidationError(f"duplicate object key: {key}")
        output[key] = value
    return output


def _validate(value: Any) -> None:
    if isinstance(value, float):
        raise RegistryValidationError("non-integer JSON numbers are forbidden")
    if isinstance(value, str):
        if unicodedata.normalize("NFC", value) != value or any(0xD800 <= ord(char) <= 0xDFFF for char in value):
            raise RegistryValidationError("strings must be NFC Unicode scalars")
    elif isinstance(value, list):
        for item in value:
            _validate(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            _validate(key)
            _validate(item)


def _string(value: str) -> str:
    result: list[str] = []
    for character in value:
        code = ord(character)
        if character == '"':
            result.append('\\"')
        elif character == "\\":
            result.append("\\\\")
        elif code < 0x20:
            result.append(f"\\u{code:04x}")
        else:
            result.append(character)
    return '"' + "".join(result) + '"'


def canonical_json(value: Any) -> bytes:
    """Encode the closed registry profile, preserving all array order."""
    _validate(value)
    if value is None:
        return b"null"
    if value is True:
        return b"true"
    if value is False:
        return b"false"
    if isinstance(value, int):
        return str(value).encode("ascii")
    if isinstance(value, str):
        return _string(value).encode("utf-8")
    if isinstance(value, list):
        return b"[" + b",".join(canonical_json(item) for item in value) + b"]"
    if isinstance(value, dict):
        keys = sorted(value, key=lambda key: tuple(ord(char) for char in key))
        return b"{" + b",".join(canonical_json(key) + b":" + canonical_json(value[key]) for key in keys) + b"}"
    raise RegistryValidationError(f"unsupported JSON value: {type(value).__name__}")


def canonical_document(value: Any) -> bytes:
    return canonical_json(value) + b"\n"


def _id_set(items: list[Any], key: str, root: str) -> set[str]:
    values = [item.get(key) for item in items if isinstance(item, dict)]
    if len(values) != len(items) or any(not isinstance(value, str) for value in values) or len(set(values)) != len(values):
        raise RegistryValidationError(f"{root} must contain unique {key} values")
    return {value for value in values if isinstance(value, str)}


@dataclass(frozen=True)
class TraceabilityRegistry:
    source: dict[str, Any]
    canonical_bytes: bytes
    source_identity: str
    root_digests: dict[str, str]


def _item_digest(domain: bytes, item: dict[str, Any]) -> str:
    """Digest a registered schema/profile without permitting self-reference."""
    return sha256(domain + canonical_document(item)).hexdigest()


def _special_root_digest(domain: bytes, item_digests: list[str]) -> str:
    # The ordered digest tuple is a typed value in the canonical profile.  A
    # JSON array is its canonical representation for this source package.
    return sha256(domain + canonical_document(item_digests)).hexdigest()


def _validate_references(source: dict[str, Any]) -> None:
    bindings = source["requirement_bindings"]
    requirements = _id_set(bindings, "requirement_id", "requirement_bindings")
    if requirements != {f"SIA-R{number:02d}" for number in range(1, 24)}:
        raise RegistryValidationError("requirement bindings must be exactly SIA-R01 through SIA-R23")
    templates = _id_set(source["assertion_templates"], "template_id", "assertion_templates")
    groups = _id_set(source["test_evidence_groups"], "group_id", "test_evidence_groups")
    group_order = [item["group_id"] for item in source["test_evidence_groups"]]
    for binding in bindings:
        if binding["assertion_template_id"] not in templates or binding["test_evidence_group"] not in groups:
            raise RegistryValidationError("requirement binding has an unresolved template or group")
    if [binding["test_evidence_group"] for binding in bindings] != group_order:
        raise RegistryValidationError("test evidence group order must match ordered requirement bindings")
    schema_items = source["report_schemas"]
    profile_items = source["runner_environment_profiles"]
    schema_coordinates = {(item.get("schema_id"), item.get("schema_version")) for item in schema_items if isinstance(item, dict)}
    profile_coordinates = {(item.get("profile_id"), item.get("profile_version")) for item in profile_items if isinstance(item, dict)}
    if len(schema_coordinates) != len(schema_items) or len(profile_coordinates) != len(profile_items):
        raise RegistryValidationError("report schema or runner profile coordinates are duplicate or malformed")
    if any(not isinstance(item.get("schema_document"), dict) or item["schema_document"].get("additionalProperties") is not False for item in schema_items):
        raise RegistryValidationError("report schemas must be closed complete documents")
    if any(not isinstance(item, dict) or set(item) != {
        "canonical_profile_id", "configuration_policy", "dependency_policy", "environment_policy", "import_path_policy",
        "interpreter_policy", "locale_timezone_policy", "network_policy", "plugin_policy", "profile_id", "profile_version",
        "runner_policy", "startup_customization_policy",
    } for item in profile_items):
        raise RegistryValidationError("runner environment profiles must use the closed v1 shape")
    schema_digests = [_item_digest(b"memorii:sia-report-schema:v1\0", item) for item in schema_items]
    profile_digests = [_item_digest(b"memorii:sia-runner-environment-profile:v1\0", item) for item in profile_items]
    for group in source["test_evidence_groups"]:
        if not isinstance(group, dict):
            raise RegistryValidationError("test evidence group is malformed")
        if (group.get("report_schema_id"), group.get("report_schema_version")) not in schema_coordinates or (
            group.get("runner_environment_profile_id"), group.get("runner_environment_profile_version")
        ) not in profile_coordinates:
            raise RegistryValidationError("test evidence group has an unresolved schema or runner profile")
        schema_index = [(item.get("schema_id"), item.get("schema_version")) for item in schema_items].index(
            (group.get("report_schema_id"), group.get("report_schema_version"))
        )
        profile_index = [(item.get("profile_id"), item.get("profile_version")) for item in profile_items].index(
            (group.get("runner_environment_profile_id"), group.get("runner_environment_profile_version"))
        )
        if group.get("expected_report_schema_digest") != schema_digests[schema_index] or group.get("expected_runner_environment_profile_digest") != profile_digests[profile_index]:
            raise RegistryValidationError("test evidence group has a stale specialized item digest")
    headings = source["heading_defaults"]
    paths = _id_set(headings, "heading_path", "heading_defaults")
    if len(paths) != 144 or any(not item["requirements"] for item in headings):
        raise RegistryValidationError("registry must contain exactly 144 nonempty heading defaults")
    if any(requirement not in requirements for item in headings for requirement in item["requirements"]):
        raise RegistryValidationError("heading default refers to an unknown requirement")
    for rule in source["structural_rules"]:
        if rule["heading_path"] not in paths or any(value not in requirements for value in rule["selector_values"]):
            raise RegistryValidationError("structural rule has an unresolved path or requirement")
    if len(source["artifact_dag"]) != 13:
        raise RegistryValidationError("artifact DAG must contain exactly 13 nodes")
    nodes = _id_set(source["artifact_dag"], "node_id", "artifact_dag")
    for node in source["artifact_dag"]:
        dependencies = node["depends_on"]
        if len(dependencies) != len(set(dependencies)) or node["node_id"] in dependencies or any(dep not in nodes for dep in dependencies):
            raise RegistryValidationError("artifact DAG has an invalid dependency")
    source_order = {node["node_id"]: index for index, node in enumerate(source["artifact_dag"])}
    ready = [node["node_id"] for node in source["artifact_dag"] if not node["depends_on"]]
    pending = {node["node_id"]: set(node["depends_on"]) for node in source["artifact_dag"]}
    ordered: list[str] = []
    while ready:
        node = min(ready, key=source_order.__getitem__)
        ready.remove(node)
        ordered.append(node)
        for candidate in source["artifact_dag"]:
            candidate_id = candidate["node_id"]
            if node in pending[candidate_id]:
                pending[candidate_id].remove(node)
                if not pending[candidate_id]:
                    ready.append(candidate_id)
    declared = [node["node_id"] for node in source["artifact_dag"]]
    if ordered != declared:
        raise RegistryValidationError("artifact DAG is not in deterministic Kahn topological order")


def load_registry(path: Path) -> TraceabilityRegistry:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf") or not raw.endswith(b"\n") or raw.endswith(b"\n\n"):
        raise RegistryValidationError("registry must be strict UTF-8 with exactly one final LF and no BOM")
    try:
        source = json.loads(raw[:-1].decode("utf-8"), object_pairs_hook=_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RegistryValidationError("registry is not valid duplicate-free UTF-8 JSON") from exc
    if not isinstance(source, dict) or set(source) != set(_ROOTS):
        raise RegistryValidationError("registry roots are missing or unknown")
    if any(not isinstance(source[root], list) for root in _ARRAY_ROOTS) or any(source[root] is None for root in _ROOTS):
        raise RegistryValidationError("registry roots have an invalid null or non-array value")
    canonical = canonical_document(source)
    if raw != canonical:
        raise RegistryValidationError("registry raw bytes are not canonical")
    _validate_references(source)
    identity = sha256(b"memorii:sia-traceability-source:v1\0" + canonical).hexdigest()
    roots = {
        root: sha256(b"memorii:sia-traceability-registry-root:" + root.encode() + b":v1\0" + canonical_json(source[root])).hexdigest()
        for root in _ARRAY_ROOTS - _SPECIAL_ROOTS
    }
    roots["report_schemas"] = _special_root_digest(
        b"memorii:sia-report-schema-registry:v1\0",
        [_item_digest(b"memorii:sia-report-schema:v1\0", item) for item in source["report_schemas"]],
    )
    roots["runner_environment_profiles"] = _special_root_digest(
        b"memorii:sia-runner-environment-profile-registry:v1\0",
        [_item_digest(b"memorii:sia-runner-environment-profile:v1\0", item) for item in source["runner_environment_profiles"]],
    )
    return TraceabilityRegistry(source, canonical, identity, roots)
