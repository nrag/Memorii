"""Frozen, independently-authored rejection vectors for the profile-3 registry.

This is deliberately a small vector author, not another registry compiler.  It
uses only the normative raw-source grammar, SHA-256, canonical JSON, and the
specified length-prefix construction to make one complete synthetic package and
targeted invalid variants.  A harness supplies the pairs and optional external
source files to the primary compiler; this module never imports it.
"""

from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import dataclass, replace
from typing import Any, Literal

_PROFILE_ID = "semantic_ingestion_typed_value"
_PROFILE_VERSION = "3"
_GRAMMAR_REVISION = "operational-3"
_HEX = "0123456789abcdef"


@dataclass(frozen=True)
class DecoderSourceFile:
    """A whole decoder-source file a vector harness should materialize.

    ``symlink_target`` is relative to the source root.  It is present solely
    for fail-closed path vectors; ordinary files have ``None``.
    """

    relative_path: str
    raw_bytes: bytes
    symlink_target: str | None = None


@dataclass(frozen=True)
class RegistryExpectedEntry:
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
class RegistryExpectedReport:
    """Normalized complete successful output, using no production types."""

    profile_digest: str
    profile_preimage: bytes
    registry_digest: str
    registry_preimage: bytes
    entries: tuple[RegistryExpectedEntry, ...]
    publication_manifest_digest: str


@dataclass(frozen=True)
class RegistryRejectionVector:
    """One immutable compiler input and its normative outcome."""

    name: str
    expected_valid: bool
    rationale: str
    raw_role_pairs: tuple[tuple[str, bytes], ...]
    decoder_source_files: tuple[DecoderSourceFile, ...]
    decoder_source_manifest_bytes: bytes | None
    publication_manifest_bytes: bytes | None
    boundary: Literal["declaration", "registry", "source", "publication"] = "declaration"
    expected_report: RegistryExpectedReport | None = None
    source_root_relative_path: str = "."
    source_root_symlink_target: str | None = None


def declaration_role_pairs(vector: RegistryRejectionVector) -> tuple[tuple[str, bytes], ...]:
    """Return authoring input without the derived registry commitment.

    A harness uses this path for malformed declarations, so rejection cannot be
    masked by a stale registry-entry digest.
    """
    return tuple(pair for pair in vector.raw_role_pairs if pair[0] != "registry")


