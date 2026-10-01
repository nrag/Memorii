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

from collections.abc import Callable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.persistence.runtime_contracts import RuntimeCommandRequest


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


def command_digest(request: RuntimeCommandRequest) -> str:
    import hashlib
    import json

    payload = json.dumps(
        request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class LocalDurableSpool:
    """Atomic file-admission spool: intake durable before acknowledgement."""

    def __init__(self, spool_directory: str | Path) -> None:
        self._directory = Path(spool_directory)
        self._directory.mkdir(parents=True, exist_ok=True)
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
            deliveries.mkdir(mode=0o700, exist_ok=True)
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
        for record in self.records():
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
    "SpoolRecord",
    "command_digest",
]
