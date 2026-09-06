"""Append-only integrity isolation, repair, and release authority."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from secrets import token_hex
from threading import local
from typing import TYPE_CHECKING, Literal, TypeAlias, TypedDict

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value, normalize_delivery_id

if TYPE_CHECKING:
    from memorii.core.memory_evolution.conflict_attention_repository import (
        FileConflictAttentionRepository,
    )
    from memorii.core.semantic_ingestion.contracts import SemanticGraphDelta

_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_SNAPSHOT_DOMAIN = b"memorii.conflict-integrity-repository-snapshot.v1\0"
_ISOLATION_PROOF_DOMAIN = b"memorii.conflict-scope-isolation-proof.v1\0"
_REPAIR_GENERATION_DOMAIN = b"memorii.conflict-repair-generation.v1\0"
_RELEASE_PROOF_DOMAIN = b"memorii.conflict-scope-release-proof.v1\0"
_CONTROL_DOMAIN = b"memorii.conflict-freeze-control-state.v1\0"
_GENERATION_DOMAIN = b"memorii.conflict-integrity-generation.v1\0"
_INCIDENT_EVIDENCE_DOMAIN = b"memorii.conflict-integrity-incident-evidence.v1\0"
_CLEAN_REPLAY_DOMAIN = b"memorii.conflict-clean-replay-verification.v1\0"
_CLEAN_RECOVERY_REQUEST_DOMAIN = b"memorii.semantic-event-clean-recovery-request.v1\0"


class ReplayIntegrityLinearization:
    """One interprocess lock ordered before event and integrity ledger locks."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._local = local()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)

    @contextmanager
    def exclusive(self) -> Iterator[None]:
        depth = getattr(self._local, "depth", 0)
        if depth:
            self._local.depth = depth + 1
            try:
                yield
            finally:
                self._local.depth -= 1
            return
        with self._path.open("r+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            self._local.depth = 1
            try:
                yield
            finally:
                self._local.depth = 0
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _digest(domain: bytes, value: object) -> str:
    return hashlib.sha256(domain + encode_typed_value(value)).hexdigest()


def _identifier(value: str) -> str:
    return normalize_delivery_id(value)


def _digest_field(value: str) -> str:
    if not _DIGEST.fullmatch(value):
        raise ValueError("digest field must be a lowercase SHA-256 digest")
    return value


def _optional_digest(value: str | None) -> str | None:
    return None if value is None else _digest_field(value)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None or value.utcoffset() != timedelta(0):
        raise ValueError("instant must be timezone-aware UTC")
    return value.astimezone(UTC)


def _canonical_identifiers(values: tuple[str, ...], *, nonempty: bool = False) -> tuple[str, ...]:
    canonical = tuple(sorted(set(values), key=lambda item: item.encode("utf-8")))
    if values != canonical or (nonempty and not values):
        raise ValueError("identifier tuple must be canonical")
    return tuple(_identifier(value) for value in values)


def _canonical_digests(values: tuple[str, ...], *, nonempty: bool = False) -> tuple[str, ...]:
    canonical = tuple(sorted(set(values)))
    if values != canonical or (nonempty and not values):
        raise ValueError("digest tuple must be canonical")
    return tuple(_digest_field(value) for value in values)


class ConflictRepositoryPartitionSnapshot(BaseModel):
    partition_id: str
    scope_digest: str
    retained_byte_digests: tuple[str, ...]

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_partition_id = field_validator("partition_id")(_identifier)
    _validate_scope_digest = field_validator("scope_digest")(_digest_field)
    _validate_retained = field_validator("retained_byte_digests")(
        lambda values: _canonical_digests(values)
    )


class ConflictRepositoryIntegritySnapshot(BaseModel):
    repository_id: str
    partitions: tuple[ConflictRepositoryPartitionSnapshot, ...]
    conflict_ledger_start_coordinate: int = Field(ge=0)
    conflict_ledger_end_coordinate: int = Field(ge=0)
    last_verified_event_batch_sequence: int = Field(ge=0)
    store_topology_fingerprint: str
    snapshot_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_repository_id = field_validator("repository_id")(_identifier)
    _validate_digests = field_validator("store_topology_fingerprint", "snapshot_digest")(_digest_field)

    @classmethod
    def create(
        cls,
        *,
        repository_id: str,
        partitions: tuple[ConflictRepositoryPartitionSnapshot, ...],
        conflict_ledger_start_coordinate: int,
        conflict_ledger_end_coordinate: int,
        last_verified_event_batch_sequence: int,
        store_topology_fingerprint: str,
    ) -> ConflictRepositoryIntegritySnapshot:
        payload = {
            "repository_id": repository_id,
            "partitions": partitions,
            "conflict_ledger_start_coordinate": conflict_ledger_start_coordinate,
            "conflict_ledger_end_coordinate": conflict_ledger_end_coordinate,
            "last_verified_event_batch_sequence": last_verified_event_batch_sequence,
            "store_topology_fingerprint": store_topology_fingerprint,
        }
        provisional = cls.model_construct(**payload, snapshot_digest="0" * 64)
        return cls(
            **payload,
            snapshot_digest=_digest(
                _SNAPSHOT_DOMAIN,
                provisional.model_dump(mode="json", exclude={"snapshot_digest"}),
            ),
        )

    @model_validator(mode="after")
    def validate_snapshot(self) -> ConflictRepositoryIntegritySnapshot:
        if not self.partitions:
            raise ValueError("repository snapshot requires at least one partition")
        partition_ids = tuple(partition.partition_id for partition in self.partitions)
        if partition_ids != tuple(sorted(set(partition_ids), key=lambda item: item.encode("utf-8"))):
            raise ValueError("snapshot partitions must be unique and canonical")
        if self.conflict_ledger_end_coordinate < self.conflict_ledger_start_coordinate:
            raise ValueError("conflict ledger coordinates are inverted")
        if self.snapshot_digest != _digest(
            _SNAPSHOT_DOMAIN,
            self.model_dump(mode="json", exclude={"snapshot_digest"}),
        ):
            raise ValueError("repository snapshot digest mismatch")
        return self


class ConflictScopeIsolationProof(BaseModel):
    proof_id: str
    repository_id: str
    predecessor_control_digest: str | None
    previous_frozen_partition_ids: tuple[str, ...]
    newly_frozen_partition_ids: tuple[str, ...]
    frozen_partition_ids: tuple[str, ...]
    frozen_scope_digests: tuple[str, ...]
    unaffected_partition_ids: tuple[str, ...]
    conflict_ledger_start_coordinate: int = Field(ge=0)
    conflict_ledger_end_coordinate: int = Field(ge=0)
    last_verified_event_batch_sequence: int = Field(ge=0)
    conflicting_byte_digests: tuple[str, ...]
    store_topology_fingerprint: str
    repository_snapshot_digest: str
    proof_revision: int = Field(ge=1)
    predecessor_proof_digest: str | None
    resulting_freeze_control_digest: str
    proof_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_ids = field_validator("proof_id", "repository_id")(_identifier)
    _validate_previous = field_validator("previous_frozen_partition_ids")(_canonical_identifiers)
    _validate_new = field_validator("newly_frozen_partition_ids")(
        lambda values: _canonical_identifiers(values, nonempty=True)
    )
    _validate_frozen = field_validator("frozen_partition_ids")(
        lambda values: _canonical_identifiers(values, nonempty=True)
    )
    _validate_unaffected = field_validator("unaffected_partition_ids")(_canonical_identifiers)
    _validate_scope_digests = field_validator("frozen_scope_digests")(
        lambda values: _canonical_digests(values, nonempty=True)
    )
    _validate_conflicting = field_validator("conflicting_byte_digests")(
        lambda values: _canonical_digests(values, nonempty=True)
    )
    _validate_digests = field_validator(
        "store_topology_fingerprint",
        "repository_snapshot_digest",
        "resulting_freeze_control_digest",
        "proof_digest",
    )(_digest_field)
    _validate_optional_digests = field_validator("predecessor_control_digest", "predecessor_proof_digest")(
        _optional_digest
    )

    @model_validator(mode="after")
    def validate_isolation(self) -> ConflictScopeIsolationProof:
        previous = set(self.previous_frozen_partition_ids)
        new = set(self.newly_frozen_partition_ids)
        frozen = set(self.frozen_partition_ids)
        unaffected = set(self.unaffected_partition_ids)
        if previous & new or frozen != previous | new or frozen & unaffected:
            raise ValueError("isolation partition sets do not form an additive disjoint topology")
        if self.conflict_ledger_end_coordinate < self.conflict_ledger_start_coordinate:
            raise ValueError("conflict ledger coordinates are inverted")
        if self.proof_revision == 1:
            if previous or self.predecessor_control_digest is not None or self.predecessor_proof_digest is not None:
                raise ValueError("initial isolation cannot name predecessor authority")
        elif self.predecessor_control_digest is None or self.predecessor_proof_digest is None:
            raise ValueError("additive isolation requires predecessor authority")
        if self.proof_digest != _proof_digest(_ISOLATION_PROOF_DOMAIN, self):
            raise ValueError("isolation proof digest mismatch")
        return self


class ConflictRepairGeneration(BaseModel):
    repair_generation_id: str
    repository_id: str
    predecessor_isolation_proof_digest: str
    latest_incident_evidence_digest: str
    repaired_partition_ids: tuple[str, ...]
    authority_source_digests: tuple[str, ...]
    retained_conflicting_byte_digests: tuple[str, ...]
    clean_generation_id: str
    clean_generation_digest: str
    retained_corrupt_generation_digest: str
    replay_start_event_batch_sequence: int = Field(ge=0)
    replay_final_event_batch_sequence: int = Field(ge=0)
    replay_final_batch_digest: str
    replay_repository_state_digest: str
    completed_at: datetime
    repair_generation_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_ids = field_validator(
        "repair_generation_id", "repository_id", "clean_generation_id"
    )(_identifier)
    _validate_repaired = field_validator("repaired_partition_ids")(
        lambda values: _canonical_identifiers(values, nonempty=True)
    )
    _validate_authority = field_validator("authority_source_digests")(
        lambda values: _canonical_digests(values, nonempty=True)
    )
    _validate_conflicting = field_validator("retained_conflicting_byte_digests")(
        lambda values: _canonical_digests(values, nonempty=True)
    )
    _validate_digests = field_validator(
        "predecessor_isolation_proof_digest",
        "latest_incident_evidence_digest",
        "clean_generation_digest",
        "retained_corrupt_generation_digest",
        "replay_final_batch_digest",
        "replay_repository_state_digest",
        "repair_generation_digest",
    )(_digest_field)
    _validate_completed_at = field_validator("completed_at")(_utc)

    @model_validator(mode="after")
    def validate_repair(self) -> ConflictRepairGeneration:
        if self.replay_final_event_batch_sequence < self.replay_start_event_batch_sequence:
            raise ValueError("repair replay coordinates are inverted")
        if self.repair_generation_digest != _digest(
            _REPAIR_GENERATION_DOMAIN,
            self.model_dump(mode="json", exclude={"repair_generation_digest"}),
        ):
            raise ValueError("repair generation digest mismatch")
        return self


class ConflictIntegrityIncidentEvidence(BaseModel):
    incident_evidence_id: str
    repository_id: str
    freeze_control_digest: str
    authority_proof_digest: str
    frozen_partition_ids: tuple[str, ...]
    conflicting_byte_digests: tuple[str, ...]
    repository_snapshot_digest: str
    predecessor_incident_evidence_digest: str | None
    recorded_at: datetime
    evidence_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_ids = field_validator("incident_evidence_id", "repository_id")(_identifier)
    _validate_partitions = field_validator("frozen_partition_ids")(
        lambda values: _canonical_identifiers(values, nonempty=True)
    )
    _validate_conflicting = field_validator("conflicting_byte_digests")(
        lambda values: _canonical_digests(values, nonempty=True)
    )
    _validate_digests = field_validator(
        "freeze_control_digest",
        "authority_proof_digest",
        "repository_snapshot_digest",
        "evidence_digest",
    )(_digest_field)
    _validate_predecessor = field_validator("predecessor_incident_evidence_digest")(_optional_digest)
    _validate_recorded_at = field_validator("recorded_at")(_utc)

    @model_validator(mode="after")
    def validate_evidence(self) -> ConflictIntegrityIncidentEvidence:
        if self.evidence_digest != _digest(
            _INCIDENT_EVIDENCE_DOMAIN,
            self.model_dump(mode="json", exclude={"evidence_digest"}),
        ):
            raise ValueError("integrity incident evidence digest mismatch")
        return self


class ConflictCleanReplayVerification(BaseModel):
    repository_id: str
    repaired_partition_ids: tuple[str, ...]
    retained_conflicting_byte_digests: tuple[str, ...]
    authority_source_digests: tuple[str, ...]
    clean_generation_id: str
    clean_generation_digest: str
    retained_corrupt_generation_digest: str
    replay_start_event_batch_sequence: int = Field(ge=0)
    replay_final_event_batch_sequence: int = Field(ge=0)
    replay_final_batch_digest: str
    replay_repository_state_digest: str
    verified_at: datetime
    verification_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_repository = field_validator("repository_id", "clean_generation_id")(_identifier)
    _validate_partitions = field_validator("repaired_partition_ids")(
        lambda values: _canonical_identifiers(values, nonempty=True)
    )
    _validate_conflicting = field_validator("retained_conflicting_byte_digests")(
        lambda values: _canonical_digests(values, nonempty=True)
    )
    _validate_authority = field_validator("authority_source_digests")(
        lambda values: _canonical_digests(values, nonempty=True)
    )
    _validate_digests = field_validator(
        "clean_generation_digest",
        "retained_corrupt_generation_digest",
        "replay_final_batch_digest",
        "replay_repository_state_digest",
        "verification_digest",
    )(_digest_field)
    _validate_verified_at = field_validator("verified_at")(_utc)

    @classmethod
    def create(
        cls,
        *,
        repository_id: str,
        repaired_partition_ids: tuple[str, ...],
        retained_conflicting_byte_digests: tuple[str, ...],
        authority_source_digests: tuple[str, ...],
        clean_generation_id: str,
        clean_generation_digest: str,
        retained_corrupt_generation_digest: str,
        replay_start_event_batch_sequence: int,
        replay_final_event_batch_sequence: int,
        replay_final_batch_digest: str,
        replay_repository_state_digest: str,
        verified_at: datetime,
    ) -> ConflictCleanReplayVerification:
        values = {
            "repository_id": repository_id,
            "repaired_partition_ids": repaired_partition_ids,
            "retained_conflicting_byte_digests": retained_conflicting_byte_digests,
            "authority_source_digests": authority_source_digests,
            "clean_generation_id": clean_generation_id,
            "clean_generation_digest": clean_generation_digest,
            "retained_corrupt_generation_digest": retained_corrupt_generation_digest,
            "replay_start_event_batch_sequence": replay_start_event_batch_sequence,
            "replay_final_event_batch_sequence": replay_final_event_batch_sequence,
            "replay_final_batch_digest": replay_final_batch_digest,
            "replay_repository_state_digest": replay_repository_state_digest,
            "verified_at": verified_at,
        }
        provisional = cls.model_construct(**values, verification_digest="0" * 64)
        return cls(
            **values,
            verification_digest=_digest(
                _CLEAN_REPLAY_DOMAIN,
                provisional.model_dump(mode="json", exclude={"verification_digest"}),
            ),
        )

    @model_validator(mode="after")
    def validate_verification(self) -> ConflictCleanReplayVerification:
        if self.replay_final_event_batch_sequence < self.replay_start_event_batch_sequence:
            raise ValueError("clean replay coordinates are inverted")
        if self.verification_digest != _digest(
            _CLEAN_REPLAY_DOMAIN,
            self.model_dump(mode="json", exclude={"verification_digest"}),
        ):
            raise ValueError("clean replay verification digest mismatch")
        return self


class SemanticEventCleanAuthorityBatch(BaseModel):
    """One authoritative canonical batch supplied to store-owned clean recovery."""

    source_id: str
    canonical_batch_bytes: bytes
    source_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_source = field_validator("source_id")(_identifier)
    _validate_digest = field_validator("source_digest")(_digest_field)

    @model_validator(mode="after")
    def validate_source_digest(self) -> SemanticEventCleanAuthorityBatch:
        if not self.canonical_batch_bytes or self.source_digest != hashlib.sha256(
            self.canonical_batch_bytes
        ).hexdigest():
            raise ValueError("clean recovery authority source digest mismatch")
        return self


class SemanticEventCleanRecoveryRequest(BaseModel):
    """Typed repair input binding authority, corrupt evidence, and exact subset."""

    repository_id: str
    repaired_partition_ids: tuple[str, ...]
    authority_batches: tuple[SemanticEventCleanAuthorityBatch, ...]
    retained_conflicting_byte_digests: tuple[str, ...]
    retained_corrupt_generation_digest: str
    request_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_repository = field_validator("repository_id")(_identifier)
    _validate_partitions = field_validator("repaired_partition_ids")(
        lambda values: _canonical_identifiers(values, nonempty=True)
    )
    _validate_retained = field_validator("retained_conflicting_byte_digests")(
        lambda values: _canonical_digests(values, nonempty=True)
    )
    _validate_digests = field_validator(
        "retained_corrupt_generation_digest", "request_digest"
    )(_digest_field)

    @classmethod
    def create(
        cls,
        *,
        repository_id: str,
        repaired_partition_ids: tuple[str, ...],
        authority_batches: tuple[SemanticEventCleanAuthorityBatch, ...],
        retained_conflicting_byte_digests: tuple[str, ...],
        retained_corrupt_generation_digest: str,
    ) -> SemanticEventCleanRecoveryRequest:
        body = {
            "repository_id": repository_id,
            "repaired_partition_ids": repaired_partition_ids,
            "authority_batches": authority_batches,
            "retained_conflicting_byte_digests": retained_conflicting_byte_digests,
            "retained_corrupt_generation_digest": retained_corrupt_generation_digest,
        }
        provisional = cls.model_construct(**body, request_digest="0" * 64)
        return cls(
            **body,
            request_digest=_digest(
                _CLEAN_RECOVERY_REQUEST_DOMAIN,
                provisional.model_dump(mode="python", exclude={"request_digest"}),
            ),
        )

    @model_validator(mode="after")
    def validate_request(self) -> SemanticEventCleanRecoveryRequest:
        source_ids = tuple(source.source_id for source in self.authority_batches)
        source_digests = tuple(
            source.source_digest for source in self.authority_batches
        )
        if (
            not source_ids
            or source_ids != tuple(sorted(set(source_ids)))
            or len(source_digests) != len(set(source_digests))
            or self.request_digest
            != _digest(
                _CLEAN_RECOVERY_REQUEST_DOMAIN,
                self.model_dump(mode="python", exclude={"request_digest"}),
            )
        ):
            raise ValueError("clean recovery request is noncanonical or corrupt")
        return self

    @property
    def authority_source_digests(self) -> tuple[str, ...]:
        return tuple(sorted(source.source_digest for source in self.authority_batches))


class SemanticEventCleanRecoveryService:
    """Build, retain, and independently replay one clean generation."""

    def __init__(
        self,
        *,
        clean_generation_root: Path,
        retained_corrupt_repository: object,
        request_provider: Callable[
            [tuple[str, ...], tuple[str, ...]], SemanticEventCleanRecoveryRequest
        ],
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._root = clean_generation_root
        self._corrupt = retained_corrupt_repository
        self._request_provider = request_provider
        self._now = now_provider or (lambda: datetime.now(UTC))
        self._root.mkdir(parents=True, exist_ok=True)

    def __call__(
        self,
        repaired_partition_ids: tuple[str, ...],
        retained_conflicting_byte_digests: tuple[str, ...],
        authority_source_digests: tuple[str, ...],
    ) -> ConflictCleanReplayVerification:
        from memorii.core.semantic_ingestion.event_replay import (
            FileSemanticEventRepository,
            SemanticEventReplayError,
            decode_semantic_memory_event_batch,
        )

        corrupt = self._corrupt
        try:
            request = SemanticEventCleanRecoveryRequest.model_validate(
                self._request_provider(
                    repaired_partition_ids,
                    retained_conflicting_byte_digests,
                ).model_dump(mode="python")
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise ConflictIntegrityError("clean_recovery_request_invalid") from exc
        if (
            not isinstance(corrupt, FileSemanticEventRepository)
            or request.repository_id != corrupt.repository_id
            or request.repaired_partition_ids != repaired_partition_ids
            or request.retained_conflicting_byte_digests
            != retained_conflicting_byte_digests
            or request.authority_source_digests != authority_source_digests
            or request.retained_corrupt_generation_digest
            != corrupt.retained_generation_digest()
            or not set(request.retained_conflicting_byte_digests)
            <= set(corrupt.retained_byte_digests())
        ):
            raise ConflictIntegrityError("clean_recovery_request_invalid")
        try:
            batches = tuple(
                decode_semantic_memory_event_batch(
                    source.canonical_batch_bytes,
                    registry_history=corrupt.registry_history,
                )
                for source in request.authority_batches
            )
        except SemanticEventReplayError as exc:
            raise ConflictIntegrityError("clean_recovery_authority_invalid") from exc
        if (
            tuple(batch.log_position.sequence for batch in batches)
            != tuple(range(1, len(batches) + 1))
            or any(batch.repository_id != request.repository_id for batch in batches)
        ):
            raise ConflictIntegrityError("clean_recovery_authority_invalid")
        generation_dir = self._root / request.request_digest
        generation_dir.mkdir(mode=0o700, exist_ok=True)
        event_path = generation_dir / "events.jsonl"
        manifest_path = generation_dir / "request.json"
        manifest_bytes = json.dumps(
            request.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        if manifest_path.exists() and manifest_path.read_bytes() != manifest_bytes:
            raise ConflictIntegrityError("clean_recovery_generation_substituted")
        clean = FileSemanticEventRepository(
            event_path,
            repository_id=request.repository_id,
            registry_history=corrupt.registry_history,
        )
        try:
            for batch in batches:
                clean.append_batch(batch)
            if clean.read_batches_after(None) != batches:
                raise ConflictIntegrityError("clean_recovery_generation_substituted")
            first_state = clean.replay_genesis()
            independent = FileSemanticEventRepository(
                event_path,
                repository_id=request.repository_id,
                registry_history=corrupt.registry_history,
            )
            second_state = independent.replay_genesis()
        except (OSError, SemanticEventReplayError) as exc:
            raise ConflictIntegrityError("clean_recovery_replay_failed") from exc
        if first_state != second_state:
            raise ConflictIntegrityError("clean_recovery_replay_failed")
        if not manifest_path.exists():
            descriptor = os.open(
                manifest_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            try:
                if os.write(descriptor, manifest_bytes) != len(manifest_bytes):
                    raise OSError("partial clean recovery manifest write")
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        clean_digest = clean.retained_generation_digest()
        if clean_digest == request.retained_corrupt_generation_digest:
            raise ConflictIntegrityError("clean_recovery_generation_not_independent")
        final_sequence = (
            0
            if first_state.last_batch_position is None
            else first_state.last_batch_position.sequence
        )
        return ConflictCleanReplayVerification.create(
            repository_id=request.repository_id,
            repaired_partition_ids=request.repaired_partition_ids,
            retained_conflicting_byte_digests=(
                request.retained_conflicting_byte_digests
            ),
            authority_source_digests=request.authority_source_digests,
            clean_generation_id=request.request_digest,
            clean_generation_digest=clean_digest,
            retained_corrupt_generation_digest=(
                request.retained_corrupt_generation_digest
            ),
            replay_start_event_batch_sequence=0,
            replay_final_event_batch_sequence=final_sequence,
            replay_final_batch_digest=(
                first_state.last_event_batch_digest
                or _digest(
                    b"memorii.semantic-event-empty-log.v1\0",
                    request.repository_id,
                )
            ),
            replay_repository_state_digest=first_state.state_digest,
            verified_at=self._now(),
        )


class ConflictScopeReleaseProof(BaseModel):
    proof_id: str
    repository_id: str
    predecessor_proof_digest: str
    predecessor_proof_revision: int = Field(ge=1)
    previous_frozen_partition_ids: tuple[str, ...]
    released_partition_ids: tuple[str, ...]
    remaining_frozen_partition_ids: tuple[str, ...]
    repair_generation_digest: str
    clean_generation_digest: str
    retained_corrupt_generation_digest: str
    clean_replay_final_event_batch_sequence: int = Field(ge=0)
    clean_replay_final_batch_digest: str
    clean_replay_repository_state_digest: str
    store_topology_fingerprint: str
    resulting_freeze_control_digest: str
    proof_revision: int = Field(ge=1)
    proof_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_ids = field_validator("proof_id", "repository_id")(_identifier)
    _validate_previous = field_validator("previous_frozen_partition_ids")(
        lambda values: _canonical_identifiers(values, nonempty=True)
    )
    _validate_released = field_validator("released_partition_ids")(
        lambda values: _canonical_identifiers(values, nonempty=True)
    )
    _validate_remaining = field_validator("remaining_frozen_partition_ids")(_canonical_identifiers)
    _validate_digests = field_validator(
        "predecessor_proof_digest",
        "repair_generation_digest",
        "clean_generation_digest",
        "retained_corrupt_generation_digest",
        "clean_replay_final_batch_digest",
        "clean_replay_repository_state_digest",
        "store_topology_fingerprint",
        "resulting_freeze_control_digest",
        "proof_digest",
    )(_digest_field)

    @model_validator(mode="after")
    def validate_release(self) -> ConflictScopeReleaseProof:
        previous = set(self.previous_frozen_partition_ids)
        released = set(self.released_partition_ids)
        if not released <= previous or set(self.remaining_frozen_partition_ids) != previous - released:
            raise ValueError("release must remove exactly its repaired subset")
        if self.proof_revision != self.predecessor_proof_revision + 1:
            raise ValueError("release proof revision must advance exactly once")
        if self.proof_digest != _proof_digest(_RELEASE_PROOF_DOMAIN, self):
            raise ValueError("release proof digest mismatch")
        return self


class ConflictFreezeControlState(BaseModel):
    repository_id: str
    frozen_partition_ids: tuple[str, ...]
    authority_proof_digest: str
    control_revision: int = Field(ge=1)
    predecessor_control_digest: str | None
    control_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_repository_id = field_validator("repository_id")(_identifier)
    _validate_frozen = field_validator("frozen_partition_ids")(_canonical_identifiers)
    _validate_authority = field_validator("authority_proof_digest", "control_digest")(_digest_field)
    _validate_predecessor = field_validator("predecessor_control_digest")(_optional_digest)

    @model_validator(mode="after")
    def validate_control(self) -> ConflictFreezeControlState:
        if self.control_revision == 1 and self.predecessor_control_digest is not None:
            raise ValueError("initial control cannot name a predecessor")
        if self.control_revision > 1 and self.predecessor_control_digest is None:
            raise ValueError("successor control requires a predecessor")
        if self.control_digest != _digest(
            _CONTROL_DOMAIN,
            self.model_dump(mode="json", exclude={"control_digest"}),
        ):
            raise ValueError("freeze control digest mismatch")
        return self


def _proof_digest(domain: bytes, proof: BaseModel) -> str:
    # The proof names its resulting control while that control names this proof.
    # Excluding the cross-link from proof identity breaks that cycle deterministically.
    return _digest(
        domain,
        proof.model_dump(mode="json", exclude={"proof_digest", "resulting_freeze_control_digest"}),
    )


class ConflictIntegrityError(ValueError):
    """Fail-closed integrity authority or CAS failure."""


class SemanticEventCleanReplayVerifier:
    """Derive repair coordinates only from a complete canonical genesis replay."""

    def __init__(
        self,
        clean_event_repository: object,
        *,
        retained_corrupt_repository: object,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._clean_event_repository = clean_event_repository
        self._retained_corrupt_repository = retained_corrupt_repository
        self._now = now_provider or (lambda: datetime.now(UTC))

    def __call__(
        self,
        repaired_partition_ids: tuple[str, ...],
        retained_conflicting_byte_digests: tuple[str, ...],
        authority_source_digests: tuple[str, ...],
    ) -> ConflictCleanReplayVerification:
        from memorii.core.semantic_ingestion.event_replay import (
            FileSemanticEventRepository,
            encode_semantic_memory_event_batch,
        )

        repository = self._clean_event_repository
        corrupt = self._retained_corrupt_repository
        if (
            not isinstance(repository, FileSemanticEventRepository)
            or not isinstance(corrupt, FileSemanticEventRepository)
            or repository is corrupt
            or repository.repository_id != corrupt.repository_id
        ):
            raise ConflictIntegrityError("clean_replay_verification_failed")
        retained = tuple(sorted(set(retained_conflicting_byte_digests)))
        if not set(retained) <= set(corrupt.retained_byte_digests()):
            raise ConflictIntegrityError("clean_replay_verification_failed")
        batches = repository.read_batches_after(None)
        expected_authority = tuple(
            sorted(
                hashlib.sha256(
                    encode_semantic_memory_event_batch(batch)
                ).hexdigest()
                for batch in batches
            )
        )
        if tuple(sorted(set(authority_source_digests))) != expected_authority:
            raise ConflictIntegrityError("clean_replay_verification_failed")
        state = repository.replay_genesis()
        final_sequence = 0 if state.last_batch_position is None else state.last_batch_position.sequence
        if len(batches) != final_sequence:
            raise ConflictIntegrityError("clean_replay_verification_failed")
        final_batch_digest = state.last_event_batch_digest or _digest(
            b"memorii.semantic-event-empty-log.v1\0", repository.repository_id
        )
        clean_generation_digest = repository.retained_generation_digest()
        corrupt_generation_digest = corrupt.retained_generation_digest()
        if clean_generation_digest == corrupt_generation_digest:
            raise ConflictIntegrityError("clean_replay_verification_failed")
        return ConflictCleanReplayVerification.create(
            repository_id=repository.repository_id,
            repaired_partition_ids=repaired_partition_ids,
            retained_conflicting_byte_digests=retained_conflicting_byte_digests,
            authority_source_digests=authority_source_digests,
            clean_generation_id=clean_generation_digest,
            clean_generation_digest=clean_generation_digest,
            retained_corrupt_generation_digest=corrupt_generation_digest,
            replay_start_event_batch_sequence=0,
            replay_final_event_batch_sequence=final_sequence,
            replay_final_batch_digest=final_batch_digest,
            replay_repository_state_digest=state.state_digest,
            verified_at=self._now(),
        )


class SemanticEventFreezeGuard:
    """Reject a semantic write unless its store-owned partitions are proven unfrozen."""

    def __init__(
        self,
        integrity_repository: FileConflictIntegrityRepository,
        partition_resolver: Callable[[SemanticGraphDelta], tuple[str, ...]],
    ) -> None:
        self._integrity_repository = integrity_repository
        self._partition_resolver = partition_resolver

    def __call__(self, graph_delta: SemanticGraphDelta) -> None:
        control = self._integrity_repository.current_control()
        if control is None or not control.frozen_partition_ids:
            return
        try:
            partitions = _canonical_identifiers(
                self._partition_resolver(graph_delta), nonempty=True
            )
        except (TypeError, ValueError) as exc:
            raise ConflictIntegrityError("semantic_write_partition_unavailable") from exc
        if set(partitions) & set(control.frozen_partition_ids):
            from memorii.core.semantic_ingestion.event_replay import SemanticEventReplayError

            raise SemanticEventReplayError("semantic_repository_scope_frozen")


class CanonicalReplayIntegrityIncidentReporter:
    """Freeze canonical replay authority and optionally publish sanitized pull attention."""

    def __init__(
        self,
        integrity_repository: FileConflictIntegrityRepository,
        attention_repository: FileConflictAttentionRepository | None = None,
    ) -> None:
        self._integrity_repository = integrity_repository
        self._attention_repository = attention_repository

    @property
    def linearization(self) -> ReplayIntegrityLinearization:
        return self._integrity_repository._linearization

    def __call__(self, conflicting_byte_digests: tuple[str, ...]) -> None:
        evidence = self._integrity_repository.report_incident(conflicting_byte_digests)
        if self._attention_repository is not None:
            self._attention_repository.append_storage_integrity_incident(evidence)


class PrivilegedSemanticIntegrityLifecycle:
    """Production owner for one freeze, clean-recovery, and release authority."""

    def __init__(
        self,
        integrity_repository: FileConflictIntegrityRepository,
        *,
        attention_repository: FileConflictAttentionRepository | None = None,
        clean_recovery_request_retainer: Callable[
            [SemanticEventCleanRecoveryRequest], None
        ]
        | None = None,
        clean_recovery_activator: Callable[
            [SemanticEventCleanRecoveryRequest], None
        ]
        | None = None,
        clean_recovery_reconciler: Callable[[bool], None] | None = None,
    ) -> None:
        self._repository = integrity_repository
        self._clean_recovery_request_retainer = clean_recovery_request_retainer
        self._clean_recovery_activator = clean_recovery_activator
        self._clean_recovery_reconciler = clean_recovery_reconciler
        self._freeze_guard = SemanticEventFreezeGuard(
            integrity_repository,
            lambda _graph_delta: ("global",),
        )
        self._incident_reporter = CanonicalReplayIntegrityIncidentReporter(
            integrity_repository,
            attention_repository,
        )

    @property
    def linearization(self) -> ReplayIntegrityLinearization:
        return self._repository._linearization

    @property
    def repository_id(self) -> str:
        return self._repository._repository_id

    @property
    def freeze_guard(self) -> SemanticEventFreezeGuard:
        return self._freeze_guard

    @property
    def incident_reporter(self) -> CanonicalReplayIntegrityIncidentReporter:
        return self._incident_reporter

    def current_control(self) -> ConflictFreezeControlState | None:
        return self._repository.current_control()

    def recover_and_release(
        self,
        request: SemanticEventCleanRecoveryRequest,
        *,
        supplied_snapshot: ConflictRepositoryIntegritySnapshot,
        expected_control_digest: str,
    ) -> tuple[ConflictRepairGeneration, ConflictFreezeControlState]:
        """Execute the only public privileged release path from one typed request."""

        try:
            validated = SemanticEventCleanRecoveryRequest.model_validate(
                request.model_dump(mode="python")
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise ConflictIntegrityError("clean_recovery_request_invalid") from exc
        with self.linearization.exclusive():
            if self._clean_recovery_request_retainer is not None:
                self._clean_recovery_request_retainer(validated)
            repair, control = self._repository.recover_and_release(
                repaired_partition_ids=validated.repaired_partition_ids,
                authority_source_digests=validated.authority_source_digests,
                retained_conflicting_byte_digests=(
                    validated.retained_conflicting_byte_digests
                ),
                supplied_snapshot=supplied_snapshot,
                expected_control_digest=expected_control_digest,
            )
            if self._clean_recovery_activator is not None:
                try:
                    self._clean_recovery_activator(validated)
                except (OSError, RuntimeError, ValueError):
                    # Release and clean-authority activation share this lock.
                    # If activation fails after release, refreeze before any
                    # ordinary writer can acquire the admission coordinate.
                    self._repository.report_incident(
                        validated.retained_conflicting_byte_digests
                    )
                    raise
            return repair, control

    def reconcile_pending_recovery(self) -> None:
        """Finish a released clean generation after a process restart."""

        if self._clean_recovery_reconciler is None:
            return
        with self.linearization.exclusive():
            control = self._repository.current_control()
            released = control is not None and not control.frozen_partition_ids
            try:
                self._clean_recovery_reconciler(released)
            except (OSError, RuntimeError, ValueError):
                if released:
                    evidence = self._repository.latest_incident_evidence()
                    if evidence is not None:
                        # A restart must not leave a released/prepared
                        # generation visible when activation validation fails.
                        self._repository.report_incident(
                            evidence.conflicting_byte_digests
                        )
                raise


class _IsolationPayload(TypedDict):
    proof_id: str
    repository_id: str
    predecessor_control_digest: str | None
    previous_frozen_partition_ids: tuple[str, ...]
    newly_frozen_partition_ids: tuple[str, ...]
    frozen_partition_ids: tuple[str, ...]
    frozen_scope_digests: tuple[str, ...]
    unaffected_partition_ids: tuple[str, ...]
    conflict_ledger_start_coordinate: int
    conflict_ledger_end_coordinate: int
    last_verified_event_batch_sequence: int
    conflicting_byte_digests: tuple[str, ...]
    store_topology_fingerprint: str
    repository_snapshot_digest: str
    proof_revision: int
    predecessor_proof_digest: str | None


class _ReleasePayload(TypedDict):
    proof_id: str
    repository_id: str
    predecessor_proof_digest: str
    predecessor_proof_revision: int
    previous_frozen_partition_ids: tuple[str, ...]
    released_partition_ids: tuple[str, ...]
    remaining_frozen_partition_ids: tuple[str, ...]
    repair_generation_digest: str
    clean_generation_digest: str
    retained_corrupt_generation_digest: str
    clean_replay_final_event_batch_sequence: int
    clean_replay_final_batch_digest: str
    clean_replay_repository_state_digest: str
    store_topology_fingerprint: str
    proof_revision: int


class _RepairPayload(TypedDict):
    repair_generation_id: str
    repository_id: str
    predecessor_isolation_proof_digest: str
    latest_incident_evidence_digest: str
    repaired_partition_ids: tuple[str, ...]
    authority_source_digests: tuple[str, ...]
    retained_conflicting_byte_digests: tuple[str, ...]
    clean_generation_id: str
    clean_generation_digest: str
    retained_corrupt_generation_digest: str
    replay_start_event_batch_sequence: int
    replay_final_event_batch_sequence: int
    replay_final_batch_digest: str
    replay_repository_state_digest: str
    completed_at: datetime


class _ControlPayload(TypedDict):
    repository_id: str
    frozen_partition_ids: tuple[str, ...]
    authority_proof_digest: str
    control_revision: int
    predecessor_control_digest: str | None


class _IntegrityTransitionGeneration(BaseModel):
    schema_version: Literal[1] = 1
    record_type: Literal["integrity_transition"] = "integrity_transition"
    isolation_proof: ConflictScopeIsolationProof | None = None
    release_proof: ConflictScopeReleaseProof | None = None
    incident_evidence: ConflictIntegrityIncidentEvidence | None = None
    control: ConflictFreezeControlState
    generation_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_generation(self) -> _IntegrityTransitionGeneration:
        proofs = [proof for proof in (self.isolation_proof, self.release_proof) if proof is not None]
        if len(proofs) != 1:
            raise ValueError("integrity transition requires exactly one proof")
        proof = proofs[0]
        if (self.isolation_proof is not None) != (self.incident_evidence is not None):
            raise ValueError("isolation transition requires its incident evidence")
        if (
            proof.repository_id != self.control.repository_id
            or proof.proof_digest != self.control.authority_proof_digest
            or proof.resulting_freeze_control_digest != self.control.control_digest
        ):
            raise ValueError("proof and freeze control cross-link mismatch")
        if self.generation_digest != _digest(
            _GENERATION_DOMAIN,
            self.model_dump(mode="json", exclude={"generation_digest"}),
        ):
            raise ValueError("integrity transition generation digest mismatch")
        return self


class _RepairGenerationEntry(BaseModel):
    schema_version: Literal[1] = 1
    record_type: Literal["repair_generation"] = "repair_generation"
    repair: ConflictRepairGeneration
    generation_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_generation(self) -> _RepairGenerationEntry:
        if self.generation_digest != _digest(
            _GENERATION_DOMAIN,
            self.model_dump(mode="json", exclude={"generation_digest"}),
        ):
            raise ValueError("repair generation entry digest mismatch")
        return self


class _IncidentEvidenceEntry(BaseModel):
    schema_version: Literal[1] = 1
    record_type: Literal["incident_evidence"] = "incident_evidence"
    evidence: ConflictIntegrityIncidentEvidence
    generation_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_generation(self) -> _IncidentEvidenceEntry:
        if self.generation_digest != _digest(
            _GENERATION_DOMAIN,
            self.model_dump(mode="json", exclude={"generation_digest"}),
        ):
            raise ValueError("incident evidence entry digest mismatch")
        return self


_IntegrityEntry: TypeAlias = (
    _IntegrityTransitionGeneration | _RepairGenerationEntry | _IncidentEvidenceEntry
)


class FileConflictIntegrityRepository:
    """Process-safe append-only control plane for one replay repository."""

    def __init__(
        self,
        path: Path,
        *,
        repository_id: str,
        snapshot_provider: Callable[[], ConflictRepositoryIntegritySnapshot],
        clean_replay_verifier: Callable[
            [tuple[str, ...], tuple[str, ...], tuple[str, ...]],
            ConflictCleanReplayVerification,
        ]
        | None = None,
        now_provider: Callable[[], datetime] | None = None,
        linearization: ReplayIntegrityLinearization | None = None,
    ) -> None:
        self._path = path
        self._repository_id = _identifier(repository_id)
        self._snapshot_provider = snapshot_provider
        self._clean_replay_verifier = clean_replay_verifier
        self._now = now_provider or (lambda: datetime.now(UTC))
        self._linearization = linearization or ReplayIntegrityLinearization(
            path.with_suffix(path.suffix + ".linearization.lock")
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)

    def current_control(self) -> ConflictFreezeControlState | None:
        with self._linearization.exclusive():
            control, _, _, _ = self._replay(self._read_all())
            return control

    def isolate(
        self,
        *,
        supplied_snapshot: ConflictRepositoryIntegritySnapshot | None,
        conflicting_byte_digests: tuple[str, ...],
        expected_control_digest: str | None,
    ) -> ConflictFreezeControlState:
        with self._linearization.exclusive():
            control, _ = self._isolate(
                supplied_snapshot=supplied_snapshot,
                conflicting_byte_digests=conflicting_byte_digests,
                expected_control_digest=expected_control_digest,
            )
            return control

    def report_incident(
        self,
        conflicting_byte_digests: tuple[str, ...],
    ) -> ConflictIntegrityIncidentEvidence:
        """Freeze from store-owned state and retain one incident evidence record."""

        with self._linearization.exclusive():
            return self._report_incident_unlocked(conflicting_byte_digests)

    def _report_incident_unlocked(
        self,
        conflicting_byte_digests: tuple[str, ...],
    ) -> ConflictIntegrityIncidentEvidence:

        conflicting = _canonical_digests(conflicting_byte_digests, nonempty=True)
        for _ in range(16):
            snapshot = self._authoritative_snapshot()
            current = self.current_control()
            try:
                _, evidence = self._isolate(
                    supplied_snapshot=snapshot,
                    conflicting_byte_digests=conflicting,
                    expected_control_digest=None if current is None else current.control_digest,
                )
            except ConflictIntegrityError as exc:
                if str(exc) == "stale_freeze_control":
                    continue
                raise
            return evidence
        raise ConflictIntegrityError("integrity_incident_contention")

    def latest_incident_evidence(self) -> ConflictIntegrityIncidentEvidence | None:
        with self._linearization.exclusive():
            _, _, _, evidence = self._replay(self._read_all())
            return evidence

    def _isolate(
        self,
        *,
        supplied_snapshot: ConflictRepositoryIntegritySnapshot | None,
        conflicting_byte_digests: tuple[str, ...],
        expected_control_digest: str | None,
    ) -> tuple[ConflictFreezeControlState, ConflictIntegrityIncidentEvidence]:
        conflicting = _canonical_digests(conflicting_byte_digests, nonempty=True)
        authoritative = self._authoritative_snapshot()
        with self._path.open("r+", encoding="utf-8") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            current, current_proof, _, latest_evidence = self._replay(
                self._decode_lines(tuple(handle))
            )
            current_digest = None if current is None else current.control_digest
            if expected_control_digest != current_digest:
                raise ConflictIntegrityError("stale_freeze_control")
            valid_snapshot = self._snapshot_matches(supplied_snapshot, authoritative)
            impacted = self._derive_impacted(authoritative, conflicting) if valid_snapshot else set()
            if not valid_snapshot or not impacted:
                impacted = {partition.partition_id for partition in authoritative.partitions}
            previous = set() if current is None else set(current.frozen_partition_ids)
            newly = impacted - previous
            if not newly:
                if current is None or current_proof is None:
                    raise ConflictIntegrityError("conflict_integrity_corrupt")
                evidence = self._incident_evidence(
                    control=current,
                    conflicting=conflicting,
                    snapshot=authoritative,
                    predecessor=latest_evidence,
                )
                self._append_locked(handle, self._incident_entry(evidence))
                return current, evidence
            frozen = previous | newly
            proof_revision = 1 if current is None else current.control_revision + 1
            proof_payload: _IsolationPayload = {
                "proof_id": token_hex(16),
                "repository_id": self._repository_id,
                "predecessor_control_digest": current_digest,
                "previous_frozen_partition_ids": tuple(sorted(previous)),
                "newly_frozen_partition_ids": tuple(sorted(newly)),
                "frozen_partition_ids": tuple(sorted(frozen)),
                "frozen_scope_digests": tuple(
                    sorted(
                        {
                            partition.scope_digest
                            for partition in authoritative.partitions
                            if partition.partition_id in frozen
                        }
                    )
                ),
                "unaffected_partition_ids": tuple(
                    sorted(
                        partition.partition_id
                        for partition in authoritative.partitions
                        if partition.partition_id not in frozen
                    )
                ),
                "conflict_ledger_start_coordinate": authoritative.conflict_ledger_start_coordinate,
                "conflict_ledger_end_coordinate": authoritative.conflict_ledger_end_coordinate,
                "last_verified_event_batch_sequence": authoritative.last_verified_event_batch_sequence,
                "conflicting_byte_digests": conflicting,
                "store_topology_fingerprint": authoritative.store_topology_fingerprint,
                "repository_snapshot_digest": authoritative.snapshot_digest,
                "proof_revision": proof_revision,
                "predecessor_proof_digest": None if current_proof is None else current_proof.proof_digest,
            }
            proof, control = self._isolation_proof_and_control(proof_payload, current)
            evidence = self._incident_evidence(
                control=control,
                conflicting=conflicting,
                snapshot=authoritative,
                predecessor=latest_evidence,
            )
            self._append_locked(
                handle,
                self._transition_generation(
                    isolation_proof=proof,
                    incident_evidence=evidence,
                    control=control,
                ),
            )
            return control, evidence

    def append_repair(
        self,
        *,
        repaired_partition_ids: tuple[str, ...],
        authority_source_digests: tuple[str, ...],
        retained_conflicting_byte_digests: tuple[str, ...],
    ) -> ConflictRepairGeneration:
        with self._linearization.exclusive():
            return self._append_repair_unlocked(
                repaired_partition_ids=repaired_partition_ids,
                authority_source_digests=authority_source_digests,
                retained_conflicting_byte_digests=retained_conflicting_byte_digests,
            )

    def recover_and_release(
        self,
        *,
        repaired_partition_ids: tuple[str, ...],
        authority_source_digests: tuple[str, ...],
        retained_conflicting_byte_digests: tuple[str, ...],
        supplied_snapshot: ConflictRepositoryIntegritySnapshot,
        expected_control_digest: str,
    ) -> tuple[ConflictRepairGeneration, ConflictFreezeControlState]:
        """Build/verify, publish repair, and release under one root coordinate."""

        with self._linearization.exclusive():
            repair = self._append_repair_unlocked(
                repaired_partition_ids=repaired_partition_ids,
                authority_source_digests=authority_source_digests,
                retained_conflicting_byte_digests=(
                    retained_conflicting_byte_digests
                ),
            )
            control = self._release_unlocked(
                repair_generation_digest=repair.repair_generation_digest,
                supplied_snapshot=supplied_snapshot,
                expected_control_digest=expected_control_digest,
            )
            return repair, control

    def _append_repair_unlocked(
        self,
        *,
        repaired_partition_ids: tuple[str, ...],
        authority_source_digests: tuple[str, ...],
        retained_conflicting_byte_digests: tuple[str, ...],
    ) -> ConflictRepairGeneration:
        repaired = _canonical_identifiers(repaired_partition_ids, nonempty=True)
        authority = _canonical_digests(authority_source_digests, nonempty=True)
        retained = _canonical_digests(retained_conflicting_byte_digests, nonempty=True)
        current, proof, _, latest_evidence = self._replay(self._read_all())
        if (
            current is None
            or proof is None
            or latest_evidence is None
            or not set(repaired) <= set(current.frozen_partition_ids)
        ):
            raise ConflictIntegrityError("invalid_repair_generation")
        expected_control_digest = current.control_digest
        expected_proof_digest = proof.proof_digest
        expected_evidence_digest = latest_evidence.evidence_digest
        verifier = self._clean_replay_verifier
        if verifier is None:
            raise ConflictIntegrityError("clean_replay_verifier_unavailable")
        try:
            verification = ConflictCleanReplayVerification.model_validate(
                verifier(repaired, retained, authority).model_dump(mode="python")
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise ConflictIntegrityError("clean_replay_verification_failed") from exc
        if (
            verification.repository_id != self._repository_id
            or verification.repaired_partition_ids != repaired
            or verification.retained_conflicting_byte_digests != retained
            or verification.authority_source_digests != authority
        ):
            raise ConflictIntegrityError("clean_replay_verification_failed")
        with self._path.open("r+", encoding="utf-8") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            current, proof, repairs, latest_evidence = self._replay(
                self._decode_lines(tuple(handle))
            )
            if (
                current is None
                or proof is None
                or latest_evidence is None
                or not set(repaired) <= set(current.frozen_partition_ids)
                or current.control_digest != expected_control_digest
                or proof.proof_digest != expected_proof_digest
                or latest_evidence.evidence_digest != expected_evidence_digest
            ):
                raise ConflictIntegrityError("invalid_repair_generation")
            if isinstance(proof, ConflictScopeIsolationProof):
                isolation_digest = proof.proof_digest
            else:
                isolation_digest = self._latest_isolation_digest(self._decode_lines_from_handle(handle))
            payload: _RepairPayload = {
                "repair_generation_id": token_hex(16),
                "repository_id": self._repository_id,
                "predecessor_isolation_proof_digest": isolation_digest,
                "latest_incident_evidence_digest": latest_evidence.evidence_digest,
                "repaired_partition_ids": repaired,
                "authority_source_digests": authority,
                "retained_conflicting_byte_digests": retained,
                "clean_generation_id": verification.clean_generation_id,
                "clean_generation_digest": verification.clean_generation_digest,
                "retained_corrupt_generation_digest": (
                    verification.retained_corrupt_generation_digest
                ),
                "replay_start_event_batch_sequence": verification.replay_start_event_batch_sequence,
                "replay_final_event_batch_sequence": verification.replay_final_event_batch_sequence,
                "replay_final_batch_digest": verification.replay_final_batch_digest,
                "replay_repository_state_digest": verification.replay_repository_state_digest,
                "completed_at": self._now(),
            }
            provisional = ConflictRepairGeneration.model_construct(**payload, repair_generation_digest="0" * 64)
            repair = ConflictRepairGeneration(
                **payload,
                repair_generation_digest=_digest(
                    _REPAIR_GENERATION_DOMAIN,
                    provisional.model_dump(mode="json", exclude={"repair_generation_digest"}),
                ),
            )
            if repair.repair_generation_digest in repairs:
                raise ConflictIntegrityError("duplicate_repair_generation")
            self._append_locked(handle, self._repair_entry(repair))
            return repair

    def release(
        self,
        *,
        repair_generation_digest: str,
        supplied_snapshot: ConflictRepositoryIntegritySnapshot,
        expected_control_digest: str,
    ) -> ConflictFreezeControlState:
        with self._linearization.exclusive():
            return self._release_unlocked(
                repair_generation_digest=repair_generation_digest,
                supplied_snapshot=supplied_snapshot,
                expected_control_digest=expected_control_digest,
            )

    def _release_unlocked(
        self,
        *,
        repair_generation_digest: str,
        supplied_snapshot: ConflictRepositoryIntegritySnapshot,
        expected_control_digest: str,
    ) -> ConflictFreezeControlState:
        authoritative = self._authoritative_snapshot()
        with self._path.open("r+", encoding="utf-8") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            current, proof, repairs, latest_evidence = self._replay(
                self._decode_lines(tuple(handle))
            )
            if (
                current is None
                or proof is None
                or latest_evidence is None
                or current.control_digest != expected_control_digest
            ):
                raise ConflictIntegrityError("stale_freeze_control")
            if not self._snapshot_matches(supplied_snapshot, authoritative):
                raise ConflictIntegrityError("invalid_release_proof")
            repair = repairs.get(_digest_field(repair_generation_digest))
            if repair is None or repair.repository_id != self._repository_id:
                raise ConflictIntegrityError("invalid_release_proof")
            if repair.latest_incident_evidence_digest != latest_evidence.evidence_digest:
                raise ConflictIntegrityError("invalid_release_proof")
            verifier = self._clean_replay_verifier
            if verifier is None:
                raise ConflictIntegrityError("invalid_release_proof")
            try:
                verification = ConflictCleanReplayVerification.model_validate(
                    verifier(
                        repair.repaired_partition_ids,
                        repair.retained_conflicting_byte_digests,
                        repair.authority_source_digests,
                    ).model_dump(mode="python")
                )
            except (AttributeError, TypeError, ValueError) as exc:
                raise ConflictIntegrityError("invalid_release_proof") from exc
            if (
                verification.authority_source_digests
                != repair.authority_source_digests
                or
                verification.clean_generation_id != repair.clean_generation_id
                or verification.clean_generation_digest != repair.clean_generation_digest
                or verification.retained_corrupt_generation_digest
                != repair.retained_corrupt_generation_digest
                or verification.replay_final_event_batch_sequence
                != repair.replay_final_event_batch_sequence
                or verification.replay_final_batch_digest != repair.replay_final_batch_digest
                or verification.replay_repository_state_digest
                != repair.replay_repository_state_digest
            ):
                raise ConflictIntegrityError("invalid_release_proof")
            released = set(repair.repaired_partition_ids)
            previous = set(current.frozen_partition_ids)
            if not released <= previous:
                raise ConflictIntegrityError("invalid_release_proof")
            remaining = previous - released
            payload: _ReleasePayload = {
                "proof_id": token_hex(16),
                "repository_id": self._repository_id,
                "predecessor_proof_digest": proof.proof_digest,
                "predecessor_proof_revision": proof.proof_revision,
                "previous_frozen_partition_ids": tuple(sorted(previous)),
                "released_partition_ids": tuple(sorted(released)),
                "remaining_frozen_partition_ids": tuple(sorted(remaining)),
                "repair_generation_digest": repair.repair_generation_digest,
                "clean_generation_digest": repair.clean_generation_digest,
                "retained_corrupt_generation_digest": (
                    repair.retained_corrupt_generation_digest
                ),
                "clean_replay_final_event_batch_sequence": repair.replay_final_event_batch_sequence,
                "clean_replay_final_batch_digest": repair.replay_final_batch_digest,
                "clean_replay_repository_state_digest": repair.replay_repository_state_digest,
                "store_topology_fingerprint": authoritative.store_topology_fingerprint,
                "proof_revision": proof.proof_revision + 1,
            }
            release, control = self._release_proof_and_control(payload, current)
            self._append_locked(handle, self._transition_generation(release_proof=release, control=control))
            return control

    def _authoritative_snapshot(self) -> ConflictRepositoryIntegritySnapshot:
        snapshot = self._snapshot_provider()
        try:
            validated = ConflictRepositoryIntegritySnapshot.model_validate(snapshot.model_dump(mode="python"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise ConflictIntegrityError("repository_snapshot_unavailable") from exc
        if validated.repository_id != self._repository_id:
            raise ConflictIntegrityError("repository_snapshot_unavailable")
        return validated

    @staticmethod
    def _snapshot_matches(
        supplied: ConflictRepositoryIntegritySnapshot | None,
        authoritative: ConflictRepositoryIntegritySnapshot,
    ) -> bool:
        if supplied is None:
            return False
        try:
            validated = ConflictRepositoryIntegritySnapshot.model_validate(supplied.model_dump(mode="python"))
        except (AttributeError, TypeError, ValueError):
            return False
        return validated == authoritative

    @staticmethod
    def _derive_impacted(
        snapshot: ConflictRepositoryIntegritySnapshot,
        conflicting: tuple[str, ...],
    ) -> set[str]:
        impacted: set[str] = set()
        for digest in conflicting:
            matches = [
                partition.partition_id
                for partition in snapshot.partitions
                if digest in partition.retained_byte_digests
            ]
            if len(matches) != 1:
                return set()
            impacted.add(matches[0])
        return impacted

    def _isolation_proof_and_control(
        self,
        payload: _IsolationPayload,
        current: ConflictFreezeControlState | None,
    ) -> tuple[ConflictScopeIsolationProof, ConflictFreezeControlState]:
        provisional = ConflictScopeIsolationProof.model_construct(
            **payload,
            resulting_freeze_control_digest="0" * 64,
            proof_digest="0" * 64,
        )
        proof_digest = _proof_digest(_ISOLATION_PROOF_DOMAIN, provisional)
        control_payload: _ControlPayload = {
            "repository_id": self._repository_id,
            "frozen_partition_ids": payload["frozen_partition_ids"],
            "authority_proof_digest": proof_digest,
            "control_revision": payload["proof_revision"],
            "predecessor_control_digest": None if current is None else current.control_digest,
        }
        control = self._control(control_payload)
        return ConflictScopeIsolationProof(
            **payload,
            resulting_freeze_control_digest=control.control_digest,
            proof_digest=proof_digest,
        ), control

    def _release_proof_and_control(
        self,
        payload: _ReleasePayload,
        current: ConflictFreezeControlState,
    ) -> tuple[ConflictScopeReleaseProof, ConflictFreezeControlState]:
        provisional = ConflictScopeReleaseProof.model_construct(
            **payload,
            resulting_freeze_control_digest="0" * 64,
            proof_digest="0" * 64,
        )
        proof_digest = _proof_digest(_RELEASE_PROOF_DOMAIN, provisional)
        control_payload: _ControlPayload = {
            "repository_id": self._repository_id,
            "frozen_partition_ids": payload["remaining_frozen_partition_ids"],
            "authority_proof_digest": proof_digest,
            "control_revision": payload["proof_revision"],
            "predecessor_control_digest": current.control_digest,
        }
        control = self._control(control_payload)
        return ConflictScopeReleaseProof(
            **payload,
            resulting_freeze_control_digest=control.control_digest,
            proof_digest=proof_digest,
        ), control

    def _incident_evidence(
        self,
        *,
        control: ConflictFreezeControlState,
        conflicting: tuple[str, ...],
        snapshot: ConflictRepositoryIntegritySnapshot,
        predecessor: ConflictIntegrityIncidentEvidence | None,
    ) -> ConflictIntegrityIncidentEvidence:
        payload = {
            "incident_evidence_id": token_hex(16),
            "repository_id": self._repository_id,
            "freeze_control_digest": control.control_digest,
            "authority_proof_digest": control.authority_proof_digest,
            "frozen_partition_ids": control.frozen_partition_ids,
            "conflicting_byte_digests": conflicting,
            "repository_snapshot_digest": snapshot.snapshot_digest,
            "predecessor_incident_evidence_digest": (
                None if predecessor is None else predecessor.evidence_digest
            ),
            "recorded_at": self._now(),
        }
        provisional = ConflictIntegrityIncidentEvidence.model_construct(
            **payload, evidence_digest="0" * 64
        )
        return ConflictIntegrityIncidentEvidence(
            **payload,
            evidence_digest=_digest(
                _INCIDENT_EVIDENCE_DOMAIN,
                provisional.model_dump(mode="json", exclude={"evidence_digest"}),
            ),
        )

    @staticmethod
    def _control(payload: _ControlPayload) -> ConflictFreezeControlState:
        provisional = ConflictFreezeControlState.model_construct(**payload, control_digest="0" * 64)
        return ConflictFreezeControlState(
            **payload,
            control_digest=_digest(
                _CONTROL_DOMAIN,
                provisional.model_dump(mode="json", exclude={"control_digest"}),
            ),
        )

    @staticmethod
    def _transition_generation(
        *,
        control: ConflictFreezeControlState,
        isolation_proof: ConflictScopeIsolationProof | None = None,
        release_proof: ConflictScopeReleaseProof | None = None,
        incident_evidence: ConflictIntegrityIncidentEvidence | None = None,
    ) -> _IntegrityTransitionGeneration:
        payload = {
            "isolation_proof": isolation_proof,
            "release_proof": release_proof,
            "incident_evidence": incident_evidence,
            "control": control,
        }
        provisional = _IntegrityTransitionGeneration.model_construct(**payload, generation_digest="0" * 64)
        return _IntegrityTransitionGeneration(
            **payload,
            generation_digest=_digest(
                _GENERATION_DOMAIN,
                provisional.model_dump(mode="json", exclude={"generation_digest"}),
            ),
        )

    @staticmethod
    def _incident_entry(
        evidence: ConflictIntegrityIncidentEvidence,
    ) -> _IncidentEvidenceEntry:
        provisional = _IncidentEvidenceEntry.model_construct(
            evidence=evidence, generation_digest="0" * 64
        )
        return _IncidentEvidenceEntry(
            evidence=evidence,
            generation_digest=_digest(
                _GENERATION_DOMAIN,
                provisional.model_dump(mode="json", exclude={"generation_digest"}),
            ),
        )

    @staticmethod
    def _repair_entry(repair: ConflictRepairGeneration) -> _RepairGenerationEntry:
        provisional = _RepairGenerationEntry.model_construct(repair=repair, generation_digest="0" * 64)
        return _RepairGenerationEntry(
            repair=repair,
            generation_digest=_digest(
                _GENERATION_DOMAIN,
                provisional.model_dump(mode="json", exclude={"generation_digest"}),
            ),
        )

    def _replay(
        self,
        entries: list[_IntegrityEntry],
    ) -> tuple[
        ConflictFreezeControlState | None,
        ConflictScopeIsolationProof | ConflictScopeReleaseProof | None,
        dict[str, ConflictRepairGeneration],
        ConflictIntegrityIncidentEvidence | None,
    ]:
        current: ConflictFreezeControlState | None = None
        proof: ConflictScopeIsolationProof | ConflictScopeReleaseProof | None = None
        repairs: dict[str, ConflictRepairGeneration] = {}
        latest_evidence: ConflictIntegrityIncidentEvidence | None = None
        for entry in entries:
            if isinstance(entry, _IncidentEvidenceEntry):
                evidence = entry.evidence
                if (
                    current is None
                    or proof is None
                    or evidence.repository_id != self._repository_id
                    or evidence.freeze_control_digest != current.control_digest
                    or evidence.authority_proof_digest != proof.proof_digest
                    or evidence.predecessor_incident_evidence_digest
                    != (None if latest_evidence is None else latest_evidence.evidence_digest)
                ):
                    raise ConflictIntegrityError("conflict_integrity_corrupt")
                latest_evidence = evidence
                continue
            if isinstance(entry, _RepairGenerationEntry):
                repair = entry.repair
                if (
                    latest_evidence is None
                    or repair.repository_id != self._repository_id
                    or repair.repair_generation_digest in repairs
                    or repair.latest_incident_evidence_digest != latest_evidence.evidence_digest
                ):
                    raise ConflictIntegrityError("conflict_integrity_corrupt")
                repairs[repair.repair_generation_digest] = repair
                continue
            next_control = entry.control
            next_proof = entry.isolation_proof or entry.release_proof
            if next_proof is None:
                raise ConflictIntegrityError("conflict_integrity_corrupt")
            if next_control.repository_id != self._repository_id:
                raise ConflictIntegrityError("conflict_integrity_corrupt")
            if current is None:
                if next_control.control_revision != 1 or next_control.predecessor_control_digest is not None:
                    raise ConflictIntegrityError("conflict_integrity_corrupt")
            elif (
                next_control.control_revision != current.control_revision + 1
                or next_control.predecessor_control_digest != current.control_digest
                or next_proof.predecessor_proof_digest != (None if proof is None else proof.proof_digest)
            ):
                raise ConflictIntegrityError("conflict_integrity_corrupt")
            if isinstance(next_proof, ConflictScopeReleaseProof):
                repair = repairs.get(next_proof.repair_generation_digest)
                if (
                    repair is None
                    or set(repair.repaired_partition_ids)
                    != set(next_proof.released_partition_ids)
                    or repair.clean_generation_digest != next_proof.clean_generation_digest
                    or repair.retained_corrupt_generation_digest
                    != next_proof.retained_corrupt_generation_digest
                ):
                    raise ConflictIntegrityError("conflict_integrity_corrupt")
            elif (
                entry.incident_evidence is None
                or entry.incident_evidence.freeze_control_digest != next_control.control_digest
                or entry.incident_evidence.authority_proof_digest != next_proof.proof_digest
                or entry.incident_evidence.predecessor_incident_evidence_digest
                != (None if latest_evidence is None else latest_evidence.evidence_digest)
            ):
                raise ConflictIntegrityError("conflict_integrity_corrupt")
            current = next_control
            proof = next_proof
            if entry.incident_evidence is not None:
                latest_evidence = entry.incident_evidence
        return current, proof, repairs, latest_evidence

    def _read_all(self) -> list[_IntegrityEntry]:
        try:
            with self._path.open("r", encoding="utf-8") as handle:
                fcntl.flock(handle, fcntl.LOCK_SH)
                return self._decode_lines(tuple(handle))
        except (OSError, TypeError, ValueError) as exc:
            raise ConflictIntegrityError("conflict_integrity_corrupt") from exc

    @staticmethod
    def _decode_lines(lines: tuple[str, ...]) -> list[_IntegrityEntry]:
        entries: list[_IntegrityEntry] = []
        for line in lines:
            wire = line.rstrip("\n")
            if not wire:
                raise ValueError("blank integrity ledger line")
            decoded = json.loads(wire)
            canonical = json.dumps(decoded, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            if wire != canonical or not isinstance(decoded, dict):
                raise ValueError("noncanonical integrity ledger line")
            if decoded.get("record_type") == "integrity_transition":
                entries.append(_IntegrityTransitionGeneration.model_validate_json(wire))
            elif decoded.get("record_type") == "repair_generation":
                entries.append(_RepairGenerationEntry.model_validate_json(wire))
            elif decoded.get("record_type") == "incident_evidence":
                entries.append(_IncidentEvidenceEntry.model_validate_json(wire))
            else:
                raise ValueError("unknown integrity ledger record")
        return entries

    @staticmethod
    def _append_locked(handle: object, value: BaseModel) -> None:
        wire = json.dumps(value.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        handle.seek(0, os.SEEK_END)  # type: ignore[attr-defined]
        handle.write(wire + "\n")  # type: ignore[attr-defined]
        handle.flush()  # type: ignore[attr-defined]
        os.fsync(handle.fileno())  # type: ignore[attr-defined]

    @staticmethod
    def _decode_lines_from_handle(handle: object) -> list[_IntegrityEntry]:
        handle.seek(0)  # type: ignore[attr-defined]
        return FileConflictIntegrityRepository._decode_lines(tuple(handle))  # type: ignore[arg-type]

    @staticmethod
    def _latest_isolation_digest(entries: list[_IntegrityEntry]) -> str:
        for entry in reversed(entries):
            if isinstance(entry, _IntegrityTransitionGeneration) and entry.isolation_proof is not None:
                return entry.isolation_proof.proof_digest
        raise ConflictIntegrityError("conflict_integrity_corrupt")
