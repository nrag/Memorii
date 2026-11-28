"""Installation-issued sidecar credentials with owner-only storage.

Credentials are minted by the installation owner's administration
service, stored with owner-only file permissions (0600 credential,
0700 directory) in the installation's control directory, and mapped
server-side to principals. Credential values are secrets: they never
appear in URLs or logs, and reading the store requires the same
filesystem authority as the installation itself.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.memory_plane.file_lock import locked_file
from memorii.stores.sqlite.private_storage import (
    ensure_private_directory,
    open_private_file,
    require_private_directory,
    require_private_file,
    write_private_file,
)


class CredentialError(RuntimeError):
    """Credential issuance or lookup refused; the detail carries the reason."""


class IssuedCredential(BaseModel):
    """One installation-issued host credential record."""

    principal: str = Field(min_length=1)
    credential_id: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid", frozen=True)


class _CredentialEntry(IssuedCredential):
    secret_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class _CredentialIndex(BaseModel):
    entries: tuple[_CredentialEntry, ...] = ()

    model_config = ConfigDict(extra="forbid", frozen=True)


class SidecarCredentialStore:
    """File-backed credential store beside the installation control owner."""

    def __init__(self, credentials_directory: str | Path) -> None:
        self._directory = Path(credentials_directory)
        ensure_private_directory(self._directory)
        self._index_path = self._directory / "credentials.json"
        self._lock_path = self._directory / "credentials.lock"

    def issue(self, principal: str, *, credential_id: str | None = None) -> tuple[IssuedCredential, str]:
        """Mint one credential for a principal; returns record and secret.

        The secret is returned exactly once; only its SHA-256 digest is
        stored. Looking up a credential compares digests in constant time.
        """
        if not principal:
            raise CredentialError("principal must be nonempty")
        secret = "mri_" + secrets.token_urlsafe(32)
        record = IssuedCredential(
            principal=principal,
            credential_id=credential_id or "cred-" + secrets.token_hex(8),
        )
        entry = _CredentialEntry(
            principal=principal,
            credential_id=record.credential_id,
            secret_digest=hashlib.sha256(secret.encode()).hexdigest(),
        )
        with locked_file(self._lock_path, exclusive=True, private=True):
            entries = self._read_entries()
            if any(existing.credential_id == record.credential_id for existing in entries):
                raise CredentialError("conflict: credential is already issued")
            self._publish((*entries, entry))
        return record, secret

    def retire(self, credential_id: str) -> None:
        """Withdraw the bearer digest without reusing or importing its secret."""
        with locked_file(self._lock_path, exclusive=True, private=True):
            entries = self._read_entries()
            remaining = tuple(entry for entry in entries if entry.credential_id != credential_id)
            if remaining != entries:
                self._publish(remaining)

    def principal_for(self, secret: str) -> str | None:
        """Map a presented bearer secret to its principal, or None."""
        record = self.credential_for(secret)
        return None if record is None else record.principal

    def credential_for(self, secret: str) -> IssuedCredential | None:
        """Resolve a bearer to its opaque credential and principal.

        Write grants bind to ``credential_id`` rather than principal so two
        credentials for one user cannot silently share command authority.
        """
        digest = hashlib.sha256(secret.encode()).hexdigest()
        for entry in self._read_entries():
            if hmac.compare_digest(entry.secret_digest, digest):
                return IssuedCredential(
                    principal=entry.principal, credential_id=entry.credential_id,
                )
        return None

    @contextmanager
    def current_credential(self, secret: str) -> Iterator[IssuedCredential]:
        """Hold the credential read lease across a nonblocking protected write."""
        with locked_file(self._lock_path, exclusive=False, private=True, blocking=False):
            credential = self.credential_for(secret)
            if credential is None:
                raise CredentialError("host credential is unavailable")
            yield credential

    def verify_permissions(self) -> None:
        """Fail closed when the store is not owner-only."""
        try:
            require_private_directory(self._directory)
            require_private_file(self._index_path, allow_missing=True)
        except OSError as exc:
            raise CredentialError("credential storage must be owner-only") from exc

    def _read_entries(self) -> tuple[_CredentialEntry, ...]:
        try:
            with open_private_file(self._index_path) as source:
                entries = _CredentialIndex.model_validate_json(source.read()).entries
        except FileNotFoundError:
            return ()
        except (OSError, ValueError) as exc:
            raise CredentialError("credential store is unreadable") from exc
        if len({entry.credential_id for entry in entries}) != len(entries):
            raise CredentialError("credential store is malformed")
        return entries

    def _publish(self, entries: tuple[_CredentialEntry, ...]) -> None:
        write_private_file(self._index_path, _CredentialIndex(entries=entries).model_dump_json().encode())
