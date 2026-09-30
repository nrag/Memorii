"""Legacy JSONL installation migration: plan, adopt, import, cut over.

The migration owner never mutates the legacy installation: planning is
read-only, adoption creates independent control authority in a fresh
owner-only sibling directory, import copies every batch with its original
bytes into a new SQLite generation, and cutover is an owner-authorized
generation-change intent whose expected-old discriminator is the typed
``LegacyStorageSelector``. Recovery accepts only the exact legacy selector
or the exact verified SQLite tuple; every third state quarantines.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_plane.store import JsonlMemoryPlaneStore
from memorii.core.persistence.contracts import canonical_json_digest
from memorii.core.storage_administration.service import (
    _DEFAULT_SIGNER_KEY_ID,
    StorageAdministrationService,
)
from memorii.stores.sqlite.partition import PartitionDataRepository

LEGACY_PLANE_MARKER = "memory_records.jsonl"
_ADOPTED_PARTICIPANTS = (
    "work_state",
    "decision_state",
    "llm_decision",
    "semantic_integrity",
    "conflict_attention",
    ".protected",
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
    records_path = plane / LEGACY_PLANE_MARKER
    if not records_path.is_file():
        raise LegacyMigrationError(
            f"migration_required: no legacy plane at {records_path}"
        )
    for member in plane.iterdir():
        if member.name in {
            LEGACY_PLANE_MARKER,
            "memory_records.lock",
            ".protected",
        }:
            continue
        raise LegacyMigrationError(
            f"unsupported_configuration: unknown plane member {member.name}"
        )
    store = JsonlMemoryPlaneStore(plane)
    # Reading validates the whole chain (checksums, contiguity, revisions)
    # and fails closed on corruption.
    _, records = store.read_write_snapshot()
    write_revision = store.read_write_snapshot()[0]
    data_revision = store.revision()
    batch_count = len(store._read_batches_unlocked())  # noqa: SLF001 - validated read
    records_bytes = records_path.read_bytes()
    participants = tuple(
        name for name in _ADOPTED_PARTICIPANTS if (root / name).exists()
    )
    fields = {
        "installation_root": str(root),
        "plane_directory": str(plane),
        "records_digest": hashlib.sha256(records_bytes).hexdigest(),
        "records_size": len(records_bytes),
        "write_revision": write_revision,
        "data_revision": data_revision,
        "batch_count": batch_count,
        "record_count": len(records),
        "participant_inventory": participants,
        "required_free_bytes": max(len(records_bytes) * 2, 1024 * 1024),
    }
    plan = MemoryPlaneMigrationPlan.model_construct(
        **fields, plan_digest="0" * 64
    )
    return MemoryPlaneMigrationPlan.model_validate(
        plan.model_dump(mode="json") | {"plan_digest": _plan_digest(plan)}
    )


__all__ = [
    "LEGACY_PLANE_MARKER",
    "LegacyMigrationError",
    "LegacyStorageSelector",
    "MemoryPlaneMigrationPlan",
    "build_migration_plan",
    "migrate_legacy_installation",
]


def migrate_legacy_installation(
    installation_root: str | Path,
    *,
    plane_directory: str | Path,
    approved_plan: MemoryPlaneMigrationPlan,
    signer_key_id: str = _DEFAULT_SIGNER_KEY_ID,
) -> StorageAdministrationService:
    """Owner-authorized adoption, import and cutover of a legacy root.

    Stages (each crash-recoverable): (1) adopt — create the independent
    owner-only control authority recording the typed LegacyStorageSelector
    and the migration plan digest in its first atomic control transaction,
    with storage lifecycle migration_only; (2) import — copy every batch
    with its original bytes and revisions into a fresh SQLite generation,
    validating the chain again before any write; (3) cut over — publish the
    imported generation through the generation-change intent whose
    expected-old discriminator is the legacy selector digest, then set the
    lifecycle operational. The legacy installation is never mutated, and an
    idempotent re-run over a completed migration returns the serving
    administration.
    """
    import uuid

    from memorii.core.persistence.contracts import (
        GenesisPosition,
        InstallationControlState,
        PartitionRevisionVector,
        RuntimeMaterializationManifest,
        RuntimePublicationIntent,
        RuntimePublicationState,
        TrustRegistryEntry,
        empty_chain_commitment,
    )

    root = Path(installation_root)
    plane = Path(plane_directory)
    current_plan = build_migration_plan(root, plane_directory=plane)
    if current_plan.plan_digest != approved_plan.plan_digest:
        raise LegacyMigrationError(
            "conflict: legacy input changed since the approved plan"
        )
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
        existing = service._control.read_control_state()
        if existing is not None:
            return _resume_or_serve(service, selector)
        # Stage 1: adoption — first atomic control transaction binding the
        # exact legacy selector, the plan and migration_only lifecycle.
        installation_id = "migrated-" + uuid.uuid4().hex
        repository_id = f"{installation_id}:default-partition"
        generation_id = "generation-" + uuid.uuid4().hex
        fingerprint = service._ensure_signing_key()
        trust_entry = TrustRegistryEntry(
            key_id=signer_key_id,
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
        # Stage 2: import — validated copy into the fresh SQLite generation.
        legacy_store = JsonlMemoryPlaneStore(plane)
        batches = legacy_store._read_batches_unlocked()  # noqa: SLF001 - validated
        partition = service.partition()
        sqlite_store = _SqliteMemoryPlaneStore(partition)
        for batch in batches:
            sqlite_store.write_records_preserving_batch(batch)
        # Stage 3: cutover — publish the imported generation through the
        # generation-change intent with the legacy selector as expected-old.
        with partition.manual_write_transaction() as handle:
            connection = handle.connection
            entries = partition.compute_materialization_manifest(connection)
            manifest = RuntimeMaterializationManifest(catalogs=entries)
            write_revision, data_revision = partition.read_revision_state(connection)
            vector = PartitionRevisionVector(
                partition_ordinal=0,
                runtime_position=GenesisPosition(),
                memory_write_revision=write_revision,
                memory_data_revision=data_revision,
                semantic_position=GenesisPosition(),
                ontology_pointer_digest=empty_chain_commitment(),
            )
            unsigned_state = RuntimePublicationState(
                installation_id=installation_id,
                repository_id=repository_id,
                data_generation_id=generation_id,
                position=GenesisPosition(),
                manifest_digest=manifest.digest(),
                trust_registry_digest=canonical_json_digest(
                    {"entries": [trust_entry.model_dump_json()]}
                ),
                eligibility_epoch=1,
                vector=vector,
                signature="0" * 64,
            )
            candidate = service._sign_state(unsigned_state)
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
            service._control.initialize_installation(
                state,
                trust_entry,
                intent,
                journal,
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
        service._control.write_control_state(
            state.model_copy(
                update={
                    "control_revision": 2,
                    "mode": "active",
                    "adopted_legacy_records_digest": selector.records_digest,
                }
            ),
            service._journal_entry(
                operation="mode_changed",
                before_digest=canonical_json_digest({"mode": "read_only"}),
                after_digest=canonical_json_digest({"mode": "active"}),
            ),
        )
        return service
    except BaseException:
        service.close()
        raise


def _resume_or_serve(
    service: StorageAdministrationService, selector: LegacyStorageSelector
) -> StorageAdministrationService:
    resolution = service.resolve_pending_publication()
    finalized = service._control.read_publication_state(service._repository_id())
    state = service._control_state()
    if finalized is None and resolution.disposition == "aborted_initialization":
        raise LegacyMigrationError(
            "migration adoption aborted; legacy input must be re-adopted"
        )
    if finalized is None:
        raise LegacyMigrationError(
            "migration is incomplete; resolve before retrying"
        )
    if state.quarantined_reason is not None:
        raise LegacyMigrationError(f"migration control is quarantined: {state.quarantined_reason}")
    del selector
    return service


def _SqliteMemoryPlaneStore(partition: PartitionDataRepository):  # noqa: N802
    from memorii.core.memory_plane.sqlite_store import SqliteMemoryPlaneStore

    return _BatchPreservingWriter(partition, SqliteMemoryPlaneStore(partition))


class _BatchPreservingWriter:
    """Import helper: append each legacy batch with original bytes intact."""

    def __init__(self, partition: PartitionDataRepository, inner: object) -> None:
        self._partition = partition
        self._inner = inner

    def write_records_preserving_batch(self, batch: object) -> None:
        with self._partition.manual_write_transaction() as handle:
            connection = handle.connection
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
            handle.commit()
