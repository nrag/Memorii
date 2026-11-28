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
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from memorii.core.memory_plane.file_lock import locked_file
from memorii.core.persistence.contracts import canonical_json_digest
from memorii.stores.sqlite.private_storage import read_private_file, write_private_file


class GrantRegistryError(RuntimeError):
    """Registry refusal; the closed reason carries the cause."""


class RevocationRecord(BaseModel):
    """One durable revocation entry."""

    grant_id: str = Field(min_length=1)
    epoch: int = Field(ge=1)
    revoked_at_unix: int = Field(ge=0)
    reason: str = Field(min_length=1)
    custody_operation_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)


_GrantId = Annotated[str, Field(min_length=1)]
_RevokedEpoch = Annotated[int, Field(ge=2, strict=True)]
_Epochs = TypeAdapter(dict[_GrantId, _RevokedEpoch])
_MAX_DENIAL_BYTES = 16 * 1024 * 1024


class GrantDenial(BaseModel):
    """Recovery-safe audit coordinate, with no bearer or free-form reason."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    grant_id: _GrantId
    epoch: _RevokedEpoch
    revoked_at_unix: Annotated[int, Field(ge=0, strict=True)]


class GrantDenialSnapshot(BaseModel):
    """Monotonic grant epochs and the corresponding durable revocation prefix."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    protocol_version: Literal[1] = 1
    denials: tuple[GrantDenial, ...] = ()

    @model_validator(mode="after")
    def validate_epochs(self) -> Self:
        epochs: dict[str, int] = {}
        for record in self.denials:
            if epochs.get(record.grant_id, 1) + 1 != record.epoch:
                raise ValueError("read grant denial epochs are not a contiguous history")
            epochs[record.grant_id] = record.epoch
        return self

    def epochs(self) -> dict[str, int]:
        return {record.grant_id: record.epoch for record in self.denials}

    def digest(self) -> str:
        return canonical_json_digest(self.model_dump(mode="json"))


