"""Durable, inert observations for learned-ontology coverage monitoring."""

from __future__ import annotations

import json
from datetime import datetime
from enum import StrEnum
from hashlib import sha256

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import (
    MemoryPlaneRevisionConflictError,
    RecordAbsentPrecondition,
    RecordDigestPrecondition,
    record_digest,
)
from memorii.core.semantic_ingestion.catalog_authority import CatalogAuthorityScope
from memorii.domain.enums import (
    CommitStatus,
    MemoryDomain,
    MemoryRecordVisibility,
    TemporalValidityStatus,
)


def _digest(domain: bytes, value: object) -> str:
    payload = json.dumps(
        value,
        default=str,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(domain + b"\0" + payload).hexdigest()


class CoverageSemanticOutcome(StrEnum):
    COVERED = "covered"
    UNSUPPORTED_RELATION = "unsupported_relation"
    UNSUPPORTED_ENTITY_TYPE = "unsupported_entity_type"
    UNCERTAIN = "uncertain"
    INELIGIBLE = "ineligible"
    NOT_EVALUATED = "not_evaluated"


class DiscoveryProcessingState(StrEnum):
    PENDING_NO_CAPABILITY = "discovery_pending_no_capability"
    QUEUED = "queued"
    RUNNING = "running"
    CLASSIFIED = "classified"
    UNAVAILABLE = "discovery_unavailable"
    INELIGIBLE = "ineligible"


class CoverageSourceSpan(BaseModel):
    start: int = Field(ge=0)
    end: int = Field(gt=0)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_order(self) -> CoverageSourceSpan:
        if self.end <= self.start:
            raise ValueError("coverage source span must be non-empty")
        return self


class ObserverBindingIdentity(BaseModel):
    binding_version: str = Field(min_length=1, max_length=256)
    provider: str = Field(min_length=1, max_length=128)
    model: str = Field(min_length=1, max_length=256)
    prompt_version: str = Field(min_length=1, max_length=256)
    transport: str = Field(min_length=1, max_length=128)
    egress_policy_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_schema_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)


class CoverageObservation(BaseModel):
    observation_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_span: CoverageSourceSpan | None = None
    source_scope_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    origin_lineage_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    session_id: str | None = None
    principal_id: str = Field(min_length=1)
    agent_id: str | None = None
    observed_at: datetime
    catalog_scope: CatalogAuthorityScope
    catalog_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    observer_binding: ObserverBindingIdentity | None = None
    semantic_outcome: CoverageSemanticOutcome
    processing_state: DiscoveryProcessingState
    downstream_failure_signature: str | None = Field(default=None, max_length=256)
    attempt_count: int = Field(ge=0)
    observation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_state(self) -> CoverageObservation:
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("coverage observation time must be timezone-aware")
        pending = self.processing_state == DiscoveryProcessingState.PENDING_NO_CAPABILITY
        if pending != (self.observer_binding is None):
            raise ValueError("observer binding and pending state are inconsistent")
        if self.processing_state in {
            DiscoveryProcessingState.PENDING_NO_CAPABILITY,
            DiscoveryProcessingState.QUEUED,
            DiscoveryProcessingState.RUNNING,
            DiscoveryProcessingState.UNAVAILABLE,
        } and self.semantic_outcome != CoverageSemanticOutcome.NOT_EVALUATED:
            raise ValueError("unclassified observation must be not_evaluated")
        if self.processing_state == DiscoveryProcessingState.CLASSIFIED and self.semantic_outcome in {
            CoverageSemanticOutcome.NOT_EVALUATED,
            CoverageSemanticOutcome.INELIGIBLE,
        }:
            raise ValueError("classified observation must have a classified outcome")
        if self.processing_state == DiscoveryProcessingState.INELIGIBLE and (
            self.semantic_outcome != CoverageSemanticOutcome.INELIGIBLE
        ):
            raise ValueError("ineligible processing requires ineligible outcome")
        body = self.model_dump(mode="json", exclude={"observation_digest"})
        expected = _digest(b"memorii.learned-ontology.coverage-observation.v1", body)
        if self.observation_digest != expected:
            raise ValueError("coverage observation digest mismatch")
        binding_version = self.observer_binding.binding_version if self.observer_binding else "none"
        expected_id = coverage_observation_id(
            source_id=self.source_id,
            source_digest=self.source_digest,
            catalog_digest=self.catalog_digest,
            observer_binding_version=binding_version,
        )
        if self.observation_id != expected_id:
            raise ValueError("coverage observation identity mismatch")
        return self


def coverage_observation_id(
    *,
    source_id: str,
    source_digest: str,
    catalog_digest: str,
    observer_binding_version: str | None,
) -> str:
    digest = _digest(
        b"memorii.learned-ontology.coverage-observation-id.v1",
        (source_id, source_digest, catalog_digest, observer_binding_version or "none"),
    )
    return f"coverage-observation:v1:{digest}"


def delivery_origin_lineage_digest(
    *, principal_binding_digest: str, normalized_delivery_id_digest: str
) -> str:
    """Derive the v1 lineage for a directly authenticated source delivery."""

    return _digest(
        b"memorii.learned-ontology.direct-delivery-origin-lineage.v1",
        (principal_binding_digest, normalized_delivery_id_digest),
    )


