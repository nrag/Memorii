"""Installed resource verification for the bounded project-assertions profile.

The profile bundle is deliberately separate from the remote transport.  Loading
it proves the installed prompt, schema, catalog, and component bytes before a
local operator record can enable the Hermes factory.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import importlib.resources
import inspect
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from memorii.core.semantic_ingestion.project_assertions import PROJECT_ASSERTIONS_ADAPTER_SEMANTIC_REVISION

_RESOURCE_PACKAGE: Final = "memorii.core.semantic_ingestion.resources"
_MANIFEST_NAME: Final = "project_assertions.manifest.v1.json"
_RESOURCE_NAMES: Final = (
    _MANIFEST_NAME,
    "project_assertions.prompt.v1.json",
    "project_assertions.output_schema.v1.json",
    "project_assertions.predicate_catalog.v1.json",
    "project_assertions.egress_policy.v1.json",
    "project_assertions.component_fingerprints.v1.json",
)
_PROFILE_ID: Final = "memorii.project_assertions"
_PROFILE_VERSION: Final = 1
_MODEL_ID: Final = "gpt-4.1-nano"


class ProjectAssertionsProfileError(ValueError):
    """The installed profile bytes cannot safely authorize an execution."""


@dataclass(frozen=True)
class ProjectAssertionsProfileBundle:
    """Verified installed profile material used by the CLI and Hermes factory."""

    profile_digests: Mapping[str, str]


class ProjectAssertionsEgressPolicy:
    """The bounded profile's local policy before a segment is sent remotely."""

    def permits(
        self,
        *,
        direct_user_authored: bool,
        installation_scope_authorized: bool,
        segment_text: str,
    ) -> bool:
        return (
            direct_user_authored
            and installation_scope_authorized
            and 0 < len(segment_text) <= 4096
        )


def load_project_assertions_bundle() -> ProjectAssertionsProfileBundle:
    """Load and verify the exact package-owned Level 2 profile bundle."""

    resources = _load_resources()
    documents = {name: _parse_json(payload, name) for name, payload in resources.items()}
    manifest = _object(documents[_MANIFEST_NAME], _MANIFEST_NAME)
    _exact_keys(
        manifest,
        {
            "schema_id",
            "profile_id",
            "profile_version",
            "adapter_semantic_revision",
            "provider",
            "member_digests",
        },
        _MANIFEST_NAME,
    )
    if (
        manifest["schema_id"] != "memorii.semantic_ingestion.project_assertions_manifest.v1"
        or manifest["profile_id"] != _PROFILE_ID
        or manifest["profile_version"] != _PROFILE_VERSION
        or manifest["adapter_semantic_revision"] != PROJECT_ASSERTIONS_ADAPTER_SEMANTIC_REVISION
    ):
        raise ProjectAssertionsProfileError("project-assertions manifest coordinate is invalid")
    provider = _object(manifest["provider"], "provider")
    _exact_keys(provider, {"background", "endpoint", "model", "store", "tools", "training_use"}, "provider")
    if provider != {
        "background": False,
        "endpoint": "/v1/responses",
        "model": _MODEL_ID,
        "store": False,
        "tools": False,
        "training_use": False,
    }:
        raise ProjectAssertionsProfileError("project-assertions provider binding is invalid")
    declared_member_digests = _object(manifest["member_digests"], "member_digests")
    expected_members = set(_RESOURCE_NAMES) - {_MANIFEST_NAME}
    if set(declared_member_digests) != expected_members:
        raise ProjectAssertionsProfileError("project-assertions manifest member list is invalid")
    for name in expected_members:
        if declared_member_digests[name] != _sha256(resources[name]):
            raise ProjectAssertionsProfileError(f"project-assertions resource digest is invalid: {name}")

    prompt = _object(documents["project_assertions.prompt.v1.json"], "prompt")
    _exact_keys(prompt, {"text"}, "prompt")
    if not isinstance(prompt["text"], str) or not prompt["text"]:
        raise ProjectAssertionsProfileError("project-assertions prompt is invalid")
    output_schema = _object(documents["project_assertions.output_schema.v1.json"], "output schema")
    predicate_catalog = _object(documents["project_assertions.predicate_catalog.v1.json"], "predicate catalog")
    egress_policy = _object(documents["project_assertions.egress_policy.v1.json"], "egress policy")
    _validate_catalog(predicate_catalog)
    _validate_egress_policy(egress_policy)
    components = _object(documents["project_assertions.component_fingerprints.v1.json"], "component fingerprints")
    _verify_components(components)

    semantic_contract = _canonical_json(
        {
            "adapter_semantic_revision": PROJECT_ASSERTIONS_ADAPTER_SEMANTIC_REVISION,
            "predicate_catalog": predicate_catalog,
            "profile_id": _PROFILE_ID,
            "profile_version": _PROFILE_VERSION,
        }
    )
    bundle_digest = _sha256(
        _canonical_json({name: _sha256(resources[name]) for name in _RESOURCE_NAMES})
    )
    return ProjectAssertionsProfileBundle(
        profile_digests={
            "profile_manifest_digest": bundle_digest,
            "semantic_contract_digest": _sha256(semantic_contract),
            "component_fingerprint_digest": _sha256(_canonical_json(components)),
            "prompt_schema_digest": _sha256(_canonical_json({"prompt": prompt, "schema": output_schema})),
            "predicate_catalog_digest": _sha256(_canonical_json(predicate_catalog)),
            "egress_policy_digest": _sha256(_canonical_json(egress_policy)),
        }
    )


