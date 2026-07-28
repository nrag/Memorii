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
    root_bindings: dict[str, str] | None = None


TraceabilityGateResult = TraceabilityGateUnavailable | TraceabilityGateRejected | TraceabilityGateAuthorized
SignatureVerifier = Callable[[str, str, bytes, bytes], bool]


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


@dataclass
class TraceabilityReleaseWatermark:
    """Acceptance-owned monotonic coordinate for the active release channel."""

    epoch: int = 0
    sequence: int = 0
    release_digest: str | None = None


@dataclass(frozen=True)
class AcceptanceTrustStore:
    """Composition-owned trust channel; it is deliberately not request data."""

    material: VerifierHeldTrustMaterial
    watermark: TraceabilityReleaseWatermark


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


def _root_coordinate(root: dict[str, Any]) -> tuple[str, str, str, str, str]:
    """Return the independently authenticated root coordinate and signer."""
    if "anchor_digest" in root:
        root_id, digest, kind = root.get("anchor_id"), root.get("anchor_digest"), "bootstrap_anchor"
    else:
        root_id, digest, kind = root.get("recovery_root_id"), root.get("recovery_root_digest"), "recovery_root"
    profile, key = _anchor_key(root)
    if not isinstance(root_id, str) or not isinstance(digest, str):
        raise ValueError("provisioned_root_coordinate_invalid")
    return kind, root_id, digest, profile, key


def _root_window(root: dict[str, Any]) -> tuple[datetime, datetime | None]:
    effective = _time(root["effective_at"], "provisioned_root") if "effective_at" in root else datetime.min.replace(tzinfo=UTC)
    expires = _time(root["expires_at"], "provisioned_root") if root.get("expires_at") is not None else None
    if expires is not None and expires < effective:
        raise ValueError("provisioned_root_time_window_invalid")
    return effective, expires


