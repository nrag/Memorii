"""Confidence aggregation for evolved memory claims."""

from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from memorii.core.memory_evolution.models import (
    ClaimState,
    ConfidenceComponents,
    ConfidenceUpdate,
    ExtractedClaim,
    SourceModality,
)


class ConfidenceAggregator:
    def initial_for_claim(self, claim: ExtractedClaim, *, modality: SourceModality) -> ConfidenceComponents:
        modality_factor = {
            SourceModality.CORRECTION: 1.0,
            SourceModality.TOOL_RESULT: 0.95,
            SourceModality.ASSERTION: 0.9,
            SourceModality.THIRD_PARTY_CLAIM: 0.55,
            SourceModality.QUOTED_OR_PASTED: 0.45,
            SourceModality.ASSISTANT_CLAIM: 0.4,
            SourceModality.HYPOTHETICAL: 0.1,
            SourceModality.QUESTION: 0.05,
            SourceModality.INSTRUCTION: 0.1,
            SourceModality.NOISE: 0.0,
        }[modality]
        calibrated = min(
            1.0,
            max(
                0.0,
                claim.confidence.extraction * 0.35
                + claim.confidence.evidence * 0.25
                + claim.confidence.source_trust * 0.25
                + modality_factor * 0.15
                + claim.confidence.agreement * 0.1
                - claim.confidence.contradiction * 0.2,
            ),
        )
        return claim.confidence.model_copy(update={"calibrated": round(calibrated, 4)})

    def reinforce(
        self,
        *,
        existing: ClaimState,
        claim: ExtractedClaim,
        modality: SourceModality,
    ) -> tuple[ConfidenceComponents, ConfidenceUpdate]:
        prior = existing.confidence.calibrated
        modality_bonus = 0.08 if modality in {SourceModality.CORRECTION, SourceModality.TOOL_RESULT, SourceModality.ASSERTION} else 0.02
        evidence_bonus = 0.04 if claim.evidence_spans else 0.0
        new_value = min(1.0, prior + modality_bonus + evidence_bonus)
        update = ConfidenceUpdate(
            update_id=_stable_id("confidence-update", f"{existing.claim_id}:{claim.claim_id}:{new_value}"),
            claim_id=existing.claim_id,
            prior_confidence=prior,
            new_confidence=round(new_value, 4),
            evidence_delta=evidence_bonus,
            agreement_delta=modality_bonus,
            contradiction_delta=0.0,
            source_trust_delta=max(0.0, claim.confidence.source_trust - existing.confidence.source_trust),
            modality=modality,
            rationale="claim reinforced by additional compatible evidence",
        )
        confidence = existing.confidence.model_copy(
            update={
                "agreement": min(1.0, existing.confidence.agreement + modality_bonus),
                "calibrated": update.new_confidence,
            }
        )
        return confidence, update

    def penalize_for_contradiction(self, confidence: ConfidenceComponents, *, severity: float = 0.15) -> ConfidenceComponents:
        return confidence.model_copy(
            update={
                "contradiction": min(1.0, confidence.contradiction + severity),
                "calibrated": max(0.0, round(confidence.calibrated - severity, 4)),
            }
        )


def _stable_id(prefix: str, value: str) -> str:
    return f"{prefix}:{uuid5(NAMESPACE_URL, value)}"

