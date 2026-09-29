"""Fail-closed factory for managed persistent partitions.

Composes the verified installation control authority with the shared SQLite
partition and its memory-plane view. Managed startup never guesses: an
uninitialized root refuses with an explicit reason, a recognized-but-
unmigrated legacy layout reports migration-required (never creating a fresh
database beside old memory, whatever the spelling), and mixed or unknown
layouts are unsupported configurations. No JSONL or in-memory fallback
exists on managed roots.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.sqlite_store import SqliteMemoryPlaneStore
from memorii.core.memory_plane.store import (
    CheckpointSignatureAuthority,
    GovernedWritePolicy,
    MemoryPlanePrecondition,
    MemoryPlaneTimedWriteSnapshot,
    MemoryPlaneWriteAuthorization,
)
from memorii.core.storage_administration.service import (
    InstallationIntegrityError,
    InstallationQuarantinedError,
    StorageAdministrationError,
    StorageAdministrationService,
)
from memorii.domain.enums import CommitStatus, MemoryDomain

_CONTROL_DATABASE = Path("control") / "control.sqlite3"
_PARTITION_DATABASE = Path("partition") / "partition.sqlite3"

# Closed legacy layout inventory: exactly the directory conventions current
# composition roots produce. The hyphen and underscore spellings are distinct
# layouts; neither is assumed from the other.
_LEGACY_LAYOUTS = (
    ("hermes-host-memory-plane", "memory-plane"),
    ("filesystem-bundle-memory-plane", "memory_plane"),
)
_LEGACY_PLANE_MARKER = "memory_records.jsonl"


class ManagedPartitionError(RuntimeError):
    """Managed partition startup refused; the detail carries the reason."""

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


class PublishedMemoryPlaneStore:
    """Repository-scoped memory-plane view whose every write is published.

    Domain owners receive this view on managed roots: conditional and
    unconditional writes commit through the signed publication protocol
    (intent, atomic data commit, finalize), while reads and authority claims
    delegate to the shared partition store. Durable mode admits no
    independent append path that could leave rows outside the signed
    materialization manifest.
    """

    def __init__(
        self,
        administration: StorageAdministrationService,
        inner: SqliteMemoryPlaneStore,
    ) -> None:
        self._administration = administration
        self._inner = inner

    @property
    def durable(self) -> bool:
        return True

    def load_or_create_protected_secret(self, *, purpose: str, length: int) -> bytes:
        return self._inner.load_or_create_protected_secret(purpose=purpose, length=length)

    def _claim_semantic_checkpoint_signature_authority(
        self, *, owner: object
    ) -> CheckpointSignatureAuthority:
        return self._inner._claim_semantic_checkpoint_signature_authority(owner=owner)

    def install_governed_write_policy(self, policy: GovernedWritePolicy) -> None:
        self._inner.install_governed_write_policy(policy)

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
        return self._administration.publish_memory_plane_batch(
            records,
            store=self._inner,
            expected_revision=None,
            authorization=authorization,
        ).data_revision

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
        return self._administration.publish_memory_plane_batch(
            records,
            store=self._inner,
            expected_revision=expected_revision,
            expected_write_revision=expected_write_revision,
            preconditions=preconditions,
            authorization=authorization,
            transaction_precondition=transaction_precondition,
        ).data_revision

    def revision(self) -> int:
        return self._inner.revision()

    def read_snapshot(self) -> tuple[int, tuple[CanonicalMemoryRecord, ...]]:
        return self._inner.read_snapshot()

    def read_snapshot_linearized(
        self,
        callback: Callable[[int, tuple[CanonicalMemoryRecord, ...]], object],
    ) -> object:
        return self._inner.read_snapshot_linearized(callback)

    def read_write_snapshot(self) -> tuple[int, tuple[CanonicalMemoryRecord, ...]]:
        return self._inner.read_write_snapshot()

    def read_timed_write_snapshot(
        self, *, now: Callable[[], datetime]
    ) -> MemoryPlaneTimedWriteSnapshot:
        return self._inner.read_timed_write_snapshot(now=now)

    def get_record(self, memory_id: str) -> CanonicalMemoryRecord | None:
        return self._inner.get_record(memory_id)

    def list_records(
        self,
        *,
        status: CommitStatus | None = None,
        domains: list[MemoryDomain] | None = None,
        source_kind: str | None = None,
    ) -> list[CanonicalMemoryRecord]:
        return self._inner.list_records(
            status=status,
            domains=domains,
            source_kind=source_kind,
        )


def detect_legacy_memory_plane_layouts(root: str | Path) -> tuple[str, ...]:
    """Return the recognized legacy layouts present under ``root``."""
    base = Path(root)
    layouts: list[str] = []
    for layout_name, directory in _LEGACY_LAYOUTS:
        plane_directory = base / directory
        if (plane_directory / _LEGACY_PLANE_MARKER).exists():
            layouts.append(layout_name)
    if (base / _LEGACY_PLANE_MARKER).exists():
        layouts.append("direct-memory-plane-directory")
    return tuple(layouts)


def open_managed_partition(
    installation_root: str | Path,
) -> tuple[StorageAdministrationService, MemoryPlaneService]:
    """Open the verified managed partition or fail closed with a reason.

    Returns the administration owner (for publication and verification) and
    the memory-plane service over the same physical partition. This function
    never initializes, migrates or fabricates authority.
    """
    root = Path(installation_root)
    if not (root / _CONTROL_DATABASE).exists():
        layouts = detect_legacy_memory_plane_layouts(root)
        if len(layouts) > 1:
            raise ManagedPartitionError(
                "unsupported_configuration",
                "multiple legacy memory-plane layouts present: " + ", ".join(layouts),
            )
        if layouts:
            raise ManagedPartitionError(
                "migration_required",
                f"legacy memory-plane layout present: {layouts[0]}",
            )
        if (root / _PARTITION_DATABASE).exists():
            raise ManagedPartitionError(
                "integrity",
                "partition data exists without control authority",
            )
        raise ManagedPartitionError(
            "uninitialized",
            "no initialized control authority; run the owner-authorized "
            "installation initializer first",
        )
    administration = StorageAdministrationService(root)
    try:
        administration.acquire_verified_snapshot()
    except (StorageAdministrationError, InstallationIntegrityError, InstallationQuarantinedError) as exc:
        administration.close()
        raise ManagedPartitionError("integrity", str(exc)) from exc
    partition = administration.partition()
    inner = SqliteMemoryPlaneStore(partition)
    published = PublishedMemoryPlaneStore(administration, inner)
    return administration, MemoryPlaneService(record_store=published)


__all__ = [
    "ManagedPartitionError",
    "PublishedMemoryPlaneStore",
    "detect_legacy_memory_plane_layouts",
    "open_managed_partition",
]
