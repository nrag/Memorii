"""End-to-end proof for the installed acceptance evaluator composition.

The fixture intentionally has no evaluator injection: package entry-point
discovery constructs the fixed runtime from a protected config and validates a
fully signed, registered authority prefix before the public CLI accepts the
candidate files.
"""

from __future__ import annotations

import base64
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Literal

import pytest
from acceptance.authority_repository import (
    AcceptanceAuthorityRepository,
    AcceptanceFenceRegistration,
    SqliteAcceptanceAuthorityFence,
    repository_identity,
)
from acceptance.cli import main as acceptance_cli
from acceptance.evaluator import AcceptanceEvaluationError
from acceptance.host_runtime import (
    AcceptanceRuntimeConfigurationError,
    InstalledAcceptanceRuntime,
    _distinct_domains,
    _secure_path,
)
from acceptance.schema_registry import canonical_digest, signing_preimage, unsigned_artifact
from acceptance.statistical_certification import NumericAuthority
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from test_statistical_certification import candidate, inputs
from v2_authority_fixture import build_v2_authority


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
        held.expected_authority.sampling_frame_manifest_digest,
        held.expected_authority.sampling_frame_digest,
        held.expected_authority.independent_cluster_definition_digest,
        held.expected_authority.strata_definition_digest,
        held.expected_authority.cluster_weighting_digest,
        held.expected_authority.numeric_encoding_registry_digest,
        held.expected_authority.unsupported_cells_digest,
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
    release_issued_at: datetime | None = None,
    lifecycle_state: Literal["active", "retired", "revoked", "compromised"] = "active",
) -> tuple[list[str], Path, Path, Path]:
    """Write a real signed authority prefix and the closed installed config."""
    import acceptance.host_runtime as host_runtime
    from memorii.core.memory_evolution.deployment_authorization import (
        InstalledProductionRevocationReader,
    )

    now = datetime.now(tz=UTC)
    authority_key = Ed25519PrivateKey.generate()
    evaluator_key = Ed25519PrivateKey.generate()
    deployment_key = Ed25519PrivateKey.generate()
    production_revocation_key = Ed25519PrivateKey.generate()
    coordinate = "acceptance-root-1"
    authority_root = tmp_path / "authority"
    fence_path = tmp_path / "fence" / "authority.sqlite"
    receipt_root = tmp_path / "receipts"
    deployment_root = tmp_path / "deployment-authorizations"
    production_revocation_root = tmp_path / "production-revocations"
    policy, evidence, _, limits = inputs("0.00")
    trust_digest, trust = _artifact(
        "AcceptanceTrustSnapshot", authority_key, coordinate,
        schema_version=1, purpose="acceptance_trust_snapshot", snapshot_sequence=1,
        predecessor_snapshot_digest=None,
        key_declarations=[{
            "key_reference": coordinate, "public_key": _public(authority_key),
            "valid_from": _time(now - timedelta(days=1)), "valid_until": _time(now + timedelta(days=1)),
            "allowed_purposes": ["semantic_ingestion_capability_baseline_approval.v2"],
        }],
        trust_policy_digest="9" * 64, issued_at=_time(now - timedelta(minutes=2)),
    )
    event_digest, event = _artifact(
        "KeyLifecycleEvent", authority_key, coordinate,
        schema_version=1, purpose="acceptance_key_lifecycle_event", key_reference=coordinate,
        state="active", effective_at=_time(now - timedelta(days=1)), global_sequence=1,
        predecessor_event_digest=None, issuance_trust_snapshot_digest=trust_digest,
    )
    numeric = build_v2_authority(
        policy=policy, evidence=evidence, key=authority_key, coordinate=coordinate,
        authority_snapshot_digest=trust_digest, now=now, issued_at=release_issued_at,
        lifecycle_state=lifecycle_state,
    )
    release_digest, release = numeric.release_digest, numeric.release
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
    certificate = candidate(numeric.policy, evidence, numeric.binding, limits)
    numeric_authority = {
        "coverage": base64.b64encode(numeric.coverage).decode("ascii"),
        "gates": base64.b64encode(numeric.gates).decode("ascii"),
        "sampling_frame": base64.b64encode(numeric.sampling_frame).decode("ascii"),
        "trust_keys": {coordinate: _public(authority_key)},
        "signing_key_id": coordinate,
        "trust_policy_digest": "9" * 64,
    }
    config = {
        "format": "memorii.acceptance.runtime.v2", "authority_repository_root": str(authority_root),
        "fence_database_path": str(fence_path), "receipt_root": str(receipt_root),
        "fence_registration": {**registration_body, "signature": registration.signature},
        "trust_keys": {coordinate: _public(authority_key)},
        "production_trust_keys": {"production-revocation-1": _public(production_revocation_key)},
        "production_revocation_reader": {"reader_root": str(production_revocation_root)},
        "acceptance_keys": [{"key_reference": coordinate, "public_key": _public(authority_key),
                               "valid_from": _time(now - timedelta(days=1)), "valid_until": _time(now + timedelta(days=1)), "status": "active"}],
        "numeric_authority": numeric_authority, "numeric_limits": asdict(limits),
        "acceptance_limits": {"maximum_release_bytes": 131072, "maximum_baseline_bytes": 131072, "maximum_receipt_bytes": 131072},
        "deployment_issuer": {"subject_id": "production-issuer", "key_reference": "deployment-key",
                                "authority_snapshot_digest": trust_digest, "private_key": deployment_key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()).hex(),
                                "publisher_root": str(deployment_root)},
        "evaluator_subject_id": "fixture-evaluator", "evaluator_signing_key_coordinate": "fixture-evaluator-key",
        "evaluator_private_key": evaluator_key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()).hex(),
    }
    config_path = tmp_path / "installed" / "runtime-v2.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_bytes(_json(config))
    config_path.chmod(0o600)
    monkeypatch.setattr(host_runtime, "_CONFIG", config_path)
    monkeypatch.setattr(
        host_runtime,
        "configured_revocation_reader",
        lambda configuration: InstalledProductionRevocationReader().from_fixed_configuration(configuration),
    )
    candidates = {"release": release, "baseline": numeric.baseline, "policy": numeric.policy, "evidence": evidence, "certificate": certificate}
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