def _canonical(value: object) -> bytes:
    """RFC-8785-compatible bytes for this ASCII-only synthetic package."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _lp(*parts: str | bytes) -> bytes:
    output = bytearray()
    for part in parts:
        raw = part.encode("utf-8") if isinstance(part, str) else part
        output.extend(struct.pack(">Q", len(raw)))
        output.extend(raw)
    return bytes(output)


def _copy(value: Any) -> Any:
    """JSON-only deep copy, keeping mutations isolated between vectors."""
    return json.loads(json.dumps(value))


def _grammar() -> dict[str, object]:
    # This is the normative literal content.  _canonical produces its specified
    # ASCII key ordering and no terminal LF.
    return {
        "envelope": {
            "binding_fields": [
                "profile_id", "profile_version", "profile_digest", "schema_id",
                "schema_version", "binding_digest",
            ],
            "fields": ["binding", "canonical_value_bytes", "canonical_value_digest", "artifact_digest"],
            "permitted_value_kinds": ["bytes", "integer", "map", "scalar"],
        },
        "grammar_revision": _GRAMMAR_REVISION,
        "json": {"canonical": "RFC8785", "terminal_lf": False, "utf8": "strict"},
        "profile_id": _PROFILE_ID,
        "profile_version": _PROFILE_VERSION,
        "role": "grammar",
        "tags": {
            "bytes": "rfc4648_standard_padded", "datetime": "utc_six_fractional_digits",
            "duration_microseconds": "signed_i64", "enum": "registered_qualified_member",
            "frozenset": "canonical_member_byte_order", "integer": "canonical_decimal_string",
            "list": "declared_order", "map": "encoded_json_string_key_order",
            "set": "canonical_member_byte_order", "tuple": "declared_order",
        },
        "type_rules": {
            "bool_as_integer": False, "defaults_before_verification": False,
            "float_decimal": False, "map_keys": "string_only", "model_fields": "registered_exact",
            "optional": "registered_policy", "union": "one_registered_discriminator",
        },
    }


def _role_objects() -> dict[str, dict[str, object]]:
    """The smallest complete two-model package with nested and numeric closure."""
    ordinary = {"kind": "ordinary"}

    def required(*names: str) -> list[dict[str, str]]:
        return [{"field_name": name, "policy": "required"} for name in names]

    return {
        "grammar": _grammar(),
        "schema/Leaf/1": {
            "role": "schema", "schema_id": "Leaf", "schema_version": "1", "root_kind": "model",
            "fields": [
                {"name": "amount", "integrity_role": "ordinary", "type": {"kind": "canonical_decimal_quantity", "field_name": "amount"}},
                {"name": "flavor", "integrity_role": "ordinary", "type": {"kind": "enum_ref", "qualified_id": "ExampleFlavor"}},
            ],
        },
        "enum/Leaf/1": {"role": "enum", "schema_id": "Leaf", "schema_version": "1", "enums": [{"qualified_id": "ExampleFlavor", "members": [{"member_id": "plain", "wire_value": "plain"}]}]},
        "optional/Leaf/1": {"role": "optional", "schema_id": "Leaf", "schema_version": "1", "fields": required("amount", "flavor")},
        "numeric/Leaf/1": {"role": "numeric", "schema_id": "Leaf", "schema_version": "1", "fields": [{"encoding_spec_id": "example.amount.v1", "field_name": "amount", "lower": "0.00", "lower_inclusive": True, "reject_inexact": True, "representation": "canonical_decimal_quantity", "scale": "2", "unit": "unit", "upper": "10.00", "upper_inclusive": True}]},
        "digest-signature/Leaf/1": {"role": "digest-signature", "schema_id": "Leaf", "schema_version": "1", "policy": ordinary},
        "decoder/Leaf/1": {"role": "decoder", "schema_id": "Leaf", "schema_version": "1", "decoder_id": "example.leaf", "typed_root_kind": "model", "implementation_source_digest": ""},
        "upcast/Leaf/1": {"role": "upcast", "schema_id": "Leaf", "schema_version": "1", "target_binding": None, "upcaster_id": None, "implementation_source_digest": None},
        "schema/Root/1": {
            "role": "schema", "schema_id": "Root", "schema_version": "1", "root_kind": "model",
            "fields": [
                {"name": "child", "integrity_role": "ordinary", "type": {"kind": "model_ref", "schema_id": "Leaf", "schema_version": "1"}},
                {"name": "kind", "integrity_role": "ordinary", "type": {"kind": "literal", "values": ["root"]}},
            ],
        },
        "enum/Root/1": {"role": "enum", "schema_id": "Root", "schema_version": "1", "enums": []},
        "optional/Root/1": {"role": "optional", "schema_id": "Root", "schema_version": "1", "fields": required("child", "kind")},
        "numeric/Root/1": {"role": "numeric", "schema_id": "Root", "schema_version": "1", "fields": []},
        "digest-signature/Root/1": {"role": "digest-signature", "schema_id": "Root", "schema_version": "1", "policy": ordinary},
        "decoder/Root/1": {"role": "decoder", "schema_id": "Root", "schema_version": "1", "decoder_id": "example.root", "typed_root_kind": "model", "implementation_source_digest": ""},
        "upcast/Root/1": {"role": "upcast", "schema_id": "Root", "schema_version": "1", "target_binding": None, "upcaster_id": None, "implementation_source_digest": None},
    }


def _snapshot(decoder_id: str, files: list[tuple[str, str, bytes]]) -> str:
    parts: list[str | bytes] = ["semantic-ingestion-profile3-decoder-source-snapshot", decoder_id, str(len(files))]
    for source_file_id, path, raw in sorted(files):
        parts.extend((source_file_id, path, raw))
    return _sha(_lp(*parts))


def _publication_digest(
    decoder_manifest: bytes,
    snapshots: list[dict[str, str]],
    registry_digest: str,
    identities: list[dict[str, str]],
) -> str:
    parts: list[str | bytes] = [
        "semantic-ingestion-profile3-publication-manifest", _PROFILE_ID,
        _PROFILE_VERSION, str(len(identities)),
    ]
    for item in identities:
        parts.extend((item["role"], item["sha256"]))
    parts.extend((_sha(decoder_manifest), str(len(snapshots))))
    for snapshot in snapshots:
        parts.extend((str(snapshot["decoder_id"]), str(snapshot["source_snapshot_digest"])))
    parts.append(registry_digest)
    return _sha(_lp(*parts))


def _closure_digest(domain: str, kind: str | None, root: tuple[str, str], closure: list[tuple[str, str]], roles: dict[str, bytes]) -> str:
    parts: list[str | bytes] = [domain]
    if kind is not None:
        parts.append(kind)
    parts.extend((root[0], root[1], str(len(closure))))
    for schema_id, schema_version in closure:
        parts.extend((schema_id, schema_version, roles[f"{kind}/{schema_id}/{schema_version}"] if kind else roles[f"schema/{schema_id}/{schema_version}"]))
    return _sha(_lp(*parts))


def _derived_registry(role_bytes: dict[str, bytes]) -> tuple[bytes, str, RegistryExpectedReport]:
    """Derive complete entry commitments from the two declared closure graphs."""
    grammar = role_bytes["grammar"]
    grammar_digest = _sha(grammar)
    profile_digest = _sha(_lp("semantic-ingestion-typed-value-profile", _PROFILE_ID, _PROFILE_VERSION, _GRAMMAR_REVISION, grammar))
    closures = {("Leaf", "1"): [("Leaf", "1")], ("Root", "1"): [("Leaf", "1"), ("Root", "1")]}
    entries: list[str] = []
    expected_entries: list[RegistryExpectedEntry] = []
    for root in (("Leaf", "1"), ("Root", "1")):
        closure = closures[root]
        schema_fingerprint = _closure_digest("semantic-ingestion-typed-value-schema-fingerprint", None, root, closure, role_bytes)
        enum_digest = _closure_digest("semantic-ingestion-typed-value-policy-closure", "enum", root, closure, role_bytes)
        optional_digest = _closure_digest("semantic-ingestion-typed-value-policy-closure", "optional", root, closure, role_bytes)
        numeric_digest = _closure_digest("semantic-ingestion-typed-value-policy-closure", "numeric", root, closure, role_bytes)
        policy_digest = _closure_digest("semantic-ingestion-typed-value-policy-closure", "digest-signature", root, closure, role_bytes)
        decoder = json.loads(role_bytes[f"decoder/{root[0]}/{root[1]}"])
        decoder_digest = _sha(_lp("semantic-ingestion-typed-value-decoder", decoder["decoder_id"], "model", decoder["implementation_source_digest"]))
        binding = _sha(_lp("semantic-ingestion-typed-value-binding", _PROFILE_ID, _PROFILE_VERSION, profile_digest, *root, schema_fingerprint, enum_digest, optional_digest, numeric_digest, policy_digest))
        entry_preimage = _lp("semantic-ingestion-typed-value-registry-entry", _PROFILE_ID, _PROFILE_VERSION, profile_digest, *root, binding, schema_fingerprint, enum_digest, optional_digest, numeric_digest, policy_digest, decoder_digest, "0", b"", b"", "active")
        entry_digest = _sha(entry_preimage)
        entries.append(entry_digest)
        expected_entries.append(
            RegistryExpectedEntry(
                root[0], root[1], schema_fingerprint, enum_digest,
                optional_digest, numeric_digest, policy_digest, decoder_digest,
                binding, entry_digest, entry_preimage,
            )
        )
    registry_preimage = _lp("semantic-ingestion-typed-value-registry", _PROFILE_ID, _PROFILE_VERSION, _GRAMMAR_REVISION, grammar_digest, profile_digest, str(len(entries)), *entries)
    registry_digest = _sha(registry_preimage)
    report = RegistryExpectedReport(profile_digest, _lp("semantic-ingestion-typed-value-profile", _PROFILE_ID, _PROFILE_VERSION, _GRAMMAR_REVISION, grammar), registry_digest, registry_preimage, tuple(expected_entries), "")
    return _canonical({"role": "registry", "profile": {"profile_id": _PROFILE_ID, "profile_version": _PROFILE_VERSION, "grammar_revision": _GRAMMAR_REVISION, "grammar_digest": grammar_digest, "profile_digest": profile_digest}, "entries": entries}), registry_digest, report


def _base() -> RegistryRejectionVector:
    objects = _role_objects()
    source_files = (
        DecoderSourceFile("native/leaf.py", b"def decode_leaf(raw):\n    return raw\n"),
        DecoderSourceFile("native/root.py", b"def decode_root(raw):\n    return raw\n"),
    )
    by_path = {item.relative_path: item.raw_bytes for item in source_files}
    rows = [
        {"decoder_id": "example.leaf", "source_file_id": "native_leaf", "relative_path": "native/leaf.py", "sha256": _sha(by_path["native/leaf.py"])},
        {"decoder_id": "example.root", "source_file_id": "native_root", "relative_path": "native/root.py", "sha256": _sha(by_path["native/root.py"])},
    ]
    manifest = _canonical({"role": "decoder_source_manifest", "profile_id": _PROFILE_ID, "profile_version": _PROFILE_VERSION, "files": rows})
    objects["decoder/Leaf/1"]["implementation_source_digest"] = _snapshot("example.leaf", [("native_leaf", "native/leaf.py", by_path["native/leaf.py"])])
    objects["decoder/Root/1"]["implementation_source_digest"] = _snapshot("example.root", [("native_root", "native/root.py", by_path["native/root.py"])])
    raw_roles = {role: _canonical(value) for role, value in objects.items()}
    registry, registry_digest, expected = _derived_registry(raw_roles)
    raw_roles["registry"] = registry
    identities = [{"role": role, "sha256": _sha(raw)} for role, raw in sorted(raw_roles.items())]
    snapshots = [
        {"decoder_id": "example.leaf", "source_snapshot_digest": objects["decoder/Leaf/1"]["implementation_source_digest"]},
        {"decoder_id": "example.root", "source_snapshot_digest": objects["decoder/Root/1"]["implementation_source_digest"]},
    ]
    publication = _canonical({"role": "publication_manifest", "profile_id": _PROFILE_ID, "profile_version": _PROFILE_VERSION, "files": identities, "decoder_source_manifest_digest": _sha(manifest), "decoder_source_snapshots": snapshots, "registry_digest": registry_digest})
    expected = replace(expected, publication_manifest_digest=_publication_digest(manifest, snapshots, registry_digest, identities))
    return RegistryRejectionVector("valid_complete_package", True, "Complete synthetic nested package with derived registry and external manifests.", tuple(sorted(raw_roles.items())), source_files, manifest, publication, boundary="registry", expected_report=expected)


def _roles(vector: RegistryRejectionVector) -> dict[str, bytes]:
    return dict(vector.raw_role_pairs)


def _with_role(vector: RegistryRejectionVector, role: str, value: object | bytes) -> RegistryRejectionVector:
    pairs = _roles(vector)
    pairs[role] = value if isinstance(value, bytes) else _canonical(value)
    return replace(vector, raw_role_pairs=tuple(sorted(pairs.items())))


def _mutated(vector: RegistryRejectionVector, name: str, rationale: str, role: str, edit) -> RegistryRejectionVector:
    value = json.loads(_roles(vector)[role])
    edit(value)
    return replace(_with_role(vector, role, value), name=name, expected_valid=False, rationale=rationale, boundary="declaration", expected_report=None)


def _raw_reject(valid: RegistryRejectionVector, name: str, raw: bytes, rationale: str) -> RegistryRejectionVector:
    return replace(_with_role(valid, "schema/Leaf/1", raw), name=name, expected_valid=False, rationale=rationale, boundary="declaration", expected_report=None)


def _source_reject(valid: RegistryRejectionVector, name: str, manifest: object, rationale: str, files: tuple[DecoderSourceFile, ...] | None = None) -> RegistryRejectionVector:
    return replace(valid, name=name, expected_valid=False, rationale=rationale, boundary="source", decoder_source_manifest_bytes=_canonical(manifest), decoder_source_files=files or valid.decoder_source_files, expected_report=None)


def build_rejection_vectors() -> tuple[RegistryRejectionVector, ...]:
    """Return the finite valid/reject corpus, with no filesystem or runtime imports."""
    valid = _base()
    vectors = [valid]
    vectors.append(replace(_with_role(valid, "schema/Leaf/1", _roles(valid)["schema/Leaf/1"] + b"\n"), name="raw_terminal_lf", expected_valid=False, rationale="Raw declaration bytes forbid a terminal LF.", boundary="declaration", expected_report=None))
    vectors.extend((
        _raw_reject(valid, "raw_invalid_utf8", b"\xff", "Raw declarations are strict UTF-8."),
        _raw_reject(valid, "raw_duplicate_object_key", b'{"fields":[],"fields":[],"role":"schema","root_kind":"model","schema_id":"Leaf","schema_version":"1"}', "Raw declaration objects reject duplicate keys."),
        _raw_reject(valid, "raw_json_number", b'{"fields":[],"role":"schema","root_kind":"model","schema_id":"Leaf","schema_version":1}', "Raw declarations forbid JSON numbers."),
        _raw_reject(valid, "raw_non_ascii_key", '{"fíelds":[],"role":"schema","root_kind":"model","schema_id":"Leaf","schema_version":"1"}'.encode(), "Raw declaration keys are ASCII."),
        _raw_reject(valid, "raw_empty_key", b'{"":null,"fields":[],"role":"schema","root_kind":"model","schema_id":"Leaf","schema_version":"1"}', "Raw declaration keys are nonempty."),
        _raw_reject(valid, "raw_reordered_object_keys", b'{"schema_version":"1","schema_id":"Leaf","role":"schema","root_kind":"model","fields":[]}', "Raw objects must be in encoded JSON-string key order."),
    ))
    vectors.append(replace(valid, name="missing_grammar_role", expected_valid=False, rationale="Every package has the one literal grammar role.", raw_role_pairs=tuple(pair for pair in valid.raw_role_pairs if pair[0] != "grammar"), boundary="declaration", expected_report=None))
    vectors.append(replace(valid, name="duplicate_source_role", expected_valid=False, rationale="Each source role occurs once.", raw_role_pairs=valid.raw_role_pairs + (valid.raw_role_pairs[0],), boundary="declaration", expected_report=None))
    vectors.append(_mutated(valid, "fixed_grammar_mutation", "The grammar role is one exact published literal.", "grammar", lambda value: value["tags"].__setitem__("integer", "other")))
    vectors.append(_mutated(valid, "closed_schema_role_extra_field", "Schema roles have exact closed object fields.", "schema/Leaf/1", lambda value: value.__setitem__("extra", "x")))
    vectors.append(_mutated(valid, "unknown_type_kind", "Type expressions use the closed kind grammar.", "schema/Leaf/1", lambda value: value["fields"][0].__setitem__("type", {"kind": "any"})))
    vectors.append(_mutated(valid, "duplicate_schema_field", "Schema field names are unique.", "schema/Leaf/1", lambda value: value["fields"].append(_copy(value["fields"][1]))))
    vectors.append(_mutated(valid, "unresolved_model_reference", "Every ModelRef must resolve in the schema closure.", "schema/Root/1", lambda value: value["fields"][0]["type"].__setitem__("schema_id", "Absent")))
    vectors.append(_mutated(valid, "nested_model_cycle", "Transitive model dependencies must be acyclic.", "schema/Leaf/1", lambda value: value["fields"][1].__setitem__("type", {"kind": "model_ref", "schema_id": "Root", "schema_version": "1"})))
    vectors.append(_mutated(valid, "direct_model_self_reference", "A model cannot reference itself.", "schema/Root/1", lambda value: value["fields"][0]["type"].__setitem__("schema_id", "Root")))
    vectors.append(_mutated(valid, "unresolved_enum_reference", "EnumRef must resolve in its reachable closure.", "schema/Leaf/1", lambda value: value["fields"][1]["type"].__setitem__("qualified_id", "AbsentEnum")))
    vectors.append(_mutated(valid, "duplicate_enum_identity", "Enum identities are unique in a closure.", "enum/Leaf/1", lambda value: value["enums"].append(_copy(value["enums"][0]))))
    vectors.append(_mutated(valid, "union_discriminator_not_declared", "Every union alternative declares the discriminator as a singleton matching literal.", "schema/Root/1", lambda value: value["fields"][0].__setitem__("type", {"kind": "union", "discriminator": "kind", "alternatives": [{"discriminator_value": "leaf", "model": {"kind": "model_ref", "schema_id": "Leaf", "schema_version": "1"}}]})))
    vectors.append(_mutated(valid, "optional_field_set_not_exact", "Optional policy rows must equal schema fields.", "optional/Root/1", lambda value: value.__setitem__("fields", value["fields"][:1])))
    vectors.append(_mutated(valid, "numeric_wrapper_without_row", "Every direct numeric wrapper requires one numeric row.", "numeric/Leaf/1", lambda value: value.__setitem__("fields", [])))
    vectors.append(_mutated(valid, "decimal_numeric_encoding_id_missing", "Decimal numeric rows require a non-null encoding spec identifier.", "numeric/Leaf/1", lambda value: value["fields"][0].__setitem__("encoding_spec_id", None)))
    vectors.append(_mutated(valid, "decimal_numeric_wrong_owner", "A numeric wrapper names its direct owning schema field.", "schema/Leaf/1", lambda value: value["fields"][0]["type"].__setitem__("field_name", "flavor")))
    inverted = _roles(valid)
    inverted_numeric = json.loads(inverted["numeric/Leaf/1"])
    inverted_numeric["fields"][0]["lower"] = "11.00"
    inverted["numeric/Leaf/1"] = _canonical(inverted_numeric)
    vectors.append(replace(_rebuild_with_roles(valid, inverted), name="decimal_numeric_inverted_bounds", rationale="Generic declaration validation preserves exact-scale bounds without imposing a domain range ordering.", boundary="registry"))
    vectors.append(_mutated(valid, "decimal_numeric_missing_scale", "Decimal numeric rows require a scale.", "numeric/Leaf/1", lambda value: value["fields"][0].__setitem__("scale", None)))
    vectors.append(_mutated(valid, "decimal_numeric_wrong_scale_lower", "Decimal bounds use exactly the declared fixed scale.", "numeric/Leaf/1", lambda value: value["fields"][0].__setitem__("lower", "0.0")))
    vectors.append(_mutated(valid, "decimal_numeric_wrong_scale_upper", "Decimal bounds use exactly the declared fixed scale.", "numeric/Leaf/1", lambda value: value["fields"][0].__setitem__("upper", "10.0")))
    def binary_nonnull(value: Any) -> None:
        value["fields"][0]["representation"] = "canonical_finite_binary64"
    binary_schema = _mutated(valid, "binary64_forbidden_numeric_members", "Binary64 policy rows require every decimal-only member to be null.", "numeric/Leaf/1", binary_nonnull)
    schema = json.loads(_roles(binary_schema)["schema/Leaf/1"])
    schema["fields"][0]["type"] = {"kind": "canonical_finite_binary64", "field_name": "amount"}
    vectors.append(_with_role(binary_schema, "schema/Leaf/1", schema))
    vectors.append(_mutated(valid, "integrity_policy_unknown_member", "Digest/signature policies have a closed member set.", "digest-signature/Root/1", lambda value: value["policy"].__setitem__("excluded_fields", [])))
    vectors.append(_mutated(valid, "decoder_wrong_root_kind", "Decoder roles require typed_root_kind=model.", "decoder/Root/1", lambda value: value.__setitem__("typed_root_kind", "scalar")))
    vectors.append(_mutated(valid, "upcast_must_be_null_only", "Profile-3 has no upcast implementation route.", "upcast/Root/1", lambda value: value.__setitem__("upcaster_id", "example.upcast")))
    vectors.append(replace(_mutated(valid, "registry_entry_substitution", "Registry entries must equal independently derived entry commitments.", "registry", lambda value: value["entries"].__setitem__(0, "0" * 64)), boundary="registry"))
    bad_manifest = json.loads(valid.decoder_source_manifest_bytes or b"{}")
    bad_manifest["files"][0]["sha256"] = "0" * 64
    vectors.append(_source_reject(valid, "decoder_manifest_hash_substitution", bad_manifest, "A selected whole-file digest must equal its unmodified bytes."))
    order_manifest = json.loads(valid.decoder_source_manifest_bytes or b"{}")
    order_manifest["files"].reverse()
    vectors.append(_source_reject(valid, "decoder_manifest_row_order", order_manifest, "Decoder source rows are ordered by decoder and source-file ID."))
    path_manifest = json.loads(valid.decoder_source_manifest_bytes or b"{}")
    path_manifest["files"][0]["relative_path"] = "../native/leaf.py"
    vectors.append(_source_reject(valid, "decoder_manifest_path_escape", path_manifest, "Decoder source paths are root-contained whole-file paths."))
    pub = json.loads(valid.publication_manifest_bytes or b"{}")
    pub["files"][0]["sha256"] = "0" * 64
    vectors.append(replace(valid, name="publication_role_hash_substitution", expected_valid=False, rationale="Publication manifest role digests bind raw source bytes.", boundary="publication", publication_manifest_bytes=_canonical(pub), expected_report=None))
    pub = json.loads(valid.publication_manifest_bytes or b"{}")
    pub["files"].reverse()
    vectors.append(replace(valid, name="publication_role_order", expected_valid=False, rationale="Publication source-role rows use stable role ordering.", boundary="publication", publication_manifest_bytes=_canonical(pub), expected_report=None))
    for name, path in (("decoder_path_absolute", "/native/leaf.py"), ("decoder_path_backslash", "native\\leaf.py"), ("decoder_path_dot", "native/./leaf.py"), ("decoder_path_percent", "native/%2e/leaf.py")):
        malformed = json.loads(valid.decoder_source_manifest_bytes or b"{}")
        malformed["files"][0]["relative_path"] = path
        vectors.append(_source_reject(valid, name, malformed, "Decoder source paths use closed ASCII slash segments."))
    duplicate_id = json.loads(valid.decoder_source_manifest_bytes or b"{}")
    duplicate_id["files"].append(_copy(duplicate_id["files"][0]))
    vectors.append(_source_reject(valid, "decoder_duplicate_source_id", duplicate_id, "Decoder/source-file identities are unique."))
    duplicate_path = json.loads(valid.decoder_source_manifest_bytes or b"{}")
    duplicate_path["files"][1]["relative_path"] = duplicate_path["files"][0]["relative_path"]
    vectors.append(_source_reject(valid, "decoder_conflicting_shared_path", duplicate_path, "Shared paths require identical source IDs and bytes."))
    unknown_row = json.loads(valid.decoder_source_manifest_bytes or b"{}")
    ghost = b"def decode_ghost(raw):\n    return raw\n"
    unknown_row["files"].append({"decoder_id": "example.ghost", "source_file_id": "native_ghost", "relative_path": "native/ghost.py", "sha256": _sha(ghost)})
    vectors.append(_source_reject(valid, "decoder_unknown_extra_source_row", unknown_row, "Every source-manifest decoder row is selected by a declared decoder.", valid.decoder_source_files + (DecoderSourceFile("native/ghost.py", ghost),)))
    missing_files = tuple(item for item in valid.decoder_source_files if item.relative_path != "native/leaf.py")
    vectors.append(replace(valid, name="decoder_source_file_missing", expected_valid=False, rationale="Every manifest-selected source file must exist.", boundary="source", decoder_source_files=missing_files, expected_report=None))
    source_profile = json.loads(valid.decoder_source_manifest_bytes or b"{}")
    source_profile["profile_version"] = "4"
    vectors.append(_source_reject(valid, "decoder_manifest_profile_change", source_profile, "Decoder source manifests bind the profile identity."))
    vectors.append(replace(valid, name="decoder_manifest_terminal_lf", expected_valid=False, rationale="Decoder source manifest is canonical raw JSON without terminal LF.", boundary="source", decoder_source_manifest_bytes=(valid.decoder_source_manifest_bytes or b"") + b"\n", expected_report=None))
    publication_lf = replace(valid, name="publication_manifest_terminal_lf", expected_valid=False, rationale="Publication manifest is canonical raw JSON without terminal LF.", boundary="publication", publication_manifest_bytes=(valid.publication_manifest_bytes or b"") + b"\n", expected_report=None)
    vectors.append(publication_lf)
    publication_manifest_digest = json.loads(valid.publication_manifest_bytes or b"{}")
    publication_manifest_digest["decoder_source_manifest_digest"] = "0" * 64
    vectors.append(replace(valid, name="publication_decoder_manifest_digest_substitution", expected_valid=False, rationale="Publication commits the exact decoder source manifest raw SHA-256.", boundary="publication", publication_manifest_bytes=_canonical(publication_manifest_digest), expected_report=None))
    vectors.append(_valid_source_no_lf(valid))
    return tuple(vectors) + _path_bypass_vectors(valid)


def _path_bypass_vectors(valid: RegistryRejectionVector) -> tuple[RegistryRejectionVector, ...]:
    """Self-consistent path vectors that must reject even with matching hashes."""
    raw = b"def decode(raw):\n    return raw\n"
    root_raw = b"def decode_root(raw):\n    return raw\n"

    def vector(name: str, path: str, files: tuple[DecoderSourceFile, ...], rationale: str) -> RegistryRejectionVector:
        rows = [
            ("example.leaf", "native_leaf", path, raw),
            ("example.root", "native_root", "native/root.py", root_raw),
        ]
        return replace(_rebuild_with_sources(valid, files, rows), name=name, expected_valid=False, rationale=rationale, boundary="source", expected_report=None)
    return (
        vector("decoder_file_symlink", "linked.py", (DecoderSourceFile("native/leaf.py", raw), DecoderSourceFile("linked.py", raw, "native/leaf.py"), DecoderSourceFile("native/root.py", b"def decode_root(raw):\n    return raw\n")), "A decoder manifest must reject a symlinked whole-file source even when its bytes and SHA-256 match."),
        vector("decoder_directory_symlink", "linked/leaf.py", (DecoderSourceFile("real/leaf.py", raw), DecoderSourceFile("linked", b"", "real"), DecoderSourceFile("native/root.py", b"def decode_root(raw):\n    return raw\n")), "A decoder manifest must reject traversal through a directory symlink even when it resolves beneath the source root."),
        vector("generated_namespace_source", "observation_registry_sources/registry.json", (DecoderSourceFile("observation_registry_sources/registry.json", raw), DecoderSourceFile("native/root.py", b"def decode_root(raw):\n    return raw\n")), "The reserved observation_registry_sources namespace is never eligible decoder-source input."),
        vector("generated_namespace_nested_source", "observation_registry_sources/nested/registry.json", (DecoderSourceFile("observation_registry_sources/nested/registry.json", raw), DecoderSourceFile("native/root.py", b"def decode_root(raw):\n    return raw\n")), "The reserved observation_registry_sources namespace remains excluded at nested depth."),
        replace(_rebuild_with_sources(valid, valid.decoder_source_files, [("example.leaf", "native_leaf", "native/leaf.py", b"def decode_leaf(raw):\n    return raw\n"), ("example.root", "native_root", "native/root.py", b"def decode_root(raw):\n    return raw\n")]), name="generated_namespace_source_root", expected_valid=False, rationale="The configured decoder-source root cannot be the generated observation_registry_sources directory.", boundary="source", source_root_relative_path="observation_registry_sources", expected_report=None),
        replace(_rebuild_with_sources(valid, valid.decoder_source_files, [("example.leaf", "native_leaf", "native/leaf.py", b"def decode_leaf(raw):\n    return raw\n"), ("example.root", "native_root", "native/root.py", b"def decode_root(raw):\n    return raw\n")]), name="decoder_source_root_parent_alias", expected_valid=False, rationale="The configured decoder-source root is an exact canonical absolute path without parent aliases.", boundary="source", source_root_relative_path="canonical/../canonical", expected_report=None),
        replace(_rebuild_with_sources(valid, valid.decoder_source_files, [("example.leaf", "native_leaf", "native/leaf.py", b"def decode_leaf(raw):\n    return raw\n"), ("example.root", "native_root", "native/root.py", b"def decode_root(raw):\n    return raw\n")]), name="decoder_source_root_symlink", expected_valid=False, rationale="The configured canonical decoder-source root itself must not be a symlink.", boundary="source", source_root_relative_path="source-link", source_root_symlink_target="actual-source", expected_report=None),
    )


def _rebuild_with_sources(
    valid: RegistryRejectionVector,
    files: tuple[DecoderSourceFile, ...],
    rows: list[tuple[str, str, str, bytes]],
) -> RegistryRejectionVector:
    """Re-derive all declarations and external commitments after source selection.

    This keeps filesystem negatives from being accidentally explained by a
    decoder snapshot, registry, or publication mismatch first.
    """
    objects = {
        role: json.loads(raw)
        for role, raw in valid.raw_role_pairs
        if role != "registry"
    }
    manifest_rows = [
        {"decoder_id": decoder_id, "source_file_id": source_file_id, "relative_path": path, "sha256": _sha(raw)}
        for decoder_id, source_file_id, path, raw in rows
    ]
    for schema_id, decoder_id in (("Leaf", "example.leaf"), ("Root", "example.root")):
        selected = [
            (source_file_id, path, raw)
            for selected_id, source_file_id, path, raw in rows
            if selected_id == decoder_id
        ]
        objects[f"decoder/{schema_id}/1"]["implementation_source_digest"] = _snapshot(decoder_id, selected)
    raw_roles = {role: _canonical(value) for role, value in objects.items()}
    registry, registry_digest, expected = _derived_registry(raw_roles)
    raw_roles["registry"] = registry
    manifest = _canonical({"role": "decoder_source_manifest", "profile_id": _PROFILE_ID, "profile_version": _PROFILE_VERSION, "files": manifest_rows})
    publication = _canonical({
        "role": "publication_manifest", "profile_id": _PROFILE_ID, "profile_version": _PROFILE_VERSION,
        "files": [{"role": role, "sha256": _sha(raw)} for role, raw in sorted(raw_roles.items())],
        "decoder_source_manifest_digest": _sha(manifest),
        "decoder_source_snapshots": [
            {"decoder_id": decoder_id, "source_snapshot_digest": objects[f"decoder/{schema_id}/1"]["implementation_source_digest"]}
            for schema_id, decoder_id in (("Leaf", "example.leaf"), ("Root", "example.root"))
        ],
        "registry_digest": registry_digest,
    })
    identities = [{"role": role, "sha256": _sha(raw)} for role, raw in sorted(raw_roles.items())]
    snapshots = [
        {"decoder_id": decoder_id, "source_snapshot_digest": objects[f"decoder/{schema_id}/1"]["implementation_source_digest"]}
        for schema_id, decoder_id in (("Leaf", "example.leaf"), ("Root", "example.root"))
    ]
    return RegistryRejectionVector("rebuilt_source_package", True, "Internally consistent source-selection package.", tuple(sorted(raw_roles.items())), files, manifest, publication, boundary="registry", expected_report=replace(expected, publication_manifest_digest=_publication_digest(manifest, snapshots, registry_digest, identities)))


def _rebuild_with_roles(
    valid: RegistryRejectionVector, raw_roles: dict[str, bytes]
) -> RegistryRejectionVector:
    """Re-derive commitments after an independently-authored role-byte edit."""
    role_objects = {
        role: raw
        for role, raw in raw_roles.items()
        if role != "registry"
    }
    registry, registry_digest, expected = _derived_registry(role_objects)
    role_objects["registry"] = registry
    manifest = valid.decoder_source_manifest_bytes
    if manifest is None:
        raise ValueError("base vector requires a decoder source manifest")
    snapshots = json.loads(valid.publication_manifest_bytes or b"{}")
    decoder_snapshots = snapshots["decoder_source_snapshots"]
    identities = [
        {"role": role, "sha256": _sha(raw)}
        for role, raw in sorted(role_objects.items())
    ]
    publication = _canonical(
        {
            "role": "publication_manifest",
            "profile_id": _PROFILE_ID,
            "profile_version": _PROFILE_VERSION,
            "files": identities,
            "decoder_source_manifest_digest": _sha(manifest),
            "decoder_source_snapshots": decoder_snapshots,
            "registry_digest": registry_digest,
        }
    )
    return RegistryRejectionVector(
        "rebuilt_role_package",
        True,
        "Internally consistent declaration package.",
        tuple(sorted(role_objects.items())),
        valid.decoder_source_files,
        manifest,
        publication,
        boundary="registry",
        expected_report=replace(
            expected,
            publication_manifest_digest=_publication_digest(
                manifest, decoder_snapshots, registry_digest, identities
            ),
        ),
    )


def _valid_source_no_lf(valid: RegistryRejectionVector) -> RegistryRejectionVector:
    """Source bytes are committed as-is; a terminal LF is not normalized away."""
    leaf = b"def decode_leaf(raw):\n    return raw"
    root = b"def decode_root(raw):\n    return raw\n"
    return replace(
        _rebuild_with_sources(
            valid,
            (DecoderSourceFile("native/leaf.py", leaf), DecoderSourceFile("native/root.py", root)),
            [("example.leaf", "native_leaf", "native/leaf.py", leaf), ("example.root", "native_root", "native/root.py", root)],
        ),
        name="valid_source_without_terminal_lf",
        rationale="Whole-file decoder source bytes preserve a source file with no terminal LF.",
        boundary="registry",
    )
