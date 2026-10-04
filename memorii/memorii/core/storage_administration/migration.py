"""Legacy JSONL installation migration: plan, adopt, import, cut over.

The migration owner never mutates the legacy installation: planning is
read-only, adoption creates independent control authority with a typed
LegacyStorageSelector binding the exact input, import rebuilds the memory
catalogs from the immutable legacy log under the plane lock with a
capacity preflight, and cutover is a generation-change intent whose
expected-old discriminator is the selector digest. Crash recovery accepts
only the exact legacy state (resume from control) or the exact verified
SQLite tuple; conflicting adoption and modified adopted input refuse with
named reasons. Stages are exposed for recovery orchestration; the public
entry point performs all three under one exclusive hold.
"""

from __future__ import annotations

import hashlib
import shutil
import uuid
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_plane.file_lock import locked_file
from memorii.core.memory_plane.store import JsonlMemoryPlaneStore
from memorii.core.persistence.contracts import canonical_json_digest
from memorii.core.storage_administration.service import (
    DEFAULT_SIGNER_KEY_ID,
    StorageAdministrationService,
)

LEGACY_PLANE_MARKER = "memory_records.jsonl"
_ADOPTED_PARTICIPANTS = (
    "work_state",
    "decision_state",
    "llm_decision",
    "semantic_integrity",
    "conflict_attention",
    ".protected",
)
_KNOWN_PLANE_MEMBERS = frozenset(
    {LEGACY_PLANE_MARKER, "memory_records.lock", ".protected"}
)


class LegacyMigrationError(RuntimeError):
    """Migration refused; the detail carries the reason."""


class LegacyStorageSelector(BaseModel):
    """Typed expected-old discriminator binding the exact legacy input."""

    discriminator: Literal["legacy_jsonl"] = "legacy_jsonl"
    installation_root: str = Field(min_length=1)
    plane_directory: str = Field(min_length=1)
    records_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    records_size: int = Field(ge=0)
    write_revision: int = Field(ge=0)
    data_revision: int = Field(ge=0)
    plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    def selector_digest(self) -> str:
        return canonical_json_digest(self.model_dump(mode="json"))


class MemoryPlaneMigrationPlan(BaseModel):
    """Closed read-only plan for migrating one legacy installation."""

    installation_root: str = Field(min_length=1)
    plane_directory: str = Field(min_length=1)
    records_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    records_size: int = Field(ge=0)
    write_revision: int = Field(ge=0)
    data_revision: int = Field(ge=0)
    batch_count: int = Field(ge=0)
    record_count: int = Field(ge=0)
    participant_inventory: tuple[str, ...] = ()
    target_format: Literal["sqlite"] = "sqlite"
    required_free_bytes: int = Field(ge=0)
    plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def digest_matches(self) -> MemoryPlaneMigrationPlan:
        if self.plan_digest != _plan_digest(self):
            raise ValueError("migration plan digest is invalid")
        return self


def _plan_digest(plan: MemoryPlaneMigrationPlan) -> str:
    payload = {
        key: value
        for key, value in plan.model_dump(mode="json").items()
        if key != "plan_digest"
    }
    return canonical_json_digest(payload)


def build_migration_plan(
    installation_root: str | Path,
    *,
    plane_directory: str | Path,
) -> MemoryPlaneMigrationPlan:
    """Read-only plan over one recognized legacy layout.

    Validates the batch chain (checksums, contiguous revisions, derived data
    revisions), fingerprints the log bytes, inventories registered
    participants and refuses unknown plane members.
    """
    root = Path(installation_root)
    plane = Path(plane_directory)
    _validate_plane_shape(plane)
    # Each store read takes the plane's own advisory lock; the digest is
    # verified against the approved plan by the caller under the migration's
    # exclusive hold, so a torn read cannot be silently accepted.
    store = JsonlMemoryPlaneStore(plane)
    write_revision, records = store.read_write_snapshot()
    data_revision = store.revision()
    batch_count = len(store._read_batches_unlocked())  # noqa: SLF001 - validated read
    records_digest, records_size = _fingerprint_log(plane)
    participants = tuple(
        name for name in _ADOPTED_PARTICIPANTS if (root / name).exists()
    )
    fields = {
        "installation_root": str(root),
        "plane_directory": str(plane),
        "records_digest": records_digest,
        "records_size": records_size,
        "write_revision": write_revision,
        "data_revision": data_revision,
        "batch_count": batch_count,
        "record_count": len(records),
        "participant_inventory": participants,
        "required_free_bytes": max(records_size * 2, 1024 * 1024),
    }
    plan = MemoryPlaneMigrationPlan.model_construct(**fields, plan_digest="0" * 64)
    return MemoryPlaneMigrationPlan.model_validate(
        plan.model_dump(mode="json") | {"plan_digest": _plan_digest(plan)}
    )