def test_installed_runtime_rejects_insecure_or_overlapping_fixed_resources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, _, config_path = _installed_fixture(tmp_path, monkeypatch)
    config = json.loads(config_path.read_bytes())
    authority = Path(config["authority_repository_root"])
    authority.chmod(0o722)
    with pytest.raises(AcceptanceRuntimeConfigurationError, match="authority_repository_root"):
        InstalledAcceptanceRuntime()
    authority.chmod(0o700)
    config["receipt_root"] = str(authority / "receipts")
    config_path.write_bytes(_json(config))
    with pytest.raises(AcceptanceRuntimeConfigurationError, match="path_alias"):
        InstalledAcceptanceRuntime()


@pytest.mark.parametrize("target", ["authority", "fence.sqlite", "receipt", "publisher"])
def test_fixed_path_admission_rejects_direct_and_parent_symlinks(tmp_path: Path, target: str) -> None:
    secure = tmp_path / "secure"
    secure.mkdir(mode=0o700)
    leaf = secure / target
    leaf.symlink_to(tmp_path / "elsewhere")
    with pytest.raises(AcceptanceRuntimeConfigurationError):
        _secure_path(leaf, "resource")
    leaf.unlink()
    parent = tmp_path / "parent-link"
    parent.symlink_to(secure, target_is_directory=True)
    with pytest.raises(AcceptanceRuntimeConfigurationError):
        _secure_path(parent / target, "resource")


@pytest.mark.parametrize("name", ["fence-parent", "fence.sqlite", "receipt", "publisher"])
def test_fixed_path_admission_rejects_group_or_world_writable_coordinates(
    tmp_path: Path, name: str
) -> None:
    path = tmp_path / name
    if name.endswith("parent"):
        path.mkdir(mode=0o700)
        target = path / "fence.sqlite"
    else:
        path.mkdir(mode=0o700)
        target = path
    path.chmod(0o722)
    with pytest.raises(AcceptanceRuntimeConfigurationError):
        _secure_path(target, "resource")


def test_fixed_path_domains_reject_equal_nested_and_allow_secure_missing_leaves(tmp_path: Path) -> None:
    secure = tmp_path / "secure"
    secure.mkdir(mode=0o700)
    _secure_path(secure / "missing" / "leaf", "resource")
    with pytest.raises(AcceptanceRuntimeConfigurationError, match="path_alias"):
        _distinct_domains((secure / "authority", secure / "authority", secure / "publisher", secure / "fence"))
    with pytest.raises(AcceptanceRuntimeConfigurationError, match="path_alias"):
        _distinct_domains((secure / "authority", secure / "authority" / "receipt", secure / "publisher", secure / "fence"))
    with pytest.raises(AcceptanceRuntimeConfigurationError, match="path_alias"):
        _distinct_domains((secure / "authority", secure / "receipt", secure / "publisher", secure / "authority" / "fence"))


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


@pytest.mark.parametrize("lifecycle_state", ["retired", "revoked", "compromised"])
def test_public_cli_rejects_terminal_release_lifecycle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    lifecycle_state: Literal["retired", "revoked", "compromised"],
) -> None:
    args, receipts, authorizations, _ = _installed_fixture(
        tmp_path / lifecycle_state, monkeypatch, lifecycle_state=lifecycle_state
    )
    with pytest.raises(SystemExit, match="2"):
        acceptance_cli(args)
    assert not receipts.exists()
    assert not authorizations.exists()


