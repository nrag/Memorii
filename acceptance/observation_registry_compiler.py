"""Independent raw-source compiler for the operational observation registry.

This module intentionally knows only the approved raw declaration grammar.  It
does not import application packages or acceptance fixtures, and returns bytes
as well as digests so a vector harness can compare complete commitments.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import struct
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn


class RegistrySourceError(ValueError):
    """A source package does not satisfy the closed profile-3 grammar."""


@dataclass(frozen=True)
class SourceLimits:
    """Protected parser and source-read limits; they are never commitment inputs."""

    max_raw_bytes: int = 1_000_000
    max_json_nodes: int = 1_000_000
    max_json_depth: int = 64

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value <= 0
            for value in (self.max_raw_bytes, self.max_json_nodes, self.max_json_depth)
        ):
            raise RegistrySourceError("source limits must be positive integers")


@dataclass(frozen=True)
class SourceIdentity:
    role: str
    sha256: str
    raw_bytes: bytes


@dataclass(frozen=True)
class RegistryEntryReport:
    schema_id: str
    schema_version: str
    schema_fingerprint: str
    enum_registry_digest: str
    optional_field_policy_digest: str
    numeric_encoding_spec_registry_digest: str
    digest_signature_field_policy_digest: str
    decoder_digest: str
    binding_digest: str
    entry_digest: str
    entry_preimage: bytes


@dataclass(frozen=True)
class RegistryCompilationReport:
    profile_digest: str
    profile_preimage: bytes
    registry_digest: str
    registry_preimage: bytes
    entries: tuple[RegistryEntryReport, ...]
    source_identities: tuple[SourceIdentity, ...]
    decoder_source_manifest_bytes: bytes | None
    publication_manifest_bytes: bytes | None
    publication_manifest_digest: str | None


_ROLES = {
    "schema",
    "enum",
    "optional",
    "numeric",
    "digest-signature",
    "decoder",
    "upcast",
}
_ASCII_ID = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._/-")
_HEX = set("0123456789abcdef")
_TYPE_KINDS = {
    "string",
    "bool",
    "null",
    "literal",
    "integer",
    "bytes",
    "datetime",
    "duration_microseconds",
    "canonical_decimal_quantity",
    "canonical_finite_binary64",
    "enum_ref",
    "model_ref",
    "list",
    "set",
    "frozenset",
    "variadic_tuple",
    "fixed_tuple",
    "map",
    "union",
}
_GRAMMAR_LITERAL = {
    "envelope": {
        "binding_fields": [
            "profile_id",
            "profile_version",
            "profile_digest",
            "schema_id",
            "schema_version",
            "binding_digest",
        ],
        "fields": [
            "binding",
            "canonical_value_bytes",
            "canonical_value_digest",
            "artifact_digest",
        ],
        "permitted_value_kinds": ["bytes", "integer", "map", "scalar"],
    },
    "grammar_revision": "operational-3",
    "json": {"canonical": "RFC8785", "terminal_lf": False, "utf8": "strict"},
    "profile_id": "semantic_ingestion_typed_value",
    "profile_version": "3",
    "role": "grammar",
    "tags": {
        "bytes": "rfc4648_standard_padded",
        "datetime": "utc_six_fractional_digits",
        "duration_microseconds": "signed_i64",
        "enum": "registered_qualified_member",
        "frozenset": "canonical_member_byte_order",
        "integer": "canonical_decimal_string",
        "list": "declared_order",
        "map": "encoded_json_string_key_order",
        "set": "canonical_member_byte_order",
        "tuple": "declared_order",
    },
    "type_rules": {
        "bool_as_integer": False,
        "defaults_before_verification": False,
        "float_decimal": False,
        "map_keys": "string_only",
        "model_fields": "registered_exact",
        "optional": "registered_policy",
        "union": "one_registered_discriminator",
    },
}


def _fail(message: str) -> NoReturn:
    raise RegistrySourceError(message)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _text(value: str) -> bytes:
    try:
        return value.encode("utf-8", "strict")
    except UnicodeError as exc:
        raise RegistrySourceError("text is not strict UTF-8") from exc


def _lp(*parts: str | bytes) -> bytes:
    output = bytearray()
    for part in parts:
        raw = _text(part) if isinstance(part, str) else part
        if not isinstance(raw, bytes):
            _fail("LP member is not bytes or text")
        output.extend(struct.pack(">Q", len(raw)))
        output.extend(raw)
    return bytes(output)


def _ascii_id(value: Any, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or any(ch not in _ASCII_ID for ch in value)
    ):
        _fail(f"{name} is not an ASCII identifier")
    return value


def _positive(value: Any, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or not value.isascii()
        or not value.isdecimal()
        or value[0] == "0"
    ):
        _fail(f"{name} is not a positive canonical unsigned decimal")
    return value


def _uint(value: Any, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or not value.isascii()
        or not value.isdecimal()
        or (len(value) > 1 and value[0] == "0")
    ):
        _fail(f"{name} is not a canonical unsigned decimal")
    return value


def _digest(value: Any, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in _HEX for ch in value)
    ):
        _fail(f"{name} is not lowercase SHA-256 hex")
    return value


def _object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail(f"duplicate object key {key!r}")
        result[key] = value
    return result


def _parse(raw: bytes, label: str, limits: SourceLimits) -> dict[str, Any]:
    if not isinstance(raw, bytes) or not raw:
        _fail(f"{label} is not nonempty bytes")
    if len(raw) > limits.max_raw_bytes:
        _fail(f"{label} exceeds protected raw-byte limit")
    if raw.endswith(b"\n"):
        _fail(f"{label} has a terminal LF")
    try:
        decoded = raw.decode("utf-8", "strict")
        value = json.loads(
            decoded,
            object_pairs_hook=_object_pairs,
            parse_int=lambda _: _fail("JSON numbers are forbidden"),
            parse_float=lambda _: _fail("JSON numbers are forbidden"),
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RegistrySourceError(f"{label} is not strict JSON") from exc
    _validate_json(value, limits, 1, [0])
    try:
        canonical = json.dumps(
            value, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise RegistrySourceError(f"{label} is not canonical JSON") from exc
    if canonical != raw:
        _fail(f"{label} is not canonical JSON bytes")
    if not isinstance(value, dict):
        _fail(f"{label} root is not an object")
    return value


def _validate_json(
    value: Any, limits: SourceLimits, depth: int, nodes: list[int]
) -> None:
    nodes[0] += 1
    if nodes[0] > limits.max_json_nodes:
        _fail("JSON declaration exceeds protected node limit")
    if depth > limits.max_json_depth:
        _fail("JSON declaration exceeds protected depth limit")
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, list):
        for item in value:
            _validate_json(item, limits, depth + 1, nodes)
        return
    if isinstance(value, dict):
        keys = list(value)
        if any(
            not isinstance(key, str) or not key.isascii() or not key for key in keys
        ):
            _fail("object key is not a nonempty ASCII string")
        if keys != sorted(
            keys, key=lambda key: json.dumps(key, separators=(",", ":")).encode("ascii")
        ):
            _fail("object keys are not in encoded JSON-string order")
        for item in value.values():
            _validate_json(item, limits, depth + 1, nodes)
        return
    _fail("JSON declaration contains an unsupported value")


def _exact(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        _fail(f"{label} has an invalid field set")


def _coordinate(role: Mapping[str, Any], label: str) -> tuple[str, str]:
    return (
        _ascii_id(role.get("schema_id"), f"{label}.schema_id"),
        _positive(role.get("schema_version"), f"{label}.schema_version"),
    )


def _sorted_unique(items: list[Any], key, label: str) -> None:
    keys = [key(item) for item in items]
    if keys != sorted(keys) or len(set(keys)) != len(keys):
        _fail(f"{label} is not sorted and unique")


def _integer(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or not value.isascii():
        _fail(f"{label} is not canonical integer text")
    body = value[1:] if value.startswith("-") else value
    if (
        not body
        or not body.isdecimal()
        or body == "0"
        and value.startswith("-")
        or (len(body) > 1 and body[0] == "0")
    ):
        _fail(f"{label} is not canonical integer text")
    return value


def _walk_type(
    expr: Any,
    refs: set[tuple[str, str]],
    enums: set[str],
    numeric: set[str],
    label: str,
) -> None:
    if not isinstance(expr, dict):
        _fail(f"{label} is not a type object")
    kind = expr.get("kind")
    if kind not in _TYPE_KINDS:
        _fail(f"{label} has unknown type kind")
    if kind == "string":
        _exact(expr, {"kind", "lexical_rule"}, label)
        if expr["lexical_rule"] not in {
            "unicode_scalar",
            "nonempty_unicode_scalar",
            "sha256",
            "signature_hex128",
        }:
            _fail(f"{label} has invalid string rule")
    elif kind in {"bool", "null", "bytes", "datetime", "duration_microseconds"}:
        required = {"kind"} if kind in {"bool", "null"} else {"kind", "lexical_rule"}
        _exact(expr, required, label)
        expected = {
            "bytes": "rfc4648_standard_padded",
            "datetime": "utc_six_fractional_digits",
            "duration_microseconds": "signed_i64",
        }
        if kind in expected and expr["lexical_rule"] != expected[kind]:
            _fail(f"{label} has invalid lexical rule")
    elif kind == "literal":
        _exact(expr, {"kind", "values"}, label)
        values = expr["values"]
        if not isinstance(values, list) or not values:
            _fail(f"{label}.values is empty")
        encoded = []
        for value in values:
            if isinstance(value, dict):
                _exact(value, {"integer_value"}, f"{label}.literal")
                _integer(value["integer_value"], f"{label}.integer_value")
            elif not isinstance(value, (str, bool)):
                _fail(f"{label}.values has an invalid literal")
            encoded.append(
                json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode(
                    "utf-8"
                )
            )
        if encoded != sorted(encoded) or len(set(encoded)) != len(encoded):
            _fail(f"{label}.values is not sorted and unique")
    elif kind == "integer":
        _exact(expr, {"kind", "lexical_rule", "minimum", "maximum"}, label)
        if expr["lexical_rule"] != "canonical_decimal":
            _fail(f"{label} has invalid integer rule")
        lo, hi = expr["minimum"], expr["maximum"]
        if lo is not None:
            _integer(lo, f"{label}.minimum")
        if hi is not None:
            _integer(hi, f"{label}.maximum")
        if lo is not None and hi is not None and int(lo) > int(hi):
            _fail(f"{label} has inverted integer bounds")
    elif kind in {"canonical_decimal_quantity", "canonical_finite_binary64"}:
        _exact(expr, {"kind", "field_name"}, label)
        numeric.add(_ascii_id(expr["field_name"], f"{label}.field_name"))
    elif kind == "enum_ref":
        _exact(expr, {"kind", "qualified_id"}, label)
        enums.add(_ascii_id(expr["qualified_id"], f"{label}.qualified_id"))
    elif kind == "model_ref":
        _exact(expr, {"kind", "schema_id", "schema_version"}, label)
        refs.add(
            (
                _ascii_id(expr["schema_id"], f"{label}.schema_id"),
                _positive(expr["schema_version"], f"{label}.schema_version"),
            )
        )
    elif kind in {"list", "set", "frozenset", "variadic_tuple"}:
        _exact(expr, {"kind", "element"}, label)
        _walk_type(expr["element"], refs, enums, numeric, label + ".element")
    elif kind == "fixed_tuple":
        _exact(expr, {"kind", "items"}, label)
        if not isinstance(expr["items"], list) or not expr["items"]:
            _fail(f"{label}.items is empty")
        for index, child in enumerate(expr["items"]):
            _walk_type(child, refs, enums, numeric, f"{label}.items[{index}]")
    elif kind == "map":
        _exact(expr, {"kind", "key_kind", "value"}, label)
        if expr["key_kind"] != "string":
            _fail(f"{label} has non-string map key")
        _walk_type(expr["value"], refs, enums, numeric, label + ".value")
    else:
        _exact(expr, {"kind", "discriminator", "alternatives"}, label)
        _ascii_id(expr["discriminator"], f"{label}.discriminator")
        alts = expr["alternatives"]
        if not isinstance(alts, list) or not alts:
            _fail(f"{label}.alternatives is empty")
        _sorted_unique(
            alts,
            lambda item: (
                item.get("discriminator_value") if isinstance(item, dict) else ""
            ),
            f"{label}.alternatives",
        )
        for alt in alts:
            _exact(alt, {"discriminator_value", "model"}, f"{label}.alternative")
            if not isinstance(alt["discriminator_value"], str):
                _fail(f"{label}.alternative value is invalid")
            _walk_type(alt["model"], refs, enums, numeric, label + ".alternative.model")


def _closure(
    root: tuple[str, str],
    schemas: Mapping[tuple[str, str], tuple[dict[str, Any], bytes]],
    external: Mapping[tuple[str, str], tuple[str, str] | None],
) -> tuple[tuple[str, str], ...]:
    pending = [root]
    seen: set[tuple[str, str]] = set()
    while pending:
        coordinate = pending.pop()
        if coordinate in seen:
            continue
        if coordinate not in schemas:
            _fail(f"unresolved schema reference {coordinate}")
        seen.add(coordinate)
        schema = schemas[coordinate][0]
        refs: set[tuple[str, str]] = set()
        enums: set[str] = set()
        numeric: set[str] = set()
        for field in schema["fields"]:
            _walk_type(
                field["type"], refs, enums, numeric, f"schema {coordinate} field"
            )
        dependency = external.get(coordinate)
        if dependency is not None:
            refs.add(dependency)
        if coordinate in refs:
            _fail(f"self reference at {coordinate}")
        pending.extend(refs)
    # A DFS catches indirect cycles; an acyclic closure is mandatory even if all nodes resolve.
    visiting: set[tuple[str, str]] = set()
    done: set[tuple[str, str]] = set()

    def visit(node: tuple[str, str]) -> None:
        if node in visiting:
            _fail("schema dependency graph contains a cycle")
        if node in done:
            return
        visiting.add(node)
        schema = schemas[node][0]
        refs: set[tuple[str, str]] = set()
        enums: set[str] = set()
        numeric: set[str] = set()
        for field in schema["fields"]:
            _walk_type(field["type"], refs, enums, numeric, "schema field")
        if external.get(node) is not None:
            refs.add(external[node])  # type: ignore[arg-type]
        for child in refs:
            visit(child)
        visiting.remove(node)
        done.add(node)

    visit(root)
    return tuple(sorted(seen, key=lambda item: (_text(item[0]), int(item[1]))))


def _closure_digest(
    domain: str,
    role_kind: str | None,
    root: tuple[str, str],
    closure: tuple[tuple[str, str], ...],
    roles: Mapping[tuple[str, str], tuple[dict[str, Any], bytes]],
) -> str:
    parts: list[str | bytes] = [domain]
    if role_kind is not None:
        parts.append(role_kind)
    parts.extend([root[0], root[1], str(len(closure))])
    for coordinate in closure:
        parts.extend([coordinate[0], coordinate[1], roles[coordinate][1]])
    return _sha(_lp(*parts))


def _source_roles(
    raw_roles: Iterable[tuple[str, bytes]],
    limits: SourceLimits,
) -> tuple[dict[str, tuple[dict[str, Any], bytes]], tuple[SourceIdentity, ...]]:
    result: dict[str, tuple[dict[str, Any], bytes]] = {}
    for role, raw in raw_roles:
        _ascii_id(role, "source role")
        if role in result:
            _fail(f"duplicate source role {role}")
        parsed = _parse(raw, role, limits)
        result[role] = (parsed, raw)
    if "grammar" not in result:
        _fail("grammar role is missing")
    identities = tuple(
        SourceIdentity(role, _sha(raw), raw)
        for role, (_, raw) in sorted(result.items(), key=lambda item: _text(item[0]))
    )
    return result, identities


_DEFAULT_SOURCE_LIMITS = SourceLimits()


def compile_observation_registry(
    raw_roles: Iterable[tuple[str, bytes]],
    *,
    decoder_source_manifest_bytes: bytes | None = None,
    decoder_source_root: str | os.PathLike[str] | None = None,
    publication_manifest_bytes: bytes | None = None,
    limits: SourceLimits = _DEFAULT_SOURCE_LIMITS,
) -> RegistryCompilationReport:
    """Compile a complete raw package without loading any production implementation.

    ``raw_roles`` uses stable role strings such as ``schema/Foo/1``.  The
    decoder-source and publication manifests are independently checked when
    supplied; decoder file snapshots require a configured source root.
    """
    return _compile_observation_registry(
        raw_roles,
        decoder_source_manifest_bytes=decoder_source_manifest_bytes,
        decoder_source_root=decoder_source_root,
        publication_manifest_bytes=publication_manifest_bytes,
        limits=limits,
        require_registry=True,
    )


def derive_observation_registry(
    raw_roles: Iterable[tuple[str, bytes]], *, limits: SourceLimits = _DEFAULT_SOURCE_LIMITS
) -> RegistryCompilationReport:
    """Derive authoring commitments without asserting complete package verification."""
    return _compile_observation_registry(
        raw_roles, limits=limits, require_registry=False
    )


def _compile_observation_registry(
    raw_roles: Iterable[tuple[str, bytes]],
    *,
    decoder_source_manifest_bytes: bytes | None = None,
    decoder_source_root: str | os.PathLike[str] | None = None,
    publication_manifest_bytes: bytes | None = None,
    limits: SourceLimits,
    require_registry: bool,
) -> RegistryCompilationReport:
    roles, identities = _source_roles(raw_roles, limits)
    grammar, grammar_bytes = roles["grammar"]
    if grammar != _GRAMMAR_LITERAL:
        _fail("grammar does not equal the complete approved literal")
    profile_id = _ascii_id(grammar["profile_id"], "profile_id")
    profile_version = _positive(grammar["profile_version"], "profile_version")
    grammar_revision = grammar["grammar_revision"]
    if not isinstance(grammar_revision, str):
        _fail("grammar_revision is invalid")
    profile_preimage = _lp(
        "semantic-ingestion-typed-value-profile",
        profile_id,
        profile_version,
        grammar_revision,
        grammar_bytes,
    )
    profile_digest = _sha(profile_preimage)
    grammar_digest = _sha(grammar_bytes)

    grouped: dict[str, dict[tuple[str, str], tuple[dict[str, Any], bytes]]] = {
        kind: {} for kind in _ROLES
    }
    registry: tuple[dict[str, Any], bytes] | None = None
    for role_name, (role, raw) in roles.items():
        if role_name == "grammar":
            continue
        if role_name == "registry":
            if registry is not None:
                _fail("duplicate registry role")
            registry = (role, raw)
            continue
        pieces = role_name.split("/")
        if len(pieces) != 3 or pieces[0] not in _ROLES or pieces[0] != role.get("role"):
            _fail(f"invalid role path {role_name}")
        coordinate = _coordinate(role, role_name)
        if pieces[1:] != [coordinate[0], coordinate[1]]:
            _fail(f"role path does not match declaration {role_name}")
        if coordinate in grouped[pieces[0]]:
            _fail(f"duplicate role coordinate {role_name}")
        grouped[pieces[0]][coordinate] = (role, raw)
    schemas = grouped["schema"]
    if not schemas:
        _fail("no schema roles")
    if (
        set(grouped["enum"]) != set(schemas)
        or set(grouped["optional"]) != set(schemas)
        or set(grouped["numeric"]) != set(schemas)
        or set(grouped["digest-signature"]) != set(schemas)
        or set(grouped["decoder"]) != set(schemas)
        or set(grouped["upcast"]) != set(schemas)
    ):
        _fail("every schema requires exactly one role of each required kind")
    _validate_package_numeric_ids(grouped["numeric"])
    for schema, _ in schemas.values():
        for field in schema["fields"]:
            _validate_unions(field["type"], schemas)

    external: dict[tuple[str, str], tuple[str, str] | None] = {}
    for coordinate, (schema, _) in schemas.items():
        _exact(
            schema,
            {"fields", "role", "root_kind", "schema_id", "schema_version"},
            f"schema {coordinate}",
        )
        if schema["role"] != "schema" or schema["root_kind"] != "model":
            _fail(f"schema {coordinate} is invalid")
        fields = schema["fields"]
        if not isinstance(fields, list):
            _fail(f"schema {coordinate}.fields is invalid")
        _sorted_unique(
            fields,
            lambda item: _text(item.get("name", "")) if isinstance(item, dict) else b"",
            f"schema {coordinate}.fields",
        )
        for field in fields:
            _exact(
                field, {"integrity_role", "name", "type"}, f"schema {coordinate}.field"
            )
            _ascii_id(field["name"], "field name")
            if field["integrity_role"] not in {"ordinary", "self_digest", "signature"}:
                _fail("invalid field integrity role")
            _walk_type(field["type"], set(), set(), set(), "field type")
        policy = grouped["digest-signature"][coordinate][0]
        _exact(
            policy,
            {"policy", "role", "schema_id", "schema_version"},
            f"policy {coordinate}",
        )
        selected = policy["policy"]
        if not isinstance(selected, dict) or selected.get("kind") not in {
            "ordinary",
            "self_digest",
            "signature_only",
            "external_signing_preimage",
        }:
            _fail("invalid policy kind")
        if selected["kind"] == "ordinary":
            _exact(selected, {"kind"}, "ordinary policy")
            if any(field["integrity_role"] != "ordinary" for field in fields):
                _fail("ordinary policy has integrity field")
            external[coordinate] = None
        elif selected["kind"] == "self_digest":
            _exact(
                selected,
                {"kind", "digest_field", "digest_domain"},
                "self digest policy",
            )
            named = [
                field
                for field in fields
                if field["name"] == selected["digest_field"]
                and field["integrity_role"] == "self_digest"
            ]
            if (
                len(named) != 1
                or sum(field["integrity_role"] == "self_digest" for field in fields)
                != 1
                or any(field["integrity_role"] == "signature" for field in fields)
            ):
                _fail("self digest policy does not match fields")
            _ascii_id(selected["digest_domain"], "digest domain")
            external[coordinate] = None
        elif selected["kind"] == "signature_only":
            _exact(
                selected,
                {"kind", "signature_field", "signature_purpose", "signature_domain"},
                "signature policy",
            )
            named = [
                field
                for field in fields
                if field["name"] == selected["signature_field"]
                and field["integrity_role"] == "signature"
            ]
            if (
                len(named) != 1
                or sum(field["integrity_role"] == "signature" for field in fields) != 1
                or any(field["integrity_role"] == "self_digest" for field in fields)
            ):
                _fail("signature policy does not match fields")
            _ascii_id(selected["signature_purpose"], "signature purpose")
            _ascii_id(selected["signature_domain"], "signature domain")
            external[coordinate] = None
        else:
            _exact(
                selected,
                {
                    "kind",
                    "result_digest_field",
                    "result_signature_field",
                    "preimage_schema_id",
                    "preimage_schema_version",
                    "binding_kind",
                    "signature_purpose",
                    "signature_domain",
                },
                "external signing policy",
            )
            if (
                coordinate != ("IngestionObservationReplayCheckpoint", "1")
                or selected["preimage_schema_id"]
                != "ObservationCheckpointSigningPreimage"
                or selected["preimage_schema_version"] != "1"
                or selected["binding_kind"] != "observation_checkpoint_v1"
                or selected["signature_purpose"] != "observation_checkpoint"
            ):
                _fail("external signing policy is not the closed checkpoint exception")
            kinds = {field["name"]: field["integrity_role"] for field in fields}
            if (
                kinds.get(selected["result_digest_field"]) != "self_digest"
                or kinds.get(selected["result_signature_field"]) != "signature"
                or sum(item == "self_digest" for item in kinds.values()) != 1
                or sum(item == "signature" for item in kinds.values()) != 1
            ):
                _fail("external signing fields do not match")
            external[coordinate] = (
                selected["preimage_schema_id"],
                selected["preimage_schema_version"],
            )

    reports: list[RegistryEntryReport] = []
    decoder_snapshots: dict[str, str] = {}
    if decoder_source_manifest_bytes is not None:
        decoder_snapshots = _decoder_snapshots(
            decoder_source_manifest_bytes,
            decoder_source_root,
            profile_id,
            profile_version,
            limits,
        )
    for coordinate in schemas:
        closure = _closure(coordinate, schemas, external)
        refs: set[tuple[str, str]] = set()
        enum_refs: set[str] = set()
        numeric_refs: set[str] = set()
        for item in closure:
            for field in schemas[item][0]["fields"]:
                _walk_type(field["type"], refs, enum_refs, numeric_refs, "schema field")
        enum_names: set[str] = set()
        for item in closure:
            enum_role = grouped["enum"][item][0]
            _exact(
                enum_role, {"enums", "role", "schema_id", "schema_version"}, "enum role"
            )
            if not isinstance(enum_role["enums"], list):
                _fail("enum table invalid")
            _sorted_unique(
                enum_role["enums"],
                lambda enum: (
                    _text(enum.get("qualified_id", ""))
                    if isinstance(enum, dict)
                    else b""
                ),
                "enums",
            )
            for enum in enum_role["enums"]:
                _exact(enum, {"qualified_id", "members"}, "enum")
                qualified = _ascii_id(enum["qualified_id"], "qualified enum")
                enum_names.add(qualified)
                if not isinstance(enum["members"], list):
                    _fail("enum members invalid")
                _sorted_unique(
                    enum["members"],
                    lambda member: (
                        _text(member.get("member_id", ""))
                        if isinstance(member, dict)
                        else b""
                    ),
                    "enum members",
                )
                for member in enum["members"]:
                    _exact(member, {"member_id", "wire_value"}, "enum member")
                    _ascii_id(member["member_id"], "enum member id")
                    if not isinstance(member["wire_value"], str):
                        _fail("enum wire value invalid")
        if not enum_refs <= enum_names:
            _fail(f"unresolved enum in closure {coordinate}")
        _validate_policies(coordinate, closure, grouped, schemas)
        schema_fingerprint = _closure_digest(
            "semantic-ingestion-typed-value-schema-fingerprint",
            None,
            coordinate,
            closure,
            schemas,
        )
        enum_digest = _closure_digest(
            "semantic-ingestion-typed-value-policy-closure",
            "enum",
            coordinate,
            closure,
            grouped["enum"],
        )
        optional_digest = _closure_digest(
            "semantic-ingestion-typed-value-policy-closure",
            "optional",
            coordinate,
            closure,
            grouped["optional"],
        )
        numeric_digest = _closure_digest(
            "semantic-ingestion-typed-value-policy-closure",
            "numeric",
            coordinate,
            closure,
            grouped["numeric"],
        )
        policy_digest = _closure_digest(
            "semantic-ingestion-typed-value-policy-closure",
            "digest-signature",
            coordinate,
            closure,
            grouped["digest-signature"],
        )
        decoder = grouped["decoder"][coordinate][0]
        _exact(
            decoder,
            {
                "decoder_id",
                "implementation_source_digest",
                "role",
                "schema_id",
                "schema_version",
                "typed_root_kind",
            },
            "decoder role",
        )
        decoder_id = _ascii_id(decoder["decoder_id"], "decoder id")
        if decoder["typed_root_kind"] != "model":
            _fail("decoder root kind is invalid")
        declared_snapshot = _digest(
            decoder["implementation_source_digest"], "decoder source digest"
        )
        if decoder_snapshots and decoder_snapshots.get(decoder_id) != declared_snapshot:
            _fail(f"decoder source snapshot mismatch for {decoder_id}")
        decoder_digest = _sha(
            _lp(
                "semantic-ingestion-typed-value-decoder",
                decoder_id,
                "model",
                declared_snapshot,
            )
        )
        upcast = grouped["upcast"][coordinate][0]
        _exact(
            upcast,
            {
                "implementation_source_digest",
                "role",
                "schema_id",
                "schema_version",
                "target_binding",
                "upcaster_id",
            },
            "upcast role",
        )
        if (
            upcast["target_binding"] is not None
            or upcast["upcaster_id"] is not None
            or upcast["implementation_source_digest"] is not None
        ):
            _fail("profile-3 upcast is not null-only")
        binding = _sha(
            _lp(
                "semantic-ingestion-typed-value-binding",
                profile_id,
                profile_version,
                profile_digest,
                coordinate[0],
                coordinate[1],
                schema_fingerprint,
                enum_digest,
                optional_digest,
                numeric_digest,
                policy_digest,
            )
        )
        preimage = _lp(
            "semantic-ingestion-typed-value-registry-entry",
            profile_id,
            profile_version,
            profile_digest,
            coordinate[0],
            coordinate[1],
            binding,
            schema_fingerprint,
            enum_digest,
            optional_digest,
            numeric_digest,
            policy_digest,
            decoder_digest,
            "0",
            b"",
            b"",
            "active",
        )
        reports.append(
            RegistryEntryReport(
                coordinate[0],
                coordinate[1],
                schema_fingerprint,
                enum_digest,
                optional_digest,
                numeric_digest,
                policy_digest,
                decoder_digest,
                binding,
                _sha(preimage),
                preimage,
            )
        )
    reports.sort(
        key=lambda item: (
            _text(profile_id),
            int(profile_version),
            _text(item.schema_id),
            int(item.schema_version),
        )
    )
    registry_preimage = _lp(
        "semantic-ingestion-typed-value-registry",
        profile_id,
        profile_version,
        grammar_revision,
        grammar_digest,
        profile_digest,
        str(len(reports)),
        *(entry.entry_digest for entry in reports),
    )
    registry_digest = _sha(registry_preimage)
    if registry is None and require_registry:
        _fail("complete compilation requires exactly one registry role")
    if registry is not None:
        _validate_registry_role(
            registry[0],
            profile_id,
            profile_version,
            grammar_revision,
            grammar_digest,
            profile_digest,
            reports,
        )
    publication_digest = None
    if publication_manifest_bytes is not None:
        publication_digest = _validate_publication_manifest(
            publication_manifest_bytes,
            profile_id,
            profile_version,
            identities,
            decoder_source_manifest_bytes,
            decoder_snapshots,
            registry_digest,
            limits,
        )
    return RegistryCompilationReport(
        profile_digest,
        profile_preimage,
        registry_digest,
        registry_preimage,
        tuple(reports),
        identities,
        decoder_source_manifest_bytes,
        publication_manifest_bytes,
        publication_digest,
    )


def _validate_package_numeric_ids(
    numeric_roles: Mapping[tuple[str, str], tuple[dict[str, Any], bytes]],
) -> None:
    """The decimal encoding identifier is package-wide, not closure-local."""
    ids: set[str] = set()
    for role, _ in numeric_roles.values():
        rows = role.get("fields")
        if not isinstance(rows, list):
            continue  # The role-local shape check supplies the typed failure.
        for row in rows:
            if (
                isinstance(row, dict)
                and row.get("representation") == "canonical_decimal_quantity"
            ):
                identifier = row.get("encoding_spec_id")
                if isinstance(identifier, str):
                    if identifier in ids:
                        _fail("decimal encoding ID is repeated in source package")
                    ids.add(identifier)


def _validate_unions(
    expr: Any, schemas: Mapping[tuple[str, str], tuple[dict[str, Any], bytes]]
) -> None:
    """Check the grammar's finite discriminator promise without model reflection."""
    if not isinstance(expr, dict):
        return
    kind = expr.get("kind")
    if kind == "union":
        discriminator = expr["discriminator"]
        for alternative in expr["alternatives"]:
            model = alternative["model"]
            coordinate = (model["schema_id"], model["schema_version"])
            target = schemas.get(coordinate)
            if target is None:
                continue  # closure reports the unresolved coordinate deterministically.
            candidates = [
                field for field in target[0]["fields"] if field["name"] == discriminator
            ]
            if len(candidates) != 1:
                _fail("union discriminator is absent from an alternative")
            field_type = candidates[0]["type"]
            if field_type.get("kind") != "literal" or field_type.get("values") != [
                alternative["discriminator_value"]
            ]:
                _fail(
                    "union discriminator alternative is not a singleton string literal"
                )
        return
    for key in ("element", "value"):
        if key in expr:
            _validate_unions(expr[key], schemas)
    if kind == "fixed_tuple":
        for item in expr["items"]:
            _validate_unions(item, schemas)


