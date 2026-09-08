"""Validate one protected profile-3 CTV model body against a compiled entry.

This is deliberately a source-directed tree validator.  It does not select an
entry, import a decoder, construct native models, or materialize defaults.
Those responsibilities remain at the protected envelope/composition boundary.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime

from memorii.core.memory_evolution.typed_numeric_values import (
    ProtectedTypedNumericValueLimits,
    TypedNumericValueError,
    decode_typed_numeric_value,
)
from memorii.core.memory_evolution.typed_value_declarations import (
    CollectionTypeExpr,
    DigestSignatureRole,
    EnumDeclaration,
    EnumRefTypeExpr,
    EnumRole,
    ExternalSigningPreimagePolicy,
    FixedTupleTypeExpr,
    IntegerTypeExpr,
    LiteralInteger,
    LiteralTypeExpr,
    MapTypeExpr,
    ModelRefTypeExpr,
    NamedFieldTypeExpr,
    NumericFieldDeclaration,
    NumericRole,
    OptionalRole,
    ScalarTypeExpr,
    SchemaRole,
    TypeExpr,
    UnionTypeExpr,
)
from memorii.core.memory_evolution.typed_value_decoder_sources import (
    DecoderSourceManifestError,
    FrozenJsonValue,
    ProtectedDecoderSourceManifestLimits,
    parse_canonical_raw_json_object,
)
from memorii.core.memory_evolution.typed_value_registry_compilation import (
    CompiledRegistryEntry,
    CompiledTypedValueRegistry,
)

_INTEGER = re.compile(r"(?:0|-?[1-9][0-9]*)\Z")
_HEX = re.compile(r"[0-9a-f]+\Z")
_UTC_DATETIME = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})\.([0-9]{6})Z\Z")
_I64_MIN = "-9223372036854775808"
_I64_MAX = "9223372036854775807"


class TypedValueBodyValidationError(ValueError):
    """A CTV body violates the selected immutable entry's closed schema."""


@dataclass(frozen=True)
class ProtectedTypedValueBodyLimits:
    maximum_bytes: int
    maximum_nodes: int
    maximum_depth: int

    def __post_init__(self) -> None:
        if any(type(item) is not int or item <= 0 for item in (self.maximum_bytes, self.maximum_nodes, self.maximum_depth)):
            raise ValueError("typed_value_body_limits_must_be_positive")


@dataclass(frozen=True)
class ValidatedTypedValueBody:
    """Immutable raw body, selected entry, and validated frozen CTV tree."""

    raw_bytes: bytes
    entry: CompiledRegistryEntry
    tree: Mapping[str, FrozenJsonValue]


def validate_typed_value_body(
    raw_bytes: bytes,
    *,
    registry: CompiledTypedValueRegistry,
    entry: CompiledRegistryEntry,
    limits: ProtectedTypedValueBodyLimits,
) -> ValidatedTypedValueBody:
    """Validate exactly one root model body under an already selected entry."""
    try:
        if registry.entry_for(entry.schema_id, entry.schema_version) != entry:
            raise TypedValueBodyValidationError("typed_value_body_entry_not_registry_member")
        parsed = parse_canonical_raw_json_object(raw_bytes, limits=_raw_limits(limits))
        schema, optionals, numerics, _ = _roles_for_entry(registry, entry)
        _validate_model(
            parsed.value,
            schema,
            optionals,
            numerics,
            _reachable_coordinates(registry, (entry.schema_id, entry.schema_version)),
            registry,
            limits,
            "body",
        )
        return ValidatedTypedValueBody(raw_bytes=parsed.raw_bytes, entry=entry, tree=parsed.value)
    except RecursionError as exc:
        raise TypedValueBodyValidationError("typed_value_body_depth_limit_exceeded") from exc
    except DecoderSourceManifestError as exc:
        raise TypedValueBodyValidationError("typed_value_body_raw_invalid") from exc


def _raw_limits(limits: ProtectedTypedValueBodyLimits) -> ProtectedDecoderSourceManifestLimits:
    return ProtectedDecoderSourceManifestLimits(limits.maximum_bytes, limits.maximum_nodes, limits.maximum_depth, 1, limits.maximum_bytes)


