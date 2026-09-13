"""Acceptance-owned baseline approval verification and immutable receipts.

Only this package sees approval releases, acceptance public keys, and status.
The production deployment issuer receives the verified release digest and stable
target coordinates through a structural port defined here; it never imports
this module.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal, Protocol

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from acceptance.ctv import encode_typed_value
from acceptance.schema_registry import decode_artifact, signing_preimage

_DIGEST = re.compile(r"^[0-9a-f]{64}$")


class ApprovalRejected(ValueError):
    """No verified approval, receipt, or issuance may follow this failure."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _digest_for(domain: bytes, value: object) -> str:
    """Digest canonical acceptance CTV, never an advisory JSON reserialization."""
    return sha256(domain + b"\0" + encode_typed_value(value)).hexdigest()


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ApprovalRejected(label)
    return value


def _digest_text(value: object, label: str) -> str:
    text = _text(value, label)
    if not _DIGEST.fullmatch(text):
        raise ApprovalRejected(label)
    return text


def _time(value: object, label: str) -> datetime:
    text = _text(value, label)
    try:
        result = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ApprovalRejected(label) from exc
    if result.utcoffset() is None:
        raise ApprovalRejected(label)
    return result


@dataclass(frozen=True)
class AcceptanceVerifierLimits:
    maximum_release_bytes: int = 128 * 1024
    maximum_baseline_bytes: int = 128 * 1024
    maximum_receipt_bytes: int = 128 * 1024

    def __post_init__(self) -> None:
        if any(type(value) is not int or value < 1 for value in asdict(self).values()):
            raise ApprovalRejected("acceptance_limits")


@dataclass(frozen=True)
class AcceptanceSigningKey:
    key_reference: str
    public_key: bytes
    valid_from: datetime
    valid_until: datetime | None
    status: Literal["active", "retired", "revoked", "compromised"]

    def __post_init__(self) -> None:
        if not self.key_reference or len(self.public_key) != 32 or self.valid_from.utcoffset() is None:
            raise ApprovalRejected("acceptance_signing_key")
        if self.valid_until is not None and (
            self.valid_until.utcoffset() is None or self.valid_until <= self.valid_from
        ):
            raise ApprovalRejected("acceptance_signing_key_interval")


@dataclass(frozen=True)
class AcceptanceStatus:
    authority_snapshot_digest: str
    active_release_digest: str
    active_epoch: int
    active_sequence: int
    release_digests: tuple[str, ...]

    def __post_init__(self) -> None:
        _digest_text(self.authority_snapshot_digest, "acceptance_status_snapshot")
        _digest_text(self.active_release_digest, "acceptance_status_release")
        if self.active_epoch < 1 or self.active_sequence < 1 or not self.release_digests:
            raise ApprovalRejected("acceptance_status_coordinates")
        if len(set(self.release_digests)) != len(self.release_digests) or self.active_release_digest not in self.release_digests:
            raise ApprovalRejected("acceptance_status_history")
        for value in self.release_digests:
            _digest_text(value, "acceptance_status_history")


@dataclass(frozen=True)
class KeyLifecycleEvent:
    """One immutable, globally ordered acceptance signing-key transition."""

    key_reference: str
    state: Literal["active", "retired", "revoked", "compromised"]
    effective_at: datetime
    global_sequence: int
    predecessor_event_digest: str | None
    event_digest: str

    def __post_init__(self) -> None:
        if not self.key_reference or self.effective_at.utcoffset() is None or self.global_sequence < 1:
            raise ApprovalRejected("acceptance_key_event")
        if self.predecessor_event_digest is not None:
            _digest_text(self.predecessor_event_digest, "acceptance_key_event_predecessor")
        _digest_text(self.event_digest, "acceptance_key_event_digest")


