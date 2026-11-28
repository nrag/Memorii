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
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from secrets import token_bytes

from memorii.core.memory_plane.file_lock import locked_file
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.query import (
    DEFAULT_CURSOR_LIFETIME,
    QUERY_CURSOR_PURPOSE,
    MemoryPlanePage,
    MemoryPlaneQuery,
    QueryCursorCodec,
)
from memorii.core.memory_plane.store import (
    SEMANTIC_CHECKPOINT_SECRET_PURPOSE,
    BackendCheckpointSignatureAuthority,
    CatalogMetadataSnapshot,
    CheckpointSignatureAuthority,
    GovernedWritePolicy,
    IndexedGovernedWritePolicy,
    MemoryPlaneCorruptionError,
    MemoryPlanePrecondition,
    MemoryPlaneRevisionConflictError,
    MemoryPlaneTimedWriteSnapshot,
    MemoryPlaneWriteAuthorization,
    PersistedBatch,
    clone_record,
    contains_runtime_context,
    is_runtime_writeback_candidate,
    validate_expected_write_revision,
    validate_governed_write,
    validate_preconditions,
)
from memorii.core.storage_administration.revoked_identity_view import (
    RevokedIdentityServingGate,
)
from memorii.domain.enums import CommitStatus, MemoryDomain
from memorii.stores.sqlite.catalog_selection import selected_catalog_activation_id
from memorii.stores.sqlite.partition import PartitionDataRepository

_PARTITION_DATABASE_NAME = "partition.sqlite3"
_CATALOG_ROW_LIMIT = 4_096
_CATALOG_BYTE_LIMIT = 16 << 20
_LEARNED_ACTIVATION_KIND = "learned_ontology_activation_attempt_v1"


