"""Independent encrypted custody of verified control snapshot members."""

from __future__ import annotations

import hashlib
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Literal, Self

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_plane.file_lock import locked_file
from memorii.core.storage_administration.backup_cipher import decrypt_backup_participant, encrypt_backup_participant
from memorii.core.storage_administration.recovery_authority import (
    InstallationControlRecoveryBundle,
    InstallationRecoveryAnchor,
    RecoveryAuthorityError,
    decode_recovery_json,
)
from memorii.stores.sqlite.private_storage import (
    ensure_private_directory,
    open_private_file,
    read_private_file,
    require_private_directory,
    require_private_file,
    write_private_file,
)

_HEADER = "recovery-envelope.json"
_MANIFEST = "control-manifest.enc"
_MAX_HEADER_BYTES = 192 * 1024
_MAX_MANIFEST_BYTES = 384 * 1024
_KEY_SIZE = 32
_NONCE_SIZE = 12
_Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
_Nonce = Annotated[str, Field(pattern=r"^[0-9a-f]{24}$")]


class _EncryptedMember(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ciphertext_digest: _Digest
    ciphertext_size: Annotated[int, Field(ge=16, strict=True)]
    nonce: _Nonce


class _RecoveryEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    protocol_version: Literal[1] = 1
    bundle_digest: _Digest
    wrapping_nonce: _Nonce
    wrapped_key: Annotated[str, Field(pattern=r"^[0-9a-f]{96}$")]
    manifest_nonce: _Nonce
    members: tuple[_EncryptedMember, ...] = Field(min_length=5, max_length=256)

    @model_validator(mode="after")
    def unique_member_nonces(self) -> Self:
        nonces = {member.nonce for member in self.members}
        if len(nonces) != len(self.members) or self.manifest_nonce in nonces:
            raise ValueError("recovery bundle encryption nonces must be unique")
        return self


def _member_name(position: int, *, encrypted: bool) -> str:
    extension = "enc" if encrypted else "snapshot"
    return f"member-{position:03d}.{extension}"


def _publish_directory(candidate: Path, destination: Path) -> None:
    with locked_file(destination.parent / ".recovery-publication.lock", exclusive=True, private=True):
        if destination.exists() or destination.is_symlink():
            raise RecoveryAuthorityError("conflict: recovery custody destination already exists")
        for directory in (candidate, destination.parent):
            descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                if directory == destination.parent:
                    os.rename(candidate, destination)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)


def _check_member(path: Path, digest: str, size: int) -> None:
    with open_private_file(path) as member:
        actual = hashlib.sha256()
        while chunk := member.read(1 << 20):
            actual.update(chunk)
        if os.fstat(member.fileno()).st_size != size or actual.hexdigest() != digest:
            raise RecoveryAuthorityError("integrity_error: recovery member differs from its signed inventory")


def seal_recovery_bundle(
    manifest: InstallationControlRecoveryBundle, *, sources: Sequence[Path],
    destination: Path, recovery_key: bytes, public_key: bytes,
) -> InstallationRecoveryAnchor:
    """Seal owner-snapshot bytes separately from application data archives."""
    if len(recovery_key) != _KEY_SIZE or len(sources) != len(manifest.members):
        raise RecoveryAuthorityError("invalid_request: incomplete recovery key or snapshot inventory")
    require_private_directory(destination.parent)
    anchor = manifest.anchor()
    manifest.verify(anchor, public_key)
    binding = bytes.fromhex(anchor.bundle_digest)
    manifest_bytes = manifest.model_dump_json().encode("utf-8")
    if len(manifest_bytes) > _MAX_MANIFEST_BYTES:
        raise RecoveryAuthorityError("resource_exhausted: recovery manifest exceeds limit")
    key = AESGCM.generate_key(bit_length=256)
    wrapping_nonce, manifest_nonce = os.urandom(_NONCE_SIZE), os.urandom(_NONCE_SIZE)
    with tempfile.TemporaryDirectory(prefix=".control-recovery-", dir=destination.parent) as scratch:
        candidate = Path(scratch) / "bundle"
        ensure_private_directory(candidate)
        encrypted: list[_EncryptedMember] = []
        for position, (source, member) in enumerate(zip(sources, manifest.members, strict=True)):
            _check_member(source, member.digest, member.size_bytes)
            nonce = os.urandom(_NONCE_SIZE)
            digest, size = encrypt_backup_participant(
                source, candidate / _member_name(position, encrypted=True), key=key, nonce=nonce,
            )
            encrypted.append(_EncryptedMember(ciphertext_digest=digest, ciphertext_size=size, nonce=nonce.hex()))
        write_private_file(candidate / _MANIFEST, AESGCM(key).encrypt(manifest_nonce, manifest_bytes, binding))
        envelope = _RecoveryEnvelope(
            bundle_digest=anchor.bundle_digest, wrapping_nonce=wrapping_nonce.hex(), manifest_nonce=manifest_nonce.hex(),
            wrapped_key=AESGCM(recovery_key).encrypt(wrapping_nonce, key, binding).hex(), members=tuple(encrypted),
        )
        write_private_file(candidate / _HEADER, envelope.model_dump_json().encode("utf-8"))
        _publish_directory(candidate, destination)
    return anchor