def _validate_decimal_bound(value: Any, label: str, scale: str) -> None:
    """Validate the closed decimal bound grammar at its declared fixed scale."""
    if not isinstance(value, str) or not value or not value.isascii():
        _fail(f"{label} is not canonical decimal text")
    negative = value.startswith("-")
    text = value[1:] if negative else value
    if text.count(".") != 1:
        _fail(f"{label} is not canonical decimal text")
    whole, dot, fraction = text.partition(".")
    if (
        not whole
        or (dot and not fraction)
        or not whole.isdecimal()
        or (dot and not fraction.isdecimal())
    ):
        _fail(f"{label} is not canonical decimal text")
    if (len(whole) > 1 and whole[0] == "0") or (
        negative and whole == "0" and (not dot or set(fraction) == {"0"})
    ):
        _fail(f"{label} is not canonical decimal text")
    if str(len(fraction)) != scale:
        _fail(f"{label} does not use the declared fixed scale")


def _validate_policies(
    root: tuple[str, str],
    closure: tuple[tuple[str, str], ...],
    grouped: Mapping[str, Mapping[tuple[str, str], tuple[dict[str, Any], bytes]]],
    schemas: Mapping[tuple[str, str], tuple[dict[str, Any], bytes]],
) -> None:
    decimal_ids: set[str] = set()
    for coordinate in closure:
        names = [field["name"] for field in schemas[coordinate][0]["fields"]]
        optional = grouped["optional"][coordinate][0]
        _exact(
            optional, {"fields", "role", "schema_id", "schema_version"}, "optional role"
        )
        fields = optional["fields"]
        if not isinstance(fields, list):
            _fail("optional fields invalid")
        _sorted_unique(
            fields,
            lambda item: (
                _text(item.get("field_name", "")) if isinstance(item, dict) else b""
            ),
            "optional fields",
        )
        for field in fields:
            _exact(field, {"field_name", "policy"}, "optional field")
            _ascii_id(field["field_name"], "optional field name")
        if [item.get("field_name") for item in fields] != names or any(
            item.get("policy")
            not in {
                "required",
                "omittable_nonnull",
                "required_nullable",
                "omittable_nullable",
            }
            for item in fields
            if isinstance(item, dict)
        ):
            _fail("optional fields do not exactly match schema")
        expected_numeric: dict[str, str] = {}
        for field in schemas[coordinate][0]["fields"]:
            field_type = field["type"]
            if field_type["kind"] in {
                "canonical_decimal_quantity",
                "canonical_finite_binary64",
            }:
                if field_type["field_name"] != field["name"]:
                    _fail("numeric wrapper must name its owning root-model field")
                expected_numeric[field["name"]] = field_type["kind"]
            nested: set[str] = set()
            _walk_type(field_type, set(), set(), nested, "field")
            if nested - set(expected_numeric):
                _fail("numeric wrapper is not a direct owning root-model field")
        numeric = grouped["numeric"][coordinate][0]
        _exact(
            numeric, {"fields", "role", "schema_id", "schema_version"}, "numeric role"
        )
        rows = numeric["fields"]
        if not isinstance(rows, list):
            _fail("numeric rows invalid")
        _sorted_unique(
            rows,
            lambda item: (
                _text(item.get("field_name", "")) if isinstance(item, dict) else b""
            ),
            "numeric rows",
        )
        if {row.get("field_name") for row in rows if isinstance(row, dict)} != set(
            expected_numeric
        ):
            _fail("numeric fields do not match numeric wrappers")
        for row in rows:
            _exact(
                row,
                {
                    "encoding_spec_id",
                    "field_name",
                    "lower",
                    "lower_inclusive",
                    "reject_inexact",
                    "representation",
                    "scale",
                    "unit",
                    "upper",
                    "upper_inclusive",
                },
                "numeric row",
            )
            if row["representation"] == "canonical_decimal_quantity":
                if (
                    expected_numeric.get(row["field_name"])
                    != "canonical_decimal_quantity"
                ):
                    _fail("decimal row does not match its owning field")
                ident = _ascii_id(row["encoding_spec_id"], "decimal encoding id")
                if ident in decimal_ids:
                    _fail("duplicate decimal encoding ID")
                decimal_ids.add(ident)
                scale = _positive(row["scale"], "decimal scale")
                if (
                    not isinstance(row["unit"], str)
                    or row["lower"] is None
                    or row["upper"] is None
                    or not isinstance(row["lower_inclusive"], bool)
                    or not isinstance(row["upper_inclusive"], bool)
                    or not isinstance(row["reject_inexact"], bool)
                ):
                    _fail("decimal numeric row is incomplete")
                _validate_decimal_bound(row["lower"], "decimal lower bound", scale)
                _validate_decimal_bound(row["upper"], "decimal upper bound", scale)
            elif row["representation"] == "canonical_finite_binary64":
                if (
                    expected_numeric.get(row["field_name"])
                    != "canonical_finite_binary64"
                ):
                    _fail("binary64 row does not match its owning field")
                if any(
                    row[key] is not None
                    for key in {
                        "encoding_spec_id",
                        "unit",
                        "scale",
                        "lower",
                        "lower_inclusive",
                        "upper",
                        "upper_inclusive",
                        "reject_inexact",
                    }
                ):
                    _fail("binary64 numeric row has forbidden values")
            else:
                _fail("unknown numeric representation")