def _roles_for_entry(
    registry: CompiledTypedValueRegistry, entry: CompiledRegistryEntry
) -> tuple[SchemaRole, OptionalRole, NumericRole, EnumRole]:
    coordinate = (entry.schema_id, entry.schema_version)
    role_items = (SchemaRole, OptionalRole, NumericRole, EnumRole)
    roles = {
        (item.schema_id, item.schema_version, item.role): item
        for item in registry.parsed_roles
        if isinstance(item, role_items)
    }
    try:
        schema = roles[(*coordinate, "schema")]
        optionals = roles[(*coordinate, "optional")]
        numerics = roles[(*coordinate, "numeric")]
        enums = roles[(*coordinate, "enum")]
    except KeyError as exc:
        raise TypedValueBodyValidationError("typed_value_body_registry_roles_incomplete") from exc
    if not isinstance(schema, SchemaRole) or not isinstance(optionals, OptionalRole) or not isinstance(numerics, NumericRole) or not isinstance(enums, EnumRole):
        raise TypedValueBodyValidationError("typed_value_body_registry_roles_invalid")
    return schema, optionals, numerics, enums


def _validate_model(
    value: FrozenJsonValue, schema: SchemaRole, optionals: OptionalRole, numerics: NumericRole,
    reachable: frozenset[tuple[str, str]], registry: CompiledTypedValueRegistry, limits: ProtectedTypedValueBodyLimits, path: str,
) -> None:
    entries = _tagged_entries(value, "map", path)
    declared = {field.name: field for field in schema.fields}
    policies = {field.field_name: field.policy for field in optionals.fields}
    received = {key for key, _ in entries}
    # Omission is policy-driven; null is separately checked below and never
    # becomes an implicit omitted/defaulted field.
    required = {key for key, policy in policies.items() if not policy.startswith("omittable")}
    if received - set(declared) or not required <= received:
        raise TypedValueBodyValidationError(f"{path}_fields_invalid")
    numeric_by_field = {field.field_name: field for field in numerics.fields}
    for name, child in entries:
        policy = policies[name]
        if child is None:
            if policy not in {"required_nullable", "omittable_nullable"}:
                raise TypedValueBodyValidationError(f"{path}.{name}_null_forbidden")
            continue
        _validate_value(child, declared[name].type, numeric_by_field.get(name), reachable, registry, limits, f"{path}.{name}")


def _validate_value(value: FrozenJsonValue, expression: TypeExpr, numeric: NumericFieldDeclaration | None,
                    reachable: frozenset[tuple[str, str]], registry: CompiledTypedValueRegistry, limits: ProtectedTypedValueBodyLimits, path: str) -> None:
    if isinstance(expression, ScalarTypeExpr):
        _validate_scalar(value, expression, path)
    elif isinstance(expression, LiteralTypeExpr):
        if not _literal_matches(value, expression):
            raise TypedValueBodyValidationError(f"{path}_literal_invalid")
    elif isinstance(expression, IntegerTypeExpr):
        integer = _tagged_scalar(value, "integer", path)
        _require_integer(integer, path)
        if expression.minimum is not None and _integer_compare(integer, expression.minimum) < 0:
            raise TypedValueBodyValidationError(f"{path}_integer_below_minimum")
        if expression.maximum is not None and _integer_compare(integer, expression.maximum) > 0:
            raise TypedValueBodyValidationError(f"{path}_integer_above_maximum")
    elif isinstance(expression, NamedFieldTypeExpr):
        if numeric is None or numeric.representation != expression.kind:
            raise TypedValueBodyValidationError(f"{path}_numeric_declaration_invalid")
        try:
            decode_typed_numeric_value(_canonical_bytes(value), numeric, limits=ProtectedTypedNumericValueLimits(limits.maximum_bytes, limits.maximum_nodes, limits.maximum_depth))
        except TypedNumericValueError as exc:
            raise TypedValueBodyValidationError(f"{path}_numeric_invalid") from exc
    elif isinstance(expression, EnumRefTypeExpr):
        data = _tagged_object(value, "enum", {"$type", "enum_type", "member"}, path)
        if data["enum_type"] != expression.qualified_id or not isinstance(data["member"], str):
            raise TypedValueBodyValidationError(f"{path}_enum_invalid")
        enum = _registered_enum(registry, reachable, expression.qualified_id)
        if enum is None or data["member"] not in {item.member_id for item in enum.members}:
            raise TypedValueBodyValidationError(f"{path}_enum_member_invalid")
    elif isinstance(expression, ModelRefTypeExpr):
        nested = registry.entry_for(expression.schema_id, expression.schema_version)
        schema, optionals, numerics, _ = _roles_for_entry(registry, nested)
        _validate_model(value, schema, optionals, numerics, reachable, registry, limits, path)
    elif isinstance(expression, CollectionTypeExpr):
        tag = "tuple" if expression.kind == "variadic_tuple" else expression.kind
        items = _tagged_items(value, tag, path)
        if expression.kind in {"set", "frozenset"}:
            encoded = tuple(_canonical_bytes(item) for item in items)
            if encoded != tuple(sorted(encoded)) or len(encoded) != len(set(encoded)):
                raise TypedValueBodyValidationError(f"{path}_collection_order_invalid")
        for index, child in enumerate(items):
            _validate_value(child, expression.element, None, reachable, registry, limits, f"{path}[{index}]")
    elif isinstance(expression, FixedTupleTypeExpr):
        items = _tagged_items(value, "tuple", path)
        if len(items) != len(expression.items):
            raise TypedValueBodyValidationError(f"{path}_tuple_arity_invalid")
        for index, (child, item_expression) in enumerate(zip(items, expression.items, strict=True)):
            _validate_value(child, item_expression, None, reachable, registry, limits, f"{path}[{index}]")
    elif isinstance(expression, MapTypeExpr):
        for key, child in _tagged_entries(value, "map", path):
            _validate_value(child, expression.value, None, reachable, registry, limits, f"{path}.{key}")
    elif isinstance(expression, UnionTypeExpr):
        entries = dict(_tagged_entries(value, "map", path))
        discriminator = entries.get(expression.discriminator)
        if not isinstance(discriminator, str):
            raise TypedValueBodyValidationError(f"{path}_union_discriminator_invalid")
        alternative = next((item for item in expression.alternatives if item.discriminator_value == discriminator), None)
        if alternative is None:
            raise TypedValueBodyValidationError(f"{path}_union_member_invalid")
        _validate_value(value, alternative.model, None, reachable, registry, limits, path)
    else:  # pragma: no cover - declarations parse a closed hierarchy
        raise TypedValueBodyValidationError(f"{path}_type_expression_unknown")