class _SqliteCatalogMetadataSnapshot:
    """Bound candidate visits and decoded record bytes inside one read transaction."""

    def __init__(self, connection: sqlite3.Connection, *, raw_payloads: bool) -> None:
        self._connection = connection
        self._raw_payloads = raw_payloads
        self._visited = 0
        self._remaining_bytes = _CATALOG_BYTE_LIMIT
        self._records: dict[str, CanonicalMemoryRecord | None] = {}

    def record(self, memory_id: str) -> CanonicalMemoryRecord | None:
        if memory_id in self._records:
            return self._records[memory_id]
        if self._visited == _CATALOG_ROW_LIMIT:
            raise MemoryPlaneCorruptionError("catalog metadata exceeds its row budget")
        self._visited += 1
        if self._raw_payloads:
            query = (
                "SELECT p.raw_size, CASE WHEN p.raw_size <= ? THEN CAST(p.body AS TEXT) END AS record_json"
                " FROM memory_current_records c LEFT JOIN memory_payloads p USING (payload_digest)"
                " WHERE c.memory_id = ?"
            )
        else:
            query = (
                "SELECT length(CAST(record_json AS BLOB)) AS raw_size,"
                " CASE WHEN length(CAST(record_json AS BLOB)) <= ? THEN record_json END AS record_json"
                " FROM memory_current_records WHERE memory_id = ?"
            )
        row = self._connection.execute(query, (self._remaining_bytes, memory_id)).fetchone()
        result = None
        if row is not None:
            size = row["raw_size"]
            if type(size) is not int or size <= 0 or size > self._remaining_bytes or row["record_json"] is None:
                raise MemoryPlaneCorruptionError("catalog metadata is incomplete or exceeds its byte budget")
            self._remaining_bytes -= size
            result = _decode_record(row["record_json"])
            if result.memory_id != memory_id:
                raise MemoryPlaneCorruptionError("catalog metadata identity differs from its storage key")
        self._records[memory_id] = result
        return result

    def activation_attempts(self, *, principal_id: str, agent_id: str) -> Iterator[CanonicalMemoryRecord]:
        if self._raw_payloads:
            selected_id = selected_catalog_activation_id(
                self._connection, principal_id=principal_id, agent_id=agent_id,
            )
            if selected_id is not None:
                yield self._activation_record(selected_id)
            return
        # Legacy SQLite lacks a scoped activation projection.
        rows = self._connection.execute(
            "SELECT memory_id FROM memory_current_records"
            " INDEXED BY memory_current_records_source_kind WHERE source_kind = ?",
            (_LEARNED_ACTIVATION_KIND,),
        )
        for row in rows:
            yield self._activation_record(row["memory_id"])

    def _activation_record(self, memory_id: str) -> CanonicalMemoryRecord:
        record = self.record(memory_id)
        if record is None or record.source_kind != _LEARNED_ACTIVATION_KIND:
            raise MemoryPlaneCorruptionError("catalog activation differs from its lookup coordinate")
        return record


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
        self._checkpoint_signature_authority: BackendCheckpointSignatureAuthority | None = None
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
        base_path = self._partition.protected_storage_root
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
            self._checkpoint_signature_authority = BackendCheckpointSignatureAuthority(secret)
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
            return self.apply_batch_in_transaction(
                connection, records, expected_revision=None, authorization=authorization,
            )

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
            return self.apply_batch_in_transaction(
                connection, records, expected_revision=expected_revision,
                expected_write_revision=expected_write_revision, preconditions=preconditions,
                authorization=authorization, transaction_precondition=transaction_precondition,
            )

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
        verified_partition: bool = False,
    ) -> int:
        """Apply one batch inside a coordinator-owned partition transaction.

        The publication coordinator opens a manual partition transaction,
        applies the batch through this method, signs the candidate tuple from
        the transaction's own view, persists the control intent and only then
        commits. Validation semantics are identical to ``apply_batch``.
        """
        validate_expected_write_revision(expected_write_revision)
        if transaction_precondition is not None:
            transaction_precondition()
        self._ensure_validated_chain(connection)
        write_revision, data_revision = self._partition.read_revision_state(connection)
        current_records = self._current_records_for_write(
            connection, records, preconditions, authorization, verified_partition=verified_partition,
        )
        if expected_revision is not None and expected_revision != data_revision:
            raise MemoryPlaneRevisionConflictError(
                f"memory-plane revision changed: expected {expected_revision}, actual {data_revision}"
            )
        if expected_write_revision is not None and expected_write_revision != write_revision:
            raise MemoryPlaneRevisionConflictError(
                "memory-plane write revision changed: "
                f"expected {expected_write_revision}, actual {write_revision}"
            )
        validate_preconditions(current_records, preconditions)
        validate_governed_write(
            self._governed_write_policy,
            records,
            tuple(current_records.values()),
            authorization,
        )
        return self._append_batch_unlocked(connection, records, data_revision=data_revision)

    def _current_records_for_write(
        self,
        connection: sqlite3.Connection,
        records: tuple[CanonicalMemoryRecord, ...],
        preconditions: tuple[MemoryPlanePrecondition, ...],
        authorization: MemoryPlaneWriteAuthorization | None,
        *,
        verified_partition: bool,
    ) -> dict[str, CanonicalMemoryRecord]:
        policy = self._governed_write_policy
        required = (
            policy.required_current_record_ids(records, authorization)
            if verified_partition and isinstance(policy, IndexedGovernedWritePolicy) else None
        )
        if required is None:
            rows = self._partition.read_current_record_rows(connection)
            return {row["memory_id"]: _decode_record(row["record_json"]) for row in rows}
        identities = required.union(
            (precondition.memory_id for precondition in preconditions),
            (record.memory_id for record in records if is_runtime_writeback_candidate(record)),
        )
        result: dict[str, CanonicalMemoryRecord] = {}
        for identity in sorted(identities):
            row = self._partition.read_current_record_row(connection, identity)
            if row is not None:
                result[identity] = _decode_record(row["record_json"])
        return result

    def read_snapshot(self) -> tuple[int, tuple[CanonicalMemoryRecord, ...]]:
        with self._partition.transaction(write=False) as connection:
            _, data_revision, current_records = self._validated_state(connection)
            return data_revision, tuple(
                clone_record(record) for record in current_records.values()
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
                tuple(clone_record(record) for record in current_records.values()),
            )

    def read_verified_catalog_metadata(
        self,
        callback: Callable[[int, CatalogMetadataSnapshot], object],
        *,
        signed_manifest_digest: str,
    ) -> object:
        """Read scoped rows while the managed caller holds verified publication."""
        with self._partition.transaction(write=False) as connection:
            if not self._partition.has_verified_manifest_base(connection, signed_manifest_digest):
                raise MemoryPlaneCorruptionError("catalog metadata transaction differs from its verified manifest")
            _, data_revision = self._partition.read_revision_state(connection)
            return callback(data_revision, _SqliteCatalogMetadataSnapshot(
                connection, raw_payloads=self._partition.uses_raw_memory_payloads(connection),
            ))

    def read_write_snapshot(self) -> tuple[int, tuple[CanonicalMemoryRecord, ...]]:
        with self._partition.transaction(write=False) as connection:
            write_revision, _, current_records = self._validated_state(connection)
            return write_revision, tuple(
                clone_record(record) for record in current_records.values()
            )

    def read_timed_write_snapshot(
        self, *, now: Callable[[], datetime]
    ) -> MemoryPlaneTimedWriteSnapshot:
        with self._partition.transaction(write=False) as connection:
            write_revision, _, current_records = self._validated_state(connection)
            records = tuple(clone_record(record) for record in current_records.values())
            return MemoryPlaneTimedWriteSnapshot(write_revision, records, now())

    def get_record(self, memory_id: str) -> CanonicalMemoryRecord | None:
        with self._partition.transaction(write=False) as connection:
            self._ensure_validated_chain(connection)
            row = self._partition.read_current_record_row(connection, memory_id)
            if row is None:
                return None
            return clone_record(_decode_record(row["record_json"]))

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
                statuses=None if status is None else [status.value],
                domains=domain_values,
                source_kinds=None if source_kind is None else [source_kind],
            )
            return [clone_record(_decode_record(row["record_json"])) for row in rows]

    def query_records(
        self,
        query: MemoryPlaneQuery,
        *,
        cursor: str | None = None,
        now: Callable[[], datetime] | None = None,
        cursor_lifetime: timedelta = DEFAULT_CURSOR_LIFETIME,
        revoked_view: RevokedIdentityServingGate | None = None,
    ) -> MemoryPlanePage:
        """Serve one bounded typed query page with an authenticated cursor."""
        clock = now or (lambda: datetime.now(UTC))
        codec = QueryCursorCodec(
            self.load_or_create_protected_secret(
                purpose=QUERY_CURSOR_PURPOSE, length=32
            )
        )
        with self._partition.transaction(write=False) as connection:
            self._ensure_validated_chain(connection)
            write_revision, data_revision = self._partition.read_revision_state(
                connection
            )
            offset = 0
            if cursor is not None:
                offset = codec.decode(
                    cursor,
                    query_digest=query.digest(),
                    write_revision=write_revision,
                    data_revision=data_revision,
                    now=clock(),
                )
            if query.kind == "record_lookup":
                assert query.memory_id is not None
                row = self._partition.read_current_record_row(
                    connection, query.memory_id
                )
                record = None if row is None else _decode_record(row["record_json"])
                if record is not None and not _matches_query(record, query):
                    record = None
                if (
                    record is not None
                    and revoked_view is not None
                    and not revoked_view.keeps_record(record)
                ):
                    record = None
                return MemoryPlanePage(
                    records=() if record is None else (clone_record(record),),
                    next_cursor=None,
                    truncated=False,
                )
            if revoked_view is None:
                rows = self._partition.read_current_record_rows(
                    connection,
                    statuses=[status.value for status in query.statuses]
                    or None,
                    domains=[domain.value for domain in query.domains] or None,
                    source_kinds=list(query.source_kinds) or None,
                    limit=query.page_size + 1,
                    offset=offset,
                )
                truncated = len(rows) > query.page_size
                records = tuple(
                    clone_record(_decode_record(row["record_json"]))
                    for row in rows[: query.page_size]
                )
                next_scan_offset = offset + query.page_size if truncated else None
            else:
                # Revocation exclusion applies before the page slice, inside
                # the read transaction: rows are scanned from the cursor's
                # raw offset until page_size+1 serving-eligible records are
                # collected, so pages and cursors stay exact within one
                # revision (the cursor already binds both revisions, and a
                # forget rewrites records, invalidating older cursors).
                kept: list = []
                kept_offsets: list[int] = []
                raw_offset = offset
                scan_chunk = max(query.page_size + 1, 16)
                while len(kept) <= query.page_size:
                    chunk = self._partition.read_current_record_rows(
                        connection,
                        statuses=[status.value for status in query.statuses]
                        or None,
                        domains=[domain.value for domain in query.domains]
                        or None,
                        source_kinds=list(query.source_kinds) or None,
                        limit=scan_chunk,
                        offset=raw_offset,
                    )
                    if not chunk:
                        break
                    for row in chunk:
                        record = _decode_record(row["record_json"])
                        if revoked_view.keeps_record(record):
                            kept.append(clone_record(record))
                            kept_offsets.append(raw_offset)
                            if len(kept) > query.page_size:
                                break
                        raw_offset += 1
                    else:
                        continue
                    break
                truncated = len(kept) > query.page_size
                records = tuple(kept[: query.page_size])
                next_scan_offset = (
                    kept_offsets[query.page_size] if truncated else None
                )
        next_cursor = None
        if truncated:
            expires_at = clock() + cursor_lifetime
            next_cursor = codec.encode(
                query_digest=query.digest(),
                write_revision=write_revision,
                data_revision=data_revision,
                offset=next_scan_offset
                if next_scan_offset is not None
                else offset + query.page_size,
                expires_at=expires_at,
            )
        return MemoryPlanePage(
            records=records, next_cursor=next_cursor, truncated=truncated
        )

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
        for row in self._partition.iter_batch_rows(connection):
            try:
                batch = PersistedBatch.model_validate_json(row["batch_json"])
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
                contains_runtime_context(batch.records)
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
        batch = PersistedBatch.create(
            revision=write_revision + 1,
            data_revision=data_revision + int(contains_runtime_context(records)),
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


def _matches_query(record: CanonicalMemoryRecord, query: MemoryPlaneQuery) -> bool:
    if query.statuses and record.status not in query.statuses:
        return False
    if query.domains and record.domain not in query.domains:
        return False
    return not (query.source_kinds and record.source_kind not in query.source_kinds)


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