def _validate_lifecycle(root: dict[str, Any], *, authority_id: str, bootstrap: dict[str, Any], recovery_policy: dict[str, Any], recovery_roots: dict[str, dict[str, Any]], provisioned_roots: dict[tuple[str, str], dict[str, Any]], verifier: SignatureVerifier, now: datetime) -> tuple[str, str, dict[tuple[str, str], tuple[str, str, datetime, datetime | None]]]:
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
    bootstrap_coordinate = (str(bootstrap.get("anchor_id", "bootstrap")), str(bootstrap.get("anchor_digest")))
    if bootstrap_coordinate not in provisioned_roots:
        raise ValueError("bootstrap_not_independently_provisioned")
    initial_start, initial_expiry = _root_window(bootstrap)
    active: dict[tuple[str, str], tuple[str, str, datetime, datetime | None]] = {
        bootstrap_coordinate: (anchor_profile, anchor_key, initial_start, initial_expiry)
    }
    # Recovery roots are a purpose-separated channel: they are never ordinary
    # release/pointer/policy signers.  They can authorize only ``recover``.
    recovery_active: dict[tuple[str, str], tuple[str, str, datetime, datetime | None]] = {}
    for digest, recovery in recovery_roots.items():
        kind, root_id, _, profile, key = _root_coordinate(recovery)
        if kind != "recovery_root":
            raise ValueError("recovery_root_kind_invalid")
        start, expiry = _root_window(recovery)
        recovery_active[(root_id, digest)] = (profile, key, start, expiry)
    intervals: dict[tuple[str, str], tuple[str, str, datetime, datetime | None]] = dict(active)
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
        eligible_recovery_digests: set[str] = set()
        authorized = 0
        for binding, signature in zip(bindings, signatures, strict=True):
            if not isinstance(binding, dict) or not isinstance(binding.get("signer_id"), str) or not isinstance(binding.get("signature_profile_id"), str) or not isinstance(binding.get("key_digest"), str) or binding["signer_id"] in signer_ids:
                raise ValueError("lifecycle_signer_binding_invalid")
            signer_ids.add(binding["signer_id"])
            profile, key = binding["signature_profile_id"], binding["key_digest"]
            if action == "recover":
                root_digest = binding.get("recovery_root_digest")
                recovery = recovery_roots.get(root_digest) if isinstance(root_digest, str) else None
                if recovery is None or root_digest not in eligible_roots:
                    raise ValueError("recovery_signer_root_not_policy_listed")
                if not isinstance(root_digest, str):
                    raise ValueError("recovery_signer_root_binding_invalid")
                kind, root_id, _, root_profile, root_key = _root_coordinate(recovery)
                if kind != "recovery_root" or (root_profile, root_key) != (profile, key):
                    raise ValueError("recovery_signer_root_binding_invalid")
                root_interval = recovery_active.get((root_id, root_digest))
                if root_interval is None or not _interval_contains(root_interval, effective):
                    raise ValueError("recovery_root_not_lifecycle_eligible")
                if root_digest in eligible_recovery_digests:
                    raise ValueError("recovery_root_duplicate_signature")
                eligible_recovery_digests.add(root_digest)
                authorized += 1
            elif any(value[:2] == (profile, key) and _interval_contains(value, effective) for value in active.values()):
                authorized += 1
            _signature(signature, profile=profile, key=key, payload=record_digest.encode("ascii"), verifier=verifier)
        if action == "recover":
            policy_effective = _time(recovery_policy["effective_at"], "recovery_policy") if "effective_at" in recovery_policy else datetime.min.replace(tzinfo=UTC)
            policy_expiry = _time(recovery_policy["expires_at"], "recovery_policy") if recovery_policy.get("expires_at") is not None else None
            policy_key = recovery_policy.get("policy_signer_key_or_certificate_digest")
            policy_profile = recovery_policy.get("signature_profile_id")
            if not isinstance(policy_key, str) or not isinstance(policy_profile, str) or policy_effective > effective or (policy_expiry is not None and effective > policy_expiry) or not any(value[:2] == (policy_profile, policy_key) and _interval_contains(value, effective) for value in active.values()):
                raise ValueError("recovery_policy_not_lifecycle_eligible")
        if (action == "recover" and (authorized != threshold or len(eligible_recovery_digests) != threshold)) or (action != "recover" and authorized != 1):
            raise ValueError("lifecycle_signer_not_eligible")
        replacement_id, replacement_digest = record.get("replacement_target_id"), record.get("replacement_target_digest")
        target_active = active.get((target_id, target_digest))
        recovery_target = recovery_active.get((target_id, target_digest))
        if action in {"rotate", "recover", "revoke", "compromise"} and target_active is None and recovery_target is None:
            raise ValueError("lifecycle_target_not_active")
        if action in {"rotate", "recover"}:
            if not isinstance(replacement_id, str) or not isinstance(replacement_digest, str):
                raise ValueError("lifecycle_replacement_missing")
            if action == "recover" and replacement_digest == target_digest:
                raise ValueError("recovery_self_authorization")
            replacement = provisioned_roots.get((replacement_id, replacement_digest))
            if replacement is None:
                raise ValueError("lifecycle_replacement_not_independently_provisioned")
            replacement_kind, _, _, replacement_profile, replacement_key = _root_coordinate(replacement)
            if replacement_kind != "bootstrap_anchor" or replacement_id == target_id or replacement_digest == target_digest:
                raise ValueError("lifecycle_replacement_invalid")
            replacement_start, replacement_expiry = _root_window(replacement)
            if replacement_start > effective or (replacement_expiry is not None and replacement_expiry < effective):
                raise ValueError("lifecycle_replacement_time_invalid")
            if target_active is not None:
                active[(target_id, target_digest)] = (target_active[0], target_active[1], target_active[2], effective)
                intervals[(target_id, target_digest)] = active[(target_id, target_digest)]
                active.pop((target_id, target_digest))
            elif recovery_target is not None:
                recovery_active[(target_id, target_digest)] = (recovery_target[0], recovery_target[1], recovery_target[2], effective)
                recovery_active.pop((target_id, target_digest))
            successor = (replacement_profile, replacement_key, effective, replacement_expiry)
            active[(replacement_id, replacement_digest)] = successor
            intervals[(replacement_id, replacement_digest)] = successor
        elif action in {"revoke", "compromise"}:
            if replacement_id is not None or replacement_digest is not None:
                raise ValueError("terminal_lifecycle_action_has_replacement")
            if target_active is not None:
                active[(target_id, target_digest)] = (target_active[0], target_active[1], target_active[2], effective)
                intervals[(target_id, target_digest)] = active[(target_id, target_digest)]
                active.pop((target_id, target_digest))
            elif recovery_target is not None:
                recovery_active[(target_id, target_digest)] = (recovery_target[0], recovery_target[1], recovery_target[2], effective)
                recovery_active.pop((target_id, target_digest))
        elif action == "activate":
            target = provisioned_roots.get((target_id, target_digest))
            # Genesis records authenticate the already independently
            # provisioned bootstrap coordinate; later activation cannot reuse
            # an existing coordinate.
            if sequence == 1 and (target_id, target_digest) == bootstrap_coordinate:
                previous_digest, previous_recorded = record_digest, recorded
                continue
            if target is None or (target_id, target_digest) in intervals:
                raise ValueError("lifecycle_activation_not_independently_provisioned")
            _, _, _, target_profile, target_key = _root_coordinate(target)
            target_start, target_expiry = _root_window(target)
            if target_start > effective or (target_expiry is not None and target_expiry < effective):
                raise ValueError("lifecycle_activation_time_invalid")
            active[(target_id, target_digest)] = (target_profile, target_key, effective, target_expiry)
            intervals[(target_id, target_digest)] = active[(target_id, target_digest)]
        previous_digest, previous_recorded = record_digest, recorded
    if not active:
        raise ValueError("lifecycle_has_no_active_authority")
    if not isinstance(policy_digest, str) or not isinstance(root_digest, str):
        raise ValueError("lifecycle_digest_invalid")
    return policy_digest, root_digest, intervals


