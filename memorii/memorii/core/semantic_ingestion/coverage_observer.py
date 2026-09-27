"""Provider-neutral execution boundary for ontology coverage observation."""

from __future__ import annotations

import json
from collections.abc import Callable
from hashlib import sha256
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.semantic_ingestion.coverage_observation import (
    CoverageObservation,
    CoverageObservationRepository,
    CoverageSemanticOutcome,
    CoverageSourceSpan,
    ObserverBindingIdentity,
    classify_coverage_observation,
    fail_coverage_observation,
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
        capability: OntologyObserverCapability,
        signature_validator: Callable[[CoverageGapSignature], bool],
    ) -> None:
        self._observations = observation_repository
        self._gaps = gap_repository
        self._recurrence = recurrence_repository
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
        running = start_coverage_observation(observation)
        self._observations.replace(running, previous=observation)
        request = OntologyObservationRequest.create(
            observation=running, source_text=source_text
        )
        try:
            raw_result = self._capability.observe(request)
        except OntologyObserverUnavailableError as exc:
            unavailable = fail_coverage_observation(
                running,
                failure_signature=_digest(
                    b"memorii.learned-ontology.observer-unavailable.v1",
                    type(exc).__name__,
                ),
            )
            self._observations.replace(unavailable, previous=running)
            return CoverageObserverRunResult(observation=unavailable)
        try:
            result = OntologyObservationResult.model_validate(raw_result)
        except (TypeError, ValueError):
            result = OntologyObservationResult.create(
                semantic_outcome=CoverageSemanticOutcome.UNCERTAIN
            )
        if result.source_span is not None:
            if (
                result.source_span.end > len(source_text)
                or source_text[result.source_span.start : result.source_span.end]
                != result.source_quote
            ):
                result = OntologyObservationResult.create(
                    semantic_outcome=CoverageSemanticOutcome.UNCERTAIN
                )
            if result.signature is None or not self._signature_validator(
                result.signature
            ):
                result = OntologyObservationResult.create(
                    semantic_outcome=CoverageSemanticOutcome.UNCERTAIN
                )
        classified = classify_coverage_observation(
            running,
            semantic_outcome=result.semantic_outcome,
            source_span=result.source_span,
        )
        self._observations.replace(classified, previous=running)
        if result.signature is None:
            return CoverageObserverRunResult(observation=classified)
        gap = VerifiedCoverageGap.from_observation(
            classified, signature=result.signature
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
            observation=classified,
            recurrence_group=group,
        )


__all__ = [
    "CoverageObserverRunResult",
    "CoverageObserverRunner",
    "OntologyObservationRequest",
    "OntologyObservationResult",
    "OntologyObserverCapability",
    "OntologyObserverUnavailableError",
]
