from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest
from memorii.tools.semantic_ingestion_traceability_checker import (
    TraceabilityCoverageError,
    load_independent_registry_bytes,
    rebuild_structural_manifest_bytes,
)
from memorii.tools.semantic_ingestion_traceability_registry import (
    RegistryValidationError,
    canonical_document,
    load_registry,
)
from memorii.tools.semantic_ingestion_traceability_release import (
    TraceabilityGateAuthorized,
    TraceabilityGateRejected,
    TraceabilityGateUnavailable,
    TraceabilityReleaseWatermark,
    VerifierHeldTrustMaterial,
    verify_active_release_pointer,
    verify_release_gate,
)


def _registry_path() -> Path:
    return Path(__file__).parents[4] / "docs" / "design" / "semantic_ingestion" / "traceability_registry" / "registry-v1.json"


def _signature(profile: str, key: str, payload: bytes) -> bytes:
    """A deterministic independent verifier, never a permissive test callback."""
    return sha256(b"memorii:test-verifier:v1\0" + profile.encode() + b"\0" + key.encode() + b"\0" + payload).digest()


def _verifier(profile: str, key: str, payload: bytes, signature: bytes) -> bool:
    return signature == _signature(profile, key, payload)


def _signed(body: dict[str, object], *, domain: bytes, digest_field: str, profile: str = "deterministic-v1", key: str = "bootstrap-key") -> bytes:
    digest = sha256(domain + b"\0" + canonical_document(body)).hexdigest()
    return canonical_document({**body, digest_field: digest, "signature": _signature(profile, key, digest.encode("ascii")).hex()})


