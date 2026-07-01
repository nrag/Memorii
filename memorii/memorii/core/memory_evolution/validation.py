"""Deterministic validators for extracted memory evolution candidates."""

from __future__ import annotations

from memorii.core.memory_evolution.models import (
    EvidenceSpan,
    ExtractedClaim,
    SourceObservation,
    ValidationResult,
    ValidationVerdict,
)
from memorii.core.memory_evolution.predicates import PredicateRegistry


class MemoryEvolutionValidator:
    def __init__(self, *, predicate_registry: PredicateRegistry | None = None) -> None:
        self._predicates = predicate_registry or PredicateRegistry()

    def validate_claims(
        self,
        *,
        claims: list[ExtractedClaim],
        observations: list[SourceObservation],
    ) -> dict[str, list[ValidationResult]]:
        observation_by_id = {observation.source_id: observation for observation in observations}
        return {
            claim.claim_id: self.validate_claim(claim=claim, observation_by_id=observation_by_id)
            for claim in claims
        }

    def validate_claim(
        self,
        *,
        claim: ExtractedClaim,
        observation_by_id: dict[str, SourceObservation],
    ) -> list[ValidationResult]:
        results = [
            self._validate_predicate(claim),
            self._validate_object(claim),
            self._validate_evidence_spans(claim, observation_by_id),
        ]
        return results

    def accepted(self, results: list[ValidationResult]) -> bool:
        return all(result.verdict != ValidationVerdict.FAIL for result in results)

    def summary(self, validation_results: dict[str, list[ValidationResult]]) -> dict[str, int]:
        counts = {"pass": 0, "warn": 0, "fail": 0}
        for results in validation_results.values():
            for result in results:
                counts[result.verdict.value] += 1
        return counts

    def _validate_predicate(self, claim: ExtractedClaim) -> ValidationResult:
        if self._predicates.get(claim.claim_key.predicate_id) is None:
            return ValidationResult(
                validator_name="predicate_registry",
                verdict=ValidationVerdict.FAIL,
                score=0.0,
                rationale=f"unknown predicate: {claim.claim_key.predicate_id}",
            )
        return ValidationResult(
            validator_name="predicate_registry",
            verdict=ValidationVerdict.PASS,
            score=1.0,
            rationale="predicate policy exists",
        )

    def _validate_object(self, claim: ExtractedClaim) -> ValidationResult:
        if not claim.object_value.strip():
            return ValidationResult(
                validator_name="object_support",
                verdict=ValidationVerdict.FAIL,
                score=0.0,
                rationale="claim object is empty",
            )
        return ValidationResult(
            validator_name="object_support",
            verdict=ValidationVerdict.PASS,
            score=1.0,
            rationale="claim object is present",
        )

    def _validate_evidence_spans(
        self,
        claim: ExtractedClaim,
        observation_by_id: dict[str, SourceObservation],
    ) -> ValidationResult:
        if not claim.evidence_spans:
            return ValidationResult(
                validator_name="evidence_span_support",
                verdict=ValidationVerdict.FAIL,
                score=0.0,
                rationale="claim has no evidence spans",
            )

        failed_spans: list[EvidenceSpan] = []
        for span in claim.evidence_spans:
            observation = observation_by_id.get(span.source_id)
            if observation is None:
                failed_spans.append(span)
                continue
            if span.quote and span.quote.lower() in observation.text.lower():
                continue
            failed_spans.append(span)

        if failed_spans:
            return ValidationResult(
                validator_name="evidence_span_support",
                verdict=ValidationVerdict.FAIL,
                score=0.0,
                evidence_spans=failed_spans,
                rationale="one or more evidence quotes were not found in their source observations",
            )
        return ValidationResult(
            validator_name="evidence_span_support",
            verdict=ValidationVerdict.PASS,
            score=1.0,
            evidence_spans=list(claim.evidence_spans),
            rationale="all evidence quotes are present in source observations",
        )

