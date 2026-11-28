"""Encrypted participant streaming must preserve existing backup bytes."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from memorii.core.storage_administration.backup_cipher import (
    decrypt_backup_participant,
    encrypt_backup_participant,
)

_KEY = bytes(range(32))
_NONCE = bytes(range(12))


@pytest.mark.parametrize("size", (0, 31, 2 * 1024 * 1024 + 19))
def test_streaming_is_byte_compatible_with_existing_backup_archives(tmp_path: Path, size: int) -> None:
    source, encrypted, restored = (tmp_path / name for name in ("source", "encrypted", "restored"))
    body = (bytes(range(256)) * (size // 256 + 1))[:size]
    source.write_bytes(body)
    expected = AESGCM(_KEY).encrypt(_NONCE, body, None)

    digest, encoded_size = encrypt_backup_participant(source, encrypted, key=_KEY, nonce=_NONCE)

    assert encrypted.read_bytes() == expected
    assert (digest, encoded_size) == (sha256(expected).hexdigest(), len(expected))
    assert encrypted.stat().st_mode & 0o777 == 0o600
    decrypt_backup_participant(
        encrypted, restored, key=_KEY, nonce=_NONCE, expected_digest=digest, expected_size=encoded_size,
    )
    assert restored.read_bytes() == body
    assert restored.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("mutation", ("append", "truncate", "digest", "ciphertext", "tag", "nonce"))
def test_unverified_participant_leaves_existing_destination_intact(tmp_path: Path, mutation: str) -> None:
    source = tmp_path / "encrypted"
    destination = tmp_path / "restored"
    body = AESGCM(_KEY).encrypt(_NONCE, b"backup contents", None)
    nonce, size = _NONCE, len(body)
    if mutation == "append":
        body += b"\0"
    elif mutation == "truncate":
        body = body[:-1]
    elif mutation == "ciphertext":
        body = bytes([body[0] ^ 1]) + body[1:]
    elif mutation == "tag":
        body = body[:-1] + bytes([body[-1] ^ 1])
    elif mutation == "nonce":
        nonce = bytes(reversed(_NONCE))
    digest = "0" * 64 if mutation == "digest" else sha256(body).hexdigest()
    source.write_bytes(body)
    destination.write_bytes(b"previous destination")

    with pytest.raises(InvalidTag):
        decrypt_backup_participant(
            source, destination, key=_KEY, nonce=nonce, expected_digest=digest, expected_size=size,
        )

    assert destination.read_bytes() == b"previous destination"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["encrypted", "restored"]