def _validate_registry_role(
    role: Mapping[str, Any],
    profile_id: str,
    profile_version: str,
    revision: str,
    grammar_digest: str,
    profile_digest: str,
    reports: list[RegistryEntryReport],
) -> None:
    _exact(role, {"entries", "profile", "role"}, "registry role")
    if (
        role["role"] != "registry"
        or not isinstance(role["profile"], dict)
        or not isinstance(role["entries"], list)
    ):
        _fail("registry role invalid")
    profile = role["profile"]
    _exact(
        profile,
        {
            "grammar_digest",
            "grammar_revision",
            "profile_digest",
            "profile_id",
            "profile_version",
        },
        "registry profile",
    )
    if profile != {
        "profile_id": profile_id,
        "profile_version": profile_version,
        "grammar_revision": revision,
        "grammar_digest": grammar_digest,
        "profile_digest": profile_digest,
    }:
        _fail("registry profile does not match grammar")
    if role["entries"] != [report.entry_digest for report in reports]:
        _fail("registry entries do not match derived entries")


def _decoder_snapshots(
    raw: bytes,
    root: str | os.PathLike[str] | None,
    profile_id: str,
    profile_version: str,
    limits: SourceLimits,
) -> dict[str, str]:
    if root is None:
        _fail("decoder source manifest requires decoder_source_root")
    manifest = _parse(raw, "decoder source manifest", limits)
    _exact(
        manifest,
        {"files", "profile_id", "profile_version", "role"},
        "decoder source manifest",
    )
    if (
        manifest["role"] != "decoder_source_manifest"
        or manifest["profile_id"] != profile_id
        or manifest["profile_version"] != profile_version
        or not isinstance(manifest["files"], list)
        or not manifest["files"]
    ):
        _fail("decoder source manifest identity is invalid")
    root_text = os.fspath(root)
    base = Path(root_text)
    if not base.is_absolute():
        _fail("decoder source root must be an absolute path")
    if os.path.normpath(root_text) != root_text or os.path.realpath(root_text) != root_text:
        _fail("decoder source root is not canonical")
    if "observation_registry_sources" in base.parts:
        _fail("generated decoder source namespace is forbidden")
    rows = manifest["files"]
    _sorted_unique(
        rows,
        lambda row: (
            (_text(row.get("decoder_id", "")), _text(row.get("source_file_id", "")))
            if isinstance(row, dict)
            else (b"", b"")
        ),
        "decoder source rows",
    )
    selected: dict[str, list[tuple[str, str, bytes]]] = {}
    seen_pairs: set[tuple[str, str]] = set()
    seen_decoder_paths: set[tuple[str, str]] = set()
    paths: dict[str, tuple[str, bytes]] = {}
    for row in rows:
        _exact(
            row,
            {"decoder_id", "relative_path", "sha256", "source_file_id"},
            "decoder source row",
        )
        decoder_id = _ascii_id(row["decoder_id"], "decoder id")
        file_id = _ascii_id(row["source_file_id"], "source file id")
        digest = _digest(row["sha256"], "source file digest")
        path = row["relative_path"]
        if (
            not isinstance(path, str)
            or not path.isascii()
            or not path
            or path.endswith("/")
            or any(
                not piece
                or piece in {".", ".."}
                or any(
                    ch
                    not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-"
                    for ch in piece
                )
                for piece in path.split("/")
            )
        ):
            _fail("invalid decoder relative path")
        pieces = path.split("/")
        if "observation_registry_sources" in pieces:
            _fail("generated decoder source namespace is forbidden")
        if (decoder_id, file_id) in seen_pairs or (
            decoder_id,
            path,
        ) in seen_decoder_paths:
            _fail("duplicate decoder source pair")
        seen_pairs.add((decoder_id, file_id))
        seen_decoder_paths.add((decoder_id, path))
        content = _read_decoder_source(base, pieces, limits)
        if _sha(content) != digest:
            _fail("decoder source file digest mismatch")
        previous = paths.get(path)
        if previous is not None and previous != (file_id, content):
            _fail("shared decoder path has conflicting source ID or bytes")
        paths[path] = (file_id, content)
        selected.setdefault(decoder_id, []).append((file_id, path, content))
    snapshots: dict[str, str] = {}
    for decoder_id, files in selected.items():
        files.sort(key=lambda item: (_text(item[0]), _text(item[1])))
        parts: list[str | bytes] = [
            "semantic-ingestion-profile3-decoder-source-snapshot",
            decoder_id,
            str(len(files)),
        ]
        for file_id, path, content in files:
            parts.extend([file_id, path, content])
        snapshots[decoder_id] = _sha(_lp(*parts))
    return snapshots


