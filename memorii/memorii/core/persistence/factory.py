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
    JsonlMemoryPlaneStore,
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


def legacy_layout_directory(layout: str) -> Path:
    """Directory name of a recognized legacy layout (``.`` for direct roots)."""
    if layout == "direct-memory-plane-directory":
        return Path(".")
    for layout_name, directory in _LEGACY_LAYOUTS:
        if layout_name == layout:
            return Path(directory)
    raise ManagedPartitionError(
        "unsupported_configuration", f"unknown legacy layout: {layout}"
    )


class PersistentMemorySelection:
    """Selected persistent memory plane with its owning administration."""

    def __init__(
        self,
        administration: StorageAdministrationService | None,
        memory_plane: MemoryPlaneService,
    ) -> None:
        self.administration = administration
        self.memory_plane = memory_plane

    @property
    def managed(self) -> bool:
        return self.administration is not None


def select_persistent_memory_plane(
    storage_root: str | Path,
    *,
    allow_legacy_bootstrap: bool = False,
) -> PersistentMemorySelection:
    """Select the persistent memory plane for a storage root.

    Managed roots (an initialized control authority) serve the verified
    published partition. Legacy roots (a recognized pre-cutover JSONL plane
    and no control authority) serve their legacy plane until governed
    migration. Roots holding both, an orphan partition, or neither are
    refused — a persistent path never guesses and never creates an ephemeral
    store. ``allow_legacy_bootstrap`` preserves the pre-cutover behavior of
    composition roots that historically created a fresh legacy plane on an
    empty root; managed selection is unaffected by it.
    """
    root = Path(storage_root)
    managed = (root / _CONTROL_DATABASE).exists()
    layouts = detect_legacy_memory_plane_layouts(root)
    # A completed migration owns the root and preserves the legacy input
    # untouched; serving continues from the verified partition. Control
    # without a finalized migrated generation alongside a legacy plane is
    # ambiguous and refused until adoption completes.
    if managed and layouts and not _managed_generation_is_finalized(root):
        raise ManagedPartitionError(
            "unsupported_configuration",
            "managed control authority and legacy memory-plane layouts coexist:"
            + ", ".join(layouts),
        )
    if managed:
        administration, memory_plane = open_managed_partition(root)
        return PersistentMemorySelection(administration, memory_plane)
    if layouts:
        if len(layouts) > 1:
            raise ManagedPartitionError(
                "unsupported_configuration",
                "multiple legacy memory-plane layouts present: " + ", ".join(layouts),
            )
        plane_root = root / legacy_layout_directory(layouts[0])
        return PersistentMemorySelection(
            None,
            MemoryPlaneService(record_store=JsonlMemoryPlaneStore(plane_root)),
        )
    if (root / _PARTITION_DATABASE).exists():
        raise ManagedPartitionError(
            "integrity",
            "partition data exists without control authority",
        )
    if allow_legacy_bootstrap:
        return PersistentMemorySelection(
            None,
            MemoryPlaneService(record_store=JsonlMemoryPlaneStore(root / "memory-plane")),
        )
    raise ManagedPartitionError(
        "uninitialized",
        "no initialized control authority or legacy memory plane;"
        " refusing to create an ephemeral store",
    )


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
    from memorii.core.storage_administration.revoked_identity_view import (
        view_from_control_root,
    )

    revoked_view = view_from_control_root(root / "control")
    return administration, MemoryPlaneService(
        record_store=published, revoked_view=revoked_view
    )


__all__ = [
    "ManagedPartitionError",
    "PersistentMemorySelection",
    "PublishedMemoryPlaneStore",
    "detect_legacy_memory_plane_layouts",
    "legacy_layout_directory",
    "open_managed_partition",
    "select_persistent_memory_plane",
]

def _managed_generation_is_finalized(root: Path) -> bool:
    """True when a completed migration adopted the legacy plane present.

    The finalized generation alone is not enough: the adoption fingerprint in
    control state must match one of the preserved legacy inputs, so a plane
    dropped next to an unrelated installation still refuses.
    """
    import hashlib

    from memorii.core.storage_administration.service import (
        StorageAdministrationService,
    )

    service = StorageAdministrationService(root)
    try:
        state = service._control.read_control_state()
        if state is None or state.quarantined_reason is not None:
            return False
        finalized = service._control.read_publication_state(
            f"{state.installation_id}:default-partition"
        )
        if finalized is None or state.adopted_legacy_records_digest is None:
            return False
        for _layout_name, directory in _LEGACY_LAYOUTS:
            records = root / directory / _LEGACY_PLANE_MARKER
            if records.is_file() and (
                hashlib.sha256(records.read_bytes()).hexdigest()
                == state.adopted_legacy_records_digest
            ):
                return True
        return False
    finally:
        service.close()
