"""Routing domain schemas for cross-memory control plane."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryScope
from memorii.domain.memory_object import MemoryObject


class InboundEventClass(str, Enum):
    USER_MESSAGE = "user_message"
    AGENT_MESSAGE = "agent_message"
    TOOL_RESULT = "tool_result"
    TOOL_STATE_UPDATE = "tool_state_update"
    EXECUTION_STATE_UPDATE = "execution_state_update"
    SOLVER_OBSERVATION = "solver_observation"
    SOLVER_RESOLUTION = "solver_resolution"
    VALIDATED_ABSTRACTION_CANDIDATE = "validated_abstraction_candidate"
    USER_PREFERENCE_CANDIDATE = "user_preference_candidate"
    CHECKPOINT_EVENT = "checkpoint_event"
    RESUME_EVENT = "resume_event"


class InboundEvent(BaseModel):
    event_id: str
    event_class: InboundEventClass
    task_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    execution_node_id: str | None = None
    solver_run_id: str | None = None
    session_id: str | None = None
    thread_id: str | None = None
    user_id: str | None = None
    agent_id: str | None = None
    timestamp: datetime

    model_config = ConfigDict(extra="forbid")


class NamespaceKey(BaseModel):
    memory_domain: MemoryDomain
    task_id: str | None = None
    execution_node_id: str | None = None
    solver_run_id: str | None = None
    agent_id: str | None = None
    artifact_id: str | None = None

    model_config = ConfigDict(extra="forbid")


class RoutingMetadata(BaseModel):
    scope: MemoryScope
    namespace: NamespaceKey
    primary_store: str
    secondary_stores: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class RoutedMemoryObject(BaseModel):
    memory_object: MemoryObject
    metadata: RoutingMetadata
    domain: MemoryDomain

    model_config = ConfigDict(extra="forbid")


class RoutingDecision(BaseModel):
    event_id: str
    routed_objects: list[RoutedMemoryObject] = Field(default_factory=list)
    blocked_domains: list[MemoryDomain] = Field(default_factory=list)
    policy_trace: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class WritebackEligibilityReason(str, Enum):
    SOLVER_RESOLVED = "solver_resolved"
    VALIDATED_ABSTRACTION = "validated_abstraction"
    DURABLE_USER_SIGNAL = "durable_user_signal"
    CHECKPOINT_SUMMARY = "checkpoint_summary"


class ValidationState(str, Enum):
    UNVALIDATED = "unvalidated"
    VALIDATED = "validated"
    REJECTED = "rejected"


class CandidateRoutingState(BaseModel):
    status: CommitStatus = CommitStatus.CANDIDATE
    validation_state: ValidationState = ValidationState.UNVALIDATED
    reason: WritebackEligibilityReason | None = None

    model_config = ConfigDict(extra="forbid")