def _read_decoder_source(base: Path, pieces: list[str], limits: SourceLimits) -> bytes:
    """Read one regular source file through a no-follow descriptor traversal."""
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    file_flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    directory_fd: int | None = None
    file_fd: int | None = None
    try:
        directory_fd = _open_canonical_source_root(base, directory_flags)
        for piece in pieces[:-1]:
            next_fd = os.open(piece, directory_flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_fd
        file_fd = os.open(pieces[-1], file_flags, dir_fd=directory_fd)
        metadata = os.fstat(file_fd)
        if not stat.S_ISREG(metadata.st_mode):
            _fail("decoder source is not a regular file")
        if metadata.st_size > limits.max_raw_bytes:
            _fail("decoder source file exceeds protected raw-byte limit")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(file_fd, min(65_536, limits.max_raw_bytes - total + 1))
            if not chunk:
                break
            total += len(chunk)
            if total > limits.max_raw_bytes:
                _fail("decoder source file exceeds protected raw-byte limit")
            chunks.append(chunk)
        content = b"".join(chunks)
        content.decode("utf-8", "strict")
        return content
    except (OSError, UnicodeError) as exc:
        raise RegistrySourceError("decoder source file cannot be read") from exc
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if directory_fd is not None:
            os.close(directory_fd)


def _open_canonical_source_root(base: Path, directory_flags: int) -> int:
    """Open every absolute-root component without following an ancestor alias."""
    directory_fd = os.open(base.anchor, directory_flags)
    try:
        for piece in base.parts[1:]:
            next_fd = os.open(piece, directory_flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_fd
        return directory_fd
    except BaseException:
        os.close(directory_fd)
        raise


def _validate_publication_manifest(
    raw: bytes,
    profile_id: str,
    profile_version: str,
    identities: tuple[SourceIdentity, ...],
    decoder_manifest: bytes | None,
    snapshots: Mapping[str, str],
    registry_digest: str,
    limits: SourceLimits,
) -> str:
    if decoder_manifest is None:
        _fail("publication manifest requires decoder source manifest")
    manifest = _parse(raw, "publication manifest", limits)
    _exact(
        manifest,
        {
            "decoder_source_manifest_digest",
            "decoder_source_snapshots",
            "files",
            "profile_id",
            "profile_version",
            "registry_digest",
            "role",
        },
        "publication manifest",
    )
    if (
        manifest["role"] != "publication_manifest"
        or manifest["profile_id"] != profile_id
        or manifest["profile_version"] != profile_version
        or manifest["decoder_source_manifest_digest"] != _sha(decoder_manifest)
        or manifest["registry_digest"] != registry_digest
    ):
        _fail("publication manifest identity mismatch")
    expected_files = [{"role": item.role, "sha256": item.sha256} for item in identities]
    expected_snapshots = [
        {"decoder_id": key, "source_snapshot_digest": snapshots[key]}
        for key in sorted(snapshots, key=_text)
    ]
    if (
        manifest["files"] != expected_files
        or manifest["decoder_source_snapshots"] != expected_snapshots
    ):
        _fail("publication manifest members mismatch")
    parts: list[str | bytes] = [
        "semantic-ingestion-profile3-publication-manifest",
        profile_id,
        profile_version,
        str(len(expected_files)),
    ]
    for item in expected_files:
        parts.extend([item["role"], item["sha256"]])
    parts.extend([_sha(decoder_manifest), str(len(expected_snapshots))])
    for item in expected_snapshots:
        parts.extend([item["decoder_id"], item["source_snapshot_digest"]])
    parts.append(registry_digest)
    return _sha(_lp(*parts))
