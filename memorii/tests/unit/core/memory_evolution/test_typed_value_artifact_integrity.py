from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from memorii.core.memory_evolution import typed_value_artifact_integrity as integrity
from memorii.core.memory_evolution.typed_value_artifact_integrity import (
    TrustedTypedValueArtifactVerificationKey,
    TypedValueArtifactIntegrityError,
    registered_self_digest_preimage,
    registered_signature_only_message,
    verify_protected_typed_value_artifact_integrity,
)
from memorii.core.memory_evolution.typed_value_artifact_reader import ProtectedTypedValueArtifactReaderLimits
from memorii.core.memory_evolution.typed_value_body_validation import (
    ProtectedTypedValueBodyLimits,
    validate_typed_value_body,
)
from memorii.core.memory_evolution.typed_value_declarations import (
    DigestSignatureRole,
    ProtectedDeclarationParseLimits,
    SelfDigestPolicy,
    SignatureOnlyPolicy,
)
from memorii.core.memory_evolution.typed_value_decoder_sources import (
    DecoderSourceSelection,
    ProtectedDecoderSourceManifestLimits,
)
from memorii.core.memory_evolution.typed_value_publication import (
    DecoderSourceSnapshotPin,
    ProtectedTypedValuePublicationLimits,
    ProtectedTypedValuePublicationPins,
    parse_typed_value_publication_manifest,
    verify_typed_value_publication,
)
from memorii.core.memory_evolution.typed_value_publication_authoring import author_typed_value_publication_package
from memorii.core.memory_evolution.typed_value_registry_history import (
    ProtectedTypedValueRegistryHistory,
    TypedValueRegistryReadRoute,
)

_ROOT = Path(__file__).resolve().parents[4] / "memorii/core/memory_evolution/observation_registry_sources"
_SCHEMAS = (
    "MemoryScope",
    "AuthenticatedGraphObservationContext",
    "GraphObservationCursorPayload",
    "IngestionObservationReplayCheckpoint",
    "ObservationCheckpointSigningPreimage",
    "ObservationLedgerHead",
    "ObservationCheckpointLifecycle",
)
_DECLARATION_LIMITS = ProtectedDeclarationParseLimits(60_000, 1_000, 80)
_PUBLICATION_LIMITS = ProtectedTypedValuePublicationLimits(
    _DECLARATION_LIMITS, ProtectedDecoderSourceManifestLimits(60_000, 1_000, 80, 8, 60_000), 60_000
)
_LIMITS = ProtectedTypedValueArtifactReaderLimits(60_000, 1_000, 80, ProtectedTypedValueBodyLimits(60_000, 1_000, 80))


