"""Closed raw declaration intake for the operational typed-value profile.

This module deliberately parses one declaration at a time.  Publication,
cross-role closure, source manifests, and decoder composition are separate
owners; callers receive immutable role-local IR and the exact verified bytes.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TypeAlias, cast

_ASCII_ID = re.compile(r"[A-Za-z0-9._/-]+\Z")
_POSITIVE_UINT = re.compile(r"[1-9][0-9]*\Z")
_INTEGER = re.compile(r"(?:0|-?[1-9][0-9]*)\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class DeclarationParseError(ValueError):
    """A raw operational declaration violates its closed intake grammar."""


@dataclass(frozen=True)
class ProtectedDeclarationParseLimits:
    """Protected composition limits; these never contribute to profile bytes."""

    maximum_bytes: int
    maximum_nodes: int
    maximum_depth: int

    def __post_init__(self) -> None:
        values = (self.maximum_bytes, self.maximum_nodes, self.maximum_depth)
        if any(type(value) is not int or value <= 0 for value in values):
            raise ValueError("declaration_parse_limits_must_be_positive")


@dataclass(frozen=True)
class TypeExpr:
    kind: str


@dataclass(frozen=True)
class ScalarTypeExpr(TypeExpr):
    lexical_rule: str | None = None


@dataclass(frozen=True)
class LiteralInteger:
    value: str


LiteralValue: TypeAlias = str | bool | LiteralInteger


@dataclass(frozen=True)
class LiteralTypeExpr(TypeExpr):
    values: tuple[LiteralValue, ...]


@dataclass(frozen=True)
class IntegerTypeExpr(TypeExpr):
    minimum: str | None
    maximum: str | None


@dataclass(frozen=True)
class NamedFieldTypeExpr(TypeExpr):
    field_name: str


@dataclass(frozen=True)
class EnumRefTypeExpr(TypeExpr):
    qualified_id: str


@dataclass(frozen=True)
class ModelRefTypeExpr(TypeExpr):
    schema_id: str
    schema_version: str


@dataclass(frozen=True)
class CollectionTypeExpr(TypeExpr):
    element: TypeExpr


@dataclass(frozen=True)
class FixedTupleTypeExpr(TypeExpr):
    items: tuple[TypeExpr, ...]


@dataclass(frozen=True)
class MapTypeExpr(TypeExpr):
    value: TypeExpr


@dataclass(frozen=True)
class UnionAlternative:
    discriminator_value: str
    model: ModelRefTypeExpr


@dataclass(frozen=True)
class UnionTypeExpr(TypeExpr):
    discriminator: str
    alternatives: tuple[UnionAlternative, ...]


@dataclass(frozen=True)
class FieldDeclaration:
    name: str
    type: TypeExpr
    integrity_role: str


@dataclass(frozen=True)
class EnumMemberDeclaration:
    member_id: str
    wire_value: str


@dataclass(frozen=True)
class EnumDeclaration:
    qualified_id: str
    members: tuple[EnumMemberDeclaration, ...]


@dataclass(frozen=True)
class OptionalFieldDeclaration:
    field_name: str
    policy: str


@dataclass(frozen=True)
class NumericFieldDeclaration:
    field_name: str
    representation: str
    encoding_spec_id: str | None
    unit: str | None
    scale: str | None
    lower: str | None
    lower_inclusive: bool | None
    upper: str | None
    upper_inclusive: bool | None
    reject_inexact: bool | None


@dataclass(frozen=True)
class DigestSignaturePolicy:
    kind: str


@dataclass(frozen=True)
class OrdinaryPolicy(DigestSignaturePolicy):
    pass


@dataclass(frozen=True)
class SelfDigestPolicy(DigestSignaturePolicy):
    digest_field: str
    digest_domain: str


@dataclass(frozen=True)
class SignatureOnlyPolicy(DigestSignaturePolicy):
    signature_field: str
    signature_purpose: str
    signature_domain: str


@dataclass(frozen=True)
class ExternalSigningPreimagePolicy(DigestSignaturePolicy):
    result_digest_field: str
    result_signature_field: str
    preimage_schema_id: str
    preimage_schema_version: str
    binding_kind: str
    signature_purpose: str
    signature_domain: str


@dataclass(frozen=True)
class DeclarationRole:
    raw_bytes: bytes
    role: str


@dataclass(frozen=True)
class GrammarRole(DeclarationRole):
    profile_id: str
    profile_version: str
    grammar_revision: str


@dataclass(frozen=True)
class SchemaRole(DeclarationRole):
    schema_id: str
    schema_version: str
    fields: tuple[FieldDeclaration, ...]


@dataclass(frozen=True)
class EnumRole(DeclarationRole):
    schema_id: str
    schema_version: str
    enums: tuple[EnumDeclaration, ...]


@dataclass(frozen=True)
class OptionalRole(DeclarationRole):
    schema_id: str
    schema_version: str
    fields: tuple[OptionalFieldDeclaration, ...]


@dataclass(frozen=True)
class NumericRole(DeclarationRole):
    schema_id: str
    schema_version: str
    fields: tuple[NumericFieldDeclaration, ...]


@dataclass(frozen=True)
class DigestSignatureRole(DeclarationRole):
    schema_id: str
    schema_version: str
    policy: DigestSignaturePolicy


@dataclass(frozen=True)
class DecoderRole(DeclarationRole):
    schema_id: str
    schema_version: str
    decoder_id: str
    implementation_source_digest: str


@dataclass(frozen=True)
class UpcastRole(DeclarationRole):
    schema_id: str
    schema_version: str


@dataclass(frozen=True)
class RegistryProfile:
    profile_id: str
    profile_version: str
    grammar_revision: str
    grammar_digest: str
    profile_digest: str


@dataclass(frozen=True)
class RegistryRole(DeclarationRole):
    profile: RegistryProfile
    entries: tuple[str, ...]


ParsedDeclaration: TypeAlias = (
    GrammarRole | SchemaRole | EnumRole | OptionalRole | NumericRole | DigestSignatureRole | DecoderRole | UpcastRole | RegistryRole
)


def parse_typed_value_declaration(raw_bytes: bytes, *, limits: ProtectedDeclarationParseLimits) -> ParsedDeclaration:
    """Parse one declaration without exposing recursion failures to callers."""
    try:
        return _parse_typed_value_declaration(raw_bytes, limits=limits)
    except RecursionError as exc:
        raise DeclarationParseError("declaration_depth_limit_exceeded") from exc


def _parse_typed_value_declaration(raw_bytes: bytes, *, limits: ProtectedDeclarationParseLimits) -> ParsedDeclaration:
    """Parse exactly one RFC8785 declaration and preserve its original bytes."""
    if not isinstance(raw_bytes, bytes):
        raise DeclarationParseError("declaration_raw_bytes_required")
    if len(raw_bytes) > limits.maximum_bytes:
        raise DeclarationParseError("declaration_bytes_limit_exceeded")
    if raw_bytes.endswith(b"\n"):
        raise DeclarationParseError("declaration_terminal_lf_forbidden")
    _precheck_nesting(raw_bytes, limits.maximum_depth)
    value = _decode_json(raw_bytes)
    _check_tree_limits(value, limits)
    _verify_canonical_json(value, raw_bytes)
    root = _object(value, "declaration")
    role = _string(root, "role", "declaration")
    if role == "grammar":
        _exact_keys(root, {"envelope", "grammar_revision", "json", "profile_id", "profile_version", "role", "tags", "type_rules"}, "grammar")
        _grammar_literal(root)
        return GrammarRole(raw_bytes, role, _ascii_id(root, "profile_id", role), _positive_uint(root, "profile_version", role), _string(root, "grammar_revision", role))
    if role == "schema":
        return _parse_schema(raw_bytes, root)
    if role == "enum":
        return _parse_enum(raw_bytes, root)
    if role == "optional":
        return _parse_optional(raw_bytes, root)
    if role == "numeric":
        return _parse_numeric(raw_bytes, root)
    if role == "digest-signature":
        return _parse_policy(raw_bytes, root)
    if role == "decoder":
        _exact_keys(root, {"role", "schema_id", "schema_version", "decoder_id", "typed_root_kind", "implementation_source_digest"}, role)
        _literal(root, "typed_root_kind", "model", role)
        return DecoderRole(raw_bytes, role, _ascii_id(root, "schema_id", role), _positive_uint(root, "schema_version", role), _ascii_id(root, "decoder_id", role), _sha256(root, "implementation_source_digest", role))
    if role == "upcast":
        _exact_keys(root, {"role", "schema_id", "schema_version", "target_binding", "upcaster_id", "implementation_source_digest"}, role)
        for name in ("target_binding", "upcaster_id", "implementation_source_digest"):
            if root[name] is not None:
                raise DeclarationParseError(f"{role}.{name}_must_be_null")
        return UpcastRole(raw_bytes, role, _ascii_id(root, "schema_id", role), _positive_uint(root, "schema_version", role))
    if role == "registry":
        _exact_keys(root, {"role", "profile", "entries"}, role)
        profile = _object(root["profile"], "registry.profile")
        _exact_keys(profile, {"profile_id", "profile_version", "grammar_revision", "grammar_digest", "profile_digest"}, "registry.profile")
        entries = tuple(_sha256_value(item, "registry.entries") for item in _array(root["entries"], "registry.entries"))
        _unique(entries, "registry.entries")
        return RegistryRole(raw_bytes, role, RegistryProfile(_ascii_id(profile, "profile_id", "registry.profile"), _positive_uint(profile, "profile_version", "registry.profile"), _string(profile, "grammar_revision", "registry.profile"), _sha256(profile, "grammar_digest", "registry.profile"), _sha256(profile, "profile_digest", "registry.profile")), entries)
    raise DeclarationParseError("declaration_role_unknown")


def _parse_schema(raw: bytes, value: Mapping[str, object]) -> SchemaRole:
    _exact_keys(value, {"role", "schema_id", "schema_version", "root_kind", "fields"}, "schema")
    _literal(value, "root_kind", "model", "schema")
    fields = tuple(_parse_field(item) for item in _array(value["fields"], "schema.fields"))
    _sorted_unique((field.name for field in fields), "schema.fields")
    return SchemaRole(raw, "schema", _ascii_id(value, "schema_id", "schema"), _positive_uint(value, "schema_version", "schema"), fields)


def _parse_field(value: object) -> FieldDeclaration:
    data = _object(value, "schema.field")
    _exact_keys(data, {"name", "type", "integrity_role"}, "schema.field")
    role = _string(data, "integrity_role", "schema.field")
    if role not in {"ordinary", "self_digest", "signature"}:
        raise DeclarationParseError("schema.field.integrity_role_invalid")
    return FieldDeclaration(_ascii_id(data, "name", "schema.field"), _parse_type(data["type"]), role)


def _parse_type(value: object) -> TypeExpr:
    data = _object(value, "type")
    kind = _string(data, "kind", "type")
    scalar_rules = {"string": {"unicode_scalar", "nonempty_unicode_scalar", "sha256", "signature_hex128"}, "bytes": {"rfc4648_standard_padded"}, "datetime": {"utc_six_fractional_digits"}, "duration_microseconds": {"signed_i64"}}
    if kind in scalar_rules:
        _exact_keys(data, {"kind", "lexical_rule"}, f"type.{kind}")
        rule = _string(data, "lexical_rule", f"type.{kind}")
        if rule not in scalar_rules[kind]:
            raise DeclarationParseError("type.lexical_rule_invalid")
        return ScalarTypeExpr(kind, rule)
    if kind in {"bool", "null"}:
        _exact_keys(data, {"kind"}, f"type.{kind}")
        return ScalarTypeExpr(kind)
    if kind == "literal":
        _exact_keys(data, {"kind", "values"}, "type.literal")
        values = tuple(_parse_literal(item) for item in _array(data["values"], "type.literal.values"))
        if not values:
            raise DeclarationParseError("type.literal.values_empty")
        encoded = tuple(_canonical_json(value) for value in values)
        if encoded != tuple(sorted(encoded)) or len(set(encoded)) != len(encoded):
            raise DeclarationParseError("type.literal.values_not_unique_sorted")
        return LiteralTypeExpr(kind, values)
    if kind == "integer":
        _exact_keys(data, {"kind", "lexical_rule", "minimum", "maximum"}, "type.integer")
        _literal(data, "lexical_rule", "canonical_decimal", "type.integer")
        low = _integer_or_null(data["minimum"], "type.integer.minimum")
        high = _integer_or_null(data["maximum"], "type.integer.maximum")
        if low is not None and high is not None and _integer_compare(low, high) > 0:
            raise DeclarationParseError("type.integer_bounds_invalid")
        return IntegerTypeExpr(kind, low, high)
    if kind in {"canonical_decimal_quantity", "canonical_finite_binary64"}:
        _exact_keys(data, {"kind", "field_name"}, f"type.{kind}")
        return NamedFieldTypeExpr(kind, _ascii_id(data, "field_name", f"type.{kind}"))
    if kind == "enum_ref":
        _exact_keys(data, {"kind", "qualified_id"}, "type.enum_ref")
        return EnumRefTypeExpr(kind, _ascii_id(data, "qualified_id", "type.enum_ref"))
    if kind == "model_ref":
        return _parse_model_ref(data, "type.model_ref")
    if kind in {"list", "set", "frozenset", "variadic_tuple"}:
        _exact_keys(data, {"kind", "element"}, f"type.{kind}")
        return CollectionTypeExpr(kind, _parse_type(data["element"]))
    if kind == "fixed_tuple":
        _exact_keys(data, {"kind", "items"}, "type.fixed_tuple")
        items = tuple(_parse_type(item) for item in _array(data["items"], "type.fixed_tuple.items"))
        if not items:
            raise DeclarationParseError("type.fixed_tuple.items_empty")
        return FixedTupleTypeExpr(kind, items)
    if kind == "map":
        _exact_keys(data, {"kind", "key_kind", "value"}, "type.map")
        _literal(data, "key_kind", "string", "type.map")
        return MapTypeExpr(kind, _parse_type(data["value"]))
    if kind == "union":
        _exact_keys(data, {"kind", "discriminator", "alternatives"}, "type.union")
        alternatives = tuple(_parse_union_alternative(item) for item in _array(data["alternatives"], "type.union.alternatives"))
        if not alternatives:
            raise DeclarationParseError("type.union.alternatives_empty")
        _sorted_unique((item.discriminator_value for item in alternatives), "type.union.alternatives")
        return UnionTypeExpr(kind, _ascii_id(data, "discriminator", "type.union"), alternatives)
    raise DeclarationParseError("type.kind_unknown")


def _parse_literal(value: object) -> LiteralValue:
    if isinstance(value, (str, bool)):
        return value
    data = _object(value, "type.literal.value")
    _exact_keys(data, {"integer_value"}, "type.literal.integer")
    return LiteralInteger(_integer_value(data["integer_value"], "type.literal.integer_value"))


def _parse_model_ref(value: Mapping[str, object], path: str) -> ModelRefTypeExpr:
    _exact_keys(value, {"kind", "schema_id", "schema_version"}, path)
    return ModelRefTypeExpr("model_ref", _ascii_id(value, "schema_id", path), _positive_uint(value, "schema_version", path))


def _parse_union_alternative(value: object) -> UnionAlternative:
    data = _object(value, "type.union.alternative")
    _exact_keys(data, {"discriminator_value", "model"}, "type.union.alternative")
    model = _object(data["model"], "type.union.alternative.model")
    if _string(model, "kind", "type.union.alternative.model") != "model_ref":
        raise DeclarationParseError("type.union.alternative_model_invalid")
    return UnionAlternative(_string(data, "discriminator_value", "type.union.alternative"), _parse_model_ref(model, "type.union.alternative.model"))


def _parse_enum(raw: bytes, value: Mapping[str, object]) -> EnumRole:
    _exact_keys(value, {"role", "schema_id", "schema_version", "enums"}, "enum")
    enums: list[EnumDeclaration] = []
    for item in _array(value["enums"], "enum.enums"):
        data = _object(item, "enum.declaration")
        _exact_keys(data, {"qualified_id", "members"}, "enum.declaration")
        members = tuple(_parse_enum_member(member) for member in _array(data["members"], "enum.members"))
        _sorted_unique((member.member_id for member in members), "enum.members")
        _unique(tuple(member.wire_value for member in members), "enum.members.wire_values")
        enums.append(EnumDeclaration(_ascii_id(data, "qualified_id", "enum.declaration"), members))
    _sorted_unique((entry.qualified_id for entry in enums), "enum.enums")
    return EnumRole(raw, "enum", _ascii_id(value, "schema_id", "enum"), _positive_uint(value, "schema_version", "enum"), tuple(enums))


def _parse_enum_member(value: object) -> EnumMemberDeclaration:
    data = _object(value, "enum.member")
    _exact_keys(data, {"member_id", "wire_value"}, "enum.member")
    return EnumMemberDeclaration(_ascii_id(data, "member_id", "enum.member"), _string(data, "wire_value", "enum.member"))


def _parse_optional(raw: bytes, value: Mapping[str, object]) -> OptionalRole:
    _exact_keys(value, {"role", "schema_id", "schema_version", "fields"}, "optional")
    fields: list[OptionalFieldDeclaration] = []
    for item in _array(value["fields"], "optional.fields"):
        data = _object(item, "optional.field")
        _exact_keys(data, {"field_name", "policy"}, "optional.field")
        policy = _string(data, "policy", "optional.field")
        if policy not in {"required", "omittable_nonnull", "required_nullable", "omittable_nullable"}:
            raise DeclarationParseError("optional.policy_invalid")
        fields.append(OptionalFieldDeclaration(_ascii_id(data, "field_name", "optional.field"), policy))
    _sorted_unique((field.field_name for field in fields), "optional.fields")
    return OptionalRole(raw, "optional", _ascii_id(value, "schema_id", "optional"), _positive_uint(value, "schema_version", "optional"), tuple(fields))


def _parse_numeric(raw: bytes, value: Mapping[str, object]) -> NumericRole:
    _exact_keys(value, {"role", "schema_id", "schema_version", "fields"}, "numeric")
    fields: list[NumericFieldDeclaration] = []
    for item in _array(value["fields"], "numeric.fields"):
        data = _object(item, "numeric.field")
        keys = {"field_name", "representation", "encoding_spec_id", "unit", "scale", "lower", "lower_inclusive", "upper", "upper_inclusive", "reject_inexact"}
        _exact_keys(data, keys, "numeric.field")
        representation = _string(data, "representation", "numeric.field")
        encoding_spec_id = data["encoding_spec_id"]
        nullable = (data["unit"], data["scale"], data["lower"], data["lower_inclusive"], data["upper"], data["upper_inclusive"], data["reject_inexact"])
        if representation == "canonical_decimal_quantity":
            if not (isinstance(encoding_spec_id, str) and _ASCII_ID.fullmatch(encoding_spec_id) and isinstance(nullable[0], str) and isinstance(nullable[1], str) and _POSITIVE_UINT.fullmatch(nullable[1]) and isinstance(nullable[2], str) and isinstance(nullable[3], bool) and isinstance(nullable[4], str) and isinstance(nullable[5], bool) and isinstance(nullable[6], bool)):
                raise DeclarationParseError("numeric.decimal_policy_invalid")
        elif representation == "canonical_finite_binary64":
            if encoding_spec_id is not None or any(item is not None for item in nullable):
                raise DeclarationParseError("numeric.binary64_policy_invalid")
        else:
            raise DeclarationParseError("numeric.representation_invalid")
        fields.append(NumericFieldDeclaration(_ascii_id(data, "field_name", "numeric.field"), representation, cast(str | None, encoding_spec_id), cast(str | None, nullable[0]), cast(str | None, nullable[1]), cast(str | None, nullable[2]), cast(bool | None, nullable[3]), cast(str | None, nullable[4]), cast(bool | None, nullable[5]), cast(bool | None, nullable[6])))
    _sorted_unique((field.field_name for field in fields), "numeric.fields")
    return NumericRole(raw, "numeric", _ascii_id(value, "schema_id", "numeric"), _positive_uint(value, "schema_version", "numeric"), tuple(fields))


def _parse_policy(raw: bytes, value: Mapping[str, object]) -> DigestSignatureRole:
    _exact_keys(value, {"role", "schema_id", "schema_version", "policy"}, "digest-signature")
    data = _object(value["policy"], "digest-signature.policy")
    kind = _string(data, "kind", "digest-signature.policy")
    if kind == "ordinary":
        _exact_keys(data, {"kind"}, "digest-signature.policy")
        policy: DigestSignaturePolicy = OrdinaryPolicy(kind)
    elif kind == "self_digest":
        _exact_keys(data, {"kind", "digest_field", "digest_domain"}, "digest-signature.policy")
        policy = SelfDigestPolicy(kind, _ascii_id(data, "digest_field", "digest-signature.policy"), _ascii_id(data, "digest_domain", "digest-signature.policy"))
    elif kind == "signature_only":
        _exact_keys(data, {"kind", "signature_field", "signature_purpose", "signature_domain"}, "digest-signature.policy")
        policy = SignatureOnlyPolicy(kind, _ascii_id(data, "signature_field", "digest-signature.policy"), _ascii_id(data, "signature_purpose", "digest-signature.policy"), _ascii_id(data, "signature_domain", "digest-signature.policy"))
    elif kind == "external_signing_preimage":
        required = {"kind", "result_digest_field", "result_signature_field", "preimage_schema_id", "preimage_schema_version", "binding_kind", "signature_purpose", "signature_domain"}
        _exact_keys(data, required, "digest-signature.policy")
        for name, expected in (("preimage_schema_id", "ObservationCheckpointSigningPreimage"), ("preimage_schema_version", "1"), ("binding_kind", "observation_checkpoint_v1"), ("signature_purpose", "observation_checkpoint")):
            _literal(data, name, expected, "digest-signature.policy")
        policy = ExternalSigningPreimagePolicy(kind, _ascii_id(data, "result_digest_field", "digest-signature.policy"), _ascii_id(data, "result_signature_field", "digest-signature.policy"), "ObservationCheckpointSigningPreimage", "1", "observation_checkpoint_v1", "observation_checkpoint", _ascii_id(data, "signature_domain", "digest-signature.policy"))
    else:
        raise DeclarationParseError("digest-signature.policy_kind_invalid")
    return DigestSignatureRole(raw, "digest-signature", _ascii_id(value, "schema_id", "digest-signature"), _positive_uint(value, "schema_version", "digest-signature"), policy)


def _grammar_literal(value: Mapping[str, object]) -> None:
    # The grammar role is a fixed authority byte string, not merely a matching shape.
    expected = b'{"envelope":{"binding_fields":["profile_id","profile_version","profile_digest","schema_id","schema_version","binding_digest"],"fields":["binding","canonical_value_bytes","canonical_value_digest","artifact_digest"],"permitted_value_kinds":["bytes","integer","map","scalar"]},"grammar_revision":"operational-3","json":{"canonical":"RFC8785","terminal_lf":false,"utf8":"strict"},"profile_id":"semantic_ingestion_typed_value","profile_version":"3","role":"grammar","tags":{"bytes":"rfc4648_standard_padded","datetime":"utc_six_fractional_digits","duration_microseconds":"signed_i64","enum":"registered_qualified_member","frozenset":"canonical_member_byte_order","integer":"canonical_decimal_string","list":"declared_order","map":"encoded_json_string_key_order","set":"canonical_member_byte_order","tuple":"declared_order"},"type_rules":{"bool_as_integer":false,"defaults_before_verification":false,"float_decimal":false,"map_keys":"string_only","model_fields":"registered_exact","optional":"registered_policy","union":"one_registered_discriminator"}}'
    if _canonical_json(value) != expected:
        raise DeclarationParseError("grammar_literal_mismatch")


def _decode_json(raw: bytes) -> object:
    try:
        text = raw.decode("utf-8", "strict")
        value = json.loads(text, object_pairs_hook=_no_duplicate_object, parse_int=_no_json_number, parse_float=_no_json_number, parse_constant=_no_json_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DeclarationParseError("declaration_json_invalid") from exc
    _validate_json_tree(value)

    return value


def _verify_canonical_json(value: object, raw: bytes) -> None:
    if _canonical_json(value) != raw:
        raise DeclarationParseError("declaration_not_rfc8785_canonical")


def _no_duplicate_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise DeclarationParseError("declaration_duplicate_key")
        result[key] = value
    return result


def _no_json_number(_: str) -> object:
    raise DeclarationParseError("declaration_json_number_forbidden")


def _no_json_constant(_: str) -> object:
    raise DeclarationParseError("declaration_json_number_forbidden")


def _validate_json_tree(value: object) -> None:
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, str):
            try:
                item.encode("utf-8", "strict")
            except UnicodeEncodeError as exc:
                raise DeclarationParseError("declaration_unicode_scalar_invalid") from exc
        elif isinstance(item, dict):
            for key, nested in item.items():
                if not key.isascii() or not key:
                    raise DeclarationParseError("declaration_object_key_invalid")
                pending.append(nested)
        elif isinstance(item, list):
            pending.extend(item)
        elif item is not None and not isinstance(item, bool):
            raise DeclarationParseError("declaration_json_value_invalid")


def _canonical_json(value: object) -> bytes:
    if isinstance(value, LiteralInteger):
        value = {"integer_value": value.value}
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False).encode("utf-8", "strict")
    except (TypeError, UnicodeEncodeError, ValueError) as exc:
        raise DeclarationParseError("declaration_json_value_invalid") from exc


def _precheck_nesting(raw: bytes, maximum_depth: int) -> None:
    depth = 0
    quoted = False
    escaped = False
    for byte in raw:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 0x5C:
                escaped = True
            elif byte == 0x22:
                quoted = False
            continue
        if byte == 0x22:
            quoted = True
        elif byte in (0x5B, 0x7B):
            depth += 1
            if depth > maximum_depth:
                raise DeclarationParseError("declaration_depth_limit_exceeded")
        elif byte in (0x5D, 0x7D):
            depth -= 1


def _check_tree_limits(value: object, limits: ProtectedDeclarationParseLimits) -> None:
    pending: list[tuple[object, int]] = [(value, 1)]
    nodes = 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        if nodes > limits.maximum_nodes:
            raise DeclarationParseError("declaration_nodes_limit_exceeded")
        if depth > limits.maximum_depth:
            raise DeclarationParseError("declaration_depth_limit_exceeded")
        if isinstance(item, dict):
            pending.extend((nested, depth + 1) for nested in item.values())
        elif isinstance(item, list):
            pending.extend((nested, depth + 1) for nested in item)


def _object(value: object, path: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise DeclarationParseError(f"{path}_must_be_object")
    return value


def _array(value: object, path: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise DeclarationParseError(f"{path}_must_be_array")
    return value


def _exact_keys(value: Mapping[str, object], expected: set[str], path: str) -> None:
    if set(value) != expected:
        raise DeclarationParseError(f"{path}_keys_invalid")


def _string(value: Mapping[str, object], name: str, path: str) -> str:
    item = value.get(name)
    if not isinstance(item, str):
        raise DeclarationParseError(f"{path}.{name}_must_be_string")
    return item


def _literal(value: Mapping[str, object], name: str, expected: str, path: str) -> None:
    if _string(value, name, path) != expected:
        raise DeclarationParseError(f"{path}.{name}_literal_invalid")


def _ascii_id(value: Mapping[str, object], name: str, path: str) -> str:
    item = _string(value, name, path)
    if not _ASCII_ID.fullmatch(item):
        raise DeclarationParseError(f"{path}.{name}_ascii_id_invalid")
    return item


def _positive_uint(value: Mapping[str, object], name: str, path: str) -> str:
    item = _string(value, name, path)
    if not _POSITIVE_UINT.fullmatch(item):
        raise DeclarationParseError(f"{path}.{name}_positive_uint_invalid")
    return item


def _integer_value(value: object, path: str) -> str:
    if not isinstance(value, str) or not _INTEGER.fullmatch(value):
        raise DeclarationParseError(f"{path}_integer_invalid")
    return value


def _integer_or_null(value: object, path: str) -> str | None:
    if value is None:
        return None
    return _integer_value(value, path)


def _integer_compare(left: str, right: str) -> int:
    """Compare canonical integer strings without numeric conversion limits."""
    left_negative = left.startswith("-")
    right_negative = right.startswith("-")
    if left_negative != right_negative:
        return -1 if left_negative else 1
    left_digits = left[1:] if left_negative else left
    right_digits = right[1:] if right_negative else right
    magnitude = (len(left_digits) > len(right_digits)) - (len(left_digits) < len(right_digits))
    if magnitude == 0:
        magnitude = (left_digits > right_digits) - (left_digits < right_digits)
    return -magnitude if left_negative else magnitude


def is_canonical_fixed_scale_decimal(value: str | None, scale: str | None) -> bool:
    """Validate a fixed-scale decimal without converting arbitrary precision."""
    if value is None or scale is None:
        return False
    unsigned = value[1:] if value.startswith("-") else value
    integer, separator, fraction = unsigned.partition(".")
    if not separator or not integer or not fraction:
        return False
    if not integer.isascii() or not fraction.isascii() or not integer.isdigit() or not fraction.isdigit():
        return False
    if len(integer) > 1 and integer.startswith("0"):
        return False
    if str(len(fraction)) != scale:
        return False
    return not value.startswith("-") or integer != "0" or any(digit != "0" for digit in fraction)


def _sha256(value: Mapping[str, object], name: str, path: str) -> str:
    return _sha256_value(value.get(name), f"{path}.{name}")


def _sha256_value(value: object, path: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise DeclarationParseError(f"{path}_sha256_invalid")
    return value


def _unique(values: Sequence[str], path: str) -> None:
    if len(set(values)) != len(values):
        raise DeclarationParseError(f"{path}_duplicate")


def _sorted_unique(values: Sequence[str] | object, path: str) -> None:
    sequence = tuple(cast(Sequence[str], values))
    encoded = tuple(_canonical_json(item) for item in sequence)
    if encoded != tuple(sorted(encoded)) or len(set(sequence)) != len(sequence):
        raise DeclarationParseError(f"{path}_not_unique_sorted")
