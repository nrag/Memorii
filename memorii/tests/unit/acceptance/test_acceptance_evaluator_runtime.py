from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest
from acceptance.capability_baseline_approval import (
    AcceptanceApprovalIssuanceSnapshotV1,
    AcceptanceSigningKey,
    AcceptanceStatus,
    ApprovalRejected,
    CapabilityBaselineApprovalVerifier,
    CurrentAcceptanceCheckpoint,
    FileEvaluationReceiptStore,
    KeyLifecycleEvent,
    _digest_for,
)
from acceptance.cli import main as acceptance_cli
from acceptance.evaluator import AcceptanceEvaluationError, AcceptanceEvaluator
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from memorii.core.memory_evolution.deployment_authorization import (
    DeploymentAuthorizationArtifactVerifier,
    DeploymentAuthorizationIssuer,
    InMemoryDeploymentAuthorizationRepository,
    IssuerAuthority,
)
from test_statistical_certification import candidate, inputs
from v2_authority_fixture import build_v2_authority


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _digest(domain: bytes, value: object) -> str:
    return _digest_for(domain, value)


class _Status:
    def __init__(self, value: AcceptanceStatus, snapshot: AcceptanceApprovalIssuanceSnapshotV1, event: KeyLifecycleEvent, now: datetime, public_key: bytes) -> None:
        self.value = value
        self.snapshot = snapshot
        self.event = event
        self.now = now
        self.public_key = public_key
        self.purposes = ["semantic_ingestion_capability_baseline_approval.v2"]
        self.declarations: list[dict[str, object]] | None = None
        self.current_events = (event,)

    def load_current(self) -> AcceptanceStatus:
        return self.value

    def load_issuance_snapshot(self, snapshot_digest: str, release_digest: str) -> AcceptanceApprovalIssuanceSnapshotV1 | None:
        return self.snapshot if snapshot_digest == self.snapshot.snapshot_digest and release_digest == self.value.active_release_digest else None

    def load_current_key_history(self) -> tuple[KeyLifecycleEvent, ...]:
        return self.current_events

    def load_current_trust_snapshot(self) -> dict[str, object]:
        return {"key_declarations": self.declarations if self.declarations is not None else [{
            "key_reference": "approval-key", "public_key": self.public_key.hex(),
            "valid_from": (self.now - timedelta(days=1)).isoformat(),
            "valid_until": (self.now + timedelta(days=1)).isoformat(),
            "allowed_purposes": self.purposes,
        }]}

    def load_current_checkpoint(self) -> CurrentAcceptanceCheckpoint:
        head = self.current_events[-1]
        return CurrentAcceptanceCheckpoint(
            self.value.authority_snapshot_digest, self.value.active_release_digest, 1,
            head.event_digest, len(self.current_events), self.value.active_release_digest, 1, 1, self.now,
        )


@dataclass(frozen=True)
class _Artifact:
    authorization_digest: str


class _Signer:
    def sign(self, preimage: bytes) -> str:
        return sha256(preimage).hexdigest()

    def verify(self, *, signing_key_reference: str, preimage: bytes, signature: str) -> bool:
        return signing_key_reference == "deployment-key" and signature == self.sign(preimage)


def _release(now: datetime, issued_at: datetime | None = None) -> tuple[bytes, bytes, CapabilityBaselineApprovalVerifier, bytes, bytes, object, object]:
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    policy, evidence, _, limits = inputs("0.00")
    fixture = build_v2_authority(
        policy=policy, evidence=evidence, key=private, coordinate="approval-key",
        authority_snapshot_digest="9" * 64, now=now, issued_at=issued_at,
    )
    release_digest = fixture.release_digest
    event = KeyLifecycleEvent("approval-key", "active", now - timedelta(days=1), 1, None, "6" * 64)
    snapshot = AcceptanceApprovalIssuanceSnapshotV1(
        "9" * 64, "9" * 64, (event,), "6" * 64, 1, "approval-key"
    )
    status = _Status(AcceptanceStatus("9" * 64, release_digest, 1, 1, (release_digest,)), snapshot, event, now, public)
    verifier = CapabilityBaselineApprovalVerifier(
        keys=(AcceptanceSigningKey("approval-key", public, now - timedelta(days=1), now + timedelta(days=1), "active"),),
        authority_repository=status,
    )
    return fixture.release, fixture.baseline, verifier, fixture.policy, evidence, fixture.binding, limits