def new_coverage_observation(
    *,
    source_id: str,
    source_digest: str,
    source_span: CoverageSourceSpan | None,
    source_scope_digest: str,
    origin_lineage_digest: str,
    session_id: str | None,
    principal_id: str,
    agent_id: str | None,
    observed_at: datetime,
    catalog_scope: CatalogAuthorityScope,
    catalog_digest: str,
    observer_binding: ObserverBindingIdentity | None,
    downstream_failure_signature: str | None = None,
) -> CoverageObservation:
    state = (
        DiscoveryProcessingState.PENDING_NO_CAPABILITY
        if observer_binding is None
        else DiscoveryProcessingState.QUEUED
    )
    observation_id = coverage_observation_id(
        source_id=source_id,
        source_digest=source_digest,
        catalog_digest=catalog_digest,
        observer_binding_version=(observer_binding.binding_version if observer_binding else None),
    )
    draft = CoverageObservation.model_construct(
        observation_id=observation_id,
        source_id=source_id,
        source_digest=source_digest,
        source_span=source_span,
        source_scope_digest=source_scope_digest,
        origin_lineage_digest=origin_lineage_digest,
        session_id=session_id,
        principal_id=principal_id,
        agent_id=agent_id,
        observed_at=observed_at,
        catalog_scope=catalog_scope,
        catalog_digest=catalog_digest,
        observer_binding=observer_binding,
        semantic_outcome=CoverageSemanticOutcome.NOT_EVALUATED,
        processing_state=state,
        downstream_failure_signature=downstream_failure_signature,
        attempt_count=0,
        observation_digest="0" * 64,
    )
    body = draft.model_dump(mode="json", exclude={"observation_digest"})
    return CoverageObservation.model_validate(
        {
            **draft.model_dump(mode="python", exclude={"observation_digest"}),
            "observation_digest": _digest(
                b"memorii.learned-ontology.coverage-observation.v1", body
            ),
        }
    )


def start_coverage_observation(
    observation: CoverageObservation,
) -> CoverageObservation:
    if (
        observation.processing_state != DiscoveryProcessingState.QUEUED
        or observation.semantic_outcome != CoverageSemanticOutcome.NOT_EVALUATED
        or observation.observer_binding is None
    ):
        raise ValueError("only a queued bound observation can start")
    return _replace_observation(
        observation,
        processing_state=DiscoveryProcessingState.RUNNING,
        attempt_count=observation.attempt_count + 1,
    )


def classify_coverage_observation(
    observation: CoverageObservation,
    *,
    semantic_outcome: CoverageSemanticOutcome,
    source_span: CoverageSourceSpan | None,
) -> CoverageObservation:
    if (
        observation.processing_state != DiscoveryProcessingState.RUNNING
        or observation.observer_binding is None
    ):
        raise ValueError("only a running bound observation can be classified")
    if semantic_outcome in {
        CoverageSemanticOutcome.NOT_EVALUATED,
        CoverageSemanticOutcome.INELIGIBLE,
    }:
        raise ValueError("classification outcome is invalid")
    if semantic_outcome in {
        CoverageSemanticOutcome.UNSUPPORTED_RELATION,
        CoverageSemanticOutcome.UNSUPPORTED_ENTITY_TYPE,
    } and source_span is None:
        raise ValueError("verified ontology gaps require an exact source span")
    return _replace_observation(
        observation,
        semantic_outcome=semantic_outcome,
        processing_state=DiscoveryProcessingState.CLASSIFIED,
        source_span=source_span,
    )


def _replace_observation(
    observation: CoverageObservation, **changes: object
) -> CoverageObservation:
    draft = observation.model_copy(
        update={**changes, "observation_digest": "0" * 64}
    )
    body = draft.model_dump(mode="json", exclude={"observation_digest"})
    return CoverageObservation.model_validate(
        {
            **draft.model_dump(mode="python", exclude={"observation_digest"}),
            "observation_digest": _digest(
                b"memorii.learned-ontology.coverage-observation.v1", body
            ),
        }
    )


class CoverageObservationRepository:
    _KIND = "learned_ontology_coverage_observation_v1"

    def __init__(self, memory_plane: MemoryPlaneService) -> None:
        self._plane = memory_plane

    def load(self, observation_id: str) -> CoverageObservation | None:
        record = self._plane.get_record(observation_id)
        if (
            record is None
            or record.domain != MemoryDomain.EXECUTION
            or record.visibility != MemoryRecordVisibility.INTERNAL_CONTROL
            or record.source_kind != self._KIND
        ):
            return None
        try:
            return CoverageObservation.model_validate(record.content["observation"])
        except (KeyError, TypeError, ValueError):
            return None

    def create(self, observation: CoverageObservation) -> CoverageObservation:
        record = coverage_observation_record(observation)
        try:
            self._plane.conditionally_write_records(
                (record,),
                preconditions=(RecordAbsentPrecondition(memory_id=record.memory_id),),
            )
            return observation
        except MemoryPlaneRevisionConflictError:
            existing = self.load(observation.observation_id)
            if existing == observation:
                assert existing is not None
                return existing
            raise

    def replace(
        self,
        observation: CoverageObservation,
        *,
        previous: CoverageObservation,
    ) -> CoverageObservation:
        if observation.observation_id != previous.observation_id:
            raise ValueError("coverage observation replacement changed identity")
        record = coverage_observation_record(observation)
        self._plane.conditionally_write_records(
            (record,),
            preconditions=(
                RecordDigestPrecondition(
                    memory_id=observation.observation_id,
                    expected_digest=record_digest(
                        coverage_observation_record(previous)
                    ),
                ),
            ),
        )
        return observation



def coverage_observation_record(observation: CoverageObservation) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=observation.observation_id,
        domain=MemoryDomain.EXECUTION,
        text=observation.processing_state.value,
        content={
            "kind": CoverageObservationRepository._KIND,
            "observation": observation.model_dump(mode="json"),
        },
        status=CommitStatus.COMMITTED,
        validity_status=TemporalValidityStatus.ACTIVE,
        source_kind=CoverageObservationRepository._KIND,
        timestamp=observation.observed_at,
        session_id=observation.session_id,
        user_id=observation.principal_id,
        agent_id=observation.agent_id,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )
