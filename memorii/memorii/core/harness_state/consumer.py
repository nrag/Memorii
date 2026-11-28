"""Runtime event consumer: durable local spool with idempotent intake.

The packaged consumer library drives the same persistent command
service. Producers cannot choose authority through message fields: the
consumer configuration binds each queue to an allowlisted issuer and a
finite grant set. A crash before intake acknowledgement causes
redelivery with the same operation id; a crash after acknowledgement
resumes the stored attempt without the broker; a divergent duplicate
dead-letters; transient storage failure never acknowledges; invalid or
untrusted messages emit a content-free rejection and are never
executed.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.persistence.runtime_contracts import (
    OperationOrigin,
    OperationOriginCoordinate,
    RuntimeCommandReceipt,
    RuntimeCommandRequest,
)
from memorii.stores.sqlite.private_storage import ensure_private_directory, read_private_file

if TYPE_CHECKING:
    from contextlib import AbstractContextManager

    from memorii.core.harness_state.managed_spool_store import ManagedSpoolSnapshot, SqliteManagedSpool

MAX_MANAGED_INTAKE_BYTES = 2 << 20


class ConsumerDeliveryError(RuntimeError):
    """Delivery refused; closed reasons carry the cause."""


class HostEventDelivery(BaseModel):
    """One typed delivery from a transport; the receipt stays outside."""

    transport_message_id: str = Field(min_length=1)
    producer_binding: str = Field(min_length=1)
    command: RuntimeCommandRequest

    model_config = ConfigDict(extra="forbid", frozen=True)


class SpoolRecord(BaseModel):
    """Durable intake record: one operation id, idempotent by digest."""

    operation_id: str = Field(min_length=1)
    producer_binding: str = Field(min_length=1)
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    state: Literal["pending", "committed", "dead_letter"] = "pending"

    model_config = ConfigDict(extra="forbid", frozen=True)


class ManagedSpoolEntry(BaseModel):
    """A durable managed intent and its original installation-issued proof."""

    delivery: HostEventDelivery
    operation_origin: OperationOrigin
    state: Literal["pending", "committed"] = "pending"

    model_config = ConfigDict(extra="forbid", frozen=True)


@dataclass(frozen=True)
class ManagedSpoolItem:
    sequence: int
    entry: ManagedSpoolEntry


def operation_key(coordinate: OperationOriginCoordinate) -> str:
    identity = (
        coordinate.installation_id,
        coordinate.repository_id,
        coordinate.generation_id,
        coordinate.principal,
        coordinate.client_namespace,
        coordinate.operation_id,
    )
    return hashlib.sha256(json.dumps(identity, separators=(",", ":")).encode()).hexdigest()


def _unique_intake_fields(fields: list[tuple[str, object]]) -> dict[str, object]:
    result = dict(fields)
    if len(result) != len(fields):
        raise ValueError("duplicate managed intake field")
    return result


def parse_managed_intake(payload: bytes) -> ManagedSpoolEntry:
    if len(payload) > MAX_MANAGED_INTAKE_BYTES:
        raise ConsumerDeliveryError("integrity_error: stored managed intake exceeds limit")
    try:
        entry = ManagedSpoolEntry.model_validate(
            json.loads(payload.decode(), object_pairs_hook=_unique_intake_fields),
        )
    except ValueError as exc:
        raise ConsumerDeliveryError("integrity_error: unreadable managed intake") from exc
    coordinate, command = entry.operation_origin.coordinate, entry.delivery.command
    if (
        entry.delivery.producer_binding != coordinate.client_namespace
        or command.operation_id != coordinate.operation_id
        or command.managed_intent_digest() != coordinate.request_digest
    ):
        raise ConsumerDeliveryError("integrity_error: stored managed intake has the wrong intent binding")
    return entry


class ManagedRuntimeSpool:
    """Durable managed intake selected by the verified installation owner."""

    def __init__(self, directory: str | Path, *, expected_store_id: str | None = None) -> None:
        self._directory = Path(directory)
        self._sqlite: SqliteManagedSpool | None = None
        if expected_store_id is None:
            ensure_private_directory(self._directory)
        else:
            from memorii.core.harness_state.managed_spool_store import SqliteManagedSpool

            self._sqlite = SqliteManagedSpool(self._directory, expected_store_id)

    @classmethod
    def stage_sqlite(cls, directory: str | Path, *, store_id: str) -> Path:
        """Build a candidate before signing its expected installation identity.

        The installation owner must stop old binaries before staging and keep
        legacy inputs inert after selection. A candidate file is not authority.
        """
        from memorii.core.harness_state.managed_spool_store import SqliteManagedSpool
        from memorii.core.memory_plane.file_lock import locked_file

        root = Path(directory)
        ensure_private_directory(root)

        with locked_file(root / "intake.lock", exclusive=True):
            return SqliteManagedSpool.stage(root, store_id, lambda: cls._legacy_entries(root))

    @staticmethod
    def _legacy_entries(root: Path) -> Iterator[tuple[ManagedSpoolEntry, bytes]]:
        for path in sorted(root.glob("*.json")):
            payload = read_private_file(path, limit=MAX_MANAGED_INTAKE_BYTES + 1)
            entry = parse_managed_intake(payload)
            if path.name != f"{operation_key(entry.operation_origin.coordinate)}.json":
                raise ConsumerDeliveryError("integrity_error: legacy managed intake identity mismatch")
            yield entry, payload

    @classmethod
    @contextmanager
    def verified_sqlite_stage(cls, directory: Path, *, store_id: str) -> Iterator[Path]:
        """Pin the old exact intake through the stopped owner's selection."""
        from memorii.core.harness_state.managed_spool_store import SqliteManagedSpool
        from memorii.core.memory_plane.file_lock import locked_file

        with locked_file(directory / "intake.lock", exclusive=True):
            yield SqliteManagedSpool.verify_stage(directory, store_id, lambda: cls._legacy_entries(directory))

    def _path(self, coordinate: OperationOriginCoordinate) -> Path:
        return self._directory / f"{operation_key(coordinate)}.json"

    def _read(self, path: Path) -> ManagedSpoolEntry:
        try:
            entry = parse_managed_intake(read_private_file(path, limit=MAX_MANAGED_INTAKE_BYTES + 1))
        except OSError as exc:
            raise ConsumerDeliveryError("integrity_error: unreadable managed intake") from exc
        if self._path(entry.operation_origin.coordinate) != path:
            raise ConsumerDeliveryError("integrity_error: intake identity mismatch")
        return entry

    def _write(self, path: Path, entry: ManagedSpoolEntry) -> None:
        descriptor, name = tempfile.mkstemp(dir=self._directory, prefix=".managed-intake-")
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "wb") as writer:
                writer.write(entry.model_dump_json().encode())
                writer.flush()
                os.fsync(writer.fileno())
            os.replace(temporary, path)
            directory = os.open(self._directory, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            temporary.unlink(missing_ok=True)

    def admit(
        self,
        delivery: HostEventDelivery,
        *,
        operation_origin: OperationOrigin,
        validate: Callable[[RuntimeCommandRequest, OperationOrigin], object],
    ) -> ManagedSpoolEntry:
        """Validate with the trusted managed command owner before retaining."""
        from memorii.core.memory_plane.file_lock import locked_file

        coordinate = operation_origin.coordinate
        if (
            delivery.producer_binding != coordinate.client_namespace
            or delivery.command.operation_id != coordinate.operation_id
        ):
            raise ConsumerDeliveryError("denied: managed intake binding mismatch")
        validate(delivery.command, operation_origin)
        entry = ManagedSpoolEntry(delivery=delivery, operation_origin=operation_origin)
        if self._sqlite is not None:
            return self._sqlite.admit(entry)
        path = self._path(operation_origin.coordinate)
        with locked_file(self._directory / "intake.lock", exclusive=True):
            if path.exists():
                existing = self._read(path)
                if existing.operation_origin != operation_origin or existing.delivery.command != delivery.command:
                    raise ConsumerDeliveryError("conflict: divergent managed intake")
                return existing
            self._write(path, entry)
            return entry

    def pending(self) -> tuple[ManagedSpoolEntry, ...]:
        """Return intact intents; the dispatcher must revalidate authority."""
        if self._sqlite is not None:
            return tuple(self.iter_pending())
        from memorii.core.memory_plane.file_lock import locked_file

        with locked_file(self._directory / "intake.lock", exclusive=False):
            entries = (self._read(path) for path in sorted(self._directory.glob("*.json")))
            return tuple(entry for entry in entries if entry.state == "pending")

    def iter_pending(self) -> Iterator[ManagedSpoolEntry]:
        """Drain a stable sequence cut without holding SQLite open during dispatch."""
        if self._sqlite is None:
            yield from self.pending()
            return
        yield from self._iter_sqlite_pending(self._sqlite, generation=None)

    def iter_generation_pending(
        self, *, installation_id: str, repository_id: str, generation_id: str,
    ) -> Iterator[ManagedSpoolEntry]:
        """Only the selected generation can supply work to a live drain."""
        generation = (installation_id, repository_id, generation_id)
        if self._sqlite is not None:
            yield from self._iter_sqlite_pending(self._sqlite, generation=generation)
            return
        for entry in self.pending():
            origin = entry.operation_origin.coordinate
            if (origin.installation_id, origin.repository_id, origin.generation_id) == generation:
                yield entry

    @staticmethod
    def _iter_sqlite_pending(
        spool: SqliteManagedSpool, *, generation: tuple[str, str, str] | None,
    ) -> Iterator[ManagedSpoolEntry]:
        with spool.pin_snapshot() as snapshot:
            high_water = snapshot.high_water_mark
        after_sequence = 0
        while after_sequence < high_water:
            page = spool.pending_page(
                after_sequence=after_sequence, through_sequence=high_water, limit=100, generation=generation,
            )
            if not page:
                return
            yield from (item.entry for item in page)
            after_sequence = page[-1].sequence

    def pending_page(self, *, after_sequence: int = 0, limit: int = 100) -> tuple[ManagedSpoolItem, ...]:
        if (
            type(after_sequence) is not int or not 0 <= after_sequence < 1 << 63
            or type(limit) is not int or not 1 <= limit <= 100
        ):
            raise ConsumerDeliveryError("invalid_request: managed spool page bounds are invalid")
        return self._selected().pending_page(after_sequence=after_sequence, limit=limit)

    def pending_resumes(
        self, *, installation_id: str, repository_id: str, generation_id: str,
        principal: str, client_namespace: str, task_id: str,
    ) -> tuple[ManagedSpoolEntry, ...]:
        if self._sqlite is not None:
            return self._sqlite.pending_resumes(
                installation_id=installation_id, repository_id=repository_id, generation_id=generation_id,
                principal=principal, client_namespace=client_namespace, task_id=task_id,
            )
        return tuple(
            entry for entry in self.pending()
            if entry.delivery.command.kind == "resume_task" and entry.delivery.command.task_id == task_id
            and entry.operation_origin.coordinate.installation_id == installation_id
            and entry.operation_origin.coordinate.repository_id == repository_id
            and entry.operation_origin.coordinate.generation_id == generation_id
            and entry.operation_origin.coordinate.principal == principal
            and entry.operation_origin.coordinate.client_namespace == client_namespace
        )

    def _selected(self) -> SqliteManagedSpool:
        if self._sqlite is None:
            raise ConsumerDeliveryError("unavailable: managed spool has no verified SQLite selection")
        return self._sqlite

    def pin_snapshot(self) -> AbstractContextManager[ManagedSpoolSnapshot]:
        return self._selected().pin_snapshot()

    def hold_prior_generation(self, *, installation_id: str, repository_id: str, generation_id: str) -> None:
        self._selected().hold_prior_generation(
            installation_id=installation_id, repository_id=repository_id, generation_id=generation_id,
        )

    def find(self, coordinate: OperationOriginCoordinate) -> ManagedSpoolEntry | None:
        """Look up the original signed delivery for one immutable operation identity."""
        if self._sqlite is not None:
            return self._sqlite.find(coordinate)
        from memorii.core.memory_plane.file_lock import locked_file

        path = self._path(coordinate)
        with locked_file(self._directory / "intake.lock", exclusive=False):
            return self._read(path) if path.exists() else None

    def mark_committed(self, entry: ManagedSpoolEntry, *, receipt: RuntimeCommandReceipt | None = None) -> None:
        """Acknowledge only the exact intent whose command was dispatched."""
        if self._sqlite is not None:
            self._sqlite.mark_committed(entry, receipt)
            return
        from memorii.core.memory_plane.file_lock import locked_file

        path = self._path(entry.operation_origin.coordinate)
        with locked_file(self._directory / "intake.lock", exclusive=True):
            existing = self._read(path)
            if existing == entry.model_copy(update={"state": "committed"}):
                return
            if existing != entry or entry.state != "pending":
                raise ConsumerDeliveryError("conflict: managed intake changed before acknowledgement")
            self._write(path, entry.model_copy(update={"state": "committed"}))


def command_digest(request: RuntimeCommandRequest) -> str:
    payload = json.dumps(
        request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class LocalDurableSpool:
    """Atomic file-admission spool: intake durable before acknowledgement."""

    def __init__(self, spool_directory: str | Path) -> None:
        self._directory = Path(spool_directory)
        ensure_private_directory(self._directory)
        self._records_path = self._directory / "intake.jsonl"
        self._lock_path = self._directory / "intake.lock"

    def admit(
        self,
        delivery: HostEventDelivery,
        *,
        allowlisted_producers: tuple[str, ...],
        storage_unavailable: Callable[[], None] | None = None,
    ) -> SpoolRecord:
        """Record intake durably; returns the idempotent record.

        ``storage_unavailable`` is a fault hook for tests: when it raises,
        nothing is written and the caller must not acknowledge — modelling
        transient storage failure.
        """
        from memorii.core.memory_plane.file_lock import locked_file

        if delivery.producer_binding not in allowlisted_producers:
            raise ConsumerDeliveryError(
                "denied: producer binding is not allowlisted for this queue"
            )
        digest = command_digest(delivery.command)
        if storage_unavailable is not None:
            storage_unavailable()
        with locked_file(self._lock_path, exclusive=True):
            existing = self._find(delivery.command.operation_id)
            if existing is not None:
                if existing.request_digest != digest:
                    record = existing.model_copy(update={"state": "dead_letter"})
                    self._rewrite_except(existing.operation_id)
                    self._append(record)
                    raise ConsumerDeliveryError(
                        "conflict: divergent duplicate dead-lettered"
                    )
                return existing
            record = SpoolRecord(
                operation_id=delivery.command.operation_id,
                producer_binding=delivery.producer_binding,
                request_digest=digest,
            )
            import os

            descriptor = os.open(
                self._records_path,
                os.O_WRONLY | os.O_CREAT | os.O_APPEND,
                0o600,
            )
            try:
                payload = (record.model_dump_json() + "\n").encode("utf-8")
                os.write(descriptor, payload)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            # Retain the full delivery beside its digest-only record so a
            # consumer can drain committed intent without the producer.
            # The filename is the operation id's digest, never client text,
            # so a hostile operation id cannot traverse the directory.
            deliveries = self._directory / "deliveries"
            ensure_private_directory(deliveries)
            content_path = deliveries / f"{digest}.json"
            descriptor = os.open(
                content_path,
                os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                0o600,
            )
            try:
                os.write(descriptor, delivery.model_dump_json().encode("utf-8"))
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        return record

    def records(self) -> tuple[SpoolRecord, ...]:
        from memorii.core.memory_plane.file_lock import locked_file

        with locked_file(self._lock_path, exclusive=False):
            return self._records_unlocked_read()

    def _records_unlocked_read(self) -> tuple[SpoolRecord, ...]:
        if not self._records_path.exists():
            return ()
        lines = self._records_path.read_text(encoding="utf-8").splitlines()
        return tuple(
            SpoolRecord.model_validate_json(line) for line in lines if line.strip()
        )

    def pending_deliveries(
        self, *, allowlisted_producers: tuple[str, ...]
    ) -> tuple[tuple[SpoolRecord, HostEventDelivery], ...]:
        """Drainable (record, delivery) pairs for allowlisted pending rows.

        A pending record without retained content, or content whose digest
        no longer matches the record, is never returned: it stays for
        explicit operator handling instead of being guessed into effect.
        """
        result: list[tuple[SpoolRecord, HostEventDelivery]] = []
        deliveries = self._directory / "deliveries"
        from memorii.core.memory_plane.file_lock import locked_file

        # Content files are read under the same shared lock the records use:
        # a concurrent admit rewrites content via O_TRUNC under the exclusive
        # lock, and an unlocked read could observe an empty or partial file.
        with locked_file(self._lock_path, exclusive=False):
            for record in self._records_unlocked_read():
                if record.state != "pending":
                    continue
                if record.producer_binding not in allowlisted_producers:
                    continue
                content_path = deliveries / f"{record.request_digest}.json"
                if not content_path.exists():
                    continue
                delivery = HostEventDelivery.model_validate_json(
                    content_path.read_text(encoding="utf-8")
                )
                if command_digest(delivery.command) != record.request_digest:
                    continue
                result.append((record, delivery))
        return tuple(result)

    def mark_committed(self, operation_id: str) -> SpoolRecord:
        """Advance one pending record to committed under the intake lock."""
        from memorii.core.memory_plane.file_lock import locked_file

        with locked_file(self._lock_path, exclusive=True):
            existing = self._find(operation_id)
            if existing is None:
                raise ConsumerDeliveryError(f"unknown operation {operation_id}")
            if existing.state == "committed":
                return existing
            if existing.state == "dead_letter":
                raise ConsumerDeliveryError(
                    "conflict: dead-lettered operation cannot commit"
                )
            record = existing.model_copy(update={"state": "committed"})
            self._rewrite_except(operation_id)
            self._append(record)
            return record

    def _find(self, operation_id: str) -> SpoolRecord | None:
        for record in self._records_unlocked():
            if record.operation_id == operation_id:
                return record
        return None

    def _records_unlocked(self) -> tuple[SpoolRecord, ...]:
        if not self._records_path.exists():
            return ()
        lines = self._records_path.read_text(encoding="utf-8").splitlines()
        return tuple(
            SpoolRecord.model_validate_json(line) for line in lines if line.strip()
        )

    def _rewrite_except(self, operation_id: str) -> None:
        """Atomically rewrite the intake log without one operation's rows."""
        import os
        import tempfile

        kept = [
            record.model_dump_json()
            for record in self._records_unlocked()
            if record.operation_id != operation_id
        ]
        descriptor, temporary = tempfile.mkstemp(
            dir=self._directory, prefix=".intake.", suffix=".tmp"
        )
        try:
            payload = ("\n".join(kept) + ("\n" if kept else "")).encode("utf-8")
            os.write(descriptor, payload)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.chmod(temporary, 0o600)
        os.replace(temporary, self._records_path)
        import os as _os

        directory_fd = _os.open(self._directory, _os.O_RDONLY)
        try:
            _os.fsync(directory_fd)
        finally:
            _os.close(directory_fd)

    def _append(self, record: SpoolRecord) -> None:
        import os

        descriptor = os.open(
            self._records_path,
            os.O_WRONLY | os.O_CREAT | os.O_APPEND,
            0o600,
        )
        try:
            os.write(descriptor, (record.model_dump_json() + "\n").encode("utf-8"))
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


__all__ = [
    "ConsumerDeliveryError",
    "HostEventDelivery",
    "LocalDurableSpool",
    "ManagedRuntimeSpool",
    "ManagedSpoolEntry",
    "SpoolRecord",
    "command_digest",
]