def _trusted_artifacts(*, mutated: str | None = None) -> tuple[dict[str, bytes], VerifierHeldTrustMaterial]:
    registry = load_registry(_registry_path())
    now = datetime(2026, 1, 2, tzinfo=UTC)
    bootstrap = _signed({"anchor_id": "bootstrap", "issuance_purpose": "semantic_ingestion_traceability_release_root", "canonical_profile_id": "memorii-sia-canonical-json-v1", "signature_profile_id": "deterministic-v1", "public_key_or_root_certificate_digest": "bootstrap-key", "target_authority_id": "authority"}, domain=b"memorii:sia-traceability-bootstrap-anchor:v1", digest_field="anchor_digest")
    bootstrap_value = __import__("json").loads(bootstrap)
    recovery = _signed({"recovery_root_id": "recovery", "issuance_purpose": "semantic_ingestion_traceability_recovery_root", "canonical_profile_id": "memorii-sia-canonical-json-v1", "signature_profile_id": "deterministic-v1", "public_key_or_root_certificate_digest": "recovery-key", "target_authority_id": "authority"}, domain=b"memorii:sia-traceability-recovery-root:v1", digest_field="recovery_root_digest", key="recovery-key")
    recovery_value = __import__("json").loads(recovery)
    policy = _signed({"issuance_purpose": "semantic_ingestion_traceability_recovery_policy", "canonical_profile_id": "memorii-sia-canonical-json-v1", "signature_profile_id": "deterministic-v1", "policy_signer_key_or_certificate_digest": "bootstrap-key", "active_bootstrap_anchor_digest": bootstrap_value["anchor_digest"], "eligible_recovery_root_digests": [recovery_value["recovery_root_digest"]], "threshold": 1}, domain=b"memorii:sia-traceability-recovery-policy:v1", digest_field="recovery_policy_digest")
    record_body: dict[str, object] = {"issuance_purpose": "semantic_ingestion_traceability_trust_lifecycle", "sequence": 1, "predecessor_record_digest": None, "effective_at": "2026-01-01T00:00:00Z", "recorded_at": "2026-01-01T00:00:01Z", "action": "activate", "target_id": "bootstrap", "target_digest": bootstrap_value["anchor_digest"], "replacement_target_id": None, "replacement_target_digest": None, "signer_bindings": [{"signer_id": "bootstrap", "signature_profile_id": "deterministic-v1", "key_digest": "bootstrap-key"}]}
    record_digest = sha256(b"memorii:sia-traceability-lifecycle-record:v1\0" + canonical_document(record_body)).hexdigest()
    record = {**record_body, "record_digest": record_digest, "signatures": [_signature("deterministic-v1", "bootstrap-key", record_digest.encode("ascii")).hex()]}
    root_body = {"authority_id": "authority", "records": [record]}
    root_digest = sha256(b"memorii:sia-traceability-trust-lifecycle-root:v1\0" + canonical_document(root_body)).hexdigest()
    lifecycle = canonical_document({**root_body, "lifecycle_root_digest": root_digest, "signature": _signature("deterministic-v1", "bootstrap-key", root_digest.encode("ascii")).hex()})
    roots = {"registry_source_identity": registry.source_identity, **{f"{name}_digest": digest for name, digest in registry.root_digests.items()}, "design_document_digest": "design", "structural_manifest_digest": "structural", "coverage_root_digest": "coverage", "execution_root_digest": "execution", "report_schema_registry_digest": "report-schema", "runner_environment_profile_registry_digest": "runner-profile", "trust_snapshot_digest": "trust"}
    release_body: dict[str, object] = {"release_id": "one", "issuance_purpose": "semantic_ingestion_traceability_release", "canonical_profile_id": "memorii-sia-canonical-json-v1", "signature_profile_id": "deterministic-v1", "issuer_key_or_certificate_digest": "bootstrap-key", "grammar_revision": registry.source["grammar_revision"], "state": "active", "predecessor_release_id": None, "supersedes_release_id": None, "bootstrap_anchor_digest": bootstrap_value["anchor_digest"], "recovery_root_digest": recovery_value["recovery_root_digest"], "issued_at": "2026-01-01T00:00:02Z", "expires_at": (now + timedelta(days=1)).isoformat(), "epoch": 1, "sequence": 1, **roots}
    release = _signed(release_body, domain=b"memorii:sia-traceability-release:v1", digest_field="release_digest")
    pointer_body = {"release_id": "one", "release_digest": __import__("json").loads(release)["release_digest"], "epoch": 1, "sequence": 1, "signature_profile_id": "deterministic-v1", "issuer_key_or_certificate_digest": "bootstrap-key"}
    pointer = _signed(pointer_body, domain=b"memorii:sia-traceability-active-release-pointer:v1", digest_field="active_pointer_digest")
    artifacts = {"bootstrap": bootstrap, "recovery": recovery, "lifecycle": lifecycle, "release": release, "pointer": pointer, "history": canonical_document({"releases": [json.loads(release)]})}
    if mutated is not None:
        artifacts[mutated] = artifacts[mutated] + b" "
    return artifacts, VerifierHeldTrustMaterial(bootstrap, (recovery,), _verifier, policy)


def test_sia_t03_registry_loads_exact_frozen_source_and_dag() -> None:
    registry = load_registry(_registry_path())
    assert registry.source_identity == "7a1a8d2b1b9abbf1cf6027f8c4600b833801d52a8319acec879c43d427a72bb3"
    assert len(registry.source["heading_defaults"]) == 144


@pytest.mark.parametrize("mutation", [b" ", b"\n", b"\xef\xbb\xbf"])
def test_sia_t03_registry_rejects_noncanonical_raw_bytes(tmp_path: Path, mutation: bytes) -> None:
    target = tmp_path / "registry.json"
    target.write_bytes(_registry_path().read_bytes() + mutation)
    with pytest.raises(RegistryValidationError):
        load_registry(target)


def test_sia_t03_independent_approval_loader_consumes_raw_bytes() -> None:
    assert len(load_independent_registry_bytes(_registry_path().read_bytes())["heading_defaults"]) == 144
    with pytest.raises(TraceabilityCoverageError):
        load_independent_registry_bytes(_registry_path().read_bytes() + b" ")


