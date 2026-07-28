"""Fail-closed verification for externally provisioned traceability releases.

This module deliberately accepts bytes, not a convenient object graph.  Trust
anchors and recovery material arrive through a channel independent of the
release channel; no release field is ever allowed to install its own verifier.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from memorii.tools.semantic_ingestion_traceability_registry import (
    CANONICAL_PROFILE,
    TraceabilityRegistry,
    canonical_document,
)


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


TraceabilityGateResult = TraceabilityGateUnavailable | TraceabilityGateRejected | TraceabilityGateAuthorized
SignatureVerifier = Callable[[str, str, bytes, bytes], bool]


@dataclass(frozen=True)
class VerifierHeldTrustMaterial:
    """Immutable verifier input authenticated outside the release channel."""

    bootstrap_anchor_bytes: bytes
    recovery_root_bytes: tuple[bytes, ...]
    verify_signature: SignatureVerifier
    recovery_policy_bytes: bytes | None = None


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
        return {"heading_path_hash": self.heading_path_hash, "approved_requirement_ids": list(self.approved_requirement_ids), "applicable_rule_digests": list(self.applicable_rule_digests), "design_document_digest": self.design_document_digest, "registry_source_identity": self.registry_source_identity, "structural_manifest_digest": self.structural_manifest_digest, "reviewer_id": self.reviewer_id, "issuance_purpose": self.issuance_purpose, "issued_at": self.issued_at.isoformat(), "trust_snapshot_digest": self.trust_snapshot_digest, "expires_at": self.expires_at.isoformat() if self.expires_at else None, "signature_profile_id": self.signature_profile_id, "reviewer_key_digest": self.reviewer_key_digest}


def _digest(domain: bytes, body: bytes) -> str:
    return sha256(domain + b"\0" + body).hexdigest()


def _load(raw: bytes, name: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{name}_invalid_json") from exc
    if not isinstance(value, dict) or canonical_document(value) != raw:
        raise ValueError(f"{name}_not_canonical")
    return value


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


def _verify_signed(value: dict[str, Any], *, purpose: str, digest_field: str, domain: bytes, verifier: SignatureVerifier) -> str:
    if value.get("issuance_purpose") != purpose or value.get("canonical_profile_id") != CANONICAL_PROFILE:
        raise ValueError("wrong_purpose_or_profile")
    digest = _digest(domain, _body(value, "signature", digest_field))
    if value.get(digest_field) != digest:
        raise ValueError("content_digest_mismatch")
    profile = value.get("signature_profile_id")
    key = value.get("public_key_or_root_certificate_digest") or value.get("policy_signer_key_or_certificate_digest")
    if not isinstance(profile, str) or not isinstance(key, str):
        raise ValueError("signature_binding_invalid")
    _signature(value.get("signature"), profile=profile, key=key, payload=digest.encode("ascii"), verifier=verifier)
    return digest


def verify_coverage_root(*, approvals: tuple[CoverageApproval, ...], heading_requirements: dict[str, tuple[str, ...]], heading_rule_digests: dict[str, tuple[str, ...]], design_document_digest: str, registry_source_identity: str, structural_manifest_digest: str, trusted_reviewer_keys: dict[str, tuple[str, str]], verifier: SignatureVerifier, now: datetime) -> str:
    if now.tzinfo is None or set(heading_requirements) != set(heading_rule_digests):
        raise ValueError("coverage_inputs_invalid")
    by_heading = {approval.heading_path_hash: approval for approval in approvals}
    if len(by_heading) != len(approvals) or set(by_heading) != set(heading_requirements):
        raise ValueError("coverage_approval_set_is_not_exact")
    bodies: list[dict[str, Any]] = []
    for heading, approval in sorted(by_heading.items()):
        if approval.issuance_purpose != "semantic_ingestion_traceability_coverage" or tuple(sorted(approval.approved_requirement_ids)) != tuple(sorted(heading_requirements[heading])) or tuple(sorted(approval.applicable_rule_digests)) != tuple(sorted(heading_rule_digests[heading])):
            raise ValueError("coverage_binding_invalid")
        if (approval.design_document_digest, approval.registry_source_identity, approval.structural_manifest_digest) != (design_document_digest, registry_source_identity, structural_manifest_digest) or (approval.expires_at is not None and approval.expires_at < now):
            raise ValueError("coverage_root_binding_invalid")
        if trusted_reviewer_keys.get(approval.reviewer_id) != (approval.signature_profile_id, approval.reviewer_key_digest):
            raise ValueError("coverage_reviewer_not_lifecycle_eligible")
        digest = _digest(b"memorii:sia-traceability-coverage-approval:v1", canonical_document(approval.body()))
        if digest != approval.approval_digest:
            raise ValueError("coverage_digest_invalid")
        if not verifier(approval.signature_profile_id, approval.reviewer_key_digest, digest.encode("ascii"), approval.signature):
            raise ValueError("coverage_signature_invalid")
        bodies.append({**approval.body(), "approval_digest": digest, "signature": approval.signature.hex()})
    return _digest(b"memorii:sia-traceability-coverage-root:v1", canonical_document({"structural_manifest_digest": structural_manifest_digest, "approvals": bodies}))


def _anchor_key(anchor: dict[str, Any]) -> tuple[str, str]:
    profile, key = anchor.get("signature_profile_id"), anchor.get("public_key_or_root_certificate_digest")
    if not isinstance(profile, str) or not isinstance(key, str):
        raise ValueError("anchor_key_invalid")
    return profile, key


def _validate_lifecycle(root: dict[str, Any], *, authority_id: str, bootstrap: dict[str, Any], recovery_policy: dict[str, Any], recovery_roots: dict[str, dict[str, Any]], verifier: SignatureVerifier, now: datetime) -> tuple[str, str]:
    if root.get("authority_id") != authority_id or not isinstance(root.get("records"), list) or not root["records"]:
        raise ValueError("lifecycle_root_invalid")
    root_body = _body(root, "lifecycle_root_digest", "signature")
    root_digest = _digest(b"memorii:sia-traceability-trust-lifecycle-root:v1", root_body)
    if root.get("lifecycle_root_digest") != root_digest:
        raise ValueError("lifecycle_root_digest_invalid")
    anchor_profile, anchor_key = _anchor_key(bootstrap)
    _signature(root.get("signature"), profile=anchor_profile, key=anchor_key, payload=root_digest.encode("ascii"), verifier=verifier)
    policy_digest = _verify_signed(recovery_policy, purpose="semantic_ingestion_traceability_recovery_policy", digest_field="recovery_policy_digest", domain=b"memorii:sia-traceability-recovery-policy:v1", verifier=verifier)
    if recovery_policy.get("active_bootstrap_anchor_digest") != bootstrap.get("anchor_digest"):
        raise ValueError("recovery_policy_anchor_binding_invalid")
    eligible_roots = recovery_policy.get("eligible_recovery_root_digests")
    threshold = recovery_policy.get("threshold")
    if not isinstance(eligible_roots, list) or len(eligible_roots) != len(set(eligible_roots)) or not isinstance(threshold, int) or threshold < 1 or threshold > len(eligible_roots):
        raise ValueError("recovery_policy_invalid")
    if set(eligible_roots) != set(recovery_roots):
        raise ValueError("recovery_roots_not_independently_provisioned")
    active: dict[tuple[str, str], tuple[str, str, datetime]] = {(str(bootstrap.get("anchor_id", "bootstrap")), str(bootstrap.get("anchor_digest"))): (anchor_profile, anchor_key, datetime.min.replace(tzinfo=UTC))}
    previous_digest: str | None = None
    previous_recorded: datetime | None = None
    seen_coordinates: set[tuple[int, str, str]] = set()
    for sequence, record in enumerate(root["records"], start=1):
        if not isinstance(record, dict) or record.get("issuance_purpose") != "semantic_ingestion_traceability_trust_lifecycle" or record.get("sequence") != sequence or record.get("predecessor_record_digest") != previous_digest:
            raise ValueError("lifecycle_sequence_or_predecessor_invalid")
        effective, recorded = _time(record.get("effective_at"), "lifecycle"), _time(record.get("recorded_at"), "lifecycle")
        if effective > recorded or (previous_recorded is not None and (recorded <= previous_recorded or effective < previous_recorded)):
            raise ValueError("lifecycle_time_rollback")
        action, target_id, target_digest = record.get("action"), record.get("target_id"), record.get("target_digest")
        coordinate = (sequence, str(target_id), str(target_digest))
        if action not in {"activate", "rotate", "revoke", "compromise", "recover"} or not isinstance(target_id, str) or not isinstance(target_digest, str) or coordinate in seen_coordinates:
            raise ValueError("lifecycle_action_invalid")
        seen_coordinates.add(coordinate)
        record_digest = _digest(b"memorii:sia-traceability-lifecycle-record:v1", _body(record, "record_digest", "signatures"))
        if record.get("record_digest") != record_digest:
            raise ValueError("lifecycle_record_digest_invalid")
        bindings, signatures = record.get("signer_bindings"), record.get("signatures")
        if not isinstance(bindings, list) or not isinstance(signatures, list) or len(bindings) != len(signatures) or not bindings:
            raise ValueError("lifecycle_signatures_invalid")
        signer_ids: set[str] = set()
        authorized = 0
        for binding, signature in zip(bindings, signatures, strict=True):
            if not isinstance(binding, dict) or not isinstance(binding.get("signer_id"), str) or not isinstance(binding.get("signature_profile_id"), str) or not isinstance(binding.get("key_digest"), str) or binding["signer_id"] in signer_ids:
                raise ValueError("lifecycle_signer_binding_invalid")
            signer_ids.add(binding["signer_id"])
            profile, key = binding["signature_profile_id"], binding["key_digest"]
            if action == "recover":
                recovery = next((root for root in recovery_roots.values() if _anchor_key(root) == (profile, key)), None)
                if recovery is not None:
                    authorized += 1
            elif any(value[:2] == (profile, key) and value[2] <= effective for value in active.values()):
                authorized += 1
            _signature(signature, profile=profile, key=key, payload=record_digest.encode("ascii"), verifier=verifier)
        if (action == "recover" and authorized != threshold) or (action != "recover" and authorized != 1):
            raise ValueError("lifecycle_signer_not_eligible")
        replacement_id, replacement_digest = record.get("replacement_target_id"), record.get("replacement_target_digest")
        if action in {"rotate", "recover"}:
            if not isinstance(replacement_id, str) or not isinstance(replacement_digest, str):
                raise ValueError("lifecycle_replacement_missing")
            if action == "recover" and replacement_digest == target_digest:
                raise ValueError("recovery_self_authorization")
            active.pop((target_id, target_digest), None)
            active[(replacement_id, replacement_digest)] = (anchor_profile, anchor_key, effective)
        elif action in {"revoke", "compromise"}:
            if replacement_id is not None or replacement_digest is not None:
                raise ValueError("terminal_lifecycle_action_has_replacement")
            active.pop((target_id, target_digest), None)
        elif action == "activate":
            active[(target_id, target_digest)] = (anchor_profile, anchor_key, effective)
        previous_digest, previous_recorded = record_digest, recorded
    if not active:
        raise ValueError("lifecycle_has_no_active_authority")
    return policy_digest, root_digest


def _required_roots(registry: TraceabilityRegistry) -> dict[str, str]:
    roots = {"registry_source_identity": registry.source_identity, **{f"{name}_digest": digest for name, digest in registry.root_digests.items()}}
    # These are content-addressed release inputs.  Their exact values are external,
    # but omission is never an acceptable release.
    for field in ("design_document_digest", "structural_manifest_digest", "coverage_root_digest", "execution_root_digest", "report_schema_registry_digest", "runner_environment_profile_registry_digest", "trust_snapshot_digest"):
        roots[field] = ""
    return roots


def verify_active_release_pointer(*, releases: tuple[dict[str, Any], ...], active_pointer: dict[str, Any], required_roots: dict[str, str], verifier: SignatureVerifier | None = None) -> dict[str, Any]:
    by_id = {item.get("release_id"): item for item in releases}
    if len(by_id) != len(releases) or not all(isinstance(key, str) for key in by_id):
        raise ValueError("release_ids_invalid")
    ordered = sorted(releases, key=lambda item: (item.get("epoch"), item.get("sequence")))
    prior: dict[str, Any] | None = None
    for release in ordered:
        if not isinstance(release.get("epoch"), int) or not isinstance(release.get("sequence"), int) or any(not isinstance(release.get(key), str) or (value and release[key] != value) for key, value in required_roots.items()):
            raise ValueError("release_root_binding_invalid")
        if prior is None:
            if release.get("predecessor_release_id") is not None:
                raise ValueError("genesis_release_has_predecessor")
        elif release.get("predecessor_release_id") != prior.get("release_id") or release["epoch"] < prior["epoch"] or (release["epoch"] == prior["epoch"] and release["sequence"] != prior["sequence"] + 1):
            raise ValueError("release_successor_or_rollback_invalid")
        prior = release
    if prior is None or any(active_pointer.get(key) != prior.get(key) for key in ("release_id", "release_digest", "epoch", "sequence")):
        raise ValueError("active_pointer_is_not_current_release")
    if verifier is not None:
        digest = _digest(b"memorii:sia-traceability-active-release-pointer:v1", _body(active_pointer, "active_pointer_digest", "signature"))
        if active_pointer.get("active_pointer_digest") != digest:
            raise ValueError("active_pointer_digest_invalid")
        profile, key = active_pointer.get("signature_profile_id"), active_pointer.get("issuer_key_or_certificate_digest")
        if not isinstance(profile, str) or not isinstance(key, str):
            raise ValueError("active_pointer_signature_binding_invalid")
        _signature(active_pointer.get("signature"), profile=profile, key=key, payload=digest.encode("ascii"), verifier=verifier)
    return prior


def verify_release_gate(*, registry: TraceabilityRegistry, bootstrap_artifact: bytes | None, recovery_artifact: bytes | None, lifecycle_artifact: bytes | None, release_artifact: bytes | None, verifier_material: VerifierHeldTrustMaterial | None = None, active_pointer_artifact: bytes | None = None, now: datetime | None = None) -> TraceabilityGateResult:
    for name, artifact in (("bootstrap", bootstrap_artifact), ("recovery", recovery_artifact), ("lifecycle", lifecycle_artifact), ("release", release_artifact)):
        if artifact is None:
            return TraceabilityGateUnavailable(reason=f"{name}_unavailable")
    if verifier_material is None or verifier_material.recovery_policy_bytes is None:
        return TraceabilityGateUnavailable(reason="verifier_trust_material_unavailable")
    verification_time = now or datetime.now(UTC)
    if verification_time.tzinfo is None:
        return TraceabilityGateRejected(reason="verification_time_naive")
    # Bind each parser input after an explicit guard; optional transport values
    # never reach the canonical-byte parser.
    if bootstrap_artifact is None or recovery_artifact is None or lifecycle_artifact is None or release_artifact is None:
        return TraceabilityGateUnavailable(reason="artifact_unavailable")
    bootstrap_bytes = bootstrap_artifact
    recovery_bytes = recovery_artifact
    lifecycle_bytes = lifecycle_artifact
    release_bytes = release_artifact
    try:
        if bootstrap_bytes != verifier_material.bootstrap_anchor_bytes or recovery_bytes not in verifier_material.recovery_root_bytes:
            raise ValueError("trust_not_independently_provisioned")
        bootstrap, recovery, lifecycle, release = (_load(bootstrap_bytes, "bootstrap"), _load(recovery_bytes, "recovery"), _load(lifecycle_bytes, "lifecycle"), _load(release_bytes, "release"))
        anchor_digest = _verify_signed(bootstrap, purpose="semantic_ingestion_traceability_release_root", digest_field="anchor_digest", domain=b"memorii:sia-traceability-bootstrap-anchor:v1", verifier=verifier_material.verify_signature)
        recovery_digest = _verify_signed(recovery, purpose="semantic_ingestion_traceability_recovery_root", digest_field="recovery_root_digest", domain=b"memorii:sia-traceability-recovery-root:v1", verifier=verifier_material.verify_signature)
        authority_id = bootstrap.get("target_authority_id")
        if not isinstance(authority_id, str):
            raise ValueError("bootstrap_authority_invalid")
        policy = _load(verifier_material.recovery_policy_bytes, "recovery_policy")
        _validate_lifecycle(lifecycle, authority_id=authority_id, bootstrap=bootstrap, recovery_policy=policy, recovery_roots={recovery_digest: recovery}, verifier=verifier_material.verify_signature, now=verification_time.astimezone(UTC))
        if release.get("issuance_purpose") != "semantic_ingestion_traceability_release" or release.get("canonical_profile_id") != CANONICAL_PROFILE or release.get("state") != "active":
            raise ValueError("release_purpose_or_lifecycle_invalid")
        required = _required_roots(registry)
        if any(not isinstance(release.get(name), str) or (value and release[name] != value) for name, value in required.items()):
            raise ValueError("release_root_binding_invalid")
        if release.get("bootstrap_anchor_digest") != anchor_digest or release.get("recovery_root_digest") != recovery_digest or release.get("predecessor_release_id") is not None or release.get("supersedes_release_id") is not None:
            raise ValueError("release_trust_or_genesis_invalid")
        issued = _time(release.get("issued_at"), "release")
        expires = release.get("expires_at")
        if issued > verification_time.astimezone(UTC) or (expires is not None and _time(expires, "release") < verification_time.astimezone(UTC)):
            raise ValueError("release_time_window_invalid")
        release_digest = _digest(b"memorii:sia-traceability-release:v1", _body(release, "release_digest", "signature"))
        if release.get("release_digest") != release_digest:
            raise ValueError("release_digest_invalid")
        profile, key = release.get("signature_profile_id"), release.get("issuer_key_or_certificate_digest")
        if not isinstance(profile, str) or not isinstance(key, str):
            raise ValueError("release_signature_binding_invalid")
        _signature(release.get("signature"), profile=profile, key=key, payload=release_digest.encode("ascii"), verifier=verifier_material.verify_signature)
        if active_pointer_artifact is not None:
            pointer = _load(active_pointer_artifact, "active_pointer")
            verify_active_release_pointer(releases=(release,), active_pointer=pointer, required_roots=required, verifier=verifier_material.verify_signature)
        return TraceabilityGateAuthorized(release_id=str(release["release_id"]), release_digest=release_digest)
    except (KeyError, TypeError, ValueError) as exc:
        return TraceabilityGateRejected(reason=str(exc))
