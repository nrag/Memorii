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
    CapabilityBaselineApprovalVerifier,
    CurrentAcceptanceCheckpoint,
    FileEvaluationReceiptStore,
    KeyLifecycleEvent,
    _digest_for,
)
from acceptance.cli import main as acceptance_cli
from acceptance.evaluator import AcceptanceEvaluationError, AcceptanceEvaluator
from acceptance.schema_registry import canonical_digest, signing_preimage, unsigned_artifact
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from memorii.core.memory_evolution.deployment_authorization import (
    DeploymentAuthorizationArtifactVerifier,
    DeploymentAuthorizationIssuer,
    InMemoryDeploymentAuthorizationRepository,
    IssuerAuthority,
)
from test_statistical_certification import candidate, inputs


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _digest(domain: bytes, value: object) -> str:
    return _digest_for(domain, value)


class _Status:
    def __init__(self, value: AcceptanceStatus, snapshot: AcceptanceApprovalIssuanceSnapshotV1, event: KeyLifecycleEvent, now: datetime) -> None:
        self.value = value
        self.snapshot = snapshot
        self.event = event
        self.now = now

    def load_current(self) -> AcceptanceStatus:
        return self.value

    def load_issuance_snapshot(self, snapshot_digest: str, release_digest: str) -> AcceptanceApprovalIssuanceSnapshotV1 | None:
        return self.snapshot if snapshot_digest == self.snapshot.snapshot_digest and release_digest == self.value.active_release_digest else None

    def load_current_key_history(self) -> tuple[KeyLifecycleEvent, ...]:
        return (self.event,)

    def load_current_checkpoint(self) -> CurrentAcceptanceCheckpoint:
        return CurrentAcceptanceCheckpoint(
            self.value.authority_snapshot_digest, self.value.active_release_digest, 1,
            self.event.event_digest, 1, self.value.active_release_digest, 1, 1, self.now,
        )


@dataclass(frozen=True)
class _Artifact:
    authorization_digest: str


class _Signer:
    def sign(self, preimage: bytes) -> str:
        return sha256(preimage).hexdigest()

    def verify(self, *, signing_key_reference: str, preimage: bytes, signature: str) -> bool:
        return signing_key_reference == "deployment-key" and signature == self.sign(preimage)


def _release(now: datetime) -> tuple[bytes, bytes, CapabilityBaselineApprovalVerifier]:
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    baseline = {
        "capability_fingerprint": "a" * 64,
        "capability_contract_digest": "d" * 64,
        "coverage_manifest_digest": "e" * 64,
        "statistical_gate_manifest_digest": "f" * 64,
        "monitoring_policy_digest": "1" * 64,
        "unsupported_cells_digest": "2" * 64,
        "dependency_bundle_digest": "3" * 64,
        "canonical_content_digest": "4" * 64,
        "artifact_digest": "b" * 64,
    }
    unsigned = {
        "schema_version": 1,
        "approval_purpose": "semantic_ingestion_capability_baseline_approval",
        "approver_subject_id": "approver",
        "target_approved_capability_baseline_artifact_digest": baseline["artifact_digest"],
        "capability_fingerprint": baseline["capability_fingerprint"],
        "capability_contract_digest": baseline["capability_contract_digest"],
        "dependency_bundle_digest": baseline["dependency_bundle_digest"],
        "coverage_manifest_digest": baseline["coverage_manifest_digest"],
        "statistical_gate_manifest_digest": baseline["statistical_gate_manifest_digest"],
        "monitoring_policy_digest": baseline["monitoring_policy_digest"],
        "unsupported_cells_digest": baseline["unsupported_cells_digest"],
        "issued_at": (now - timedelta(minutes=1)).isoformat(),
        "expires_at": (now + timedelta(minutes=5)).isoformat(),
        "acceptance_authority_snapshot_digest": "9" * 64,
        "acceptance_release_epoch": 1,
        "acceptance_release_sequence": 1,
        "acceptance_signing_key_reference": "approval-key",
        "lifecycle_state": "active",
        "supersedes_release_digest": None,
        "revoked_at": None,
        "compromise_effective_at": None,
    }
    release = {**unsigned, "release_digest": "0" * 64, "signature": "0" * 128}
    release["release_digest"] = canonical_digest(
        "memorii.acceptance.capability-baseline-approval.v1",
        "registered",
        unsigned_artifact(release, "CapabilityBaselineApprovalRelease"),
    )
    release["signature"] = private.sign(
        signing_preimage("CapabilityBaselineApprovalRelease", release, "approval-key")
    ).hex()
    release_digest = release["release_digest"]
    event = KeyLifecycleEvent("approval-key", "active", now - timedelta(days=1), 1, None, "6" * 64)
    snapshot = AcceptanceApprovalIssuanceSnapshotV1(
        "9" * 64, "9" * 64, (event,), "6" * 64, 1, "approval-key"
    )
    status = _Status(AcceptanceStatus("9" * 64, release_digest, 1, 1, (release_digest,)), snapshot, event, now)
    verifier = CapabilityBaselineApprovalVerifier(
        keys=(AcceptanceSigningKey("approval-key", public, now - timedelta(days=1), now + timedelta(days=1), "active"),),
        authority_repository=status,
    )
    return _canonical(release), _canonical(baseline), verifier


def test_evaluator_publishes_idempotent_receipt_and_digest_only_authorization(tmp_path: Path) -> None:
    now = datetime(2026, 9, 12, tzinfo=UTC)
    release, baseline, verifier = _release(now)
    policy, evidence, binding, limits = inputs("0.00")
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
    release, baseline, verifier = _release(now)
    policy, evidence, binding, limits = inputs("0.00")
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
    release, baseline, verifier = _release(now)
    policy, evidence, binding, limits = inputs("0.00")
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