def test_sia_t03_independent_raw_root_rebuild_equals_generator_for_every_root() -> None:
    """Approval uses raw bytes; every nested specialized item participates."""
    registry = load_registry(_registry_path())
    design = (Path(__file__).parents[4] / "docs" / "design" / "semantic_ingestion_architecture.md").read_bytes()
    rebuilt = rebuild_structural_manifest_bytes(
        design_bytes=design, registry=registry, registry_bytes=_registry_path().read_bytes()
    )
    assert rebuilt == rebuild_structural_manifest_bytes(design_bytes=design, registry=registry)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda source: source["report_schemas"][0]["schema_document"].__setitem__("title", "substituted"),
        lambda source: source["runner_environment_profiles"][0]["network_policy"].__setitem__("enforcement", "allowed"),
        lambda source: source["test_evidence_groups"].reverse(),
    ],
)
def test_sia_t03_both_approval_loaders_reject_specialized_schema_profile_or_order_mutations(tmp_path: Path, mutate: object) -> None:
    source = json.loads(_registry_path().read_text())
    assert callable(mutate)
    mutate(source)
    target = tmp_path / "registry.json"
    target.write_bytes(canonical_document(source))
    with pytest.raises(RegistryValidationError):
        load_registry(target)
    with pytest.raises(TraceabilityCoverageError):
        load_independent_registry_bytes(target.read_bytes())


def test_sia_t03_release_gate_is_typed_unavailable_without_independent_material() -> None:
    result = verify_release_gate(registry=load_registry(_registry_path()), bootstrap_artifact=None, recovery_artifact=None, lifecycle_artifact=None, release_artifact=None)
    assert isinstance(result, TraceabilityGateUnavailable)


