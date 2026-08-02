"""Strict loader for the revision-3 semantic-ingestion traceability registry."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

CANONICAL_PROFILE = "memorii-sia-canonical-json-v1"
_MAX_RAW_JSON_NESTING = 256
_MAX_RAW_JSON_NUMBER_TOKEN_BYTES = 1024
_SCALAR_METADATA = {
    "format": "memorii.semantic-ingestion.traceability-source.v1",
    "registry_id": "semantic-ingestion-traceability-registry-v1",
    "grammar_revision": "sia-traceability-v1",
    "design_path": "docs/design/semantic_ingestion_architecture.md",
}
_ROOTS = (
    "anchor_bindings", "artifact_dag", "assertion_templates", "design_path", "format", "grammar_revision",
    "heading_defaults", "overrides", "registry_id", "report_schemas", "requirement_bindings",
    "runner_environment_profiles", "structural_rules", "test_evidence_groups",
)
_ARRAY_ROOTS = frozenset(_ROOTS) - {"design_path", "format", "grammar_revision", "registry_id"}
_SPECIAL_ROOTS = frozenset({"report_schemas", "runner_environment_profiles"})
_ORDINARY_ITEM_KEYS = {
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
_COMMAND_KEYS = frozenset({"command_id", "argv", "working_directory"})
_SELECTED_TEST_KEYS = frozenset(
    {"test_id", "pytest_node_id", "implementation_status", "behavioral_assertion"}
)
_RUNNER_REQUIREMENT_KEYS = frozenset(
    {
        "runner_kind",
        "minimum_python_version",
        "minimum_pytest_version",
        "network_policy",
        "environment_policy",
        "selection_policy",
        "exit_policy",
    }
)
_ARTIFACT_POLICY_KEYS = frozenset(
    {"report_bytes", "result_bytes", "stdout_stderr", "stream_sharing", "report_binding"}
)
_UNIT_KINDS = frozenset(
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
_ARTIFACT_DAG_ORDER = (
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
_REPORT_SCHEMA_KEYS = frozenset(
    {
        "schema_id",
        "schema_version",
        "canonical_profile_id",
        "media_type",
        "schema_document",
    }
)
_REPORT_SCHEMA_DOCUMENT_KEYS = frozenset(
    {"$schema", "additionalProperties", "properties", "required", "type"}
)
_RUNNER_PROFILE_KEYS = frozenset(
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


class RegistryValidationError(ValueError):
    """Raised when a registry source package is not the exact frozen artifact."""


def _validate_raw_registry_complexity(raw: bytes) -> None:
    """Reject parser-hostile JSON shapes before stdlib decoding.

    This is intentionally a small transport check, not a general resource
    policy.  It bounds only the two inputs whose failure modes otherwise vary
    with Python's recursive decoder and integer conversion limits.
    """
    nesting = 0
    number_width = 0
    in_string = False
    escaped = False
    number_bytes = b"-+0123456789.eE"
    for byte in raw:
        if in_string:
            if escaped:
                escaped = False
            elif byte == ord("\\"):
                escaped = True
            elif byte == ord('"'):
                in_string = False
            continue
        if byte == ord('"'):
            in_string = True
            number_width = 0
        elif byte in (ord("["), ord("{")):
            nesting += 1
            if nesting > _MAX_RAW_JSON_NESTING:
                raise RegistryValidationError("registry JSON nesting exceeds the closed transport bound")
            number_width = 0
        elif byte in (ord("]"), ord("}")):
            nesting -= 1
            number_width = 0
        elif byte in number_bytes:
            number_width += 1
            if number_width > _MAX_RAW_JSON_NUMBER_TOKEN_BYTES:
                raise RegistryValidationError("registry JSON numeric token exceeds the closed transport bound")
        else:
            number_width = 0


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


def _validate_report_schema_dialect(schema: Any, *, root: bool = False) -> None:
    if not isinstance(schema, dict):
        raise RegistryValidationError("report schema node must be an object")
    if "anyOf" in schema:
        alternatives = schema["anyOf"]
        if (
            set(schema) != {"anyOf"}
            or not isinstance(alternatives, list)
            or not alternatives
        ):
            raise RegistryValidationError("report schema anyOf must be a nonempty closed node")
        for alternative in alternatives:
            _validate_report_schema_dialect(alternative)
        return
    if "const" in schema:
        if set(schema) not in ({"const"}, {"const", "type"}):
            raise RegistryValidationError("report schema const node has unsupported keywords")
        if "type" not in schema:
            return
        kind = schema["type"]
        constant = schema["const"]
        constant_matches = {
            "object": isinstance(constant, dict),
            "array": isinstance(constant, list),
            "string": isinstance(constant, str),
            "integer": isinstance(constant, int) and not isinstance(constant, bool),
            "null": constant is None,
        }
        if kind not in constant_matches or not constant_matches[kind]:
            raise RegistryValidationError("report schema const does not match its type")
        return
    kind = schema.get("type")
    if kind not in {"object", "array", "string", "integer", "null"}:
        raise RegistryValidationError("report schema has an unsupported type")
    if kind == "object":
        allowed = {"type", "properties", "required", "additionalProperties"}
        if root:
            allowed.add("$schema")
        properties = schema.get("properties")
        required = schema.get("required")
        if (
            set(schema) != allowed
            or not isinstance(properties, dict)
            or not all(isinstance(name, str) for name in properties)
            or not isinstance(required, list)
            or not all(isinstance(name, str) for name in required)
            or len(required) != len(set(required))
            or any(name not in properties for name in required)
            or schema.get("additionalProperties") is not False
            or set(required) != set(properties)
        ):
            raise RegistryValidationError("report schema object node is malformed or open")
        for child in properties.values():
            _validate_report_schema_dialect(child)
        return
    if kind == "array":
        if set(schema) not in (
            {"type", "items", "minItems"},
            {"type", "items", "minItems", "uniqueItems"},
        ):
            raise RegistryValidationError("report schema array node has unsupported keywords")
        minimum = schema["minItems"]
        if (
            type(minimum) is not int
            or minimum < 0
            or (
                "uniqueItems" in schema
                and not isinstance(schema["uniqueItems"], bool)
            )
        ):
            raise RegistryValidationError("report schema array constraints are malformed")
        _validate_report_schema_dialect(schema["items"])
        return
    if kind == "string":
        if not set(schema) <= {"type", "minLength", "pattern", "format"}:
            raise RegistryValidationError("report schema string node has unsupported keywords")
        minimum = schema.get("minLength")
        if minimum is not None and (type(minimum) is not int or minimum < 0):
            raise RegistryValidationError("report schema minLength is malformed")
        pattern = schema.get("pattern")
        if pattern is not None:
            if not isinstance(pattern, str):
                raise RegistryValidationError("report schema pattern is malformed")
            try:
                re.compile(pattern)
            except (OverflowError, re.error) as exc:
                raise RegistryValidationError(
                    "report schema pattern is not compilable"
                ) from exc
        format_name = schema.get("format")
        if format_name is not None and format_name != "date-time":
            raise RegistryValidationError("report schema format is unsupported")
        return
    if set(schema) != {"type"}:
        raise RegistryValidationError("report schema scalar node has unsupported keywords")


def _validate_report_schema(item: Any) -> None:
    if not isinstance(item, dict) or set(item) != _REPORT_SCHEMA_KEYS:
        raise RegistryValidationError("report schemas must use the exact v1 outer shape")
    document = item["schema_document"]
    if (
        item["schema_id"] != "memorii.semantic_ingestion.pytest_report"
        or type(item["schema_version"]) is not int
        or item["schema_version"] != 1
        or item["canonical_profile_id"] != CANONICAL_PROFILE
        or item["media_type"] != "application/schema+json"
        or not isinstance(document, dict)
        or set(document) != _REPORT_SCHEMA_DOCUMENT_KEYS
        or document["$schema"] != "https://json-schema.org/draft/2020-12/schema"
        or document["additionalProperties"] is not False
        or not isinstance(document["properties"], dict)
        or not isinstance(document["required"], list)
        or not all(isinstance(value, str) for value in document["required"])
        or document["type"] != "object"
    ):
        raise RegistryValidationError("report schemas must use the exact closed v1 contract")
    _validate_report_schema_dialect(document, root=True)


def _validate_runner_profile(item: Any) -> None:
    if not isinstance(item, dict) or set(item) != _RUNNER_PROFILE_KEYS:
        raise RegistryValidationError("runner environment profiles must use the closed v1 shape")
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
        or item["canonical_profile_id"] != CANONICAL_PROFILE
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
        raise RegistryValidationError(
            "runner environment profile uses an invalid nested v1 policy"
        )


def expected_requirement_ids() -> tuple[str, ...]:
    """Return the closed traceability requirement universe."""
    return tuple(f"SIA-R{number:02d}" for number in range(1, 24))


def _validate_references(source: dict[str, Any]) -> None:
    if any(source[key] != expected for key, expected in _SCALAR_METADATA.items()):
        raise RegistryValidationError("registry scalar metadata differs from frozen v1")
    for root, expected_keys in _ORDINARY_ITEM_KEYS.items():
        if any(not isinstance(item, dict) or set(item) != expected_keys for item in source[root]):
            raise RegistryValidationError(f"{root} members must use the exact v1 shape")
    if source["overrides"]:
        raise RegistryValidationError("registry v1 overrides must be exactly empty")

    bindings = source["requirement_bindings"]
    requirements = _id_set(bindings, "requirement_id", "requirement_bindings")
    expected_requirements = expected_requirement_ids()
    if (
        requirements != set(expected_requirements)
        or tuple(item["requirement_id"] for item in bindings) != expected_requirements
        or any(
            not isinstance(item["assertion_template_id"], str)
            or type(item["assertion_version"]) is not int
            or item["assertion_version"] < 1
            or not isinstance(item["test_evidence_group"], str)
            for item in bindings
        )
    ):
        raise RegistryValidationError("requirement bindings do not match the complete requirement set")
    template_items = source["assertion_templates"]
    template_coordinates = [
        (item["template_id"], item["version"]) for item in template_items
    ]
    if (
        any(
            not isinstance(item["template_id"], str)
            or type(item["version"]) is not int
            or item["version"] < 1
            or not isinstance(item["unit_kinds"], list)
            or not item["unit_kinds"]
            or not all(isinstance(kind, str) and kind in _UNIT_KINDS for kind in item["unit_kinds"])
            or len(item["unit_kinds"]) != len(set(item["unit_kinds"]))
            or not isinstance(item["acceptance"], str)
            for item in template_items
        )
        or len(template_coordinates) != len(set(template_coordinates))
        or [item["template_id"] for item in template_items]
        != sorted((item["template_id"] for item in template_items), key=lambda value: value.encode("utf-8"))
    ):
        raise RegistryValidationError("assertion templates are malformed, duplicate, or unordered")
    groups = _id_set(source["test_evidence_groups"], "group_id", "test_evidence_groups")
    group_order = [item["group_id"] for item in source["test_evidence_groups"]]
    for binding in bindings:
        if (
            (binding["assertion_template_id"], binding["assertion_version"])
            not in template_coordinates
            or binding["test_evidence_group"] not in groups
        ):
            raise RegistryValidationError("requirement binding has an unresolved template or group")
    if [binding["test_evidence_group"] for binding in bindings] != group_order:
        raise RegistryValidationError("test evidence groups must follow ordered requirement bindings")
    schema_items = source["report_schemas"]
    profile_items = source["runner_environment_profiles"]
    if not schema_items or not profile_items:
        raise RegistryValidationError("report schema and runner profile registries must be nonempty")
    for item in schema_items:
        _validate_report_schema(item)
    for item in profile_items:
        _validate_runner_profile(item)
    schema_coordinates = {(item["schema_id"], item["schema_version"]) for item in schema_items}
    profile_coordinates = {(item["profile_id"], item["profile_version"]) for item in profile_items}
    if len(schema_coordinates) != len(schema_items) or len(profile_coordinates) != len(profile_items):
        raise RegistryValidationError("report schema or runner profile coordinates are duplicate or malformed")
    schema_digests = [_item_digest(b"memorii:sia-report-schema:v1\0", item) for item in schema_items]
    profile_digests = [_item_digest(b"memorii:sia-runner-environment-profile:v1\0", item) for item in profile_items]
    for group in source["test_evidence_groups"]:
        command = group["command"]
        selected_tests = group["selected_tests"]
        runner_requirements = group["runner_requirements"]
        artifact_policy = group["artifact_result_policy"]
        if (
            not isinstance(command, dict)
            or set(command) != _COMMAND_KEYS
            or not isinstance(command["command_id"], str)
            or not isinstance(command["argv"], list)
            or not command["argv"]
            or not all(isinstance(value, str) for value in command["argv"])
            or command["working_directory"] != "memorii"
            or not isinstance(selected_tests, list)
            or not selected_tests
            or any(
                not isinstance(test, dict)
                or set(test) != _SELECTED_TEST_KEYS
                or not all(isinstance(test[key], str) for key in _SELECTED_TEST_KEYS)
                or test["implementation_status"]
                not in {"repository_evidenced", "required_not_yet_evidenced"}
                for test in selected_tests
            )
            or not isinstance(runner_requirements, dict)
            or set(runner_requirements) != _RUNNER_REQUIREMENT_KEYS
            or not all(isinstance(value, str) for value in runner_requirements.values())
            or runner_requirements["runner_kind"] != "cpython_pytest"
            or runner_requirements["network_policy"] != "denied"
            or runner_requirements["environment_policy"] != "clean_allowlisted"
            or runner_requirements["selection_policy"]
            != "all_selected_collected_no_skip_xfail_deselect"
            or runner_requirements["exit_policy"] != "zero_and_every_selected_test_passed"
            or not isinstance(artifact_policy, dict)
            or set(artifact_policy) != _ARTIFACT_POLICY_KEYS
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
    if any(
        not isinstance(item["heading_path"], str)
        or not isinstance(item["requirements"], list)
        or not all(isinstance(requirement, str) for requirement in item["requirements"])
        for item in headings
    ):
        raise RegistryValidationError("heading defaults use invalid field types")
    paths = _id_set(headings, "heading_path", "heading_defaults")
    # The frozen Layer1 registry covers every numeric Section 1-5 heading in
    # the reviewed design. Its cardinality is itself a closed source invariant.
    if len(paths) != 151 or any(not item["requirements"] for item in headings):
        raise RegistryValidationError("registry must contain exactly 151 nonempty heading defaults")
    if any(requirement not in requirements for item in headings for requirement in item["requirements"]):
        raise RegistryValidationError("heading default refers to an unknown requirement")
    if any(
        len(item["requirements"]) != len(set(item["requirements"]))
        or item["requirements"] != sorted(item["requirements"], key=lambda value: int(value.rsplit("R", 1)[1]))
        for item in headings
    ):
        raise RegistryValidationError("heading default requirements must be unique and in requirement order")
    _id_set(source["structural_rules"], "rule_id", "structural_rules")
    _id_set(source["anchor_bindings"], "anchor", "anchor_bindings")
    if any(
        not isinstance(item["heading_path"], str)
        for item in source["anchor_bindings"]
    ):
        raise RegistryValidationError("anchor bindings use invalid field types")
    for rule in source["structural_rules"]:
        if (
            not isinstance(rule["rule_id"], str)
            or not isinstance(rule["heading_path"], str)
            or rule["selector_kind"] != "named_table_rows"
            or not isinstance(rule["selector_values"], list)
            or not all(isinstance(value, str) for value in rule["selector_values"])
            or rule["effect"] != "add_matching_ledger_requirement"
            or rule["heading_path"] not in paths
            or any(value not in requirements for value in rule["selector_values"])
        ):
            raise RegistryValidationError("structural rule has an unresolved path or requirement")
    if len(source["artifact_dag"]) != 13:
        raise RegistryValidationError("artifact DAG must contain exactly 13 nodes")
    nodes = _id_set(source["artifact_dag"], "node_id", "artifact_dag")
    for node in source["artifact_dag"]:
        dependencies = node["depends_on"]
        if (
            not isinstance(dependencies, list)
            or not all(isinstance(dependency, str) for dependency in dependencies)
            or len(dependencies) != len(set(dependencies))
            or node["node_id"] in dependencies
            or any(dep not in nodes for dep in dependencies)
        ):
            raise RegistryValidationError("artifact DAG has an invalid dependency")
    declared = [node["node_id"] for node in source["artifact_dag"]]
    if tuple(declared) != _ARTIFACT_DAG_ORDER:
        raise RegistryValidationError("artifact DAG is not in the closed v1 source order")
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
    if ordered != declared:
        raise RegistryValidationError("artifact DAG is not in deterministic Kahn topological order")


def load_registry(path: Path) -> TraceabilityRegistry:
    return load_registry_bytes(path.read_bytes())


def load_registry_bytes(raw: bytes) -> TraceabilityRegistry:
    """Load complete canonical registry authority from its raw package bytes."""
    if raw.startswith(b"\xef\xbb\xbf") or not raw.endswith(b"\n") or raw.endswith(b"\n\n"):
        raise RegistryValidationError("registry must be strict UTF-8 with exactly one final LF and no BOM")
    try:
        _validate_raw_registry_complexity(raw[:-1])
        source = json.loads(raw[:-1].decode("utf-8"), object_pairs_hook=_pairs)
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
    except RegistryValidationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise RegistryValidationError("registry is not valid duplicate-free UTF-8 JSON") from exc
