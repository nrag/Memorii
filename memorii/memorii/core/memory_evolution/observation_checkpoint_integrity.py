"""Pure registered integrity construction for observation checkpoints.

This owner verifies fixed checkpoint bytes and signatures only.  It neither
accepts raw external artifacts nor grants replay, lifecycle, key, persistence,
or activation authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from memorii.core.memory_evolution.ingestion_contracts import CanonicalTypedValueProfileBinding
from memorii.core.memory_evolution.observation_ledger_contracts import ObservationLedgerHead
from memorii.core.memory_evolution.observation_replay_contracts import (
    IngestionObservationReplayCheckpoint,
    ObservationCheckpointLifecycle,
    ObservationCheckpointSigningPreimage,
    ObservationReplayState,
)
from memorii.core.memory_evolution.typed_value_artifact_integrity import (
    TrustedTypedValueArtifactVerificationKey,
)
from memorii.core.memory_evolution.typed_value_declarations import (
    DigestSignatureRole,
    ExternalSigningPreimagePolicy,
)
from memorii.core.memory_evolution.typed_value_model_codec import (
    TypedValueModelCodecError,
    encode_typed_value_model_candidate,
)
from memorii.core.memory_evolution.typed_value_registry_history import (
    ResolvedTypedValueRegistryHistoryEntry,
)


class ObservationCheckpointIntegrityError(ValueError):
    """A fixed checkpoint preimage or its cryptographic proof is invalid."""


@dataclass(frozen=True)
class ObservationCheckpointIntegrityResult:
    """Non-authorizing checkpoint integrity evidence only."""

    canonical_preimage_bytes: bytes
    checkpoint_digest: str
    signature_verified: bool


@dataclass(frozen=True)
class ObservationCheckpointPreimageConstruction:
    """Fixed typed checkpoint preimage and its canonical body, without authority."""

    preimage: ObservationCheckpointSigningPreimage
    canonical_preimage_bytes: bytes
    checkpoint_binding: CanonicalTypedValueProfileBinding
    policy: ExternalSigningPreimagePolicy


def verify_observation_checkpoint_integrity(
    *,
    selected_checkpoint: ResolvedTypedValueRegistryHistoryEntry,
    replay_state: ObservationReplayState,
    independently_loaded_head: ObservationLedgerHead,
    lifecycle: ObservationCheckpointLifecycle,
    checkpoint: IngestionObservationReplayCheckpoint,
    repository_id: str,
    activation_digest: str,
    sequence: int,
    verification_key: TrustedTypedValueArtifactVerificationKey,
    maximum_bytes: int,
    maximum_nodes: int,
    maximum_depth: int,
) -> ObservationCheckpointIntegrityResult:
    """Construct and verify the one closed ``observation_checkpoint_v1`` preimage."""
    construction = construct_observation_checkpoint_v1_preimage(
        selected_checkpoint=selected_checkpoint,
        replay_state=replay_state,
        independently_loaded_head=independently_loaded_head,
        lifecycle=lifecycle,
        checkpoint=checkpoint,
        repository_id=repository_id,
        activation_digest=activation_digest,
        sequence=sequence,
        maximum_bytes=maximum_bytes,
        maximum_nodes=maximum_nodes,
        maximum_depth=maximum_depth,
    )
    if type(verification_key) is not TrustedTypedValueArtifactVerificationKey:
        raise ObservationCheckpointIntegrityError("observation_checkpoint_integrity_input_invalid")
    schema_preimage = _length_prefixed(
        construction.policy.signature_domain.encode("utf-8"),
        *_binding_members(construction.checkpoint_binding),
        construction.canonical_preimage_bytes,
    )
    digest = sha256(schema_preimage).hexdigest()
    if checkpoint.checkpoint_digest != digest:
        raise ObservationCheckpointIntegrityError("observation_checkpoint_integrity_digest_mismatch")
    try:
        signature = bytes.fromhex(checkpoint.signature)
        if len(signature) != 64:
            raise ValueError("signature length")
        Ed25519PublicKey.from_public_bytes(verification_key.public_key).verify(
            signature,
            _length_prefixed(
                construction.policy.signature_purpose.encode("utf-8"),
                *_binding_members(construction.checkpoint_binding),
                schema_preimage,
                digest.encode("ascii"),
            ),
        )
    except (InvalidSignature, ValueError) as exc:
        raise ObservationCheckpointIntegrityError("observation_checkpoint_integrity_signature_mismatch") from exc
    return ObservationCheckpointIntegrityResult(construction.canonical_preimage_bytes, digest, True)


def construct_observation_checkpoint_v1_preimage(
    *,
    selected_checkpoint: ResolvedTypedValueRegistryHistoryEntry,
    replay_state: ObservationReplayState,
    independently_loaded_head: ObservationLedgerHead,
    lifecycle: ObservationCheckpointLifecycle,
    checkpoint: IngestionObservationReplayCheckpoint,
    repository_id: str,
    activation_digest: str,
    sequence: int,
    maximum_bytes: int,
    maximum_nodes: int,
    maximum_depth: int,
) -> ObservationCheckpointPreimageConstruction:
    """Build the sole fixed checkpoint preimage without digesting or signing it."""
    _require_inputs(
        selected_checkpoint,
        replay_state,
        independently_loaded_head,
        lifecycle,
        checkpoint,
        repository_id,
        activation_digest,
        sequence,
    )
    policy = _checkpoint_policy(selected_checkpoint)
    _require_joins(
        replay_state,
        independently_loaded_head,
        lifecycle,
        checkpoint,
        repository_id,
        activation_digest,
        sequence,
    )
    publication = selected_checkpoint.publication
    try:
        preimage_entry = publication.compiled_registry.entry_for(
            policy.preimage_schema_id, policy.preimage_schema_version
        )
    except KeyError as exc:
        raise ObservationCheckpointIntegrityError("observation_checkpoint_integrity_preimage_entry_missing") from exc
    preimage = ObservationCheckpointSigningPreimage(
        purpose="observation_checkpoint",
        repository_id=repository_id,
        activation_digest=activation_digest,
        sequence=sequence,
        head=independently_loaded_head,
        lifecycle=lifecycle,
        checkpoint_id=checkpoint.checkpoint_id,
        observation_revision=checkpoint.observation_revision,
        last_observation_delta_id=checkpoint.last_observation_delta_id,
        last_observation_delta_digest=checkpoint.last_observation_delta_digest,
        materialized_observation_ledger_digest=checkpoint.materialized_observation_ledger_digest,
        observation_schema_fingerprint=checkpoint.observation_schema_fingerprint,
        created_at=checkpoint.created_at,
        signing_key_id=checkpoint.signing_key_id,
        trust_policy_digest=checkpoint.trust_policy_digest,
    )
    try:
        materialized = encode_typed_value_model_candidate(
            preimage,
            entry=preimage_entry,
            publication=publication,
            maximum_bytes=maximum_bytes,
            maximum_nodes=maximum_nodes,
            maximum_depth=maximum_depth,
        )
    except TypedValueModelCodecError as exc:
        raise ObservationCheckpointIntegrityError("observation_checkpoint_integrity_preimage_encoding_invalid") from exc
    return ObservationCheckpointPreimageConstruction(preimage, materialized.body.raw_bytes, _binding(selected_checkpoint), policy)


def _checkpoint_policy(
    selected: ResolvedTypedValueRegistryHistoryEntry,
) -> ExternalSigningPreimagePolicy:
    entry = selected.entry
    if (entry.schema_id, entry.schema_version) != ("IngestionObservationReplayCheckpoint", "1"):
        raise ObservationCheckpointIntegrityError("observation_checkpoint_integrity_checkpoint_entry_invalid")
    roles = tuple(
        role
        for role in selected.publication.compiled_registry.parsed_roles
        if isinstance(role, DigestSignatureRole)
        and role.schema_id == entry.schema_id
        and role.schema_version == entry.schema_version
    )
    if len(roles) != 1 or not isinstance(roles[0].policy, ExternalSigningPreimagePolicy):
        raise ObservationCheckpointIntegrityError("observation_checkpoint_integrity_policy_invalid")
    policy = roles[0].policy
    if (
        policy.binding_kind != "observation_checkpoint_v1"
        or policy.preimage_schema_id != "ObservationCheckpointSigningPreimage"
        or policy.preimage_schema_version != "1"
        or policy.signature_purpose != "observation_checkpoint"
    ):
        raise ObservationCheckpointIntegrityError("observation_checkpoint_integrity_policy_invalid")
    return policy


def _require_inputs(*values: object) -> None:
    expected = (
        ResolvedTypedValueRegistryHistoryEntry,
        ObservationReplayState,
        ObservationLedgerHead,
        ObservationCheckpointLifecycle,
        IngestionObservationReplayCheckpoint,
        str,
        str,
        int,
    )
    if any(type(value) is not kind for value, kind in zip(values, expected, strict=True)):
        raise ObservationCheckpointIntegrityError("observation_checkpoint_integrity_input_invalid")


def _require_joins(
    state: ObservationReplayState,
    head: ObservationLedgerHead,
    lifecycle: ObservationCheckpointLifecycle,
    checkpoint: IngestionObservationReplayCheckpoint,
    repository_id: str,
    activation_digest: str,
    sequence: int,
) -> None:
    if (
        sequence <= 0
        or state.head != head
        or state.repository_id != repository_id
        or state.activation_digest != activation_digest
        or head.repository_id != repository_id
        or head.activation_digest != activation_digest
        or head.sequence != sequence
        or lifecycle.repository_id != repository_id
        or checkpoint.materialized_observation_ledger_digest != state.state_digest
        or checkpoint.observation_revision != head.observation_revision
        or checkpoint.last_observation_delta_id != head.last_delta_id
        or checkpoint.last_observation_delta_digest != head.last_delta_digest
        or checkpoint.trust_policy_digest != lifecycle.trust_policy_digest
    ):
        raise ObservationCheckpointIntegrityError("observation_checkpoint_integrity_join_invalid")


def _binding(selected: ResolvedTypedValueRegistryHistoryEntry) -> CanonicalTypedValueProfileBinding:
    entry = selected.entry
    return CanonicalTypedValueProfileBinding(
        entry.profile.profile_id,
        int(entry.profile.profile_version),
        entry.profile.profile_digest,
        entry.schema_id,
        int(entry.schema_version),
        entry.binding_digest,
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


def _length_prefixed(*parts: bytes) -> bytes:
    return b"".join(len(part).to_bytes(8, "big") + part for part in parts)