@dataclass(frozen=True)
class AcceptanceApprovalIssuanceSnapshotV1:
    """Committed exact key-event prefix bound to an approval release."""

    snapshot_digest: str
    trust_snapshot_digest: str
    key_events: tuple[KeyLifecycleEvent, ...]
    key_history_head_digest: str
    key_history_head_sequence: int
    signing_key_reference: str

    def __post_init__(self) -> None:
        _digest_text(self.snapshot_digest, "issuance_snapshot_digest")
        _digest_text(self.trust_snapshot_digest, "issuance_snapshot_trust")
        _digest_text(self.key_history_head_digest, "issuance_snapshot_head")
        if not self.signing_key_reference or not self.key_events or self.key_history_head_sequence < 1:
            raise ApprovalRejected("issuance_snapshot_shape")
        _validate_key_event_prefix(self.key_events, self.key_history_head_digest, self.key_history_head_sequence)


@dataclass(frozen=True)
class CurrentAcceptanceCheckpoint:
    """Protected current-head observation used to reject stale history prefixes."""

    authority_snapshot_digest: str
    release_history_head_digest: str
    release_history_head_sequence: int
    key_history_head_digest: str
    key_history_head_sequence: int
    active_release_digest: str
    active_epoch: int
    active_sequence: int
    observed_at: datetime

    def __post_init__(self) -> None:
        for value in (self.authority_snapshot_digest, self.release_history_head_digest, self.key_history_head_digest, self.active_release_digest):
            _digest_text(value, "acceptance_checkpoint_digest")
        if min(self.release_history_head_sequence, self.key_history_head_sequence, self.active_epoch, self.active_sequence) < 1 or self.observed_at.utcoffset() is None:
            raise ApprovalRejected("acceptance_checkpoint_coordinates")


def _validate_key_event_prefix(
    events: tuple[KeyLifecycleEvent, ...], head_digest: str, head_sequence: int
) -> None:
    previous: KeyLifecycleEvent | None = None
    states: dict[str, str] = {}
    for expected_sequence, event in enumerate(events, start=1):
        if event.global_sequence != expected_sequence or event.predecessor_event_digest != (None if previous is None else previous.event_digest):
            raise ApprovalRejected("acceptance_key_event_sequence")
        if previous is not None and (event.effective_at, event.global_sequence) < (previous.effective_at, previous.global_sequence):
            raise ApprovalRejected("acceptance_key_event_order")
        prior = states.get(event.key_reference)
        if event.state == "active":
            if prior is not None:
                raise ApprovalRejected("acceptance_key_event_activation")
        elif prior != "active":
            raise ApprovalRejected("acceptance_key_event_transition")
        states[event.key_reference] = event.state
        previous = event
    if previous is None or previous.event_digest != head_digest or previous.global_sequence != head_sequence:
        raise ApprovalRejected("acceptance_key_event_head")


def _key_is_active(events: tuple[KeyLifecycleEvent, ...], key_reference: str, at: datetime) -> bool:
    relevant = [event for event in events if event.key_reference == key_reference and event.effective_at <= at]
    return bool(relevant) and relevant[-1].state == "active"


class CurrentAcceptanceStatusProvider(Protocol):
    def load_current(self) -> AcceptanceStatus: ...


class AcceptanceAuthorityRepository(CurrentAcceptanceStatusProvider, Protocol):
    """Protected immutable history reader; callers cannot choose its coordinates."""

    def load_issuance_snapshot(
        self, snapshot_digest: str, release_digest: str
    ) -> AcceptanceApprovalIssuanceSnapshotV1 | None: ...

    def load_current_checkpoint(self) -> CurrentAcceptanceCheckpoint: ...

    def load_current_key_history(self) -> tuple[KeyLifecycleEvent, ...]: ...

    def load_current_trust_snapshot(self) -> dict[str, Any]: ...


@dataclass(frozen=True)
class VerifiedCapabilityBaselineApproval:
    release_digest: str
    target_approved_capability_baseline_artifact_digest: str
    acceptance_authority_snapshot_digest: str
    acceptance_release_epoch: int
    capability_fingerprint: str
    capability_contract_digest: str
    coverage_manifest_digest: str
    coverage_release_id: str
    statistical_gate_manifest_digest: str
    sampling_frame_manifest_digest: str
    sampling_frame_digest: str
    independent_cluster_definition_digest: str
    strata_definition_digest: str
    cluster_weighting_digest: str
    numeric_encoding_registry_digest: str
    unsupported_cells_digest: str
    verified_at: datetime
    verification_digest: str