def _registered_enum(
    registry: CompiledTypedValueRegistry,
    reachable: frozenset[tuple[str, str]],
    qualified_id: str,
) -> EnumDeclaration | None:
    matches = [
        enum
        for role in registry.parsed_roles
        if isinstance(role, EnumRole)
        and (role.schema_id, role.schema_version) in reachable
        for enum in role.enums
        if enum.qualified_id == qualified_id
    ]
    return matches[0] if len(matches) == 1 else None


def _reachable_coordinates(
    registry: CompiledTypedValueRegistry, root: tuple[str, str]
) -> frozenset[tuple[str, str]]:
    schemas = {
        (role.schema_id, role.schema_version): role
        for role in registry.parsed_roles
        if isinstance(role, SchemaRole)
    }
    policies = {
        (role.schema_id, role.schema_version): role
        for role in registry.parsed_roles
        if isinstance(role, DigestSignatureRole)
    }
    seen: set[tuple[str, str]] = set()
    pending = [root]
    while pending:
        coordinate = pending.pop()
        if coordinate in seen:
            continue
        schema = schemas.get(coordinate)
        if schema is None:
            raise TypedValueBodyValidationError("typed_value_body_registry_roles_incomplete")
        seen.add(coordinate)
        for expression in _walk_type_expressions(field.type for field in schema.fields):
            if isinstance(expression, ModelRefTypeExpr):
                pending.append((expression.schema_id, expression.schema_version))
        policy = policies.get(coordinate)
        if policy is None:
            raise TypedValueBodyValidationError("typed_value_body_registry_roles_incomplete")
        if isinstance(policy.policy, ExternalSigningPreimagePolicy):
            pending.append(
                (
                    policy.policy.preimage_schema_id,
                    policy.policy.preimage_schema_version,
                )
            )
    return frozenset(seen)


def _walk_type_expressions(expressions: Iterable[TypeExpr]) -> tuple[TypeExpr, ...]:
    pending = list(expressions)
    found: list[TypeExpr] = []
    while pending:
        current = pending.pop()
        found.append(current)
        if isinstance(current, CollectionTypeExpr):
            pending.append(current.element)
        elif isinstance(current, FixedTupleTypeExpr):
            pending.extend(current.items)
        elif isinstance(current, MapTypeExpr):
            pending.append(current.value)
        elif isinstance(current, UnionTypeExpr):
            pending.extend(item.model for item in current.alternatives)
    return tuple(found)


