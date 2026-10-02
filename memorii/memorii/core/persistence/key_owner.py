"""Opaque local signing-key owner for installation control authority.

Keys live in an owner-only directory outside replaceable application-data
generations, are never persisted inside the data or control databases, and
every signature is domain-separated by purpose so a signature over one
surface cannot be replayed onto another.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
    load_pem_private_key,
)

from memorii.core.persistence.contracts import (
    RUNTIME_CONTROL_JOURNAL_SIGNATURE_PURPOSE,
    RUNTIME_PUBLICATION_SIGNATURE_PURPOSE,
)

INSTALLATION_BACKUP_MANIFEST_SIGNATURE_PURPOSE = (
    "memorii.installation-backup-manifest.v1"
)

RUNTIME_CHECKPOINT_SIGNATURE_PURPOSE = "memorii.runtime-checkpoint.v1"

_SUPPORTED_PURPOSES = (
    RUNTIME_PUBLICATION_SIGNATURE_PURPOSE,
    RUNTIME_CONTROL_JOURNAL_SIGNATURE_PURPOSE,
    INSTALLATION_BACKUP_MANIFEST_SIGNATURE_PURPOSE,
    RUNTIME_CHECKPOINT_SIGNATURE_PURPOSE,
)
_KEY_FILE_MODE = 0o600


def _domain_separator(purpose: str) -> bytes:
    return purpose.encode("ascii") + b"\x00"


class LocalSigningKeyOwner:
    """File-backed Ed25519 signer/verifier for one installation owner."""

    def __init__(self, keys_directory: str | Path) -> None:
        self._keys_directory = Path(keys_directory)
        self._keys_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self._keys_directory, 0o700)
        self._private_keys: dict[str, Ed25519PrivateKey] = {}

    def create_key(self, key_id: str) -> str:
        """Provision a new signing key and return its public fingerprint."""
        if not key_id or "/" in key_id or key_id.startswith("."):
            raise ValueError("signing key id must be a plain nonempty label")
        key_path = self._private_key_path(key_id)
        if key_path.exists():
            raise FileExistsError(f"signing key already exists: {key_id}")
        private_key = Ed25519PrivateKey.generate()
        descriptor = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, _KEY_FILE_MODE)
        try:
            pem = private_key.private_bytes(
                Encoding.PEM,
                PrivateFormat.PKCS8,
                NoEncryption(),
            )
            os.write(descriptor, pem)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        self._private_keys[key_id] = private_key
        return self.public_key_fingerprint(key_id)

    def has_key(self, key_id: str) -> bool:
        return self._private_key_path(key_id).exists()

    def public_key_fingerprint(self, key_id: str) -> str:
        public_bytes = self._public_bytes(self._load_private_key(key_id))
        return hashlib.sha256(public_bytes).hexdigest()

    def sign(self, key_id: str, purpose: str, message: str) -> str:
        self._validate_purpose(purpose)
        private_key = self._load_private_key(key_id)
        signature = private_key.sign(_domain_separator(purpose) + message.encode("utf-8"))
        return signature.hex()

    def verify(self, key_id: str, purpose: str, message: str, signature: str) -> bool:
        self._validate_purpose(purpose)
        try:
            public_key = self._load_public_key(key_id)
            public_key.verify(
                bytes.fromhex(signature),
                _domain_separator(purpose) + message.encode("utf-8"),
            )
        except (InvalidSignature, ValueError, TypeError):
            return False
        return True

    def _load_private_key(self, key_id: str) -> Ed25519PrivateKey:
        cached = self._private_keys.get(key_id)
        if cached is not None:
            return cached
        key_path = self._private_key_path(key_id)
        try:
            mode = key_path.stat().st_mode & 0o777
            pem = key_path.read_bytes()
        except OSError as exc:
            raise PermissionError(f"signing key is unavailable: {key_id}") from exc
        if mode & 0o077:
            raise PermissionError(f"signing key permissions are not owner-only: {key_id}")
        try:
            key = load_pem_private_key(pem, password=None)
        except ValueError as exc:
            raise PermissionError(f"signing key is unreadable: {key_id}") from exc
        if not isinstance(key, Ed25519PrivateKey):
            raise PermissionError(f"signing key is not Ed25519: {key_id}")
        self._private_keys[key_id] = key
        return key

    def _load_public_key(self, key_id: str) -> Ed25519PublicKey:
        return self._load_private_key(key_id).public_key()

    def _private_key_path(self, key_id: str) -> Path:
        return self._keys_directory / f"{key_id}.key"

    @staticmethod
    def _public_bytes(private_key: Ed25519PrivateKey) -> bytes:
        return private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)

    @staticmethod
    def _validate_purpose(purpose: str) -> None:
        if purpose not in _SUPPORTED_PURPOSES:
            raise ValueError(f"unsupported signature purpose: {purpose}")


__all__ = ["LocalSigningKeyOwner"]