def _verify_components(document: Mapping[str, object]) -> None:
    _exact_keys(document, {"components"}, "component fingerprints")
    values = document["components"]
    if not isinstance(values, list) or not values:
        raise ProjectAssertionsProfileError("project-assertions component fingerprints are invalid")
    expected_names = {
        "egress_evaluator",
        "predicate_catalog_loader",
        "proposal_adapter",
        "prompt_renderer",
        "response_schema_validator",
        "semantic_writer",
        "transport",
    }
    found_names: set[str] = set()
    try:
        distribution = importlib.metadata.distribution("memorii")
    except importlib.metadata.PackageNotFoundError as error:
        raise ProjectAssertionsProfileError("memorii distribution metadata is unavailable") from error
    for value in values:
        component = _object(value, "component")
        _exact_keys(component, {"distribution", "distribution_version", "module", "name", "source_sha256", "symbol"}, "component")
        name = _string(component["name"], "component name")
        if name in found_names:
            raise ProjectAssertionsProfileError("project-assertions component fingerprints are duplicated")
        found_names.add(name)
        if component["distribution"] != "memorii" or component["distribution_version"] != distribution.version:
            raise ProjectAssertionsProfileError("project-assertions distribution binding is invalid")
        module_name = _string(component["module"], "component module")
        symbol_name = _string(component["symbol"], "component symbol")
        try:
            module = importlib.import_module(module_name)
            symbol = getattr(module, symbol_name)
            source_path = inspect.getsourcefile(symbol) or inspect.getsourcefile(module)
        except (AttributeError, ImportError, OSError, TypeError) as error:
            raise ProjectAssertionsProfileError("project-assertions component is unavailable") from error
        if source_path is None:
            raise ProjectAssertionsProfileError("project-assertions component source is unavailable")
        if component["source_sha256"] != _sha256(Path(source_path).read_bytes()):
            raise ProjectAssertionsProfileError("project-assertions component fingerprint is invalid")
    if found_names != expected_names:
        raise ProjectAssertionsProfileError("project-assertions component set is invalid")


def _validate_catalog(catalog: Mapping[str, object]) -> None:
    _exact_keys(catalog, {"predicates"}, "predicate catalog")
    predicates = catalog["predicates"]
    if not isinstance(predicates, list) or len(predicates) != 3:
        raise ProjectAssertionsProfileError("project-assertions predicate catalog is invalid")
    expected = {
        "project_owner": ("PersonName", "entity"),
        "project_status": ("StatusText", "literal"),
        "project_deadline": ("LocalDate", "literal"),
    }
    actual: dict[str, tuple[str, str]] = {}
    for value in predicates:
        predicate = _object(value, "predicate")
        _exact_keys(predicate, {"correction_policy", "evidence_rule", "predicate_id", "routing", "scope", "value_kind", "value_type"}, "predicate")
        predicate_id = _string(predicate["predicate_id"], "predicate id")
        actual[predicate_id] = (_string(predicate["value_type"], "value type"), _string(predicate["value_kind"], "value kind"))
        if predicate["correction_policy"] != "one_current_value" or predicate["scope"] != "installation":
            raise ProjectAssertionsProfileError("project-assertions predicate policy is invalid")
    if actual != expected:
        raise ProjectAssertionsProfileError("project-assertions predicate catalog is invalid")


def _validate_egress_policy(policy: Mapping[str, object]) -> None:
    _exact_keys(policy, {"allow_verbatim", "max_unicode_scalars", "required_source_classification"}, "egress policy")
    if policy != {
        "allow_verbatim": True,
        "max_unicode_scalars": 4096,
        "required_source_classification": "direct_user_authored_project_assertion",
    }:
        raise ProjectAssertionsProfileError("project-assertions egress policy is invalid")


def _object(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ProjectAssertionsProfileError(f"project-assertions {field} is invalid")
    return cast(dict[str, object], value)


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ProjectAssertionsProfileError(f"project-assertions {field} is invalid")
    return value


def _exact_keys(value: Mapping[str, object], expected: set[str], field: str) -> None:
    if set(value) != expected:
        raise ProjectAssertionsProfileError(f"project-assertions {field} fields are invalid")


def _parse_json(payload: bytes, resource_name: str) -> object:
    try:
        text = payload.decode("utf-8")
        return json.loads(text, object_pairs_hook=_reject_duplicate_keys, parse_constant=_reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, ProjectAssertionsProfileError) as error:
        raise ProjectAssertionsProfileError(f"project-assertions resource is invalid: {resource_name}") from error


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ProjectAssertionsProfileError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(_: str) -> None:
    raise ProjectAssertionsProfileError("non-finite JSON value")


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _load_resources() -> dict[str, bytes]:
    try:
        root = importlib.resources.files(_RESOURCE_PACKAGE)
        payloads = {name: root.joinpath(name).read_bytes() for name in _RESOURCE_NAMES}
    except (FileNotFoundError, ModuleNotFoundError, OSError) as error:
        raise ProjectAssertionsProfileError("project-assertions profile resources are unavailable") from error
    return payloads


__all__ = [
    "ProjectAssertionsEgressPolicy",
    "ProjectAssertionsProfileBundle",
    "ProjectAssertionsProfileError",
    "load_project_assertions_bundle",
]