def _validate_scalar(value: FrozenJsonValue, expression: ScalarTypeExpr, path: str) -> None:
    if expression.kind == "bool":
        if type(value) is not bool:
            raise TypedValueBodyValidationError(f"{path}_bool_invalid")
    elif expression.kind == "null":
        if value is not None:
            raise TypedValueBodyValidationError(f"{path}_null_invalid")
    elif expression.kind == "string":
        if not isinstance(value, str) or (expression.lexical_rule == "nonempty_unicode_scalar" and not value) or (expression.lexical_rule == "sha256" and not (_HEX.fullmatch(value) and len(value) == 64)) or (expression.lexical_rule == "signature_hex128" and not (_HEX.fullmatch(value) and len(value) == 128)):
            raise TypedValueBodyValidationError(f"{path}_string_invalid")
    elif expression.kind == "bytes":
        encoded = _tagged_scalar(value, "bytes", path)
        try:
            if base64.b64encode(base64.b64decode(encoded, validate=True)).decode("ascii") != encoded:
                raise ValueError
        except (ValueError, binascii.Error, UnicodeEncodeError) as exc:
            raise TypedValueBodyValidationError(f"{path}_bytes_invalid") from exc
    elif expression.kind == "datetime":
        text = _tagged_scalar(value, "datetime", path)
        match = _UTC_DATETIME.fullmatch(text)
        if match is None:
            raise TypedValueBodyValidationError(f"{path}_datetime_invalid")
        try:
            year, month, day, hour, minute, second, microsecond = (
                int(component) for component in match.groups()
            )
            datetime(year, month, day, hour, minute, second, microsecond)
        except ValueError as exc:
            raise TypedValueBodyValidationError(f"{path}_datetime_invalid") from exc
    elif expression.kind == "duration_microseconds":
        text = _tagged_scalar(value, "duration_microseconds", path)
        _require_integer(text, path)
        if _integer_compare(text, _I64_MIN) < 0 or _integer_compare(text, _I64_MAX) > 0:
            raise TypedValueBodyValidationError(f"{path}_duration_range_invalid")
    else:
        raise TypedValueBodyValidationError(f"{path}_scalar_invalid")


def _literal_matches(value: FrozenJsonValue, expression: LiteralTypeExpr) -> bool:
    for literal in expression.values:
        if isinstance(literal, LiteralInteger):
            if isinstance(value, Mapping) and _tagged_scalar(value, "integer", "literal") == literal.value:
                return True
        elif type(value) is type(literal) and value == literal:
            return True
    return False


def _tagged_scalar(value: FrozenJsonValue, tag: str, path: str) -> str:
    data = _tagged_object(value, tag, {"$type", "value"}, path)
    result = data["value"]
    if not isinstance(result, str):
        raise TypedValueBodyValidationError(f"{path}_{tag}_value_invalid")
    return result


def _tagged_items(value: FrozenJsonValue, tag: str, path: str) -> tuple[FrozenJsonValue, ...]:
    data = _tagged_object(value, tag, {"$type", "items"}, path)
    if not isinstance(data["items"], tuple):
        raise TypedValueBodyValidationError(f"{path}_{tag}_items_invalid")
    return data["items"]


def _tagged_entries(value: FrozenJsonValue, tag: str, path: str) -> tuple[tuple[str, FrozenJsonValue], ...]:
    data = _tagged_object(value, tag, {"$type", "entries"}, path)
    source = data["entries"]
    if not isinstance(source, tuple):
        raise TypedValueBodyValidationError(f"{path}_{tag}_entries_invalid")
    entries: list[tuple[str, FrozenJsonValue]] = []
    for item in source:
        if not isinstance(item, tuple) or len(item) != 2 or not isinstance(item[0], str):
            raise TypedValueBodyValidationError(f"{path}_{tag}_entry_invalid")
        entries.append((item[0], item[1]))
    keys = tuple(key for key, _ in entries)
    ordered = tuple(sorted(keys, key=lambda key: _canonical_bytes(key)))
    if keys != ordered or len(keys) != len(set(keys)):
        raise TypedValueBodyValidationError(f"{path}_{tag}_key_order_invalid")
    return tuple(entries)


def _tagged_object(value: FrozenJsonValue, tag: str, keys: set[str], path: str) -> Mapping[str, FrozenJsonValue]:
    if not isinstance(value, Mapping) or set(value) != keys or value.get("$type") != tag:
        raise TypedValueBodyValidationError(f"{path}_{tag}_shape_invalid")
    return value


def _require_integer(value: str, path: str) -> None:
    if not _INTEGER.fullmatch(value):
        raise TypedValueBodyValidationError(f"{path}_integer_lexical_invalid")


def _integer_compare(left: str, right: str) -> int:
    left_negative, right_negative = left.startswith("-"), right.startswith("-")
    if left_negative != right_negative:
        return -1 if left_negative else 1
    left_digits, right_digits = left.removeprefix("-"), right.removeprefix("-")
    result = (len(left_digits) > len(right_digits)) - (len(left_digits) < len(right_digits))
    if result == 0:
        result = (left_digits > right_digits) - (left_digits < right_digits)
    return -result if left_negative else result


def _canonical_bytes(value: FrozenJsonValue) -> bytes:
    return json.dumps(_thaw(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8", "strict")


def _thaw(value: FrozenJsonValue) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value
