"""Focused current-CTV detached release signing preparation proof."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import replace
from datetime import datetime
from hashlib import sha256
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from memorii.core.memory_evolution.ingestion_contracts import decode_artifact, decode_typed_value, serialize_artifact
from memorii.tools.semantic_ingestion_release_signing import (
    DetachedSignature,
    assemble_release_signatures,
    prepare_release_signatures,
)
from memorii.tools.semantic_ingestion_signature_verifier import Ed25519VerificationKeyBinding
from memorii.tools.semantic_ingestion_traceability_registry import TraceabilityRegistry
from memorii.tools.semantic_ingestion_traceability_release import (
    VerifiedReleaseCandidate,
    VerifierHeldTrustMaterial,
    validate_release_candidate,
)
from tests.fixtures.semantic_ingestion.current_release_chain import _current_chain

_DOMAIN = b"memorii:release-signing-test-key:v1\0"
_PROFILES = ("profile-a", "profile-b", "profile-r", "profile-c", "profile-r2")


def _bytes(value: object) -> bytes:
    assert isinstance(value, bytes)
    return value


def _templates(chain: dict[str, object]) -> dict[str, bytes]:
    return {kind: _bytes(chain[source]) for kind, source in (
        ("recovery_policy", "policy"), ("release", "release"),
        ("release_history", "history"), ("active_pointer", "pointer"),
    )}


def _chain():
    keys = tuple(Ed25519PrivateKey.from_private_bytes(sha256(profile.encode()).digest()) for profile in _PROFILES)
    bindings = tuple(
        Ed25519VerificationKeyBinding(
            profile,
            key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw),
            sha256(_DOMAIN + key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).hexdigest(),
            _DOMAIN,
        )
        for profile, key in zip(_PROFILES, keys, strict=True)
    )
    private = {(binding.profile_id, binding.public_key_digest): key for binding, key in zip(bindings, keys, strict=True)}
    chain = _current_chain(
        signature_signer=lambda profile, digest, payload: private[(profile, digest)].sign(payload),
        key_digests=(bindings[0].public_key_digest, bindings[1].public_key_digest, bindings[2].public_key_digest, bindings[3].public_key_digest, bindings[4].public_key_digest),
    )
    return chain, bindings, private


def test_prepare_assemble_roundtrip_is_accepted_by_existing_release_validator() -> None:
    chain, bindings, private = _chain()
    templates = _templates(chain) | {"lifecycle": _bytes(chain["lifecycle"])}
    with pytest.raises(ValueError, match="template_kinds"):
        prepare_release_signatures(templates)
    prepared = prepare_release_signatures({key: value for key, value in templates.items() if key != "lifecycle"})
    supplied = tuple(
        DetachedSignature(request.artifact_kind, request.profile_id, request.public_key_digest, request.purpose, private[(request.profile_id, request.public_key_digest)].sign(request.preimage))
        for request in prepared.requests
    )
    assembled = assemble_release_signatures(prepared, supplied, bindings)
    original_material, registry, now = chain["material"], chain["registry"], chain["now"]
    assert isinstance(original_material, VerifierHeldTrustMaterial)
    assert isinstance(registry, TraceabilityRegistry) and isinstance(now, datetime)
    material = replace(original_material, recovery_policy_bytes=assembled["recovery_policy"])
    recoveries, raw_roots = chain["recoveries"], chain["roots"]
    assert isinstance(recoveries, (tuple, list)) and isinstance(raw_roots, dict)
    roots: dict[str, str] = {}
    for name, value in raw_roots.items():
        assert isinstance(name, str) and isinstance(value, str)
        roots[name] = value
    result = validate_release_candidate(
        registry=registry, bootstrap_artifact=_bytes(chain["bootstrap"]), recovery_artifact=_bytes(chain["recovery"]),
        lifecycle_artifact=_bytes(chain["lifecycle"]), release_artifact=assembled["release"], active_pointer_artifact=assembled["active_pointer"],
        release_history_artifact=assembled["release_history"], verifier_material=material,
        recovery_artifacts=tuple(_bytes(item) for item in recoveries if item != chain["recovery"]),
        expected_release_roots=roots, now=now,
    )
    assert isinstance(result, VerifiedReleaseCandidate)


@pytest.mark.parametrize("field", ("profile_id", "public_key_digest", "purpose"))
def test_assemble_rejects_swapped_signature_coordinate(field: str) -> None:
    chain, bindings, private = _chain()
    prepared = prepare_release_signatures(_templates(chain))
    supplied = tuple(
        DetachedSignature(request.artifact_kind, request.profile_id, request.public_key_digest, request.purpose, private[(request.profile_id, request.public_key_digest)].sign(request.preimage))
        for request in prepared.requests
    )
    values = {"profile_id": "other", "public_key_digest": "0" * 64, "purpose": "other"}
    with pytest.raises(ValueError, match="coordinate_invalid"):
        assemble_release_signatures(prepared, (replace(supplied[0], **{field: values[field]}), *supplied[1:]), bindings)


def test_assemble_rejects_substituted_cached_request() -> None:
    chain, bindings, private = _chain()
    prepared = prepare_release_signatures(_templates(chain))
    supplied = tuple(DetachedSignature(r.artifact_kind, r.profile_id, r.public_key_digest, r.purpose, private[(r.profile_id, r.public_key_digest)].sign(r.preimage)) for r in prepared.requests)
    substituted = replace(prepared, requests=(replace(prepared.requests[0], preimage=b"substituted"), *prepared.requests[1:]))
    with pytest.raises(ValueError, match="preparation_substituted"):
        assemble_release_signatures(substituted, supplied, bindings)


@pytest.mark.parametrize("kind", ("recovery_policy", "release", "release_history", "active_pointer"))
@pytest.mark.parametrize("mutation", ("extra_field", "wrong_purpose"))
def test_prepare_rejects_noncanonical_shape_or_purpose(kind: str, mutation: str) -> None:
    chain, _, _ = _chain()
    templates = _templates(chain)
    artifact = decode_artifact(templates[kind])
    body = decode_typed_value(artifact.canonical_value_bytes)
    assert isinstance(body, dict)
    body["unexpected" if mutation == "extra_field" else "issuance_purpose"] = "other"
    templates[kind] = serialize_artifact(body, artifact.binding)
    with pytest.raises(ValueError, match="shape_invalid"):
        prepare_release_signatures(templates)


def test_cli_prepares_signs_and_assembles_without_overwriting(tmp_path: Path) -> None:
    chain, bindings, private = _chain()
    names = {"recovery_policy": "policy", "release": "release", "release_history": "history", "active_pointer": "pointer"}
    arguments: list[str] = []
    for kind, source in names.items():
        raw = chain[source]
        assert isinstance(raw, bytes)
        path = tmp_path / f"{kind}.ctv"
        path.write_bytes(raw)
        arguments.extend(("--" + kind.replace("_", "-"), str(path)))

    def run(module: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, "-m", module, *args], capture_output=True, text=True, check=False)

    module = "memorii.tools.semantic_ingestion_release_signing"
    requests = tmp_path / "requests.json"
    prepared = run(module, "--prepare", *arguments, "--output", str(requests))
    assert prepared.returncode == 0, prepared.stderr
    original_requests = requests.read_bytes()
    assert run(module, "--prepare", *arguments, "--output", str(requests)).returncode != 0
    assert requests.read_bytes() == original_requests
    domain = tmp_path / "domain.bin"
    domain.write_bytes(_DOMAIN)
    config_rows: list[dict[str, str]] = []
    key_paths: dict[tuple[str, str], tuple[Path, Path]] = {}
    for index, binding in enumerate(bindings):
        key = private[(binding.profile_id, binding.public_key_digest)]
        public_path, private_path = tmp_path / f"public-{index}.pem", tmp_path / f"private-{index}.pem"
        public_path.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        private_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        key_paths[(binding.profile_id, binding.public_key_digest)] = (public_path, private_path)
        config_rows.append({"profile_id": binding.profile_id, "expected_digest": binding.public_key_digest, "digest_domain_file": str(domain), "public_key_file": str(public_path)})
    config = tmp_path / "trusted-bindings.json"
    config.write_text(json.dumps({"bindings": config_rows}))
    signature_args: list[str] = []
    for request in json.loads(original_requests)["requests"]:
        kind = request["artifact_kind"]
        preimage, signature = tmp_path / f"{kind}.preimage", tmp_path / f"{kind}.sig"
        preimage.write_bytes(bytes.fromhex(request["preimage_hex"]))
        public_path, private_path = key_paths[(request["profile_id"], request["public_key_digest"])]
        signed = run("memorii.tools.semantic_ingestion_offline_signing", "sign-preimage", "--preimage", str(preimage), "--output", str(signature), "--public-key", str(public_path), "--private-key", str(private_path), "--profile-id", request["profile_id"], "--public-key-digest", request["public_key_digest"], "--digest-domain-file", str(domain))
        assert signed.returncode == 0, signed.stderr
        signature_args.extend(("--" + kind.replace("_", "-") + "-signature", str(signature)))
    output = tmp_path / "assembled"
    assemble_args = ("--assemble", *arguments, *signature_args, "--bindings", str(config), "--output", str(output))
    assembled = run(module, *assemble_args)
    assert assembled.returncode == 0, assembled.stderr
    assert {p.name: p.read_bytes() for p in output.iterdir()} == {f"{kind}.ctv": chain[source] for kind, source in names.items()}
    assert run(module, *assemble_args).returncode != 0
    duplicate_config = '{"bindings":[],"bindings":' + json.dumps(config_rows) + '}'
    config.write_text(duplicate_config)
    duplicate_output = tmp_path / "duplicate-config"
    assert run(module, "--assemble", *arguments, *signature_args, "--bindings", str(config), "--output", str(duplicate_output)).returncode != 0
    assert not duplicate_output.exists()
    config.write_text(json.dumps({"bindings": config_rows}))
    signature = tmp_path / "release.sig"
    signature.write_bytes(b"\0" * 64)
    rejected_output = tmp_path / "rejected"
    rejected = run(module, "--assemble", *arguments, *signature_args, "--bindings", str(config), "--output", str(rejected_output))
    assert rejected.returncode != 0
    assert not rejected_output.exists()
