"""Typed contracts shared by memory extraction providers and consumers."""

from __future__ import annotations

from collections.abc import Hashable, Sequence
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_evolution.models import (
    EntityMention,
    EntityType,
    EvidenceSpan,
    ExtractedAction,
    ExtractedClaim,
    ExtractedIdentityRelation,
    ExtractionFailureCode,
    ExtractionRun,
    ExtractionRunStatus,
    SourceObservation,
)


class MemoryExtractionProposal(BaseModel):
    """Source-grounded provider proposal awaiting state-aware compilation."""

    run: ExtractionRun
    entities: list[EntityMention] = Field(default_factory=list)
    claims: list[ExtractedClaim] = Field(default_factory=list)
    actions: list[ExtractedAction] = Field(default_factory=list)
    identity_relations: list[ExtractedIdentityRelation] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True, extra="forbid")

    @model_validator(mode="after")
    def validate_internal_references(self) -> MemoryExtractionProposal:
        entity_ids = [entity.entity_id for entity in self.entities]
        entity_keys = [(entity.entity_id, entity.scope.identity) for entity in self.entities]
        claim_ids = [claim.claim_id for claim in self.claims]
        action_ids = [action.action_id for action in self.actions]
        relation_ids = [relation.relation_id for relation in self.identity_relations]
        _require_unique(entity_keys, "scoped entity")
        _require_unique(claim_ids, "claim")
        _require_unique(action_ids, "action")
        _require_unique(relation_ids, "identity relation")
        if any(entity.aliases for entity in self.entities):
            raise ValueError("provider proposals cannot carry unverified entity aliases")
        _require_same_ids(self.run.entity_ids, entity_ids, "entity")
        _require_same_ids(self.run.claim_ids, claim_ids, "claim")
        _require_same_ids(self.run.action_ids, action_ids, "action")
        _require_same_ids(self.run.identity_relation_ids, relation_ids, "identity relation")

        declared_entities = set(entity_ids)
        input_sources = set(self.run.input_source_ids)
        for claim in self.claims:
            _require_extraction_run(claim.extraction_run_id, self.run.extraction_run_id, "claim", claim.claim_id)
            _require_declared_entity(
                claim.claim_key.subject_entity_id, declared_entities, "claim subject", claim.claim_id
            )
            if claim.object_entity_id is not None:
                _require_declared_entity(claim.object_entity_id, declared_entities, "claim object", claim.claim_id)
            _require_evidence_sources(claim.evidence_spans, input_sources, "claim", claim.claim_id)
        for action in self.actions:
            _require_extraction_run(action.extraction_run_id, self.run.extraction_run_id, "action", action.action_id)
            references = {
                *action.target_entity_ids,
                *action.dependency_entity_ids,
                *action.blocking_entity_ids,
                *([action.actor_entity_id] if action.actor_entity_id is not None else []),
            }
            for entity_id in references:
                _require_declared_entity(entity_id, declared_entities, "action", action.action_id)
            _require_evidence_sources(action.evidence_spans, input_sources, "action", action.action_id)
        for relation in self.identity_relations:
            _require_extraction_run(
                relation.extraction_run_id,
                self.run.extraction_run_id,
                "identity relation",
                relation.relation_id,
            )
            _require_declared_entity(
                relation.source_entity_id,
                declared_entities,
                "identity relation source",
                relation.relation_id,
            )
            _require_declared_entity(
                relation.target_entity_id,
                declared_entities,
                "identity relation target",
                relation.relation_id,
            )
            _require_evidence_sources(
                relation.evidence_spans,
                input_sources,
                "identity relation",
                relation.relation_id,
            )
        return self


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
    ) -> MemoryExtractionProposal: ...


class MemoryExtractionRunError(RuntimeError):
    """Terminal extraction outcome that must not be committed as live success."""

    def __init__(self, run: ExtractionRun) -> None:
        if run.status not in {ExtractionRunStatus.FAILED, ExtractionRunStatus.PARTIAL} or run.failure_code is None:
            raise ValueError("non-committable extraction requires a failed or partial run with a failure code")
        super().__init__(f"memory extraction is not commit-eligible: {run.status.value}:{run.failure_code.value}")
        self.run = run

    @property
    def retryable(self) -> bool:
        return self.run.failure_code == ExtractionFailureCode.PROVIDER_ERROR


class ExtractedEntityOutput(BaseModel):
    entity_ref: str = Field(min_length=1)
    mention_text: str
    entity_type: EntityType
    source_id: str
    quote: str
    confidence: float = Field(ge=0.0, le=1.0)

    model_config = ConfigDict(extra="forbid")


class ExtractedClaimOutput(BaseModel):
    subject_entity_ref: str = Field(min_length=1)
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
    object_entity_ref: str | None
    source_id: str
    quote: str
    confidence: float = Field(ge=0.0, le=1.0)

    model_config = ConfigDict(extra="forbid")


class ExtractedActionOutput(BaseModel):
    action_ref: str = Field(min_length=1)
    actor_entity_ref: str | None
    action_type: str
    target_entity_refs: list[str]
    status: str
    dependency_entity_refs: list[str]
    blocking_entity_refs: list[str]
    source_id: str
    quote: str

    model_config = ConfigDict(extra="forbid")


class ExtractedIdentityRelationOutput(BaseModel):
    relation_ref: str = Field(min_length=1)
    relation_type: Literal["alias_of", "same_as", "split_from", "merged_into"]
    source_entity_ref: str = Field(min_length=1)
    target_entity_ref: str = Field(min_length=1)
    source_id: str
    quote: str
    confidence: float = Field(ge=0.0, le=1.0)

    model_config = ConfigDict(extra="forbid")


class MemoryExtractionOutput(BaseModel):
    entities: list[ExtractedEntityOutput]
    claims: list[ExtractedClaimOutput]
    actions: list[ExtractedActionOutput]
    identity_relations: list[ExtractedIdentityRelationOutput]

    model_config = ConfigDict(extra="forbid")


def _require_unique(values: Sequence[Hashable], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {label} IDs in extraction proposal")


def _require_same_ids(recorded: list[str], actual: list[str], label: str) -> None:
    if len(recorded) != len(set(recorded)) or set(recorded) != set(actual):
        raise ValueError(f"extraction run {label} IDs do not match the proposal payload")


def _require_extraction_run(actual: str, expected: str, label: str, item_id: str) -> None:
    if actual != expected:
        raise ValueError(f"{label} {item_id!r} belongs to a different extraction run")


def _require_declared_entity(entity_id: str, declared: set[str], label: str, item_id: str) -> None:
    if entity_id not in declared:
        raise ValueError(f"{label} {item_id!r} references undeclared entity {entity_id!r}")


def _require_evidence_sources(
    spans: list[EvidenceSpan],
    input_sources: set[str],
    label: str,
    item_id: str,
) -> None:
    source_ids = {span.source_id for span in spans}
    if not source_ids or not source_ids <= input_sources:
        raise ValueError(f"{label} {item_id!r} evidence is outside the extraction input sources")


@runtime_checkable
class StructuredProposalProvider(Protocol):
    """Extractor capability for replaying schema-valid provider proposals."""

    @property
    def structured_proposal(self) -> MemoryExtractionOutput | None: ...
