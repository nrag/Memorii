"""Content-addressed delivery-coordinate migration and activation evidence."""

from __future__ import annotations

from hashlib import sha256

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value


class DeliveryCoordinateMigrationError(ValueError):
    pass


class DeliveryCoordinateMigrationEntry(BaseModel):
    legacy_record_id: str = Field(min_length=1)
    legacy_evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    target_delivery_key_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    migrated_state_digests: tuple[str, ...]
    owner_disposition_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    entry_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)


class DeliveryCoordinateMigrationPlan(BaseModel):
    migration_plan_id: str = Field(min_length=1)
    source_writer_epoch: int = Field(ge=0)
    target_writer_epoch: int = Field(ge=1)
    legacy_snapshot_token: str = Field(min_length=1)
    complete_legacy_record_ids: tuple[str, ...]
    entries: tuple[DeliveryCoordinateMigrationEntry, ...]
    canonical_plan_bytes: bytes
    plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_complete_inventory(self) -> DeliveryCoordinateMigrationPlan:
        ids = tuple(entry.legacy_record_id for entry in self.entries)
        if self.target_writer_epoch != self.source_writer_epoch + 1:
            raise ValueError("migration target epoch must be the immediate successor")
        if ids != self.complete_legacy_record_ids or len(set(ids)) != len(ids):
            raise ValueError("migration entries must be a bijection over the frozen inventory")
        if tuple(sorted(ids)) != ids:
            raise ValueError("migration inventory must be canonically ordered")
        if any(entry.entry_digest != _digest(entry.model_dump(exclude={"entry_digest"})) for entry in self.entries):
            raise ValueError("migration entry digest is invalid")
        if self.canonical_plan_bytes != encode_typed_value(_plan_preimage(self)):
            raise ValueError("canonical migration plan bytes are invalid")
        if self.plan_digest != sha256(self.canonical_plan_bytes).hexdigest():
            raise ValueError("migration plan digest is invalid")
        return self


class DeliveryCoordinateMigrationCheckpoint(BaseModel):
    migration_plan_id: str
    plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    completed_entry_digests: tuple[str, ...]
    target_generation: int = Field(ge=1)
    checkpoint_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_digest(self) -> DeliveryCoordinateMigrationCheckpoint:
        if self.checkpoint_digest != _digest(self.model_dump(exclude={"checkpoint_digest"})):
            raise ValueError("migration checkpoint digest is invalid")
        return self


class DeliveryCoordinateMigrationCertificate(BaseModel):
    migration_plan_id: str
    plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_writer_epoch: int = Field(ge=0)
    target_writer_epoch: int = Field(ge=1)
    legacy_snapshot_token: str
    complete_legacy_record_ids: tuple[str, ...]
    verified_entry_digests: tuple[str, ...]
    owner_disposition_digests: tuple[str, ...]
    target_generation: int = Field(ge=1)
    independent_verifier_fingerprint: str = Field(min_length=1)
    certificate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_digest(self) -> DeliveryCoordinateMigrationCertificate:
        if self.target_writer_epoch != self.source_writer_epoch + 1:
            raise ValueError("certificate target epoch is invalid")
        if self.certificate_digest != _digest(self.model_dump(exclude={"certificate_digest"})):
            raise ValueError("migration certificate digest is invalid")
        return self


class DeliveryCoordinateMigrationActivation(BaseModel):
    migration_plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    migration_certificate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_writer_epoch: int = Field(ge=0)
    target_writer_epoch: int = Field(ge=1)
    target_generation: int = Field(ge=1)
    activation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_digest(self) -> DeliveryCoordinateMigrationActivation:
        if self.target_writer_epoch != self.source_writer_epoch + 1:
            raise ValueError("activation target epoch is invalid")
        if self.activation_digest != _digest(self.model_dump(exclude={"activation_digest"})):
            raise ValueError("migration activation digest is invalid")
        return self


class DeliveryCoordinateMigrationTargetProjection(BaseModel):
    entry_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    target_delivery_key_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    target_generation: int = Field(ge=1)
    target_record_id: str = Field(min_length=1)
    target_record_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    projection_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_digest(self) -> DeliveryCoordinateMigrationTargetProjection:
        if self.projection_digest != _digest(self.model_dump(exclude={"projection_digest"})):
            raise ValueError("migration target projection digest is invalid")
        return self


