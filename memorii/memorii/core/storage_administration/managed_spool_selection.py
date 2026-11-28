"""Signed storage-owner selection of a physically separate managed spool."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from uuid import NAMESPACE_OID, uuid5

from memorii.core.harness_state.consumer import ConsumerDeliveryError, ManagedRuntimeSpool
from memorii.core.memory_plane.file_lock import locked_file
from memorii.core.persistence.contracts import InstalledManagedSpoolBinding
from memorii.core.storage_administration.operator import OwnerCapability, require_owner_capability
from memorii.core.storage_administration.service import StorageAdministrationService
from memorii.stores.sqlite.control import ControlJournalChainError, ControlStateError


def _directory(administration: StorageAdministrationService) -> Path:
    return administration.installation_root / "spool" / "managed"


@contextmanager
def managed_spool_lease(administration: StorageAdministrationService, *, selecting: bool = False) -> Iterator[None]:
    """Keep a selected store stable for a running managed service or consumer."""
    path = administration.installation_root / "control" / "managed-spool-selection.lock"
    with ExitStack() as stack:
        try:
            stack.enter_context(locked_file(path, exclusive=selecting, private=True, blocking=False))
        except BlockingIOError as exc:
            raise ConsumerDeliveryError("conflict: managed spool selection or use is already in progress") from exc
        yield


def _binding(administration: StorageAdministrationService) -> InstalledManagedSpoolBinding | None:
    try:
        binding = administration._control.read_managed_spool_binding()
    except (ControlJournalChainError, ControlStateError) as exc:
        raise ConsumerDeliveryError("integrity_error: managed spool cannot validate registered authority") from exc
    if binding is not None and (
        binding.installation_id != administration._control_state().installation_id
        or binding.repository_id != administration._repository_id()
    ):
        raise ConsumerDeliveryError("integrity_error: managed spool belongs to different installation authority")
    return binding


def open_managed_spool(
    administration: StorageAdministrationService, *, directory: Path | None = None,
) -> ManagedRuntimeSpool:
    """Use an authenticated registration or the unchanged pre-registration spool."""
    binding = _binding(administration)
    expected = _directory(administration)
    if binding is None:
        return ManagedRuntimeSpool(expected if directory is None else directory)
    if directory is not None and directory.absolute() != expected.absolute():
        raise ConsumerDeliveryError("denied: registered managed spool cannot use an alternate directory")
    return ManagedRuntimeSpool(expected, expected_store_id=binding.store_id)


def register_managed_spool(
    administration: StorageAdministrationService, *, capability: OwnerCapability,
    store_id: str | None = None, initializing: bool = False,
) -> InstalledManagedSpoolBinding:
    """Stage and activate an exact owner-selected spool after legacy readers stop."""
    require_owner_capability(administration, capability)
    with managed_spool_lease(administration, selecting=True):
        return _register_managed_spool(administration, capability, store_id=store_id, initializing=initializing)


def _register_managed_spool(
    administration: StorageAdministrationService, capability: OwnerCapability, *,
    store_id: str | None, initializing: bool,
) -> InstalledManagedSpoolBinding:
    with administration.verified_operation_context() as (state, publication):
        require_owner_capability(administration, capability)
        binding = InstalledManagedSpoolBinding(
            installation_id=publication.installation_id,
            repository_id=publication.repository_id,
            store_id=store_id if store_id is not None else uuid5(NAMESPACE_OID, publication.repository_id).hex,
        )
        prior = _binding(administration)
        if prior is not None:
            if prior != binding:
                raise ConsumerDeliveryError("conflict: an exact managed spool is already registered")
            open_managed_spool(administration)
            return prior
        initial_installation = initializing and state.mode == "active" and publication.vector.partition_ordinal == 0
        if state.mode != "read_only" and not initial_installation:
            raise ConsumerDeliveryError("conflict: managed spool staging requires a stopped read-only installation")
        expected_mode = state.mode
        expected_revision = state.control_revision
        expected_publication = publication.payload_digest()
    directory = _directory(administration)
    ManagedRuntimeSpool.stage_sqlite(directory, store_id=binding.store_id)
    with administration.verified_operation_context() as (state, publication):
        require_owner_capability(administration, capability)
        prior = _binding(administration)
        if prior == binding:
            open_managed_spool(administration)
            return binding
        if (
            prior is not None or state.mode != expected_mode or state.control_revision != expected_revision
            or publication.payload_digest() != expected_publication
        ):
            raise ConsumerDeliveryError("conflict: installation authority changed before managed spool selection")
        with ManagedRuntimeSpool.verified_sqlite_stage(directory, store_id=binding.store_id):
            administration._control.register_managed_spool(
                binding,
                administration._journal_entry(operation="managed_spool_registered", after_digest=binding.digest()),
                initializing=initializing,
            )
    return binding
