"""Sealed graph snapshots and bounded CAS revalidation for identity compilation."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Protocol, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_evolution.graph_records import GraphStateSnapshot
from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value
from memorii.core.memory_evolution.reference_integrity import ReferenceEdgeLedgerSnapshot
from memorii.core.semantic_ingestion.event_replay import SemanticReplayState

_Result = TypeVar("_Result")


def _digest(domain: bytes, value: object) -> str:
    return sha256(domain + encode_typed_value(_canonical(value))).hexdigest()


def _canonical(value: object) -> object:
    if isinstance(value, BaseModel):
        return _canonical(value.model_dump(mode="python"))
    if isinstance(value, dict):
        return {key: _canonical(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_canonical(item) for item in value)
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    return value


class GraphSnapshotReader(Protocol):
    def semantic_replay_state(self) -> SemanticReplayState: ...
    def reference_integrity_snapshot(self) -> ReferenceEdgeLedgerSnapshot: ...
    def graph_state_snapshot(self) -> GraphStateSnapshot: ...


class GraphReadSetToken(BaseModel):
    graph_revision: str = Field(min_length=1)
    replay_state_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    reference_ledger_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    read_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_token(self) -> GraphReadSetToken:
        body = self.model_dump(mode="python", exclude={"read_set_digest"})
        if self.read_set_digest != _digest(b"memorii.graph-read-set-token.v1\0", body):
            raise ValueError("graph_read_set_digest_mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> GraphReadSetToken:
        return cls.model_validate(
            values | {"read_set_digest": _digest(b"memorii.graph-read-set-token.v1\0", values)}
        )


class SealedGraphStateSnapshot(BaseModel):
    graph_state: SemanticReplayState
    canonical_graph: GraphStateSnapshot
    reference_integrity: ReferenceEdgeLedgerSnapshot
    read_set: GraphReadSetToken
    system_as_of: datetime
    snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_snapshot(self) -> SealedGraphStateSnapshot:
        if self.system_as_of.tzinfo is None or self.system_as_of.utcoffset() != timedelta(0):
            raise ValueError("graph_snapshot_time_must_be_utc")
        if (
            self.read_set.graph_revision != self.graph_state.graph_revision
            or self.canonical_graph.graph_revision != self.graph_state.graph_revision
            or self.read_set.replay_state_digest != self.graph_state.state_digest
            or self.read_set.reference_ledger_digest != self.reference_integrity.ledger_digest
        ):
            raise ValueError("graph_snapshot_read_set_mismatch")
        if not self.reference_integrity.active:
            raise ValueError("unresolved_reference_integrity_not_bootstrapped")
        body = self.model_dump(mode="python", exclude={"snapshot_digest"})
        if self.snapshot_digest != _digest(b"memorii.sealed-graph-state-snapshot.v1\0", body):
            raise ValueError("graph_snapshot_digest_mismatch")
        return self

    @classmethod
    def create(cls, **values: object) -> SealedGraphStateSnapshot:
        return cls.model_validate(
            values | {"snapshot_digest": _digest(b"memorii.sealed-graph-state-snapshot.v1\0", values)}
        )


class SemanticIngestionTransactionCoordinator:
    """Acquire one immutable authority pair and retry one stale CAS observation."""

    def __init__(
        self,
        reader: GraphSnapshotReader,
        *,
        now_provider: Callable[[], datetime] = lambda: datetime.now(UTC),
        max_related_conflicts: int = 1,
    ) -> None:
        if max_related_conflicts != 1:
            raise ValueError("identity transaction coordinator requires exactly one bounded retry")
        self._reader = reader
        self._now = now_provider

    def acquire_snapshot(self) -> SealedGraphStateSnapshot:
        # Read graph twice around the ledger read. A concurrent atomic publication
        # can never be combined into a mixed snapshot.
        first = self._reader.semantic_replay_state()
        ledger = self._reader.reference_integrity_snapshot()
        canonical_graph = self._reader.graph_state_snapshot()
        second = self._reader.semantic_replay_state()
        partition_versions = {
            item.partition_id: item.version
            for item in canonical_graph.read_set.partition_versions
        }
        if (
            first != second
            or partition_versions.get("canonical_graph") != first.state_digest
            or partition_versions.get("reference_ledger") != ledger.ledger_digest
        ):
            raise ValueError("stale_graph_snapshot")
        token = GraphReadSetToken.create(
            graph_revision=first.graph_revision,
            replay_state_digest=first.state_digest,
            reference_ledger_digest=ledger.ledger_digest,
        )
        return SealedGraphStateSnapshot.create(
            graph_state=first,
            canonical_graph=canonical_graph,
            reference_integrity=ledger,
            read_set=token,
            system_as_of=self._now().astimezone(UTC),
        )

    def execute(self, compile_once: Callable[[SealedGraphStateSnapshot], _Result]) -> _Result:
        for attempt in range(2):
            snapshot = self.acquire_snapshot()
            result = compile_once(snapshot)
            current = self._reader.semantic_replay_state()
            current_ledger = self._reader.reference_integrity_snapshot()
            if (
                current.state_digest == snapshot.read_set.replay_state_digest
                and current_ledger.ledger_digest == snapshot.read_set.reference_ledger_digest
            ):
                return result
            if attempt == 1:
                raise ValueError("related_graph_conflict_retry_exhausted")
        raise AssertionError("unreachable bounded transaction retry")


__all__ = [
    "GraphReadSetToken", "GraphSnapshotReader", "SealedGraphStateSnapshot",
    "SemanticIngestionTransactionCoordinator",
]
