"""Runtime memory evolution primitives."""

from memorii.core.memory_evolution.extraction import HybridMemoryExtractor, LLMMemoryExtractor, MemoryExtractor, RuleMemoryExtractor
from memorii.core.memory_evolution.factory import build_memory_extractor_from_env
from memorii.core.memory_evolution.models import (
    ClaimKey,
    ClaimLifecycleState,
    ClaimLifecycleTransition,
    ClaimState,
    EntityMention,
    EvidenceSpan,
    ExtractedAction,
    ExtractedClaim,
    ExtractionRun,
    MemoryEvolutionResult,
    RetrievalView,
    SourceObservation,
    ValidationResult,
)
from memorii.core.memory_evolution.predicates import PredicatePolicy, PredicateRegistry
from memorii.core.memory_evolution.service import MemoryEvolutionService, source_observation_from_record
from memorii.core.memory_evolution.validation import MemoryEvolutionValidator

__all__ = [
    "ClaimKey",
    "ClaimLifecycleState",
    "ClaimLifecycleTransition",
    "ClaimState",
    "EntityMention",
    "EvidenceSpan",
    "ExtractedAction",
    "ExtractedClaim",
    "ExtractionRun",
    "MemoryEvolutionResult",
    "MemoryEvolutionService",
    "MemoryEvolutionValidator",
    "MemoryExtractor",
    "HybridMemoryExtractor",
    "LLMMemoryExtractor",
    "PredicatePolicy",
    "PredicateRegistry",
    "RetrievalView",
    "RuleMemoryExtractor",
    "SourceObservation",
    "ValidationResult",
    "source_observation_from_record",
    "build_memory_extractor_from_env",
]
