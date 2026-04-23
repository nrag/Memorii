"""Canonical internal memory-plane record and edge conversion helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.provider.models import ProviderStoredRecord
from memorii.domain.common import Provenance, RoutingInfo
from memorii.domain.enums import CommitStatus, Durability, MemoryDomain, MemoryScope, SourceType, TemporalValidityStatus
from memorii.domain.memory_object import MemoryObject


class CanonicalMemoryRecord(BaseModel):
    memory_id: str
    domain: MemoryDomain
    text: str
    content: dict[str, Any] = Field(default_factory=dict)
    status: CommitStatus
    validity_status: TemporalValidityStatus | None = None
    source_kind: str = "unknown"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    session_id: str | None = None
    task_id: str | None = None
    execution_node_id: str | None = None
    solver_run_id: str | None = None
    user_id: str | None = None
    agent_id: str | None = None
    is_raw_event: bool = False
    source_candidate_id: str | None = None
    promotion_state: str | None = None
    supersedes_memory_ids: list[str] = Field(default_factory=list)
    duplicate_of_memory_id: str | None = None
    rejected_reason: str | None = None
    conflict_with_memory_ids: list[str] = Field(default_factory=list)
    episode_id: str | None = None

    model_config = ConfigDict(extra="forbid")


def from_memory_object(memory_object: MemoryObject, *, source_kind: str = "runtime") -> CanonicalMemoryRecord:
    namespace = memory_object.namespace or {}
    text = _text_from_content(memory_object.content)
    return CanonicalMemoryRecord(
        memory_id=memory_object.memory_id,
        domain=memory_object.memory_type,
        text=text,
        content=dict(memory_object.content),
        status=memory_object.status,
        validity_status=memory_object.validity_status,
        source_kind=source_kind,
        timestamp=memory_object.provenance.created_at,
        valid_from=memory_object.valid_from,
        valid_to=memory_object.valid_to,
        session_id=namespace.get("session_id"),
        task_id=namespace.get("task_id"),
        execution_node_id=namespace.get("execution_node_id"),
        solver_run_id=namespace.get("solver_run_id"),
        user_id=namespace.get("user_id"),
        agent_id=namespace.get("agent_id"),
        is_raw_event=memory_object.memory_type == MemoryDomain.TRANSCRIPT,
    )


def from_provider_stored_record(record: ProviderStoredRecord, *, source_kind: str = "provider") -> CanonicalMemoryRecord:
    validity_status = TemporalValidityStatus.ACTIVE if record.status == CommitStatus.COMMITTED.value else None
    return CanonicalMemoryRecord(
        memory_id=record.memory_id,
        domain=record.domain,
        text=record.text,
        content={"text": record.text},
        status=CommitStatus(record.status),
        validity_status=validity_status,
        source_kind=source_kind,
        timestamp=record.timestamp,
        session_id=record.session_id,
        task_id=record.task_id,
        user_id=record.user_id,
        is_raw_event=record.domain == MemoryDomain.TRANSCRIPT,
    )


def to_provider_stored_record(record: CanonicalMemoryRecord) -> ProviderStoredRecord:
    return ProviderStoredRecord(
        memory_id=record.memory_id,
        domain=record.domain,
        text=record.text,
        status=record.status.value,
        session_id=record.session_id,
        task_id=record.task_id,
        user_id=record.user_id,
        timestamp=record.timestamp,
    )


def to_memory_object(record: CanonicalMemoryRecord) -> MemoryObject:
    namespace: dict[str, str] = {"memory_domain": record.domain.value}
    if record.task_id is not None:
        namespace["task_id"] = record.task_id
    if record.execution_node_id is not None:
        namespace["execution_node_id"] = record.execution_node_id
    if record.solver_run_id is not None:
        namespace["solver_run_id"] = record.solver_run_id
    if record.agent_id is not None:
        namespace["agent_id"] = record.agent_id
    if record.user_id is not None:
        namespace["user_id"] = record.user_id
    if record.session_id is not None:
        namespace["session_id"] = record.session_id

    return MemoryObject(
        memory_id=record.memory_id,
        memory_type=record.domain,
        scope=_scope_for_record(record),
        durability=Durability.TASK_PERSISTENT,
        status=record.status,
        content=dict(record.content) if record.content else {"text": record.text},
        provenance=Provenance(
            source_type=SourceType.SYSTEM,
            source_refs=[record.memory_id],
            created_at=record.timestamp,
            created_by="memory_plane",
        ),
        routing=RoutingInfo(primary_store="memory_plane", secondary_stores=[]),
        namespace=namespace,
        valid_from=record.valid_from,
        valid_to=record.valid_to,
        validity_status=record.validity_status,
    )


def _text_from_content(content: dict[str, Any]) -> str:
    if "text" in content and isinstance(content["text"], str):
        return content["text"]
    if "summary" in content and isinstance(content["summary"], str):
        return content["summary"]
    return str(content)


def _scope_for_record(record: CanonicalMemoryRecord) -> MemoryScope:
    if record.execution_node_id is not None or record.solver_run_id is not None:
        return MemoryScope.EXECUTION_NODE
    if record.user_id is not None:
        return MemoryScope.USER
    return MemoryScope.TASK