def _raw(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _lp(*parts: bytes) -> bytes:
    return b"".join(len(part).to_bytes(8, "big") + part for part in parts)


def _publication(
    tmp_path: Path, schemas: tuple[str, ...] = _SCHEMAS
) -> ProtectedTypedValueRegistryHistory:
    sources = [(_ROOT / "grammar.json").read_bytes()]
    for schema in schemas:
        for role in ("schema", "enum", "optional", "numeric", "digest-signature", "upcast"):
            sources.append((_ROOT / role / schema / "1.json").read_bytes())
    source = tmp_path / "native_decoder_snapshot.py"
    source.write_bytes(b"# selected native decoder snapshot\n")
    package = author_typed_value_publication_package(
        sources,
        tuple(
            DecoderSourceSelection(f"memorii.semantic_ingestion.observation.{schema}.v1", "feature-test", source.name)
            for schema in schemas
        ),
        source_package_root=tmp_path,
        limits=_PUBLICATION_LIMITS,
    )
    manifest = parse_typed_value_publication_manifest(
        package.raw_publication_manifest, maximum_bytes=_PUBLICATION_LIMITS.maximum_publication_manifest_bytes
    )
    vector = b'{"registered":"integrity"}'
    verified = verify_typed_value_publication(
        package.raw_role_sources,
        package.raw_decoder_source_manifest,
        package.raw_publication_manifest,
        vector,
        source_package_root=tmp_path,
        limits=_PUBLICATION_LIMITS,
        pins=ProtectedTypedValuePublicationPins(
            manifest.publication_digest,
            package.compiled_registry.registry_digest,
            tuple(
                DecoderSourceSnapshotPin(item.decoder_id, item.source_snapshot_digest)
                for item in package.verified_decoder_sources.snapshots
            ),
            sha256(vector).hexdigest(),
        ),
    )
    return ProtectedTypedValueRegistryHistory((verified,))


def _binding(history: ProtectedTypedValueRegistryHistory, schema: str) -> tuple[dict[str, object], tuple[bytes, ...]]:
    entry = history.publications[0].compiled_registry.entry_for(schema, "1")
    binding = {
        "profile_id": entry.profile.profile_id,
        "profile_version": {"$type": "integer", "value": entry.profile.profile_version},
        "profile_digest": entry.profile.profile_digest,
        "schema_id": schema,
        "schema_version": {"$type": "integer", "value": "1"},
        "binding_digest": entry.binding_digest,
    }
    members = (
        entry.profile.profile_id.encode(),
        b"3",
        entry.profile.profile_digest.encode(),
        schema.encode(),
        b"1",
        entry.binding_digest.encode(),
    )
    return binding, members


def _policy(history: ProtectedTypedValueRegistryHistory, schema: str) -> DigestSignatureRole:
    for item in history.publications[0].compiled_registry.parsed_roles:
        if isinstance(item, DigestSignatureRole) and item.schema_id == schema and item.schema_version == "1":
            return item
    raise AssertionError("missing digest signature role")


def _wire(history: ProtectedTypedValueRegistryHistory, schema: str, body: bytes) -> bytes:
    binding, members = _binding(history, schema)
    artifact = sha256(_lp(b"semantic-ingestion-canonical-artifact", *members, body)).hexdigest()
    return _raw(
        {
            "$type": "map",
            "entries": [
                ["artifact_digest", artifact],
                ["binding", {"$type": "map", "entries": [[key, binding[key]] for key in sorted(binding)]}],
                ["canonical_value_bytes", {"$type": "bytes", "value": base64.b64encode(body).decode()}],
                ["canonical_value_digest", sha256(body).hexdigest()],
            ],
        }
    )


def _body(entries: Mapping[str, object]) -> bytes:
    return _raw({"$type": "map", "entries": [[key, entries[key]] for key in sorted(entries)]})


def test_ordinary_integrity_uses_real_authored_verified_publication_and_native_memory_scope(tmp_path: Path) -> None:
    history = _publication(tmp_path)
    body = _body({"session_id": None, "task_id": None, "user_id": None})
    result = verify_protected_typed_value_artifact_integrity(
        _wire(history, "MemoryScope", body), history=history, route=TypedValueRegistryReadRoute.PUBLIC, limits=_LIMITS
    )
    assert result.integrity_policy_kind == "ordinary"
    assert not result.cryptographic_signature_checked
    assert result.materialization.materialized.value.__class__.__name__ == "MemoryScope"


def test_forwards_exact_limits_and_rejects_outer_and_body_limit_exhaustion(tmp_path: Path) -> None:
    history = _publication(tmp_path)
    body = _body({"session_id": None, "task_id": None, "user_id": None})
    raw = _wire(history, "MemoryScope", body)
    with (
        patch.object(integrity, "read_protected_typed_value_artifact", wraps=integrity.read_protected_typed_value_artifact) as protected_read,
        patch.object(integrity, "validate_materialize_and_reencode_checked_typed_value_artifact", wraps=integrity.validate_materialize_and_reencode_checked_typed_value_artifact) as materialize,
    ):
        verify_protected_typed_value_artifact_integrity(raw, history=history, route=TypedValueRegistryReadRoute.PUBLIC, limits=_LIMITS)
    assert protected_read.call_args.kwargs["limits"] is _LIMITS
    assert materialize.call_args.kwargs["limits"] is _LIMITS
    outer_too_small = replace(_LIMITS, maximum_envelope_bytes=len(raw) - 1)
    body_too_small = replace(_LIMITS, body_limits=replace(_LIMITS.body_limits, maximum_bytes=len(body) - 1))
    for limited in (outer_too_small, replace(_LIMITS, maximum_envelope_nodes=1), replace(_LIMITS, maximum_envelope_depth=1), body_too_small, replace(_LIMITS, body_limits=replace(_LIMITS.body_limits, maximum_nodes=1)), replace(_LIMITS, body_limits=replace(_LIMITS.body_limits, maximum_depth=1))):
        with pytest.raises(TypedValueArtifactIntegrityError):
            verify_protected_typed_value_artifact_integrity(raw, history=history, route=TypedValueRegistryReadRoute.PUBLIC, limits=limited)
    with (
        patch.object(integrity, "validate_materialize_and_reencode_checked_typed_value_artifact") as body_stage,
        patch.object(integrity, "_selected_root_policy") as integrity_stage,
        pytest.raises(TypedValueArtifactIntegrityError, match="protected_read_invalid"),
    ):
        verify_protected_typed_value_artifact_integrity(b"{bad", history=history, route=TypedValueRegistryReadRoute.PUBLIC, limits=_LIMITS)
    body_stage.assert_not_called()
    integrity_stage.assert_not_called()


def test_flat_native_self_digest_verifies_and_rejects_field_binding_domain_and_digest_mutations(
    tmp_path: Path,
) -> None:
    history = _publication(tmp_path)
    entry = history.publications[0].compiled_registry.entry_for("AuthenticatedGraphObservationContext", "1")
    body = _body(
        {
            "authentication_session_id": "session",
            "authorized_scope_set_digest": "a" * 64,
            "context_digest": "0" * 64,
            "principal_subject_id": "subject",
            "tenant_partition_id": "tenant",
        }
    )
    validated = validate_typed_value_body(
        body, registry=history.publications[0].compiled_registry, entry=entry, limits=_LIMITS.body_limits
    )
    role = _policy(history, entry.schema_id)
    assert isinstance(role.policy, SelfDigestPolicy)
    _, members = _binding(history, entry.schema_id)
    from memorii.core.memory_evolution.ingestion_contracts import CanonicalTypedValueProfileBinding

    bound = CanonicalTypedValueProfileBinding(
        entry.profile.profile_id, 3, entry.profile.profile_digest, entry.schema_id, 1, entry.binding_digest
    )
    expected = sha256(
        _lp(
            role.policy.digest_domain.encode(),
            *members,
            _body(
                {
                    "authentication_session_id": "session",
                    "authorized_scope_set_digest": "a" * 64,
                    "principal_subject_id": "subject",
                    "tenant_partition_id": "tenant",
                }
            ),
        )
    ).digest()
    assert registered_self_digest_preimage(validated.tree, binding=bound, policy=role.policy) == _lp(
        role.policy.digest_domain.encode(),
        *members,
        _body(
            {
                "authentication_session_id": "session",
                "authorized_scope_set_digest": "a" * 64,
                "principal_subject_id": "subject",
                "tenant_partition_id": "tenant",
            }
        ),
    )
    assert (
        expected
        != sha256(
            _lp(
                role.policy.digest_domain.encode(),
                *members,
                _body(
                    {
                        "authentication_session_id": "session",
                        "authorized_scope_set_digest": "a" * 64,
                        "context_digest": "0" * 64,
                        "principal_subject_id": "subject",
                        "tenant_partition_id": "tenant",
                    }
                ),
            )
        ).digest()
    )
    signed_values = {
        "authentication_session_id": "session",
        "authorized_scope_set_digest": "a" * 64,
        "context_digest": sha256(
            registered_self_digest_preimage(validated.tree, binding=bound, policy=role.policy)
        ).hexdigest(),
        "principal_subject_id": "subject",
        "tenant_partition_id": "tenant",
    }
    signed_body = _body(signed_values)
    verified = verify_protected_typed_value_artifact_integrity(
        _wire(history, entry.schema_id, signed_body),
        history=history,
        route=TypedValueRegistryReadRoute.PUBLIC,
        limits=_LIMITS,
    )
    assert verified.integrity_policy_kind == "self_digest"
    for field in ("authentication_session_id", "context_digest"):
        altered = dict(signed_values)
        altered[field] = "x" if field == "authentication_session_id" else "f" * 64
        with pytest.raises(TypedValueArtifactIntegrityError):
            verify_protected_typed_value_artifact_integrity(
                _wire(history, entry.schema_id, _body(altered)),
                history=history,
                route=TypedValueRegistryReadRoute.PUBLIC,
                limits=_LIMITS,
            )
    with pytest.raises(TypedValueArtifactIntegrityError, match="protected_read_invalid"):
        verify_protected_typed_value_artifact_integrity(
            _wire(history, entry.schema_id, signed_body).replace(
                b"AuthenticatedGraphObservationContext", b"UnauthenticatedGraphObservationContext"
            ),
            history=history,
            route=TypedValueRegistryReadRoute.PUBLIC,
            limits=_LIMITS,
        )
    changed_domain = replace(role.policy, digest_domain="memorii.changed.domain")
    assert registered_self_digest_preimage(
        validated.tree, binding=bound, policy=changed_domain
    ) != registered_self_digest_preimage(validated.tree, binding=bound, policy=role.policy)


def test_self_digest_helper_retains_nested_integrity_fields_in_raw_tree_preimage() -> None:
    from memorii.core.memory_evolution.ingestion_contracts import CanonicalTypedValueProfileBinding

    binding = CanonicalTypedValueProfileBinding("profile", 3, "a" * 64, "Example", 1, "b" * 64)
    policy = SelfDigestPolicy("self_digest", "context_digest", "memorii.example.v1")
    nested = {
        "$type": "map",
        "entries": (("context_digest", "c" * 64), ("signature", "d" * 128)),
    }
    tree = {
        "$type": "map",
        "entries": (("context_digest", "0" * 64), ("nested", nested), ("ordinary", "value")),
    }
    retained = _raw(
        {
            "$type": "map",
            "entries": [
                [
                    "nested",
                    {
                        "$type": "map",
                        "entries": [["context_digest", "c" * 64], ["signature", "d" * 128]],
                    },
                ],
                ["ordinary", "value"],
            ],
        }
    )
    expected = _lp(
        b"memorii.example.v1", b"profile", b"3", b"a" * 64, b"Example", b"1", b"b" * 64, retained
    )
    preimage = registered_self_digest_preimage(tree, binding=binding, policy=policy)
    assert preimage == expected
    changed_nested = {
        "$type": "map",
        "entries": (
            ("context_digest", "0" * 64),
            (
                "nested",
                {
                    "$type": "map",
                    "entries": (("context_digest", "e" * 64), ("signature", "d" * 128)),
                },
            ),
            ("ordinary", "value"),
        ),
    }
    changed = registered_self_digest_preimage(changed_nested, binding=binding, policy=policy)
    assert changed != preimage
    assert sha256(changed).hexdigest() != sha256(preimage).hexdigest()


def test_historical_self_digest_uses_original_publication_policy_after_new_coordinate_append(
    tmp_path: Path,
) -> None:
    original = _publication(tmp_path, ("AuthenticatedGraphObservationContext",))
    newer = _publication(tmp_path, ("GraphObservationAuthorizationDecision",))
    history = original.append(newer.publications[0])
    entry = original.publications[0].compiled_registry.entry_for(
        "AuthenticatedGraphObservationContext", "1"
    )
    original_policy = _policy(original, entry.schema_id)
    newer_policy = _policy(newer, "GraphObservationAuthorizationDecision")
    assert isinstance(original_policy.policy, SelfDigestPolicy)
    assert isinstance(newer_policy.policy, SelfDigestPolicy)
    fields = {
        "authentication_session_id": "session",
        "authorized_scope_set_digest": "a" * 64,
        "context_digest": "0" * 64,
        "principal_subject_id": "subject",
        "tenant_partition_id": "tenant",
    }
    placeholder = _body(fields)
    validated = validate_typed_value_body(
        placeholder,
        registry=original.publications[0].compiled_registry,
        entry=entry,
        limits=_LIMITS.body_limits,
    )
    from memorii.core.memory_evolution.ingestion_contracts import CanonicalTypedValueProfileBinding

    binding = CanonicalTypedValueProfileBinding(
        entry.profile.profile_id,
        3,
        entry.profile.profile_digest,
        entry.schema_id,
        1,
        entry.binding_digest,
    )
    fields["context_digest"] = sha256(
        registered_self_digest_preimage(validated.tree, binding=binding, policy=original_policy.policy)
    ).hexdigest()
    original_body = _body(fields)
    verified = verify_protected_typed_value_artifact_integrity(
        _wire(original, entry.schema_id, original_body),
        history=history,
        route=TypedValueRegistryReadRoute.PUBLIC,
        limits=_LIMITS,
    )
    assert verified.materialization.checked_artifact.selected_entry.publication is original.publications[0]
    fields["context_digest"] = sha256(
        _lp(
            newer_policy.policy.digest_domain.encode(),
            *_binding(original, entry.schema_id)[1],
            _body({key: value for key, value in fields.items() if key != "context_digest"}),
        )
    ).hexdigest()
    with pytest.raises(TypedValueArtifactIntegrityError, match="self_digest_mismatch"):
        verify_protected_typed_value_artifact_integrity(
            _wire(original, entry.schema_id, _body(fields)),
            history=history,
            route=TypedValueRegistryReadRoute.PUBLIC,
            limits=_LIMITS,
        )


def test_profile_three_cursor_uses_registered_message_and_separately_trusted_key(tmp_path: Path) -> None:
    history = _publication(tmp_path)
    entry = history.publications[0].compiled_registry.entry_for("GraphObservationCursorPayload", "1")
    values: dict[str, object] = {
        "authorization_decision_digest": "a" * 64,
        "authorization_expires_at": {"$type": "datetime", "value": "2026-09-08T00:00:00.000000Z"},
        "caller_context_digest": "b" * 64,
        "cohort_digest": "c" * 64,
        "graph_revision": "graph",
        "observation_revision": "observation",
        "page_policy_digest": "d" * 64,
        "page_policy_revision": "policy",
        "preceding_primary_key": None,
        "preceding_record_digest": None,
        "preceding_record_kind": None,
        "requested_total_page_size": {"$type": "integer", "value": "1"},
        "schema_version": {"$type": "integer", "value": "1"},
        "signature": "0" * 128,
        "snapshot_token": "snapshot",
        "snapshot_write_revision": {"$type": "integer", "value": "0"},
        "stream_position": {"$type": "integer", "value": "0"},
        "system_as_of": {"$type": "datetime", "value": "2026-09-07T00:00:00.000000Z"},
        "valid_at": None,
        "view": "current",
    }
    unsigned = _body(values)
    validated = validate_typed_value_body(
        unsigned, registry=history.publications[0].compiled_registry, entry=entry, limits=_LIMITS.body_limits
    )
    role = _policy(history, entry.schema_id)
    assert isinstance(role.policy, SignatureOnlyPolicy)
    _, members = _binding(history, entry.schema_id)
    from memorii.core.memory_evolution.ingestion_contracts import CanonicalTypedValueProfileBinding

    bound = CanonicalTypedValueProfileBinding(
        entry.profile.profile_id, 3, entry.profile.profile_digest, entry.schema_id, 1, entry.binding_digest
    )
    private = Ed25519PrivateKey.generate()
    preimage = _lp(
        role.policy.signature_domain.encode(),
        *members,
        _body({key: value for key, value in values.items() if key != "signature"}),
    )
    message = _lp(role.policy.signature_purpose.encode(), *members, preimage, sha256(preimage).hexdigest().encode())
    values["signature"] = private.sign(message).hex()
    body = _body(values)
    public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    assert registered_signature_only_message(validated.tree, binding=bound, policy=role.policy) == message
    result = verify_protected_typed_value_artifact_integrity(
        _wire(history, entry.schema_id, body),
        history=history,
        route=TypedValueRegistryReadRoute.PUBLIC,
        limits=_LIMITS,
        verification_key=TrustedTypedValueArtifactVerificationKey(public),
    )
    assert result.cryptographic_signature_checked
    with pytest.raises(TypedValueArtifactIntegrityError, match="verification_key_required"):
        verify_protected_typed_value_artifact_integrity(
            _wire(history, entry.schema_id, body),
            history=history,
            route=TypedValueRegistryReadRoute.PUBLIC,
            limits=_LIMITS,
        )
    other = (
        Ed25519PrivateKey.generate()
        .public_key()
        .public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    )
    with pytest.raises(TypedValueArtifactIntegrityError, match="signature_mismatch"):
        verify_protected_typed_value_artifact_integrity(
            _wire(history, entry.schema_id, body),
            history=history,
            route=TypedValueRegistryReadRoute.PUBLIC,
            limits=_LIMITS,
            verification_key=TrustedTypedValueArtifactVerificationKey(other),
        )
    binary_digest_values = dict(values)
    binary_digest_values["signature"] = private.sign(
        _lp(role.policy.signature_purpose.encode(), *members, preimage, sha256(preimage).digest())
    ).hex()
    with pytest.raises(TypedValueArtifactIntegrityError, match="signature_mismatch"):
        verify_protected_typed_value_artifact_integrity(
            _wire(history, entry.schema_id, _body(binary_digest_values)),
            history=history,
            route=TypedValueRegistryReadRoute.PUBLIC,
            limits=_LIMITS,
            verification_key=TrustedTypedValueArtifactVerificationKey(public),
        )
    wrong_purpose = dict(values)
    wrong_purpose["signature"] = private.sign(
        _lp(b"wrong-purpose", *members, preimage, sha256(preimage).hexdigest().encode())
    ).hex()
    altered_body = dict(values)
    altered_body["graph_revision"] = "changed"
    for rejected in (_body(wrong_purpose), _body(altered_body)):
        with pytest.raises(TypedValueArtifactIntegrityError, match="signature_mismatch"):
            verify_protected_typed_value_artifact_integrity(
                _wire(history, entry.schema_id, rejected),
                history=history,
                route=TypedValueRegistryReadRoute.PUBLIC,
                limits=_LIMITS,
                verification_key=TrustedTypedValueArtifactVerificationKey(public),
            )
    with pytest.raises(TypedValueArtifactIntegrityError, match="protected_read_invalid"):
        verify_protected_typed_value_artifact_integrity(
            b"v1.legacy",
            history=history,
            route=TypedValueRegistryReadRoute.PUBLIC,
            limits=_LIMITS,
            verification_key=TrustedTypedValueArtifactVerificationKey(public),
        )


def test_malformed_envelope_never_reaches_body_or_integrity_and_checkpoint_requires_external_context(
    tmp_path: Path,
) -> None:
    history = _publication(tmp_path)
    with (
        patch(
            "memorii.core.memory_evolution.typed_value_artifact_integrity.validate_materialize_and_reencode_checked_typed_value_artifact"
        ) as materialize,
        pytest.raises(TypedValueArtifactIntegrityError, match="protected_read_invalid"),
    ):
        verify_protected_typed_value_artifact_integrity(
            b"{bad", history=history, route=TypedValueRegistryReadRoute.PUBLIC, limits=_LIMITS
        )
    materialize.assert_not_called()
    checkpoint = _body(
        {
            "checkpoint_digest": "0" * 64,
            "checkpoint_id": "checkpoint",
            "created_at": {"$type": "datetime", "value": "2026-09-07T00:00:00.000000Z"},
            "last_observation_delta_digest": "a" * 64,
            "last_observation_delta_id": "delta",
            "materialized_observation_ledger_digest": "b" * 64,
            "observation_revision": "revision",
            "observation_schema_fingerprint": "c" * 64,
            "signature": "0" * 128,
            "signing_key_id": "key",
            "trust_policy_digest": "d" * 64,
        }
    )
    with pytest.raises(TypedValueArtifactIntegrityError, match="required_external_context_unavailable"):
        verify_protected_typed_value_artifact_integrity(
            _wire(history, "IngestionObservationReplayCheckpoint", checkpoint),
            history=history,
            route=TypedValueRegistryReadRoute.PUBLIC,
            limits=_LIMITS,
        )
