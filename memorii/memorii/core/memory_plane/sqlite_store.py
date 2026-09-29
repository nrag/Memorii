"""SQLite memory-plane store over the shared application-data partition.

Implements the existing ``MemoryPlaneStore`` contract over one SQLite
partition: immutable batches with the canonical checksum codec, dual
write/data revisions driven by the runtime-context visibility rule,
precondition compare-and-swap, governed write policies, detached snapshots
in first-insertion order, protected secrets and the backend-owned checkpoint
signature authority. Batches are appended, never rewritten.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from secrets import token_bytes

from memorii.core.memory_plane.file_lock import locked_file
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.store import (
    SEMANTIC_CHECKPOINT_SECRET_PURPOSE,
    CheckpointSignatureAuthority,
    GovernedWritePolicy,
    MemoryPlaneCorruptionError,
    MemoryPlanePrecondition,
    MemoryPlaneRevisionConflictError,
    MemoryPlaneTimedWriteSnapshot,
    MemoryPlaneWriteAuthorization,
    _BackendCheckpointSignatureAuthority,
    _clone_record,
    _contains_runtime_context,
    _PersistedBatch,
    _validate_expected_write_revision,
    _validate_governed_write,
    _validate_preconditions,
)
from memorii.domain.enums import CommitStatus, MemoryDomain
from memorii.stores.sqlite.partition import PartitionDataRepository

_PARTITION_DATABASE_NAME = "partition.sqlite3"


class SqliteMemoryPlaneStore:
    """Durable memory-plane backend on the shared SQLite partition."""

    def __init__(self, partition: PartitionDataRepository | str | Path) -> None:
        if isinstance(partition, PartitionDataRepository):
            self._partition = partition
        else:
            path = Path(partition)
            database_path = path if path.suffix else path / _PARTITION_DATABASE_NAME
            self._partition = PartitionDataRepository(database_path)
        self._governed_write_policy: GovernedWritePolicy | None = None
        self._checkpoint_signature_owner: object | None = None
        self._checkpoint_signature_authority: _BackendCheckpointSignatureAuthority | None = None
        self._validated_chain_key: tuple[int, int] | None = None

    @property
    def durable(self) -> bool:
        return True

    @property
    def partition(self) -> PartitionDataRepository:
        return self._partition

    def load_or_create_protected_secret(self, *, purpose: str, length: int) -> bytes:
        if purpose == SEMANTIC_CHECKPOINT_SECRET_PURPOSE:
            raise PermissionError("checkpoint signing material is backend-private")
        return self._load_or_create_protected_secret(purpose=purpose, length=length)

    def _load_or_create_protected_secret(self, *, purpose: str, length: int) -> bytes:
        if not purpose or length < 32:
            raise ValueError("protected secret purpose or length is invalid")
        base_path = self._partition.database_path.parent
        protected = base_path / ".protected"
        secret_path = protected / f"{hashlib.sha256(purpose.encode('utf-8')).hexdigest()}.key"
        with locked_file(base_path / ".protected.lock", exclusive=True):
            protected.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.chmod(protected, 0o700)
            if secret_path.exists():
                try:
                    mode = secret_path.stat().st_mode & 0o777
                    secret = secret_path.read_bytes()
                except OSError as exc:
                    raise MemoryPlaneCorruptionError("protected secret is unreadable") from exc
                if mode & 0o077 or len(secret) != length:
                    raise MemoryPlaneCorruptionError(
                        "protected secret permissions or length are invalid"
                    )
                return secret
            secret = token_bytes(length)
            descriptor = os.open(
                secret_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            try:
                written = os.write(descriptor, secret)
                if written != len(secret):
                    raise OSError("partial protected-secret write")
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            _fsync_directory(protected)
            return secret

    def _claim_semantic_checkpoint_signature_authority(
        self,
        *,
        owner: object,
    ) -> CheckpointSignatureAuthority:
        if self._checkpoint_signature_owner is None:
            self._checkpoint_signature_owner = owner
        elif self._checkpoint_signature_owner is not owner:
            raise PermissionError("checkpoint signing authority is already owned")
        if self._checkpoint_signature_authority is None:
            secret = self._load_or_create_protected_secret(
                purpose=SEMANTIC_CHECKPOINT_SECRET_PURPOSE,
                length=32,
            )
            self._checkpoint_signature_authority = _BackendCheckpointSignatureAuthority(secret)
        return self._checkpoint_signature_authority

    def install_governed_write_policy(self, policy: GovernedWritePolicy) -> None:
        self._governed_write_policy = policy

    def stage_record(
        self,
        record: CanonicalMemoryRecord,
        *,
        authorization: MemoryPlaneWriteAuthorization | None = None,
    ) -> None:
        self.write_records((record,), authorization=authorization)

    def upsert_record(
        self,
        record: CanonicalMemoryRecord,
        *,
        authorization: MemoryPlaneWriteAuthorization | None = None,
    ) -> None:
        self.write_records((record,), authorization=authorization)

    def write_records(
        self,
        records: tuple[CanonicalMemoryRecord, ...],
        *,
        authorization: MemoryPlaneWriteAuthorization | None = None,
    ) -> int:
        with self._partition.transaction(write=True) as connection:
            _, data_revision, current_records = self._validated_state(connection)
            _validate_governed_write(
                self._governed_write_policy,
                records,
                tuple(current_records.values()),
                authorization,
            )
            return self._append_batch_unlocked(connection, records, data_revision=data_revision)

    def revision(self) -> int:
        with self._partition.transaction(write=False) as connection:
            _, data_revision, _ = self._validated_state(connection)
            return data_revision

    def apply_batch(
        self,
        records: tuple[CanonicalMemoryRecord, ...],
        *,
        expected_revision: int | None,
        expected_write_revision: int | None = None,
        preconditions: tuple[MemoryPlanePrecondition, ...] = (),
        authorization: MemoryPlaneWriteAuthorization | None = None,
        transaction_precondition: Callable[[], None] | None = None,
    ) -> int:
        with self._partition.transaction(write=True) as connection:
            _validate_expected_write_revision(expected_write_revision)
            if transaction_precondition is not None:
                transaction_precondition()
            write_revision, data_revision, current_records = self._validated_state(connection)
            if expected_revision is not None and expected_revision != data_revision:
                raise MemoryPlaneRevisionConflictError(
                    f"memory-plane revision changed: expected {expected_revision}, actual {data_revision}"
                )
            if expected_write_revision is not None and expected_write_revision != write_revision:
                raise MemoryPlaneRevisionConflictError(
                    "memory-plane write revision changed: "
                    f"expected {expected_write_revision}, actual {write_revision}"
                )
            _validate_preconditions(current_records, preconditions)
            _validate_governed_write(
                self._governed_write_policy,
                records,
                tuple(current_records.values()),
                authorization,
            )
            return self._append_batch_unlocked(connection, records, data_revision=data_revision)

    def apply_batch_in_transaction(
        self,
        connection: sqlite3.Connection,
        records: tuple[CanonicalMemoryRecord, ...],
        *,
        expected_revision: int | None,
        expected_write_revision: int | None = None,
        preconditions: tuple[MemoryPlanePrecondition, ...] = (),
        authorization: MemoryPlaneWriteAuthorization | None = None,
        transaction_precondition: Callable[[], None] | None = None,
    ) -> int:
        """Apply one batch inside a coordinator-owned partition transaction.

        The publication coordinator opens a manual partition transaction,
        applies the batch through this method, signs the candidate tuple from
        the transaction's own view, persists the control intent and only then
        commits. Validation semantics are identical to ``apply_batch``.
        """
        _validate_expected_write_revision(expected_write_revision)
        if transaction_precondition is not None:
            transaction_precondition()
        write_revision, data_revision, current_records = self._validated_state(connection)
        if expected_revision is not None and expected_revision != data_revision:
            raise MemoryPlaneRevisionConflictError(
                f"memory-plane revision changed: expected {expected_revision}, actual {data_revision}"
            )
        if expected_write_revision is not None and expected_write_revision != write_revision:
            raise MemoryPlaneRevisionConflictError(
                "memory-plane write revision changed: "
                f"expected {expected_write_revision}, actual {write_revision}"
            )
        _validate_preconditions(current_records, preconditions)
        _validate_governed_write(
            self._governed_write_policy,
            records,
            tuple(current_records.values()),
            authorization,
        )
        return self._append_batch_unlocked(connection, records, data_revision=data_revision)

    def read_snapshot(self) -> tuple[int, tuple[CanonicalMemoryRecord, ...]]:
        with self._partition.transaction(write=False) as connection:
            _, data_revision, current_records = self._validated_state(connection)
            return data_revision, tuple(
                _clone_record(record) for record in current_records.values()
            )

    def read_snapshot_linearized(
        self,
        callback: Callable[[int, tuple[CanonicalMemoryRecord, ...]], object],
    ) -> object:
        """Hold the partition read transaction through protected read release."""
        with self._partition.transaction(write=False) as connection:
            _, data_revision, current_records = self._validated_state(connection)
            return callback(
                data_revision,
                tuple(_clone_record(record) for record in current_records.values()),
            )

    def read_write_snapshot(self) -> tuple[int, tuple[CanonicalMemoryRecord, ...]]:
        with self._partition.transaction(write=False) as connection:
            write_revision, _, current_records = self._validated_state(connection)
            return write_revision, tuple(
                _clone_record(record) for record in current_records.values()
            )

    def read_timed_write_snapshot(
        self, *, now: Callable[[], datetime]
    ) -> MemoryPlaneTimedWriteSnapshot:
        with self._partition.transaction(write=False) as connection:
            write_revision, _, current_records = self._validated_state(connection)
            records = tuple(_clone_record(record) for record in current_records.values())
            return MemoryPlaneTimedWriteSnapshot(write_revision, records, now())

    def get_record(self, memory_id: str) -> CanonicalMemoryRecord | None:
        with self._partition.transaction(write=False) as connection:
            self._ensure_validated_chain(connection)
            row = self._partition.read_current_record_row(connection, memory_id)
            if row is None:
                return None
            return _clone_record(_decode_record(row["record_json"]))

    def list_records(
        self,
        *,
        status: CommitStatus | None = None,
        domains: list[MemoryDomain] | None = None,
        source_kind: str | None = None,
    ) -> list[CanonicalMemoryRecord]:
        domain_values = (
            [domain.value for domain in domains] if domains is not None else None
        )
        with self._partition.transaction(write=False) as connection:
            self._ensure_validated_chain(connection)
            rows = self._partition.read_current_record_rows(
                connection,
                status=None if status is None else status.value,
                domains=domain_values,
                source_kind=source_kind,
            )
            return [_clone_record(_decode_record(row["record_json"])) for row in rows]

    def _validated_state(
        self, connection: sqlite3.Connection
    ) -> tuple[int, int, dict[str, CanonicalMemoryRecord]]:
        self._ensure_validated_chain(connection)
        write_revision, data_revision = self._partition.read_revision_state(connection)
        rows = self._partition.read_current_record_rows(connection)
        current_records = {row["memory_id"]: _decode_record(row["record_json"]) for row in rows}
        return write_revision, data_revision, current_records

    def _ensure_validated_chain(self, connection: sqlite3.Connection) -> None:
        """Validate the immutable batch chain once per observed revision state.

        The cache key is the persisted revision state, so a second handle's
        commit is detected and the chain revalidated before any read relies
        on it. Own writes refresh the key in the same transaction.
        """
        write_revision, data_revision = self._partition.read_revision_state(connection)
        chain_key = (write_revision, data_revision)
        if self._validated_chain_key == chain_key:
            return
        expected_revision = 1
        previous_data_revision = 0
        for row in self._partition.read_batch_rows(connection):
            try:
                batch = _PersistedBatch.model_validate_json(row["batch_json"])
            except ValueError as exc:
                raise MemoryPlaneCorruptionError(
                    f"invalid memory-plane batch at revision {row['revision']}: {exc}"
                ) from exc
            if batch.revision != expected_revision or row["revision"] != expected_revision:
                raise MemoryPlaneCorruptionError(
                    f"non-contiguous memory-plane revision: expected {expected_revision},"
                    f" got {row['revision']}"
                )
            if batch.checksum != row["checksum"]:
                raise MemoryPlaneCorruptionError("memory-plane batch checksum mismatch")
            expected_data_revision = previous_data_revision + int(
                _contains_runtime_context(batch.records)
            )
            if batch.data_revision != expected_data_revision or (
                row["data_revision"] != expected_data_revision
            ):
                raise MemoryPlaneCorruptionError(
                    f"invalid memory-plane data revision: expected {expected_data_revision},"
                    f" got {row['data_revision']}"
                )
            previous_data_revision = expected_data_revision
            expected_revision += 1
        if (write_revision, data_revision) != (expected_revision - 1, previous_data_revision):
            raise MemoryPlaneCorruptionError(
                "memory-plane revision state does not match the batch chain"
            )
        self._validated_chain_key = chain_key

    def _append_batch_unlocked(
        self,
        connection: sqlite3.Connection,
        records: tuple[CanonicalMemoryRecord, ...],
        *,
        data_revision: int,
    ) -> int:
        write_revision, _ = self._partition.read_revision_state(connection)
        batch = _PersistedBatch.create(
            revision=write_revision + 1,
            data_revision=data_revision + int(_contains_runtime_context(records)),
            records=records,
        )
        self._partition.append_memory_batch(
            connection,
            revision=batch.revision,
            data_revision=batch.data_revision,
            checksum=batch.checksum,
            batch_json=batch.model_dump_json(),
            records_json=[
                (
                    record.memory_id,
                    record.model_dump_json(),
                    record.status.value,
                    record.domain.value,
                    record.source_kind,
                )
                for record in batch.records
            ],
        )
        self._validated_chain_key = (batch.revision, batch.data_revision)
        return batch.data_revision


def _decode_record(record_json: str) -> CanonicalMemoryRecord:
    try:
        return CanonicalMemoryRecord.model_validate_json(record_json)
    except ValueError as exc:
        raise MemoryPlaneCorruptionError(f"invalid memory-plane record: {exc}") from exc


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


__all__ = ["SqliteMemoryPlaneStore"]