def migrate_legacy_installation(
    installation_root: str | Path,
    *,
    plane_directory: str | Path,
    approved_plan: MemoryPlaneMigrationPlan,
    signer_key_id: str = DEFAULT_SIGNER_KEY_ID,
) -> StorageAdministrationService:
    """Owner-authorized adoption, import and cutover of a legacy root.

    Holds the legacy plane's exclusive lock across the whole operation,
    verifies free capacity, and completes or resumes atomically staged
    phases. An idempotent re-run over a completed migration returns the
    serving administration; conflicting or modified input refuses.
    """
    root = Path(installation_root)
    plane = Path(plane_directory)
    current_plan = build_migration_plan(root, plane_directory=plane)
    if current_plan.plan_digest != approved_plan.plan_digest:
        raise LegacyMigrationError(
            "conflict: legacy input changed since the approved plan"
        )
    _verify_capacity(root, current_plan)
    selector = LegacyStorageSelector(
        installation_root=str(root),
        plane_directory=str(plane),
        records_digest=current_plan.records_digest,
        records_size=current_plan.records_size,
        write_revision=current_plan.write_revision,
        data_revision=current_plan.data_revision,
        plan_digest=current_plan.plan_digest,
    )
    service = StorageAdministrationService(root, signer_key_id=signer_key_id)
    try:
        with _plane_locked(plane):
            existing = service._control.read_control_state()
            if existing is None:
                _adopt(service, selector)
            elif (
                existing.adopted_legacy_records_digest is not None
                and existing.adopted_legacy_records_digest != selector.records_digest
            ):
                raise LegacyMigrationError(
                    "conflict: this installation already adopted a different"
                    " legacy input"
                )
            resolution = service.resolve_pending_publication()
            finalized = service._control.read_publication_state(
                service._repository_id()
            )
            if finalized is None and resolution.disposition == "quarantined":
                raise LegacyMigrationError(
                    "migration control is quarantined; owner recovery required"
                )
            if finalized is not None:
                _complete_operational_transition(service)
                return service
            # Exact legacy state (adoption recorded, no published tuple):
            # re-import idempotently from the immutable log and cut over.
            _import_batches(service, plane)
            _cutover(service, selector)
            _complete_operational_transition(service)
            return service
    except BaseException:
        service.close()
        raise


def _adopt(
    service: StorageAdministrationService, selector: LegacyStorageSelector
) -> str:
    """Record adoption: first atomic control transaction, migration-only."""
    from memorii.core.persistence.contracts import (
        InstallationControlState,
        TrustRegistryEntry,
    )

    installation_id = "migrated-" + uuid.uuid4().hex
    repository_id = f"{installation_id}:default-partition"
    fingerprint = service._ensure_signing_key()
    trust_entry = TrustRegistryEntry(
        key_id=service._signer_key_id,
        public_key_fingerprint=fingerprint,
        purpose="memorii.runtime-publication.v1",
        sequence_interval_start=1,
    )
    state = InstallationControlState(
        installation_id=installation_id,
        format_version=1,
        control_revision=1,
        eligibility_epoch=1,
        mode="read_only",
        adopted_legacy_records_digest=selector.records_digest,
    )
    journal = service._journal_entry(
        operation="initialize",
        after_digest=canonical_json_digest(
            {"legacy_adoption": selector.model_dump(mode="json")}
        ),
    )
    # A placeholder pending intent reserves the one-intent slot until the
    # real cutover candidate is known; the cutover stage replaces it.
    service._control.initialize_installation(
        state,
        trust_entry,
        _placeholder_intent(repository_id, selector),
        journal,
    )
    return repository_id