def open_recovery_bundle(
    source: Path, *, anchor: InstallationRecoveryAnchor, public_key: bytes, recovery_key: bytes, destination: Path,
) -> InstallationControlRecoveryBundle:
    """Verify every member against independently supplied trust before publishing plaintext."""
    if len(recovery_key) != _KEY_SIZE:
        raise RecoveryAuthorityError("invalid_request: recovery key must be exactly 32 bytes")
    try:
        require_private_directory(source)
        require_private_directory(destination.parent)
        envelope_bytes = read_private_file(source / _HEADER, limit=_MAX_HEADER_BYTES + 1)
        if len(envelope_bytes) > _MAX_HEADER_BYTES:
            raise RecoveryAuthorityError("integrity_error: recovery envelope exceeds limit")
        envelope = _RecoveryEnvelope.model_validate(decode_recovery_json(envelope_bytes))
        if envelope.bundle_digest != anchor.bundle_digest:
            raise RecoveryAuthorityError("integrity_error: recovery envelope is for different authority")
        binding = bytes.fromhex(anchor.bundle_digest)
        key = AESGCM(recovery_key).decrypt(bytes.fromhex(envelope.wrapping_nonce), bytes.fromhex(envelope.wrapped_key), binding)
        manifest_ct = read_private_file(source / _MANIFEST, limit=_MAX_MANIFEST_BYTES + 17)
        if len(manifest_ct) > _MAX_MANIFEST_BYTES + 16:
            raise RecoveryAuthorityError("integrity_error: encrypted recovery manifest exceeds limit")
        manifest_bytes = AESGCM(key).decrypt(bytes.fromhex(envelope.manifest_nonce), manifest_ct, binding)
        manifest = InstallationControlRecoveryBundle.model_validate(decode_recovery_json(manifest_bytes))
        manifest.verify(anchor, public_key)
        members = {_member_name(position, encrypted=True) for position in range(len(manifest.members))}
        if len(envelope.members) != len(members) or {item.name for item in source.iterdir()} != members | {_HEADER, _MANIFEST}:
            raise RecoveryAuthorityError("integrity_error: recovery envelope member inventory differs")
        with tempfile.TemporaryDirectory(prefix=".control-recovery-open-", dir=destination.parent) as scratch:
            candidate = Path(scratch) / "verified"
            ensure_private_directory(candidate)
            for position, (member, encrypted) in enumerate(zip(manifest.members, envelope.members, strict=True)):
                ciphertext = source / _member_name(position, encrypted=True)
                require_private_file(ciphertext)
                if encrypted.ciphertext_size != member.size_bytes + 16:
                    raise RecoveryAuthorityError("integrity_error: recovery member ciphertext size differs")
                plaintext = candidate / _member_name(position, encrypted=False)
                decrypt_backup_participant(
                    ciphertext, plaintext, key=key, nonce=bytes.fromhex(encrypted.nonce),
                    expected_digest=encrypted.ciphertext_digest, expected_size=encrypted.ciphertext_size,
                )
                _check_member(plaintext, member.digest, member.size_bytes)
            _publish_directory(candidate, destination)
    except (InvalidTag, OSError, ValueError) as exc:
        raise RecoveryAuthorityError("integrity_error: encrypted control recovery could not be verified") from exc
    return manifest