def _unique_fields(items: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in items:
        if key in result:
            raise ValueError("grant registry contains duplicate fields")
        result[key] = value
    return result


def _bounded_private_file(path: Path) -> bytes:
    content = read_private_file(path, limit=_MAX_DENIAL_BYTES + 1)
    if len(content) > _MAX_DENIAL_BYTES:
        raise GrantRegistryError("resource_exhausted: read grant denial exceeds limit")
    return content


class GrantEpochRegistry:
    """File-backed, owner-only grant-epoch revocation registry."""

    def __init__(self, registry_directory: str | Path) -> None:
        self._directory = Path(registry_directory)
        self._directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self._directory, 0o700)
        self._epochs_path = self._directory / "grant-epochs.json"
        self._revocations_path = self._directory / "grant-revocations.jsonl"
        self._custody_required = self._directory / "recovery-custody.json"
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
        if not grant_id:
            raise GrantRegistryError("grant id must be nonempty")
        if not reason.strip():
            raise GrantRegistryError("revocation reason must be nonempty")
        with locked_file(self._directory / "registry.lock", exclusive=True):
            if self._custody_required.exists() or self._custody_required.is_symlink():
                raise GrantRegistryError("unavailable: read grant revocation requires independent custody")
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
                handle.write(record.model_dump_json(exclude_none=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        return record

    @contextmanager
    def recovery_lease(self) -> Iterator[None]:
        """Take the registry lease after independent custody and publication."""
        with locked_file(self._directory / "registry.lock", exclusive=True, private=True):
            yield

    def register_recovery_custody(self, custody_id: str) -> None:
        """Bind the registry to a custody owner while its recovery lease is held."""
        try:
            write_private_file(self._custody_required, self._custody_record(custody_id), exclusive=True)
        except FileExistsError:
            self.require_recovery_custody(custody_id)

    @staticmethod
    def _custody_record(custody_id: str) -> bytes:
        return json.dumps({"protocol_version": 1, "custody_id": custody_id}, sort_keys=True).encode("utf-8")

    def require_recovery_custody(self, custody_id: str) -> None:
        try:
            if _bounded_private_file(self._custody_required) == self._custody_record(custody_id):
                return
        except FileNotFoundError:
            pass
        raise GrantRegistryError("conflict: read grant registry is not bound to this recovery custodian")

    def _recovery_state(self) -> tuple[dict[str, int], GrantDenialSnapshot, tuple[RevocationRecord, ...]]:
        try:
            epochs = _Epochs.validate_python(json.loads(
                _bounded_private_file(self._epochs_path), object_pairs_hook=_unique_fields,
            ))
        except FileNotFoundError:
            epochs = {}
        lines = _bounded_private_file(self._revocations_path).splitlines()
        records = tuple(
            RevocationRecord.model_validate(json.loads(line, object_pairs_hook=_unique_fields)) for line in lines
        )
        snapshot = GrantDenialSnapshot(denials=tuple(GrantDenial(
            grant_id=record.grant_id, epoch=record.epoch, revoked_at_unix=record.revoked_at_unix,
        ) for record in records))
        return epochs, snapshot, records

    def recovery_snapshot(self) -> GrantDenialSnapshot:
        """Pin full deny history under an already-held recovery lease."""
        epochs, snapshot, _ = self._recovery_state()
        if epochs != snapshot.epochs():
            raise GrantRegistryError("needs_reconciliation: read grant epochs and audit disagree")
        return snapshot

    def apply_recovery_denial(
        self, denial: GrantDenial, *, before_digest: str, before_count: int, effect_digest: str,
        operation_digest: str,
    ) -> GrantDenialSnapshot:
        """Finish the exact planned epoch/audit effect under a recovery lease."""
        epochs, audit, records = self._recovery_state()
        prior = GrantDenialSnapshot(denials=audit.denials[:before_count])
        if prior.digest() != before_digest or len(prior.denials) != before_count:
            raise GrantRegistryError("needs_reconciliation: read grant audit does not match pending proof")
        successor = GrantDenialSnapshot(denials=(*prior.denials, denial))
        if successor.digest() != effect_digest:
            raise GrantRegistryError("needs_reconciliation: read grant effect differs from pending proof")
        if audit == prior and epochs in (prior.epochs(), successor.epochs()):
            append_record = RevocationRecord(
                grant_id=denial.grant_id, epoch=denial.epoch, revoked_at_unix=denial.revoked_at_unix,
                reason="operator-authorized recovery revocation", custody_operation_digest=operation_digest,
            )
            previous = _bounded_private_file(self._revocations_path)
            content = previous + (append_record.model_dump_json() + "\n").encode("utf-8")
            if len(content) > _MAX_DENIAL_BYTES:
                raise GrantRegistryError("resource_exhausted: read grant denial exceeds limit")
            if epochs != successor.epochs():
                self._write_epochs(successor.epochs())
            write_private_file(self._revocations_path, content)
        elif (
            audit != successor or epochs != successor.epochs()
            or records[-1].custody_operation_digest != operation_digest
        ):
            raise GrantRegistryError("needs_reconciliation: read grant effect differs from pending proof")
        return self.recovery_snapshot()

    def restore_recovery_snapshot(self, snapshot: GrantDenialSnapshot, *, custody_id: str) -> None:
        """Materialize content-free terminal denials into an inert replacement."""
        with self.recovery_lease():
            if self.recovery_snapshot().denials:
                raise GrantRegistryError("conflict: replacement read grant registry is already populated")
            records = (
                RevocationRecord(grant_id=record.grant_id, epoch=record.epoch, revoked_at_unix=record.revoked_at_unix,
                                 reason="retained recovery revocation")
                for record in snapshot.denials
            )
            write_private_file(self._revocations_path, b"".join(
                (record.model_dump_json(exclude_none=True) + "\n").encode("utf-8") for record in records
            ))
            self._write_epochs(snapshot.epochs())
            self.register_recovery_custody(custody_id)

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

    @contextmanager
    def current_read(self, grant_id: str, epoch: int, *, blocking: bool = True) -> Iterator[None]:
        """Linearize assembling an authorized read result with grant revocation."""
        with locked_file(self._directory / "registry.lock", exclusive=False, blocking=blocking):
            self.require_current(grant_id, epoch)
            yield

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
