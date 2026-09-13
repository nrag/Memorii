"""End-to-end proof for the installed acceptance evaluator composition.

The fixture intentionally has no evaluator injection: package entry-point
discovery constructs the fixed runtime from a protected config and validates a
fully signed, registered authority prefix before the public CLI accepts the
candidate files.
"""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest
from acceptance.authority_repository import (
    AcceptanceAuthorityRepository,
    AcceptanceFenceRegistration,
    SqliteAcceptanceAuthorityFence,
    repository_identity,
)
from acceptance.cli import main as acceptance_cli
from acceptance.host_runtime import AcceptanceRuntimeConfigurationError, InstalledAcceptanceRuntime
from acceptance.schema_registry import canonical_digest, signing_preimage, unsigned_artifact
from acceptance.statistical_certification import NumericAuthority
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from test_statistical_certification import candidate, inputs


def _json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _time(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _public(key: Ed25519PrivateKey) -> str:
    return key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()


def _artifact(schema: str, signer: Ed25519PrivateKey | None, coordinate: str | None, **fields: object) -> tuple[str, bytes]:
    from acceptance.schema_registry import schema_for

    value = dict(fields)
    registered = schema_for(schema)
    digest_name = registered["digest_field"]
    value[digest_name] = "0" * 64
    if signer is not None:
        assert coordinate is not None
        signer_field = registered["signer_coordinate_field"]
        assert isinstance(signer_field, str)
        value[signer_field] = coordinate
        value["signature"] = "0" * 128
    value[digest_name] = canonical_digest(
        _domain(schema), "registered", unsigned_artifact(value, schema)
    )
    if signer is not None:
        value["signature"] = signer.sign(signing_preimage(schema, value, coordinate)).hex()
    return value[digest_name], _json(value)


def _domain(schema: str) -> str:
    from acceptance.schema_registry import schema_for

    return schema_for(schema)["digest_domain"]


def _numeric_config(policy: bytes, evidence: bytes, release_digest: str) -> tuple[dict[str, object], bytes]:
    policy_value = json.loads(policy)
    _, _, held, limits = inputs("0.00")
    authority = NumericAuthority(
        held.expected_authority.approved_baseline_artifact_digest,
        release_digest,
        held.expected_authority.capability_fingerprint,
        held.expected_authority.capability_contract_digest,
        held.expected_authority.coverage_manifest_digest,
        held.expected_authority.coverage_release_id,
        held.expected_authority.statistical_gate_manifest_digest,
        held.expected_authority.sampling_frame_digest,
        held.expected_authority.independent_cluster_definition_digest,
        held.expected_authority.strata_definition_digest,
        held.expected_authority.cluster_weighting_digest,
        held.expected_authority.numeric_encoding_registry_digest,
    )
    binding = replace(
        held,
        expected_authority=authority,
        context=replace(held.context, authority=authority),
    )
    certificate = candidate(policy, evidence, binding, limits)
    gates = []
    for gate in policy_value["gates"]:
        gates.append({**gate, "iid_bernoulli_clusters_proven": True})
    return (
        {
            "policy_sha256": sha256(policy).hexdigest(),
            "evidence_sha256": sha256(evidence).hexdigest(),
            "authority": asdict(authority),
            "specs": policy_value["specs"],
            "family_alpha": policy_value["family_alpha"],
            "family_alpha_spec_id": policy_value["family_alpha_spec_id"],
            "gates": gates,
            "clusters": policy_value["memberships"],
        },
        certificate,
    )


def _installed_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    checkpoint_offset: timedelta = timedelta(minutes=-1),
) -> tuple[list[str], Path, Path, Path]:
    """Write a real signed authority prefix and the closed installed config."""
    import acceptance.host_runtime as host_runtime

    now = datetime.now(tz=UTC)
    authority_key = Ed25519PrivateKey.generate()
    evaluator_key = Ed25519PrivateKey.generate()
    deployment_key = Ed25519PrivateKey.generate()
    coordinate = "acceptance-root-1"
    authority_root = tmp_path / "authority"
    fence_path = tmp_path / "fence" / "authority.sqlite"
    receipt_root = tmp_path / "receipts"
    deployment_root = tmp_path / "deployment-authorizations"
    policy, evidence, _, limits = inputs("0.00")
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
    trust_digest, trust = _artifact(
        "AcceptanceTrustSnapshot", authority_key, coordinate,
        schema_version=1, purpose="acceptance_trust_snapshot", snapshot_sequence=1,
        predecessor_snapshot_digest=None,
        key_declarations=[{
            "key_reference": coordinate, "public_key": _public(authority_key),
            "valid_from": _time(now - timedelta(days=1)), "valid_until": _time(now + timedelta(days=1)),
            "allowed_purposes": ["acceptance"],
        }],
        trust_policy_digest="9" * 64, issued_at=_time(now - timedelta(minutes=2)),
    )
    event_digest, event = _artifact(
        "KeyLifecycleEvent", authority_key, coordinate,
        schema_version=1, purpose="acceptance_key_lifecycle_event", key_reference=coordinate,
        state="active", effective_at=_time(now - timedelta(days=1)), global_sequence=1,
        predecessor_event_digest=None, issuance_trust_snapshot_digest=trust_digest,
    )
    release_fields = {
        "schema_version": 1,
        "approval_purpose": "semantic_ingestion_capability_baseline_approval",
        "approver_subject_id": "acceptance-approver",
        "target_approved_capability_baseline_artifact_digest": baseline["artifact_digest"],
        "capability_fingerprint": baseline["capability_fingerprint"],
        "capability_contract_digest": baseline["capability_contract_digest"],
        "dependency_bundle_digest": baseline["dependency_bundle_digest"],
        "coverage_manifest_digest": baseline["coverage_manifest_digest"],
        "statistical_gate_manifest_digest": baseline["statistical_gate_manifest_digest"],
        "monitoring_policy_digest": baseline["monitoring_policy_digest"],
        "unsupported_cells_digest": baseline["unsupported_cells_digest"],
        "issued_at": _time(now - timedelta(minutes=2)), "expires_at": _time(now + timedelta(days=1)),
        "acceptance_authority_snapshot_digest": trust_digest, "acceptance_release_epoch": 1,
        "acceptance_release_sequence": 1, "acceptance_signing_key_reference": coordinate,
        "lifecycle_state": "active", "supersedes_release_digest": None, "revoked_at": None,
        "compromise_effective_at": None,
    }
    release_digest, release = _artifact("CapabilityBaselineApprovalRelease", authority_key, coordinate, **release_fields)
    issuance_digest, issuance = _artifact(
        "AcceptanceApprovalIssuanceSnapshot", authority_key, coordinate,
        schema_version=1, purpose="acceptance_approval_issuance_snapshot", trust_snapshot_digest=trust_digest,
        key_event_digests=[event_digest], key_history_head_digest=event_digest, key_history_head_sequence=1,
    )
    checkpoint_digest, checkpoint = _artifact(
        "AcceptanceCurrentCheckpoint", authority_key, coordinate,
        schema_version=1, purpose="acceptance_current_checkpoint", capability_digest="8" * 64,
        checkpoint_generation=1, predecessor_checkpoint_digest=None, authority_snapshot_digest=trust_digest,
        release_history_head_digest=release_digest, release_history_head_sequence=1,
        key_history_head_digest=event_digest, key_history_head_sequence=1, active_release_digest=release_digest,
        active_epoch=1, active_sequence=1, production_revocation_evidence=[], observed_at=_time(now + checkpoint_offset),
    )
    commit_digest, commit = _artifact(
        "AcceptanceAuthorityCommit", None, None,
        schema_version=1, purpose="acceptance_authority_commit", transaction_sequence=1,
        predecessor_commit_digest=None, authority_snapshot_digest=trust_digest, key_history_head_digest=event_digest,
        key_history_head_sequence=1, release_history_head_digest=release_digest, release_history_head_sequence=1,
        active_release_digest=release_digest, active_release_epoch=1, active_release_sequence=1,
        current_checkpoint_digest=checkpoint_digest, issuance_snapshot_digest=issuance_digest,
        approval_release_digest=release_digest, production_revocation_evidence=[],
    )
    registration_body = {
        "namespace": "memorii.acceptance.fixture", "backend_id": "fixture-fence", "backend_kind": "sqlite",
        "failure_domain": "fixture-fence-domain", "repository_id": repository_identity(authority_root),
        "credential_reference": "fixture-credential", "signer_coordinate": coordinate,
    }
    registration = AcceptanceFenceRegistration(
        **registration_body, signature=authority_key.sign(_json(registration_body)).hex()
    )

    def verify(_: str, preimage: bytes, signer: str, signature: str) -> bool:
        try:
            if signer != coordinate:
                return False
            authority_key.public_key().verify(bytes.fromhex(signature), preimage)
        except ValueError:
            return False
        except InvalidSignature:
            return False
        return True

    fence = SqliteAcceptanceAuthorityFence(fence_path, registration, lambda raw, signer, signature: verify("fence", raw, signer, signature))
    repository = AcceptanceAuthorityRepository(authority_root, fence, artifact_signature_verifier=verify)
    prepared = {
        digest: raw for digest, raw in (
            (trust_digest, trust), (event_digest, event), (release_digest, release),
            (issuance_digest, issuance), (checkpoint_digest, checkpoint),
        )
    }
    repository.compare_and_publish(
        prepared_objects=prepared, expected_commit_digest=None, expected_key_head=None,
        expected_status_generation=None, next_commit=commit,
    )
    numeric_binding, certificate = _numeric_config(policy, evidence, release_digest)
    config = {
        "format": "memorii.acceptance.runtime.v1", "authority_repository_root": str(authority_root),
        "fence_database_path": str(fence_path), "receipt_root": str(receipt_root),
        "fence_registration": {**registration_body, "signature": registration.signature},
        "trust_keys": {coordinate: _public(authority_key)},
        "acceptance_keys": [{"key_reference": coordinate, "public_key": _public(authority_key),
                               "valid_from": _time(now - timedelta(days=1)), "valid_until": _time(now + timedelta(days=1)), "status": "active"}],
        "numeric_binding": numeric_binding, "numeric_limits": asdict(limits),
        "acceptance_limits": {"maximum_release_bytes": 131072, "maximum_baseline_bytes": 131072, "maximum_receipt_bytes": 131072},
        "deployment_issuer": {"subject_id": "production-issuer", "key_reference": "deployment-key",
                                "authority_snapshot_digest": trust_digest, "private_key": deployment_key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()).hex(),
                                "publisher_root": str(deployment_root)},
        "evaluator_subject_id": "fixture-evaluator", "evaluator_signing_key_coordinate": "fixture-evaluator-key",
        "evaluator_private_key": evaluator_key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()).hex(),
    }
    config_path = tmp_path / "installed" / "runtime-v1.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_bytes(_json(config))
    config_path.chmod(0o600)
    monkeypatch.setattr(host_runtime, "_CONFIG", config_path)
    candidates = {"release": release, "baseline": _json(baseline), "policy": policy, "evidence": evidence, "certificate": certificate}
    args: list[str] = []
    for name, raw in candidates.items():
        path = tmp_path / f"{name}.bin"
        path.write_bytes(raw)
        args.extend((f"--{name}", str(path)))
    return args + ["--deployment-manifest-digest", "7" * 64], receipt_root, deployment_root, config_path


