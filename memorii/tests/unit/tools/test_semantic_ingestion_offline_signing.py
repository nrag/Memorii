"""Focused proof for offline PEM Ed25519 detached preimage signing."""

from __future__ import annotations

import os
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from memorii.tools.semantic_ingestion_offline_signing import (
    PemEd25519PrivateKeySigner,
    load_pem_ed25519_public_key_binding,
    verify_preimage,
)

_PROFILE = "offline-test-profile"
_DOMAIN = b"memorii:offline-signing-test-public-key:v1\0"
_MODULE = "memorii.tools.semantic_ingestion_offline_signing"


def _key_material(password: bytes | None = None) -> tuple[bytes, bytes, bytes, str]:
    private_key = Ed25519PrivateKey.generate()
    encryption = serialization.NoEncryption() if password is None else serialization.BestAvailableEncryption(password)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, encryption
    )
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    public_key = private_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return private_pem, public_pem, public_key, sha256(_DOMAIN + public_key).hexdigest()


def _binding(public_pem: bytes, digest: str):
    return load_pem_ed25519_public_key_binding(
        public_pem, profile_id=_PROFILE, digest_domain=_DOMAIN, public_key_digest=digest
    )


@pytest.mark.parametrize("password", (None, b"encrypted PEM password\x00bytes"))
def test_pem_signer_handles_unencrypted_and_encrypted_private_keys(password: bytes | None) -> None:
    private_pem, public_pem, _, digest = _key_material(password)
    binding = _binding(public_pem, digest)
    signature = PemEd25519PrivateKeySigner.from_pem(private_pem, binding=binding, password=password).sign_preimage(b"exact\x00payload")
    assert verify_preimage(binding=binding, preimage=b"exact\x00payload", signature=signature)


def test_signer_uses_exact_preimage_without_rehashing() -> None:
    private_pem, public_pem, _, digest = _key_material()
    binding = _binding(public_pem, digest)
    signer = PemEd25519PrivateKeySigner.from_pem(private_pem, binding=binding)
    payload = b"exact preimage"
    signature = signer.sign_preimage(payload)
    assert verify_preimage(binding=binding, preimage=payload, signature=signature)
    assert not verify_preimage(binding=binding, preimage=sha256(payload).digest(), signature=signature)


def test_loaders_reject_wrong_key_kind_malformed_pem_wrong_password_and_binding_mismatch() -> None:
    private_pem, public_pem, _, digest = _key_material(b"secret")
    binding = _binding(public_pem, digest)
    rsa_private_pem = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    ec_public_pem = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    with pytest.raises(ValueError, match="ed25519_private_key_pem_invalid"):
        PemEd25519PrivateKeySigner.from_pem(private_pem, binding=binding, password=b"wrong")
    with pytest.raises(ValueError, match="ed25519_private_key_pem_invalid"):
        PemEd25519PrivateKeySigner.from_pem(rsa_private_pem, binding=binding)
    with pytest.raises(ValueError, match="ed25519_public_key_pem_invalid"):
        load_pem_ed25519_public_key_binding(
            ec_public_pem, profile_id=_PROFILE, digest_domain=_DOMAIN, public_key_digest=digest
        )
    with pytest.raises(ValueError, match="ed25519_public_key_pem_invalid"):
        load_pem_ed25519_public_key_binding(b"not a pem", profile_id=_PROFILE, digest_domain=_DOMAIN, public_key_digest=digest)
    other_private, other_public, _, other_digest = _key_material()
    assert other_private
    with pytest.raises(ValueError, match="ed25519_private_key_binding_mismatch"):
        PemEd25519PrivateKeySigner.from_pem(other_private, binding=_binding(public_pem, digest))
    with pytest.raises(ValueError, match="public_key_digest_mismatch"):
        _binding(other_public, digest)
    assert _binding(other_public, other_digest).profile_id == _PROFILE