class CapabilityBaselineApprovalVerifier:
    """Verifies a release using constructor-held keys and current status only."""

    def __init__(
        self,
        *,
        keys: tuple[AcceptanceSigningKey, ...],
        authority_repository: AcceptanceAuthorityRepository,
        limits: AcceptanceVerifierLimits | None = None,
    ) -> None:
        if not keys or len({key.key_reference for key in keys}) != len(keys):
            raise ApprovalRejected("acceptance_key_history")
        self._keys = {key.key_reference: key for key in keys}
        self._authority_repository = authority_repository
        self._limits = limits if limits is not None else AcceptanceVerifierLimits()

    def select_snapshot(self, snapshot: object) -> None:
        selector = getattr(self._authority_repository, "select_snapshot", None)
        if not callable(selector):
            raise ApprovalRejected("acceptance_snapshot_authority")
        selector(snapshot)

    def verify(
        self, release_bytes: bytes, baseline_artifact_bytes: bytes, evaluation_time: datetime
    ) -> VerifiedCapabilityBaselineApproval:
        if evaluation_time.utcoffset() is None:
            raise ApprovalRejected("acceptance_evaluation_time")
        # Approval releases are registered authority artifacts.  Decode them
        # through the one schema owner before looking at their business fields;
        # this rejects a legacy digest or a non-canonical wire representation.
        if not isinstance(release_bytes, bytes) or len(release_bytes) > self._limits.maximum_release_bytes:
            raise ApprovalRejected("approval_release_bytes")
        try:
            release = decode_artifact(release_bytes, "CapabilityBaselineApprovalRelease")
        except ValueError as exc:
            raise ApprovalRejected("approval_release_schema") from exc
        try:
            baseline = decode_artifact(baseline_artifact_bytes, "ApprovedCapabilityBaseline")
        except ValueError as exc:
            raise ApprovalRejected("approval_baseline_schema") from exc
        if release["schema_version"] != 2 or release["purpose"] != "semantic_ingestion_capability_baseline_approval.v2":
            raise ApprovalRejected("approval_release_purpose")
        lifecycle = release["lifecycle_state"]
        if (
            lifecycle != "active"
            or release["revoked_at"] is not None
            or release["compromise_effective_at"] is not None
        ):
            raise ApprovalRejected("approval_release_lifecycle")
        issued_at, expires_at = _time(release["issued_at"], "approval_release_issued"), _time(release["expires_at"], "approval_release_expires")
        if expires_at <= issued_at or evaluation_time < issued_at or evaluation_time >= expires_at:
            raise ApprovalRejected("approval_release_interval")
        for name in (
            "approved_baseline_artifact_digest", "capability_contract_digest", "coverage_manifest_digest", "statistical_gate_manifest_digest",
            "sampling_frame_manifest_digest", "sampling_frame_digest", "independent_cluster_definition_digest", "strata_definition_digest",
            "cluster_weighting_digest", "numeric_encoding_registry_digest", "unsupported_cells_digest", "acceptance_authority_snapshot_digest", "release_digest",
        ):
            _digest_text(release[name], name)
        baseline_digest = sha256(baseline_artifact_bytes).hexdigest()
        if release["approved_baseline_artifact_digest"] != baseline_digest:
            raise ApprovalRejected("approval_release_baseline")
        for name in (
            "capability_fingerprint", "capability_contract_digest", "coverage_manifest_digest", "statistical_gate_manifest_digest",
            "sampling_frame_manifest_digest", "sampling_frame_digest", "independent_cluster_definition_digest", "strata_definition_digest",
            "cluster_weighting_digest", "numeric_encoding_registry_digest", "unsupported_cells_digest",
        ):
            if release[name] != baseline[name]:
                raise ApprovalRejected("approval_release_coordinate")
        release_digest = release["release_digest"]
        key_reference = _text(release["acceptance_signing_key_reference"], "approval_release_key")
        key = self._keys.get(key_reference)
        if key is None:
            raise ApprovalRejected("approval_release_key")
        trust = self._authority_repository.load_current_trust_snapshot()
        declarations = trust.get("key_declarations") if type(trust) is dict else None
        if type(declarations) is not list:
            raise ApprovalRejected("acceptance_trust_declarations")
        declared = [item for item in declarations if type(item) is dict and item.get("key_reference") == key_reference]
        if len(declared) != 1:
            raise ApprovalRejected("acceptance_trust_declaration")
        declaration = declared[0]
        try:
            declared_key = bytes.fromhex(str(declaration["public_key"]))
            valid_from = _time(declaration["valid_from"], "acceptance_trust_valid_from")
            valid_until = None if declaration["valid_until"] is None else _time(declaration["valid_until"], "acceptance_trust_valid_until")
            purposes = declaration["allowed_purposes"]
        except (KeyError, TypeError, ValueError) as exc:
            raise ApprovalRejected("acceptance_trust_declaration") from exc
        if (
            declared_key != key.public_key
            or len(declared_key) != 32
            or type(purposes) is not list
            or purposes != sorted(purposes)
            or len(set(purposes)) != len(purposes)
            or "semantic_ingestion_capability_baseline_approval.v2" not in purposes
            or issued_at < valid_from
            or (valid_until is not None and issued_at >= valid_until)
        ):
            raise ApprovalRejected("acceptance_trust_declaration")
        try:
            signature = bytes.fromhex(_text(release["signature"], "approval_release_signature"))
            Ed25519PublicKey.from_public_bytes(key.public_key).verify(
                signature,
                signing_preimage(
                    "CapabilityBaselineApprovalRelease", release, key_reference
                ),
            )
        except (InvalidSignature, ValueError) as exc:
            raise ApprovalRejected("approval_release_signature") from exc
        status = self._authority_repository.load_current()
        if (
            status.authority_snapshot_digest != release["acceptance_authority_snapshot_digest"]
            or status.active_release_digest != release_digest
            or status.active_epoch != release["acceptance_release_epoch"]
            or status.active_sequence != release["acceptance_release_sequence"]
            or release_digest not in status.release_digests
        ):
            raise ApprovalRejected("approval_release_currentness")
        snapshot = self._authority_repository.load_issuance_snapshot(
            release["acceptance_authority_snapshot_digest"], release_digest
        )
        if snapshot is None or snapshot.trust_snapshot_digest != status.authority_snapshot_digest:
            raise ApprovalRejected("approval_release_issuance_snapshot")
        if snapshot.signing_key_reference != key_reference or not _key_is_active(snapshot.key_events, key_reference, issued_at):
            raise ApprovalRejected("approval_release_issuance_authority")
        current_events = self._authority_repository.load_current_key_history()
        _validate_key_event_prefix(current_events, current_events[-1].event_digest, len(current_events))
        if (
            len(current_events) < len(snapshot.key_events)
            or current_events[: len(snapshot.key_events)] != snapshot.key_events
            or not _key_is_active(current_events, key_reference, evaluation_time)
        ):
            raise ApprovalRejected("approval_release_current_key_history")
        checkpoint = self._authority_repository.load_current_checkpoint()
        if (
            checkpoint.authority_snapshot_digest != status.authority_snapshot_digest
            or checkpoint.active_release_digest != status.active_release_digest
            or checkpoint.active_epoch != status.active_epoch
            or checkpoint.active_sequence != status.active_sequence
            or checkpoint.release_history_head_sequence != len(status.release_digests)
            or checkpoint.release_history_head_digest != status.release_digests[-1]
            or checkpoint.key_history_head_sequence != len(current_events)
            or checkpoint.key_history_head_digest != current_events[-1].event_digest
            or checkpoint.observed_at > evaluation_time
        ):
            raise ApprovalRejected("approval_release_checkpoint")
        body = {
            "release_digest": release_digest,
            "target_approved_capability_baseline_artifact_digest": baseline_digest,
            "acceptance_authority_snapshot_digest": status.authority_snapshot_digest,
            "acceptance_release_epoch": status.active_epoch,
            **{name: release[name] for name in (
                "capability_fingerprint", "capability_contract_digest", "coverage_manifest_digest",
                "coverage_release_id", "statistical_gate_manifest_digest", "sampling_frame_manifest_digest",
                "sampling_frame_digest", "independent_cluster_definition_digest", "strata_definition_digest",
                "cluster_weighting_digest", "numeric_encoding_registry_digest", "unsupported_cells_digest",
            )},
            "verified_at": evaluation_time.isoformat(),
        }
        return VerifiedCapabilityBaselineApproval(**body, verification_digest=_digest_for(b"memorii.acceptance.verified-approval.v1", body))


