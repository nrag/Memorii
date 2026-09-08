from __future__ import annotations

import base64
import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from memorii.core.memory_evolution import ingestion_contracts
from memorii.core.memory_evolution import typed_value_artifact_reader as reader
from memorii.core.memory_evolution import typed_value_registry_compilation as compilation
from memorii.core.memory_evolution.typed_value_artifact_reader import (
    ProtectedTypedValueArtifactReaderLimits,
    TypedValueArtifactReaderError,
    UnauthenticatedTypedValueMaterialization,
    read_protected_typed_value_artifact,
    validate_materialize_and_reencode_checked_typed_value_artifact,
)
from memorii.core.memory_evolution.typed_value_body_validation import ProtectedTypedValueBodyLimits
from memorii.core.memory_evolution.typed_value_decoder_sources import (
    DecoderSourceManifest,
    DecoderSourceSnapshot,
    VerifiedDecoderSourceManifest,
)
from memorii.core.memory_evolution.typed_value_publication import (
    DecoderSourceSnapshotPin,
    ProtectedTypedValuePublicationPins,
    PublicationDecoderSourceSnapshot,
    TypedValuePublicationManifest,
    VerifiedTypedValuePublication,
)
from memorii.core.memory_evolution.typed_value_registry_history import (
    ProtectedTypedValueRegistryHistory,
    TypedValueRegistryReadRoute,
)

_DECLARATION_LIMITS = compilation.ProtectedDeclarationParseLimits(10_000, 200, 20)
_LIMITS = ProtectedTypedValueArtifactReaderLimits(10_000, 200, 20, ProtectedTypedValueBodyLimits(10_000, 200, 20))
_DECODER_ID = "memorii.semantic_ingestion.observation.MemoryScope.v1"


