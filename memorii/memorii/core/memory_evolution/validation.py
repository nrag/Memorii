"""Deterministic validators for extracted memory evolution candidates."""

from __future__ import annotations

import re

from memorii.core.memory_evolution.models import (
    ClaimAssertionMode,
    ClaimPolarity,
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
            self._validate_semantic_status(claim, observation_by_id),
            self._validate_modality(claim, observation_by_id),
            self._validate_object(claim),
            self._validate_subject_support(claim, observation_by_id),
            self._validate_temporal_support(claim),
            self._validate_evidence_spans(claim, observation_by_id),
        ]
        return results

    def _validate_semantic_status(
        self,
        claim: ExtractedClaim,
        observation_by_id: dict[str, SourceObservation],
    ) -> ValidationResult:
        context = claim.semantic_context
        if context.assertion_mode == ClaimAssertionMode.LEGACY_UNCLASSIFIED:
            return ValidationResult(
                validator_name="semantic_status",
                verdict=ValidationVerdict.FAIL,
                score=0.0,
                rationale="claim semantic status is unresolved and cannot promote",
            )
        if context.attribution_source_id not in {span.source_id for span in claim.evidence_spans}:
            return ValidationResult(
                validator_name="semantic_status",
                verdict=ValidationVerdict.FAIL,
                score=0.0,
                rationale="claim attribution is not source-grounded by its evidence",
            )
        source = observation_by_id.get(context.attribution_source_id or "")
        if source is None:
            return ValidationResult(
                validator_name="semantic_status",
                verdict=ValidationVerdict.FAIL,
                score=0.0,
                rationale="claim attribution source is not an extraction input",
            )
        if context.attribution_speaker_id is not None and source.speaker_id != context.attribution_speaker_id:
            return ValidationResult(
                validator_name="semantic_status",
                verdict=ValidationVerdict.FAIL,
                score=0.0,
                rationale="claim attribution speaker does not match its source envelope",
            )
        if context.assertion_mode == ClaimAssertionMode.WORLD_ASSERTION:
            source_form_error = _world_assertion_evidence_form_error(
                claim=claim,
                source=source,
            )
            if source_form_error is not None:
                return ValidationResult(
                    validator_name="semantic_status",
                    verdict=ValidationVerdict.FAIL,
                    score=0.0,
                    rationale=f"world assertion is not source-certified: {source_form_error}",
                )
        if context.assertion_mode == ClaimAssertionMode.ATTRIBUTED_BELIEF:
            return ValidationResult(
                validator_name="semantic_status",
                verdict=ValidationVerdict.FAIL,
                score=0.0,
                rationale="attributed belief is evidence-only until a dedicated belief projection exists",
            )
        if context.polarity != ClaimPolarity.POSITIVE:
            return ValidationResult(
                validator_name="semantic_status",
                verdict=ValidationVerdict.FAIL,
                score=0.0,
                rationale="negative world assertion is evidence-only until negative claim lifecycle exists",
            )
        return ValidationResult(
            validator_name="semantic_status",
            verdict=ValidationVerdict.PASS,
            score=1.0,
            rationale="source-grounded world assertion is promotion-eligible",
        )
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


def _world_assertion_evidence_form_error(
    *,
    claim: ExtractedClaim,
    source: SourceObservation,
) -> str | None:
    attribution_spans = [
        span for span in claim.evidence_spans if span.source_id == source.source_id
    ]
    if len(attribution_spans) != 1:
        return "ambiguous attributed evidence spans"
    span = attribution_spans[0]
    quote = span.quote
    if not quote:
        return "empty attributed evidence span"
    if span.char_start is not None:
        quote_start = span.char_start
        quote_end = span.char_end
        if quote_end is None or source.text[quote_start:quote_end] != quote:
            return "attributed evidence offsets do not match the source quote"
    else:
        quote_start = source.text.find(quote)
        if quote_start < 0 or source.text.find(quote, quote_start + 1) >= 0:
            return "ambiguous attributed evidence quote"
        quote_end = quote_start + len(quote)
    constructions = _source_constructions(source.text)
    governing_constructions = [
        construction
        for construction in constructions
        if construction[0] <= quote_start and quote_end <= construction[1]
    ]
    if len(governing_constructions) != 1:
        return "attributed evidence does not identify one complete source construction"
    return _world_assertion_source_form_error(governing_constructions[0][2])


def _source_constructions(source_text: str) -> tuple[tuple[int, int, str], ...]:
    """Derive conservative sentence/clause boundaries from source text alone."""

    constructions: list[tuple[int, int, str]] = []
    start = 0
    quoted = False
    for index, character in enumerate(source_text):
        if character in {'"', "\u201c", "\u201d"}:
            quoted = not quoted
            continue
        if character not in ".?!;" or quoted:
            continue
        _append_source_construction(constructions, source_text, start, index + 1)
        start = index + 1
    _append_source_construction(constructions, source_text, start, len(source_text))
    return tuple(constructions)


def _append_source_construction(
    constructions: list[tuple[int, int, str]],
    source_text: str,
    start: int,
    end: int,
) -> None:
    while start < end and source_text[start].isspace():
        start += 1
    while end > start and source_text[end - 1].isspace():
        end -= 1
    if start < end:
        constructions.append((start, end, source_text[start:end]))


def _world_assertion_source_form_error(text: str) -> str | None:
    """Fail closed unless the source itself is a direct positive assertion.

    A model's world label is not authority to reinterpret reported, negated, modal,
    quoted, or interrogative language as committed world truth.
    """

    normalized = text.casefold()
    if "?" in normalized:
        return "interrogative source"
    if '"' in normalized or "\u201c" in normalized or "\u201d" in normalized:
        return "quoted source"
    if re.search(r"\b(?:believes?|thinks?|claims?|reports?|said|says|heard|according to)\b", normalized):
        return "reported belief or speech"
    if re.search(r"\b(?:may|might|could|possibly|perhaps|likely|unclear|unknown)\b", normalized):
        return "modal or ambiguous source"
    if re.search(r"\b(?:not|never|neither|no)\b|n['\u2019]t", normalized):
        return "negated source"
    return None


def _entity_token(entity_id: str) -> str:
    if entity_id.startswith("ent:"):
        return entity_id.removeprefix("ent:").replace("-", " ").lower()
    return entity_id.replace("-", " ").lower()
