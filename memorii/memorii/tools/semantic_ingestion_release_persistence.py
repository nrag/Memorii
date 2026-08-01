"""Durable publication tails coordinated with an independent monotonic fence.

The release gate authenticates and validates opaque publication bytes before
calling this owner.  This module never parses or upgrades those bytes: it
persists their exact authenticated tail, atomically selects one tail, and
allows a rollback only by appending another monotonic selection transaction.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Literal, Protocol

from memorii.core.memory_plane.file_lock import locked_file
from memorii.tools.semantic_ingestion_traceability_registry import canonical_document
from memorii.tools.semantic_ingestion_traceability_release import (
    TraceabilityGateAuthorized,
    TraceabilityGateRejected,
    TraceabilityGateResult,
    TraceabilityGateUnavailable,
    TraceabilityReleasePublicationStore,
    TraceabilityReleaseWatermarkStore,
    WatermarkAdvanced,
    WatermarkRejected,
    WatermarkUnavailable,
)

_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class PublishedTraceabilityRelease:
    """Exact immutable bytes selected by one accepted publication tail."""

    epoch: int
    sequence: int
    release_digest: str
    release_artifact: bytes
    release_history_artifact: bytes
    active_pointer_artifact: bytes
    pointer_history_artifact: bytes


@dataclass(frozen=True)
class PublicationTail:
    """Opaque, exact-CAS identity of a corrected-v2 selected tail."""

    epoch: int
    sequence: int
    release_digest: str
    pointer_history_digest: str
    tail_digest: str
    predecessor_tail_digest: str | None = None
    selected_tail_digest: str | None = None


@dataclass(frozen=True)
class PublicationVersionInventory:
    """Read-only version classification; legacy state is never activatable."""

    state: Literal["empty", "corrected_v2", "legacy", "mixed", "corrupt"]
    corrected_v2_tail_count: int
    legacy_record_count: int
    current: PublicationTail | None

    @property
    def can_activate_corrected_v2(self) -> bool:
        return self.state == "corrected_v2" and self.current is not None


FenceRecord = tuple[int, int, str, str | None, str]


class MonotonicFenceStore(Protocol):
    """Independent durable authority for the minimum accepted coordinate."""

    def records(self) -> list[FenceRecord] | TraceabilityGateUnavailable: ...

    def advance(
        self, epoch: int, sequence: int, release_digest: str, tail_digest: str | None
    ) -> WatermarkAdvanced | WatermarkRejected | WatermarkUnavailable: ...


class FileMonotonicFenceStore:
    """Explicitly test-only file fence; snapshots can capture its authority."""

    _FORMAT = "memorii.semantic-ingestion.monotonic-fence.v1"
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock_path = path.with_name(f"{path.name}.lock")

    def durable_backend_id(self) -> str:
        return f"file:{self._path.resolve()}"

    def records(self) -> list[FenceRecord] | TraceabilityGateUnavailable:
        try:
            if not self._path.parent.exists():
                return []
            with locked_file(self._lock_path, exclusive=False):
                return self._records_locked()
        except (OSError, TypeError, ValueError):
            return TraceabilityGateUnavailable("persistence_outcome_indeterminate")

    def advance(
        self, epoch: int, sequence: int, release_digest: str, tail_digest: str | None
    ) -> WatermarkAdvanced | WatermarkRejected | WatermarkUnavailable:
        if (
            not _valid_coordinate(epoch, sequence)
            or not _valid_digest(release_digest)
            or tail_digest is not None and not _valid_digest(tail_digest)
        ):
            return WatermarkUnavailable("watermark_candidate_invalid")
        try:
            parent_existed = self._path.parent.exists()
            self._path.parent.mkdir(parents=True, exist_ok=True)
            if not parent_existed:
                parent = os.open(self._path.parent.parent, os.O_RDONLY)
                try:
                    os.fsync(parent)
                finally:
                    os.close(parent)
            with locked_file(self._lock_path, exclusive=True):
                records = self._records_locked()
                if isinstance(records, TraceabilityGateUnavailable):
                    return WatermarkUnavailable("watermark_storage_corrupt")
                prior = None if not records else records[-1]
                if prior is not None:
                    coordinate = (epoch, sequence)
                    if coordinate < prior[:2]:
                        return WatermarkRejected("active_pointer_watermark_rewind")
                    if coordinate == prior[:2]:
                        if (release_digest, tail_digest) == (prior[2], prior[3]):
                            return WatermarkAdvanced()
                        if not (
                            release_digest == prior[2]
                            and prior[3] is None
                            and tail_digest is not None
                        ):
                            return WatermarkRejected("active_pointer_watermark_substitution")
                body = {
                    "format": self._FORMAT,
                    "epoch": epoch,
                    "sequence": sequence,
                    "release_digest": release_digest,
                    "tail_digest": tail_digest,
                    "predecessor_fence_digest": None if prior is None else prior[4],
                }
                raw = canonical_document(body)
                descriptor = os.open(
                    self._path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600
                )
                with os.fdopen(descriptor, "ab", closefd=True) as handle:
                    handle.write(raw)
                    handle.flush()
                    os.fsync(handle.fileno())
                directory = os.open(self._path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
                return WatermarkAdvanced()
        except (OSError, TypeError, ValueError):
            return WatermarkUnavailable("watermark_storage_unavailable")

    def _records_locked(self) -> list[FenceRecord] | TraceabilityGateUnavailable:
        if not self._path.exists():
            return []
        records: list[FenceRecord] = []
        prior: FenceRecord | None = None
        for raw in self._path.read_bytes().splitlines(keepends=True):
            value = _canonical_json(raw)
            if value is None or set(value) != {
                "format", "epoch", "sequence", "release_digest", "tail_digest",
                "predecessor_fence_digest",
            } or value.get("format") != self._FORMAT:
                return TraceabilityGateUnavailable("persistence_outcome_indeterminate")
            epoch, sequence = value["epoch"], value["sequence"]
            release_digest, tail_digest = value["release_digest"], value["tail_digest"]
            predecessor = value["predecessor_fence_digest"]
            if (
                not _valid_coordinate(epoch, sequence)
                or not _valid_digest(release_digest)
                or tail_digest is not None and not _valid_digest(tail_digest)
                or predecessor is not None and not _valid_digest(predecessor)
                or predecessor != (None if prior is None else prior[4])
            ):
                return TraceabilityGateUnavailable("persistence_outcome_indeterminate")
            assert isinstance(epoch, int) and isinstance(sequence, int)
            assert isinstance(release_digest, str)
            assert tail_digest is None or isinstance(tail_digest, str)
            prior = (epoch, sequence, release_digest, tail_digest, _digest(raw))
            records.append(prior)
        return records


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _valid_coordinate(epoch: object, sequence: object) -> bool:
    return type(epoch) is int and type(sequence) is int and epoch >= 1 and sequence >= 1


def _valid_digest(value: object) -> bool:
    return type(value) is str and _DIGEST.fullmatch(value) is not None


class InMemoryTraceabilityReleasePublicationStore(TraceabilityReleasePublicationStore):
    """Linearizable reference implementation with append-only accepted tails."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._current: PublishedTraceabilityRelease | None = None
        self._tails: dict[str, tuple[PublishedTraceabilityRelease, PublicationTail]] = {}
        self._current_tail: PublicationTail | None = None

    def anti_rollback_backend_identity(self) -> object:
        return self

    def publication_recovery_domain(self) -> str:
        return "test-memory-publication"

    def publication_store_id(self) -> str:
        return "test-memory-publication-store"

    @property
    def current(self) -> PublishedTraceabilityRelease | None:
        with self._lock:
            return self._current

    def version_inventory(self) -> PublicationVersionInventory:
        with self._lock:
            return PublicationVersionInventory(
                state="empty" if self._current_tail is None else "corrected_v2",
                corrected_v2_tail_count=len(self._tails),
                legacy_record_count=0,
                current=self._current_tail,
            )

    def compare_and_publish(
        self,
        *,
        epoch: int,
        sequence: int,
        release_digest: str,
        release_artifact: bytes,
        release_history_artifact: bytes,
        active_pointer_artifact: bytes,
        pointer_history_artifact: bytes,
    ) -> TraceabilityGateResult:
        return self.compare_and_publish_after(
            epoch=epoch,
            sequence=sequence,
            release_digest=release_digest,
            release_artifact=release_artifact,
            release_history_artifact=release_history_artifact,
            active_pointer_artifact=active_pointer_artifact,
            pointer_history_artifact=pointer_history_artifact,
            expected_predecessor=None,
        )

    def compare_fence_and_publish(
        self,
        *,
        watermark_store: TraceabilityReleaseWatermarkStore,
        epoch: int,
        sequence: int,
        release_digest: str,
        release_artifact: bytes,
        release_history_artifact: bytes,
        active_pointer_artifact: bytes,
        pointer_history_artifact: bytes,
    ) -> TraceabilityGateResult:
        fence = watermark_store.compare_and_advance(epoch, sequence, release_digest)
        if isinstance(fence, WatermarkRejected):
            return TraceabilityGateRejected(fence.reason)
        if isinstance(fence, WatermarkUnavailable):
            return TraceabilityGateUnavailable(fence.reason)
        if not isinstance(fence, WatermarkAdvanced):
            return TraceabilityGateUnavailable("watermark_store_indeterminate")
        return self.compare_and_publish(
            epoch=epoch,
            sequence=sequence,
            release_digest=release_digest,
            release_artifact=release_artifact,
            release_history_artifact=release_history_artifact,
            active_pointer_artifact=active_pointer_artifact,
            pointer_history_artifact=pointer_history_artifact,
        )

    def compare_and_publish_after(
        self,
        *,
        epoch: int,
        sequence: int,
        release_digest: str,
        release_artifact: bytes,
        release_history_artifact: bytes,
        active_pointer_artifact: bytes,
        pointer_history_artifact: bytes,
        expected_predecessor: PublicationTail | None,
    ) -> TraceabilityGateResult:
        candidate = PublishedTraceabilityRelease(
            epoch, sequence, release_digest, release_artifact, release_history_artifact,
            active_pointer_artifact, pointer_history_artifact,
        )
        if not _candidate_is_valid(candidate):
            return TraceabilityGateUnavailable("persistence_candidate_invalid")
        with self._lock:
            outcome = _check_transition(self._current, candidate, self._current_tail, expected_predecessor)
            if outcome is not None:
                return outcome
            tail = _tail_for(candidate, self._current_tail, selected_tail_digest=None)
            self._tails.setdefault(tail.tail_digest, (candidate, tail))
            self._current, self._current_tail = candidate, tail
            return _authorized(candidate)

    def rollback_to(
        self,
        target: PublicationTail,
        *,
        epoch: int,
        sequence: int,
        expected_predecessor: PublicationTail,
        release_artifact: bytes,
        release_history_artifact: bytes,
        active_pointer_artifact: bytes,
        pointer_history_artifact: bytes,
    ) -> TraceabilityGateResult:
        with self._lock:
            stored = self._tails.get(target.tail_digest)
            if stored is None or stored[1] != target:
                return TraceabilityGateRejected("rollback_target_not_corrected_v2_tail")
            if self._current_tail != expected_predecessor:
                return TraceabilityGateRejected("stale_pointer_predecessor_cas")
            original = stored[0]
            if (
                active_pointer_artifact == original.active_pointer_artifact
                or pointer_history_artifact == original.pointer_history_artifact
            ):
                return TraceabilityGateRejected("rollback_pointer_bundle_replayed")
            candidate = PublishedTraceabilityRelease(
                epoch, sequence, original.release_digest, release_artifact,
                release_history_artifact, active_pointer_artifact,
                pointer_history_artifact,
            )
            outcome = _check_transition(self._current, candidate, self._current_tail, expected_predecessor)
            if outcome is not None:
                return outcome
            tail = _tail_for(candidate, self._current_tail, selected_tail_digest=target.tail_digest)
            self._tails[tail.tail_digest] = (candidate, tail)
            self._current, self._current_tail = candidate, tail
            return _authorized(candidate)