def _raw(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _registry():
    grammar = {"role": "grammar", "profile_id": "semantic_ingestion_typed_value", "profile_version": "3", "grammar_revision": "operational-3", "json": {"canonical": "RFC8785", "terminal_lf": False, "utf8": "strict"}, "envelope": {"binding_fields": ["profile_id", "profile_version", "profile_digest", "schema_id", "schema_version", "binding_digest"], "fields": ["binding", "canonical_value_bytes", "canonical_value_digest", "artifact_digest"], "permitted_value_kinds": ["bytes", "integer", "map", "scalar"]}, "tags": {"bytes": "rfc4648_standard_padded", "datetime": "utc_six_fractional_digits", "duration_microseconds": "signed_i64", "enum": "registered_qualified_member", "frozenset": "canonical_member_byte_order", "integer": "canonical_decimal_string", "list": "declared_order", "map": "encoded_json_string_key_order", "set": "canonical_member_byte_order", "tuple": "declared_order"}, "type_rules": {"bool_as_integer": False, "defaults_before_verification": False, "float_decimal": False, "map_keys": "string_only", "model_fields": "registered_exact", "optional": "registered_policy", "union": "one_registered_discriminator"}}
    rows = [_raw(grammar)]
    common = {"schema_id": "MemoryScope", "schema_version": "1"}
    rows.extend((_raw({"role": "schema", **common, "root_kind": "model", "fields": [{"name": name, "type": {"kind": "string", "lexical_rule": "unicode_scalar"}, "integrity_role": "ordinary"} for name in ("session_id", "task_id", "user_id")]}), _raw({"role": "enum", **common, "enums": []}), _raw({"role": "optional", **common, "fields": [{"field_name": name, "policy": "required_nullable"} for name in ("session_id", "task_id", "user_id")]}), _raw({"role": "numeric", **common, "fields": []}), _raw({"role": "digest-signature", **common, "policy": {"kind": "ordinary"}}), _raw({"role": "decoder", **common, "decoder_id": _DECODER_ID, "typed_root_kind": "model", "implementation_source_digest": "a" * 64}), _raw({"role": "upcast", **common, "target_binding": None, "upcaster_id": None, "implementation_source_digest": None})))
    rows.append(compilation.author_typed_value_registry_role(rows, limits=_DECLARATION_LIMITS))
    return compilation.compile_typed_value_registry(rows, limits=_DECLARATION_LIMITS)


def _history(*, status: str = "active") -> ProtectedTypedValueRegistryHistory:
    registry = _registry()
    entry = registry.entries[0]
    if status != "active":
        entry = replace(entry, read_status=status)
        registry = replace(registry, entries=(entry,))
    snapshot = DecoderSourceSnapshot(_DECODER_ID, "a" * 64, ())
    sources = VerifiedDecoderSourceManifest(DecoderSourceManifest(b"{}", "b" * 64, "semantic_ingestion_typed_value", "3", ()), (), (snapshot,))
    manifest = TypedValuePublicationManifest(b"{}", "c" * 64, "semantic_ingestion_typed_value", "3", (), "b" * 64, (PublicationDecoderSourceSnapshot(_DECODER_ID, "a" * 64),), registry.registry_digest)
    pins = ProtectedTypedValuePublicationPins("c" * 64, registry.registry_digest, (DecoderSourceSnapshotPin(_DECODER_ID, "a" * 64),), "e" * 64)
    return ProtectedTypedValueRegistryHistory((VerifiedTypedValuePublication(registry, sources, manifest, pins, "e" * 64),))


def _body() -> bytes:
    return _raw({"$type": "map", "entries": [["session_id", None], ["task_id", None], ["user_id", None]]})


def _lp(*parts: bytes) -> bytes:
    return b"".join(len(part).to_bytes(8, "big") + part for part in parts)


def _wire(history: ProtectedTypedValueRegistryHistory, body: bytes | None = None) -> bytes:
    entry = history.publications[0].compiled_registry.entries[0]
    body = _body() if body is None else body
    binding = {"profile_id": entry.profile.profile_id, "profile_version": {"$type": "integer", "value": entry.profile.profile_version}, "profile_digest": entry.profile.profile_digest, "schema_id": entry.schema_id, "schema_version": {"$type": "integer", "value": entry.schema_version}, "binding_digest": entry.binding_digest}
    # This literal oracle intentionally uses only stdlib JSON, base64, SHA-256 and LP.
    preimage = _lp(b"semantic-ingestion-canonical-artifact", binding["profile_id"].encode(), b"3", binding["profile_digest"].encode(), binding["schema_id"].encode(), b"1", binding["binding_digest"].encode(), body)
    envelope = {"$type": "map", "entries": [["artifact_digest", sha256(preimage).hexdigest()], ["binding", {"$type": "map", "entries": [["binding_digest", binding["binding_digest"]], ["profile_digest", binding["profile_digest"]], ["profile_id", binding["profile_id"]], ["profile_version", binding["profile_version"]], ["schema_id", binding["schema_id"]], ["schema_version", binding["schema_version"]]]}], ["canonical_value_bytes", {"$type": "bytes", "value": base64.b64encode(body).decode()}], ["canonical_value_digest", sha256(body).hexdigest()]]}
    return _raw(envelope)


def test_reads_history_selected_opaque_body_then_explicitly_materializes() -> None:
    history = _history()
    checked = read_protected_typed_value_artifact(_wire(history), history=history, route=TypedValueRegistryReadRoute.PUBLIC, limits=_LIMITS)
    assert checked.canonical_value_bytes == _body()
    materialized = validate_materialize_and_reencode_checked_typed_value_artifact(checked, limits=_LIMITS)
    assert isinstance(materialized, UnauthenticatedTypedValueMaterialization)
    assert materialized.materialized.value.model_dump()["session_id"] is None


def test_body_is_not_parsed_until_after_history_and_digest_checks() -> None:
    history = _history()
    malformed_body = b"{not-json"
    checked = read_protected_typed_value_artifact(_wire(history, malformed_body), history=history, route=TypedValueRegistryReadRoute.PUBLIC, limits=_LIMITS)
    with pytest.raises(TypedValueArtifactReaderError, match="selected_body_invalid"):
        validate_materialize_and_reencode_checked_typed_value_artifact(checked, limits=_LIMITS)


@pytest.mark.parametrize("field", ("profile_id", "profile_version", "profile_digest", "schema_id", "schema_version", "binding_digest"))
def test_each_binding_member_rejects_before_body_validation(field: str) -> None:
    history = _history()
    raw = _wrong_binding_member(_wire(history), field)
    with patch("memorii.core.memory_evolution.typed_value_artifact_reader.validate_typed_value_body") as body_validator, pytest.raises(TypedValueArtifactReaderError):
        read_protected_typed_value_artifact(raw, history=history, route=TypedValueRegistryReadRoute.PUBLIC, limits=_LIMITS)
    body_validator.assert_not_called()


@pytest.mark.parametrize("status", ("active", "replay_only", "retired"))
@pytest.mark.parametrize("route", tuple(TypedValueRegistryReadRoute))
def test_history_read_status_controls_selection(status: str, route: TypedValueRegistryReadRoute) -> None:
    history = _history(status=status)
    allowed = status == "active" or (status == "replay_only" and route is not TypedValueRegistryReadRoute.PUBLIC) or (status == "retired" and route is TypedValueRegistryReadRoute.RETAINED_VERIFICATION)
    if allowed:
        assert read_protected_typed_value_artifact(_wire(history), history=history, route=route, limits=_LIMITS)
    else:
        with pytest.raises(TypedValueArtifactReaderError, match="binding_unresolved"):
            read_protected_typed_value_artifact(_wire(history), history=history, route=route, limits=_LIMITS)


@pytest.mark.parametrize("mutation", (lambda raw: raw.replace(b'canonical_value_digest', b'wrong_digest'), lambda raw: raw.replace(b'artifact_digest', b'wrong_artifact')))
def test_digest_field_mutations_reject_before_body_validation(mutation: Callable[[bytes], bytes]) -> None:
    history = _history()
    with patch("memorii.core.memory_evolution.typed_value_artifact_reader.validate_typed_value_body") as body_validator, pytest.raises(TypedValueArtifactReaderError):
        read_protected_typed_value_artifact(mutation(_wire(history)), history=history, route=TypedValueRegistryReadRoute.PUBLIC, limits=_LIMITS)
    body_validator.assert_not_called()


def test_exact_outer_byte_limit_and_one_byte_less_reject_before_history() -> None:
    history = _history()
    raw = _wire(history)
    exact = replace(_LIMITS, maximum_envelope_bytes=len(raw))
    assert read_protected_typed_value_artifact(raw, history=history, route=TypedValueRegistryReadRoute.PUBLIC, limits=exact)
    with pytest.raises(TypedValueArtifactReaderError, match="outer_invalid"):
        read_protected_typed_value_artifact(raw, history=history, route=TypedValueRegistryReadRoute.PUBLIC, limits=replace(exact, maximum_envelope_bytes=len(raw) - 1))


def _wrong_binding_member(raw: bytes, field: str) -> bytes:
    envelope = json.loads(raw)
    binding = next(value for name, value in envelope["entries"] if name == "binding")
    entries = dict(binding["entries"])
    replacements: dict[str, object] = {
        "profile_id": "other_profile",
        "profile_version": {"$type": "integer", "value": "4"},
        "profile_digest": "f" * 64,
        "schema_id": "OtherScope",
        "schema_version": {"$type": "integer", "value": "2"},
        "binding_digest": "f" * 64,
    }
    entries[field] = replacements[field]
    binding["entries"] = [[name, entries[name]] for name, _ in binding["entries"]]
    return _raw(envelope)


@contextmanager
def _stages() -> Iterator[tuple[MagicMock, MagicMock, MagicMock]]:
    original = ProtectedTypedValueRegistryHistory.resolve
    with (
        patch.object(ProtectedTypedValueRegistryHistory, "resolve", autospec=True, side_effect=original) as history,
        patch.object(reader, "validate_typed_value_body", wraps=reader.validate_typed_value_body) as body,
        patch.object(reader, "materialize_typed_value_model", wraps=reader.materialize_typed_value_model) as native,
    ):
        yield history, body, native


def _read_and_convert(raw: bytes, history: ProtectedTypedValueRegistryHistory, limits: ProtectedTypedValueArtifactReaderLimits = _LIMITS) -> UnauthenticatedTypedValueMaterialization:
    checked = read_protected_typed_value_artifact(raw, history=history, route=TypedValueRegistryReadRoute.PUBLIC, limits=limits)
    return validate_materialize_and_reencode_checked_typed_value_artifact(checked, limits=limits)


def test_positive_stages_use_real_delegates_and_never_legacy_reader() -> None:
    history = _history()
    with _stages() as stages, patch.object(ingestion_contracts, "decode_artifact", side_effect=AssertionError("legacy reader invoked")):
        result = _read_and_convert(_wire(history), history)
    assert [stage.call_count for stage in stages] == [1, 1, 1]
    assert isinstance(result, UnauthenticatedTypedValueMaterialization)
    assert result.checked_artifact.selected_entry.publication is history.publications[0]
    assert result.materialized.value.model_dump() == {"session_id": None, "task_id": None, "user_id": None}
    assert result.validated_body.raw_bytes == _body()


def _malformed_outer(raw: bytes, mutation: str) -> bytes:
    envelope = json.loads(raw)
    entries = envelope["entries"]
    binding = entries[1][1]["entries"]
    if mutation == "outer_missing":
        entries.pop()
    elif mutation == "outer_extra":
        entries.append(["extra", None])
    elif mutation == "binding_missing":
        binding.pop()
    elif mutation == "binding_extra":
        binding.append(["z_extra", None])
    elif mutation == "outer_tag":
        envelope["$type"] = "list"
    elif mutation == "binding_tag":
        entries[1][1]["$type"] = "set"
    elif mutation == "bytes_tag":
        entries[2][1]["$type"] = "string"
    elif mutation == "integer_tag":
        binding[3][1]["$type"] = "duration_microseconds"
    elif mutation in ("profile_number", "profile_bool", "schema_number", "schema_bool"):
        binding[3 if mutation.startswith("profile") else 5][1] = True if mutation.endswith("bool") else 3
    elif mutation == "bad_digest":
        entries[0][1] = "A" * 64
    elif mutation == "bad_base64":
        entries[2][1]["value"] = "YQ"
    elif mutation == "duplicate_map_key":
        entries.insert(1, entries[0])
    elif mutation == "map_order":
        entries.reverse()
    elif mutation == "duplicate_json_key":
        return raw.replace(b'{"$type":"map",', b'{"$type":"map","$type":"map",', 1)
    elif mutation == "unknown_tag":
        entries[3][1] = {"$type": "future", "value": "x"}
    else:
        raise AssertionError(mutation)
    return _raw(envelope)


@pytest.mark.parametrize("mutation", (
    "outer_missing", "outer_extra", "binding_missing", "binding_extra",
    "outer_tag", "binding_tag", "bytes_tag", "integer_tag",
    "profile_number", "profile_bool", "schema_number", "schema_bool",
    "bad_digest", "bad_base64", "duplicate_map_key", "map_order",
    "duplicate_json_key", "unknown_tag",
))
def test_outer_failure_never_looks_up_or_decodes(mutation: str) -> None:
    history = _history()
    with _stages() as stages, pytest.raises(TypedValueArtifactReaderError):
        _read_and_convert(_malformed_outer(_wire(history), mutation), history)
    assert [stage.call_count for stage in stages] == [0, 0, 0]


@pytest.mark.parametrize("limit_name", ("maximum_envelope_bytes", "maximum_envelope_nodes", "maximum_envelope_depth"))
def test_outer_resource_boundaries_stop_before_history(limit_name: str) -> None:
    history = _history()
    raw = _wire(history)
    # The literal outer tree has 41 value nodes and deepest scalar depth eight;
    # body bytes are one base64 string regardless of the inner JSON tree.
    exact = replace(_LIMITS, maximum_envelope_bytes=len(raw), maximum_envelope_nodes=41, maximum_envelope_depth=8)
    with _stages() as accepted:
        _read_and_convert(raw, history, exact)
    assert [stage.call_count for stage in accepted] == [1, 1, 1]
    smaller = replace(exact, **{limit_name: getattr(exact, limit_name) - 1})
    with _stages() as rejected, pytest.raises(TypedValueArtifactReaderError, match="outer_invalid"):
        _read_and_convert(raw, history, smaller)
    assert [stage.call_count for stage in rejected] == [0, 0, 0]


@pytest.mark.parametrize("mutation", ("body", "body_digest", "artifact_digest"))
def test_native_digest_values_reject_after_history_before_body(mutation: str) -> None:
    history = _history()
    envelope = json.loads(_wire(history))
    entries = envelope["entries"]
    if mutation == "body":
        entries[2][1]["value"] = base64.b64encode(b"opaque changed bytes").decode()
    else:
        entries[0 if mutation == "artifact_digest" else 3][1] = "f" * 64
    with _stages() as stages, pytest.raises(TypedValueArtifactReaderError, match="digest_mismatch"):
        _read_and_convert(_raw(envelope), history)
    assert [stage.call_count for stage in stages] == [1, 0, 0]


@pytest.mark.parametrize("field", ("profile_id", "profile_version", "profile_digest", "schema_id", "schema_version", "binding_digest"))
def test_full_binding_selection_precedes_body(field: str) -> None:
    history = _history()
    with _stages() as stages, pytest.raises(TypedValueArtifactReaderError, match="binding_unresolved"):
        _read_and_convert(_wrong_binding_member(_wire(history), field), history)
    assert [stage.call_count for stage in stages] == [1, 0, 0]


def test_unknown_large_version_has_typed_lookup_failure() -> None:
    history = _history()
    raw = _wire(history).replace(b'"value":"3"', b'"value":"' + b"9" * 5000 + b'"')
    with _stages() as stages, pytest.raises(TypedValueArtifactReaderError, match="binding_unresolved"):
        _read_and_convert(raw, history)
    assert [stage.call_count for stage in stages] == [1, 0, 0]


def test_coherently_digested_invalid_body_never_materializes() -> None:
    history = _history()
    body = _body().replace(b"session_id", b"unknown_field")
    with _stages() as stages, pytest.raises(TypedValueArtifactReaderError, match="selected_body_invalid"):
        _read_and_convert(_wire(history, body), history)
    assert [stage.call_count for stage in stages] == [1, 1, 0]


def test_native_reencoding_mismatch_is_rejected() -> None:
    history = _history()
    with _stages() as stages, patch.object(reader, "reencode_materialized_typed_value_model", return_value=b"different"), pytest.raises(TypedValueArtifactReaderError, match="native_reencode_mismatch"):
        _read_and_convert(_wire(history), history)
    assert [stage.call_count for stage in stages] == [1, 1, 1]


def test_profile_two_stays_on_explicit_historical_route() -> None:
    history = _history()
    binding = ingestion_contracts.CanonicalTypedValueProfileBinding("semantic_ingestion_typed_value", 2, "a" * 64, "MemoryScope", 1, "b" * 64)
    raw = ingestion_contracts.serialize_artifact({"session_id": None, "task_id": None, "user_id": None}, binding)
    assert ingestion_contracts.decode_artifact(raw, expected_binding=binding).binding == binding
    with _stages() as stages, pytest.raises(TypedValueArtifactReaderError, match="binding_unresolved"):
        _read_and_convert(raw, history)
    assert [stage.call_count for stage in stages] == [1, 0, 0]


def test_frozen_literal_wire_and_digests() -> None:
    history = _history()
    raw = (Path(__file__).parents[3] / "fixtures/semantic_ingestion/observation_artifact.json").read_bytes()
    with _stages() as stages:
        result = _read_and_convert(raw, history)
    assert [stage.call_count for stage in stages] == [1, 1, 1]
    assert isinstance(result, UnauthenticatedTypedValueMaterialization)
    assert result.checked_artifact.selected_entry.entry is history.publications[0].compiled_registry.entries[0]
    assert result.checked_artifact.canonical_value_bytes == b'{"$type":"map","entries":[["session_id",null],["task_id",null],["user_id",null]]}'
    assert result.checked_artifact.canonical_value_digest == "bfe19705ba3f4cd5e9790f2531a14eedf0c5d6d3efdc00c55320d6240b839833"
    assert result.checked_artifact.artifact_digest == "fd91ebc2593296a71e08f390ec708c09fdc6b08aa70189363a61fd2acd5fb659"
    assert result.materialized.value.model_dump() == {"session_id": None, "task_id": None, "user_id": None}


def _later_publication(original: VerifiedTypedValuePublication) -> VerifiedTypedValuePublication:
    source = Path(__file__).parents[4] / "memorii/core/memory_evolution/observation_registry_sources"
    sources = [(source / "grammar.json").read_bytes()]
    for role in ("schema", "enum", "optional", "numeric", "digest-signature", "upcast"):
        sources.append((source / role / "TypedLiteral/1.json").read_bytes())
    decoder_id = "memorii.semantic_ingestion.observation.TypedLiteral.v1"
    sources.append(_raw({"role": "decoder", "schema_id": "TypedLiteral", "schema_version": "1", "decoder_id": decoder_id, "typed_root_kind": "model", "implementation_source_digest": "a" * 64}))
    sources.append(compilation.author_typed_value_registry_role(sources, limits=_DECLARATION_LIMITS))
    registry = compilation.compile_typed_value_registry(sources, limits=_DECLARATION_LIMITS)
    return replace(
        original,
        compiled_registry=registry,
        verified_decoder_sources=replace(original.verified_decoder_sources, snapshots=(DecoderSourceSnapshot(decoder_id, "a" * 64, ()),)),
        publication_manifest=replace(original.publication_manifest, publication_digest="9" * 64, registry_digest=registry.registry_digest, decoder_source_snapshots=(PublicationDecoderSourceSnapshot(decoder_id, "a" * 64),)),
        pins=replace(original.pins, publication_digest="9" * 64, registry_digest=registry.registry_digest, decoder_source_snapshots=(DecoderSourceSnapshotPin(decoder_id, "a" * 64),)),
    )


def test_prior_artifact_keeps_original_entry_after_history_append() -> None:
    original = _history()
    history = original.append(_later_publication(original.publications[0]))
    with _stages() as stages:
        result = _read_and_convert(_wire(original), history)
    assert [stage.call_count for stage in stages] == [1, 1, 1]
    assert result.checked_artifact.selected_entry.publication is original.publications[0]
    assert result.checked_artifact.selected_entry.entry is original.publications[0].compiled_registry.entries[0]
    with _stages() as stages, pytest.raises(TypedValueArtifactReaderError, match="binding_unresolved"):
        _read_and_convert(_wrong_binding_member(_wire(original), "binding_digest"), history)
    assert [stage.call_count for stage in stages] == [1, 0, 0]


@pytest.mark.parametrize("field", ("artifact_digest", "canonical_value_digest", "profile_id", "schema_id", "profile_digest", "binding_digest"))
@pytest.mark.parametrize("value", (True, 1))
def test_string_required_scalars_reject_before_history(field: str, value: object) -> None:
    history = _history()
    envelope = json.loads(_wire(history))
    entries = envelope["entries"] if field in ("artifact_digest", "canonical_value_digest") else envelope["entries"][1][1]["entries"]
    for pair in entries:
        if pair[0] == field:
            pair[1] = value
    with _stages() as stages, pytest.raises(TypedValueArtifactReaderError):
        _read_and_convert(_raw(envelope), history)
    assert [stage.call_count for stage in stages] == [0, 0, 0]


@pytest.mark.parametrize("spelling", ("0", "-0", "03", "-1", "", "missing", "extra"))
@pytest.mark.parametrize("field", ("profile_version", "schema_version"))
def test_integer_spelling_and_members_reject_before_history(field: str, spelling: str) -> None:
    history = _history()
    envelope = json.loads(_wire(history))
    integer = next(value for name, value in envelope["entries"][1][1]["entries"] if name == field)
    if spelling == "missing":
        del integer["value"]
    elif spelling == "extra":
        integer["extra"] = "1"
    else:
        integer["value"] = spelling
    with _stages() as stages, pytest.raises(TypedValueArtifactReaderError):
        _read_and_convert(_raw(envelope), history)
    assert [stage.call_count for stage in stages] == [0, 0, 0]


def test_required_body_omission_cannot_reach_native_default() -> None:
    history = _history()
    body = b'{"$type":"map","entries":[["task_id",null],["user_id",null]]}'
    with _stages() as stages, pytest.raises(TypedValueArtifactReaderError, match="selected_body_invalid"):
        _read_and_convert(_wire(history, body), history)
    assert [stage.call_count for stage in stages] == [1, 1, 0]
