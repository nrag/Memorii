"""Reusable mechanics for language-owned semantic evidence policies."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product

from memorii.core.memory_evolution.language_support.contracts import (
    ArgumentOrder,
    EvidenceDecision,
    EvidenceVerdict,
    RuleActionCandidate,
    RuleFactCandidate,
    SourceEvidence,
)
from memorii.core.memory_evolution.language_support.unicode_text import (
    TokenSpan,
    has_intervening_entity,
    interval_contains_any,
    normalize_text,
    phrase_spans,
    word_tokens,
)
from memorii.core.memory_evolution.models import SourceModality


@dataclass(frozen=True)
class SemanticFrame:
    """Ordered semantic roles around an optional language-specific trigger."""

    roles: tuple[str, ...]
    triggers: tuple[str, ...] = ()
    gap_allowlists: tuple[frozenset[str] | None, ...] = ()

    def __post_init__(self) -> None:
        if len(self.roles) < 2 or any(role not in {"subject", "object", "trigger"} for role in self.roles):
            raise ValueError("semantic frame roles are invalid")
        if ("trigger" in self.roles) != bool(self.triggers):
            raise ValueError("semantic frame trigger role and trigger phrases must agree")
        if not self.gap_allowlists:
            object.__setattr__(self, "gap_allowlists", tuple(None for _ in range(len(self.roles) - 1)))
        elif len(self.gap_allowlists) != len(self.roles) - 1:
            raise ValueError("semantic frame requires one allowlist per role gap")


@dataclass(frozen=True)
class ModalityLexicon:
    """Language-owned lexical signals in deterministic precedence order."""

    question_prefixes: tuple[str, ...] = ()
    hypothetical_markers: tuple[str, ...] = ()
    quoted_or_pasted_markers: tuple[str, ...] = ()
    correction_markers: tuple[str, ...] = ()
    third_party_markers: tuple[str, ...] = ()
    instruction_prefixes: tuple[str, ...] = ()


@dataclass(frozen=True, order=True)
class _FrameMatch:
    start: int
    end: int
    trigger: str | None


class FrameLanguageCapabilities:
    """High-precision frame matcher configured only by a concrete language pack."""

    capability_id: str
    language_codes: frozenset[str]
    relation_frames: dict[str, tuple[SemanticFrame, ...]]
    identity_frames: dict[str, tuple[SemanticFrame, ...]]
    entity_type_frames: dict[str, tuple[SemanticFrame, ...]]
    literal_frames: dict[str, tuple[SemanticFrame, ...]] = {}
    literal_value_aliases: dict[str, dict[str, tuple[str, ...]]] = {}
    negations: frozenset[tuple[str, ...]]
    denial_markers: tuple[str, ...] = ()
    clause_boundaries: tuple[str, ...] = ()
    dependency_markers: tuple[str, ...] = ()
    blocking_markers: tuple[str, ...] = ()
    entity_name_suffixes: tuple[str, ...] = ()
    relation_type_hints: dict[str, tuple[str | None, str | None]]
    modality_lexicon: ModalityLexicon

    def normalize_identity(self, value: str) -> str:
        return normalize_text(value)

    def rule_fact_candidates(self, text: str) -> tuple[RuleFactCandidate, ...]:
        del text
        return ()

    def rule_action_candidates(self, text: str) -> tuple[RuleActionCandidate, ...]:
        del text
        return ()

    def detect_modality(self, text: str) -> SourceModality | None:
        normalized = normalize_text(text)
        if not normalized:
            return SourceModality.NOISE
        tokens = word_tokens(text, self._language_code)
        if _starts_with_any(tokens, self.modality_lexicon.instruction_prefixes, self._language_code):
            return SourceModality.INSTRUCTION
        if text.strip().endswith("?") or _starts_with_any(
            tokens,
            self.modality_lexicon.question_prefixes,
            self._language_code,
        ):
            return SourceModality.QUESTION
        if _contains_any(tokens, self.modality_lexicon.hypothetical_markers, self._language_code):
            return SourceModality.HYPOTHETICAL
        if (
            "```" in text
            or "\n>" in text
            or _contains_any(tokens, self.modality_lexicon.quoted_or_pasted_markers, self._language_code)
        ):
            return SourceModality.QUOTED_OR_PASTED
        if _contains_any(tokens, self.modality_lexicon.third_party_markers, self._language_code):
            return SourceModality.THIRD_PARTY_CLAIM
        if _contains_any(tokens, self.modality_lexicon.correction_markers, self._language_code):
            return SourceModality.CORRECTION
        return None

    def verify_entity_mention(
        self,
        *,
        evidence: SourceEvidence,
        entity_name: str,
    ) -> EvidenceDecision:
        quote_tokens = word_tokens(evidence.quote, self._language_code)
        surfaces = (entity_name, *(f"{entity_name}{suffix}" for suffix in self.entity_name_suffixes))
        if any(phrase_spans(quote_tokens, surface, self._language_code) for surface in surfaces):
            return EvidenceDecision(EvidenceVerdict.SUPPORTED, "entity name occurs in its verbatim evidence quote")
        return EvidenceDecision(EvidenceVerdict.UNSUPPORTED, "entity name is absent from its evidence quote")

    def verify_entity_type(
        self,
        *,
        evidence: SourceEvidence,
        entity_name: str,
        entity_type: str,
        known_entity_names: tuple[str, ...],
    ) -> EvidenceDecision:
        frames = self.entity_type_frames.get(entity_type, ())
        if not frames:
            return EvidenceDecision(EvidenceVerdict.UNSUPPORTED, f"unsupported entity type {entity_type!r}")
        return self._verify_frames(
            evidence=evidence,
            frames=frames,
            subject_name=entity_name,
            object_name=entity_type,
            known_entity_names=known_entity_names,
            allow_reversal=False,
        )

    def verify_relation(
        self,
        *,
        evidence: SourceEvidence,
        predicate_id: str,
        subject_name: str,
        object_name: str,
        known_entity_names: tuple[str, ...],
    ) -> EvidenceDecision:
        frames = self.relation_frames.get(predicate_id, ())
        if not frames:
            return EvidenceDecision(EvidenceVerdict.UNSUPPORTED, f"unsupported predicate {predicate_id!r}")
        return self._verify_frames(
            evidence=evidence,
            frames=frames,
            subject_name=subject_name,
            object_name=object_name,
            known_entity_names=known_entity_names,
            allow_reversal=True,
        )

    def verify_identity_relation(
        self,
        *,
        evidence: SourceEvidence,
        relation_type: str,
        source_name: str,
        target_name: str,
        known_entity_names: tuple[str, ...],
    ) -> EvidenceDecision:
        frames = self.identity_frames.get(relation_type, ())
        if not frames:
            return EvidenceDecision(EvidenceVerdict.UNSUPPORTED, f"unsupported identity relation {relation_type!r}")
        return self._verify_frames(
            evidence=evidence,
            frames=frames,
            subject_name=source_name,
            object_name=target_name,
            known_entity_names=known_entity_names,
            allow_reversal=False,
        )

    def verify_literal_claim(
        self,
        *,
        evidence: SourceEvidence,
        predicate_id: str,
        subject_name: str,
        object_value: str,
        known_entity_names: tuple[str, ...],
    ) -> EvidenceDecision:
        if predicate_id == "semantic_fact":
            return self._verify_evidence_only_fact(
                evidence=evidence,
                subject_name=subject_name,
                object_value=object_value,
            )
        frames = self.literal_frames.get(predicate_id, ())
        if not frames:
            return EvidenceDecision(EvidenceVerdict.UNSUPPORTED, f"unsupported literal predicate {predicate_id!r}")
        decisions = [
            self._verify_frames(
                evidence=evidence,
                frames=frames,
                subject_name=subject_name,
                object_name=surface,
                known_entity_names=known_entity_names,
                allow_reversal=False,
            )
            for surface in self._literal_surfaces(predicate_id, object_value)
        ]
        supported = [decision for decision in decisions if decision.supported]
        if supported:
            return supported[0]
        if any(decision.verdict == EvidenceVerdict.CONTRADICTED for decision in decisions):
            return EvidenceDecision(EvidenceVerdict.CONTRADICTED, "literal claim is negated in its assertion scope")
        return EvidenceDecision(EvidenceVerdict.UNSUPPORTED, "no supported literal frame binds subject and value")

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
    ) -> EvidenceDecision:
        del action_type
        if not target_names:
            return EvidenceDecision(EvidenceVerdict.UNSUPPORTED, "action has no target")
        for target_name in target_names:
            decision = self.verify_literal_claim(
                evidence=evidence,
                predicate_id="action_state",
                subject_name=target_name,
                object_value=status,
                known_entity_names=known_entity_names,
            )
            if not decision.supported:
                return decision
        for endpoint in (*(dependency_names or ()), *(blocking_names or ())):
            decision = self.verify_entity_mention(evidence=evidence, entity_name=endpoint)
            if not decision.supported:
                return decision
        if actor_name is not None:
            actor_decision = self.verify_entity_mention(evidence=evidence, entity_name=actor_name)
            if not actor_decision.supported:
                return actor_decision
        clause_tokens = word_tokens(_assertion_scope(evidence.source_text, evidence.char_start, evidence.char_end), self._language_code)
        if dependency_names and not _contains_any(clause_tokens, self.dependency_markers, self._language_code):
            return EvidenceDecision(EvidenceVerdict.UNSUPPORTED, "action dependencies lack a language-supported relation marker")
        if blocking_names and not _contains_any(clause_tokens, self.blocking_markers, self._language_code):
            return EvidenceDecision(EvidenceVerdict.UNSUPPORTED, "action blockers lack a language-supported relation marker")
        return EvidenceDecision(EvidenceVerdict.SUPPORTED, "action state and referenced endpoints are source-grounded")

    def inferred_entity_types(self, predicate_id: str) -> tuple[str | None, str | None]:
        return self.relation_type_hints.get(predicate_id, (None, None))

    def _verify_evidence_only_fact(
        self,
        *,
        evidence: SourceEvidence,
        subject_name: str,
        object_value: str,
    ) -> EvidenceDecision:
        quote_tokens = word_tokens(evidence.quote, self._language_code)
        scope_tokens = word_tokens(
            _assertion_scope(evidence.source_text, evidence.char_start, evidence.char_end),
            self._language_code,
        )
        subject_required = normalize_text(subject_name) != "user"
        if subject_required and not phrase_spans(scope_tokens, subject_name, self._language_code):
            return EvidenceDecision(EvidenceVerdict.UNSUPPORTED, "semantic fact subject is absent from evidence")
        if not phrase_spans(quote_tokens, _literal_surface(object_value), self._language_code):
            return EvidenceDecision(EvidenceVerdict.UNSUPPORTED, "semantic fact value is absent from evidence")
        if interval_contains_any(scope_tokens, start=0, end=len(scope_tokens), phrases=self.negations):
            return EvidenceDecision(EvidenceVerdict.CONTRADICTED, "semantic fact assertion scope is negated")
        return EvidenceDecision(EvidenceVerdict.SUPPORTED, "semantic fact endpoints occur in positive evidence")

    def _literal_surfaces(self, predicate_id: str, object_value: str) -> tuple[str, ...]:
        normalized = _literal_surface(object_value)
        aliases = self.literal_value_aliases.get(predicate_id, {}).get(normalized, ())
        return tuple(dict.fromkeys((normalized, *aliases)))

    def _verify_frames(
        self,
        *,
        evidence: SourceEvidence,
        frames: tuple[SemanticFrame, ...],
        subject_name: str,
        object_name: str,
        known_entity_names: tuple[str, ...],
        allow_reversal: bool,
    ) -> EvidenceDecision:
        context = _assertion_scope(evidence.source_text, evidence.char_start, evidence.char_end)
        direct = self._matching_frames(
            text=context,
            quote=evidence.quote,
            frames=frames,
            subject_name=subject_name,
            object_name=object_name,
            known_entity_names=known_entity_names,
        )
        reverse = (
            self._matching_frames(
                text=context,
                quote=evidence.quote,
                frames=frames,
                subject_name=object_name,
                object_name=subject_name,
                known_entity_names=known_entity_names,
            )
            if allow_reversal
            else set()
        )
        if direct and reverse:
            return EvidenceDecision(EvidenceVerdict.AMBIGUOUS, "both argument orders match the evidence")
        if direct:
            match = min(direct, key=lambda item: (item.start, item.end, item.trigger or ""))
            return EvidenceDecision(
                EvidenceVerdict.SUPPORTED,
                "assertion scope uniquely supports the proposed semantic roles",
                matched_trigger=match.trigger,
            )
        if reverse:
            match = min(reverse, key=lambda item: (item.start, item.end, item.trigger or ""))
            return EvidenceDecision(
                EvidenceVerdict.SUPPORTED,
                "assertion scope uniquely supports the reversed semantic roles",
                argument_order=ArgumentOrder.REVERSED,
                matched_trigger=match.trigger,
            )
        tokens = word_tokens(context, self._language_code)
        if interval_contains_any(tokens, start=0, end=len(tokens), phrases=self.negations) or _contains_any(
            tokens, self.denial_markers, self._language_code
        ):
            return EvidenceDecision(EvidenceVerdict.CONTRADICTED, "claim is negated or denied in its assertion scope")
        return EvidenceDecision(EvidenceVerdict.UNSUPPORTED, "no supported semantic frame binds the evidence")

    @property
    def _language_code(self) -> str:
        return sorted(self.language_codes)[0]

    def _matching_frames(
        self,
        *,
        text: str,
        quote: str,
        frames: tuple[SemanticFrame, ...],
        subject_name: str,
        object_name: str,
        known_entity_names: tuple[str, ...],
    ) -> set[_FrameMatch]:
        tokens = word_tokens(text, self._language_code)
        quote_tokens = word_tokens(quote, self._language_code)
        role_spans = {
            "subject": phrase_spans(tokens, subject_name, self._language_code),
            "object": phrase_spans(tokens, object_name, self._language_code),
        }
        quote_role_spans = {
            "subject": phrase_spans(quote_tokens, subject_name, self._language_code),
            "object": phrase_spans(quote_tokens, object_name, self._language_code),
        }
        matches: set[_FrameMatch] = set()
        for frame in frames:
            required_roles = set(frame.roles) - {"trigger"}
            if any(not role_spans[role] or not quote_role_spans[role] for role in required_roles):
                continue
            trigger_values: tuple[str | None, ...] = frame.triggers or (None,)
            for trigger in trigger_values:
                trigger_spans = (
                    phrase_spans(tokens, trigger, self._language_code) if trigger is not None else (None,)
                )
                if trigger is not None and not phrase_spans(quote_tokens, trigger, self._language_code):
                    continue
                span_options: list[tuple[TokenSpan | None, ...]] = []
                for role in frame.roles:
                    span_options.append(trigger_spans if role == "trigger" else role_spans[role])
                for candidate in product(*span_options):
                    ordered = tuple(span for span in candidate if span is not None)
                    if len(ordered) != len(frame.roles) or not _strictly_ordered(ordered):
                        continue
                    if not _gaps_allowed(tokens, ordered, frame.gap_allowlists):
                        continue
                    interval = TokenSpan(
                        start=min(span.start for span in ordered),
                        end=max(span.end for span in ordered),
                    )
                    scope_start, scope_end = _semantic_scope_bounds(
                        tokens=tokens,
                        interval=interval,
                        boundaries=self.clause_boundaries,
                        language=self._language_code,
                    )
                    if interval_contains_any(
                        tokens,
                        start=interval.start,
                        end=interval.end,
                        phrases=self.negations,
                    ) or _contains_phrases(
                        tokens,
                        start=scope_start,
                        end=interval.start,
                        phrases=self.denial_markers,
                        language=self._language_code,
                    ):
                        continue
                    selected = tuple(
                        span
                        for role, span in zip(frame.roles, ordered, strict=True)
                        if role in {"subject", "object"}
                    )
                    if has_intervening_entity(
                        tokens=tokens,
                        language=self._language_code,
                        interval=interval,
                        selected=selected,
                        known_entity_names=known_entity_names,
                    ):
                        continue
                    matches.add(_FrameMatch(interval.start, interval.end, normalize_text(trigger) if trigger else None))
        return matches


def _assertion_scope(source_text: str, char_start: int, char_end: int) -> str:
    """Return the punctuation-bounded assertion containing the evidence span."""

    separators = frozenset(".!?;\n")
    left = char_start
    while left > 0 and source_text[left - 1] not in separators:
        left -= 1
    right = char_end
    while right < len(source_text) and source_text[right] not in separators:
        right += 1
    return source_text[left:right].strip()


def _strictly_ordered(spans: tuple[TokenSpan, ...]) -> bool:
    return all(left.end <= right.start for left, right in zip(spans[:-1], spans[1:], strict=True))


def _gaps_allowed(
    tokens: tuple[str, ...],
    spans: tuple[TokenSpan, ...],
    allowlists: tuple[frozenset[str] | None, ...],
) -> bool:
    """Require configured frame gaps to contain only language-owned bridge tokens."""

    return all(
        allowed is None or all(token in allowed for token in tokens[left.end : right.start])
        for left, right, allowed in zip(spans[:-1], spans[1:], allowlists, strict=True)
    )


def _semantic_scope_bounds(
    *,
    tokens: tuple[str, ...],
    interval: TokenSpan,
    boundaries: tuple[str, ...],
    language: str,
) -> tuple[int, int]:
    spans = sorted(
        (span for phrase in boundaries for span in phrase_spans(tokens, phrase, language)),
        key=lambda span: (span.start, span.end),
    )
    start = max((span.end for span in spans if span.end <= interval.start), default=0)
    end = min((span.start for span in spans if span.start >= interval.end), default=len(tokens))
    return start, end


def _literal_surface(value: str) -> str:
    return " ".join(value.strip().casefold().replace("_", " ").replace("-", " ").split())


def _starts_with_any(tokens: tuple[str, ...], phrases: tuple[str, ...], language: str) -> bool:
    return any(any(span.start == 0 for span in phrase_spans(tokens, phrase, language)) for phrase in phrases)


def _contains_any(tokens: tuple[str, ...], phrases: tuple[str, ...], language: str) -> bool:
    return any(phrase_spans(tokens, phrase, language) for phrase in phrases)


def _contains_phrases(
    tokens: tuple[str, ...],
    *,
    start: int,
    end: int,
    phrases: tuple[str, ...],
    language: str,
) -> bool:
    return any(
        span.start >= start and span.end <= end
        for phrase in phrases
        for span in phrase_spans(tokens, phrase, language)
    )
