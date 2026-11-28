"""Stream backup participants using the existing AES-GCM wire format."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

_CHUNK_SIZE = 1024 * 1024
_TAG_SIZE = 16


def encrypt_backup_participant(
    source: Path, destination: Path, *, key: bytes, nonce: bytes,
) -> tuple[str, int]:
    """Publish ciphertext followed by the 16-byte tag and return its digest and length."""
    encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
    digest = hashlib.sha256()
    size = 0
    with tempfile.TemporaryDirectory(prefix=".participant-", dir=destination.parent) as scratch:
        pending = Path(scratch) / "ciphertext"
        with source.open("rb") as original, pending.open("xb") as output:
            os.fchmod(output.fileno(), 0o600)
            while plaintext := original.read(_CHUNK_SIZE):
                ciphertext = encryptor.update(plaintext)
                output.write(ciphertext)
                digest.update(ciphertext)
                size += len(ciphertext)
            tail = encryptor.finalize() + encryptor.tag
            output.write(tail)
            digest.update(tail)
            size += len(tail)
            output.flush()
            os.fsync(output.fileno())
        os.replace(pending, destination)
    return digest.hexdigest(), size


def decrypt_backup_participant(
    source: Path, destination: Path, *, key: bytes, nonce: bytes, expected_digest: str, expected_size: int,
) -> None:
    """Publish plaintext only when the archive digest and GCM tag both verify."""
    if expected_size < _TAG_SIZE:
        raise InvalidTag("backup participant is shorter than its authentication tag")
    decryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).decryptor()
    digest = hashlib.sha256()
    with tempfile.TemporaryDirectory(prefix=".participant-", dir=destination.parent) as scratch:
        pending = Path(scratch) / "plaintext"
        with source.open("rb") as original, pending.open("xb") as output:
            os.fchmod(output.fileno(), 0o600)
            remaining = expected_size - _TAG_SIZE
            while remaining:
                ciphertext = original.read(min(remaining, _CHUNK_SIZE))
                if not ciphertext:
                    raise InvalidTag("backup participant is truncated")
                digest.update(ciphertext)
                output.write(decryptor.update(ciphertext))
                remaining -= len(ciphertext)
            tag = original.read(_TAG_SIZE)
            digest.update(tag)
            if len(tag) != _TAG_SIZE or original.read(1) or digest.hexdigest() != expected_digest:
                raise InvalidTag("backup participant does not match its manifest")
            output.write(decryptor.finalize_with_tag(tag))
            output.flush()
            os.fsync(output.fileno())
        os.replace(pending, destination)
