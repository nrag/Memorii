"""Source modality and extraction trigger policy."""

from __future__ import annotations

import re

from memorii.core.memory_evolution.models import ExtractionTriggerMode, SourceModality, SourceObservation
from memorii.domain.enums import SourceType


class SourceModalityClassifier:
    """Classify what a source observation represents before extraction."""

    def classify(self, observation: SourceObservation) -> SourceModality:
        text = observation.text.strip()
        lowered = text.lower()
        if not text:
            return SourceModality.NOISE
        if observation.source_type == SourceType.TOOL:
            return SourceModality.TOOL_RESULT
        if observation.source_type == SourceType.AGENT:
            return SourceModality.ASSISTANT_CLAIM
        if _looks_like_question(text):
            return SourceModality.QUESTION
        if _looks_like_hypothetical(lowered):
            return SourceModality.HYPOTHETICAL
        if _looks_like_paste(lowered):
            return SourceModality.QUOTED_OR_PASTED
        if _looks_like_correction(lowered):
            return SourceModality.CORRECTION
        if _looks_like_third_party(lowered):
            return SourceModality.THIRD_PARTY_CLAIM
        if _looks_like_instruction(lowered):
            return SourceModality.INSTRUCTION
        if observation.source_type in {SourceType.USER, SourceType.ENVIRONMENT}:
            return SourceModality.ASSERTION
        return SourceModality.QUOTED_OR_PASTED


class ExtractionTriggerPolicy:
    """Decide whether a classified source should evolve memory immediately."""

    def trigger_for(self, observation: SourceObservation) -> ExtractionTriggerMode:
        if observation.modality in {
            SourceModality.CORRECTION,
            SourceModality.TOOL_RESULT,
        }:
            return ExtractionTriggerMode.IMMEDIATE
        if observation.source_type == SourceType.ENVIRONMENT:
            return ExtractionTriggerMode.IMMEDIATE
        if observation.source_type == SourceType.USER and observation.modality == SourceModality.ASSERTION:
            return ExtractionTriggerMode.IMMEDIATE
        if observation.modality in {
            SourceModality.QUESTION,
            SourceModality.HYPOTHETICAL,
            SourceModality.INSTRUCTION,
            SourceModality.NOISE,
        }:
            return ExtractionTriggerMode.SKIP
        if observation.modality in {
            SourceModality.QUOTED_OR_PASTED,
            SourceModality.THIRD_PARTY_CLAIM,
            SourceModality.ASSISTANT_CLAIM,
        }:
            return ExtractionTriggerMode.DEFERRED
        return ExtractionTriggerMode.DEFERRED


def classify_and_mark_observation(
    observation: SourceObservation,
    *,
    classifier: SourceModalityClassifier | None = None,
    trigger_policy: ExtractionTriggerPolicy | None = None,
) -> SourceObservation:
    resolved_classifier = classifier or SourceModalityClassifier()
    resolved_policy = trigger_policy or ExtractionTriggerPolicy()
    modality = resolved_classifier.classify(observation)
    marked = observation.model_copy(update={"modality": modality})
    return marked.model_copy(update={"trigger_mode": resolved_policy.trigger_for(marked)})


def _looks_like_question(text: str) -> bool:
    stripped = text.strip()
    if stripped.endswith("?"):
        return True
    return bool(re.match(r"^(who|what|when|where|why|how|is|are|does|do|did|can|could|should)\b", stripped, re.IGNORECASE))


def _looks_like_hypothetical(lowered: str) -> bool:
    markers = ["suppose ", "hypothetically", "imagine ", "if ", "what if", "would be", "could be"]
    return any(marker in lowered for marker in markers)


def _looks_like_paste(lowered: str) -> bool:
    markers = ["pasted", "paste:", "here is a doc", "here's a doc", "document:", "```", "\n>"]
    return any(marker in lowered for marker in markers)


def _looks_like_correction(lowered: str) -> bool:
    markers = ["correction:", "correcting", "actually ", "not ", "instead ", "should be"]
    return any(marker in lowered for marker in markers)


def _looks_like_third_party(lowered: str) -> bool:
    markers = ["says ", "said ", "according to", "the doc says", "the transcript says", "manager says"]
    return any(marker in lowered for marker in markers)


def _looks_like_instruction(lowered: str) -> bool:
    return lowered.startswith(("please ", "can you ", "could you ", "remember to ", "do not ", "don't "))

