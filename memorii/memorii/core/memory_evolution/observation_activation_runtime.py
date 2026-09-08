"""Registered observation artifacts and fixed ledger hash preimages."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from hashlib import sha256

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import BaseModel

from memorii.core.memory_evolution.graph_effect_contracts import (
    GraphRevisionDelta,
    IngestionObservationDelta,
    SourceFinalizationObservationDelta,
)
from memorii.core.memory_evolution.graph_observation_public_contracts import (
    AuthenticatedGraphObservationContext,
    GraphObservationAuthorizationDecision,
    GraphObservationPage,
    GraphObservationPagePolicySnapshot,
    GraphRecordObservationSnapshot,
)
from memorii.core.memory_evolution.graph_observation_snapshot_contracts import (
    GraphObservationCohortPreimage,
    GraphObservationCursorPayload,
    ResolvedGraphObservationCohort,
)
from memorii.core.memory_evolution.ingestion_contracts import CanonicalTypedValueProfileBinding, encode_typed_value
from memorii.core.memory_evolution.observation_ledger_contracts import (
    ObservationGroupSemanticPayload,
    ObservationLedgerActivation,
    ObservationLedgerEntry,
    ObservationLedgerHead,
    ObservationSourceSemanticPayload,
    SourceObservationIntent,
)
from memorii.core.memory_evolution.observation_replay_contracts import ObservationReplayState
from memorii.core.memory_evolution.typed_value_artifact_integrity import (
    TrustedTypedValueArtifactVerificationKey,
    registered_self_digest_preimage,
    registered_signature_only_message,
    verify_protected_typed_value_artifact_integrity,
)
from memorii.core.memory_evolution.typed_value_artifact_reader import ProtectedTypedValueArtifactReaderLimits
from memorii.core.memory_evolution.typed_value_body_validation import ProtectedTypedValueBodyLimits
from memorii.core.memory_evolution.typed_value_declarations import (
    DigestSignatureRole,
    OrdinaryPolicy,
    SelfDigestPolicy,
    SignatureOnlyPolicy,
)
from memorii.core.memory_evolution.typed_value_model_codec import encode_typed_value_model_candidate
from memorii.core.memory_evolution.typed_value_publication import VerifiedTypedValuePublication
from memorii.core.memory_evolution.typed_value_registry_history import (
    ProtectedTypedValueRegistryHistory,
    ResolvedTypedValueRegistryHistoryEntry,
    TypedValueRegistryReadRoute,
)
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.store import record_digest
from memorii.core.semantic_ingestion.bootstrap_graph_projection_publication import (
    BootstrapGraphNativeProjectionPublicationReceiptV3,
    BootstrapGraphNativeReplayAuthorityEvidenceV3,
    BootstrapGraphNativeReplayCheckpointEvidenceV3,
)


class ObservationActivationRuntimeError(ValueError):
    pass


_ROOT_TYPES: dict[str, type[BaseModel]] = {
    "ObservationLedgerActivation": ObservationLedgerActivation,
    "ObservationLedgerHead": ObservationLedgerHead,
    "ObservationLedgerEntry": ObservationLedgerEntry,
    "SourceObservationIntent": SourceObservationIntent,
    "ObservationGroupSemanticPayload": ObservationGroupSemanticPayload,
    "ObservationSourceSemanticPayload": ObservationSourceSemanticPayload,
    "IngestionObservationDelta": IngestionObservationDelta,
    "SourceFinalizationObservationDelta": SourceFinalizationObservationDelta,
    "ObservationReplayState": ObservationReplayState,
    "GraphRevisionDelta": GraphRevisionDelta,
    "GraphObservationCursorPayload": GraphObservationCursorPayload,
    "AuthenticatedGraphObservationContext": AuthenticatedGraphObservationContext,
    "GraphObservationAuthorizationDecision": GraphObservationAuthorizationDecision,
    "GraphObservationPagePolicySnapshot": GraphObservationPagePolicySnapshot,
    "GraphObservationCohortPreimage": GraphObservationCohortPreimage,
    "ResolvedGraphObservationCohort": ResolvedGraphObservationCohort,
    "GraphRecordObservationSnapshot": GraphRecordObservationSnapshot,
    "GraphObservationPage": GraphObservationPage,
    "BootstrapGraphNativeProjectionPublicationReceiptV3": BootstrapGraphNativeProjectionPublicationReceiptV3,
    "BootstrapGraphNativeReplayAuthorityEvidenceV3": BootstrapGraphNativeReplayAuthorityEvidenceV3,
    "BootstrapGraphNativeReplayCheckpointEvidenceV3": BootstrapGraphNativeReplayCheckpointEvidenceV3,
}
_PAYLOAD_DOMAIN = b"memorii.observation-ledger.semantic-payload.v1"
_REVISION_DOMAIN = b"memorii.observation-ledger.revision.v1"


@dataclass(frozen=True)
class RegisteredObservationArtifact:
    value: BaseModel
    raw: bytes
    binding: CanonicalTypedValueProfileBinding
    canonical_value_bytes: bytes
    canonical_value_digest: str


_LIMITS = ProtectedTypedValueArtifactReaderLimits(
    2 * 1024 * 1024, 64_000, 32, ProtectedTypedValueBodyLimits(2 * 1024 * 1024, 64_000, 32)
)


def legacy_terminal_inventory_digest(snapshot: tuple[CanonicalMemoryRecord, ...]) -> str:
    """Commit the exact retired control/root set, excluding locator aliases."""
    rows = tuple(sorted(
        (record.memory_id, record_digest(record)) for record in snapshot
        if record.source_kind in {
            "semantic_ingestion_preplanning_control",
            "semantic_ingestion_bootstrap_graph_v3_terminal_control",
        } or (record.source_kind == "semantic_ingestion_bootstrap_graph_v3_terminal_locator"
              and record.memory_id.startswith("semantic_ingestion:bootstrap-graph-v3:terminal-locator:"))
    ))
    if len({row[0] for row in rows}) != len(rows):
        raise ObservationActivationRuntimeError("legacy inventory contains duplicate identities")
    return sha256(encode_typed_value(rows)).hexdigest()


def require_registered_activation_schemas(history: ProtectedTypedValueRegistryHistory, *, publication: VerifiedTypedValuePublication) -> None:
    _entry(history, "ObservationLedgerActivation", publication)
    _entry(history, "ObservationLedgerHead", publication)


def registered_activation_artifact(
    activation: ObservationLedgerActivation,
    *, history: ProtectedTypedValueRegistryHistory, publication: VerifiedTypedValuePublication | None = None,
    limits: ProtectedTypedValueArtifactReaderLimits = _LIMITS,
) -> tuple[ObservationLedgerActivation, bytes]:
    raw = _registered_artifact(activation, "ObservationLedgerActivation", history, publication, limits)
    value = validate_registered_artifact(raw, schema_id="ObservationLedgerActivation", history=history, limits=limits)
    if type(value) is not ObservationLedgerActivation:
        raise ObservationActivationRuntimeError("registered observation activation decode is invalid")
    return value, raw


def registered_genesis_head_artifact(
    activation: ObservationLedgerActivation,
    *, history: ProtectedTypedValueRegistryHistory, publication: VerifiedTypedValuePublication | None = None,
    limits: ProtectedTypedValueArtifactReaderLimits = _LIMITS,
) -> tuple[ObservationLedgerHead, bytes]:
    provisional = ObservationLedgerHead(
        schema_version=1, repository_id=activation.repository_id,
        activation_digest=activation.activation_digest, sequence=0,
        observation_revision="genesis", last_delta_id=None, last_delta_digest=None,
        last_entry_digest=None, head_digest="0" * 64,
    )
    raw = _registered_artifact(provisional, "ObservationLedgerHead", history, publication, limits)
    checked = verify_protected_typed_value_artifact_integrity(
        raw, history=history, route=TypedValueRegistryReadRoute.INTERNAL_REPLAY, limits=limits,
    )
    value = checked.materialization.materialized.value
    if type(value) is not ObservationLedgerHead:
        raise ObservationActivationRuntimeError("registered observation genesis head decode is invalid")
    return value, raw


def validate_registered_artifact(
    raw: bytes, *, schema_id: str, history: ProtectedTypedValueRegistryHistory,
    limits: ProtectedTypedValueArtifactReaderLimits = _LIMITS,
    verification_key: TrustedTypedValueArtifactVerificationKey | None = None,
) -> BaseModel:
    checked = verify_protected_typed_value_artifact_integrity(
        raw, history=history, route=TypedValueRegistryReadRoute.INTERNAL_REPLAY, limits=limits,
        verification_key=verification_key,
    )
    value = checked.materialization.materialized.value
    expected = _ROOT_TYPES.get(schema_id)
    if expected is None or type(value) is not expected:
        raise ObservationActivationRuntimeError("registered observation artifact schema is invalid")
    return value


def issue_registered_observation_cursor(
    payload: GraphObservationCursorPayload, *, history: ProtectedTypedValueRegistryHistory,
    publication: VerifiedTypedValuePublication, signing_key: Ed25519PrivateKey,
    verification_key: TrustedTypedValueArtifactVerificationKey,
    limits: ProtectedTypedValueArtifactReaderLimits,
) -> str:
    """Sign the registered cursor body; the page owner supplies frozen coordinates."""
    if type(payload) is not GraphObservationCursorPayload:
        raise ObservationActivationRuntimeError("observation cursor model is invalid")
    return _registered_artifact(
        payload, "GraphObservationCursorPayload", history, publication, limits,
        signing_key=signing_key, verification_key=verification_key,
    ).decode("utf-8", errors="strict")


def decode_registered_observation_cursor(
    cursor: str, *, history: ProtectedTypedValueRegistryHistory,
    publication: VerifiedTypedValuePublication,
    verification_key: TrustedTypedValueArtifactVerificationKey,
    limits: ProtectedTypedValueArtifactReaderLimits,
) -> GraphObservationCursorPayload:
    """Verify original envelope bytes and the protected selected cursor binding."""
    if type(cursor) is not str or len(cursor) > limits.maximum_envelope_bytes:
        raise ObservationActivationRuntimeError("observation cursor wire limit exceeded")
    try:
        raw = cursor.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise ObservationActivationRuntimeError("observation cursor is not Unicode scalar text") from exc
    checked = verify_protected_typed_value_artifact_integrity(
        raw, history=history, route=TypedValueRegistryReadRoute.INTERNAL_REPLAY,
        limits=limits, verification_key=verification_key,
    )
    selected = _entry(history, "GraphObservationCursorPayload", publication)
    value = checked.materialization.materialized.value
    if (type(value) is not GraphObservationCursorPayload
            or checked.materialization.checked_artifact.binding != _binding(selected)
            or not checked.cryptographic_signature_checked):
        raise ObservationActivationRuntimeError("observation cursor binding is substituted")
    return value


def emit_registered_observation_artifact(
    value: BaseModel, *, schema_id: str, history: ProtectedTypedValueRegistryHistory,
    publication: VerifiedTypedValuePublication,
    limits: ProtectedTypedValueArtifactReaderLimits = _LIMITS,
) -> RegisteredObservationArtifact:
    """Emit one exact root under the caller's protected selected publication."""
    expected = _ROOT_TYPES.get(schema_id)
    if expected is None or type(value) is not expected:
        raise ObservationActivationRuntimeError("registered observation artifact model is invalid")
    selected = _entry(history, schema_id, publication)
    binding = _binding(selected)
    raw = _registered_artifact(value, schema_id, history, publication, limits)
    checked = verify_protected_typed_value_artifact_integrity(
        raw, history=history, route=TypedValueRegistryReadRoute.INTERNAL_REPLAY, limits=limits,
    )
    if checked.materialization.checked_artifact.binding != binding or type(checked.materialization.materialized.value) is not expected:
        raise ObservationActivationRuntimeError("registered observation artifact publication is substituted")
    body = checked.materialization.checked_artifact.canonical_value_bytes
    return RegisteredObservationArtifact(checked.materialization.materialized.value, raw, binding, body, sha256(body).hexdigest())


