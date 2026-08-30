"""Independent structural and coverage checker (no generator imports)."""

from __future__ import annotations

import ast
import json
import re
import signal
import threading
import unicodedata
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from hashlib import sha256
from time import monotonic
from typing import Any

from memorii.core.memory_evolution.ingestion_contracts import (
    CanonicalTypedValueProfileBinding,
    decode_artifact,
    encode_typed_value,
    serialize_artifact,
)
from memorii.tools.semantic_ingestion_structural_ledger import (
    digest_raw_bytes,
    digest_typed_value,
    load_checked_in_frozen_structural_manifest_ledger,
)


@contextmanager
def _parse_watchdog(seconds: float = 30) -> Any:
    def expired(_signum: int, _frame: object) -> None:
        raise TraceabilityCoverageError("independent structural parser deadline exceeded")

    if threading.current_thread() is not threading.main_thread():
        raise TraceabilityCoverageError(
            "independent structural parser is unavailable outside the main thread"
        )
    previous = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)

_H = re.compile(r"^(#{2,6})\s+(.+?)\s*$")
_L = re.compile(r"^(\s*)(?:[-*+] |\d+[.)] )")
_T = re.compile(r"^\s*\|.*\|\s*$")
_REV = "sia-traceability-v1"
_INDEPENDENT_MAX_RAW_JSON_NESTING = 256
_INDEPENDENT_MAX_RAW_JSON_NUMBER_TOKEN_BYTES = 1024
_INDEPENDENT_SCALAR_METADATA = {
    "format": "memorii.semantic-ingestion.traceability-source.v1",
    "registry_id": "semantic-ingestion-traceability-registry-v1",
    "grammar_revision": "sia-traceability-v1",
    "design_path": "docs/design/semantic_ingestion_architecture.md",
}


class TraceabilityCoverageError(ValueError):
    pass


def _independent_expected_requirement_ids() -> tuple[str, ...]:
    """Reconstruct the closed requirement universe without registry imports."""
    return tuple("SIA-R" + str(number).zfill(2) for number in range(1, 24))


def _independently_validate_raw_registry_complexity(raw: bytes) -> None:
    """Bound decoder-sensitive JSON transport features on the approval path.

    This deliberately repeats the production policy without sharing a parser:
    it is a narrow defense against recursive decoding and integer conversion
    failures, not a general resource-limiting framework.
    """
    depth = 0
    token_width = 0
    quoted = False
    escaped = False
    numeric_token_bytes = b"-+0123456789.eE"
    for byte in raw:
        if quoted:
            if escaped:
                escaped = False
            elif byte == ord("\\"):
                escaped = True
            elif byte == ord('"'):
                quoted = False
            continue
        if byte == ord('"'):
            quoted = True
            token_width = 0
        elif byte in (ord("["), ord("{")):
            depth += 1
            if depth > _INDEPENDENT_MAX_RAW_JSON_NESTING:
                raise TraceabilityCoverageError("registry JSON nesting exceeds the closed transport bound")
            token_width = 0
        elif byte in (ord("]"), ord("}")):
            depth -= 1
            token_width = 0
        elif byte in numeric_token_bytes:
            token_width += 1
            if token_width > _INDEPENDENT_MAX_RAW_JSON_NUMBER_TOKEN_BYTES:
                raise TraceabilityCoverageError("registry JSON numeric token exceeds the closed transport bound")
        else:
            token_width = 0


def _validate_raw_design_bytes(document: bytes) -> None:
    """Independently reject noncanonical design transport before parsing it."""
    if len(document) > 8 * 1024 * 1024:
        raise TraceabilityCoverageError("design exceeds the frozen 8 MiB bound")
    if not document:
        raise TraceabilityCoverageError("design is empty")
    if document.startswith(b"\xef\xbb\xbf"):
        raise TraceabilityCoverageError("design must not contain a UTF-8 BOM")
    if b"\x00" in document:
        raise TraceabilityCoverageError("design must not contain NUL")
    if b"\r" in document:
        raise TraceabilityCoverageError("design must use LF line endings")
    try:
        text = document.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise TraceabilityCoverageError("design bytes must be strict UTF-8") from exc
    if unicodedata.normalize("NFC", text) != text:
        raise TraceabilityCoverageError("design must be NFC-normalized")
    if not document.endswith(b"\n") or document.endswith(b"\n\n"):
        raise TraceabilityCoverageError("design must end in exactly one LF")


_REGISTRY_ROOTS = frozenset(
    {
        "anchor_bindings", "artifact_dag", "assertion_templates", "design_path", "format", "grammar_revision",
        "heading_defaults", "overrides", "registry_id", "report_schemas", "requirement_bindings",
        "runner_environment_profiles", "structural_rules", "test_evidence_groups",
    }
)
_INDEPENDENT_ARRAY_ROOTS = _REGISTRY_ROOTS - {
    "design_path",
    "format",
    "grammar_revision",
    "registry_id",
}
_INDEPENDENT_ORDINARY_ITEM_KEYS = {
    "requirement_bindings": frozenset(
        {"requirement_id", "assertion_template_id", "assertion_version", "test_evidence_group"}
    ),
    "assertion_templates": frozenset(
        {"template_id", "version", "unit_kinds", "acceptance"}
    ),
    "heading_defaults": frozenset({"heading_path", "requirements"}),
    "structural_rules": frozenset(
        {"rule_id", "heading_path", "selector_kind", "selector_values", "effect"}
    ),
    "anchor_bindings": frozenset({"anchor", "heading_path"}),
    "artifact_dag": frozenset({"node_id", "depends_on"}),
    "test_evidence_groups": frozenset(
        {
            "group_id",
            "command",
            "selected_tests",
            "report_schema_id",
            "report_schema_version",
            "expected_report_schema_digest",
            "runner_environment_profile_id",
            "runner_environment_profile_version",
            "expected_runner_environment_profile_digest",
            "runner_requirements",
            "artifact_result_policy",
        }
    ),
}
_INDEPENDENT_UNIT_KINDS = frozenset(
    {
        "heading",
        "paragraph",
        "list",
        "list_item",
        "table",
        "table_row",
        "fence",
        "schema_declaration",
        "schema_field",
        "schema_union_member",
        "code_line",
        "diagram_node",
        "diagram_edge",
    }
)
_INDEPENDENT_DAG_ORDER = (
    "bootstrap_trust_anchor",
    "recovery_trust_roots",
    "recovery_trust_policy",
    "trust_lifecycle_root",
    "design_bytes",
    "registry_source",
    "report_schema_registry",
    "runner_environment_profile_registry",
    "structural_manifest",
    "coverage_root",
    "execution_root",
    "signed_release",
    "active_release_pointer",
)
_INDEPENDENT_REPORT_KEYS = frozenset(
    {
        "schema_id",
        "schema_version",
        "canonical_profile_id",
        "media_type",
        "schema_document",
    }
)
_INDEPENDENT_REPORT_DOCUMENT_KEYS = frozenset(
    {"$schema", "additionalProperties", "properties", "required", "type"}
)
_INDEPENDENT_PROFILE_KEYS = frozenset(
    {
        "canonical_profile_id",
        "configuration_policy",
        "dependency_policy",
        "environment_policy",
        "import_path_policy",
        "interpreter_policy",
        "locale_timezone_policy",
        "network_policy",
        "plugin_policy",
        "profile_id",
        "profile_version",
        "runner_policy",
        "startup_customization_policy",
    }
)


