"""All-writer enrollment barrier for one installation.

The design contract: every production composition root registers its
actual writers, and an installation with an unregistered writer refuses
active service rather than making best-effort consistency claims. The
registry is durable control state; unknown writers fail closed with the
closed unsupported_configuration reason, and mode/backup guarantees can
rely on the enrollment being complete.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class WriterEnrollmentError(RuntimeError):
    """Enrollment refusal; the closed reason carries the cause."""


class WriterRecord(BaseModel):
    """One registered durable writer."""

    writer_id: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    enrolled_at_unix: int = Field(ge=0)

    model_config = ConfigDict(extra="forbid", frozen=True)


class WriterEnrollmentRegistry:
    """File-backed, owner-only writer enrollment under control state."""

    def __init__(self, enrollment_directory: str | Path) -> None:
        self._directory = Path(enrollment_directory)
        self._directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self._directory, 0o700)
        self._registry_path = self._directory / "writers.json"

    def enroll(self, writer_id: str, *, kind: str) -> WriterRecord:
        """Register one writer; re-enrollment is idempotent by identity."""
        if not writer_id or not kind:
            raise WriterEnrollmentError("writer id and kind must be nonempty")
        records = self._read()
        for record in records:
            if record.writer_id == writer_id:
                if record.kind != kind:
                    raise WriterEnrollmentError(
                        f"conflict: writer {writer_id} already enrolled as"
                        f" {record.kind}; refusing silent kind drift"
                    )
                return record
        record = WriterRecord(
            writer_id=writer_id,
            kind=kind,
            enrolled_at_unix=int(time.time()),
        )
        records.append(record)
        self._write(records)
        return record

    def require_enrolled(self, writer_id: str) -> WriterRecord:
        """Fail closed for unknown writers before any active service."""
        for record in self._read():
            if record.writer_id == writer_id:
                return record
        raise WriterEnrollmentError(
            f"unsupported_configuration: writer {writer_id} is not enrolled;"
            " register every production writer before serving active traffic"
        )

    def writers(self) -> tuple[WriterRecord, ...]:
        return tuple(self._read())

    def _read(self) -> list[WriterRecord]:
        if not self._registry_path.exists():
            return []
        value = json.loads(self._registry_path.read_text())
        if not isinstance(value, list):
            raise WriterEnrollmentError("writer enrollment registry is corrupt")
        return [WriterRecord.model_validate(item) for item in value]

    def _write(self, records: list[WriterRecord]) -> None:
        temporary = self._directory / ".writers.tmp"
        temporary.write_text(
            json.dumps(
                [record.model_dump() for record in records], sort_keys=True
            )
        )
        os.chmod(temporary, 0o600)
        os.replace(temporary, self._registry_path)


__all__ = ["WriterEnrollmentError", "WriterEnrollmentRegistry", "WriterRecord"]