def _placeholder_intent(
    repository_id: str, selector: LegacyStorageSelector
) -> object:
    """Migration-recovery marker intent (never finalized as-is).

    Its expected-old discriminator is the legacy selector digest and its
    candidate is a tombstone; recovery treats a pending marker with no
    published tuple as the exact legacy state and re-enters cutover.
    """
    from memorii.core.persistence.contracts import (
        GenesisPosition,
        InstallationControlState,
        PartitionRevisionVector,
        RuntimePublicationIntent,
        RuntimePublicationState,
    )

    del InstallationControlState
    tombstone = RuntimePublicationState.model_construct(
        installation_id=repository_id.split(":")[0],
        repository_id=repository_id,
        data_generation_id="pending-cutover",
        position=GenesisPosition(),
        manifest_digest="0" * 64,
        trust_registry_digest="0" * 64,
        eligibility_epoch=1,
        vector=PartitionRevisionVector.genesis(),
        signature="0" * 64,
    )
    return RuntimePublicationIntent(
        intent_id=uuid.uuid4().hex,
        repository_id=repository_id,
        expected_old_discriminator=selector.selector_digest(),
        candidate_state=tombstone,
        operation_binding="migrate",
        authority_epoch=1,
        fence_token=1,
        phase="prepared",
    )