def test_evaluator_publishes_idempotent_receipt_and_digest_only_authorization(tmp_path: Path) -> None:
    now = datetime(2026, 9, 12, tzinfo=UTC)
    release, baseline, verifier, policy, evidence, binding, limits = _release(now)
    certificate = candidate(policy, evidence, binding, limits)
    issuer = DeploymentAuthorizationIssuer(
        authority=IssuerAuthority("deployment", "deployment-key", "8" * 64, _Signer()),
        repository=InMemoryDeploymentAuthorizationRepository(),
        now_provider=lambda: now,
    )
    evaluator = AcceptanceEvaluator(
        approval_verifier=verifier,
        numeric_binding=binding,
        numeric_limits=limits,
        receipt_store=FileEvaluationReceiptStore(tmp_path, maximum_receipt_bytes=128 * 1024),
        deployment_issuer=issuer,
        now_provider=lambda: now,
    )
    first = evaluator.evaluate_and_publish(
        release_bytes=release, baseline_bytes=baseline, policy_bytes=policy, evidence_bytes=evidence,
        certificate_bytes=certificate, deployment_manifest_digest="7" * 64,
    )
    second = evaluator.evaluate_and_publish(
        release_bytes=release, baseline_bytes=baseline, policy_bytes=policy, evidence_bytes=evidence,
        certificate_bytes=certificate, deployment_manifest_digest="7" * 64,
    )
    assert second == first
    assert (tmp_path / f"{first.receipt_digest}.json").is_file()


def test_rejected_current_status_never_calls_issuer(tmp_path: Path) -> None:
    now = datetime(2026, 9, 12, tzinfo=UTC)
    release, baseline, verifier, policy, evidence, binding, limits = _release(now)
    certificate = candidate(policy, evidence, binding, limits)
    evaluator = AcceptanceEvaluator(
        approval_verifier=verifier, numeric_binding=binding, numeric_limits=limits,
        receipt_store=FileEvaluationReceiptStore(tmp_path, maximum_receipt_bytes=128 * 1024),
        deployment_issuer=object(), now_provider=lambda: now + timedelta(days=1),
    )
    with pytest.raises(AcceptanceEvaluationError, match="rejected"):
        evaluator.evaluate_and_publish(
            release_bytes=release, baseline_bytes=baseline, policy_bytes=policy, evidence_bytes=evidence,
            certificate_bytes=certificate, deployment_manifest_digest="7" * 64,
        )


