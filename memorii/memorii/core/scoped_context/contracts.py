"""Closed public contracts for scoped context activation."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, model_validator

from memorii.core.memory_evolution.retrieval_contracts import MemoryQueryInput
from memorii.core.scoped_context.authority import ScopedAuthorityBindingReceipt
from memorii.domain.enums import MemoryDomain


class ScopedContextChannel(StrEnum):
    MANDATORY = "mandatory"
    SEMANTIC_BM25 = "semantic_bm25"
    EPISODIC_BM25 = "episodic_bm25"
    STRUCTURED_GRAPH = "structured_graph"


class ScopedContextStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL_OPTIONAL = "partial_optional"
    DENIED = "denied"
    INVALID_REQUEST = "invalid_request"
    MANDATORY_UNRESOLVED = "mandatory_unresolved"
    MANDATORY_OVERFLOW = "mandatory_overflow"
    UNAVAILABLE = "unavailable"


class ScopedOmissionReason(StrEnum):
    EMPTY_QUERY = "empty_query"
    NO_MATCH = "no_match"
    OPTIONAL_LIMIT = "optional_limit"
    RENDERED_BYTE_LIMIT = "rendered_byte_limit"
    SCORER_UNAVAILABLE = "scorer_unavailable"
    PROVENANCE_UNAVAILABLE = "provenance_unavailable"
    STRUCTURED_NO_MATCH = "structured_no_match"
    STRUCTURED_ABSTAINED = "structured_abstained"
    STRUCTURED_UNSUPPORTED_QUERY = "structured_unsupported_query"
    STRUCTURED_UNAVAILABLE = "structured_unavailable"


class ScopedRecordReference(BaseModel):
    record_id: str = Field(min_length=1)
    purpose: Literal["state", "artifact", "constraint"]
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_identity(self) -> ScopedRecordReference:
        if not self.record_id.strip():
            raise ValueError("record_id must be nonblank")
        return self


class ScopedContextBudget(BaseModel):
    max_mandatory_items: PositiveInt
    max_optional_items: PositiveInt
    max_optional_omission_ids: PositiveInt
    max_rendered_utf8_bytes: PositiveInt
    model_config = ConfigDict(extra="forbid", frozen=True)


class ScopedContextRequest(BaseModel):
    host_task_id: str = Field(min_length=1)
    host_state_id: str = Field(min_length=1)
    declared_complete_mandatory_set: bool
    mandatory_record_references: tuple[ScopedRecordReference, ...]
    optional_query: str | None = None
    optional_domains: tuple[Literal[MemoryDomain.SEMANTIC, MemoryDomain.EPISODIC], ...] = ()
    budget: ScopedContextBudget
    reference_time: datetime
    structured_query: MemoryQueryInput | None = None
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_request(self) -> ScopedContextRequest:
        if not self.host_task_id.strip() or not self.host_state_id.strip():
            raise ValueError("host identities must be nonblank")
        if self.reference_time.tzinfo is None or self.reference_time.utcoffset() is None:
            raise ValueError("reference_time must be timezone-aware")
        if self.reference_time.utcoffset() != UTC.utcoffset(self.reference_time):
            raise ValueError("reference_time must be UTC")
        ids = [item.record_id for item in self.mandatory_record_references]
        if len(ids) != len(set(ids)):
            raise ValueError("mandatory record IDs must be unique")
        if len(self.optional_domains) != len(set(self.optional_domains)):
            raise ValueError("optional domains must be unique")
        if self.structured_query is not None and self.structured_query.reference_time not in (None, self.reference_time):
            raise ValueError("structured query reference_time must match request")
        return self


class ScopedContextItem(BaseModel):
    channel: ScopedContextChannel
    record_id: str = Field(min_length=1)
    domain: MemoryDomain
    source_kind: str = Field(min_length=1)
    rendered_text: str
    source_record_ids: tuple[str, ...]
    provenance_ref: str | None = None
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_identities(self) -> ScopedContextItem:
        if not self.record_id.strip() or not self.source_kind.strip():
            raise ValueError("item identities must be nonblank")
        if any(not source_id.strip() for source_id in self.source_record_ids):
            raise ValueError("source record IDs must be nonblank")
        if self.provenance_ref is not None and not self.provenance_ref.strip():
            raise ValueError("provenance_ref must be nonblank when present")
        return self


class ScopedContextOmission(BaseModel):
    channel: ScopedContextChannel
    reason: ScopedOmissionReason
    omitted_count: int = Field(ge=0)
    omitted_record_ids: tuple[str, ...]
    identifiers_truncated: bool
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_identifiers(self) -> ScopedContextOmission:
        if any(not record_id.strip() for record_id in self.omitted_record_ids):
            raise ValueError("omitted record IDs must be nonblank")
        if len(self.omitted_record_ids) != len(set(self.omitted_record_ids)):
            raise ValueError("omitted record IDs must be unique")
        if self.omitted_count < len(self.omitted_record_ids):
            raise ValueError("omitted_count cannot be less than retained identifiers")
        if self.identifiers_truncated != (self.omitted_count > len(self.omitted_record_ids)):
            raise ValueError("identifiers_truncated must match retained identifier count")
        return self


class ScopedStructuredOutcome(BaseModel):
    status: Literal["answered", "no_match", "abstained"]
    claim_items: tuple[ScopedContextItem, ...]
    evidence_items: tuple[ScopedContextItem, ...]
    abstention_reason: str | None = None
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_shape(self) -> ScopedStructuredOutcome:
        claim_ids = [item.record_id for item in self.claim_items]
        evidence_ids = [item.record_id for item in self.evidence_items]
        if len(claim_ids) != len(set(claim_ids)) or len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("structured item identifiers must be unique")
        if set(claim_ids) & set(evidence_ids):
            raise ValueError("structured claims and evidence must be disjoint")
        if self.status == "answered":
            if not self.claim_items or not self.evidence_items or self.abstention_reason is not None:
                raise ValueError("answered structured outcome requires claims and evidence")
        elif self.status == "no_match":
            if self.claim_items or self.evidence_items or self.abstention_reason is not None:
                raise ValueError("no-match structured outcome cannot disclose items or a reason")
        elif self.claim_items or self.evidence_items or not self.abstention_reason:
            raise ValueError("abstained structured outcome requires only a reason")
        return self


class ScopedContextActivation(BaseModel):
    status: ScopedContextStatus
    request_task_id: str | None
    request_state_id: str | None
    authority_binding_receipt: ScopedAuthorityBindingReceipt | None
    memory_snapshot_revision: int | None
    mandatory_items: tuple[ScopedContextItem, ...]
    optional_items: tuple[ScopedContextItem, ...]
    omissions: tuple[ScopedContextOmission, ...]
    structured_outcome: ScopedStructuredOutcome | None
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True, frozen=True)

    @model_validator(mode="after")
    def validate_terminal_shape(self) -> ScopedContextActivation:
        failure_statuses = {
            ScopedContextStatus.DENIED,
            ScopedContextStatus.INVALID_REQUEST,
            ScopedContextStatus.MANDATORY_UNRESOLVED,
            ScopedContextStatus.MANDATORY_OVERFLOW,
            ScopedContextStatus.UNAVAILABLE,
        }
        if self.status in failure_statuses:
            if any((
                self.request_task_id is not None,
                self.request_state_id is not None,
                self.authority_binding_receipt is not None,
                self.memory_snapshot_revision is not None,
                self.mandatory_items,
                self.optional_items,
                self.omissions,
                self.structured_outcome,
            )):
                raise ValueError("failed scoped context outcomes must not disclose data")
        elif (
            self.request_task_id is None
            or self.request_state_id is None
            or self.authority_binding_receipt is None
            or self.memory_snapshot_revision is None
        ):
            raise ValueError("successful scoped context outcomes require request binding and snapshot")
        if self.status == ScopedContextStatus.COMPLETE and self.omissions:
            raise ValueError("complete scoped context outcomes cannot have omissions")
        if self.status == ScopedContextStatus.PARTIAL_OPTIONAL and not self.omissions:
            raise ValueError("partial scoped context outcomes require omissions")
        return self