def _interval_contains(interval: tuple[str, str, datetime, datetime | None], when: datetime) -> bool:
    return interval[2] <= when and (interval[3] is None or when < interval[3])


def _active_signer_or_reject(
    *, active: dict[tuple[str, str], tuple[str, str, datetime, datetime | None]], profile: object, key: object, issued_at: datetime, purpose: object
) -> None:
    """Keep approval signatures inside the replayed active trust interval."""
    if purpose != "semantic_ingestion_traceability_release" or not isinstance(profile, str) or not isinstance(key, str):
        raise ValueError("release_signer_purpose_or_profile_invalid")
    if not any(value[:2] == (profile, key) and _interval_contains(value, issued_at) for value in active.values()):
        raise ValueError("release_signer_not_lifecycle_eligible")


def _required_roots(registry: TraceabilityRegistry) -> dict[str, str]:
    roots = {"registry_source_identity": registry.source_identity, **{f"{name}_digest": digest for name, digest in registry.root_digests.items()}}
    # These are content-addressed release inputs.  Their exact values are external,
    # but omission is never an acceptable release.
    for field in ("design_document_digest", "structural_manifest_digest", "coverage_root_digest", "execution_root_digest", "report_schema_registry_digest", "runner_environment_profile_registry_digest", "trust_snapshot_digest"):
        roots[field] = ""
    return roots


def verify_active_release_pointer(*, releases: tuple[dict[str, Any], ...], active_pointer: dict[str, Any], required_roots: dict[str, str], verifier: SignatureVerifier | None = None, active_signers: dict[tuple[str, str], tuple[str, str, datetime, datetime | None]] | None = None, now: datetime | None = None) -> dict[str, Any]:
    by_id = {item.get("release_id"): item for item in releases}
    if len(by_id) != len(releases) or not all(isinstance(key, str) for key in by_id):
        raise ValueError("release_ids_invalid")
    coordinates = [(item.get("epoch"), item.get("sequence")) for item in releases]
    if len(coordinates) != len(set(coordinates)):
        raise ValueError("release_coordinate_substitution_or_duplicate")
    ordered = sorted(releases, key=lambda item: (item.get("epoch"), item.get("sequence")))
    prior: dict[str, Any] | None = None
    for release in ordered:
        if not isinstance(release.get("epoch"), int) or release["epoch"] < 1 or not isinstance(release.get("sequence"), int) or release["sequence"] < 1 or release.get("state") not in {"active", "superseded", "revoked", "compromised"} or any(not isinstance(release.get(key), str) or (value and release[key] != value) for key, value in required_roots.items()):
            raise ValueError("release_root_binding_invalid")
        if prior is None:
            if release.get("predecessor_release_id") is not None:
                raise ValueError("genesis_release_has_predecessor")
        elif release.get("predecessor_release_id") != prior.get("release_id") or release["epoch"] < prior["epoch"] or (release["epoch"] == prior["epoch"] and release["sequence"] != prior["sequence"] + 1):
            raise ValueError("release_successor_or_rollback_invalid")
        elif release.get("supersedes_release_id") is not None and release.get("supersedes_release_id") != prior.get("release_id"):
            raise ValueError("release_rollback_must_explicitly_supersede_active_predecessor")
        prior = release
    if sum(item.get("state") == "active" for item in ordered) != 1:
        raise ValueError("release_history_must_have_exactly_one_active_release")
    if prior is None or prior.get("state") != "active" or any(active_pointer.get(key) != prior.get(key) for key in ("release_id", "release_digest", "epoch", "sequence")):
        raise ValueError("active_pointer_is_not_current_release")
    if verifier is not None:
        digest = _digest(b"memorii:sia-traceability-active-release-pointer:v1", _body(active_pointer, "active_pointer_digest", "signature"))
        if active_pointer.get("active_pointer_digest") != digest:
            raise ValueError("active_pointer_digest_invalid")
        profile, key = active_pointer.get("signature_profile_id"), active_pointer.get("issuer_key_or_certificate_digest")
        if not isinstance(profile, str) or not isinstance(key, str):
            raise ValueError("active_pointer_signature_binding_invalid")
        _signature(active_pointer.get("signature"), profile=profile, key=key, payload=digest.encode("ascii"), verifier=verifier)
        if active_signers is not None:
            pointer_time = _time(active_pointer.get("issued_at"), "active_pointer") if "issued_at" in active_pointer else (now or datetime.now(UTC))
            if not any(value[:2] == (profile, key) and _interval_contains(value, pointer_time) for value in active_signers.values()):
                raise ValueError("active_pointer_signer_not_lifecycle_eligible")
    return prior