def test_cli_accepts_only_resource_paths_with_configured_runtime(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime(2026, 9, 12, tzinfo=UTC)
    release, baseline, verifier, policy, evidence, binding, limits = _release(now)
    certificate = candidate(policy, evidence, binding, limits)
    files = {"release": release, "baseline": baseline, "policy": policy, "evidence": evidence, "certificate": certificate}
    arguments: list[str] = []
    for name, value in files.items():
        path = tmp_path / name
        path.write_bytes(value)
        arguments.extend((f"--{name}", str(path)))
    evaluator = AcceptanceEvaluator(
        approval_verifier=verifier, numeric_binding=binding, numeric_limits=limits,
        receipt_store=FileEvaluationReceiptStore(tmp_path / "receipts", maximum_receipt_bytes=128 * 1024),
        deployment_issuer=DeploymentAuthorizationIssuer(
            authority=IssuerAuthority("deployment", "deployment-key", "8" * 64, _Signer()),
            repository=InMemoryDeploymentAuthorizationRepository(), now_provider=lambda: now,
        ),
        now_provider=lambda: now,
    )
    monkeypatch.setattr("acceptance.cli._configured_evaluator", lambda: evaluator)
    assert acceptance_cli(arguments + ["--deployment-manifest-digest", "7" * 64]) == 0
    assert len(capsys.readouterr().out.strip()) == 64


def test_production_artifact_decoder_verifies_digest_only_bridge_output() -> None:
    now = datetime(2026, 9, 12, tzinfo=UTC)
    signer = _Signer()
    issuer = DeploymentAuthorizationIssuer(
        authority=IssuerAuthority("deployment", "deployment-key", "8" * 64, signer),
        repository=InMemoryDeploymentAuthorizationRepository(), now_provider=lambda: now,
    )
    artifact = issuer.prepare_verified(
        target_artifact_digest="b" * 64, deployment_manifest_digest="7" * 64,
        capability_fingerprint="a" * 64, verified_capability_baseline_approval_release_digest="c" * 64,
        requested_active_epoch=1, expires_at=now + timedelta(minutes=1),
    )
    raw = _canonical(artifact.model_dump(mode="json"))
    assert DeploymentAuthorizationArtifactVerifier(signer).verify(raw, server_time=now) == artifact
    with pytest.raises(ValueError, match="deployment_authorization"):
        DeploymentAuthorizationArtifactVerifier(signer).verify(raw.replace(b"deployment-key", b"deployment-no"), server_time=now)


def _release_status(verifier: CapabilityBaselineApprovalVerifier) -> _Status:
    return verifier._authority_repository  # type: ignore[return-value, attr-defined]


@pytest.mark.parametrize("mutation", ["undeclared", "different_bytes", "wrong_purpose", "missing_purpose", "duplicate_reference", "unsorted_purposes", "duplicate_purposes"])
def test_signed_trust_declaration_rejects_invalid_key_authority(mutation: str) -> None:
    now = datetime(2026, 9, 12, tzinfo=UTC)
    release, baseline, verifier, *_ = _release(now)
    status = _release_status(verifier)
    if mutation == "undeclared":
        status.declarations = []
    elif mutation == "different_bytes":
        status.public_key = Ed25519PrivateKey.generate().public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    elif mutation == "wrong_purpose":
        status.purposes = ["other"]
    elif mutation == "missing_purpose":
        status.purposes = []
    elif mutation == "duplicate_reference":
        status.declarations = [status.load_current_trust_snapshot()["key_declarations"][0]] * 2
    elif mutation == "unsorted_purposes":
        status.purposes = ["z", "semantic_ingestion_capability_baseline_approval.v2"]
    else:
        status.purposes = ["semantic_ingestion_capability_baseline_approval.v2"] * 2
    with pytest.raises(ApprovalRejected, match="trust_declaration"):
        verifier.verify(release, baseline, now)


def test_signed_trust_declaration_honors_half_open_issue_interval() -> None:
    now = datetime(2026, 9, 12, tzinfo=UTC)
    release, baseline, verifier, *_ = _release(now, now - timedelta(days=1))
    assert verifier.verify(release, baseline, now).release_digest
    release, baseline, verifier, *_ = _release(now, now + timedelta(days=1))
    with pytest.raises(ApprovalRejected, match="trust_declaration"):
        verifier.verify(release, baseline, now + timedelta(days=1))


@pytest.mark.parametrize("state", ["retired", "revoked", "compromised"])
def test_signed_trust_declaration_rejects_later_nonactive_lifecycle(state: str) -> None:
    now = datetime(2026, 9, 12, tzinfo=UTC)
    release, baseline, verifier, *_ = _release(now)
    status = _release_status(verifier)
    prior = status.event
    status.current_events = (prior, KeyLifecycleEvent("approval-key", state, now, 2, prior.event_digest, "7" * 64))
    with pytest.raises(ApprovalRejected, match="current_key_history"):
        verifier.verify(release, baseline, now)
