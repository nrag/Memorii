"""Offline PEM Ed25519 signing for already-authorized traceability preimages.

This module signs or verifies caller-provided bytes.  It does not create keys,
issue trust bindings, choose profiles, or assemble release artifacts.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Protocol

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from memorii.tools.semantic_ingestion_signature_verifier import Ed25519SignatureVerifier, Ed25519VerificationKeyBinding


class DetachedPreimageSigner(Protocol):
    """External or local signer of exact detached-signature preimage bytes."""

    def sign_preimage(self, preimage: bytes) -> bytes: ...


def load_pem_ed25519_public_key_binding(
    pem: bytes,
    *,
    profile_id: str,
    digest_domain: bytes,
    public_key_digest: str,
) -> Ed25519VerificationKeyBinding:
    """Load an explicitly authorized PEM public key into an existing binding type."""
    if not isinstance(pem, bytes):
        raise ValueError("ed25519_public_key_pem_invalid")
    try:
        public_key = serialization.load_pem_public_key(pem)
    except (TypeError, ValueError) as exc:
        raise ValueError("ed25519_public_key_pem_invalid") from exc
    if not isinstance(public_key, Ed25519PublicKey):
        raise ValueError("ed25519_public_key_pem_invalid")
    raw_public_key = public_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return Ed25519VerificationKeyBinding(profile_id, raw_public_key, public_key_digest, digest_domain)


class PemEd25519PrivateKeySigner:
    """Locally held PEM Ed25519 key constrained to a supplied public binding."""

    def __init__(self, private_key: Ed25519PrivateKey, binding: Ed25519VerificationKeyBinding) -> None:
        derived_public_key = private_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        if derived_public_key != binding.public_key:
            raise ValueError("ed25519_private_key_binding_mismatch")
        self._private_key = private_key

    @classmethod
    def from_pem(
        cls,
        pem: bytes,
        *,
        binding: Ed25519VerificationKeyBinding,
        password: bytes | None = None,
    ) -> PemEd25519PrivateKeySigner:
        """Load encrypted or unencrypted PEM key material without creating authority."""
        if not isinstance(pem, bytes) or (password is not None and not isinstance(password, bytes)):
            raise ValueError("ed25519_private_key_pem_invalid")
        try:
            private_key = serialization.load_pem_private_key(pem, password=password)
        except (TypeError, ValueError) as exc:
            raise ValueError("ed25519_private_key_pem_invalid") from exc
        if not isinstance(private_key, Ed25519PrivateKey):
            raise ValueError("ed25519_private_key_pem_invalid")
        return cls(private_key, binding)

    def sign_preimage(self, preimage: bytes) -> bytes:
        """Sign exact supplied bytes; hashing and artifact construction are callers' work."""
        if not isinstance(preimage, bytes):
            raise ValueError("signature_preimage_invalid")
        return self._private_key.sign(preimage)


def verify_preimage(
    *,
    binding: Ed25519VerificationKeyBinding,
    preimage: bytes,
    signature: bytes,
) -> bool:
    """Verify an exact detached signature with an already-verified binding."""
    return Ed25519SignatureVerifier((binding,)).verify(
        binding.profile_id, binding.public_key_digest, preimage, signature
    )


def _read_password(args: argparse.Namespace) -> bytes | None:
    password_file = args.password_file
    if password_file is not None:
        return Path(password_file).read_bytes()
    if args.password_stdin:
        return sys.stdin.buffer.read()
    return None


def _binding_from_args(args: argparse.Namespace) -> Ed25519VerificationKeyBinding:
    return load_pem_ed25519_public_key_binding(
        Path(args.public_key).read_bytes(),
        profile_id=args.profile_id,
        digest_domain=Path(args.digest_domain_file).read_bytes(),
        public_key_digest=args.public_key_digest,
    )


def _write_new(path: Path, value: bytes) -> None:
    try:
        with path.open("xb") as output:
            output.write(value)
    except FileExistsError as exc:
        raise ValueError(f"refusing_to_overwrite_existing_output:{path}") from exc


def _sign(args: argparse.Namespace) -> int:
    output = Path(args.output)
    if output.exists():
        raise ValueError(f"refusing_to_overwrite_existing_output:{output}")
    binding = _binding_from_args(args)
    signer = PemEd25519PrivateKeySigner.from_pem(
        Path(args.private_key).read_bytes(), binding=binding, password=_read_password(args)
    )
    _write_new(output, signer.sign_preimage(Path(args.preimage).read_bytes()))
    return 0


def _verify(args: argparse.Namespace) -> int:
    binding = _binding_from_args(args)
    return 0 if verify_preimage(
        binding=binding, preimage=Path(args.preimage).read_bytes(), signature=Path(args.signature).read_bytes()
    ) else 1


def _binding_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--public-key", required=True, help="PEM Ed25519 public-key file")
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--public-key-digest", required=True)
    parser.add_argument("--digest-domain-file", required=True, help="Exact digest-domain bytes file")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    sign = commands.add_parser("sign-preimage", help="write a raw detached signature without overwriting output")
    sign.add_argument("--private-key", required=True, help="PEM Ed25519 private-key file")
    sign.add_argument("--preimage", required=True, help="exact input bytes file")
    sign.add_argument("--output", required=True, help="new raw detached-signature output file")
    password = sign.add_mutually_exclusive_group()
    password.add_argument("--password-file", help="password bytes file for encrypted PEM")
    password.add_argument("--password-stdin", action="store_true", help="read password bytes from standard input")
    _binding_arguments(sign)
    verify = commands.add_parser("verify-preimage", help="verify a raw detached signature")
    verify.add_argument("--preimage", required=True, help="exact input bytes file")
    verify.add_argument("--signature", required=True, help="raw detached-signature file")
    _binding_arguments(verify)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "sign-preimage":
            return _sign(args)
        return _verify(args)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