def registered_semantic_payload(
    delta: IngestionObservationDelta | SourceFinalizationObservationDelta,
    *, history: ProtectedTypedValueRegistryHistory, publication: VerifiedTypedValuePublication,
    limits: ProtectedTypedValueArtifactReaderLimits = _LIMITS,
) -> RegisteredObservationArtifact:
    if type(delta) is IngestionObservationDelta:
        delta = IngestionObservationDelta.model_validate(delta.model_dump(mode="python"))
        return emit_registered_observation_artifact(
            ObservationGroupSemanticPayload.from_delta(delta), schema_id="ObservationGroupSemanticPayload",
            history=history, publication=publication, limits=limits,
        )
    if type(delta) is SourceFinalizationObservationDelta:
        delta = SourceFinalizationObservationDelta.model_validate(delta.model_dump(mode="python"))
        return emit_registered_observation_artifact(
            ObservationSourceSemanticPayload.from_delta(delta), schema_id="ObservationSourceSemanticPayload",
            history=history, publication=publication, limits=limits,
        )
    raise ObservationActivationRuntimeError("native observation delta type is invalid")


def semantic_payload_digest(
    artifact: RegisteredObservationArtifact, *, history: ProtectedTypedValueRegistryHistory,
    publication: VerifiedTypedValuePublication,
    limits: ProtectedTypedValueArtifactReaderLimits = _LIMITS,
) -> str:
    if artifact.binding.schema_id not in {"ObservationGroupSemanticPayload", "ObservationSourceSemanticPayload"}:
        raise ObservationActivationRuntimeError("semantic payload artifact schema is invalid")
    expected = _ROOT_TYPES[artifact.binding.schema_id]
    if type(artifact.value) is not expected:
        raise ObservationActivationRuntimeError("semantic payload value is invalid")
    # Re-emission is deliberately part of the commitment boundary: callers
    # cannot hand-assemble a plausible binding/body dataclass.
    verified = emit_registered_observation_artifact(
        artifact.value, schema_id=artifact.binding.schema_id, history=history,
        publication=publication, limits=limits,
    )
    if verified != artifact:
        raise ObservationActivationRuntimeError("semantic payload artifact is substituted")
    return sha256(_lp8(
        _PAYLOAD_DOMAIN, artifact.binding.profile_id.encode("utf-8"),
        str(artifact.binding.profile_version).encode("ascii"), artifact.binding.profile_digest.encode("ascii"),
        artifact.binding.schema_id.encode("utf-8"), str(artifact.binding.schema_version).encode("ascii"),
        artifact.binding.binding_digest.encode("ascii"), artifact.canonical_value_bytes,
    )).hexdigest()


