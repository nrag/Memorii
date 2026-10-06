"""Grant-epoch revocation registry for read grants.

The registry advances one monotonically increasing epoch per grant id and
records revocations durably. A revoked grant must fail closed at the
service boundary: the read path consults ``current_epoch`` before serving,
and continuation cursors minted under a superseded epoch are already
rejected by the cursor codec's epoch binding. Revocation is append-only —
re-issuing a grant never lowers its epoch.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class GrantRegistryError(RuntimeError):
    """Registry refusal; the closed reason carries the cause."""


class RevocationRecord(BaseModel):
    """One durable revocation entry."""

    grant_id: str = Field(min_length=1)
    epoch: int = Field(ge=1)
    revoked_at_unix: int = Field(ge=0)
    reason: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid", frozen=True)


class GrantEpochRegistry:
    """File-backed, owner-only grant-epoch revocation registry."""

    def __init__(self, registry_directory: str | Path) -> None:
        self._directory = Path(registry_directory)
        self._directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self._directory, 0o700)
        self._epochs_path = self._directory / "grant-epochs.json"
        self._revocations_path = self._directory / "grant-revocations.jsonl"
        # Owner-only from the first append; plain open() would apply umask.
        if not self._revocations_path.exists():
            descriptor = os.open(
                self._revocations_path, os.O_WRONLY | os.O_CREAT, 0o600
            )
            os.close(descriptor)

    def current_epoch(self, grant_id: str) -> int:
        """The grant's current epoch (1 before any revocation)."""
        return int(self._read_epochs().get(grant_id, 1))

    def revoke(self, grant_id: str, *, reason: str) -> RevocationRecord:
        """Advance the grant's epoch and record the revocation durably.

        The whole operation holds the registry's exclusive lock so two
        concurrent revocations of different grants cannot lose one epoch
        advance through a last-writer-wins epochs map.
        """
        from memorii.core.memory_plane.file_lock import locked_file

        if not grant_id:
            raise GrantRegistryError("grant id must be nonempty")
        if not reason.strip():
            raise GrantRegistryError("revocation reason must be nonempty")
        with locked_file(self._directory / "registry.lock", exclusive=True):
            epochs = self._read_epochs()
            next_epoch = int(epochs.get(grant_id, 1)) + 1
            epochs[grant_id] = next_epoch
            self._write_epochs(epochs)
            record = RevocationRecord(
                grant_id=grant_id,
                epoch=next_epoch,
                revoked_at_unix=int(time.time()),
                reason=reason,
            )
            with self._revocations_path.open("a", encoding="utf-8") as handle:
                handle.write(record.model_dump_json() + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        return record

    def revocations(self) -> tuple[RevocationRecord, ...]:
        if not self._revocations_path.exists():
            return ()
        return tuple(
            RevocationRecord.model_validate_json(line)
            for line in self._revocations_path.read_text().splitlines()
            if line.strip()
        )

    def require_current(self, grant_id: str, epoch: int) -> None:
        """Fail closed when the presented epoch is superseded."""
        current = self.current_epoch(grant_id)
        if int(epoch) != current:
            raise GrantRegistryError(
                f"stale_grant: grant {grant_id} at epoch {epoch};"
                f" current epoch is {current}"
            )

    def verify_permissions(self) -> None:
        for path in (self._epochs_path, self._revocations_path):
            if path.exists() and (path.stat().st_mode & 0o077) != 0:
                raise GrantRegistryError(
                    f"grant registry file permissions are not owner-only: {path}"
                )

    def _read_epochs(self) -> dict[str, int]:
        if not self._epochs_path.exists():
            return {}
        value = json.loads(self._epochs_path.read_text())
        if not isinstance(value, dict):
            raise GrantRegistryError("grant epoch registry is corrupt")
        return {str(key): int(item) for key, item in value.items()}

    def _write_epochs(self, epochs: dict[str, int]) -> None:
        temporary = self._directory / f".grant-epochs.{os.getpid()}.tmp"
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(epochs, sort_keys=True))
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, self._epochs_path)
        directory = os.open(self._directory, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)


__all__ = ["GrantEpochRegistry", "GrantRegistryError", "RevocationRecord"]