def test_verification_rejects_altered_payload_key_profile_digest_and_signature() -> None:
    private_pem, public_pem, _, digest = _key_material()
    binding = _binding(public_pem, digest)
    signature = PemEd25519PrivateKeySigner.from_pem(private_pem, binding=binding).sign_preimage(b"payload")
    _, other_public, _, other_digest = _key_material()
    assert not verify_preimage(binding=binding, preimage=b"payload!", signature=signature)
    assert not verify_preimage(binding=_binding(other_public, other_digest), preimage=b"payload", signature=signature)
    assert not verify_preimage(binding=binding, preimage=b"payload", signature=signature[:-1])
    assert binding.profile_id == _PROFILE and binding.public_key_digest == digest


def _cli_environment() -> dict[str, str]:
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


def _command(command: str, paths: dict[str, Path], digest: str) -> list[str]:
    return [
        sys.executable, "-m", _MODULE, command,
        "--public-key", str(paths["public"]), "--profile-id", _PROFILE,
        "--public-key-digest", digest, "--digest-domain-file", str(paths["domain"]),
    ]


def test_cli_signs_verifies_and_preserves_existing_output(tmp_path: Path) -> None:
    private_pem, public_pem, _, digest = _key_material(b"password")
    paths = {
        "private": tmp_path / "private.pem", "public": tmp_path / "public.pem", "domain": tmp_path / "domain",
        "password": tmp_path / "password", "preimage": tmp_path / "preimage", "signature": tmp_path / "signature",
    }
    paths["private"].write_bytes(private_pem)
    paths["public"].write_bytes(public_pem)
    paths["domain"].write_bytes(_DOMAIN)
    paths["password"].write_bytes(b"password")
    paths["preimage"].write_bytes(b"cli exact preimage\x00")
    sign = [
        *_command("sign-preimage", paths, digest), "--private-key", str(paths["private"]), "--preimage", str(paths["preimage"]),
        "--output", str(paths["signature"]), "--password-file", str(paths["password"]),
    ]
    completed = subprocess.run(sign, env=_cli_environment(), capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    verify = subprocess.run(
        [*_command("verify-preimage", paths, digest), "--preimage", str(paths["preimage"]), "--signature", str(paths["signature"])],
        env=_cli_environment(), capture_output=True, text=True,
    )
    assert verify.returncode == 0, verify.stderr
    original = paths["signature"].read_bytes()
    repeated = subprocess.run(sign, env=_cli_environment(), capture_output=True, text=True)
    assert repeated.returncode != 0
    assert paths["signature"].read_bytes() == original


def test_cli_verify_fails_for_altered_payload_and_wrong_profile(tmp_path: Path) -> None:
    private_pem, public_pem, _, digest = _key_material()
    paths = {
        "private": tmp_path / "private.pem", "public": tmp_path / "public.pem", "domain": tmp_path / "domain",
        "preimage": tmp_path / "preimage", "signature": tmp_path / "signature",
    }
    paths["private"].write_bytes(private_pem)
    paths["public"].write_bytes(public_pem)
    paths["domain"].write_bytes(_DOMAIN)
    paths["preimage"].write_bytes(b"original")
    sign = [
        *_command("sign-preimage", paths, digest), "--private-key", str(paths["private"]), "--preimage", str(paths["preimage"]),
        "--output", str(paths["signature"]),
    ]
    assert subprocess.run(sign, env=_cli_environment(), capture_output=True, text=True).returncode == 0
    paths["preimage"].write_bytes(b"altered")
    altered = subprocess.run(
        [*_command("verify-preimage", paths, digest), "--preimage", str(paths["preimage"]), "--signature", str(paths["signature"])],
        env=_cli_environment(), capture_output=True, text=True,
    )
    assert altered.returncode == 1
    wrong_profile = [*_command("verify-preimage", paths, digest), "--preimage", str(paths["preimage"]), "--signature", str(paths["signature"])]
    wrong_profile[wrong_profile.index(_PROFILE)] = "another-profile"
    assert subprocess.run(wrong_profile, env=_cli_environment(), capture_output=True, text=True).returncode == 1
