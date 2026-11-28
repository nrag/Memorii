"""Registered runtime event profile: closed grammar, reducers, replay.

``RuntimeEventBatch`` specializes the canonical event model for the
execution/solver/system domains: full-state mutations only (no partial
patches, no ID-only commits), closed graph/entity/operation combinations,
batch-position ordering (timestamps never order replay), equal-version
non-identical envelopes failing closed as ``memory_integrity_conflict``,
and the three replay bindings (event id, dedupe key, record version)
publishing atomically with materialized state. The reference reducer is
separately authored from the production reducer and imports no production
replay, normalization or materialization helpers — shared canonical
encoded fixtures are its only common input.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.persistence.runtime_contracts import canonical_runtime_digest

_HEX_64 = r"^[0-9a-f]{64}$"
_EVENT_DIGEST_DOMAIN = "memorii.runtime-event-envelope.v1"
_EVENT_BATCH_DIGEST_DOMAIN = "memorii.runtime-event-batch.v1"

GraphType = Literal["execution", "solver", "system"]
EntityType = Literal["node", "edge", "overlay", "directory", "checkpoint", "routing"]
EventOperation = Literal["create", "update", "delete", "version"]

#: Closed legal combinations: each graph/entity pair admits exactly the
#: operations the durable contract permits. Solver deletes are logical
#: retirement only (backtracking is revision); overlay changes version.
LEGAL_COMBINATIONS: frozenset[tuple[str, str, str]] = frozenset(
    {
        *(("execution", "node", op) for op in ("create", "update", "delete")),
        *(("execution", "edge", op) for op in ("create", "update", "delete")),
        *(("solver", "node", op) for op in ("create", "update", "delete")),
        *(("solver", "edge", op) for op in ("create", "update", "delete")),
        ("solver", "overlay", "version"),
        *(("system", "directory", op) for op in ("create", "update", "delete")),
        ("system", "checkpoint", "create"),
        *(("system", "routing", op) for op in ("create", "update")),
    }
)

#: Business labels mapped onto the existing EventType semantics; schema
#: generation must enumerate this mapping for every value.
EVENT_BUSINESS_LABELS: frozenset[str] = frozenset(
    {
        "task_started", "task_resumed", "task_paused", "task_completed",
        "task_aborted", "solver_started", "solver_resolved",
        "node_merged", "node_reopened", "belief_updated",
        "justification_invalidated", "status_updated",
        "action_selected", "action_dispatched", "action_completed",
        "observation_received", "checkpoint_recorded",
        "consolidation_recorded",
    }
)


class RuntimeEventEnvelope(BaseModel):
    """One full-state mutation inside the runtime profile."""

    event_id: str = Field(min_length=1)
    dedupe_key: str = Field(min_length=1)
    graph_type: GraphType
    entity_type: EntityType
    operation: EventOperation
    entity_id: str = Field(min_length=1)
    record_id: str = Field(min_length=1)
    entity: dict[str, object]
    metadata_version: int = Field(ge=1)
    is_candidate: bool = False
    is_committed: bool = True
    task_id: str = Field(min_length=1)
    solver_run_id: str | None = None
    event_digest: str = Field(pattern=_HEX_64)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def closed_combination_and_identity(self) -> RuntimeEventEnvelope:
        if (self.graph_type, self.entity_type, self.operation) not in LEGAL_COMBINATIONS:
            raise ValueError(
                "illegal runtime event combination: "
                f"{self.graph_type}/{self.entity_type}/{self.operation}"
            )
        if self.entity_id != self.record_id:
            raise ValueError(
                "runtime profile entity ids equal record ids; aliasing is rejected"
            )
        if self.is_candidate and self.is_committed:
            raise ValueError("an event cannot be candidate and committed")
        if not self.entity:
            raise ValueError(
                "runtime events carry full state; ID-only payloads are rejected"
            )
        if self.event_digest != self._compute_digest():
            raise ValueError("runtime event digest is invalid")
        return self

    def _compute_digest(self) -> str:
        return canonical_runtime_digest((_EVENT_DIGEST_DOMAIN, self.model_dump(exclude={"event_digest"})))


class RuntimeEventBatch(BaseModel):
    """One atomic repository-ordered batch of runtime events."""

    repository_id: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    events: tuple[RuntimeEventEnvelope, ...]
    event_batch_digest: str = Field(pattern=_HEX_64)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def batch_digest_matches(self) -> RuntimeEventBatch:
        if not self.events:
            raise ValueError("a runtime event batch is nonempty")
        if self.event_batch_digest != self._compute_digest():
            raise ValueError("runtime event batch digest is invalid")
        return self

    def _compute_digest(self) -> str:
        return _batch_digest(self.repository_id, self.sequence, self.events)


class RuntimeReplayState(BaseModel):
    """Materialized replay result: candidate and committed stay distinct."""

    execution_nodes: dict[str, dict[str, object]] = Field(default_factory=dict)
    solver_nodes: dict[str, dict[str, object]] = Field(default_factory=dict)
    overlays: dict[str, dict[str, object]] = Field(default_factory=dict)
    directory: dict[str, dict[str, object]] = Field(default_factory=dict)
    processed_event_digests: dict[str, str] = Field(default_factory=dict)
    applied_dedupe_keys: frozenset[str] = frozenset()
    record_version_digests: dict[str, str] = Field(default_factory=dict)
    record_versions: dict[str, int] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid", frozen=True)


class RuntimeReplayError(RuntimeError):
    """Replay failed closed; the detail carries the invariant."""


def create_runtime_event(
    *,
    event_id: str,
    dedupe_key: str,
    graph_type: str,
    entity_type: str,
    operation: str,
    entity_id: str,
    entity: dict[str, object],
    metadata_version: int,
    task_id: str,
    solver_run_id: str | None = None,
    is_candidate: bool = False,
) -> RuntimeEventEnvelope:
    """Build one envelope, computing its digest over the closed fields."""
    payload = {
        "event_id": event_id,
        "dedupe_key": dedupe_key,
        "graph_type": graph_type,
        "entity_type": entity_type,
        "operation": operation,
        "entity_id": entity_id,
        "record_id": entity_id,
        "entity": entity,
        "metadata_version": metadata_version,
        "is_candidate": is_candidate,
        "is_committed": not is_candidate,
        "task_id": task_id,
        "solver_run_id": solver_run_id,
    }
    return RuntimeEventEnvelope.model_validate(
        {**payload, "event_digest": canonical_runtime_digest((_EVENT_DIGEST_DOMAIN, payload))}
    )


def _batch_digest(repository_id: str, sequence: int, events: tuple[RuntimeEventEnvelope, ...]) -> str:
    return canonical_runtime_digest((
        _EVENT_BATCH_DIGEST_DOMAIN, repository_id, sequence, tuple(event.event_digest for event in events),
    ))


def create_runtime_batch(
    *, repository_id: str, sequence: int, events: tuple[RuntimeEventEnvelope, ...]
) -> RuntimeEventBatch:
    """Build one batch with its canonical digest over the event digests."""
    return RuntimeEventBatch(
        repository_id=repository_id,
        sequence=sequence,
        events=events,
        event_batch_digest=_batch_digest(repository_id, sequence, events),
    )


def reduce_runtime_batch(
    state: RuntimeReplayState, batch: RuntimeEventBatch
) -> RuntimeReplayState:
    """Apply one complete batch atomically or fail the whole batch.

    Duplicate delivery of a byte-identical envelope is idempotent
    (skipped); a non-identical envelope claiming the same entity identity
    and version is a storage-integrity conflict that fails closed before
    either event is selected.
    """
    current = state
    for event in batch.events:
        seen_digest = current.processed_event_digests.get(event.event_id)
        if seen_digest is not None:
            if seen_digest != event.event_digest:
                raise RuntimeReplayError(
                    "memory_integrity_conflict: event id"
                    f" {event.event_id} reused with a different envelope"
                )
            continue  # byte-identical redelivery: idempotent skip
        if event.dedupe_key in current.applied_dedupe_keys:
            raise RuntimeReplayError(
                f"memory_integrity_conflict: divergent reuse of dedupe key"
                f" {event.dedupe_key}"
            )
        target = _target_view(event)
        index = _index_key(event)
        record_version = int(event.entity.get("version", event.metadata_version))  # type: ignore[arg-type]
        record_key = canonical_runtime_digest((
            event.graph_type, event.entity_type, event.task_id, event.solver_run_id, event.record_id,
        ))
        version_key = canonical_runtime_digest((record_key, record_version))
        reserved_digest = current.record_version_digests.get(version_key)
        if reserved_digest is not None and reserved_digest != event.event_digest:
            raise RuntimeReplayError(
                f"memory_integrity_conflict: non-identical equal-version envelopes for {index}"
            )
        updates: dict[str, object] = {
            "processed_event_digests": {
                **current.processed_event_digests, event.event_id: event.event_digest,
            },
            "applied_dedupe_keys": current.applied_dedupe_keys | {event.dedupe_key},
            "record_version_digests": {
                **current.record_version_digests, version_key: event.event_digest,
            },
        }
        if record_version > current.record_versions.get(record_key, 0):
            view = dict(getattr(current, target))
            if event.operation == "delete":
                view[index] = {**view.get(index, event.entity), "deleted": True}
            else:
                view[index] = dict(event.entity)
            updates[target] = view
            updates["record_versions"] = current.record_versions | {record_key: record_version}
        current = current.model_copy(update=updates)
    return current


def replay_runtime_batches(
    batches: tuple[RuntimeEventBatch, ...],
) -> RuntimeReplayState:
    """Genesis replay: contiguous batches, complete history only."""
    state = RuntimeReplayState()
    if not batches:
        return state
    repository_id = batches[0].repository_id
    expected_sequence = 1
    for batch in batches:
        if batch.repository_id != repository_id:
            raise RuntimeReplayError("memory_integrity_conflict: replay spans distinct repositories")
        if batch.sequence != expected_sequence:
            raise RuntimeReplayError(
                f"batch position gap: expected {expected_sequence},"
                f" got {batch.sequence}"
            )
        state = reduce_runtime_batch(state, batch)
        expected_sequence += 1
    return state


def _target_view(event: RuntimeEventEnvelope) -> str:
    if event.graph_type == "execution":
        return "execution_nodes"
    if event.graph_type == "solver":
        return "solver_nodes" if event.entity_type != "overlay" else "overlays"
    return "directory"


def _index_key(event: RuntimeEventEnvelope) -> str:
    if event.solver_run_id:
        return f"{event.solver_run_id}:{event.entity_id}"
    return event.entity_id


__all__ = [
    "EVENT_BUSINESS_LABELS",
    "create_runtime_batch",
    "LEGAL_COMBINATIONS",
    "RuntimeEventBatch",
    "RuntimeEventEnvelope",
    "RuntimeReplayError",
    "RuntimeReplayState",
    "create_runtime_event",
    "reduce_runtime_batch",
    "replay_runtime_batches",
]
