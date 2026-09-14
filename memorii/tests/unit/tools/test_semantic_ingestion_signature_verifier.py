"""Focused proof for configured Ed25519 traceability verification."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from memorii.core.memory_evolution.ingestion_contracts import decode_artifact, decode_typed_value, serialize_artifact
from memorii.tools.semantic_ingestion_acceptance_watermark_store import WatermarkAdvanced, WatermarkAdvanceResult
from memorii.tools.semantic_ingestion_execution_evidence import ExecutionEvidenceError, RegisteredApprovalExecutor
from memorii.tools.semantic_ingestion_release_persistence import (
    FileMonotonicFenceStore,
    FileTraceabilityReleasePublicationStore,
)
from memorii.tools.semantic_ingestion_signature_verifier import Ed25519SignatureVerifier, Ed25519VerificationKeyBinding
from memorii.tools.semantic_ingestion_traceability_release import (
    AcceptanceTrustStore,
    TraceabilityGateAuthorized,
    TraceabilityGateRejected,
    VerifierHeldTrustMaterial,
    verify_release_gate,
)
from memorii.tools.semantic_ingestion_trust_resolver import ConfiguredAcceptanceTrustResolver
from tests.fixtures.semantic_ingestion.current_release_chain import _binding as _chain_binding
from tests.fixtures.semantic_ingestion.current_release_chain import _current_chain

_PROFILE = "memorii.test.ed25519.rfc8032.v1"
_DOMAIN = b"memorii:sia-test-ed25519-public-key:v1\0"
_PUBLIC_KEY = bytes.fromhex("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")
_OTHER_PUBLIC_KEY = bytes.fromhex("3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c")
_SIGNATURE = bytes.fromhex(
    "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
    "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"
)
_CHAIN_SEEDS = (
    "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
    "c0e0bcc3a021871dc779b17af8fc864f8a745573b140725f9652caa0d5ab9388",
    "4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
    "c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7",
    sha256(b"memorii:sia-test-ed25519-seed:fixture-current-chain-5:v1").hexdigest(),
)
_CHAIN_PROFILES = ("profile-a", "profile-b", "profile-r", "profile-c", "profile-r2")


def _binding(*, profile: str = _PROFILE, key: bytes = _PUBLIC_KEY) -> Ed25519VerificationKeyBinding:
    return Ed25519VerificationKeyBinding(profile, key, sha256(_DOMAIN + key).hexdigest(), _DOMAIN)


def test_rfc8032_known_answer_verifies_exact_empty_message() -> None:
    assert Ed25519SignatureVerifier((_binding(),)).verify(_PROFILE, _binding().public_key_digest, b"", _SIGNATURE)


@pytest.mark.parametrize(
    ("profile", "key_digest", "payload", "signature"),
    [
        ("other-profile", _binding().public_key_digest, b"", _SIGNATURE),
        (_PROFILE, "0" * 64, b"", _SIGNATURE),
        (_PROFILE, _binding().public_key_digest, b"changed", _SIGNATURE),
        (_PROFILE, _binding().public_key_digest, sha256(b"").digest(), _SIGNATURE),
        (_PROFILE, _binding().public_key_digest, b"", _SIGNATURE[:-1]),
        (_PROFILE, _binding().public_key_digest, b"", _SIGNATURE + b"x"),
        (_PROFILE, _binding().public_key_digest, b"", bytes([_SIGNATURE[0] ^ 1]) + _SIGNATURE[1:]),
        (_PROFILE, _binding().public_key_digest, b"", sha256(b"wrong digest").digest() + _SIGNATURE[32:]),
        (_PROFILE, _binding().public_key_digest, "not-bytes", _SIGNATURE),
        (_PROFILE, _binding().public_key_digest, b"", "not-bytes"),
    ],
)
def test_verifier_rejects_wrong_binding_payload_or_signature_length(
    profile: str, key_digest: str, payload: object, signature: object
) -> None:
    assert not Ed25519SignatureVerifier((_binding(),)).verify(profile, key_digest, payload, signature)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "make_binding",
    [
        lambda: Ed25519VerificationKeyBinding(_PROFILE, b"short", "0" * 64, _DOMAIN),
        lambda: Ed25519VerificationKeyBinding(_PROFILE, _PUBLIC_KEY, "A" * 64, _DOMAIN),
        lambda: Ed25519VerificationKeyBinding(_PROFILE, _PUBLIC_KEY, "0" * 64, b""),
        lambda: Ed25519VerificationKeyBinding(_PROFILE, _PUBLIC_KEY, "0" * 63, _DOMAIN),
    ],
)
def test_binding_rejects_malformed_configuration(make_binding: Callable[[], Ed25519VerificationKeyBinding]) -> None:
    with pytest.raises(ValueError):
        make_binding()


def test_verifier_rejects_duplicate_or_empty_bindings() -> None:
    with pytest.raises(ValueError, match="signature_binding_duplicate"):
        Ed25519SignatureVerifier((_binding(), _binding()))
    with pytest.raises(ValueError, match="signature_bindings_empty"):
        Ed25519SignatureVerifier(())


def test_verifier_rejects_signature_from_another_configured_key() -> None:
    other = _binding(key=_OTHER_PUBLIC_KEY)
    assert not Ed25519SignatureVerifier((_binding(), other)).verify(_PROFILE, other.public_key_digest, b"", _SIGNATURE)


@dataclass
class _InMemoryWatermarkStore:
    committed: tuple[int, int, str] | None = None
    calls: int = 0

    def provision(self, epoch: int, sequence: int, release_digest: str) -> WatermarkAdvanceResult:
        return self.compare_and_advance(epoch, sequence, release_digest)

    def compare_and_advance(self, epoch: int, sequence: int, release_digest: str) -> WatermarkAdvanceResult:
        self.calls += 1
        self.committed = (epoch, sequence, release_digest)
        return WatermarkAdvanced()


def _ed25519_current_chain() -> tuple[dict[str, object], _InMemoryWatermarkStore, AcceptanceTrustStore]:
    private_keys = tuple(Ed25519PrivateKey.from_private_bytes(bytes.fromhex(seed)) for seed in _CHAIN_SEEDS)
    public_keys = tuple(
        private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        for private in private_keys
    )
    bindings = tuple(
        Ed25519VerificationKeyBinding(profile, public_key, sha256(_DOMAIN + public_key).hexdigest(), _DOMAIN)
        for profile, public_key in zip(_CHAIN_PROFILES, public_keys, strict=True)
    )
    signers = {(binding.profile_id, binding.public_key_digest): private for binding, private in zip(bindings, private_keys, strict=True)}

    def sign(profile: str, key_digest: str, payload: bytes) -> bytes:
        return signers[(profile, key_digest)].sign(payload)

    chain_key_digests = (
        bindings[0].public_key_digest,
        bindings[1].public_key_digest,
        bindings[2].public_key_digest,
        bindings[3].public_key_digest,
        bindings[4].public_key_digest,
    )
    chain = _current_chain(signature_signer=sign, key_digests=chain_key_digests)
    material, roots = chain["material"], chain["roots"]
    assert isinstance(material, VerifierHeldTrustMaterial) and isinstance(roots, dict)
    watermark = _InMemoryWatermarkStore()
    authority = AcceptanceTrustStore(material=material, watermark_store=watermark, expected_release_roots=roots)  # type: ignore[arg-type]
    configured = ConfiguredAcceptanceTrustResolver(authority=authority, signature_bindings=bindings).resolve_registered_execution()
    assert configured is not None
    return chain, watermark, configured


def _verify_current_chain(chain: dict[str, object], authority: AcceptanceTrustStore) -> object:
    return verify_release_gate(
        registry=chain["registry"],  # type: ignore[arg-type]
        bootstrap_artifact=chain["bootstrap"],  # type: ignore[arg-type]
        recovery_artifact=chain["recovery"],  # type: ignore[arg-type]
        lifecycle_artifact=chain["lifecycle"],  # type: ignore[arg-type]
        release_artifact=chain["release"],  # type: ignore[arg-type]
        active_pointer_artifact=chain["pointer"],  # type: ignore[arg-type]
        release_history_artifact=chain["history"],  # type: ignore[arg-type]
        verifier_material=authority.material,
        watermark_store=authority.watermark_store,
        expected_release_roots=authority.expected_release_roots,
        now=chain["now"],  # type: ignore[arg-type]
    )


def test_configured_resolver_authorizes_current_release_with_ed25519() -> None:
    chain, watermark, authority = _ed25519_current_chain()
    assert isinstance(_verify_current_chain(chain, authority), TraceabilityGateAuthorized)
    assert watermark.calls == 1


@pytest.mark.parametrize("artifact_name", ("release", "lifecycle"))
def test_configured_resolver_rejects_tampered_current_release_before_watermark(artifact_name: str) -> None:
    chain, watermark, authority = _ed25519_current_chain()
    artifact = chain[artifact_name]
    assert isinstance(artifact, bytes)
    value = decode_typed_value(decode_artifact(artifact).canonical_value_bytes)
    assert isinstance(value, dict)
    if artifact_name == "release":
        assert isinstance(value["signature"], str)
        value["signature"] = ("0" if value["signature"][0] != "0" else "1") + value["signature"][1:]
    else:
        assert isinstance(value["signatures"], list) and isinstance(value["signatures"][0], bytes)
        value["signatures"][0] = bytes([value["signatures"][0][0] ^ 1]) + value["signatures"][0][1:]
    chain[artifact_name] = serialize_artifact(value, _chain_binding(artifact_name))
    assert isinstance(_verify_current_chain(chain, authority), TraceabilityGateRejected)
    assert watermark.calls == 0


def test_configured_resolver_rejects_wrong_release_purpose_before_watermark() -> None:
    chain, watermark, authority = _ed25519_current_chain()
    release = chain["release"]
    assert isinstance(release, bytes)
    value = decode_typed_value(decode_artifact(release).canonical_value_bytes)
    assert isinstance(value, dict)
    value["issuance_purpose"] = "semantic_ingestion_traceability_coverage"
    chain["release"] = serialize_artifact(value, _chain_binding("release"))
    assert isinstance(_verify_current_chain(chain, authority), TraceabilityGateRejected)
    assert watermark.calls == 0


def test_configured_resolver_executes_signed_current_release(tmp_path: Path) -> None:
    from tests.acceptance.semantic_ingestion import test_sia_requirements as acceptance

    private_keys = tuple(Ed25519PrivateKey.from_private_bytes(bytes.fromhex(seed)) for seed in _CHAIN_SEEDS)
    bindings = tuple(
        Ed25519VerificationKeyBinding(
            profile,
            private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw),
            sha256(_DOMAIN + private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).hexdigest(),
            _DOMAIN,
        )
        for profile, private in zip(_CHAIN_PROFILES, private_keys, strict=True)
    )
    signers = {(binding.profile_id, binding.public_key_digest): private for binding, private in zip(bindings, private_keys, strict=True)}

    def sign(profile: str, key_digest: str, payload: bytes) -> bytes:
        return signers[(profile, key_digest)].sign(payload)

    key_digests = (bindings[0].public_key_digest, bindings[1].public_key_digest, bindings[2].public_key_digest, bindings[3].public_key_digest, bindings[4].public_key_digest)
    baseline = acceptance._approval_inputs(
        "semantic-ingestion-normative-traceability-approval", signature_signer=sign, key_digests=key_digests
    )
    inputs = acceptance._successor_inputs(
        "semantic-ingestion-normative-traceability-approval",
        signature_signer=sign,
        key_digests=key_digests,
    )
    material, roots = inputs["verifier_material"], inputs["expected_release_roots"]
    assert isinstance(material, VerifierHeldTrustMaterial) and isinstance(roots, dict)
    publication_path = tmp_path / "publication.json"
    publication = FileTraceabilityReleasePublicationStore(
        publication_path, FileMonotonicFenceStore(tmp_path / "fence.json")
    )
    release_value = decode_typed_value(decode_artifact(inputs["release_artifact"]).canonical_value_bytes)  # type: ignore[arg-type]
    assert isinstance(release_value, dict)
    historical = inputs["historical_release_artifacts"]
    release_history = baseline["release_history_artifact"]
    active_pointer = baseline["active_pointer_artifact"]
    pointer_history = baseline["pointer_history_artifact"]
    baseline_release = baseline["release_artifact"]
    assert isinstance(historical, tuple) and len(historical) == 1 and isinstance(historical[0], bytes)
    assert isinstance(baseline_release, bytes) and baseline_release == historical[0]
    assert isinstance(release_history, bytes) and isinstance(active_pointer, bytes) and isinstance(pointer_history, bytes)
    prior_value = decode_typed_value(decode_artifact(baseline_release).canonical_value_bytes)
    assert isinstance(prior_value, dict)
    assert isinstance(publication.provision(prior_value["epoch"], prior_value["sequence"], prior_value["release_digest"]), WatermarkAdvanced)
    assert isinstance(publication.compare_fence_and_publish(
        watermark_store=publication, epoch=prior_value["epoch"], sequence=prior_value["sequence"], release_digest=prior_value["release_digest"],
        release_artifact=baseline_release, release_history_artifact=release_history,
        active_pointer_artifact=active_pointer, pointer_history_artifact=pointer_history,
    ), TraceabilityGateAuthorized)
    authority = AcceptanceTrustStore(material, publication, roots, publication_store=publication, independent_generation_verifier=inputs["independent_generation_verifier"], allow_test_file_fence=True)  # type: ignore[arg-type]
    executor = RegisteredApprovalExecutor.from_resolver(ConfiguredAcceptanceTrustResolver(authority=authority, signature_bindings=bindings))
    tampered = dict(inputs)
    tampered_release = decode_typed_value(decode_artifact(inputs["release_artifact"]).canonical_value_bytes)  # type: ignore[arg-type]
    assert isinstance(tampered_release, dict) and isinstance(tampered_release["signature"], str)
    tampered_release["signature"] = ("0" if tampered_release["signature"][0] != "0" else "1") + tampered_release["signature"][1:]
    tampered["release_artifact"] = serialize_artifact(tampered_release, _chain_binding("release"))
    inventory_before = publication.version_inventory()
    with pytest.raises(ExecutionEvidenceError, match="release gate did not authorize"):
        acceptance._registered_call(tampered, authority, executor=executor)
    assert publication.version_inventory() == inventory_before
    result = acceptance._registered_call(inputs, authority, executor=executor)
    assert result["command_id"] == "pytest-normative-traceability-approval-v1"
    published = publication.version_inventory().current
    assert published is not None
    assert (published.epoch, published.sequence, published.release_digest) == (
        release_value["epoch"],
        release_value["sequence"],
        release_value["release_digest"],
    )
