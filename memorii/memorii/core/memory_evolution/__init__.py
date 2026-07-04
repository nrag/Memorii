"""Runtime memory evolution primitives."""

from memorii.core.memory_evolution.extraction import HybridMemoryExtractor, LLMMemoryExtractor, MemoryExtractor, RuleMemoryExtractor
from memorii.core.memory_evolution.entity_resolution import EntityResolutionService
from memorii.core.memory_evolution.factory import build_memory_extractor_from_env
from memorii.core.memory_evolution.graph import MemoryGraphProjector, MemoryGraphStore, MemoryGraphValidator
from memorii.core.memory_evolution.models import (
    ClaimKey,
    ClaimLifecycleState,
    ClaimLifecycleTransition,
    ClaimState,
    ConfidenceUpdate,
    ContradictionSet,
    EntityMention,
    EntityLinkState,
    ExtractionTriggerMode,
    EvidenceSpan,
    ExtractedAction,
    ExtractedClaim,
    ExtractionRun,
    MemoryGraphEdge,
    MemoryGraphEdgeType,
    MemoryGraphNode,
    MemoryGraphNodeType,
    MemoryGraphSnapshot,
    MemoryEvolutionResult,
    RetrievalView,
    SourceModality,
    SourceObservation,
    ValidationResult,
)
from memorii.core.memory_evolution.modality import ExtractionTriggerPolicy, SourceModalityClassifier
from memorii.core.memory_evolution.predicates import PredicatePolicy, PredicateRegistry
from memorii.core.memory_evolution.reference import BuiltInReferenceKnowledgeProvider, ReferenceClaim, ReferenceEntity
from memorii.core.memory_evolution.service import MemoryEvolutionService, source_observation_from_record
from memorii.core.memory_evolution.validation import MemoryEvolutionValidator

__all__ = [
    "ClaimKey",
    "ClaimLifecycleState",
    "ClaimLifecycleTransition",
    "ClaimState",
    "ConfidenceUpdate",
    "ContradictionSet",
    "EntityMention",
    "EntityLinkState",
    "EntityResolutionService",
    "ExtractionTriggerMode",
    "EvidenceSpan",
    "ExtractedAction",
    "ExtractedClaim",
    "ExtractionRun",
    "MemoryGraphEdge",
    "MemoryGraphEdgeType",
    "MemoryGraphNode",
    "MemoryGraphNodeType",
    "MemoryGraphProjector",
    "MemoryGraphSnapshot",
    "MemoryGraphStore",
    "MemoryGraphValidator",
    "MemoryEvolutionResult",
    "MemoryEvolutionService",
    "MemoryEvolutionValidator",
    "MemoryExtractor",
    "HybridMemoryExtractor",
    "LLMMemoryExtractor",
    "PredicatePolicy",
    "PredicateRegistry",
    "ReferenceClaim",
    "ReferenceEntity",
    "RetrievalView",
    "RuleMemoryExtractor",
    "SourceModality",
    "SourceObservation",
    "SourceModalityClassifier",
    "ExtractionTriggerPolicy",
    "ValidationResult",
    "BuiltInReferenceKnowledgeProvider",
    "source_observation_from_record",
    "build_memory_extractor_from_env",
]
