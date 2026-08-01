"""Fail-closed verification for externally provisioned traceability releases.

This module deliberately accepts bytes, not a convenient object graph.  Trust
anchors and recovery material arrive through a channel independent of the
release channel; no release field is ever allowed to install its own verifier.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, Protocol

from memorii.core.memory_evolution.ingestion_contracts import (
    CanonicalTypedValueError,
    CanonicalTypedValueProfileBinding,
    decode_artifact,
    decode_typed_value,
    encode_artifact,
    encode_typed_value,
)
from memorii.tools.semantic_ingestion_acceptance_watermark_store import (
    TraceabilityReleaseWatermarkStore,
    WatermarkAdvanced,
    WatermarkRejected,
    WatermarkUnavailable,
)
from memorii.tools.semantic_ingestion_traceability_registry import (
    CANONICAL_PROFILE,
    TraceabilityRegistry,
    canonical_document,
)

_LOWERCASE_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_KNOWN_SIGNER_KEY_FIELDS = frozenset(
    {
        "public_key_or_root_certificate_digest",
        "policy_signer_key_or_certificate_digest",
        "issuer_key_or_certificate_digest",
    }
)
_CTV_PROFILE = ("semantic_ingestion_typed_value", 2, "9dc8b3d01e3f78ed6a11c7668cbb576b09f48ddf107c5efe441bb8bad234fd7f")
_CTV_BODY_BINDINGS = {
    "bootstrap": (
        "TraceabilityBootstrapTrustAnchorBody.v1",
        "b3afc00594f4ba871e64a1a1d649a1d32e1b7bb77e7eb2ff14d550e897f19c77",
    ),
    "recovery": (
        "TraceabilityRecoveryTrustRootBody.v1",
        "b8e2679794f444955932cd204dee8312e6c0077346c9f5570e1c28770c09abf3",
    ),
    "recovery_policy": (
        "TraceabilityRecoveryTrustPolicyBody.v1",
        "4cf90609b1ab78610816b1316082f40f749052f33fe3ad5a2b85b65820cffd75",
    ),
    "lifecycle": (
        "TraceabilityTrustLifecycleRootBody.v1",
        "82cee87c03a941f2dc58489f9f358d18eb505bf956a72bc23b9f4f2abd0d214e",
    ),
    "lifecycle_record": (
        "TraceabilityTrustLifecycleRecordBody.v1",
        "99da1c12a9c22342a15b1e6fbd12a51f4b2b043d2db4149bc18c21ca78dd44f0",
    ),
    "release": (
        "SemanticIngestionTraceabilityReleaseBody.v1",
        "2e1ba193b6fac94c03598d7c27489f5fa69e48c5a052072124acb398adfd8ce2",
    ),
    "historical_release": (
        "SemanticIngestionTraceabilityReleaseBody.v1",
        "2e1ba193b6fac94c03598d7c27489f5fa69e48c5a052072124acb398adfd8ce2",
    ),
    "active_pointer": (
        "TraceabilityActiveReleasePointerBody.v1",
        "fd5f73aadb565cdaf53afa7aa3acb2218af5e0cac5f0dfaff7032aaa9a982d7d",
    ),
    "release_history": (
        "TraceabilityReleaseHistoryBody.v1",
        "398f87e800eba421e3e657af5c6b34e1887c5c93e7038c981d6e6ce3d38d87e3",
    ),
}


@dataclass(frozen=True)
class TraceabilityGateUnavailable:
    reason: str


@dataclass(frozen=True)
class TraceabilityGateRejected:
    reason: str


@dataclass(frozen=True)
class TraceabilityGateAuthorized:
    release_id: str
    release_digest: str
    root_bindings: dict[str, str] | None = None


TraceabilityGateResult = TraceabilityGateUnavailable | TraceabilityGateRejected | TraceabilityGateAuthorized
SignatureVerifier = Callable[[str, str, bytes, bytes], bool]


@dataclass(frozen=True)
class TraceabilityLegacyDiagnostic:
    """Historical transport observation which cannot authorize a release."""

    reason: str


def read_legacy_release_diagnostic(raw: bytes, *, name: str) -> TraceabilityLegacyDiagnostic:
    """Classify retained pre-correction bytes without parsing them as current.

    This deliberately has no verifier or watermark argument.  It is the sole
    retained compatibility surface for incomplete provenance artifacts.
    """
    try:
        artifact = decode_artifact(raw)
    except CanonicalTypedValueError:
        artifact = None
    if artifact is not None:
        return TraceabilityLegacyDiagnostic(reason="legacy_incomplete_provenance")
    try:
        _load(raw, name)
    except ValueError:
        return TraceabilityLegacyDiagnostic(reason="legacy_transport_invalid")
    return TraceabilityLegacyDiagnostic(reason="legacy_incomplete_provenance")


@dataclass(frozen=True)
class _VerifiedReleaseCandidate:
    """Private proof that the complete release generation validated."""

    release_id: str
    release_digest: str
    epoch: int
    sequence: int
    root_bindings: tuple[tuple[str, str], ...]
    active_signers: tuple[tuple[str, str, str, str, datetime, datetime | None], ...]


_ReleaseValidationResult = _VerifiedReleaseCandidate | TraceabilityGateUnavailable | TraceabilityGateRejected


@dataclass(frozen=True)
class VerifierHeldTrustMaterial:
    """Immutable verifier input authenticated outside the release channel."""

    bootstrap_anchor_bytes: bytes
    recovery_root_bytes: tuple[bytes, ...]
    verify_signature: SignatureVerifier
    recovery_policy_bytes: bytes | None = None
    # Successor roots arrive through the same independently authenticated
    # channel as genesis roots.  A lifecycle record is never a provisioning
    # mechanism.
    provisioned_successor_root_bytes: tuple[bytes, ...] = ()
    # Historical lifecycle views are independently provisioned composition
    # material.  A successor may name one of these roots but never supply it.
    prior_verified_lifecycle_root_bytes: tuple[bytes, ...] = ()


@dataclass(frozen=True)
class IndependentGenerationVerificationResult:
    """Opaque output returned only by a composition-owned isolated verifier."""

    executor_id: str
    implementation_sha256: str
    structural_body_bytes: bytes
    structural_envelope_bytes: bytes
    structural_spool_bytes: bytes


class IndependentGenerationVerifier(Protocol):
    """Composition boundary for independently reconstructing structural bytes."""

    def verify(
        self,
        *,
        design_bytes: bytes,
        registry_bytes: bytes,
        ledger_bytes: bytes,
        expected_body_bytes: bytes,
        expected_envelope_bytes: bytes,
    ) -> IndependentGenerationVerificationResult: ...


@dataclass(frozen=True)
class AcceptanceTrustStore:
    """Composition-owned trust channel; it is deliberately not request data."""

    material: VerifierHeldTrustMaterial
    watermark_store: TraceabilityReleaseWatermarkStore
    expected_release_roots: dict[str, str]
    publication_store: TraceabilityReleasePublicationStore | None = None
    independent_generation_verifier: IndependentGenerationVerifier | None = None
    # Compatibility is explicit test composition only. Production registered
    # approval must provide the all-or-none publication store.
    allow_test_watermark_fallback: bool = False
    allow_test_file_fence: bool = False
    anti_rollback_resolver: AntiRollbackTrustResolver | None = None
    verified_anti_rollback_registration: VerifiedAntiRollbackRegistration | None = None


@dataclass(frozen=True)
class VerifiedAntiRollbackRegistration:
    """Signed canonical registration revalidated at every production commit."""

    payload: bytes
    signature: bytes


class AntiRollbackTrustResolver:
    """Verifier-held, immutable issuer for registered anti-rollback backends."""

    def __init__(
        self,
        *,
        allowed_registrations: frozenset[tuple[str, str, str]],
        verify_registration_signature: Callable[[bytes, bytes], bool],
    ) -> None:
        self._allowed = frozenset(allowed_registrations)
        self._verify = verify_registration_signature

    def register(
        self,
        *,
        signed_artifact: bytes,
    ) -> VerifiedAntiRollbackRegistration:
        try:
            artifact = json.loads(signed_artifact.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("anti_rollback_backend_registration_invalid") from exc
        if not isinstance(artifact, dict) or set(artifact) != {"payload", "signature"}:
            raise ValueError("anti_rollback_backend_registration_invalid")
        payload_value, signature_hex = artifact["payload"], artifact["signature"]
        if not isinstance(payload_value, dict) or not isinstance(signature_hex, str):
            raise ValueError("anti_rollback_backend_registration_invalid")
        payload = canonical_document(payload_value)
        try:
            signature = bytes.fromhex(signature_hex)
        except ValueError as exc:
            raise ValueError("anti_rollback_backend_registration_invalid") from exc
        token = VerifiedAntiRollbackRegistration(payload, signature)
        if not self.verify(token, None, None):
            raise ValueError("anti_rollback_backend_registration_invalid")
        return token

    def verify(
        self,
        token: VerifiedAntiRollbackRegistration,
        publication_store: TraceabilityReleasePublicationStore | None,
        backend: object | None,
    ) -> bool:
        from memorii.tools.semantic_ingestion_release_persistence import FileMonotonicFenceStore

        try:
            value = json.loads(token.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False
        if not isinstance(value, dict) or set(value) != {
            "backend_id", "backend_kind", "failure_domain", "publication_store_id"
        } or canonical_document(value) != token.payload:
            return False
        backend_id, backend_kind = value["backend_id"], value["backend_kind"]
        failure_domain, store_id = value["failure_domain"], value["publication_store_id"]
        registration = (backend_id, backend_kind, failure_domain)
        if not (
            isinstance(backend_id, str) and isinstance(backend_kind, str)
            and isinstance(failure_domain, str) and isinstance(store_id, str)
        ):
            return False
        if (
            registration not in self._allowed
            or backend_kind in {"file", "local", "filesystem", "proxy"}
            or not self._verify(token.payload, token.signature)
        ):
            return False
        if publication_store is None and backend is None:
            return True
        return bool(
            publication_store is not None and backend is not None
            and not isinstance(backend, FileMonotonicFenceStore)
            and backend is publication_store.anti_rollback_backend_identity()
            and backend_id == getattr(backend, "durable_backend_id", lambda: None)()
            and store_id == publication_store.publication_store_id()
            and failure_domain != publication_store.publication_recovery_domain()
        )


def validate_anti_rollback_backend_registration(**kwargs: object) -> None:
    """Deprecated: caller-supplied validation inputs cannot issue trust tokens."""
    raise RuntimeError("use composition-owned AntiRollbackTrustResolver")


class TraceabilityReleasePublicationStore(Protocol):
    """Composition-owned all-or-none publisher for a validated traceability release.

    Candidate bytes are validated before this boundary. The store may publish
    only these exact immutable bytes while advancing its current index/fence.
    """

    def anti_rollback_backend_identity(self) -> object: ...

    def publication_recovery_domain(self) -> str: ...

    def publication_store_id(self) -> str: ...

    def compare_and_publish(
        self,
        *,
        epoch: int,
        sequence: int,
        release_digest: str,
        release_artifact: bytes,
        release_history_artifact: bytes,
        active_pointer_artifact: bytes,
        pointer_history_artifact: bytes,
    ) -> TraceabilityGateResult: ...

    def compare_fence_and_publish(
        self,
        *,
        watermark_store: TraceabilityReleaseWatermarkStore,
        epoch: int,
        sequence: int,
        release_digest: str,
        release_artifact: bytes,
        release_history_artifact: bytes,
        active_pointer_artifact: bytes,
        pointer_history_artifact: bytes,
    ) -> TraceabilityGateResult: ...


@dataclass(frozen=True)
class CoverageApproval:
    heading_path_hash: str
    approved_requirement_ids: tuple[str, ...]
    applicable_rule_digests: tuple[str, ...]
    design_document_digest: str
    registry_source_identity: str
    structural_manifest_digest: str
    reviewer_id: str
    issuance_purpose: str
    issued_at: datetime
    trust_snapshot_digest: str
    expires_at: datetime | None
    signature_profile_id: str
    reviewer_key_digest: str
    signature: bytes
    approval_digest: str

    def body(self) -> dict[str, Any]:
        return {
            "heading_path_hash": self.heading_path_hash,
            "approved_requirement_ids": list(self.approved_requirement_ids),
            "applicable_rule_digests": list(self.applicable_rule_digests),
            "design_document_digest": self.design_document_digest,
            "registry_source_identity": self.registry_source_identity,
            "structural_manifest_digest": self.structural_manifest_digest,
            "reviewer_id": self.reviewer_id,
            "issuance_purpose": self.issuance_purpose,
            "issued_at": self.issued_at.isoformat(),
            "trust_snapshot_digest": self.trust_snapshot_digest,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "signature_profile_id": self.signature_profile_id,
            "reviewer_key_digest": self.reviewer_key_digest,
        }


def _digest(domain: bytes, body: bytes) -> str:
    return sha256(domain + b"\0" + body).hexdigest()


def _load(raw: bytes, name: str) -> dict[str, Any]:
    """Load canonical JSON or a self-authenticating CTV-v2 body envelope."""
    # CTV-v2 outer envelopes are themselves typed maps, so their top-level
    # JSON keys are `$type`/`entries`, not the retired wrapper's four fields.
    try:
        artifact = decode_artifact(raw)
    except CanonicalTypedValueError:
        artifact = None
    if artifact is not None:
        try:
            if name == "provisioned_successor_root":
                allowed = {
                    CanonicalTypedValueProfileBinding(*_CTV_PROFILE, schema_id, 1, binding_digest)
                    for schema_id, binding_digest in (
                        _CTV_BODY_BINDINGS["bootstrap"],
                        _CTV_BODY_BINDINGS["recovery"],
                    )
                }
                if artifact.binding not in allowed:
                    raise ValueError(f"{name}_ctv_binding_mismatch")
            else:
                schema_id, binding_digest = _CTV_BODY_BINDINGS[name]
                expected_binding = CanonicalTypedValueProfileBinding(
                    *_CTV_PROFILE, schema_id, 1, binding_digest
                )
                if artifact.binding != expected_binding:
                    raise ValueError(f"{name}_ctv_binding_mismatch")
            decoded = decode_typed_value(artifact.canonical_value_bytes)
            if encode_artifact(decoded, artifact.binding) != artifact:
                raise ValueError(f"{name}_ctv_reencode_mismatch")
        except (CanonicalTypedValueError, ValueError) as exc:
            raise ValueError(f"{name}_ctv_invalid") from exc
        if not isinstance(decoded, dict):
            raise ValueError(f"{name}_ctv_body_invalid")
        return decoded
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{name}_invalid_json") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{name}_not_canonical")
    if value.get("$type") == "map":
        raise ValueError(f"{name}_ctv_invalid")
    # A retired look-alike wrapper is not a raw body and must never use this
    # legacy JSON branch; diagnostic tooling has an explicit reader instead.
    if set(value) == {"binding", "canonical_value_bytes", "canonical_value_digest", "artifact_digest"}:
        raise ValueError(f"{name}_ctv_invalid")
    if canonical_document(value) != raw:
        raise ValueError(f"{name}_not_canonical")
    return value


def _canonical_loaded_bytes(raw: bytes, name: str) -> bytes:
    return canonical_document(_load(raw, name))


def _time(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{name}_missing_time")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name}_invalid_time") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{name}_naive_time")
    return parsed.astimezone(UTC)


def _body(value: dict[str, Any], *excluded: str) -> bytes:
    if any(field not in value for field in excluded):
        raise ValueError("signature_or_digest_missing")
    return canonical_document({key: item for key, item in value.items() if key not in excluded})


def _signature(value: object, *, profile: str, key: str, payload: bytes, verifier: SignatureVerifier) -> None:
    if not isinstance(value, str):
        raise ValueError("signature_binding_invalid")
    try:
        raw = bytes.fromhex(value)
    except ValueError as exc:
        raise ValueError("signature_not_hex") from exc
    if not verifier(profile, key, payload, raw):
        raise ValueError("signature_invalid")


def _enforce_signer_key_field(value: dict[str, Any], *, expected: str | None) -> None:
    """Reject cross-purpose signer aliases without claiming a closed schema."""
    unexpected = _KNOWN_SIGNER_KEY_FIELDS.intersection(value)
    if expected is not None:
        unexpected = unexpected.difference({expected})
    if unexpected:
        raise ValueError("signature_key_field_ambiguous")


def _verify_signed(
    value: dict[str, Any],
    *,
    purpose: str,
    digest_field: str,
    signer_key_field: str,
    domain: bytes,
    verifier: SignatureVerifier,
) -> str:
    if value.get("issuance_purpose") != purpose or value.get("canonical_profile_id") != CANONICAL_PROFILE:
        raise ValueError("wrong_purpose_or_profile")
    _enforce_signer_key_field(value, expected=signer_key_field)
    digest = _digest(domain, _body(value, "signature", digest_field))
    if value.get(digest_field) != digest:
        raise ValueError("content_digest_mismatch")
    profile = value.get("signature_profile_id")
    key = value.get(signer_key_field)
    if not isinstance(profile, str) or not isinstance(key, str):
        raise ValueError("signature_binding_invalid")
    _signature(value.get("signature"), profile=profile, key=key, payload=digest.encode("ascii"), verifier=verifier)
    return digest


def verify_coverage_root(
    *,
    approvals: tuple[CoverageApproval, ...],
    heading_requirements: dict[str, tuple[str, ...]],
    heading_rule_digests: dict[str, tuple[str, ...]],
    design_document_digest: str,
    registry_source_identity: str,
    structural_manifest_digest: str,
    trusted_reviewer_keys: dict[str, tuple[str, str]],
    verifier: SignatureVerifier,
    now: datetime,
) -> str:
    if now.tzinfo is None or set(heading_requirements) != set(heading_rule_digests):
        raise ValueError("coverage_inputs_invalid")
    by_heading = {approval.heading_path_hash: approval for approval in approvals}
    if len(by_heading) != len(approvals) or set(by_heading) != set(heading_requirements):
        raise ValueError("coverage_approval_set_is_not_exact")
    bodies: list[dict[str, Any]] = []
    for heading, approval in sorted(by_heading.items()):
        if (
            approval.issuance_purpose != "semantic_ingestion_traceability_coverage"
            or tuple(sorted(approval.approved_requirement_ids)) != tuple(sorted(heading_requirements[heading]))
            or tuple(sorted(approval.applicable_rule_digests)) != tuple(sorted(heading_rule_digests[heading]))
        ):
            raise ValueError("coverage_binding_invalid")
        if (
            approval.design_document_digest,
            approval.registry_source_identity,
            approval.structural_manifest_digest,
        ) != (design_document_digest, registry_source_identity, structural_manifest_digest) or (
            approval.expires_at is not None and approval.expires_at < now
        ):
            raise ValueError("coverage_root_binding_invalid")
        if trusted_reviewer_keys.get(approval.reviewer_id) != (
            approval.signature_profile_id,
            approval.reviewer_key_digest,
        ):
            raise ValueError("coverage_reviewer_not_lifecycle_eligible")
        digest = _digest(b"memorii:sia-traceability-coverage-approval:v1", canonical_document(approval.body()))
        if digest != approval.approval_digest:
            raise ValueError("coverage_digest_invalid")
        if not verifier(
            approval.signature_profile_id, approval.reviewer_key_digest, digest.encode("ascii"), approval.signature
        ):
            raise ValueError("coverage_signature_invalid")
        bodies.append({**approval.body(), "approval_digest": digest, "signature": approval.signature.hex()})
    return _digest(
        b"memorii:sia-traceability-coverage-root:v1",
        canonical_document({"structural_manifest_digest": structural_manifest_digest, "approvals": bodies}),
    )


def _anchor_key(anchor: dict[str, Any]) -> tuple[str, str]:
    profile, key = anchor.get("signature_profile_id"), anchor.get("public_key_or_root_certificate_digest")
    if not isinstance(profile, str) or not isinstance(key, str):
        raise ValueError("anchor_key_invalid")
    return profile, key


def _root_coordinate(root: dict[str, Any]) -> tuple[str, str, str, str, str]:
    """Return the independently authenticated root coordinate and signer."""
    if "anchor_id" in root:
        root_id, kind = root.get("anchor_id"), "bootstrap_anchor"
        digest = _typed_digest(b"memorii:sia-traceability-bootstrap-anchor:v1", root)
    else:
        root_id, kind = root.get("recovery_root_id"), "recovery_root"
        digest = _typed_digest(b"memorii:sia-traceability-recovery-root:v1", root)
    profile, key = _anchor_key(root)
    if not isinstance(root_id, str) or not isinstance(digest, str):
        raise ValueError("provisioned_root_coordinate_invalid")
    return kind, root_id, digest, profile, key


def _root_window(root: dict[str, Any]) -> tuple[datetime, datetime | None]:
    effective = (
        _time(root["effective_at"], "provisioned_root") if "effective_at" in root else datetime.min.replace(tzinfo=UTC)
    )
    expires = _time(root["expires_at"], "provisioned_root") if root.get("expires_at") is not None else None
    if expires is not None and expires < effective:
        raise ValueError("provisioned_root_time_window_invalid")
    return effective, expires


_PROVISIONED_GENESIS_FIELDS = frozenset(
    {
        "source_kind",
        "authority_id",
        "provisioned_channel_id",
        "provisioned_authorization_artifact_digest",
        "provisioned_signature_purpose",
        "provisioned_signature_profile_id",
        "provisioned_key_or_certificate_digest",
        "eligible_not_before",
        "eligible_not_after",
    }
)
_PROVISIONED_SUCCESSOR_FIELDS = frozenset(
    {
        "source_kind",
        "authority_id",
        "trust_lifecycle_root_digest",
        "lifecycle_record_digest",
        "eligible_not_before",
        "eligible_not_after",
    }
)
_POLICY_GENESIS_FIELDS = frozenset(
    {
        "source_kind",
        "signature_purpose",
        "authority_id",
        "provisioned_channel_id",
        "bootstrap_anchor_digest",
        "issuer_id",
        "key_or_certificate_digest",
        "signature_profile_id",
        "eligible_not_before",
        "eligible_not_after",
    }
)
_SIGNER_COORDINATE_FIELDS = frozenset(
    {
        "source_kind",
        "signature_purpose",
        "issuer_id",
        "key_or_certificate_digest",
        "signature_profile_id",
        "trust_lifecycle_root_digest",
        "lifecycle_record_digest",
        "eligible_not_before",
        "eligible_not_after",
    }
)


def _exact_keys(value: object, fields: frozenset[str], reason: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(reason)
    return value


def _provenance_interval(value: dict[str, Any], reason: str) -> tuple[datetime, datetime | None]:
    start = _time(value.get("eligible_not_before"), reason)
    end = _time(value["eligible_not_after"], reason) if value.get("eligible_not_after") is not None else None
    if end is not None and end <= start:
        raise ValueError(f"{reason}_interval_invalid")
    return start, end


def _validate_provisioned_root_provenance(
    root: dict[str, Any], *, authority_id: str, lifecycle: dict[str, Any] | None = None,
    prior_lifecycles: dict[str, dict[str, Any]] | None = None,
) -> None:
    """Validate the closed BA/RR union before any signature operation.

    The independently provisioned document is held by the verifier.  This
    function therefore validates only the candidate's typed declaration; the
    caller compares its bytes to that configured document before invoking it.
    """
    bootstrap_fields = {
        "anchor_id", "issuance_purpose", "target_purpose", "target_authority_id",
        "authorized_signature_purposes", "canonical_profile_binding", "signature_profile_id",
        "public_key_or_root_certificate_digest", "provisioned_channel_id", "rotation_sequence",
        "predecessor_anchor_id", "predecessor_anchor_digest", "effective_at", "recorded_at",
        "expires_at", "provenance",
    }
    recovery_fields = {
        "recovery_root_id", "issuance_purpose", "target_authority_id", "authorized_signature_purposes",
        "canonical_profile_binding", "signature_profile_id", "public_key_or_root_certificate_digest",
        "provisioned_channel_id", "rotation_sequence", "predecessor_recovery_root_id",
        "predecessor_recovery_root_digest", "effective_at", "recorded_at", "expires_at", "provenance",
    }
    is_bootstrap = "anchor_id" in root
    if set(root) != (bootstrap_fields if is_bootstrap else recovery_fields):
        raise ValueError("provisioned_root_fields_invalid")
    if root.get("canonical_profile_binding") != _binding_for("bootstrap" if is_bootstrap else "recovery"):
        raise ValueError("provisioned_root_binding_invalid")
    expected_issuance = (
        "semantic_ingestion_traceability_release_root"
        if is_bootstrap
        else "semantic_ingestion_traceability_recovery_root"
    )
    expected_purposes = (
        {
            "semantic_ingestion_traceability_lifecycle_record",
            "semantic_ingestion_traceability_lifecycle_root",
            "semantic_ingestion_traceability_recovery_policy",
            "semantic_ingestion_traceability_release",
            "semantic_ingestion_traceability_release_history",
            "semantic_ingestion_traceability_active_release_pointer",
        }
        if is_bootstrap
        else {"semantic_ingestion_traceability_recovery_policy"}
    )
    root_id = root.get("anchor_id" if is_bootstrap else "recovery_root_id")
    purposes = root.get("authorized_signature_purposes")
    if (
        root.get("issuance_purpose") != expected_issuance
        or not isinstance(root_id, str)
        or not root_id
        or (is_bootstrap and root.get("target_purpose") != "semantic_ingestion_traceability_release")
        or not isinstance(purposes, list)
        or set(purposes) != expected_purposes
        or len(purposes) != len(expected_purposes)
        or not isinstance(root.get("signature_profile_id"), str)
        or not root["signature_profile_id"]
        or not isinstance(root.get("public_key_or_root_certificate_digest"), str)
        or _LOWERCASE_SHA256.fullmatch(root["public_key_or_root_certificate_digest"]) is None
    ):
        raise ValueError("provisioned_root_semantics_invalid")
    effective = _time(root.get("effective_at"), "provisioned_root")
    recorded = _time(root.get("recorded_at"), "provisioned_root")
    if effective > recorded:
        raise ValueError("provisioned_root_time_invalid")
    provenance = root.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError("provisioned_root_provenance_missing")
    sequence = root.get("rotation_sequence")
    if type(sequence) is not int or sequence < 1:
        raise ValueError("provisioned_root_rotation_sequence_invalid")
    predecessor_id = "predecessor_anchor_id" if is_bootstrap else "predecessor_recovery_root_id"
    predecessor_digest = "predecessor_anchor_digest" if is_bootstrap else "predecessor_recovery_root_digest"
    if root.get("target_authority_id") != authority_id:
        raise ValueError("provisioned_root_authority_invalid")
    source_kind = provenance.get("source_kind")
    if source_kind == "independently_provisioned_genesis":
        provenance = _exact_keys(provenance, _PROVISIONED_GENESIS_FIELDS, "provisioned_genesis_fields_invalid")
        if sequence != 1 or root.get(predecessor_id) is not None or root.get(predecessor_digest) is not None:
            raise ValueError("provisioned_genesis_predecessor_invalid")
        if provenance.get("authority_id") != authority_id or provenance.get("provisioned_channel_id") != root.get("provisioned_channel_id"):
            raise ValueError("provisioned_genesis_authority_or_channel_invalid")
        if provenance.get("provisioned_signature_profile_id") != root.get("signature_profile_id") or provenance.get("provisioned_key_or_certificate_digest") != root.get("public_key_or_root_certificate_digest"):
            raise ValueError("provisioned_genesis_signature_binding_invalid")
        if provenance.get("provisioned_signature_purpose") != root.get("issuance_purpose"):
            raise ValueError("provisioned_genesis_purpose_invalid")
        digest = provenance.get("provisioned_authorization_artifact_digest")
        if not isinstance(digest, str) or _LOWERCASE_SHA256.fullmatch(digest) is None:
            raise ValueError("provisioned_genesis_authorization_digest_invalid")
        _provenance_interval(provenance, "provisioned_genesis")
        return
    if source_kind != "prior_verified_lifecycle_root":
        raise ValueError("provisioned_root_provenance_kind_invalid")
    provenance = _exact_keys(provenance, _PROVISIONED_SUCCESSOR_FIELDS, "provisioned_successor_fields_invalid")
    if sequence <= 1 or not isinstance(root.get(predecessor_id), str) or not isinstance(root.get(predecessor_digest), str):
        raise ValueError("provisioned_successor_predecessor_invalid")
    if provenance.get("authority_id") != authority_id:
        raise ValueError("provisioned_successor_authority_invalid")
    lifecycle_digest = provenance.get("trust_lifecycle_root_digest")
    referenced_lifecycle = (
        lifecycle if lifecycle is not None and lifecycle.get("lifecycle_root_digest") == lifecycle_digest
        else (prior_lifecycles or {}).get(lifecycle_digest) if isinstance(lifecycle_digest, str) else None
    )
    if referenced_lifecycle is None:
        raise ValueError("provisioned_successor_lifecycle_root_invalid")
    if referenced_lifecycle.get("authority_id") != authority_id:
        raise ValueError("provisioned_successor_lifecycle_authority_invalid")
    records = referenced_lifecycle.get("records")
    record = next(
        (
            item
            for item in records
            if isinstance(item, dict) and item.get("record_digest") == provenance.get("lifecycle_record_digest")
        ),
        None,
    ) if isinstance(records, list) else None
    if record is None:
        raise ValueError("provisioned_successor_lifecycle_record_invalid")
    predecessor_coordinate = (
        root.get(predecessor_id),
        root.get(predecessor_digest),
    )
    record_binds_predecessor = predecessor_coordinate in {
        (record.get("target_id"), record.get("target_digest")),
        (
            record.get("replacement_target_id"),
            record.get("replacement_target_digest"),
        ),
    }
    if (
        type(record.get("sequence")) is not int
        or not record_binds_predecessor
    ):
        raise ValueError("provisioned_successor_lifecycle_binding_invalid")
    _provenance_interval(provenance, "provisioned_successor")


def _is_independently_provisioned_genesis_bootstrap(root: dict[str, Any]) -> bool:
    """Identify the one bootstrap variant that may exist before lifecycle state.

    A recovery root can be independently provisioned before it is activated.
    A second bootstrap anchor cannot: after lifecycle activation it must carry
    successor provenance tied to an already verified lifecycle root.
    """
    provenance = root.get("provenance")
    return (
        "anchor_id" in root
        and isinstance(provenance, dict)
        and provenance.get("source_kind") == "independently_provisioned_genesis"
    )


def _validate_recovery_policy_provenance(
    policy: dict[str, Any], *, authority_id: str, bootstrap: dict[str, Any], lifecycle: dict[str, Any] | None = None
) -> None:
    provenance = policy.get("signer_provenance")
    if not isinstance(provenance, dict):
        raise ValueError("recovery_policy_provenance_missing")
    sequence = policy.get("sequence")
    predecessor = policy.get("predecessor_policy_digest")
    if type(sequence) is not int or sequence < 1:
        raise ValueError("recovery_policy_sequence_invalid")
    if provenance.get("source_kind") == "independently_provisioned_bootstrap_anchor":
        provenance = _exact_keys(provenance, _POLICY_GENESIS_FIELDS, "recovery_policy_genesis_fields_invalid")
        if sequence != 1 or predecessor is not None:
            raise ValueError("recovery_policy_genesis_predecessor_invalid")
        if (
            provenance.get("signature_purpose") != "semantic_ingestion_traceability_recovery_policy"
            or provenance.get("authority_id") != authority_id
            or provenance.get("provisioned_channel_id") != bootstrap.get("provisioned_channel_id")
            or provenance.get("bootstrap_anchor_digest") != _root_coordinate(bootstrap)[2]
            or provenance.get("issuer_id") != bootstrap.get("anchor_id")
            or provenance.get("key_or_certificate_digest") != bootstrap.get("public_key_or_root_certificate_digest")
            or provenance.get("signature_profile_id") != bootstrap.get("signature_profile_id")
        ):
            raise ValueError("recovery_policy_genesis_binding_invalid")
        _provenance_interval(provenance, "recovery_policy_genesis")
        return
    provenance = _exact_keys(provenance, _SIGNER_COORDINATE_FIELDS, "recovery_policy_successor_fields_invalid")
    if sequence <= 1 or not isinstance(predecessor, str):
        raise ValueError("recovery_policy_successor_predecessor_invalid")
    if provenance.get("signature_purpose") != "semantic_ingestion_traceability_recovery_policy":
        raise ValueError("recovery_policy_successor_purpose_invalid")
    if lifecycle is None or provenance.get("trust_lifecycle_root_digest") != lifecycle.get("lifecycle_root_digest"):
        raise ValueError("recovery_policy_successor_lifecycle_root_invalid")
    records = lifecycle.get("records")
    if not isinstance(records, list) or not any(record.get("record_digest") == provenance.get("lifecycle_record_digest") for record in records if isinstance(record, dict)):
        raise ValueError("recovery_policy_successor_lifecycle_record_invalid")
    _provenance_interval(provenance, "recovery_policy_successor")


def _typed_digest(domain: bytes, body: dict[str, Any]) -> str:
    """CGS typed-body digest; no JSON projection may replace a CTV preimage."""
    return sha256(domain + b"\0" + encode_typed_value(body)).hexdigest()


def _binding_for(kind: str) -> dict[str, object]:
    """Return the one frozen CTV binding accepted for a current body."""
    schema_id, binding_digest = _CTV_BODY_BINDINGS[kind]
    return CanonicalTypedValueProfileBinding(
        *_CTV_PROFILE, schema_id, 1, binding_digest
    ).as_value()


def _signer_coordinate(
    value: object,
    *,
    purpose: str,
    lifecycle_root_digest: str,
    active_signers: dict[tuple[str, str], tuple[str, str, datetime, datetime | None]],
    when: datetime,
    verifier: SignatureVerifier,
    signature: object,
    payload: bytes,
) -> None:
    """Validate the closed RP coordinate and its verifier-held lifecycle link."""
    signer = _exact_keys(value, _SIGNER_COORDINATE_FIELDS, "signer_coordinate_fields_invalid")
    if (
        signer.get("source_kind") != "prior_verified_lifecycle_root"
        or signer.get("signature_purpose") != purpose
        or signer.get("trust_lifecycle_root_digest") != lifecycle_root_digest
    ):
        raise ValueError("signer_coordinate_lifecycle_binding_invalid")
    profile, key, issuer = (
        signer.get("signature_profile_id"),
        signer.get("key_or_certificate_digest"),
        signer.get("issuer_id"),
    )
    if not isinstance(profile, str) or not isinstance(key, str) or not isinstance(issuer, str):
        raise ValueError("signer_coordinate_binding_invalid")
    interval = _provenance_interval(signer, "signer_coordinate")
    matches = [
        interval_value
        for (signer_id, _), interval_value in active_signers.items()
        if signer_id == issuer and interval_value[:2] == (profile, key)
    ]
    if not any(_interval_contains(candidate, when) for candidate in matches):
        raise ValueError("signer_coordinate_not_lifecycle_eligible")
    if not _interval_contains((profile, key, *interval), when):
        raise ValueError("signer_coordinate_interval_ineligible")
    _signature(signature, profile=profile, key=key, payload=payload, verifier=verifier)


def _verify_corrected_recovery_policy(
    policy: dict[str, Any], *, authority_id: str, bootstrap: dict[str, Any], lifecycle: dict[str, Any], verifier: SignatureVerifier
) -> str:
    required = {
        "policy_id", "issuance_purpose", "target_authority_id", "bootstrap_anchor_id",
        "bootstrap_anchor_digest", "eligible_recovery_root_digests", "minimum_distinct_signatures",
        "signer_separation_rule_digest", "canonical_profile_binding", "effective_at", "recorded_at",
        "sequence", "predecessor_policy_digest", "expires_at", "signer_provenance",
        "signature", "recovery_policy_digest",
    }
    if set(policy) != required:
        raise ValueError("recovery_policy_fields_invalid")
    if policy.get("issuance_purpose") != "semantic_ingestion_traceability_recovery_policy" or policy.get("target_authority_id") != authority_id:
        raise ValueError("recovery_policy_purpose_or_authority_invalid")
    _validate_recovery_policy_provenance(policy, authority_id=authority_id, bootstrap=bootstrap, lifecycle=lifecycle)
    body = {key: value for key, value in policy.items() if key not in {"signature", "recovery_policy_digest"}}
    digest = _typed_digest(b"memorii:sia-traceability-recovery-policy:v1", body)
    if policy.get("recovery_policy_digest") != digest:
        raise ValueError("recovery_policy_digest_invalid")
    binding = policy.get("canonical_profile_binding")
    provenance = policy["signer_provenance"]
    if not isinstance(binding, dict) or not isinstance(provenance, dict):
        raise ValueError("recovery_policy_signature_binding_invalid")
    profile = provenance.get("signature_profile_id")
    key = provenance.get("key_or_certificate_digest")
    if not isinstance(profile, str) or not isinstance(key, str):
        raise ValueError("recovery_policy_signature_binding_invalid")
    if provenance.get("source_kind") == "prior_verified_lifecycle_root" and "signer_coordinates" in lifecycle:
        _, terminal_digest, authorized = _current_lifecycle_terminal_authorizations(
            lifecycle, authority_id=authority_id, verifier=verifier
        )
        if provenance.get("lifecycle_record_digest") != terminal_digest:
            raise ValueError("recovery_policy_successor_lifecycle_record_invalid")
        start, end = _provenance_interval(provenance, "recovery_policy_successor")
        if (provenance.get("issuer_id"), profile, key, start, end) not in authorized:
            raise ValueError("recovery_policy_successor_not_final_action_authorized")
    preimage = encode_typed_value(
        {
            "issuance_purpose": "semantic_ingestion_traceability_recovery_policy",
            "body_binding": binding,
            "recovery_policy_digest": digest,
            "signer_provenance": provenance,
        }
    )
    _signature(policy.get("signature"), profile=profile, key=key, payload=preimage, verifier=verifier)
    return digest


def _verify_current_lifecycle_signature(
    signature: object, *, profile: str, key: str, payload: bytes, verifier: SignatureVerifier
) -> None:
    if not isinstance(signature, bytes) or not verifier(profile, key, payload, signature):
        raise ValueError("lifecycle_signature_invalid")


def _validate_current_lifecycle_genesis(
    root: dict[str, Any], *, authority_id: str, bootstrap: dict[str, Any], verifier: SignatureVerifier
) -> tuple[str, dict[tuple[str, str], tuple[str, str, datetime, datetime | None]]]:
    """Validate the closed current CTV lifecycle-root/record envelope.

    This deliberately has no flat-digest or flat-signer fallback: both record
    and root signatures cover their registered typed preimages.
    """
    root_body_keys = {
        "authority_id", "issuance_purpose", "canonical_profile_binding",
        "bootstrap_anchor_history_digest", "recovery_root_history_digest",
        "recovery_policy_history_digest", "records",
    }
    root_keys = root_body_keys | {"signer_coordinates", "signatures", "lifecycle_root_digest"}
    if set(root) != root_keys or root.get("authority_id") != authority_id or root.get("issuance_purpose") != "semantic_ingestion_traceability_lifecycle_root" or root.get("canonical_profile_binding") != _binding_for("lifecycle"):
        raise ValueError("lifecycle_root_invalid")
    records = root.get("records")
    coordinates = root.get("signer_coordinates")
    signatures = root.get("signatures")
    if not isinstance(records, list) or len(records) != 1 or not isinstance(coordinates, list) or len(coordinates) != 1 or not isinstance(signatures, list) or len(signatures) != 1:
        raise ValueError("lifecycle_root_cardinality_invalid")
    record = records[0]
    if not isinstance(record, dict):
        raise ValueError("lifecycle_record_invalid")
    record_body_keys = {
        "record_id", "issuance_purpose", "target_kind", "target_id", "target_digest", "action",
        "replacement_target_id", "replacement_target_digest", "canonical_profile_binding", "effective_at",
        "recorded_at", "sequence", "predecessor_record_digest", "recovery_policy_digest", "signer_bindings",
    }
    if set(record) != record_body_keys | {"signatures", "record_digest"} or record.get("issuance_purpose") != "semantic_ingestion_traceability_lifecycle_record" or record.get("canonical_profile_binding") != _binding_for("lifecycle_record") or record.get("sequence") != 1 or record.get("predecessor_record_digest") is not None or record.get("action") != "activate":
        raise ValueError("lifecycle_record_invalid")
    record_digest = _typed_digest(b"memorii:sia-traceability-trust-lifecycle-record:v1", {key: record[key] for key in record_body_keys})
    if record.get("record_digest") != record_digest:
        raise ValueError("lifecycle_record_digest_invalid")
    bindings = record.get("signer_bindings")
    record_signatures = record.get("signatures")
    if not isinstance(bindings, list) or len(bindings) != 1 or not isinstance(record_signatures, list) or len(record_signatures) != 1:
        raise ValueError("lifecycle_signatures_invalid")
    binding = bindings[0]
    if not isinstance(binding, dict):
        raise ValueError("lifecycle_signer_binding_invalid")
    expected_binding_keys = {"signature_purpose", "signer_id", "signer_key_or_certificate_digest", "signature_profile_id", "eligibility_reference", "recovery_root_digest"}
    if set(binding) != expected_binding_keys or binding.get("signature_purpose") != "semantic_ingestion_traceability_lifecycle_record" or binding.get("recovery_root_digest") is not None:
        raise ValueError("lifecycle_signer_binding_invalid")
    ref = binding.get("eligibility_reference")
    expected_ref_keys = {"source_kind", "authority_id", "eligibility_purpose", "source_artifact_digest", "prior_lifecycle_root_digest", "prior_lifecycle_record_digest", "prior_lifecycle_sequence", "target_id", "target_digest", "eligible_not_before", "eligible_not_after", "provisioned_channel_id"}
    bootstrap_digest = _root_coordinate(bootstrap)[2]
    if not isinstance(ref, dict) or set(ref) != expected_ref_keys or ref.get("source_kind") != "independently_provisioned_genesis" or ref.get("authority_id") != authority_id or ref.get("eligibility_purpose") != "semantic_ingestion_traceability_lifecycle_record" or ref.get("source_artifact_digest") != bootstrap_digest or ref.get("prior_lifecycle_root_digest") is not None or ref.get("prior_lifecycle_record_digest") is not None or ref.get("prior_lifecycle_sequence") != 0 or ref.get("target_id") != bootstrap.get("anchor_id") or ref.get("target_digest") != bootstrap_digest or ref.get("provisioned_channel_id") != bootstrap.get("provisioned_channel_id"):
        raise ValueError("lifecycle_genesis_eligibility_invalid")
    start, end = _provenance_interval(ref, "lifecycle_genesis")
    bootstrap_start, bootstrap_end = _root_window(bootstrap)
    record_effective = _time(record.get("effective_at"), "lifecycle_genesis")
    if (
        (start, end) != (bootstrap_start, bootstrap_end)
        or not _interval_contains(("", "", bootstrap_start, bootstrap_end), record_effective)
    ):
        raise ValueError("lifecycle_genesis_eligibility_window_invalid")
    profile, key = bootstrap.get("signature_profile_id"), bootstrap.get("public_key_or_root_certificate_digest")
    if (binding.get("signer_id"), binding.get("signature_profile_id"), binding.get("signer_key_or_certificate_digest")) != (bootstrap.get("anchor_id"), profile, key) or not isinstance(profile, str) or not isinstance(key, str):
        raise ValueError("lifecycle_genesis_signer_invalid")
    _verify_current_lifecycle_signature(record_signatures[0], profile=profile, key=key, payload=encode_typed_value({"issuance_purpose": "semantic_ingestion_traceability_lifecycle_record", "body_binding": record["canonical_profile_binding"], "record_digest": record_digest, "signer_binding": binding}), verifier=verifier)
    root_body = {key: root[key] for key in root_body_keys}
    root_digest = _typed_digest(b"memorii:sia-traceability-trust-lifecycle-root:v1", root_body)
    if root.get("lifecycle_root_digest") != root_digest:
        raise ValueError("lifecycle_root_digest_invalid")
    coordinate = coordinates[0]
    expected_coordinate_keys = {"source_kind", "authority_id", "provisioned_channel_id", "bootstrap_anchor_id", "bootstrap_anchor_digest", "issuer_id", "key_or_certificate_digest", "signature_profile_id", "signature_purpose", "eligible_not_before", "eligible_not_after"}
    if not isinstance(coordinate, dict) or set(coordinate) != expected_coordinate_keys or coordinate.get("source_kind") != "independently_provisioned_bootstrap_anchor" or coordinate.get("authority_id") != authority_id or coordinate.get("provisioned_channel_id") != bootstrap.get("provisioned_channel_id") or coordinate.get("bootstrap_anchor_id") != bootstrap.get("anchor_id") or coordinate.get("bootstrap_anchor_digest") != bootstrap_digest or coordinate.get("issuer_id") != bootstrap.get("anchor_id") or coordinate.get("key_or_certificate_digest") != key or coordinate.get("signature_profile_id") != profile or coordinate.get("signature_purpose") != "semantic_ingestion_traceability_lifecycle_root":
        raise ValueError("lifecycle_root_genesis_provenance_invalid")
    coordinate_interval = _provenance_interval(coordinate, "lifecycle_root_genesis")
    if coordinate_interval != (bootstrap_start, bootstrap_end):
        raise ValueError("lifecycle_root_genesis_interval_invalid")
    _verify_current_lifecycle_signature(signatures[0], profile=profile, key=key, payload=encode_typed_value({"issuance_purpose": "semantic_ingestion_traceability_lifecycle_root", "body_binding": root["canonical_profile_binding"], "lifecycle_root_digest": root_digest, "signer_coordinate": coordinate}), verifier=verifier)
    return root_digest, {(str(bootstrap["anchor_id"]), bootstrap_digest): (profile, key, start, end)}


def _current_lifecycle_successor_coordinate(
    value: object, *, authority_id: str, root_digest: str, terminal_record_digest: str
) -> tuple[str, str, datetime, datetime | None]:
    """Decode the one closed non-genesis root signer coordinate."""
    coordinate = _exact_keys(value, _SIGNER_COORDINATE_FIELDS, "lifecycle_root_successor_fields_invalid")
    if (
        coordinate.get("source_kind") != "prior_verified_lifecycle_root"
        or coordinate.get("signature_purpose") != "semantic_ingestion_traceability_lifecycle_root"
        or coordinate.get("trust_lifecycle_root_digest") != root_digest
        or coordinate.get("lifecycle_record_digest") != terminal_record_digest
    ):
        raise ValueError("lifecycle_root_successor_binding_invalid")
    issuer = coordinate.get("issuer_id")
    profile = coordinate.get("signature_profile_id")
    key = coordinate.get("key_or_certificate_digest")
    if not isinstance(issuer, str) or not issuer or not isinstance(profile, str) or not profile:
        raise ValueError("lifecycle_root_successor_signer_invalid")
    if not isinstance(key, str) or _LOWERCASE_SHA256.fullmatch(key) is None:
        raise ValueError("lifecycle_root_successor_signer_invalid")
    start, end = _provenance_interval(coordinate, "lifecycle_root_successor")
    return issuer, profile, start, end


def _current_lifecycle_terminal_authorizations(
    root: dict[str, Any], *, authority_id: str, verifier: SignatureVerifier
) -> tuple[int, str, set[tuple[str, str, str, datetime, datetime | None]]]:
    """Recompute the append-only record chain and its terminal action signers.

    This intentionally validates only the current CTV record grammar.  The
    separate lifecycle replay below validates signer eligibility against the
    verifier-held predecessor root, never against candidate-supplied history.
    """
    records = root.get("records")
    if not isinstance(records, list) or not records:
        raise ValueError("lifecycle_record_invalid")
    body_keys = {
        "record_id", "issuance_purpose", "target_kind", "target_id", "target_digest", "action",
        "replacement_target_id", "replacement_target_digest", "canonical_profile_binding", "effective_at",
        "recorded_at", "sequence", "predecessor_record_digest", "recovery_policy_digest", "signer_bindings",
    }
    previous_digest: str | None = None
    previous_recorded: datetime | None = None
    active_targets: set[tuple[str, str]] = set()
    terminal_authorizations: set[tuple[str, str, str, datetime, datetime | None]] = set()
    for expected_sequence, record in enumerate(records, start=1):
        if (
            not isinstance(record, dict)
            or set(record) != body_keys | {"signatures", "record_digest"}
            or record.get("issuance_purpose") != "semantic_ingestion_traceability_lifecycle_record"
            or record.get("canonical_profile_binding") != _binding_for("lifecycle_record")
            or record.get("sequence") != expected_sequence
            or record.get("predecessor_record_digest") != previous_digest
            or record.get("target_kind") not in {"bootstrap_anchor", "recovery_root"}
            or record.get("action") not in {"activate", "rotate", "revoke", "compromise", "recover"}
            or not isinstance(record.get("target_id"), str)
            or not isinstance(record.get("target_digest"), str)
        ):
            raise ValueError("lifecycle_sequence_or_target_invalid")
        if _typed_digest(b"memorii:sia-traceability-trust-lifecycle-record:v1", {key: record[key] for key in body_keys}) != record.get("record_digest"):
            raise ValueError("lifecycle_record_digest_invalid")
        effective = _time(record.get("effective_at"), "lifecycle")
        recorded = _time(record.get("recorded_at"), "lifecycle")
        if effective > recorded or (previous_recorded is not None and (effective < previous_recorded or recorded <= previous_recorded)):
            raise ValueError("lifecycle_time_rollback")
        replacement = (record.get("replacement_target_id"), record.get("replacement_target_digest"))
        if record["action"] in {"rotate", "recover"}:
            if not all(isinstance(item, str) for item in replacement):
                raise ValueError("lifecycle_replacement_missing")
        elif replacement != (None, None):
            raise ValueError("terminal_lifecycle_action_has_replacement")
        target = (record["target_id"], record["target_digest"])
        if expected_sequence == 1:
            if record["action"] != "activate" or target in active_targets:
                raise ValueError("lifecycle_genesis_transition_invalid")
        elif record["action"] == "activate":
            if target in active_targets:
                raise ValueError("lifecycle_activation_duplicate_or_stale")
        elif target not in active_targets:
            raise ValueError("lifecycle_target_not_active")
        if record["action"] in {"rotate", "recover"}:
            replacement_target = (str(replacement[0]), str(replacement[1]))
            if replacement_target == target or replacement_target in active_targets:
                raise ValueError("lifecycle_replacement_invalid")
            active_targets.remove(target)
            active_targets.add(replacement_target)
        elif record["action"] == "activate":
            active_targets.add(target)
        elif record["action"] in {"revoke", "compromise"}:
            active_targets.remove(target)
        bindings, signatures = record.get("signer_bindings"), record.get("signatures")
        if not isinstance(bindings, list) or not isinstance(signatures, list) or len(bindings) != len(signatures) or not bindings:
            raise ValueError("lifecycle_signatures_invalid")
        terminal_authorizations = set()
        for binding, signature in zip(bindings, signatures, strict=True):
            if not isinstance(binding, dict) or not isinstance(signature, bytes):
                raise ValueError("lifecycle_signer_binding_invalid")
            expected_binding = {
                "signature_purpose", "signer_id", "signer_key_or_certificate_digest", "signature_profile_id", "eligibility_reference", "recovery_root_digest",
            }
            if set(binding) != expected_binding or binding.get("signature_purpose") != "semantic_ingestion_traceability_lifecycle_record":
                raise ValueError("lifecycle_signer_binding_invalid")
            reference = binding.get("eligibility_reference")
            if not isinstance(reference, dict) or reference.get("authority_id") != authority_id:
                raise ValueError("lifecycle_signer_binding_invalid")
            start, end = _provenance_interval(reference, "lifecycle_signer")
            signer_id = binding.get("signer_id")
            profile = binding.get("signature_profile_id")
            key = binding.get("signer_key_or_certificate_digest")
            if not isinstance(signer_id, str) or not signer_id or not isinstance(profile, str) or not profile or not isinstance(key, str) or _LOWERCASE_SHA256.fullmatch(key) is None:
                raise ValueError("lifecycle_signer_binding_invalid")
            _verify_current_lifecycle_signature(signature, profile=profile, key=key, payload=encode_typed_value({"issuance_purpose": "semantic_ingestion_traceability_lifecycle_record", "body_binding": record["canonical_profile_binding"], "record_digest": record["record_digest"], "signer_binding": binding}), verifier=verifier)
            terminal_authorizations.add((signer_id, profile, key, start, end))
        previous_digest = record["record_digest"]
        previous_recorded = recorded
    if not isinstance(previous_digest, str):
        raise ValueError("lifecycle_record_digest_invalid")
    if not active_targets:
        raise ValueError("lifecycle_has_no_active_authority")
    return len(records), previous_digest, terminal_authorizations


def _validate_current_lifecycle_successor(
    root: dict[str, Any], *, authority_id: str, prior_verified_roots: dict[str, dict[str, Any]], verifier: SignatureVerifier
) -> tuple[str, dict[tuple[str, str], tuple[str, str, datetime, datetime | None]]]:
    root_body_keys = {"authority_id", "issuance_purpose", "canonical_profile_binding", "bootstrap_anchor_history_digest", "recovery_root_history_digest", "recovery_policy_history_digest", "records"}
    if set(root) != root_body_keys | {"signer_coordinates", "signatures", "lifecycle_root_digest"} or root.get("authority_id") != authority_id or root.get("issuance_purpose") != "semantic_ingestion_traceability_lifecycle_root" or root.get("canonical_profile_binding") != _binding_for("lifecycle"):
        raise ValueError("lifecycle_root_invalid")
    sequence, terminal_digest, _ = _current_lifecycle_terminal_authorizations(root, authority_id=authority_id, verifier=verifier)
    if sequence <= 1:
        raise ValueError("lifecycle_root_sequence_requires_genesis")
    root_digest = _typed_digest(b"memorii:sia-traceability-trust-lifecycle-root:v1", {key: root[key] for key in root_body_keys})
    if root.get("lifecycle_root_digest") != root_digest:
        raise ValueError("lifecycle_root_digest_invalid")
    coordinates, signatures = root.get("signer_coordinates"), root.get("signatures")
    if not isinstance(coordinates, list) or len(coordinates) != 1 or not isinstance(signatures, list) or len(signatures) != 1:
        raise ValueError("lifecycle_root_cardinality_invalid")
    coordinate = coordinates[0]
    if not isinstance(coordinate, dict):
        raise ValueError("lifecycle_root_successor_fields_invalid")
    prior_digest = coordinate.get("trust_lifecycle_root_digest")
    prior = prior_verified_roots.get(prior_digest) if isinstance(prior_digest, str) else None
    if not isinstance(prior_digest, str) or prior is None or prior is root:
        raise ValueError("lifecycle_root_successor_reference_unverified")
    prior_sequence, prior_terminal, authorized = _current_lifecycle_terminal_authorizations(prior, authority_id=authority_id, verifier=verifier)
    prior_body_keys = {"authority_id", "issuance_purpose", "canonical_profile_binding", "bootstrap_anchor_history_digest", "recovery_root_history_digest", "recovery_policy_history_digest", "records"}
    if (
        set(prior) != prior_body_keys | {"signer_coordinates", "signatures", "lifecycle_root_digest"}
        or _typed_digest(b"memorii:sia-traceability-trust-lifecycle-root:v1", {key: prior[key] for key in prior_body_keys}) != prior_digest
        or prior.get("lifecycle_root_digest") != prior_digest
    ):
        raise ValueError("lifecycle_root_successor_prior_root_digest_invalid")
    if prior.get("authority_id") != authority_id or prior_sequence != sequence - 1:
        raise ValueError("lifecycle_root_successor_reference_not_immediate")
    root_records = root.get("records")
    prior_records = prior.get("records")
    if (
        not isinstance(root_records, list)
        or not isinstance(prior_records, list)
        or root_records[:-1] != prior_records
        or not isinstance(root_records[-1], dict)
        or root_records[-1].get("predecessor_record_digest") != prior_terminal
    ):
        raise ValueError("lifecycle_root_successor_not_append_only")
    # The successor adds one record; that record's eligibility reference is a
    # typed copy of the verifier-held predecessor terminal authorization.
    terminal_record = root["records"][-1]
    if not isinstance(terminal_record, dict):
        raise ValueError("lifecycle_record_invalid")
    bindings = terminal_record.get("signer_bindings")
    if not isinstance(bindings, list) or not bindings:
        raise ValueError("lifecycle_signer_binding_invalid")
    reference_fields = {
        "source_kind", "authority_id", "eligibility_purpose", "source_artifact_digest",
        "prior_lifecycle_root_digest", "prior_lifecycle_record_digest",
        "prior_lifecycle_sequence", "target_id", "target_digest",
        "eligible_not_before", "eligible_not_after", "provisioned_channel_id",
    }
    for binding in bindings:
        if not isinstance(binding, dict):
            raise ValueError("lifecycle_signer_binding_invalid")
        reference = binding.get("eligibility_reference")
        if not isinstance(reference, dict) or set(reference) != reference_fields:
            raise ValueError("lifecycle_eligibility_reference_invalid")
        start, end = _provenance_interval(reference, "lifecycle_eligibility")
        expected = (
            reference.get("source_kind") == "prior_verified_lifecycle_root"
            and reference.get("authority_id") == authority_id
            and reference.get("eligibility_purpose") == "semantic_ingestion_traceability_lifecycle_record"
            and reference.get("source_artifact_digest") == prior_digest
            and reference.get("prior_lifecycle_root_digest") == prior_digest
            and reference.get("prior_lifecycle_record_digest") == prior_terminal
            and reference.get("prior_lifecycle_sequence") == prior_sequence
            and reference.get("target_id") == terminal_record.get("target_id")
            and reference.get("target_digest") == terminal_record.get("target_digest")
        )
        signer = (
            binding.get("signer_id"), binding.get("signature_profile_id"),
            binding.get("signer_key_or_certificate_digest"), start, end,
        )
        if not expected or (
            terminal_record.get("action") != "recover" and signer not in authorized
        ):
            raise ValueError("lifecycle_eligibility_reference_not_authorized")
    issuer, profile, start, end = _current_lifecycle_successor_coordinate(coordinate, authority_id=authority_id, root_digest=prior_digest, terminal_record_digest=prior_terminal)
    if (issuer, profile, coordinate.get("key_or_certificate_digest"), start, end) not in authorized:
        raise ValueError("lifecycle_root_successor_not_final_action_authorized")
    issued_at = _time(root["records"][-1].get("recorded_at"), "lifecycle_root")
    if not _interval_contains((profile, str(coordinate["key_or_certificate_digest"]), start, end), issued_at):
        raise ValueError("lifecycle_root_successor_issued_at_ineligible")
    preimage = encode_typed_value({"issuance_purpose": "semantic_ingestion_traceability_lifecycle_root", "body_binding": root["canonical_profile_binding"], "lifecycle_root_digest": root_digest, "signer_coordinate": coordinate})
    _verify_current_lifecycle_signature(signatures[0], profile=profile, key=str(coordinate["key_or_certificate_digest"]), payload=preimage, verifier=verifier)
    return root_digest, {(issuer, str(coordinate["key_or_certificate_digest"])): (profile, str(coordinate["key_or_certificate_digest"]), start, end)}


def _validate_lifecycle(
    root: dict[str, Any],
    *,
    authority_id: str,
    bootstrap: dict[str, Any],
    recovery_policy: dict[str, Any],
    recovery_roots: dict[str, dict[str, Any]],
    provisioned_roots: dict[tuple[str, str], dict[str, Any]],
    verifier: SignatureVerifier,
    now: datetime,
    prior_verified_roots: dict[str, dict[str, Any]] | None = None,
) -> tuple[str, str, dict[tuple[str, str], tuple[str, str, datetime, datetime | None]]]:
    if "signer_coordinates" in root:
        records = root.get("records")
        terminal_sequence = records[-1].get("sequence") if isinstance(records, list) and records and isinstance(records[-1], dict) else None
        if terminal_sequence == 1:
            root_digest, active = _validate_current_lifecycle_genesis(
                root, authority_id=authority_id, bootstrap=bootstrap, verifier=verifier
            )
        else:
            root_digest, active = _validate_current_lifecycle_successor(
                root,
                authority_id=authority_id,
                prior_verified_roots=prior_verified_roots or {},
                verifier=verifier,
            )
        policy_digest = _verify_corrected_recovery_policy(
            recovery_policy, authority_id=authority_id, bootstrap=bootstrap, lifecycle=root, verifier=verifier
        )
        return policy_digest, root_digest, active
    if root.get("authority_id") != authority_id or not isinstance(root.get("records"), list) or not root["records"]:
        raise ValueError("lifecycle_root_invalid")
    _enforce_signer_key_field(root, expected=None)
    root_body = _body(root, "lifecycle_root_digest", "signature")
    root_digest = _digest(b"memorii:sia-traceability-trust-lifecycle-root:v1", root_body)
    if root.get("lifecycle_root_digest") != root_digest:
        raise ValueError("lifecycle_root_digest_invalid")
    anchor_profile, anchor_key = _anchor_key(bootstrap)
    corrected_policy = "signer_provenance" in recovery_policy
    policy_digest = (
        _verify_corrected_recovery_policy(
            recovery_policy,
            authority_id=authority_id,
            bootstrap=bootstrap,
            lifecycle=root,
            verifier=verifier,
        )
        if corrected_policy
        else _verify_signed(
            recovery_policy,
            purpose="semantic_ingestion_traceability_recovery_policy",
            digest_field="recovery_policy_digest",
            signer_key_field="policy_signer_key_or_certificate_digest",
            domain=b"memorii:sia-traceability-recovery-policy:v1",
            verifier=verifier,
        )
    )
    policy_anchor_digest = recovery_policy.get("bootstrap_anchor_digest") if corrected_policy else recovery_policy.get("active_bootstrap_anchor_digest")
    if policy_anchor_digest != _root_coordinate(bootstrap)[2]:
        raise ValueError("recovery_policy_anchor_binding_invalid")
    eligible_roots = recovery_policy.get("eligible_recovery_root_digests")
    threshold = recovery_policy.get("minimum_distinct_signatures") if corrected_policy else recovery_policy.get("threshold")
    if (
        not isinstance(eligible_roots, list)
        or not all(isinstance(digest, str) for digest in eligible_roots)
        or len(eligible_roots) != len(set(eligible_roots))
        or type(threshold) is not int
        or threshold < 1
        or threshold > len(eligible_roots)
    ):
        raise ValueError("recovery_policy_invalid")
    if set(eligible_roots) != set(recovery_roots):
        raise ValueError("recovery_roots_not_independently_provisioned")
    bootstrap_coordinate = _root_coordinate(bootstrap)[1:3]
    if bootstrap_coordinate not in provisioned_roots:
        raise ValueError("bootstrap_not_independently_provisioned")
    initial_start, initial_expiry = _root_window(bootstrap)
    active: dict[tuple[str, str], tuple[str, str, datetime, datetime | None]] = {
        bootstrap_coordinate: (anchor_profile, anchor_key, initial_start, initial_expiry)
    }
    # Recovery roots are a purpose-separated channel: they are never ordinary
    # release/pointer/policy signers.  They can authorize only ``recover``.
    recovery_active: dict[tuple[str, str], tuple[str, str, datetime, datetime | None]] = {}
    seen_recovery_activations: set[tuple[str, str]] = set()
    for recovery in recovery_roots.values():
        kind, *_ = _root_coordinate(recovery)
        if kind != "recovery_root":
            raise ValueError("recovery_root_kind_invalid")
        _root_window(recovery)
    intervals: dict[tuple[str, str], tuple[str, str, datetime, datetime | None]] = dict(active)
    previous_digest: str | None = None
    previous_recorded: datetime | None = None
    seen_coordinates: set[tuple[int, str, str]] = set()
    root_signer: tuple[str, str] | None = None
    final_action: str | None = None
    for sequence, record in enumerate(root["records"], start=1):
        if (
            not isinstance(record, dict)
            or record.get("issuance_purpose") != "semantic_ingestion_traceability_trust_lifecycle"
            or type(record.get("sequence")) is not int
            or record["sequence"] < 1
            or record["sequence"] != sequence
            or record.get("predecessor_record_digest") != previous_digest
        ):
            raise ValueError("lifecycle_sequence_or_predecessor_invalid")
        effective, recorded = (
            _time(record.get("effective_at"), "lifecycle"),
            _time(record.get("recorded_at"), "lifecycle"),
        )
        if effective > recorded or (
            previous_recorded is not None and (recorded <= previous_recorded or effective < previous_recorded)
        ):
            raise ValueError("lifecycle_time_rollback")
        action, target_id, target_digest = record.get("action"), record.get("target_id"), record.get("target_digest")
        coordinate = (sequence, str(target_id), str(target_digest))
        if (
            action not in {"activate", "rotate", "revoke", "compromise", "recover"}
            or not isinstance(target_id, str)
            or not isinstance(target_digest, str)
            or coordinate in seen_coordinates
        ):
            raise ValueError("lifecycle_action_invalid")
        seen_coordinates.add(coordinate)
        record_digest = _digest(
            b"memorii:sia-traceability-lifecycle-record:v1", _body(record, "record_digest", "signatures")
        )
        if record.get("record_digest") != record_digest:
            raise ValueError("lifecycle_record_digest_invalid")
        bindings, signatures = record.get("signer_bindings"), record.get("signatures")
        if (
            not isinstance(bindings, list)
            or not isinstance(signatures, list)
            or len(bindings) != len(signatures)
            or not bindings
        ):
            raise ValueError("lifecycle_signatures_invalid")
        if action == "recover" and (len(bindings) != threshold or len(signatures) != threshold):
            raise ValueError("recovery_signature_threshold_invalid")
        if action != "recover" and (len(bindings) != 1 or len(signatures) != 1):
            raise ValueError("lifecycle_signatures_invalid")
        signer_ids: set[str] = set()
        signer_id_order: list[str] = []
        eligible_recovery_digests: set[str] = set()
        authorized = 0
        ordinary_record_signer: tuple[str, str] | None = None
        for binding, signature in zip(bindings, signatures, strict=True):
            if (
                not isinstance(binding, dict)
                or not isinstance(binding.get("signer_id"), str)
                or not isinstance(binding.get("signature_profile_id"), str)
                or not isinstance(binding.get("key_digest"), str)
                or binding["signer_id"] in signer_ids
            ):
                raise ValueError("lifecycle_signer_binding_invalid")
            signer_ids.add(binding["signer_id"])
            signer_id_order.append(binding["signer_id"])
            profile, key = binding["signature_profile_id"], binding["key_digest"]
            if action == "recover":
                recovery_digest = binding.get("recovery_root_digest")
                recovery = recovery_roots.get(recovery_digest) if isinstance(recovery_digest, str) else None
                if recovery is None or recovery_digest not in eligible_roots:
                    raise ValueError("recovery_signer_root_not_policy_listed")
                if not isinstance(recovery_digest, str):
                    raise ValueError("recovery_signer_root_binding_invalid")
                kind, root_id, _, root_profile, root_key = _root_coordinate(recovery)
                if kind != "recovery_root" or (root_profile, root_key) != (profile, key):
                    raise ValueError("recovery_signer_root_binding_invalid")
                root_interval = recovery_active.get((root_id, recovery_digest))
                if root_interval is None or not _interval_contains(root_interval, effective):
                    raise ValueError("recovery_root_not_lifecycle_eligible")
                if recovery_digest in eligible_recovery_digests:
                    raise ValueError("recovery_root_duplicate_signature")
                eligible_recovery_digests.add(recovery_digest)
                authorized += 1
            elif any(value[:2] == (profile, key) and _interval_contains(value, effective) for value in active.values()):
                authorized += 1
                ordinary_record_signer = (profile, key)
            _signature(signature, profile=profile, key=key, payload=record_digest.encode("ascii"), verifier=verifier)
        if signer_id_order != sorted(signer_id_order):
            raise ValueError("lifecycle_signer_order_invalid")
        if action == "recover":
            binding_roots = [binding.get("recovery_root_digest") for binding in bindings]
            # A recovery may select any exact-threshold subset, but its signer
            # bindings must retain the selected roots' policy-tuple order.
            positions = [eligible_roots.index(root) if isinstance(root, str) else -1 for root in binding_roots]
            if positions != sorted(positions):
                raise ValueError("recovery_signer_order_not_policy_order")
            policy_effective = (
                _time(recovery_policy["effective_at"], "recovery_policy")
                if "effective_at" in recovery_policy
                else datetime.min.replace(tzinfo=UTC)
            )
            policy_expiry = (
                _time(recovery_policy["expires_at"], "recovery_policy")
                if recovery_policy.get("expires_at") is not None
                else None
            )
            if corrected_policy:
                signer_provenance = recovery_policy.get("signer_provenance")
                if not isinstance(signer_provenance, dict):
                    raise ValueError("recovery_policy_signature_binding_invalid")
                policy_key = signer_provenance.get("key_or_certificate_digest")
                policy_profile = signer_provenance.get("signature_profile_id")
            else:
                policy_key = recovery_policy.get("policy_signer_key_or_certificate_digest")
                policy_profile = recovery_policy.get("signature_profile_id")
            if (
                not isinstance(policy_key, str)
                or not isinstance(policy_profile, str)
                or policy_effective > effective
                or (policy_expiry is not None and effective >= policy_expiry)
                or not any(
                    value[:2] == (policy_profile, policy_key) and _interval_contains(value, effective)
                    for value in active.values()
                )
            ):
                raise ValueError("recovery_policy_not_lifecycle_eligible")
        if (action == "recover" and (authorized != threshold or len(eligible_recovery_digests) != threshold)) or (
            action != "recover" and authorized != 1
        ):
            raise ValueError("lifecycle_signer_not_eligible")
        replacement_id, replacement_digest = (
            record.get("replacement_target_id"),
            record.get("replacement_target_digest"),
        )
        target_active = active.get((target_id, target_digest))
        recovery_target = recovery_active.get((target_id, target_digest))
        if action in {"rotate", "recover"} and target_active is None:
            if recovery_target is not None:
                raise ValueError("lifecycle_target_not_ordinary_authority")
            raise ValueError("lifecycle_target_not_active")
        if action in {"revoke", "compromise"} and target_active is None and recovery_target is None:
            raise ValueError("lifecycle_target_not_active")
        if action in {"rotate", "recover"}:
            if not isinstance(replacement_id, str) or not isinstance(replacement_digest, str):
                raise ValueError("lifecycle_replacement_missing")
            if action == "recover" and replacement_digest == target_digest:
                raise ValueError("recovery_self_authorization")
            replacement = provisioned_roots.get((replacement_id, replacement_digest))
            if replacement is None:
                raise ValueError("lifecycle_replacement_not_independently_provisioned")
            if _is_independently_provisioned_genesis_bootstrap(replacement):
                raise ValueError("lifecycle_post_activation_genesis_downgrade")
            # Ordinary authority coordinates are tombstoned by their first
            # installation.  A valid provisioned artifact is not permission
            # to resurrect an old/revoked/compromised authority.
            if (replacement_id, replacement_digest) in intervals:
                raise ValueError("lifecycle_replacement_coordinate_reused")
            replacement_kind, _, _, replacement_profile, replacement_key = _root_coordinate(replacement)
            if (
                replacement_kind != "bootstrap_anchor"
                or replacement_id == target_id
                or replacement_digest == target_digest
            ):
                raise ValueError("lifecycle_replacement_invalid")
            replacement_start, replacement_expiry = _root_window(replacement)
            if replacement_start > effective or (replacement_expiry is not None and effective >= replacement_expiry):
                raise ValueError("lifecycle_replacement_time_invalid")
            if target_active is not None:
                active[(target_id, target_digest)] = (target_active[0], target_active[1], target_active[2], effective)
                intervals[(target_id, target_digest)] = active[(target_id, target_digest)]
                active.pop((target_id, target_digest))
            successor = (replacement_profile, replacement_key, effective, replacement_expiry)
            active[(replacement_id, replacement_digest)] = successor
            intervals[(replacement_id, replacement_digest)] = successor
            if action != "recover":
                root_signer = (replacement_profile, replacement_key)
        elif action in {"revoke", "compromise"}:
            if replacement_id is not None or replacement_digest is not None:
                raise ValueError("terminal_lifecycle_action_has_replacement")
            if target_active is not None:
                root_signer = target_active[:2]
                active[(target_id, target_digest)] = (target_active[0], target_active[1], target_active[2], effective)
                intervals[(target_id, target_digest)] = active[(target_id, target_digest)]
                active.pop((target_id, target_digest))
            elif recovery_target is not None:
                if ordinary_record_signer is None:
                    raise ValueError("lifecycle_root_signer_unresolved")
                root_signer = ordinary_record_signer
                recovery_active[(target_id, target_digest)] = (
                    recovery_target[0],
                    recovery_target[1],
                    recovery_target[2],
                    effective,
                )
                recovery_active.pop((target_id, target_digest))
        elif action == "activate":
            target = provisioned_roots.get((target_id, target_digest))
            # Genesis records authenticate the already independently
            # provisioned bootstrap coordinate; later activation cannot reuse
            # an existing coordinate.
            if sequence == 1 and (target_id, target_digest) == bootstrap_coordinate:
                root_signer = (anchor_profile, anchor_key)
                final_action = action
                previous_digest, previous_recorded = record_digest, recorded
                continue
            if target is None:
                raise ValueError("lifecycle_activation_not_independently_provisioned")
            if _is_independently_provisioned_genesis_bootstrap(target):
                raise ValueError("lifecycle_post_activation_genesis_downgrade")
            target_kind, _, _, target_profile, target_key = _root_coordinate(target)
            target_start, target_expiry = _root_window(target)
            if target_start > effective or (target_expiry is not None and effective >= target_expiry):
                raise ValueError("lifecycle_activation_time_invalid")
            if target_kind == "recovery_root":
                if ordinary_record_signer is None:
                    raise ValueError("lifecycle_root_signer_unresolved")
                recovery_coordinate = (target_id, target_digest)
                if recovery_coordinate in seen_recovery_activations:
                    raise ValueError("lifecycle_activation_duplicate_or_stale")
                seen_recovery_activations.add(recovery_coordinate)
                recovery_active[(target_id, target_digest)] = (
                    target_profile,
                    target_key,
                    effective,
                    target_expiry,
                )
                root_signer = ordinary_record_signer
            else:
                if (target_id, target_digest) in intervals:
                    raise ValueError("lifecycle_activation_not_independently_provisioned")
                active[(target_id, target_digest)] = (
                    target_profile,
                    target_key,
                    effective,
                    target_expiry,
                )
                intervals[(target_id, target_digest)] = active[(target_id, target_digest)]
                root_signer = (target_profile, target_key)
        final_action = action
        previous_digest, previous_recorded = record_digest, recorded
    if not active:
        raise ValueError("lifecycle_has_no_active_authority")
    if not isinstance(policy_digest, str) or not isinstance(root_digest, str):
        raise ValueError("lifecycle_digest_invalid")
    if final_action == "recover":
        raise ValueError("lifecycle_root_recover_signature_threshold_unsupported")
    if root_signer is None:
        raise ValueError("lifecycle_root_signer_unresolved")
    _signature(
        root.get("signature"),
        profile=root_signer[0],
        key=root_signer[1],
        payload=root_digest.encode("ascii"),
        verifier=verifier,
    )
    return policy_digest, root_digest, intervals


def _interval_contains(interval: tuple[str, str, datetime, datetime | None], when: datetime) -> bool:
    return interval[2] <= when and (interval[3] is None or when < interval[3])


def _active_signer_or_reject(
    *,
    active: dict[tuple[str, str], tuple[str, str, datetime, datetime | None]],
    profile: object,
    key: object,
    issued_at: datetime,
    purpose: object,
) -> None:
    """Keep approval signatures inside the replayed active trust interval."""
    if purpose != "semantic_ingestion_traceability_release" or not isinstance(profile, str) or not isinstance(key, str):
        raise ValueError("release_signer_purpose_or_profile_invalid")
    if not any(value[:2] == (profile, key) and _interval_contains(value, issued_at) for value in active.values()):
        raise ValueError("release_signer_not_lifecycle_eligible")


def _required_roots(
    registry: TraceabilityRegistry, expected_release_roots: dict[str, str] | None = None
) -> dict[str, str]:
    # The current release schema names registry commitments by semantic role;
    # the registry itself uses collection names.  Mapping here keeps the
    # verifier's required roots within the closed release-body grammar.
    registry_release_fields = {
        "artifact_dag_digest": "artifact_dag",
        "requirement_binding_registry_digest": "requirement_bindings",
        "assertion_registry_digest": "assertion_templates",
        "test_evidence_group_registry_digest": "test_evidence_groups",
        "section_default_registry_digest": "heading_defaults",
        "structural_mapping_rule_registry_digest": "structural_rules",
        "override_registry_digest": "overrides",
        "anchor_binding_registry_digest": "anchor_bindings",
    }
    roots = {
        "registry_source_identity": registry.source_identity,
        **{
            release_field: registry.root_digests[registry_name]
            for release_field, registry_name in registry_release_fields.items()
        },
    }
    external = (
        "design_document_digest",
        "structural_manifest_digest",
        "coverage_root_digest",
        "execution_root_digest",
        "report_schema_registry_digest",
        "runner_environment_profile_registry_digest",
        "trust_snapshot_digest",
    )
    if (
        expected_release_roots is None
        or set(expected_release_roots) != set(external)
        or any(
            not isinstance(expected_release_roots[key], str)
            or _LOWERCASE_SHA256.fullmatch(expected_release_roots[key]) is None
            for key in external
        )
    ):
        raise ValueError("expected_release_roots_unavailable")
    roots.update(expected_release_roots)
    return roots


def _expected_release_roots_available(expected_release_roots: object) -> bool:
    fields = {
        "design_document_digest",
        "structural_manifest_digest",
        "coverage_root_digest",
        "execution_root_digest",
        "report_schema_registry_digest",
        "runner_environment_profile_registry_digest",
        "trust_snapshot_digest",
    }
    return (
        isinstance(expected_release_roots, dict)
        and set(expected_release_roots) == fields
        and all(
            isinstance(expected_release_roots[field], str)
            and _LOWERCASE_SHA256.fullmatch(expected_release_roots[field]) is not None
            for field in fields
        )
    )


def _release_digest(release: dict[str, Any]) -> str:
    return _typed_digest(
        b"memorii:sia-traceability-release:v1",
        {key: value for key, value in release.items() if key not in {"release_digest", "signature"}},
    )


def _history_entry_digest(entry: dict[str, Any]) -> str:
    return _typed_digest(
        b"memorii:sia-traceability-release-history-entry:v1",
        {key: value for key, value in entry.items() if key != "entry_digest"},
    )


def _history_digest(history: dict[str, Any]) -> str:
    return _typed_digest(
        b"memorii:sia-traceability-release-history:v1",
        {key: value for key, value in history.items() if key not in {"release_history_digest", "signature"}},
    )


def verify_active_release_pointer(
    *,
    releases: tuple[dict[str, Any], ...],
    active_pointer: dict[str, Any],
    required_roots: dict[str, str],
    verifier: SignatureVerifier | None = None,
    active_signers: dict[tuple[str, str], tuple[str, str, datetime, datetime | None]] | None = None,
    lifecycle_root_digest: str | None = None,
    authority_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    required_pointer_fields = {
        "pointer_id",
        "issuance_purpose",
        "target_authority_id",
        "canonical_profile_binding",
        "generation_id",
        "generation_manifest_digest",
        "release_id",
        "release_digest",
        "release_epoch",
        "release_sequence",
        "release_history_digest",
        "predecessor_pointer_history_digest",
        "predecessor_active_pointer_digest",
        "pointer_sequence",
        "published_at",
        "signer_coordinate",
        "signature",
        "active_pointer_digest",
    }
    if set(active_pointer) != required_pointer_fields:
        raise ValueError("legacy_incomplete_provenance")
    if active_pointer.get("issuance_purpose") != "semantic_ingestion_traceability_active_release_pointer":
        raise ValueError("active_pointer_purpose_invalid")
    if active_pointer.get("target_authority_id") != authority_id:
        raise ValueError("active_pointer_authority_invalid")
    pointer_schema, pointer_binding_digest = _CTV_BODY_BINDINGS["active_pointer"]
    expected_pointer_binding = CanonicalTypedValueProfileBinding(
        *_CTV_PROFILE, pointer_schema, 1, pointer_binding_digest
    )
    if active_pointer.get("canonical_profile_binding") != expected_pointer_binding.as_value():
        raise ValueError("active_pointer_binding_invalid")
    by_id = {item.get("release_id"): item for item in releases}
    if len(by_id) != len(releases) or not all(isinstance(key, str) for key in by_id):
        raise ValueError("release_ids_invalid")
    if any(
        type(item.get("epoch")) is not int
        or type(item.get("sequence")) is not int
        or item["epoch"] < 1
        or item["sequence"] < 1
        for item in releases
    ):
        raise ValueError("release_coordinate_invalid")
    if (
        type(active_pointer.get("release_epoch")) is not int
        or type(active_pointer.get("release_sequence")) is not int
        or active_pointer["release_epoch"] < 1
        or active_pointer["release_sequence"] < 1
    ):
        raise ValueError("active_pointer_coordinate_invalid")
    coordinates = [(item["epoch"], item["sequence"]) for item in releases]
    if len(coordinates) != len(set(coordinates)):
        raise ValueError("release_coordinate_substitution_or_duplicate")
    ordered = sorted(releases, key=lambda item: (item.get("epoch"), item.get("sequence")))
    prior: dict[str, Any] | None = None
    for release in ordered:
        if (
            type(release.get("epoch")) is not int
            or release["epoch"] < 1
            or type(release.get("sequence")) is not int
            or release["sequence"] < 1
            or release.get("issued_state") != "active"
        ):
            raise ValueError("release_root_binding_invalid")
        if prior is None:
            if release.get("predecessor_release_id") is not None:
                raise ValueError("genesis_release_has_predecessor")
        elif (
            release.get("predecessor_release_id") != prior.get("release_id")
            or release["epoch"] < prior["epoch"]
            or (release["epoch"] == prior["epoch"] and release["sequence"] != prior["sequence"] + 1)
        ):
            raise ValueError("release_successor_or_rollback_invalid")
        elif release.get("supersedes_release_id") is not None and release.get("supersedes_release_id") != prior.get(
            "release_id"
        ):
            raise ValueError("release_rollback_must_explicitly_supersede_active_predecessor")
        prior = release
    if prior is None or (
        active_pointer.get("release_id"),
        active_pointer.get("release_digest"),
        active_pointer.get("release_epoch"),
        active_pointer.get("release_sequence"),
    ) != (
        prior.get("release_id"),
        prior.get("release_digest"),
        prior.get("epoch"),
        prior.get("sequence"),
    ):
        raise ValueError("active_pointer_is_not_current_release")
    if any(
        not isinstance(prior.get(name), str) or (value and prior[name] != value)
        for name, value in required_roots.items()
    ):
        raise ValueError("active_pointer_current_release_root_binding_invalid")
    if verifier is not None:
        pointer_body = {
            key: value for key, value in active_pointer.items() if key not in {"signature", "active_pointer_digest"}
        }
        digest = _digest(
            b"memorii:sia-traceability-active-release-pointer:v1",
            encode_typed_value(pointer_body),
        )
        if active_pointer.get("active_pointer_digest") != digest:
            raise ValueError("active_pointer_digest_invalid")
        signer = active_pointer.get("signer_coordinate")
        if not isinstance(signer, dict) or active_signers is None or lifecycle_root_digest is None:
            raise ValueError("active_pointer_signature_binding_invalid")
        binding = active_pointer.get("canonical_profile_binding")
        if not isinstance(binding, dict):
            raise ValueError("active_pointer_signature_binding_invalid")
        preimage = encode_typed_value(
            {
                "issuance_purpose": "semantic_ingestion_traceability_active_release_pointer",
                "body_binding": binding,
                "active_pointer_digest": digest,
                "signer_coordinate": signer,
            }
        )
        pointer_time = _time(active_pointer.get("published_at"), "active_pointer")
        _signer_coordinate(
            signer,
            purpose="semantic_ingestion_traceability_active_release_pointer",
            lifecycle_root_digest=lifecycle_root_digest,
            active_signers=active_signers,
            when=pointer_time,
            verifier=verifier,
            signature=active_pointer.get("signature"),
            payload=preimage,
        )
        _signer_coordinate(
            signer,
            purpose="semantic_ingestion_traceability_active_release_pointer",
            lifecycle_root_digest=lifecycle_root_digest,
            active_signers=active_signers,
            when=now or datetime.now(UTC),
            verifier=verifier,
            signature=active_pointer.get("signature"),
            payload=preimage,
        )
    return prior


def _verify_legacy_active_release_pointer(
    *,
    releases: tuple[dict[str, Any], ...],
    active_pointer: dict[str, Any],
    required_roots: dict[str, str],
    verifier: SignatureVerifier | None,
    active_signers: dict[tuple[str, str], tuple[str, str, datetime, datetime | None]] | None,
    now: datetime | None,
) -> dict[str, Any]:
    """Preserve the explicitly legacy release-gate pointer contract."""
    if active_pointer.get("issuance_purpose") != "semantic_ingestion_traceability_active_release_pointer":
        raise ValueError("active_pointer_purpose_invalid")
    _enforce_signer_key_field(active_pointer, expected="issuer_key_or_certificate_digest")
    by_id = {item.get("release_id"): item for item in releases}
    if len(by_id) != len(releases) or not all(isinstance(key, str) for key in by_id):
        raise ValueError("release_ids_invalid")
    coordinates = [(item.get("epoch"), item.get("sequence")) for item in releases]
    if len(coordinates) != len(set(coordinates)):
        raise ValueError("release_coordinate_substitution_or_duplicate")
    ordered = sorted(releases, key=lambda item: (item.get("epoch"), item.get("sequence")))
    prior: dict[str, Any] | None = None
    for release in ordered:
        if (
            type(release.get("epoch")) is not int
            or type(release.get("sequence")) is not int
            or release["epoch"] < 1
            or release["sequence"] < 1
            or release.get("issued_state") != "active"
        ):
            raise ValueError("release_root_binding_invalid")
        if prior is None:
            if release.get("predecessor_release_id") is not None:
                raise ValueError("genesis_release_has_predecessor")
        elif (
            release.get("predecessor_release_id") != prior.get("release_id")
            or release["epoch"] < prior["epoch"]
            or (release["epoch"] == prior["epoch"] and release["sequence"] != prior["sequence"] + 1)
        ):
            raise ValueError("release_successor_or_rollback_invalid")
        elif release.get("supersedes_release_id") is not None and release.get("supersedes_release_id") != prior.get(
            "release_id"
        ):
            raise ValueError("release_rollback_must_explicitly_supersede_active_predecessor")
        prior = release
    if prior is None or any(
        active_pointer.get(key) != prior.get(key) for key in ("release_id", "release_digest", "epoch", "sequence")
    ):
        raise ValueError("active_pointer_is_not_current_release")
    if any(
        not isinstance(prior.get(name), str) or (value and prior[name] != value)
        for name, value in required_roots.items()
    ):
        raise ValueError("active_pointer_current_release_root_binding_invalid")
    if verifier is not None:
        digest = _digest(
            b"memorii:sia-traceability-active-release-pointer:v1",
            _body(active_pointer, "active_pointer_digest", "signature"),
        )
        if active_pointer.get("active_pointer_digest") != digest:
            raise ValueError("active_pointer_digest_invalid")
        profile = active_pointer.get("signature_profile_id")
        key = active_pointer.get("issuer_key_or_certificate_digest")
        if not isinstance(profile, str) or not isinstance(key, str):
            raise ValueError("active_pointer_signature_binding_invalid")
        _signature(
            active_pointer.get("signature"),
            profile=profile,
            key=key,
            payload=digest.encode("ascii"),
            verifier=verifier,
        )
        if active_signers is not None:
            verification_time = now or datetime.now(UTC)
            pointer_time = (
                _time(active_pointer.get("issued_at"), "active_pointer")
                if "issued_at" in active_pointer
                else verification_time
            )
            if not any(
                value[:2] == (profile, key) and _interval_contains(value, pointer_time)
                for value in active_signers.values()
            ):
                raise ValueError("active_pointer_signer_not_lifecycle_eligible")
            if not any(
                value[:2] == (profile, key) and _interval_contains(value, verification_time)
                for value in active_signers.values()
            ):
                raise ValueError("active_pointer_signer_not_lifecycle_eligible")
    return prior


def _validate_release_candidate(
    *,
    registry: TraceabilityRegistry,
    bootstrap_artifact: bytes | None,
    recovery_artifact: bytes | None,
    lifecycle_artifact: bytes | None,
    release_artifact: bytes | None,
    verifier_material: VerifierHeldTrustMaterial | None = None,
    active_pointer_artifact: bytes | None = None,
    release_history_artifact: bytes | None = None,
    historical_release_artifacts: tuple[bytes, ...] = (),
    recovery_artifacts: tuple[bytes, ...] | None = None,
    expected_release_roots: dict[str, str] | None = None,
    now: datetime | None = None,
) -> _ReleaseValidationResult:
    for name, artifact in (
        ("bootstrap", bootstrap_artifact),
        ("recovery", recovery_artifact),
        ("lifecycle", lifecycle_artifact),
        ("release", release_artifact),
        ("active_pointer", active_pointer_artifact),
        ("release_history", release_history_artifact),
    ):
        if artifact is None:
            return TraceabilityGateUnavailable(reason=f"{name}_unavailable")
    if verifier_material is None or verifier_material.recovery_policy_bytes is None:
        return TraceabilityGateUnavailable(reason="verifier_trust_material_unavailable")
    if not _expected_release_roots_available(expected_release_roots):
        return TraceabilityGateUnavailable(reason="expected_release_roots_unavailable")
    verification_time = now or datetime.now(UTC)
    if verification_time.tzinfo is None:
        return TraceabilityGateRejected(reason="verification_time_naive")
    # Bind each parser input after an explicit guard; optional transport values
    # never reach the canonical-byte parser.
    if (
        bootstrap_artifact is None
        or recovery_artifact is None
        or lifecycle_artifact is None
        or release_artifact is None
        or active_pointer_artifact is None
        or release_history_artifact is None
    ):
        return TraceabilityGateUnavailable(reason="artifact_unavailable")
    bootstrap_bytes = bootstrap_artifact
    recovery_bytes = recovery_artifact
    lifecycle_bytes = lifecycle_artifact
    release_bytes = release_artifact
    try:
        # Authorization dispatch accepts one complete corrected CTV-v2
        # generation. Flat or mixed artifacts are legacy diagnostics only.
        current_artifacts = (
            bootstrap_artifact,
            recovery_artifact,
            lifecycle_artifact,
            release_artifact,
            active_pointer_artifact,
            release_history_artifact,
            verifier_material.recovery_policy_bytes,
            *(recovery_artifacts or ()),
            *historical_release_artifacts,
        )
        try:
            for artifact in current_artifacts:
                decode_artifact(artifact)
        except CanonicalTypedValueError as exc:
            raise ValueError("legacy_incomplete_provenance") from exc
        release_bytes = _canonical_loaded_bytes(release_artifact, "release")
        supplied_recovery_bytes = (recovery_bytes, *(recovery_artifacts or ()))
        if len(supplied_recovery_bytes) != len(set(supplied_recovery_bytes)):
            raise ValueError("recovery_roots_duplicate")
        if bootstrap_bytes != verifier_material.bootstrap_anchor_bytes or set(supplied_recovery_bytes) != set(
            verifier_material.recovery_root_bytes
        ):
            raise ValueError("trust_not_independently_provisioned")
        bootstrap, lifecycle, release = (
            _load(bootstrap_bytes, "bootstrap"),
            _load(lifecycle_bytes, "lifecycle"),
            _load(release_bytes, "release"),
        )
        recoveries = [_load(item, "recovery") for item in supplied_recovery_bytes]
        authority_id = bootstrap.get("target_authority_id")
        if not isinstance(authority_id, str) or not authority_id:
            raise ValueError("bootstrap_authority_invalid")
        prior_lifecycles: dict[str, dict[str, Any]] = {}
        for raw in verifier_material.prior_verified_lifecycle_root_bytes:
            try:
                decode_artifact(raw)
            except CanonicalTypedValueError as exc:
                raise ValueError("legacy_incomplete_provenance") from exc
            historical = _load(raw, "lifecycle")
            digest = historical.get("lifecycle_root_digest")
            if not isinstance(digest, str) or digest in prior_lifecycles:
                raise ValueError("prior_lifecycle_root_missing_or_ambiguous")
            if historical.get("authority_id") != authority_id:
                raise ValueError("prior_lifecycle_root_authority_invalid")
            prior_lifecycles[digest] = historical
        ordered_prior_lifecycles = sorted(
            prior_lifecycles.values(),
            key=lambda item: len(item.get("records", ()))
            if isinstance(item.get("records"), list)
            else -1,
        )
        validated_prior_lifecycles: dict[str, dict[str, Any]] = {}
        for expected_sequence, historical in enumerate(
            ordered_prior_lifecycles, start=1
        ):
            records = historical.get("records")
            if not isinstance(records, list) or len(records) != expected_sequence:
                raise ValueError("prior_lifecycle_root_sequence_invalid")
            if expected_sequence == 1:
                historical_digest, _ = _validate_current_lifecycle_genesis(
                    historical,
                    authority_id=authority_id,
                    bootstrap=bootstrap,
                    verifier=verifier_material.verify_signature,
                )
            else:
                historical_digest, _ = _validate_current_lifecycle_successor(
                    historical,
                    authority_id=authority_id,
                    prior_verified_roots=validated_prior_lifecycles,
                    verifier=verifier_material.verify_signature,
                )
            validated_prior_lifecycles[historical_digest] = historical
        prior_lifecycles = validated_prior_lifecycles
        if "provenance" not in bootstrap or any("provenance" not in item for item in recoveries):
            raise ValueError("legacy_incomplete_provenance")
        _validate_provisioned_root_provenance(bootstrap, authority_id=authority_id, lifecycle=lifecycle, prior_lifecycles=prior_lifecycles)
        for item in recoveries:
            _validate_provisioned_root_provenance(item, authority_id=authority_id, lifecycle=lifecycle, prior_lifecycles=prior_lifecycles)
        recovery_digests = [_root_coordinate(item)[2] for item in recoveries]
        if any(recovery.get("target_authority_id") != authority_id for recovery in recoveries):
            raise ValueError("provisioned_root_authority_invalid")
        policy = _load(verifier_material.recovery_policy_bytes, "recovery_policy")
        provisioned_documents = [bootstrap, *recoveries]
        for raw in verifier_material.provisioned_successor_root_bytes:
            try:
                decode_artifact(raw)
            except CanonicalTypedValueError as exc:
                raise ValueError("legacy_incomplete_provenance") from exc
            candidate = _load(raw, "provisioned_successor_root")
            if candidate.get("target_authority_id") != authority_id:
                raise ValueError("provisioned_root_authority_invalid")
            _validate_provisioned_root_provenance(candidate, authority_id=authority_id, lifecycle=lifecycle, prior_lifecycles=prior_lifecycles)
            if _is_independently_provisioned_genesis_bootstrap(candidate):
                # A second bootstrap root is only admissible as a lifecycle
                # successor.  Its independently provisioned genesis variant
                # is valid transport but cannot downgrade an activated chain.
                raise ValueError("lifecycle_post_activation_genesis_downgrade")
            provisioned_documents.append(candidate)
        provisioned_roots: dict[tuple[str, str], dict[str, Any]] = {}
        signer_coordinates: dict[tuple[str, str], tuple[str, str]] = {}
        for document in provisioned_documents:
            kind, root_id, root_digest, profile, key = _root_coordinate(document)
            coordinate = (root_id, root_digest)
            if coordinate in provisioned_roots:
                raise ValueError("provisioned_root_duplicate")
            provisioned_roots[coordinate] = document
            # The current envelope carries a flat profile/key signer binding.
            # Until M0A supplies a typed root coordinate on each signed object,
            # a key shared by any distinct provisioned root is ambiguous.
            signer = (profile, key)
            previous_coordinate = signer_coordinates.setdefault(signer, coordinate)
            if previous_coordinate != coordinate:
                raise ValueError("ambiguous_lifecycle_signer_coordinate")
        for document in provisioned_documents:
            if _root_coordinate(document)[0] != "bootstrap_anchor":
                continue
            predecessor_id = document.get("predecessor_anchor_id")
            predecessor_digest = document.get("predecessor_anchor_digest")
            if predecessor_id is None and predecessor_digest is None:
                continue
            predecessor = provisioned_roots.get(
                (str(predecessor_id), str(predecessor_digest))
            )
            if (
                predecessor is None
                or _root_coordinate(predecessor)[0] != "bootstrap_anchor"
                or type(document.get("rotation_sequence")) is not int
                or type(predecessor.get("rotation_sequence")) is not int
                or document["rotation_sequence"]
                != predecessor["rotation_sequence"] + 1
            ):
                raise ValueError("provisioned_successor_rotation_sequence_invalid")
        recovery_by_digest: dict[str, dict[str, Any]] = {}
        for digest, recovery in zip(recovery_digests, recoveries, strict=True):
            if not isinstance(digest, str):
                raise ValueError("recovery_root_digest_invalid")
            recovery_by_digest[digest] = recovery
        policy_digest, lifecycle_digest, active_signers = _validate_lifecycle(
            lifecycle,
            authority_id=authority_id,
            bootstrap=bootstrap,
            recovery_policy=policy,
            recovery_roots=recovery_by_digest,
            provisioned_roots=provisioned_roots,
            verifier=verifier_material.verify_signature,
            now=verification_time.astimezone(UTC),
            prior_verified_roots=prior_lifecycles,
        )
        active_targets: set[tuple[str, str]] = set()
        active_recovery_targets: set[tuple[str, str]] = set()
        tombstoned_targets: set[tuple[str, str]] = set()
        records = lifecycle.get("records")
        if not isinstance(records, list):
            raise ValueError("lifecycle_record_invalid")
        for record in records:
            if not isinstance(record, dict):
                raise ValueError("lifecycle_record_invalid")
            target = (record.get("target_id"), record.get("target_digest"))
            if not all(isinstance(value, str) for value in target):
                raise ValueError("lifecycle_sequence_or_target_invalid")
            target_coordinate = (str(target[0]), str(target[1]))
            target_document = provisioned_roots.get(target_coordinate)
            effective = _time(record.get("effective_at"), "lifecycle_action")
            if target_document is None:
                raise ValueError("lifecycle_target_not_independently_provisioned")
            target_start, target_end = _root_window(target_document)
            if not _interval_contains(("", "", target_start, target_end), effective):
                raise ValueError("lifecycle_action_outside_provisioned_window")
            action = record.get("action")
            bindings = record.get("signer_bindings")
            if not isinstance(bindings, list):
                raise ValueError("lifecycle_signatures_invalid")
            if action == "recover":
                eligible = policy.get("eligible_recovery_root_digests")
                threshold = policy.get("minimum_distinct_signatures")
                if (
                    not isinstance(eligible, list)
                    or type(threshold) is not int
                    or len(bindings) != threshold
                ):
                    raise ValueError("recovery_signature_threshold_invalid")
                selected: list[str] = []
                for binding in bindings:
                    if not isinstance(binding, dict):
                        raise ValueError("lifecycle_signer_binding_invalid")
                    recovery_digest = binding.get("recovery_root_digest")
                    recovery = (
                        recovery_by_digest.get(recovery_digest)
                        if isinstance(recovery_digest, str)
                        else None
                    )
                    if recovery is None or recovery_digest not in eligible:
                        raise ValueError("recovery_signer_root_not_policy_listed")
                    _, recovery_id, _, profile, key = _root_coordinate(recovery)
                    recovery_coordinate = (recovery_id, recovery_digest)
                    if (
                        binding.get("signer_id") != recovery_id
                        or binding.get("signature_profile_id") != profile
                        or binding.get("signer_key_or_certificate_digest") != key
                    ):
                        raise ValueError("recovery_signer_root_binding_invalid")
                    recovery_start, recovery_end = _root_window(recovery)
                    if not _interval_contains(
                        ("", "", recovery_start, recovery_end), effective
                    ):
                        raise ValueError("recovery_root_not_lifecycle_eligible")
                    if recovery_coordinate not in active_recovery_targets:
                        raise ValueError("recovery_root_not_lifecycle_eligible")
                    if not isinstance(recovery_digest, str):
                        raise ValueError("recovery_signer_root_binding_invalid")
                    selected.append(recovery_digest)
                if (
                    len(selected) != len(set(selected))
                    or selected != [
                        digest for digest in eligible if digest in set(selected)
                    ]
                ):
                    raise ValueError("recovery_signer_order_not_policy_order")
            elif any(
                not isinstance(binding, dict)
                or binding.get("recovery_root_digest") is not None
                for binding in bindings
            ):
                raise ValueError("lifecycle_signer_binding_invalid")
            if action == "activate":
                if target_coordinate in tombstoned_targets:
                    raise ValueError("lifecycle_activation_duplicate_or_stale")
                target_kind = _root_coordinate(target_document)[0]
                if target_kind == "recovery_root":
                    if target_coordinate in active_recovery_targets:
                        raise ValueError("lifecycle_activation_duplicate_or_stale")
                    active_recovery_targets.add(target_coordinate)
                elif target_kind == "bootstrap_anchor":
                    if target_coordinate in active_targets:
                        raise ValueError("lifecycle_activation_duplicate_or_stale")
                    active_targets.add(target_coordinate)
                else:
                    raise ValueError("lifecycle_target_kind_invalid")
            elif action in {"rotate", "recover"}:
                if target_coordinate not in active_targets:
                    raise ValueError("lifecycle_target_not_active")
                active_targets.remove(target_coordinate)
                tombstoned_targets.add(target_coordinate)
                replacement = (
                    record.get("replacement_target_id"),
                    record.get("replacement_target_digest"),
                )
                if not all(isinstance(value, str) for value in replacement):
                    raise ValueError("lifecycle_replacement_missing")
                replacement_coordinate = (str(replacement[0]), str(replacement[1]))
                replacement_document = provisioned_roots.get(replacement_coordinate)
                if replacement_document is None:
                    raise ValueError("lifecycle_replacement_not_independently_provisioned")
                if (
                    replacement_coordinate in active_targets
                    or replacement_coordinate in active_recovery_targets
                    or replacement_coordinate in tombstoned_targets
                    or _root_coordinate(replacement_document)[0] != "bootstrap_anchor"
                ):
                    raise ValueError("lifecycle_replacement_invalid")
                replacement_start, replacement_end = _root_window(replacement_document)
                if not _interval_contains(("", "", replacement_start, replacement_end), effective):
                    raise ValueError("lifecycle_action_outside_provisioned_window")
                active_targets.add(replacement_coordinate)
            elif action in {"revoke", "compromise"}:
                if target_coordinate in active_targets:
                    active_targets.remove(target_coordinate)
                elif target_coordinate in active_recovery_targets:
                    active_recovery_targets.remove(target_coordinate)
                else:
                    raise ValueError("lifecycle_target_not_active")
                tombstoned_targets.add(target_coordinate)
        active_bootstraps = {
            coordinate
            for coordinate in active_targets
            if coordinate in provisioned_roots
            and _root_coordinate(provisioned_roots[coordinate])[0] == "bootstrap_anchor"
        }
        if len(active_bootstraps) != 1:
            raise ValueError("active_bootstrap_authority_ambiguous")
        active_bootstrap = next(iter(active_bootstraps))
        release_fields = {
            "release_id", "issuance_purpose", "registry_source_identity", "design_document_digest",
            "structural_manifest_digest", "grammar_revision", "canonical_profile_binding",
            "artifact_dag_digest", "requirement_binding_registry_digest", "assertion_registry_digest",
            "test_evidence_group_registry_digest", "report_schema_registry_digest",
            "runner_environment_profile_registry_digest", "golden_vector_manifest_digest",
            "section_default_registry_digest", "structural_mapping_rule_registry_digest",
            "override_registry_digest", "anchor_binding_registry_digest", "coverage_root_digest",
            "execution_root_digest", "bootstrap_anchor_id", "bootstrap_anchor_digest",
            "bootstrap_anchor_history_digest", "bootstrap_rotation_sequence",
            "recovery_trust_policy_digest", "recovery_policy_history_digest",
            "recovery_trust_root_digests", "recovery_root_history_digest", "trust_lifecycle_root_digest",
            "trust_snapshot_digest", "epoch", "sequence", "issued_state", "predecessor_release_id",
            "supersedes_release_id", "issued_at", "expires_at", "signer_coordinate", "signature",
            "release_digest",
        }
        if (
            set(release) != release_fields
            or release.get("issuance_purpose") != "semantic_ingestion_traceability_release"
            or release.get("canonical_profile_binding") != _binding_for("release")
            or release.get("issued_state") != "active"
        ):
            raise ValueError("release_purpose_or_lifecycle_invalid")
        required = _required_roots(registry, expected_release_roots)
        history_document = _load(release_history_artifact, "release_history")
        history_keys = {"history_id", "issuance_purpose", "canonical_profile_binding", "entries", "signer_coordinate", "release_history_digest", "signature"}
        if (
            set(history_document) != history_keys
            or history_document.get("issuance_purpose") != "semantic_ingestion_traceability_release_history"
            or history_document.get("canonical_profile_binding") != _binding_for("release_history")
            or not isinstance(history_document.get("entries"), list)
        ):
            raise ValueError("release_history_invalid")
        if _history_digest(history_document) != history_document.get("release_history_digest"):
            raise ValueError("release_history_digest_invalid")
        history_signer = history_document.get("signer_coordinate")
        if not isinstance(history_signer, dict):
            raise ValueError("release_history_signature_binding_invalid")
        history_preimage = encode_typed_value({
            "issuance_purpose": "semantic_ingestion_traceability_release_history",
            "body_binding": history_document["canonical_profile_binding"],
            "release_history_digest": history_document["release_history_digest"],
            "signer_coordinate": history_signer,
        })
        _signer_coordinate(
            history_signer, purpose="semantic_ingestion_traceability_release_history",
            lifecycle_root_digest=lifecycle_digest, active_signers=active_signers,
            when=verification_time.astimezone(UTC), verifier=verifier_material.verify_signature,
            signature=history_document.get("signature"), payload=history_preimage,
        )
        history = history_document["entries"]
        if not history:
            raise ValueError("release_history_does_not_end_at_release")
        if len(historical_release_artifacts) != len(set(historical_release_artifacts)):
            raise ValueError("historical_release_artifacts_duplicate")
        historical_releases = [_load(raw, "historical_release") for raw in historical_release_artifacts]
        releases_by_digest: dict[str, dict[str, Any]] = {}
        for candidate in [release, *historical_releases]:
            digest = _release_digest(candidate)
            if digest in releases_by_digest or candidate.get("release_digest") != digest:
                raise ValueError("historical_release_artifact_duplicate_or_invalid")
            releases_by_digest[digest] = candidate
        releases: list[dict[str, Any]] = []
        prior_entry: dict[str, Any] | None = None
        prior_release: dict[str, Any] | None = None
        for index, entry in enumerate(history, start=1):
            entry_keys = {
                "entry_id",
                "sequence",
                "predecessor_entry_digest",
                "release_id",
                "release_digest",
                "release_epoch",
                "release_sequence",
                "prior_active_release_digest",
                "prior_release_terminal_state",
                "effective_at",
                "entry_digest",
            }
            if (
                not isinstance(entry, dict)
                or set(entry) != entry_keys
                or _history_entry_digest(entry) != entry.get("entry_digest")
            ):
                raise ValueError("release_history_entry_digest_invalid")
            if any(
                type(entry[name]) is not int or entry[name] < 1
                for name in ("sequence", "release_epoch", "release_sequence")
            ):
                raise ValueError("release_history_entry_coordinate_invalid")
            release_digest_from_entry = entry.get("release_digest")
            candidate = (
                releases_by_digest.get(release_digest_from_entry)
                if isinstance(release_digest_from_entry, str)
                else None
            )
            if candidate is None:
                raise ValueError("release_history_artifact_missing")
            if (
                type(candidate.get("epoch")) is not int
                or type(candidate.get("sequence")) is not int
                or candidate["epoch"] < 1
                or candidate["sequence"] < 1
            ):
                raise ValueError("release_coordinate_invalid")
            if (
                candidate.get("issuance_purpose") != "semantic_ingestion_traceability_release"
                or candidate.get("canonical_profile_binding") != _binding_for("release")
                or candidate.get("issued_state") != "active"
            ):
                raise ValueError("release_purpose_or_lifecycle_invalid")
            if (
                (candidate.get("bootstrap_anchor_id"), candidate.get("bootstrap_anchor_digest"))
                != active_bootstrap
                or set(candidate.get("recovery_trust_root_digests", ())) != set(recovery_digests)
                or candidate.get("trust_lifecycle_root_digest") != lifecycle_digest
                or candidate.get("recovery_trust_policy_digest") != policy_digest
            ):
                raise ValueError("release_trust_binding_invalid")
            issued = _time(candidate.get("issued_at"), "release")
            expires = candidate.get("expires_at")
            if issued > verification_time.astimezone(UTC) or (
                expires is not None and _time(expires, "release") < issued
            ):
                raise ValueError("release_time_window_invalid")
            candidate_digest = _release_digest(candidate)
            if candidate.get("release_digest") != candidate_digest:
                raise ValueError("release_digest_invalid")
            signer = candidate.get("signer_coordinate")
            if not isinstance(signer, dict):
                raise ValueError("release_signature_binding_invalid")
            release_preimage = encode_typed_value({
                "issuance_purpose": "semantic_ingestion_traceability_release",
                "body_binding": candidate["canonical_profile_binding"],
                "release_digest": candidate_digest,
                "signer_coordinate": signer,
            })
            _signer_coordinate(
                signer, purpose="semantic_ingestion_traceability_release", lifecycle_root_digest=lifecycle_digest,
                active_signers=active_signers, when=issued, verifier=verifier_material.verify_signature,
                signature=candidate.get("signature"), payload=release_preimage,
            )
            if (
                entry.get("sequence") != index
                or entry.get("release_id") != candidate.get("release_id")
                or entry.get("release_digest") != candidate_digest
                or entry.get("release_epoch") != candidate.get("epoch")
                or entry.get("release_sequence") != candidate.get("sequence")
            ):
                raise ValueError("release_history_entry_release_binding_invalid")
            effective = _time(entry.get("effective_at"), "release_history_entry")
            if prior_entry is None:
                if (
                    entry.get("predecessor_entry_digest") is not None
                    or entry.get("prior_active_release_digest") is not None
                    or entry.get("prior_release_terminal_state") is not None
                    or candidate.get("predecessor_release_id") is not None
                    or candidate.get("supersedes_release_id") is not None
                ):
                    raise ValueError("release_history_genesis_invalid")
            else:
                if prior_release is None:
                    raise ValueError("release_history_predecessor_missing")
                if (
                    entry.get("predecessor_entry_digest") != prior_entry.get("entry_digest")
                    or entry.get("prior_active_release_digest") != prior_release.get("release_digest")
                    or entry.get("prior_release_terminal_state") not in {"superseded", "revoked", "compromised"}
                ):
                    raise ValueError("release_history_predecessor_invalid")
                if (
                    candidate.get("predecessor_release_id") != prior_release.get("release_id")
                    or candidate.get("supersedes_release_id") != prior_release.get("release_id")
                    or (candidate["epoch"], candidate["sequence"])
                    <= (prior_release["epoch"], prior_release["sequence"])
                ):
                    raise ValueError("release_successor_or_rollback_invalid")
                prior_effective = _time(prior_entry.get("effective_at"), "release_history_entry")
                if issued <= prior_effective or effective <= prior_effective:
                    raise ValueError("release_history_time_not_strictly_increasing")
            if effective < issued or (expires is not None and effective > _time(expires, "release")):
                raise ValueError("release_history_effective_time_invalid")
            prior_entry, prior_release = entry, candidate
            releases.append(candidate)
        if set(releases_by_digest) != {str(item["release_digest"]) for item in history}:
            raise ValueError("historical_release_artifact_unreferenced")
        release_digest = str(release["release_digest"])
        pointer = _load(active_pointer_artifact, "active_pointer")
        if pointer.get("release_history_digest") != history_document.get("release_history_digest"):
            raise ValueError("active_pointer_release_history_binding_invalid")
        current = verify_active_release_pointer(
            releases=tuple(releases),
            active_pointer=pointer,
            required_roots=required,
            verifier=verifier_material.verify_signature,
            active_signers=active_signers,
            lifecycle_root_digest=lifecycle_digest,
            authority_id=authority_id,
            now=verification_time.astimezone(UTC),
        )
        if (
            current is not prior_release
            or current.get("release_digest") != release_digest
            or release_bytes != canonical_document(current)
        ):
            raise ValueError("release_artifact_is_not_authenticated_current_release")
        if any(
            not isinstance(current.get(name), str) or (value and current[name] != value)
            for name, value in required.items()
        ):
            raise ValueError("release_root_binding_invalid")
        tail_effective = _time(history[-1].get("effective_at"), "release_history_entry")
        if tail_effective > verification_time.astimezone(UTC):
            raise ValueError("release_history_tail_not_yet_effective")
        _signer_coordinate(
            history_signer, purpose="semantic_ingestion_traceability_release_history",
            lifecycle_root_digest=lifecycle_digest, active_signers=active_signers,
            when=tail_effective, verifier=verifier_material.verify_signature,
            signature=history_document.get("signature"), payload=history_preimage,
        )
        current_issued = _time(current.get("issued_at"), "release")
        current_expires = current.get("expires_at")
        if current_issued > verification_time.astimezone(UTC) or (
            current_expires is not None and verification_time.astimezone(UTC) > _time(current_expires, "release")
        ):
            raise ValueError("current_release_time_window_invalid")
        # A historical release remains valid as evidence of its issuance, but
        # authorizing the selected current release is a present-tense action.
        # Re-evaluate its signer at use time before touching durable state.
        current_signer = current.get("signer_coordinate")
        if not isinstance(current_signer, dict):
            raise ValueError("release_signature_binding_invalid")
        current_preimage = encode_typed_value({
            "issuance_purpose": "semantic_ingestion_traceability_release",
            "body_binding": current["canonical_profile_binding"],
            "release_digest": release_digest,
            "signer_coordinate": current_signer,
        })
        _signer_coordinate(
            current_signer, purpose="semantic_ingestion_traceability_release",
            lifecycle_root_digest=lifecycle_digest, active_signers=active_signers,
            when=verification_time.astimezone(UTC), verifier=verifier_material.verify_signature,
            signature=current.get("signature"), payload=current_preimage,
        )
        return _VerifiedReleaseCandidate(
            release_id=str(release["release_id"]),
            release_digest=release_digest,
            epoch=current["epoch"],
            sequence=current["sequence"],
            root_bindings=tuple((name, str(release[name])) for name in sorted(required)),
            active_signers=tuple(
                (
                    signer_id,
                    signer_digest,
                    profile,
                    key,
                    eligible_not_before,
                    eligible_not_after,
                )
                for (signer_id, signer_digest), (
                    profile,
                    key,
                    eligible_not_before,
                    eligible_not_after,
                ) in sorted(active_signers.items())
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        return TraceabilityGateRejected(reason=str(exc))


def _candidate_authorization(
    candidate: _VerifiedReleaseCandidate,
) -> TraceabilityGateAuthorized:
    return TraceabilityGateAuthorized(
        release_id=candidate.release_id,
        release_digest=candidate.release_digest,
        root_bindings=dict(candidate.root_bindings),
    )


def _commit_verified_release(
    candidate: _VerifiedReleaseCandidate,
    watermark_store: TraceabilityReleaseWatermarkStore,
    *,
    publication_store: TraceabilityReleasePublicationStore | None = None,
    release_artifact: bytes | None = None,
    release_history_artifact: bytes | None = None,
    active_pointer_artifact: bytes | None = None,
    pointer_history_artifact: bytes | None = None,
    allow_test_file_fence: bool = False,
    verified_anti_rollback_registration: VerifiedAntiRollbackRegistration | None = None,
    anti_rollback_resolver: AntiRollbackTrustResolver | None = None,
) -> TraceabilityGateResult:
    """Atomically authorize exactly one privately validated release candidate."""
    if publication_store is not None:
        if publication_store is not watermark_store:
            return TraceabilityGateUnavailable(reason="persistence_outcome_indeterminate")
        if not allow_test_file_fence:
            backend = publication_store.anti_rollback_backend_identity()
            if (
                verified_anti_rollback_registration is None
                or anti_rollback_resolver is None
                or not anti_rollback_resolver.verify(
                    verified_anti_rollback_registration, publication_store, backend
                )
            ):
                return TraceabilityGateUnavailable(
                    reason="verified_anti_rollback_registration_required"
                )
        if (
            not isinstance(release_artifact, bytes)
            or not isinstance(release_history_artifact, bytes)
            or not isinstance(active_pointer_artifact, bytes)
            or not isinstance(pointer_history_artifact, bytes)
        ):
            return TraceabilityGateUnavailable(reason="release_publication_inputs_unavailable")
        return publication_store.compare_fence_and_publish(
            watermark_store=watermark_store,
            epoch=candidate.epoch,
            sequence=candidate.sequence,
            release_digest=candidate.release_digest,
            release_artifact=release_artifact,
            release_history_artifact=release_history_artifact,
            active_pointer_artifact=active_pointer_artifact,
            pointer_history_artifact=pointer_history_artifact,
        )
    watermark_result = watermark_store.compare_and_advance(
        candidate.epoch, candidate.sequence, candidate.release_digest
    )
    if isinstance(watermark_result, WatermarkUnavailable):
        return TraceabilityGateUnavailable(reason=watermark_result.reason)
    if isinstance(watermark_result, WatermarkRejected):
        return TraceabilityGateRejected(reason=watermark_result.reason)
    if not isinstance(watermark_result, WatermarkAdvanced):
        return TraceabilityGateUnavailable(reason="watermark_store_indeterminate")
    return _candidate_authorization(candidate)


# Public owner-module names for the execution boundary. The implementation
# remains centralized here; consumers must not import cross-module privates.
VerifiedReleaseCandidate = _VerifiedReleaseCandidate
validate_release_candidate = _validate_release_candidate
candidate_authorization = _candidate_authorization
commit_verified_release = _commit_verified_release


def verify_release_gate(
    *,
    registry: TraceabilityRegistry,
    bootstrap_artifact: bytes | None,
    recovery_artifact: bytes | None,
    lifecycle_artifact: bytes | None,
    release_artifact: bytes | None,
    verifier_material: VerifierHeldTrustMaterial | None = None,
    active_pointer_artifact: bytes | None = None,
    release_history_artifact: bytes | None = None,
    historical_release_artifacts: tuple[bytes, ...] = (),
    recovery_artifacts: tuple[bytes, ...] | None = None,
    watermark_store: TraceabilityReleaseWatermarkStore | None = None,
    expected_release_roots: dict[str, str] | None = None,
    now: datetime | None = None,
) -> TraceabilityGateResult:
    """Authorize only a corrected, exact-binding CTV-v2 release generation.

    Retained raw/projection bytes are observable through
    :func:`read_legacy_release_diagnostic`; they cannot reach a watermark
    operation through this public authorization boundary.
    """
    ctv_inputs = (
        bootstrap_artifact,
        recovery_artifact,
        lifecycle_artifact,
        release_artifact,
        active_pointer_artifact,
        release_history_artifact,
        *(historical_release_artifacts or ()),
        *(recovery_artifacts or ()),
    )
    public_body_fields = {
        "release": frozenset({
            "release_id", "issuance_purpose", "registry_source_identity", "design_document_digest", "structural_manifest_digest", "grammar_revision", "canonical_profile_binding", "artifact_dag_digest", "requirement_binding_registry_digest", "assertion_registry_digest", "test_evidence_group_registry_digest", "report_schema_registry_digest", "runner_environment_profile_registry_digest", "golden_vector_manifest_digest", "section_default_registry_digest", "structural_mapping_rule_registry_digest", "override_registry_digest", "anchor_binding_registry_digest", "coverage_root_digest", "execution_root_digest", "bootstrap_anchor_id", "bootstrap_anchor_digest", "bootstrap_anchor_history_digest", "bootstrap_rotation_sequence", "recovery_trust_policy_digest", "recovery_policy_history_digest", "recovery_trust_root_digests", "recovery_root_history_digest", "trust_lifecycle_root_digest", "trust_snapshot_digest", "epoch", "sequence", "issued_state", "predecessor_release_id", "supersedes_release_id", "issued_at", "expires_at", "signer_coordinate", "signature", "release_digest",
        }),
        "release_history": frozenset({"history_id", "issuance_purpose", "canonical_profile_binding", "entries", "signer_coordinate", "signature", "release_history_digest"}),
        "active_pointer": frozenset({"pointer_id", "issuance_purpose", "target_authority_id", "canonical_profile_binding", "generation_id", "generation_manifest_digest", "release_id", "release_digest", "release_epoch", "release_sequence", "release_history_digest", "predecessor_pointer_history_digest", "predecessor_active_pointer_digest", "pointer_sequence", "published_at", "signer_coordinate", "signature", "active_pointer_digest"}),
        "lifecycle": frozenset({"authority_id", "issuance_purpose", "canonical_profile_binding", "bootstrap_anchor_history_digest", "recovery_root_history_digest", "recovery_policy_history_digest", "records", "signer_coordinates", "signatures", "lifecycle_root_digest"}),
    }
    named_public_inputs = (
        ("release", release_artifact),
        ("release_history", release_history_artifact),
        ("active_pointer", active_pointer_artifact),
        ("lifecycle", lifecycle_artifact),
    )
    for name, raw in named_public_inputs:
        if raw is None:
            continue
        try:
            artifact = decode_artifact(raw)
            schema_id, binding_digest = _CTV_BODY_BINDINGS[name]
            expected = CanonicalTypedValueProfileBinding(*_CTV_PROFILE, schema_id, 1, binding_digest)
            body = decode_typed_value(artifact.canonical_value_bytes)
            if artifact.binding != expected or not isinstance(body, dict) or set(body) != public_body_fields[name]:
                return TraceabilityGateRejected(reason="legacy_incomplete_provenance")
        except CanonicalTypedValueError:
            return TraceabilityGateRejected(reason="legacy_incomplete_provenance")
    for raw in ctv_inputs:
        if raw is None:
            continue
        try:
            decode_artifact(raw)
        except CanonicalTypedValueError:
            return TraceabilityGateRejected(reason="legacy_incomplete_provenance")
    if verifier_material is not None and verifier_material.recovery_policy_bytes is not None:
        try:
            decode_artifact(verifier_material.recovery_policy_bytes)
        except CanonicalTypedValueError:
            return TraceabilityGateRejected(reason="legacy_incomplete_provenance")
    candidate = _validate_release_candidate(
        registry=registry,
        bootstrap_artifact=bootstrap_artifact,
        recovery_artifact=recovery_artifact,
        lifecycle_artifact=lifecycle_artifact,
        release_artifact=release_artifact,
        verifier_material=verifier_material,
        active_pointer_artifact=active_pointer_artifact,
        release_history_artifact=release_history_artifact,
        historical_release_artifacts=historical_release_artifacts,
        recovery_artifacts=recovery_artifacts,
        expected_release_roots=expected_release_roots,
        now=now,
    )
    if not isinstance(candidate, _VerifiedReleaseCandidate):
        return candidate
    if watermark_store is None:
        return TraceabilityGateUnavailable(reason="watermark_store_unavailable")
    return _commit_verified_release(candidate, watermark_store)
