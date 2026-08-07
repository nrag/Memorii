"""Memory-plane storage contracts and in-memory/JSONL implementations."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from secrets import token_bytes
from threading import RLock
from typing import Annotated, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_plane.file_lock import locked_file
from memorii.core.memory_plane.models import CanonicalMemoryRecord, MemoryRecordFence
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility

SEMANTIC_CHECKPOINT_SECRET_PURPOSE = "semantic-ingestion-replay-checkpoint-signing"
_SEMANTIC_CHECKPOINT_KEY_ID = "semantic-ingestion-checkpoint-key"
_SEMANTIC_CHECKPOINT_SIGNATURE_DOMAIN = b"memorii.semantic-replay-checkpoint-signature.v1\0"


@runtime_checkable
class CheckpointSignatureAuthority(Protocol):
    """Opaque backend-owned signer/verifier without raw-key access."""

    @property
    def key_id(self) -> str: ...

    @property
    def public_key_fingerprint(self) -> str: ...

    def sign_checkpoint_digest(self, checkpoint_digest: str) -> str: ...

    def verify_checkpoint_signature(
        self,
        checkpoint_digest: str,
        signature: str,
    ) -> bool: ...


class _BackendCheckpointSignatureAuthority:
    __slots__ = ("_secret",)

    def __init__(self, secret: bytes) -> None:
        self._secret = secret

    @property
    def key_id(self) -> str:
        return _SEMANTIC_CHECKPOINT_KEY_ID

    @property
    def public_key_fingerprint(self) -> str:
        return hashlib.sha256(self._secret).hexdigest()

    def sign_checkpoint_digest(self, checkpoint_digest: str) -> str:
        return hmac.new(
            self._secret,
            _SEMANTIC_CHECKPOINT_SIGNATURE_DOMAIN + checkpoint_digest.encode("ascii"),
            hashlib.sha256,
        ).hexdigest()

    def verify_checkpoint_signature(
        self,
        checkpoint_digest: str,
        signature: str,
    ) -> bool:
        return hmac.compare_digest(
            self.sign_checkpoint_digest(checkpoint_digest),
            signature,
        )


class MemoryPlaneRevisionConflictError(RuntimeError):
    """Raised when a unit of work commits against a stale store revision."""


class MemoryPlaneCorruptionError(RuntimeError):
    """Raised when persisted memory cannot be replayed without data loss."""


class MemoryPlaneGovernedWritePolicyRequiredError(RuntimeError):
    """A governed namespace was written without its installed policy."""


class MemoryPlaneWriteAuthorization:
    """Opaque authorization owned by a feature policy, not the memory plane."""


class GovernedWritePolicy(Protocol):
    def validate(
        self,
        records: tuple[CanonicalMemoryRecord, ...],
        current: tuple[CanonicalMemoryRecord, ...],
        authorization: MemoryPlaneWriteAuthorization | None,
    ) -> None: ...


class RecordAbsentPrecondition(BaseModel):
    kind: Literal["record_absent"] = "record_absent"
    memory_id: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid", frozen=True)


class RecordDigestPrecondition(BaseModel):
    kind: Literal["record_digest"] = "record_digest"
    memory_id: str = Field(min_length=1)
    expected_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)


class RecordFencePrecondition(BaseModel):
    kind: Literal["record_fence"] = "record_fence"
    memory_id: str = Field(min_length=1)
    expected_fence: MemoryRecordFence

    model_config = ConfigDict(extra="forbid", frozen=True)


MemoryPlanePrecondition = Annotated[
    RecordAbsentPrecondition | RecordDigestPrecondition | RecordFencePrecondition,
    Field(discriminator="kind"),
]


class _PersistedBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: int
    data_revision: int = Field(ge=0)
    records: tuple[CanonicalMemoryRecord, ...]
    checksum: str = Field(pattern=r"^[0-9a-f]{64}$")

    @classmethod
    def create(
        cls,
        *,
        revision: int,
        data_revision: int,
        records: tuple[CanonicalMemoryRecord, ...],
    ) -> _PersistedBatch:
        return cls(
            revision=revision,
            data_revision=data_revision,
            records=records,
            checksum=_batch_checksum(revision, data_revision, records),
        )

    @model_validator(mode="after")
    def validate_checksum(self) -> _PersistedBatch:
        if self.checksum != _batch_checksum(self.revision, self.data_revision, self.records):
            raise ValueError("memory-plane batch checksum mismatch")
        return self


class MemoryPlaneStore(Protocol):
    @property
    def durable(self) -> bool: ...

    def load_or_create_protected_secret(self, *, purpose: str, length: int) -> bytes: ...

    def write_records(
        self, records: tuple[CanonicalMemoryRecord, ...], *, authorization: MemoryPlaneWriteAuthorization | None = None
    ) -> int: ...

    def stage_record(
        self,
        record: CanonicalMemoryRecord,
        *,
        authorization: MemoryPlaneWriteAuthorization | None = None,
    ) -> None: ...

    def upsert_record(
        self,
        record: CanonicalMemoryRecord,
        *,
        authorization: MemoryPlaneWriteAuthorization | None = None,
    ) -> None: ...

    def install_governed_write_policy(self, policy: GovernedWritePolicy) -> None: ...

    def revision(self) -> int: ...

    def apply_batch(
        self,
        records: tuple[CanonicalMemoryRecord, ...],
        *,
        expected_revision: int | None,
        preconditions: tuple[MemoryPlanePrecondition, ...] = (),
        authorization: MemoryPlaneWriteAuthorization | None = None,
        transaction_precondition: Callable[[], None] | None = None,
    ) -> int: ...

    def read_snapshot(self) -> tuple[int, tuple[CanonicalMemoryRecord, ...]]: ...

    def get_record(self, memory_id: str) -> CanonicalMemoryRecord | None: ...

    def list_records(
        self,
        *,
        status: CommitStatus | None = None,
        domains: list[MemoryDomain] | None = None,
        source_kind: str | None = None,
    ) -> list[CanonicalMemoryRecord]: ...


class InMemoryMemoryPlaneStore:
    def __init__(self) -> None:
        self._records: dict[str, CanonicalMemoryRecord] = {}
        self._revision = 0
        self._lock = RLock()
        self._governed_write_policy: GovernedWritePolicy | None = None
        self._protected_secrets: dict[str, bytes] = {}
        self._checkpoint_signature_owner: object | None = None
        self._checkpoint_signature_authority: _BackendCheckpointSignatureAuthority | None = None

    @property
    def durable(self) -> bool:
        return False

    def load_or_create_protected_secret(self, *, purpose: str, length: int) -> bytes:
        if purpose == SEMANTIC_CHECKPOINT_SECRET_PURPOSE:
            raise PermissionError("checkpoint signing material is backend-private")
        return self._load_or_create_protected_secret(
            purpose=purpose,
            length=length,
        )

    def _load_or_create_protected_secret(
        self,
        *,
        purpose: str,
        length: int,
    ) -> bytes:
        if not purpose or length < 32:
            raise ValueError("protected secret purpose or length is invalid")
        with self._lock:
            secret = self._protected_secrets.get(purpose)
            if secret is None:
                secret = token_bytes(length)
                self._protected_secrets[purpose] = secret
            if len(secret) != length:
                raise MemoryPlaneCorruptionError("protected secret length changed")
            return bytes(secret)

    def _claim_semantic_checkpoint_signature_authority(
        self,
        *,
        owner: object,
    ) -> CheckpointSignatureAuthority:
        with self._lock:
            if self._checkpoint_signature_owner is None:
                self._checkpoint_signature_owner = owner
            elif self._checkpoint_signature_owner is not owner:
                raise PermissionError("checkpoint signing authority is already owned")
            if self._checkpoint_signature_authority is None:
                secret = self._load_or_create_protected_secret(
                    purpose=SEMANTIC_CHECKPOINT_SECRET_PURPOSE,
                    length=32,
                )
                self._checkpoint_signature_authority = _BackendCheckpointSignatureAuthority(secret)
            return self._checkpoint_signature_authority

    def install_governed_write_policy(self, policy: GovernedWritePolicy) -> None:
        self._governed_write_policy = policy

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
        self, records: tuple[CanonicalMemoryRecord, ...], *, authorization: MemoryPlaneWriteAuthorization | None = None
    ) -> int:
        with self._lock:
            return self._apply_locked(records, preconditions=(), authorization=authorization)

    def revision(self) -> int:
        with self._lock:
            return self._revision

    def apply_batch(
        self,
        records: tuple[CanonicalMemoryRecord, ...],
        *,
        expected_revision: int | None,
        preconditions: tuple[MemoryPlanePrecondition, ...] = (),
        authorization: MemoryPlaneWriteAuthorization | None = None,
        transaction_precondition: Callable[[], None] | None = None,
    ) -> int:
        with self._lock:
            if transaction_precondition is not None:
                transaction_precondition()
            if expected_revision is not None and expected_revision != self._revision:
                raise MemoryPlaneRevisionConflictError(
                    f"memory-plane revision changed: expected {expected_revision}, actual {self._revision}"
                )
            return self._apply_locked(records, preconditions=preconditions, authorization=authorization)

    def _apply_locked(
        self,
        records: tuple[CanonicalMemoryRecord, ...],
        *,
        preconditions: tuple[MemoryPlanePrecondition, ...],
        authorization: MemoryPlaneWriteAuthorization | None,
    ) -> int:
        _validate_preconditions(self._records, preconditions)
        _validate_governed_write(
            self._governed_write_policy,
            records,
            tuple(self._records.values()),
            authorization,
        )
        updated = dict(self._records)
        for record in records:
            updated[record.memory_id] = _clone_record(record)
        self._records = updated
        if _contains_runtime_context(records):
            self._revision += 1
        return self._revision

    def read_snapshot(self) -> tuple[int, tuple[CanonicalMemoryRecord, ...]]:
        with self._lock:
            return self._revision, tuple(_clone_record(record) for record in self._records.values())

    def get_record(self, memory_id: str) -> CanonicalMemoryRecord | None:
        with self._lock:
            record = self._records.get(memory_id)
            return _clone_record(record) if record is not None else None

    def list_records(
        self,
        *,
        status: CommitStatus | None = None,
        domains: list[MemoryDomain] | None = None,
        source_kind: str | None = None,
    ) -> list[CanonicalMemoryRecord]:
        domain_set = set(domains) if domains is not None else None
        with self._lock:
            return [
                _clone_record(item)
                for item in self._records.values()
                if (status is None or item.status == status)
                and (domain_set is None or item.domain in domain_set)
                and (source_kind is None or item.source_kind == source_kind)
            ]


class JsonlMemoryPlaneStore:
    def __init__(self, path: str | Path) -> None:
        self._base_path = Path(path)
        self._records_path = self._base_path / "memory_records.jsonl"
        self._lock_path = self._base_path / "memory_records.lock"
        self._base_path.mkdir(parents=True, exist_ok=True)
        self._governed_write_policy: GovernedWritePolicy | None = None
        self._checkpoint_signature_owner: object | None = None
        self._checkpoint_signature_authority: _BackendCheckpointSignatureAuthority | None = None

    @property
    def durable(self) -> bool:
        return True

    def load_or_create_protected_secret(self, *, purpose: str, length: int) -> bytes:
        if purpose == SEMANTIC_CHECKPOINT_SECRET_PURPOSE:
            raise PermissionError("checkpoint signing material is backend-private")
        return self._load_or_create_protected_secret(
            purpose=purpose,
            length=length,
        )

    def _load_or_create_protected_secret(
        self,
        *,
        purpose: str,
        length: int,
    ) -> bytes:
        if not purpose or length < 32:
            raise ValueError("protected secret purpose or length is invalid")
        protected = self._base_path / ".protected"
        secret_path = protected / f"{hashlib.sha256(purpose.encode('utf-8')).hexdigest()}.key"
        with self._locked(exclusive=True):
            protected.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.chmod(protected, 0o700)
            if secret_path.exists():
                try:
                    mode = secret_path.stat().st_mode & 0o777
                    secret = secret_path.read_bytes()
                except OSError as exc:
                    raise MemoryPlaneCorruptionError("protected secret is unreadable") from exc
                if mode & 0o077 or len(secret) != length:
                    raise MemoryPlaneCorruptionError("protected secret permissions or length are invalid")
                return secret
            secret = token_bytes(length)
            descriptor = os.open(
                secret_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            try:
                written = os.write(descriptor, secret)
                if written != len(secret):
                    raise OSError("partial protected-secret write")
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            _fsync_directory(protected)
            return secret

    def _claim_semantic_checkpoint_signature_authority(
        self,
        *,
        owner: object,
    ) -> CheckpointSignatureAuthority:
        if self._checkpoint_signature_owner is None:
            self._checkpoint_signature_owner = owner
        elif self._checkpoint_signature_owner is not owner:
            raise PermissionError("checkpoint signing authority is already owned")
        if self._checkpoint_signature_authority is None:
            secret = self._load_or_create_protected_secret(
                purpose=SEMANTIC_CHECKPOINT_SECRET_PURPOSE,
                length=32,
            )
            self._checkpoint_signature_authority = _BackendCheckpointSignatureAuthority(secret)
        return self._checkpoint_signature_authority

    def install_governed_write_policy(self, policy: GovernedWritePolicy) -> None:
        self._governed_write_policy = policy

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
        self, records: tuple[CanonicalMemoryRecord, ...], *, authorization: MemoryPlaneWriteAuthorization | None = None
    ) -> int:
        with self._locked(exclusive=True):
            batches = self._read_batches_unlocked()
            _validate_governed_write(
                self._governed_write_policy,
                records,
                tuple(_records_from_batches(batches).values()),
                authorization,
            )
            next_revision = batches[-1].revision + 1 if batches else 1
            current_data_revision = batches[-1].data_revision if batches else 0
            next_data_revision = current_data_revision + int(_contains_runtime_context(records))
            self._replace_batches(
                [
                    *batches,
                    _PersistedBatch.create(
                        revision=next_revision,
                        data_revision=next_data_revision,
                        records=records,
                    ),
                ]
            )
            return next_data_revision

    def revision(self) -> int:
        with self._locked(exclusive=False):
            batches = self._read_batches_unlocked()
            return batches[-1].data_revision if batches else 0

    def apply_batch(
        self,
        records: tuple[CanonicalMemoryRecord, ...],
        *,
        expected_revision: int | None,
        preconditions: tuple[MemoryPlanePrecondition, ...] = (),
        authorization: MemoryPlaneWriteAuthorization | None = None,
        transaction_precondition: Callable[[], None] | None = None,
    ) -> int:
        with self._locked(exclusive=True):
            if transaction_precondition is not None:
                transaction_precondition()
            batches = self._read_batches_unlocked()
            actual_revision = batches[-1].revision if batches else 0
            actual_data_revision = batches[-1].data_revision if batches else 0
            if expected_revision is not None and expected_revision != actual_data_revision:
                raise MemoryPlaneRevisionConflictError(
                    f"memory-plane revision changed: expected {expected_revision}, actual {actual_data_revision}"
                )
            _validate_preconditions(_records_from_batches(batches), preconditions)
            _validate_governed_write(
                self._governed_write_policy,
                records,
                tuple(_records_from_batches(batches).values()),
                authorization,
            )
            next_revision = actual_revision + 1
            next_data_revision = actual_data_revision + int(_contains_runtime_context(records))
            self._replace_batches(
                [
                    *batches,
                    _PersistedBatch.create(
                        revision=next_revision,
                        data_revision=next_data_revision,
                        records=records,
                    ),
                ]
            )
            return next_data_revision

    def read_snapshot(self) -> tuple[int, tuple[CanonicalMemoryRecord, ...]]:
        with self._locked(exclusive=False):
            batches = self._read_batches_unlocked()
            latest_by_id = _records_from_batches(batches)
            revision = batches[-1].data_revision if batches else 0
            return revision, tuple(_clone_record(record) for record in latest_by_id.values())

    def get_record(self, memory_id: str) -> CanonicalMemoryRecord | None:
        _, records = self.read_snapshot()
        return next((record for record in records if record.memory_id == memory_id), None)

    def list_records(
        self,
        *,
        status: CommitStatus | None = None,
        domains: list[MemoryDomain] | None = None,
        source_kind: str | None = None,
    ) -> list[CanonicalMemoryRecord]:
        domain_set = set(domains) if domains is not None else None
        _, records = self.read_snapshot()
        return [
            item
            for item in records
            if (status is None or item.status == status)
            and (domain_set is None or item.domain in domain_set)
            and (source_kind is None or item.source_kind == source_kind)
        ]

    def _read_batches_unlocked(self) -> list[_PersistedBatch]:
        batches: list[_PersistedBatch] = []
        expected_revision = 1
        for line_number, line in enumerate(self._iter_jsonl_lines_unlocked(), start=1):
            try:
                batch = _PersistedBatch.model_validate_json(line)
            except ValueError as exc:
                raise MemoryPlaneCorruptionError(f"invalid memory-plane batch at line {line_number}: {exc}") from exc
            if batch.revision != expected_revision:
                raise MemoryPlaneCorruptionError(
                    f"non-contiguous memory-plane revision: expected {expected_revision}, got {batch.revision}"
                )
            previous_data_revision = batches[-1].data_revision if batches else 0
            expected_data_revision = previous_data_revision + int(_contains_runtime_context(batch.records))
            if batch.data_revision != expected_data_revision:
                raise MemoryPlaneCorruptionError(
                    f"invalid memory-plane data revision: expected {expected_data_revision}, got {batch.data_revision}"
                )
            batches.append(batch)
            expected_revision += 1
        return batches

    def _iter_jsonl_lines_unlocked(self) -> list[str]:
        if not self._records_path.exists():
            return []
        try:
            content = self._records_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise MemoryPlaneCorruptionError(f"cannot read memory-plane log: {exc}") from exc
        if content and not content.endswith("\n"):
            raise MemoryPlaneCorruptionError("memory-plane log ends with an incomplete batch")
        return [line for line in content.splitlines() if line.strip()]

    def _replace_batches(self, batches: list[_PersistedBatch]) -> None:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=self._base_path,
            prefix=f".{self._records_path.name}.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                for batch in batches:
                    handle.write(batch.model_dump_json())
                    handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self._records_path)
            _fsync_directory(self._base_path)
        except BaseException:
            temporary_path.unlink(missing_ok=True)
            raise

    def _locked(self, *, exclusive: bool) -> AbstractContextManager[None]:
        return locked_file(self._lock_path, exclusive=exclusive)


def _clone_record(record: CanonicalMemoryRecord) -> CanonicalMemoryRecord:
    return record.model_copy(deep=True)


def _validate_governed_write(
    policy: GovernedWritePolicy | None,
    records: tuple[CanonicalMemoryRecord, ...],
    current: tuple[CanonicalMemoryRecord, ...],
    authorization: MemoryPlaneWriteAuthorization | None,
) -> None:
    if policy is not None:
        policy.validate(records, current, authorization)
        return
    from memorii.core.memory_plane.semantic_control import (
        SEMANTIC_PUBLIC_NON_AUTHORITY_SOURCE_KINDS,
        is_semantic_control_record,
    )

    writer_exists = any(existing.memory_id == "semantic_ingestion:writer_admission:current" for existing in current)
    if any(
        is_semantic_control_record(record)
        and not (not writer_exists and record.source_kind in SEMANTIC_PUBLIC_NON_AUTHORITY_SOURCE_KINDS)
        for record in records
    ):
        raise MemoryPlaneGovernedWritePolicyRequiredError(
            "semantic-ingestion governed write requires its installed policy"
        )


def record_digest(record: CanonicalMemoryRecord) -> str:
    payload = json.dumps(record.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _batch_checksum(
    revision: int,
    data_revision: int,
    records: tuple[CanonicalMemoryRecord, ...],
) -> str:
    payload = json.dumps(
        {
            "revision": revision,
            "data_revision": data_revision,
            "records": [record.model_dump(mode="json") for record in records],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _contains_runtime_context(records: tuple[CanonicalMemoryRecord, ...]) -> bool:
    return any(record.visibility == MemoryRecordVisibility.RUNTIME_CONTEXT for record in records)


def _records_from_batches(batches: list[_PersistedBatch]) -> dict[str, CanonicalMemoryRecord]:
    latest_by_id: dict[str, CanonicalMemoryRecord] = {}
    for batch in batches:
        for record in batch.records:
            latest_by_id[record.memory_id] = record
    return latest_by_id


def _validate_preconditions(
    records: dict[str, CanonicalMemoryRecord],
    preconditions: tuple[MemoryPlanePrecondition, ...],
) -> None:
    for precondition in preconditions:
        current = records.get(precondition.memory_id)
        if isinstance(precondition, RecordAbsentPrecondition):
            satisfied = current is None
        elif isinstance(precondition, RecordDigestPrecondition):
            satisfied = current is not None and record_digest(current) == precondition.expected_digest
        else:
            satisfied = current is not None and current.mutation_fence == precondition.expected_fence
        if not satisfied:
            raise MemoryPlaneRevisionConflictError(
                f"memory-plane precondition failed: {precondition.kind}:{precondition.memory_id}"
            )


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
