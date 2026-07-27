"""Language-owned contracts for source-grounded semantic extraction."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from memorii.core.memory_evolution.models import SourceModality


class EvidenceVerdict(StrEnum):
    """Deterministic verdict for one proposed semantic edge."""

    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    AMBIGUOUS = "ambiguous"
    UNSUPPORTED = "unsupported"


class ArgumentOrder(StrEnum):
    """How provider arguments relate to the source-supported canonical roles."""

    DIRECT = "direct"
    REVERSED = "reversed"


@dataclass(frozen=True)
class EvidenceDecision:
    verdict: EvidenceVerdict
    rationale: str
    argument_order: ArgumentOrder = ArgumentOrder.DIRECT
    matched_trigger: str | None = None

    @property
    def supported(self) -> bool:
        return self.verdict == EvidenceVerdict.SUPPORTED


@dataclass(frozen=True)
class SourceEvidence:
    """Exact evidence span together with the source context that scopes it."""

    source_text: str
    quote: str
    char_start: int
    char_end: int

    def __post_init__(self) -> None:
        if not self.quote:
            raise ValueError("source evidence quote must be non-empty")
        if self.char_start < 0 or self.char_end < self.char_start:
            raise ValueError("source evidence offsets are invalid")
        if self.source_text[self.char_start : self.char_end] != self.quote:
            raise ValueError("source evidence offsets must identify the verbatim quote")


@dataclass(frozen=True)
class RuleFactCandidate:
    predicate_id: str
    subject_name: str
    object_value: str
    quote: str


@dataclass(frozen=True)
class RuleActionCandidate:
    target_name: str
    status: str
    quote: str


class ExtractionLanguageCapabilities(Protocol):
    """Behavior supplied by one versioned language implementation."""

    @property
    def capability_id(self) -> str: ...

    @property
    def language_codes(self) -> frozenset[str]: ...

    def normalize_identity(self, value: str) -> str: ...

    def detect_modality(self, text: str) -> SourceModality | None: ...

    def rule_fact_candidates(self, text: str) -> tuple[RuleFactCandidate, ...]: ...

    def rule_action_candidates(self, text: str) -> tuple[RuleActionCandidate, ...]: ...

    def verify_entity_mention(
        self,
        *,
        evidence: SourceEvidence,
        entity_name: str,
    ) -> EvidenceDecision: ...

    def verify_entity_type(
        self,
        *,
        evidence: SourceEvidence,
        entity_name: str,
        entity_type: str,
        known_entity_names: tuple[str, ...],
    ) -> EvidenceDecision: ...

    def verify_relation(
        self,
        *,
        evidence: SourceEvidence,
        predicate_id: str,
        subject_name: str,
        object_name: str,
        known_entity_names: tuple[str, ...],
    ) -> EvidenceDecision: ...

    def verify_identity_relation(
        self,
        *,
        evidence: SourceEvidence,
        relation_type: str,
        source_name: str,
        target_name: str,
        known_entity_names: tuple[str, ...],
    ) -> EvidenceDecision: ...

    def inferred_entity_types(self, predicate_id: str) -> tuple[str | None, str | None]: ...

    def verify_literal_claim(
        self,
        *,
        evidence: SourceEvidence,
        predicate_id: str,
        subject_name: str,
        object_value: str,
        known_entity_names: tuple[str, ...],
    ) -> EvidenceDecision: ...

    def verify_action(
        self,
        *,
        evidence: SourceEvidence,
        action_type: str,
        status: str,
        target_names: tuple[str, ...],
        actor_name: str | None,
        dependency_names: tuple[str, ...],
        blocking_names: tuple[str, ...],
        known_entity_names: tuple[str, ...],
    ) -> EvidenceDecision: ...