def build_migration_plan(
    *, migration_plan_id: str, source_writer_epoch: int, legacy_snapshot_token: str,
    entries: tuple[DeliveryCoordinateMigrationEntry, ...]
) -> DeliveryCoordinateMigrationPlan:
    ordered = tuple(sorted(entries, key=lambda entry: entry.legacy_record_id))
    values: dict[str, object] = {
        "migration_plan_id": migration_plan_id,
        "source_writer_epoch": source_writer_epoch,
        "target_writer_epoch": source_writer_epoch + 1,
        "legacy_snapshot_token": legacy_snapshot_token,
        "complete_legacy_record_ids": tuple(entry.legacy_record_id for entry in ordered),
        "entry_digests": tuple(entry.entry_digest for entry in ordered),
    }
    canonical = encode_typed_value(values)
    return DeliveryCoordinateMigrationPlan(
        migration_plan_id=migration_plan_id,
        source_writer_epoch=source_writer_epoch,
        target_writer_epoch=source_writer_epoch + 1,
        legacy_snapshot_token=legacy_snapshot_token,
        complete_legacy_record_ids=tuple(entry.legacy_record_id for entry in ordered),
        entries=ordered,
        canonical_plan_bytes=canonical,
        plan_digest=sha256(canonical).hexdigest(),
    )


def certify_migration(
    plan: DeliveryCoordinateMigrationPlan, checkpoint: DeliveryCoordinateMigrationCheckpoint,
    *, independent_verifier_fingerprint: str
) -> DeliveryCoordinateMigrationCertificate:
    expected = tuple(entry.entry_digest for entry in plan.entries)
    if checkpoint.migration_plan_id != plan.migration_plan_id or checkpoint.plan_digest != plan.plan_digest:
        raise DeliveryCoordinateMigrationError("checkpoint does not bind the migration plan")
    if checkpoint.completed_entry_digests != expected:
        raise DeliveryCoordinateMigrationError("target generation is incomplete")
    certificate_values = {
        "migration_plan_id": plan.migration_plan_id, "plan_digest": plan.plan_digest,
        "source_writer_epoch": plan.source_writer_epoch, "target_writer_epoch": plan.target_writer_epoch,
        "legacy_snapshot_token": plan.legacy_snapshot_token,
        "complete_legacy_record_ids": plan.complete_legacy_record_ids,
        "verified_entry_digests": expected,
        "owner_disposition_digests": tuple(
            entry.owner_disposition_digest for entry in plan.entries if entry.owner_disposition_digest is not None
        ),
        "target_generation": checkpoint.target_generation,
        "independent_verifier_fingerprint": independent_verifier_fingerprint,
    }
    return DeliveryCoordinateMigrationCertificate(
        **certificate_values, certificate_digest=_digest(certificate_values)
    )


def activate_migration(
    plan: DeliveryCoordinateMigrationPlan, certificate: DeliveryCoordinateMigrationCertificate
) -> DeliveryCoordinateMigrationActivation:
    if (
        certificate.plan_digest != plan.plan_digest
        or certificate.source_writer_epoch != plan.source_writer_epoch
        or certificate.target_writer_epoch != plan.target_writer_epoch
        or certificate.complete_legacy_record_ids != plan.complete_legacy_record_ids
        or certificate.verified_entry_digests != tuple(entry.entry_digest for entry in plan.entries)
    ):
        raise DeliveryCoordinateMigrationError("migration certificate is not complete for this plan")
    values = {
        "migration_plan_digest": plan.plan_digest,
        "migration_certificate_digest": certificate.certificate_digest,
        "source_writer_epoch": plan.source_writer_epoch,
        "target_writer_epoch": plan.target_writer_epoch,
        "target_generation": certificate.target_generation,
    }
    return DeliveryCoordinateMigrationActivation(**values, activation_digest=_digest(values))


def _plan_preimage(plan: DeliveryCoordinateMigrationPlan) -> dict[str, object]:
    return {
        "migration_plan_id": plan.migration_plan_id, "source_writer_epoch": plan.source_writer_epoch,
        "target_writer_epoch": plan.target_writer_epoch, "legacy_snapshot_token": plan.legacy_snapshot_token,
        "complete_legacy_record_ids": plan.complete_legacy_record_ids,
        "entry_digests": tuple(entry.entry_digest for entry in plan.entries),
    }


def _digest(value: object) -> str:
    return sha256(encode_typed_value(value)).hexdigest()
