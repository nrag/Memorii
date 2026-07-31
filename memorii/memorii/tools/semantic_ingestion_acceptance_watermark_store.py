"""Durable, acceptance-owned anti-rewind coordinate for traceability releases.

This intentionally stores one small record only.  It is not a MemoryPlane
record and is not an implementation of the broader approval repository.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from memorii.core.memory_plane.file_lock import locked_file
from memorii.tools.semantic_ingestion_traceability_registry import canonical_document

_FORMAT = "memorii.semantic-ingestion.acceptance-watermark.v1"
_SEAL_FORMAT = "memorii.semantic-ingestion.acceptance-watermark-bootstrap-seal.v1"
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class WatermarkAdvanced:
    """The candidate is now the durable high-water coordinate."""


@dataclass(frozen=True)
class WatermarkRejected:
    reason: str


@dataclass(frozen=True)
class WatermarkUnavailable:
    reason: str


WatermarkAdvanceResult = WatermarkAdvanced | WatermarkRejected | WatermarkUnavailable


class TraceabilityReleaseWatermarkStore(Protocol):
    """The acceptance gate's required single-record atomic authority."""

    def provision(self, epoch: int, sequence: int, release_digest: str) -> WatermarkAdvanceResult: ...

    def compare_and_advance(self, epoch: int, sequence: int, release_digest: str) -> WatermarkAdvanceResult: ...


def _coordinate_is_valid(epoch: object, sequence: object) -> bool:
    return type(epoch) is int and type(sequence) is int and epoch >= 1 and sequence >= 1


def _digest_is_valid(value: object) -> bool:
    return type(value) is str and _DIGEST.fullmatch(value) is not None


class FileTraceabilityReleaseWatermarkStore:
    """One-record durable adapter with a cross-process exclusive transaction."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._seal_path = path.with_name(f"{path.name}.bootstrap-seal")
        self._lock_path = path.with_name(f"{path.name}.lock")

    def provision(self, epoch: int, sequence: int, release_digest: str) -> WatermarkAdvanceResult:
        if not _coordinate_is_valid(epoch, sequence) or not _digest_is_valid(release_digest):
            return WatermarkUnavailable("watermark_candidate_invalid")
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with locked_file(self._lock_path, exclusive=True):
                seal = self._read_locked(self._seal_path, _SEAL_FORMAT)
                prior = self._read_locked(self._path, _FORMAT)
                if seal is None and prior is None:
                    self._write_locked(self._seal_path, _SEAL_FORMAT, epoch, sequence, release_digest)
                    self._write_locked(self._path, _FORMAT, epoch, sequence, release_digest)
                    return WatermarkAdvanced()
                if isinstance(seal, WatermarkUnavailable):
                    return seal
                if isinstance(prior, WatermarkUnavailable):
                    return prior
                if seal is None or prior is None:
                    return WatermarkUnavailable("watermark_storage_missing")
                sealed = (seal["epoch"], seal["sequence"], seal["release_digest"])
                if sealed != (
                    epoch,
                    sequence,
                    release_digest,
                ):
                    return WatermarkRejected("watermark_already_provisioned")
                return self._validate_seal_and_current(seal, prior)
        except (OSError, TypeError, ValueError):
            return WatermarkUnavailable("watermark_storage_unavailable")

    def compare_and_advance(self, epoch: int, sequence: int, release_digest: str) -> WatermarkAdvanceResult:
        if not _coordinate_is_valid(epoch, sequence) or not _digest_is_valid(release_digest):
            return WatermarkUnavailable("watermark_candidate_invalid")
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with locked_file(self._lock_path, exclusive=True):
                seal = self._read_locked(self._seal_path, _SEAL_FORMAT)
                prior = self._read_locked(self._path, _FORMAT)
                if isinstance(seal, WatermarkUnavailable):
                    return seal
                if isinstance(prior, WatermarkUnavailable):
                    return prior
                if seal is None or prior is None:
                    return WatermarkUnavailable("watermark_storage_missing")
                consistent = self._validate_seal_and_current(seal, prior)
                if not isinstance(consistent, WatermarkAdvanced):
                    return consistent
                candidate = (epoch, sequence)
                old_coordinate = (prior["epoch"], prior["sequence"])
                if candidate < old_coordinate:
                    return WatermarkRejected("active_pointer_watermark_rewind")
                if candidate == old_coordinate:
                    if release_digest == prior["release_digest"]:
                        return WatermarkAdvanced()
                    return WatermarkRejected("active_pointer_watermark_substitution")
                self._write_locked(self._path, _FORMAT, epoch, sequence, release_digest)
                return WatermarkAdvanced()
        except (OSError, TypeError, ValueError):
            return WatermarkUnavailable("watermark_storage_unavailable")

    def _read_locked(self, path: Path, expected_format: str) -> dict[str, object] | WatermarkUnavailable | None:
        if not path.exists():
            return None
        raw = path.read_bytes()
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return WatermarkUnavailable("watermark_storage_corrupt")
        if (
            not isinstance(value, dict)
            or set(value) != {"format", "epoch", "sequence", "release_digest"}
            or value.get("format") != expected_format
            or not _coordinate_is_valid(value.get("epoch"), value.get("sequence"))
            or not _digest_is_valid(value.get("release_digest"))
            or canonical_document(value) != raw
        ):
            return WatermarkUnavailable("watermark_storage_corrupt")
        return value

    def _validate_seal_and_current(
        self, seal: dict[str, object], current: dict[str, object]
    ) -> WatermarkAdvanceResult:
        sealed_coordinate = (seal["epoch"], seal["sequence"])
        current_coordinate = (current["epoch"], current["sequence"])
        if current_coordinate < sealed_coordinate:
            return WatermarkUnavailable("watermark_storage_corrupt")
        if current_coordinate == sealed_coordinate and current["release_digest"] != seal["release_digest"]:
            return WatermarkUnavailable("watermark_storage_corrupt")
        return WatermarkAdvanced()

    def _write_locked(self, path: Path, format_name: str, epoch: int, sequence: int, release_digest: str) -> None:
        payload = canonical_document(
            {"format": format_name, "epoch": epoch, "sequence": sequence, "release_digest": release_digest}
        )
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
