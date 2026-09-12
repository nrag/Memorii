"""Registered integrity checks for a protected profile-3 artifact.

This layer deliberately grants only integrity and cryptographic-check results.
It does not establish key lifecycle, request authorization, persistence, or
activation authority.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from memorii.core.memory_evolution.ingestion_contracts import CanonicalTypedValueProfileBinding
from memorii.core.memory_evolution.typed_value_artifact_reader import (
    CheckedTypedValueArtifact,
    ProtectedTypedValueArtifactReaderLimits,
    TypedValueArtifactReaderError,
    UnauthenticatedTypedValueMaterialization,
    read_protected_typed_value_artifact,
    validate_materialize_and_reencode_checked_typed_value_artifact,
)
from memorii.core.memory_evolution.typed_value_body_validation import canonical_bytes
from memorii.core.memory_evolution.typed_value_declarations import (
    DigestSignatureRole,
    ExternalSigningPreimagePolicy,
    OrdinaryPolicy,
    SelfDigestPolicy,
    SignatureOnlyPolicy,
)
from memorii.core.memory_evolution.typed_value_decoder_sources import FrozenJsonValue
from memorii.core.memory_evolution.typed_value_registry_history import (
    ProtectedTypedValueRegistryHistory,
    TypedValueRegistryReadRoute,
)


class TypedValueArtifactIntegrityError(ValueError):
    """A selected artifact has not passed its registered integrity policy."""


@dataclass(frozen=True)
class TrustedTypedValueArtifactVerificationKey:
    """A separately trusted Ed25519 public key for the signature-only cursor."""

    public_key: bytes

    def __post_init__(self) -> None:
        if type(self.public_key) is not bytes or len(self.public_key) != 32:
            raise ValueError("typed_value_artifact_integrity_verification_key_invalid")


@dataclass(frozen=True)
class IntegrityCheckedTypedValueArtifact:
    """A materialized value whose selected registered integrity check passed.

    This result is intentionally insufficient for authorization, key lifecycle,
    persistence, activation, or any other native-authority decision.
    """

    materialization: UnauthenticatedTypedValueMaterialization
    integrity_policy_kind: str
    cryptographic_signature_checked: bool


def verify_protected_typed_value_artifact_integrity(
    raw_bytes: bytes,
    *,
    history: ProtectedTypedValueRegistryHistory,
    route: TypedValueRegistryReadRoute,
    limits: ProtectedTypedValueArtifactReaderLimits,
    verification_key: TrustedTypedValueArtifactVerificationKey | None = None,
) -> IntegrityCheckedTypedValueArtifact:
    """Read, losslessly materialize, then apply the exact root policy.

    The protected reader owns outer parsing, historical entry selection, native
    digests, selected body validation, and native round-trip reconstruction.
    This function supplies no caller-selected binding, policy, exclusions, or
    decoder.
    """
    if type(raw_bytes) is not bytes:
        raise TypedValueArtifactIntegrityError("typed_value_artifact_integrity_raw_bytes_invalid")
    try:
        checked = read_protected_typed_value_artifact(
            raw_bytes, history=history, route=route, limits=limits
        )
        policy = _selected_root_policy(checked)
        if isinstance(policy, ExternalSigningPreimagePolicy):
            raise TypedValueArtifactIntegrityError(
                "typed_value_artifact_integrity_required_external_context_unavailable"
            )
        materialization = validate_materialize_and_reencode_checked_typed_value_artifact(
            checked, limits=limits
        )
    except TypedValueArtifactReaderError as exc:
        raise TypedValueArtifactIntegrityError("typed_value_artifact_integrity_protected_read_invalid") from exc

    body = materialization.validated_body
    binding = materialization.checked_artifact.binding
    if isinstance(policy, OrdinaryPolicy):
        return IntegrityCheckedTypedValueArtifact(materialization, policy.kind, False)
    if isinstance(policy, SelfDigestPolicy):
        _verify_self_digest(body.tree, binding, policy)
        return IntegrityCheckedTypedValueArtifact(materialization, policy.kind, False)
    if isinstance(policy, SignatureOnlyPolicy):
        _verify_signature_only(body.tree, binding, policy, verification_key)
        return IntegrityCheckedTypedValueArtifact(materialization, policy.kind, True)
    raise TypedValueArtifactIntegrityError("typed_value_artifact_integrity_policy_unknown")


def _selected_root_policy(
    checked: CheckedTypedValueArtifact,
) -> OrdinaryPolicy | SelfDigestPolicy | SignatureOnlyPolicy | ExternalSigningPreimagePolicy:
    entry = checked.selected_entry.entry
    roles = tuple(
        item
        for item in checked.selected_entry.publication.compiled_registry.parsed_roles
        if isinstance(item, DigestSignatureRole)
        and item.schema_id == entry.schema_id
        and item.schema_version == entry.schema_version
    )
    if len(roles) != 1 or not isinstance(
        roles[0].policy,
        (OrdinaryPolicy, SelfDigestPolicy, SignatureOnlyPolicy, ExternalSigningPreimagePolicy),
    ):
        raise TypedValueArtifactIntegrityError("typed_value_artifact_integrity_root_policy_invalid")
    return roles[0].policy


def _verify_self_digest(
    tree: Mapping[str, FrozenJsonValue],
    binding: CanonicalTypedValueProfileBinding,
    policy: SelfDigestPolicy,
) -> None:
    supplied = _root_string_field(tree, policy.digest_field)
    expected = sha256(registered_self_digest_preimage(tree, binding=binding, policy=policy)).hexdigest()
    if supplied != expected:
        raise TypedValueArtifactIntegrityError("typed_value_artifact_integrity_self_digest_mismatch")


def _verify_signature_only(
    tree: Mapping[str, FrozenJsonValue],
    binding: CanonicalTypedValueProfileBinding,
    policy: SignatureOnlyPolicy,
    verification_key: TrustedTypedValueArtifactVerificationKey | None,
) -> None:
    if type(verification_key) is not TrustedTypedValueArtifactVerificationKey:
        raise TypedValueArtifactIntegrityError("typed_value_artifact_integrity_verification_key_required")
    signature_text = _root_string_field(tree, policy.signature_field)
    try:
        signature = bytes.fromhex(signature_text)
    except ValueError as exc:  # Body validation normally catches this lexical failure.
        raise TypedValueArtifactIntegrityError("typed_value_artifact_integrity_signature_invalid") from exc
    if len(signature) != 64:
        raise TypedValueArtifactIntegrityError("typed_value_artifact_integrity_signature_invalid")
    message = registered_signature_only_message(tree, binding=binding, policy=policy)
    try:
        Ed25519PublicKey.from_public_bytes(verification_key.public_key).verify(signature, message)
    except (InvalidSignature, ValueError) as exc:
        raise TypedValueArtifactIntegrityError("typed_value_artifact_integrity_signature_mismatch") from exc


def registered_self_digest_preimage(
    tree: Mapping[str, FrozenJsonValue],
    *,
    binding: CanonicalTypedValueProfileBinding,
    policy: SelfDigestPolicy,
) -> bytes:
    """Build the registered self-digest preimage without issuing a digest.

    Future controlled candidate preparation can reuse this exact construction,
    but must still own materialization and authority separately.
    """
    _root_string_field(tree, policy.digest_field)
    return _length_prefixed(
        policy.digest_domain.encode("utf-8"),
        *_binding_members(binding),
        canonical_bytes(_root_without_field(tree, policy.digest_field)),
    )


def registered_signature_only_message(
    tree: Mapping[str, FrozenJsonValue],
    *,
    binding: CanonicalTypedValueProfileBinding,
    policy: SignatureOnlyPolicy,
) -> bytes:
    """Build the registered signature-only verification message, never a signature."""
    _root_string_field(tree, policy.signature_field)
    preimage = _length_prefixed(
        policy.signature_domain.encode("utf-8"),
        *_binding_members(binding),
        canonical_bytes(_root_without_field(tree, policy.signature_field)),
    )
    return _length_prefixed(
        policy.signature_purpose.encode("utf-8"),
        *_binding_members(binding),
        preimage,
        sha256(preimage).hexdigest().encode("ascii"),
    )


def _binding_members(binding: CanonicalTypedValueProfileBinding) -> tuple[bytes, ...]:
    return (
        binding.profile_id.encode("utf-8"),
        str(binding.profile_version).encode("ascii"),
        binding.profile_digest.encode("ascii"),
        binding.schema_id.encode("utf-8"),
        str(binding.schema_version).encode("ascii"),
        binding.binding_digest.encode("ascii"),
    )


def _root_string_field(tree: Mapping[str, FrozenJsonValue], field_name: str) -> str:
    entries = _root_entries(tree)
    matches = tuple(value for name, value in entries if name == field_name)
    if len(matches) != 1 or type(matches[0]) is not str:
        raise TypedValueArtifactIntegrityError("typed_value_artifact_integrity_root_field_invalid")
    return matches[0]


def _root_without_field(
    tree: Mapping[str, FrozenJsonValue], field_name: str
) -> Mapping[str, FrozenJsonValue]:
    entries = _root_entries(tree)
    retained = tuple((name, value) for name, value in entries if name != field_name)
    if len(retained) != len(entries) - 1:
        raise TypedValueArtifactIntegrityError("typed_value_artifact_integrity_root_field_invalid")
    # The parsed CTV tree is already canonical.  This removes only the declared
    # root member; nested integrity fields remain part of the serialized body.
    return {"$type": "map", "entries": retained}


def _root_entries(tree: Mapping[str, FrozenJsonValue]) -> tuple[tuple[str, FrozenJsonValue], ...]:
    if set(tree) != {"$type", "entries"} or tree.get("$type") != "map":
        raise TypedValueArtifactIntegrityError("typed_value_artifact_integrity_root_tree_invalid")
    raw_entries = tree.get("entries")
    if not isinstance(raw_entries, tuple):
        raise TypedValueArtifactIntegrityError("typed_value_artifact_integrity_root_tree_invalid")
    entries: list[tuple[str, FrozenJsonValue]] = []
    for item in raw_entries:
        if not isinstance(item, tuple) or len(item) != 2 or not isinstance(item[0], str):
            raise TypedValueArtifactIntegrityError("typed_value_artifact_integrity_root_tree_invalid")
        entries.append((item[0], item[1]))
    return tuple(entries)


def _length_prefixed(*parts: bytes) -> bytes:
    return b"".join(len(part).to_bytes(8, "big") + part for part in parts)