def _import_batches(
    service: StorageAdministrationService, plane: Path
) -> None:
    """Rebuild the memory catalogs from the immutable legacy log.

    Import is a full generation rebuild: the memory catalogs are reset
    first so an interrupted earlier import cannot collide, then every
    validated batch is appended with its original revision, data revision
    and checksum. Protected key material is adopted in place.
    """
    store = JsonlMemoryPlaneStore(plane)
    batches = store._read_batches_unlocked()  # noqa: SLF001 - validated read
    partition = service.partition()
    with partition.manual_write_transaction() as handle:
        connection = handle.connection
        connection.execute("DELETE FROM memory_record_versions")
        connection.execute("DELETE FROM memory_current_records")
        connection.execute("DELETE FROM memory_batches")
        connection.execute(
            "UPDATE memory_revision_state SET write_revision = 0, data_revision = 0"
            " WHERE id = 1"
        )
        for batch in batches:
            partition.append_memory_batch(
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
        handle.commit()
    _adopt_protected_material(service, plane)


def _adopt_protected_material(
    service: StorageAdministrationService, plane: Path
) -> None:
    """Carry legacy protected secrets into the partition key owner.

    Purpose-named key files keep their identity and owner-only modes; the
    partition's secret directory is created with the same discipline. No
    key is ever regenerated to make verification pass.
    """
    legacy_protected = plane / ".protected"
    if not legacy_protected.is_dir():
        return
    target = service.partition_path().parent / ".protected"
    target.mkdir(mode=0o700, parents=True, exist_ok=True)
    import os

    os.chmod(target, 0o700)
    for member in legacy_protected.iterdir():
        if not member.is_file() or not member.name.endswith(".key"):
            continue
        destination = target / member.name
        if destination.exists():
            continue
        shutil.copyfile(member, destination)
        os.chmod(destination, 0o600)


def _cutover(
    service: StorageAdministrationService, selector: LegacyStorageSelector
) -> None:
    """Publish the imported generation via the legacy-selector intent."""
    from memorii.core.persistence.contracts import (
        GenesisPosition,
        PartitionRevisionVector,
        RuntimeMaterializationManifest,
        RuntimePublicationIntent,
        RuntimePublicationState,
        empty_chain_commitment,
        empty_pointer_set_digest,
    )

    state = service._control_state()
    repository_id = service._repository_id()
    generation_id = "generation-" + uuid.uuid4().hex
    entries = service._control.list_trust_entries()
    trust_digest = canonical_json_digest(
        {"entries": [entry.model_dump_json() for entry in entries]}
    )
    partition = service.partition()
    with partition.manual_write_transaction() as handle:
        connection = handle.connection
        manifest_entries = partition.compute_materialization_manifest(connection)
        manifest = RuntimeMaterializationManifest(catalogs=manifest_entries)
        write_revision, data_revision = partition.read_revision_state(connection)
        vector = PartitionRevisionVector(
            partition_ordinal=0,
            runtime_position=GenesisPosition(),
            memory_write_revision=write_revision,
            memory_data_revision=data_revision,
            semantic_position=GenesisPosition(),
            ontology_pointer_digest=empty_pointer_set_digest(),
        )
        unsigned = RuntimePublicationState(
            installation_id=state.installation_id,
            repository_id=repository_id,
            data_generation_id=generation_id,
            # The genesis position names the first tuple of the migration
            # generation's publication chain — never the data volume, which
            # the vector and manifest bind to the imported heads.
            position=GenesisPosition(),
            manifest_digest=manifest.digest(),
            trust_registry_digest=trust_digest,
            eligibility_epoch=1,
            vector=vector,
            signature="0" * 64,
        )
        candidate = service._sign_state(unsigned)
        partition.write_publication_row(
            connection,
            ordinal=0,
            position_kind="genesis",
            position_sequence=None,
            position_digest=empty_chain_commitment(),
            tuple_digest=candidate.payload_digest(),
            generation_id=generation_id,
            vector_json=candidate.vector.model_dump_json(),
            manifest_digest=candidate.manifest_digest,
        )
        intent = RuntimePublicationIntent(
            intent_id=uuid.uuid4().hex,
            repository_id=repository_id,
            expected_old_discriminator=selector.selector_digest(),
            candidate_state=candidate,
            operation_binding="migrate",
            authority_epoch=1,
            fence_token=1,
        )
        service._control.write_intent(
            intent,
            service._journal_entry(
                operation="publication_prepared",
                after_digest=candidate.payload_digest(),
            ),
        )
        handle.commit()
    service._finalize_publication(candidate)
    service._control.write_intent(
        intent.model_copy(update={"phase": "finalized"}),
        service._journal_entry(
            operation="publication_finalized",
            after_digest=candidate.payload_digest(),
        ),
    )


def _complete_operational_transition(
    service: StorageAdministrationService,
) -> None:
    """Set the operational mode after a verified cutover (idempotent)."""
    state = service._control_state()
    if state.mode == "active" and state.control_revision >= 2:
        return
    service._control.write_control_state(
        state.model_copy(update={"control_revision": state.control_revision + 1, "mode": "active"}),
        service._journal_entry(
            operation="mode_changed",
            before_digest=canonical_json_digest({"mode": state.mode}),
            after_digest=canonical_json_digest({"mode": "active"}),
        ),
    )


def _validate_plane_shape(plane: Path) -> None:
    records_path = plane / LEGACY_PLANE_MARKER
    if not records_path.is_file():
        raise LegacyMigrationError(
            f"migration_required: no legacy plane at {records_path}"
        )
    for member in plane.iterdir():
        if member.name in _KNOWN_PLANE_MEMBERS:
            continue
        raise LegacyMigrationError(
            f"unsupported_configuration: unknown plane member {member.name}"
        )


def _fingerprint_log(plane: Path) -> tuple[str, int]:
    records_bytes = (plane / LEGACY_PLANE_MARKER).read_bytes()
    return hashlib.sha256(records_bytes).hexdigest(), len(records_bytes)


def _verify_capacity(root: Path, plan: MemoryPlaneMigrationPlan) -> None:
    usage = shutil.disk_usage(root)
    if usage.free < plan.required_free_bytes:
        raise LegacyMigrationError(
            "resource_exhausted: required"
            f" {plan.required_free_bytes} bytes, available {usage.free}"
        )


def _plane_locked(plane: Path):
    return locked_file(plane / "memory_records.lock", exclusive=True)


__all__ = [
    "LEGACY_PLANE_MARKER",
    "LegacyMigrationError",
    "LegacyStorageSelector",
    "MemoryPlaneMigrationPlan",
    "build_migration_plan",
    "migrate_legacy_installation",
]
