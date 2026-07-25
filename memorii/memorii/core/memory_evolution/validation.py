"""Deterministic validators for extracted memory evolution candidates."""

from __future__ import annotations

from memorii.core.memory_evolution.models import (
    EntityMention,
    EvidenceSpan,
    ExtractedAction,
    ExtractedClaim,
    ExtractionTriggerMode,
    SourceModality,
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

    def extraction_coverage_errors(
        self,
        *,
        observations: list[SourceObservation],
        entities: list[EntityMention],
        claims: list[ExtractedClaim],
        actions: list[ExtractedAction],
    ) -> list[str]:
        """Require every eligible source to have a grounded extraction outcome."""

        expected_source_ids = {observation.source_id for observation in observations}
        covered_source_ids = {
            span.source_id
            for candidate in [*entities, *claims, *actions]
            for span in candidate.evidence_spans
        }
        missing = sorted(expected_source_ids - covered_source_ids)
        unknown = sorted(covered_source_ids - expected_source_ids)
        return [
            *(f"source_unaccounted:{source_id}" for source_id in missing),
            *(f"source_outside_extraction_input:{source_id}" for source_id in unknown),
        ]

    def validate_claim(
        self,
        *,
        claim: ExtractedClaim,
        observation_by_id: dict[str, SourceObservation],
    ) -> list[ValidationResult]:
        results = [
            self._validate_predicate(claim),
            self._validate_modality(claim, observation_by_id),
            self._validate_object(claim),
            self._validate_subject_support(claim, observation_by_id),
            self._validate_predicate_support(claim, observation_by_id),
            self._validate_temporal_support(claim),
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

    def _validate_modality(
        self,
        claim: ExtractedClaim,
        observation_by_id: dict[str, SourceObservation],
    ) -> ValidationResult:
        observations = _claim_observations(claim, observation_by_id)
        if not observations:
            return ValidationResult(
                validator_name="modality_eligibility",
                verdict=ValidationVerdict.FAIL,
                score=0.0,
                rationale="claim has no resolvable source observation for modality validation",
            )
        blocked = [
            obs
            for obs in observations
            if obs.modality in {
                SourceModality.QUESTION,
                SourceModality.HYPOTHETICAL,
                SourceModality.INSTRUCTION,
                SourceModality.NOISE,
                SourceModality.QUOTED_OR_PASTED,
            }
            or obs.trigger_mode in {ExtractionTriggerMode.DEFERRED, ExtractionTriggerMode.BATCH_ONLY, ExtractionTriggerMode.SKIP}
        ]
        if blocked:
            return ValidationResult(
                validator_name="modality_eligibility",
                verdict=ValidationVerdict.FAIL,
                score=0.0,
                rationale=f"source modality {blocked[0].modality.value} is not eligible for active claim creation",
            )
        return ValidationResult(
            validator_name="modality_eligibility",
            verdict=ValidationVerdict.PASS,
            score=1.0,
            rationale="source modality is eligible for active claim creation",
        )

    def _validate_subject_support(
        self,
        claim: ExtractedClaim,
        observation_by_id: dict[str, SourceObservation],
    ) -> ValidationResult:
        subject_token = _entity_token(claim.claim_key.subject_entity_id)
        if subject_token == "user":
            return ValidationResult(
                validator_name="subject_support",
                verdict=ValidationVerdict.PASS,
                score=1.0,
                rationale="implicit user subject is allowed",
            )
        text = _source_text_for_claim(claim, observation_by_id)
        if subject_token and subject_token in text:
            return ValidationResult(
                validator_name="subject_support",
                verdict=ValidationVerdict.PASS,
                score=1.0,
                rationale="claim subject appears in source text",
            )
        return ValidationResult(
            validator_name="subject_support",
            verdict=ValidationVerdict.WARN,
            score=0.5,
            rationale="claim subject was not directly found in source text",
        )

    def _validate_predicate_support(
        self,
        claim: ExtractedClaim,
        observation_by_id: dict[str, SourceObservation],
    ) -> ValidationResult:
        predicate = claim.claim_key.predicate_id
        text = _source_text_for_claim(claim, observation_by_id)
        support_terms = {
            "owner": ["owner", "owns", "owned", "ownership", "belongs to", "belonged to"],
            "approver": ["approver", "approval"],
            "api_owner": ["api owner", "api_owner"],
            "status": ["status", "state", "deploy", "deployment", "failed", "succeeded", "blocked"],
            "preference": ["prefer", "preference", "style"],
            "dependency": ["depends", "dependency", "requires", "supports"],
            "action_state": [
                "started",
                "in progress",
                "in_progress",
                "progressing",
                "blocked",
                "resumed",
                "abandoned",
                "completed",
                "failed",
                "succeeded",
            ],
            "belief": ["hypothesis", "belief", "root cause", "candidate"],
            "correction": ["correction", "actually", "not", "instead", "should be"],
            "entity_type": ["is", "project", "service", "type", "workstream"],
            "semantic_fact": [],
        }.get(predicate, [])
        if not support_terms or any(term in text for term in support_terms):
            return ValidationResult(
                validator_name="predicate_support",
                verdict=ValidationVerdict.PASS,
                score=1.0,
                rationale="predicate is supported by source text",
            )
        return ValidationResult(
            validator_name="predicate_support",
            verdict=ValidationVerdict.FAIL,
            score=0.0,
            rationale=f"predicate {predicate} is not supported by source text",
        )

    def _validate_temporal_support(self, claim: ExtractedClaim) -> ValidationResult:
        if claim.valid_from is not None and claim.valid_to is not None and claim.valid_from > claim.valid_to:
            return ValidationResult(
                validator_name="temporal_support",
                verdict=ValidationVerdict.FAIL,
                score=0.0,
                rationale="valid_from is after valid_to",
            )
        return ValidationResult(
            validator_name="temporal_support",
            verdict=ValidationVerdict.PASS,
            score=1.0,
            rationale="temporal validity is well formed",
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


def _claim_observations(
    claim: ExtractedClaim,
    observation_by_id: dict[str, SourceObservation],
) -> list[SourceObservation]:
    return [
        observation
        for span in claim.evidence_spans
        if (observation := observation_by_id.get(span.source_id)) is not None
    ]


def _source_text_for_claim(
    claim: ExtractedClaim,
    observation_by_id: dict[str, SourceObservation],
) -> str:
    return " ".join(obs.text.lower() for obs in _claim_observations(claim, observation_by_id))


def _entity_token(entity_id: str) -> str:
    if entity_id.startswith("ent:"):
        return entity_id.removeprefix("ent:").replace("-", " ").lower()
    return entity_id.replace("-", " ").lower()
