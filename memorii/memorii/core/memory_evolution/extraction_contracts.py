"""Typed contracts shared by memory extraction providers and consumers."""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.memory_evolution.models import (
    EntityMention,
    EntityType,
    ExtractedAction,
    ExtractedClaim,
    ExtractionFailureCode,
    ExtractionRun,
    ExtractionRunStatus,
    SourceObservation,
)


class MemoryExtractor(Protocol):
    @property
    def provider(self) -> str: ...

    @property
    def model(self) -> str | None: ...

    @property
    def prompt_hash(self) -> str | None: ...

    def extract(
        self,
        observations: list[SourceObservation],
    ) -> tuple[ExtractionRun, list[EntityMention], list[ExtractedClaim], list[ExtractedAction]]: ...


class MemoryExtractionRunError(RuntimeError):
    """Terminal extraction outcome that must not be committed as live success."""

    def __init__(self, run: ExtractionRun) -> None:
        if run.status != ExtractionRunStatus.FAILED or run.failure_code is None:
            raise ValueError("extraction failure requires a failed run with a failure code")
        super().__init__(f"memory extraction failed: {run.failure_code.value}")
        self.run = run

    @property
    def retryable(self) -> bool:
        return self.run.failure_code == ExtractionFailureCode.PROVIDER_ERROR


class ExtractedEntityOutput(BaseModel):
    entity_id: str
    mention_text: str
    normalized_name: str
    aliases: list[str]
    entity_type: EntityType
    source_id: str
    quote: str
    confidence: float = Field(ge=0.0, le=1.0)

    model_config = ConfigDict(extra="forbid")


class EmptyQualifiersOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExtractedClaimOutput(BaseModel):
    claim_id: str
    subject_entity_id: str
    predicate_id: Literal[
        "owner",
        "approver",
        "api_owner",
        "status",
        "preference",
        "dependency",
        "action_state",
        "belief",
        "correction",
        "entity_type",
        "semantic_fact",
    ]
    object_value: str
    object_entity_id: str | None
    scope_key: str
    qualifier_key: str
    qualifiers: EmptyQualifiersOutput
    valid_from: str | None
    valid_to: str | None
    source_id: str
    quote: str
    confidence: float = Field(ge=0.0, le=1.0)

    model_config = ConfigDict(extra="forbid")


class ExtractedActionOutput(BaseModel):
    action_id: str
    actor_entity_id: str | None
    action_type: str
    target_entity_ids: list[str]
    status: str
    dependency_ids: list[str]
    blocking_ids: list[str]
    timestamp: str | None
    source_id: str
    quote: str

    model_config = ConfigDict(extra="forbid")


class MemoryExtractionOutput(BaseModel):
    entities: list[ExtractedEntityOutput]
    claims: list[ExtractedClaimOutput]
    actions: list[ExtractedActionOutput]

    model_config = ConfigDict(extra="forbid")
