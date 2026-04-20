"""Typed writeback candidate models for consolidation outputs."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from memorii.domain.common import Provenance
from memorii.domain.enums import CommitStatus, MemoryDomain, TemporalValidityStatus
from memorii.domain.routing import ValidationState


class WritebackType(str, Enum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    USER = "user"
    SKILL = "skill"


class ValidityWindow(BaseModel):
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    validity_status: TemporalValidityStatus = TemporalValidityStatus.UNKNOWN

    model_config = ConfigDict(extra="forbid")


class WritebackCandidate(BaseModel):
    candidate_id: str
    writeback_type: WritebackType
    target_domain: MemoryDomain
    status: CommitStatus = CommitStatus.CANDIDATE
    content: dict[str, Any]
    provenance: Provenance
    source_refs: list[str] = Field(default_factory=list)
    source_task_id: str
    source_solver_run_id: str | None = None
    source_execution_node_id: str | None = None
    validation_state: ValidationState = ValidationState.UNVALIDATED
    eligibility_reason: str
    namespace: dict[str, str] | None = None
    validity_window: ValidityWindow | None = None

    model_config = ConfigDict(extra="forbid")
