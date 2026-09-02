"""Canonical full-state semantic memory events and deterministic replay."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
from collections.abc import Callable, Iterable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, TypeAdapter, field_validator, model_validator

from memorii.core.memory_evolution.conflict_attention import (
    SemanticConflictReplayBinding,
)
from memorii.core.memory_evolution.graph_records import (
    AliasRevision,
    CitationRecord,
    ClaimProjection,
    EntityRevision,
    NonOwningGraphRecord,
    ProvenanceRecord,
    ReferenceDispositionRecord,
    RelationRevision,
    TypeEvidence,
    graph_record_id,
)
from memorii.core.memory_evolution.ingestion_contracts import (
    CanonicalTypedValueError,
    decode_typed_value,
    encode_typed_value,
    normalize_delivery_id,
)
from memorii.core.memory_evolution.projection_binding import (
    ProjectionHistoryReplayBinding,
)
from memorii.core.semantic_ingestion.canonical_evidence_arena import (
    certified_instance,
    deeply_immutable_type,
    record_certified_instance,
)
from memorii.core.semantic_ingestion.contracts import (
    ActionRevision,
    ClaimAssertion,
    IdentityLineageRecord,
    IndependentSourceAnalysis,
    SemanticArtifactClosure,
    SemanticCandidate,
    SemanticExecutionLineage,
    SemanticGraphDelta,
    SemanticObservationDelta,
    SemanticRecoveryAuthorityBinding,
    SemanticRetryableProgress,
    SemanticTerminalOutcome,
    TemporalTransitionRecord,
    contract_digest,
    decode_semantic_contract,
)

CURRENT_SEMANTIC_EVENT_SCHEMA_VERSION = "memorii.semantic-memory-event.v1"
SEMANTIC_MEMORY_EVENT_TYPE = "memorii.semantic_ingestion.memory_mutation"
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_EVENT_DOMAIN = b"memorii.event-envelope.v1\0"
_POSITION_DOMAIN = b"memorii.event-batch-position.v1\0"
_BATCH_DOMAIN = b"memorii.semantic-memory-event-batch.v1\0"
_EVENT_ID_DOMAIN = b"memorii.semantic-memory-event-id.v1\0"
_DEDUPE_DOMAIN = b"memorii.semantic-memory-event-dedupe.v1\0"
_MUTATION_DOMAIN = b"memorii.semantic-memory-logical-mutation.v1\0"
_SUPPORT_DOMAIN = b"memorii.semantic-event-schema-support.v1\0"
_REGISTRY_DOMAIN = b"memorii.semantic-event-schema-registry.v1\0"
_REGISTRY_HISTORY_DOMAIN = b"memorii.semantic-event-schema-registry-history.v1\0"
_STATE_DOMAIN = b"memorii.semantic-replay-state.v1\0"
_CHECKPOINT_POSITION_DOMAIN = b"memorii.semantic-replay-checkpoint.v1\0"
_CHECKPOINT_POLICY_DOMAIN = b"memorii.semantic-replay-checkpoint-trust-policy.v1\0"
_CHECKPOINT_KEY_DOMAIN = b"memorii.semantic-replay-checkpoint-key.v1\0"
_CHECKPOINT_BUNDLE_DOMAIN = b"memorii.semantic-replay-checkpoint-bundle.v1\0"
_CHECKPOINT_LIFECYCLE_DOMAIN = b"memorii.semantic-replay-checkpoint-lifecycle.v1\0"
_REPLAY_AUTHORITY_MEMBER_DOMAIN = b"memorii.semantic-replay-authority-member.v1\0"
_REPLAY_AUTHORITY_AGGREGATE_DOMAIN = b"memorii.semantic-replay-authority-aggregate.v1\0"
_REPLAY_AUTHORITY_AGGREGATE_V2_DOMAIN = b"memorii.semantic-replay-authority-aggregate.v2\0"
_REPLAY_MEMBER_PROJECTION_DOMAIN = b"memorii.semantic-replay-member-projection.v1\0"
_RECONSTRUCTED_REPLAY_AUTHORITY_DOMAIN = b"memorii.semantic-reconstructed-replay-authority.v1\0"

GraphRecordKind = Literal[
    "entity_revision", "alias_revision", "type_evidence", "claim_assertion",
    "claim_projection", "relation_revision", "action_revision", "citation",
    "provenance", "temporal_transition", "identity_lineage", "reference_disposition",
]
MutationKind = Literal["create", "update"]
CommittedRecord = Annotated[
    ClaimAssertion | ActionRevision | IdentityLineageRecord | TemporalTransitionRecord
    | NonOwningGraphRecord,
    Field(discriminator="record_kind"),
]
_CARRIER_ADAPTER = TypeAdapter(CommittedRecord)

_CARRIER_UNION_MEMBER_TYPES = (
    ActionRevision,
    ClaimAssertion,
    IdentityLineageRecord,
    TemporalTransitionRecord,
    CitationRecord,
    ClaimProjection,
    EntityRevision,
    AliasRevision,
    ProvenanceRecord,
    ReferenceDispositionRecord,
    RelationRevision,
    TypeEvidence,
)


def _CARRIER_UNION_MEMBER(value: object) -> bool:
    return isinstance(value, _CARRIER_UNION_MEMBER_TYPES)


class SemanticEventReplayError(ValueError):
    """A closed replay/schema/checkpoint failure with no partial visibility."""

    def __init__(
        self,
        message: str,
        *,
        conflicting_byte_digests: tuple[str, ...] = (),
    ) -> None:
        self.conflicting_byte_digests = tuple(sorted(set(conflicting_byte_digests)))
        super().__init__(message)


class ProjectionHistoryCheckpointVerifier(Protocol):
    """Independent persisted projection authority consulted during replay."""

    def validate_checkpoint_bindings(
        self,
        bindings: tuple[ProjectionHistoryReplayBinding, ...],
        *,
        graph_revision: str,
    ) -> None: ...


class SemanticConflictCheckpointVerifier(Protocol):
    def validate_semantic_conflict_replay_binding(
        self,
        binding: SemanticConflictReplayBinding,
    ) -> None: ...


class MemoryIntegrityConflict(SemanticEventReplayError):
    """A non-identical event, dedupe, or record-version binding collision."""


class ReplayIntegrityLinearizer(Protocol):
    def exclusive(self) -> AbstractContextManager[None]: ...


def _digest(domain: bytes, value: object) -> str:
    return hashlib.sha256(domain + encode_typed_value(_canonical_digest_value(value))).hexdigest()


def _canonical_digest_value(value: object) -> object:
    if isinstance(value, BaseModel):
        return _canonical_digest_value(value.model_dump(mode="python"))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _canonical_digest_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_canonical_digest_value(item) for item in value)
    if isinstance(value, list):
        return [_canonical_digest_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        normalized = (_canonical_digest_value(item) for item in value)
        return frozenset(normalized) if isinstance(value, frozenset) else set(normalized)
    return value


def _digest_field(value: str) -> str:
    if _DIGEST.fullmatch(value) is None:
        raise ValueError("field must be a lowercase SHA-256 digest")
    return value


def _optional_digest(value: str | None) -> str | None:
    return None if value is None else _digest_field(value)


def _identifier(value: str) -> str:
    return normalize_delivery_id(value)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None or value.utcoffset() != timedelta(0):
        raise ValueError("instant must be timezone-aware UTC")
    return value.astimezone(UTC)


def _record_identity(record: CommittedRecord) -> str:
    if isinstance(record, ClaimAssertion):
        return record.claim_assertion_id
    if isinstance(record, ActionRevision):
        return record.action_revision_id
    if isinstance(record, IdentityLineageRecord):
        return record.identity_lineage_id
    if isinstance(record, TemporalTransitionRecord):
        return record.transition_id
    return graph_record_id(record)


class MemoryEventMetadata(BaseModel):
    version: int = Field(ge=1)
    is_candidate: Literal[False] = False
    is_committed: Literal[True] = True

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class CommittedMemoryRecordSnapshot(BaseModel):
    kind: Literal["committed_record"] = "committed_record"
    record: CommittedRecord

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class SemanticMemoryEventPayload(BaseModel):
    graph_type: Literal["memory"] = "memory"
    entity_type: Literal["memory_object"] = "memory_object"
    operation: MutationKind
    entity_id: str
    record_id: str
    entity: CommittedMemoryRecordSnapshot
    metadata: MemoryEventMetadata
    record_kind: GraphRecordKind
    prior_record_digest: str | None
    record_digest: str
    graph_revision_before: str
    graph_revision_after: str
    graph_delta_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_ids = field_validator("entity_id", "record_id")(_identifier)
    _validate_digests = field_validator("record_digest", "graph_delta_digest")(_digest_field)
    _validate_prior = field_validator("prior_record_digest")(_optional_digest)

    @model_validator(mode="after")
    def validate_payload(self) -> SemanticMemoryEventPayload:
        record = self.entity.record
        if (
            self.entity_id != self.record_id
            or self.record_id != _record_identity(record)
            or self.record_kind != record.record_kind
            or self.metadata.version != record.record_version
            or self.record_digest != record.record_digest
        ):
            raise ValueError("event payload does not bind its complete record identity")
        if self.operation == "create":
            if self.metadata.version != 1 or self.prior_record_digest is not None:
                raise ValueError("create must reserve version one without a predecessor")
        elif self.metadata.version == 1 or self.prior_record_digest is None:
            raise ValueError("update must advance a prior record")
        if not self.graph_revision_before or not self.graph_revision_after:
            raise ValueError("event payload graph revisions must be nonblank")
        if self.graph_revision_before == self.graph_revision_after:
            raise ValueError("event payload must advance graph revision")
        return self


class EventProvenance(BaseModel):
    source_type: Literal["derived"] = "derived"
    source_id: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_source_id = field_validator("source_id")(_identifier)


class SemanticMemoryEvent(BaseModel):
    event_id: str
    dedupe_key: str
    logical_mutation_digest: str
    event_type: Literal["memorii.semantic_ingestion.memory_mutation"] = SEMANTIC_MEMORY_EVENT_TYPE
    schema_version: str
    repository_id: str
    timestamp: datetime
    task_id: str | None = None
    execution_node_id: str | None = None
    solver_run_id: str | None = None
    payload: SemanticMemoryEventPayload
    provenance: EventProvenance
    transaction_group_id: str
    operation_fence_id: str
    writer_epoch: int = Field(ge=1)
    event_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    # Upcasting yields a current-schema materialized view.  These private
    # coordinates retain the verified persisted identity used for replay
    # evidence, deduplication, checkpoints, and incident diagnosis.
    _source_schema_version: str | None = PrivateAttr(default=None)
    _source_event_id: str | None = PrivateAttr(default=None)
    _source_event_digest: str | None = PrivateAttr(default=None)

    @property
    def source_schema_version(self) -> str:
        return self._source_schema_version or self.schema_version

    @property
    def source_event_id(self) -> str:
        return self._source_event_id or self.event_id

    @property
    def source_event_digest(self) -> str:
        return self._source_event_digest or self.event_digest

    _validate_ids = field_validator(
        "event_id", "dedupe_key", "repository_id", "transaction_group_id", "operation_fence_id"
    )(_identifier)
    _validate_optional_ids = field_validator("task_id", "execution_node_id", "solver_run_id")(
        lambda value: None if value is None else _identifier(value)
    )
    _validate_digests = field_validator("logical_mutation_digest", "event_digest")(_digest_field)
    _validate_timestamp = field_validator("timestamp")(_utc)

    @model_validator(mode="after")
    def validate_event(self) -> SemanticMemoryEvent:
        if self.schema_version != CURRENT_SEMANTIC_EVENT_SCHEMA_VERSION:
            raise ValueError("canonical semantic event has an unsupported write schema")
        if self.event_digest != _digest(
            _EVENT_DOMAIN,
            self.model_dump(mode="python", exclude={"event_digest"}),
        ):
            raise ValueError("semantic event digest mismatch")
        expected_event_id = semantic_event_id(
            schema_version=self.schema_version,
            transaction_group_id=self.transaction_group_id,
            operation_fence_id=self.operation_fence_id,
            graph_revision_after=self.payload.graph_revision_after,
            record_kind=self.payload.record_kind,
            record_id=self.payload.record_id,
            record_version=self.payload.metadata.version,
            mutation_kind=self.payload.operation,
        )
        if self.event_id != expected_event_id:
            raise ValueError("semantic event ID mismatch")
        expected_dedupe = semantic_dedupe_key(
            repository_id=self.repository_id,
            source_id=self.provenance.source_id,
            transaction_group_id=self.transaction_group_id,
            record_kind=self.payload.record_kind,
            record_id=self.payload.record_id,
            record_version=self.payload.metadata.version,
            mutation_kind=self.payload.operation,
        )
        if self.dedupe_key != expected_dedupe:
            raise ValueError("semantic event dedupe key mismatch")
        expected_mutation = semantic_logical_mutation_digest(
            dedupe_key=self.dedupe_key,
            mutation_kind=self.payload.operation,
            prior_record_digest=self.payload.prior_record_digest,
            record=self.payload.entity.record,
        )
        if self.logical_mutation_digest != expected_mutation:
            raise ValueError("semantic logical mutation digest mismatch")
        return self


class EventBatchLogPosition(BaseModel):
    repository_id: str
    sequence: int = Field(ge=1)
    position_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_repository_id = field_validator("repository_id")(_identifier)
    _validate_digest = field_validator("position_digest")(_digest_field)

    @classmethod
    def create(cls, *, repository_id: str, sequence: int) -> EventBatchLogPosition:
        payload = {"repository_id": repository_id, "sequence": sequence}
        return cls(**payload, position_digest=_digest(_POSITION_DOMAIN, payload))

    @model_validator(mode="after")
    def validate_position(self) -> EventBatchLogPosition:
        if self.position_digest != _digest(
            _POSITION_DOMAIN,
            self.model_dump(mode="python", exclude={"position_digest"}),
        ):
            raise ValueError("event batch position digest mismatch")
        return self


class SemanticMemoryEventBatch(BaseModel):
    repository_id: str
    log_position: EventBatchLogPosition
    source_id: str
    transaction_group_id: str
    operation_fence_id: str
    writer_epoch: int = Field(ge=1)
    event_schema_registry_revision: int = Field(ge=1)
    event_schema_registry_digest: str
    graph_delta_digest: str
    events: tuple[SemanticMemoryEvent, ...]
    event_batch_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _source_event_batch_digest: str | None = PrivateAttr(default=None)

    @property
    def source_event_batch_digest(self) -> str:
        return self._source_event_batch_digest or self.event_batch_digest

    _validate_ids = field_validator("repository_id", "source_id", "transaction_group_id", "operation_fence_id")(
        _identifier
    )
    _validate_digests = field_validator("event_schema_registry_digest", "graph_delta_digest", "event_batch_digest")(
        _digest_field
    )

    @model_validator(mode="after")
    def validate_batch(self) -> SemanticMemoryEventBatch:
        if not self.events:
            raise ValueError("semantic event batch cannot be empty")
        if self.log_position.repository_id != self.repository_id:
            raise ValueError("semantic event batch position is cross-repository")
        sort_keys = tuple(_event_sort_key(event) for event in self.events)
        if sort_keys != tuple(sorted(set(sort_keys))):
            raise ValueError("semantic event tuple must be unique and canonical")
        if any(
            event.repository_id != self.repository_id
            or event.provenance.source_id != self.source_id
            or event.transaction_group_id != self.transaction_group_id
            or event.operation_fence_id != self.operation_fence_id
            or event.writer_epoch != self.writer_epoch
            or event.payload.graph_delta_digest != self.graph_delta_digest
            for event in self.events
        ):
            raise ValueError("semantic event batch member binding mismatch")
        if self.event_batch_digest != _digest(
            _BATCH_DOMAIN,
            self.model_dump(mode="python", exclude={"event_batch_digest"}),
        ):
            raise ValueError("semantic event batch digest mismatch")
        return self


class SemanticEventSchemaSupport(BaseModel):
    source_schema_version: str
    canonical_schema_version: str
    envelope_decoder_fingerprint: str
    upcaster_fingerprints: tuple[str, ...]
    status: Literal["active", "deprecated", "retired"]
    support_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_digests = field_validator("envelope_decoder_fingerprint", "support_digest")(_digest_field)
    _validate_upcasters = field_validator("upcaster_fingerprints")(
        lambda values: tuple(_digest_field(value) for value in values)
    )

    @model_validator(mode="after")
    def validate_support(self) -> SemanticEventSchemaSupport:
        if self.support_digest != _digest(
            _SUPPORT_DOMAIN,
            self.model_dump(mode="python", exclude={"support_digest"}),
        ):
            raise ValueError("event schema support digest mismatch")
        if self.source_schema_version == self.canonical_schema_version and self.upcaster_fingerprints:
            raise ValueError("canonical schema support cannot contain upcasters")
        if (
            self.source_schema_version != self.canonical_schema_version
            and self.status != "retired"
            and not self.upcaster_fingerprints
        ):
            raise ValueError("historical schema support requires an upcaster chain")
        return self

    @classmethod
    def create(
        cls,
        *,
        source_schema_version: str,
        canonical_schema_version: str,
        envelope_decoder_fingerprint: str,
        upcaster_fingerprints: tuple[str, ...],
        status: Literal["active", "deprecated", "retired"],
    ) -> SemanticEventSchemaSupport:
        payload = {
            "source_schema_version": source_schema_version,
            "canonical_schema_version": canonical_schema_version,
            "envelope_decoder_fingerprint": envelope_decoder_fingerprint,
            "upcaster_fingerprints": upcaster_fingerprints,
            "status": status,
        }
        return cls(**payload, support_digest=_digest(_SUPPORT_DOMAIN, payload))


class SemanticEventSchemaRegistry(BaseModel):
    registry_revision: int = Field(ge=1)
    current_write_schema_version: str
    supported_read_schemas: tuple[SemanticEventSchemaSupport, ...]
    registry_fingerprint: str
    registry_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_digests = field_validator("registry_fingerprint", "registry_digest")(_digest_field)

    @model_validator(mode="after")
    def validate_registry(self) -> SemanticEventSchemaRegistry:
        versions = tuple(entry.source_schema_version for entry in self.supported_read_schemas)
        if not versions or versions != tuple(sorted(set(versions))):
            raise ValueError("event registry versions must be nonempty, unique, and canonical")
        current = [
            entry
            for entry in self.supported_read_schemas
            if entry.source_schema_version == self.current_write_schema_version
        ]
        if len(current) != 1 or current[0].status != "active":
            raise ValueError("event registry has no active current write schema")
        if self.current_write_schema_version != CURRENT_SEMANTIC_EVENT_SCHEMA_VERSION:
            raise ValueError("event registry current writer is unsupported")
        if self.registry_digest != _digest(
            _REGISTRY_DOMAIN,
            self.model_dump(mode="python", exclude={"registry_digest"}),
        ):
            raise ValueError("event schema registry digest mismatch")
        return self

    @classmethod
    def create(
        cls,
        *,
        registry_revision: int = 1,
        historical_versions: tuple[str, ...] = (),
    ) -> SemanticEventSchemaRegistry:
        decoder = hashlib.sha256(b"memorii.semantic-memory-event.decoder.v1").hexdigest()
        upcaster = hashlib.sha256(b"memorii.semantic-memory-event.upcaster.v0-to-v1").hexdigest()
        entries = tuple(
            sorted(
                (
                    *(
                        SemanticEventSchemaSupport.create(
                            source_schema_version=version,
                            canonical_schema_version=CURRENT_SEMANTIC_EVENT_SCHEMA_VERSION,
                            envelope_decoder_fingerprint=decoder,
                            upcaster_fingerprints=(upcaster,),
                            status="deprecated",
                        )
                        for version in historical_versions
                    ),
                    SemanticEventSchemaSupport.create(
                        source_schema_version=CURRENT_SEMANTIC_EVENT_SCHEMA_VERSION,
                        canonical_schema_version=CURRENT_SEMANTIC_EVENT_SCHEMA_VERSION,
                        envelope_decoder_fingerprint=decoder,
                        upcaster_fingerprints=(),
                        status="active",
                    ),
                ),
                key=lambda entry: entry.source_schema_version,
            )
        )
        fingerprint = _digest(b"memorii.semantic-event-schema-registry-fingerprint.v1\0", entries)
        payload = {
            "registry_revision": registry_revision,
            "current_write_schema_version": CURRENT_SEMANTIC_EVENT_SCHEMA_VERSION,
            "supported_read_schemas": entries,
            "registry_fingerprint": fingerprint,
        }
        return cls(**payload, registry_digest=_digest(_REGISTRY_DOMAIN, payload))


class SemanticEventSchemaRegistryHistory(BaseModel):
    """Immutable monotonic authority resolving every persisted registry coordinate."""

    registries: tuple[SemanticEventSchemaRegistry, ...]
    history_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_digest = field_validator("history_digest")(_digest_field)

    @classmethod
    def create(cls, registries: tuple[SemanticEventSchemaRegistry, ...]) -> SemanticEventSchemaRegistryHistory:
        body = {"registries": registries}
        return cls(
            **body,
            history_digest=_digest(_REGISTRY_HISTORY_DOMAIN, body),
        )

    @model_validator(mode="after")
    def validate_history(self) -> SemanticEventSchemaRegistryHistory:
        revisions = tuple(registry.registry_revision for registry in self.registries)
        coordinates = tuple((registry.registry_revision, registry.registry_digest) for registry in self.registries)
        if (
            not revisions
            or revisions != tuple(range(1, len(revisions) + 1))
            or len(set(coordinates)) != len(coordinates)
            or self.history_digest
            != _digest(
                _REGISTRY_HISTORY_DOMAIN,
                self.model_dump(mode="python", exclude={"history_digest"}),
            )
        ):
            raise ValueError("event schema registry history is non-monotonic or corrupt")
        return self

    @property
    def current(self) -> SemanticEventSchemaRegistry:
        return self.registries[-1]

    def resolve(self, *, revision: int, registry_digest: str) -> SemanticEventSchemaRegistry:
        matches = tuple(
            registry
            for registry in self.registries
            if registry.registry_revision == revision and registry.registry_digest == registry_digest
        )
        if len(matches) != 1:
            raise SemanticEventReplayError("semantic event registry history is absent, ambiguous, or substituted")
        return matches[0]


def _registry_history(
    *,
    registry: SemanticEventSchemaRegistry | None,
    registry_history: SemanticEventSchemaRegistryHistory | None,
) -> SemanticEventSchemaRegistryHistory:
    if registry_history is None:
        if registry is None:
            raise SemanticEventReplayError("semantic event registry history is unavailable")
        body = {"registries": (registry,)}
        return SemanticEventSchemaRegistryHistory.model_construct(
            registries=(registry,),
            history_digest=_digest(_REGISTRY_HISTORY_DOMAIN, body),
        )
    if registry is not None and registry != registry_history.current:
        raise SemanticEventReplayError("active event registry and history disagree")
    return registry_history


class SemanticEventBinding(BaseModel):
    event_id: str
    event_digest: str
    dedupe_key: str
    logical_mutation_digest: str
    record_kind: GraphRecordKind
    record_id: str
    record_version: int = Field(ge=1)
    transaction_group_id: str
    graph_revision_after: str
    batch_sequence: int = Field(ge=1)
    event_offset: int = Field(ge=0)

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_ids = field_validator("event_id", "dedupe_key", "record_id", "transaction_group_id")(_identifier)
    _validate_digests = field_validator("event_digest", "logical_mutation_digest")(_digest_field)


class SemanticMaterializedMemoryRecord(BaseModel):
    record_kind: GraphRecordKind
    record_id: str
    record_version: int = Field(ge=1)
    record_digest: str
    record: CommittedRecord
    source_event_id: str
    source_event_digest: str
    source_id: str
    transaction_group_id: str
    system_valid_from: datetime

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_record_id = field_validator("record_id")(_identifier)
    _validate_ids = field_validator("source_event_id", "source_id", "transaction_group_id")(_identifier)
    _validate_digest = field_validator("record_digest", "source_event_digest")(_digest_field)
    _validate_system_time = field_validator("system_valid_from")(_utc)

    @model_validator(mode="after")
    def validate_record(self) -> SemanticMaterializedMemoryRecord:
        if (
            self.record_kind != self.record.record_kind
            or self.record_id != _record_identity(self.record)
            or self.record_version != self.record.record_version
            or self.record_digest != self.record.record_digest
        ):
            raise ValueError("materialized record binding mismatch")
        return self


class SemanticReplayState(BaseModel):
    repository_id: str
    graph_revision: str
    last_batch_position: EventBatchLogPosition | None = None
    last_event_batch_digest: str | None = None
    materialized_records: tuple[SemanticMaterializedMemoryRecord, ...] = ()
    event_bindings: tuple[SemanticEventBinding, ...] = ()
    state_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_repository_id = field_validator("repository_id")(_identifier)
    _validate_batch_digest = field_validator("last_event_batch_digest")(_optional_digest)
    _validate_state_digest = field_validator("state_digest")(_digest_field)

    @classmethod
    def genesis(cls, repository_id: str) -> SemanticReplayState:
        payload = {
            "repository_id": repository_id,
            "graph_revision": "genesis",
            "last_batch_position": None,
            "last_event_batch_digest": None,
            "materialized_records": (),
            "event_bindings": (),
        }
        return cls(**payload, state_digest=_digest(_STATE_DOMAIN, payload))

    @model_validator(mode="after")
    def validate_state(self) -> SemanticReplayState:
        records = tuple((record.record_kind, record.record_id) for record in self.materialized_records)
        bindings = tuple(
            (binding.batch_sequence, binding.event_offset, binding.event_id) for binding in self.event_bindings
        )
        if records != tuple(sorted(set(records))) or bindings != tuple(sorted(set(bindings))):
            raise ValueError("replay state records and bindings must be unique and canonical")
        if (self.last_batch_position is None) != (self.last_event_batch_digest is None):
            raise ValueError("replay state batch coordinates must be present together")
        if self.last_batch_position is not None and self.last_batch_position.repository_id != self.repository_id:
            raise ValueError("replay state has a cross-repository position")
        if self.state_digest != _digest(
            _STATE_DOMAIN,
            self.model_dump(mode="python", exclude={"state_digest"}),
        ):
            raise ValueError("semantic replay state digest mismatch")
        return self


def semantic_event_id(
    *,
    schema_version: str,
    transaction_group_id: str,
    operation_fence_id: str,
    graph_revision_after: str,
    record_kind: GraphRecordKind,
    record_id: str,
    record_version: int,
    mutation_kind: MutationKind,
) -> str:
    """Derive the concrete envelope identity, including attempt coordinates."""

    return _digest(
        _EVENT_ID_DOMAIN,
        {
            "schema_version": schema_version,
            "transaction_group_id": transaction_group_id,
            "operation_fence_id": operation_fence_id,
            "graph_revision_after": graph_revision_after,
            "record_kind": record_kind,
            "record_id": record_id,
            "record_version": record_version,
            "mutation_kind": mutation_kind,
        },
    )


def semantic_dedupe_key(
    *,
    repository_id: str,
    source_id: str,
    transaction_group_id: str,
    record_kind: GraphRecordKind,
    record_id: str,
    record_version: int,
    mutation_kind: MutationKind,
) -> str:
    """Derive the logical retry identity, excluding attempt-specific fields."""

    return _digest(
        _DEDUPE_DOMAIN,
        {
            "event_type": SEMANTIC_MEMORY_EVENT_TYPE,
            "repository_id": repository_id,
            "source_id": source_id,
            "transaction_group_id": transaction_group_id,
            "record_kind": record_kind,
            "record_id": record_id,
            "record_version": record_version,
            "mutation_kind": mutation_kind,
        },
    )


def semantic_logical_mutation_digest(
    *,
    dedupe_key: str,
    mutation_kind: MutationKind,
    prior_record_digest: str | None,
    record: CommittedRecord,
) -> str:
    return _digest(
        _MUTATION_DOMAIN,
        {
            "dedupe_key": dedupe_key,
            "mutation_kind": mutation_kind,
            "prior_record_digest": prior_record_digest,
            "after_record": record,
        },
    )


def _event_sort_key(event: SemanticMemoryEvent) -> tuple[str, str, int, str]:
    return (
        event.payload.record_kind,
        event.payload.record_id,
        event.payload.metadata.version,
        event.event_id,
    )


def build_semantic_memory_event(
    *,
    record: CommittedRecord,
    prior_record: SemanticMaterializedMemoryRecord | None,
    repository_id: str,
    source_id: str,
    transaction_group_id: str,
    operation_fence_id: str,
    writer_epoch: int,
    graph_revision_before: str,
    graph_revision_after: str,
    graph_delta_digest: str,
    timestamp: datetime,
    task_id: str | None = None,
    execution_node_id: str | None = None,
    solver_run_id: str | None = None,
) -> SemanticMemoryEvent:
    """Construct one full-state event from a store-owned durable carrier."""

    try:
        if (
            certified_instance(record)
            and deeply_immutable_type(type(record))
            and _CARRIER_UNION_MEMBER(record)
        ):
            pass
        else:
            record = _CARRIER_ADAPTER.validate_python(record.model_dump(mode="python"))
            record_certified_instance(record)
    except (TypeError, ValueError) as exc:
        raise SemanticEventReplayError("semantic event carrier validation failed") from exc
    if (
        isinstance(record, IdentityLineageRecord)
        and record.transition.graph_revision_before != graph_revision_before
    ):
        raise SemanticEventReplayError("identity_lineage_graph_revision_mismatch")
    record_id = _record_identity(record)
    if prior_record is None:
        if record.record_version != 1:
            raise SemanticEventReplayError("a new semantic record must begin at version one")
        operation: MutationKind = "create"
        prior_digest = None
    else:
        if (
            prior_record.record_kind != record.record_kind
            or prior_record.record_id != record_id
            or record.record_version != prior_record.record_version + 1
        ):
            raise SemanticEventReplayError("semantic record update does not advance its exact predecessor")
        operation = "update"
        prior_digest = prior_record.record_digest
    dedupe_key = semantic_dedupe_key(
        repository_id=repository_id,
        source_id=source_id,
        transaction_group_id=transaction_group_id,
        record_kind=record.record_kind,
        record_id=record_id,
        record_version=record.record_version,
        mutation_kind=operation,
    )
    event_id = semantic_event_id(
        schema_version=CURRENT_SEMANTIC_EVENT_SCHEMA_VERSION,
        transaction_group_id=transaction_group_id,
        operation_fence_id=operation_fence_id,
        graph_revision_after=graph_revision_after,
        record_kind=record.record_kind,
        record_id=record_id,
        record_version=record.record_version,
        mutation_kind=operation,
    )
    body = {
        "event_id": event_id,
        "dedupe_key": dedupe_key,
        "logical_mutation_digest": semantic_logical_mutation_digest(
            dedupe_key=dedupe_key,
            mutation_kind=operation,
            prior_record_digest=prior_digest,
            record=record,
        ),
        "event_type": SEMANTIC_MEMORY_EVENT_TYPE,
        "schema_version": CURRENT_SEMANTIC_EVENT_SCHEMA_VERSION,
        "repository_id": repository_id,
        "timestamp": _utc(timestamp),
        "task_id": task_id,
        "execution_node_id": execution_node_id,
        "solver_run_id": solver_run_id,
        "payload": SemanticMemoryEventPayload(
            operation=operation,
            entity_id=record_id,
            record_id=record_id,
            entity=CommittedMemoryRecordSnapshot(record=record),
            metadata=MemoryEventMetadata(version=record.record_version),
            record_kind=record.record_kind,
            prior_record_digest=prior_digest,
            record_digest=record.record_digest,
            graph_revision_before=graph_revision_before,
            graph_revision_after=graph_revision_after,
            graph_delta_digest=graph_delta_digest,
        ),
        "provenance": EventProvenance(source_id=source_id),
        "transaction_group_id": transaction_group_id,
        "operation_fence_id": operation_fence_id,
        "writer_epoch": writer_epoch,
    }
    return SemanticMemoryEvent(**body, event_digest=_digest(_EVENT_DOMAIN, body))


def build_semantic_memory_event_batch(
    *,
    graph_delta: SemanticGraphDelta,
    prior_state: SemanticReplayState,
    repository_id: str,
    source_id: str,
    transaction_group_id: str,
    operation_fence_id: str,
    writer_epoch: int,
    graph_revision_before: str,
    graph_revision_after: str,
    timestamp: datetime,
    registry: SemanticEventSchemaRegistry,
    task_id: str | None = None,
    execution_node_id: str | None = None,
    solver_run_id: str | None = None,
) -> SemanticMemoryEventBatch:
    """Derive the canonical event/delta bijection without accepting caller events."""

    if prior_state.repository_id != repository_id or prior_state.graph_revision != graph_revision_before:
        raise SemanticEventReplayError("event compilation state does not match repository graph revision")
    if registry.current_write_schema_version != CURRENT_SEMANTIC_EVENT_SCHEMA_VERSION:
        raise SemanticEventReplayError("event registry does not authorize the current writer")
    prior_by_record = {(record.record_kind, record.record_id): record for record in prior_state.materialized_records}
    graph_records = tuple(sorted(
        (*graph_delta.carriers, *graph_delta.graph_records),
        key=lambda item: (item.record_kind, _record_identity(item)),
    ))
    identities = tuple((carrier.record_kind, _record_identity(carrier)) for carrier in graph_records)
    if identities != tuple(sorted(set(identities))):
        raise SemanticEventReplayError("graph delta carriers must have unique canonical identities")
    events = tuple(
        sorted(
            (
                build_semantic_memory_event(
                    record=carrier,
                    prior_record=prior_by_record.get((carrier.record_kind, _record_identity(carrier))),
                    repository_id=repository_id,
                    source_id=source_id,
                    transaction_group_id=transaction_group_id,
                    operation_fence_id=operation_fence_id,
                    writer_epoch=writer_epoch,
                    graph_revision_before=graph_revision_before,
                    graph_revision_after=graph_revision_after,
                    graph_delta_digest=graph_delta.delta_digest,
                    timestamp=timestamp,
                    task_id=task_id,
                    execution_node_id=execution_node_id,
                    solver_run_id=solver_run_id,
                )
                for carrier in graph_records
            ),
            key=_event_sort_key,
        )
    )
    if len(events) != len(graph_records):
        raise SemanticEventReplayError("graph delta and semantic events are not bijective")
    sequence = 1 if prior_state.last_batch_position is None else prior_state.last_batch_position.sequence + 1
    body = {
        "repository_id": repository_id,
        "log_position": EventBatchLogPosition.create(repository_id=repository_id, sequence=sequence),
        "source_id": source_id,
        "transaction_group_id": transaction_group_id,
        "operation_fence_id": operation_fence_id,
        "writer_epoch": writer_epoch,
        "event_schema_registry_revision": registry.registry_revision,
        "event_schema_registry_digest": registry.registry_digest,
        "graph_delta_digest": graph_delta.delta_digest,
        "events": events,
    }
    return SemanticMemoryEventBatch(**body, event_batch_digest=_digest(_BATCH_DOMAIN, body))


def encode_semantic_memory_event(value: SemanticMemoryEvent) -> bytes:
    return encode_typed_value(
        {
            "schema": "memorii.semantic-memory-event-envelope.v1",
            "payload": value.model_dump(mode="python"),
        }
    )


def decode_semantic_memory_event(
    raw: bytes,
    *,
    registry: SemanticEventSchemaRegistry,
) -> SemanticMemoryEvent:
    """Verify original bytes under their source schema before a pure upcast."""

    try:
        decoded = decode_typed_value(raw)
        if not isinstance(decoded, dict) or set(decoded) != {"schema", "payload"}:
            raise SemanticEventReplayError("semantic event envelope is not closed")
        if decoded["schema"] != "memorii.semantic-memory-event-envelope.v1":
            raise SemanticEventReplayError("semantic event envelope schema is unsupported")
        payload = decoded["payload"]
        if not isinstance(payload, dict):
            raise SemanticEventReplayError("semantic event payload is not an object")
        source_version = payload.get("schema_version")
        support = tuple(
            entry for entry in registry.supported_read_schemas if entry.source_schema_version == source_version
        )
        if len(support) != 1:
            raise SemanticEventReplayError("semantic event schema is unknown, retired, or ambiguous")
        supplied_digest = payload.get("event_digest")
        if not isinstance(supplied_digest, str) or supplied_digest != _digest(
            _EVENT_DOMAIN, {key: value for key, value in payload.items() if key != "event_digest"}
        ):
            raise SemanticEventReplayError("semantic event source envelope digest mismatch")
        if (
            support[0].status == "retired"
            or not support[0].upcaster_fingerprints
            and (source_version != CURRENT_SEMANTIC_EVENT_SCHEMA_VERSION)
        ):
            raise SemanticEventReplayError("historical semantic event has no deterministic upcaster")
        if source_version == CURRENT_SEMANTIC_EVENT_SCHEMA_VERSION:
            event = SemanticMemoryEvent.model_validate(payload)
            object.__setattr__(event, "_source_schema_version", str(source_version))
            object.__setattr__(event, "_source_event_id", event.event_id)
            object.__setattr__(event, "_source_event_digest", event.event_digest)
            return event
        if not support[0].upcaster_fingerprints:
            raise SemanticEventReplayError("historical semantic event has no deterministic upcaster")
        # The only supported historical shape is v0, whose declared default for
        # solver_run_id is null. No state, clock, provider, or analyzer is consulted.
        expected = set(SemanticMemoryEvent.model_fields) - {"solver_run_id"}
        if set(payload) != expected:
            raise SemanticEventReplayError("historical semantic event shape is not the registered v0 shape")
        historical_event_id = semantic_event_id(
            schema_version=str(source_version),
            transaction_group_id=payload["transaction_group_id"],
            operation_fence_id=payload["operation_fence_id"],
            graph_revision_after=payload["payload"]["graph_revision_after"],
            record_kind=payload["payload"]["record_kind"],
            record_id=payload["payload"]["record_id"],
            record_version=payload["payload"]["metadata"]["version"],
            mutation_kind=payload["payload"]["operation"],
        )
        if payload["event_id"] != historical_event_id:
            raise SemanticEventReplayError("historical semantic event ID mismatch")
        upcast = dict(payload)
        upcast["schema_version"] = CURRENT_SEMANTIC_EVENT_SCHEMA_VERSION
        upcast["solver_run_id"] = None
        upcast["event_id"] = semantic_event_id(
            schema_version=CURRENT_SEMANTIC_EVENT_SCHEMA_VERSION,
            transaction_group_id=upcast["transaction_group_id"],
            operation_fence_id=upcast["operation_fence_id"],
            graph_revision_after=upcast["payload"]["graph_revision_after"],
            record_kind=upcast["payload"]["record_kind"],
            record_id=upcast["payload"]["record_id"],
            record_version=upcast["payload"]["metadata"]["version"],
            mutation_kind=upcast["payload"]["operation"],
        )
        upcast["event_digest"] = _digest(
            _EVENT_DOMAIN, {key: value for key, value in upcast.items() if key != "event_digest"}
        )
        event = SemanticMemoryEvent.model_validate(upcast)
        object.__setattr__(event, "_source_schema_version", str(source_version))
        object.__setattr__(event, "_source_event_id", str(payload["event_id"]))
        object.__setattr__(event, "_source_event_digest", str(payload["event_digest"]))
        return event
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, SemanticEventReplayError):
            raise
        raise SemanticEventReplayError("semantic event decode or upcast failed") from exc


def encode_semantic_memory_event_batch(value: SemanticMemoryEventBatch) -> bytes:
    return encode_typed_value(
        {
            "schema": "memorii.semantic-memory-event-batch-envelope.v1",
            "payload": value.model_dump(mode="python"),
        }
    )


def decode_semantic_memory_event_batch(
    raw: bytes,
    *,
    registry: SemanticEventSchemaRegistry | None = None,
    registry_history: SemanticEventSchemaRegistryHistory | None = None,
) -> SemanticMemoryEventBatch:
    """Verify one persisted source batch before materializing its current view."""

    try:
        decoded = decode_typed_value(raw)
        if (
            not isinstance(decoded, dict)
            or set(decoded) != {"schema", "payload"}
            or decoded["schema"] != "memorii.semantic-memory-event-batch-envelope.v1"
        ):
            raise SemanticEventReplayError("semantic event batch envelope is not closed")
        payload = decoded["payload"]
        expected_fields = set(SemanticMemoryEventBatch.model_fields)
        if not isinstance(payload, dict) or set(payload) != expected_fields:
            raise SemanticEventReplayError("semantic event batch payload is not closed")
        supplied_digest = payload.get("event_batch_digest")
        if not isinstance(supplied_digest, str) or supplied_digest != _digest(
            _BATCH_DOMAIN,
            {key: value for key, value in payload.items() if key != "event_batch_digest"},
        ):
            raise SemanticEventReplayError("semantic event source batch digest mismatch")
        history = _registry_history(
            registry=registry,
            registry_history=registry_history,
        )
        revision = payload.get("event_schema_registry_revision")
        registry_digest = payload.get("event_schema_registry_digest")
        if not isinstance(revision, int) or not isinstance(registry_digest, str):
            raise SemanticEventReplayError("semantic event batch registry binding is invalid")
        source_registry = history.resolve(
            revision=revision,
            registry_digest=registry_digest,
        )
        source_events = payload.get("events")
        if not isinstance(source_events, (tuple, list)) or not source_events:
            raise SemanticEventReplayError("semantic event source batch has no events")

        # Decode each source member independently only after the enclosing
        # source-batch digest is valid.  A failure therefore cannot expose a
        # partially upcast batch or partially reduced state.
        events = tuple(
            decode_semantic_memory_event(
                encode_typed_value(
                    {
                        "schema": "memorii.semantic-memory-event-envelope.v1",
                        "payload": source_event,
                    }
                ),
                registry=source_registry,
            )
            for source_event in source_events
        )
        canonical_body = {key: value for key, value in payload.items() if key not in {"events", "event_batch_digest"}}
        canonical_body["events"] = events
        batch = SemanticMemoryEventBatch(
            **canonical_body,
            event_batch_digest=_digest(_BATCH_DOMAIN, canonical_body),
        )
        object.__setattr__(batch, "_source_event_batch_digest", supplied_digest)
        return batch
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, SemanticEventReplayError):
            raise
        raise SemanticEventReplayError("semantic event batch validation failed") from exc


def encode_semantic_replay_state(value: SemanticReplayState) -> bytes:
    return encode_typed_value(
        {
            "schema": "memorii.semantic-replay-state-envelope.v1",
            "payload": value.model_dump(mode="python"),
        }
    )


def decode_semantic_replay_state(raw: bytes) -> SemanticReplayState:
    try:
        decoded = decode_typed_value(raw)
        if (
            not isinstance(decoded, dict)
            or set(decoded) != {"schema", "payload"}
            or decoded["schema"] != "memorii.semantic-replay-state-envelope.v1"
        ):
            raise SemanticEventReplayError("semantic replay state envelope is not closed")
        return SemanticReplayState.model_validate(decoded["payload"])
    except (TypeError, ValueError) as exc:
        if isinstance(exc, SemanticEventReplayError):
            raise
        raise SemanticEventReplayError("semantic replay state validation failed") from exc


def encode_event_schema_registry_history(
    value: SemanticEventSchemaRegistryHistory,
) -> bytes:
    return encode_typed_value(
        {
            "schema": "memorii.semantic-event-schema-registry-history-envelope.v1",
            "payload": value.model_dump(mode="python"),
        }
    )


def decode_event_schema_registry_history(
    raw: bytes,
) -> SemanticEventSchemaRegistryHistory:
    try:
        decoded = decode_typed_value(raw)
        if (
            not isinstance(decoded, dict)
            or set(decoded) != {"schema", "payload"}
            or decoded["schema"] != "memorii.semantic-event-schema-registry-history-envelope.v1"
        ):
            raise SemanticEventReplayError("event registry history envelope is not closed")
        return SemanticEventSchemaRegistryHistory.model_validate(decoded["payload"])
    except (TypeError, ValueError) as exc:
        if isinstance(exc, SemanticEventReplayError):
            raise
        raise SemanticEventReplayError("event registry history validation failed") from exc


def encode_replay_checkpoint_lifecycle(value: ReplayCheckpointLifecycleState) -> bytes:
    return encode_typed_value(
        {
            "schema": "memorii.semantic-replay-checkpoint-lifecycle-envelope.v1",
            "payload": value.model_dump(mode="python"),
        }
    )


def decode_replay_checkpoint_lifecycle(raw: bytes) -> ReplayCheckpointLifecycleState:
    try:
        decoded = decode_typed_value(raw)
        if (
            not isinstance(decoded, dict)
            or set(decoded) != {"schema", "payload"}
            or decoded["schema"] != "memorii.semantic-replay-checkpoint-lifecycle-envelope.v1"
        ):
            raise SemanticEventReplayError("checkpoint lifecycle envelope is not closed")
        return ReplayCheckpointLifecycleState.model_validate(decoded["payload"])
    except (TypeError, ValueError) as exc:
        if isinstance(exc, SemanticEventReplayError):
            raise
        raise SemanticEventReplayError("checkpoint lifecycle validation failed") from exc


def encode_semantic_replay_authority(value: SemanticReplayAuthorityAggregate) -> bytes:
    return encode_typed_value(
        {
            "schema": "memorii.semantic-replay-authority-envelope.v2",
            "payload": value.model_dump(mode="python"),
        }
    )


def decode_semantic_replay_authority(raw: bytes) -> SemanticReplayAuthorityAggregate:
    try:
        decoded = decode_typed_value(raw)
        if not isinstance(decoded, dict) or set(decoded) != {"schema", "payload"}:
            raise SemanticEventReplayError("semantic replay authority envelope is not closed")
        payload = decoded["payload"]
        if not isinstance(payload, dict):
            raise SemanticEventReplayError("semantic replay authority payload is not an object")
        if decoded["schema"] == "memorii.semantic-replay-authority-envelope.v1":
            payload = {
                **payload,
                "aggregate_schema_version": "memorii.semantic-replay-authority-aggregate.v1",
            }
        elif decoded["schema"] != "memorii.semantic-replay-authority-envelope.v2":
            raise SemanticEventReplayError("semantic replay authority envelope is not closed")
        return SemanticReplayAuthorityAggregate.model_validate(payload)
    except (TypeError, ValueError) as exc:
        if isinstance(exc, SemanticEventReplayError):
            raise
        raise SemanticEventReplayError("semantic replay authority validation failed") from exc


def replay_semantic_event_batches(
    *,
    repository_id: str,
    batches: Iterable[SemanticMemoryEventBatch],
    registry: SemanticEventSchemaRegistry | None = None,
    registry_history: SemanticEventSchemaRegistryHistory | None = None,
    initial_state: SemanticReplayState | None = None,
) -> SemanticReplayState:
    """Replay complete batches through isolated immutable candidate states."""

    history = _registry_history(
        registry=registry,
        registry_history=registry_history,
    )
    state = initial_state or SemanticReplayState.genesis(repository_id)
    if state.repository_id != repository_id:
        raise SemanticEventReplayError("replay state belongs to another repository")
    for batch in batches:
        _validate_identity_lineage_batch_closure(state=state, batch=batch)
        state = _apply_semantic_event_batch(
            state=state,
            batch=batch,
            registry_history=history,
        )
    from memorii.core.memory_evolution.identity_lineage import (
        IdentityLineageError,
        replay_identity_lineage,
    )

    try:
        replay_identity_lineage(state)
    except IdentityLineageError as exc:
        raise SemanticEventReplayError("identity_lineage_replay_invalid") from exc
    return state


def _validate_identity_lineage_batch_closure(
    *,
    state: SemanticReplayState,
    batch: SemanticMemoryEventBatch,
) -> None:
    from memorii.core.memory_evolution.identity_lineage import (
        derive_total_reverse_reference_closure,
    )

    for event in batch.events:
        record = event.payload.entity.record
        if not isinstance(record, IdentityLineageRecord):
            continue
        expected = derive_total_reverse_reference_closure(
            materialized_records=state.materialized_records,
            predecessors=record.transition.predecessors,
            recorded_before=event.timestamp,
        )
        if record.transition.reverse_reference_closure != expected:
            raise SemanticEventReplayError(
                "identity_lineage_reference_closure_mismatch"
            )


def _apply_semantic_event_batch(
    *,
    state: SemanticReplayState,
    batch: SemanticMemoryEventBatch,
    registry_history: SemanticEventSchemaRegistryHistory,
) -> SemanticReplayState:
    expected_sequence = 1 if state.last_batch_position is None else state.last_batch_position.sequence + 1
    if batch.repository_id != state.repository_id or batch.log_position.sequence != expected_sequence:
        raise MemoryIntegrityConflict("semantic event batch position is non-contiguous or cross-repository")
    registry_history.resolve(
        revision=batch.event_schema_registry_revision,
        registry_digest=batch.event_schema_registry_digest,
    )

    # All mutations in one graph delta share one before/after revision. Building
    # fresh dictionaries ensures a rejected batch cannot leak partial state.
    records = {(item.record_kind, item.record_id): item for item in state.materialized_records}
    event_index = {item.event_id: item for item in state.event_bindings}
    dedupe_index = {item.dedupe_key: item for item in state.event_bindings}
    reservation_index = {(item.record_kind, item.record_id, item.record_version): item for item in state.event_bindings}
    bindings = list(state.event_bindings)
    if any(
        event.payload.graph_revision_before != state.graph_revision
        or event.payload.graph_revision_after != batch.events[0].payload.graph_revision_after
        or event.payload.graph_delta_digest != batch.graph_delta_digest
        for event in batch.events
    ):
        raise MemoryIntegrityConflict("semantic event batch graph revision binding is discontinuous")

    for offset, event in enumerate(batch.events):
        existing_event = event_index.get(event.source_event_id)
        if existing_event is not None:
            if existing_event.event_digest != event.source_event_digest:
                raise MemoryIntegrityConflict("semantic event ID has conflicting envelope bytes")
            continue
        existing_dedupe = dedupe_index.get(event.dedupe_key)
        if existing_dedupe is not None:
            if (
                existing_dedupe.logical_mutation_digest != event.logical_mutation_digest
                or existing_dedupe.event_id != event.source_event_id
                or existing_dedupe.event_digest != event.source_event_digest
                or existing_dedupe.record_kind != event.payload.record_kind
                or existing_dedupe.record_id != event.payload.record_id
                or existing_dedupe.record_version != event.payload.metadata.version
                or existing_dedupe.transaction_group_id != event.transaction_group_id
            ):
                raise MemoryIntegrityConflict("semantic dedupe key has a conflicting mutation binding")
            continue
        reservation = (
            event.payload.record_kind,
            event.payload.record_id,
            event.payload.metadata.version,
        )
        existing_reservation = reservation_index.get(reservation)
        if existing_reservation is not None:
            if (
                existing_reservation.event_id != event.source_event_id
                or existing_reservation.event_digest != event.source_event_digest
            ):
                raise MemoryIntegrityConflict("semantic record/version has conflicting envelope bytes")
            continue

        identity = (event.payload.record_kind, event.payload.record_id)
        current = records.get(identity)
        if current is not None and current.record_version > event.payload.metadata.version:
            # Older events are safe only after all three binding indexes proved
            # they were already committed. An unseen older envelope is a gap.
            raise MemoryIntegrityConflict("unbound older semantic event cannot be ignored")
        if event.payload.operation == "create":
            if current is not None:
                raise MemoryIntegrityConflict("semantic create targets an existing record")
        elif (
            current is None
            or event.payload.metadata.version != current.record_version + 1
            or event.payload.prior_record_digest != current.record_digest
        ):
            raise MemoryIntegrityConflict("semantic update does not advance the exact current record")
        materialized = SemanticMaterializedMemoryRecord(
            record_kind=event.payload.record_kind,
            record_id=event.payload.record_id,
            record_version=event.payload.metadata.version,
            record_digest=event.payload.record_digest,
            record=event.payload.entity.record,
            source_event_id=event.source_event_id,
            source_event_digest=event.source_event_digest,
            source_id=event.provenance.source_id,
            transaction_group_id=event.transaction_group_id,
            system_valid_from=event.timestamp,
        )
        records[identity] = materialized
        binding = SemanticEventBinding(
            event_id=event.source_event_id,
            event_digest=event.source_event_digest,
            dedupe_key=event.dedupe_key,
            logical_mutation_digest=event.logical_mutation_digest,
            record_kind=event.payload.record_kind,
            record_id=event.payload.record_id,
            record_version=event.payload.metadata.version,
            transaction_group_id=event.transaction_group_id,
            graph_revision_after=event.payload.graph_revision_after,
            batch_sequence=batch.log_position.sequence,
            event_offset=offset,
        )
        event_index[event.source_event_id] = binding
        dedupe_index[event.dedupe_key] = binding
        reservation_index[reservation] = binding
        bindings.append(binding)

    body = {
        "repository_id": state.repository_id,
        "graph_revision": batch.events[0].payload.graph_revision_after,
        "last_batch_position": batch.log_position,
        "last_event_batch_digest": batch.source_event_batch_digest,
        "materialized_records": tuple(sorted(records.values(), key=lambda item: (item.record_kind, item.record_id))),
        "event_bindings": tuple(
            sorted(bindings, key=lambda item: (item.batch_sequence, item.event_offset, item.event_id))
        ),
    }
    return SemanticReplayState(**body, state_digest=_digest(_STATE_DOMAIN, body))


class ReplayCheckpointSigningKey(BaseModel):
    key_id: str
    issuer_id: str
    public_key_fingerprint: str
    valid_from: datetime
    valid_until: datetime | None = None
    status: Literal["active", "retired", "revoked"]
    retired_at: datetime | None = None
    revoked_at: datetime | None = None
    compromise_effective_at: datetime | None = None
    key_status_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_ids = field_validator("key_id", "issuer_id")(_identifier)
    _validate_digest = field_validator("public_key_fingerprint", "key_status_digest")(_digest_field)
    _validate_times = field_validator(
        "valid_from", "valid_until", "retired_at", "revoked_at", "compromise_effective_at"
    )(lambda value: None if value is None else _utc(value))

    @classmethod
    def create(
        cls,
        *,
        key_id: str,
        issuer_id: str,
        public_key_fingerprint: str,
        valid_from: datetime,
        valid_until: datetime | None = None,
        status: Literal["active", "retired", "revoked"] = "active",
        retired_at: datetime | None = None,
        revoked_at: datetime | None = None,
        compromise_effective_at: datetime | None = None,
    ) -> ReplayCheckpointSigningKey:
        body = {
            "key_id": key_id,
            "issuer_id": issuer_id,
            "public_key_fingerprint": public_key_fingerprint,
            "valid_from": valid_from,
            "valid_until": valid_until,
            "status": status,
            "retired_at": retired_at,
            "revoked_at": revoked_at,
            "compromise_effective_at": compromise_effective_at,
        }
        return cls(**body, key_status_digest=_digest(_CHECKPOINT_KEY_DOMAIN, body))

    @model_validator(mode="after")
    def validate_key(self) -> ReplayCheckpointSigningKey:
        if self.status == "active" and (self.retired_at is not None or self.revoked_at is not None):
            raise ValueError("active checkpoint key cannot carry retirement or revocation")
        if self.status == "retired" and self.retired_at is None:
            raise ValueError("retired checkpoint key requires retirement time")
        if self.status == "revoked" and self.revoked_at is None:
            raise ValueError("revoked checkpoint key requires revocation time")
        if self.valid_until is not None and self.valid_until <= self.valid_from:
            raise ValueError("checkpoint key validity interval is empty")
        if self.key_status_digest != _digest(
            _CHECKPOINT_KEY_DOMAIN,
            self.model_dump(mode="python", exclude={"key_status_digest"}),
        ):
            raise ValueError("checkpoint key status digest mismatch")
        return self


class ReplayCheckpointTrustPolicy(BaseModel):
    policy_revision: int = Field(ge=1)
    authorized_repository_id: str
    keys: tuple[ReplayCheckpointSigningKey, ...]
    policy_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_repository_id = field_validator("authorized_repository_id")(_identifier)
    _validate_digest = field_validator("policy_digest")(_digest_field)

    @classmethod
    def create(
        cls,
        *,
        policy_revision: int,
        authorized_repository_id: str,
        keys: tuple[ReplayCheckpointSigningKey, ...],
    ) -> ReplayCheckpointTrustPolicy:
        ordered = tuple(sorted(keys, key=lambda key: key.key_id))
        body = {
            "policy_revision": policy_revision,
            "authorized_repository_id": authorized_repository_id,
            "keys": ordered,
        }
        return cls(**body, policy_digest=_digest(_CHECKPOINT_POLICY_DOMAIN, body))

    @model_validator(mode="after")
    def validate_policy(self) -> ReplayCheckpointTrustPolicy:
        ids = tuple(key.key_id for key in self.keys)
        if not ids or ids != tuple(sorted(set(ids))):
            raise ValueError("checkpoint trust-policy keys must be nonempty, unique, and canonical")
        if self.policy_digest != _digest(
            _CHECKPOINT_POLICY_DOMAIN,
            self.model_dump(mode="python", exclude={"policy_digest"}),
        ):
            raise ValueError("checkpoint trust-policy digest mismatch")
        return self


class ReplayCheckpointSignatureAuthority(Protocol):
    """Opaque checkpoint signing capability; implementations never expose key bytes."""

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


class ReplayCheckpointLifecycleState(BaseModel):
    """Store-owned monotonic public authority used at every resume boundary."""

    repository_id: str
    authority_revision: int = Field(ge=1)
    registry_revision: int = Field(ge=1)
    registry_digest: str
    registry_history_digest: str
    trust_policy_revision: int = Field(ge=1)
    trust_policy_digest: str
    minimum_checkpoint_sequence: int = Field(ge=1)
    predecessor_authority_digest: str | None = None
    authority_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_repository_id = field_validator("repository_id")(_identifier)
    _validate_digests = field_validator(
        "registry_digest",
        "registry_history_digest",
        "trust_policy_digest",
        "authority_digest",
    )(_digest_field)
    _validate_predecessor = field_validator("predecessor_authority_digest")(_optional_digest)

    @classmethod
    def create(
        cls,
        *,
        repository_id: str,
        authority_revision: int,
        registry: SemanticEventSchemaRegistry,
        registry_history: SemanticEventSchemaRegistryHistory | None = None,
        trust_policy: ReplayCheckpointTrustPolicy,
        minimum_checkpoint_sequence: int = 1,
        predecessor_authority_digest: str | None = None,
    ) -> ReplayCheckpointLifecycleState:
        history = registry_history or SemanticEventSchemaRegistryHistory.create((registry,))
        if history.current != registry:
            raise ValueError("checkpoint lifecycle registry history is not current")
        body = {
            "repository_id": repository_id,
            "authority_revision": authority_revision,
            "registry_revision": registry.registry_revision,
            "registry_digest": registry.registry_digest,
            "registry_history_digest": history.history_digest,
            "trust_policy_revision": trust_policy.policy_revision,
            "trust_policy_digest": trust_policy.policy_digest,
            "minimum_checkpoint_sequence": minimum_checkpoint_sequence,
            "predecessor_authority_digest": predecessor_authority_digest,
        }
        return cls(**body, authority_digest=_digest(_CHECKPOINT_LIFECYCLE_DOMAIN, body))

    @model_validator(mode="after")
    def validate_lifecycle(self) -> ReplayCheckpointLifecycleState:
        if self.authority_revision == 1 and self.predecessor_authority_digest is not None:
            raise ValueError("initial checkpoint lifecycle authority cannot name a predecessor")
        if self.authority_revision > 1 and self.predecessor_authority_digest is None:
            raise ValueError("successor checkpoint lifecycle authority requires a predecessor")
        if self.authority_digest != _digest(
            _CHECKPOINT_LIFECYCLE_DOMAIN,
            self.model_dump(mode="python", exclude={"authority_digest"}),
        ):
            raise ValueError("checkpoint lifecycle authority digest mismatch")
        return self


@dataclass(frozen=True)
class ReplayCheckpointResumeAuthority:
    """Runtime authority whose public lifecycle state is persisted by the store."""

    lifecycle: ReplayCheckpointLifecycleState
    registry: SemanticEventSchemaRegistry
    trust_policy: ReplayCheckpointTrustPolicy
    signature_authority_provider: Callable[[str], ReplayCheckpointSignatureAuthority | None]
    signing_key_id: str
    registry_history: SemanticEventSchemaRegistryHistory | None = None
    persistence_scope: Literal["ephemeral", "durable"] = "ephemeral"
    current_time_provider: Callable[[], datetime] = lambda: datetime.now(UTC)

    def __post_init__(self) -> None:
        try:
            lifecycle = ReplayCheckpointLifecycleState.model_validate(self.lifecycle.model_dump(mode="python"))
            registry = SemanticEventSchemaRegistry.model_validate(self.registry.model_dump(mode="python"))
            trust_policy = ReplayCheckpointTrustPolicy.model_validate(self.trust_policy.model_dump(mode="python"))
            history = SemanticEventSchemaRegistryHistory.model_validate(
                (self.registry_history or SemanticEventSchemaRegistryHistory.create((registry,))).model_dump(
                    mode="python"
                )
            )
            used_at = _utc(self.current_time_provider())
        except (AttributeError, TypeError, ValueError) as exc:
            raise SemanticEventReplayError("checkpoint resume authority is invalid") from exc
        object.__setattr__(self, "lifecycle", lifecycle)
        object.__setattr__(self, "registry", registry)
        object.__setattr__(self, "trust_policy", trust_policy)
        object.__setattr__(self, "registry_history", history)
        if (
            lifecycle.repository_id != trust_policy.authorized_repository_id
            or lifecycle.registry_revision != registry.registry_revision
            or lifecycle.registry_digest != registry.registry_digest
            or lifecycle.registry_history_digest != history.history_digest
            or history.current != registry
            or lifecycle.trust_policy_revision != trust_policy.policy_revision
            or lifecycle.trust_policy_digest != trust_policy.policy_digest
        ):
            raise SemanticEventReplayError("checkpoint resume authority is stale, substituted, or rolled back")
        keys = tuple(key for key in trust_policy.keys if key.key_id == self.signing_key_id)
        signature_authority = self.signature_authority_provider(self.signing_key_id)
        if (
            len(keys) != 1
            or signature_authority is None
            or signature_authority.key_id != self.signing_key_id
            or signature_authority.public_key_fingerprint != keys[0].public_key_fingerprint
        ):
            raise SemanticEventReplayError("checkpoint resume signing authority is unavailable")
        key = keys[0]
        if (
            key.status != "active"
            or used_at < key.valid_from
            or (key.valid_until is not None and used_at >= key.valid_until)
            or (key.retired_at is not None and key.retired_at <= used_at)
            or (key.revoked_at is not None and key.revoked_at <= used_at)
            or (key.compromise_effective_at is not None and key.compromise_effective_at <= used_at)
        ):
            raise SemanticEventReplayError("checkpoint resume signing key is not current and active")


class SemanticReplayCheckpoint(BaseModel):
    checkpoint_id: str
    checkpoint_schema_version: Literal[
        "memorii.semantic-replay-checkpoint.v1",
        "memorii.semantic-replay-checkpoint.v2",
    ] = "memorii.semantic-replay-checkpoint.v2"
    repository_id: str
    graph_revision: str
    writer_epoch: int = Field(ge=1)
    last_event_batch_position: EventBatchLogPosition
    last_event_id: str
    last_event_dedupe_key: str
    last_event_batch_digest: str
    last_graph_delta_digest: str
    materialized_memory_snapshot_digest: str
    reconstructed_replay_authority_digest: str
    projection_history_bindings: tuple[ProjectionHistoryReplayBinding, ...] = ()
    semantic_conflict_replay_binding: SemanticConflictReplayBinding | None = None
    event_schema_registry_revision: int = Field(ge=1)
    event_schema_registry_digest: str
    event_schema_registry_history_digest: str
    created_at: datetime
    signing_key_id: str
    trust_policy_revision: int = Field(ge=1)
    trust_policy_digest: str
    checkpoint_digest: str
    signature: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_ids = field_validator(
        "checkpoint_id", "repository_id", "last_event_id", "last_event_dedupe_key", "signing_key_id"
    )(_identifier)
    _validate_digests = field_validator(
        "last_event_batch_digest",
        "last_graph_delta_digest",
        "materialized_memory_snapshot_digest",
        "reconstructed_replay_authority_digest",
        "event_schema_registry_digest",
        "event_schema_registry_history_digest",
        "trust_policy_digest",
        "checkpoint_digest",
        "signature",
    )(_digest_field)
    _validate_created_at = field_validator("created_at")(_utc)

    @model_validator(mode="after")
    def validate_checkpoint(self) -> SemanticReplayCheckpoint:
        projection_kinds = tuple(binding.projection_kind for binding in self.projection_history_bindings)
        if (
            self.last_event_batch_position.repository_id != self.repository_id
            or projection_kinds not in {(), ("temporal", "trust")}
            or any(binding.repository_id != self.repository_id for binding in self.projection_history_bindings)
            or (
                self.semantic_conflict_replay_binding is not None
                and self.semantic_conflict_replay_binding.repository_id != self.repository_id
            )
        ):
            raise ValueError("checkpoint position is cross-repository")
        if self.checkpoint_schema_version == "memorii.semantic-replay-checkpoint.v1":
            if self.semantic_conflict_replay_binding is not None:
                raise ValueError("v1 checkpoint cannot bind semantic conflict authority")
            digest_fields = {"checkpoint_digest", "signature", "semantic_conflict_replay_binding"}
        else:
            if self.semantic_conflict_replay_binding is None:
                raise ValueError("v2 checkpoint requires semantic conflict replay binding")
            digest_fields = {"checkpoint_digest", "signature"}
        if self.checkpoint_digest != _digest(
            _CHECKPOINT_POSITION_DOMAIN,
            self.model_dump(mode="python", exclude=digest_fields),
        ):
            raise ValueError("semantic replay checkpoint digest mismatch")
        return self


class SemanticReplayCheckpointBundle(BaseModel):
    checkpoint: SemanticReplayCheckpoint
    materialized_snapshot: SemanticReplayState
    watermark_batch: SemanticMemoryEventBatch
    bundle_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_digest = field_validator("bundle_digest")(_digest_field)

    @model_validator(mode="after")
    def validate_bundle(self) -> SemanticReplayCheckpointBundle:
        if self.bundle_digest != _digest(
            _CHECKPOINT_BUNDLE_DOMAIN,
            self.model_dump(mode="python", exclude={"bundle_digest"}),
        ):
            raise ValueError("semantic replay checkpoint bundle digest mismatch")
        return self


class SemanticReplayAuthorityMemberBinding(BaseModel):
    operation_fence_id: str
    generation: int = Field(ge=2)
    member_id: str
    member_kind: Literal[
        "observation_delta",
        "progress",
        "replay_artifact",
        "artifact_index",
        "artifact_closure",
    ]
    payload_digest: str
    binding_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_ids = field_validator("operation_fence_id", "member_id")(_identifier)
    _validate_digests = field_validator("payload_digest", "binding_digest")(_digest_field)

    @classmethod
    def create(
        cls,
        *,
        operation_fence_id: str,
        generation: int,
        member_id: str,
        member_kind: str,
        payload_digest: str,
    ) -> SemanticReplayAuthorityMemberBinding:
        if member_kind not in {
            "observation_delta",
            "progress",
            "replay_artifact",
            "artifact_index",
            "artifact_closure",
        }:
            raise ValueError("member kind is not replay authority")
        body = {
            "operation_fence_id": operation_fence_id,
            "generation": generation,
            "member_id": member_id,
            "member_kind": member_kind,
            "payload_digest": payload_digest,
        }
        return cls(**body, binding_digest=_digest(_REPLAY_AUTHORITY_MEMBER_DOMAIN, body))

    @model_validator(mode="after")
    def validate_binding(self) -> SemanticReplayAuthorityMemberBinding:
        if self.binding_digest != _digest(
            _REPLAY_AUTHORITY_MEMBER_DOMAIN,
            self.model_dump(mode="python", exclude={"binding_digest"}),
        ):
            raise ValueError("semantic replay authority member digest mismatch")
        return self


class SemanticReplayAuthorityMemberProjection(BaseModel):
    binding: SemanticReplayAuthorityMemberBinding
    semantic_object_kind: Literal[
        "observation_delta",
        "retryable_progress",
        "stage_progress",
        "planned_progress",
        "replay_artifact",
        "artifact_index",
        "artifact_closure",
    ]
    semantic_object_digest: str
    referenced_digests: tuple[str, ...]
    projection_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_digests = field_validator("semantic_object_digest", "projection_digest")(_digest_field)
    _validate_references = field_validator("referenced_digests")(
        lambda values: tuple(_digest_field(value) for value in values)
    )

    @model_validator(mode="after")
    def validate_projection(self) -> SemanticReplayAuthorityMemberProjection:
        if self.referenced_digests != tuple(sorted(set(self.referenced_digests))):
            raise ValueError("semantic replay member references are not canonical")
        if self.projection_digest != _digest(
            _REPLAY_MEMBER_PROJECTION_DOMAIN,
            self.model_dump(mode="python", exclude={"projection_digest"}),
        ):
            raise ValueError("semantic replay member projection digest mismatch")
        return self


class SemanticReconstructedReplayAuthority(BaseModel):
    repository_id: str
    graph_state: SemanticReplayState
    member_projections: tuple[SemanticReplayAuthorityMemberProjection, ...]
    authority_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_repository = field_validator("repository_id")(_identifier)
    _validate_digest = field_validator("authority_digest")(_digest_field)

    @model_validator(mode="after")
    def validate_authority(self) -> SemanticReconstructedReplayAuthority:
        keys = tuple(
            (
                item.binding.operation_fence_id,
                item.binding.generation,
                item.binding.member_id,
            )
            for item in self.member_projections
        )
        if (
            self.graph_state.repository_id != self.repository_id
            or keys != tuple(sorted(set(keys)))
            or self.authority_digest
            != _digest(
                _RECONSTRUCTED_REPLAY_AUTHORITY_DOMAIN,
                self.model_dump(mode="python", exclude={"authority_digest"}),
            )
        ):
            raise ValueError("reconstructed semantic replay authority is invalid")
        return self


def project_semantic_replay_member(
    binding: SemanticReplayAuthorityMemberBinding,
    *,
    canonical_payload: bytes,
    verified_dependency_digests: frozenset[str],
) -> SemanticReplayAuthorityMemberProjection:
    """Decode one member against verified same-or-earlier generation closure."""

    if hashlib.sha256(canonical_payload).hexdigest() != binding.payload_digest:
        raise SemanticEventReplayError("bound semantic replay member payload is substituted")
    references: tuple[str, ...]
    try:
        decode_typed_value(canonical_payload)
    except CanonicalTypedValueError:
        typed_payload = False
    else:
        typed_payload = True
    if not typed_payload:
        # Pre-authority generations permitted opaque replay artifacts. Their
        # byte digest remains replay authority, but they cannot contribute
        # typed cross-member references that were never encoded in them.
        kind = "replay_artifact"
        semantic_digest = hashlib.sha256(canonical_payload).hexdigest()
        references = ()
    elif binding.member_kind == "observation_delta":
        value = decode_semantic_contract(canonical_payload, SemanticObservationDelta)
        kind = "observation_delta"
        semantic_digest = value.observation_digest
        references = tuple(value for value in (value.terminal_digest, value.graph_delta_digest) if value is not None)
    elif binding.member_kind == "artifact_closure":
        value = decode_semantic_contract(canonical_payload, SemanticArtifactClosure)
        kind = "artifact_closure"
        semantic_digest = value.closure_digest
        references = (
            value.terminal_digest,
            *value.sealed_operation_digests,
            *value.accepted_carrier_digests,
            *value.terminal_binding_set_digests,
            *((value.execution_lineage_digest,) if value.execution_lineage_digest is not None else ()),
            *((value.arbitration_policy_bundle_digest,) if value.arbitration_policy_bundle_digest is not None else ()),
            *((value.authorization_read_set_digest,) if value.authorization_read_set_digest is not None else ()),
        )
    elif binding.member_kind == "progress":
        try:
            value = decode_semantic_contract(canonical_payload, SemanticRetryableProgress)
        except ValueError:
            decoded = decode_typed_value(canonical_payload)
            if not isinstance(decoded, dict):
                raise SemanticEventReplayError("semantic replay progress is not typed") from None
            if set(decoded) == {"stage", "artifact_digest"}:
                stage = decoded["stage"]
                artifact_digest = decoded["artifact_digest"]
                if not isinstance(stage, str) or not stage or not isinstance(artifact_digest, str):
                    raise SemanticEventReplayError("semantic replay stage progress is invalid") from None
                _digest_field(artifact_digest)
                kind = "stage_progress"
                semantic_digest = hashlib.sha256(canonical_payload).hexdigest()
                references = (artifact_digest,)
            elif set(decoded) == {"state", "terminal_digest"}:
                terminal_digest = decoded["terminal_digest"]
                if decoded["state"] != "planned" or not isinstance(terminal_digest, str):
                    raise SemanticEventReplayError("semantic replay planned progress is invalid") from None
                _digest_field(terminal_digest)
                kind = "planned_progress"
                semantic_digest = hashlib.sha256(canonical_payload).hexdigest()
                references = (terminal_digest,)
            else:
                raise SemanticEventReplayError("semantic replay progress shape is unknown") from None
        else:
            kind = "retryable_progress"
            semantic_digest = value.progress_digest
            references = (value.terminal_artifact_digest,) if value.terminal_artifact_digest is not None else ()
    elif binding.member_kind == "artifact_index":
        value = decode_typed_value(canonical_payload)
        if not isinstance(value, dict) or set(value) != {"terminal", "closure"}:
            raise SemanticEventReplayError("semantic replay artifact index is not closed")
        terminal = value["terminal"]
        closure = value["closure"]
        if not isinstance(terminal, str) or not isinstance(closure, str):
            raise SemanticEventReplayError("semantic replay artifact index is invalid")
        _digest_field(terminal)
        _digest_field(closure)
        kind = "artifact_index"
        semantic_digest = hashlib.sha256(canonical_payload).hexdigest()
        references = (terminal, closure)
    else:
        decode_typed_value(canonical_payload)
        kind = "replay_artifact"
        semantic_digest = hashlib.sha256(canonical_payload).hexdigest()
        references = ()
    if not set(references) <= verified_dependency_digests:
        raise SemanticEventReplayError("semantic replay member has an unresolved cross-generation reference")
    body = {
        "binding": binding,
        "semantic_object_kind": kind,
        "semantic_object_digest": semantic_digest,
        "referenced_digests": tuple(sorted(set(references))),
    }
    return SemanticReplayAuthorityMemberProjection(
        **body,
        projection_digest=_digest(_REPLAY_MEMBER_PROJECTION_DOMAIN, body),
    )


def semantic_replay_dependency_digests(
    member_kind: str,
    canonical_payload: bytes,
) -> frozenset[str]:
    """Return only typed producer coordinates contributed by one member."""

    try:
        return _semantic_replay_dependency_digests(member_kind, canonical_payload)
    except SemanticEventReplayError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise SemanticEventReplayError("semantic replay producer payload is invalid") from exc


def _semantic_replay_dependency_digests(
    member_kind: str,
    canonical_payload: bytes,
) -> frozenset[str]:

    payload_digest = hashlib.sha256(canonical_payload).hexdigest()
    try:
        decode_typed_value(canonical_payload)
    except CanonicalTypedValueError:
        # Historical opaque members contribute their immutable byte identity,
        # never digest-shaped strings embedded in unvalidated payloads.
        return frozenset((payload_digest,))
    semantic_digests: set[str] = set()
    if member_kind == "observation_delta":
        semantic_digests.add(decode_semantic_contract(canonical_payload, SemanticObservationDelta).observation_digest)
    elif member_kind == "artifact_closure":
        semantic_digests.add(decode_semantic_contract(canonical_payload, SemanticArtifactClosure).closure_digest)
    elif member_kind == "progress":
        try:
            retryable_progress = decode_semantic_contract(canonical_payload, SemanticRetryableProgress)
        except ValueError:
            # Stage/planned progress is itself content-addressed and consumes
            # an artifact coordinate; it does not advertise that coordinate.
            retryable_progress = None
        if retryable_progress is not None:
            semantic_digests.add(retryable_progress.progress_digest)
    elif member_kind == "terminal_artifact":
        terminal = decode_semantic_contract(canonical_payload, SemanticTerminalOutcome)
        semantic_digests.add(terminal.terminal_digest)
        semantic_digests.update(operation.sealed_operation_digest for operation in terminal.sealed_operations)
        semantic_digests.update(carrier.record_digest for carrier in terminal.accepted_carriers)
        semantic_digests.update(binding.binding_set_digest for binding in terminal.terminal_binding_sets)
        if terminal.execution_lineage is not None:
            semantic_digests.add(terminal.execution_lineage.lineage_digest)
        if terminal.arbitration_policy_bundle is not None:
            semantic_digests.add(terminal.arbitration_policy_bundle.bundle_digest)
        if terminal.authorization_read_set is not None:
            semantic_digests.add(terminal.authorization_read_set.read_set_digest)
    elif member_kind == "graph_delta":
        semantic_digests.add(decode_semantic_contract(canonical_payload, SemanticGraphDelta).delta_digest)
    elif member_kind == "recovery_authority_binding":
        semantic_digests.add(
            decode_semantic_contract(canonical_payload, SemanticRecoveryAuthorityBinding).binding_digest
        )
    elif member_kind == "stage_artifact":
        decoded = decode_typed_value(canonical_payload)
        if not isinstance(decoded, dict) or not isinstance(decoded.get("kind"), str):
            raise SemanticEventReplayError("semantic stage artifact is not typed")
        artifact_kind = decoded["kind"]
        if artifact_kind == "local_proposal_attempt" and set(decoded) == {
            "kind",
            "candidates",
        }:
            candidates = tuple(SemanticCandidate.model_validate(value) for value in decoded["candidates"])
            semantic_digests.add(
                contract_digest(
                    b"memorii.semantic-ingestion.local-proposal-attempt.v1",
                    candidates,
                )
            )
        elif artifact_kind == "remote_proposal_attempt" and set(decoded) == {
            "kind",
            "request_digest",
            "response_digest",
        }:
            request_digest = _digest_field(decoded["request_digest"])
            response_digest = _digest_field(decoded["response_digest"])
            semantic_digests.add(
                contract_digest(
                    b"memorii.semantic-ingestion.remote-proposal-attempt.v1",
                    {
                        "request_digest": request_digest,
                        "response_digest": response_digest,
                    },
                )
            )
        elif artifact_kind == "source_analysis" and set(decoded) == {
            "kind",
            "analysis",
        }:
            semantic_digests.add(IndependentSourceAnalysis.model_validate(decoded["analysis"]).analysis_digest)
        elif artifact_kind == "execution_lineage" and set(decoded) == {
            "kind",
            "lineage",
        }:
            semantic_digests.add(SemanticExecutionLineage.model_validate(decoded["lineage"]).lineage_digest)
        else:
            raise SemanticEventReplayError("semantic stage artifact shape is unknown")
    return frozenset((payload_digest, *semantic_digests))


def reconstruct_semantic_replay_authority(
    *,
    repository_id: str,
    graph_state: SemanticReplayState,
    member_projections: tuple[SemanticReplayAuthorityMemberProjection, ...],
) -> SemanticReconstructedReplayAuthority:
    ordered = tuple(
        sorted(
            member_projections,
            key=lambda item: (
                item.binding.operation_fence_id,
                item.binding.generation,
                item.binding.member_id,
            ),
        )
    )
    body = {
        "repository_id": repository_id,
        "graph_state": graph_state,
        "member_projections": ordered,
    }
    return SemanticReconstructedReplayAuthority(
        **body,
        authority_digest=_digest(_RECONSTRUCTED_REPLAY_AUTHORITY_DOMAIN, body),
    )


class SemanticReplayAuthorityAggregate(BaseModel):
    aggregate_schema_version: Literal[
        "memorii.semantic-replay-authority-aggregate.v1",
        "memorii.semantic-replay-authority-aggregate.v2",
    ] = "memorii.semantic-replay-authority-aggregate.v2"
    repository_id: str
    graph_state: SemanticReplayState
    observation_bindings: tuple[SemanticReplayAuthorityMemberBinding, ...] = ()
    progress_bindings: tuple[SemanticReplayAuthorityMemberBinding, ...] = ()
    artifact_bindings: tuple[SemanticReplayAuthorityMemberBinding, ...] = ()
    reconstructed_authority_digest: str
    projection_history_bindings: tuple[ProjectionHistoryReplayBinding, ...] = ()
    semantic_conflict_replay_binding: SemanticConflictReplayBinding | None = None
    latest_checkpoint: SemanticReplayCheckpointBundle | None = None
    aggregate_revision: int = Field(ge=0)
    aggregate_digest: str

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    _validate_repository_id = field_validator("repository_id")(_identifier)
    _validate_digest = field_validator("aggregate_digest")(_digest_field)
    _validate_reconstructed = field_validator("reconstructed_authority_digest")(_digest_field)

    @classmethod
    def genesis(cls, repository_id: str) -> SemanticReplayAuthorityAggregate:
        graph_state = SemanticReplayState.genesis(repository_id)
        reconstructed = reconstruct_semantic_replay_authority(
            repository_id=repository_id,
            graph_state=graph_state,
            member_projections=(),
        )
        body = {
            "aggregate_schema_version": "memorii.semantic-replay-authority-aggregate.v2",
            "repository_id": repository_id,
            "graph_state": graph_state,
            "observation_bindings": (),
            "progress_bindings": (),
            "artifact_bindings": (),
            "reconstructed_authority_digest": reconstructed.authority_digest,
            "projection_history_bindings": (),
            "semantic_conflict_replay_binding": SemanticConflictReplayBinding.genesis(repository_id),
            "latest_checkpoint": None,
            "aggregate_revision": 0,
        }
        return cls(**body, aggregate_digest=_digest(_REPLAY_AUTHORITY_AGGREGATE_V2_DOMAIN, body))

    @model_validator(mode="after")
    def validate_aggregate(self) -> SemanticReplayAuthorityAggregate:
        projection_kinds = tuple(binding.projection_kind for binding in self.projection_history_bindings)
        if (
            self.graph_state.repository_id != self.repository_id
            or projection_kinds not in {(), ("temporal", "trust")}
            or any(binding.repository_id != self.repository_id for binding in self.projection_history_bindings)
            or (
                self.semantic_conflict_replay_binding is not None
                and self.semantic_conflict_replay_binding.repository_id != self.repository_id
            )
        ):
            raise ValueError("semantic replay aggregate is cross-repository")
        if self.aggregate_schema_version == "memorii.semantic-replay-authority-aggregate.v1":
            if self.semantic_conflict_replay_binding is not None:
                raise ValueError("v1 aggregate cannot bind semantic conflict authority")
            aggregate_domain = _REPLAY_AUTHORITY_AGGREGATE_DOMAIN
            digest_fields = {"aggregate_digest", "aggregate_schema_version", "semantic_conflict_replay_binding"}
        else:
            if self.semantic_conflict_replay_binding is None:
                raise ValueError("v2 aggregate requires semantic conflict replay binding")
            aggregate_domain = _REPLAY_AUTHORITY_AGGREGATE_V2_DOMAIN
            digest_fields = {"aggregate_digest"}
        for bindings, expected_kinds in (
            (self.observation_bindings, {"observation_delta"}),
            (self.progress_bindings, {"progress"}),
            (self.artifact_bindings, {"replay_artifact", "artifact_index", "artifact_closure"}),
        ):
            keys = tuple((binding.operation_fence_id, binding.generation, binding.member_id) for binding in bindings)
            if keys != tuple(sorted(set(keys))) or any(
                binding.member_kind not in expected_kinds for binding in bindings
            ):
                raise ValueError("semantic replay aggregate member closure is not canonical")
        if self.latest_checkpoint is not None and (
            self.latest_checkpoint.materialized_snapshot != self.graph_state
            or self.latest_checkpoint.checkpoint.repository_id != self.repository_id
            or self.latest_checkpoint.checkpoint.reconstructed_replay_authority_digest
            != self.reconstructed_authority_digest
            or self.latest_checkpoint.checkpoint.projection_history_bindings != self.projection_history_bindings
            or self.latest_checkpoint.checkpoint.semantic_conflict_replay_binding
            != self.semantic_conflict_replay_binding
        ):
            raise ValueError("semantic replay aggregate checkpoint does not bind graph state")
        if self.aggregate_digest != _digest(
            aggregate_domain,
            self.model_dump(mode="python", exclude=digest_fields),
        ):
            raise ValueError("semantic replay authority aggregate digest mismatch")
        return self


def advance_semantic_replay_authority(
    prior: SemanticReplayAuthorityAggregate,
    *,
    graph_state: SemanticReplayState,
    member_bindings: tuple[SemanticReplayAuthorityMemberBinding, ...],
    reconstructed_authority_digest: str,
    latest_checkpoint: SemanticReplayCheckpointBundle | None,
    projection_history_bindings: tuple[ProjectionHistoryReplayBinding, ...] = (),
    semantic_conflict_replay_binding: SemanticConflictReplayBinding | None = None,
) -> SemanticReplayAuthorityAggregate:
    """Advance graph, observation, progress, artifact, and checkpoint authority once."""

    if prior.repository_id != graph_state.repository_id:
        raise SemanticEventReplayError("semantic replay authority advance is cross-repository")
    observations = (*prior.observation_bindings, *(b for b in member_bindings if b.member_kind == "observation_delta"))
    progress = (*prior.progress_bindings, *(b for b in member_bindings if b.member_kind == "progress"))
    artifacts = (
        *prior.artifact_bindings,
        *(b for b in member_bindings if b.member_kind in {"replay_artifact", "artifact_index", "artifact_closure"}),
    )

    def key(
        item: SemanticReplayAuthorityMemberBinding,
    ) -> tuple[str, int, str]:
        return (item.operation_fence_id, item.generation, item.member_id)

    body = {
        "aggregate_schema_version": "memorii.semantic-replay-authority-aggregate.v2",
        "repository_id": prior.repository_id,
        "graph_state": graph_state,
        "observation_bindings": tuple(sorted(observations, key=key)),
        "progress_bindings": tuple(sorted(progress, key=key)),
        "artifact_bindings": tuple(sorted(artifacts, key=key)),
        "reconstructed_authority_digest": reconstructed_authority_digest,
        "projection_history_bindings": projection_history_bindings,
        "semantic_conflict_replay_binding": (
            semantic_conflict_replay_binding
            or prior.semantic_conflict_replay_binding
            or SemanticConflictReplayBinding.genesis(prior.repository_id)
        ),
        # A checkpoint is an authority boundary, not merely a graph snapshot.
        # Any later observation/progress/artifact generation makes the prior
        # checkpoint stale until a new complete event-batch boundary is signed.
        "latest_checkpoint": latest_checkpoint,
        "aggregate_revision": prior.aggregate_revision + 1,
    }
    return SemanticReplayAuthorityAggregate(
        **body,
        aggregate_digest=_digest(_REPLAY_AUTHORITY_AGGREGATE_V2_DOMAIN, body),
    )


def create_replay_checkpoint(
    *,
    state: SemanticReplayState,
    watermark_batch: SemanticMemoryEventBatch,
    writer_epoch: int,
    authority: ReplayCheckpointResumeAuthority,
    created_at: datetime,
    reconstructed_replay_authority_digest: str | None = None,
    projection_history_bindings: tuple[ProjectionHistoryReplayBinding, ...] = (),
    semantic_conflict_replay_binding: SemanticConflictReplayBinding | None = None,
) -> SemanticReplayCheckpointBundle:
    """Sign a complete snapshot only at its last committed batch boundary."""

    from memorii.core.memory_evolution.identity_lineage import (
        IdentityLineageError,
        replay_identity_lineage,
    )

    try:
        replay_identity_lineage(state)
    except IdentityLineageError as exc:
        raise SemanticEventReplayError("identity_lineage_checkpoint_invalid") from exc

    if (
        state.last_batch_position is None
        or state.last_event_batch_digest is None
        or state.last_batch_position != watermark_batch.log_position
        or state.last_event_batch_digest != watermark_batch.source_event_batch_digest
        or state.graph_revision != watermark_batch.events[-1].payload.graph_revision_after
        or state.repository_id != watermark_batch.repository_id
    ):
        raise SemanticEventReplayError("checkpoint snapshot is not at the supplied complete batch boundary")
    registry = authority.registry
    history = authority.registry_history
    assert history is not None
    trust_policy = authority.trust_policy
    signature_authority = authority.signature_authority_provider(authority.signing_key_id)
    signing_keys = tuple(key for key in trust_policy.keys if key.key_id == authority.signing_key_id)
    if (
        authority.lifecycle.repository_id != state.repository_id
        or trust_policy.authorized_repository_id != state.repository_id
        or signature_authority is None
        or signature_authority.key_id != authority.signing_key_id
        or len(signing_keys) != 1
    ):
        raise SemanticEventReplayError("checkpoint signing authority is not repository-authorized")
    signing_key = signing_keys[0]
    binding = max(
        (item for item in state.event_bindings if item.batch_sequence == state.last_batch_position.sequence),
        key=lambda item: item.event_offset,
    )
    at = _utc(created_at)
    if (
        signing_key.status != "active"
        or at < signing_key.valid_from
        or (signing_key.valid_until is not None and at >= signing_key.valid_until)
        or (signing_key.compromise_effective_at is not None and signing_key.compromise_effective_at <= at)
        or signing_key.public_key_fingerprint != signature_authority.public_key_fingerprint
    ):
        raise SemanticEventReplayError("checkpoint signing key is not current and active")
    checkpoint_id = _digest(
        b"memorii.semantic-replay-checkpoint-id.v1\0",
        {
            "repository_id": state.repository_id,
            "position": state.last_batch_position,
            "snapshot_digest": state.state_digest,
            "created_at": at,
        },
    )
    body = {
        "checkpoint_id": checkpoint_id,
        "checkpoint_schema_version": "memorii.semantic-replay-checkpoint.v2",
        "repository_id": state.repository_id,
        "graph_revision": state.graph_revision,
        "writer_epoch": writer_epoch,
        "last_event_batch_position": state.last_batch_position,
        "last_event_id": binding.event_id,
        "last_event_dedupe_key": binding.dedupe_key,
        "last_event_batch_digest": watermark_batch.source_event_batch_digest,
        "last_graph_delta_digest": watermark_batch.graph_delta_digest,
        "materialized_memory_snapshot_digest": state.state_digest,
        "reconstructed_replay_authority_digest": (
            reconstructed_replay_authority_digest
            or reconstruct_semantic_replay_authority(
                repository_id=state.repository_id,
                graph_state=state,
                member_projections=(),
            ).authority_digest
        ),
        "projection_history_bindings": projection_history_bindings,
        "semantic_conflict_replay_binding": (
            semantic_conflict_replay_binding
            or SemanticConflictReplayBinding.genesis(state.repository_id)
        ),
        "event_schema_registry_revision": registry.registry_revision,
        "event_schema_registry_digest": registry.registry_digest,
        "event_schema_registry_history_digest": history.history_digest,
        "created_at": at,
        "signing_key_id": signature_authority.key_id,
        "trust_policy_revision": trust_policy.policy_revision,
        "trust_policy_digest": trust_policy.policy_digest,
    }
    checkpoint_digest = _digest(_CHECKPOINT_POSITION_DOMAIN, body)
    signature = signature_authority.sign_checkpoint_digest(checkpoint_digest)
    checkpoint = SemanticReplayCheckpoint(**body, checkpoint_digest=checkpoint_digest, signature=signature)
    bundle_body = {
        "checkpoint": checkpoint,
        "materialized_snapshot": state,
        "watermark_batch": watermark_batch,
    }
    return SemanticReplayCheckpointBundle(**bundle_body, bundle_digest=_digest(_CHECKPOINT_BUNDLE_DOMAIN, bundle_body))


def validate_replay_checkpoint(
    bundle: SemanticReplayCheckpointBundle,
    *,
    authority: ReplayCheckpointResumeAuthority,
    projection_history_verifier: ProjectionHistoryCheckpointVerifier | None = None,
    semantic_conflict_verifier: SemanticConflictCheckpointVerifier | None = None,
) -> SemanticReplayState:
    """Validate trust, rollback, snapshot, and watermark before exposing state."""

    try:
        bundle = SemanticReplayCheckpointBundle.model_validate(bundle.model_dump(mode="python"))
    except ValueError as exc:
        raise SemanticEventReplayError("checkpoint authority bytes are invalid or substituted") from exc
    checkpoint = bundle.checkpoint
    state = bundle.materialized_snapshot
    batch = bundle.watermark_batch
    lifecycle = authority.lifecycle
    registry = authority.registry
    history = authority.registry_history
    assert history is not None
    trust_policy = authority.trust_policy
    if (
        checkpoint.last_event_batch_position.sequence < lifecycle.minimum_checkpoint_sequence
        or checkpoint.event_schema_registry_revision != lifecycle.registry_revision
        or checkpoint.event_schema_registry_digest != lifecycle.registry_digest
        or checkpoint.event_schema_registry_history_digest != lifecycle.registry_history_digest
        or checkpoint.trust_policy_revision != lifecycle.trust_policy_revision
        or checkpoint.trust_policy_digest != lifecycle.trust_policy_digest
        or checkpoint.event_schema_registry_revision != registry.registry_revision
        or checkpoint.event_schema_registry_digest != registry.registry_digest
        or checkpoint.event_schema_registry_history_digest != history.history_digest
        or checkpoint.trust_policy_revision != trust_policy.policy_revision
        or checkpoint.trust_policy_digest != trust_policy.policy_digest
    ):
        raise SemanticEventReplayError("checkpoint registry or trust policy is stale, substituted, or rolled back")
    if (
        checkpoint.repository_id != trust_policy.authorized_repository_id
        or checkpoint.repository_id != state.repository_id
        or checkpoint.repository_id != batch.repository_id
        or checkpoint.materialized_memory_snapshot_digest != state.state_digest
        or checkpoint.graph_revision != state.graph_revision
        or checkpoint.last_event_batch_position != state.last_batch_position
        or checkpoint.last_event_batch_position != batch.log_position
        or checkpoint.last_event_batch_digest != state.last_event_batch_digest
        or checkpoint.last_event_batch_digest != batch.source_event_batch_digest
        or checkpoint.last_graph_delta_digest != batch.graph_delta_digest
        or checkpoint.graph_revision != batch.events[-1].payload.graph_revision_after
    ):
        raise SemanticEventReplayError("checkpoint snapshot or watermark binding is invalid")
    matching_bindings = tuple(
        item
        for item in state.event_bindings
        if item.event_id == checkpoint.last_event_id
        and item.dedupe_key == checkpoint.last_event_dedupe_key
        and item.batch_sequence == checkpoint.last_event_batch_position.sequence
    )
    if len(matching_bindings) != 1 or matching_bindings[0].event_offset != len(batch.events) - 1:
        raise SemanticEventReplayError("checkpoint last-event coordinate does not close its watermark batch")
    keys = tuple(key for key in trust_policy.keys if key.key_id == checkpoint.signing_key_id)
    signature_authority = authority.signature_authority_provider(checkpoint.signing_key_id)
    if len(keys) != 1 or signature_authority is None or signature_authority.key_id != checkpoint.signing_key_id:
        raise SemanticEventReplayError("checkpoint signing key is unavailable or ambiguous")
    key = keys[0]
    if signature_authority.public_key_fingerprint != key.public_key_fingerprint:
        raise SemanticEventReplayError("checkpoint signing material does not match trusted key")
    issued_at = checkpoint.created_at
    used_at = _utc(authority.current_time_provider())
    if (
        key.status != "active"
        or issued_at < key.valid_from
        or (key.valid_until is not None and issued_at >= key.valid_until)
        or (key.retired_at is not None and key.retired_at <= issued_at)
        or (key.revoked_at is not None and key.revoked_at <= issued_at)
        or (key.compromise_effective_at is not None and key.compromise_effective_at <= issued_at)
        or used_at < key.valid_from
        or (key.valid_until is not None and used_at >= key.valid_until)
        or (key.retired_at is not None and key.retired_at <= used_at)
        or (key.revoked_at is not None and key.revoked_at <= used_at)
        or (key.compromise_effective_at is not None and key.compromise_effective_at <= used_at)
    ):
        raise SemanticEventReplayError("checkpoint signing key is not valid at issuance and current use")
    if not signature_authority.verify_checkpoint_signature(
        checkpoint.checkpoint_digest,
        checkpoint.signature,
    ):
        raise SemanticEventReplayError("checkpoint signature is invalid")
    if projection_history_verifier is None:
        raise SemanticEventReplayError("checkpoint projection history verifier is required")
    try:
        projection_history_verifier.validate_checkpoint_bindings(
            checkpoint.projection_history_bindings,
            graph_revision=checkpoint.graph_revision,
        )
    except (TypeError, ValueError) as exc:
        raise SemanticEventReplayError("checkpoint projection history is unavailable or divergent") from exc
    empty_conflict_binding = SemanticConflictReplayBinding.genesis(
        checkpoint.repository_id
    )
    conflict_binding = (
        checkpoint.semantic_conflict_replay_binding or empty_conflict_binding
    )
    if (
        checkpoint.checkpoint_schema_version
        == "memorii.semantic-replay-checkpoint.v1"
        and conflict_binding != empty_conflict_binding
    ):
        raise SemanticEventReplayError(
            "v1 checkpoint cannot bind nonempty semantic conflict authority"
        )
    if semantic_conflict_verifier is None:
        if (
            checkpoint.checkpoint_schema_version
            == "memorii.semantic-replay-checkpoint.v1"
            or conflict_binding != empty_conflict_binding
        ):
            raise SemanticEventReplayError(
                "checkpoint semantic conflict authority verifier is required"
            )
    else:
        try:
            semantic_conflict_verifier.validate_semantic_conflict_replay_binding(
                conflict_binding
            )
        except (TypeError, ValueError) as exc:
            raise SemanticEventReplayError(
                "checkpoint semantic conflict authority is unavailable or divergent"
            ) from exc
    return state


def replay_semantic_checkpoint_tail(
    bundle: SemanticReplayCheckpointBundle,
    *,
    tail_batches: Iterable[SemanticMemoryEventBatch],
    authority: ReplayCheckpointResumeAuthority,
    projection_history_verifier: ProjectionHistoryCheckpointVerifier | None = None,
    semantic_conflict_verifier: SemanticConflictCheckpointVerifier | None = None,
) -> SemanticReplayState:
    state = validate_replay_checkpoint(
        bundle,
        authority=authority,
        projection_history_verifier=projection_history_verifier,
        semantic_conflict_verifier=semantic_conflict_verifier,
    )
    return replay_semantic_event_batches(
        repository_id=state.repository_id,
        batches=tail_batches,
        registry_history=authority.registry_history,
        initial_state=state,
    )


class FileSemanticEventRepository:
    """One process-safe append authority for complete canonical event batches."""

    def __init__(
        self,
        path: str | Path,
        *,
        repository_id: str,
        registry: SemanticEventSchemaRegistry | None = None,
        registry_history: SemanticEventSchemaRegistryHistory | None = None,
        freeze_guard: Callable[[SemanticGraphDelta], None] | None = None,
        integrity_incident_reporter: Callable[[tuple[str, ...]], None] | None = None,
        integrity_linearization: ReplayIntegrityLinearizer | None = None,
    ) -> None:
        self._path = Path(path)
        self._lock_path = self._path.with_suffix(self._path.suffix + ".lock")
        self.repository_id = _identifier(repository_id)
        self.registry_history = _registry_history(
            registry=registry,
            registry_history=(
                registry_history
                or (
                    None
                    if registry is not None
                    else SemanticEventSchemaRegistryHistory.create((SemanticEventSchemaRegistry.create(),))
                )
            ),
        )
        self.registry = self.registry_history.current
        self._freeze_guard = freeze_guard
        self._integrity_incident_reporter = integrity_incident_reporter
        reporter_linearization = getattr(integrity_incident_reporter, "linearization", None)
        self._integrity_linearization = integrity_linearization or (
            reporter_linearization
            if reporter_linearization is not None and hasattr(reporter_linearization, "exclusive")
            else None
        )
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _locked(self, *, exclusive: bool):
        with self._linearized():
            self._lock_path.touch(exist_ok=True)
            with self._lock_path.open("r+b") as lock_file:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
                incident_digests: tuple[str, ...] = ()
                try:
                    yield
                except SemanticEventReplayError as exc:
                    incident_digests = exc.conflicting_byte_digests
                    raise
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                    if incident_digests:
                        # Isolation is durable before the outer admission lock
                        # is released, so no affected append can slip through.
                        self._report_integrity(incident_digests)

    @contextmanager
    def _linearized(self) -> Iterator[None]:
        linearization = self._integrity_linearization
        if linearization is None:
            yield
            return
        with linearization.exclusive():
            yield

    def _read_unlocked(self) -> tuple[SemanticMemoryEventBatch, ...]:
        if not self._path.exists():
            return ()
        result: list[SemanticMemoryEventBatch] = []
        with self._path.open("rb") as stream:
            for line_number, raw_line in enumerate(stream, start=1):
                if not raw_line.endswith(b"\n"):
                    raise SemanticEventReplayError(
                        f"semantic event repository has a partial batch at line {line_number}",
                        conflicting_byte_digests=(hashlib.sha256(raw_line).hexdigest(),),
                    )
                line = raw_line[:-1]
                try:
                    decoded = json.loads(line)
                    if not isinstance(decoded, dict) or set(decoded) != {"canonical_hex"}:
                        raise ValueError
                    canonical_hex = decoded["canonical_hex"]
                    if not isinstance(canonical_hex, str) or not re.fullmatch(r"[0-9a-f]+", canonical_hex):
                        raise ValueError
                    if json.dumps(decoded, sort_keys=True, separators=(",", ":")).encode() != line:
                        raise ValueError
                    result.append(
                        decode_semantic_memory_event_batch(
                            bytes.fromhex(canonical_hex),
                            registry_history=self.registry_history,
                        )
                    )
                except (json.JSONDecodeError, TypeError, ValueError) as exc:
                    raise SemanticEventReplayError(
                        f"semantic event repository batch {line_number} is corrupt",
                        conflicting_byte_digests=(hashlib.sha256(raw_line).hexdigest(),),
                    ) from exc
        try:
            replay_semantic_event_batches(
                repository_id=self.repository_id,
                batches=result,
                registry_history=self.registry_history,
            )
        except SemanticEventReplayError as exc:
            raise type(exc)(
                str(exc),
                conflicting_byte_digests=tuple(batch.source_event_batch_digest for batch in result),
            ) from exc
        return tuple(result)

    def _append_unlocked(self, batch: SemanticMemoryEventBatch) -> None:
        encoded = encode_semantic_memory_event_batch(batch)
        line = json.dumps({"canonical_hex": encoded.hex()}, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        descriptor = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            written = os.write(descriptor, line)
            if written != len(line):
                raise OSError("partial semantic event repository append")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def read_batches_after(
        self,
        position: EventBatchLogPosition | None,
    ) -> tuple[SemanticMemoryEventBatch, ...]:
        with self._locked(exclusive=False):
            batches = self._read_unlocked()
        if position is not None and position.repository_id != self.repository_id:
            raise SemanticEventReplayError("event batch cursor belongs to another repository")
        sequence = 0 if position is None else position.sequence
        if position is not None:
            matching = tuple(batch for batch in batches if batch.log_position == position)
            if len(matching) != 1:
                raise SemanticEventReplayError("event batch cursor is absent or substituted")
        result = tuple(batch for batch in batches if batch.log_position.sequence > sequence)
        if result and result[0].log_position.sequence != sequence + 1:
            raise SemanticEventReplayError("event batch tail does not begin contiguously")
        return result

    def replay_genesis(self) -> SemanticReplayState:
        return replay_semantic_event_batches(
            repository_id=self.repository_id,
            batches=self.read_batches_after(None),
            registry_history=self.registry_history,
        )

    def retained_generation_digest(self) -> str:
        """Digest immutable retained bytes without attempting semantic decode."""

        with self._locked(exclusive=False):
            raw = b"" if not self._path.exists() else self._path.read_bytes()
        return hashlib.sha256(
            b"memorii.semantic-event-retained-generation.v1\0" + self.repository_id.encode("utf-8") + b"\0" + raw
        ).hexdigest()

    def retained_byte_digests(self) -> tuple[str, ...]:
        """Return exact retained line/partial-tail digests for incident binding."""

        with self._locked(exclusive=False):
            if not self._path.exists():
                return ()
            return tuple(hashlib.sha256(line).hexdigest() for line in self._path.read_bytes().splitlines(keepends=True))

    def append_batch(self, batch: SemanticMemoryEventBatch) -> SemanticMemoryEventBatch:
        with self._locked(exclusive=True):
            batches = self._read_unlocked()
            for existing in batches:
                if existing.log_position.sequence != batch.log_position.sequence:
                    continue
                if existing == batch:
                    return existing
                raise MemoryIntegrityConflict(
                    "semantic event batch position is already bound differently",
                    conflicting_byte_digests=(
                        existing.event_batch_digest,
                        batch.event_batch_digest,
                    ),
                )
            state = replay_semantic_event_batches(
                repository_id=self.repository_id,
                batches=batches,
                registry_history=self.registry_history,
            )
            _validate_identity_lineage_batch_closure(state=state, batch=batch)
            _apply_semantic_event_batch(
                state=state,
                batch=batch,
                registry_history=self.registry_history,
            )
            self._append_unlocked(batch)
            return batch

    def append_graph_delta(
        self,
        *,
        graph_delta: SemanticGraphDelta,
        source_id: str,
        transaction_group_id: str,
        operation_fence_id: str,
        writer_epoch: int,
        graph_revision_before: str,
        graph_revision_after: str,
        timestamp: datetime,
        task_id: str | None = None,
        execution_node_id: str | None = None,
        solver_run_id: str | None = None,
    ) -> SemanticMemoryEventBatch:
        if self._freeze_guard is not None:
            self._freeze_guard(graph_delta)
        with self._locked(exclusive=True):
            if self._freeze_guard is not None:
                self._freeze_guard(graph_delta)
            batches = self._read_unlocked()
            state = replay_semantic_event_batches(
                repository_id=self.repository_id,
                batches=batches,
                registry_history=self.registry_history,
            )
            existing_by_dedupe = {event.dedupe_key: (batch, event) for batch in batches for event in batch.events}
            existing_by_reservation = {
                (event.payload.record_kind, event.payload.record_id, event.payload.metadata.version): (batch, event)
                for batch in batches
                for event in batch.events
            }
            retry_batches: set[str] = set()
            retry_count = 0
            graph_records = tuple(sorted(
                (*graph_delta.carriers, *graph_delta.graph_records),
                key=lambda item: (item.record_kind, _record_identity(item)),
            ))
            for carrier in graph_records:
                mutation: MutationKind = "create" if carrier.record_version == 1 else "update"
                record_id = _record_identity(carrier)
                key = semantic_dedupe_key(
                    repository_id=self.repository_id,
                    source_id=source_id,
                    transaction_group_id=transaction_group_id,
                    record_kind=carrier.record_kind,
                    record_id=record_id,
                    record_version=carrier.record_version,
                    mutation_kind=mutation,
                )
                prior = None
                if mutation == "update":
                    prior_candidates = tuple(
                        item
                        for item in state.materialized_records
                        if item.record_kind == carrier.record_kind
                        and item.record_id == record_id
                        and item.record_version == carrier.record_version - 1
                    )
                    if len(prior_candidates) == 1:
                        prior = prior_candidates[0].record_digest
                logical = semantic_logical_mutation_digest(
                    dedupe_key=key,
                    mutation_kind=mutation,
                    prior_record_digest=prior,
                    record=carrier,
                )
                existing = existing_by_dedupe.get(key)
                reservation = existing_by_reservation.get((carrier.record_kind, record_id, carrier.record_version))
                if existing is not None:
                    if existing[1].logical_mutation_digest != logical:
                        raise MemoryIntegrityConflict(
                            "semantic logical retry diverges from committed mutation",
                            conflicting_byte_digests=(
                                existing[1].event_digest,
                                carrier.record_digest,
                            ),
                        )
                    retry_batches.add(existing[0].event_batch_digest)
                    retry_count += 1
                elif reservation is not None:
                    raise MemoryIntegrityConflict(
                        "semantic record/version reservation is already committed",
                        conflicting_byte_digests=(
                            reservation[1].event_digest,
                            carrier.record_digest,
                        ),
                    )
            if retry_count:
                if retry_count != len(graph_records) or len(retry_batches) != 1:
                    raise MemoryIntegrityConflict("semantic logical retry is only partially committed")
                return next(batch for batch in batches if batch.event_batch_digest in retry_batches)
            batch = build_semantic_memory_event_batch(
                graph_delta=graph_delta,
                prior_state=state,
                repository_id=self.repository_id,
                source_id=source_id,
                transaction_group_id=transaction_group_id,
                operation_fence_id=operation_fence_id,
                writer_epoch=writer_epoch,
                graph_revision_before=graph_revision_before,
                graph_revision_after=graph_revision_after,
                timestamp=timestamp,
                registry=self.registry,
                task_id=task_id,
                execution_node_id=execution_node_id,
                solver_run_id=solver_run_id,
            )
            _validate_identity_lineage_batch_closure(state=state, batch=batch)
            _apply_semantic_event_batch(
                state=state,
                batch=batch,
                registry_history=self.registry_history,
            )
            self._append_unlocked(batch)
            return batch

    def _report_integrity(self, byte_digests: tuple[str, ...]) -> None:
        reporter = self._integrity_incident_reporter
        if reporter is not None:
            reporter(tuple(sorted(set(byte_digests))))


__all__ = [
    "CURRENT_SEMANTIC_EVENT_SCHEMA_VERSION",
    "CommittedMemoryRecordSnapshot",
    "EventBatchLogPosition",
    "EventProvenance",
    "FileSemanticEventRepository",
    "MemoryEventMetadata",
    "MemoryIntegrityConflict",
    "ProjectionHistoryCheckpointVerifier",
    "ReplayCheckpointLifecycleState",
    "ReplayCheckpointResumeAuthority",
    "ReplayCheckpointSigningKey",
    "ReplayCheckpointTrustPolicy",
    "SemanticEventBinding",
    "SemanticEventReplayError",
    "SemanticEventSchemaRegistry",
    "SemanticEventSchemaRegistryHistory",
    "SemanticEventSchemaSupport",
    "SemanticMaterializedMemoryRecord",
    "SemanticMemoryEvent",
    "SemanticMemoryEventBatch",
    "SemanticMemoryEventPayload",
    "SemanticReplayCheckpoint",
    "SemanticReplayCheckpointBundle",
    "SemanticReplayAuthorityAggregate",
    "SemanticReplayAuthorityMemberBinding",
    "SemanticReplayAuthorityMemberProjection",
    "SemanticReconstructedReplayAuthority",
    "SemanticReplayState",
    "build_semantic_memory_event",
    "build_semantic_memory_event_batch",
    "create_replay_checkpoint",
    "decode_semantic_memory_event",
    "decode_semantic_memory_event_batch",
    "decode_event_schema_registry_history",
    "decode_replay_checkpoint_lifecycle",
    "decode_semantic_replay_authority",
    "decode_semantic_replay_state",
    "encode_semantic_memory_event",
    "encode_semantic_memory_event_batch",
    "encode_event_schema_registry_history",
    "encode_replay_checkpoint_lifecycle",
    "encode_semantic_replay_authority",
    "encode_semantic_replay_state",
    "replay_semantic_checkpoint_tail",
    "replay_semantic_event_batches",
    "project_semantic_replay_member",
    "semantic_replay_dependency_digests",
    "reconstruct_semantic_replay_authority",
    "semantic_dedupe_key",
    "semantic_event_id",
    "semantic_logical_mutation_digest",
    "validate_replay_checkpoint",
]
