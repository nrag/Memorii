"""CGS-01/02/03 closed provenance validation tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from memorii.core.memory_evolution.ingestion_contracts import (
    encode_typed_value,
    serialize_artifact,
)
from memorii.tools.semantic_ingestion_acceptance_watermark_store import (
    FileTraceabilityReleaseWatermarkStore,
    WatermarkAdvanced,
    WatermarkAdvanceResult,
)
from memorii.tools.semantic_ingestion_traceability_registry import (
    TraceabilityRegistry,
    canonical_document,
)
from memorii.tools.semantic_ingestion_traceability_release import (
    TraceabilityGateAuthorized,
    TraceabilityGateRejected,
    VerifierHeldTrustMaterial,
    _active_signer_or_reject,
    _binding_for,
    _load,
    _root_coordinate,
    _typed_digest,
    _validate_current_lifecycle_genesis,
    _validate_current_lifecycle_successor,
    _validate_provisioned_root_provenance,
    _validate_recovery_policy_provenance,
    _verify_corrected_recovery_policy,
    read_legacy_release_diagnostic,
    verify_release_gate,
)
from tests.fixtures.semantic_ingestion.current_release_chain import (
    AUTHORITY,
    RECORD_DIGEST,
    ROOT_DIGEST,
    _artifact,
    _binding,
    _bootstrap,
    _current_chain,
    _lifecycle,
    _policy,
    current_chain_successor,
)


def test_genesis_root_requires_exact_variant_and_forbids_predecessor() -> None:
    root = _bootstrap()
    _validate_provisioned_root_provenance(root, authority_id=AUTHORITY, lifecycle=_lifecycle())

    smuggled = deepcopy(root)
    smuggled["provenance"]["trust_lifecycle_root_digest"] = ROOT_DIGEST  # type: ignore[index]
    with pytest.raises(ValueError, match="provisioned_genesis_fields_invalid"):
        _validate_provisioned_root_provenance(smuggled, authority_id=AUTHORITY, lifecycle=_lifecycle())

    downgraded = deepcopy(root)
    downgraded["predecessor_anchor_digest"] = ROOT_DIGEST
    with pytest.raises(ValueError, match="provisioned_genesis_predecessor_invalid"):
        _validate_provisioned_root_provenance(downgraded, authority_id=AUTHORITY, lifecycle=_lifecycle())

    unknown = deepcopy(root)
    unknown["provenance"]["source_kind"] = "unrecognized"  # type: ignore[index]
    with pytest.raises(ValueError, match="provisioned_root_provenance_kind_invalid"):
        _validate_provisioned_root_provenance(unknown, authority_id=AUTHORITY, lifecycle=_lifecycle())


def test_successor_root_requires_prior_lifecycle_coordinate() -> None:
    root = _bootstrap()
    root["rotation_sequence"] = 2
    root["predecessor_anchor_id"] = "bootstrap-old"
    root["predecessor_anchor_digest"] = "d" * 64
    root["provenance"] = {
        "source_kind": "prior_verified_lifecycle_root",
        "authority_id": AUTHORITY,
        "trust_lifecycle_root_digest": ROOT_DIGEST,
        "lifecycle_record_digest": RECORD_DIGEST,
        "eligible_not_before": "2026-01-01T00:00:00Z",
        "eligible_not_after": None,
    }
    _validate_provisioned_root_provenance(root, authority_id=AUTHORITY, lifecycle=_lifecycle())

    root["provenance"]["lifecycle_record_digest"] = "e" * 64  # type: ignore[index]
    with pytest.raises(ValueError, match="provisioned_successor_lifecycle_record_invalid"):
        _validate_provisioned_root_provenance(root, authority_id=AUTHORITY, lifecycle=_lifecycle())

    root["provenance"]["lifecycle_record_digest"] = RECORD_DIGEST  # type: ignore[index]
    root["predecessor_anchor_id"] = "other"
    with pytest.raises(ValueError, match="provisioned_successor_lifecycle_binding_invalid"):
        _validate_provisioned_root_provenance(root, authority_id=AUTHORITY, lifecycle=_lifecycle())


def test_current_lifecycle_successor_replays_the_immediate_verifier_held_terminal() -> None:
    """The current CTV root accepts only its immediate, exact prior signer."""
    from hashlib import sha256

    key = "a" * 64
    profile = "profile-a"

    def signature(_profile: str, _key: str, payload: bytes) -> bytes:
        return sha256(_profile.encode() + b"\0" + _key.encode() + b"\0" + payload).digest()

    def record(
        sequence: int,
        predecessor: str | None,
        action: str,
        *,
        replacement: bool = False,
        eligibility_reference: dict[str, object] | None = None,
    ) -> dict[str, object]:
        body = {
            "record_id": f"record-{sequence}", "issuance_purpose": "semantic_ingestion_traceability_lifecycle_record",
            "target_kind": "bootstrap_anchor", "target_id": "bootstrap-a", "target_digest": ROOT_DIGEST,
            "action": action, "replacement_target_id": "bootstrap-b" if replacement else None,
            "replacement_target_digest": "c" * 64 if replacement else None,
            "canonical_profile_binding": _binding_for("lifecycle_record"),
            "effective_at": f"2026-01-01T00:00:0{sequence}Z", "recorded_at": f"2026-01-01T00:00:0{sequence}Z",
            "sequence": sequence, "predecessor_record_digest": predecessor, "recovery_policy_digest": None,
            "signer_bindings": [{
                "signature_purpose": "semantic_ingestion_traceability_lifecycle_record", "signer_id": "bootstrap-a",
                "signer_key_or_certificate_digest": key, "signature_profile_id": profile,
                "eligibility_reference": eligibility_reference or {
                    "authority_id": AUTHORITY,
                    "eligible_not_before": "2026-01-01T00:00:00Z",
                    "eligible_not_after": None,
                },
                "recovery_root_digest": None,
            }],
        }
        digest = _typed_digest(b"memorii:sia-traceability-trust-lifecycle-record:v1", body)
        binding = body["signer_bindings"][0]
        preimage = encode_typed_value({"issuance_purpose": body["issuance_purpose"], "body_binding": body["canonical_profile_binding"], "record_digest": digest, "signer_binding": binding})
        return {**body, "record_digest": digest, "signatures": [signature(profile, key, preimage)]}

    first = record(1, None, "activate")

    def root(records: list[dict[str, object]], coordinate: dict[str, object]) -> dict[str, object]:
        body = {
            "authority_id": AUTHORITY, "issuance_purpose": "semantic_ingestion_traceability_lifecycle_root",
            "canonical_profile_binding": _binding_for("lifecycle"), "bootstrap_anchor_history_digest": "d" * 64,
            "recovery_root_history_digest": "e" * 64, "recovery_policy_history_digest": "f" * 64, "records": records,
        }
        digest = _typed_digest(b"memorii:sia-traceability-trust-lifecycle-root:v1", body)
        preimage = encode_typed_value({"issuance_purpose": body["issuance_purpose"], "body_binding": body["canonical_profile_binding"], "lifecycle_root_digest": digest, "signer_coordinate": coordinate})
        return {**body, "signer_coordinates": [coordinate], "signatures": [signature(profile, key, preimage)], "lifecycle_root_digest": digest}

    prior_coordinate = {"source_kind": "prior_verified_lifecycle_root", "signature_purpose": "semantic_ingestion_traceability_lifecycle_root", "issuer_id": "bootstrap-a", "key_or_certificate_digest": key, "signature_profile_id": profile, "trust_lifecycle_root_digest": "0" * 64, "lifecycle_record_digest": first["record_digest"], "eligible_not_before": "2026-01-01T00:00:00Z", "eligible_not_after": None}
    prior = root([first], prior_coordinate)
    first_digest = first["record_digest"]
    assert isinstance(first_digest, str)
    second = record(
        2,
        first_digest,
        "rotate",
        replacement=True,
        eligibility_reference={
            "source_kind": "prior_verified_lifecycle_root", "authority_id": AUTHORITY,
            "eligibility_purpose": "semantic_ingestion_traceability_lifecycle_record",
            "source_artifact_digest": prior["lifecycle_root_digest"],
            "prior_lifecycle_root_digest": prior["lifecycle_root_digest"],
            "prior_lifecycle_record_digest": first_digest, "prior_lifecycle_sequence": 1,
            "target_id": "bootstrap-a", "target_digest": ROOT_DIGEST,
            "eligible_not_before": "2026-01-01T00:00:00Z", "eligible_not_after": None,
            "provisioned_channel_id": "channel-a",
        },
    )
    coordinate = {**prior_coordinate, "trust_lifecycle_root_digest": prior["lifecycle_root_digest"]}
    successor = root([first, second], coordinate)
    prior_digest = prior["lifecycle_root_digest"]
    assert isinstance(prior_digest, str)

    _validate_current_lifecycle_successor(successor, authority_id=AUTHORITY, prior_verified_roots={prior_digest: prior}, verifier=lambda p, k, payload, value: value == signature(p, k, payload))

    substituted_prefix = deepcopy(successor)
    substituted_prefix["records"][0]["signatures"] = [b"alternate-valid-signature"]  # type: ignore[index]
    substituted_body = {
        key: substituted_prefix[key]
        for key in (
            "authority_id", "issuance_purpose", "canonical_profile_binding",
            "bootstrap_anchor_history_digest", "recovery_root_history_digest",
            "recovery_policy_history_digest", "records",
        )
    }
    substituted_prefix["lifecycle_root_digest"] = _typed_digest(
        b"memorii:sia-traceability-trust-lifecycle-root:v1", substituted_body
    )
    with pytest.raises(ValueError, match="lifecycle_root_successor_not_append_only"):
        _validate_current_lifecycle_successor(
            substituted_prefix,
            authority_id=AUTHORITY,
            prior_verified_roots={prior_digest: prior},
            verifier=lambda _p, _k, _payload, _value: True,
        )

    mismatched = deepcopy(successor)
    mismatched["signer_coordinates"][0]["issuer_id"] = "other"  # type: ignore[index]
    with pytest.raises(ValueError, match="lifecycle_root_successor_not_final_action_authorized"):
        _validate_current_lifecycle_successor(mismatched, authority_id=AUTHORITY, prior_verified_roots={prior_digest: prior}, verifier=lambda p, k, payload, value: value == signature(p, k, payload))

    with pytest.raises(ValueError, match="lifecycle_root_successor_reference_unverified"):
        _validate_current_lifecycle_successor(successor, authority_id=AUTHORITY, prior_verified_roots={}, verifier=lambda p, k, payload, value: value == signature(p, k, payload))


def test_current_lifecycle_genesis_copies_exact_provisioned_interval() -> None:
    chain = _current_chain()
    bootstrap = _load(chain["bootstrap"], "bootstrap")  # type: ignore[arg-type]
    genesis = _load(chain["prior_lifecycle"], "lifecycle")  # type: ignore[arg-type]
    record = genesis["records"][0]
    binding = record["signer_bindings"][0]
    binding["eligibility_reference"]["eligible_not_before"] = "2026-01-01T00:00:00.500000Z"
    body_keys = {
        "record_id", "issuance_purpose", "target_kind", "target_id", "target_digest",
        "action", "replacement_target_id", "replacement_target_digest",
        "canonical_profile_binding", "effective_at", "recorded_at", "sequence",
        "predecessor_record_digest", "recovery_policy_digest", "signer_bindings",
    }
    record["record_digest"] = _typed_digest(
        b"memorii:sia-traceability-trust-lifecycle-record:v1",
        {key: record[key] for key in body_keys},
    )
    with pytest.raises(ValueError, match="lifecycle_genesis_eligibility_window_invalid"):
        _validate_current_lifecycle_genesis(
            genesis,
            authority_id=AUTHORITY,
            bootstrap=bootstrap,
            verifier=lambda _p, _k, _payload, _value: True,
        )


def test_historical_release_rejects_a_signer_outside_its_issuance_interval() -> None:
    """A replayed historical release cannot borrow a later signer interval."""
    intervals: dict[tuple[str, str], tuple[str, str, datetime, datetime | None]] = {
        ("bootstrap-a", ROOT_DIGEST): (
            "profile-a",
            "key-a",
            datetime(2026, 1, 2, tzinfo=UTC),
            datetime(2026, 1, 3, tzinfo=UTC),
        )
    }

    with pytest.raises(ValueError, match="release_signer_not_lifecycle_eligible"):
        _active_signer_or_reject(
            active=intervals,
            profile="profile-a",
            key="key-a",
            issued_at=datetime(2026, 1, 1, tzinfo=UTC),
            purpose="semantic_ingestion_traceability_release",
        )


def test_revoked_historical_signer_cannot_sign_at_or_after_revocation() -> None:
    intervals: dict[tuple[str, str], tuple[str, str, datetime, datetime | None]] = {
        ("bootstrap-a", ROOT_DIGEST): (
            "profile-a",
            "key-a",
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 1, 3, tzinfo=UTC),
        )
    }

    with pytest.raises(ValueError, match="release_signer_not_lifecycle_eligible"):
        _active_signer_or_reject(
            active=intervals,
            profile="profile-a",
            key="key-a",
            issued_at=datetime(2026, 1, 3, tzinfo=UTC),
            purpose="semantic_ingestion_traceability_release",
        )


def test_selected_current_release_requires_a_presently_eligible_signer() -> None:
    intervals: dict[tuple[str, str], tuple[str, str, datetime, datetime | None]] = {
        ("bootstrap-a", ROOT_DIGEST): (
            "profile-a",
            "key-a",
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 1, 3, tzinfo=UTC),
        )
    }

    with pytest.raises(ValueError, match="release_signer_not_lifecycle_eligible"):
        _active_signer_or_reject(
            active=intervals,
            profile="profile-a",
            key="key-a",
            issued_at=datetime(2026, 1, 4, tzinfo=UTC),
            purpose="semantic_ingestion_traceability_release",
        )


def test_recovery_policy_genesis_and_successor_variants_are_closed() -> None:
    bootstrap = _bootstrap()
    policy = _policy()
    _validate_recovery_policy_provenance(policy, authority_id=AUTHORITY, bootstrap=bootstrap, lifecycle=_lifecycle())
    policy["signer_provenance"]["trust_lifecycle_root_digest"] = ROOT_DIGEST  # type: ignore[index]
    with pytest.raises(ValueError, match="recovery_policy_genesis_fields_invalid"):
        _validate_recovery_policy_provenance(policy, authority_id=AUTHORITY, bootstrap=bootstrap, lifecycle=_lifecycle())

    policy = _policy()
    policy["sequence"] = 2
    policy["predecessor_policy_digest"] = "f" * 64
    policy["signer_provenance"] = {
        "source_kind": "prior_verified_lifecycle_root",
        "signature_purpose": "semantic_ingestion_traceability_recovery_policy",
        "issuer_id": "bootstrap-a",
        "key_or_certificate_digest": "key-a",
        "signature_profile_id": "profile-a",
        "trust_lifecycle_root_digest": ROOT_DIGEST,
        "lifecycle_record_digest": RECORD_DIGEST,
        "eligible_not_before": "2026-01-01T00:00:00Z",
        "eligible_not_after": None,
    }
    _validate_recovery_policy_provenance(policy, authority_id=AUTHORITY, bootstrap=bootstrap, lifecycle=_lifecycle())


def test_recovery_policy_signature_uses_complete_typed_provenance_preimage() -> None:
    bootstrap = _bootstrap()
    policy = {
        "policy_id": "policy-a",
        "issuance_purpose": "semantic_ingestion_traceability_recovery_policy",
        "target_authority_id": AUTHORITY,
        "bootstrap_anchor_id": "bootstrap-a",
        "bootstrap_anchor_digest": _root_coordinate(bootstrap)[2],
        "eligible_recovery_root_digests": ["d" * 64],
        "minimum_distinct_signatures": 1,
        "signer_separation_rule_digest": "e" * 64,
        "canonical_profile_binding": _binding_for("recovery_policy"),
        "effective_at": "2026-01-01T00:00:00Z",
        "recorded_at": "2026-01-01T00:00:01Z",
        "sequence": 1,
        "predecessor_policy_digest": None,
        "expires_at": None,
        "signer_provenance": _policy()["signer_provenance"],
    }
    digest = _typed_digest(b"memorii:sia-traceability-recovery-policy:v1", policy)
    policy["recovery_policy_digest"] = digest
    payload = encode_typed_value(
        {
            "issuance_purpose": policy["issuance_purpose"],
            "body_binding": policy["canonical_profile_binding"],
            "recovery_policy_digest": digest,
            "signer_provenance": policy["signer_provenance"],
        }
    )
    calls: list[bytes] = []

    def verifier(profile: str, key: str, actual: bytes, signature: bytes) -> bool:
        calls.append(actual)
        return (profile, key, actual, signature) == ("profile-a", "a" * 64, payload, b"ok")

    policy["signature"] = b"ok".hex()
    assert _verify_corrected_recovery_policy(
        policy, authority_id=AUTHORITY, bootstrap=bootstrap, lifecycle=_lifecycle(), verifier=verifier
    ) == digest
    assert calls == [payload]

    malformed = deepcopy(policy)
    malformed["signer_provenance"]["extra"] = "smuggled"  # type: ignore[index]
    with pytest.raises(ValueError, match="recovery_policy_genesis_fields_invalid"):
        _verify_corrected_recovery_policy(
            malformed, authority_id=AUTHORITY, bootstrap=bootstrap, lifecycle=_lifecycle(), verifier=verifier
        )
    assert calls == [payload]


def test_legacy_diagnostic_has_no_authorization_or_mutation_surface() -> None:
    assert (
        read_legacy_release_diagnostic(canonical_document({"release_id": "old"}), name="release").reason
        == "legacy_incomplete_provenance"
    )
    assert read_legacy_release_diagnostic(b"not-json", name="release").reason == "legacy_transport_invalid"


def test_current_ctv_rotation_chain_authorizes_and_replays_byte_identically(tmp_path: Path) -> None:
    chain = _current_chain()
    registry = chain["registry"]
    bootstrap = chain["bootstrap"]
    recovery = chain["recovery"]
    lifecycle = chain["lifecycle"]
    release = chain["release"]
    pointer = chain["pointer"]
    history = chain["history"]
    material = chain["material"]
    roots = chain["roots"]
    now = chain["now"]
    release_digest = chain["release_digest"]
    assert isinstance(registry, TraceabilityRegistry)
    assert isinstance(bootstrap, bytes) and isinstance(recovery, bytes) and isinstance(lifecycle, bytes)
    assert isinstance(release, bytes) and isinstance(pointer, bytes) and isinstance(history, bytes)
    assert isinstance(material, VerifierHeldTrustMaterial) and isinstance(roots, dict)
    assert isinstance(now, datetime) and isinstance(release_digest, str)
    store = FileTraceabilityReleaseWatermarkStore(tmp_path / "watermark.json")
    assert isinstance(store.provision(1, 1, release_digest), WatermarkAdvanced)

    def gate() -> object:
        return verify_release_gate(
            registry=registry,
            bootstrap_artifact=bootstrap, recovery_artifact=recovery,
            lifecycle_artifact=lifecycle, release_artifact=release,
            active_pointer_artifact=pointer, release_history_artifact=history,
            verifier_material=material, watermark_store=store,
            expected_release_roots=roots, now=now,
        )

    first = gate()
    assert isinstance(first, TraceabilityGateAuthorized), first
    watermark = (tmp_path / "watermark.json").read_bytes()
    replay = gate()
    assert isinstance(replay, TraceabilityGateAuthorized), replay
    assert replay == first
    assert (tmp_path / "watermark.json").read_bytes() == watermark


def test_current_ctv_release_successor_advances_exactly_once(tmp_path: Path) -> None:
    first = _current_chain()
    second = current_chain_successor(first)
    registry = first["registry"]
    material = first["material"]
    roots = first["roots"]
    now = first["now"]
    assert isinstance(registry, TraceabilityRegistry)
    assert isinstance(material, VerifierHeldTrustMaterial)
    assert isinstance(roots, dict) and isinstance(now, datetime)
    first_digest = first["release_digest"]
    assert isinstance(first_digest, str)
    store = FileTraceabilityReleaseWatermarkStore(tmp_path / "watermark.json")
    assert isinstance(store.provision(1, 1, first_digest), WatermarkAdvanced)

    def gate(chain: dict[str, object]) -> object:
        return verify_release_gate(
            registry=registry,
            bootstrap_artifact=chain["bootstrap"],  # type: ignore[arg-type]
            recovery_artifact=chain["recovery"],  # type: ignore[arg-type]
            lifecycle_artifact=chain["lifecycle"],  # type: ignore[arg-type]
            release_artifact=chain["release"],  # type: ignore[arg-type]
            active_pointer_artifact=chain["pointer"],  # type: ignore[arg-type]
            release_history_artifact=chain["history"],  # type: ignore[arg-type]
            historical_release_artifacts=chain.get("historical_releases", ()),  # type: ignore[arg-type]
            verifier_material=material,
            watermark_store=store,
            expected_release_roots=roots,
            now=now,
        )

    assert isinstance(gate(first), TraceabilityGateAuthorized)
    advanced = gate(second)
    assert isinstance(advanced, TraceabilityGateAuthorized), advanced
    persisted = (tmp_path / "watermark.json").read_bytes()
    assert isinstance(gate(second), TraceabilityGateAuthorized)
    assert (tmp_path / "watermark.json").read_bytes() == persisted


def test_current_ctv_threshold_recovery_then_rotation_authorizes(tmp_path: Path) -> None:
    chain = _current_chain(threshold_recovery=True)
    release_digest = chain["release_digest"]
    assert isinstance(release_digest, str)
    store = FileTraceabilityReleaseWatermarkStore(tmp_path / "watermark.json")
    assert isinstance(store.provision(1, 1, release_digest), WatermarkAdvanced)
    result = verify_release_gate(
        registry=chain["registry"],  # type: ignore[arg-type]
        bootstrap_artifact=chain["bootstrap"],  # type: ignore[arg-type]
        recovery_artifact=chain["recovery"],  # type: ignore[arg-type]
        recovery_artifacts=chain["recoveries"][1:],  # type: ignore[index,arg-type]
        lifecycle_artifact=chain["lifecycle"],  # type: ignore[arg-type]
        release_artifact=chain["release"],  # type: ignore[arg-type]
        active_pointer_artifact=chain["pointer"],  # type: ignore[arg-type]
        release_history_artifact=chain["history"],  # type: ignore[arg-type]
        verifier_material=chain["material"],  # type: ignore[arg-type]
        watermark_store=store,
        expected_release_roots=chain["roots"],  # type: ignore[arg-type]
        now=chain["now"],  # type: ignore[arg-type]
    )
    assert isinstance(result, TraceabilityGateAuthorized)


def test_current_ctv_threshold_recovery_requires_explicit_root_activation(
    tmp_path: Path,
) -> None:
    chain = _current_chain(
        threshold_recovery=True, activate_recovery_roots=False
    )
    release_digest = chain["release_digest"]
    assert isinstance(release_digest, str)
    store = FileTraceabilityReleaseWatermarkStore(tmp_path / "watermark.json")
    assert isinstance(store.provision(1, 1, release_digest), WatermarkAdvanced)
    result = verify_release_gate(
        registry=chain["registry"],  # type: ignore[arg-type]
        bootstrap_artifact=chain["bootstrap"],  # type: ignore[arg-type]
        recovery_artifact=chain["recovery"],  # type: ignore[arg-type]
        recovery_artifacts=chain["recoveries"][1:],  # type: ignore[index,arg-type]
        lifecycle_artifact=chain["lifecycle"],  # type: ignore[arg-type]
        release_artifact=chain["release"],  # type: ignore[arg-type]
        active_pointer_artifact=chain["pointer"],  # type: ignore[arg-type]
        release_history_artifact=chain["history"],  # type: ignore[arg-type]
        verifier_material=chain["material"],  # type: ignore[arg-type]
        watermark_store=store,
        expected_release_roots=chain["roots"],  # type: ignore[arg-type]
        now=chain["now"],  # type: ignore[arg-type]
    )
    assert result == TraceabilityGateRejected(
        reason="recovery_root_not_lifecycle_eligible"
    )


@pytest.mark.parametrize("action", ("revoke", "compromise"))
def test_current_ctv_threshold_recovery_tombstones_terminal_roots(
    tmp_path: Path, action: str
) -> None:
    chain = _current_chain(
        threshold_recovery=True, terminal_recovery_action=action
    )
    release_digest = chain["release_digest"]
    assert isinstance(release_digest, str)
    store = FileTraceabilityReleaseWatermarkStore(tmp_path / "watermark.json")
    assert isinstance(store.provision(1, 1, release_digest), WatermarkAdvanced)
    result = verify_release_gate(
        registry=chain["registry"],  # type: ignore[arg-type]
        bootstrap_artifact=chain["bootstrap"],  # type: ignore[arg-type]
        recovery_artifact=chain["recovery"],  # type: ignore[arg-type]
        recovery_artifacts=chain["recoveries"][1:],  # type: ignore[index,arg-type]
        lifecycle_artifact=chain["lifecycle"],  # type: ignore[arg-type]
        release_artifact=chain["release"],  # type: ignore[arg-type]
        active_pointer_artifact=chain["pointer"],  # type: ignore[arg-type]
        release_history_artifact=chain["history"],  # type: ignore[arg-type]
        verifier_material=chain["material"],  # type: ignore[arg-type]
        watermark_store=store,
        expected_release_roots=chain["roots"],  # type: ignore[arg-type]
        now=chain["now"],  # type: ignore[arg-type]
    )
    assert result == TraceabilityGateRejected(
        reason="recovery_root_not_lifecycle_eligible"
    )


@pytest.mark.parametrize(
    ("mutation", "expected"),
    (
        ("skipped", "prior_lifecycle_root_sequence_invalid"),
        ("cyclic", "lifecycle_root_successor_reference_unverified"),
    ),
)
def test_current_ctv_prior_chain_requires_complete_signed_successors(
    tmp_path: Path, mutation: str, expected: str
) -> None:
    chain = _current_chain(threshold_recovery=True)
    material = chain["material"]
    assert isinstance(material, VerifierHeldTrustMaterial)
    priors = material.prior_verified_lifecycle_root_bytes
    assert len(priors) == 4
    if mutation == "skipped":
        replacement_priors = (priors[0], *priors[2:])
    else:
        cyclic_body = _load(priors[1], "lifecycle")
        cyclic_digest = cyclic_body["lifecycle_root_digest"]
        coordinates = cyclic_body["signer_coordinates"]
        assert isinstance(cyclic_digest, str)
        assert isinstance(coordinates, list) and isinstance(coordinates[0], dict)
        coordinates[0]["trust_lifecycle_root_digest"] = cyclic_digest
        replacement_priors = (
            priors[0],
            serialize_artifact(cyclic_body, _binding("lifecycle")),
            *priors[2:],
        )
    replacement_material = VerifierHeldTrustMaterial(
        material.bootstrap_anchor_bytes,
        material.recovery_root_bytes,
        material.verify_signature,
        material.recovery_policy_bytes,
        material.provisioned_successor_root_bytes,
        replacement_priors,
    )
    release_digest = chain["release_digest"]
    assert isinstance(release_digest, str)
    path = tmp_path / "watermark.json"
    store = FileTraceabilityReleaseWatermarkStore(path)
    assert isinstance(store.provision(1, 1, release_digest), WatermarkAdvanced)
    record_before = path.read_bytes()
    seal = path.with_name(f"{path.name}.bootstrap-seal")
    seal_before = seal.read_bytes()
    result = verify_release_gate(
        registry=chain["registry"],  # type: ignore[arg-type]
        bootstrap_artifact=chain["bootstrap"],  # type: ignore[arg-type]
        recovery_artifact=chain["recovery"],  # type: ignore[arg-type]
        recovery_artifacts=chain["recoveries"][1:],  # type: ignore[index,arg-type]
        lifecycle_artifact=chain["lifecycle"],  # type: ignore[arg-type]
        release_artifact=chain["release"],  # type: ignore[arg-type]
        active_pointer_artifact=chain["pointer"],  # type: ignore[arg-type]
        release_history_artifact=chain["history"],  # type: ignore[arg-type]
        verifier_material=replacement_material,
        watermark_store=store,
        expected_release_roots=chain["roots"],  # type: ignore[arg-type]
        now=chain["now"],  # type: ignore[arg-type]
    )
    assert result == TraceabilityGateRejected(reason=expected)
    assert path.read_bytes() == record_before
    assert seal.read_bytes() == seal_before


def test_current_chain_rejects_post_activation_bootstrap_genesis_downgrade_before_watermark(
    tmp_path: Path,
) -> None:
    chain = _current_chain()
    material = chain["material"]
    assert isinstance(material, VerifierHeldTrustMaterial)
    successor = _load(material.provisioned_successor_root_bytes[0], "bootstrap")
    successor.update(
        {
            "rotation_sequence": 1,
            "predecessor_anchor_id": None,
            "predecessor_anchor_digest": None,
            "provenance": {
                "source_kind": "independently_provisioned_genesis",
                "authority_id": AUTHORITY,
                "provisioned_channel_id": successor["provisioned_channel_id"],
                "provisioned_authorization_artifact_digest": "f" * 64,
                "provisioned_signature_purpose": successor["issuance_purpose"],
                "provisioned_signature_profile_id": successor["signature_profile_id"],
                "provisioned_key_or_certificate_digest": successor["public_key_or_root_certificate_digest"],
                "eligible_not_before": "2026-01-01T00:00:02Z",
                "eligible_not_after": None,
            },
        }
    )
    downgraded = serialize_artifact(successor, _binding("bootstrap"))
    replacement = VerifierHeldTrustMaterial(
        material.bootstrap_anchor_bytes, material.recovery_root_bytes, material.verify_signature,
        material.recovery_policy_bytes, (downgraded,), material.prior_verified_lifecycle_root_bytes,
    )
    store = FileTraceabilityReleaseWatermarkStore(tmp_path / "watermark.json")
    assert isinstance(store.provision(1, 1, "0" * 64), WatermarkAdvanced)
    before = (tmp_path / "watermark.json").read_bytes()
    registry = chain["registry"]
    bootstrap = chain["bootstrap"]
    recovery = chain["recovery"]
    lifecycle = chain["lifecycle"]
    release = chain["release"]
    pointer = chain["pointer"]
    history = chain["history"]
    roots = chain["roots"]
    now = chain["now"]
    assert isinstance(registry, TraceabilityRegistry)
    assert isinstance(bootstrap, bytes) and isinstance(recovery, bytes) and isinstance(lifecycle, bytes)
    assert isinstance(release, bytes) and isinstance(pointer, bytes) and isinstance(history, bytes)
    assert isinstance(roots, dict) and isinstance(now, datetime)
    result = verify_release_gate(
        registry=registry,
        bootstrap_artifact=bootstrap, recovery_artifact=recovery,
        lifecycle_artifact=lifecycle, release_artifact=release,
        active_pointer_artifact=pointer, release_history_artifact=history,
        verifier_material=replacement, watermark_store=store,
        expected_release_roots=roots, now=now,
    )
    assert result == TraceabilityGateRejected("lifecycle_post_activation_genesis_downgrade")
    assert (tmp_path / "watermark.json").read_bytes() == before


@pytest.mark.parametrize("held_kind", ["prior_lifecycle", "successor_root"])
def test_public_gate_rejects_raw_verifier_held_current_state_without_mutation(
    tmp_path: Path, held_kind: str
) -> None:
    chain = _current_chain()
    material = chain["material"]
    assert isinstance(material, VerifierHeldTrustMaterial)
    prior = material.prior_verified_lifecycle_root_bytes
    successors = material.provisioned_successor_root_bytes
    if held_kind == "prior_lifecycle":
        prior = (canonical_document({"legacy": "prior-lifecycle"}),)
    else:
        successors = (
            canonical_document(_load(successors[0], "provisioned_successor_root")),
        )
    replacement = replace(
        material,
        provisioned_successor_root_bytes=successors,
        prior_verified_lifecycle_root_bytes=prior,
    )
    path = tmp_path / "watermark.json"
    store = FileTraceabilityReleaseWatermarkStore(path)
    assert isinstance(store.provision(1, 1, "0" * 64), WatermarkAdvanced)
    seal = path.with_name(f"{path.name}.bootstrap-seal")
    before = (path.read_bytes(), seal.read_bytes())
    registry = chain["registry"]
    roots = chain["roots"]
    now = chain["now"]
    assert isinstance(registry, TraceabilityRegistry)
    assert isinstance(roots, dict) and isinstance(now, datetime)
    result = verify_release_gate(
        registry=registry,
        bootstrap_artifact=chain["bootstrap"],  # type: ignore[arg-type]
        recovery_artifact=chain["recovery"],  # type: ignore[arg-type]
        lifecycle_artifact=chain["lifecycle"],  # type: ignore[arg-type]
        release_artifact=chain["release"],  # type: ignore[arg-type]
        active_pointer_artifact=chain["pointer"],  # type: ignore[arg-type]
        release_history_artifact=chain["history"],  # type: ignore[arg-type]
        verifier_material=replacement,
        watermark_store=store,
        expected_release_roots=roots,
        now=now,
    )
    assert result == TraceabilityGateRejected("legacy_incomplete_provenance")
    assert (path.read_bytes(), seal.read_bytes()) == before


def test_public_release_gate_rejects_legacy_bytes_before_watermark() -> None:
    class Watermark:
        calls = 0

        def compare_and_advance(self, epoch: int, sequence: int, digest: str) -> object:
            self.calls += 1
            raise AssertionError("legacy bytes must not reach watermark")

    watermark = Watermark()
    result = verify_release_gate(
        registry=object(),  # type: ignore[arg-type]
        bootstrap_artifact=canonical_document({"legacy": "bootstrap"}),
        recovery_artifact=canonical_document({"legacy": "recovery"}),
        lifecycle_artifact=canonical_document({"legacy": "lifecycle"}),
        release_artifact=canonical_document({"legacy": "release"}),
        active_pointer_artifact=canonical_document({"legacy": "pointer"}),
        release_history_artifact=canonical_document({"legacy": "history"}),
        verifier_material=VerifierHeldTrustMaterial(
            b"legacy-policy", (), lambda _profile, _key, _payload, _signature: False, b"legacy-policy"
        ),
        watermark_store=watermark,  # type: ignore[arg-type]
    )
    assert result == TraceabilityGateRejected(reason="legacy_incomplete_provenance")
    assert watermark.calls == 0


def test_public_gate_rejects_legacy_shaped_ctv_before_watermark() -> None:
    """A CTV envelope cannot make the retired flat release schema current."""
    from datetime import UTC, datetime, timedelta
    from hashlib import sha256

    from memorii.tools.semantic_ingestion_traceability_registry import load_registry

    def signature(profile: str, key: str, payload: bytes) -> bytes:
        return sha256(profile.encode() + b"\0" + key.encode() + b"\0" + payload).digest()

    def verifier(profile: str, key: str, payload: bytes, value: bytes) -> bool:
        return value == signature(profile, key, payload)

    def legacy_signed(body: dict[str, object], domain: bytes, field: str, key: str = "key-a") -> dict[str, object]:
        digest = sha256(domain + b"\0" + canonical_document(body)).hexdigest()
        profile = "profile-b" if key == "key-b" else "profile-a"
        return {**body, field: digest, "signature": signature(profile, key, digest.encode()).hex()}

    now = datetime(2026, 1, 2, tzinfo=UTC)
    bootstrap = _bootstrap()
    bootstrap.update(
        {
            "target_purpose": "semantic_ingestion_traceability_release",
            "authorized_signature_purposes": ["semantic_ingestion_traceability_release"],
            "canonical_profile_binding": _binding("bootstrap").as_value(),
            "effective_at": "2026-01-01T00:00:00Z",
            "recorded_at": "2026-01-01T00:00:00Z",
            "expires_at": None,
        }
    )
    recovery = {
        "recovery_root_id": "recovery-a", "recovery_root_digest": "d" * 64,
        "issuance_purpose": "semantic_ingestion_traceability_recovery_root", "target_authority_id": AUTHORITY,
        "authorized_signature_purposes": ["semantic_ingestion_traceability_recovery_policy"],
        "canonical_profile_binding": _binding("recovery").as_value(), "signature_profile_id": "profile-r",
        "public_key_or_root_certificate_digest": "key-r", "provisioned_channel_id": "channel-r",
        "rotation_sequence": 1, "predecessor_recovery_root_id": None, "predecessor_recovery_root_digest": None,
        "effective_at": "2026-01-01T00:00:00Z", "recorded_at": "2026-01-01T00:00:00Z", "expires_at": None,
        "provenance": {
            "source_kind": "independently_provisioned_genesis", "authority_id": AUTHORITY,
            "provisioned_channel_id": "channel-r", "provisioned_authorization_artifact_digest": "e" * 64,
            "provisioned_signature_purpose": "semantic_ingestion_traceability_recovery_root",
            "provisioned_signature_profile_id": "profile-r", "provisioned_key_or_certificate_digest": "key-r",
            "eligible_not_before": "2026-01-01T00:00:00Z", "eligible_not_after": None,
        },
    }
    record_body = {
        "issuance_purpose": "semantic_ingestion_traceability_trust_lifecycle", "sequence": 1,
        "predecessor_record_digest": None, "effective_at": "2026-01-01T00:00:00Z", "recorded_at": "2026-01-01T00:00:01Z",
        "action": "activate", "target_id": "bootstrap-a", "target_digest": ROOT_DIGEST,
        "replacement_target_id": None, "replacement_target_digest": None,
        "signer_bindings": [{"signer_id": "bootstrap-a", "signature_profile_id": "profile-a", "key_digest": "key-a"}],
    }
    record_digest = sha256(b"memorii:sia-traceability-lifecycle-record:v1\0" + canonical_document(record_body)).hexdigest()
    lifecycle_body = {"authority_id": AUTHORITY, "records": [{**record_body, "record_digest": record_digest, "signatures": [signature("profile-a", "key-a", record_digest.encode()).hex()]}]}
    lifecycle_digest = sha256(b"memorii:sia-traceability-trust-lifecycle-root:v1\0" + canonical_document(lifecycle_body)).hexdigest()
    lifecycle = {**lifecycle_body, "lifecycle_root_digest": lifecycle_digest, "signature": signature("profile-a", "key-a", lifecycle_digest.encode()).hex()}
    provenance = _policy()["signer_provenance"]
    policy_body = {
        "policy_id": "policy-a", "issuance_purpose": "semantic_ingestion_traceability_recovery_policy", "target_authority_id": AUTHORITY,
        "bootstrap_anchor_id": "bootstrap-a", "bootstrap_anchor_digest": ROOT_DIGEST, "eligible_recovery_root_digests": ["d" * 64],
        "minimum_distinct_signatures": 1, "signer_separation_rule_digest": "f" * 64,
        "canonical_profile_binding": _binding("recovery_policy").as_value(), "effective_at": "2026-01-01T00:00:00Z",
        "recorded_at": "2026-01-01T00:00:01Z", "sequence": 1, "predecessor_policy_digest": None, "expires_at": None,
        "signer_provenance": provenance,
    }
    policy_digest = _typed_digest(b"memorii:sia-traceability-recovery-policy:v1", policy_body)
    policy_preimage = encode_typed_value({"issuance_purpose": policy_body["issuance_purpose"], "body_binding": policy_body["canonical_profile_binding"], "recovery_policy_digest": policy_digest, "signer_provenance": provenance})
    policy = {**policy_body, "recovery_policy_digest": policy_digest, "signature": signature("profile-a", "key-a", policy_preimage).hex()}
    registry = load_registry(Path(__file__).parents[4] / "docs/design/semantic_ingestion/traceability_registry/registry-v1.json")
    roots = {"registry_source_identity": registry.source_identity, **{f"{name}_digest": digest for name, digest in registry.root_digests.items()}, "design_document_digest": "1" * 64, "structural_manifest_digest": "2" * 64, "coverage_root_digest": "3" * 64, "execution_root_digest": "4" * 64, "report_schema_registry_digest": "5" * 64, "runner_environment_profile_registry_digest": "6" * 64, "trust_snapshot_digest": "7" * 64}
    release = legacy_signed({"release_id": "release-a", "issuance_purpose": "semantic_ingestion_traceability_release", "canonical_profile_id": "memorii-sia-canonical-json-v1", "signature_profile_id": "profile-a", "issuer_key_or_certificate_digest": "key-a", "grammar_revision": registry.source["grammar_revision"], "issued_state": "active", "predecessor_release_id": None, "supersedes_release_id": None, "bootstrap_anchor_digest": ROOT_DIGEST, "recovery_root_digest": "d" * 64, "issued_at": "2026-01-01T00:00:02Z", "expires_at": (now + timedelta(days=1)).isoformat(), "epoch": 1, "sequence": 1, **roots}, b"memorii:sia-traceability-release:v1", "release_digest")
    entry_body = {"entry_id": "entry-a", "sequence": 1, "predecessor_entry_digest": None, "release_id": "release-a", "release_digest": release["release_digest"], "release_epoch": 1, "release_sequence": 1, "prior_active_release_digest": None, "prior_release_terminal_state": None, "effective_at": "2026-01-01T00:00:02Z"}
    entry = {**entry_body, "entry_digest": sha256(b"memorii:sia-traceability-release-history-entry:v1\0" + canonical_document(entry_body)).hexdigest()}
    history = legacy_signed({"history_id": "history-a", "issuance_purpose": "semantic_ingestion_traceability_release_history", "canonical_profile_id": "memorii-sia-canonical-json-v1", "signature_profile_id": "profile-a", "issuer_key_or_certificate_digest": "key-a", "entries": [entry]}, b"memorii:sia-traceability-release-history:v1", "release_history_digest")
    pointer = legacy_signed({"issuance_purpose": "semantic_ingestion_traceability_active_release_pointer", "release_id": "release-a", "release_digest": release["release_digest"], "epoch": 1, "sequence": 1, "signature_profile_id": "profile-a", "issuer_key_or_certificate_digest": "key-a"}, b"memorii:sia-traceability-active-release-pointer:v1", "active_pointer_digest")
    class Watermark:
        calls = 0
        advances = 0
        committed: tuple[int, int, str] | None = None

        def provision(self, epoch: int, sequence: int, release_digest: str) -> WatermarkAdvanceResult:
            return self.compare_and_advance(epoch, sequence, release_digest)

        def compare_and_advance(
            self, epoch: int, sequence: int, release_digest: str
        ) -> WatermarkAdvanceResult:
            self.calls += 1
            candidate = (epoch, sequence, release_digest)
            if candidate != self.committed:
                self.advances += 1
                self.committed = candidate
            return WatermarkAdvanced()
    watermark = Watermark()
    result = verify_release_gate(registry=registry, bootstrap_artifact=_artifact("bootstrap", bootstrap), recovery_artifact=_artifact("recovery", recovery), lifecycle_artifact=_artifact("lifecycle", lifecycle), release_artifact=_artifact("release", release), active_pointer_artifact=_artifact("active_pointer", pointer), release_history_artifact=_artifact("release_history", history), verifier_material=VerifierHeldTrustMaterial(_artifact("bootstrap", bootstrap), (_artifact("recovery", recovery),), verifier, _artifact("recovery_policy", policy)), watermark_store=watermark, expected_release_roots={name: roots[name] for name in ("design_document_digest", "structural_manifest_digest", "coverage_root_digest", "execution_root_digest", "report_schema_registry_digest", "runner_environment_profile_registry_digest", "trust_snapshot_digest")}, now=now)
    assert result == TraceabilityGateRejected(reason="legacy_incomplete_provenance")
    assert watermark.calls == 0
