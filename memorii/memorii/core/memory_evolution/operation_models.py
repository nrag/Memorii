"""Typed state for durable memory-evolution operations."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_evolution.models import ExtractionRunStatus


class EvolutionOperationStatus(StrEnum):
    PENDING = "evolution_pending"
    RUNNING = "evolution_running"
    COMMITTED = "evolution_committed"
    FAILED = "evolution_failed"


class EvolutionFailureCategory(StrEnum):
    PROVIDER_ERROR = "provider_error"
    EXTRACTION_OUTPUT_ERROR = "extraction_output_error"
    REVISION_CONFLICT = "revision_conflict"
    STORE_ERROR = "store_error"
    CORRUPTION_ERROR = "corruption_error"
    VALIDATION_ERROR = "validation_error"
    RETRY_EXHAUSTED = "retry_exhausted"
    LEASE_RECOVERY_EXHAUSTED = "lease_recovery_exhausted"
    UNEXPECTED_ERROR = "unexpected_error"


class EvolutionFailure(BaseModel):
    category: EvolutionFailureCategory
    error_type: str = Field(min_length=1)
    message: str = Field(min_length=1)
    retryable: bool

    model_config = ConfigDict(extra="forbid")


class EvolutionOperation(BaseModel):
    operation_id: str = Field(min_length=1)
    source_record_ids: list[str] = Field(min_length=1)
    source_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    defer_assertions: bool
    status: EvolutionOperationStatus
    state_revision: int = Field(default=0, ge=0)
    attempt_count: int = Field(default=0, ge=0)
    lease_recovery_count: int = Field(default=0, ge=0)
    ownership_epoch: int = Field(default=0, ge=0)
    completed_fence_epoch: int | None = Field(default=None, ge=1)
    extraction_run_id: str | None = None
    extraction_status: ExtractionRunStatus | None = None
    fallback_provider: str | None = None
    projection_record_ids: list[str] = Field(default_factory=list)
    execution_token: str | None = None
    lease_expires_at: datetime | None = None
    failure: EvolutionFailure | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_state(self) -> EvolutionOperation:
        if len(set(self.source_record_ids)) != len(self.source_record_ids):
            raise ValueError("source_record_ids must be unique")
        if any(not source_id.strip() for source_id in self.source_record_ids):
            raise ValueError("source_record_ids must be non-empty")
        if self.created_at.tzinfo is None or self.updated_at.tzinfo is None:
            raise ValueError("operation timestamps must be timezone-aware")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not precede created_at")
        if self.lease_expires_at is not None and self.lease_expires_at.tzinfo is None:
            raise ValueError("lease_expires_at must be timezone-aware")
        if self.status == EvolutionOperationStatus.RUNNING:
            if not self.execution_token or self.lease_expires_at is None:
                raise ValueError("running operation requires an execution token and lease")
            if self.attempt_count < 1:
                raise ValueError("running operation requires at least one attempt")
            if self.ownership_epoch < 1:
                raise ValueError("running operation requires a positive ownership epoch")
        elif self.execution_token is not None or self.lease_expires_at is not None:
            raise ValueError("only running operations may hold an execution claim")
        if self.status == EvolutionOperationStatus.COMMITTED:
            if not self.extraction_run_id or self.extraction_status is None:
                raise ValueError("committed operation requires extraction identity and status")
            if self.extraction_status == ExtractionRunStatus.FAILED:
                raise ValueError("failed extraction cannot be committed")
            if self.extraction_status == ExtractionRunStatus.FALLBACK_SUCCEEDED and not self.fallback_provider:
                raise ValueError("committed fallback extraction requires fallback provider")
            if self.completed_fence_epoch != self.ownership_epoch or self.ownership_epoch < 1:
                raise ValueError("committed operation requires its completing ownership epoch")
        elif self.extraction_run_id is not None or self.projection_record_ids or self.fallback_provider is not None:
            raise ValueError("only committed operations may identify projection results")
        elif self.completed_fence_epoch is not None:
            raise ValueError("only committed operations may identify a completion fence")
        if self.status == EvolutionOperationStatus.FAILED and self.extraction_status not in {
            None,
            ExtractionRunStatus.FAILED,
        }:
            raise ValueError("failed operation may only identify a failed extraction")
        if self.status == EvolutionOperationStatus.FAILED:
            if self.failure is None:
                raise ValueError("failed operation requires failure details")
        elif self.failure is not None:
            raise ValueError("only failed operations may contain failure details")
        return self
