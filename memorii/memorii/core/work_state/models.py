"""Work-state schemas shared across provider and memory-plane paths."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AgentEventEnvelope(BaseModel):
    event_id: str
    provider: str
    operation: str
    session_id: str | None = None
    parent_session_id: str | None = None
    user_id: str | None = None
    agent_id: str | None = None
    task_id: str | None = None
    content: str
    assistant_content: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime

    model_config = ConfigDict(extra="forbid")


class WorkStateKind(str, Enum):
    NONE = "none"
    TASK_EXECUTION = "task_execution"
    INVESTIGATION = "investigation"
    DECISION = "decision"
    RESEARCH = "research"


class WorkStateStatus(str, Enum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    PAUSED = "paused"
    RESOLVED = "resolved"
    ABANDONED = "abandoned"


class WorkStateBindingStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    RESOLVED = "resolved"
    ABANDONED = "abandoned"


class WorkStateRecord(BaseModel):
    work_state_id: str
    kind: WorkStateKind
    status: WorkStateStatus
    task_id: str | None = None
    session_id: str | None = None
    user_id: str | None = None
    title: str
    summary: str
    confidence: float
    source_event_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(extra="forbid")


class WorkStateBinding(BaseModel):
    binding_id: str
    session_id: str | None = None
    task_id: str | None = None
    work_state_id: str | None = None
    execution_node_id: str | None = None
    solver_run_id: str | None = None
    status: WorkStateBindingStatus = WorkStateBindingStatus.ACTIVE
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(extra="forbid")


class WorkStateDetectionAction(str, Enum):
    NO_STATE_UPDATE = "no_state_update"
    CREATE_CANDIDATE_STATE = "create_candidate_state"
    UPDATE_EXISTING_STATE = "update_existing_state"
    COMMIT_STATE_UPDATE = "commit_state_update"


class WorkStateReasonCode(str, Enum):
    GENERIC_CHAT = "generic_chat"
    EXPLICIT_TASK_LANGUAGE = "explicit_task_language"
    TOOL_FAILURE_OR_ERROR = "tool_failure_or_error"
    DEBUGGING_LANGUAGE = "debugging_language"
    DECISION_LANGUAGE = "decision_language"
    RESEARCH_LANGUAGE = "research_language"
    DELEGATION_RESULT = "delegation_result"
    LOW_CONFIDENCE = "low_confidence"


class WorkStateDetectionDecision(BaseModel):
    action: WorkStateDetectionAction
    kind: WorkStateKind
    confidence: float
    task_id: str | None = None
    work_state_id: str | None = None
    title: str | None = None
    summary: str | None = None
    reason_codes: list[WorkStateReasonCode] = Field(default_factory=list)
    evidence_event_ids: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")