def test_sia_t03_release_gate_accepts_complete_genesis_and_signed_pointer() -> None:
    artifacts, material = _trusted_artifacts()
    result = verify_release_gate(registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"], recovery_artifact=artifacts["recovery"], lifecycle_artifact=artifacts["lifecycle"], release_artifact=artifacts["release"], release_history_artifact=artifacts["history"], active_pointer_artifact=artifacts["pointer"], verifier_material=material, now=datetime(2026, 1, 2, tzinfo=UTC))
    assert isinstance(result, TraceabilityGateAuthorized)


def test_sia_t03_recovery_root_cannot_sign_an_ordinary_release_or_pointer() -> None:
    artifacts, material = _trusted_artifacts()
    release = json.loads(artifacts["release"])
    body = {key: value for key, value in release.items() if key not in {"release_digest", "signature"}}
    artifacts["release"] = _signed(
        {**body, "issuer_key_or_certificate_digest": "recovery-key"},
        domain=b"memorii:sia-traceability-release:v1", digest_field="release_digest", key="recovery-key",
    )
    pointer = json.loads(artifacts["pointer"])
    pointer_body = {key: value for key, value in pointer.items() if key not in {"active_pointer_digest", "signature"}}
    artifacts["pointer"] = _signed(
        {**pointer_body, "release_digest": json.loads(artifacts["release"])["release_digest"], "issuer_key_or_certificate_digest": "recovery-key"},
        domain=b"memorii:sia-traceability-active-release-pointer:v1", digest_field="active_pointer_digest", key="recovery-key",
    )
    artifacts["history"] = canonical_document({"releases": [json.loads(artifacts["release"])]})
    result = verify_release_gate(registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"], recovery_artifact=artifacts["recovery"], lifecycle_artifact=artifacts["lifecycle"], release_artifact=artifacts["release"], release_history_artifact=artifacts["history"], active_pointer_artifact=artifacts["pointer"], verifier_material=material, now=datetime(2026, 1, 2, tzinfo=UTC))
    assert isinstance(result, TraceabilityGateRejected)


def test_sia_t03_acceptance_owned_watermark_rejects_history_replay() -> None:
    artifacts, material = _trusted_artifacts()
    watermark = TraceabilityReleaseWatermark(epoch=1, sequence=2, release_digest="newer")
    result = verify_release_gate(registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"], recovery_artifact=artifacts["recovery"], lifecycle_artifact=artifacts["lifecycle"], release_artifact=artifacts["release"], release_history_artifact=artifacts["history"], active_pointer_artifact=artifacts["pointer"], verifier_material=material, watermark=watermark, now=datetime(2026, 1, 2, tzinfo=UTC))
    assert isinstance(result, TraceabilityGateRejected)


def test_sia_t03_release_gate_requires_complete_history_and_signed_pointer() -> None:
    artifacts, material = _trusted_artifacts()
    result = verify_release_gate(
        registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"],
        recovery_artifact=artifacts["recovery"], lifecycle_artifact=artifacts["lifecycle"],
        release_artifact=artifacts["release"], verifier_material=material, now=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert isinstance(result, TraceabilityGateUnavailable)


@pytest.mark.parametrize(
    ("now", "authorized"),
    [
        (datetime(2025, 12, 31, tzinfo=UTC), False),
        (datetime(2026, 1, 3, tzinfo=UTC), True),
        (datetime(2026, 1, 3, 0, 0, 1, tzinfo=UTC), False),
    ],
)
def test_sia_t03_current_release_enforces_inclusive_issued_expiry_window(now: datetime, authorized: bool) -> None:
    artifacts, material = _trusted_artifacts()
    result = verify_release_gate(registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"], recovery_artifact=artifacts["recovery"], lifecycle_artifact=artifacts["lifecycle"], release_artifact=artifacts["release"], release_history_artifact=artifacts["history"], active_pointer_artifact=artifacts["pointer"], verifier_material=material, now=now)
    assert isinstance(result, TraceabilityGateAuthorized) is authorized


@pytest.mark.parametrize("mutated", ["bootstrap", "recovery", "lifecycle", "release", "pointer"])
def test_sia_t03_release_gate_rejects_mutated_or_same_coordinate_substitution(mutated: str) -> None:
    artifacts, material = _trusted_artifacts(mutated=mutated)
    result = verify_release_gate(registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"], recovery_artifact=artifacts["recovery"], lifecycle_artifact=artifacts["lifecycle"], release_artifact=artifacts["release"], release_history_artifact=artifacts["history"], active_pointer_artifact=artifacts["pointer"], verifier_material=material, now=datetime(2026, 1, 2, tzinfo=UTC))
    assert isinstance(result, TraceabilityGateRejected)


def test_sia_t03_active_pointer_requires_monotonic_successor_and_signed_current_pointer() -> None:
    artifacts, material = _trusted_artifacts()
    release = __import__("json").loads(artifacts["release"])
    required = {key: release[key] for key in release if key.endswith("_digest") or key == "registry_source_identity"}
    pointer = __import__("json").loads(artifacts["pointer"])
    assert verify_active_release_pointer(releases=(release,), active_pointer=pointer, required_roots=required, verifier=_verifier)["release_id"] == "one"
    pointer["sequence"] = 0
    with pytest.raises(ValueError, match="active_pointer"):
        verify_active_release_pointer(releases=(release,), active_pointer=pointer, required_roots=required, verifier=_verifier)
    assert material.recovery_policy_bytes is not None


def test_sia_t03_release_gate_accepts_explicit_higher_sequence_rollback_history() -> None:
    artifacts, material = _trusted_artifacts()
    genesis = json.loads(artifacts["release"])
    genesis_body = {key: value for key, value in genesis.items() if key not in {"release_digest", "signature"}}
    genesis = json.loads(_signed({**genesis_body, "state": "superseded"}, domain=b"memorii:sia-traceability-release:v1", digest_field="release_digest"))
    successor_body = {key: value for key, value in genesis.items() if key not in {"release_digest", "signature"}}
    successor = json.loads(_signed({
        **successor_body,
        "release_id": "two",
        "state": "active",
        "predecessor_release_id": "one",
        "supersedes_release_id": "one",
        "sequence": 2,
        "issued_at": "2026-01-01T00:00:03Z",
    }, domain=b"memorii:sia-traceability-release:v1", digest_field="release_digest"))
    pointer = json.loads(artifacts["pointer"])
    pointer_body = {key: value for key, value in pointer.items() if key not in {"active_pointer_digest", "signature"}}
    artifacts["pointer"] = _signed({**pointer_body, "release_id": "two", "release_digest": successor["release_digest"], "sequence": 2}, domain=b"memorii:sia-traceability-active-release-pointer:v1", digest_field="active_pointer_digest")
    history = canonical_document({"releases": [genesis, successor]})
    result = verify_release_gate(registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"], recovery_artifact=artifacts["recovery"], lifecycle_artifact=artifacts["lifecycle"], release_artifact=canonical_document(successor), release_history_artifact=history, active_pointer_artifact=artifacts["pointer"], verifier_material=material, now=datetime(2026, 1, 2, tzinfo=UTC))
    assert isinstance(result, TraceabilityGateAuthorized)
    successor["supersedes_release_id"] = "unrelated"
    with pytest.raises(ValueError):
        verify_active_release_pointer(releases=(genesis, successor), active_pointer=json.loads(artifacts["pointer"]), required_roots={key: successor[key] for key in successor if key.endswith("_digest") or key == "registry_source_identity"}, verifier=_verifier)


def test_sia_t03_release_gate_accepts_rotated_lifecycle_signer() -> None:
    artifacts, material = _trusted_artifacts()
    rotated_root = _signed({"anchor_id": "bootstrap-rotated", "issuance_purpose": "semantic_ingestion_traceability_release_root", "canonical_profile_id": "memorii-sia-canonical-json-v1", "signature_profile_id": "deterministic-v1", "public_key_or_root_certificate_digest": "rotated-key", "target_authority_id": "authority", "effective_at": "2026-01-01T00:00:02Z"}, domain=b"memorii:sia-traceability-bootstrap-anchor:v1", digest_field="anchor_digest", key="rotated-key")
    rotated_digest = json.loads(rotated_root)["anchor_digest"]
    lifecycle = json.loads(artifacts["lifecycle"])
    previous = lifecycle["records"][-1]
    body = {
        "issuance_purpose": "semantic_ingestion_traceability_trust_lifecycle",
        "sequence": 2,
        "predecessor_record_digest": previous["record_digest"],
        "effective_at": "2026-01-01T00:00:02Z",
        "recorded_at": "2026-01-01T00:00:03Z",
        "action": "rotate",
        "target_id": "bootstrap",
        "target_digest": json.loads(artifacts["bootstrap"])["anchor_digest"],
        "replacement_target_id": "bootstrap-rotated",
        "replacement_target_digest": rotated_digest,
        "replacement_signature_profile_id": "deterministic-v1",
        "replacement_key_digest": "rotated-key",
        "signer_bindings": [{"signer_id": "bootstrap", "signature_profile_id": "deterministic-v1", "key_digest": "bootstrap-key"}],
    }
    digest = sha256(b"memorii:sia-traceability-lifecycle-record:v1\0" + canonical_document(body)).hexdigest()
    record = {**body, "record_digest": digest, "signatures": [_signature("deterministic-v1", "bootstrap-key", digest.encode("ascii")).hex()]}
    root_body = {"authority_id": "authority", "records": [*lifecycle["records"], record]}
    root_digest = sha256(b"memorii:sia-traceability-trust-lifecycle-root:v1\0" + canonical_document(root_body)).hexdigest()
    artifacts["lifecycle"] = canonical_document({**root_body, "lifecycle_root_digest": root_digest, "signature": _signature("deterministic-v1", "bootstrap-key", root_digest.encode("ascii")).hex()})
    release = json.loads(artifacts["release"])
    release_body = {key: value for key, value in release.items() if key not in {"release_digest", "signature"}}
    artifacts["release"] = _signed({**release_body, "issuer_key_or_certificate_digest": "rotated-key", "issued_at": "2026-01-01T00:00:04Z"}, domain=b"memorii:sia-traceability-release:v1", digest_field="release_digest", key="rotated-key")
    pointer = json.loads(artifacts["pointer"])
    pointer_body = {key: value for key, value in pointer.items() if key not in {"active_pointer_digest", "signature"}}
    artifacts["pointer"] = _signed({**pointer_body, "release_digest": json.loads(artifacts["release"])["release_digest"], "issuer_key_or_certificate_digest": "rotated-key"}, domain=b"memorii:sia-traceability-active-release-pointer:v1", digest_field="active_pointer_digest", key="rotated-key")
    artifacts["history"] = canonical_document({"releases": [json.loads(artifacts["release"])]})
    material = VerifierHeldTrustMaterial(material.bootstrap_anchor_bytes, material.recovery_root_bytes, _verifier, material.recovery_policy_bytes, (rotated_root,))
    result = verify_release_gate(registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"], recovery_artifact=artifacts["recovery"], lifecycle_artifact=artifacts["lifecycle"], release_artifact=artifacts["release"], release_history_artifact=artifacts["history"], active_pointer_artifact=artifacts["pointer"], verifier_material=material, now=datetime(2026, 1, 2, tzinfo=UTC))
    assert isinstance(result, TraceabilityGateAuthorized)


def test_sia_t03_release_gate_requires_threshold_recovery_and_authorizes_recovered_signer() -> None:
    artifacts, material = _trusted_artifacts()
    bootstrap = json.loads(artifacts["bootstrap"])
    first_recovery = json.loads(artifacts["recovery"])
    second_recovery_bytes = _signed({
        "recovery_root_id": "recovery-two", "issuance_purpose": "semantic_ingestion_traceability_recovery_root",
        "canonical_profile_id": "memorii-sia-canonical-json-v1", "signature_profile_id": "deterministic-v1",
        "public_key_or_root_certificate_digest": "recovery-two-key", "target_authority_id": "authority",
    }, domain=b"memorii:sia-traceability-recovery-root:v1", digest_field="recovery_root_digest", key="recovery-two-key")
    second_recovery = json.loads(second_recovery_bytes)
    recovered_root = _signed({"anchor_id": "bootstrap-recovered", "issuance_purpose": "semantic_ingestion_traceability_release_root", "canonical_profile_id": "memorii-sia-canonical-json-v1", "signature_profile_id": "deterministic-v1", "public_key_or_root_certificate_digest": "recovered-key", "target_authority_id": "authority", "effective_at": "2026-01-01T00:00:02Z"}, domain=b"memorii:sia-traceability-bootstrap-anchor:v1", digest_field="anchor_digest", key="recovered-key")
    recovered_digest = json.loads(recovered_root)["anchor_digest"]
    policy = _signed({
        "issuance_purpose": "semantic_ingestion_traceability_recovery_policy", "canonical_profile_id": "memorii-sia-canonical-json-v1",
        "signature_profile_id": "deterministic-v1", "policy_signer_key_or_certificate_digest": "bootstrap-key",
        "active_bootstrap_anchor_digest": bootstrap["anchor_digest"],
        "eligible_recovery_root_digests": [first_recovery["recovery_root_digest"], second_recovery["recovery_root_digest"]], "threshold": 2,
    }, domain=b"memorii:sia-traceability-recovery-policy:v1", digest_field="recovery_policy_digest")
    lifecycle = json.loads(artifacts["lifecycle"])
    body = {
        "issuance_purpose": "semantic_ingestion_traceability_trust_lifecycle", "sequence": 2,
        "predecessor_record_digest": lifecycle["records"][-1]["record_digest"], "effective_at": "2026-01-01T00:00:02Z",
        "recorded_at": "2026-01-01T00:00:03Z", "action": "recover", "target_id": "bootstrap",
        "target_digest": bootstrap["anchor_digest"], "replacement_target_id": "bootstrap-recovered",
        "replacement_target_digest": recovered_digest, "replacement_signature_profile_id": "deterministic-v1",
        "replacement_key_digest": "recovered-key", "signer_bindings": [
            {"signer_id": "recovery-one", "signature_profile_id": "deterministic-v1", "key_digest": "recovery-key", "recovery_root_digest": first_recovery["recovery_root_digest"]},
            {"signer_id": "recovery-two", "signature_profile_id": "deterministic-v1", "key_digest": "recovery-two-key", "recovery_root_digest": second_recovery["recovery_root_digest"]},
        ],
    }
    digest = sha256(b"memorii:sia-traceability-lifecycle-record:v1\0" + canonical_document(body)).hexdigest()
    record = {**body, "record_digest": digest, "signatures": [_signature("deterministic-v1", "recovery-key", digest.encode("ascii")).hex(), _signature("deterministic-v1", "recovery-two-key", digest.encode("ascii")).hex()]}
    root_body = {"authority_id": "authority", "records": [*lifecycle["records"], record]}
    root_digest = sha256(b"memorii:sia-traceability-trust-lifecycle-root:v1\0" + canonical_document(root_body)).hexdigest()
    artifacts["lifecycle"] = canonical_document({**root_body, "lifecycle_root_digest": root_digest, "signature": _signature("deterministic-v1", "bootstrap-key", root_digest.encode("ascii")).hex()})
    release = json.loads(artifacts["release"])
    release_body = {key: value for key, value in release.items() if key not in {"release_digest", "signature"}}
    artifacts["release"] = _signed({**release_body, "issuer_key_or_certificate_digest": "recovered-key", "issued_at": "2026-01-01T00:00:04Z"}, domain=b"memorii:sia-traceability-release:v1", digest_field="release_digest", key="recovered-key")
    pointer = json.loads(artifacts["pointer"])
    pointer_body = {key: value for key, value in pointer.items() if key not in {"active_pointer_digest", "signature"}}
    artifacts["pointer"] = _signed({**pointer_body, "release_digest": json.loads(artifacts["release"])["release_digest"], "issuer_key_or_certificate_digest": "recovered-key"}, domain=b"memorii:sia-traceability-active-release-pointer:v1", digest_field="active_pointer_digest", key="recovered-key")
    threshold_material = VerifierHeldTrustMaterial(artifacts["bootstrap"], (artifacts["recovery"], second_recovery_bytes), _verifier, policy, (recovered_root,))
    artifacts["history"] = canonical_document({"releases": [json.loads(artifacts["release"])]})
    result = verify_release_gate(registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"], recovery_artifact=artifacts["recovery"], recovery_artifacts=(second_recovery_bytes,), lifecycle_artifact=artifacts["lifecycle"], release_artifact=artifacts["release"], release_history_artifact=artifacts["history"], active_pointer_artifact=artifacts["pointer"], verifier_material=threshold_material, now=datetime(2026, 1, 2, tzinfo=UTC))
    assert isinstance(result, TraceabilityGateAuthorized)
    rejected = verify_release_gate(registry=load_registry(_registry_path()), bootstrap_artifact=artifacts["bootstrap"], recovery_artifact=artifacts["recovery"], lifecycle_artifact=artifacts["lifecycle"], release_artifact=artifacts["release"], release_history_artifact=artifacts["history"], active_pointer_artifact=artifacts["pointer"], verifier_material=threshold_material, now=datetime(2026, 1, 2, tzinfo=UTC))
    assert isinstance(rejected, TraceabilityGateRejected)
