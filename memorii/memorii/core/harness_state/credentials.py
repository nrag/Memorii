"""Installation-issued sidecar credentials with owner-only storage.

Credentials are minted by the installation owner's administration
service, stored with owner-only file permissions (0600 credential,
0700 directory) in the installation's control directory, and mapped
server-side to principals. Credential values are secrets: they never
appear in URLs or logs, and reading the store requires the same
filesystem authority as the installation itself.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class CredentialError(RuntimeError):
    """Credential issuance or lookup refused; the detail carries the reason."""


class IssuedCredential(BaseModel):
    """One installation-issued host credential record."""

    principal: str = Field(min_length=1)
    credential_id: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid", frozen=True)


class SidecarCredentialStore:
    """File-backed credential store beside the installation control owner."""

    def __init__(self, credentials_directory: str | Path) -> None:
        self._directory = Path(credentials_directory)
        self._directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self._directory, 0o700)
        self._index_path = self._directory / "credentials.json"

    def issue(self, principal: str) -> tuple[IssuedCredential, str]:
        """Mint one credential for a principal; returns record and secret.

        The secret is returned exactly once; only its SHA-256 digest is
        stored. Looking up a credential compares digests in constant time.
        """
        import hashlib
        import json

        if not principal:
            raise CredentialError("principal must be nonempty")
        secret = "mri_" + secrets.token_urlsafe(32)
        record = IssuedCredential(
            principal=principal,
            credential_id="cred-" + secrets.token_hex(8),
        )
        entries = self._read_entries()
        entries.append(
            {
                "principal": principal,
                "credential_id": record.credential_id,
                "secret_digest": hashlib.sha256(secret.encode()).hexdigest(),
            }
        )
        import tempfile

        descriptor, temporary = tempfile.mkstemp(
            dir=self._directory, prefix=".credentials.", suffix=".tmp"
        )
        try:
            payload = json.dumps({"entries": entries}, indent=2, sort_keys=True)
            os.write(descriptor, payload.encode("utf-8"))
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.chmod(temporary, 0o600)
        os.replace(temporary, self._index_path)
        return record, secret

    def principal_for(self, secret: str) -> str | None:
        """Map a presented bearer secret to its principal, or None."""
        import hashlib
        import hmac as _hmac

        digest = hashlib.sha256(secret.encode()).hexdigest()
        for entry in self._read_entries():
            if _hmac.compare_digest(entry["secret_digest"], digest):
                return entry["principal"]
        return None

    def verify_permissions(self) -> None:
        """Fail closed when the store is not owner-only."""
        mode = self._directory.stat().st_mode & 0o777
        if mode & 0o077:
            raise CredentialError(
                f"credential directory permissions are not owner-only: {oct(mode)}"
            )
        if self._index_path.exists():
            file_mode = self._index_path.stat().st_mode & 0o777
            if file_mode & 0o077:
                raise CredentialError(
                    "credential file permissions are not owner-only:"
                    f" {oct(file_mode)}"
                )

    def _read_entries(self) -> list[dict[str, str]]:
        import json

        if not self._index_path.exists():
            return []
        try:
            payload = json.loads(self._index_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise CredentialError("credential store is unreadable") from exc
        entries = payload.get("entries") if isinstance(payload, dict) else None
        if not isinstance(entries, list):
            raise CredentialError("credential store is malformed")
        return entries
