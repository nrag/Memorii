"""Source modality and extraction trigger policy."""

from __future__ import annotations

from memorii.core.memory_evolution.language_support import (
    DEFAULT_EXTRACTION_LANGUAGE_REGISTRY,
    ExtractionLanguageRegistry,
)
from memorii.core.memory_evolution.models import ExtractionTriggerMode, SourceModality, SourceObservation
from memorii.domain.enums import SourceType


class SourceModalityClassifier:
    """Classify what a source observation represents before extraction."""

    def __init__(
        self,
        *,
        language_registry: ExtractionLanguageRegistry = DEFAULT_EXTRACTION_LANGUAGE_REGISTRY,
    ) -> None:
        self._language_registry = language_registry

    def classify(self, observation: SourceObservation) -> SourceModality:
        text = observation.text.strip()
        if not text:
            return SourceModality.NOISE
        if observation.source_type == SourceType.TOOL:
            return SourceModality.TOOL_RESULT
        if observation.source_type == SourceType.AGENT:
            return SourceModality.ASSISTANT_CLAIM
        capability = self._language_registry.resolve(observation.language)
        detected = capability.detect_modality(text) if capability is not None else None
        if detected is not None:
            return detected
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
    declared_modality: SourceModality | None = None,
) -> SourceObservation:
    resolved_classifier = classifier or SourceModalityClassifier()
    resolved_policy = trigger_policy or ExtractionTriggerPolicy()
    modality = declared_modality or resolved_classifier.classify(observation)
    marked = observation.model_copy(update={"modality": modality})
    return marked.model_copy(update={"trigger_mode": resolved_policy.trigger_for(marked)})
