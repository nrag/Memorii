"""Retrieval domain schemas and intent contracts."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from memorii.domain.enums import MemoryDomain


class RetrievalIntent(str, Enum):
    CONTINUE_EXECUTION = "continue_execution"
    DEBUG_OR_INVESTIGATE = "debug_or_investigate"
    ANSWER_WITH_USER_CONTEXT = "answer_with_user_context"
    RESUME_TASK = "resume_task"
    CONSOLIDATE_CASE = "consolidate_case"


class ValidityStatus(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    INVALIDATED = "invalidated"
    UNKNOWN = "unknown"


class RetrievalScope(BaseModel):
    task_id: str | None = None
    execution_node_id: str | None = None
    solver_run_id: str | None = None
    agent_id: str | None = None
    user_id: str | None = None
    artifact_id: str | None = None
    session_id: str | None = None
    thread_id: str | None = None

    model_config = ConfigDict(extra="forbid")


class RetrievalNamespace(BaseModel):
    memory_domain: MemoryDomain
    task_id: str | None = None
    execution_node_id: str | None = None
    solver_run_id: str | None = None
    agent_id: str | None = None
    artifact_id: str | None = None

    model_config = ConfigDict(extra="forbid")


class TimeRange(BaseModel):
    start: datetime | None = None
    end: datetime | None = None

    model_config = ConfigDict(extra="forbid")


class FreshnessPolicy(BaseModel):
    required_validity: ValidityStatus | None = None
    valid_at: datetime | None = None
    max_age_seconds: int | None = None

    model_config = ConfigDict(extra="forbid")


class DomainRetrievalQuery(BaseModel):
    domain: MemoryDomain
    scope: RetrievalScope
    namespace: RetrievalNamespace
    time_range: TimeRange | None = None
    freshness: FreshnessPolicy | None = None
    require_raw_transcript: bool = False

    model_config = ConfigDict(extra="forbid")


class RetrievalPlan(BaseModel):
    intent: RetrievalIntent
    queries: list[DomainRetrievalQuery] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")