def test_public_cli_rejects_expired_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args, receipts, authorizations, _ = _installed_fixture(
        tmp_path / "expired", monkeypatch,
        release_issued_at=datetime.now(tz=UTC) - timedelta(days=3),
    )
    with pytest.raises(SystemExit, match="2"):
        acceptance_cli(args)
    assert not receipts.exists()
    assert not authorizations.exists()

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


class _PublicationPublisher:
    """Minimal serialized publisher with controllable acknowledgement behavior."""

    def __init__(self, *, persist_then_raise: bool = False, fail_without_persist: bool = False) -> None:
        self.persist_then_raise = persist_then_raise
        self.fail_without_persist = fail_without_persist
        self.prepared = 0
        self.published: list[bytes] = []

    def prepare_verified(self, _: bytes) -> bytes:
        self.prepared += 1
        return _json({"authorization_digest": "a" * 64})

    def publish_prepared(self, artifact: bytes) -> bytes:
        if self.fail_without_persist:
            raise ValueError("no_persist")
        self.published.append(artifact)
        if self.persist_then_raise:
            raise ValueError("lost_ack")
        return artifact

    def visible_exact(self, artifact: bytes) -> bool:
        return artifact in self.published


def _runtime_inputs(args: list[str]) -> dict[str, bytes]:
    return {args[index][2:]: Path(args[index + 1]).read_bytes() for index in range(0, 10, 2)}


def _evaluate_runtime(runtime: InstalledAcceptanceRuntime, values: dict[str, bytes]) -> object:
    return runtime.evaluator().evaluate_and_publish(
        release_bytes=values["release"], baseline_bytes=values["baseline"], policy_bytes=values["policy"],
        evidence_bytes=values["evidence"], certificate_bytes=values["certificate"],
        deployment_manifest_digest="7" * 64,
    )


def test_registered_attempt_reconciles_lost_ack_and_reuses_no_persist_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args, receipt_root, _, _ = _installed_fixture(tmp_path / "lost-ack", monkeypatch)
    values = _runtime_inputs(args)
    lost_ack = _PublicationPublisher(persist_then_raise=True)
    monkeypatch.setattr("acceptance.host_runtime.configured_publisher", lambda _: lost_ack)
    first = _evaluate_runtime(InstalledAcceptanceRuntime(), values)
    assert len(lost_ack.published) == 1
    assert (receipt_root / first.receipt_digest).is_file()

    args, receipt_root, _, _ = _installed_fixture(tmp_path / "no-persist", monkeypatch)
    values = _runtime_inputs(args)
    failing = _PublicationPublisher(fail_without_persist=True)
    monkeypatch.setattr("acceptance.host_runtime.configured_publisher", lambda _: failing)
    with pytest.raises(AcceptanceEvaluationError, match="deployment_issuer_outcome"):
        _evaluate_runtime(InstalledAcceptanceRuntime(), values)
    assert failing.prepared == 1
    # The failed publisher did not create a second signed preparation: the
    # prior attempt survives and is reused by a later runtime process.
    retry = _PublicationPublisher()
    monkeypatch.setattr("acceptance.host_runtime.configured_publisher", lambda _: retry)
    _evaluate_runtime(InstalledAcceptanceRuntime(), values)
    assert retry.prepared == 0
    assert len(retry.published) == 1
    assert len(list((receipt_root / "attempts").iterdir())) == 1


def test_registered_attempt_concurrent_retries_converge_on_one_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args, receipt_root, _, _ = _installed_fixture(tmp_path, monkeypatch)
    values = _runtime_inputs(args)
    publisher = _PublicationPublisher()
    monkeypatch.setattr("acceptance.host_runtime.configured_publisher", lambda _: publisher)
    runtime = InstalledAcceptanceRuntime()
    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = list(pool.map(lambda _: _evaluate_runtime(runtime, values), range(2)))
    assert receipts[0].receipt_digest == receipts[1].receipt_digest
    assert publisher.prepared == 1
    assert len(list((receipt_root / "attempts").iterdir())) == 1
    assert (receipt_root / receipts[0].receipt_digest).is_file()

    class _EntryPoint:
        def load(self) -> object:
            return object

    monkeypatch.setattr("acceptance.cli.entry_points", lambda **_: (_EntryPoint(), _EntryPoint()))
    with pytest.raises(ValueError, match="configuration"):
        __import__("acceptance.cli", fromlist=["_configured_evaluator"])._configured_evaluator()
