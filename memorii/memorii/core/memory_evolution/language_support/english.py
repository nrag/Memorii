"""English semantic evidence capabilities for memory extraction."""

from __future__ import annotations

import re

from memorii.core.memory_evolution.language_support.base import (
    FrameLanguageCapabilities,
    ModalityLexicon,
    SemanticFrame,
)
from memorii.core.memory_evolution.language_support.contracts import RuleActionCandidate, RuleFactCandidate


class EnglishExtractionCapabilities(FrameLanguageCapabilities):
    capability_id = "memory-extraction/en@1"
    language_codes = frozenset({"en", "eng"})
    negations = frozenset({("not",), ("never",), ("no",), ("neither",), ("nor",)})
    relation_type_hints = {
        "owner": (None, "person"),
        "approver": (None, "person"),
        "api_owner": (None, "person"),
        "dependency": (None, None),
    }
    modality_lexicon = ModalityLexicon(
        question_prefixes=(
            "who",
            "what",
            "when",
            "where",
            "why",
            "how",
            "is",
            "are",
            "does",
            "do",
            "did",
            "can",
            "could",
            "should",
        ),
        hypothetical_markers=("suppose", "hypothetically", "imagine", "if", "what if", "would be", "could be"),
        quoted_or_pasted_markers=("pasted", "paste", "here is a doc", "here's a doc", "document"),
        correction_markers=("correction", "correcting", "actually", "instead", "should be"),
        third_party_markers=(
            "says",
            "said",
            "according to",
            "the doc says",
            "the transcript says",
            "manager says",
            "reportedly",
            "allegedly",
            "apparently",
        ),
        instruction_prefixes=("please", "can you", "could you", "remember to", "do not", "don't"),
    )
    denial_markers = (
        "false that",
        "it is false that",
        "not true that",
        "it is not true that",
        "denies that",
        "denied that",
    )
    clause_boundaries = ("but", "however", "instead")
    dependency_markers = ("depends on", "requires", "is dependent on", "dependency is")
    blocking_markers = ("blocked by", "is blocked by", "blocking")
    entity_name_suffixes = ("'s", "’s")
    _rule_fact_patterns = (
        (
            "api_owner",
            r"(?P<subject>[A-Z][A-Za-z0-9 _:-]+?)\s+(?:API\s+owner|api\s+owner)\s*(?:is|:|=)\s*(?P<value>[A-Z][A-Za-z0-9 _:-]+)",
        ),
        (
            "approver",
            r"(?P<subject>[A-Z][A-Za-z0-9 _:-]+?)\s+approver\s*(?:is|:|=)\s*(?P<value>[A-Z][A-Za-z0-9 _:-]+)",
        ),
        (
            "owner",
            r"(?P<subject>[A-Z][A-Za-z0-9 _:-]+?)\s+owner\s*(?:is|:|=)\s*(?P<value>[A-Z][A-Za-z0-9 _:-]+)",
        ),
        (
            "owner",
            r"(?P<subject>[A-Z][A-Za-z0-9 _:-]+?)\s+ownership\s+(?:in\s+\w+\s+)?(?:belonged to|belongs to)\s+(?P<value>[A-Z][A-Za-z0-9 _:-]+)",
        ),
        (
            "owner",
            r"(?P<value>[A-Z][A-Za-z0-9 _:-]+?)\s+owns\s+(?P<subject>[A-Z][A-Za-z0-9 _:-]+?)(?=\s+for now|\s+currently|[.,;]|$)",
        ),
        (
            "owner",
            r"(?P<subject>[A-Z][A-Za-z0-9 _:-]+?)\s+is\s+(?:the\s+)?[A-Za-z0-9 _:-]*?\b(?:project|service|task|workstream)\b\s+owned\s+by\s+(?P<value>[A-Z][A-Za-z0-9 _:-]+)",
        ),
        (
            "entity_type",
            r"(?P<subject>[A-Z][A-Za-z0-9 _:-]+?)\s+is\s+(?:the\s+)?[A-Za-z0-9 _:-]*?\b(?P<value>project|service|task|incident|document|preference)\b",
        ),
        (
            "status",
            r"(?P<subject>[A-Z][A-Za-z0-9 _:-]+?)\s+(?:state|status)\s*(?:is|:|=)\s*(?P<value>failed|succeeded|blocked|running|done|active|inactive)",
        ),
        (
            "status",
            r"(?P<subject>[A-Z][A-Za-z0-9 _:-]+?)\s+(?:deploy|deployment)\s+(?P<value>failed|succeeded)",
        ),
        (
            "preference",
            r"(?:prefers|preference is|style is)\s+(?P<value>[a-z][A-Za-z0-9 _:-]+)",
        ),
    )
    _rule_action_pattern = re.compile(
        r"\b(?P<target>[A-Z][A-Za-z0-9 _:-]+?)\s+(?P<status>started|blocked|resumed|abandoned|completed|failed|succeeded)\b",
        re.IGNORECASE,
    )

    def rule_fact_candidates(self, text: str) -> tuple[RuleFactCandidate, ...]:
        candidates: list[RuleFactCandidate] = []
        seen: set[tuple[str, str, str, str]] = set()
        for predicate_id, pattern in self._rule_fact_patterns:
            for match in re.finditer(pattern, text):
                subject = _clean_rule_value(match.groupdict().get("subject") or "user")
                object_value = _clean_rule_value(match.group("value"))
                quote = match.group(0).strip(" .")
                key = (predicate_id, subject.casefold(), object_value.casefold(), quote.casefold())
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(
                    RuleFactCandidate(
                        predicate_id=predicate_id,
                        subject_name=subject,
                        object_value=object_value,
                        quote=quote,
                    )
                )
        return tuple(candidates)

    def rule_action_candidates(self, text: str) -> tuple[RuleActionCandidate, ...]:
        match = self._rule_action_pattern.search(text)
        if match is None:
            return ()
        return (
            RuleActionCandidate(
                target_name=match.group("target").strip(),
                status=match.group("status").casefold(),
                quote=match.group(0),
            ),
        )
    relation_frames = {
        "owner": (
            SemanticFrame(
                ("object", "trigger", "subject"),
                ("owns", "is owner of", "is the owner of", "is responsible for"),
            ),
            SemanticFrame(
                ("subject", "trigger", "object"),
                ("owner is", "owner equals", "is owned by", "owner and api owner are"),
            ),
            SemanticFrame(
                ("subject", "trigger", "object"),
                ("owner",),
                gap_allowlists=(frozenset(), frozenset()),
            ),
            SemanticFrame(("trigger", "subject", "object"), ("owner of",)),
            SemanticFrame(
                ("object", "subject", "trigger"),
                ("owner",),
                gap_allowlists=(
                    frozenset(
                        {
                            "a",
                            "an",
                            "acting",
                            "current",
                            "is",
                            "new",
                            "now",
                            "primary",
                            "remains",
                            "the",
                            "temporary",
                            "was",
                        }
                    ),
                    frozenset(),
                ),
            ),
        ),
        "approver": (
            SemanticFrame(("object", "trigger", "subject"), ("approves", "is approver for", "is the approver for")),
            SemanticFrame(("subject", "trigger", "object"), ("approver is", "is approved by")),
            SemanticFrame(
                ("subject", "trigger", "object"),
                ("approver",),
                gap_allowlists=(frozenset(), frozenset()),
            ),
            SemanticFrame(("trigger", "subject", "object"), ("approver for", "approver of")),
        ),
        "api_owner": (
            SemanticFrame(
                ("object", "trigger", "subject"),
                ("owns the api for", "is api owner for", "is the api owner for"),
            ),
            SemanticFrame(
                ("subject", "trigger", "object"),
                ("api owner is", "owner and api owner are"),
            ),
            SemanticFrame(
                ("subject", "trigger", "object"),
                ("api owner",),
                gap_allowlists=(frozenset(), frozenset()),
            ),
        ),
        "dependency": (
            SemanticFrame(
                ("subject", "trigger", "object"), ("depends on", "requires", "is dependent on", "dependency is")
            ),
            SemanticFrame(("object", "trigger", "subject"), ("supports", "is required by")),
        ),
    }
    identity_frames = {
        "alias_of": (
            SemanticFrame(
                ("object", "trigger", "subject"), ("also called", "is also called", "also known as", "is also known as")
            ),
            SemanticFrame(("subject", "trigger", "object"), ("is an alias for", "is an alias of")),
        ),
        "same_as": (
            SemanticFrame(
                ("subject", "trigger", "object"), ("is the same as", "is identical to", "refers to the same entity as")
            ),
        ),
        "split_from": (
            SemanticFrame(
                ("subject", "trigger", "object"), ("split from", "was split from", "branched from", "was branched from")
            ),
        ),
        "merged_into": (
            SemanticFrame(
                ("subject", "trigger", "object"),
                ("merged into", "was merged into", "consolidated into", "was consolidated into"),
            ),
        ),
    }
    entity_type_frames = {
        entity_type: (
            SemanticFrame(("subject", "trigger", "object"), ("is a", "is an", "is the", "is")),
            SemanticFrame(("trigger", "subject", "object"), ("the",)),
        )
        for entity_type in ("project", "person", "service", "task", "preference")
    }
    literal_frames = {
        "status": (
            SemanticFrame(
                ("subject", "trigger", "object"),
                ("status is", "status equals", "is", "remains", "became", "deploy", "deployment"),
            ),
            SemanticFrame(("subject", "object"), gap_allowlists=(frozenset(),)),
        ),
        "action_state": (
            SemanticFrame(("subject", "trigger", "object"), ("status is", "state is", "is", "remains", "became")),
            SemanticFrame(("subject", "object")),
        ),
        "preference": (
            SemanticFrame(("subject", "trigger", "object"), ("prefers", "preference is", "likes")),
            SemanticFrame(("trigger", "object"), ("prefers", "preference is", "likes")),
        ),
        "belief": (
            SemanticFrame(("subject", "trigger", "object"), ("believes", "belief is", "hypothesis is", "root cause is")),
            SemanticFrame(("trigger", "object"), ("belief is", "hypothesis is", "root cause is")),
        ),
        "correction": (
            SemanticFrame(("subject", "trigger", "object"), ("correction is", "corrected to", "should be", "actually is")),
            SemanticFrame(("trigger", "object"), ("correction is", "corrected to", "should be")),
        ),
    }
    literal_value_aliases = {
        "status": {
            "in progress": ("in_progress", "progressing"),
            "started": ("in progress", "in_progress"),
        },
        "action_state": {
            "in progress": ("in_progress", "progressing"),
            "started": ("in progress", "in_progress"),
        },
    }


def _clean_rule_value(value: str) -> str:
    cleaned = re.sub(r"^(?:the|a|an)\s+", "", value.strip(" .:"), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+for now$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+currently$", "", cleaned, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", cleaned).strip(" .:")