def _registry_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise TraceabilityCoverageError("registry contains a duplicate JSON object key")
        result[key] = value
    return result


def _canonical(value: Any) -> bytes:
    """Independent canonical JSON encoder for the approval path.

    This intentionally does not call the registry loader or its serializer.
    """
    if value is None:
        return b"null"
    if value is True:
        return b"true"
    if value is False:
        return b"false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value).encode("ascii")
    if isinstance(value, str):
        if unicodedata.normalize("NFC", value) != value or any(
            0xD800 <= ord(character) <= 0xDFFF for character in value
        ):
            raise TraceabilityCoverageError(
                "registry string is not NFC Unicode scalar text"
            )
        encoded: list[str] = []
        for character in value:
            scalar = ord(character)
            if character == '"':
                encoded.append('\\"')
            elif character == "\\":
                encoded.append("\\\\")
            elif scalar < 0x20:
                encoded.append(f"\\u{scalar:04x}")
            else:
                encoded.append(character)
        return ('"' + "".join(encoded) + '"').encode("utf-8")
    if isinstance(value, list):
        return b"[" + b",".join(_canonical(item) for item in value) + b"]"
    if isinstance(value, dict):
        return b"{" + b",".join(
            _canonical(key) + b":" + _canonical(value[key]) for key in sorted(value, key=lambda k: tuple(map(ord, k)))
        ) + b"}"
    raise TraceabilityCoverageError("registry has an unsupported JSON value")


def _independently_validate_schema_dialect(
    schema: Any, *, document_root: bool = False
) -> None:
    if not isinstance(schema, dict):
        raise TraceabilityCoverageError("registry report schema node is not an object")
    if "anyOf" in schema:
        choices = schema["anyOf"]
        if (
            set(schema) != {"anyOf"}
            or not isinstance(choices, list)
            or not choices
        ):
            raise TraceabilityCoverageError("registry report anyOf node is malformed")
        for choice in choices:
            _independently_validate_schema_dialect(choice)
        return
    if "const" in schema:
        if set(schema) not in ({"const"}, {"const", "type"}):
            raise TraceabilityCoverageError(
                "registry report const node has unsupported keywords"
            )
        if "type" not in schema:
            return
        declared = schema["type"]
        value = schema["const"]
        compatible = {
            "object": isinstance(value, dict),
            "array": isinstance(value, list),
            "string": isinstance(value, str),
            "integer": isinstance(value, int) and not isinstance(value, bool),
            "null": value is None,
        }
        if declared not in compatible or not compatible[declared]:
            raise TraceabilityCoverageError(
                "registry report const value conflicts with its type"
            )
        return
    declared = schema.get("type")
    if declared not in {"object", "array", "string", "integer", "null"}:
        raise TraceabilityCoverageError("registry report schema type is unsupported")
    if declared == "object":
        allowed_fields = {
            "type",
            "properties",
            "required",
            "additionalProperties",
        }
        if document_root:
            allowed_fields.add("$schema")
        properties = schema.get("properties")
        required = schema.get("required")
        if (
            set(schema) != allowed_fields
            or not isinstance(properties, dict)
            or not all(isinstance(name, str) for name in properties)
            or not isinstance(required, list)
            or not all(isinstance(name, str) for name in required)
            or len(required) != len(set(required))
            or any(name not in properties for name in required)
            or schema.get("additionalProperties") is not False
            or set(required) != set(properties)
        ):
            raise TraceabilityCoverageError(
                "registry report object schema is incomplete or malformed"
            )
        for property_schema in properties.values():
            _independently_validate_schema_dialect(property_schema)
        return
    if declared == "array":
        if set(schema) not in (
            {"type", "items", "minItems"},
            {"type", "items", "minItems", "uniqueItems"},
        ):
            raise TraceabilityCoverageError(
                "registry report array schema has unsupported keywords"
            )
        minimum = schema["minItems"]
        if (
            type(minimum) is not int
            or minimum < 0
            or (
                "uniqueItems" in schema
                and not isinstance(schema["uniqueItems"], bool)
            )
        ):
            raise TraceabilityCoverageError(
                "registry report array schema constraints are malformed"
            )
        _independently_validate_schema_dialect(schema["items"])
        return
    if declared == "string":
        if not set(schema) <= {"type", "minLength", "pattern", "format"}:
            raise TraceabilityCoverageError(
                "registry report string schema has unsupported keywords"
            )
        minimum = schema.get("minLength")
        if minimum is not None and (type(minimum) is not int or minimum < 0):
            raise TraceabilityCoverageError(
                "registry report string minimum is malformed"
            )
        pattern = schema.get("pattern")
        if pattern is not None:
            if not isinstance(pattern, str):
                raise TraceabilityCoverageError(
                    "registry report pattern is malformed"
                )
            try:
                re.compile(pattern)
            except (OverflowError, re.error) as exc:
                raise TraceabilityCoverageError(
                    "registry report pattern is not compilable"
                ) from exc
        format_name = schema.get("format")
        if format_name is not None and format_name != "date-time":
            raise TraceabilityCoverageError("registry report format is unsupported")
        return
    if set(schema) != {"type"}:
        raise TraceabilityCoverageError(
            "registry report scalar schema has unsupported keywords"
        )


def _independently_validate_report_schema(item: Any) -> None:
    if not isinstance(item, dict) or set(item) != _INDEPENDENT_REPORT_KEYS:
        raise TraceabilityCoverageError("registry report schema outer shape is not closed")
    document = item["schema_document"]
    if (
        item["schema_id"] != "memorii.semantic_ingestion.pytest_report"
        or type(item["schema_version"]) is not int
        or item["schema_version"] != 1
        or item["canonical_profile_id"] != "memorii-sia-canonical-json-v1"
        or item["media_type"] != "application/schema+json"
        or not isinstance(document, dict)
        or set(document) != _INDEPENDENT_REPORT_DOCUMENT_KEYS
        or document["$schema"] != "https://json-schema.org/draft/2020-12/schema"
        or document["additionalProperties"] is not False
        or not isinstance(document["properties"], dict)
        or not isinstance(document["required"], list)
        or not all(isinstance(value, str) for value in document["required"])
        or document["type"] != "object"
    ):
        raise TraceabilityCoverageError("registry report schema contract is not frozen v1")
    _independently_validate_schema_dialect(document, document_root=True)