def observation_successor_revision(
    head: ObservationLedgerHead, *, repository_id: str, activation_digest: str,
    payload_digest: str,
) -> str:
    head = ObservationLedgerHead.model_validate(head.model_dump(mode="python"))
    if head.repository_id != repository_id or head.activation_digest != activation_digest:
        raise ObservationActivationRuntimeError("observation successor head is substituted")
    _digest_ascii(payload_digest)
    return sha256(_lp8(
        _REVISION_DOMAIN, _identifier_bytes(repository_id), activation_digest.encode("ascii"),
        _identifier_bytes(head.observation_revision), payload_digest.encode("ascii"),
    )).hexdigest()


def _registered_artifact(value: BaseModel, schema_id: str, history: ProtectedTypedValueRegistryHistory, publication: VerifiedTypedValuePublication | None, limits: ProtectedTypedValueArtifactReaderLimits, *, signing_key: Ed25519PrivateKey | None = None, verification_key: TrustedTypedValueArtifactVerificationKey | None = None) -> bytes:
    selected = _entry(history, schema_id, publication)
    binding = _binding(selected)
    # A fixed-width placeholder preserves the body tree excluding the registered
    # digest field, whose self-digest preimage is selected from the publication.
    materialized = encode_typed_value_model_candidate(
        value, entry=selected.entry, publication=selected.publication,
        maximum_bytes=limits.body_limits.maximum_bytes,
        maximum_nodes=limits.body_limits.maximum_nodes,
        maximum_depth=limits.body_limits.maximum_depth,
    )
    policy = _digest_policy(selected)
    if isinstance(policy, SelfDigestPolicy):
        digest = sha256(registered_self_digest_preimage(materialized.body.tree, binding=binding, policy=policy)).hexdigest()
        final = value.model_copy(update={policy.digest_field: digest})
    elif isinstance(policy, OrdinaryPolicy):
        final = value
    elif isinstance(policy, SignatureOnlyPolicy):
        if (schema_id != "GraphObservationCursorPayload" or signing_key is None
                or verification_key is None or policy.signature_field != "signature"
                or policy.signature_domain != "memorii.graph-observation.cursor.v3"
                or policy.signature_purpose != "graph_observation_cursor"):
            raise ObservationActivationRuntimeError("observation cursor signing authority is invalid")
        message = registered_signature_only_message(materialized.body.tree, binding=binding, policy=policy)
        final = value.model_copy(update={policy.signature_field: signing_key.sign(message).hex()})
    else:
        raise ObservationActivationRuntimeError("registered observation artifact policy is unsupported")
    body = encode_typed_value_model_candidate(
        final, entry=selected.entry, publication=selected.publication,
        maximum_bytes=limits.body_limits.maximum_bytes,
        maximum_nodes=limits.body_limits.maximum_nodes,
        maximum_depth=limits.body_limits.maximum_depth,
    ).body.raw_bytes
    outer = {"$type": "map", "entries": [
        ("artifact_digest", sha256(_artifact_preimage(binding, body)).hexdigest()),
        ("binding", {"$type": "map", "entries": [
            ("binding_digest", binding.binding_digest), ("profile_digest", binding.profile_digest),
            ("profile_id", binding.profile_id), ("profile_version", {"$type": "integer", "value": str(binding.profile_version)}),
            ("schema_id", binding.schema_id), ("schema_version", {"$type": "integer", "value": str(binding.schema_version)}),
        ]}),
        ("canonical_value_bytes", {"$type": "bytes", "value": base64.b64encode(body).decode("ascii")}),
        ("canonical_value_digest", sha256(body).hexdigest()),
    ]}
    raw = json.dumps(outer, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    verified = validate_registered_artifact(raw, schema_id=schema_id, history=history, limits=limits, verification_key=verification_key)
    if verified != final:
        raise ObservationActivationRuntimeError("registered observation artifact roundtrip is invalid")
    return raw


def _entry(history: ProtectedTypedValueRegistryHistory, schema_id: str, expected_publication: VerifiedTypedValuePublication | None = None) -> ResolvedTypedValueRegistryHistoryEntry:
    candidates = []
    for publication in history.publications:
        if expected_publication is not None and publication != expected_publication:
            continue
        try:
            entry = publication.compiled_registry.entry_for(schema_id, "1")
        except KeyError:
            continue
        binding = CanonicalTypedValueProfileBinding(entry.profile.profile_id, int(entry.profile.profile_version), entry.profile.profile_digest, entry.schema_id, int(entry.schema_version), entry.binding_digest)
        candidates.append(history.resolve(binding, route=TypedValueRegistryReadRoute.INTERNAL_REPLAY))
    if len(candidates) != 1:
        raise ObservationActivationRuntimeError("registered observation activation schema is absent or ambiguous")
    return candidates[0]


def _binding(selected: ResolvedTypedValueRegistryHistoryEntry) -> CanonicalTypedValueProfileBinding:
    return CanonicalTypedValueProfileBinding(
        selected.entry.profile.profile_id, int(selected.entry.profile.profile_version),
        selected.entry.profile.profile_digest, selected.entry.schema_id,
        int(selected.entry.schema_version), selected.entry.binding_digest,
    )


def _digest_policy(selected: ResolvedTypedValueRegistryHistoryEntry) -> SelfDigestPolicy | OrdinaryPolicy | SignatureOnlyPolicy:
    policies = [role.policy for role in selected.publication.compiled_registry.parsed_roles if isinstance(role, DigestSignatureRole) and role.schema_id == selected.entry.schema_id and role.schema_version == selected.entry.schema_version]
    if len(policies) != 1 or not isinstance(policies[0], (SelfDigestPolicy, OrdinaryPolicy, SignatureOnlyPolicy)):
        raise ObservationActivationRuntimeError("registered observation artifact integrity policy is invalid")
    return policies[0]


def _identifier_bytes(value: str) -> bytes:
    if not value:
        raise ObservationActivationRuntimeError("observation identifier is empty")
    try:
        return value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ObservationActivationRuntimeError("observation identifier is not Unicode scalar text") from exc


def _digest_ascii(value: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ObservationActivationRuntimeError("observation digest is invalid")


def _lp8(*parts: bytes) -> bytes:
    if any(len(part) >= 1 << 64 for part in parts):
        raise ObservationActivationRuntimeError("observation preimage part is too large")
    return b"".join(len(part).to_bytes(8, "big") + part for part in parts)


def _artifact_preimage(binding: CanonicalTypedValueProfileBinding, body: bytes) -> bytes:
    from memorii.core.memory_evolution.ingestion_contracts import artifact_preimage
    return artifact_preimage(binding, body)
