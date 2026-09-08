"""Materialize an already validated profile-3 body into a native model.

This owner deliberately stops before envelope authentication.  It joins a
validated body to a verified publication, converts its declared CTV tree, and
then calls the finite native decoder table.  Self-digest, signature, external
native-authority, and persistence checks belong to the protected envelope
owner that will call this code.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import cmp_to_key
from itertools import zip_longest
from typing import cast

from pydantic import BaseModel

from memorii.core.memory_evolution.ingestion_contracts import decode_native_observation
from memorii.core.memory_evolution.typed_numeric_values import (
    CanonicalDecimalQuantity,
    CanonicalFiniteBinary64,
    ProtectedTypedNumericValueLimits,
    TypedNumericValueError,
    decode_typed_numeric_value,
    encode_typed_numeric_value,
)
from memorii.core.memory_evolution.typed_value_body_validation import (
    ProtectedTypedValueBodyLimits,
    TypedValueBodyValidationError,
    ValidatedTypedValueBody,
    validate_typed_value_body,
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
from memorii.core.memory_evolution.typed_value_publication import VerifiedTypedValuePublication
from memorii.core.memory_evolution.typed_value_registry_compilation import (
    CompiledRegistryEntry,
    CompiledTypedValueRegistry,
)
from memorii.domain.enums import SourceModality


class TypedValueModelCodecError(ValueError):
    """A validated body cannot be joined to or represented by its native model."""


@dataclass(frozen=True)
class MaterializedTypedValueModel:
    """A native value plus the exact validated body needed for lossless reencoding.

    This is an internal conversion result.  It is not authenticated, signed,
    authoritative, or persistable merely because native construction passed.
    """

    body: ValidatedTypedValueBody
    value: BaseModel
    present_fields: frozenset[str]


_SOURCE_MODALITY_ENUM_ID = "memorii.domain.SourceModality"
_SOURCE_MODALITY_BY_MEMBER: Mapping[str, SourceModality] = {
    "ASSERTION": SourceModality.ASSERTION,
    "ASSISTANT_CLAIM": SourceModality.ASSISTANT_CLAIM,
    "CORRECTION": SourceModality.CORRECTION,
    "HYPOTHETICAL": SourceModality.HYPOTHETICAL,
    "INSTRUCTION": SourceModality.INSTRUCTION,
    "NOISE": SourceModality.NOISE,
    "QUESTION": SourceModality.QUESTION,
    "QUOTED_OR_PASTED": SourceModality.QUOTED_OR_PASTED,
    "THIRD_PARTY_CLAIM": SourceModality.THIRD_PARTY_CLAIM,
    "TOOL_RESULT": SourceModality.TOOL_RESULT,
}


def encode_typed_value_model_candidate(
    value: BaseModel,
    *,
    entry: CompiledRegistryEntry,
    publication: VerifiedTypedValuePublication,
    maximum_bytes: int,
    maximum_nodes: int,
    maximum_depth: int,
) -> MaterializedTypedValueModel:
    """Encode and locally reconstruct one source-selected native candidate.

    The result is conversion evidence only.  A verified publication selects the
    immutable schema and finite native decoder, but it grants neither writer,
    persistence, signature, nor authentication authority.
    """
    _require_limits(maximum_bytes, maximum_nodes, maximum_depth)
    if not isinstance(value, BaseModel):
        raise TypedValueModelCodecError("typed_value_model_codec_native_model_invalid")
    registry = publication.compiled_registry
    _verify_publication_join(entry, registry, publication)
    schema, optionals, numerics, _ = _roles_for_entry(registry, entry)
    if any(policy.startswith("omittable") for policy in (item.policy for item in optionals.fields)):
        raise TypedValueModelCodecError("typed_value_model_codec_omittable_native_presence_unsupported")

    writer = _BoundedWriter(maximum_bytes, maximum_nodes, maximum_depth)
    _emit_model(
        writer,
        value,
        schema,
        optionals,
        numerics,
        registry,
        publication,
        entry,
        frozenset(value.__dict__),
    )
    raw_bytes = writer.finish()
    try:
        body = validate_typed_value_body(
            raw_bytes,
            registry=registry,
            entry=entry,
            limits=ProtectedTypedValueBodyLimits(
                maximum_bytes,
                maximum_nodes,
                maximum_depth,
            ),
        )
    except TypedValueBodyValidationError as exc:
        raise TypedValueModelCodecError("typed_value_model_codec_candidate_body_invalid") from exc
    materialized = materialize_typed_value_model(
        body,
        publication=publication,
        maximum_bytes=maximum_bytes,
        maximum_nodes=maximum_nodes,
        maximum_depth=maximum_depth,
    )
    if type(materialized.value) is not type(value) or materialized.value != value:
        raise TypedValueModelCodecError("typed_value_model_codec_candidate_native_roundtrip_mismatch")
    if (
        reencode_materialized_typed_value_model(
            materialized,
            publication=publication,
            maximum_bytes=maximum_bytes,
            maximum_nodes=maximum_nodes,
            maximum_depth=maximum_depth,
        )
        != raw_bytes
    ):
        raise TypedValueModelCodecError("typed_value_model_codec_candidate_reencode_mismatch")
    return materialized


def materialize_typed_value_model(
    body: ValidatedTypedValueBody,
    *,
    publication: VerifiedTypedValuePublication,
    maximum_bytes: int,
    maximum_nodes: int,
    maximum_depth: int,
) -> MaterializedTypedValueModel:
    """Join one validated body to publication identity then call its static decoder."""
    _require_limits(maximum_bytes, maximum_nodes, maximum_depth)
    _require_tree_limits(body.tree, maximum_nodes, maximum_depth)
    registry = publication.compiled_registry
    _verify_publication_join(body.entry, registry, publication)
    schema, optionals, numerics, _ = _roles_for_entry(registry, body.entry)
    if len(body.raw_bytes) > maximum_bytes:
        raise TypedValueModelCodecError("typed_value_model_codec_bytes_limit_exceeded")
    fields = _decode_model(
        body.tree,
        schema,
        optionals,
        numerics,
        registry,
        publication,
        body.entry,
        maximum_bytes,
        maximum_nodes,
        maximum_depth,
    )
    # Native defaults cannot prove omitted wire-field preservation.  The
    # current published inventory has no omittable fields; reject any future
    # one until its native owner supplies an explicit presence contract.
    if any(policy.startswith("omittable") for policy in (item.policy for item in optionals.fields)):
        raise TypedValueModelCodecError("typed_value_model_codec_omittable_native_presence_unsupported")
    try:
        native = decode_native_observation(body.entry.decoder_id, fields)
    except (TypeError, ValueError) as exc:
        raise TypedValueModelCodecError("typed_value_model_codec_native_decode_invalid") from exc
    result = MaterializedTypedValueModel(body, native, frozenset(fields))
    if reencode_materialized_typed_value_model(
        result,
        publication=publication,
        maximum_bytes=maximum_bytes,
        maximum_nodes=maximum_nodes,
        maximum_depth=maximum_depth,
    ) != body.raw_bytes:
        raise TypedValueModelCodecError("typed_value_model_codec_native_reencode_mismatch")
    return result


def reencode_materialized_typed_value_model(
    materialized: MaterializedTypedValueModel,
    *,
    publication: VerifiedTypedValuePublication,
    maximum_bytes: int,
    maximum_nodes: int,
    maximum_depth: int,
) -> bytes:
    """Schema-direct native reencoding; it is deliberately not authentication."""
    _require_limits(maximum_bytes, maximum_nodes, maximum_depth)
    body = materialized.body
    _require_tree_limits(body.tree, maximum_nodes, maximum_depth)
    registry = publication.compiled_registry
    _verify_publication_join(body.entry, registry, publication)
    schema, optionals, numerics, _ = _roles_for_entry(registry, body.entry)
    if any(policy.startswith("omittable") for policy in (item.policy for item in optionals.fields)):
        raise TypedValueModelCodecError("typed_value_model_codec_omittable_native_presence_unsupported")
    writer = _BoundedWriter(maximum_bytes, maximum_nodes, maximum_depth)
    _emit_model(
        writer,
        materialized.value,
        schema,
        optionals,
        numerics,
        registry,
        publication,
        body.entry,
        materialized.present_fields,
    )
    return writer.finish()


def _verify_publication_join(
    entry: CompiledRegistryEntry,
    registry: CompiledTypedValueRegistry,
    publication: VerifiedTypedValuePublication,
) -> None:
    if registry.registry_digest != publication.publication_manifest.registry_digest:
        raise TypedValueModelCodecError("typed_value_model_codec_publication_registry_digest_mismatch")
    try:
        selected = registry.entry_for(entry.schema_id, entry.schema_version)
    except KeyError as exc:
        raise TypedValueModelCodecError("typed_value_model_codec_entry_not_published") from exc
    if selected != entry:
        raise TypedValueModelCodecError("typed_value_model_codec_entry_identity_mismatch")
    source_snapshots = {
        item.decoder_id: item.source_snapshot_digest
        for item in publication.verified_decoder_sources.snapshots
    }
    published_snapshots = {
        item.decoder_id: item.source_snapshot_digest
        for item in publication.publication_manifest.decoder_source_snapshots
    }
    if source_snapshots != published_snapshots:
        raise TypedValueModelCodecError("typed_value_model_codec_publication_snapshot_mismatch")
    if source_snapshots.get(entry.decoder_id) != entry.implementation_source_digest:
        raise TypedValueModelCodecError("typed_value_model_codec_decoder_source_identity_mismatch")


def _decode_model(value: object, schema: SchemaRole, optionals: OptionalRole, numerics: NumericRole, registry: CompiledTypedValueRegistry, publication: VerifiedTypedValuePublication, root_entry: CompiledRegistryEntry, maximum_bytes: int, maximum_nodes: int, maximum_depth: int) -> dict[str, object]:
    entries = _entries(value, "map")
    declared = {field.name: field for field in schema.fields}
    policies = {field.field_name: field.policy for field in optionals.fields}
    numeric_fields = {field.field_name: field for field in numerics.fields}
    result: dict[str, object] = {}
    for name, child in entries:
        field = declared.get(name)
        policy = policies.get(name)
        if field is None or policy is None:
            raise TypedValueModelCodecError("typed_value_model_codec_declared_field_missing")
        if child is None:
            result[name] = None
        else:
            result[name] = _decode_value(child, field.type, numeric_fields.get(name), registry, publication, root_entry, maximum_bytes, maximum_nodes, maximum_depth)
    return result


def _decode_value(value: object, expression: TypeExpr, numeric: NumericFieldDeclaration | None, registry: CompiledTypedValueRegistry, publication: VerifiedTypedValuePublication, root_entry: CompiledRegistryEntry, maximum_bytes: int, maximum_nodes: int, maximum_depth: int) -> object:
    if isinstance(expression, ScalarTypeExpr):
        return _decode_scalar(value, expression)
    if isinstance(expression, LiteralTypeExpr):
        if isinstance(value, Mapping) and value.get("$type") == "integer":
            return _parse_integer(_scalar(value, "integer"))
        return value
    if isinstance(expression, IntegerTypeExpr):
        return _parse_integer(_scalar(value, "integer"))
    if isinstance(expression, NamedFieldTypeExpr):
        if numeric is None:
            raise TypedValueModelCodecError("typed_value_model_codec_numeric_declaration_missing")
        try:
            return decode_typed_numeric_value(_canonical_bytes(value), numeric, limits=ProtectedTypedNumericValueLimits(maximum_bytes, maximum_nodes, maximum_depth))
        except TypedNumericValueError as exc:
            raise TypedValueModelCodecError("typed_value_model_codec_numeric_invalid") from exc
    if isinstance(expression, EnumRefTypeExpr):
        member = _enum_member(value, expression.qualified_id)
        return _native_enum(expression.qualified_id, member, registry, root_entry)
    if isinstance(expression, ModelRefTypeExpr):
        nested = registry.entry_for(expression.schema_id, expression.schema_version)
        _verify_publication_join(nested, registry, publication)
        schema, optionals, numerics, _ = _roles_for_entry(registry, nested)
        fields = _decode_model(value, schema, optionals, numerics, registry, publication, nested, maximum_bytes, maximum_nodes, maximum_depth)
        try:
            return decode_native_observation(nested.decoder_id, fields)
        except (TypeError, ValueError) as exc:
            raise TypedValueModelCodecError("typed_value_model_codec_nested_native_decode_invalid") from exc
    if isinstance(expression, CollectionTypeExpr):
        tag = "tuple" if expression.kind == "variadic_tuple" else expression.kind
        items = _items(value, tag)
        decoded = tuple(_decode_value(item, expression.element, None, registry, publication, root_entry, maximum_bytes, maximum_nodes, maximum_depth) for item in items)
        if expression.kind == "list":
            return list(decoded)
        if expression.kind == "set":
            return set(decoded)
        if expression.kind == "frozenset":
            return frozenset(decoded)
        return decoded
    if isinstance(expression, FixedTupleTypeExpr):
        items = _items(value, "tuple")
        return tuple(_decode_value(item, child, None, registry, publication, root_entry, maximum_bytes, maximum_nodes, maximum_depth) for item, child in zip(items, expression.items, strict=True))
    if isinstance(expression, MapTypeExpr):
        return {key: _decode_value(child, expression.value, None, registry, publication, root_entry, maximum_bytes, maximum_nodes, maximum_depth) for key, child in _entries(value, "map")}
    if isinstance(expression, UnionTypeExpr):
        members = dict(_entries(value, "map"))
        discriminator = members.get(expression.discriminator)
        alternative = next((item for item in expression.alternatives if item.discriminator_value == discriminator), None)
        if alternative is None:
            raise TypedValueModelCodecError("typed_value_model_codec_union_discriminator_invalid")
        return _decode_value(value, alternative.model, None, registry, publication, root_entry, maximum_bytes, maximum_nodes, maximum_depth)
    raise TypedValueModelCodecError("typed_value_model_codec_type_expression_unknown")


def _decode_scalar(value: object, expression: ScalarTypeExpr) -> object:
    if expression.kind == "bool" and type(value) is bool:
        return value
    if expression.kind == "null" and value is None:
        return value
    if expression.kind == "string" and type(value) is str:
        return value
    if expression.kind == "bytes":
        try:
            return base64.b64decode(_scalar(value, "bytes"), validate=True)
        except ValueError as exc:
            raise TypedValueModelCodecError("typed_value_model_codec_bytes_invalid") from exc
    if expression.kind == "datetime":
        text = _scalar(value, "datetime")
        try:
            return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
        except ValueError as exc:
            raise TypedValueModelCodecError("typed_value_model_codec_datetime_invalid") from exc
    if expression.kind == "duration_microseconds":
        return timedelta(microseconds=_parse_integer(_scalar(value, "duration_microseconds")))
    raise TypedValueModelCodecError("typed_value_model_codec_scalar_unknown")


def _native_enum(qualified_id: str, member: str, registry: CompiledTypedValueRegistry, root_entry: CompiledRegistryEntry) -> object:
    enum = _find_enum(registry, root_entry, qualified_id)
    declared = None if enum is None else next((item for item in enum.members if item.member_id == member), None)
    if declared is None:
        raise TypedValueModelCodecError("typed_value_model_codec_enum_member_unknown")
    if qualified_id != _SOURCE_MODALITY_ENUM_ID:
        raise TypedValueModelCodecError("typed_value_model_codec_native_enum_unmapped")
    result = _SOURCE_MODALITY_BY_MEMBER.get(member)
    if result is None:
        raise TypedValueModelCodecError("typed_value_model_codec_source_modality_member_unmapped")
    if declared.wire_value != result.value:
        raise TypedValueModelCodecError("typed_value_model_codec_source_modality_wire_mismatch")
    return result


def _encode_enum_member(value: object, qualified_id: str) -> str:
    if qualified_id != _SOURCE_MODALITY_ENUM_ID or not isinstance(value, SourceModality):
        raise TypedValueModelCodecError("typed_value_model_codec_native_enum_invalid")
    for member, native in _SOURCE_MODALITY_BY_MEMBER.items():
        if native is value:
            return member
    raise TypedValueModelCodecError("typed_value_model_codec_source_modality_value_unmapped")


def _roles_for_entry(registry: CompiledTypedValueRegistry, entry: CompiledRegistryEntry) -> tuple[SchemaRole, OptionalRole, NumericRole, EnumRole]:
    coordinate = (entry.schema_id, entry.schema_version)
    matches = {
        role.role: role
        for role in registry.parsed_roles
        if isinstance(role, (SchemaRole, OptionalRole, NumericRole, EnumRole))
        and (role.schema_id, role.schema_version) == coordinate
    }
    schema, optionals, numerics, enums = (matches.get("schema"), matches.get("optional"), matches.get("numeric"), matches.get("enum"))
    if not isinstance(schema, SchemaRole) or not isinstance(optionals, OptionalRole) or not isinstance(numerics, NumericRole) or not isinstance(enums, EnumRole):
        raise TypedValueModelCodecError("typed_value_model_codec_registry_roles_invalid")
    return schema, optionals, numerics, enums


def _find_enum(registry: CompiledTypedValueRegistry, root_entry: CompiledRegistryEntry, qualified_id: str) -> EnumDeclaration | None:
    reachable = _reachable_coordinates(registry, (root_entry.schema_id, root_entry.schema_version))
    matches = [enum for role in registry.parsed_roles if isinstance(role, EnumRole) and (role.schema_id, role.schema_version) in reachable for enum in role.enums if enum.qualified_id == qualified_id]
    return matches[0] if len(matches) == 1 else None


def _reachable_coordinates(registry: CompiledTypedValueRegistry, root: tuple[str, str]) -> frozenset[tuple[str, str]]:
    schemas = {(role.schema_id, role.schema_version): role for role in registry.parsed_roles if isinstance(role, SchemaRole)}
    policies = {(role.schema_id, role.schema_version): role for role in registry.parsed_roles if isinstance(role, DigestSignatureRole)}
    pending = [root]
    seen: set[tuple[str, str]] = set()
    while pending:
        coordinate = pending.pop()
        if coordinate in seen:
            continue
        schema = schemas.get(coordinate)
        policy = policies.get(coordinate)
        if schema is None or policy is None:
            raise TypedValueModelCodecError("typed_value_model_codec_registry_roles_invalid")
        seen.add(coordinate)
        pending.extend((item.schema_id, item.schema_version) for item in _walk_model_refs(field.type for field in schema.fields))
        if isinstance(policy.policy, ExternalSigningPreimagePolicy):
            pending.append((policy.policy.preimage_schema_id, policy.policy.preimage_schema_version))
    return frozenset(seen)


def _walk_model_refs(expressions: Iterable[TypeExpr]) -> tuple[ModelRefTypeExpr, ...]:
    pending = list(expressions)
    found: list[ModelRefTypeExpr] = []
    while pending:
        expression = pending.pop()
        if isinstance(expression, ModelRefTypeExpr):
            found.append(expression)
        elif isinstance(expression, CollectionTypeExpr):
            pending.append(expression.element)
        elif isinstance(expression, FixedTupleTypeExpr):
            pending.extend(expression.items)
        elif isinstance(expression, MapTypeExpr):
            pending.append(expression.value)
        elif isinstance(expression, UnionTypeExpr):
            pending.extend(item.model for item in expression.alternatives)
    return tuple(found)


def _entries(value: object, tag: str) -> tuple[tuple[str, object], ...]:
    if not isinstance(value, Mapping) or value.get("$type") != tag or set(value) != {"$type", "entries"} or not isinstance(value["entries"], tuple):
        raise TypedValueModelCodecError("typed_value_model_codec_ctv_map_invalid")
    result: list[tuple[str, object]] = []
    for item in value["entries"]:
        if not isinstance(item, tuple) or len(item) != 2 or not isinstance(item[0], str):
            raise TypedValueModelCodecError("typed_value_model_codec_ctv_map_invalid")
        result.append((item[0], item[1]))
    return tuple(result)


def _items(value: object, tag: str) -> tuple[object, ...]:
    if not isinstance(value, Mapping) or value.get("$type") != tag or set(value) != {"$type", "items"} or not isinstance(value["items"], tuple):
        raise TypedValueModelCodecError("typed_value_model_codec_ctv_collection_invalid")
    return value["items"]


def _scalar(value: object, tag: str) -> str:
    if not isinstance(value, Mapping) or value.get("$type") != tag or set(value) != {"$type", "value"} or not isinstance(value["value"], str):
        raise TypedValueModelCodecError("typed_value_model_codec_ctv_scalar_invalid")
    return value["value"]


def _enum_member(value: object, qualified_id: str) -> str:
    if not isinstance(value, Mapping) or set(value) != {"$type", "enum_type", "member"} or value.get("$type") != "enum" or value.get("enum_type") != qualified_id or not isinstance(value.get("member"), str):
        raise TypedValueModelCodecError("typed_value_model_codec_ctv_enum_invalid")
    return value["member"]


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8", "strict")


def _parse_integer(text: str) -> int:
    if not text or text == "-" or (text[0] == "-" and (len(text) == 1 or text[1] == "0")) or (text[0] == "0" and len(text) > 1) or not all("0" <= item <= "9" for item in text.removeprefix("-")):
        raise TypedValueModelCodecError("typed_value_model_codec_integer_invalid")
    negative = text.startswith("-")
    digits = text[1:] if negative else text
    result = 0
    for start in range(0, len(digits), 9):
        chunk = digits[start : start + 9]
        chunk_value = 0
        for character in chunk:
            chunk_value = chunk_value * 10 + ord(character) - ord("0")
        result = result * (10 ** len(chunk)) + chunk_value
    return -result if negative else result


def _integer_text(value: int) -> str:
    if type(value) is not int:
        raise TypedValueModelCodecError("typed_value_model_codec_native_integer_invalid")
    if value == 0:
        return "0"
    negative = value < 0
    remaining = -value if negative else value
    chunks: list[str] = []
    while remaining:
        remaining, chunk = divmod(remaining, 1_000_000_000)
        chunks.append(f"{chunk:09d}" if remaining else f"{chunk:d}")
    return ("-" if negative else "") + "".join(reversed(chunks))


class _BoundedWriter:
    def __init__(self, maximum_bytes: int, maximum_nodes: int, maximum_depth: int) -> None:
        self._maximum_bytes = maximum_bytes
        self._maximum_nodes = maximum_nodes
        self._maximum_depth = maximum_depth
        self._parts: list[bytes] = []
        self._bytes = 0
        self._nodes = 0

    def node(self, depth: int) -> None:
        self._nodes += 1
        if self._nodes > self._maximum_nodes:
            raise TypedValueModelCodecError("typed_value_model_codec_nodes_limit_exceeded")
        if depth > self._maximum_depth:
            raise TypedValueModelCodecError("typed_value_model_codec_depth_limit_exceeded")

    def write(self, value: bytes) -> None:
        self.require_bytes(len(value))
        self._parts.append(value)
        self._bytes += len(value)

    def require_bytes(self, count: int) -> None:
        if count < 0 or self._bytes + count > self._maximum_bytes:
            raise TypedValueModelCodecError("typed_value_model_codec_bytes_limit_exceeded")

    @property
    def remaining_bytes(self) -> int:
        return self._maximum_bytes - self._bytes

    @property
    def remaining_nodes(self) -> int:
        return self._maximum_nodes - self._nodes

    def string(self, value: str) -> None:
        if type(value) is not str:
            raise TypedValueModelCodecError("typed_value_model_codec_native_string_invalid")
        self.write(b'"')
        for character in value:
            codepoint = ord(character)
            if character == '"':
                self.write(b'\\"')
            elif character == "\\":
                self.write(b"\\\\")
            elif character == "\b":
                self.write(b"\\b")
            elif character == "\f":
                self.write(b"\\f")
            elif character == "\n":
                self.write(b"\\n")
            elif character == "\r":
                self.write(b"\\r")
            elif character == "\t":
                self.write(b"\\t")
            elif codepoint < 0x20:
                self.write(f"\\u{codepoint:04x}".encode("ascii"))
            else:
                self.write(character.encode("utf-8", "strict"))
        self.write(b'"')

    def finish(self) -> bytes:
        return b"".join(self._parts)


def _emit_model(
    writer: _BoundedWriter,
    value: BaseModel,
    schema: SchemaRole,
    optionals: OptionalRole,
    numerics: NumericRole,
    registry: CompiledTypedValueRegistry,
    publication: VerifiedTypedValuePublication,
    entry: CompiledRegistryEntry,
    present: frozenset[str],
    depth: int = 1,
) -> None:
    if not isinstance(value, BaseModel):
        raise TypedValueModelCodecError("typed_value_model_codec_native_model_invalid")
    fields = value.__dict__
    declared = {field.name: field for field in schema.fields}
    policies = {field.field_name: field.policy for field in optionals.fields}
    numeric_fields = {field.field_name: field for field in numerics.fields}
    if set(fields) != set(declared) or not present <= set(fields):
        raise TypedValueModelCodecError("typed_value_model_codec_native_fields_invalid")
    writer.node(depth)
    writer.write(b'{"$type":"map","entries":[')
    for index, name in enumerate(_sort_json_string_values(present)):
        if index:
            writer.write(b",")
        writer.write(b"[")
        writer.string(name)
        writer.write(b",")
        item = fields[name]
        if item is None:
            if policies[name] not in {"required_nullable", "omittable_nullable"}:
                raise TypedValueModelCodecError("typed_value_model_codec_native_null_forbidden")
            writer.node(depth + 1)
            writer.write(b"null")
        else:
            _emit_value(writer, item, declared[name].type, numeric_fields.get(name), registry, publication, entry, depth + 1)
        writer.write(b"]")
    writer.write(b"]}")


def _emit_value(
    writer: _BoundedWriter,
    value: object,
    expression: TypeExpr,
    numeric: NumericFieldDeclaration | None,
    registry: CompiledTypedValueRegistry,
    publication: VerifiedTypedValuePublication,
    entry: CompiledRegistryEntry,
    depth: int,
) -> None:
    writer.node(depth)
    if isinstance(expression, ScalarTypeExpr):
        if expression.kind == "bool" and type(value) is bool:
            writer.write(b"true" if value else b"false")
            return
        if expression.kind == "null" and value is None:
            writer.write(b"null")
            return
        if expression.kind == "string" and type(value) is str:
            writer.string(value)
            return
        if expression.kind == "bytes" and type(value) is bytes:
            _emit_bytes(writer, value)
            return
        if expression.kind == "datetime" and isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() == timedelta(0):
            utc = value.astimezone(UTC)
            text = f"{utc.year:04d}-{utc.month:02d}-{utc.day:02d}T{utc.hour:02d}:{utc.minute:02d}:{utc.second:02d}.{utc.microsecond:06d}Z"
            writer.write(b'{"$type":"datetime","value":')
            writer.string(text)
            writer.write(b"}")
            return
        if expression.kind == "duration_microseconds" and type(value) is timedelta:
            amount = value.days * 86_400_000_000 + value.seconds * 1_000_000 + value.microseconds
            if amount < -(2**63) or amount > 2**63 - 1:
                raise TypedValueModelCodecError("typed_value_model_codec_native_duration_range_invalid")
            _emit_tagged_integer(writer, b'{"$type":"duration_microseconds","value":', amount)
            return
        raise TypedValueModelCodecError("typed_value_model_codec_native_scalar_invalid")
    if isinstance(expression, IntegerTypeExpr):
        if type(value) is not int:
            raise TypedValueModelCodecError("typed_value_model_codec_native_integer_invalid")
        _emit_tagged_integer(writer, b'{"$type":"integer","value":', value)
        return
    if isinstance(expression, LiteralTypeExpr):
        if not any(
            (isinstance(item, LiteralInteger) and type(value) is int and item.value == _integer_text(value))
            or (type(item) is type(value) and item == value)
            for item in expression.values
        ):
            raise TypedValueModelCodecError("typed_value_model_codec_native_literal_invalid")
        if type(value) is int:
            _emit_tagged_integer(writer, b'{"$type":"integer","value":', value)
        elif type(value) is bool:
            writer.write(b"true" if value else b"false")
        else:
            writer.string(cast(str, value))
        return
    if isinstance(expression, NamedFieldTypeExpr):
        if numeric is None or not isinstance(value, (CanonicalFiniteBinary64, CanonicalDecimalQuantity)):
            raise TypedValueModelCodecError("typed_value_model_codec_native_numeric_invalid")
        writer.write(
            encode_typed_numeric_value(
                value,
                numeric,
                limits=ProtectedTypedNumericValueLimits(
                    writer._maximum_bytes, writer._maximum_nodes, writer._maximum_depth
                ),
            )
        )
        return
    if isinstance(expression, EnumRefTypeExpr):
        member = _encode_enum_member(value, expression.qualified_id)
        writer.write(b'{"$type":"enum","enum_type":')
        writer.string(expression.qualified_id)
        writer.write(b",\"member\":")
        writer.string(member)
        writer.write(b"}")
        return
    if isinstance(expression, ModelRefTypeExpr):
        if not isinstance(value, BaseModel):
            raise TypedValueModelCodecError("typed_value_model_codec_native_model_invalid")
        nested = registry.entry_for(expression.schema_id, expression.schema_version)
        _verify_publication_join(nested, registry, publication)
        schema, optional, numeric_role, _ = _roles_for_entry(registry, nested)
        _emit_model(
            writer,
            value,
            schema,
            optional,
            numeric_role,
            registry,
            publication,
            nested,
            frozenset(value.__dict__),
            depth + 1,
        )
        return
    if isinstance(expression, CollectionTypeExpr):
        expected = {"list": list, "variadic_tuple": tuple, "set": set, "frozenset": frozenset}[expression.kind]
        if type(value) is not expected:
            raise TypedValueModelCodecError("typed_value_model_codec_native_collection_kind_invalid")
        collection = cast(list[object] | tuple[object, ...] | set[object] | frozenset[object], value)
        _require_collection_capacity(writer, len(collection))
        members: Iterable[object] = collection
        if expression.kind in {"set", "frozenset"}:
            members = _sorted_bounded_set_members(writer, members, expression.element, registry, publication, entry)
        tag = "tuple" if expression.kind == "variadic_tuple" else expression.kind
        writer.write(b'{"$type":')
        writer.string(tag)
        writer.write(b',"items":[')
        for index, item in enumerate(members):
            if index:
                writer.write(b",")
            _emit_value(writer, item, expression.element, None, registry, publication, entry, depth + 1)
        writer.write(b"]}")
        return
    if isinstance(expression, FixedTupleTypeExpr):
        if type(value) is not tuple or len(value) != len(expression.items):
            raise TypedValueModelCodecError("typed_value_model_codec_native_tuple_invalid")
        writer.write(b'{"$type":"tuple","items":[')
        for index, (item, child) in enumerate(zip(value, expression.items, strict=True)):
            if index:
                writer.write(b",")
            _emit_value(writer, item, child, None, registry, publication, entry, depth + 1)
        writer.write(b"]}")
        return
    if isinstance(expression, MapTypeExpr):
        if not isinstance(value, Mapping) or any(type(key) is not str for key in value):
            raise TypedValueModelCodecError("typed_value_model_codec_native_map_invalid")
        _require_collection_capacity(writer, len(value))
        writer.write(b'{"$type":"map","entries":[')
        for index, key in enumerate(_sort_json_string_values(value)):
            if index:
                writer.write(b",")
            writer.write(b"[")
            writer.string(key)
            writer.write(b",")
            _emit_value(writer, value[key], expression.value, None, registry, publication, entry, depth + 1)
            writer.write(b"]")
        writer.write(b"]}")
        return
    if isinstance(expression, UnionTypeExpr):
        if not isinstance(value, BaseModel):
            raise TypedValueModelCodecError("typed_value_model_codec_native_union_invalid")
        discriminator = value.__dict__.get(expression.discriminator)
        alternative = next((item for item in expression.alternatives if item.discriminator_value == discriminator), None)
        if alternative is None:
            raise TypedValueModelCodecError("typed_value_model_codec_native_union_discriminator_invalid")
        _emit_value(writer, value, alternative.model, None, registry, publication, entry, depth + 1)
        return
    raise TypedValueModelCodecError("typed_value_model_codec_type_expression_unknown")


def _emit_bytes(writer: _BoundedWriter, value: bytes) -> None:
    encoded_length = 4 * ((len(value) + 2) // 3)
    prefix = b'{"$type":"bytes","value":"'
    writer.require_bytes(len(prefix) + encoded_length + 2)
    writer.write(prefix)
    for start in range(0, len(value), 3_072):
        writer.write(base64.b64encode(value[start : start + 3_072]))
    writer.write(b'"}')


def _emit_tagged_integer(writer: _BoundedWriter, prefix: bytes, value: int) -> None:
    if type(value) is not int:
        raise TypedValueModelCodecError("typed_value_model_codec_native_integer_invalid")
    digits = _integer_digit_count(value)
    writer.require_bytes(len(prefix) + digits + 3)
    writer.write(prefix)
    writer.write(b'"')
    _write_integer(writer, value)
    writer.write(b'"}')


def _integer_digit_count(value: int) -> int:
    remaining = -value if value < 0 else value
    digits = 1
    while remaining >= 10:
        remaining //= 10
        digits += 1
    return digits + int(value < 0)


def _write_integer(writer: _BoundedWriter, value: int) -> None:
    if value == 0:
        writer.write(b"0")
        return
    if value < 0:
        writer.write(b"-")
        value = -value
    divisor = 1
    while divisor <= value // 10:
        divisor *= 10
    while divisor:
        digit, value = divmod(value, divisor)
        writer.write(bytes((ord("0") + digit,)))
        divisor //= 10


def _sort_json_string_values(values: Iterable[str]) -> list[str]:
    return sorted(values, key=cmp_to_key(_compare_json_string_bytes))


def _compare_json_string_bytes(left: str, right: str) -> int:
    sentinel = -1
    for left_byte, right_byte in zip_longest(
        _json_string_byte_iter(left), _json_string_byte_iter(right), fillvalue=sentinel
    ):
        if left_byte != right_byte:
            return -1 if left_byte < right_byte else 1
    return 0


def _json_string_byte_iter(value: str) -> Iterable[int]:
    yield ord('"')
    for character in value:
        codepoint = ord(character)
        if character == '"':
            yield from b'\\"'
        elif character == "\\":
            yield from b"\\\\"
        elif character == "\b":
            yield from b"\\b"
        elif character == "\f":
            yield from b"\\f"
        elif character == "\n":
            yield from b"\\n"
        elif character == "\r":
            yield from b"\\r"
        elif character == "\t":
            yield from b"\\t"
        elif codepoint < 0x20:
            yield from f"\\u{codepoint:04x}".encode("ascii")
        else:
            yield from character.encode("utf-8", "strict")
    yield ord('"')


def _require_collection_capacity(writer: _BoundedWriter, count: int) -> None:
    if count > writer.remaining_nodes:
        raise TypedValueModelCodecError("typed_value_model_codec_nodes_limit_exceeded")


def _sorted_bounded_set_members(
    writer: _BoundedWriter,
    members: Iterable[object],
    expression: TypeExpr,
    registry: CompiledTypedValueRegistry,
    publication: VerifiedTypedValuePublication,
    entry: CompiledRegistryEntry,
) -> list[object]:
    staged: list[tuple[bytes, object]] = []
    staged_bytes = 0
    for item in members:
        candidate = _BoundedWriter(
            writer.remaining_bytes - staged_bytes,
            writer._maximum_nodes,
            writer._maximum_depth,
        )
        _emit_value(candidate, item, expression, None, registry, publication, entry, 1)
        encoded = candidate.finish()
        staged.append((encoded, item))
        staged_bytes += len(encoded)
    staged.sort(key=lambda item: item[0])
    return [item for _, item in staged]


def _require_limits(maximum_bytes: int, maximum_nodes: int, maximum_depth: int) -> None:
    if any(type(value) is not int or value <= 0 for value in (maximum_bytes, maximum_nodes, maximum_depth)):
        raise ValueError("typed_value_model_codec_limits_must_be_positive")


def _require_tree_limits(value: object, maximum_nodes: int, maximum_depth: int) -> None:
    pending: list[tuple[object, int]] = [(value, 1)]
    nodes = 0
    while pending:
        current, depth = pending.pop()
        nodes += 1
        if nodes > maximum_nodes:
            raise TypedValueModelCodecError("typed_value_model_codec_nodes_limit_exceeded")
        if depth > maximum_depth:
            raise TypedValueModelCodecError("typed_value_model_codec_depth_limit_exceeded")
        if isinstance(current, Mapping):
            pending.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, (list, tuple, set, frozenset)):
            pending.extend((item, depth + 1) for item in current)
