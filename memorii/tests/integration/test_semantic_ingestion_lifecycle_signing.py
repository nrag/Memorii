"""Detached signing of current lifecycle record and root CTV stages."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import replace
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Literal

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from memorii.core.memory_evolution.ingestion_contracts import (
    decode_artifact,
    decode_typed_value,
    serialize_artifact,
)
from memorii.tools.semantic_ingestion_lifecycle_signing import (
    DetachedLifecycleSignature,
    PreparedLifecycleSignatures,
    assemble_lifecycle_signatures,
    prepare_lifecycle_signatures,
)
from memorii.tools.semantic_ingestion_lifecycle_signing import (
    main as lifecycle_signing_main,
)
from memorii.tools.semantic_ingestion_signature_verifier import Ed25519VerificationKeyBinding
from memorii.tools.semantic_ingestion_traceability_registry import TraceabilityRegistry
from memorii.tools.semantic_ingestion_traceability_release import (
    VerifiedReleaseCandidate,
    VerifierHeldTrustMaterial,
    validate_release_candidate,
)
from tests.fixtures.semantic_ingestion.current_release_chain import _current_chain

_DOMAIN = b"memorii:lifecycle-signing-test-key:v1\0"
_PROFILES = ("profile-a", "profile-b", "profile-r", "profile-c", "profile-r2")


def _bytes(value: object) -> bytes:
    assert isinstance(value, bytes)
    return value


def _chain(*, threshold_recovery: bool = True) -> tuple[
    dict[str, object], tuple[Ed25519VerificationKeyBinding, ...], dict[tuple[str, str], Ed25519PrivateKey],
]:
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
        threshold_recovery=threshold_recovery,
        signature_signer=lambda profile, digest, payload: private[(profile, digest)].sign(payload),
        key_digests=(
            bindings[0].public_key_digest, bindings[1].public_key_digest,
            bindings[2].public_key_digest, bindings[3].public_key_digest,
            bindings[4].public_key_digest,
        ),
    )
    return chain, bindings, private


def _sign(
    prepared: PreparedLifecycleSignatures, private: dict[tuple[str, str], Ed25519PrivateKey],
) -> tuple[DetachedLifecycleSignature, ...]:
    requests = prepared.requests
    kind = prepared.lifecycle_kind
    return tuple(
        DetachedLifecycleSignature(
            kind, request.record_index, request.signature_index, request.profile_id,
            request.public_key_digest, request.purpose,
            private[(request.profile_id, request.public_key_digest)].sign(request.preimage),
        )
        for request in requests
    )


def _assemble_lifecycle(
    raw: bytes, bindings: tuple[Ed25519VerificationKeyBinding, ...], private: dict[tuple[str, str], Ed25519PrivateKey],
) -> bytes:
    records = prepare_lifecycle_signatures("lifecycle_record", raw)
    after_records = assemble_lifecycle_signatures(records, _sign(records, private), bindings)
    root = prepare_lifecycle_signatures("lifecycle_root", after_records)
    return assemble_lifecycle_signatures(root, _sign(root, private), bindings)


@pytest.mark.parametrize("threshold_recovery", (False, True))
def test_split_record_then_root_assembly_reaches_existing_release_validator(
    threshold_recovery: bool,
) -> None:
    chain, bindings, private = _chain(threshold_recovery=threshold_recovery)
    lifecycle = _assemble_lifecycle(_bytes(chain["lifecycle"]), bindings, private)
    assert lifecycle == _bytes(chain["lifecycle"])
    material, registry, now = chain["material"], chain["registry"], chain["now"]
    assert isinstance(material, VerifierHeldTrustMaterial)
    assert isinstance(registry, TraceabilityRegistry)
    assert isinstance(now, datetime)
    recoveries, raw_roots = chain["recoveries"], chain["roots"]
    assert isinstance(recoveries, (tuple, list))
    assert isinstance(raw_roots, dict)
    roots: dict[str, str] = {}
    for name, value in raw_roots.items():
        assert isinstance(name, str) and isinstance(value, str)
        roots[name] = value
    result = validate_release_candidate(
        registry=registry, bootstrap_artifact=_bytes(chain["bootstrap"]),
        recovery_artifact=_bytes(chain["recovery"]), lifecycle_artifact=lifecycle,
        release_artifact=_bytes(chain["release"]), active_pointer_artifact=_bytes(chain["pointer"]),
        release_history_artifact=_bytes(chain["history"]), verifier_material=material,
        recovery_artifacts=tuple(_bytes(item) for item in recoveries if item != chain["recovery"]),
        expected_release_roots=roots, now=now,
    )
    assert isinstance(result, VerifiedReleaseCandidate)


def test_assembly_reprepares_and_rejects_cached_body_forgery() -> None:
    chain, bindings, private = _chain()
    prepared = prepare_lifecycle_signatures("lifecycle_record", _bytes(chain["lifecycle"]))
    forged = replace(prepared, template_bytes=prepared.template_bytes + b"\n")
    with pytest.raises(ValueError):
        assemble_lifecycle_signatures(forged, _sign(prepared, private), bindings)


@pytest.mark.parametrize("kind", ("lifecycle_record", "lifecycle_root"))
def test_assembly_rejects_wrong_key_and_tampered_signature(
    kind: Literal["lifecycle_record", "lifecycle_root"],
) -> None:
    chain, bindings, private = _chain()
    record_prepared = prepare_lifecycle_signatures("lifecycle_record", _bytes(chain["lifecycle"]))
    template = (
        _bytes(chain["lifecycle"])
        if kind == "lifecycle_record"
        else assemble_lifecycle_signatures(record_prepared, _sign(record_prepared, private), bindings)
    )
    prepared = prepare_lifecycle_signatures(kind, template)
    supplied = _sign(prepared, private)
    signature = supplied[0].signature
    tampered = signature[:-1] + bytes((signature[-1] ^ 1,))
    with pytest.raises(ValueError, match="signature_invalid"):
        assemble_lifecycle_signatures(prepared, (replace(supplied[0], signature=tampered), *supplied[1:]), bindings)
    wrong_public = Ed25519PrivateKey.generate().public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    wrong = Ed25519VerificationKeyBinding(
        supplied[0].profile_id, wrong_public, sha256(_DOMAIN + wrong_public).hexdigest(), _DOMAIN
    )
    wrong_bindings = tuple(
        wrong if binding.profile_id == supplied[0].profile_id else binding for binding in bindings
    )
    with pytest.raises(ValueError, match="signature_invalid"):
        assemble_lifecycle_signatures(prepared, supplied, wrong_bindings)


@pytest.mark.parametrize("field", ("profile_id", "public_key_digest", "purpose", "record_index", "signature_index"))
def test_assembly_rejects_coordinate_substitution(field: str) -> None:
    chain, bindings, private = _chain()
    prepared = prepare_lifecycle_signatures("lifecycle_record", _bytes(chain["lifecycle"]))
    supplied = _sign(prepared, private)
    changes: dict[str, object] = {
        "profile_id": "other", "public_key_digest": "0" * 64, "purpose": "other",
        "record_index": None, "signature_index": 9,
    }
    with pytest.raises(ValueError, match="coordinate_invalid"):
        assemble_lifecycle_signatures(prepared, (replace(supplied[0], **{field: changes[field]}), *supplied[1:]), bindings)


@pytest.mark.parametrize("mutation", ("extra", "purpose", "duplicate_binding"))
def test_prepare_rejects_noncanonical_or_duplicate_lifecycle_fields(mutation: str) -> None:
    chain, _, _ = _chain()
    artifact = decode_artifact(_bytes(chain["lifecycle"]))
    body = decode_typed_value(artifact.canonical_value_bytes)
    assert isinstance(body, dict)
    if mutation == "extra":
        body["unexpected"] = True
    elif mutation == "purpose":
        body["issuance_purpose"] = "other"
    else:
        records = body["records"]
        assert isinstance(records, list) and isinstance(records[0], dict)
        signer_bindings = records[0]["signer_bindings"]
        signatures = records[0]["signatures"]
        assert isinstance(signer_bindings, list) and isinstance(signatures, list)
        signer_bindings.append(dict(signer_bindings[0]))
        signatures.append(signatures[0])
    raw = serialize_artifact(body, artifact.binding)
    with pytest.raises(ValueError):
        prepare_lifecycle_signatures("lifecycle_record", raw)


def test_cli_explicit_signature_indices_and_exclusive_output(tmp_path: Path) -> None:
    chain, bindings, private = _chain()
    lifecycle = tmp_path / "lifecycle.ctv"
    lifecycle.write_bytes(_bytes(chain["lifecycle"]))
    domain = tmp_path / "domain.bin"
    domain.write_bytes(_DOMAIN)
    rows: list[dict[str, str]] = []
    for index, binding in enumerate(bindings):
        key = private[(binding.profile_id, binding.public_key_digest)]
        public = tmp_path / f"public-{index}.pem"
        public.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        rows.append({"profile_id": binding.profile_id, "expected_digest": binding.public_key_digest,
                     "digest_domain_file": str(domain), "public_key_file": str(public)})
    config = tmp_path / "bindings.json"
    config.write_text(json.dumps({"bindings": rows}))

    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, "-m", "memorii.tools.semantic_ingestion_lifecycle_signing", *args], capture_output=True, text=True, check=False)

    def stage(kind: str, template: Path, output: Path) -> None:
        requests = tmp_path / f"{kind}.json"
        prepared = run("--prepare", "--kind", kind, "--template", str(template), "--output", str(requests))
        assert prepared.returncode == 0, prepared.stderr
        values = json.loads(requests.read_text())["requests"]
        signature_args: list[str] = []
        for index, request in enumerate(values):
            preimage, signature = tmp_path / f"{kind}-{index}.bin", tmp_path / f"{kind}-{index}.sig"
            preimage.write_bytes(bytes.fromhex(request["preimage_hex"]))
            signature.write_bytes(private[(request["profile_id"], request["public_key_digest"])].sign(preimage.read_bytes()))
            signature_args.extend(("--signature", f"{index}={signature}"))
        if kind == "lifecycle_record":
            base = ("--assemble", "--kind", kind, "--template", str(template), "--bindings", str(config))
            rejected_output = tmp_path / "rejected.ctv"
            rejected_output.write_bytes(b"sentinel")
            with pytest.raises(SystemExit):
                lifecycle_signing_main([*base, *signature_args[:-2], "--output", str(rejected_output)])
            assert rejected_output.read_bytes() == b"sentinel"
            with pytest.raises(SystemExit):
                lifecycle_signing_main([*base, *signature_args, "--signature", signature_args[1], "--output", str(rejected_output)])
            assert rejected_output.read_bytes() == b"sentinel"
            out_of_range = tmp_path / "out-of-range.ctv"
            with pytest.raises(SystemExit):
                lifecycle_signing_main([
                    *base, *signature_args, "--signature", f"{len(values)}={tmp_path / 'out-of-range.sig'}",
                    "--output", str(out_of_range),
                ])
            assert not out_of_range.exists()
        assembled = run("--assemble", "--kind", kind, "--template", str(template), "--bindings", str(config), *signature_args, "--output", str(output))
        assert assembled.returncode == 0, assembled.stderr

    after_records = tmp_path / "records.ctv"
    stage("lifecycle_record", lifecycle, after_records)
    assembled = tmp_path / "root.ctv"
    stage("lifecycle_root", after_records, assembled)
    assert assembled.read_bytes() == lifecycle.read_bytes()
    assert run("--prepare", "--kind", "lifecycle_record", "--template", str(lifecycle), "--output", str(assembled)).returncode != 0
