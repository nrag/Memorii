"""Cross-role compilation for protected operational typed-value declarations.

The compiler only accepts raw source bytes and reparses them before deriving
commitments.  Source manifests, decoder implementation loading, and runtime
publication belong to later owners.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from hashlib import sha256
from typing import TypeVar

from memorii.core.memory_evolution.ingestion_contracts import _length_prefixed
from memorii.core.memory_evolution.typed_value_declarations import (
    CollectionTypeExpr,
    DeclarationRole,
    DecoderRole,
    DigestSignatureRole,
    EnumRefTypeExpr,
    EnumRole,
    ExternalSigningPreimagePolicy,
    FieldDeclaration,
    FixedTupleTypeExpr,
    GrammarRole,
    LiteralTypeExpr,
    MapTypeExpr,
    ModelRefTypeExpr,
    NamedFieldTypeExpr,
    NumericRole,
    OptionalRole,
    OrdinaryPolicy,
    ParsedDeclaration,
    ProtectedDeclarationParseLimits,
    RegistryProfile,
    RegistryRole,
    ScalarTypeExpr,
    SchemaRole,
    SelfDigestPolicy,
    SignatureOnlyPolicy,
    TypeExpr,
    UnionTypeExpr,
    UpcastRole,
    is_canonical_fixed_scale_decimal,
    parse_typed_value_declaration,
)


class TypedValueRegistryCompilationError(ValueError):
    """A declaration set cannot form one closed operational registry."""


Coordinate = tuple[str, str]
RoleT = TypeVar("RoleT", bound=DeclarationRole)


@dataclass(frozen=True)
class CompiledProfile:
    profile_id: str
    profile_version: str
    grammar_revision: str
    grammar_digest: str
    profile_digest: str


@dataclass(frozen=True)
class CompiledPolicyDigests:
    enum_registry_digest: str
    optional_field_policy_digest: str
    numeric_encoding_spec_registry_digest: str
    digest_signature_field_policy_digest: str


@dataclass(frozen=True)
class CompiledRegistryEntry:
    profile: CompiledProfile
    schema_id: str
    schema_version: str
    schema_fingerprint: str
    policy_digests: CompiledPolicyDigests
    binding_digest: str
    decoder_id: str
    implementation_source_digest: str
    decoder_digest: str
    entry_digest: str
    read_status: str


@dataclass(frozen=True)
class CompiledTypedValueRegistry:
    profile: CompiledProfile
    entries: tuple[CompiledRegistryEntry, ...]
    registry_digest: str
    parsed_roles: tuple[ParsedDeclaration, ...]

    def entry_for(self, schema_id: str, schema_version: str) -> CompiledRegistryEntry:
        for entry in self.entries:
            if (entry.schema_id, entry.schema_version) == (schema_id, schema_version):
                return entry
        raise KeyError((schema_id, schema_version))


@dataclass(frozen=True)
class _Roles:
    schemas: Mapping[Coordinate, SchemaRole]
    enums: Mapping[Coordinate, EnumRole]
    optionals: Mapping[Coordinate, OptionalRole]
    numerics: Mapping[Coordinate, NumericRole]
    policies: Mapping[Coordinate, DigestSignatureRole]
    decoders: Mapping[Coordinate, DecoderRole]
    upcasts: Mapping[Coordinate, UpcastRole]


@dataclass(frozen=True)
class _ValidatedCompilationPreparation:
    parsed: tuple[ParsedDeclaration, ...]
    profile: CompiledProfile
    roles: _Roles


def compile_typed_value_registry(
    raw_role_sources: Iterable[bytes], *, limits: ProtectedDeclarationParseLimits
) -> CompiledTypedValueRegistry:
    """Reparse and compile one complete profile-3 declaration source set."""
    prepared = _prepare_validated_compilation(raw_role_sources, limits=limits)
    registry = _registry_role(prepared.parsed)
    profile = prepared.profile
    if registry.profile != _registry_profile(profile):
        raise TypedValueRegistryCompilationError("registry_profile_mismatch")
    entries = _compile_entries(prepared.roles, profile)
    if tuple(entry.entry_digest for entry in entries) != registry.entries:
        raise TypedValueRegistryCompilationError("registry_entry_digests_mismatch")
    registry_digest = _digest(
        b"semantic-ingestion-typed-value-registry",
        _text(profile.profile_id),
        _text(profile.profile_version),
        _text(profile.grammar_revision),
        _text(profile.grammar_digest),
        _text(profile.profile_digest),
        _text(str(len(entries))),
        *(_text(entry.entry_digest) for entry in entries),
    )
    return CompiledTypedValueRegistry(profile, entries, registry_digest, prepared.parsed)


def author_typed_value_registry_role(
    raw_non_registry_role_sources: Iterable[bytes], *, limits: ProtectedDeclarationParseLimits
) -> bytes:
    """Derive canonical registry-role bytes from one complete non-registry source set.

    This offline authoring operation is intentionally separate from production
    compilation: it has no supplied registry role to trust or verify.
    """
    prepared = _prepare_validated_compilation(
        raw_non_registry_role_sources,
        limits=limits,
        reject_registry_role=True,
    )
    entries = _compile_entries(prepared.roles, prepared.profile)
    raw = json.dumps(
        {
            "role": "registry",
            "profile": {
                "profile_id": prepared.profile.profile_id,
                "profile_version": prepared.profile.profile_version,
                "grammar_revision": prepared.profile.grammar_revision,
                "grammar_digest": prepared.profile.grammar_digest,
                "profile_digest": prepared.profile.profile_digest,
            },
            "entries": [entry.entry_digest for entry in entries],
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8", "strict")
    parsed = parse_typed_value_declaration(raw, limits=limits)
    if not isinstance(parsed, RegistryRole):
        raise AssertionError("registry author emitted a non-registry declaration")
    return raw


def typed_value_declaration_role_descriptor(parsed: ParsedDeclaration) -> str:
    """Return the canonical source-package role name for one parsed declaration."""
    if isinstance(parsed, GrammarRole):
        return "grammar"
    if isinstance(parsed, RegistryRole):
        return "registry"
    if isinstance(
        parsed,
        (SchemaRole, EnumRole, OptionalRole, NumericRole, DigestSignatureRole, DecoderRole, UpcastRole),
    ):
        return f"{parsed.role}/{parsed.schema_id}/{parsed.schema_version}"
    raise TypedValueRegistryCompilationError("typed_value_declaration_role_unknown")


def _prepare_validated_compilation(
    raw_role_sources: Iterable[bytes],
    *,
    limits: ProtectedDeclarationParseLimits,
    reject_registry_role: bool = False,
) -> _ValidatedCompilationPreparation:
    parsed = tuple(parse_typed_value_declaration(raw, limits=limits) for raw in raw_role_sources)
    if reject_registry_role and any(isinstance(item, RegistryRole) for item in parsed):
        raise TypedValueRegistryCompilationError("registry_role_supplied_to_author")
    grammar = _grammar_role(parsed)
    roles = _index_roles(parsed)
    _validate_complete_role_set(roles)
    profile = _compile_profile(
        grammar.raw_bytes,
        grammar.profile_id,
        grammar.profile_version,
        grammar.grammar_revision,
    )
    return _ValidatedCompilationPreparation(parsed, profile, roles)


def _compile_entries(roles: _Roles, profile: CompiledProfile) -> tuple[CompiledRegistryEntry, ...]:
    return tuple(
        _compile_entry(coordinate, roles, profile)
        for coordinate in sorted(roles.schemas, key=_entry_coordinate_sort_key)
    )


def _grammar_role(parsed: tuple[ParsedDeclaration, ...]) -> GrammarRole:
    matches = tuple(item for item in parsed if isinstance(item, GrammarRole))
    if len(matches) != 1:
        raise TypedValueRegistryCompilationError("grammar_role_count_invalid")
    return matches[0]


def _registry_role(parsed: tuple[ParsedDeclaration, ...]) -> RegistryRole:
    matches = tuple(item for item in parsed if isinstance(item, RegistryRole))
    if len(matches) != 1:
        raise TypedValueRegistryCompilationError("registry_role_count_invalid")
    return matches[0]


def _index_roles(parsed: tuple[ParsedDeclaration, ...]) -> _Roles:
    schemas: dict[Coordinate, SchemaRole] = {}
    enums: dict[Coordinate, EnumRole] = {}
    optionals: dict[Coordinate, OptionalRole] = {}
    numerics: dict[Coordinate, NumericRole] = {}
    policies: dict[Coordinate, DigestSignatureRole] = {}
    decoders: dict[Coordinate, DecoderRole] = {}
    upcasts: dict[Coordinate, UpcastRole] = {}
    for item in parsed:
        if isinstance(item, SchemaRole):
            _insert_role(schemas, (item.schema_id, item.schema_version), item)
        elif isinstance(item, EnumRole):
            _insert_role(enums, (item.schema_id, item.schema_version), item)
        elif isinstance(item, OptionalRole):
            _insert_role(optionals, (item.schema_id, item.schema_version), item)
        elif isinstance(item, NumericRole):
            _insert_role(numerics, (item.schema_id, item.schema_version), item)
        elif isinstance(item, DigestSignatureRole):
            _insert_role(policies, (item.schema_id, item.schema_version), item)
        elif isinstance(item, DecoderRole):
            _insert_role(decoders, (item.schema_id, item.schema_version), item)
        elif isinstance(item, UpcastRole):
            _insert_role(upcasts, (item.schema_id, item.schema_version), item)
        elif not isinstance(item, (GrammarRole, RegistryRole)):
            raise TypedValueRegistryCompilationError("registry_role_unknown")
    return _Roles(schemas, enums, optionals, numerics, policies, decoders, upcasts)


def _insert_role(table: dict[Coordinate, RoleT], coordinate: Coordinate, role: RoleT) -> None:
    if coordinate in table:
        raise TypedValueRegistryCompilationError("registry_role_coordinate_duplicate")
    table[coordinate] = role


def _validate_complete_role_set(roles: _Roles) -> None:
    coordinates = set(roles.schemas)
    if not coordinates or any(set(table) != coordinates for table in (roles.enums, roles.optionals, roles.numerics, roles.policies, roles.decoders, roles.upcasts)):
        raise TypedValueRegistryCompilationError("registry_role_set_incomplete")
    for coordinate, schema in roles.schemas.items():
        _validate_schema_local_cross_role(schema, roles.optionals[coordinate], roles.numerics[coordinate], roles.policies[coordinate])
        if roles.upcasts[coordinate].raw_bytes and (roles.upcasts[coordinate].schema_id, roles.upcasts[coordinate].schema_version) != coordinate:
            raise TypedValueRegistryCompilationError("upcast_coordinate_invalid")
    _validate_numeric_encoding_spec_ids(roles)


def _validate_schema_local_cross_role(schema: SchemaRole, optional: OptionalRole, numeric: NumericRole, policy: DigestSignatureRole) -> None:
    fields = {field.name: field for field in schema.fields}
    if set(fields) != {field.field_name for field in optional.fields}:
        raise TypedValueRegistryCompilationError("optional_field_closure_invalid")
    wrappers = {
        field.name: field.type
        for field in schema.fields
        if isinstance(field.type, NamedFieldTypeExpr) and field.type.field_name == field.name
    }
    numeric_expected = {
        name: expression.kind for name, expression in wrappers.items()
    }
    numeric_actual = {field.field_name: field.representation for field in numeric.fields}
    all_wrappers = tuple(
        expression
        for field in schema.fields
        for expression in _walk_types((field.type,))
        if isinstance(expression, NamedFieldTypeExpr)
    )
    if len(all_wrappers) != len(wrappers) or numeric_expected != numeric_actual:
        raise TypedValueRegistryCompilationError("numeric_field_closure_invalid")
    for field in numeric.fields:
        if field.representation == "canonical_decimal_quantity" and (
            not is_canonical_fixed_scale_decimal(field.lower, field.scale)
            or not is_canonical_fixed_scale_decimal(field.upper, field.scale)
        ):
            raise TypedValueRegistryCompilationError("numeric_decimal_bound_lexical_invalid")
    current = policy.policy
    integrity = {name: field.integrity_role for name, field in fields.items()}
    if isinstance(current, OrdinaryPolicy):
        valid = all(role == "ordinary" for role in integrity.values())
    elif isinstance(current, SelfDigestPolicy):
        valid = (
            integrity.get(current.digest_field) == "self_digest"
            and _has_integrity_lexical_type(fields.get(current.digest_field), "sha256")
            and tuple(integrity.values()).count("self_digest") == 1
            and "signature" not in integrity.values()
        )
    elif isinstance(current, SignatureOnlyPolicy):
        valid = (
            integrity.get(current.signature_field) == "signature"
            and _has_integrity_lexical_type(fields.get(current.signature_field), "signature_hex128")
            and tuple(integrity.values()).count("signature") == 1
            and "self_digest" not in integrity.values()
        )
    elif isinstance(current, ExternalSigningPreimagePolicy):
        valid = (
            (schema.schema_id, schema.schema_version) == ("IngestionObservationReplayCheckpoint", "1")
            and integrity.get(current.result_digest_field) == "self_digest"
            and _has_integrity_lexical_type(fields.get(current.result_digest_field), "sha256")
            and integrity.get(current.result_signature_field) == "signature"
            and _has_integrity_lexical_type(fields.get(current.result_signature_field), "signature_hex128")
            and tuple(integrity.values()).count("self_digest") == 1
            and tuple(integrity.values()).count("signature") == 1
        )
    else:
        valid = False
    if not valid:
        raise TypedValueRegistryCompilationError("digest_signature_policy_closure_invalid")


def _validate_numeric_encoding_spec_ids(roles: _Roles) -> None:
    declared: set[str] = set()
    for numeric in roles.numerics.values():
        for field in numeric.fields:
            if field.representation == "canonical_decimal_quantity":
                assert field.encoding_spec_id is not None
                if field.encoding_spec_id in declared:
                    raise TypedValueRegistryCompilationError("numeric_encoding_spec_id_duplicate")
                declared.add(field.encoding_spec_id)


def _has_integrity_lexical_type(field: FieldDeclaration | None, lexical_rule: str) -> bool:
    return (
        isinstance(field, FieldDeclaration)
        and isinstance(field.type, ScalarTypeExpr)
        and field.type.kind == "string"
        and field.type.lexical_rule == lexical_rule
    )


def _compile_entry(coordinate: Coordinate, roles: _Roles, profile: CompiledProfile) -> CompiledRegistryEntry:
    closure = _schema_closure(coordinate, roles)
    _validate_references(closure, roles)
    schema_fingerprint = _closure_digest(b"semantic-ingestion-typed-value-schema-fingerprint", coordinate, closure, roles.schemas)
    policies = CompiledPolicyDigests(
        _policy_digest("enum", coordinate, closure, roles.enums),
        _policy_digest("optional", coordinate, closure, roles.optionals),
        _policy_digest("numeric", coordinate, closure, roles.numerics),
        _policy_digest("digest-signature", coordinate, closure, roles.policies),
    )
    schema_id, schema_version = coordinate
    binding_digest = _digest(b"semantic-ingestion-typed-value-binding", _text(profile.profile_id), _text(profile.profile_version), _text(profile.profile_digest), _text(schema_id), _text(schema_version), _text(schema_fingerprint), _text(policies.enum_registry_digest), _text(policies.optional_field_policy_digest), _text(policies.numeric_encoding_spec_registry_digest), _text(policies.digest_signature_field_policy_digest))
    decoder = roles.decoders[coordinate]
    decoder_digest = _digest(b"semantic-ingestion-typed-value-decoder", _text(decoder.decoder_id), b"model", _text(decoder.implementation_source_digest))
    entry_digest = _digest(b"semantic-ingestion-typed-value-registry-entry", _text(profile.profile_id), _text(profile.profile_version), _text(profile.profile_digest), _text(schema_id), _text(schema_version), _text(binding_digest), _text(schema_fingerprint), _text(policies.enum_registry_digest), _text(policies.optional_field_policy_digest), _text(policies.numeric_encoding_spec_registry_digest), _text(policies.digest_signature_field_policy_digest), _text(decoder_digest), b"0", b"", b"", b"active")
    return CompiledRegistryEntry(profile, schema_id, schema_version, schema_fingerprint, policies, binding_digest, decoder.decoder_id, decoder.implementation_source_digest, decoder_digest, entry_digest, "active")


def _schema_closure(root: Coordinate, roles: _Roles) -> tuple[Coordinate, ...]:
    seen: set[Coordinate] = set()
    visiting: set[Coordinate] = set()
    def visit(coordinate: Coordinate) -> None:
        if coordinate in visiting:
            raise TypedValueRegistryCompilationError("schema_dependency_cycle")
        if coordinate in seen:
            return
        schema = roles.schemas.get(coordinate)
        if schema is None:
            raise TypedValueRegistryCompilationError("schema_dependency_unresolved")
        visiting.add(coordinate)
        for expression in _walk_types(field.type for field in schema.fields):
            if isinstance(expression, ModelRefTypeExpr):
                visit((expression.schema_id, expression.schema_version))
        policy = roles.policies[coordinate].policy
        if isinstance(policy, ExternalSigningPreimagePolicy):
            visit((policy.preimage_schema_id, policy.preimage_schema_version))
        visiting.remove(coordinate)
        seen.add(coordinate)
    visit(root)
    return tuple(sorted(seen, key=_closure_coordinate_sort_key))


def _validate_references(closure: tuple[Coordinate, ...], roles: _Roles) -> None:
    enum_ids = {entry.qualified_id for coordinate in closure for entry in roles.enums[coordinate].enums}
    if len(enum_ids) != sum(len(roles.enums[coordinate].enums) for coordinate in closure):
        raise TypedValueRegistryCompilationError("enum_identity_duplicate")
    for coordinate in closure:
        policy = roles.policies[coordinate].policy
        if isinstance(policy, ExternalSigningPreimagePolicy) and not isinstance(
            roles.policies[(policy.preimage_schema_id, policy.preimage_schema_version)].policy,
            OrdinaryPolicy,
        ):
            raise TypedValueRegistryCompilationError("external_preimage_policy_invalid")
        for expression in _walk_types(field.type for field in roles.schemas[coordinate].fields):
            if isinstance(expression, EnumRefTypeExpr) and expression.qualified_id not in enum_ids:
                raise TypedValueRegistryCompilationError("enum_reference_unresolved")
            if isinstance(expression, UnionTypeExpr):
                for alternative in expression.alternatives:
                    schema = roles.schemas.get((alternative.model.schema_id, alternative.model.schema_version))
                    field = None if schema is None else next((item for item in schema.fields if item.name == expression.discriminator), None)
                    if field is None or not isinstance(field.type, LiteralTypeExpr) or field.type.values != (alternative.discriminator_value,):
                        raise TypedValueRegistryCompilationError("union_discriminator_closure_invalid")


def _walk_types(roots: Iterable[TypeExpr]) -> Iterable[TypeExpr]:
    pending = list(roots)
    while pending:
        current = pending.pop()
        yield current
        if isinstance(current, CollectionTypeExpr):
            pending.append(current.element)
        elif isinstance(current, FixedTupleTypeExpr):
            pending.extend(current.items)
        elif isinstance(current, MapTypeExpr):
            pending.append(current.value)
        elif isinstance(current, UnionTypeExpr):
            pending.extend(item.model for item in current.alternatives)


def _compile_profile(grammar_bytes: bytes, profile_id: str, profile_version: str, grammar_revision: str) -> CompiledProfile:
    grammar_digest = sha256(grammar_bytes).hexdigest()
    profile_digest = _digest(b"semantic-ingestion-typed-value-profile", _text(profile_id), _text(profile_version), _text(grammar_revision), grammar_bytes)
    return CompiledProfile(profile_id, profile_version, grammar_revision, grammar_digest, profile_digest)


def _registry_profile(profile: CompiledProfile) -> object:
    return RegistryProfile(profile.profile_id, profile.profile_version, profile.grammar_revision, profile.grammar_digest, profile.profile_digest)


def _closure_digest(domain: bytes, root: Coordinate, closure: tuple[Coordinate, ...], table: Mapping[Coordinate, DeclarationRole]) -> str:
    parts: list[bytes] = [domain, _text(root[0]), _text(root[1]), _text(str(len(closure)))]
    for coordinate in closure:
        role = table[coordinate]
        parts.extend((_text(coordinate[0]), _text(coordinate[1]), role.raw_bytes))
    return _digest(*parts)


def _policy_digest(role_kind: str, root: Coordinate, closure: tuple[Coordinate, ...], table: Mapping[Coordinate, DeclarationRole]) -> str:
    parts: list[bytes] = [b"semantic-ingestion-typed-value-policy-closure", _text(role_kind), _text(root[0]), _text(root[1]), _text(str(len(closure)))]
    for coordinate in closure:
        role = table[coordinate]
        parts.extend((_text(coordinate[0]), _text(coordinate[1]), role.raw_bytes))
    return _digest(*parts)


def _digest(*parts: bytes) -> str:
    return sha256(_length_prefixed(*parts)).hexdigest()


def _text(value: str) -> bytes:
    return value.encode("utf-8", "strict")


def _closure_coordinate_sort_key(coordinate: Coordinate) -> tuple[bytes, int, bytes]:
    # Positive canonical decimal strings compare mathematically by length then
    # bytes, without inheriting Python's configurable integer-digit limit.
    version = coordinate[1].encode("ascii")
    return coordinate[0].encode("utf-8"), len(version), version


def _entry_coordinate_sort_key(coordinate: Coordinate) -> tuple[bytes, bytes]:
    return coordinate[0].encode("utf-8"), coordinate[1].encode("utf-8")