class FileTraceabilityReleasePublicationStore(TraceabilityReleasePublicationStore):
    """File-backed append-only corrected-v2 tail store.

    History members are content-addressed immutable prepared records. A tiny
    current-index pointer selects one after it is durable, while the injected
    fence backend remains the sole authoritative minimum across local restore.
    """

    _FORMAT = "memorii.semantic-ingestion.corrected-v2-publication.v2"
    _INDEX_FORMAT = "memorii.semantic-ingestion.corrected-v2-publication-index.v2"
    def __init__(self, path: Path, fence_store: MonotonicFenceStore | None) -> None:
        self._path = path
        self._history_path = path.with_name(f"{path.name}.history")
        self._lock_path = path.with_name(f"{path.name}.lock")
        self._fence_store = fence_store

    def anti_rollback_backend_identity(self) -> object:
        return self._fence_store

    def publication_recovery_domain(self) -> str:
        return str(self._path.parent.resolve())

    def publication_store_id(self) -> str:
        return f"file-publication:{self._path.resolve()}"

    def compare_and_publish(
        self,
        *,
        epoch: int,
        sequence: int,
        release_digest: str,
        release_artifact: bytes,
        release_history_artifact: bytes,
        active_pointer_artifact: bytes,
        pointer_history_artifact: bytes,
    ) -> TraceabilityGateResult:
        return self.compare_fence_and_publish(
            watermark_store=self,
            epoch=epoch,
            sequence=sequence,
            release_digest=release_digest,
            release_artifact=release_artifact,
            release_history_artifact=release_history_artifact,
            active_pointer_artifact=active_pointer_artifact,
            pointer_history_artifact=pointer_history_artifact,
        )

    def provision(self, epoch: int, sequence: int, release_digest: str):
        if not _valid_coordinate(epoch, sequence) or not _valid_digest(release_digest):
            return WatermarkUnavailable("watermark_candidate_invalid")
        try:
            self._prepare()
            with locked_file(self._lock_path, exclusive=True):
                state = self._load_index_locked()
                if isinstance(state, TraceabilityGateUnavailable):
                    return WatermarkUnavailable("persistence_outcome_indeterminate")
                if state is None:
                    records = self._committed_records_locked()
                    if isinstance(records, TraceabilityGateUnavailable):
                        return WatermarkUnavailable("persistence_outcome_indeterminate")
                    if records:
                        committed = records[-1]
                        if committed[:4] != (epoch, sequence, release_digest, None):
                            return WatermarkRejected("watermark_already_provisioned")
                    else:
                        self._append_commit_locked(None, epoch, sequence, release_digest)
                    self._write_index_locked(None, epoch, sequence, release_digest)
                    return WatermarkAdvanced()
                state = self._recover_locked(state)
                if isinstance(state, TraceabilityGateUnavailable):
                    return WatermarkUnavailable("persistence_outcome_indeterminate")
                sealed = (state[1], state[2], state[3])
                if sealed != (epoch, sequence, release_digest):
                    return WatermarkRejected("watermark_already_provisioned")
                return WatermarkAdvanced()
        except (OSError, TypeError, ValueError):
            return WatermarkUnavailable("persistence_outcome_indeterminate")

    def compare_and_advance(self, epoch: int, sequence: int, release_digest: str):
        # A registered release may advance the fence only with its immutable
        # publication bundle through compare_fence_and_publish.
        return WatermarkUnavailable("integrated_publication_required")

    def compare_fence_and_publish(
        self,
        *,
        watermark_store: TraceabilityReleaseWatermarkStore,
        epoch: int,
        sequence: int,
        release_digest: str,
        release_artifact: bytes,
        release_history_artifact: bytes,
        active_pointer_artifact: bytes,
        pointer_history_artifact: bytes,
    ) -> TraceabilityGateResult:
        if watermark_store is not self:
            return TraceabilityGateUnavailable("persistence_outcome_indeterminate")
        candidate = PublishedTraceabilityRelease(
            epoch, sequence, release_digest, release_artifact,
            release_history_artifact, active_pointer_artifact, pointer_history_artifact,
        )
        if not _candidate_is_valid(candidate):
            return TraceabilityGateUnavailable("persistence_candidate_invalid")
        try:
            self._prepare()
            with locked_file(self._lock_path, exclusive=True):
                state = self._load_index_locked()
                if isinstance(state, TraceabilityGateUnavailable):
                    return state
                if state is not None:
                    state = self._recover_locked(state)
                    if isinstance(state, TraceabilityGateUnavailable):
                        return state
                current = None if state is None else state[0]
                current_record = None
                if current is not None:
                    current_record = self._load_tail_locked(current)
                    if not isinstance(current_record, tuple):
                        return TraceabilityGateUnavailable("persistence_outcome_indeterminate")
                journal_fence = self._committed_fence_locked()
                if isinstance(journal_fence, TraceabilityGateUnavailable):
                    return journal_fence
                if state is not None or journal_fence is not None:
                    index_fence = None if state is None else (state[1], state[2], state[3])
                    effective_fence = max(
                        item for item in (index_fence, journal_fence) if item is not None
                    )
                    fence_coordinate = effective_fence[:2]
                    coordinate = (epoch, sequence)
                    if coordinate < fence_coordinate:
                        return TraceabilityGateRejected("active_pointer_watermark_rewind")
                    if coordinate == fence_coordinate and release_digest != effective_fence[2]:
                        return TraceabilityGateRejected("active_pointer_watermark_substitution")
                outcome = _check_transition(
                    None if current_record is None else current_record[0], candidate,
                    None if current_record is None else current_record[1], None,
                )
                if outcome is not None:
                    return outcome
                predecessor = None if current_record is None else current_record[1]
                tail = _tail_for(candidate, predecessor, selected_tail_digest=None)
                self._commit_locked(candidate, tail, epoch, sequence, release_digest)
                return _authorized(candidate)
        except (OSError, TypeError, ValueError):
            return TraceabilityGateUnavailable("persistence_outcome_indeterminate")

    def compare_and_publish_after(
        self,
        *,
        epoch: int,
        sequence: int,
        release_digest: str,
        release_artifact: bytes,
        release_history_artifact: bytes,
        active_pointer_artifact: bytes,
        pointer_history_artifact: bytes,
        expected_predecessor: PublicationTail | None,
    ) -> TraceabilityGateResult:
        candidate = PublishedTraceabilityRelease(
            epoch, sequence, release_digest, release_artifact, release_history_artifact,
            active_pointer_artifact, pointer_history_artifact,
        )
        if not _candidate_is_valid(candidate):
            return TraceabilityGateUnavailable("persistence_candidate_invalid")
        try:
            self._prepare()
            with locked_file(self._lock_path, exclusive=True):
                current = self._load_current_locked()
                if isinstance(current, TraceabilityGateUnavailable):
                    return current
                outcome = _check_transition(
                    None if current is None else current[0], candidate,
                    None if current is None else current[1], expected_predecessor,
                )
                if outcome is not None:
                    return outcome
                predecessor = None if current is None else current[1]
                tail = _tail_for(candidate, predecessor, selected_tail_digest=None)
                self._commit_locked(candidate, tail)
                return _authorized(candidate)
        except (OSError, TypeError, ValueError):
            return TraceabilityGateUnavailable("persistence_outcome_indeterminate")

    def rollback_to(
        self,
        target: PublicationTail,
        *,
        epoch: int,
        sequence: int,
        expected_predecessor: PublicationTail,
        release_artifact: bytes,
        release_history_artifact: bytes,
        active_pointer_artifact: bytes,
        pointer_history_artifact: bytes,
    ) -> TraceabilityGateResult:
        try:
            self._prepare()
            with locked_file(self._lock_path, exclusive=True):
                current = self._load_current_locked()
                if isinstance(current, TraceabilityGateUnavailable):
                    return current
                if current is None:
                    return TraceabilityGateRejected("active_pointer_watermark_unprovisioned")
                if current[1] != expected_predecessor:
                    return TraceabilityGateRejected("stale_pointer_predecessor_cas")
                target_record = self._load_tail_locked(target.tail_digest)
                if target_record is None or isinstance(target_record, TraceabilityGateUnavailable):
                    return TraceabilityGateRejected("rollback_target_not_corrected_v2_tail")
                original, stored_target = target_record
                if stored_target != target:
                    return TraceabilityGateRejected("rollback_target_not_corrected_v2_tail")
                if (
                    active_pointer_artifact == original.active_pointer_artifact
                    or pointer_history_artifact == original.pointer_history_artifact
                ):
                    return TraceabilityGateRejected("rollback_pointer_bundle_replayed")
                candidate = PublishedTraceabilityRelease(
                    epoch, sequence, original.release_digest, release_artifact,
                    release_history_artifact, active_pointer_artifact,
                    pointer_history_artifact,
                )
                outcome = _check_transition(current[0], candidate, current[1], expected_predecessor)
                if outcome is not None:
                    return outcome
                tail = _tail_for(candidate, current[1], selected_tail_digest=target.tail_digest)
                self._commit_locked(candidate, tail)
                return _authorized(candidate)
        except (OSError, TypeError, ValueError):
            return TraceabilityGateUnavailable("persistence_outcome_indeterminate")

    def version_inventory(self) -> PublicationVersionInventory:
        try:
            if not self._path.exists() and not self._history_path.exists():
                return PublicationVersionInventory("empty", 0, 0, None)
            self._prepare()
            with locked_file(self._lock_path, exclusive=True):
                legacy_index = False
                if self._path.exists():
                    index_value = _canonical_json(self._path.read_bytes())
                    legacy_index = (
                        index_value is not None
                        and index_value.get("format") != self._INDEX_FORMAT
                    )
                current = self._load_current_locked()
                corrected_count, malformed_count = self._history_inventory_locked()
                if isinstance(current, TraceabilityGateUnavailable):
                    if legacy_index:
                        return PublicationVersionInventory(
                            "mixed" if corrected_count else "legacy",
                            corrected_count,
                            malformed_count + 1,
                            None,
                        )
                    return PublicationVersionInventory("corrupt", corrected_count, malformed_count, None)
                legacy_count = malformed_count + (1 if current is None and self._path.exists() else 0)
                if current is None:
                    state: Literal["empty", "corrected_v2", "legacy", "mixed", "corrupt"] = (
                        "legacy" if legacy_count else "empty"
                    )
                    return PublicationVersionInventory(state, corrected_count, legacy_count, None)
                state = "mixed" if legacy_count else "corrected_v2"
                return PublicationVersionInventory(state, corrected_count, legacy_count, current[1])
        except (OSError, TypeError, ValueError):
            return PublicationVersionInventory("corrupt", 0, 0, None)

    def _prepare(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._history_path.mkdir(parents=True, exist_ok=True)

    def _history_file(self, tail_digest: str) -> Path:
        return self._history_path / f"{tail_digest}.json"

    def _load_current_locked(
        self,
    ) -> tuple[PublishedTraceabilityRelease, PublicationTail] | TraceabilityGateUnavailable | None:
        state = self._load_index_locked()
        if isinstance(state, TraceabilityGateUnavailable) or state is None:
            return state
        state = self._recover_locked(state)
        if isinstance(state, TraceabilityGateUnavailable):
            return state
        digest = state[0]
        if digest is None:
            return None
        record = self._load_tail_locked(digest)
        return record if record is not None else TraceabilityGateUnavailable("persistence_outcome_indeterminate")

    def _load_index_locked(
        self,
    ) -> tuple[str | None, int, int, str] | TraceabilityGateUnavailable | None:
        if not self._path.exists():
            return None
        value = _canonical_json(self._path.read_bytes())
        required = {"format", "tail_digest", "fence_epoch", "fence_sequence", "fence_release_digest"}
        if value is None or set(value) != required or value.get("format") != self._INDEX_FORMAT:
            return TraceabilityGateUnavailable("persistence_outcome_indeterminate")
        tail = value["tail_digest"]
        epoch = value["fence_epoch"]
        sequence = value["fence_sequence"]
        release_digest = value["fence_release_digest"]
        if (
            tail is not None and not _valid_digest(tail)
            or not _valid_coordinate(epoch, sequence)
            or not _valid_digest(release_digest)
        ):
            return TraceabilityGateUnavailable("persistence_outcome_indeterminate")
        assert tail is None or isinstance(tail, str)
        assert isinstance(epoch, int) and isinstance(sequence, int) and isinstance(release_digest, str)
        return tail, epoch, sequence, release_digest

    def _load_tail_locked(
        self, tail_digest: str
    ) -> tuple[PublishedTraceabilityRelease, PublicationTail] | TraceabilityGateUnavailable | None:
        if not _valid_digest(tail_digest):
            return TraceabilityGateUnavailable("persistence_outcome_indeterminate")
        path = self._history_file(tail_digest)
        if not path.exists():
            return None
        raw = path.read_bytes()
        if _digest(raw) != tail_digest:
            return TraceabilityGateUnavailable("persistence_outcome_indeterminate")
        value = _canonical_json(raw)
        if value is None:
            return TraceabilityGateUnavailable("persistence_outcome_indeterminate")
        decoded = _decode_tail(value, tail_digest)
        return decoded if decoded is not None else TraceabilityGateUnavailable("persistence_outcome_indeterminate")

    def _commit_locked(
        self, candidate: PublishedTraceabilityRelease, tail: PublicationTail,
        fence_epoch: int | None = None, fence_sequence: int | None = None,
        fence_release_digest: str | None = None,
    ) -> None:
        tail_bytes = _tail_bytes(candidate, tail)
        history_file = self._history_file(tail.tail_digest)
        if history_file.exists():
            if history_file.read_bytes() != tail_bytes:
                raise ValueError("content-addressed-tail-collision")
        else:
            _atomic_replace(history_file, tail_bytes)
        self._write_index_locked(
            tail.tail_digest,
            candidate.epoch if fence_epoch is None else fence_epoch,
            candidate.sequence if fence_sequence is None else fence_sequence,
            candidate.release_digest if fence_release_digest is None else fence_release_digest,
        )
        self._append_commit_locked(
            tail.tail_digest,
            candidate.epoch if fence_epoch is None else fence_epoch,
            candidate.sequence if fence_sequence is None else fence_sequence,
            candidate.release_digest if fence_release_digest is None else fence_release_digest,
        )

    def _write_index_locked(
        self, tail_digest: str | None, epoch: int, sequence: int, release_digest: str
    ) -> None:
        _atomic_replace(
            self._path,
            canonical_document({
                "format": self._INDEX_FORMAT,
                "tail_digest": tail_digest,
                "fence_epoch": epoch,
                "fence_sequence": sequence,
                "fence_release_digest": release_digest,
            }),
        )

    def _history_inventory_locked(self) -> tuple[int, int]:
        commits = self._committed_records_locked()
        if isinstance(commits, TraceabilityGateUnavailable):
            return 0, 1
        selected = {record[3] for record in commits if record[3] is not None}
        corrected = 0
        malformed = 0
        for path in self._history_path.iterdir():
            if not path.is_file() or not _DIGEST.fullmatch(path.stem):
                malformed += 1
                continue
            record = self._load_tail_locked(path.stem)
            if isinstance(record, tuple):
                # A durable immutable tail is PREPARED until selected by the
                # external commit fence.  Inventory must not promote debris
                # left by an interrupted preparation.
                corrected += int(path.stem in selected)
            else:
                malformed += 1
        return corrected, malformed

    def _append_commit_locked(
        self, tail_digest: str | None, epoch: int, sequence: int, release_digest: str
    ) -> None:
        if self._fence_store is None:
            raise ValueError("external-fence-missing")
        outcome = self._fence_store.advance(epoch, sequence, release_digest, tail_digest)
        if not isinstance(outcome, WatermarkAdvanced):
            raise ValueError("external-fence-rejected-or-unavailable")

    def _committed_fence_locked(
        self,
    ) -> tuple[int, int, str, str | None, str] | TraceabilityGateUnavailable | None:
        records = self._committed_records_locked()
        if isinstance(records, TraceabilityGateUnavailable):
            return records
        return None if not records else records[-1]

    def _committed_records_locked(
        self,
    ) -> list[tuple[int, int, str, str | None, str]] | TraceabilityGateUnavailable:
        if self._fence_store is None:
            return TraceabilityGateUnavailable("persistence_outcome_indeterminate")
        return self._fence_store.records()

    def _recover_locked(
        self, state: tuple[str | None, int, int, str]
    ) -> tuple[str | None, int, int, str] | TraceabilityGateUnavailable:
        committed = self._committed_fence_locked()
        if isinstance(committed, TraceabilityGateUnavailable):
            return committed
        if committed is None:
            return TraceabilityGateUnavailable("persistence_outcome_indeterminate")
        index_coordinate = (state[1], state[2])
        committed_coordinate = committed[:2]
        if index_coordinate > committed_coordinate:
            # Prepared tail and index are complete; deterministically finish.
            if not self._index_tail_matches_locked(state):
                return TraceabilityGateUnavailable("persistence_outcome_indeterminate")
            self._append_commit_locked(state[0], state[1], state[2], state[3])
            return state
        if index_coordinate < committed_coordinate or (
            state[3], state[0]
        ) != (committed[2], committed[3]):
            if committed[3] is not None and not isinstance(
                self._load_tail_locked(committed[3]), tuple
            ):
                return TraceabilityGateUnavailable("persistence_outcome_indeterminate")
            self._write_index_locked(committed[3], committed[0], committed[1], committed[2])
            return committed[3], committed[0], committed[1], committed[2]
        return state

    def _index_tail_matches_locked(self, state: tuple[str | None, int, int, str]) -> bool:
        if state[0] is None:
            return True
        record = self._load_tail_locked(state[0])
        return isinstance(record, tuple) and (
            record[0].epoch, record[0].sequence, record[0].release_digest
        ) == (state[1], state[2], state[3])


def _candidate_is_valid(candidate: PublishedTraceabilityRelease) -> bool:
    return (
        _valid_coordinate(candidate.epoch, candidate.sequence)
        and _valid_digest(candidate.release_digest)
        and all(
            isinstance(value, bytes)
            for value in (
                candidate.release_artifact, candidate.release_history_artifact,
                candidate.active_pointer_artifact, candidate.pointer_history_artifact,
            )
        )
    )


def _tail_for(
    candidate: PublishedTraceabilityRelease,
    predecessor: PublicationTail | None,
    *,
    selected_tail_digest: str | None,
) -> PublicationTail:
    # Digesting canonical immutable bytes binds the selected authenticated
    # pointer-history artifact to the exact predecessor transaction.
    body = _tail_body(candidate, predecessor, selected_tail_digest)
    raw = canonical_document(body)
    return PublicationTail(
        candidate.epoch, candidate.sequence, candidate.release_digest,
        _digest(candidate.pointer_history_artifact), _digest(raw),
        None if predecessor is None else predecessor.tail_digest, selected_tail_digest,
    )


def _tail_body(
    candidate: PublishedTraceabilityRelease,
    predecessor: PublicationTail | None,
    selected_tail_digest: str | None,
) -> dict[str, object]:
    return {
        "format": FileTraceabilityReleasePublicationStore._FORMAT,
        "epoch": candidate.epoch,
        "sequence": candidate.sequence,
        "release_digest": candidate.release_digest,
        "release_artifact": base64.b64encode(candidate.release_artifact).decode("ascii"),
        "release_history_artifact": base64.b64encode(candidate.release_history_artifact).decode("ascii"),
        "active_pointer_artifact": base64.b64encode(candidate.active_pointer_artifact).decode("ascii"),
        "pointer_history_artifact": base64.b64encode(candidate.pointer_history_artifact).decode("ascii"),
        "pointer_history_digest": _digest(candidate.pointer_history_artifact),
        "predecessor_tail_digest": None if predecessor is None else predecessor.tail_digest,
        "selected_tail_digest": selected_tail_digest,
    }


def _tail_bytes(candidate: PublishedTraceabilityRelease, tail: PublicationTail) -> bytes:
    predecessor = None
    if tail.predecessor_tail_digest is not None:
        predecessor = PublicationTail(0, 0, "", "", tail.predecessor_tail_digest)
    return canonical_document(_tail_body(candidate, predecessor, tail.selected_tail_digest))


def _decode_tail(
    value: dict[str, object], expected_digest: str
) -> tuple[PublishedTraceabilityRelease, PublicationTail] | None:
    required = {
        "format", "epoch", "sequence", "release_digest", "release_artifact",
        "release_history_artifact", "active_pointer_artifact", "pointer_history_artifact",
        "pointer_history_digest", "predecessor_tail_digest", "selected_tail_digest",
    }
    if set(value) != required or value.get("format") != FileTraceabilityReleasePublicationStore._FORMAT:
        return None
    epoch = value["epoch"]
    sequence = value["sequence"]
    release_digest = value["release_digest"]
    pointer_history_digest = value["pointer_history_digest"]
    predecessor_tail_digest = value["predecessor_tail_digest"]
    selected_tail_digest = value["selected_tail_digest"]
    if (
        not isinstance(epoch, int)
        or not isinstance(sequence, int)
        or not isinstance(release_digest, str)
        or not isinstance(pointer_history_digest, str)
        or not _valid_coordinate(epoch, sequence)
        or not _valid_digest(release_digest)
        or not _valid_digest(pointer_history_digest)
    ):
        return None
    if predecessor_tail_digest is not None and (
        not isinstance(predecessor_tail_digest, str) or not _valid_digest(predecessor_tail_digest)
    ):
        return None
    if selected_tail_digest is not None and (
        not isinstance(selected_tail_digest, str) or not _valid_digest(selected_tail_digest)
    ):
        return None
    try:
        encoded_artifacts: list[str] = []
        for name in (
            "release_artifact", "release_history_artifact", "active_pointer_artifact",
            "pointer_history_artifact",
        ):
            artifact = value[name]
            if not isinstance(artifact, str):
                return None
            encoded_artifacts.append(artifact)
        artifacts = [base64.b64decode(artifact.encode("ascii"), validate=True) for artifact in encoded_artifacts]
    except (AttributeError, ValueError):
        return None
    candidate = PublishedTraceabilityRelease(epoch, sequence, release_digest, *artifacts)
    if not _candidate_is_valid(candidate) or pointer_history_digest != _digest(candidate.pointer_history_artifact):
        return None
    tail = PublicationTail(
        candidate.epoch, candidate.sequence, candidate.release_digest,
        pointer_history_digest, expected_digest, predecessor_tail_digest, selected_tail_digest,
    )
    return candidate, tail


def _check_transition(
    current: PublishedTraceabilityRelease | None,
    candidate: PublishedTraceabilityRelease,
    current_tail: PublicationTail | None,
    expected_predecessor: PublicationTail | None,
) -> TraceabilityGateResult | None:
    if expected_predecessor is not None and current_tail != expected_predecessor:
        return TraceabilityGateRejected("stale_pointer_predecessor_cas")
    if current is None:
        if (candidate.epoch, candidate.sequence) != (1, 1):
            return TraceabilityGateRejected("active_pointer_watermark_unprovisioned")
        return None
    coordinate = (candidate.epoch, candidate.sequence)
    prior_coordinate = (current.epoch, current.sequence)
    if coordinate < prior_coordinate:
        return TraceabilityGateRejected("active_pointer_watermark_rewind")
    if coordinate == prior_coordinate:
        if candidate == current:
            return _authorized(candidate)
        return TraceabilityGateRejected("stale_pointer_cas")
    if candidate.epoch != current.epoch or candidate.sequence != current.sequence + 1:
        return TraceabilityGateRejected("active_pointer_monotonicity")
    return None


def _authorized(candidate: PublishedTraceabilityRelease) -> TraceabilityGateAuthorized:
    return TraceabilityGateAuthorized("published-release", candidate.release_digest)


def _canonical_json(raw: bytes) -> dict[str, object] | None:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) and canonical_document(value) == raw else None


def _atomic_replace(path: Path, payload: bytes) -> None:
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