def _independently_validate_runner_profile(item: Any) -> None:
    if not isinstance(item, dict) or set(item) != _INDEPENDENT_PROFILE_KEYS:
        raise TraceabilityCoverageError("registry runner profile outer shape is not closed")
    interpreter = item["interpreter_policy"]
    runner = item["runner_policy"]
    plugin = item["plugin_policy"]
    configuration = item["configuration_policy"]
    dependency = item["dependency_policy"]
    import_path = item["import_path_policy"]
    startup = item["startup_customization_policy"]
    environment = item["environment_policy"]
    locale = item["locale_timezone_policy"]
    network = item["network_policy"]
    if (
        item["profile_id"] != "memorii.semantic_ingestion.runner_environment"
        or type(item["profile_version"]) is not int
        or item["profile_version"] != 1
        or item["canonical_profile_id"] != "memorii-sia-canonical-json-v1"
        or not isinstance(interpreter, dict)
        or set(interpreter)
        != {
            "implementation",
            "minimum_version",
            "maximum_version_exclusive",
            "invocation",
            "executable_sha256",
        }
        or interpreter["implementation"] != "CPython"
        or not isinstance(interpreter["minimum_version"], str)
        or not isinstance(interpreter["maximum_version_exclusive"], str)
        or not isinstance(interpreter["invocation"], list)
        or not all(isinstance(value, str) for value in interpreter["invocation"])
        or interpreter["executable_sha256"] != "independently_observed_required"
        or not isinstance(runner, dict)
        or set(runner)
        != {
            "distribution",
            "minimum_version",
            "maximum_version_exclusive",
            "distribution_tree_sha256",
            "selected_test_policy",
        }
        or runner["distribution"] != "pytest"
        or not isinstance(runner["minimum_version"], str)
        or not isinstance(runner["maximum_version_exclusive"], str)
        or runner["distribution_tree_sha256"] != "independently_observed_required"
        or runner["selected_test_policy"] != "all_collected_no_skip_xfail_deselect"
        or not isinstance(plugin, dict)
        or set(plugin) != {"autoload", "allowed_third_party_plugins", "builtin_plugin_set"}
        or plugin["autoload"] != "disabled"
        or not isinstance(plugin["allowed_third_party_plugins"], list)
        or not all(isinstance(value, str) for value in plugin["allowed_third_party_plugins"])
        or plugin["builtin_plugin_set"] != "bound_by_pytest_distribution_tree_digest"
        or not isinstance(configuration, dict)
        or set(configuration)
        != {"config_discovery", "command_options", "files", "pytest_ini_options"}
        or configuration["config_discovery"] != "exact_only"
        or not isinstance(configuration["command_options"], list)
        or not all(value == "-q" for value in configuration["command_options"])
        or not isinstance(configuration["files"], list)
        or any(
            not isinstance(value, dict)
            or set(value) != {"path", "sha256"}
            or value["path"] != "pyproject.toml"
            or not isinstance(value["sha256"], str)
            for value in configuration["files"]
        )
        or not isinstance(configuration["pytest_ini_options"], dict)
        or set(configuration["pytest_ini_options"])
        != {"testpaths", "pythonpath", "markers"}
        or not isinstance(configuration["pytest_ini_options"]["testpaths"], list)
        or not all(
            value == "tests"
            for value in configuration["pytest_ini_options"]["testpaths"]
        )
        or not isinstance(configuration["pytest_ini_options"]["pythonpath"], list)
        or not all(
            value == "." for value in configuration["pytest_ini_options"]["pythonpath"]
        )
        or not isinstance(configuration["pytest_ini_options"]["markers"], list)
        or not all(
            isinstance(value, str)
            for value in configuration["pytest_ini_options"]["markers"]
        )
        or not isinstance(dependency, dict)
        or set(dependency)
        != {"project_metadata", "lockfile", "installed_distribution_fingerprint"}
        or not isinstance(dependency["project_metadata"], dict)
        or set(dependency["project_metadata"]) != {"path", "sha256"}
        or dependency["project_metadata"]["path"] != "pyproject.toml"
        or not isinstance(dependency["project_metadata"]["sha256"], str)
        or not isinstance(dependency["lockfile"], dict)
        or set(dependency["lockfile"]) != {"path", "state", "state_must_be_observed"}
        or dependency["lockfile"]["path"] is not None
        or dependency["lockfile"]["state"] != "absent"
        or dependency["lockfile"]["state_must_be_observed"] is not True
        or not isinstance(dependency["installed_distribution_fingerprint"], dict)
        or set(dependency["installed_distribution_fingerprint"])
        != {"fields", "ordering", "required"}
        or not isinstance(
            dependency["installed_distribution_fingerprint"]["fields"], list
        )
        or not all(
            isinstance(value, str)
            for value in dependency["installed_distribution_fingerprint"]["fields"]
        )
        or dependency["installed_distribution_fingerprint"]["ordering"]
        != "normalized_name_then_version"
        or dependency["installed_distribution_fingerprint"]["required"] is not True
        or not isinstance(import_path, dict)
        or set(import_path)
        != {"normalized_paths", "outside_root", "pythonpath_environment", "symlinks"}
        or not isinstance(import_path["normalized_paths"], list)
        or not all(
            value == "<implementation-root>" for value in import_path["normalized_paths"]
        )
        or import_path["outside_root"] != "reject"
        or import_path["pythonpath_environment"] != "absent"
        or import_path["symlinks"] != "resolve_then_require_root_containment"
        or not isinstance(startup, dict)
        or set(startup) != {"sitecustomize", "usercustomize"}
        or startup["sitecustomize"] != "absent"
        or startup["usercustomize"] != "absent"
        or not isinstance(environment, dict)
        or set(environment)
        != {"fixed_variables", "dynamic_artifact_coordinate_variables", "other_variables"}
        or not isinstance(environment["fixed_variables"], dict)
        or set(environment["fixed_variables"])
        != {
            "LANG",
            "LC_ALL",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
            "PYTHONNOUSERSITE",
            "TZ",
        }
        or environment["fixed_variables"]["LANG"] != "C.UTF-8"
        or environment["fixed_variables"]["LC_ALL"] != "C.UTF-8"
        or environment["fixed_variables"]["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] != "1"
        or environment["fixed_variables"]["PYTHONNOUSERSITE"] != "1"
        or environment["fixed_variables"]["TZ"] != "UTC"
        or not isinstance(environment["dynamic_artifact_coordinate_variables"], list)
        or not all(
            isinstance(value, str)
            for value in environment["dynamic_artifact_coordinate_variables"]
        )
        or environment["other_variables"] != "removed"
        or not isinstance(locale, dict)
        or set(locale) != {"lang", "lc_all", "timezone"}
        or locale["lang"] != "C.UTF-8"
        or locale["lc_all"] != "C.UTF-8"
        or locale["timezone"] != "UTC"
        or not isinstance(network, dict)
        or set(network)
        != {"enforcement", "outbound_and_listen", "enforcement_observation_digest"}
        or network["enforcement"] != "denied"
        or network["outbound_and_listen"] != "forbidden"
        or network["enforcement_observation_digest"] != "required"
    ):
        raise TraceabilityCoverageError("registry runner profile policy is not frozen v1")


def _load_independent_registry_bytes(raw: bytes) -> dict[str, Any]:
    """Load the approval input directly from raw canonical registry bytes."""
    try:
        _independently_validate_raw_registry_complexity(raw)
        source = json.loads(raw.decode("utf-8"), object_pairs_hook=_registry_pairs)
        if not isinstance(source, dict) or set(source) != _REGISTRY_ROOTS or raw != _canonical(source) + b"\n":
            raise TraceabilityCoverageError("registry bytes are not the complete canonical source")
        if any(not isinstance(source[root], list) for root in _INDEPENDENT_ARRAY_ROOTS):
            raise TraceabilityCoverageError(
                "registry non-scalar roots must all be arrays"
            )
        if any(
            source[key] != expected
            for key, expected in _INDEPENDENT_SCALAR_METADATA.items()
        ):
            raise TraceabilityCoverageError("registry scalar metadata differs from frozen v1")
    except TraceabilityCoverageError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise TraceabilityCoverageError("registry bytes are not strict JSON") from exc
    expected_requirement_ids = _independent_expected_requirement_ids()
    requirements = set(expected_requirement_ids)
    for root, expected_keys in _INDEPENDENT_ORDINARY_ITEM_KEYS.items():
        if any(not isinstance(item, dict) or set(item) != expected_keys for item in source[root]):
            raise TraceabilityCoverageError(f"registry {root} member shape is not closed")
    if source["overrides"]:
        raise TraceabilityCoverageError("registry v1 overrides must be exactly empty")
    bindings = source["requirement_bindings"]
    defaults = source["heading_defaults"]
    groups = source["test_evidence_groups"]
    templates = source["assertion_templates"]
    if not all(isinstance(item, dict) for item in bindings + defaults + groups + templates):
        raise TraceabilityCoverageError("registry collections contain an invalid item")
    expected_binding_ids = expected_requirement_ids
    if any(not isinstance(item["requirement_id"], str) for item in bindings):
        raise TraceabilityCoverageError("registry requirement binding IDs are malformed")
    binding_ids = {item["requirement_id"] for item in bindings}
    if (
        binding_ids != requirements
        or len(bindings) != 23
        or tuple(item["requirement_id"] for item in bindings) != expected_binding_ids
        or any(
            not isinstance(item["assertion_template_id"], str)
            or type(item["assertion_version"]) is not int
            or item["assertion_version"] < 1
            or not isinstance(item["test_evidence_group"], str)
            for item in bindings
        )
    ):
        raise TraceabilityCoverageError("registry does not bind the complete requirement set")
    if any(
        not isinstance(item["heading_path"], str)
        or not isinstance(item["requirements"], list)
        or not all(isinstance(requirement, str) for requirement in item["requirements"])
        for item in defaults
    ):
        raise TraceabilityCoverageError("registry heading defaults use invalid field types")
    paths = [item["heading_path"] for item in defaults]
    # This independent loader deliberately repeats the closed 192-heading
    # contract rather than importing the production-side registry validation.
    if len(defaults) != 192 or len(set(paths)) != 192 or any(not item.get("requirements") for item in defaults):
        raise TraceabilityCoverageError("registry does not contain exactly 192 nonempty unique defaults")
    if any(
        not isinstance(item.get("requirements"), list)
        or len(item["requirements"]) != len(set(item["requirements"]))
        or item["requirements"] != sorted(item["requirements"], key=lambda value: int(str(value).rsplit("R", 1)[1]))
        or any(value not in requirements for value in item["requirements"])
        for item in defaults
    ):
        raise TraceabilityCoverageError("registry heading requirements are unknown, duplicate, or unordered")
    template_coordinates = [(item["template_id"], item["version"]) for item in templates]
    if (
        any(
            not isinstance(item["template_id"], str)
            or type(item["version"]) is not int
            or item["version"] < 1
            or not isinstance(item["unit_kinds"], list)
            or not item["unit_kinds"]
            or not all(
                isinstance(kind, str) and kind in _INDEPENDENT_UNIT_KINDS
                for kind in item["unit_kinds"]
            )
            or len(item["unit_kinds"]) != len(set(item["unit_kinds"]))
            or not isinstance(item["acceptance"], str)
            for item in templates
        )
        or len(template_coordinates) != len(set(template_coordinates))
        or [item["template_id"] for item in templates]
        != sorted((item["template_id"] for item in templates), key=lambda value: value.encode("utf-8"))
    ):
        raise TraceabilityCoverageError("registry assertion templates are malformed, duplicate, or unordered")
    if any(not isinstance(item["group_id"], str) for item in groups):
        raise TraceabilityCoverageError("registry test evidence group IDs are malformed")
    group_ids = {item["group_id"] for item in groups}
    group_order = [item["group_id"] for item in groups]
    if (
        len(group_ids) != 23
        or any(
            (item["assertion_template_id"], item["assertion_version"])
            not in template_coordinates
            or item["test_evidence_group"] not in group_ids
            for item in bindings
        )
    ):
        raise TraceabilityCoverageError("registry has an unresolved assertion or evidence group")
    if [item["test_evidence_group"] for item in bindings] != group_order:
        raise TraceabilityCoverageError("registry evidence group order differs from ordered bindings")
    rules = source["structural_rules"]
    anchors = source["anchor_bindings"]
    if (
        not all(isinstance(item, dict) for item in rules + anchors)
        or any(
            not isinstance(item["rule_id"], str)
            or not isinstance(item["heading_path"], str)
            or item["selector_kind"] != "named_table_rows"
            or not isinstance(item["selector_values"], list)
            or not all(isinstance(value, str) for value in item["selector_values"])
            or item["effect"] != "add_matching_ledger_requirement"
            for item in rules
        )
        or any(
            not isinstance(item["anchor"], str)
            or not isinstance(item["heading_path"], str)
            for item in anchors
        )
        or len({item.get("rule_id") for item in rules}) != len(rules)
        or len({item.get("anchor") for item in anchors}) != len(anchors)
    ):
        raise TraceabilityCoverageError("registry structural rules or anchors are duplicate or malformed")
    schemas = source["report_schemas"]
    profiles = source["runner_environment_profiles"]
    if not isinstance(schemas, list) or not schemas or not isinstance(profiles, list) or not profiles:
        raise TraceabilityCoverageError("registry schema/profile collections must be nonempty arrays")
    for item in schemas:
        _independently_validate_report_schema(item)
    for item in profiles:
        _independently_validate_runner_profile(item)
    schema_coordinates = [(item["schema_id"], item["schema_version"]) for item in schemas]
    profile_coordinates = [(item["profile_id"], item["profile_version"]) for item in profiles]
    if len(set(schema_coordinates)) != len(schemas) or len(set(profile_coordinates)) != len(profiles):
        raise TraceabilityCoverageError("registry schema/profile coordinates are duplicate")
    schema_digests = [sha256(b"memorii:sia-report-schema:v1\0" + _canonical(item) + b"\n").hexdigest() for item in schemas]
    profile_digests = [sha256(b"memorii:sia-runner-environment-profile:v1\0" + _canonical(item) + b"\n").hexdigest() for item in profiles]
    for group in groups:
        command = group["command"]
        selected_tests = group["selected_tests"]
        runner_requirements = group["runner_requirements"]
        artifact_policy = group["artifact_result_policy"]
        if (
            not isinstance(command, dict)
            or set(command) != {"command_id", "argv", "working_directory"}
            or not isinstance(command["command_id"], str)
            or not isinstance(command["argv"], list)
            or not command["argv"]
            or not all(isinstance(value, str) for value in command["argv"])
            or command["working_directory"] != "memorii"
            or not isinstance(selected_tests, list)
            or not selected_tests
            or any(
                not isinstance(test, dict)
                or set(test)
                != {"test_id", "pytest_node_id", "implementation_status", "behavioral_assertion"}
                or not all(
                    isinstance(test[key], str)
                    for key in {
                        "test_id",
                        "pytest_node_id",
                        "implementation_status",
                        "behavioral_assertion",
                    }
                )
                or test["implementation_status"]
                not in {"repository_evidenced", "required_not_yet_evidenced"}
                for test in selected_tests
            )
            or not isinstance(runner_requirements, dict)
            or set(runner_requirements)
            != {
                "runner_kind",
                "minimum_python_version",
                "minimum_pytest_version",
                "network_policy",
                "environment_policy",
                "selection_policy",
                "exit_policy",
            }
            or not all(isinstance(value, str) for value in runner_requirements.values())
            or runner_requirements["runner_kind"] != "cpython_pytest"
            or runner_requirements["network_policy"] != "denied"
            or runner_requirements["environment_policy"] != "clean_allowlisted"
            or runner_requirements["selection_policy"]
            != "all_selected_collected_no_skip_xfail_deselect"
            or runner_requirements["exit_policy"] != "zero_and_every_selected_test_passed"
            or not isinstance(artifact_policy, dict)
            or set(artifact_policy)
            != {"report_bytes", "result_bytes", "stdout_stderr", "stream_sharing", "report_binding"}
            or artifact_policy["report_bytes"] != "required_immutable_content_addressed"
            or artifact_policy["result_bytes"] != "required_immutable_content_addressed"
            or artifact_policy["stdout_stderr"] != "content_addressed_or_explicit_empty"
            or artifact_policy["stream_sharing"]
            not in {"forbidden", "exact_bytes_all_owners_explicitly_permit"}
            or artifact_policy["report_binding"]
            != "exact_command_selection_runner_roots_and_results"
            or group["report_schema_id"] != "memorii.semantic_ingestion.pytest_report"
            or group["report_schema_version"] != 1
            or not isinstance(group["expected_report_schema_digest"], str)
            or group["runner_environment_profile_id"]
            != "memorii.semantic_ingestion.runner_environment"
            or group["runner_environment_profile_version"] != 1
            or not isinstance(group["expected_runner_environment_profile_digest"], str)
        ):
            raise TraceabilityCoverageError("registry evidence group uses an invalid closed v1 shape")
        schema_coordinate = (group.get("report_schema_id"), group.get("report_schema_version"))
        profile_coordinate = (group.get("runner_environment_profile_id"), group.get("runner_environment_profile_version"))
        if (
            not group.get("selected_tests")
            or schema_coordinate not in schema_coordinates
            or profile_coordinate not in profile_coordinates
            or group.get("expected_report_schema_digest") != schema_digests[schema_coordinates.index(schema_coordinate)]
            or group.get("expected_runner_environment_profile_digest") != profile_digests[profile_coordinates.index(profile_coordinate)]
        ):
            raise TraceabilityCoverageError("registry evidence group is incomplete")
    nodes = source["artifact_dag"]
    if any(not isinstance(item["node_id"], str) for item in nodes):
        raise TraceabilityCoverageError("registry artifact DAG node IDs are malformed")
    node_ids = [item["node_id"] for item in nodes]
    if len(nodes) != 13 or len(node_ids) != 13 or len(set(node_ids)) != 13:
        raise TraceabilityCoverageError("registry artifact DAG is incomplete")
    node_id_set = set(node_ids)
    if any(
        not isinstance(node.get("depends_on"), list)
        or not all(isinstance(dependency, str) for dependency in node["depends_on"])
        or len(node["depends_on"]) != len(set(node["depends_on"]))
        or node["node_id"] in node["depends_on"]
        or any(dependency not in node_id_set for dependency in node["depends_on"])
        for node in nodes
    ):
        raise TraceabilityCoverageError("registry artifact DAG has an invalid dependency")
    if tuple(node_ids) != _INDEPENDENT_DAG_ORDER:
        raise TraceabilityCoverageError("registry artifact DAG is not in the closed v1 source order")
    source_order = {node_id: index for index, node_id in enumerate(node_ids)}
    pending = {node["node_id"]: set(node["depends_on"]) for node in nodes}
    ready = [node["node_id"] for node in nodes if not node["depends_on"]]
    ordered: list[str] = []
    while ready:
        node_id = min(ready, key=source_order.__getitem__)
        ready.remove(node_id)
        ordered.append(node_id)
        for candidate in nodes:
            candidate_id = candidate["node_id"]
            if node_id in pending[candidate_id]:
                pending[candidate_id].remove(node_id)
                if not pending[candidate_id]:
                    ready.append(candidate_id)
    if ordered != node_ids:
        raise TraceabilityCoverageError("registry artifact DAG is not in deterministic Kahn topological order")
    return source


def load_independent_registry_bytes(raw: bytes) -> dict[str, Any]:
    """Load the approval input, normalizing parser and canonicalizer failures."""
    if len(raw) > 8 * 1024 * 1024:
        raise TraceabilityCoverageError("registry exceeds the frozen 8 MiB bound")
    try:
        return _load_independent_registry_bytes(raw)
    except TraceabilityCoverageError:
        raise
    except (RecursionError, ValueError) as exc:
        raise TraceabilityCoverageError("registry bytes are not a supported closed source") from exc


@dataclass(frozen=True)
class _Unit:
    invariant_id: str
    content_key: str
    duplicate_occurrence: int
    unit_kind: str
    parent_invariant_id: str | None
    heading_path_hash: str
    source_start_line: int
    source_end_line: int
    canonical_payload_digest: str


def _d(v: object) -> str:
    return sha256(
        b"semantic-ingestion-traceability\0"
        + json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _p(v: list[str]) -> str:
    return "\n".join(unicodedata.normalize("NFC", x.rstrip(" \t")) for x in v)


def _schema(body: list[str]) -> list[tuple[str, str, int]]:
    try:
        tree = ast.parse("\n".join(body))
    except SyntaxError as exc:
        raise TraceabilityCoverageError("unclassifiable Python schema fence") from exc

    def leaves(v: ast.expr) -> tuple[ast.expr, ...]:
        return leaves(v.left) + leaves(v.right) if isinstance(v, ast.BinOp) and isinstance(v.op, ast.BitOr) else (v,)

    output = []
    seen = set()
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            output.append(
                ("schema_declaration", ast.get_source_segment("\n".join(body), node) or node.name, node.lineno - 1)
            )
            seen.add(node.lineno - 1)
            for m in node.body:
                if isinstance(m, ast.AnnAssign) and isinstance(m.target, ast.Name):
                    output.append(
                        ("schema_field", ast.get_source_segment("\n".join(body), m) or m.target.id, m.lineno - 1)
                    )
                    seen.add(m.lineno - 1)
                    if "|" in ast.unparse(m.annotation) or "Union[" in ast.unparse(m.annotation):
                        output.extend(
                            ("schema_union_member", ast.unparse(x), m.lineno - 1) for x in leaves(m.annotation)
                        )
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            output.append(("schema_declaration", ast.get_source_segment("\n".join(body), node) or "", node.lineno - 1))
            seen.add(node.lineno - 1)
            value = getattr(node, "value", None)
            if value is not None and ("|" in ast.unparse(value) or "Union[" in ast.unparse(value)):
                output.extend(("schema_union_member", ast.unparse(x), node.lineno - 1) for x in leaves(value))
    return output + [("code_line", x, i) for i, x in enumerate(body) if x.strip() and i not in seen]


def _independent_extract(
    data: bytes, *, check: Callable[[], None] | None = None
) -> tuple[_Unit, ...]:
    _validate_raw_design_bytes(data)
    try:
        all_lines = data.decode("utf-8", "strict").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    except UnicodeDecodeError as exc:
        raise TraceabilityCoverageError("design bytes must be valid UTF-8") from exc
    starts = [i for i, x in enumerate(all_lines) if x.startswith("## 1.")]
    if len(starts) != 1:
        raise TraceabilityCoverageError("design must contain exactly one Section 1 heading")
    five = next((i for i in range(starts[0], len(all_lines)) if all_lines[i].startswith("## 5.")), None)
    if five is None:
        raise TraceabilityCoverageError("design must contain a Section 5 heading")
    stop = next((i for i in range(five + 1, len(all_lines)) if all_lines[i].startswith("## ")), len(all_lines))
    lines = all_lines[starts[0] : stop]
    offset = starts[0] + 1
    raw = []
    # Do not use the hash of a heading path as an occurrence key: repeated
    # headings are legal and children must bind to the emitted parent instance.
    stack: list[tuple[int, str, int]] = []
    i = 0
    while i < len(lines):
        if check is not None:
            check()
        x = lines[i]
        if not x.strip():
            i += 1
            continue
        m = _H.match(x)
        if m:
            level, title = len(m.group(1)), m.group(2)
            while stack and stack[-1][0] >= level:
                stack.pop()
            path = _d({"heading_path": tuple(q[1] for q in stack) + (title,)})
            heading_index = len(raw)
            raw.append(("heading", title, f"@{stack[-1][2]}" if stack else None, path, offset + i, offset + i, ()))
            stack.append((level, title, heading_index))
            i += 1
            continue
        parent = f"@{stack[-1][2]}" if stack else None
        path = _d({"heading_path": tuple(q[1] for q in stack)}) if stack else _d({"heading_path": ()})
        if x.startswith("```"):
            begin = i
            lang = x[3:].strip().lower()
            i += 1
            body = []
            while i < len(lines) and not lines[i].startswith("```"):
                body.append(lines[i])
                i += 1
            if i == len(lines):
                raise TraceabilityCoverageError("unclosed fence")
            fence_index = len(raw)
            raw.append(("fence", f"{lang}\n{_p(body)}", parent, path, offset + begin, offset + i, ()))
            children = (
                _schema(body)
                if lang in {"python", "py"}
                else [
                    ("diagram_edge" if "-->" in z.strip() or "---" in z.strip() else "diagram_node", z.strip(), j)
                    for j, z in enumerate(body)
                    if z.strip()
                ]
                if lang in {"mermaid", "diagram"}
                else [("code_line", z, j) for j, z in enumerate(body) if z.strip()]
            )
            raw.extend((k, v, f"@{fence_index}", path, offset + begin + j + 1, offset + begin + j + 1, ()) for k, v, j in children)
            i += 1
            continue
        if _T.match(x):
            begin = i
            rows = []
            while i < len(lines) and _T.match(lines[i]):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if len(cells) < 2:
                    raise TraceabilityCoverageError("malformed table")
                rows.append(lines[i])
                i += 1
            child_rows = [
                r for r in rows if not all(c and set(c) <= {"-", ":"} for c in r.strip().strip("|").split("|"))
            ]
            visible_rows = [
                r
                for r in rows
                if not all(c.strip() and set(c.strip()) <= {"-", ":"} for c in r.strip().strip("|").split("|"))
            ]
            table_index = len(raw)
            raw.append(
                (
                    "table",
                    _p(rows),
                    parent,
                    path,
                    offset + begin,
                    offset + i - 1,
                    tuple(_d({"row": _p([r])}) for r in child_rows),
                )
            )
            raw.extend(
                ("table_row", r, f"@{table_index}", path, offset + begin + j, offset + begin + j, ())
                for j, r in enumerate(rows)
                if r in visible_rows
            )
            continue
        if _L.match(x):
            begin = i
            items = []
            while i < len(lines) and (not lines[i].strip() or _L.match(lines[i]) or lines[i].startswith((" ", "\t"))):
                if _L.match(lines[i]):
                    s = i
                    item = [lines[i]]
                    i += 1
                    while i < len(lines) and lines[i].startswith((" ", "\t")) and not _L.match(lines[i]):
                        item.append(lines[i])
                        i += 1
                    items.append((s, item))
                else:
                    i += 1
            list_index = len(raw)
            raw.append(
                (
                    "list",
                    _p([v[0] for _, v in items]),
                    parent,
                    path,
                    offset + begin,
                    offset + i - 1,
                    tuple(_d({"item": _p(v)}) for _, v in items),
                )
            )
            raw.extend(("list_item", _p(v), f"@{list_index}", path, offset + s, offset + s + len(v) - 1, ()) for s, v in items)
            continue
        if x.startswith((">", "---", "***")):
            raise TraceabilityCoverageError("unknown Markdown block")
        begin = i
        p = []
        while (
            i < len(lines)
            and lines[i].strip()
            and not _H.match(lines[i])
            and not lines[i].startswith("```")
            and not _T.match(lines[i])
            and not _L.match(lines[i])
        ):
            p.append(lines[i])
            i += 1
        raw.append(("paragraph", _p(p), parent, path, offset + begin, offset + i - 1, ()))
    seen = {}
    provisional = []
    for k, v, parent, path, b, e, ch in raw:
        if check is not None:
            check()
        key = _d({"grammar_revision": _REV, "kind": k, "payload": v, "children": ch})
        n = seen.get(key, 0)
        seen[key] = n + 1
        provisional.append((f"SIA-N-{key}-{n}", key, n, k, parent, path, b, e, _d(v)))
    out = []
    for invariant_id, key, occurrence, kind, parent, path, begin, end, payload_digest in provisional:
        if check is not None:
            check()
        if parent is None:
            resolved_parent = None
        elif parent.startswith("@"):
            resolved_parent = provisional[int(parent[1:])][0]
        else:
            raise TraceabilityCoverageError("unit parent must reference an emitted raw occurrence")
        out.append(_Unit(invariant_id, key, occurrence, kind, resolved_parent, path, begin, end, payload_digest))
    return tuple(out)


def _shape(value: Any) -> tuple[Any, ...]:
    return tuple(getattr(value, n) for n in _Unit.__dataclass_fields__)


def verify_traceability_coverage(
    *,
    design_bytes: bytes,
    published_units: tuple[Any, ...],
    mappings: tuple[Any, ...],
    requirements_to_owners: dict[str, str],
) -> None:
    if tuple(_shape(x) for x in _independent_extract(design_bytes)) != tuple(_shape(x) for x in published_units):
        raise TraceabilityCoverageError("published structural units do not equal independent extraction")
    if not requirements_to_owners:
        raise TraceabilityCoverageError("requirement ledger cannot be empty")
    keys = {(x.invariant_id, x.content_key) for x in published_units}
    invariant_ids = {x.invariant_id for x in published_units}
    if any(x.parent_invariant_id is not None and x.parent_invariant_id not in invariant_ids for x in published_units):
        raise TraceabilityCoverageError("published unit has an unresolved structural parent")
    covered = {x.invariant_id: set() for x in published_units}
    seen = set()
    for m in mappings:
        if (m.invariant_id, m.content_key) not in keys:
            raise TraceabilityCoverageError("mapping refers to an orphaned unit or stale content key")
        if (m.invariant_id, m.requirement_id) in seen:
            raise TraceabilityCoverageError("duplicate unit-to-requirement mapping")
        seen.add((m.invariant_id, m.requirement_id))
        if requirements_to_owners.get(m.requirement_id) != m.owner:
            raise TraceabilityCoverageError("mapping owner differs from the requirement ledger")
        if m.assertion_version < 1 or not m.assertion_id or not m.test_evidence_group:
            raise TraceabilityCoverageError("mapping has an invalid assertion binding")
        covered[m.invariant_id].add(m.requirement_id)
    if any(not v for v in covered.values()):
        raise TraceabilityCoverageError("every structural unit requires explicit requirement coverage")


def rebuild_structural_manifest_bytes(
    *,
    design_bytes: bytes,
    registry: Any,
    registry_bytes: bytes | None = None,
    parse_check: Callable[[], None] | None = None,
    reconstruction_check: Callable[[], None] | None = None,
) -> bytes:
    """Independently expand the registry and return the canonical manifest body.

    This deliberately accepts only canonical source artifacts and does not
    import the generator's parser, models, or mapping implementation.
    """
    if threading.current_thread() is not threading.main_thread():
        raise TraceabilityCoverageError(
            "independent structural parser is unavailable outside the main thread"
        )
    # Approval callers must supply the canonical raw artifact.  The optional
    # object parameter only preserves the legacy non-approval helper surface.
    started = monotonic()

    def effective_parse_check() -> None:
        if parse_check is not None:
            parse_check()
        if monotonic() - started >= 30:
            raise TraceabilityCoverageError("independent structural parser deadline exceeded")

    def effective_reconstruction_check() -> None:
        if reconstruction_check is not None:
            reconstruction_check()
        if monotonic() - started >= 60:
            raise TraceabilityCoverageError("independent structural reconstruction deadline exceeded")

    _validate_raw_design_bytes(design_bytes)
    effective_parse_check()
    with _parse_watchdog():
        source = load_independent_registry_bytes(registry_bytes) if registry_bytes is not None else registry.source
    effective_parse_check()
    units = _independent_extract(design_bytes, check=effective_parse_check)
    effective_reconstruction_check()
    try:
        lines = design_bytes.decode("utf-8", "strict").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    except UnicodeDecodeError as exc:
        raise TraceabilityCoverageError("design bytes must be valid UTF-8") from exc
    numbered = []
    active_section = False
    section_paths: set[str] = set()
    for line_number, line in enumerate(lines, start=1):
        effective_reconstruction_check()
        if re.match(r"^##\s+[1-5]\.\s", line):
            active_section = True
        elif line.startswith("## "):
            active_section = False
        match = re.match(r"^(#{2,6})\s+(\d+(?:\.\d+)*)[.\s]", line)
        if match:
            numbered.append((line_number, match.group(2)))
            if active_section:
                path = match.group(2)
                if path in section_paths:
                    raise TraceabilityCoverageError(
                        f"design contains duplicate numeric Section 1-5 heading {path}"
                    )
                section_paths.add(path)
    defaults = {item["heading_path"]: tuple(item["requirements"]) for item in source["heading_defaults"]}
    if set(defaults) != section_paths:
        raise TraceabilityCoverageError("registry heading defaults do not exactly cover numeric Sections 1-5 headings")
    bindings = {item["requirement_id"]: item for item in source["requirement_bindings"]}
    overrides = {item["invariant_id"]: item for item in source["overrides"]}
    rendered = design_bytes.decode("utf-8", "strict")
    for anchor in source["anchor_bindings"]:
        effective_reconstruction_check()
        if rendered.count(f"[{anchor['anchor']}]") != 1:
            raise TraceabilityCoverageError("registry anchor is dangling or duplicated")
    mappings: list[dict[str, Any]] = []
    for unit in units:
        effective_reconstruction_check()
        candidates = [path for line, path in numbered if line <= unit.source_start_line]
        if not candidates:
            raise TraceabilityCoverageError("unit has no numeric heading")
        heading_path = candidates[-1]
        requirements = set(defaults.get(heading_path, ()))
        if not requirements:
            raise TraceabilityCoverageError("unit has no registered heading default")
        sources = [f"heading-default:{heading_path}"]
        for rule in source["structural_rules"]:
            if rule["heading_path"] != heading_path or rule["selector_kind"] != "named_table_rows" or unit.unit_kind != "table_row":
                continue
            row = next((line for line in lines[unit.source_start_line - 1 : unit.source_end_line] if line.lstrip().startswith("|")), "")
            cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
            for requirement in rule["selector_values"]:
                if requirement in cells:
                    requirements.add(requirement)
                    sources.append(f"rule:{rule['rule_id']}:{requirement}")
        override = overrides.get(unit.invariant_id)
        if override:
            requirements.update(override["added_requirements"])
            sources.append(f"override:{unit.invariant_id}")
        for requirement in sorted(requirements, key=lambda item: int(item.rsplit("R", 1)[1])):
            binding = bindings.get(requirement)
            if binding is None:
                raise TraceabilityCoverageError("mapping refers to an unregistered requirement")
            mappings.append({
                "invariant_id": unit.invariant_id,
                "content_key": unit.content_key,
                "requirement_id": requirement,
                "assertion_template_id": binding["assertion_template_id"],
                "assertion_version": binding["assertion_version"],
                "test_evidence_group": binding["test_evidence_group"],
                "mapping_sources": sources,
            })
    if registry_bytes is None:
        root_digests = registry.root_digests
    else:
        root_digests = {
            key: sha256(
                b"memorii:sia-traceability-registry-root:" + key.encode() + b":v1\0" + _canonical(source[key])
            ).hexdigest()
            for key in _REGISTRY_ROOTS - {"design_path", "format", "grammar_revision", "registry_id", "report_schemas", "runner_environment_profiles"}
        }
        root_digests["report_schemas"] = sha256(
            b"memorii:sia-report-schema-registry:v1\0" + _canonical([
                sha256(b"memorii:sia-report-schema:v1\0" + _canonical(item) + b"\n").hexdigest()
                for item in source["report_schemas"]
            ]) + b"\n"
        ).hexdigest()
        root_digests["runner_environment_profiles"] = sha256(
            b"memorii:sia-runner-environment-profile-registry:v1\0" + _canonical([
                sha256(b"memorii:sia-runner-environment-profile:v1\0" + _canonical(item) + b"\n").hexdigest()
                for item in source["runner_environment_profiles"]
            ]) + b"\n"
        ).hexdigest()
    ledger = load_checked_in_frozen_structural_manifest_ledger()
    profile = CanonicalTypedValueProfileBinding(
        "semantic_ingestion_typed_value", 2,
        "9dc8b3d01e3f78ed6a11c7668cbb576b09f48ddf107c5efe441bb8bad234fd7f",
        "NormativeTraceabilityStructuralManifestBody.v1", 1,
        "133ba5b492880d5b773eb75f5a81de0bdf0c09e85cce20d17d7aa076cee7b79b",
    )
    assertion = serialize_artifact(
        source["assertion_templates"],
        CanonicalTypedValueProfileBinding(
            profile.profile_id, profile.profile_version, profile.profile_digest,
            "TraceabilityRegistryRoot.assertion_templates.v1", 1,
            "bcec42cc6a2f198fd8a35461f612ee5ca373af14b6e74d023e98cc7cbe70acb6",
        ),
    )
    requirement_bindings = sorted(
        source["requirement_bindings"], key=lambda item: int(item["requirement_id"].rsplit("R", 1)[1])
    )
    section_defaults = sorted(
        source["heading_defaults"],
        key=lambda item: next(index for index, (_, path) in enumerate(numbered) if path == item["heading_path"]),
    )
    anchors = [(item["anchor"], (item["heading_path"],)) for item in source["anchor_bindings"]]
    body: dict[str, Any] = {
        "grammar_revision": ledger.grammar_revision,
        "design_document_digest": digest_raw_bytes(ledger, "raw_design", design_bytes),
        "registry_source_identity": digest_raw_bytes(ledger, "raw_registry", registry_bytes or registry.canonical_bytes),
        "derivation_ledger_schema_id": ledger.schema_id,
        "derivation_ledger_schema_version": ledger.schema_version,
        "derivation_ledger_digest": ledger.digest,
        "derivation_ledger_coordinate": ledger.coordinate,
        "artifact_dag": source["artifact_dag"],
        "artifact_dag_digest": digest_typed_value(ledger, "artifact_dag_root", source["artifact_dag"]),
        "canonical_profile_binding": profile.as_value(),
        "requirement_binding_registry_digest": digest_typed_value(ledger, "requirement_binding_root", requirement_bindings),
        "section_defaults": section_defaults,
        "section_default_registry_digest": digest_typed_value(ledger, "section_default_root", section_defaults),
        "structural_mapping_rules": source["structural_rules"],
        "structural_mapping_rule_registry_digest": digest_typed_value(ledger, "structural_mapping_rule_root", source["structural_rules"]),
        "assertion_registry_artifact": assertion,
        "assertion_registry_digest": decode_artifact(assertion).artifact_digest,
        "test_evidence_groups": source["test_evidence_groups"],
        "test_evidence_group_registry_digest": digest_typed_value(ledger, "test_evidence_group_root", source["test_evidence_groups"]),
        "report_schemas": source["report_schemas"],
        "report_schema_registry_digest": digest_typed_value(ledger, "report_schema_root", source["report_schemas"]),
        "runner_environment_profiles": source["runner_environment_profiles"],
        "runner_environment_profile_registry_digest": digest_typed_value(ledger, "runner_environment_profile_root", source["runner_environment_profiles"]),
        "units": [asdict(unit) for unit in units],
        "entries": mappings,
        "overrides": source["overrides"],
        "override_registry_digest": digest_typed_value(ledger, "override_root", source["overrides"]),
        "explicit_anchor_bindings": anchors,
        "anchor_binding_registry_digest": digest_typed_value(ledger, "anchor_binding_root", anchors),
    }
    try:
        ledger.validate_body_shape(body)
    except ValueError as exc:
        raise TraceabilityCoverageError("independent structural body violates frozen ledger") from exc
    effective_reconstruction_check()
    encoded = encode_typed_value(body, check=effective_reconstruction_check)
    effective_reconstruction_check()
    return encoded


def verify_structural_manifest(*, design_bytes: bytes, registry: Any, published_manifest: Any) -> None:
    """Require the published manifest body to equal the independent rebuild."""
    expected = rebuild_structural_manifest_bytes(design_bytes=design_bytes, registry=registry)
    actual = getattr(published_manifest, "canonical_bytes", None)
    if not isinstance(actual, bytes) or actual != expected:
        raise TraceabilityCoverageError("published structural manifest differs from independent registry expansion")
    try:
        from memorii.core.memory_evolution.ingestion_contracts import decode_typed_value
        body = decode_typed_value(actual)
        if not isinstance(body, dict):
            raise ValueError("manifest body is not a map")
        digest = digest_typed_value(load_checked_in_frozen_structural_manifest_ledger(), "structural_body", body)
    except ValueError as exc:
        raise TraceabilityCoverageError("published structural manifest CTV is invalid") from exc
    if getattr(published_manifest, "structural_manifest_digest", None) != digest:
        raise TraceabilityCoverageError("published structural manifest digest is invalid")


def design_digest(design_bytes: bytes) -> str:
    _validate_raw_design_bytes(design_bytes)
    return sha256(b"semantic-ingestion-traceability\0" + design_bytes).hexdigest()