@dataclass(frozen=True)
class EvaluationReceipt:
    receipt_digest: str
    verified_approval_digest: str
    certificate_digest: str
    policy_digest: str
    evidence_digest: str
    deployment_authorization_digest: str
    published_at: datetime

    def canonical_bytes(self) -> bytes:
        return _canonical(
            {
                "receipt_digest": self.receipt_digest,
                "verified_approval_digest": self.verified_approval_digest,
                "certificate_digest": self.certificate_digest,
                "policy_digest": self.policy_digest,
                "evidence_digest": self.evidence_digest,
                "deployment_authorization_digest": self.deployment_authorization_digest,
                "published_at": self.published_at.isoformat(),
            }
        )


class EvaluationReceiptStore(Protocol):
    def publish_if_absent(self, receipt: EvaluationReceipt) -> EvaluationReceipt: ...


class FileEvaluationReceiptStore:
    """Digest-addressed immutable receipt storage with byte-identical retry semantics."""

    def __init__(self, root: Path, *, maximum_receipt_bytes: int) -> None:
        self._root = root
        self._maximum_receipt_bytes = maximum_receipt_bytes

    def publish_if_absent(self, receipt: EvaluationReceipt) -> EvaluationReceipt:
        raw = receipt.canonical_bytes()
        if len(raw) > self._maximum_receipt_bytes:
            raise ApprovalRejected("evaluation_receipt_bytes")
        expected = _digest_for(
            b"memorii.acceptance.evaluation-receipt.v1",
            {
                "verified_approval_digest": receipt.verified_approval_digest,
                "certificate_digest": receipt.certificate_digest,
                "policy_digest": receipt.policy_digest,
                "evidence_digest": receipt.evidence_digest,
                "deployment_authorization_digest": receipt.deployment_authorization_digest,
                "published_at": receipt.published_at.isoformat(),
            },
        )
        if receipt.receipt_digest != expected:
            raise ApprovalRejected("evaluation_receipt_digest")
        self._root.mkdir(parents=True, exist_ok=True)
        path = self._root / f"{receipt.receipt_digest}.json"
        try:
            with path.open("xb") as output:
                output.write(raw)
            return receipt
        except FileExistsError:
            try:
                existing = path.read_bytes()
            except OSError as exc:
                raise ApprovalRejected("evaluation_receipt_read") from exc
            if existing != raw:
                raise ApprovalRejected("evaluation_receipt_conflict") from None
            return receipt


class DeploymentAuthorizationBridge(Protocol):
    def prepare_verified(
        self,
        *,
        target_artifact_digest: str,
        deployment_manifest_digest: str,
        capability_fingerprint: str,
        verified_capability_baseline_approval_release_digest: str,
        requested_active_epoch: int,
        expires_at: datetime,
    ) -> Any: ...

    def publish_prepared(self, artifact: Any) -> Any: ...


__all__ = [
    "AcceptanceSigningKey", "AcceptanceStatus", "AcceptanceVerifierLimits", "ApprovalRejected",
    "CapabilityBaselineApprovalVerifier", "CurrentAcceptanceStatusProvider", "DeploymentAuthorizationBridge",
    "EvaluationReceipt", "EvaluationReceiptStore", "FileEvaluationReceiptStore", "VerifiedCapabilityBaselineApproval",
]