def test_public_cli_discovers_installed_runtime_and_publishes_signed_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    args, receipt_root, deployment_root, _ = _installed_fixture(tmp_path, monkeypatch)
    assert acceptance_cli(args) == 0
    receipt_digest = capsys.readouterr().out.strip()
    raw = (receipt_root / receipt_digest).read_bytes()
    receipt = json.loads(raw)
    assert receipt["receipt_digest"] == receipt_digest
    assert len(receipt["signature"]) == 128
    assert receipt["purpose"] == "acceptance_evaluation_receipt"
    authorization_digest = receipt["deployment_authorization_digest"]
    assert (deployment_root / authorization_digest).is_file()


def test_installed_runtime_rejects_writable_or_aliased_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, _, config = _installed_fixture(tmp_path, monkeypatch)
    config.chmod(0o622)
    with pytest.raises(AcceptanceRuntimeConfigurationError, match="config"):
        InstalledAcceptanceRuntime()
    config.chmod(0o600)
    alias = tmp_path / "runtime-alias.json"
    alias.symlink_to(config)
    monkeypatch.setattr("acceptance.host_runtime._CONFIG", alias)
    with pytest.raises(AcceptanceRuntimeConfigurationError, match="config"):
        InstalledAcceptanceRuntime()


def test_public_cli_rejects_bad_signature_missing_authority_and_future_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args, _, _, _ = _installed_fixture(tmp_path / "signature", monkeypatch)
    release_path = Path(args[1])
    release = json.loads(release_path.read_bytes())
    release["signature"] = "0" * 128
    release_path.write_bytes(_json(release))
    with pytest.raises(SystemExit, match="2"):
        acceptance_cli(args)

    args, _, _, _ = _installed_fixture(tmp_path / "missing", monkeypatch)
    release = json.loads(Path(args[1]).read_bytes())
    (tmp_path / "missing" / "authority" / "objects" / release["release_digest"]).unlink()
    with pytest.raises(SystemExit, match="2"):
        acceptance_cli(args)

    args, _, _, _ = _installed_fixture(
        tmp_path / "future", monkeypatch, checkpoint_offset=timedelta(minutes=1)
    )
    with pytest.raises(SystemExit, match="2"):
        acceptance_cli(args)


def test_cli_fails_closed_when_runtime_discovery_is_not_exactly_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("acceptance.cli.entry_points", lambda **_: ())
    with pytest.raises(ValueError, match="configuration"):
        __import__("acceptance.cli", fromlist=["_configured_evaluator"])._configured_evaluator()

    class _EntryPoint:
        def load(self) -> object:
            return object

    monkeypatch.setattr("acceptance.cli.entry_points", lambda **_: (_EntryPoint(), _EntryPoint()))
    with pytest.raises(ValueError, match="configuration"):
        __import__("acceptance.cli", fromlist=["_configured_evaluator"])._configured_evaluator()
