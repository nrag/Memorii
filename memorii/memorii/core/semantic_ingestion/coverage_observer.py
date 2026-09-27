"""Provider-neutral execution boundary for ontology coverage observation."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from hashlib import sha256
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import (
    MemoryPlaneRevisionConflictError,
    RecordAbsentPrecondition,
)
from memorii.core.semantic_ingestion.coverage_observation import (
    CoverageObservation,
    CoverageObservationRepository,
    CoverageSemanticOutcome,
    CoverageSourceSpan,
    DiscoveryProcessingState,
    ObserverBindingIdentity,
    classify_coverage_observation,
    fail_coverage_observation,
    retry_coverage_observation,
    start_coverage_observation,
)
from memorii.core.semantic_ingestion.coverage_recurrence import (
    CoverageGapSignature,
    CoverageRecurrenceGroup,
    CoverageRecurrenceRepository,
    VerifiedCoverageGap,
    VerifiedCoverageGapRepository,
    build_coverage_recurrence_group,
)
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


class OntologyObservationRequest(BaseModel):
    observation_id: str = Field(min_length=1)
    observation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_text: str = Field(min_length=1, max_length=1_000_000)
    catalog_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @classmethod
    def create(
        cls, *, observation: CoverageObservation, source_text: str
    ) -> OntologyObservationRequest:
        body = {
            "observation_id": observation.observation_id,
            "observation_digest": observation.observation_digest,
            "source_text": source_text,
            "catalog_digest": observation.catalog_digest,
        }
        return cls(
            **body,
            request_digest=_digest(
                b"memorii.learned-ontology.observation-request.v1", body
            ),
        )

    @model_validator(mode="after")
    def validate_digest(self) -> OntologyObservationRequest:
        body = self.model_dump(mode="json", exclude={"request_digest"})
        if self.request_digest != _digest(
            b"memorii.learned-ontology.observation-request.v1", body
        ):
            raise ValueError("ontology observation request digest mismatch")
        return self


class OntologyObservationResult(BaseModel):
    semantic_outcome: CoverageSemanticOutcome
    source_span: CoverageSourceSpan | None = None
    source_quote: str | None = Field(default=None, max_length=16_384)
    signature: CoverageGapSignature | None = None
    result_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @classmethod
    def create(
        cls,
        *,
        semantic_outcome: CoverageSemanticOutcome,
        source_span: CoverageSourceSpan | None = None,
        source_quote: str | None = None,
        signature: CoverageGapSignature | None = None,
    ) -> OntologyObservationResult:
        body = {
            "semantic_outcome": semantic_outcome,
            "source_span": source_span,
            "source_quote": source_quote,
            "signature": signature,
        }
        draft = cls.model_construct(**body, result_digest="0" * 64)
        return cls(
            **body,
            result_digest=_digest(
                b"memorii.learned-ontology.observation-result.v1",
                draft.model_dump(mode="json", exclude={"result_digest"}),
            ),
        )

    @model_validator(mode="after")
    def validate_result(self) -> OntologyObservationResult:
        is_gap = self.semantic_outcome in {
            CoverageSemanticOutcome.UNSUPPORTED_RELATION,
            CoverageSemanticOutcome.UNSUPPORTED_ENTITY_TYPE,
        }
        if is_gap != (
            self.source_span is not None
            and self.source_quote is not None
            and self.signature is not None
        ):
            raise ValueError("ontology observer gap result shape is invalid")
        if self.signature is not None and (
            self.signature.kind != self.semantic_outcome.value
        ):
            raise ValueError("ontology observer signature kind is mismatched")
        if self.semantic_outcome in {
            CoverageSemanticOutcome.NOT_EVALUATED,
            CoverageSemanticOutcome.INELIGIBLE,
        }:
            raise ValueError("ontology observer returned a non-classification")
        body = self.model_dump(mode="json", exclude={"result_digest"})
        if self.result_digest != _digest(
            b"memorii.learned-ontology.observation-result.v1", body
        ):
            raise ValueError("ontology observation result digest mismatch")
        return self


class OntologyObserverCapability(Protocol):
    @property
    def binding(self) -> ObserverBindingIdentity: ...

    def observe(
        self, request: OntologyObservationRequest
    ) -> object: ...


class OntologyObserverUnavailableError(OSError):
    """The configured observer transport cannot complete this attempt."""


class DurableOntologyObservationResult(BaseModel):
    record_id: str = Field(min_length=1)
    observation_id: str = Field(min_length=1)
    running_observation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    result: OntologyObservationResult
    record_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @classmethod
    def create(
        cls,
        *,
        observation: CoverageObservation,
        result: OntologyObservationResult,
    ) -> DurableOntologyObservationResult:
        if observation.processing_state != DiscoveryProcessingState.RUNNING:
            raise ValueError("observer result requires a running observation")
        body = {
            "observation_id": observation.observation_id,
            "running_observation_digest": observation.observation_digest,
            "result": result,
        }
        digest = _digest(
            b"memorii.learned-ontology.durable-observation-result.v1",
            {
                **body,
                "result": result.model_dump(mode="json"),
            },
        )
        return cls(
            record_id=f"ontology-observer-result:v1:{digest}",
            record_digest=digest,
            **body,
        )

    @model_validator(mode="after")
    def validate_identity(self) -> DurableOntologyObservationResult:
        expected = _digest(
            b"memorii.learned-ontology.durable-observation-result.v1",
            {
                "observation_id": self.observation_id,
                "running_observation_digest": self.running_observation_digest,
                "result": self.result.model_dump(mode="json"),
            },
        )
        if self.record_digest != expected or self.record_id != (
            f"ontology-observer-result:v1:{expected}"
        ):
            raise ValueError("durable observer result identity mismatch")
        return self


class OntologyObservationResultRepository:
    _KIND = "learned_ontology_observer_result_v1"

    def __init__(self, memory_plane: MemoryPlaneService) -> None:
        self._plane = memory_plane

    def load_for_observation(
        self, observation_id: str
    ) -> DurableOntologyObservationResult | None:
        matches: list[DurableOntologyObservationResult] = []
        for record in self._plane.list_records(source_kind=self._KIND):
            try:
                result = DurableOntologyObservationResult.model_validate(
                    record.content["result"]
                )
            except (KeyError, TypeError, ValueError):
                continue
            if result.observation_id == observation_id:
                matches.append(result)
        if len(matches) > 1:
            raise ValueError("observation has multiple durable observer results")
        return matches[0] if matches else None

    def create(
        self,
        result: DurableOntologyObservationResult,
        *,
        observed_at: datetime,
    ) -> DurableOntologyObservationResult:
        record = CanonicalMemoryRecord(
            memory_id=result.record_id,
            domain=MemoryDomain.EXECUTION,
            text=result.result.semantic_outcome.value,
            content={"kind": self._KIND, "result": result.model_dump(mode="json")},
            status=CommitStatus.COMMITTED,
            validity_status=TemporalValidityStatus.ACTIVE,
            source_kind=self._KIND,
            timestamp=observed_at,
            visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
        )
        try:
            self._plane.conditionally_write_records(
                (record,),
                preconditions=(RecordAbsentPrecondition(memory_id=result.record_id),),
            )
        except MemoryPlaneRevisionConflictError:
            existing = self.load_for_observation(result.observation_id)
            if existing == result:
                return result
            raise
        return result


class CoverageObserverRunResult(BaseModel):
    observation: CoverageObservation
    recurrence_group: CoverageRecurrenceGroup | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)


class CoverageObserverRunner:
    """Validate one authorized observer result and update inert recurrence state."""

    def __init__(
        self,
        *,
        observation_repository: CoverageObservationRepository,
        gap_repository: VerifiedCoverageGapRepository,
        recurrence_repository: CoverageRecurrenceRepository,
        result_repository: OntologyObservationResultRepository,
        capability: OntologyObserverCapability,
        signature_validator: Callable[[CoverageGapSignature], bool],
    ) -> None:
        self._observations = observation_repository
        self._gaps = gap_repository
        self._recurrence = recurrence_repository
        self._results = result_repository
        self._capability = capability
        self._signature_validator = signature_validator

    @property
    def binding(self) -> ObserverBindingIdentity:
        return self._capability.binding

    def run(
        self, *, observation: CoverageObservation, source_text: str
    ) -> CoverageObserverRunResult:
        if observation.observer_binding != self._capability.binding:
            raise ValueError("ontology observer binding is not authorized")
        persisted = self._observations.load(observation.observation_id)
        if persisted != observation:
            raise ValueError("ontology observation is not the persisted head")
        head = observation
        if head.processing_state == DiscoveryProcessingState.QUEUED:
            running = start_coverage_observation(head)
            self._observations.replace(running, previous=head)
            head = running
        durable_result = self._results.load_for_observation(head.observation_id)
        if durable_result is None:
            if head.processing_state != DiscoveryProcessingState.RUNNING:
                return CoverageObserverRunResult(observation=head)
            request = OntologyObservationRequest.create(
                observation=head, source_text=source_text
            )
            try:
                raw_result = self._capability.observe(request)
            except OSError as exc:
                unavailable = fail_coverage_observation(
                    head,
                    failure_signature=_digest(
                        b"memorii.learned-ontology.observer-unavailable.v1",
                        type(exc).__name__,
                    ),
                )
                self._observations.replace(unavailable, previous=head)
                return CoverageObserverRunResult(observation=unavailable)
            result = self._validated_result(raw_result, source_text=source_text)
            durable_result = self._results.create(
                DurableOntologyObservationResult.create(
                    observation=head,
                    result=result,
                ),
                observed_at=head.observed_at,
            )
        result = durable_result.result
        if head.processing_state == DiscoveryProcessingState.RUNNING:
            classified = classify_coverage_observation(
                head,
                semantic_outcome=result.semantic_outcome,
                source_span=result.source_span,
            )
            self._observations.replace(classified, previous=head)
            head = classified
        elif head.processing_state != DiscoveryProcessingState.CLASSIFIED:
            return CoverageObserverRunResult(observation=head)
        if result.signature is None:
            return CoverageObserverRunResult(observation=head)
        gap = VerifiedCoverageGap.from_observation(
            head, signature=result.signature
        )
        self._gaps.create(gap)
        gaps = self._gaps.for_group(
            catalog_scope=gap.catalog_scope,
            catalog_digest=gap.catalog_digest,
            source_scope_digest=gap.source_scope_digest,
            signature=gap.signature,
        )
        group = build_coverage_recurrence_group(gaps)
        previous = self._recurrence.load(group.group_id)
        self._recurrence.write(group, previous=previous)
        return CoverageObserverRunResult(
            observation=head,
            recurrence_group=group,
        )

    def recover_interrupted(
        self, *, source_loader: Callable[[str], str | None]
    ) -> tuple[CoverageObserverRunResult, ...]:
        results: list[CoverageObserverRunResult] = []
        for observation in self._observations.all():
            if observation.observer_binding != self.binding:
                continue
            source_text = source_loader(observation.source_id)
            if source_text is None:
                continue
            head = observation
            if (
                head.processing_state == DiscoveryProcessingState.RUNNING
                and self._results.load_for_observation(head.observation_id) is None
            ):
                queued = retry_coverage_observation(
                    fail_coverage_observation(
                        head,
                        failure_signature="interrupted_observer_attempt",
                    )
                )
                self._observations.replace(queued, previous=head)
                head = queued
            if head.processing_state in {
                DiscoveryProcessingState.QUEUED,
                DiscoveryProcessingState.RUNNING,
                DiscoveryProcessingState.CLASSIFIED,
            }:
                results.append(self.run(observation=head, source_text=source_text))
        return tuple(results)

    def _validated_result(
        self, raw_result: object, *, source_text: str
    ) -> OntologyObservationResult:
        try:
            result = OntologyObservationResult.model_validate(raw_result)
        except (TypeError, ValueError):
            return OntologyObservationResult.create(
                semantic_outcome=CoverageSemanticOutcome.UNCERTAIN
            )
        if result.source_span is None:
            return result
        if (
            result.source_span.end > len(source_text)
            or source_text[result.source_span.start : result.source_span.end]
            != result.source_quote
            or result.signature is None
            or not self._signature_validator(result.signature)
        ):
            return OntologyObservationResult.create(
                semantic_outcome=CoverageSemanticOutcome.UNCERTAIN
            )
        return result


__all__ = [
    "CoverageObserverRunResult",
    "CoverageObserverRunner",
    "DurableOntologyObservationResult",
    "OntologyObservationRequest",
    "OntologyObservationResult",
    "OntologyObserverCapability",
    "OntologyObserverUnavailableError",
    "OntologyObservationResultRepository",
]