def verify_release_gate(*, registry: TraceabilityRegistry, bootstrap_artifact: bytes | None, recovery_artifact: bytes | None, lifecycle_artifact: bytes | None, release_artifact: bytes | None, verifier_material: VerifierHeldTrustMaterial | None = None, active_pointer_artifact: bytes | None = None, release_history_artifact: bytes | None = None, recovery_artifacts: tuple[bytes, ...] | None = None, watermark: TraceabilityReleaseWatermark | None = None, now: datetime | None = None) -> TraceabilityGateResult:
    for name, artifact in (("bootstrap", bootstrap_artifact), ("recovery", recovery_artifact), ("lifecycle", lifecycle_artifact), ("release", release_artifact), ("active_pointer", active_pointer_artifact), ("release_history", release_history_artifact)):
        if artifact is None:
            return TraceabilityGateUnavailable(reason=f"{name}_unavailable")
    if verifier_material is None or verifier_material.recovery_policy_bytes is None:
        return TraceabilityGateUnavailable(reason="verifier_trust_material_unavailable")
    verification_time = now or datetime.now(UTC)
    if verification_time.tzinfo is None:
        return TraceabilityGateRejected(reason="verification_time_naive")
    # Bind each parser input after an explicit guard; optional transport values
    # never reach the canonical-byte parser.
    if bootstrap_artifact is None or recovery_artifact is None or lifecycle_artifact is None or release_artifact is None or active_pointer_artifact is None or release_history_artifact is None:
        return TraceabilityGateUnavailable(reason="artifact_unavailable")
    bootstrap_bytes = bootstrap_artifact
    recovery_bytes = recovery_artifact
    lifecycle_bytes = lifecycle_artifact
    release_bytes = release_artifact
    try:
        supplied_recovery_bytes = (recovery_bytes, *(recovery_artifacts or ()))
        if len(supplied_recovery_bytes) != len(set(supplied_recovery_bytes)):
            raise ValueError("recovery_roots_duplicate")
        if bootstrap_bytes != verifier_material.bootstrap_anchor_bytes or set(supplied_recovery_bytes) != set(verifier_material.recovery_root_bytes):
            raise ValueError("trust_not_independently_provisioned")
        bootstrap, lifecycle, release = (_load(bootstrap_bytes, "bootstrap"), _load(lifecycle_bytes, "lifecycle"), _load(release_bytes, "release"))
        anchor_digest = _verify_signed(bootstrap, purpose="semantic_ingestion_traceability_release_root", digest_field="anchor_digest", domain=b"memorii:sia-traceability-bootstrap-anchor:v1", verifier=verifier_material.verify_signature)
        recoveries = [_load(item, "recovery") for item in supplied_recovery_bytes]
        recovery_digests = [_verify_signed(item, purpose="semantic_ingestion_traceability_recovery_root", digest_field="recovery_root_digest", domain=b"memorii:sia-traceability-recovery-root:v1", verifier=verifier_material.verify_signature) for item in recoveries]
        authority_id = bootstrap.get("target_authority_id")
        if not isinstance(authority_id, str):
            raise ValueError("bootstrap_authority_invalid")
        policy = _load(verifier_material.recovery_policy_bytes, "recovery_policy")
        provisioned_documents = [bootstrap, *recoveries]
        for raw in verifier_material.provisioned_successor_root_bytes:
            candidate = _load(raw, "provisioned_successor_root")
            if "anchor_digest" in candidate:
                _verify_signed(candidate, purpose="semantic_ingestion_traceability_release_root", digest_field="anchor_digest", domain=b"memorii:sia-traceability-bootstrap-anchor:v1", verifier=verifier_material.verify_signature)
            else:
                _verify_signed(candidate, purpose="semantic_ingestion_traceability_recovery_root", digest_field="recovery_root_digest", domain=b"memorii:sia-traceability-recovery-root:v1", verifier=verifier_material.verify_signature)
            provisioned_documents.append(candidate)
        provisioned_roots: dict[tuple[str, str], dict[str, Any]] = {}
        for document in provisioned_documents:
            _, root_id, root_digest, _, _ = _root_coordinate(document)
            coordinate = (root_id, root_digest)
            if coordinate in provisioned_roots:
                raise ValueError("provisioned_root_duplicate")
            provisioned_roots[coordinate] = document
        policy_digest, lifecycle_digest, active_signers = _validate_lifecycle(lifecycle, authority_id=authority_id, bootstrap=bootstrap, recovery_policy=policy, recovery_roots=dict(zip(recovery_digests, recoveries, strict=True)), provisioned_roots=provisioned_roots, verifier=verifier_material.verify_signature, now=verification_time.astimezone(UTC))
        if release.get("issuance_purpose") != "semantic_ingestion_traceability_release" or release.get("canonical_profile_id") != CANONICAL_PROFILE or release.get("state") != "active":
            raise ValueError("release_purpose_or_lifecycle_invalid")
        required = _required_roots(registry)
        history_document = _load(release_history_artifact, "release_history")
        if set(history_document) != {"releases"} or not isinstance(history_document["releases"], list):
            raise ValueError("release_history_invalid")
        history = history_document["releases"]
        if not history:
            raise ValueError("release_history_does_not_end_at_release")
        for candidate in history:
            if not isinstance(candidate, dict) or any(not isinstance(candidate.get(name), str) or (value and candidate[name] != value) for name, value in required.items()):
                raise ValueError("release_root_binding_invalid")
            if candidate.get("bootstrap_anchor_digest") != anchor_digest or candidate.get("recovery_root_digest") not in recovery_digests:
                raise ValueError("release_trust_binding_invalid")
            issued = _time(candidate.get("issued_at"), "release")
            expires = candidate.get("expires_at")
            if issued > verification_time.astimezone(UTC) or (expires is not None and _time(expires, "release") < issued):
                raise ValueError("release_time_window_invalid")
            candidate_digest = _digest(b"memorii:sia-traceability-release:v1", _body(candidate, "release_digest", "signature"))
            if candidate.get("release_digest") != candidate_digest:
                raise ValueError("release_digest_invalid")
            profile, key = candidate.get("signature_profile_id"), candidate.get("issuer_key_or_certificate_digest")
            _active_signer_or_reject(active=active_signers, profile=profile, key=key, issued_at=issued, purpose=candidate.get("issuance_purpose"))
            if not isinstance(profile, str) or not isinstance(key, str):
                raise ValueError("release_signature_binding_invalid")
            _signature(candidate.get("signature"), profile=profile, key=key, payload=candidate_digest.encode("ascii"), verifier=verifier_material.verify_signature)
        release_digest = str(release["release_digest"])
        pointer = _load(active_pointer_artifact, "active_pointer")
        current = verify_active_release_pointer(releases=tuple(history), active_pointer=pointer, required_roots=required, verifier=verifier_material.verify_signature, active_signers=active_signers, now=verification_time.astimezone(UTC))
        if current.get("release_digest") != release_digest:
            raise ValueError("release_artifact_is_not_authenticated_current_release")
        current_issued = _time(current.get("issued_at"), "release")
        current_expires = current.get("expires_at")
        if current_issued > verification_time.astimezone(UTC) or (current_expires is not None and verification_time.astimezone(UTC) > _time(current_expires, "release")):
            raise ValueError("current_release_time_window_invalid")
        if watermark is not None:
            coordinate = (int(current["epoch"]), int(current["sequence"]))
            prior = (watermark.epoch, watermark.sequence)
            if coordinate < prior:
                raise ValueError("active_pointer_watermark_rewind")
            if coordinate == prior and watermark.release_digest not in {None, current["release_digest"]}:
                raise ValueError("active_pointer_watermark_substitution")
            watermark.epoch, watermark.sequence, watermark.release_digest = (*coordinate, str(current["release_digest"]))
        return TraceabilityGateAuthorized(
            release_id=str(release["release_id"]),
            release_digest=release_digest,
            root_bindings={name: str(release[name]) for name in required},
        )
    except (KeyError, TypeError, ValueError) as exc:
        return TraceabilityGateRejected(reason=str(exc))
